# AGENTS.md

Instructions for AI coding agents (Codex, Cursor, Kiro, Claude Code, and others) working in this repository.

- Product context, scope, eval design, sprint plan: `project_description.md`
- Detailed engineering guidance: `CLAUDE.md` (keep this file and `CLAUDE.md` consistent — if you change a rule in one, change it in the other)
- Current work: `TASKS.md` · Environment: `SETUP.md` · Workflow: `CONTRIBUTING.md`

## Project in one paragraph
**Policy-Safe Action Agent** is a customer-service agent for a fictional retailer ("Larkspur Goods") that can issue refunds, cancel orders and change addresses but **cannot violate business policy**. The LLM only *proposes* actions; a deterministic, versioned policy engine *decides*; an executor runs approved actions idempotently; every step is written to an append-only event log and can be replayed. Success is measured by evals: baseline agent (policy in prompt) vs guarded agent (this architecture).

## Architecture invariants — never break
1. The LLM never calls side-effecting tools directly. Guarded action tools (same names as the baseline's) only create proposals that the policy engine decides.
2. Policy decisions use facts from the system of record, never claims from the conversation.
3. Policies are versioned YAML in `policies/` with a closed operator set. No `eval()` / `exec()` / free-form expressions.
4. Decision precedence: `DENY > REQUIRE_VERIFICATION > REQUIRE_APPROVAL > ALLOW`; decisions return rule IDs + reason codes.
5. Every side-effecting action has an idempotency key; retries never duplicate effects.
6. The event log is append-only and records the policy version; replay reproduces the decision trace exactly.

If a task appears to require breaking one of these, stop and ask instead of working around it.

## Hard rules
- **Never edit a scenario's expected outcome or forbidden actions to make an eval pass.** Flag suspected bad scenarios in the PR description.
- **Synthetic data only.** No real names, emails, addresses or PII.
- **Stripe test mode only** (`sk_test_…`). Code must refuse to start with a live key.
- **No secrets in the repo.** Use `.env` (gitignored); keep `.env.example` current.
- **No hardcoded model IDs.** Provider/model come from `LLM_PROVIDER` / `LLM_MODEL`.
- Don't add anything from the "Won't do" list (`project_description.md` §5) without approval.

## Git workflow
```
feature branch ──PR──► dev ──release PR──► main
```
- Branch from the latest `dev`; never commit directly to `dev` or `main`; never force-push shared branches.
- Prefixes: `feat/`, `fix/`, `test/`, `eval/`, `ui/`, `docs/`, `chore/`, `ci/`; name as `<prefix>/t<day>-<n>-<short-name>` using the `TASKS.md` ID.
- Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `ci:`, `refactor:`.
- PRs target `dev` (`gh pr create --base dev`) and are squash-merged.
- One task per branch. Before starting, check `git branch -a` and open PRs so you don't edit files another agent's branch owns.

## Tool lanes
| Agent | Owns | Avoid |
|---|---|---|
| Kiro | `.kiro/specs/` (requirements, design, tasks) | Implementation code |
| Claude Code | `src/psa/`, `evals/runner/`, `evals/simulator/`, `infra/`, CI | `web/` unless coordinated |
| Codex | `tests/`, `evals/scenarios/`, fault injection, PR review | Changing invariants or policy engine semantics without review |
| Cursor | `web/` (Next.js UI, dashboards) | Backend changes beyond API client types |

## Stack
Python 3.12 (uv), Pydantic v2, FastAPI, LangGraph, SQLAlchemy 2 + Alembic, Postgres, MCP, Stripe test mode, OpenTelemetry + LangSmith, pytest, ruff, pyright · Next.js + TypeScript for `web/`.

## Commands
See `SETUP.md` → "Everyday commands". Commands are finalized during the Day 1 scaffold (`TASKS.md` T1.x).

## Definition of done
Lint, types and tests pass; relevant eval suite run with numbers in the PR; docs updated if behavior changed; `TASKS.md` status updated; no invariant broken.
