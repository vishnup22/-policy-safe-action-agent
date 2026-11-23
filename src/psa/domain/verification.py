"""Identity verification contract (T5.0). Implemented by `psa.verification` (Lane H).

The agent calls the read-only tool `verify_identity` with what the customer typed.
The check runs against the system of record only (customer email + the order's
shipping postal code); conversation claims never verify anyone. On success the
conversation's `customer_id` is set and `identity_verified` becomes true, so the
policy fact `session.identity_verified` flips for the rest of the conversation.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class VerificationMethod(StrEnum):
    EMAIL_AND_POSTAL_CODE = "email_and_postal_code"


class VerifyIdentityArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str = Field(pattern=r"^ord_[a-z0-9]{6,}$")
    email: str = Field(min_length=3, max_length=254)
    postal_code: str = Field(min_length=3, max_length=16)


class VerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verified: bool
    method: VerificationMethod = VerificationMethod.EMAIL_AND_POSTAL_CODE
    customer_id: str | None = Field(default=None, description="Set only when verified")
    attempts_remaining: int = Field(ge=0, description="Per conversation; 0 locks verification")
    message: str = Field(description="Safe to show the customer; never reveals which field failed")


MAX_VERIFICATION_ATTEMPTS = 3
