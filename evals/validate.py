"""Validate scenario structure, fixture references and contradictory effect oracles."""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, TypeAdapter

from evals.schema import Scenario
from psa.domain.actions import (
    CancelOrderArgs,
    CreateTicketArgs,
    EscalateToHumanArgs,
    IssueRefundArgs,
    IssueStoreCreditArgs,
    ScheduleFollowUpArgs,
    UpdateAddressArgs,
)
from psa.domain.reports import ScenarioCategory
from psa.seed import World, generate_world

COLLECTIONS = {
    "customer": ("customers", "customer_id"),
    "order": ("orders", "order_id"),
    "shipment": ("shipments", "shipment_id"),
    "catalog": ("catalog", "sku"),
}
ACTION_MODELS = {
    model.model_fields["action"].default: model
    for model in (
        IssueRefundArgs,
        IssueStoreCreditArgs,
        CancelOrderArgs,
        UpdateAddressArgs,
        CreateTicketArgs,
        EscalateToHumanArgs,
        ScheduleFollowUpArgs,
    )
}


def materialize_world(scenario: Scenario) -> World:
    """Upsert full entities; explicitly override shipments when changing shipped orders."""
    world = generate_world(scenario.world.seed, scenario.world.now)
    data = world.model_dump()
    seen: set[tuple[str, str]] = set()
    for override in scenario.world.overrides:
        collection, key = COLLECTIONS[override.entity]
        record = override.value.model_dump()
        identifier = str(record[key])
        if (collection, identifier) in seen:
            raise ValueError(f"duplicate override {override.entity} {identifier}")
        seen.add((collection, identifier))
        records = {row[key]: row for row in data[collection]}
        records[identifier] = record
        data[collection] = tuple(records.values())
    world = World.model_validate(data)
    for order in world.orders:
        if any(
            stamp > scenario.world.now
            for stamp in (order.placed_at, order.shipped_at, order.delivered_at)
            if stamp
        ):
            raise ValueError(f"future timestamp in {order.order_id}")
    return world


def entities(world: World) -> dict[str, dict[str, BaseModel]]:
    return {
        entity: {getattr(row, key): row for row in getattr(world, collection)}
        for entity, (collection, key) in COLLECTIONS.items()
    }


def field_value(record: BaseModel, path: str) -> Any:
    current: Any = record
    for part in path.split("."):
        if not isinstance(current, BaseModel) or (
            part not in type(current).model_fields
            and not isinstance(getattr(type(current), part, None), property)
        ):
            raise ValueError(f"unknown assertion field {path}")
        current = getattr(current, part)
    return current.model_dump(mode="json") if isinstance(current, BaseModel) else current


def subset(pattern: dict[str, Any], actual: dict[str, Any]) -> bool:
    return all(
        key in actual
        and (
            subset(value, actual[key])
            if isinstance(value, dict) and isinstance(actual[key], dict)
            else value == actual[key]
        )
        for key, value in pattern.items()
    )


def check_references(data: Any, index: dict[str, dict[str, BaseModel]]) -> None:
    keys = {
        "customer_id": "customer",
        "order_id": "order",
        "shipment_id": "shipment",
        "sku": "catalog",
    }
    if isinstance(data, dict):
        for key, value in data.items():
            if key in keys and value is not None and value not in index[keys[key]]:
                raise ValueError(f"unknown {key}: {value}")
            if (
                key == "item_skus"
                and isinstance(value, (list, tuple))
                and any(sku not in index["catalog"] for sku in value)
            ):
                raise ValueError("unknown item_skus")
            check_references(value, index)
    elif isinstance(data, (list, tuple)):
        for value in data:
            check_references(value, index)


def validate_match(model: type[BaseModel], pattern: dict[str, Any]) -> None:
    """A match is partial, including nested address objects, but always well typed."""
    for key, value in pattern.items():
        if key not in model.model_fields or key == "action":
            raise ValueError(f"unknown forbidden argument {key} for {model.__name__}")
        field = model.model_fields[key]
        annotation = field.annotation
        if (
            isinstance(annotation, type)
            and issubclass(annotation, BaseModel)
            and isinstance(value, dict)
        ):
            validate_match(annotation, value)
        else:
            TypeAdapter(field.rebuild_annotation()).validate_python(value)


