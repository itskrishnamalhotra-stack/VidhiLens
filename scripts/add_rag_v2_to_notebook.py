"""Build Krishna's triage-first, candidate-by-candidate RAG v2 Colab notebook."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


RAG_TAG_PREFIX = "legalai-rag-"


def markdown(source: str, tag: str) -> dict:
    return {"cell_type": "markdown", "metadata": {"tags": [tag]},
            "source": source.splitlines(keepends=True)}


def code(source: str, tag: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {"tags": [tag]},
            "outputs": [], "source": source.splitlines(keepends=True)}


RAG_V2_CODE = r'''# ============================================================
# RAG V2: TRIAGE FIRST + CANDIDATE-BY-CANDIDATE ASSESSMENT
# ============================================================

import hashlib
import json
import math
import os
import re
import torch
from collections import Counter
from pathlib import Path
from IPython.display import display, Markdown, JSON as DisplayJSON

RAG_V2_VERSION = "triage_first_candidate_assessment_v2"
RAG_V2_RESULT_PATH = PROJECT / "rag_v2_comparison_results.json"
RAG_V1_RESULT_PATH = PROJECT / "rag_comparison_results_v1.json"
RAG_CATALOGUE_FILE = PROJECT / "rag_catalogue_v1.json"
RAG_CATALOGUE_SHA256 = "7e29261f71d494d2846d6ac6a170548191853fe7b1d90940cde3e240053c3cfe"
RAG_V2_WORK = Path("/content/legal_ai_rag_v2")
RAG_V2_WORK.mkdir(parents=True, exist_ok=True)
RESTART_RAG_V2 = False
RAG_V2_MAX_OFFENCE_CANDIDATES = 6
RAG_V2_MAX_CONTEXT_CANDIDATES = 3
RAG_V2_MIN_BM25_SCORE = 18.0

TRIAGE_SYSTEM_PROMPT = (
    "Read the reported incident. Return JSON only with outcome, "
    "possible_provision_ids, and uncertain_sections. "
    "A section is only a possibility, never a finding of guilt. "
    "Never invent missing facts."
)

CANDIDATE_SYSTEM_PROMPT = """Compare one candidate statutory provision with one reported incident.
Use only the supplied incident and statutory text. Return one JSON object only with:
provision_id, decision, missing_facts, and reason.
decision must be supported, missing_facts, or rejected.
Use supported only when every material factual element stated in the candidate text is supported by the incident.
Use missing_facts when the provision is plausibly connected but at least one material factual element is absent.
Use rejected when the facts contradict the provision or the connection is merely a shared keyword.
missing_facts must be a JSON list of short factual questions and must be empty for supported or rejected.
reason must be one short sentence grounded in the supplied text.
Do not infer gender, consent, dishonest intention, use of credentials, injury severity, repetition, payment, publication, or another missing fact.
This is research classification of possible provisions, never a finding of guilt or legal advice."""

QUERY_EXPANSIONS = (
    (("bus", "train", "metro", "taxi"), "means of transport passengers article goods theft"),
    (("stole", "stolen", "steal", "removed", "took", "missing phone"),
     "theft movable property possession consent dishonestly"),
    (("snatched", "grabbed", "seized"), "snatching suddenly quickly forcibly grabs takes away"),
    (("hacked", "unauthorised", "unauthorized", "accessed", "login history"),
     "computer access without permission data download computer related offence"),
    (("password", "otp", "login"), "password unique identification identity theft computer resource"),
    (("pretending", "impersonating", "fake profile", "fake account"),
     "cheating personation communication device computer resource"),
    (("private photograph", "private image", "intimate", "changing clothes"),
     "privacy private area image capture publish transmit voyeurism"),
    (("sexual", "sexually"), "sexual harassment explicit sexual act obscene material"),
    (("followed", "following", "monitoring"),
     "stalking follows contacts repeatedly monitors electronic communication"),
    (("fracture", "fractured", "broken bone", "injured"),
     "hurt grievous hurt fracture dangerous weapon"),
    (("threat", "threatening", "blackmail"),
     "criminal intimidation fear injury extortion demand property"),
    (("repair", "entrusted", "returning"),
     "entrusted property criminal breach of trust misappropriates"),
    (("forged", "fabricated", "false document"), "forgery forged document cheating"),
    (("seller", "product", "advertisement", "delivery", "blocked me"),
     "cheating deceiving dishonestly induces delivery property payment"),
)

RETRIEVAL_ANCHORS = (
    (("bus", "train", "metro", "backpack", "stole", "stolen", "snatched", "missing phone"),
     ("BNS_303", "BNS_304", "BNS_305")),
    (("hacked", "unauthorised", "unauthorized", "accessed", "login history"),
     ("ITA_43", "ITA_66", "ITA_66C")),
    (("otp", "password"), ("ITA_66", "ITA_66C", "ITA_66D")),
    (("pretending", "impersonating", "fake profile", "fake account"),
     ("BNS_319", "ITA_66C", "ITA_66D")),
    (("private photograph", "private image", "intimate", "changing clothes"),
     ("BNS_77", "ITA_66E", "ITA_67", "ITA_67A")),
    (("sexual favour", "sexual remark", "sexual harassment"), ("BNS_75",)),
    (("followed", "following", "monitoring"), ("BNS_78",)),
    (("injured", "fracture", "fractured", "iron rod", "weapon"),
     ("BNS_115", "BNS_117", "BNS_118")),
    (("threat", "threatening", "blackmail"), ("BNS_308", "BNS_351")),
    (("repair", "entrusted"), ("BNS_316", "BNS_314")),
    (("forged", "fabricated", "false document"), ("BNS_318", "BNS_336", "BNS_340")),
    (("seller", "product", "advertisement", "delivery", "blocked me"), ("BNS_318",)),
)


def rag_v2_tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def remove_explicit_no_clauses(text):
    # Prevent phrases such as "there were no threats or forged documents" from
    # becoming positive retrieval anchors. Other negative facts remain available
    # to the candidate assessor in the original complaint.
    return re.sub(r"\bno\b[^.;!?]*(?=[.;!?]|$)", " ", text.lower())


def expand_rag_v2_query(text):
    positive_text = remove_explicit_no_clauses(text)
    additions = [addition for triggers, addition in QUERY_EXPANSIONS
                 if any(trigger in positive_text for trigger in triggers)]
    return positive_text + " " + " ".join(additions)


if not RAG_CATALOGUE_FILE.is_file():
    raise FileNotFoundError(
        "Upload rag_catalogue_v1.json beside this notebook in MyDrive/LegalAI, then run again"
    )
catalogue_bytes = RAG_CATALOGUE_FILE.read_bytes()
if hashlib.sha256(catalogue_bytes).hexdigest() != RAG_CATALOGUE_SHA256:
    raise ValueError("rag_catalogue_v1.json failed its SHA-256 integrity check")
catalogue_payload = json.loads(catalogue_bytes)
if catalogue_payload.get("counts") != {
        "total": 467, "in_force": 466, "uncertain": 1, "recommendable": 19}:
    raise ValueError("Unexpected RAG catalogue scope")

RAG_V2_ROWS = catalogue_payload["provisions"]
RAG_V2_CATALOGUE = {row["provision_id"]: row for row in RAG_V2_ROWS}
RAG_V2_INDEX = {row["provision_id"]: index for index, row in enumerate(RAG_V2_ROWS)}
RAG_V2_DOCUMENT_TOKENS = []
RAG_V2_TITLE_TOKENS = []
for row in RAG_V2_ROWS:
    title = row.get("title", "")
    RAG_V2_TITLE_TOKENS.append(set(rag_v2_tokens(title)))
    RAG_V2_DOCUMENT_TOKENS.append(rag_v2_tokens((title + " ") * 3 + row.get("verified_text", "")))

RAG_V2_DF = Counter()
for tokens in RAG_V2_DOCUMENT_TOKENS:
    RAG_V2_DF.update(set(tokens))
RAG_V2_DOCUMENT_COUNT = len(RAG_V2_DOCUMENT_TOKENS)
RAG_V2_AVERAGE_LENGTH = sum(map(len, RAG_V2_DOCUMENT_TOKENS)) / RAG_V2_DOCUMENT_COUNT


def rag_v2_idf(term):
    frequency = RAG_V2_DF.get(term, 0)
    return math.log(1 + (RAG_V2_DOCUMENT_COUNT - frequency + 0.5) / (frequency + 0.5))


def rag_v2_bm25_scores(complaint):
    query_counts = Counter(rag_v2_tokens(expand_rag_v2_query(complaint)))
    scores = {}
    k1 = 1.5
    b = 0.75
    for index, document_tokens in enumerate(RAG_V2_DOCUMENT_TOKENS):
        frequencies = Counter(document_tokens)
        length = len(document_tokens)
        score = 0.0
        for term, query_frequency in query_counts.items():
            term_frequency = frequencies.get(term, 0)
            if not term_frequency:
                continue
            denominator = term_frequency + k1 * (1 - b + b * length / RAG_V2_AVERAGE_LENGTH)
            score += rag_v2_idf(term) * (term_frequency * (k1 + 1) / denominator) * min(query_frequency, 2)
            if term in RAG_V2_TITLE_TOKENS[index]:
                score += 1.25 * rag_v2_idf(term)
        scores[index] = score
    return scores


def triage_seed_ids(triage):
    result = []
    if not isinstance(triage, dict):
        return result
    possible = triage.get("possible_provision_ids", [])
    if isinstance(possible, list):
        result.extend(pid for pid in possible if isinstance(pid, str))
    uncertain = triage.get("uncertain_sections", [])
    if isinstance(uncertain, list):
        for item in uncertain:
            if isinstance(item, dict) and isinstance(item.get("provision_id"), str):
                result.append(item["provision_id"])
    return list(dict.fromkeys(result))


def retrieve_rag_v2(complaint, triage):
    positive_text = remove_explicit_no_clauses(complaint)
    scores = rag_v2_bm25_scores(complaint)
    anchor_ids = []
    for triggers, provision_ids in RETRIEVAL_ANCHORS:
        if any(trigger in positive_text for trigger in triggers):
            anchor_ids.extend(provision_ids)
    seed_ids = triage_seed_ids(triage)
    priority_ids = list(dict.fromkeys(anchor_ids + seed_ids))
    ranked_ids = [RAG_V2_ROWS[index]["provision_id"]
                  for index, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
                  if score >= RAG_V2_MIN_BM25_SCORE]
    ordered_ids = list(dict.fromkeys(priority_ids + ranked_ids))
    offence_candidates = []
    context_candidates = []
    for provision_id in ordered_ids:
        row = RAG_V2_CATALOGUE.get(provision_id)
        if not row:
            continue
        item = {
            "provision_id": provision_id,
            "title": row.get("title"),
            "verified_text": row.get("verified_text", ""),
            "legal_status": row.get("legal_status"),
            "provision_kind": row.get("provision_kind"),
            "recommendable": bool(row.get("recommendable")),
            "anchor_matched": provision_id in anchor_ids,
            "triage_seed": provision_id in seed_ids,
            "retrieval_score": round(scores.get(RAG_V2_INDEX[provision_id], 0.0), 6)
        }
        if row.get("legal_status") == "in_force" and row.get("provision_kind") == "offence":
            if len(offence_candidates) < RAG_V2_MAX_OFFENCE_CANDIDATES:
                offence_candidates.append(item)
        elif len(context_candidates) < RAG_V2_MAX_CONTEXT_CANDIDATES:
            context_candidates.append(item)
        if (len(offence_candidates) >= RAG_V2_MAX_OFFENCE_CANDIDATES and
                len(context_candidates) >= RAG_V2_MAX_CONTEXT_CANDIDATES):
            break
    return {
        "offence_candidates": offence_candidates,
        "context_candidates": context_candidates,
        "minimum_bm25_score": RAG_V2_MIN_BM25_SCORE
    }


def ensure_rag_v2_model_loaded():
    global rag_v2_model, rag_v2_tokenizer
    if "rag_v2_model" in globals():
        return
    if "batch_test_model" in globals() and "batch_test_tokenizer" in globals():
        rag_v2_model = batch_test_model
        rag_v2_tokenizer = batch_test_tokenizer
        print("Reusing the LoRA loaded by the 21-complaint test.")
        return
    print("Loading the selected LoRA for RAG v2...")
    torch.cuda.empty_cache()
    training_results = json.loads((PROJECT / "training_results.json").read_text(encoding="utf-8"))
    selected_run = PROJECT / "runs" / training_results["chosen"]
    rag_v2_model, rag_v2_tokenizer = train_runner.load_adapter(selected_run, RAG_V2_WORK)
    print("RAG v2 model loaded.")


def generate_messages(messages, max_new_tokens, use_adapter):
    input_ids = rag_v2_tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt"
    ).to(rag_v2_model.device)
    attention_mask = torch.ones_like(input_ids, dtype=torch.long)
    if use_adapter:
        context = torch.inference_mode()
    else:
        # Official PEFT API: this context temporarily runs the same model without LoRA.
        context = rag_v2_model.disable_adapter()
    with context:
        with torch.inference_mode():
            generated = rag_v2_model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=rag_v2_tokenizer.eos_token_id,
                eos_token_id=rag_v2_tokenizer.eos_token_id
            )
    return rag_v2_tokenizer.decode(
        generated[0, input_ids.shape[-1]:], skip_special_tokens=True
    ).strip()


def validate_candidate_assessment(parsed, expected_id):
    errors = []
    if not isinstance(parsed, dict):
        return ["output is not a JSON object"]
    if parsed.get("provision_id") != expected_id:
        errors.append("provision_id does not match candidate")
    if parsed.get("decision") not in {"supported", "missing_facts", "rejected"}:
        errors.append("invalid decision")
    missing = parsed.get("missing_facts")
    if not isinstance(missing, list) or not all(isinstance(item, str) for item in missing):
        errors.append("missing_facts is not a list of strings")
    elif parsed.get("decision") == "missing_facts" and not missing:
        errors.append("missing_facts decision has no questions")
    elif parsed.get("decision") in {"supported", "rejected"} and missing:
        errors.append("supported/rejected decision must have empty missing_facts")
    if not isinstance(parsed.get("reason"), str) or not parsed.get("reason", "").strip():
        errors.append("reason is missing")
    return errors


def assess_one_candidate(complaint, candidate, context_candidates):
    support = [{
        "provision_id": row["provision_id"],
        "title": row["title"],
        "legal_status": row["legal_status"],
        "provision_kind": row["provision_kind"],
        "legal_text": re.sub(r"\s+", " ", row["verified_text"]).strip()[:3500]
    } for row in context_candidates]
    candidate_payload = {
        "provision_id": candidate["provision_id"],
        "title": candidate["title"],
        "legal_text": re.sub(r"\s+", " ", candidate["verified_text"]).strip()[:6500]
    }
    user_payload = {
        "reported_incident": complaint,
        "candidate_provision": candidate_payload,
        "context_only_provisions": support
    }
    messages = [
        {"role": "system", "content": CANDIDATE_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
    ]
    raw = generate_messages(messages, 260, use_adapter=False)
    parsed = train_runner.parse_json(raw)
    errors = validate_candidate_assessment(parsed, candidate["provision_id"])
    if errors:
        repair_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content":
             "The previous response failed these schema checks: " + "; ".join(errors) +
             ". Return a corrected JSON object only."}
        ]
        repaired_raw = generate_messages(repair_messages, 260, use_adapter=False)
        repaired = train_runner.parse_json(repaired_raw)
        repaired_errors = validate_candidate_assessment(repaired, candidate["provision_id"])
        if not repaired_errors:
            raw, parsed, errors = repaired_raw, repaired, []
        else:
            errors = repaired_errors
    return {
        "provision_id": candidate["provision_id"],
        "title": candidate["title"],
        "recommendable": candidate["recommendable"],
        "retrieval_score": candidate["retrieval_score"],
        "raw_model_output": raw,
        "parsed_assessment": parsed,
        "schema_valid": not errors,
        "schema_errors": errors
    }


def assemble_rag_v2(triage, retrieval, assessments):
    triage_outcome = triage.get("outcome") if isinstance(triage, dict) else None
    if triage_outcome == "out_of_scope":
        return {
            "outcome": "out_of_scope",
            "possible_provision_ids": [],
            "uncertain_sections": [],
        }, [], "triage_out_of_scope_guard"

    supported = []
    missing = []
    rejected = []
    assessment_errors = []
    for item in assessments:
        parsed = item.get("parsed_assessment")
        if not item.get("schema_valid") or not isinstance(parsed, dict):
            assessment_errors.append(item["provision_id"])
            continue
        decision = parsed["decision"]
        if decision == "supported":
            supported.append(item)
        elif decision == "missing_facts":
            missing.append(item)
        else:
            rejected.append(item)

    visible_supported = [item for item in supported if item["recommendable"]]
    blocked_supported = [{
        "provision_id": item["provision_id"],
        "title": item["title"],
        "block_reason": "not recommendation-approved"
    } for item in supported if not item["recommendable"]]

    uncertain = []
    uncertain_seen = set()
    for item in missing:
        if not item["recommendable"] or item["provision_id"] in uncertain_seen:
            continue
        parsed = item["parsed_assessment"]
        uncertain.append({
            "provision_id": item["provision_id"],
            "missing_facts": "; ".join(parsed.get("missing_facts", []))
        })
        uncertain_seen.add(item["provision_id"])

    if triage_outcome == "insufficient_information":
        # Candidate assessment may improve the questions, but never upgrades an
        # incomplete complaint into a match in this conservative prototype.
        if not uncertain:
            for item in visible_supported:
                if item["provision_id"] not in uncertain_seen:
                    uncertain.append({
                        "provision_id": item["provision_id"],
                        "missing_facts": "Confirm the complete incident facts before suggesting this provision"
                    })
        final = {"outcome": "insufficient_information", "possible_provision_ids": [],
                 "uncertain_sections": uncertain}
        return final, blocked_supported, "triage_insufficient_guard"

    if visible_supported:
        final = {
            "outcome": "provision_match",
            "possible_provision_ids": [item["provision_id"] for item in visible_supported],
            "uncertain_sections": uncertain
        }
        return final, blocked_supported, "supported_recommendable_candidates"

    if uncertain:
        final = {"outcome": "insufficient_information", "possible_provision_ids": [],
                 "uncertain_sections": uncertain}
        return final, blocked_supported, "only_missing_fact_candidates"

    fallback_uncertain = []
    for provision_id in triage_seed_ids(triage):
        row = RAG_V2_CATALOGUE.get(provision_id)
        if row and row.get("recommendable"):
            fallback_uncertain.append({
                "provision_id": provision_id,
                "missing_facts": "The grounded candidate assessment did not confirm the original suggestion"
            })
    final = {
        "outcome": "insufficient_information" if fallback_uncertain or assessment_errors else "out_of_scope",
        "possible_provision_ids": [],
        "uncertain_sections": fallback_uncertain
    }
    return final, blocked_supported, "no_supported_candidate"


def validate_final_rag_v2(final):
    errors = []
    if not isinstance(final, dict):
        return {"valid": False, "errors": ["final output is not an object"]}
    if final.get("outcome") not in {"provision_match", "insufficient_information", "out_of_scope"}:
        errors.append("invalid outcome")
    ids = final.get("possible_provision_ids")
    if not isinstance(ids, list):
        errors.append("possible_provision_ids is not a list")
        ids = []
    if not isinstance(final.get("uncertain_sections"), list):
        errors.append("uncertain_sections is not a list")
    for provision_id in ids:
        row = RAG_V2_CATALOGUE.get(provision_id)
        if not row:
            errors.append(f"unknown provision: {provision_id}")
        elif not row.get("recommendable"):
            errors.append(f"not recommendation-approved: {provision_id}")
        elif row.get("legal_status") != "in_force" or row.get("provision_kind") != "offence":
            errors.append(f"not an in-force offence: {provision_id}")
    return {"valid": not errors, "errors": errors}


def write_rag_v2_state(comparisons, in_progress, baseline_payload, adapter_hash):
    ordered_by_id = {item["case_id"]: item for item in comparisons}
    ordered = [ordered_by_id[case["case_id"]] for case in TEST_CASES
               if case["case_id"] in ordered_by_id]
    payload = {
        "schema_version": 2,
        "rag_version": RAG_V2_VERSION,
        "chosen_variant": baseline_payload["chosen_variant"],
        "base_model": baseline_payload["base_model"],
        "adapter_sha256": adapter_hash,
        "total_test_cases": len(TEST_CASES),
        "completed_test_cases": len(ordered),
        "in_progress": in_progress,
        "comparisons": ordered
    }
    temporary = RAG_V2_RESULT_PATH.with_suffix(".json.part")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, RAG_V2_RESULT_PATH)
    return ordered


BASELINE_PATH = PROJECT / "manual_batch_test_results_v1.json"
if not BASELINE_PATH.exists():
    raise FileNotFoundError("Run the original 21-complaint test cell first")
baseline_payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
if baseline_payload.get("completed_test_cases") != len(TEST_CASES):
    raise ValueError("The original LoRA-only test is incomplete")
adapter_hash = baseline_payload["adapter_sha256"]
baseline_by_id = {row["case_id"]: row for row in baseline_payload["cases"]}

v1_by_id = {}
if RAG_V1_RESULT_PATH.exists():
    v1_payload = json.loads(RAG_V1_RESULT_PATH.read_text(encoding="utf-8"))
    if v1_payload.get("adapter_sha256") == adapter_hash:
        v1_by_id = {row["case_id"]: row for row in v1_payload.get("comparisons", [])}

comparisons = []
in_progress = None
if RAG_V2_RESULT_PATH.exists() and not RESTART_RAG_V2:
    previous = json.loads(RAG_V2_RESULT_PATH.read_text(encoding="utf-8"))
    if previous.get("rag_version") != RAG_V2_VERSION or previous.get("adapter_sha256") != adapter_hash:
        raise RuntimeError("Existing RAG v2 file uses a different method or adapter. Set RESTART_RAG_V2=True.")
    comparisons = previous.get("comparisons", [])
    in_progress = previous.get("in_progress")
    print(f"Resuming RAG v2: {len(comparisons)}/{len(TEST_CASES)} complete")
elif RESTART_RAG_V2 and RAG_V2_RESULT_PATH.exists():
    RAG_V2_RESULT_PATH.unlink()

completed_ids = {row["case_id"] for row in comparisons}
pending_cases = [case for case in TEST_CASES if case["case_id"] not in completed_ids]
if pending_cases:
    ensure_rag_v2_model_loaded()

for case in pending_cases:
    baseline = baseline_by_id[case["case_id"]]
    triage = baseline.get("parsed_output")
    print(f"RAG v2 {case['case_id']} ({len(comparisons) + 1}/{len(TEST_CASES)})")

    if triage.get("outcome") == "out_of_scope":
        retrieval = {"offence_candidates": [], "context_candidates": [],
                     "minimum_bm25_score": RAG_V2_MIN_BM25_SCORE}
        assessments = []
        in_progress = None
    else:
        retrieval = retrieve_rag_v2(case["complaint"], triage)
        candidate_ids = [row["provision_id"] for row in retrieval["offence_candidates"]]
        if in_progress and in_progress.get("case_id") == case["case_id"]:
            assessments = in_progress.get("assessments", [])
        else:
            assessments = []
        assessed_ids = {row["provision_id"] for row in assessments}
        for candidate in retrieval["offence_candidates"]:
            if candidate["provision_id"] in assessed_ids:
                continue
            print("  assessing", candidate["provision_id"], candidate["title"])
            assessments.append(assess_one_candidate(
                case["complaint"], candidate, retrieval["context_candidates"]
            ))
            in_progress = {
                "case_id": case["case_id"],
                "candidate_ids": candidate_ids,
                "assessments": assessments
            }
            comparisons = write_rag_v2_state(
                comparisons, in_progress, baseline_payload, adapter_hash
            )

    final, blocked, assembly_rule = assemble_rag_v2(triage, retrieval, assessments)
    final_validation = validate_final_rag_v2(final)
    if not final_validation["valid"]:
        raise ValueError(f"Final RAG v2 gate failed for {case['case_id']}: {final_validation['errors']}")
    comparison = {
        "case_id": case["case_id"],
        "category": case["category"],
        "review_goal": case["review_goal"],
        "complaint": case["complaint"],
        "lora_only": baseline.get("parsed_output"),
        "rag_v1": (v1_by_id.get(case["case_id"], {}).get("lora_plus_rag", {})
                   .get("parsed_output")),
        "rag_v2": {
            "triage_guard": triage.get("outcome"),
            "retrieval": retrieval,
            "candidate_assessments": assessments,
            "blocked_supported_candidates": blocked,
            "assembly_rule": assembly_rule,
            "final_output": final,
            "final_validation": final_validation
        },
        "v2_differs_from_lora_only": final != triage,
        "v2_differs_from_v1": final != (v1_by_id.get(case["case_id"], {})
                                         .get("lora_plus_rag", {}).get("parsed_output"))
    }
    comparisons.append(comparison)
    in_progress = None
    comparisons = write_rag_v2_state(comparisons, in_progress, baseline_payload, adapter_hash)
    print("  LoRA only:", json.dumps(triage, ensure_ascii=False))
    print("  RAG v2:", json.dumps(final, ensure_ascii=False))
    print("  saved to Drive\n")

comparisons = write_rag_v2_state(comparisons, None, baseline_payload, adapter_hash)
valid_final = sum(row["rag_v2"]["final_validation"]["valid"] for row in comparisons)
outcome_counts = Counter(row["rag_v2"]["final_output"]["outcome"] for row in comparisons)
blocked_cases = sum(bool(row["rag_v2"]["blocked_supported_candidates"]) for row in comparisons)
schema_error_cases = sum(any(not assessment["schema_valid"]
                             for assessment in row["rag_v2"]["candidate_assessments"])
                         for row in comparisons)

display(Markdown("## RAG v2 batch summary"))
display(DisplayJSON({
    "completed_cases": len(comparisons),
    "valid_final_outputs": valid_final,
    "final_outcome_counts": dict(outcome_counts),
    "cases_with_blocked_research_candidates": blocked_cases,
    "cases_with_candidate_schema_errors": schema_error_cases,
    "output_file": str(RAG_V2_RESULT_PATH)
}, expanded=True))
print("Attach rag_v2_comparison_results.json from MyDrive/LegalAI for independent review.")
'''


INTERACTIVE_V2_CODE = r'''# ============================================================
# INTERACTIVE LoRA-ONLY VERSUS RAG V2 TESTER
# ============================================================

import json
from datetime import datetime, timezone
import ipywidgets as widgets
from IPython.display import display, Markdown, JSON as DisplayJSON, clear_output

RAG_V2_INTERACTIVE_LOG = PROJECT / "interactive_rag_v2_tests.jsonl"


def run_live_lora_triage(complaint):
    messages = [
        {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
        {"role": "user", "content": complaint}
    ]
    raw = generate_messages(messages, 180, use_adapter=True)
    return raw, train_runner.parse_json(raw)


def run_live_rag_v2(complaint, triage, progress=None):
    if triage.get("outcome") == "out_of_scope":
        retrieval = {"offence_candidates": [], "context_candidates": [],
                     "minimum_bm25_score": RAG_V2_MIN_BM25_SCORE}
        assessments = []
    else:
        retrieval = retrieve_rag_v2(complaint, triage)
        assessments = []
        for index, candidate in enumerate(retrieval["offence_candidates"], start=1):
            if progress:
                progress(index, len(retrieval["offence_candidates"]), candidate)
            assessments.append(assess_one_candidate(
                complaint, candidate, retrieval["context_candidates"]
            ))
    final, blocked, rule = assemble_rag_v2(triage, retrieval, assessments)
    validation = validate_final_rag_v2(final)
    return {
        "retrieval": retrieval,
        "candidate_assessments": assessments,
        "blocked_supported_candidates": blocked,
        "assembly_rule": rule,
        "final_output": final,
        "final_validation": validation
    }


ensure_rag_v2_model_loaded()

v2_complaint_input = widgets.Textarea(
    value="",
    placeholder="Describe an incident in ordinary language...",
    description="Complaint:",
    layout=widgets.Layout(width="100%", height="180px"),
    style={"description_width": "90px"}
)
v2_compare_button = widgets.Button(
    description="Run LoRA and RAG v2",
    button_style="primary",
    icon="search"
)
v2_output = widgets.Output()


def run_interactive_v2(_):
    complaint = v2_complaint_input.value.strip()
    with v2_output:
        clear_output(wait=True)
        if not complaint:
            print("Enter a complaint first.")
            return
        v2_compare_button.disabled = True
        try:
            print("Running LoRA triage...")
            triage_raw, triage = run_live_lora_triage(complaint)
            if not isinstance(triage, dict):
                raise ValueError("LoRA triage did not produce a JSON object: " + triage_raw)

            def show_progress(index, total, candidate):
                print(f"Assessing candidate {index}/{total}: {candidate['provision_id']}")

            v2_result = run_live_rag_v2(complaint, triage, show_progress)
            record = {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "rag_version": RAG_V2_VERSION,
                "complaint": complaint,
                "lora_only": {"raw": triage_raw, "parsed": triage},
                "rag_v2": v2_result
            }
            with RAG_V2_INTERACTIVE_LOG.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")

            display(Markdown("## LoRA-only triage"))
            display(DisplayJSON(record["lora_only"], expanded=True))
            display(Markdown("## Retrieved offence candidates"))
            display(DisplayJSON(v2_result["retrieval"]["offence_candidates"], expanded=True))
            display(Markdown("## Context-only provisions"))
            display(DisplayJSON(v2_result["retrieval"]["context_candidates"], expanded=True))
            display(Markdown("## Candidate assessments"))
            display(DisplayJSON(v2_result["candidate_assessments"], expanded=True))
            display(Markdown("## Final gated RAG v2 output"))
            display(DisplayJSON({
                "final_output": v2_result["final_output"],
                "blocked_supported_candidates": v2_result["blocked_supported_candidates"],
                "assembly_rule": v2_result["assembly_rule"],
                "validation": v2_result["final_validation"]
            }, expanded=True))
            print("Saved to:", RAG_V2_INTERACTIVE_LOG)
        except Exception as error:
            print(type(error).__name__ + ":", error)
        finally:
            v2_compare_button.disabled = False


v2_compare_button.on_click(run_interactive_v2)
display(Markdown("# Test your own complaint with RAG v2"))
display(Markdown(
    "The first response uses the trained LoRA. RAG v2 then assesses each retrieved "
    "provision separately and constructs a gated final response. A test may take several minutes."
))
display(v2_complaint_input, v2_compare_button, v2_output)
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    notebook = json.loads(args.source.read_text(encoding="utf-8"))
    if notebook.get("nbformat") != 4:
        raise ValueError("Expected a v4 Jupyter notebook")
    preserved = []
    for cell in notebook.get("cells", []):
        tags = cell.get("metadata", {}).get("tags", [])
        if any(tag.startswith(RAG_TAG_PREFIX) for tag in tags):
            continue
        if cell.get("cell_type") == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        preserved.append(cell)
    if len(preserved) < 7 or "AUTOMATIC 21-COMPLAINT BATCH TEST" not in "".join(preserved[6].get("source", [])):
        raise ValueError("Source notebook does not include Krishna's 21-complaint cell")
    preserved.extend([
        markdown("""# RAG v2 comparison

Upload `rag_catalogue_v1.json` beside this notebook in `MyDrive/LegalAI`. RAG v2 preserves the trained LoRA for broad triage, skips retrieval for out-of-scope complaints, retrieves with negation-aware lexical/BM25 ranking, evaluates each candidate separately using the base instruction model, and constructs the final answer in code after applying status and recommendation gates.

The cell saves after every candidate assessment and resumes after a disconnect. It reuses the LoRA-only and RAG v1 result files when available; no model training is repeated.
""", "legalai-rag-v2-comparison"),
        code(RAG_V2_CODE, "legalai-rag-v2-comparison"),
        markdown("""# Interactive RAG v2 testing

The final cell lets you enter a new complaint. It shows the original LoRA triage, retrieved candidates, individual element assessments, blocked research candidates and final gated result.
""", "legalai-rag-v2-interactive"),
        code(INTERACTIVE_V2_CODE, "legalai-rag-v2-interactive")
    ])
    notebook["cells"] = preserved
    notebook.get("metadata", {}).pop("widgets", None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
