"""T5.2 / T5.3: comparison table and policy-regression gate on synthetic reports."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from evals.runner.compare import flips, render
from evals.runner.gate import violations

from psa.domain import (
    ActionName,
    EvalRunReport,
    ScenarioCategory,
    SystemUnderTest,
)
from psa.domain.reports import ScenarioResult, SystemMetrics, TrialResult

G, B = SystemUnderTest.GUARDED, SystemUnderTest.BASELINE
T = datetime(2026, 11, 22, tzinfo=UTC)


def trial(ok: bool, unauth: tuple[ActionName, ...] = ()) -> TrialResult:
    return TrialResult(
        trial=0,
        success=ok,
        unauthorized_actions=unauth,
        turns=1,
        latency_ms_p50=1,
        latency_ms_p95=1,
        cost_usd=0,
        conversation_id="conv_x",
    )


def metrics(system: SystemUnderTest, success: float, duplicates: int = 0) -> SystemMetrics:
    return SystemMetrics(
        system=system,
        scenarios=2,
        trials_per_scenario=1,
        task_success_rate=success,
        unauthorized_action_rate=0,
        false_refusal_rate=0,
        correct_escalation_rate=1,
        injection_resistance_rate=1,
        duplicate_side_effects=duplicates,
        pass_hat_k={1: success},
        latency_ms_p50=1,
        latency_ms_p95=1,
        cost_usd_per_resolved=0,
        by_category={ScenarioCategory.HAPPY_PATH: success},
    )


def report(
    run_id: str,
    guarded: dict[str, TrialResult],
    *,
    success: float | None = None,
    duplicates: int = 0,
    baseline_unauth: bool = True,
) -> EvalRunReport:
    scen = [
        ScenarioResult(scenario_id=s, category=ScenarioCategory.HAPPY_PATH, system=G, trials=(t,))
        for s, t in guarded.items()
    ] + [
        ScenarioResult(
            scenario_id=s,
            category=ScenarioCategory.HAPPY_PATH,
            system=B,
            trials=(trial(True, (ActionName.ISSUE_REFUND,) if baseline_unauth else ()),),
        )
        for s in guarded
    ]
    rate = (
        success if success is not None else sum(t.success for t in guarded.values()) / len(guarded)
    )
    return EvalRunReport(
        run_id=run_id,
        suite="regression",
        started_at=T,
        finished_at=T,
        git_sha="abc",
        policy_version="2026.11.21-1",
        agent_model="m",
        simulator_model="m",
        systems=(metrics(G, rate, duplicates), metrics(B, 1.0)),
        scenarios=tuple(scen),
    )


BASE = report("base", {"a": trial(True), "b": trial(False)})


def test_identical_report_passes() -> None:
    assert violations(BASE, BASE) == []


def test_new_unauthorized_action_in_guarded_fails() -> None:
    bad = report("x", {"a": trial(True), "b": trial(False, (ActionName.ISSUE_REFUND,))})
    assert violations(bad, BASE) == ["new unauthorized action in guarded `b` (1)"]


def test_unguarded_baseline_system_is_never_gated() -> None:
    # The control system's unauthorized actions are the point of the experiment.
    assert violations(report("x", {"a": trial(True), "b": trial(False)}), BASE) == []


def test_scenario_regression_and_success_drop_fail() -> None:
    worse = report("x", {"a": trial(False), "b": trial(False)})
    found = violations(worse, BASE)
    assert "guarded `a` passed in the baseline and now fails" in found
    assert any("task success dropped 50.0 pts" in v for v in found)


def test_small_success_drop_within_limit_passes() -> None:
    assert violations(report("x", {"a": trial(True), "b": trial(False)}, success=0.46), BASE) == []


def test_duplicate_side_effects_fail() -> None:
    dup = report("x", {"a": trial(True), "b": trial(False)}, duplicates=1)
    assert violations(dup, BASE) == ["duplicate side effects 0 → 1"]


def test_flips_and_render() -> None:
    better = report("x", {"a": trial(True), "b": trial(True), "c": trial(True)})
    f = flips(better, BASE, G)
    assert (f.regressed, f.fixed, f.new, f.missing) == ([], ["b"], ["c"], [])
    table = render(better, BASE)
    assert "| guarded | Task success | 50.0% |" in table
    assert "✓ fixed: `b`" in table


@pytest.mark.parametrize(("current", "code"), [("same", 0), ("bad", 1)])
def test_cli_exit_code(tmp_path: Path, current: str, code: int) -> None:
    (tmp_path / "base.json").write_text(BASE.model_dump_json())
    cur = BASE if current == "same" else report("x", {"a": trial(False), "b": trial(False)})
    (tmp_path / "cur.json").write_text(json.dumps(cur.model_dump(mode="json")))
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "evals.runner.gate",
            str(tmp_path / "cur.json"),
            "--baseline",
            str(tmp_path / "base.json"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == code, proc.stdout + proc.stderr
    assert ("FAILED" in proc.stdout) == (code == 1)
