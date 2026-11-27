"""Append the improved multilingual grounded RAG workflow to the tested Colab notebook."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "scripts" / "rag_improved_core.py"
TAG_PREFIX = "legalai-improved-rag-"


def markdown(source: str, tag: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {"tags": [tag]},
        "source": source.splitlines(keepends=True),
    }


def code(source: str, tag: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"tags": [tag]},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


SETUP_CODE = r'''# ============================================================
# IMPROVED MULTILINGUAL RETRIEVAL + EVIDENCE-QUOTED ASSESSMENT
# ============================================================

import json
import re
import torch
from IPython.display import display, Markdown, JSON as DisplayJSON

IMPROVED_PREDICTIONS = PROJECT / "rag_improved_regression_predictions.json"
IMPROVED_REPORT = PROJECT / "rag_improved_regression_report.json"
IMPROVED_INTERACTIVE_LOG = PROJECT / "interactive_rag_improved_tests.jsonl"
RESTART_IMPROVED_REGRESSION = False
IMPROVED_CANDIDATE_BATCH_SIZE = 2

IMPROVED_RETRIEVER = build_retriever(RAG_V2_ROWS)

IMPROVED_CANDIDATE_SYSTEM_PROMPT = """You assess one possible Indian legal provision against one reported incident.
This is cautious possible-section triage, not a finding of guilt and not legal advice.
Use only the reported incident, the supplied statutory text and element checklist.
Return exactly one JSON object with these fields:
provision_id, decision, evidence_spans, missing_facts, reason.
decision must be supported, missing_facts, or rejected.
For supported: every material statutory element must be stated or directly supported by the incident.
evidence_spans must contain one to three short exact quotations copied from the reported incident.
For missing_facts: name only genuinely absent material facts as one or two short questions.
For rejected: use it when a required element is contradicted, absent beyond a useful follow-up, or the match is merely a shared word.
Do not treat delayed delivery as cheating without facts showing deception when payment was induced.
Do not treat late return of entrusted property as breach of trust without facts showing dishonest use, sale, conversion or refusal.
Do not treat account transfers, passwords or credentials as physical theft of movable property.
Do not treat obscene electronic material as sexually explicit conduct unless the incident says it contains a sexual act or conduct.
The LoRA prior and retrieval signals are clues only. Independently apply the checklist.
Return JSON only."""

IMPROVED_FEW_SHOTS = [
    (
        {
            "reported_incident": "A caller pretended to be my bank manager and convinced me to approve a transfer.",
            "candidate_provision": {"provision_id": "ITA_66D", "title": "Cheating by personation using computer resource", "legal_text": "..."},
            "element_checklist": ["A communication device or computer resource was used.", "Cheating occurred through personation."],
            "retrieval_signals": {"concept_hit_count": 1, "triage_seed": False},
            "lora_triage_prior": {"outcome": "provision_match", "possible_provision_ids": ["BNS_319"]},
        },
        {
            "provision_id": "ITA_66D", "decision": "supported",
            "evidence_spans": ["caller pretended to be my bank manager", "convinced me to approve a transfer"],
            "missing_facts": [], "reason": "The caller used personation through a communication device to induce the transfer.",
        },
    ),
    (
        {
            "reported_incident": "The seller says delivery is delayed, remains reachable, and I have no facts showing dishonest intention when I paid.",
            "candidate_provision": {"provision_id": "BNS_318", "title": "Cheating", "legal_text": "..."},
            "element_checklist": ["There was deception.", "The deception induced delivery or action."],
            "retrieval_signals": {"concept_hit_count": 0, "uncertainty_hit_count": 1},
            "lora_triage_prior": {"outcome": "out_of_scope", "possible_provision_ids": []},
        },
        {
            "provision_id": "BNS_318", "decision": "missing_facts", "evidence_spans": [],
            "missing_facts": ["What facts show that the seller intended to deceive you when accepting payment?"],
            "reason": "Delay while the seller remains reachable does not itself state deception at payment.",
        },
    ),
    (
        {
            "reported_incident": "Someone used my banking password to enter my account and transfer funds.",
            "candidate_provision": {"provision_id": "BNS_303", "title": "Theft", "legal_text": "..."},
            "element_checklist": ["Movable property was dishonestly moved out of another's possession without consent."],
            "retrieval_signals": {"companion_candidate": True},
            "lora_triage_prior": {"outcome": "provision_match", "possible_provision_ids": ["ITA_66C"]},
        },
        {
            "provision_id": "BNS_303", "decision": "rejected", "evidence_spans": [], "missing_facts": [],
            "reason": "The incident states credential misuse and an account transfer, not a separate physical taking of movable property.",
        },
    ),
    (
        {
            "reported_incident": "A stranger entered my locked home intending to steal and carried away my television.",
            "candidate_provision": {"provision_id": "BNS_329", "title": "Criminal trespass and house-trespass", "legal_text": "..."},
            "element_checklist": ["There was entry onto another's property.", "The entry had intent to commit an offence."],
            "retrieval_signals": {"concept_hit_count": 1},
            "lora_triage_prior": {"outcome": "provision_match", "possible_provision_ids": ["BNS_303"]},
        },
        {
            "provision_id": "BNS_329", "decision": "supported",
            "evidence_spans": ["entered my locked home intending to steal"], "missing_facts": [],
            "reason": "The stated entry into the home was for the purpose of committing theft.",
        },
    ),
    (
        {
            "reported_incident": "A person uploaded a video containing a sexually explicit act.",
            "candidate_provision": {"provision_id": "ITA_67A", "title": "Publishing sexually explicit material electronically", "legal_text": "..."},
            "element_checklist": ["Sexually explicit conduct was published or transmitted electronically."],
            "retrieval_signals": {"concept_hit_count": 1},
            "lora_triage_prior": {"outcome": "provision_match", "possible_provision_ids": ["ITA_67A"]},
        },
        {
            "provision_id": "ITA_67A", "decision": "supported",
            "evidence_spans": ["uploaded a video containing a sexually explicit act"], "missing_facts": [],
            "reason": "The incident expressly states electronic publication of sexually explicit conduct.",
        },
    ),
]


def improved_candidate_messages(complaint, candidate, context_candidates, triage):
    context = [{
        "provision_id": row["provision_id"],
        "title": row["title"],
        "legal_text": re.sub(r"\s+", " ", row["verified_text"]).strip()[:2600],
    } for row in context_candidates]
    payload = {
        "reported_incident": complaint,
        "candidate_provision": {
            "provision_id": candidate["provision_id"],
            "title": candidate["title"],
            "legal_text": re.sub(r"\s+", " ", candidate["verified_text"]).strip()[:4200],
        },
        "element_checklist": candidate["element_checklist"],
        "supporting_context": context,
        "retrieval_signals": {
            "concept_hit_count": candidate["concept_hit_count"],
            "uncertainty_hit_count": candidate["uncertainty_hit_count"],
            "triage_seed": candidate["triage_seed"],
            "companion_candidate": candidate["companion_candidate"],
        },
        "lora_triage_prior": triage if isinstance(triage, dict) else None,
    }
    messages = [{"role": "system", "content": IMPROVED_CANDIDATE_SYSTEM_PROMPT}]
    for example_input, example_output in IMPROVED_FEW_SHOTS:
        messages.extend([
            {"role": "user", "content": json.dumps(example_input, ensure_ascii=False)},
            {"role": "assistant", "content": json.dumps(example_output, ensure_ascii=False)},
        ])
    messages.append({"role": "user", "content": json.dumps(payload, ensure_ascii=False)})
    return messages


def validate_improved_assessment(parsed, expected_id, complaint):
    errors = []
    if not isinstance(parsed, dict):
        return ["output is not a JSON object"]
    if parsed.get("provision_id") != expected_id:
        errors.append("provision_id does not match candidate")
    decision = parsed.get("decision")
    if decision not in {"supported", "missing_facts", "rejected"}:
        errors.append("invalid decision")
    evidence = parsed.get("evidence_spans")
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        errors.append("evidence_spans is not a list of strings")
        evidence = []
    elif len(evidence) > 3:
        errors.append("evidence_spans has more than three items")
    if decision == "supported" and not evidence:
        errors.append("supported decision requires evidence_spans")
    complaint_normal = normalise_text(complaint)
    for span in evidence:
        if normalise_text(span) not in complaint_normal:
            errors.append("evidence span is not an exact complaint quotation")
            break
    missing = parsed.get("missing_facts")
    if not isinstance(missing, list) or not all(isinstance(item, str) for item in missing):
        errors.append("missing_facts is not a list of strings")
        missing = []
    elif len(missing) > 2:
        errors.append("missing_facts has more than two items")
    if decision == "missing_facts" and not missing:
        errors.append("missing_facts decision requires a question")
    if decision != "missing_facts" and missing:
        errors.append("supported/rejected decision must not contain missing_facts")
    if not isinstance(parsed.get("reason"), str) or not parsed.get("reason", "").strip():
        errors.append("reason is missing")
    return errors


def _assessment_record(candidate, complaint, raw):
    parsed = train_runner.parse_json(raw)
    errors = validate_improved_assessment(parsed, candidate["provision_id"], complaint)
    return {
        **{key: candidate[key] for key in (
            "provision_id", "title", "recommendable", "retrieval_score",
            "concept_hit_count", "uncertainty_hit_count", "triage_seed", "companion_candidate"
        )},
        "raw_model_output": raw,
        "parsed_assessment": parsed,
        "schema_valid": not errors,
        "schema_errors": errors,
    }


def assess_improved_candidates(complaint, candidates, context_candidates, triage,
                               completed=None, save_progress=None):
    completed = list(completed or [])
    by_id = {item["provision_id"]: item for item in completed}
    pending = [item for item in candidates if item["provision_id"] not in by_id]
    for start in range(0, len(pending), IMPROVED_CANDIDATE_BATCH_SIZE):
        batch = pending[start:start + IMPROVED_CANDIDATE_BATCH_SIZE]
        messages = [improved_candidate_messages(complaint, item, context_candidates, triage)
                    for item in batch]
        rendered = [rag_v2_tokenizer.apply_chat_template(
            item, add_generation_prompt=True, tokenize=False) for item in messages]
        previous_padding = rag_v2_tokenizer.padding_side
        rag_v2_tokenizer.padding_side = "left"
        try:
            encoded = rag_v2_tokenizer(
                rendered, return_tensors="pt", padding=True, add_special_tokens=False
            ).to(rag_v2_model.device)
            try:
                with rag_v2_model.disable_adapter(), torch.inference_mode():
                    generated = rag_v2_model.generate(
                        input_ids=encoded["input_ids"], attention_mask=encoded["attention_mask"],
                        max_new_tokens=300, do_sample=False,
                        pad_token_id=rag_v2_tokenizer.eos_token_id,
                        eos_token_id=rag_v2_tokenizer.eos_token_id,
                    )
                raw_outputs = rag_v2_tokenizer.batch_decode(
                    generated[:, encoded["input_ids"].shape[1]:], skip_special_tokens=True
                )
            except RuntimeError as error:
                if "out of memory" not in str(error).lower():
                    raise
                torch.cuda.empty_cache()
                raw_outputs = [generate_messages(item, 300, use_adapter=False) for item in messages]
        finally:
            rag_v2_tokenizer.padding_side = previous_padding

        for candidate, messages_one, raw in zip(batch, messages, raw_outputs):
            record = _assessment_record(candidate, complaint, raw.strip())
            if not record["schema_valid"]:
                repair = messages_one + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content":
                     "Correct these schema problems: " + "; ".join(record["schema_errors"]) +
                     ". Return one corrected JSON object only."},
                ]
                repaired_raw = generate_messages(repair, 300, use_adapter=False)
                repaired = _assessment_record(candidate, complaint, repaired_raw)
                if repaired["schema_valid"]:
                    record = repaired
            by_id[candidate["provision_id"]] = record
        completed = [by_id[item["provision_id"]] for item in candidates
                     if item["provision_id"] in by_id]
        if save_progress:
            save_progress(completed)
    return [by_id[item["provision_id"]] for item in candidates if item["provision_id"] in by_id]


def assemble_improved(complaint, triage, retrieval, assessments):
    supported = []
    questions = {}
    actions = []
    for item in assessments:
        parsed = item.get("parsed_assessment")
        if not item.get("schema_valid") or not isinstance(parsed, dict):
            actions.append({"provision_id": item["provision_id"], "action": "schema_blocked"})
            continue
        provision_id = item["provision_id"]
        decision = parsed["decision"]
        state = cue_state(complaint, provision_id)
        if decision == "supported":
            # Companion candidates need their own complaint signal. This prevents
            # a related but unstated offence from being added by association.
            if item.get("companion_candidate") and not state["positive"]:
                actions.append({
                    "provision_id": provision_id, "action": "unsupported_companion_removed",
                    "reason": "No independent complaint cue supported this related candidate.",
                })
            else:
                supported.append(provision_id)
        elif decision == "missing_facts":
            questions[provision_id] = "; ".join(parsed.get("missing_facts", [])[:2])
        elif state["uncertain"]:
            questions[provision_id] = DEFAULT_MISSING_QUESTIONS[provision_id]
            actions.append({
                "provision_id": provision_id, "action": "explicit_uncertainty_preserved",
                "reason": "The complaint expressly leaves a material statutory fact unknown.",
            })

    supported, questions, gate_actions = apply_deterministic_gates(
        complaint, supported, questions
    )
    actions.extend(gate_actions)
    supported = list(dict.fromkeys(supported))
    uncertain = [
        {"provision_id": provision_id, "missing_facts": question}
        for provision_id, question in questions.items() if provision_id not in supported
    ]
    if supported:
        final = {"outcome": "provision_match", "possible_provision_ids": supported,
                 "uncertain_sections": uncertain}
    elif uncertain:
        final = {"outcome": "insufficient_information", "possible_provision_ids": [],
                 "uncertain_sections": uncertain}
    else:
        final = {"outcome": "out_of_scope", "possible_provision_ids": [],
                 "uncertain_sections": []}
    validation = validate_final_rag_v2(final)
    return final, actions, validation


def run_improved_pipeline(complaint, triage, completed_assessments=None, save_progress=None):
    retrieval = retrieve_candidates(complaint, triage, IMPROVED_RETRIEVER)
    if not retrieval["offence_candidates"]:
        final = {"outcome": "out_of_scope", "possible_provision_ids": [],
                 "uncertain_sections": []}
        return {"retrieval": retrieval, "candidate_assessments": [],
                "evidence_gate_actions": [], "final_output": final,
                "final_validation": validate_final_rag_v2(final)}
    ensure_rag_v2_model_loaded()
    assessments = assess_improved_candidates(
        complaint, retrieval["offence_candidates"], retrieval["context_candidates"], triage,
        completed=completed_assessments, save_progress=save_progress,
    )
    final, actions, validation = assemble_improved(complaint, triage, retrieval, assessments)
    return {"retrieval": retrieval, "candidate_assessments": assessments,
            "evidence_gate_actions": actions, "final_output": final,
            "final_validation": validation}

print("Improved RAG loaded:", PIPELINE_ID)
'''


REGRESSION_CODE = r'''# ============================================================
# 150-CASE REGRESSION RUN (THE PREVIOUS SEALED SET IS NOW DEVELOPMENT EVIDENCE)
# ============================================================

import hashlib
import json
import os
import statistics
import time
from collections import Counter, defaultdict


def improved_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def improved_atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


benchmark_inputs = read_jsonl(BENCHMARK_INPUTS)
benchmark_manifest = json.loads(BENCHMARK_MANIFEST.read_text(encoding="utf-8"))
old_prediction_payload = json.loads(BENCHMARK_PREDICTIONS.read_text(encoding="utf-8"))
if old_prediction_payload.get("completed_cases") != len(benchmark_inputs):
    raise ValueError("The completed prior benchmark predictions are required to reuse LoRA triage")
triage_cache = {
    item["case_id"]: item["lora_only"] for item in old_prediction_payload["predictions"]
}
adapter_hash = old_prediction_payload["adapter_sha256"]
pipeline_identity = hashlib.sha256((
    PIPELINE_ID + IMPROVED_CORE_SHA256 + IMPROVED_CANDIDATE_SYSTEM_PROMPT +
    json.dumps(CONCEPT_PATTERNS, sort_keys=True, ensure_ascii=False) +
    json.dumps(ELEMENT_CHECKLISTS, sort_keys=True, ensure_ascii=False)
).encode("utf-8")).hexdigest()


def write_improved_state(rows, in_progress=None):
    by_id = {item["case_id"]: item for item in rows}
    ordered = [by_id[item["case_id"]] for item in benchmark_inputs
               if item["case_id"] in by_id]
    payload = {
        "schema_version": 1,
        "purpose": "regression_after_using_the_previous_benchmark_for_error_analysis",
        "pipeline_id": PIPELINE_ID,
        "pipeline_identity": pipeline_identity,
        "adapter_sha256": adapter_hash,
        "benchmark_input_sha256": benchmark_manifest["files_sha256"]["benchmark_inputs.jsonl"],
        "total_cases": len(benchmark_inputs),
        "completed_cases": len(ordered),
        "in_progress": in_progress,
        "predictions": ordered,
    }
    improved_atomic_json(IMPROVED_PREDICTIONS, payload)
    return ordered


predictions = []
resume_progress = None
if IMPROVED_PREDICTIONS.is_file() and not RESTART_IMPROVED_REGRESSION:
    prior = json.loads(IMPROVED_PREDICTIONS.read_text(encoding="utf-8"))
    if prior.get("pipeline_identity") != pipeline_identity or prior.get("adapter_sha256") != adapter_hash:
        raise RuntimeError("Existing improved results use different code or adapter. Set RESTART_IMPROVED_REGRESSION=True for an intentional restart.")
    predictions = prior.get("predictions", [])
    resume_progress = prior.get("in_progress")
    print(f"Resuming improved regression: {len(predictions)}/{len(benchmark_inputs)} complete")
elif RESTART_IMPROVED_REGRESSION:
    for path in (IMPROVED_PREDICTIONS, IMPROVED_REPORT):
        path.unlink(missing_ok=True)

completed_ids = {item["case_id"] for item in predictions}
for case in benchmark_inputs:
    if case["case_id"] in completed_ids:
        continue
    print(f"IMPROVED {case['case_id']} ({len(predictions)+1}/{len(benchmark_inputs)})")
    triage_record = triage_cache[case["case_id"]]
    triage = triage_record["parsed"]
    retrieval_preview = retrieve_candidates(case["complaint"], triage, IMPROVED_RETRIEVER)
    candidate_ids = [item["provision_id"] for item in retrieval_preview["offence_candidates"]]
    prior_assessments = []
    if (isinstance(resume_progress, dict) and resume_progress.get("case_id") == case["case_id"]
            and resume_progress.get("candidate_ids") == candidate_ids):
        prior_assessments = resume_progress.get("candidate_assessments", [])

    def save_progress(assessments):
        write_improved_state(predictions, {
            "case_id": case["case_id"], "candidate_ids": candidate_ids,
            "candidate_assessments": assessments,
        })

    started = time.perf_counter()
    result = run_improved_pipeline(
        case["complaint"], triage,
        completed_assessments=prior_assessments,
        save_progress=save_progress,
    )
    elapsed = time.perf_counter() - started
    predictions.append({
        **case,
        "lora_only": triage_record,
        "retrieved_provision_ids": [
            item["provision_id"] for item in result["retrieval"]["offence_candidates"]
        ],
        "candidate_assessments": result["candidate_assessments"],
        "evidence_gate_actions": result["evidence_gate_actions"],
        "final_output": result["final_output"],
        "final_validation": result["final_validation"],
        "latency_seconds": round(elapsed, 6),
    })
    predictions = write_improved_state(predictions, None)
    resume_progress = None
    print(" ", json.dumps(result["final_output"], ensure_ascii=False), f"{elapsed:.1f}s")


def score_improved(predictions, gold_by_id):
    tp = fp = fn = outcomes = exact_positive = positive = 0
    invalid = 0
    missing_total = missing_hit = 0
    out_total = out_fp = 0
    by_group = defaultdict(lambda: {"cases": 0, "outcome_correct": 0, "strict_exact": 0})
    by_language = defaultdict(lambda: {"cases": 0, "outcome_correct": 0, "strict_exact": 0})
    false_sections = Counter()
    missed_sections = Counter()
    valid_ids = set(IMPROVED_RETRIEVER["index"])
    for row in predictions:
        gold = gold_by_id[row["case_id"]]
        output = row["final_output"]
        predicted = set(output.get("possible_provision_ids", []))
        required = set(gold["required_provision_ids"])
        outcome_ok = output.get("outcome") == gold["outcome"]
        strict = outcome_ok and predicted == required
        outcomes += int(outcome_ok)
        if gold["outcome"] == "provision_match":
            positive += 1
            exact_positive += int(strict)
            tp += len(predicted & required)
            fp += len(predicted - required)
            fn += len(required - predicted)
            false_sections.update(predicted - required - set(gold["optional_provision_ids"]))
            missed_sections.update(required - predicted)
        if gold["required_uncertain_ids"]:
            missing_total += 1
            uncertain_ids = {item.get("provision_id") for item in output.get("uncertain_sections", [])}
            missing_hit += int(bool(uncertain_ids & set(gold["required_uncertain_ids"])))
        if gold["outcome"] == "out_of_scope":
            out_total += 1
            out_fp += int(output.get("outcome") == "provision_match" or bool(predicted))
        invalid += len(predicted - valid_ids)
        for bucket, key in ((by_group, row["group"]), (by_language, row["language"])):
            bucket[key]["cases"] += 1
            bucket[key]["outcome_correct"] += int(outcome_ok)
            bucket[key]["strict_exact"] += int(strict)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    def finish(buckets):
        return {key: {**value,
                      "outcome_accuracy": value["outcome_correct"] / value["cases"],
                      "strict_exact_accuracy": value["strict_exact"] / value["cases"]}
                for key, value in sorted(buckets.items())}
    return {
        "cases": len(predictions), "positive_cases": positive,
        "outcome_accuracy": outcomes / len(predictions),
        "strict_exact_positive_section_accuracy": exact_positive / positive,
        "strict_section_precision": precision, "required_section_recall": recall,
        "strict_section_f1": f1,
        "missing_question_target_accuracy": missing_hit / missing_total if missing_total else 1.0,
        "out_of_scope_false_positive_rate": out_fp / out_total if out_total else 0.0,
        "invalid_provision_id_count": invalid,
        "false_positive_sections": dict(false_sections),
        "missed_sections": dict(missed_sections),
        "by_group": finish(by_group), "by_language": finish(by_language),
    }


if len(predictions) == len(benchmark_inputs):
    gold_rows = read_jsonl(BENCHMARK_GOLD)
    gold_by_id = {item["case_id"]: item for item in gold_rows}
    metrics = score_improved(predictions, gold_by_id)
    retrieval_required = retrieval_found = all_found = positive_cases = 0
    for row in predictions:
        required = set(gold_by_id[row["case_id"]]["required_provision_ids"])
        if required:
            retrieved = set(row["retrieved_provision_ids"])
            retrieval_required += len(required)
            retrieval_found += len(required & retrieved)
            positive_cases += 1
            all_found += int(required.issubset(retrieved))
    retrieval_recall = retrieval_found / retrieval_required
    gates = {
        "output_structure_100_percent": all(row["final_validation"]["valid"] for row in predictions),
        "invalid_provision_ids_zero": metrics["invalid_provision_id_count"] == 0,
        "outcome_accuracy_at_least_0_90": metrics["outcome_accuracy"] >= 0.90,
        "strict_exact_positive_at_least_0_80": metrics["strict_exact_positive_section_accuracy"] >= 0.80,
        "strict_precision_at_least_0_90": metrics["strict_section_precision"] >= 0.90,
        "required_recall_at_least_0_80": metrics["required_section_recall"] >= 0.80,
        "retrieval_recall_at_least_0_95": retrieval_recall >= 0.95,
        "out_of_scope_false_positive_at_most_0_05": metrics["out_of_scope_false_positive_rate"] <= 0.05,
    }
    report = {
        "schema_version": 1,
        "purpose": "development_regression_not_final_unseen_accuracy",
        "pipeline_id": PIPELINE_ID,
        "pipeline_identity": pipeline_identity,
        "adapter_sha256": adapter_hash,
        "note": "This set was used for error analysis. Results are regression evidence, not a new sealed estimate. Labels are AI-reviewed, not lawyer-verified.",
        "metrics": metrics,
        "retrieval": {
            "required_section_recall_at_6": retrieval_recall,
            "all_required_retrieved_case_accuracy": all_found / positive_cases,
            "required_sections": retrieval_required,
            "required_sections_found": retrieval_found,
        },
        "reliability": {
            "candidate_schema_error_count": sum(
                not item["schema_valid"] for row in predictions for item in row["candidate_assessments"]
            ),
            "final_validation_error_count": sum(not row["final_validation"]["valid"] for row in predictions),
        },
        "latency_seconds": {
            "mean": statistics.mean(row["latency_seconds"] for row in predictions),
            "median": statistics.median(row["latency_seconds"] for row in predictions),
            "total": sum(row["latency_seconds"] for row in predictions),
        },
        "release_gates": gates,
        "all_regression_gates_passed": all(gates.values()),
    }
    improved_atomic_json(IMPROVED_REPORT, report)
    display(Markdown("# Improved RAG regression results"))
    display(DisplayJSON(report, expanded=True))
    print("Saved:", IMPROVED_REPORT)
else:
    print(f"Improved regression incomplete: {len(predictions)}/{len(benchmark_inputs)}")
'''


INTERACTIVE_CODE = r'''# ============================================================
# INTERACTIVE FINAL PIPELINE TESTER
# ============================================================

import ipywidgets as widgets
from IPython.display import display, clear_output, Markdown, JSON as DisplayJSON

improved_input = widgets.Textarea(
    value="",
    placeholder="Describe the complaint in English, Hindi or Hinglish...",
    description="Complaint:",
    layout=widgets.Layout(width="100%", height="130px"),
    style={"description_width": "90px"},
)
improved_button = widgets.Button(description="Run improved RAG", button_style="primary", icon="search")
improved_output = widgets.Output()


def on_improved_click(_):
    complaint = improved_input.value.strip()
    with improved_output:
        clear_output()
        if not complaint:
            print("Enter a complaint first.")
            return
        try:
            ensure_rag_v2_model_loaded()
            raw, triage = run_live_lora_triage(complaint)
            result = run_improved_pipeline(complaint, triage)
            record = {
                "complaint": complaint,
                "lora_only": {"raw": raw, "parsed": triage},
                "pipeline_id": PIPELINE_ID,
                **result,
            }
            with IMPROVED_INTERACTIVE_LOG.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            display(Markdown("## LoRA triage"))
            display(DisplayJSON(triage, expanded=True))
            display(Markdown("## Retrieved candidates"))
            display(DisplayJSON(result["retrieval"]["offence_candidates"], expanded=False))
            display(Markdown("## Candidate assessments"))
            display(DisplayJSON(result["candidate_assessments"], expanded=False))
            display(Markdown("## Final validated output"))
            display(DisplayJSON(result["final_output"], expanded=True))
            print("Saved to:", IMPROVED_INTERACTIVE_LOG)
        except Exception as error:
            print(type(error).__name__ + ":", error)


improved_button.on_click(on_improved_click)
display(Markdown("# Test a new complaint"))
display(improved_input, improved_button, improved_output)
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    notebook = json.loads(args.source.read_text(encoding="utf-8"))
    cells = []
    for cell in notebook.get("cells", []):
        tags = cell.get("metadata", {}).get("tags", [])
        if any(tag.startswith(TAG_PREFIX) for tag in tags):
            continue
        if cell.get("cell_type") == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        cells.append(cell)
    if not any("SEALED RAG V2.2 BENCHMARK" in "".join(cell.get("source", [])) for cell in cells):
        raise ValueError("Source notebook does not contain the completed benchmark workflow")
    core_source = CORE.read_text(encoding="utf-8")
    core_sha256 = hashlib.sha256(core_source.encode("utf-8")).hexdigest()
    setup_source = f'IMPROVED_CORE_SHA256 = "{core_sha256}"\n' + SETUP_CODE
    cells.extend([
        markdown("""# Improved grounded RAG pipeline

This stage fixes the measured retrieval and filtering weaknesses without retraining the LoRA. It uses multilingual concept retrieval over the 19 approved complaint provisions, exact complaint evidence in every positive candidate assessment, stronger statutory distinctions and resumable per-candidate saving.

The earlier 150-case set has already been inspected, so this run is labelled a **regression test**. It is used to verify the fixes and is not reported as a new unseen final accuracy estimate.
""", "legalai-improved-rag-intro"),
        code(core_source, "legalai-improved-rag-core"),
        code(setup_source, "legalai-improved-rag-setup"),
        code(REGRESSION_CODE, "legalai-improved-rag-regression"),
        code(INTERACTIVE_CODE, "legalai-improved-rag-interactive"),
    ])
    notebook["cells"] = cells
    metadata = notebook.setdefault("metadata", {})
    metadata.pop("widgets", None)
    metadata["accelerator"] = "GPU"
    metadata.setdefault("colab", {})["gpuType"] = "T4"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
