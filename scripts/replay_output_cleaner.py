"""Replay the deterministic output layer over saved warm-model decisions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_improved_core import (
    DEFAULT_MISSING_QUESTIONS,
    apply_deterministic_gates,
    apply_output_cleaner,
    cue_state,
    explicit_transaction_uncertainty,
    has_scoped_legal_subject,
    triage_seed_ids,
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def replay(row: dict) -> dict:
    complaint = row["complaint"]
    triage = row.get("triage") if isinstance(row.get("triage"), dict) else {}
    candidates = row.get("candidate_assessments", [])
    candidate_ids = [item["provision_id"] for item in candidates]
    supported: list[str] = []
    questions: dict[str, str] = {}

    for item in candidates:
        parsed = item.get("parsed_assessment")
        if not isinstance(parsed, dict):
            continue
        provision_id = item["provision_id"]
        decision = parsed.get("decision")
        state = cue_state(complaint, provision_id)
        if decision == "supported":
            if state["positive"] or item.get("triage_seed"):
                supported.append(provision_id)
        elif decision == "missing_facts":
            questions[provision_id] = DEFAULT_MISSING_QUESTIONS[provision_id]
        elif state["uncertain"]:
            questions[provision_id] = DEFAULT_MISSING_QUESTIONS[provision_id]

    supported, questions, _ = apply_deterministic_gates(complaint, supported, questions)
    triage_outcome = triage.get("outcome")
    if triage_outcome == "provision_match":
        for provision_id in triage_seed_ids(triage):
            if (
                provision_id in candidate_ids
                and cue_state(complaint, provision_id)["positive"]
                and provision_id not in supported
            ):
                supported.append(provision_id)
        supported, questions, _ = apply_deterministic_gates(complaint, supported, questions)
        supported, questions, _ = apply_output_cleaner(
            complaint, supported, questions, candidate_ids
        )

    supported = list(dict.fromkeys(supported))
    uncertain = [
        {"provision_id": provision_id, "missing_facts": question}
        for provision_id, question in questions.items()
        if provision_id not in supported
    ]
    if (
        triage_outcome == "insufficient_information"
        and not uncertain
        and not has_scoped_legal_subject(complaint)
    ):
        return {"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}
    if triage_outcome == "insufficient_information":
        return {
            "outcome": "insufficient_information",
            "possible_provision_ids": [],
            "uncertain_sections": uncertain,
        }
    if (
        triage_outcome != "provision_match"
        and uncertain
        and explicit_transaction_uncertainty(complaint)
    ):
        return {
            "outcome": "insufficient_information",
            "possible_provision_ids": [],
            "uncertain_sections": uncertain,
        }
    if triage_outcome != "provision_match":
        return {"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}
    if supported:
        return {
            "outcome": "provision_match",
            "possible_provision_ids": supported,
            "uncertain_sections": uncertain,
        }
    if uncertain:
        return {
            "outcome": "insufficient_information",
            "possible_provision_ids": [],
            "uncertain_sections": uncertain,
        }
    return {"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}


def score(rows: list[dict], gold_by_id: dict[str, dict]) -> dict:
    tp = fp = fn = outcome_hits = exact_hits = positive = exact_positive = 0
    out_total = out_fp = 0
    for row in rows:
        gold = gold_by_id[row["case_id"]]
        output = row["final_output"]
        predicted = set(output.get("possible_provision_ids", []))
        required = set(gold["required_provision_ids"])
        outcome_ok = output.get("outcome") == gold["outcome"]
        strict = outcome_ok and predicted == required
        outcome_hits += int(outcome_ok)
        exact_hits += int(strict)
        if gold["outcome"] == "provision_match":
            positive += 1
            exact_positive += int(strict)
            tp += len(predicted & required)
            fp += len(predicted - required)
            fn += len(required - predicted)
        if gold["outcome"] == "out_of_scope":
            out_total += 1
            out_fp += int(output.get("outcome") == "provision_match" or bool(predicted))
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        "cases": len(rows),
        "outcome_accuracy": outcome_hits / len(rows),
        "strict_exact_all_case_accuracy": exact_hits / len(rows),
        "strict_exact_positive_section_accuracy": exact_positive / positive,
        "strict_section_precision": precision,
        "required_section_recall": recall,
        "strict_section_f1": 2 * precision * recall / (precision + recall),
        "out_of_scope_false_positive_rate": out_fp / out_total,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", type=Path)
    parser.add_argument("answer_key", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = json.loads(args.predictions.read_text(encoding="utf-8"))
    gold_by_id = {row["case_id"]: row for row in read_jsonl(args.answer_key)}
    old_rows = root["predictions"]
    new_rows = [
        {**row, "final_output": replay(row)}
        for row in old_rows
    ]
    report = {
        "before": score(old_rows, gold_by_id),
        "after": score(new_rows, gold_by_id),
        "changed_cases": [
            {
                "case_id": old["case_id"],
                "before": old["final_output"],
                "after": new["final_output"],
            }
            for old, new in zip(old_rows, new_rows)
            if old["final_output"] != new["final_output"]
        ],
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
