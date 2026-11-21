# Policy-Safe Action Agent — Project Description

> A customer-service AI agent that can take real actions (refunds, cancellations, order changes) and is **provably unable to violate business policy** — because the LLM only *proposes* actions and a deterministic, versioned policy engine *decides*.

- **Sprint:** 10 days (Sprint 1 of 3 in the STEM OPT POC plan)
- **Started:** 2026-11-21
- **Builders:** Claude Code, Codex, Cursor, Kiro
- **Outcome:** a deployed, measured, production-grade POC + case studies used for outreach to agent-engineering / forward-deployed engineering teams

---

## 1. Why this project

### The problem the industry has admitted to
- Customer-facing agents now **move money**: Decagon processes refunds via Stripe/Shopify/Salesforce integrations; Sierra added PCI-compliant payments in April 2026.
- Hallucination is still unsolved. Sierra co-founder Clay Bavor: *"the hallucination problem, I think, is still an unsolved area,"* citing deployments where agent behavior didn't match the actual return policy.
- Legal precedent: **Air Canada** was held liable after its chatbot invented a bereavement-refund policy. Buyers' takeaway: *you own what your agent says and does.*
- Buyer guidance in 2026 converges on one design principle: **refund windows, return policies and escalation thresholds must be enforced in code, not in the prompt.**
- Production gap: widely cited 2026 surveys report ~78% of enterprises piloting agents but only ~14% scaling them; Datadog's 2026 report found ~5% of production LLM call spans error out (mostly rate limits / timeouts / capacity). Treat these numbers as directional.
- Half of surveyed companies reportedly shipped agents that passed internal evals but failed real customers → evals must look like real, adversarial customers.

### Why this POC instead of a generic "agent control plane"
The target companies already sell control-plane products (LangSmith Tool Gateway, Workato AI Control Plane + Agent Evals, Decagon Watchtower/Guardrails). Pitching them a competing product is weak. What they are **hiring for** is engineers who deploy agents into messy client environments:
- **Sierra** — "Agent Engineer" (owns the Agent Development Life Cycle for customer brands)
- **Decagon** — "Forward Deployed Engineer, Agent Builder" / Agent Deployment Engineer
- **Distyl** — "Forward Deployed AI Engineer"

**Positioning:** *"I built what your Agent Engineers deliver in a client's first week — turning their refund policy into an agent that can't violate it, with proof."*

---

## 2. Target companies & tailoring

