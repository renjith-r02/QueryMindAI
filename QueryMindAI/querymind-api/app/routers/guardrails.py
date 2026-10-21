"""The guardrail policy, stored in Qdrant (querymind-agentic `querymind.guardrails`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from querymind.guardrails import (
    LOCKED_RULE_IDS,
    POLITE_TOKEN,
    REQUIRED_SQL_KEYWORDS,
    GuardrailPolicy,
    GuardrailPolicyError,
    GuardrailPolicyInput,
    Guardrails,
)
from querymind.service import QueryMindService

from app.dependencies import get_service

router = APIRouter(prefix="/guardrails", tags=["guardrails"])

Service = Annotated[QueryMindService, Depends(get_service)]


class GuardrailSettings(GuardrailPolicy):
    """The stored policy, plus the parts of the baseline that can't be removed."""

    required_sql_keywords: list[str] = Field(description="Always blocked; cannot be removed")
    locked_rule_ids: list[str] = Field(description="Question rules that cannot be removed or disabled")
    polite_token: str = Field(description="Placeholder in rule patterns for an optional polite lead-in")

    @classmethod
    def of(cls, policy: GuardrailPolicy) -> "GuardrailSettings":
        return cls(
            **policy.model_dump(),
            required_sql_keywords=list(REQUIRED_SQL_KEYWORDS),
            locked_rule_ids=sorted(LOCKED_RULE_IDS),
            polite_token=POLITE_TOKEN,
        )


class GuardrailCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str | None = Field(default=None, min_length=1, max_length=2000)
    sql: str | None = Field(default=None, min_length=1, max_length=20_000)
    policy: GuardrailPolicyInput | None = Field(
        default=None,
        description="Check against this (unsaved) policy instead of the saved one",
    )

    @model_validator(mode="after")
    def _something_to_check(self) -> "GuardrailCheckRequest":
        if self.question is None and self.sql is None:
            raise ValueError("give a question, SQL, or both")
        return self


class QuestionCheck(BaseModel):
    allowed: bool
    rule_id: str | None = None
    message: str | None = None


class SqlCheck(BaseModel):
    allowed: bool
    reason: str | None = None


class GuardrailCheckResponse(BaseModel):
    question: QuestionCheck | None = None
    sql: SqlCheck | None = None


INVALID = {422: {"description": "Invalid policy, or it would remove or disable part of the baseline"}}


def _save(service: QueryMindService, save) -> GuardrailSettings:
    try:
        return GuardrailSettings.of(save(service.guardrail_store))
    except GuardrailPolicyError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None


@router.get("", response_model=GuardrailSettings, summary="Get the guardrail policy")
def get_guardrails(service: Service) -> GuardrailSettings:
    """The policy every question and generated query is checked against. The first call saves
    the built-in policy (its row limit comes from QUERYMIND_MAX_ROWS)."""
    return GuardrailSettings.of(service.guardrail_store.get())


@router.put(
    "",
    response_model=GuardrailSettings,
    responses=INVALID,
    summary="Replace the guardrail policy",
)
def update_guardrails(body: GuardrailPolicyInput, service: Service) -> GuardrailSettings:
    """Applies to new questions straight away. Locked question rules can be reworded (and given
    more patterns) but not removed or disabled, and the required SQL keywords stay blocked."""
    return _save(service, lambda store: store.save(body))


@router.post(
    "/reset",
    response_model=GuardrailSettings,
    summary="Restore the built-in guardrail policy",
)
def reset_guardrails(service: Service) -> GuardrailSettings:
    return _save(service, lambda store: store.reset())


@router.post(
    "/check",
    response_model=GuardrailCheckResponse,
    summary="Test a question or SQL against the policy",
)
def check_guardrails(body: GuardrailCheckRequest, service: Service) -> GuardrailCheckResponse:
    """Nothing is generated or run. `question` is checked against the question rules; `sql` is
    checked the way generated SQL is before it runs (read-only, keywords, restricted columns)."""
    if body.policy is not None:
        guardrails = Guardrails(GuardrailPolicy(**body.policy.model_dump()))
    else:
        guardrails = Guardrails(service.guardrail_store.get())
    response = GuardrailCheckResponse()
    if body.question is not None:
        rule = guardrails.refuse(body.question)
        response.question = QuestionCheck(
            allowed=rule is None,
            rule_id=rule.id if rule else None,
            message=rule.message if rule else None,
        )
    if body.sql is not None:
        reason = guardrails.check_sql(body.sql)
        response.sql = SqlCheck(allowed=reason is None, reason=reason)
    return response
