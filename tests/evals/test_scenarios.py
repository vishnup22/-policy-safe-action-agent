"""Negative fixtures exercise validation independently of the authored policy oracles."""

import copy
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from evals.schema import Scenario
from evals.validate import materialize_world, validate_paths, validate_scenario

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "evals" / "scenarios"


@pytest.fixture
def document() -> dict[str, Any]:
    return yaml.safe_load((SCENARIOS / "happy_path" / "refund-in-window.yaml").read_text())


def test_full_suite_and_round_trip() -> None:
    scenarios, errors = validate_paths(SCENARIOS)
    assert not errors
    assert len(scenarios) >= 150
    assert Counter(s.category.value for s in scenarios) >= Counter(
        {
            "happy_path": 19,
            "policy_boundary": 13,
            "policy_bait": 13,
            "prompt_injection": 10,
            "identity": 10,
            "stale_policy": 6,
            "tool_failure": 10,
            "idempotency": 6,
            "multi_intent": 6,
            "escalation": 3,
            "follow_up": 4,
        }
    )
    for scenario in scenarios:
        assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    assert (
        json.loads((ROOT / "evals/scenario.schema.json").read_text())
        == Scenario.model_json_schema()
    )


def test_override_add_and_replace(document: dict[str, Any]) -> None:
    scenario = Scenario.model_validate(document)
    world = materialize_world(scenario)
    assert len(world.orders) == 601
    assert next(o for o in world.orders if o.order_id == "ord_900001").amount_paid_cents == 10000
    document["world"]["overrides"][0]["value"]["order_id"] = "ord_000001"
    document["world"]["overrides"][1]["value"]["order_id"] = "ord_000001"
    document["world"]["overrides"][1]["value"]["shipment_id"] = "shp_000001"
    world = materialize_world(Scenario.model_validate(document))
    assert len(world.orders) == 600
    assert next(o for o in world.orders if o.order_id == "ord_000001").amount_paid_cents == 10000


