from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreate(StrictModel):
    title: str = Field(default="New complaint", min_length=1, max_length=120)


class UserMessageCreate(StrictModel):
    text: str = Field(min_length=3, max_length=12_000)
    start_new_incident: bool = False


class AnalyzeRequest(StrictModel):
    complaint: str = Field(min_length=3, max_length=12_000)


class DraftCreate(StrictModel):
    session_id: str
    details: dict[str, str] = Field(default_factory=dict)


class DraftPatch(StrictModel):
    expected_version: int = Field(ge=1)
    changes: dict[str, str]


class DraftConfirm(StrictModel):
    expected_version: int = Field(ge=1)
    explicit_confirmation: Literal[True]


class DraftCancel(StrictModel):
    expected_version: int = Field(ge=1)


class DraftReanalyze(StrictModel):
    expected_version: int = Field(ge=1)


class CaseSubmit(StrictModel):
    draft_id: str
    reporter_role: Literal["self", "witness", "on_behalf"]
    reporter_relationship: str = Field(default="", max_length=500)
    affected_person_name: str = Field(default="", max_length=300)
    declaration_accepted: Literal[True]


class CaseMessageCreate(StrictModel):
    text: str = Field(min_length=1, max_length=12_000)


class CaseReviewRequest(StrictModel):
    reason: str = Field(min_length=10, max_length=4_000)


class CaseDecision(StrictModel):
    action: Literal["request_information", "under_review", "ready_to_refer", "out_of_scope", "close", "reopen"]
    reason: str = Field(min_length=10, max_length=4_000)


class EvidenceCreate(StrictModel):
    filename: str = Field(min_length=1, max_length=180)
    content_type: Literal["image/jpeg", "image/png", "application/pdf"]
    data_base64: str = Field(min_length=4, max_length=11_200_000)


class ApiMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    structured: dict[str, Any] | None = None
    created_at: str
