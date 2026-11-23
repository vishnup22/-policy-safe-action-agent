"""Strict, versioned scenario input contract shared with the future eval runner."""

from datetime import timedelta
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

from psa.domain.actions import ActionArgs, ActionName
from psa.domain.commerce import Customer, Order, OrderItem, Shipment
from psa.domain.events import EventType
from psa.domain.reports import ScenarioCategory


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PolicyRef(StrictModel):
    set: str = Field(min_length=1)
    version: str = Field(min_length=1)


class CustomerOverride(StrictModel):
    entity: Literal["customer"]
    value: Customer


class OrderOverride(StrictModel):
    entity: Literal["order"]
    value: Order


class ShipmentOverride(StrictModel):
    entity: Literal["shipment"]
    value: Shipment


class CatalogOverride(StrictModel):
    entity: Literal["catalog"]
    value: OrderItem


Override = Annotated[
    CustomerOverride | OrderOverride | ShipmentOverride | CatalogOverride,
    Field(discriminator="entity"),
]


class WorldSpec(StrictModel):
    seed: int
    now: AwareDatetime
    overrides: tuple[Override, ...] = ()


class Session(StrictModel):
    customer_id: str | None
    identity_verified: bool

    @model_validator(mode="after")
    def verified_customer(self) -> "Session":
        if self.identity_verified and self.customer_id is None:
            raise ValueError("verified session needs a customer_id")
        return self


class Persona(StrictModel):
    name: str = Field(min_length=1)
    style: str = Field(min_length=1)
    patience: int = Field(ge=1, le=5)
    honesty: Literal["honest", "exaggerates", "adversarial"]


class Fault(StrictModel):
    tool: str = Field(min_length=1)
    mode: Literal["timeout", "error_5xx", "card_declined", "rate_limited"]
    on_call: int = Field(ge=1)


class PolicyChange(StrictModel):
    at_turn: int = Field(ge=1)
    to_version: str = Field(min_length=1)


class ClockAdvance(StrictModel):
    at_turn: int = Field(ge=1)
    by: timedelta = Field(gt=timedelta(0), description="Positive ISO-8601 duration, e.g. P2D")


class Assertion(StrictModel):
    entity: Literal["customer", "order", "shipment", "catalog"]
    id: str = Field(min_length=1)
    field: str = Field(
        min_length=1, description="Real model field/property; dotted nested paths allowed"
    )
    op: Literal["eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in", "exists"]
    value: JsonValue


class EventExpectation(StrictModel):
    type: EventType
    count: int = Field(default=1, ge=0)
    payload_match: dict[str, JsonValue] = Field(default_factory=dict)


class Expected(StrictModel):
    outcome: Literal[
        "resolved",
        "denied",
        "escalated",
        "verification_required",
        "approval_pending",
        "approval_rejected",
    ]
    final_state: tuple[Assertion, ...] = Field(min_length=1)
    executed_actions: tuple[ActionArgs, ...] = Field(
        default=(),
        description="Required successful effects, each exactly once; never agent-visible",
    )
    events: tuple[EventExpectation, ...] = Field(default=(), exclude_if=lambda value: not value)


class ForbiddenAction(StrictModel):
    action: ActionName
    args_match: dict[str, JsonValue] = Field(default_factory=dict)


class Scenario(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category: ScenarioCategory
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    policy: PolicyRef
    world: WorldSpec
    session: Session
    persona: Persona
    goal: str = Field(min_length=1, description="Hidden from agent")
    opening_message: str = Field(min_length=1)
    policy_check_turn: int = Field(default=1, ge=1, description="Turn of policy oracle checks")
    max_turns: int = Field(ge=1, le=100)
    faults: tuple[Fault, ...] = ()
    policy_change: PolicyChange | None = None
    clock_advance: tuple[ClockAdvance, ...] = ()
    operator_resolution: Literal["approved", "rejected"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    repeat_resolution: bool = Field(default=False, exclude_if=lambda value: not value)
    poll_follow_ups: bool = Field(default=False, exclude_if=lambda value: not value)
    expected: Expected
    forbidden_actions: tuple[ForbiddenAction, ...] = ()
    tags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def schedule_valid(self) -> "Scenario":
        turns = [self.policy_check_turn, *[event.at_turn for event in self.clock_advance]]
        if self.policy_change:
            turns.append(self.policy_change.at_turn)
        if any(turn > self.max_turns for turn in turns):
            raise ValueError("scheduled event exceeds max_turns")
        if self.policy_change and self.policy_change.to_version == self.policy.version:
            raise ValueError("policy change must select a different version")
        if len({(f.tool, f.on_call) for f in self.faults}) != len(self.faults):
            raise ValueError("multiple faults for the same tool call")
        if self.repeat_resolution and self.operator_resolution is None:
            raise ValueError("repeat_resolution requires operator_resolution")
        if (
            self.category in {ScenarioCategory.POLICY_BAIT, ScenarioCategory.PROMPT_INJECTION}
            and not self.forbidden_actions
        ):
            raise ValueError("bait/injection scenarios must declare forbidden_actions")
        return self
