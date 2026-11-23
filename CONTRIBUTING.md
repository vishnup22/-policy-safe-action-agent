# Contributing

This guide covers how work moves through the repo — for humans and for AI coding agents (agents should also read `AGENTS.md`).

## Branching model
```
feat/… ─┐
fix/…  ─┼──PR (squash)──► dev ──release PR (merge commit)──► main
eval/… ─┘
```
| Branch | Purpose | Who writes to it |
|---|---|---|
| `main` | Stable, demo-ready. What recruiters and hiring managers see. | Release PRs from `dev` only |
| `dev` | Integration of finished features | Squash-merged feature PRs only |
| `<prefix>/<short-name>` | One task each | You / one agent |

Prefixes: `feat/` feature · `fix/` bug · `test/` tests only · `eval/` scenarios or eval harness · `ui/` frontend · `docs/` documentation · `chore/` tooling, config · `ci/` pipelines.

## Day-to-day flow
```bash
# 1. Start from the latest dev
git switch dev && git pull

# 2. Create a branch for one task (use the task ID from TASKS.md)
git switch -c feat/t2-1-policy-engine

# 3. Work in small commits
git add -p
git commit -m "feat(policy): evaluate REFUND_WINDOW rule"

# 4. Check before pushing (see SETUP.md for the full list)
uv run ruff check . && uv run pyright && uv run pytest

# 5. Push and open a PR into dev
git push -u origin HEAD
gh pr create --base dev --fill

# 6. After review + green CI: squash-merge and delete the branch
gh pr merge --squash --delete-branch
git switch dev && git pull
```

## Commit messages
[Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`

- Types: `feat`, `fix`, `test`, `docs`, `chore`, `ci`, `refactor`, `perf`
- Scopes (suggested): `policy`, `agent`, `tools`, `executor`, `store`, `scheduler`, `api`, `evals`, `web`, `infra`
- Summary in imperative mood, ≤72 chars: `fix(executor): reuse idempotency key on retry`

## Pull requests
Every PR into `dev` must include:

- **What** changed and **why** (link the `TASKS.md` ID)
- **How it was tested** — commands run and results
- **Eval impact** — if agent, policy, prompt or tool behavior changed: the regression-suite table (unauthorized action rate, task success, false-refusal rate) before vs after
- **Screenshots / clip** for UI changes

PR checklist:
- [ ] Branched from latest `dev`, one task only
- [ ] `ruff`, `pyright`, `pytest` pass locally
- [ ] Regression eval suite run if behavior changed; numbers in the description
- [ ] No architecture invariant broken (`AGENTS.md`)
- [ ] No secrets, no real PII, Stripe test keys only
- [ ] Docs and `.env.example` updated if needed
- [ ] `TASKS.md` status updated

## Releases (`dev` → `main`)
Cut a release at milestones — typically the end of a sprint day with green CI and a full eval run.
```bash
gh pr create --base main --head dev --title "release: day-N <milestone>" --body "<eval summary + changes>"
gh pr merge --merge
git tag -a v0.N.0 -m "Day N: <milestone>" && git push --tags
```
Version tags: `v0.1.0` after Day 1, `v0.2.0` after Day 2 … `v1.0.0` = Day 10 demo release.

## Recipes

### Adding or changing a policy rule
1. Edit or add YAML in `policies/`; **bump the policy set `version`**.
2. Add unit tests on **both sides of every threshold** (e.g. day 30 allowed, day 31 denied).
3. Add at least one eval scenario that exercises the rule.
4. Run the regression suite; paste the outcome diff in the PR.

### Adding an eval scenario
1. Create one YAML file in `evals/scenarios/<category>/` (categories in `project_description.md` §4.2).
2. Include: seed DB state, persona + hidden goal, policy version, injected faults, expected final DB state, forbidden actions, `escalation_required`.
3. Run it against **both** baseline and guarded agents.
4. Never change an existing scenario's expected outcome to make a run pass — open a discussion in the PR instead.

### Adding a tool
1. Read tools: add to the MCP server and the agent's tool list.
2. Write (side-effecting) tools: add to the MCP server **and** the executor allow-list only — never expose them to the LLM. Require an idempotency key.
3. Add tests for success, timeout, error and duplicate-call cases.

## Code style
- Python: ruff (lint + format), pyright (strict in `policy/` and `executor/`), type hints everywhere, Pydantic v2 models at boundaries.
- TypeScript: strict mode, ESLint + Prettier.
- Keep side effects in `tools/` and `executor/`; keep the policy engine pure.
- Tests sit in `tests/` mirroring `src/psa/`.

## Working with multiple AI tools
- One agent per branch; check open branches/PRs before starting.
- Tool lanes are listed in `AGENTS.md`.
- Review AI-generated PRs like any other PR — at least skim every diff, and use a second tool (e.g. Codex) for review on core modules (`policy/`, `executor/`).
