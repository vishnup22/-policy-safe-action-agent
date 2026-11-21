# Tasks — Sprint 1 (10 days)

Task board for the Policy-Safe Action Agent. Scope and acceptance metrics: `project_description.md`. Workflow: `CONTRIBUTING.md`.

**Status legend:** `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked
**Branch naming:** `<prefix>/t<day>-<n>-<short-name>` (e.g. `feat/t2-1-policy-engine`)
**Update rule:** whoever opens a PR updates the task's status and adds the PR number.

---

## Day 0 — Repo & workflow ✅
- [x] **T0.1** Project docs: `project_description.md`, `CLAUDE.md` — Claude Code
- [x] **T0.2** GitHub repo, `main` + `dev`, feature → dev → main workflow (PR #1) — Claude Code
- [x] **T0.3** `CONTRIBUTING.md`, `AGENTS.md`, `TASKS.md`, `SETUP.md` — Claude Code · `chore/project-docs` (PR #2)
- [ ] **T0.4** Repo settings: default branch `dev`, branch protection on `main`/`dev`, fix leading hyphen in repo name — owner decision
- [ ] **T0.5** Visa pre-check: E-Verify search + current U.S. opening for Sierra, Decagon, Distyl, LangChain — owner

## Day 1 — Spec, scaffold, baseline
- [ ] **T1.1** Kiro spec: `.kiro/specs/policy-safe-agent/{requirements,design,tasks}.md` — Kiro · `chore/t1-1-kiro-spec`
- [ ] **T1.2** Scaffold: uv project, `src/psa/` layout, ruff/pyright/pytest config, `.env.example`, docker-compose (Postgres) — Claude Code · `chore/t1-2-scaffold`
- [ ] **T1.3** CI: GitHub Actions for lint, types, tests on PRs to `dev`/`main` — Claude Code · `ci/t1-3-pipeline`
- [ ] **T1.4** Policy YAML schema (Pydantic) + `policies/larkspur-returns.yaml` v1 — Claude Code · `feat/t1-4-policy-schema`
- [ ] **T1.5** Scenario file format + 40 seed scenarios across all categories — Codex · `eval/t1-5-seed-scenarios`
- [ ] **T1.6** Baseline agent (policy in prompt, direct tool access) + first metrics report — Claude Code · `feat/t1-6-baseline-agent`
- **Exit:** baseline report generated; CI green · **Release:** `v0.1.0`

## Day 2 — Policy engine & data
- [ ] **T2.1** Policy engine: closed operator set, precedence, rule IDs + reason codes — Claude Code · `feat/t2-1-policy-engine`
- [ ] **T2.2** Boundary-case unit tests for every rule (both sides of each threshold) — Codex · `test/t2-2-policy-boundaries`
- [ ] **T2.3** Commerce DB schema (customers, orders, items, shipments, payments) + Alembic — Claude Code · `feat/t2-3-commerce-schema`
- [ ] **T2.4** Synthetic seed generator (deterministic by seed) — Claude Code · `feat/t2-4-seed-data`
- **Exit:** 100% rule coverage in tests

## Day 3 — Tools & idempotency
- [ ] **T3.1** MCP server: read tools (order, customer, shipment, policy lookup) — Claude Code · `feat/t3-1-read-tools`
- [ ] **T3.2** MCP write tools: refund (Stripe test mode), cancel, update address, create ticket — Claude Code · `feat/t3-2-write-tools`
- [ ] **T3.3** Idempotency keys + live-key guard (`sk_live_` refusal) — Claude Code · `feat/t3-3-idempotency`
- [ ] **T3.4** Tests: success, timeout, error, duplicate call for each write tool — Codex · `test/t3-4-tool-tests`
- **Exit:** duplicate-refund test passes

## Day 4 — Guarded agent, executor, event log
- [ ] **T4.1** Append-only event log (messages, tool calls, intents, decisions, executions, policy version) — Claude Code · `feat/t4-1-event-log`
- [ ] **T4.2** Executor: allow-list, retries, timeouts, circuit breaker — Claude Code · `feat/t4-2-executor`
- [ ] **T4.3** Guarded LangGraph agent with read tools + `propose_action` only — Claude Code · `feat/t4-3-guarded-agent`
- [ ] **T4.4** FastAPI chat endpoint + auth stub — Claude Code · `feat/t4-4-chat-api`
- **Exit:** end-to-end refund flows through policy engine → executor → event log

## Day 5 — Eval harness
- [ ] **T5.1** LLM user simulator (persona + hidden goal, stop conditions) — Claude Code · `eval/t5-1-simulator`
- [ ] **T5.2** Scenario runner: DB-state assertions, forbidden-action checks, metrics — Claude Code · `eval/t5-2-runner`
- [ ] **T5.3** pass^k (k = 1…4) + baseline vs guarded comparison report — Claude Code · `eval/t5-3-passk`
- [ ] **T5.4** Expand scenarios to 100 — Codex · `eval/t5-4-scenarios-100`
- **Exit:** daily eval report generated automatically · **Release:** `v0.5.0`

## Day 6 — Faults & regression gate
- [ ] **T6.1** Fault injection: timeouts, 5xx, Stripe declines, rate limits — Codex · `eval/t6-1-fault-injection`
- [ ] **T6.2** Regression suite + accepted-baseline snapshot — Claude Code · `eval/t6-2-regression-suite`
- [ ] **T6.3** CI policy-regression gate (fails on new unauthorized action / success drop) — Claude Code · `ci/t6-3-regression-gate`
- [ ] **T6.4** Demo PR: refund window 30 → 14 days shows behavior diff — Claude Code · `feat/t6-4-policy-change-demo`
- **Exit:** CI fails on an injected violation

## Day 7 — Approvals & long-running follow-ups
- [ ] **T7.1** Approval queue (REQUIRE_APPROVAL) API — Claude Code · `feat/t7-1-approvals`
- [ ] **T7.2** Identity verification flow (REQUIRE_VERIFICATION) — Claude Code · `feat/t7-2-verification`
- [ ] **T7.3** Durable scheduler + simulated clock for follow-ups — Claude Code · `feat/t7-3-scheduler`
- [ ] **T7.4** Expand scenarios to 150+ — Codex · `eval/t7-4-scenarios-150`
- **Exit:** follow-up survives a restart

## Day 8 — Frontend
- [ ] **T8.1** Next.js app scaffold + chat demo — Cursor · `ui/t8-1-chat`
- [ ] **T8.2** Replay / audit viewer (rule IDs, policy version, decision per action) — Cursor · `ui/t8-2-replay`
- [ ] **T8.3** Approvals panel — Cursor · `ui/t8-3-approvals`
- [ ] **T8.4** Metrics dashboard (eval results, latency, cost) — Cursor · `ui/t8-4-metrics`
- **Exit:** replay shows rule IDs for every executed action

## Day 9 — Deploy & harden
- [ ] **T9.1** Dockerfiles + full docker-compose; fresh-clone run verified — Claude Code · `chore/t9-1-containers`
- [ ] **T9.2** Deploy API + web + Postgres; auth on demo — Claude Code · `chore/t9-2-deploy`
- [ ] **T9.3** OpenTelemetry + LangSmith tracing; cost per conversation — Claude Code · `feat/t9-3-observability`
- [ ] **T9.4** README (architecture diagram, results table) + `docs/failure-analysis.md` — Claude Code · `docs/t9-4-readme`
- **Exit:** live URL works; `docker compose up` from fresh clone works

## Day 10 — Results & outreach
- [ ] **T10.1** Final full eval run (≥150 scenarios, k = 4) and results freeze — Claude Code
- [ ] **T10.2** 2-minute demo video (block → approval → replay → regression gate) — owner
- [ ] **T10.3** One-page case studies: Sierra, Decagon, Distyl, LangChain (`docs/case-studies/`) — Claude Code + owner
- [ ] **T10.4** Release `dev` → `main`, tag `v1.0.0` — owner
- [ ] **T10.5** Send outreach; log in the company tracker workbook — owner

---

## Backlog (only if ahead of schedule)
- [ ] Second domain (airline rebooking) for Sierra tailoring
- [ ] LangSmith Tool Gateway integration
- [ ] Incident Investigation Agent add-on (Resolve AI / Datadog cluster)

## Blocked / decisions needed
- T0.4 — repo default branch, branch protection, repo rename
