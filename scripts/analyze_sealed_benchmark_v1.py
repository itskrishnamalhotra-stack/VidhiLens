"""Create a deterministic error audit from the completed sealed RAG benchmark."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(r"E:\term paper project")
PREDICTIONS = ROOT / "phase1/evaluation/sealed_rag_benchmark_v1_predictions.json"
GOLD = ROOT / "phase1/evaluation/sealed_rag_benchmark_v1/sealed_answer_key.jsonl"
OUTPUT_JSON = ROOT / "phase1/evaluation/SEALED_BENCHMARK_V1_ERROR_ANALYSIS.json"
OUTPUT_MD = ROOT / "phase1/evaluation/SEALED_BENCHMARK_V1_ERROR_ANALYSIS.md"

payload = json.loads(PREDICTIONS.read_text(encoding="utf-8"))
gold_rows = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines()]
gold_by_id = {row["case_id"]: row for row in gold_rows}

errors = []
miss_stage_counts = Counter()
miss_by_section = Counter()
false_positive_counts = Counter()
outcome_errors = Counter()
assessment_decisions = Counter()

for prediction in payload["predictions"]:
    case_id = prediction["case_id"]
    gold = gold_by_id[case_id]
    required = set(gold["required_provision_ids"])
    optional = set(gold["optional_provision_ids"])
    allowed = required | optional
    final = prediction["rag_v2_2"]["final_output"]
    predicted = set(final["possible_provision_ids"])
    retrieved = set(prediction["retrieved_provision_ids"])
    assessment_by_id = {
        row["provision_id"]: row for row in prediction["candidate_assessments"]
    }
    actions_by_id = defaultdict(list)
    for action in prediction["rag_v2_2"]["evidence_gate_actions"]:
        actions_by_id[action["provision_id"]].append(action)

    missed = sorted(required - predicted)
    extra = sorted(predicted - allowed)
    outcome_ok = final["outcome"] == gold["outcome"]
    if not outcome_ok:
        outcome_errors[f"{gold['outcome']} -> {final['outcome']}"] += 1

    misses = []
    for provision_id in missed:
        miss_by_section[provision_id] += 1
        assessment = assessment_by_id.get(provision_id)
        if provision_id not in retrieved:
            stage = "retrieval_miss"
        elif not assessment:
            stage = "assessment_missing"
        elif not assessment.get("schema_valid"):
            stage = "assessment_schema_error"
        elif assessment["parsed_assessment"].get("decision") != "supported":
            stage = "candidate_assessor_" + assessment["parsed_assessment"].get("decision", "unknown")
        elif actions_by_id.get(provision_id):
            stage = "evidence_gate_removed_or_downgraded"
        else:
            stage = "assembly_or_scoring"
        miss_stage_counts[stage] += 1
        misses.append({
            "provision_id": provision_id,
            "stage": stage,
            "assessment": assessment,
            "gate_actions": actions_by_id.get(provision_id, []),
        })

    extras = []
    for provision_id in extra:
        false_positive_counts[provision_id] += 1
        assessment = assessment_by_id.get(provision_id)
        if assessment and isinstance(assessment.get("parsed_assessment"), dict):
            assessment_decisions[assessment["parsed_assessment"].get("decision", "unknown")] += 1
        extras.append({
            "provision_id": provision_id,
            "assessment": assessment,
            "gate_actions": actions_by_id.get(provision_id, []),
        })

    expected_uncertain = set(gold["required_uncertain_ids"])
    actual_uncertain = {
        row.get("provision_id") for row in final.get("uncertain_sections", [])
        if isinstance(row, dict)
    }
    missing_uncertain = sorted(expected_uncertain - actual_uncertain)
    if missed or extra or not outcome_ok or missing_uncertain:
        errors.append({
            "case_id": case_id,
            "group": prediction["group"],
            "language": prediction["language"],
            "complaint": prediction["complaint"],
            "gold": gold,
            "lora_only": prediction["lora_only"]["parsed"],
            "retrieved_provision_ids": prediction["retrieved_provision_ids"],
            "rag_v2_2_final": final,
            "misses": misses,
            "extras": extras,
            "missing_required_uncertain_ids": missing_uncertain,
            "outcome_correct": outcome_ok,
            "latency_seconds": prediction["latency_seconds"],
        })

analysis = {
    "benchmark_version": payload["benchmark_version"],
    "cases": payload["completed_cases"],
    "cases_with_any_gold_disagreement": len(errors),
    "miss_stage_counts": dict(miss_stage_counts),
    "missed_required_sections": dict(miss_by_section),
    "false_positive_sections": dict(false_positive_counts),
    "false_positive_assessment_decisions": dict(assessment_decisions),
    "outcome_error_transitions": dict(outcome_errors),
    "errors": errors,
}
OUTPUT_JSON.write_text(json.dumps(analysis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

lines = [
    "# Sealed benchmark v1 error analysis",
    "",
    f"- Cases: {payload['completed_cases']}",
    f"- Cases with any gold disagreement: {len(errors)}",
    f"- Required-section miss stages: `{json.dumps(dict(miss_stage_counts), sort_keys=True)}`",
    f"- Outcome transitions: `{json.dumps(dict(outcome_errors), sort_keys=True)}`",
    "",
    "## Case details",
    "",
]
for error in errors:
    lines.extend([
        f"### {error['case_id']} — {error['group']} — {error['language']}",
        "",
        error["complaint"],
        "",
        f"- Gold outcome: `{error['gold']['outcome']}`",
        f"- Required: `{', '.join(error['gold']['required_provision_ids']) or '(none)'}`",
        f"- Optional: `{', '.join(error['gold']['optional_provision_ids']) or '(none)'}`",
        f"- LoRA: `{json.dumps(error['lora_only'], ensure_ascii=False)}`",
        f"- Retrieved: `{', '.join(error['retrieved_provision_ids']) or '(none)'}`",
        f"- RAG v2.2: `{json.dumps(error['rag_v2_2_final'], ensure_ascii=False)}`",
    ])
    for miss in error["misses"]:
        reason = ""
        parsed = (miss.get("assessment") or {}).get("parsed_assessment")
        if isinstance(parsed, dict):
            reason = parsed.get("reason", "")
        lines.append(f"- Miss `{miss['provision_id']}`: **{miss['stage']}** — {reason}")
    for extra in error["extras"]:
        reason = ""
        parsed = (extra.get("assessment") or {}).get("parsed_assessment")
        if isinstance(parsed, dict):
            reason = parsed.get("reason", "")
        lines.append(f"- Extra `{extra['provision_id']}` — {reason}")
    if error["missing_required_uncertain_ids"]:
        lines.append("- Missing uncertainty target: `" + ", ".join(
            error["missing_required_uncertain_ids"]) + "`")
    lines.append("")

OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps({key: value for key, value in analysis.items() if key != "errors"}, indent=2))
print(OUTPUT_MD)
