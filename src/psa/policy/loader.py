"""Load and validate policy sets from YAML.

Validation goes beyond the schema: fact names, fact/action applicability, operator/type
compatibility, closed vocabularies, message placeholders and action coverage. Every error
names the file, the rule ID and the offending field.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from psa.domain import ActionName
from psa.policy.facts import FACTS, FactSpec, FactType
from psa.policy.schema import (
    MAX_CONDITION_DEPTH,
    MEMBERSHIP_OPS,
    ORDERING_OPS,
    PLACEHOLDER,
    AllOf,
    AnyOf,
    Condition,
    NotOf,
    Op,
    PolicySet,
    Predicate,
    Rule,
)


@dataclass(frozen=True)
class PolicyIssue:
    path: str
    rule_id: str | None
    location: str
    message: str

    def __str__(self) -> str:
        where = f"rule {self.rule_id}" if self.rule_id else "policy"
        loc = f" [{self.location}]" if self.location else ""
        return f"{self.path}: {where}{loc}: {self.message}"


class PolicyLoadError(Exception):
    def __init__(self, issues: list[PolicyIssue]) -> None:
        self.issues = issues
        super().__init__("\n".join(str(issue) for issue in issues))


# ---------------------------------------------------------------------------
# Semantic validation
# ---------------------------------------------------------------------------


def _type_ok(spec: FactSpec, value: object) -> bool:
    match spec.type:
        case FactType.BOOL:
            return isinstance(value, bool)
        case FactType.INT:
            return isinstance(value, int) and not isinstance(value, bool)
        case FactType.STR:
            return isinstance(value, str)


def _depth(cond: Condition) -> int:
    if isinstance(cond, Predicate):
        return 1
    if isinstance(cond, AllOf):
        return 1 + max(_depth(c) for c in cond.all)
    if isinstance(cond, AnyOf):
        return 1 + max(_depth(c) for c in cond.any)
    return 1 + _depth(cond.not_)


def _predicates(cond: Condition, loc: str) -> Iterator[tuple[Predicate, str]]:
    if isinstance(cond, Predicate):
        yield cond, loc
    elif isinstance(cond, AllOf):
        for i, child in enumerate(cond.all):
            yield from _predicates(child, f"{loc}.all[{i}]")
    elif isinstance(cond, AnyOf):
        for i, child in enumerate(cond.any):
            yield from _predicates(child, f"{loc}.any[{i}]")
    elif isinstance(cond, NotOf):  # pyright: ignore[reportUnnecessaryIsInstance]
        yield from _predicates(cond.not_, f"{loc}.not")


@dataclass
class _Checker:
    path: str
    issues: list[PolicyIssue] = field(default_factory=list[PolicyIssue])

    def add(self, rule: Rule | None, loc: str, message: str) -> None:
        self.issues.append(PolicyIssue(self.path, rule.id if rule else None, loc, message))

    def fact(self, rule: Rule, name: str, loc: str) -> FactSpec | None:
        spec = FACTS.get(name)
        if spec is None:
            self.add(rule, loc, f"unknown fact '{name}'")
            return None
        if spec.actions is not None:
            unsupported = sorted(a.value for a in rule.applies_to if a not in spec.actions)
            if unsupported:
                self.add(
                    rule,
                    loc,
                    f"fact '{name}' is not available for action(s): {', '.join(unsupported)}",
                )
        return spec

    def predicate(self, rule: Rule, pred: Predicate, loc: str) -> None:
        spec = self.fact(rule, pred.fact, f"{loc}.fact")
        if spec is None or pred.op is Op.EXISTS:
            return
        if pred.op in ORDERING_OPS and spec.type is not FactType.INT:
            self.add(
                rule, f"{loc}.op", f"op '{pred.op}' needs an int fact; '{spec.name}' is {spec.type}"
            )
        if pred.value_from is not None:
            other = self.fact(rule, pred.value_from, f"{loc}.value_from")
            if other is not None and other.type is not spec.type:
                self.add(
                    rule,
                    f"{loc}.value_from",
                    f"type mismatch: '{spec.name}' is {spec.type}, '{other.name}' is {other.type}",
                )
            return
        values: list[object] = list(pred.value) if isinstance(pred.value, list) else [pred.value]
        if pred.op in MEMBERSHIP_OPS and not values:
            self.add(rule, f"{loc}.value", "membership list must not be empty")
        for value in values:
            if not _type_ok(spec, value):
                self.add(
                    rule, f"{loc}.value", f"{value!r} is not a valid {spec.type} for '{spec.name}'"
                )
            elif spec.allowed_values is not None and value not in spec.allowed_values:
                allowed = ", ".join(sorted(spec.allowed_values))
                self.add(
                    rule,
                    f"{loc}.value",
                    f"{value!r} not in allowed values for '{spec.name}': {allowed}",
                )

    def condition(self, rule: Rule, cond: Condition, loc: str) -> None:
        if _depth(cond) > MAX_CONDITION_DEPTH:
            self.add(rule, loc, f"condition nesting exceeds max depth {MAX_CONDITION_DEPTH}")
        for pred, pred_loc in _predicates(cond, loc):
            self.predicate(rule, pred, pred_loc)

    def rule(self, rule: Rule) -> None:
        if rule.only_if is not None:
            self.condition(rule, rule.only_if, "only_if")
        if rule.when is not None:
            self.condition(rule, rule.when, "when")
        for branch, outcome in (("then", rule.then), ("else", rule.else_)):
            if outcome.message:
                for name in PLACEHOLDER.findall(outcome.message):
                    self.fact(rule, name, f"{branch}.message")

    def policy(self, policy: PolicySet) -> None:
        seen: set[str] = set()
        for rule in policy.rules:
            if rule.id in seen:
                self.add(rule, "id", "duplicate rule id")
            seen.add(rule.id)
            if len(set(rule.applies_to)) != len(rule.applies_to):
                self.add(rule, "applies_to", "duplicate action")
            self.rule(rule)
        covered = {action for rule in policy.rules for action in rule.applies_to}
        for action in ActionName:
            if action not in covered:
                self.add(
                    None,
                    "rules",
                    f"no rule applies to action '{action}' (it would always be denied)",
                )


def validate_policy(policy: PolicySet, path: str = "<memory>") -> list[PolicyIssue]:
    checker = _Checker(path)
    checker.policy(policy)
    return checker.issues


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _rule_label(raw: Mapping[str, Any], index: int) -> str:
    rules: object = raw.get("rules")
    if isinstance(rules, list) and index < len(rules):  # pyright: ignore[reportUnknownArgumentType]
        candidate: object = rules[index]  # pyright: ignore[reportUnknownVariableType]
        if isinstance(candidate, dict) and "id" in candidate:
            return str(candidate["id"])  # pyright: ignore[reportUnknownArgumentType]
    return f"#{index}"


def _schema_issues(path: str, raw: Mapping[str, Any], error: ValidationError) -> list[PolicyIssue]:
    issues: list[PolicyIssue] = []
    for err in error.errors():
        loc = list(err["loc"])
        rule_id: str | None = None
        if len(loc) >= 2 and loc[0] == "rules" and isinstance(loc[1], int):
            rule_id = _rule_label(raw, loc[1])
            loc = loc[2:]
        issues.append(PolicyIssue(path, rule_id, ".".join(str(p) for p in loc), err["msg"]))
    return issues


def parse_policy(text: str, path: str = "<memory>") -> PolicySet:
    try:
        raw: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PolicyLoadError([PolicyIssue(path, None, "", f"invalid YAML: {exc}")]) from exc
    if not isinstance(raw, dict):
        raise PolicyLoadError([PolicyIssue(path, None, "", "top level must be a mapping")])
    try:
        policy = PolicySet.model_validate(raw)
    except ValidationError as exc:
        raise PolicyLoadError(_schema_issues(path, raw, exc)) from exc  # pyright: ignore[reportUnknownArgumentType]
    issues = validate_policy(policy, path)
    if issues:
        raise PolicyLoadError(issues)
    return policy


def load_policy(path: Path) -> PolicySet:
    policy = parse_policy(path.read_text(encoding="utf-8"), str(path))
    if path.stem != policy.version or path.parent.name != policy.policy_set:
        raise PolicyLoadError(
            [
                PolicyIssue(
                    str(path),
                    None,
                    "",
                    f"file must live at <root>/{policy.policy_set}/{policy.version}.yaml",
                )
            ]
        )
    return policy


def _version_key(version: str) -> tuple[str, int]:
    date, _, revision = version.partition("-")
    return date, int(revision)


class PolicyRegistry:
    """All policy versions on disk, addressable by (policy_set, version)."""

    def __init__(self, policies: list[PolicySet]) -> None:
        self._by_key: dict[tuple[str, str], PolicySet] = {}
        for policy in policies:
            self._by_key[(policy.policy_set, policy.version)] = policy

    @classmethod
    def from_dir(cls, root: Path) -> PolicyRegistry:
        files = sorted(root.glob("*/*.yaml"))
        policies: list[PolicySet] = []
        issues: list[PolicyIssue] = []
        for file in files:
            try:
                policies.append(load_policy(file))
            except PolicyLoadError as exc:
                issues.extend(exc.issues)
        if issues:
            raise PolicyLoadError(issues)
        if not policies:
            raise PolicyLoadError([PolicyIssue(str(root), None, "", "no policy files found")])
        return cls(policies)

    def get(self, policy_set: str, version: str) -> PolicySet:
        try:
            return self._by_key[(policy_set, version)]
        except KeyError:
            raise KeyError(f"unknown policy {policy_set}@{version}") from None

    def latest(self, policy_set: str) -> PolicySet:
        versions = [p for (name, _), p in self._by_key.items() if name == policy_set]
        if not versions:
            raise KeyError(f"unknown policy set {policy_set}")
        return max(versions, key=lambda p: _version_key(p.version))

    def all(self) -> list[PolicySet]:
        return sorted(self._by_key.values(), key=lambda p: (p.policy_set, _version_key(p.version)))
