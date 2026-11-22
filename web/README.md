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

Smoke tests (Playwright, mock mode, 375 px and 1440 px) run against the production build:

```bash
pnpm build
pnpm exec playwright install chromium   # once; or set PW_CHANNEL=chrome to use an installed Chrome
pnpm test:e2e                           # starts `pnpm start` on :3100; set E2E_BASE_URL to reuse a running server
```

## Layout

- `lib/api/schemas.ts` — Zod mirrors of every shape in the API contract; TS types in `lib/api/types.ts` are inferred from them.
- `lib/api/client.ts` — `ApiClient` interface. `LiveClient` (fetch + bearer token + error envelope, responses validated with Zod) and `MockClient` (in-memory, latency jitter, deterministic fixtures).
- `lib/api/mock/` — deterministic demo world: the five stories (in-window refund ALLOW, out-of-window DENY, $340 REQUIRE_APPROVAL, prompt injection in order notes blocked, follow-up scheduled and fired) and two eval runs whose metrics are computed from their trials.
- `lib/api/queries.ts` — TanStack Query hooks, including the optimistic approval mutation.
- `lib/api/config.ts` — env config and `createApiClient`. The client is a `LazyClient` that imports `LiveClient` / `MockClient` (and with them Zod and the fixtures) on the first call, so pages that never call the API don't download them.
- `app/(console)/` — `/chat`, `/conversations`, `/conversations/[id]`, `/approvals`, `/evals`, `/evals/[runId]`, behind the demo-passcode guard. Any 401 from the API drops the session and sends the operator to `/login?next=…` with a "session expired" notice.
- `app/page.tsx` — the public landing page: hero, bento grid and dock footer. Bento numbers come from the newest run on `GET /api/evals/runs`; when the API is unreachable or answers 401 (anonymous visitors), they come from the mock world and the tile says "Demo data". Nothing is hardcoded.

## Design system ("Liquid Glass")

- `components/ui/glass/` — `GlassPanel` (variants `default`, `strong`, `inset`; optional cursor spotlight), `Aurora`, `PillNav` (shared-layout active pill), `SegmentedTabs`, `BlurFade`, `Dock`.
- `lib/motion.ts` — spring `{ stiffness: 300, damping: 30 }`, blur-fade presets, page transitions. Framer Motion is used through `m` + `LazyMotion`; its features load after first paint. `MotionConfig reducedMotion="user"` turns springs into fades, and CSS stops the aurora drift and badge shimmer under `prefers-reduced-motion`.
- Tokens live in `app/globals.css` (`bg-glass`, `border-glass-edge`, `shadow-glass`, …) with a dark "obsidian" default and a light "frost" theme.
- Blur budget: only `default` / `strong` glass uses `backdrop-filter`; anything nested inside a panel uses `inset`, and the sheet overlay is unblurred, so at most three blur layers stack (nav, panel, sheet).
- Contrast: secondary text is `#A1A1A6` on the dark theme rather than `#86868B`, which drops to about 4.5:1 where the aurora is brightest. Fonts are Geist Sans / Geist Mono, self-hosted.

In mock mode the chat routes messages by keyword to the five stories; a known demo email (e.g. `maya.r@example.com`) simulates a verified customer, and an empty email shows `REQUIRE_VERIFICATION`. Mock state lives in memory and resets on reload.
