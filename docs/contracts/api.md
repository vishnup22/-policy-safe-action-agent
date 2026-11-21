# API Contract v0.1

The HTTP contract between the FastAPI backend (`src/psa/api/`) and the web console (`web/`).
JSON field names and enums mirror the Pydantic models in `src/psa/domain/` exactly — **those models are the source of truth**; this file documents them for the frontend.

- Base URL: `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`)
- All endpoints are under `/api`; all except login require `Authorization: Bearer <token>`
- Timestamps: ISO-8601 UTC strings. Money: integer cents (`*_cents`).
- Errors: `{ "error": { "code": string, "message": string } }` with 4xx/5xx status

Changing this contract requires a PR that updates the Pydantic models, this file and the web client together.

---

## Auth
### `POST /api/auth/demo-login`
```json
// request
{ "passcode": "string" }
// 200
{ "token": "string", "expires_at": "2026-11-22T12:00:00Z" }
```

## Conversations
### `POST /api/conversations`
Start a conversation. `customer_email` is optional (simulates a logged-in customer).
```json
// request
{ "customer_email": "maya.r@example.com" }
// 201
{ "conversation_id": "conv_8f3k2l1m", "started_at": "2026-11-21T12:00:00Z" }
```

### `GET /api/conversations?limit=50&cursor=<opaque>`
```json
{
  "items": [
    {
      "conversation_id": "conv_8f3k2l1m",
      "started_at": "2026-11-21T12:00:00Z",
      "last_event_at": "2026-11-21T12:03:10Z",
      "customer_id": "cus_k2m9x1",
      "status": "active | ended | awaiting_approval",
      "message_count": 8,
      "actions_executed": 1,
      "actions_blocked": 2
    }
  ],
  "next_cursor": null
}
```

### `POST /api/conversations/{conversation_id}/messages`
Send a user message; returns the agent reply and every event produced during this turn.
```json
// request
{ "text": "My mug arrived cracked, can I get a refund?" }
// 200
{
  "reply": { "text": "I'm sorry about that...", "at": "2026-11-21T12:00:05Z" },
  "events": [ /* Event[] — see below */ ],
  "pending_approval_id": null
}
```

### `GET /api/conversations/{conversation_id}/events`
Full ordered event log for replay/audit. `seq` is gap-free starting at 0.
```json
{ "conversation_id": "conv_8f3k2l1m", "events": [ /* Event[] */ ] }
```

## Event (`psa.domain.events.Event`)
```json
{
  "event_id": "evt_a1b2c3d4",
  "conversation_id": "conv_8f3k2l1m",
  "seq": 7,
  "type": "policy_decision",
  "at": "2026-11-21T12:00:04Z",
  "policy_version": "2026.11.21-1",
  "payload": { }
}
```
`type` ∈ `conversation_started, user_message, agent_message, tool_call, tool_result, model_call, action_proposed, policy_decision, verification_requested, verification_completed, approval_requested, approval_resolved, action_executed, action_failed, follow_up_scheduled, follow_up_fired, conversation_ended`

Payload shapes by type:

| type | payload |
|---|---|
| `user_message` / `agent_message` | `{ "text": string }` |
| `tool_call` | `{ "call_id": string, "tool": string, "args": object }` |
| `tool_result` | `{ "call_id": string, "ok": boolean, "result": object \| null, "error": string \| null, "latency_ms": number }` |
| `model_call` | `{ "model": string, "input_tokens": number, "output_tokens": number, "latency_ms": number, "cost_usd": number }` |
| `action_proposed` | `{ "intent": ActionIntent }` |
| `policy_decision` | `{ "decision": Decision }` |
| `approval_requested` | `{ "approval_id": string, "intent_id": string }` |
| `approval_resolved` | `{ "approval_id": string, "resolution": "approved" \| "rejected", "reviewer": string, "note": string \| null }` |
| `action_executed` | `{ "intent_id": string, "idempotency_key": string, "result": object }` |
| `action_failed` | `{ "intent_id": string, "error": string, "retryable": boolean, "attempt": number }` |
| `follow_up_scheduled` | `{ "follow_up_id": string, "due_at": string, "note": string }` |
| `follow_up_fired` | `{ "follow_up_id": string }` |

