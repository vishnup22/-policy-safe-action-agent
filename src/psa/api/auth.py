"""Demo authentication: expiring, purpose-bound HMAC tokens, no extra dependency."""

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    demo_passcode: SecretStr
    app_auth_secret: SecretStr = Field(min_length=32)
    token_ttl_seconds: int = Field(default=86400, gt=0)
    web_origin: str = "http://localhost:3000"
    policy_set: str = "larkspur-returns"
    policy_version: str = "2026.11.21-1"
    policies_dir: Path = Path("policies")
    reports_dir: Path = Path("evals/reports")


def encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def sign(payload: dict[str, object], secret: str) -> str:
    body = encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{encode(signature)}"


def verify(token: str, secret: str, now: datetime) -> None:
    try:
        body, signature = token.split(".")
        expected = encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload["aud"] != "psa-demo" or payload["sub"] != "demo-operator":
            raise ValueError("invalid principal")
        if not isinstance(payload["exp"], int) or payload["exp"] <= now.timestamp():
            raise ValueError("expired token")
    except (ValueError, KeyError, TypeError, UnicodeError) as error:
        raise ValueError("Invalid or expired bearer token") from error


def issue(secret: str, expires: datetime) -> str:
    return sign(
        {
            "aud": "psa-demo",
            "sub": "demo-operator",
            "exp": int(expires.timestamp()),
            "nonce": secrets.token_hex(16),
        },
        secret,
    )
