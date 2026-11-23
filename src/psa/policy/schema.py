"""Policy-set schema. Policies are data: a closed set of operators, no expressions."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from psa.domain import ActionName, DecisionOutcome, ReasonCode

Scalar = int | str | bool
MAX_CONDITION_DEPTH = 4
FACT_NAME = r"[a-z_]+(?:\.[a-z_0-9]+)+"
PLACEHOLDER = re.compile(r"\{(" + FACT_NAME + r")\}")
"""Message templates may reference facts as {fact.name}; nothing else is interpolated."""


class Op(StrEnum):
    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"


ORDERING_OPS: frozenset[Op] = frozenset({Op.LT, Op.LTE, Op.GT, Op.GTE})
MEMBERSHIP_OPS: frozenset[Op] = frozenset({Op.IN, Op.NOT_IN})


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Predicate(_Model):
    """Leaf condition: compare a fact to a literal (`value`) or to another fact (`value_from`)."""

    fact: str = Field(pattern=r"^[a-z_]+(\.[a-z_0-9]+)+$")
    op: Op
    value: Scalar | list[Scalar] | None = None
    value_from: str | None = Field(default=None, pattern=r"^[a-z_]+(\.[a-z_0-9]+)+$")

    @model_validator(mode="after")
    def _one_operand(self) -> Predicate:
        if (self.value is None) == (self.value_from is None):
            raise ValueError("exactly one of 'value' or 'value_from' is required")
        if self.op in MEMBERSHIP_OPS:
            if self.value_from is not None or not isinstance(self.value, list):
                raise ValueError(f"op '{self.op}' requires a list 'value'")
        elif isinstance(self.value, list):
            raise ValueError(f"op '{self.op}' does not accept a list")
        if self.op is Op.EXISTS and not isinstance(self.value, bool):
            raise ValueError("op 'exists' requires value: true|false")
        return self


class AllOf(_Model):
    all: list[Condition] = Field(min_length=1)


class AnyOf(_Model):
    any: list[Condition] = Field(min_length=1)


class NotOf(_Model):
    not_: Condition = Field(alias="not")

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


Condition = Annotated[Predicate | AllOf | AnyOf | NotOf, Field(union_mode="smart")]


class Outcome(_Model):
    decision: DecisionOutcome
    reason: ReasonCode | None = None
    message: str | None = Field(
        default=None,
        max_length=300,
        description="Customer-safe text; may reference facts as {fact.name}",
    )

    @model_validator(mode="after")
    def _reason_for_restrictions(self) -> Outcome:
        if self.decision is not DecisionOutcome.ALLOW and self.reason is None:
            raise ValueError(f"decision {self.decision} requires a 'reason' code")
        return self


ALLOW = Outcome(decision=DecisionOutcome.ALLOW)


class Rule(_Model):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    description: str = Field(min_length=1, max_length=300)
    applies_to: list[ActionName] = Field(min_length=1)
    only_if: Condition | None = Field(
        default=None, description="Guard: if false the rule is skipped for this intent"
    )
    when: Condition | None = Field(
        default=None, description="Omit for an unconditional rule whose result is 'then'"
    )
    then: Outcome = ALLOW
    else_: Outcome = Field(default=ALLOW, alias="else")

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _well_formed(self) -> Rule:
        if self.when is None:
            if "else" in self.model_fields_set or "else_" in self.model_fields_set:
                raise ValueError("an unconditional rule (no 'when') cannot have 'else'")
            return self
        if (
            self.then.decision is DecisionOutcome.ALLOW
            and self.else_.decision is DecisionOutcome.ALLOW
        ):
            raise ValueError(
                "rule can never restrict: both 'then' and 'else' are ALLOW "
                "(omit 'when' for an explicit unconditional allow)"
            )
        return self


class PolicySet(_Model):
    schema_version: Literal[1] = 1
    policy_set: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    version: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}-\d+$")
    description: str = ""
    rules: list[Rule] = Field(min_length=1)

    def rules_for(self, action: ActionName) -> list[Rule]:
        return [rule for rule in self.rules if action in rule.applies_to]


AllOf.model_rebuild()
AnyOf.model_rebuild()
NotOf.model_rebuild()
Rule.model_rebuild()
