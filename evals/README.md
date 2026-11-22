# Lane B: synthetic worlds and scenario authoring

The seed generator and validator are offline: they do not call an LLM, payment
provider, database, or Lane A's policy engine. Scenario outcomes are authored
against TASKS.md A4, not derived from an agent's observed behavior.

```powershell
uv run python -m psa.seed export --seed 42 --now 2026-11-21T12:00:00Z --out evals/fixtures/world_42.json
uv run python -m evals.validate evals/scenarios/
```

`generate_world(seed, now)` requires timezone-aware time and returns frozen domain
entities in a `World` container: 60 catalog SKUs, 200 fictional customers, 600
orders, and one shipment per shipped order. Prices and money use integer cents.
A private `random.Random(seed)` provides determinism without changing global
random state. Generated payment-intent IDs are null; no Stripe resources exist.
The export is reproducible and need not be committed.

## Authoring

Use `psa.seed.builders` to pin delivery dates, remaining refunds, final-sale items,
shipment state, ownership, or untrusted notes. Helpers accept explicit `now` and
can compose through their `order` argument. The YAML files store the resulting
full domain records so reviewers can inspect the exact input facts.

`world.overrides` upserts `{entity: customer|order|shipment|catalog, value: ...}`.
IDs are stable, and overrides may add or replace records. Related shipments must
be overridden explicitly when order timestamps change. Duplicate override IDs,
dangling references, inconsistent amounts, and mismatched shipments are errors.
This initial schema does not support deletion or arbitrary fixture expressions.

`evals/scenario.schema.json` is exported from `Scenario.model_json_schema()`;
a test checks that it stays in sync. Unknown fields are rejected. The validator
accepts a single YAML file or recursively reads `.yaml` and `.yml` in a directory.
It reports all file errors, prints category counts, and returns 1 on any error
(including an empty input directory). It checks structured IDs, not strings in
natural-language messages. The latter are deliberately untrusted user claims.

Assertions use singular entity names and existing entity IDs, with real fields
or properties (for example `amount_refundable_cents`), including dotted address
fields. `exists` means non-null, with a boolean expected value. Ordering operators
are numeric; membership operators take lists. `eq` compares JSON representations.

`expected.executed_actions` supplements final-state checks for effects not modeled
in the frozen commerce contracts: tickets, store credits, escalations, and durable
follow-ups. Each entry requires exactly one successful committed effect; retries
and cached responses are not extra effects. This is a runner contract, not an
execution implementation. Match business parameters; free-text reasons/subjects/
notes describe the intended task and must not require verbatim LLM wording.
`forbidden_actions.args_match` matches action arguments; an empty map forbids all
executions of that action. The validator detects overlaps with required actions
and direct refund/cancel/address effects implied by final-state equalities.
It does not execute policies or prove arbitrary constraints satisfiable.

## Policy and runner assumptions

All scenarios pin `larkspur-returns` version `2026.11.21-1`. A4's delivery window
includes day 30; $200 refunds and $50 credits do not require approval; one cent
above those amounts does. Refunds cannot exceed the remaining amount. Final-sale,
gift-card, ownership, and country restrictions are not overridden by claims.
No approval or verification completion is supplied unless explicitly stated.
Credit scenarios assume an initially empty credit ledger. The frozen commerce
contracts do not include credit-ledger records; historical rolling-cap scenarios
can be added with the store integration, without changing these expectations.

Each ambiguous runner behavior is described in its scenario. Clock advances apply
before the specified turn. Faults are one-shot, on the specified 1-based tool call;
current timeout scenarios are pre-effect. The decline scenario treats a decline
as terminal and requests human help. A post-commit timeout and scheduler firing
across restarts require the later executor/scheduler harness.

Stale-policy cases cover a claimed obsolete policy and cached eligibility becoming
stale after a clock advance. The schema supports `policy_change`, but these seeds
do not invent an unavailable successor policy version. A mixed permitted/denied
request is marked denied while still asserting the permitted action completes.

The 40-scenario validation result measures dataset validity only. Baseline versus
guarded success rates, policy compliance, and pass^k require the Day 4 runner.
Never change a scenario's outcome or forbidden actions to make an eval pass.
