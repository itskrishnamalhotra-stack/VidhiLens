from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from .inference import InferenceClient
from .rag_core import (
    DEFAULT_MISSING_QUESTIONS,
    PIPELINE_ID,
    apply_deterministic_gates,
    apply_output_cleaner,
    build_retriever,
    cue_state,
    explicit_transaction_uncertainty,
    has_scoped_legal_subject,
    retrieve_candidates,
    triage_seed_ids,
)


TRIAGE_SYSTEM_PROMPT = (
    "Read the reported incident. Return JSON only with outcome, "
    "possible_provision_ids, and uncertain_sections. "
    "A section is only a possibility, never a finding of guilt. "
    "Never invent missing facts."
)

JOINT_CANDIDATE_SYSTEM_PROMPT = """Assess every supplied candidate provision against the reported incident.
This is cautious possible-section triage, not guilt and not legal advice.
For each candidate return only provision_id and decision.
decision is supported, missing_facts, or rejected.
supported requires all material checklist elements in the reported incident.
missing_facts means a material element could be established by one focused factual question.
rejected is used for contradiction, a shared keyword, or no reasonable factual link.
Do not infer cheating from delay alone, breach of trust from late return alone, physical theft from a bank transfer, or sexually explicit conduct from merely private or obscene material.
Return compact JSON only in this exact form:
{"assessments":[{"provision_id":"...","decision":"supported|missing_facts|rejected"}]}
Return exactly one assessment for every supplied candidate and no extra IDs."""


def parse_json(raw: str) -> Any:
    value = raw.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.I | re.S).strip()
    try:
        return json.loads(value)
    except Exception:
        start, end = value.find("{"), value.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(value[start:end + 1])
            except Exception:
                return None
        return None


