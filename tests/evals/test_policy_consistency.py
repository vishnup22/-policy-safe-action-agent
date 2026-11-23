"""All authored action oracles are checked against the real versioned policy engine."""

from pathlib import Path

import pytest
import yaml
from evals.policy_oracle import policy_checks
from evals.schema import Scenario

from psa.policy import PolicyRegistry

ROOT = Path(__file__).resolve().parents[2]
FILES = sorted((ROOT / "evals/scenarios").rglob("*.yaml"))
REGISTRY = PolicyRegistry.from_dir(ROOT / "policies")


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_policy_consistency(path: Path) -> None:
    scenario = Scenario.model_validate(yaml.safe_load(path.read_text()))
    for kind, decision, expected in policy_checks(scenario, REGISTRY):
        assert decision.outcome == expected, (scenario.id, kind, decision.model_dump())


def test_regression_suite_covers_every_category() -> None:
    scenarios = {
        s.id: s for s in (Scenario.model_validate(yaml.safe_load(p.read_text())) for p in FILES)
    }
    ids = yaml.safe_load((ROOT / "evals/suites/regression.yaml").read_text())["scenarios"]
    assert len(ids) == 25
    assert len(set(ids)) == 25
    assert {scenarios[i].category for i in ids} == {s.category for s in scenarios.values()}