| Company | Status (Nov 2026) | What they're pushing | Angle for this POC |
|---|---|---|---|
| **Sierra** (Portfolio Fit A) | $950M Series E, >$15B valuation (May 2026) | Horizon (long-running outbound agents), Ghostwriter (agent-as-a-service), PCI payments | τ-bench-style eval + **pass^k** (Sierra's own benchmark/metric), payment action path, multi-day follow-up |
| **Decagon** (A) | $250M Series D, $4.5B (Jan 2026); Voice 3, Experiment Hub | Duet Autopilot — verified self-improving agents | **Policy-regression gate**: proves an agent "improvement" didn't break policy |
| **Distyl** (A) | $175M Series B, $1.8B (Sep 2025); Gemini Enterprise partner | Enterprise AI-native transformation | Permissions, approvals, immutable audit trail for Fortune-500-style workflows |
| **LangChain** (A, secondary) | $300M Series C, $3B (Nov 13, 2026) | LangSmith Agent Platform, Tool Gateway, spend-by-outcome | A production reference build on LangGraph + LangSmith |

Deprioritized for this POC: Workato (has its own control plane), Resolve AI (better fit for later Incident-Agent add-on), n8n/Sim (workflow builders), Replit/Cognition (coding agents), Wordware (pivoted).

> Several financial figures come from secondary sources and conflict; verify against primary announcements before quoting them in a pitch.

---

## 3. What we are building

### 3.1 Domain
Fictional e-commerce retailer **"Larkspur Goods"** (clothing + home goods). All data is synthetic.

Customer intents supported:
1. Order status / tracking
2. Return & refund (full, partial, store credit)
3. Order cancellation (before / after shipment)
4. Shipping-address change
5. Damaged / wrong-item claims
6. Escalation to a human agent
7. Follow-up promises ("I'll check back in 2 days")

### 3.2 Core idea — propose / decide / execute
```
Customer ──► Agent (LLM, LangGraph)
               │  proposes ActionIntent {action, args, justification}
               ▼
         Policy Engine (deterministic, versioned YAML)
               │  loads FACTS from system of record (never from the chat)
               │  decision: ALLOW | DENY(reason) | REQUIRE_APPROVAL | REQUIRE_VERIFICATION
               ▼
         Action Executor (idempotency keys, retries, timeouts)
               │  calls MCP tools → Stripe test mode / Orders DB
               ▼
         Event Log (append-only, Postgres) ──► Replay / Audit UI
```

### 3.3 Non-negotiable invariants
1. **The LLM never calls side-effecting tools directly.** It can only call read tools and `propose_action`.
2. **Facts come from tools, not from the conversation.** If the customer says "I got it 10 days ago", the engine checks the delivery date in the orders DB.
3. **Every executed action records the policy version and rule IDs** that allowed it.
4. **Side-effecting actions are idempotent** (idempotency key per intent); retries never double-refund.
5. **Policies are data, not prompts.** Versioned YAML, reviewed in PRs, tested in CI.
6. **Every conversation is replayable** from the event log with recorded tool responses.

### 3.4 Components

| Component | Responsibility | Tech |
|---|---|---|
| Agent | Dialogue, intent understanding, read-tool use, action proposal, explaining decisions to the customer | LangGraph, provider-agnostic LLM client |
| Policy engine | Evaluate ActionIntent against facts + policy version; return decision with rule IDs and reason codes | Pure Python, Pydantic v2, YAML policies |
| Tool layer | Read tools (orders, customers, shipments) and write tools (refund, cancel, update address, create ticket) | MCP server; Stripe **test mode**; Postgres mock commerce DB |
| Executor | Run approved actions with idempotency, timeouts, bounded retries, circuit breaker | Python, Postgres |
| Approval queue | Human-in-the-loop for REQUIRE_APPROVAL decisions | FastAPI endpoints + UI panel |
| Scheduler | Durable follow-ups ("check back in 2 days") that survive restarts | Postgres-backed jobs (simulated clock in evals) |
| Event log | Append-only record of messages, tool calls/results, intents, decisions, executions | Postgres |
| API | Chat, approvals, replay, eval-report endpoints; auth | FastAPI |
| Web UI | Chat demo, conversation replay/audit, approvals queue, metrics dashboard | Next.js |
| Observability | Traces, latency, cost per conversation | OpenTelemetry + LangSmith |
| Eval harness | Simulated customers, scenario runner, metrics, baseline comparison, CI gate | Python, pytest |

### 3.5 Policy model (example)
```yaml
policy_set: larkspur-returns
version: "2026.11.21-1"
rules:
  - id: REFUND_WINDOW
    applies_to: [issue_refund]
    when:
      all:
        - fact: order.days_since_delivery
          op: lte
          value: 30
        - fact: order.status
          op: in
          value: [delivered]
    else: { decision: DENY, reason: OUTSIDE_RETURN_WINDOW }

  - id: REFUND_AMOUNT_CAP
    applies_to: [issue_refund]
    when:
      all:
        - fact: intent.amount
          op: lte
          value_from: order.amount_paid_remaining
    else: { decision: DENY, reason: AMOUNT_EXCEEDS_PAID }

  - id: HIGH_VALUE_APPROVAL
    applies_to: [issue_refund]
    when:
      all:
        - fact: intent.amount
          op: gt
          value: 200
    then: { decision: REQUIRE_APPROVAL, reason: HIGH_VALUE_REFUND }

  - id: IDENTITY_VERIFIED
    applies_to: [issue_refund, cancel_order, update_address]
    when:
      all:
        - fact: session.identity_verified
          op: eq
          value: true
    else: { decision: REQUIRE_VERIFICATION, reason: IDENTITY_NOT_VERIFIED }
```
Rules use a small, closed set of operators (`eq, ne, lt, lte, gt, gte, in, not_in`) evaluated by Python — **no `eval()`**, no free-form expressions. Precedence: DENY > REQUIRE_VERIFICATION > REQUIRE_APPROVAL > ALLOW.

---

## 4. Evaluation design (built on Day 1, run every day)

### 4.1 Approach
τ-bench-style: an **LLM user simulator** with a persona and hidden goal talks to the agent; success is judged on the **final database state** plus **forbidden-action checks**, not on how the reply sounds.

### 4.2 Scenario set (target ≥150)

| Category | Examples | Target count |
|---|---|---|
| Happy path | In-window refund, status check, pre-shipment cancel | 30 |
| Policy boundary | Day 30 vs day 31, refund = remaining paid amount, $200 vs $200.01 | 20 |
| Social engineering / policy bait | "Your manager approved it", "I'm a VIP", "other agent promised" | 20 |
| Prompt injection | Instructions hidden in order notes, product reviews, email bodies | 15 |
| Identity & authorization | Wrong email, partial info, someone else's order | 15 |
| Stale / changed policy | Policy version changes mid-conversation or between runs | 10 |
| Tool failures | Timeouts, 5xx, Stripe card decline, rate limits | 15 |
| Retries & idempotency | Duplicate requests, user repeats "refund me" | 10 |
| Multi-intent | Refund item A + change address on order B | 10 |
| Escalation required | Legal threat, safety issue, approval-tier refunds | 5 |
| Long-running follow-up | Promise to check back in N days; simulated clock advance | 5 |

Each scenario file contains: seed DB state, persona + goal, policy version, injected faults, **expected final DB state**, **forbidden actions**, and whether escalation is required.

### 4.3 Systems compared
- **Baseline:** same LLM, same tools, policies pasted into the system prompt, side-effecting tools callable directly.
- **Guarded (ours):** propose/decide/execute architecture.

### 4.4 Metrics

| Metric | Definition | Target (guarded) |
|---|---|---|
| Unauthorized action rate | Executed actions that violate policy / all executed actions | **0** |
| Task success | Final DB state matches expected | ≥ baseline |
| pass^k (k = 1…4) | Probability all k independent trials of a task succeed: mean over tasks of C(c,k)/C(n,k) | Report curve vs baseline |
| False-refusal rate | Legitimate requests denied or needlessly escalated | ≤ baseline + 5 pts |
| Correct escalation rate | Escalation-required scenarios routed to a human | ≥ 95% |
| Injection resistance | Injection scenarios with zero forbidden actions | 100% |
| Idempotency | Duplicate side effects | 0 |
| Replay determinism | Replays producing identical decision trace | 100% |
| Latency | P50 / P95 per agent turn | Report |
| Cost | $ per resolved conversation | Report |

### 4.5 Policy-regression gate (CI)
On any PR touching `policies/`, the agent, or prompts: run the regression subset, diff outcomes against the last accepted run, and **fail the build** on any new unauthorized action or task-success drop beyond tolerance. Demo: change the refund window 30 → 14 days and show exactly which conversations change behavior.

---

## 5. Scope

**Must have (Day 10)**
- Propose/decide/execute architecture with all six invariants
- Policy engine + versioned YAML policies + unit tests
- MCP tool server: orders, customers, shipments (Postgres) + refunds (Stripe test mode)
- LangGraph agent with read tools + `propose_action`
- Append-only event log + deterministic replay
- Eval harness, ≥150 scenarios, baseline vs guarded report
- Policy-regression gate in GitHub Actions
- Approval queue (API + minimal UI)
- Durable follow-up with simulated clock
- Deployed URL with auth; Docker one-command local run
- README, architecture diagram, failure analysis, 2-minute demo video

**Should have**
- Next.js replay/audit viewer with decision explanations
- Metrics dashboard (eval results, latency, cost)
- LangSmith tracing integration

**Won't do (this sprint)**
- Voice channel (that's Sprint 3)
- Real customer data or live Stripe keys
- Multi-tenant SaaS, billing, SSO
- Fine-tuning models

---

## 6. 10-day sprint plan

| Day | Deliverable | Lead tool | Exit check |
|---|---|---|---|
| 1 | Spec (requirements, design, tasks), policy YAML schema, scenario format, 40 seed scenarios, repo + CI skeleton, baseline agent running | Kiro (spec), Claude Code | Baseline produces a first metrics report |
| 2 | Policy engine + unit tests; commerce DB schema + seed generator | Claude Code | 100% rule coverage in tests |
| 3 | MCP tool server (read + write tools), Stripe test-mode refunds, idempotency | Claude Code | Duplicate refund test passes |
| 4 | Guarded LangGraph agent with `propose_action`; executor; event log | Claude Code | End-to-end refund through policy engine |
| 5 | User simulator + scenario runner + pass^k; expand to 100 scenarios | Claude Code + Codex (scenarios) | Daily eval report generated |
| 6 | Fault injection (timeouts, 5xx, declines); policy-regression gate in CI | Codex | CI fails on injected violation |
| 7 | Approval queue + durable follow-ups with simulated clock; 150 scenarios | Claude Code | Follow-up survives restart |
| 8 | Next.js chat, replay/audit viewer, approvals panel, metrics dashboard | Cursor | Replay shows rule IDs per action |
| 9 | Deploy, auth, OTel/LangSmith, hardening, README + failure analysis | Claude Code | Live URL; fresh-clone `docker compose up` works |
| 10 | Final eval run, demo video, 4 tailored one-page case studies, outreach sent | — | Outreach logged in tracker |

---

## 7. How the four tools work together

| Tool | Role | Rules |
|---|---|---|
| **Kiro** | Spec-driven planning: requirements, design, task list (Day 1, and when scope changes) | Specs are committed and are the source of truth |
| **Claude Code** | Primary builder: backend, agent, policy engine, eval harness, infra, CI | Reads `CLAUDE.md`; runs tests + evals before declaring done |
| **Codex** | Parallel work on separate branches: tests, scenario authoring, fault injection; second-opinion PR review | One task per branch; never edits the same files as an in-flight Claude Code task |
| **Cursor** | Frontend (Next.js), dashboards, quick in-editor fixes | UI only unless explicitly coordinated |

Git rules: one repo, `main` protected, one branch per task (`feat/…`, `eval/…`, `fix/…`), merge only when CI (lint, types, tests, regression gate) is green. Eval numbers — not demo vibes — decide whether a change helped.

---

## 8. Deliverables (Definition of Done)

- [ ] Live deployed URL with auth
- [ ] `docker compose up` works from a fresh clone
- [ ] Eval report: baseline vs guarded on ≥150 scenarios, including pass^k curve
- [ ] Unauthorized action rate = 0 for guarded agent; numbers for every metric in §4.4
- [ ] CI with lint, type-check, tests, and policy-regression gate
- [ ] README: problem, architecture diagram, how to run, results table, limitations
- [ ] `docs/failure-analysis.md`: what still fails and why
- [ ] 2-minute demo video (violation blocked → approval → replay → regression gate)
- [ ] 4 one-page case studies (Sierra, Decagon, Distyl, LangChain)

---

## 9. Sales & outreach plan

**Who:** hiring managers / leads for Agent Engineering and Forward Deployed Engineering (not founders at large companies). Apply to the posted role *and* message the team lead.

**Hook (one line):** *"I built what your Agent Engineers deliver in a client's first week — an agent that can issue refunds but can't violate policy. Baseline agent: X% unauthorized actions; mine: 0, with pass^k results on 150 adversarial scenarios."*

**Message structure (≤120 words):** hook → results table (3 numbers) → 2-min video → repo → one sentence on the role you're applying for.

**Per-company emphasis**
- **Sierra:** τ-bench-style eval and pass^k; payment action path; long-running follow-up (Horizon)
- **Decagon:** policy-regression gate as the safety net for self-improving agents
- **Distyl:** approvals, permissions, audit trail for enterprise clients
- **LangChain:** production reference build on LangGraph + LangSmith (Tool Gateway if integrated)

**Framing rules**
- Never claim their product is deficient; frame gaps as industry problems they themselves have named.
- Objection "we already have guardrails" → "Agreed — this isn't a competing product; it shows I can do your deployment work on your platform."

**Visa sequencing**
- Before Day 1: check each target in E-Verify Employer Search; confirm a current U.S. opening.
- Raise I-983 / future H-1B only after interest is established, but before investing in further tailoring.
- Initial OPT EAD expires **Jan 2027** — outreach goes out on **Day 10**, not after all three sprints.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Eval set too easy → impressive but meaningless numbers | Adversarial categories are ≥50% of scenarios; boundary cases at exact thresholds |
| Over-blocking (guarded agent refuses everything) | Track false-refusal rate as a first-class metric |
| LLM cost of k trials × 150 scenarios | k ≤ 4; cache simulator turns; nightly full run, PR runs use regression subset |
| Non-deterministic LLM breaks replay | Replay uses recorded tool + model outputs from the event log |
| Four tools editing the same files | Branch-per-task; tool roles in §7 |
| Scope creep | §5 "Won't do" list is binding for this sprint |
| Company facts in pitch are wrong | Verify from primary sources before sending |

---

## 11. Sources (research, 2026-11-21)

- Sierra $950M: https://techcrunch.com/2026/05/04/sierra-raises-950m-as-the-race-to-own-enterprise-ai-gets-serious/
- Sierra beyond support: https://www.cmswire.com/customer-experience/sierra-raises-950m-at-15b-valuation-eyes-transformation-beyond-customer-support/
- Clay Bavor on hallucination: https://sequoiacap.com/podcast/training-data-clay-bavor
- Decagon Series D: https://siliconangle.com/2026/01/28/decagon-ai-raises-250m-4-5b-valuation-scale-ai-concierge-platform/
- Decagon Duet Autopilot: https://www.businesswire.com/news/home/20260609133756/en/Decagon-Introduces-Duet-Autopilot-the-First-Verified-Self-Improving-AI-Agent-for-Customer-Experience
- LangChain Series C: https://www.langchain.com/blog/series-c
- LangSmith Tool Gateway: https://www.unite.ai/langchain-launches-langsmith-tool-gateway-to-govern-agent-tool-calls/
- Distyl Series B: https://www.prnewswire.com/news-releases/distyl-ai-raises-175-million-at-1-8-billion-valuation-to-help-global-enterprises-become-ai-native-302564270.html
- Workato AIRO / control plane: https://www.morningstar.com/news/business-wire/20260923682171/workato-unveils-airo-as-the-new-face-of-its-control-and-execution-platform-for-enterprise-ai-supported-by-new-enterprise-ai-capabilities-across-the-platform
- Agents in production gap: https://www.aiacceleratorinstitute.com/ai-agents-keep-breaking-in-production-heres-why-nobodys-fixed-it-yet/
- Support-agent buyer guidance: https://superkind.ai/blog/ai-customer-support-agents
- Sierra Agent Engineer roles: https://www.tryexponent.com/jobs/fde/sierra
- Decagon FDE role: https://jobs.accel.com/companies/decagon-2/jobs/65821439-forward-deployed-engineer-agent-builder
- Distyl FDE role: https://jobs.khoslaventures.com/companies/distylai/jobs/83406877-forward-deployed-ai-engineer
