"""Every validation rule in the loader rejects bad policies with a precise location."""

from __future__ import annotations

from pathlib import Path

import pytest

from psa.policy import PolicyLoadError, PolicyRegistry, load_policy, parse_policy

HEADER = """
schema_version: 1
policy_set: test-set
version: "2026.11.21-1"
rules:
  - id: BASELINE_ALLOW
    description: covers every action
    applies_to: [issue_refund, issue_store_credit, cancel_order, update_address,
                 create_ticket, escalate_to_human, schedule_follow_up]
"""


def _policy(rule_yaml: str = "") -> str:
    return HEADER + rule_yaml


def _issues(text: str) -> list[str]:
    with pytest.raises(PolicyLoadError) as info:
        parse_policy(text, "test.yaml")
    return [str(issue) for issue in info.value.issues]


def test_minimal_policy_loads() -> None:
    policy = parse_policy(_policy())
    assert policy.policy_set == "test-set"
    assert len(policy.rules) == 1


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        pytest.param(
            """
  - id: BAD_FACT
    description: x
    applies_to: [issue_refund]
    when: { fact: order.colour, op: eq, value: red }
    else: { decision: DENY, reason: ORDER_NOT_FOUND }
""",
            "rule BAD_FACT [when.fact]: unknown fact 'order.colour'",
            id="unknown-fact",
        ),
        pytest.param(
            """
  - id: WRONG_ACTION
    description: x
    applies_to: [escalate_to_human]
    when: { fact: intent.amount_cents, op: gt, value: 1 }
    then: { decision: DENY, reason: HIGH_VALUE_REFUND }
""",
            "fact 'intent.amount_cents' is not available for action(s): escalate_to_human",
            id="fact-not-available-for-action",
        ),
        pytest.param(
            """
  - id: ORDERING_ON_BOOL
    description: x
    applies_to: [issue_refund]
    when: { fact: session.identity_verified, op: gt, value: 1 }
    then: { decision: DENY, reason: IDENTITY_NOT_VERIFIED }
""",
            "op 'gt' needs an int fact",
            id="ordering-op-on-bool",
        ),
        pytest.param(
            """
  - id: TYPE_MISMATCH
    description: x
    applies_to: [issue_refund]
    when: { fact: order.days_since_delivery, op: lte, value: "30" }
    else: { decision: DENY, reason: OUTSIDE_RETURN_WINDOW }
""",
            "'30' is not a valid int for 'order.days_since_delivery'",
            id="value-type-mismatch",
        ),
        pytest.param(
            """
  - id: BOOL_AS_INT
    description: x
    applies_to: [issue_refund]
    when: { fact: order.days_since_delivery, op: lte, value: true }
    else: { decision: DENY, reason: OUTSIDE_RETURN_WINDOW }
""",
            "True is not a valid int",
            id="bool-is-not-int",
        ),
        pytest.param(
            """
  - id: TYPO_STATUS
    description: x
    applies_to: [issue_refund]
    when: { fact: order.status, op: in, value: [delivred] }
    else: { decision: DENY, reason: ORDER_NOT_DELIVERED }
""",
            "'delivred' not in allowed values for 'order.status'",
            id="closed-vocabulary",
        ),
        pytest.param(
            """
  - id: VALUE_FROM_MISMATCH
    description: x
    applies_to: [issue_refund]
    when: { fact: intent.amount_cents, op: eq, value_from: order.status }
    else: { decision: DENY, reason: AMOUNT_EXCEEDS_REFUNDABLE }
""",
            "type mismatch: 'intent.amount_cents' is int, 'order.status' is str",
            id="value-from-type-mismatch",
        ),
        pytest.param(
            """
  - id: EMPTY_IN
    description: x
    applies_to: [issue_refund]
    when: { fact: order.status, op: in, value: [] }
    else: { decision: DENY, reason: ORDER_NOT_DELIVERED }
""",
            "membership list must not be empty",
            id="empty-membership",
        ),
        pytest.param(
            """
  - id: TOO_DEEP
    description: x
    applies_to: [issue_refund]
    when:
      all:
        - any:
            - all:
                - not: { fact: session.identity_verified, op: eq, value: true }
    else: { decision: DENY, reason: IDENTITY_NOT_VERIFIED }
""",
            "condition nesting exceeds max depth 4",
            id="max-depth",
        ),
        pytest.param(
            """
  - id: BASELINE_ALLOW
    description: duplicate
    applies_to: [issue_refund]
    then: { decision: ALLOW }
""",
            "rule BASELINE_ALLOW [id]: duplicate rule id",
            id="duplicate-rule-id",
        ),
        pytest.param(
            """
  - id: DUP_ACTION
    description: x
    applies_to: [issue_refund, issue_refund]
    then: { decision: ALLOW }
""",
            "rule DUP_ACTION [applies_to]: duplicate action",
            id="duplicate-action",
        ),
        pytest.param(
            """
  - id: BAD_PLACEHOLDER
    description: x
    applies_to: [issue_refund]
    when: { fact: session.identity_verified, op: eq, value: true }
    else: { decision: DENY, reason: IDENTITY_NOT_VERIFIED, message: "Hi {customer.email}" }
""",
            "rule BAD_PLACEHOLDER [else.message]: unknown fact 'customer.email'",
            id="unknown-placeholder",
        ),
    ],
)
def test_semantic_rejections(rule: str, expected: str) -> None:
    issues = _issues(_policy(rule))
    assert any(expected in issue for issue in issues), issues
    assert all(issue.startswith("test.yaml:") for issue in issues)


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        pytest.param(
            """
  - id: NEVER_RESTRICTS
    description: x
    applies_to: [issue_refund]
    when: { fact: session.identity_verified, op: eq, value: true }
""",
            "can never restrict",
            id="both-branches-allow",
        ),
        pytest.param(
            """
  - id: NO_REASON
    description: x
    applies_to: [issue_refund]
    when: { fact: session.identity_verified, op: eq, value: true }
    else: { decision: DENY }
""",
            "requires a 'reason' code",
            id="restriction-without-reason",
        ),
        pytest.param(
            """
  - id: UNCONDITIONAL_ELSE
    description: x
    applies_to: [issue_refund]
    then: { decision: ALLOW }
    else: { decision: DENY, reason: ORDER_NOT_FOUND }
""",
            "cannot have 'else'",
            id="unconditional-with-else",
        ),
        pytest.param(
            """
  - id: BAD_REASON
    description: x
    applies_to: [issue_refund]
    when: { fact: session.identity_verified, op: eq, value: true }
    else: { decision: DENY, reason: BECAUSE_I_SAID_SO }
""",
            "rule BAD_REASON",
            id="unknown-reason-code",
        ),
        pytest.param(
            """
  - id: BAD_ACTION
    description: x
    applies_to: [launch_rocket]
    then: { decision: ALLOW }
""",
            "rule BAD_ACTION",
            id="unknown-action",
        ),
        pytest.param(
            """
  - id: EXPRESSION
    description: x
    applies_to: [issue_refund]
    when: "order.days_since_delivery <= 30"
    else: { decision: DENY, reason: OUTSIDE_RETURN_WINDOW }
""",
            "rule EXPRESSION",
            id="string-expression-rejected",
        ),
        pytest.param(
            """
  - id: EXTRA_KEY
    description: x
    applies_to: [issue_refund]
    then: { decision: ALLOW }
    priority: 10
""",
            "rule EXTRA_KEY [priority]",
            id="unknown-key",
        ),
        pytest.param(
            """
  - id: BOTH_OPERANDS
    description: x
    applies_to: [issue_refund]
    when:
      fact: intent.amount_cents
      op: lte
      value: 1
      value_from: order.amount_refundable_cents
    else: { decision: DENY, reason: AMOUNT_EXCEEDS_REFUNDABLE }
""",
            "exactly one of 'value' or 'value_from'",
            id="value-and-value-from",
        ),
    ],
)
def test_schema_rejections(rule: str, expected: str) -> None:
    issues = _issues(_policy(rule))
    assert any(expected in issue for issue in issues), issues


