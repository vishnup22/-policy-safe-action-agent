"""Scenario execution through runtime ports, with bounded turns and resumable checkpoints."""

import hashlib
import json
import math
import re
import shutil
import subprocess
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from evals.metrics import TrialRecord, metrics, percentile
from evals.report import atomic_write, write_report
from evals.runner.audit import EVAL_REVIEWER, ExecutionAudit
from evals.runner.database import trial_database
from evals.runner.judge import check_final_state, judge_events
from evals.schema import Scenario
from evals.validate import materialize_world
from psa.clock import SimulatedClock
from psa.domain import EvalRunReport, Event, EventType, ScenarioResult, SystemUnderTest, TrialResult
from psa.policy import PolicyRegistry
from psa.runtime.ports import (
    ApprovalResolution,
    RuntimeConfig,
    RuntimeFactory,
    SessionStart,
    SimulatorTurn,
    ToolFault,
    UserSimulator,
)
from psa.scheduler import Scheduler
from psa.seed.loader import load_world
from psa.store import EventLog


class Budget:
    """Serialize billable turns so parallel trials cannot oversubscribe the remaining budget.

    The frozen ports expose usage only after a synchronous turn, so the last turn may
    exceed the threshold. No further runtime or simulator call is made after that turn.
    """

    def __init__(self, maximum: float, spent: float = 0):
        if not math.isfinite(maximum) or maximum < 0:
            raise ValueError("budget cannot be negative")
        self.maximum, self.spent = maximum, spent
        self.lock = threading.Lock()


class Checkpoint(BaseModel):
    fingerprint: str
    started_at: datetime
    records: list[TrialRecord]
    budget_spent: float


def run_trial(
    scenario: Scenario,
    system: SystemUnderTest,
    trial: int,
    *,
    runtime_factory: RuntimeFactory,
    simulator: UserSimulator,
    sessions: sessionmaker[Session],
    registry: PolicyRegistry,
    budget: Budget,
) -> TrialRecord:
    world = materialize_world(scenario)
    with sessions.begin() as db:
        load_world(world, db)
    clock = SimulatedClock(scenario.world.now)
    config = RuntimeConfig(
        system=system,
        policy_set=scenario.policy.set,
        policy_version=scenario.policy.version,
        faults=tuple(ToolFault.model_validate(f.model_dump()) for f in scenario.faults),
    )
    runtime = runtime_factory(config, sessions=sessions, clock=clock)
    conversation = runtime.start_conversation(SessionStart(**scenario.session.model_dump()))
    transcript: list[SimulatorTurn] = []
    turn_count = 0
    turn_events: list[Event] = []
    version_at: dict[int, str] = {}
    active_version = scenario.policy.version
    failure: str | None = None
    budget_interrupted = False
    with ExecutionAudit(
        sessions,
        world,
        registry,
        clock,
        scenario.policy.set,
        lambda: active_version,
        allow_operator_approval=scenario.operator_resolution == "approved",
    ) as audit:
        for number in range(1, scenario.max_turns + 1):
            for advance in scenario.clock_advance:
                if advance.at_turn == number:
                    clock.advance(advance.by)
            if scenario.poll_follow_ups:
                Scheduler(sessions, clock).run_due()
            if scenario.policy_change and scenario.policy_change.at_turn == number:
                registry.get(scenario.policy.set, scenario.policy_change.to_version)
                active_version = scenario.policy_change.to_version
                runtime.set_policy_version(active_version)
            with budget.lock:
                if budget.spent >= budget.maximum:
                    failure = "budget exhausted"
                    budget_interrupted = True
                    break
                message = (
                    scenario.opening_message
                    if number == 1
                    else simulator.next_message(scenario, transcript)
                )
                if message is None:
                    break
                transcript.append(SimulatorTurn(role="user", text=message))
                with sessions() as db:
                    previous = EventLog(db).read(conversation)
                    last_seq = previous[-1].seq if previous else -1
                turn = None
                operator_turn = None
                try:
                    turn = runtime.handle_user_message(conversation, message)
                    if turn.pending_approval_id and scenario.operator_resolution:
                        resolution = ApprovalResolution(scenario.operator_resolution)
                        operator_turn = runtime.resolve_approval(
                            turn.pending_approval_id, resolution, reviewer=EVAL_REVIEWER
                        )
                        if scenario.repeat_resolution:
                            try:
                                runtime.resolve_approval(
                                    turn.pending_approval_id, resolution, reviewer=EVAL_REVIEWER
                                )
                            except LookupError:
                                pass
                            else:
                                failure = "runtime accepted a second approval resolution"
                except Exception as error:
                    failure = f"runtime failure: {type(error).__name__}"
                with sessions() as db:
                    appended = [e for e in EventLog(db).read(conversation) if e.seq > last_seq]
                observed = appended or [
                    event for step in (turn, operator_turn) if step for event in step.events
                ]
                turn_events.extend(observed)
                for event in observed:
                    version_at[event.seq] = active_version
                budget.spent += sum(
                    float(e.payload["cost_usd"]) for e in observed if e.type == EventType.MODEL_CALL
                )
                if turn is None or failure:
                    break
                turn_count += 1
                transcript.append(SimulatorTurn(role="agent", text=turn.reply_text))
                if operator_turn:
                    transcript.append(SimulatorTurn(role="agent", text=operator_turn.reply_text))
                if turn.ended:
                    break
    with sessions() as db:
        events = EventLog(db).read(conversation)
        # Reference fakes may not persist events; real runtimes must, per the frozen port.
        if not events:
            events = turn_events
        judgment = judge_events(
            scenario,
            world,
            events,
            registry,
            version_at=version_at,
            audited=audit.decisions,
            approved_executions=audit.approved_executions,
        )
        judgment.errors.extend(check_final_state(scenario, world, db))
    if failure:
        judgment.errors.append(failure)
    return TrialRecord(
        scenario_id=scenario.id,
        category=scenario.category,
        system=system,
        result=TrialResult(
            trial=trial,
            success=not judgment.errors,
            unauthorized_actions=tuple(judgment.unauthorized),
            false_refusal=judgment.false_refusal,
            escalated=judgment.escalated,
            turns=turn_count,
            latency_ms_p50=percentile(judgment.latencies, 0.5),
            latency_ms_p95=percentile(judgment.latencies, 0.95),
            cost_usd=judgment.cost,
            conversation_id=conversation,
            failure_reason="; ".join(judgment.errors) or None,
        ),
        executed=judgment.executed,
        duplicates=judgment.duplicates,
        escalation_expected=scenario.expected.outcome == "escalated",
        latencies=judgment.latencies,
        unattributed_executions=sum("no proposed intent" in e for e in judgment.errors),
        budget_interrupted=budget_interrupted,
    )


