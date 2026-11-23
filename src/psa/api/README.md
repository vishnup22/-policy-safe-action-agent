# HTTP API integration

`create_app(*, runtime_factory, sessions, clock, settings)` is the injection point.
It consumes only `psa.runtime.ports` for runtime behavior. The ASGI entrypoint
`psa.api.main:app` (T4.5) injects `psa.runtime.factory.build_runtime`, a session
factory for `DATABASE_URL` and `SystemClock`; run it with
`uv run uvicorn psa.api.main:app`. `app.py` itself imports no agent/tool/executor/LLM code.

Use `Settings` with `DEMO_PASSCODE`, a minimum 32-character `APP_AUTH_SECRET`,
`WEB_ORIGIN` (default http://localhost:3000), and optional `POLICY_SET`,
`POLICY_VERSION`, `POLICIES_DIR`, `REPORTS_DIR`, and `TOKEN_TTL_SECONDS`.
Settings may be passed explicitly for tests or loaded from the environment/.env.
The app never supplies a default passcode or signing key.

Every route in docs/contracts/api.md is implemented. Login issues an HMAC-SHA256
signed, purpose-bound token with expiry; health is public per its endpoint contract.
All other routes require the token. Demo email lookup identifies a customer but
never sets identity_verified. This is a shared demo operator console, not a
multi-tenant authorization scheme.

Conversation pagination uses a stable timestamp/ID cursor. Runtime methods own
conversation/event/approval persistence. Approval resolution serializes API
callers with a PostgreSQL advisory transaction lock; repeated resolution returns
409. Policies come from PolicyRegistry; the detail endpoint returns the runtime's
active version. Evals read only EvalRunReport JSON, excluding checkpoint files.
Errors use the documented envelope, and CORS allows the configured web origin.

Tests use the reference FakeRuntime with a persistence adapter and isolated
Postgres fixtures; database tests skip when Postgres is unavailable. Contract tests
validate all 17 JSON examples, expanding the document's explicit comment and enum
placeholders without modifying the frozen API contract.
