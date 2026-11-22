# Larkspur Policy Console (`web/`)

Operator console for the Policy-Safe Action Agent: chat with inline policy decisions, replay/audit of the event log, the approvals queue, and the baseline-vs-guarded eval dashboard. Built against `docs/contracts/api.md`.

## Run

```bash
cp .env.example .env.local   # defaults to mock mode
pnpm install
pnpm dev                     # http://localhost:3000 — mock passcode: larkspur-demo
```

| Variable | Meaning |
|---|---|
| `NEXT_PUBLIC_API_MODE` | `mock` (in-memory fixtures, default) or `live` (real API) |
| `NEXT_PUBLIC_API_URL` | Backend base URL for live mode (default `http://localhost:8000`) |
| `NEXT_PUBLIC_MOCK_PASSCODE` | Passcode the mock login accepts (default `larkspur-demo`) |

Checks (same as CI): `pnpm lint && pnpm typecheck && pnpm test && pnpm build`.

## Layout

- `lib/api/schemas.ts` — Zod mirrors of every shape in the API contract; TS types in `lib/api/types.ts` are inferred from them.
- `lib/api/client.ts` — `ApiClient` interface. `LiveClient` (fetch + bearer token + error envelope, responses validated with Zod) and `MockClient` (in-memory, latency jitter, deterministic fixtures).
- `lib/api/mock/` — deterministic demo world: the five stories (in-window refund ALLOW, out-of-window DENY, $340 REQUIRE_APPROVAL, prompt injection in order notes blocked, follow-up scheduled and fired) and two eval runs whose metrics are computed from their trials.
- `lib/api/queries.ts` — TanStack Query hooks, including the optimistic approval mutation.
- `app/(console)/` — `/chat`, `/conversations`, `/conversations/[id]`, `/approvals`, `/evals`, `/evals/[runId]`, behind the demo-passcode guard.

In mock mode the chat routes messages by keyword to the five stories; a known demo email (e.g. `maya.r@example.com`) simulates a verified customer, and an empty email shows `REQUIRE_VERIFICATION`. Mock state lives in memory and resets on reload.