def run_suite(
    scenarios: list[Scenario],
    *,
    systems: list[SystemUnderTest],
    trials: int,
    runtime_factory: RuntimeFactory,
    simulator_factory: Callable[[], UserSimulator],
    url: str,
    policies_dir: Path,
    reports_dir: Path,
    suite: str,
    run_id: str,
    max_cost_usd: float = 10,
    workers: int = 1,
    resume: bool = False,
    agent_model: str = "fake",
    simulator_model: str = "scripted",
) -> EvalRunReport:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("invalid run id")
    if trials < 1 or workers < 1 or not scenarios or not systems:
        raise ValueError("empty or invalid run")
    if len(set(systems)) != len(systems) or len({s.id for s in scenarios}) != len(scenarios):
        raise ValueError("duplicate systems or scenarios")
    registry = PolicyRegistry.from_dir(policies_dir)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "scenarios": [s.model_dump(mode="json") for s in scenarios],
                "policies": [p.model_dump(mode="json") for p in registry.all()],
                "systems": systems,
                "trials": trials,
                "agent_model": agent_model,
                "simulator_model": simulator_model,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    path = reports_dir / f"{run_id}.checkpoint.json"
    started = datetime.now(UTC)
    records: list[TrialRecord] = []
    spent = 0.0
    if path.exists():
        if not resume:
            raise ValueError("run exists; choose a new run id or --resume")
        checkpoint = Checkpoint.model_validate_json(path.read_text())
        if checkpoint.fingerprint != fingerprint:
            raise ValueError("resume inputs differ from checkpoint")
        started, records, spent = checkpoint.started_at, checkpoint.records, checkpoint.budget_spent
    budget = Budget(max_cost_usd, spent)
    completed = {
        (r.scenario_id, r.system, r.result.trial) for r in records if not r.budget_interrupted
    }

    def execute(scenario: Scenario, system: SystemUnderTest, index: int) -> TrialRecord | None:
        with budget.lock:
            if budget.spent >= budget.maximum:
                return None
        with trial_database(url) as sessions:
            return run_trial(
                scenario,
                system,
                index,
                runtime_factory=runtime_factory,
                simulator=simulator_factory(),
                sessions=sessions,
                registry=registry,
                budget=budget,
            )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = [
            pool.submit(execute, s, system, index)
            for s in scenarios
            for system in systems
            for index in range(trials)
            if (s.id, system, index) not in completed
        ]
        for future in as_completed(pending):
            record = future.result()
            if record is not None:
                records = [
                    previous
                    for previous in records
                    if (previous.scenario_id, previous.system, previous.result.trial)
                    != (record.scenario_id, record.system, record.result.trial)
                ]
                records.append(record)
            records.sort(key=lambda r: (r.scenario_id, r.system, r.result.trial))
            atomic_write(
                path,
                Checkpoint(
                    fingerprint=fingerprint,
                    started_at=started,
                    records=records,
                    budget_spent=budget.spent,
                ).model_dump_json(indent=2)
                + "\n",
            )
    grouped = []
    for scenario in scenarios:
        for system in systems:
            results = tuple(
                r.result for r in records if r.scenario_id == scenario.id and r.system == system
            )
            if results:
                grouped.append(
                    ScenarioResult(
                        scenario_id=scenario.id,
                        category=scenario.category,
                        system=system,
                        trials=results,
                    )
                )
    sha = subprocess.run(  # noqa: S603 - fixed git arguments, no user command
        [shutil.which("git") or "git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    report = EvalRunReport(
        run_id=run_id,
        suite=suite,
        started_at=started,
        finished_at=datetime.now(UTC),
        git_sha=sha,
        policy_version=",".join(sorted({s.policy.version for s in scenarios})),
        agent_model=agent_model,
        simulator_model=simulator_model,
        systems=tuple(metrics(system, records) for system in systems),
        scenarios=tuple(grouped),
    )
    write_report(report, reports_dir)
    return report
