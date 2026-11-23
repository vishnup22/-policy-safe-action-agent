"""Atomic report and Markdown exports; checkpoint metadata stays in a separate file."""

import os
from pathlib import Path

from psa.domain import EvalRunReport


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def write_report(report: EvalRunReport, directory: Path) -> None:
    atomic_write(directory / f"{report.run_id}.json", report.model_dump_json(indent=2) + "\n")
    lines = [
        f"# Eval run {report.run_id}",
        "",
        f"Suite: {report.suite}; model: {report.agent_model}.",
        "",
        "| System | Trials | Task success | Unauthorized/action | False refusal | "
        "Escalation recall | Injection resistance | Duplicates | P50 ms | P95 ms | USD/resolved |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in report.systems:
        trials = sum(len(r.trials) for r in report.scenarios if r.system == s.system)
        cells = [
            s.system.value,
            str(trials),
            f"{s.task_success_rate:.3f}",
            f"{s.unauthorized_action_rate:.3f}",
            f"{s.false_refusal_rate:.3f}",
            f"{s.correct_escalation_rate:.3f}",
            f"{s.injection_resistance_rate:.3f}",
            str(s.duplicate_side_effects),
            f"{s.latency_ms_p50:.2f}",
            f"{s.latency_ms_p95:.2f}",
            f"{s.cost_usd_per_resolved:.4f}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "| System | k | pass^k |", "|---|---:|---:|"])
    for s in report.systems:
        lines.extend(f"| {s.system} | {k} | {value:.4f} |" for k, value in s.pass_hat_k.items())
    lines.extend(
        [
            "",
            "Zero-denominator rates are reported as 0; inspect trial counts before comparing.",
            "Fake-runtime reports test the harness and are not agent-performance measurements.",
        ]
    )
    atomic_write(directory / f"{report.run_id}.md", "\n".join(lines) + "\n")
