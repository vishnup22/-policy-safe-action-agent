"""Run offline harness smoke checks; production runtime is injected at integration."""

import argparse
from datetime import UTC, datetime
from pathlib import Path

import yaml

from evals.runner import run_suite
from evals.runner.fake import EchoRuntime, StopSimulator
from evals.validate import validate_paths
from psa.domain import SystemUnderTest
from psa.store import database_url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["regression", "full"], default="regression")
    parser.add_argument("--runtime", choices=["fake"], default="fake")
    parser.add_argument(
        "--systems",
        nargs="+",
        choices=[s.value for s in SystemUnderTest],
        default=["baseline", "guarded"],
    )
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-cost-usd", type=float, default=10)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.resume and not args.run_id:
        parser.error("--resume requires --run-id")
    scenarios, errors = validate_paths(Path("evals/scenarios"))
    if errors:
        parser.error("\n".join(errors))
    if args.suite != "full":
        ids = yaml.safe_load(Path(f"evals/suites/{args.suite}.yaml").read_text())["scenarios"]
        known = {s.id: s for s in scenarios}
        if len(set(ids)) != len(ids) or set(ids) - known.keys():
            parser.error("suite has duplicate or unknown IDs")
        scenarios = [known[i] for i in ids]
    run_id = args.run_id or datetime.now(UTC).strftime("run_%Y%m%d_%H%M%S_%f")
    report = run_suite(
        scenarios,
        systems=[SystemUnderTest(s) for s in args.systems],
        trials=args.trials,
        runtime_factory=EchoRuntime,
        simulator_factory=StopSimulator,
        url=database_url(),
        policies_dir=Path("policies"),
        reports_dir=Path("evals/reports"),
        suite=args.suite,
        run_id=run_id,
        max_cost_usd=args.max_cost_usd,
        workers=args.workers,
        resume=args.resume,
    )
    print(f"Wrote evals/reports/{report.run_id}.json and .md; fake echo runtime, not agent results")


if __name__ == "__main__":
    main()
