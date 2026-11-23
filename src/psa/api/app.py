"""HTTP adapter over the frozen runtime ports and durable store."""

import base64
import hmac
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

import yaml
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from psa.api import models as m
from psa.api.auth import Settings, issue, verify
from psa.clock import Clock
from psa.domain import EvalRunReport, EventType, SystemUnderTest
from psa.policy import PolicyRegistry
from psa.runtime.ports import ApprovalResolution, RuntimeConfig, RuntimeFactory, SessionStart
from psa.store import CommerceRepo, EventLog
from psa.store.models import ApprovalRow, ApprovalStatus, ConversationRow


def create_app(
    *,
    runtime_factory: RuntimeFactory,
    sessions: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
) -> FastAPI:
    app = FastAPI(title="Policy-Safe Action Agent", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    registry = PolicyRegistry.from_dir(settings.policies_dir)
    registry.get(settings.policy_set, settings.policy_version)
    runtime = runtime_factory(
        RuntimeConfig(
            system=SystemUnderTest.GUARDED,
            policy_set=settings.policy_set,
            policy_version=settings.policy_version,
        ),
        sessions=sessions,
        clock=clock,
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": codes.get(exc.status_code, "HTTP_ERROR"),
                    "message": str(exc.detail),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request does not match the API schema",
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "error": {"code": "STORE_UNAVAILABLE", "message": "The data store is unavailable"}
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {"code": "INTERNAL_ERROR", "message": "The request could not be completed"}
            },
        )

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Bearer token required")
        try:
            verify(authorization[7:], settings.app_auth_secret.get_secret_value(), clock.now())
        except ValueError as error:
            raise HTTPException(401, str(error)) from error

    api = APIRouter(prefix="/api", dependencies=[Depends(authorize)])

    @app.post("/api/auth/demo-login", response_model=m.LoginResponse)
    def login(body: m.LoginRequest) -> m.LoginResponse:
        if not hmac.compare_digest(
            body.passcode.encode(), settings.demo_passcode.get_secret_value().encode()
        ):
            raise HTTPException(401, "Invalid demo passcode")
        expires = clock.now() + timedelta(seconds=settings.token_ttl_seconds)
        return m.LoginResponse(
            token=issue(settings.app_auth_secret.get_secret_value(), expires), expires_at=expires
        )

    @app.get("/api/health", response_model=m.Health)
    def health() -> m.Health:
        return m.Health(policy_version=runtime.config.policy_version)

    @api.post("/conversations", status_code=201, response_model=m.ConversationCreated)
    def start(body: m.ConversationRequest) -> m.ConversationCreated:
        customer_id = None
        if body.customer_email:
            with sessions() as session:
                customer = CommerceRepo(session).find_customer_by_email(body.customer_email)
                if customer is None:
                    raise HTTPException(404, "Customer not found")
                customer_id = customer.customer_id
        # Email lookup identifies the demo customer; it never verifies identity.
        identifier = runtime.start_conversation(
            SessionStart(customer_id=customer_id, identity_verified=False)
        )
        with sessions() as session:
            row = session.get(ConversationRow, identifier)
            if row is None:
                raise HTTPException(500, "Runtime did not persist the conversation")
            return m.ConversationCreated(conversation_id=identifier, started_at=row.started_at)

    def require_conversation(session: Session, identifier: str) -> ConversationRow:
        row = session.get(ConversationRow, identifier)
        if row is None:
            raise HTTPException(404, "Conversation not found")
        return row

    @api.get("/conversations", response_model=m.Conversations)
    def conversations(
        limit: Annotated[int, Query(ge=1, le=200)] = 50, cursor: str | None = None
    ) -> m.Conversations:
        query = select(ConversationRow)
        if cursor:
            try:
                stamp, identifier = json.loads(
                    base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                )
                at = datetime.fromisoformat(stamp)
                if at.tzinfo is None or not isinstance(identifier, str):
                    raise ValueError("invalid cursor")
            except (ValueError, TypeError, UnicodeError) as error:
                raise HTTPException(400, "Invalid cursor") from error
            query = query.where(
                or_(
                    ConversationRow.started_at < at,
                    and_(
                        ConversationRow.started_at == at,
                        ConversationRow.conversation_id < identifier,
                    ),
                )
            )
        query = query.order_by(
            ConversationRow.started_at.desc(), ConversationRow.conversation_id.desc()
        ).limit(limit + 1)
        items = []
        with sessions() as session:
            rows = list(session.scalars(query))
            for row in rows[:limit]:
                events = EventLog(session).read(row.conversation_id)
                items.append(
                    m.ConversationSummary(
                        conversation_id=row.conversation_id,
                        started_at=row.started_at,
                        last_event_at=events[-1].at if events else row.started_at,
                        customer_id=row.customer_id,
                        status=row.status.value,
                        message_count=sum(
                            e.type in {EventType.USER_MESSAGE, EventType.AGENT_MESSAGE}
                            for e in events
                        ),
                        actions_executed=sum(e.type == EventType.ACTION_EXECUTED for e in events),
                        actions_blocked=sum(
                            e.type == EventType.POLICY_DECISION
                            and e.payload.get("decision", {}).get("outcome") != "ALLOW"
                            for e in events
                        ),
                    )
                )
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = (
                base64.urlsafe_b64encode(
                    json.dumps([last.started_at.isoformat(), last.conversation_id]).encode()
                )
                .decode()
                .rstrip("=")
            )
        return m.Conversations(items=items, next_cursor=next_cursor)

    @api.post("/conversations/{conversation_id}/messages", response_model=m.MessageResponse)
    def message(conversation_id: str, body: m.MessageRequest) -> m.MessageResponse:
        with sessions() as session:
            require_conversation(session, conversation_id)
        turn = runtime.handle_user_message(conversation_id, body.text)
        at = next(
            (e.at for e in reversed(turn.events) if e.type == EventType.AGENT_MESSAGE), clock.now()
        )
        return m.MessageResponse(
            reply=m.Reply(text=turn.reply_text, at=at),
            events=turn.events,
            pending_approval_id=turn.pending_approval_id,
        )

    @api.get("/conversations/{conversation_id}/events", response_model=m.EventsResponse)
    def events(conversation_id: str) -> m.EventsResponse:
        with sessions() as session:
            require_conversation(session, conversation_id)
            return m.EventsResponse(
                conversation_id=conversation_id, events=EventLog(session).read(conversation_id)
            )

    @api.get("/approvals", response_model=m.Approvals)
    def approvals(status: Literal["pending", "approved", "rejected"] = "pending") -> m.Approvals:
        with sessions() as session:
            rows = session.scalars(
                select(ApprovalRow)
                .where(ApprovalRow.status == ApprovalStatus(status))
                .order_by(ApprovalRow.requested_at, ApprovalRow.approval_id)
            )
            return m.Approvals(items=[m.Approval.model_validate(row) for row in rows])

    @api.post("/approvals/{approval_id}/resolve", response_model=m.Approval)
    def resolve(approval_id: str, body: m.ResolveRequest) -> m.Approval:
        # Serialize API callers across workers without locking the row needed by the runtime.
        with sessions.begin() as guard:
            guard.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": "api-approval:" + approval_id},
            )
            row = guard.get(ApprovalRow, approval_id)
            if row is None:
                raise HTTPException(404, "Approval not found")
            if row.status != ApprovalStatus.PENDING:
                raise HTTPException(409, "Approval already resolved")
            try:
                runtime.resolve_approval(
                    approval_id,
                    ApprovalResolution(body.resolution),
                    reviewer="demo-operator",
                    note=body.note,
                )
            except (ValueError, LookupError) as error:
                raise HTTPException(409, "Approval cannot be resolved") from error
            guard.refresh(row)
            if row.status == ApprovalStatus.PENDING:
                raise HTTPException(500, "Runtime did not persist the resolution")
            return m.Approval.model_validate(row)

    @api.get("/policies", response_model=m.Policies)
    def policies() -> m.Policies:
        return m.Policies(
            items=[
                m.PolicySummary(
                    policy_set=p.policy_set,
                    version=p.version,
                    rule_count=len(p.rules),
                    updated_at=datetime.fromtimestamp(
                        (settings.policies_dir / p.policy_set / f"{p.version}.yaml")
                        .stat()
                        .st_mtime,
                        UTC,
                    ),
                )
                for p in registry.all()
            ]
        )

    def policy_yaml(policy_set: str, version: str) -> str:
        return (settings.policies_dir / policy_set / f"{version}.yaml").read_text(encoding="utf-8")

    @api.get("/policies/{policy_set}", response_model=m.PolicyDetail)
    def policy(policy_set: str) -> m.PolicyDetail:
        try:
            p = (
                registry.get(policy_set, runtime.config.policy_version)
                if policy_set == runtime.config.policy_set
                else registry.latest(policy_set)
            )
        except KeyError as error:
            raise HTTPException(404, "Policy not found") from error
        return m.PolicyDetail(
            policy_set=p.policy_set,
            version=p.version,
            yaml=policy_yaml(p.policy_set, p.version),
            rules=[
                m.PolicyRule(id=r.id, applies_to=tuple(r.applies_to), description=r.description)
                for r in p.rules
            ],
        )

    @api.get("/policies/{policy_set}/diff", response_model=m.PolicyDiff)
    def policy_diff(
        policy_set: str,
        from_version: Annotated[str, Query(alias="from")],
        to_version: Annotated[str, Query(alias="to")],
    ) -> m.PolicyDiff:
        def source_rules(version: str) -> dict[str, dict[str, Any]]:
            policy = registry.get(policy_set, version)
            raw = yaml.safe_load(policy_yaml(policy.policy_set, policy.version))
            return {rule["id"]: rule for rule in raw["rules"]}

        try:
            before = source_rules(from_version)
            after = source_rules(to_version)
        except KeyError as error:
            raise HTTPException(404, "Policy version not found") from error

        common = sorted(before.keys() & after.keys())
        return m.PolicyDiff(
            policy_set=policy_set,
            from_version=from_version,
            to_version=to_version,
            added=[
                m.RuleRef(id=key, rule=after[key]) for key in sorted(after.keys() - before.keys())
            ],
            removed=[
                m.RuleRef(id=key, rule=before[key]) for key in sorted(before.keys() - after.keys())
            ],
            changed=[
                m.RuleChange(id=key, before=before[key], after=after[key])
                for key in common
                if before[key] != after[key]
            ],
            unchanged=[key for key in common if before[key] == after[key]],
        )

    def reports() -> list[EvalRunReport]:
        return [
            EvalRunReport.model_validate_json(p.read_text(encoding="utf-8"))
            for p in settings.reports_dir.glob("*.json")
            if not p.name.endswith(".checkpoint.json")
        ]

    @api.get("/evals/runs", response_model=m.Runs)
    def runs(limit: Annotated[int, Query(ge=1, le=200)] = 20) -> m.Runs:
        ordered = sorted(reports(), key=lambda r: (r.started_at, r.run_id), reverse=True)[:limit]
        return m.Runs(
            items=[
                m.RunSummary(
                    **r.model_dump(
                        include={
                            "run_id",
                            "suite",
                            "started_at",
                            "finished_at",
                            "git_sha",
                            "policy_version",
                        }
                    ),
                    headline={
                        s.system.value: m.Headline(
                            task_success_rate=s.task_success_rate,
                            unauthorized_action_rate=s.unauthorized_action_rate,
                        )
                        for s in r.systems
                    },
                )
                for r in ordered
            ]
        )

    @api.get("/evals/runs/{run_id}", response_model=EvalRunReport)
    def run(run_id: str) -> EvalRunReport:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
            raise HTTPException(404, "Run not found")
        path = settings.reports_dir / f"{run_id}.json"
        if not path.is_file():
            raise HTTPException(404, "Run not found")
        return EvalRunReport.model_validate_json(path.read_text(encoding="utf-8"))

    app.include_router(api)
    return app