def test_uncovered_action_rejected() -> None:
    text = """
schema_version: 1
policy_set: test-set
version: "2026.11.21-1"
rules:
  - id: ONLY_ESCALATION
    description: x
    applies_to: [escalate_to_human]
    then: { decision: ALLOW }
"""
    issues = _issues(text)
    assert any("no rule applies to action 'issue_refund'" in i for i in issues)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("rules: [", "invalid YAML"),
        ("- just\n- a list\n", "top level must be a mapping"),
        (_policy().replace('"2026.11.21-1"', '"v1"'), "[version]"),
        (_policy().replace("schema_version: 1", "schema_version: 2"), "[schema_version]"),
    ],
)
def test_document_level_rejections(text: str, expected: str) -> None:
    issues = _issues(text)
    assert any(expected in i for i in issues), issues


def test_file_location_must_match_content(tmp_path: Path) -> None:
    wrong = tmp_path / "other-set" / "2026.11.21-1.yaml"
    wrong.parent.mkdir()
    wrong.write_text(_policy(), encoding="utf-8")
    with pytest.raises(PolicyLoadError, match="must live at"):
        load_policy(wrong)


def test_registry_latest_and_lookup(tmp_path: Path) -> None:
    for version in ("2026.11.21-1", "2026.11.21-10", "2026.11.21-2"):
        path = tmp_path / "test-set" / f"{version}.yaml"
        path.parent.mkdir(exist_ok=True)
        path.write_text(_policy().replace("2026.11.21-1", version), encoding="utf-8")
    registry = PolicyRegistry.from_dir(tmp_path)
    assert registry.latest("test-set").version == "2026.11.21-10"  # numeric, not lexical
    assert registry.get("test-set", "2026.11.21-2").version == "2026.11.21-2"
    with pytest.raises(KeyError):
        registry.get("test-set", "2099.01.01-1")


def test_registry_reports_all_broken_files(tmp_path: Path) -> None:
    for name in ("a-set", "b-set"):
        path = tmp_path / name / "2026.11.21-1.yaml"
        path.parent.mkdir()
        path.write_text("rules: [", encoding="utf-8")
    with pytest.raises(PolicyLoadError) as info:
        PolicyRegistry.from_dir(tmp_path)
    assert len(info.value.issues) == 2


def test_empty_registry_rejected(tmp_path: Path) -> None:
    with pytest.raises(PolicyLoadError, match="no policy files found"):
        PolicyRegistry.from_dir(tmp_path)


def test_repo_policies_are_valid() -> None:
    root = Path(__file__).resolve().parents[2] / "policies"
    registry = PolicyRegistry.from_dir(root)
    assert {p.version for p in registry.all()} >= {"2026.11.21-1", "2026.11.21-2"}