# Each entry is written as a separate malformed YAML fixture and checked by the public CLI loader.
@pytest.mark.parametrize(
    ("fault", "match"),
    [
        ("schema", "category"),
        ("extra", "Extra inputs"),
        ("id", "pattern"),
        ("session", "unknown customer_id"),
        ("verified", "verified session"),
        ("override_customer", "unknown customer"),
        ("override_sku", "unknown SKU"),
        ("override_duplicate", "duplicate override"),
        ("shipment", "unknown order"),
        ("shipment_time", "shipment timestamps"),
        ("money", "inconsistent money"),
        ("dates", "inconsistent timestamps"),
        ("future", "future timestamp"),
        ("missing_shipment", "exactly one shipment"),
        ("assertion_id", "unknown assertion entity"),
        ("field", "unknown assertion field"),
        ("nested_field", "unknown assertion field"),
        ("field_type", "int_parsing"),
        ("exists", "requires a boolean"),
        ("membership", "requires a list"),
        ("ordered", "require numbers"),
        ("contradiction", "contradicts"),
        ("state_contradiction", "contradicts"),
        ("equalities", "contradictory final_state"),
        ("forbidden_argument", "unknown forbidden argument"),
        ("forbidden_reference", "unknown order_id"),
        ("action_reference", "unknown order_id"),
        ("action_sku", "unknown item_skus"),
        ("assertion_reference", "unknown customer_id"),
        ("fault_schedule", "multiple faults"),
        ("turn", "exceeds max_turns"),
        ("duration", "greater than"),
        ("policy_version", "different version"),
        ("bait", "declare forbidden_actions"),
    ],
)
def test_negative_fixture(document: dict[str, Any], tmp_path: Path, fault: str, match: str) -> None:
    order = document["world"]["overrides"][0]["value"]
    shipment = document["world"]["overrides"][1]["value"]
    assertion = document["expected"]["final_state"][0]
    action = document["expected"]["executed_actions"][0]
    if fault == "schema":
        document["category"] = "not-a-category"
    elif fault == "extra":
        document["unexpected"] = True
    elif fault == "id":
        document["id"] = "Not Kebab"
    elif fault == "session":
        document["session"]["customer_id"] = "cus_missing"
    elif fault == "verified":
        document["session"]["customer_id"] = None
    elif fault == "override_customer":
        order["customer_id"] = "cus_missing"
    elif fault == "override_sku":
        order["items"][0]["sku"] = "UNKNOWN"
    elif fault == "override_duplicate":
        document["world"]["overrides"].append(copy.deepcopy(document["world"]["overrides"][0]))
    elif fault == "shipment":
        shipment["order_id"] = "ord_missing"
    elif fault == "shipment_time":
        shipment["delivered_at"] = "2026-11-12T12:00:00Z"
    elif fault == "money":
        order["amount_paid_cents"] += 1
    elif fault == "dates":
        order["placed_at"] = "2026-11-20T12:00:00Z"
    elif fault == "future":
        document["world"]["now"] = "2026-10-01T12:00:00Z"
    elif fault == "missing_shipment":
        document["world"]["overrides"].pop()
    elif fault == "assertion_id":
        assertion["id"] = "ord_missing"
    elif fault == "field":
        assertion["field"] = "imaginary"
    elif fault == "nested_field":
        assertion["field"] = "shipping_address.imaginary"
    elif fault == "field_type":
        assertion["value"] = "not-money"
    elif fault == "exists":
        assertion.update(op="exists", value=123)
    elif fault == "membership":
        assertion.update(op="in", value=123)
    elif fault == "ordered":
        assertion.update(op="gt", value="not-money")
    elif fault in {"contradiction", "state_contradiction"}:
        document["forbidden_actions"] = [
            {"action": "issue_refund", "args_match": {"order_id": order["order_id"]}}
        ]
        if fault == "state_contradiction":
            document["expected"]["executed_actions"] = []
    elif fault == "equalities":
        document["expected"]["final_state"].append({**assertion, "value": 5})
    elif fault == "forbidden_argument":
        document["forbidden_actions"] = [{"action": "issue_refund", "args_match": {"typo": 1}}]
    elif fault == "forbidden_reference":
        document["forbidden_actions"] = [
            {"action": "issue_refund", "args_match": {"order_id": "ord_missing"}}
        ]
    elif fault == "action_reference":
        action["order_id"] = "ord_missing"
    elif fault == "action_sku":
        action["item_skus"] = ["UNKNOWN"]
    elif fault == "assertion_reference":
        assertion.update(field="customer_id", value="cus_missing")
    elif fault == "fault_schedule":
        document["faults"] = [{"tool": "issue_refund", "mode": "timeout", "on_call": 1}] * 2
    elif fault == "turn":
        document["clock_advance"] = [{"at_turn": 99, "by": "P1D"}]
    elif fault == "duration":
        document["clock_advance"] = [{"at_turn": 2, "by": "PT0S"}]
    elif fault == "policy_version":
        document["policy_change"] = {"at_turn": 2, "to_version": document["policy"]["version"]}
    elif fault == "bait":
        document["category"] = "policy_bait"
    fixture = tmp_path / f"{fault}.yaml"
    fixture.write_text(yaml.safe_dump(document), encoding="utf-8")
    scenarios, errors = validate_paths(fixture)
    assert not scenarios
    assert len(errors) == 1, errors
    assert match in errors[0], errors
    assert str(fixture) in errors[0]


def test_duplicate_ids(document: dict[str, Any], tmp_path: Path) -> None:
    for name in ("first.yaml", "second.yml"):
        (tmp_path / name).write_text(yaml.safe_dump(document), encoding="utf-8")
    scenarios, errors = validate_paths(tmp_path)
    assert len(scenarios) == 1
    assert len(errors) == 1
    assert "duplicate scenario id" in errors[0]


