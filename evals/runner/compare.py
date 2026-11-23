"""Compare an eval report with an accepted baseline (T5.2).

    uv run python -m evals.runner.compare evals/reports/<run>.json \
        [--baseline evals/baselines/regression.json]

A scenario "passes" for a system when every trial succeeded (pass^k with k = trials).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from psa.domain import EvalRunReport, SystemUnderTest

DEFAULT_BASELINE = Path("evals/baselines/regression.json")
HEADLINE = (
    ("task_success_rate", "Task success", True),
    ("unauthorized_action_rate", "Unauthorized-action rate", False),
    ("false_refusal_rate", "False-refusal rate", False),
    ("correct_escalation_rate", "Correct escalation", True),
    ("injection_resistance_rate", "Injection resistance", True),
)


def load(path: Path) -> EvalRunReport:
    return EvalRunReport.model_validate(json.loads(path.read_text(encoding="utf-8")))


def passes(report: EvalRunReport, system: SystemUnderTest) -> dict[str, bool]:
    return {
        s.scenario_id: bool(s.trials) and all(t.success for t in s.trials)
        for s in report.scenarios
        if s.system is system
    }


def unauthorized(report: EvalRunReport, system: SystemUnderTest) -> dict[str, int]:
    return {
        s.scenario_id: sum(len(t.unauthorized_actions) for t in s.trials)
        for s in report.scenarios
        if s.system is system
    }


@dataclass(frozen=True)
class Flips:
    regressed: list[str]  # pass -> fail
    fixed: list[str]  # fail -> pass
    new: list[str]  # not in the baseline
    missing: list[str]  # in the baseline, not in the report


def flips(current: EvalRunReport, baseline: EvalRunReport, system: SystemUnderTest) -> Flips:
    now, before = passes(current, system), passes(baseline, system)
    shared = now.keys() & before.keys()
    return Flips(
        regressed=sorted(s for s in shared if before[s] and not now[s]),
        fixed=sorted(s for s in shared if not before[s] and now[s]),
        new=sorted(now.keys() - before.keys()),
        missing=sorted(before.keys() - now.keys()),
    )


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _delta(now: float, before: float, higher_is_better: bool) -> str:
    diff = (now - before) * 100
    if abs(diff) < 0.05:
        return "±0"
    good = (diff > 0) == higher_is_better
    return f"{diff:+.1f} pts {'✓' if good else '✗'}"


def render(current: EvalRunReport, baseline: EvalRunReport) -> str:
    lines = [
        f"## Eval comparison: `{current.run_id}` vs baseline `{baseline.run_id}`",
        "",
        f"Policy {baseline.policy_version} → {current.policy_version} · "
        f"agent model {current.agent_model} · suite `{current.suite}`",
        "",
        "| System | Metric | Baseline | Current | Δ |",
        "|---|---|---|---|---|",
    ]
    before = {m.system: m for m in baseline.systems}
    for metrics in current.systems:
        old = before.get(metrics.system)
        if old is None:
            continue
        for field, label, higher in HEADLINE:
            now_v, old_v = getattr(metrics, field), getattr(old, field)
            lines.append(
                f"| {metrics.system} | {label} | {_pct(old_v)} | {_pct(now_v)} | "
                f"{_delta(now_v, old_v, higher)} |"
            )
        lines.append(
            f"| {metrics.system} | Duplicate side effects | {old.duplicate_side_effects} | "
            f"{metrics.duplicate_side_effects} | "
            f"{metrics.duplicate_side_effects - old.duplicate_side_effects:+d} |"
        )
    for system in (SystemUnderTest.GUARDED, SystemUnderTest.BASELINE):
        f = flips(current, baseline, system)
        lines += ["", f"**{system}:** {len(f.regressed)} regressed, {len(f.fixed)} fixed"]
        lines += [f"- ✗ regressed: `{s}`" for s in f.regressed]
        lines += [f"- ✓ fixed: `{s}`" for s in f.fixed]
        if f.new or f.missing:
            lines.append(f"- new: {len(f.new)} · missing: {len(f.missing)}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # Windows consoles
    print(render(load(args.report), load(args.baseline)), end="")


if __name__ == "__main__":
    main()
