"""HTTP contract, auth, cursor pagination, and durable runtime routing."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker
from tests.api.fakes import PersistedFake

from psa.api import Settings, create_app
from psa.api.auth import issue, verify
from psa.api.models import PolicyDiff
from psa.clock import SimulatedClock
from psa.domain import ActionIntent, Decision, DecisionOutcome, IssueRefundArgs
from psa.seed import generate_world
from psa.seed.loader import load_world
from psa.store.models import ApprovalRow, ApprovalStatus

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 21, 12, tzinfo=UTC)


def settings(tmp_path: Path) -> Settings:
    return Settings(
        demo_passcode=SecretStr("test-passcode"),
        app_auth_secret=SecretStr("s" * 32),
        policies_dir=ROOT / "policies",
        reports_dir=tmp_path,
    )


@pytest.mark.db
def test_all_http_routes(sessions: sessionmaker[Session], tmp_path: Path) -> None:
    world = generate_world(42, NOW)
    with sessions.begin() as db:
        load_world(world, db)
    clock = SimulatedClock(NOW)
    app = create_app(
        runtime_factory=PersistedFake, sessions=sessions, clock=clock, settings=settings(tmp_path)
    )
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/conversations").status_code == 401
        assert client.post("/api/auth/demo-login", json={"passcode": "wrong"}).status_code == 401
        login = client.post("/api/auth/demo-login", json={"passcode": "test-passcode"})
        assert login.status_code == 200
        client.headers["Authorization"] = "Bearer " + login.json()["token"]
        created = client.post(
            "/api/conversations", json={"customer_email": world.customers[0].email}
        )
        assert created.status_code == 201
        identifier = created.json()["conversation_id"]
        assert client.post("/api/conversations", json={}).status_code == 201
        page = client.get("/api/conversations?limit=1").json()
        assert page["next_cursor"]
        following = client.get(
            "/api/conversations", params={"limit": 1, "cursor": page["next_cursor"]}
        ).json()
        assert following["items"][0]["conversation_id"] != page["items"][0]["conversation_id"]
        assert following["next_cursor"] is None
        assert client.get("/api/conversations?cursor=bad").status_code == 400
        assert (
            client.post(
                "/api/conversations", json={"customer_email": "missing@example.com"}
            ).status_code
            == 404
        )
        turn = client.post(f"/api/conversations/{identifier}/messages", json={"text": "hello"})
        assert turn.json()["reply"]["text"] == "echo: hello"
        events = client.get(f"/api/conversations/{identifier}/events").json()["events"]
        assert [e["seq"] for e in events] == [0, 1, 2]
        assert client.get("/api/conversations/missing/events").status_code == 404
        assert (
            client.post("/api/conversations/missing/messages", json={"text": "hello"}).status_code
            == 404
        )
        assert (
            client.post(f"/api/conversations/{identifier}/messages", json={"text": ""}).status_code
            == 422
        )
        assert client.get("/api/policies").json()["items"]
        assert client.get("/api/policies/larkspur-returns").json()["version"] == "2026.11.21-1"
        assert client.get("/api/policies/missing").status_code == 404
        assert client.get("/api/evals/runs").json() == {"items": []}
        assert client.get("/api/evals/runs/missing").status_code == 404
        intent = ActionIntent(
            intent_id="int_approval0001",
            conversation_id=identifier,
            customer_id=world.customers[0].customer_id,
            args=IssueRefundArgs(
                order_id=world.orders[0].order_id, amount_cents=30000, reason="Synthetic refund"
            ),
            justification="Test approval",
            proposed_at=NOW,
            idempotency_key="approval-key-0001",
        )
        decision = Decision(
            intent_id=intent.intent_id,
            outcome=DecisionOutcome.REQUIRE_APPROVAL,
            rule_results=(),
            policy_set="larkspur-returns",
            policy_version="2026.11.21-1",
            evaluated_at=NOW,
            facts_snapshot={},
        )
        with sessions.begin() as db:
            db.add(
                ApprovalRow(
                    approval_id="apr_test0001",
                    conversation_id=identifier,
                    intent_id=intent.intent_id,
                    intent=intent.model_dump(mode="json"),
                    decision=decision.model_dump(mode="json"),
                    status=ApprovalStatus.PENDING,
                    requested_at=NOW,
                )
            )
        assert len(client.get("/api/approvals").json()["items"]) == 1
        resolved = client.post(
            "/api/approvals/apr_test0001/resolve", json={"resolution": "rejected", "note": "Test"}
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "rejected"
        assert (
            client.post(
                "/api/approvals/apr_test0001/resolve", json={"resolution": "approved"}
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/approvals/missing/resolve", json={"resolution": "rejected"}
            ).status_code
            == 404
        )
        assert len(client.get("/api/approvals?status=rejected").json()["items"]) == 1
        clock.advance(timedelta(days=1))
        assert client.get("/api/conversations").status_code == 401


def test_policy_diff_returns_raw_rules_and_requires_auth(tmp_path: Path) -> None:
    config = settings(tmp_path)
    app = create_app(
        runtime_factory=PersistedFake,
        sessions=sessionmaker(),
        clock=SimulatedClock(NOW),
        settings=config,
    )
    policy_set = "larkspur-returns"
    first, second = "2026.11.21-1", "2026.11.21-2"
    endpoint = f"/api/policies/{policy_set}/diff"
    versions = {"from": first, "to": second}

    def raw_window(version: str) -> dict[str, object]:
        policy = (config.policies_dir / policy_set / f"{version}.yaml").read_text(encoding="utf-8")
        return next(
            rule for rule in yaml.safe_load(policy)["rules"] if rule["id"] == "REFUND_WINDOW"
        )

    with TestClient(app) as client:
        assert client.get(endpoint, params=versions).status_code == 401
        login = client.post("/api/auth/demo-login", json={"passcode": "test-passcode"})
        client.headers["Authorization"] = "Bearer " + login.json()["token"]
        response = client.get(endpoint, params=versions)
        assert response.status_code == 200, response.text
        diff = PolicyDiff.model_validate(response.json())
        assert (diff.policy_set, diff.from_version, diff.to_version) == (policy_set, first, second)
        window = next(rule for rule in diff.changed if rule.id == "REFUND_WINDOW")
        assert window.before == raw_window(first)
        assert window.after == raw_window(second)
        assert "ORDER_EXISTS" in diff.unchanged
        assert client.get(endpoint, params={"from": first, "to": "unknown"}).status_code == 404
        assert client.get(endpoint, params={"from": "unknown", "to": second}).status_code == 404
        assert client.get("/api/policies/unknown/diff", params=versions).status_code == 404


def test_token_tampering_and_expiry() -> None:
    secret = "test-secret" * 4
    token = issue(secret, NOW + timedelta(seconds=1))
    verify(token, secret, NOW)
    for invalid in ("bad", token + "x", "x." + token.split(".")[1]):
        with pytest.raises(ValueError):
            verify(invalid, secret, NOW)
    with pytest.raises(ValueError):
        verify(token, secret, NOW + timedelta(seconds=1))


@pytest.mark.db
def test_eval_report_routes_and_cors(sessions: sessionmaker[Session], tmp_path: Path) -> None:
    from evals.metrics import metrics
    from evals.report import write_report

    from psa.domain import EvalRunReport, SystemUnderTest

    report = EvalRunReport(
        run_id="run_test",
        suite="test",
        started_at=NOW,
        finished_at=NOW,
        git_sha="test",
        policy_version="2026.11.21-1",
        agent_model="fake",
        simulator_model="scripted",
        systems=(metrics(SystemUnderTest.GUARDED, []),),
        scenarios=(),
    )
    write_report(report, tmp_path)
    app = create_app(
        runtime_factory=PersistedFake,
        sessions=sessions,
        clock=SimulatedClock(NOW),
        settings=settings(tmp_path),
    )
    with TestClient(app) as client:
        response = client.options(
            "/api/conversations",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        token = client.post("/api/auth/demo-login", json={"passcode": "test-passcode"}).json()[
            "token"
        ]
        client.headers["Authorization"] = "Bearer " + token
        assert client.get("/api/evals/runs").json()["items"][0]["run_id"] == "run_test"
        response = client.get("/api/evals/runs/run_test")
        assert EvalRunReport.model_validate(response.json()) == report
        assert (
            client.get("/api/conversations?limit=0").json()["error"]["code"] == "VALIDATION_ERROR"
        )
