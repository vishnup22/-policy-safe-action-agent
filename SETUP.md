# Setup

How to get a working development environment. Primary dev machine is **Windows 11**; commands are given for Git Bash/PowerShell and work the same on macOS/Linux unless noted.

> Status: the code scaffold is created in Day 1 (`TASKS.md` T1.x). Sections marked *(after scaffold)* will work once that lands on `dev`.

## 1. Prerequisites

| Tool | Version | Install (Windows) | Check |
|---|---|---|---|
| Git | 2.45+ | `winget install Git.Git` | `git --version` |
| GitHub CLI | 2.60+ | `winget install GitHub.cli` | `gh auth status` |
| uv (Python manager) | latest | `winget install astral-sh.uv` | `uv --version` |
| Python | 3.12 | `uv python install 3.12` | `uv run python --version` |
| Node.js | 22 LTS or newer | `winget install OpenJS.NodeJS.LTS` | `node --version` |
| pnpm | 9+ | `npm install -g pnpm` | `pnpm --version` |
| Docker Desktop | latest | `winget install Docker.DockerDesktop` | `docker compose version` |
| Stripe CLI (optional) | latest | `winget install Stripe.StripeCli` | `stripe --version` |

Accounts / keys you need:
- **LLM provider API key** (whichever provider you configure in `LLM_PROVIDER`)
- **Stripe** account in **test mode** → secret key starting with `sk_test_`
- **LangSmith** API key (tracing; optional but recommended)

## 2. Clone
```bash
git clone https://github.com/vishnup22/-policy-safe-action-agent.git policy-safe-action-agent
cd policy-safe-action-agent
git switch dev
```

## 3. Environment variables *(after scaffold)*
```bash
cp .env.example .env
```
Fill in `.env`:

| Variable | Example | Notes |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` / `openai` | Selects the client adapter |
| `LLM_MODEL` | *(provider model ID)* | Never hardcoded in code |
| `LLM_API_KEY` | `…` | Key for the chosen provider |
| `SIM_LLM_MODEL` | *(model ID)* | Model for the user simulator (can differ from agent) |
| `DATABASE_URL` | `postgresql+psycopg://psa:psa@localhost:5433/psa` | Local Postgres from docker compose |
| `STRIPE_SECRET_KEY` | `sk_test_…` | **Test mode only** — app refuses `sk_live_` keys |
| `LANGSMITH_API_KEY` | `…` | Optional |
| `LANGSMITH_TRACING` | `true` | Optional |
| `LANGSMITH_PROJECT` | `policy-safe-action-agent` | Optional |
| `APP_AUTH_SECRET` | random 32+ chars | Signs session tokens for the demo UI |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Used by `web/` |

`.env` is gitignored. Never commit real keys.

## 4. Install dependencies *(after scaffold)*
```bash
uv sync                 # Python deps + dev tools into .venv
cd web && pnpm install  # frontend deps
```

## 5. Start local services *(after scaffold)*
```bash
docker compose -f infra/docker-compose.yml up -d db    # Postgres only
uv run alembic upgrade head                            # create schema
uv run python -m psa.store.seed                        # synthetic Larkspur Goods data
```

## 6. Run the app *(after scaffold)*
```bash
uv run uvicorn psa.api.main:app --reload --port 8000   # API  → http://localhost:8000/docs
cd web && pnpm dev                                     # UI   → http://localhost:3000
```
Or everything in containers:
```bash
docker compose -f infra/docker-compose.yml up --build
```

## 7. Everyday commands *(after scaffold)*
```bash
# Quality
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest
uv run pytest tests/policy -q            # one area

# Evals
uv run python -m evals.runner --suite regression                 # fast, used on PRs
uv run python -m evals.runner --suite full --trials 4            # nightly / pre-release
uv run python -m evals.runner --compare baseline guarded         # results table
uv run python -m evals.runner --scenario evals/scenarios/policy_bait/manager_approved.yaml  # one scenario
```

## 8. Stripe test mode (optional)
```bash
stripe login
stripe listen --forward-to localhost:8000/webhooks/stripe   # if webhooks are used
```
Use Stripe's test card numbers only. Seeded orders are linked to test-mode PaymentIntents by the seed script.

## 9. AI coding tools
| Tool | Reads | Notes |
|---|---|---|
| Claude Code | `CLAUDE.md` | Run from repo root |
| Codex | `AGENTS.md` | One task per branch |
| Cursor | `AGENTS.md`, `.cursor/rules/` | Mainly `web/` |
| Kiro | `.kiro/specs/`, `.kiro/steering/` | Specs are the scope source of truth |

## 10. Troubleshooting
| Symptom | Fix |
|---|---|
| `LF will be replaced by CRLF` warnings | Repo uses `.gitattributes` (LF). Run `git add --renormalize .` once. |
| Port 5433 already in use | Set `PSA_DB_PORT` to a free port and update `DATABASE_URL` to match (default 5433 avoids a locally installed Postgres on 5432) |
| App exits with "live Stripe key detected" | Working as intended — use an `sk_test_` key |
| `uv` not found after install | Open a new terminal so PATH updates |
| Docker commands hang on Windows | Start Docker Desktop and wait for the engine to be running |