def validate_scenario(scenario: Scenario) -> None:
    world = materialize_world(scenario)
    index = entities(world)
    check_references(scenario.session.model_dump(), index)
    for forbidden in scenario.forbidden_actions:
        model = ACTION_MODELS[forbidden.action]
        validate_match(model, forbidden.args_match)
        check_references(forbidden.args_match, index)
    effects = [action.model_dump(mode="json") for action in scenario.expected.executed_actions]
    check_references(effects, index)
    equalities: dict[tuple[str, str, str], Any] = {}
    for assertion in scenario.expected.final_state:
        if assertion.id not in index[assertion.entity]:
            raise ValueError(f"unknown assertion entity {assertion.entity} {assertion.id}")
        record = index[assertion.entity][assertion.id]
        initial = field_value(record, assertion.field)
        if assertion.op == "exists" and not isinstance(assertion.value, bool):
            raise ValueError("exists assertion requires a boolean")
        if assertion.op in {"in", "not_in"} and not isinstance(assertion.value, list):
            raise ValueError("membership assertion requires a list")
        if assertion.op in {"lt", "lte", "gt", "gte"} and (
            isinstance(initial, bool)
            or not isinstance(initial, (int, float))
            or isinstance(assertion.value, bool)
            or not isinstance(assertion.value, (int, float))
        ):
            raise ValueError("ordered assertions require numbers")
        parent = record
        parts = assertion.field.split(".")
        for part in parts[:-1]:
            parent = getattr(parent, part)
        field = type(parent).model_fields.get(parts[-1])
        annotation = field.rebuild_annotation() if field else type(initial)
        if assertion.op != "exists":
            values = (
                assertion.value
                if assertion.op in {"in", "not_in"} and isinstance(assertion.value, list)
                else [assertion.value]
            )
            for value in values:
                TypeAdapter(annotation).validate_json(json.dumps(value))
                if assertion.op in {"eq", "in"}:
                    check_references({parts[-1]: value}, index)
        if assertion.entity == "order" and isinstance(assertion.value, int):
            # Bounds can imply a refund without identifying its exact amount.
            increasing = assertion.field == "amount_refunded_cents" and (
                (assertion.op == "gt" and assertion.value >= initial)
                or (assertion.op == "gte" and assertion.value > initial)
            )
            decreasing = assertion.field == "amount_refundable_cents" and (
                (assertion.op == "lt" and assertion.value <= initial)
                or (assertion.op == "lte" and assertion.value < initial)
                or (assertion.op == "eq" and assertion.value < initial)
            )
            if increasing or decreasing:
                implied: dict[str, Any] = {"action": "issue_refund", "order_id": assertion.id}
                if assertion.op == "eq":
                    implied["amount_cents"] = initial - assertion.value
                effects.append(implied)
        if assertion.op != "eq":
            continue
        key = (assertion.entity, assertion.id, assertion.field)
        if key in equalities and equalities[key] != assertion.value:
            raise ValueError("contradictory final_state equalities")
        equalities[key] = assertion.value
        if assertion.entity != "order" or initial == assertion.value:
            continue
        if (
            assertion.field == "amount_refunded_cents"
            and isinstance(assertion.value, int)
            and assertion.value > initial
        ):
            effects.append(
                {
                    "action": "issue_refund",
                    "order_id": assertion.id,
                    "amount_cents": assertion.value - initial,
                }
            )
        elif assertion.field == "status" and assertion.value == "cancelled":
            effects.append({"action": "cancel_order", "order_id": assertion.id})
        elif assertion.field.startswith("shipping_address"):
            effect: dict[str, Any] = {"action": "update_address", "order_id": assertion.id}
            if assertion.field == "shipping_address":
                effect["new_address"] = assertion.value
            else:
                effect["new_address"] = {assertion.field.split(".", 1)[1]: assertion.value}
            effects.append(effect)
    for effect in effects:
        for forbidden in scenario.forbidden_actions:
            if effect["action"] == forbidden.action and subset(forbidden.args_match, effect):
                raise ValueError(
                    f"forbidden action {forbidden.action} contradicts expected effects/final_state"
                )


def validate_paths(path: Path) -> tuple[list[Scenario], list[str]]:
    files = sorted([*path.rglob("*.yaml"), *path.rglob("*.yml")]) if path.is_dir() else [path]
    scenarios: list[Scenario] = []
    errors: list[str] = []
    seen: set[str] = set()
    if not files:
        errors.append(f"{path}: no scenario files")
    for file in files:
        try:
            scenario = Scenario.model_validate(yaml.safe_load(file.read_text(encoding="utf-8-sig")))
            if scenario.id in seen:
                raise ValueError(f"duplicate scenario id {scenario.id}")
            seen.add(scenario.id)
            validate_scenario(scenario)
            scenarios.append(scenario)
        except (ValueError, TypeError, KeyError, OSError, yaml.YAMLError) as error:
            errors.append(f"{file}: {error}")
    return scenarios, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    scenarios, errors = validate_paths(args.path)
    counts = Counter(s.category for s in scenarios)
    print("Category              Valid scenarios")
    for category in ScenarioCategory:
        print(f"{category.value:22s}{counts[category]:3d}")
    print(f"Total: {len(scenarios)} valid; {len(errors)} errors")
    for error in errors:
        print(error)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