### ActionIntent (`psa.domain.actions.ActionIntent`)
```json
{
  "intent_id": "int_9x8y7z6w",
  "conversation_id": "conv_8f3k2l1m",
  "customer_id": "cus_k2m9x1",
  "args": { "action": "issue_refund", "order_id": "ord_q1w2e3", "amount_cents": 3200, "item_skus": ["LG-MUG-014"], "reason": "Arrived cracked" },
  "justification": "Customer reports item damaged on arrival",
  "proposed_at": "2026-11-21T12:00:03Z",
  "idempotency_key": "idem_conv8f3k_refund_ord_q1w2e3"
}
```
`args.action` ∈ `issue_refund, issue_store_credit, cancel_order, update_address, create_ticket, escalate_to_human, schedule_follow_up` (discriminated union — see `actions.py` for each args shape).

### Decision (`psa.domain.decisions.Decision`)
```json
{
  "intent_id": "int_9x8y7z6w",
  "outcome": "DENY",
  "rule_results": [
    { "rule_id": "IDENTITY_VERIFIED", "outcome": "ALLOW", "reason_code": null, "message": "Identity verified" },
    { "rule_id": "REFUND_WINDOW", "outcome": "DENY", "reason_code": "OUTSIDE_RETURN_WINDOW", "message": "Delivered 41 days ago; return window is 30 days" }
  ],
  "policy_set": "larkspur-returns",
  "policy_version": "2026.11.21-1",
  "evaluated_at": "2026-11-21T12:00:04Z",
  "facts_snapshot": { "order.days_since_delivery": 41, "order.status": "delivered", "session.identity_verified": true }
}
```
`outcome` ∈ `ALLOW, REQUIRE_APPROVAL, REQUIRE_VERIFICATION, DENY` (precedence: DENY > REQUIRE_VERIFICATION > REQUIRE_APPROVAL > ALLOW).

## Approvals
### `GET /api/approvals?status=pending|approved|rejected`
```json
{
  "items": [
    {
      "approval_id": "apr_5t6y7u8i",
      "conversation_id": "conv_8f3k2l1m",
      "status": "pending",
      "requested_at": "2026-11-21T12:00:04Z",
      "intent": { /* ActionIntent */ },
      "decision": { /* Decision with outcome REQUIRE_APPROVAL */ },
      "resolved_at": null,
      "reviewer": null,
      "note": null
    }
  ]
}
```
### `POST /api/approvals/{approval_id}/resolve`
```json
// request
{ "resolution": "approved | rejected", "note": "Verified photo of damage" }
// 200 — the updated approval object; 409 if already resolved
```

## Policies
### `GET /api/policies`
```json
{ "items": [ { "policy_set": "larkspur-returns", "version": "2026.11.21-1", "rule_count": 14, "updated_at": "2026-11-21T10:00:00Z" } ] }
```
### `GET /api/policies/{policy_set}`
```json
{ "policy_set": "larkspur-returns", "version": "2026.11.21-1", "yaml": "string", "rules": [ { "id": "REFUND_WINDOW", "applies_to": ["issue_refund"], "description": "string" } ] }
```

## Evals
### `GET /api/evals/runs?limit=20`
```json
{
  "items": [
    {
      "run_id": "run_20261121_1200",
      "suite": "full",
      "started_at": "2026-11-21T12:00:00Z",
      "finished_at": "2026-11-21T12:41:00Z",
      "git_sha": "a1b2c3d",
      "policy_version": "2026.11.21-1",
      "headline": {
        "baseline": { "task_success_rate": 0.71, "unauthorized_action_rate": 0.12 },
        "guarded":  { "task_success_rate": 0.83, "unauthorized_action_rate": 0.0 }
      }
    }
  ]
}
```
### `GET /api/evals/runs/{run_id}`
Returns `EvalRunReport` (`psa.domain.reports.EvalRunReport`) — systems metrics (incl. `pass_hat_k` map `{ "1": 0.83, "2": 0.74, "3": 0.69, "4": 0.66 }` and `by_category`), and per-scenario trial results.

## Health
### `GET /api/health` (no auth)
```json
{ "status": "ok", "version": "0.1.0", "policy_version": "2026.11.21-1" }
```
