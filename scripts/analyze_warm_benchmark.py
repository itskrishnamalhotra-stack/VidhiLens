import json
from collections import Counter, defaultdict
from pathlib import Path


PREDICTIONS = Path(r"H:\My Drive\LegalAI\warm_vllm_predictions.json")
ANSWER_KEY = Path(r"H:\My Drive\LegalAI\sealed_rag_benchmark_v1\sealed_answer_key.jsonl")


def as_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


root = json.loads(PREDICTIONS.read_text(encoding="utf-8"))
predictions = root["predictions"]
gold = {
    row["case_id"]: row
    for row in (
        json.loads(line)
        for line in ANSWER_KEY.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
}

confusion = Counter()
fn_sections = Counter()
fp_sections = Counter()
misses = []
repair_times = []
normal_times = []

for pred in predictions:
    case_id = pred["case_id"]
    expected = gold[case_id]
    final = pred["final_output"]
    expected_outcome = expected["outcome"]
    predicted_outcome = final["outcome"]
    required = set(as_list(expected.get("required_provision_ids")))
    optional = set(as_list(expected.get("optional_provision_ids")))
    predicted = set(as_list(final.get("possible_provision_ids")))
    confusion[(expected_outcome, predicted_outcome)] += 1
    for section in required - predicted:
        fn_sections[section] += 1
    for section in predicted - required - optional:
        fp_sections[section] += 1

    timing = pred.get("timing", {})
    if pred.get("repair_used"):
        repair_times.append(timing.get("total_seconds", 0))
    else:
        normal_times.append(timing.get("total_seconds", 0))

    outcome_wrong = expected_outcome != predicted_outcome
    missing_required = sorted(required - predicted)
    extra = sorted(predicted - required - optional)
    if outcome_wrong or missing_required or extra:
        triage = pred.get("triage", {})
        triage_ids = set(as_list(triage.get("possible_provision_ids")))
        retrieved = set(as_list(pred.get("retrieved_provision_ids")))
        misses.append(
            {
                "case_id": case_id,
                "group": pred.get("group"),
                "difficulty": pred.get("difficulty"),
                "language": pred.get("language"),
                "gold_outcome": expected_outcome,
                "predicted_outcome": predicted_outcome,
                "required": sorted(required),
                "predicted": sorted(predicted),
                "missing_required": missing_required,
                "extra": extra,
                "missing_was_in_triage": sorted(set(missing_required) & triage_ids),
                "missing_was_retrieved": sorted(set(missing_required) & retrieved),
                "triage_outcome": triage.get("outcome"),
                "triage_ids": sorted(triage_ids),
                "gate_actions": pred.get("evidence_gate_actions", []),
                "repair_used": bool(pred.get("repair_used")),
                "seconds": round(timing.get("total_seconds", 0), 2),
                "complaint": pred.get("complaint"),
            }
        )

summary = {
    "cases": len(predictions),
    "outcome_confusion": [
        {"gold": key[0], "predicted": key[1], "count": count}
        for key, count in sorted(confusion.items())
    ],
    "outcome_mismatch_count": sum(
        count for (expected, predicted), count in confusion.items() if expected != predicted
    ),
    "cases_with_any_strict_error": len(misses),
    "top_missing_sections": fn_sections.most_common(),
    "top_extra_sections": fp_sections.most_common(),
    "repair": {
        "count": len(repair_times),
        "mean_seconds": round(sum(repair_times) / len(repair_times), 2) if repair_times else None,
    },
    "no_repair": {
        "count": len(normal_times),
        "mean_seconds": round(sum(normal_times) / len(normal_times), 2) if normal_times else None,
    },
    "mismatches": misses,
}

print(json.dumps(summary, ensure_ascii=False, indent=2))