def test_forbidden_different_order_is_not_contradiction(document: dict[str, Any]) -> None:
    document["forbidden_actions"] = [
        {"action": "issue_refund", "args_match": {"order_id": "ord_000001"}}
    ]
    validate_scenario(Scenario.model_validate(document))


@pytest.mark.parametrize("name", ["unverified-address", "country-change-bait"])
def test_unchanged_address_is_not_an_effect(name: str) -> None:
    category = "identity" if name == "unverified-address" else "policy_bait"
    scenarios, errors = validate_paths(SCENARIOS / category / f"{name}.yaml")
    assert len(scenarios) == 1
    assert not errors


def test_malformed_yaml_and_empty_directory(tmp_path: Path) -> None:
    assert "no scenario files" in validate_paths(tmp_path)[1][0]
    bad = tmp_path / "broken.yaml"
    bad.write_text("id: [", encoding="utf-8")
    assert validate_paths(bad)[1]
    assert validate_paths(tmp_path / "missing.yaml")[1]


def test_cli_exit_codes(tmp_path: Path) -> None:
    good = subprocess.run(
        [sys.executable, "-m", "evals.validate", str(SCENARIOS)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert good.returncode == 0, good.stdout + good.stderr
    assert f"Total: {len(list(SCENARIOS.rglob('*.yaml')))} valid; 0 errors" in good.stdout
    bad = subprocess.run(
        [sys.executable, "-m", "evals.validate", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert bad.returncode == 1


@pytest.mark.parametrize(
    ("field", "op", "value"),
    [
        ("amount_refunded_cents", "gt", 0),
        ("amount_refunded_cents", "gte", 1),
        ("amount_refundable_cents", "eq", 0),
        ("amount_refundable_cents", "lt", 10000),
        ("amount_refundable_cents", "lte", 9999),
    ],
)
def test_refund_bounds_cannot_require_forbidden_effect(
    document: dict[str, Any], field: str, op: str, value: int
) -> None:
    document["expected"]["executed_actions"] = []
    document["expected"]["final_state"] = [
        {"entity": "order", "id": "ord_900001", "field": field, "op": op, "value": value}
    ]
    document["forbidden_actions"] = [{"action": "issue_refund", "args_match": {}}]
    with pytest.raises(ValueError, match="contradicts"):
        validate_scenario(Scenario.model_validate(document))


@pytest.mark.parametrize(
    ("name", "action"),
    [("cancel-before-shipment", "cancel_order"), ("address-same-country", "update_address")],
)
def test_order_change_contradictions(name: str, action: str) -> None:
    document = yaml.safe_load((SCENARIOS / "happy_path" / f"{name}.yaml").read_text())
    document["expected"]["executed_actions"] = []
    document["forbidden_actions"] = [{"action": action, "args_match": {"order_id": "ord_900001"}}]
    with pytest.raises(ValueError, match="contradicts"):
        validate_scenario(Scenario.model_validate(document))


def test_partial_nested_forbidden_match() -> None:
    document = yaml.safe_load((SCENARIOS / "happy_path/address-same-country.yaml").read_text())
    document["forbidden_actions"] = [
        {"action": "update_address", "args_match": {"new_address": {"country": "CA"}}}
    ]
    validate_scenario(Scenario.model_validate(document))
    document["forbidden_actions"][0]["args_match"]["new_address"]["country"] = "US"
    with pytest.raises(ValueError, match="contradicts"):
        validate_scenario(Scenario.model_validate(document))


def test_policy_change_and_duration_roundtrip(document: dict[str, Any]) -> None:
    document["policy_change"] = {"at_turn": 2, "to_version": "test-successor"}
    document["clock_advance"] = [{"at_turn": 3, "by": "PT12H"}]
    scenario = Scenario.model_validate(document)
    assert scenario.clock_advance[0].by.total_seconds() == 43200
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
