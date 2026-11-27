"""Append the sealed 150-case RAG v2.2 evaluator to the tested notebook."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


TAG_PREFIX = "legalai-sealed-rag-benchmark-v1-"


def markdown(source: str, tag: str) -> dict:
    return {"cell_type": "markdown", "metadata": {"tags": [tag]},
            "source": source.splitlines(keepends=True)}


def code(source: str, tag: str) -> dict:
    return {"cell_type": "code", "execution_count": None,
            "metadata": {"tags": [tag]}, "outputs": [],
            "source": source.splitlines(keepends=True)}


BENCHMARK_CODE = r'''# ============================================================
# SEALED RAG V2.2 BENCHMARK: 150 UNSEEN COMPLAINTS
# ============================================================

import hashlib
import json
import math
import os
import re
import statistics
import time
import torch
from collections import Counter, defaultdict
from pathlib import Path
from IPython.display import display, Markdown, JSON as DisplayJSON

BENCHMARK_VERSION = "sealed_rag_benchmark_v1"
BENCHMARK_DIR = PROJECT / BENCHMARK_VERSION
BENCHMARK_INPUTS = BENCHMARK_DIR / "benchmark_inputs.jsonl"
BENCHMARK_GOLD = BENCHMARK_DIR / "sealed_answer_key.jsonl"
BENCHMARK_MANIFEST = BENCHMARK_DIR / "manifest.json"
BENCHMARK_PREDICTIONS = PROJECT / "sealed_rag_benchmark_v1_predictions.json"
BENCHMARK_REPORT = PROJECT / "sealed_rag_benchmark_v1_report.json"
RESTART_SEALED_BENCHMARK = False


def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


for required_path in (BENCHMARK_INPUTS, BENCHMARK_GOLD, BENCHMARK_MANIFEST):
    if not required_path.is_file():
        raise FileNotFoundError(f"Missing sealed benchmark file: {required_path}")

benchmark_manifest = json.loads(BENCHMARK_MANIFEST.read_text(encoding="utf-8"))
if benchmark_manifest.get("benchmark") != BENCHMARK_VERSION:
    raise ValueError("Unexpected benchmark manifest")
for filename, expected_hash in benchmark_manifest["files_sha256"].items():
    path = BENCHMARK_DIR / filename
    if file_sha256(path) != expected_hash:
        raise ValueError(f"Benchmark integrity check failed: {filename}")

benchmark_inputs = read_jsonl(BENCHMARK_INPUTS)
if len(benchmark_inputs) != 150 or len({row["case_id"] for row in benchmark_inputs}) != 150:
    raise ValueError("Expected 150 unique benchmark inputs")

BENCHMARK_CANDIDATE_BATCH_SIZE = 2


def benchmark_candidate_messages(complaint, candidate, context_candidates, triage):
    support = [{
        "provision_id": row["provision_id"],
        "title": row["title"],
        "legal_status": row["legal_status"],
        "provision_kind": row["provision_kind"],
        "legal_text": re.sub(r"\s+", " ", row["verified_text"]).strip()[:3500],
    } for row in context_candidates]
    candidate_payload = {
        "provision_id": candidate["provision_id"],
        "title": candidate["title"],
        "legal_text": re.sub(r"\s+", " ", candidate["verified_text"]).strip()[:6500],
    }
    user_payload = {
        "reported_incident": complaint,
        "candidate_provision": candidate_payload,
        "context_only_provisions": support,
        "lora_triage_prior": triage if isinstance(triage, dict) else None,
    }
    messages = [{"role": "system", "content": CANDIDATE_SYSTEM_PROMPT}]
    for example_input, example_output in CANDIDATE_FEW_SHOTS:
        messages.extend([
            {"role": "user", "content": json.dumps(example_input, ensure_ascii=False)},
            {"role": "assistant", "content": json.dumps(example_output, ensure_ascii=False)},
        ])
    messages.append({"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)})
    return messages


def generate_benchmark_candidate_batch(message_batches, max_new_tokens=260):
    """Deterministically generate several independent candidate assessments."""
    rendered = [
        rag_v2_tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False
        )
        for messages in message_batches
    ]
    previous_padding_side = rag_v2_tokenizer.padding_side
    rag_v2_tokenizer.padding_side = "left"
    try:
        encoded = rag_v2_tokenizer(
            rendered, return_tensors="pt", padding=True, add_special_tokens=False
        ).to(rag_v2_model.device)
        with rag_v2_model.disable_adapter():
            with torch.inference_mode():
                generated = rag_v2_model.generate(
                    input_ids=encoded["input_ids"],
                    attention_mask=encoded["attention_mask"],
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    pad_token_id=rag_v2_tokenizer.eos_token_id,
                    eos_token_id=rag_v2_tokenizer.eos_token_id,
                )
        continuations = generated[:, encoded["input_ids"].shape[1]:]
        return [text.strip() for text in rag_v2_tokenizer.batch_decode(
            continuations, skip_special_tokens=True
        )]
    finally:
        rag_v2_tokenizer.padding_side = previous_padding_side


def benchmark_assessment_record(candidate, raw):
    parsed = train_runner.parse_json(raw)
    errors = validate_candidate_assessment(parsed, candidate["provision_id"])
    return {
        "provision_id": candidate["provision_id"],
        "title": candidate["title"],
        "recommendable": candidate["recommendable"],
        "retrieval_score": candidate["retrieval_score"],
        "raw_model_output": raw,
        "parsed_assessment": parsed,
        "schema_valid": not errors,
        "schema_errors": errors,
    }


def assess_benchmark_candidates(complaint, candidates, context_candidates, triage):
    assessments = []
    for start in range(0, len(candidates), BENCHMARK_CANDIDATE_BATCH_SIZE):
        batch = candidates[start:start + BENCHMARK_CANDIDATE_BATCH_SIZE]
        messages = [
            benchmark_candidate_messages(complaint, candidate, context_candidates, triage)
            for candidate in batch
        ]
        try:
            raw_outputs = generate_benchmark_candidate_batch(messages)
        except RuntimeError as error:
            if "out of memory" not in str(error).lower():
                raise
            print("  Candidate batch exceeded GPU memory; retrying this batch one at a time")
            torch.cuda.empty_cache()
            raw_outputs = []
            for one_messages in messages:
                raw_outputs.append(generate_messages(one_messages, 260, use_adapter=False))
        for candidate, raw in zip(batch, raw_outputs):
            record = benchmark_assessment_record(candidate, raw)
            if not record["schema_valid"]:
                # Reuse the proven repair path for the uncommon malformed response.
                record = assess_one_candidate(complaint, candidate, context_candidates, triage)
            assessments.append(record)
    return assessments


def run_benchmark_rag_v2(complaint, triage):
    if triage.get("outcome") == "out_of_scope":
        retrieval = {
            "offence_candidates": [], "context_candidates": [],
            "minimum_bm25_score": RAG_V2_MIN_BM25_SCORE,
        }
        assessments = []
    else:
        retrieval = retrieve_rag_v2(complaint, triage)
        assessments = assess_benchmark_candidates(
            complaint, retrieval["offence_candidates"], retrieval["context_candidates"], triage
        )
    final, blocked, rule = assemble_rag_v2(triage, retrieval, assessments)
    validation = validate_final_rag_v2(final)
    return {
        "retrieval": retrieval,
        "candidate_assessments": assessments,
        "blocked_supported_candidates": blocked,
        "assembly_rule": rule,
        "final_output": final,
        "final_validation": validation,
    }


def write_prediction_state(predictions, in_progress=None):
    by_id = {row["case_id"]: row for row in predictions}
    ordered = [by_id[row["case_id"]] for row in benchmark_inputs if row["case_id"] in by_id]
    payload = {
        "schema_version": 1,
        "benchmark_version": BENCHMARK_VERSION,
        "rag_version": RAG_V2_2_VERSION,
        "adapter_sha256": v2_1_payload["adapter_sha256"],
        "input_sha256": benchmark_manifest["files_sha256"]["benchmark_inputs.jsonl"],
        "total_cases": len(benchmark_inputs),
        "completed_cases": len(ordered),
        "in_progress": in_progress,
        "predictions": ordered,
    }
    temporary = BENCHMARK_PREDICTIONS.with_suffix(".json.part")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, BENCHMARK_PREDICTIONS)
    return ordered


predictions = []
if BENCHMARK_PREDICTIONS.is_file() and not RESTART_SEALED_BENCHMARK:
    previous = json.loads(BENCHMARK_PREDICTIONS.read_text(encoding="utf-8"))
    identity_errors = []
    if previous.get("benchmark_version") != BENCHMARK_VERSION:
        identity_errors.append("benchmark version")
    if previous.get("rag_version") != RAG_V2_2_VERSION:
        identity_errors.append("RAG version")
    if previous.get("adapter_sha256") != v2_1_payload["adapter_sha256"]:
        identity_errors.append("adapter hash")
    if previous.get("input_sha256") != benchmark_manifest["files_sha256"]["benchmark_inputs.jsonl"]:
        identity_errors.append("input hash")
    if identity_errors:
        raise RuntimeError(
            "Existing sealed predictions use a different " + ", ".join(identity_errors) +
            ". Set RESTART_SEALED_BENCHMARK=True only for an intentional restart."
        )
    predictions = previous.get("predictions", [])
    print(f"Resuming sealed benchmark: {len(predictions)}/{len(benchmark_inputs)} complete")
elif RESTART_SEALED_BENCHMARK:
    for path in (BENCHMARK_PREDICTIONS, BENCHMARK_REPORT):
        if path.exists():
            path.unlink()

completed_ids = {row["case_id"] for row in predictions}
pending = [row for row in benchmark_inputs if row["case_id"] not in completed_ids]
if pending:
    ensure_rag_v2_model_loaded()

for case in pending:
    position = len(predictions) + 1
    print(f"SEALED {case['case_id']} ({position}/{len(benchmark_inputs)}) "
          f"{case['group']} {case['language']}")
    started = time.perf_counter()
    triage_raw, triage = run_live_lora_triage(case["complaint"])
    if not isinstance(triage, dict):
        raise ValueError(f"LoRA output was not JSON for {case['case_id']}: {triage_raw}")

    v2_1_result = run_benchmark_rag_v2(case["complaint"], triage)
    v2_2_final, actions, rule = postprocess_rag_v2_2(
        case["complaint"], triage, v2_1_result["candidate_assessments"],
        v2_1_result.get("blocked_supported_candidates", [])
    )
    validation = validate_final_rag_v2(v2_2_final)
    elapsed = time.perf_counter() - started
    record = {
        **case,
        "lora_only": {"raw": triage_raw, "parsed": triage},
        "retrieved_provision_ids": [
            item["provision_id"] for item in v2_1_result["retrieval"]["offence_candidates"]
        ],
        "context_provision_ids": [
            item["provision_id"] for item in v2_1_result["retrieval"]["context_candidates"]
        ],
        "candidate_assessments": v2_1_result["candidate_assessments"],
        "blocked_supported_candidates": v2_1_result["blocked_supported_candidates"],
        "rag_v2_2": {
            "evidence_gate_actions": actions,
            "assembly_rule": rule,
            "final_output": v2_2_final,
            "final_validation": validation,
        },
        "latency_seconds": round(elapsed, 6),
    }
    predictions.append(record)
    predictions = write_prediction_state(predictions)
    print("  LoRA:", json.dumps(triage, ensure_ascii=False))
    print("  RAG v2.2:", json.dumps(v2_2_final, ensure_ascii=False))
    print(f"  {elapsed:.1f}s; saved to Drive\n")

predictions = write_prediction_state(predictions)
if len(predictions) != len(benchmark_inputs):
    print(f"Benchmark incomplete: {len(predictions)}/{len(benchmark_inputs)}")
else:
    # The sealed key is loaded only after all model predictions have been saved.
    gold_rows = read_jsonl(BENCHMARK_GOLD)
    gold_by_id = {row["case_id"]: row for row in gold_rows}
    if set(gold_by_id) != {row["case_id"] for row in benchmark_inputs}:
        raise ValueError("Sealed answer key IDs do not match benchmark inputs")

    recommendable_ids = {
        provision_id for provision_id, row in RAG_V2_CATALOGUE.items()
        if row.get("recommendable") and row.get("legal_status") == "in_force"
        and row.get("provision_kind") == "offence"
    }

    def percentile(values, fraction):
        values = sorted(values)
        if not values:
            return None
        position = (len(values) - 1) * fraction
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return values[lower]
        return values[lower] + (values[upper] - values[lower]) * (position - lower)

    def score_variant(name, output_getter):
        detail = []
        strict_tp = strict_fp = strict_fn = 0
        tolerant_good_predictions = tolerant_predictions = 0
        required_found = required_total = 0
        outcome_correct = 0
        exact_all = exact_positive = acceptable_positive = 0
        positive_count = 0
        invalid_ids = []
        false_positive_sections = Counter()
        missed_sections = Counter()
        per_provision = defaultdict(lambda: {"required": 0, "found": 0})
        group_stats = defaultdict(lambda: {"cases": 0, "outcome_correct": 0,
                                            "strict_exact": 0, "acceptable": 0})
        language_stats = defaultdict(lambda: {"cases": 0, "outcome_correct": 0,
                                               "strict_exact": 0, "acceptable": 0})
        missing_target_total = missing_target_found = 0
        out_scope_total = out_scope_false_positive = 0

        for prediction in predictions:
            gold = gold_by_id[prediction["case_id"]]
            output = output_getter(prediction)
            if not isinstance(output, dict):
                output = {}
            predicted = {item for item in output.get("possible_provision_ids", [])
                         if isinstance(item, str)}
            required = set(gold["required_provision_ids"])
            optional = set(gold["optional_provision_ids"])
            allowed = required | optional
            expected_outcome = gold["outcome"]
            actual_outcome = output.get("outcome")
            outcome_ok = actual_outcome == expected_outcome
            outcome_correct += int(outcome_ok)
            if expected_outcome == "out_of_scope":
                out_scope_total += 1
                out_scope_false_positive += int(actual_outcome == "provision_match" or bool(predicted))

            strict_set_ok = predicted == required
            exact_case = outcome_ok and strict_set_ok
            acceptable = outcome_ok and required.issubset(predicted) and predicted.issubset(allowed)
            exact_all += int(exact_case)
            if expected_outcome == "provision_match":
                positive_count += 1
                exact_positive += int(exact_case)
                acceptable_positive += int(acceptable)
                strict_tp += len(predicted & required)
                strict_fp += len(predicted - required)
                strict_fn += len(required - predicted)
                tolerant_good_predictions += len(predicted & allowed)
                tolerant_predictions += len(predicted)
                required_found += len(predicted & required)
                required_total += len(required)
                for provision_id in required:
                    per_provision[provision_id]["required"] += 1
                    per_provision[provision_id]["found"] += int(provision_id in predicted)
                false_positive_sections.update(predicted - allowed)
                missed_sections.update(required - predicted)

            uncertain_ids = {
                item.get("provision_id") for item in output.get("uncertain_sections", [])
                if isinstance(item, dict)
            }
            expected_uncertain = set(gold["required_uncertain_ids"])
            if expected_uncertain:
                missing_target_total += 1
                missing_target_found += int(bool(uncertain_ids & expected_uncertain))

            invalid = sorted(predicted - recommendable_ids)
            if invalid:
                invalid_ids.append({"case_id": prediction["case_id"], "ids": invalid})
            row = {
                "case_id": prediction["case_id"], "expected_outcome": expected_outcome,
                "actual_outcome": actual_outcome, "required": sorted(required),
                "optional": sorted(optional), "predicted": sorted(predicted),
                "outcome_correct": outcome_ok, "strict_exact": exact_case,
                "acceptable": acceptable,
            }
            detail.append(row)
            for bucket, key in ((group_stats, prediction["group"]),
                                (language_stats, prediction["language"])):
                bucket[key]["cases"] += 1
                bucket[key]["outcome_correct"] += int(outcome_ok)
                bucket[key]["strict_exact"] += int(exact_case)
                bucket[key]["acceptable"] += int(acceptable)

        strict_precision = strict_tp / (strict_tp + strict_fp) if strict_tp + strict_fp else 1.0
        strict_recall = strict_tp / (strict_tp + strict_fn) if strict_tp + strict_fn else 1.0
        strict_f1 = (2 * strict_precision * strict_recall / (strict_precision + strict_recall)
                     if strict_precision + strict_recall else 0.0)
        tolerant_precision = (tolerant_good_predictions / tolerant_predictions
                              if tolerant_predictions else 1.0)

        def finalise_buckets(buckets):
            result = {}
            for key, value in sorted(buckets.items()):
                count = value["cases"]
                result[key] = {
                    **value,
                    "outcome_accuracy": value["outcome_correct"] / count,
                    "strict_exact_accuracy": value["strict_exact"] / count,
                    "acceptable_accuracy": value["acceptable"] / count,
                }
            return result

        return {
            "name": name,
            "cases": len(predictions),
            "positive_cases": positive_count,
            "outcome_accuracy": outcome_correct / len(predictions),
            "strict_exact_all_case_accuracy": exact_all / len(predictions),
            "strict_exact_positive_section_accuracy": exact_positive / positive_count,
            "acceptable_positive_section_accuracy": acceptable_positive / positive_count,
            "strict_section_precision": strict_precision,
            "tolerant_section_precision": tolerant_precision,
            "required_section_recall": required_found / required_total,
            "strict_section_f1": strict_f1,
            "missing_question_target_accuracy": (missing_target_found / missing_target_total
                                                 if missing_target_total else None),
            "out_of_scope_false_positive_rate": (out_scope_false_positive / out_scope_total
                                                  if out_scope_total else None),
            "invalid_provision_id_count": sum(len(row["ids"]) for row in invalid_ids),
            "invalid_provision_ids": invalid_ids,
            "false_positive_sections": dict(false_positive_sections.most_common()),
            "missed_sections": dict(missed_sections.most_common()),
            "per_provision_recall": {
                provision_id: {
                    **counts,
                    "recall": counts["found"] / counts["required"],
                }
                for provision_id, counts in sorted(per_provision.items())
            },
            "by_group": finalise_buckets(group_stats),
            "by_language": finalise_buckets(language_stats),
            "case_results": detail,
        }

    lora_metrics = score_variant(
        "lora_only", lambda prediction: prediction["lora_only"].get("parsed")
    )
    rag_metrics = score_variant(
        "rag_v2_2", lambda prediction: prediction["rag_v2_2"]["final_output"]
    )

    retrieval_required = retrieval_found = retrieval_all_case = retrieval_case_total = 0
    candidate_schema_errors = 0
    final_validation_errors = 0
    for prediction in predictions:
        gold = gold_by_id[prediction["case_id"]]
        required = set(gold["required_provision_ids"])
        if required:
            retrieved = set(prediction["retrieved_provision_ids"])
            retrieval_required += len(required)
            retrieval_found += len(required & retrieved)
            retrieval_case_total += 1
            retrieval_all_case += int(required.issubset(retrieved))
        candidate_schema_errors += sum(
            not item.get("schema_valid") for item in prediction["candidate_assessments"]
        )
        final_validation_errors += int(
            not prediction["rag_v2_2"]["final_validation"].get("valid")
        )

    latencies = [prediction["latency_seconds"] for prediction in predictions]
    retrieval_recall = retrieval_found / retrieval_required if retrieval_required else 1.0
    retrieval_all_case_accuracy = (retrieval_all_case / retrieval_case_total
                                   if retrieval_case_total else 1.0)
    gates = {
        "output_structure_100_percent": final_validation_errors == 0,
        "invalid_provision_ids_zero": rag_metrics["invalid_provision_id_count"] == 0,
        "outcome_accuracy_at_least_0_90": rag_metrics["outcome_accuracy"] >= 0.90,
        "strict_exact_positive_at_least_0_80": (
            rag_metrics["strict_exact_positive_section_accuracy"] >= 0.80
        ),
        "strict_precision_at_least_0_90": rag_metrics["strict_section_precision"] >= 0.90,
        "required_recall_at_least_0_80": rag_metrics["required_section_recall"] >= 0.80,
        "retrieval_recall_at_least_0_95": retrieval_recall >= 0.95,
        "out_of_scope_false_positive_at_most_0_05": (
            rag_metrics["out_of_scope_false_positive_rate"] <= 0.05
        ),
    }
    report = {
        "schema_version": 1,
        "benchmark_version": BENCHMARK_VERSION,
        "rag_version": RAG_V2_2_VERSION,
        "adapter_sha256": v2_1_payload["adapter_sha256"],
        "benchmark_manifest_sha256": file_sha256(BENCHMARK_MANIFEST),
        "answer_key_sha256": benchmark_manifest["files_sha256"]["sealed_answer_key.jsonl"],
        "note": "Scores measure agreement with an AI-reviewed statutory answer key, not lawyer-verified accuracy.",
        "lora_only": lora_metrics,
        "rag_v2_2": rag_metrics,
        "retrieval": {
            "required_section_recall_at_6": retrieval_recall,
            "all_required_retrieved_case_accuracy": retrieval_all_case_accuracy,
            "required_sections": retrieval_required,
            "required_sections_found": retrieval_found,
        },
        "reliability": {
            "candidate_schema_error_count": candidate_schema_errors,
            "final_validation_error_count": final_validation_errors,
        },
        "latency_seconds": {
            "mean": statistics.mean(latencies),
            "median": statistics.median(latencies),
            "p95": percentile(latencies, 0.95),
            "minimum": min(latencies),
            "maximum": max(latencies),
            "total": sum(latencies),
        },
        "release_gates": gates,
        "all_release_gates_passed": all(gates.values()),
    }
    temporary = BENCHMARK_REPORT.with_suffix(".json.part")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, BENCHMARK_REPORT)

    display(Markdown("# Sealed RAG v2.2 benchmark results"))
    display(DisplayJSON({
        "lora_only": {key: value for key, value in lora_metrics.items()
                      if key not in {"case_results", "per_provision_recall", "by_group", "by_language"}},
        "rag_v2_2": {key: value for key, value in rag_metrics.items()
                     if key not in {"case_results", "per_provision_recall", "by_group", "by_language"}},
        "retrieval": report["retrieval"],
        "reliability": report["reliability"],
        "latency_seconds": report["latency_seconds"],
        "release_gates": gates,
        "all_release_gates_passed": report["all_release_gates_passed"],
        "report_file": str(BENCHMARK_REPORT),
    }, expanded=True))
    print("Attach or sync sealed_rag_benchmark_v1_report.json for analysis.")
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
    if not any("RAG V2.2: STATUTORY-EVIDENCE GATE" in "".join(cell.get("source", []))
               for cell in cells):
        raise ValueError("Source notebook does not contain RAG v2.2")
    cells.extend([
        markdown("""# Independent sealed benchmark

This cell evaluates the frozen RAG v2.2 system on 150 complaints that were checked for separation from the training, development, old sealed and previous 21-case sets. The answer key is never included in a model prompt and is loaded only after every prediction is saved.

The run saves after every complaint. If Colab disconnects, mount the same `LegalAI` folder and choose **Run all** again. Completed cases are skipped.
""", "legalai-sealed-rag-benchmark-v1-intro"),
        code(BENCHMARK_CODE, "legalai-sealed-rag-benchmark-v1-run"),
    ])
    notebook["cells"] = cells
    notebook.get("metadata", {}).pop("widgets", None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
