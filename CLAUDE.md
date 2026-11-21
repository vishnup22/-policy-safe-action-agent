# CLAUDE.md

Guidance for Claude Code (and other coding agents) working in this repository.
Full product context, scope, eval design and sprint plan: **`project_description.md`** — read it before starting any non-trivial task.

## What this is
**Policy-Safe Action Agent** — a customer-service agent for a fictional retailer ("Larkspur Goods") that can issue refunds, cancel orders and change addresses, but **cannot violate business policy**: the LLM only *proposes* actions; a deterministic, versioned policy engine *decides*; an executor runs approved actions idempotently; everything is logged and replayable.

It is a 10-day, production-grade portfolio POC. Measured results (baseline vs guarded) matter more than features.

## Architecture invariants — never break these
1. The LLM **never calls side-effecting tools directly**. It gets read tools + `propose_action` only. Write tools are reachable only through the policy engine → executor path.
2. Policy decisions use **facts from the system of record** (DB / tool results), never claims made in the conversation.
3. Policies are **versioned YAML data** in `policies/`, evaluated with a closed operator set. No `eval()`, no `exec()`, no free-form expressions, no policy logic in prompts for the guarded agent.
4. Decision precedence: `DENY > REQUIRE_VERIFICATION > REQUIRE_APPROVAL > ALLOW`. Every decision returns rule IDs + reason codes.
5. Every side-effecting action carries an **idempotency key**; retries must never duplicate effects.
6. The **event log is append-only**. Every message, tool call/result, intent, decision and execution is recorded with the policy version. Replay must reproduce the decision trace exactly.

If a task seems to require breaking an invariant, stop and ask.

## Planned layout
```
src/psa/
  agent/      # LangGraph graph, prompts, LLM client (provider-agnostic)
  policy/     # engine, schema (Pydantic v2), loader
  tools/      # MCP server: read tools + write tools (Stripe test mode, orders DB)
  executor/   # idempotent execution, retries, timeouts, circuit breaker
  store/      # Postgres models, event log, migrations
  scheduler/  # durable follow-ups (supports simulated clock)
  api/        # FastAPI app: chat, approvals, replay, reports, auth
policies/     # versioned YAML policy sets
evals/
  scenarios/  # one YAML per scenario (seed state, persona, faults, expected state, forbidden actions)
  simulator/  # LLM user simulator
  runner/     # scenario runner, metrics, pass^k, baseline comparison
  reports/    # generated results (gitignored except accepted baselines)
web/          # Next.js: chat demo, replay/audit viewer, approvals, metrics
tests/        # unit + integration tests
infra/        # Dockerfiles, docker-compose
docs/         # architecture, failure analysis, case studies
.kiro/specs/  # Kiro requirements / design / tasks (source of truth for scope)
```
Update this section when the real layout diverges.

## Stack & conventions
- Python 3.12, managed with **uv**. Pydantic v2 for all schemas. Type hints everywhere.
- Lint/format: **ruff**. Types: **pyright** (strict in `policy/` and `executor/`).
- Tests: **pytest**. Policy engine and executor need exhaustive unit tests, including exact-threshold boundary cases.
- Agent: **LangGraph**; tracing via OpenTelemetry + LangSmith.
- DB: Postgres (SQLAlchemy 2.x + Alembic). Frontend: Next.js + TypeScript.
- LLM provider and model are **configuration** (`LLM_PROVIDER`, `LLM_MODEL` env vars) — never hardcode a model ID in code.
- Keep modules small and pure where possible; side effects live in `tools/` and `executor/` only.

## Commands (planned — fix these once the repo is scaffolded)
```bash
uv sync                                  # install
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest                            # unit + integration
docker compose -f infra/docker-compose.yml up   # full local stack
uv run python -m evals.runner --suite regression          # fast PR subset
uv run python -m evals.runner --suite full --trials 4     # nightly / pre-demo
uv run python -m evals.runner --compare baseline guarded  # results table
```

## Working rules
- **Evals are the judge.** Before claiming a change improves the agent, run the relevant eval suite and report the numbers. Never call something "fixed" on vibes.
- **Never edit a scenario's expected outcome or forbidden actions to make a run pass.** If you believe a scenario is wrong, say so and explain; don't change it silently.
- **Synthetic data only.** No real customer data, names or PII. Stripe keys must be **test mode** (`sk_test_…`); refuse to run with a live key.
- Secrets live in `.env` (gitignored); keep `.env.example` current.
- Track the false-refusal rate alongside safety metrics — an agent that refuses everything is a failure too.
- When adding a policy rule: add the YAML, unit tests for both sides of each threshold, and at least one eval scenario.
- Prefer small, reviewable PRs. One task per branch: `feat/…`, `eval/…`, `fix/…`, `ui/…`.
- Don't add scope from the "Won't do" list in `project_description.md` §5 without asking.

## Multi-tool coordination
This repo is worked on by Claude Code, Codex, Cursor and Kiro.
- **Kiro** owns specs in `.kiro/specs/` — treat them as the scope source of truth.
- **Claude Code** — primary builder for backend, agent, policy engine, evals, infra, CI.
- **Codex** — tests, scenario authoring, fault injection, PR review on separate branches.
- **Cursor** — `web/` frontend and dashboards.
- Don't edit files another tool's in-flight branch owns; check `git status` / open branches first.
- Keep `AGENTS.md` (Codex) and `.cursor/rules` aligned with the invariants and rules in this file when they are created.

## Definition of done for any task
Lint + types + tests pass, relevant eval suite run with numbers reported, docs updated if behavior changed, no invariant broken.