class LegalPipeline:
    model_version = "Qwen3-4B-Instruct-2507+complaint-LoRA"

    def __init__(self, catalogue_path: Path, inference: InferenceClient):
        raw = catalogue_path.read_bytes()
        payload = json.loads(raw)
        self.rows: list[dict[str, Any]] = payload["provisions"]
        self.catalogue = {row["provision_id"]: row for row in self.rows}
        self.retriever = build_retriever(self.rows)
        self.valid_ids = set(self.retriever["index"])
        self.kb_version = hashlib.sha256(raw).hexdigest()[:16]
        self.inference = inference

    def candidate_messages(
        self, complaint: str, candidates: list[dict[str, Any]],
        context_candidates: list[dict[str, Any]], triage: dict[str, Any],
    ) -> list[dict[str, str]]:
        payload = {
            "reported_incident": complaint,
            "candidates": [{
                "provision_id": item["provision_id"],
                "title": item["title"],
                "legal_text": re.sub(r"\s+", " ", item["verified_text"]).strip()[:1800],
                "element_checklist": item["element_checklist"],
                "retrieval_signals": {
                    "concept_hit_count": item["concept_hit_count"],
                    "uncertainty_hit_count": item["uncertainty_hit_count"],
                    "triage_seed": item["triage_seed"],
                    "companion_candidate": item["companion_candidate"],
                },
            } for item in candidates],
            "supporting_context": [{
                "provision_id": item["provision_id"],
                "title": item["title"],
                "legal_text": re.sub(r"\s+", " ", item["verified_text"]).strip()[:1500],
            } for item in context_candidates],
            "lora_triage_prior": triage,
        }
        return [
            {"role": "system", "content": JOINT_CANDIDATE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

    @staticmethod
    def assessment_response_format(candidates: list[dict[str, Any]]) -> dict[str, Any]:
        candidate_ids = [item["provision_id"] for item in candidates]
        count = len(candidate_ids)
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "legal_candidate_assessments",
                "strict": True,
                "schema": {
                    "type": "object", "additionalProperties": False,
                    "required": ["assessments"],
                    "properties": {
                        "assessments": {
                            "type": "array", "minItems": count, "maxItems": count,
                            "items": {
                                "type": "object", "additionalProperties": False,
                                "required": ["provision_id", "decision"],
                                "properties": {
                                    "provision_id": {"type": "string", "enum": candidate_ids},
                                    "decision": {"type": "string", "enum": [
                                        "supported", "missing_facts", "rejected"
                                    ]},
                                },
                            },
                        }
                    },
                },
            },
        }

    @staticmethod
    def unpack_assessments(
        candidates: list[dict[str, Any]], complaint: str, raw: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        parsed = parse_json(raw)
        rows = parsed.get("assessments") if isinstance(parsed, dict) else None
        if not isinstance(rows, list):
            return [], ["root must contain assessments list"]
        by_id = {item.get("provision_id"): item for item in rows if isinstance(item, dict)}
        expected = [item["provision_id"] for item in candidates]
        root_errors = [] if set(by_id) == set(expected) else ["assessment IDs differ from candidates"]
        records = []
        for candidate in candidates:
            provision_id = candidate["provision_id"]
            item = by_id.get(provision_id)
            errors: list[str] = []
            if not isinstance(item, dict):
                errors.append("assessment is not an object")
            else:
                if item.get("provision_id") != provision_id:
                    errors.append("wrong provision_id")
                if item.get("decision") not in {"supported", "missing_facts", "rejected"}:
                    errors.append("invalid decision")
            records.append({
                **{key: candidate[key] for key in (
                    "provision_id", "title", "recommendable", "retrieval_score",
                    "concept_hit_count", "uncertainty_hit_count", "triage_seed",
                    "companion_candidate",
                )},
                "parsed_assessment": item,
                "schema_valid": not errors,
                "schema_errors": errors,
            })
        return records, root_errors + [error for row in records for error in row["schema_errors"]]

    def assemble(
        self, complaint: str, retrieval: dict[str, Any],
        assessments: list[dict[str, Any]], triage: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        supported: list[str] = []
        questions: dict[str, str] = {}
        actions: list[dict[str, Any]] = []
        for item in assessments:
            parsed = item.get("parsed_assessment")
            if not item.get("schema_valid") or not isinstance(parsed, dict):
                actions.append({"provision_id": item["provision_id"], "action": "schema_blocked"})
                continue
            provision_id, decision = item["provision_id"], parsed["decision"]
            state = cue_state(complaint, provision_id)
            if decision == "supported":
                if state["positive"] or item.get("triage_seed"):
                    supported.append(provision_id)
                else:
                    actions.append({"provision_id": provision_id, "action": "unsupported_without_signal_removed"})
            elif decision == "missing_facts":
                questions[provision_id] = DEFAULT_MISSING_QUESTIONS[provision_id]
            elif state["uncertain"]:
                questions[provision_id] = DEFAULT_MISSING_QUESTIONS[provision_id]

        supported, questions, gate_actions = apply_deterministic_gates(complaint, supported, questions)
        actions.extend(gate_actions)
        triage_outcome = triage.get("outcome")
        candidate_ids = {item["provision_id"] for item in retrieval["offence_candidates"]}
        if triage_outcome == "provision_match":
            for provision_id in triage_seed_ids(triage):
                if (provision_id in candidate_ids and provision_id in self.valid_ids
                        and cue_state(complaint, provision_id)["positive"]
                        and provision_id not in supported):
                    supported.append(provision_id)
                    actions.append({"provision_id": provision_id, "action": "grounded_triage_fallback"})
            supported, questions, more_actions = apply_deterministic_gates(complaint, supported, questions)
            actions.extend(more_actions)
            supported, questions, cleaner_actions = apply_output_cleaner(
                complaint, supported, questions,
                [item["provision_id"] for item in retrieval["offence_candidates"]],
            )
            actions.extend(cleaner_actions)

        supported = list(dict.fromkeys(supported))
        uncertain = [
            {"provision_id": provision_id, "missing_facts": question}
            for provision_id, question in questions.items() if provision_id not in supported
        ]
        if (triage_outcome == "insufficient_information" and not uncertain
                and not has_scoped_legal_subject(complaint)):
            final = {"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}
        elif triage_outcome == "insufficient_information":
            final = {"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": uncertain}
        elif (triage_outcome != "provision_match" and uncertain
              and explicit_transaction_uncertainty(complaint)):
            final = {"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": uncertain}
        elif triage_outcome != "provision_match":
            final = {"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}
        elif supported:
            final = {"outcome": "provision_match", "possible_provision_ids": supported, "uncertain_sections": uncertain}
        elif uncertain:
            final = {"outcome": "insufficient_information", "possible_provision_ids": [], "uncertain_sections": uncertain}
        else:
            final = {"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}
        return final, actions

    def provision_view(self, provision_id: str) -> dict[str, Any]:
        row = self.catalogue[provision_id]
        return {
            "provision_id": provision_id,
            "title": row["title"],
            "legal_status": row["legal_status"],
            "verified_text": row["verified_text"],
            "source_url": row["source_url"],
            "source_pdf_page": row.get("source_pdf_page"),
        }

    async def analyze(self, complaint: str) -> dict[str, Any]:
        started = time.perf_counter()
        triage_generation = await self.inference.chat([
            {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
            {"role": "user", "content": complaint},
        ], max_tokens=140, use_lora=True)
        triage = parse_json(triage_generation.text)
        if not isinstance(triage, dict):
            triage = {}
        retrieval_started = time.perf_counter()
        retrieval = retrieve_candidates(complaint, triage, self.retriever)
        retrieval_seconds = time.perf_counter() - retrieval_started
        assessments: list[dict[str, Any]] = []
        assessment_seconds = 0.0
        assessment_tokens = 0
        assessment_errors: list[str] = []
        if retrieval["offence_candidates"]:
            generation = await self.inference.chat(
                self.candidate_messages(
                    complaint, retrieval["offence_candidates"],
                    retrieval["context_candidates"], triage,
                ),
                max_tokens=220,
                use_lora=False,
                response_format=self.assessment_response_format(retrieval["offence_candidates"]),
            )
            assessment_seconds = generation.seconds
            assessment_tokens = generation.completion_tokens
            assessments, assessment_errors = self.unpack_assessments(
                retrieval["offence_candidates"], complaint, generation.text
            )
        final, actions = self.assemble(complaint, retrieval, assessments, triage)
        invalid = [item for item in final["possible_provision_ids"] if item not in self.valid_ids]
        if invalid:
            raise RuntimeError(f"Pipeline produced invalid provision IDs: {invalid}")
        provisions = [self.provision_view(item) for item in final["possible_provision_ids"]]
        uncertain = []
        for item in final["uncertain_sections"]:
            provision = self.provision_view(item["provision_id"])
            uncertain.append({**item, "title": provision["title"], "options": ["Yes", "No", "Not sure", "Other"]})
        return {
            "outcome": final["outcome"],
            "possible_provision_ids": final["possible_provision_ids"],
            "provisions": provisions,
            "uncertain_sections": uncertain,
            "can_prepare_draft": final["outcome"] == "provision_match",
            "pipeline_id": PIPELINE_ID,
            "model_version": self.model_version,
            "kb_version": self.kb_version,
            "audit": {
                "retrieved_provision_ids": [item["provision_id"] for item in retrieval["offence_candidates"]],
                "evidence_gate_actions": actions,
                "assessment_schema_errors": assessment_errors,
            },
            "timing": {
                "triage_seconds": triage_generation.seconds,
                "retrieval_seconds": retrieval_seconds,
                "assessment_seconds": assessment_seconds,
                "total_seconds": time.perf_counter() - started,
                "output_tokens": triage_generation.completion_tokens + assessment_tokens,
            },
            "notice": "Possible provisions for research triage only; this is not a finding of guilt or legal advice.",
        }

