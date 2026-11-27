from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .auth import Principal, authenticated_user
from .config import Settings
from .database import Database
from .inference import InferenceClient, VLLMClient
from .pipeline import LegalPipeline
from .schemas import (
    AnalyzeRequest,
    DraftCancel,
    DraftConfirm,
    DraftCreate,
    DraftPatch,
    DraftReanalyze,
    CaseSubmit,
    CaseMessageCreate,
    CaseReviewRequest,
    CaseDecision,
    EvidenceCreate,
    SessionCreate,
    UserMessageCreate,
)
from .workflow import (
    DRAFT_FIELD_GUIDANCE,
    LEGAL_FACT_FIELDS,
    assistant_response,
    complaint_title,
    contextual_draft_question,
    draft_lookup_requested,
    extract_draft_field,
    extract_draft_facts,
    fallback_unclear_response,
    format_draft_narrative,
    guided_incident_response,
    model_conversational_response,
    render_draft,
    reviewer_research_response,
    rewrite_draft_incident,
    stated_reporter_name,
    validate_draft_details,
)


API_BUILD_ID = "nyayasetu_draft_intake_2026_09_29"


def create_app(
    settings: Settings | None = None,
    pipeline: LegalPipeline | Any | None = None,
    inference: InferenceClient | None = None,
) -> FastAPI:
    runtime_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(runtime_settings.database_path)  # type: ignore[arg-type]
        database.initialize()
        app.state.settings = runtime_settings
        app.state.database = database
        app.state.pipeline = pipeline or LegalPipeline(
            runtime_settings.catalogue_path, inference or VLLMClient(runtime_settings)  # type: ignore[arg-type]
        )
        app.state.session_locks = {}
        app.state.model_slots = asyncio.Semaphore(runtime_settings.max_concurrent_model_requests)
        yield

    app = FastAPI(
        title="Legal AI Complaint Triage API",
        version="1.0.0",
        description=(
            "Source-grounded BNS and IT Act complaint triage with private sessions and local draft workflow."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-LegalAI-Demo-User"],
    )

    def db() -> Database:
        return app.state.database

    def legal_pipeline() -> Any:
        return app.state.pipeline

    def owned_session(database: Database, owner_uid: str, session_id: str) -> dict[str, Any]:
        session = database.get_session(owner_uid, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    def owned_draft(database: Database, owner_uid: str, draft_id: str) -> dict[str, Any]:
        draft = database.get_draft(owner_uid, draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="Draft not found")
        return draft

    def visible_case(database: Database, principal: Principal, case_id: str) -> dict[str, Any]:
        case = database.get_case(case_id)
        if case is None or (case["owner_uid"] != principal.uid and not principal.is_admin):
            raise HTTPException(status_code=404, detail="Case not found")
        return case

    def require_admin(principal: Principal) -> None:
        if not principal.is_admin:
            raise HTTPException(status_code=403, detail="Reviewer access required")

    def require_citizen(principal: Principal) -> None:
        if principal.is_admin:
            raise HTTPException(status_code=403, detail="Reviewers cannot prepare or submit complaints")

    def session_lock(session_id: str) -> asyncio.Lock:
        locks: dict[str, asyncio.Lock] = app.state.session_locks
        return locks.setdefault(session_id, asyncio.Lock())

    async def acquire_model_slot() -> asyncio.Semaphore:
        slots: asyncio.Semaphore = app.state.model_slots
        try:
            await asyncio.wait_for(slots.acquire(), runtime_settings.model_queue_timeout_seconds)
        except TimeoutError as error:
            raise HTTPException(
                status_code=503,
                detail="The model queue is full; retry this request shortly",
            ) from error
        return slots

    async def run_analysis(complaint: str) -> dict[str, Any]:
        slots = await acquire_model_slot()
        try:
            return await legal_pipeline().analyze(complaint)
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=502, detail="Model pipeline is temporarily unavailable") from error
        finally:
            slots.release()

    async def prepare_draft(
        database: Database, principal: Principal, session_id: str,
        supplied_details: dict[str, str] | None = None,
        additional_reporter_words: str = "",
        extract: bool = True,
    ) -> dict[str, Any]:
        require_citizen(principal)
        session = owned_session(database, principal.uid, session_id)
        analysis = database.latest_analysis(principal.uid, session_id)
        if analysis is None or analysis["result"]["outcome"] != "provision_match":
            raise HTTPException(status_code=409, detail="A supported current analysis is required before drafting")
        try:
            details = validate_draft_details(supplied_details or {})
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        inferred: dict[str, str] = {}
        fact_source = format_draft_narrative(session["active_narrative"])
        incident_description = fact_source
        inference_client = getattr(legal_pipeline(), "inference", None)
        if inference_client is not None and extract:
            slots = await acquire_model_slot()
            try:
                missing = tuple(key for key in DRAFT_FIELD_GUIDANCE if not details.get(key))
                inferred = await extract_draft_facts(
                    inference_client,
                    fact_source + "\nReporter also said: " + additional_reporter_words,
                    field_names=missing,
                )
                incident_description = await rewrite_draft_incident(inference_client, fact_source)
            except Exception:
                pass
            finally:
                slots.release()
        fields = {
            "incident_description": incident_description,
            "requested_action": "Please examine the reported facts and take action according to law.",
            **inferred,
            **details,
        }
        provision_ids = analysis["result"]["possible_provision_ids"]
        return database.create_draft(
            principal.uid, session_id, analysis["analysis_id"],
            fields, provision_ids, render_draft(fields, provision_ids),
        )

    async def route_conversation(
        text: str, has_active_incident: bool, last_action: str | None,
        recent_messages: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]] | None:
        inference_client = getattr(legal_pipeline(), "inference", None)
        if inference_client is None:
            return None
        slots = await acquire_model_slot()
        try:
            return await model_conversational_response(
                inference_client, text, has_active_incident, last_action,
                recent_messages,
            )
        except Exception:
            return fallback_unclear_response(has_active_incident)
        finally:
            slots.release()

    def latest_assistant_action(messages: list[dict[str, Any]]) -> str | None:
        for message in reversed(messages):
            if message.get("role") != "assistant":
                continue
            structured = message.get("structured")
            return structured.get("action") if isinstance(structured, dict) else None
        return None

    def is_answer_to_last_question(text: str, messages: list[dict[str, Any]]) -> bool:
        for message in reversed(messages):
            if message.get("role") != "assistant":
                continue
            structured = message.get("structured") or {}
            question = (structured.get("next_question") or {}).get("text")
            if not question:
                analysis = structured.get("analysis") or {}
                uncertain = analysis.get("uncertain_sections") or []
                question = uncertain[0].get("missing_facts") if uncertain else None
            return bool(question and text.strip().startswith(question + "\nAnswer: "))
        return False

    intake_questions = (
        ("reporter_name", "What name should appear on your report?"),
        ("incident_date", "When did this happen? An approximate date is okay."),
        ("location", "Where did this happen? A city, area, or place is enough."),
    )

    def next_intake_question(fields: dict[str, str], skipped: list[str] | None = None) -> tuple[str, str] | None:
        return next(((key, question) for key, question in intake_questions
                     if not fields.get(key, "").strip() and key not in (skipped or [])), None)

    async def intake_response(fields: dict[str, str], key: str, question: str,
                              incident: str, skipped: list[str] | None = None) -> tuple[str, dict[str, Any]]:
        inference_client = getattr(legal_pipeline(), "inference", None)
        if inference_client is not None:
            slots = await acquire_model_slot()
            try:
                question = await contextual_draft_question(inference_client, key, incident, question)
            except Exception:
                pass
            finally:
                slots.release()
        return question, {
            "action": "collect_draft_details", "intake_field": key, "intake_fields": fields,
            "intake_skipped": skipped or [],
            "next_question": {"text": question, "options": ["I don't know"]},
            "draft_is_local_only": True, "official_filing_performed": False,
        }

    @app.get("/health")
    async def health(deep: bool = Query(default=False)) -> dict[str, Any]:
        result: dict[str, Any] = {
            "api": "ready", "database": "ready", "build_id": API_BUILD_ID,
            "auth_mode": runtime_settings.auth_mode,
        }
        if deep:
            inference_client = getattr(legal_pipeline(), "inference", None)
            result["model"] = await inference_client.health() if inference_client else {"ready": True, "mode": "test"}
        return result

    @app.post("/sessions", status_code=status.HTTP_201_CREATED)
    async def create_session(
        body: SessionCreate, principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        return db().create_session(principal.uid, body.title)

    @app.get("/sessions")
    async def list_sessions(principal: Principal = Depends(authenticated_user)) -> list[dict[str, Any]]:
        return db().list_sessions(principal.uid)

    @app.get("/sessions/{session_id}")
    async def get_session(
        session_id: str, principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        session = owned_session(db(), principal.uid, session_id)
        return {**session, "messages": db().list_messages(principal.uid, session_id)}

    @app.delete("/sessions/{session_id}")
    async def remove_session(
        session_id: str, principal: Principal = Depends(authenticated_user),
    ) -> dict[str, str]:
        outcome = db().remove_or_archive_session(principal.uid, session_id)
        if outcome is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"outcome": outcome}

    @app.post("/analyze")
    async def analyze(
        body: AnalyzeRequest, principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        result = await run_analysis(body.complaint)
        record = db().save_analysis(
            principal.uid, None, body.complaint, result,
            result["model_version"], result["kb_version"],
        )
        return {"analysis_id": record["analysis_id"], **result}

    @app.post("/sessions/{session_id}/messages")
    async def add_message(
        session_id: str, body: UserMessageCreate,
        principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        database = db()
        async with session_lock(session_id):
            session = owned_session(database, principal.uid, session_id)
            prior_messages = database.list_messages(principal.uid, session_id)
            last_action = latest_assistant_action(prior_messages)
            user_message = database.add_message(principal.uid, session_id, "user", body.text)
            if last_action == "collect_draft_details" and not principal.is_admin:
                previous = next((item.get("structured") for item in reversed(prior_messages)
                                 if item.get("role") == "assistant"), None) or {}
                fields = dict(previous.get("intake_fields") or {})
                skipped = list(previous.get("intake_skipped") or [])
                field = previous.get("intake_field")
                answer = body.text.rpartition("\nAnswer: ")[2].strip() if "\nAnswer: " in body.text else body.text.strip()
                if answer.casefold() in {"cancel", "stop", "never mind"}:
                    text = "Okay, I stopped preparing the draft. You can ask me to prepare it later."
                    structured = {"action": "conversation", "conversation_kind": "cancelled_intake",
                                  "draft_is_local_only": True, "official_filing_performed": False}
                    assistant_message = database.add_message(principal.uid, session_id, "assistant", text, structured)
                    return {"user_message": user_message, "assistant_message": assistant_message, "analysis_id": None}
                if field in {key for key, _ in intake_questions} and answer.casefold() not in {
                    "i don't know", "not sure", "unknown", "skip", "don't know"
                }:
                    value = ""
                    inference_client = getattr(legal_pipeline(), "inference", None)
                    if inference_client is not None:
                        slots = await acquire_model_slot()
                        try:
                            value = await extract_draft_field(inference_client, field, answer)
                        except Exception:
                            pass
                        finally:
                            slots.release()
                    fields[field] = (value or (stated_reporter_name(answer) if field == "reporter_name" else answer))[:500]
                elif field in {key for key, _ in intake_questions}:
                    skipped.append(field)
                pending = next_intake_question(fields, skipped)
                if pending:
                    text, structured = await intake_response(fields, *pending, session["active_narrative"], skipped=skipped)
                else:
                    created = await prepare_draft(database, principal, session_id, fields)
                    text = "Your editable report draft is ready. Please check every detail, then choose Save for later or Continue to review and send."
                    structured = {"action": "review_draft", "draft_id": created["draft_id"],
                                  "draft_is_local_only": True, "official_filing_performed": False}
                assistant_message = database.add_message(principal.uid, session_id, "assistant", text, structured)
                return {"user_message": user_message, "assistant_message": assistant_message, "analysis_id": None}
            if not principal.is_admin and draft_lookup_requested(body.text):
                existing = next((item for item in database.list_drafts(principal.uid)
                                 if item["session_id"] == session_id and item["status"] != "cancelled"), None)
                if existing:
                    text = "Here is your saved report draft. Open it to review, edit, or continue to the send step."
                    structured = {"action": "review_draft", "draft_id": existing["draft_id"],
                                  "draft_is_local_only": True, "official_filing_performed": False}
                else:
                    text = "There is no report draft in this chat yet. Tell me about the incident, then ask me to prepare one."
                    structured = {"action": "conversation", "conversation_kind": "draft_lookup",
                                  "draft_is_local_only": True, "official_filing_performed": False}
                assistant_message = database.add_message(principal.uid, session_id, "assistant", text, structured)
                return {"user_message": user_message, "assistant_message": assistant_message, "analysis_id": None}
            has_active_incident = bool(session["active_narrative"])
            conversation = None if is_answer_to_last_question(body.text, prior_messages) else await route_conversation(
                body.text, has_active_incident, last_action, prior_messages
            )
            if conversation is not None:
                text, structured = conversation
                if structured.get("conversation_kind") == "draft_request":
                    if principal.is_admin:
                        text = "Research chat can assess reports and provisions. Reviewers cannot prepare or send a citizen complaint."
                    elif not has_active_incident:
                        text = "Tell me what happened first, then I can prepare a draft for your review."
                    elif not (latest := database.latest_analysis(principal.uid, session_id)) or latest["result"]["outcome"] != "provision_match":
                        text = "I need enough facts to identify a supported provision before preparing a draft. Please describe what happened."
                    else:
                        existing = next((item for item in database.list_drafts(principal.uid)
                                         if item["session_id"] == session_id and item["status"] != "cancelled"), None)
                        if existing:
                            structured = {**structured, "action": "review_draft", "draft_id": existing["draft_id"]}
                            text = "Here is your existing report draft. Open it to review or continue."
                        else:
                            inference_client = getattr(legal_pipeline(), "inference", None)
                            fields: dict[str, str] = {}
                            if inference_client is not None:
                                slots = await acquire_model_slot()
                                try:
                                    fields = await extract_draft_facts(
                                        inference_client,
                                        format_draft_narrative(session["active_narrative"]) + "\nReporter also said: " + body.text,
                                        field_names=("reporter_name", "incident_date", "location"),
                                    )
                                except Exception:
                                    pass
                                finally:
                                    slots.release()
                            if not fields.get("reporter_name"):
                                declared_name = stated_reporter_name(body.text)
                                if declared_name:
                                    fields["reporter_name"] = declared_name
                            pending = next_intake_question(fields)
                            if pending:
                                text, structured = await intake_response(fields, *pending, session["active_narrative"])
                            else:
                                created = await prepare_draft(database, principal, session_id, fields)
                                text = "Your editable report draft is ready. Open it to review, edit, or continue to the send step."
                                structured = {**structured, "action": "review_draft", "draft_id": created["draft_id"]}
                assistant_message = database.add_message(
                    principal.uid, session_id, "assistant", text, structured
                )
                return {
                    "user_message": user_message,
                    "assistant_message": assistant_message,
                    "analysis_id": None,
                }
            if body.start_new_incident or not session["active_narrative"]:
                narrative = body.text.strip()
                database.set_session_title(
                    principal.uid, session_id, complaint_title(body.text)
                )
            else:
                narrative = session["active_narrative"].rstrip() + "\nAdditional information from the user: " + body.text.strip()
            database.set_narrative(principal.uid, session_id, narrative)
            result = await run_analysis(narrative)
            analysis = database.save_analysis(
                principal.uid, session_id, narrative, result,
                result["model_version"], result["kb_version"],
            )
            text, structured = assistant_response(result)
            inference_client = getattr(legal_pipeline(), "inference", None)
            if principal.is_admin:
                structured = {**structured, "action": "review_research"}
                if inference_client is not None:
                    slots = await acquire_model_slot()
                    try:
                        text = await reviewer_research_response(inference_client, body.text, result)
                    except Exception:
                        text = "Review the reported facts, the possible sections, and any missing details before recording a decision."
                    finally:
                        slots.release()
            elif inference_client is not None and result["outcome"] == "provision_match":
                prior_questions = [
                    item["structured"]["next_question"]["text"]
                    for item in prior_messages
                    if item.get("role") == "assistant" and isinstance(item.get("structured"), dict)
                    and isinstance(item["structured"].get("next_question"), dict)
                    and item["structured"]["next_question"].get("text")
                ]
                slots = await acquire_model_slot()
                try:
                    guided = await guided_incident_response(
                        inference_client, narrative, result,
                        allow_question=len(prior_questions) < 2,
                        previous_questions=prior_questions,
                    )
                    if guided is not None:
                        text, structured = guided
                except Exception:
                    pass
                finally:
                    slots.release()
            structured["analysis_id"] = analysis["analysis_id"]
            assistant_message = database.add_message(
                principal.uid, session_id, "assistant", text, structured
            )
            return {
                "user_message": user_message,
                "assistant_message": assistant_message,
                "analysis_id": analysis["analysis_id"],
            }

    @app.post("/drafts", status_code=status.HTTP_201_CREATED)
    async def create_draft(
        body: DraftCreate, principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        return await prepare_draft(db(), principal, body.session_id, body.details)

    @app.get("/drafts/{draft_id}")
    async def get_draft(
        draft_id: str, principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        return owned_draft(db(), principal.uid, draft_id)

    @app.get("/drafts")
    async def list_drafts(principal: Principal = Depends(authenticated_user)) -> list[dict[str, Any]]:
        return db().list_drafts(principal.uid)

    @app.patch("/drafts/{draft_id}")
    async def patch_draft(
        draft_id: str, body: DraftPatch,
        principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        require_citizen(principal)
        database = db()
        current = owned_draft(database, principal.uid, draft_id)
        if current["status"] not in {"preview", "needs_reanalysis", "saved"} or database.has_case_for_draft(draft_id):
            raise HTTPException(status_code=409, detail="A submitted case cannot be edited as a draft")
        try:
            changes = validate_draft_details(body.changes)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        fields = {**current["fields"], **changes}
        needs_reanalysis = bool(set(changes) & LEGAL_FACT_FIELDS)
        next_status = "needs_reanalysis" if needs_reanalysis else "preview"
        updated = database.update_draft(
            principal.uid, draft_id, body.expected_version, fields,
            render_draft(fields, current["provision_ids"]), next_status,
            {"changes": changes, "requires_reanalysis": needs_reanalysis},
        )
        if updated is None:
            raise HTTPException(status_code=409, detail="Draft version changed; reload before editing")
        return updated

    @app.post("/drafts/{draft_id}/reanalyze")
    async def reanalyze_draft(
        draft_id: str, body: DraftReanalyze,
        principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        require_citizen(principal)
        database = db()
        current = owned_draft(database, principal.uid, draft_id)
        if current["status"] != "needs_reanalysis":
            raise HTTPException(status_code=409, detail="This draft does not require reanalysis")
        result = await run_analysis(current["fields"]["incident_description"])
        if result["outcome"] != "provision_match":
            raise HTTPException(
                status_code=409,
                detail={"message": "Edited facts no longer support a complaint draft", "analysis": result},
            )
        analysis = database.save_analysis(
            principal.uid, current["session_id"], current["fields"]["incident_description"], result,
            result["model_version"], result["kb_version"],
        )
        provision_ids = result["possible_provision_ids"]
        updated = database.replace_draft_analysis(
            principal.uid, draft_id, body.expected_version, analysis["analysis_id"],
            provision_ids, render_draft(current["fields"], provision_ids),
        )
        if updated is None:
            raise HTTPException(status_code=409, detail="Draft version changed; reload before reanalysis")
        return updated

    @app.post("/drafts/{draft_id}/confirm")
    async def confirm_draft(
        draft_id: str, body: DraftConfirm,
        principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        require_citizen(principal)
        database = db()
        current = owned_draft(database, principal.uid, draft_id)
        if current["status"] == "needs_reanalysis":
            raise HTTPException(status_code=409, detail="Legally relevant edits must be reanalyzed first")
        if current["status"] != "preview":
            raise HTTPException(status_code=409, detail="Draft is not awaiting confirmation")
        pipeline_ids = set(legal_pipeline().valid_ids)
        if not current["provision_ids"] or not set(current["provision_ids"]).issubset(pipeline_ids):
            raise HTTPException(status_code=409, detail="Draft provisions are no longer eligible")
        reference = "LAI-" + datetime.now(UTC).strftime("%Y%m%d") + "-" + secrets.token_hex(4).upper()
        updated = database.transition_draft(
            principal.uid, draft_id, body.expected_version, "preview", "saved", reference
        )
        if updated is None:
            raise HTTPException(status_code=409, detail="Draft version changed; reload before confirming")
        updated["filing_notice"] = (
            "Saved inside this project only. This is not an FIR, police complaint number, or government submission."
        )
        return updated

    @app.post("/drafts/{draft_id}/cancel")
    async def cancel_draft(
        draft_id: str, body: DraftCancel,
        principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        require_citizen(principal)
        database = db()
        current = owned_draft(database, principal.uid, draft_id)
        if current["status"] not in {"preview", "needs_reanalysis"}:
            raise HTTPException(status_code=409, detail="Draft cannot be cancelled in its current state")
        updated = database.transition_draft(
            principal.uid, draft_id, body.expected_version, current["status"], "cancelled"
        )
        if updated is None:
            raise HTTPException(status_code=409, detail="Draft version changed; reload before cancelling")
        return updated

    @app.delete("/drafts/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_saved_draft(
        draft_id: str, principal: Principal = Depends(authenticated_user),
    ) -> None:
        require_citizen(principal)
        owned_draft(db(), principal.uid, draft_id)
        if db().has_case_for_draft(draft_id):
            raise HTTPException(status_code=409, detail="A submitted case record cannot be deleted")
        if not db().delete_saved_draft(principal.uid, draft_id):
            raise HTTPException(status_code=409, detail="Only a saved record can be deleted")

    @app.get("/me")
    async def me(principal: Principal = Depends(authenticated_user)) -> dict[str, Any]:
        return {
            "uid": principal.uid, "is_admin": principal.is_admin,
            "phone_verified": bool(principal.phone_number),
            "demo_mode": principal.auth_mode == "dev",
        }

    @app.post("/cases", status_code=status.HTTP_201_CREATED)
    async def submit_case(
        body: CaseSubmit, principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        require_citizen(principal)
        draft = owned_draft(db(), principal.uid, body.draft_id)
        if draft["status"] != "saved":
            raise HTTPException(status_code=409, detail="Save the reviewed draft before sending it")
        if not draft["fields"].get("reporter_name", "").strip():
            raise HTTPException(status_code=422, detail="Add your name to the draft")
        if body.reporter_role == "on_behalf" and len(body.reporter_relationship.strip()) < 5:
            raise HTTPException(status_code=422, detail="Explain your relationship to the person concerned")
        if body.reporter_role == "on_behalf" and len(body.affected_person_name.strip()) < 2:
            raise HTTPException(status_code=422, detail="Name the person you are reporting for")
        if principal.auth_mode == "firebase" and not principal.phone_number:
            raise HTTPException(status_code=403, detail="Verify your phone number before sending a case")
        created = db().create_case(
            principal.uid, draft, body.reporter_role,
            body.reporter_relationship.strip(), body.affected_person_name.strip(),
            principal.phone_number,
        )
        if created is None:
            raise HTTPException(status_code=409, detail="This draft was already sent for review")
        return {
            **created, "demo_case": principal.auth_mode == "dev",
            "filing_notice": "Sent to VidhiLens for internal review only. No police or government complaint was filed.",
        }

    @app.get("/cases")
    async def list_cases(principal: Principal = Depends(authenticated_user)) -> list[dict[str, Any]]:
        return db().list_cases(principal.uid)

    @app.get("/cases/{case_id}")
    async def get_case(
        case_id: str, principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        case = visible_case(db(), principal, case_id)
        return {**case, **db().case_history(case_id)}

    @app.post("/cases/{case_id}/messages", status_code=status.HTTP_201_CREATED)
    async def send_case_message(
        case_id: str, body: CaseMessageCreate,
        principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        case = visible_case(db(), principal, case_id)
        if case["status"] == "closed" and not principal.is_admin:
            raise HTTPException(status_code=409, detail="Ask for a review before replying to a closed case")
        return db().add_case_message(
            case_id, principal.uid, "reviewer" if principal.is_admin else "citizen", body.text.strip()
        )

    @app.post("/cases/{case_id}/review-request")
    async def request_case_review(
        case_id: str, body: CaseReviewRequest,
        principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        case = visible_case(db(), principal, case_id)
        if case["owner_uid"] != principal.uid or case["status"] != "closed":
            raise HTTPException(status_code=409, detail="Only the case owner may ask to review a closed case")
        result = db().request_case_review(case_id, principal.uid, body.reason.strip())
        if result is None:
            raise HTTPException(status_code=409, detail="This case is already open for review")
        return result

    @app.post("/cases/{case_id}/evidence", status_code=status.HTTP_201_CREATED)
    async def add_case_evidence(
        case_id: str, body: EvidenceCreate,
        principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        case = visible_case(db(), principal, case_id)
        if case["status"] == "closed":
            raise HTTPException(status_code=409, detail="The case is closed")
        try:
            payload = base64.b64decode(body.data_base64, validate=True)
        except (ValueError, binascii.Error) as error:
            raise HTTPException(status_code=422, detail="Invalid evidence data") from error
        if len(payload) > 8_000_000:
            raise HTTPException(status_code=413, detail="Evidence must be under 8 MB")
        signatures = {
            "application/pdf": payload.startswith(b"%PDF-"),
            "image/png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": payload.startswith(b"\xff\xd8\xff"),
        }
        if not signatures[body.content_type]:
            raise HTTPException(status_code=422, detail="The file does not match its stated type")
        return db().add_evidence(
            case_id, principal.uid, body.filename, body.content_type,
            hashlib.sha256(payload).hexdigest(), payload,
        )

    @app.get("/cases/{case_id}/evidence/{evidence_id}")
    async def download_case_evidence(
        case_id: str, evidence_id: str,
        principal: Principal = Depends(authenticated_user),
    ) -> Response:
        visible_case(db(), principal, case_id)
        item = db().get_evidence(case_id, evidence_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Evidence not found")
        return Response(
            content=item["bytes"], media_type=item["content_type"],
            headers={"Content-Disposition": "attachment", "Cache-Control": "no-store"},
        )

    @app.get("/review/cases")
    async def review_queue(principal: Principal = Depends(authenticated_user)) -> list[dict[str, Any]]:
        require_admin(principal)
        return db().list_cases()

    @app.post("/review/cases/{case_id}/decision")
    async def decide_case(
        case_id: str, body: CaseDecision,
        principal: Principal = Depends(authenticated_user),
    ) -> dict[str, Any]:
        require_admin(principal)
        case = visible_case(db(), principal, case_id)
        if body.action == "reopen" and case["status"] != "closed":
            raise HTTPException(status_code=409, detail="Only a closed case can be reopened")
        if body.action != "reopen" and case["status"] == "closed":
            raise HTTPException(status_code=409, detail="Reopen this case before changing its status")
        return db().decide_case(case_id, principal.uid, body.action, body.reason.strip())

    return app


app = create_app()
