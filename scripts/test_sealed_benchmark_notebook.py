"""Non-GPU integrity and scoring checks for the sealed benchmark notebook."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(r"E:\term paper project")
SOURCE = ROOT / "phase1/archive/research_notebooks/Krishna_Train_RAG_v2_2.ipynb"
OUTPUT = ROOT / "phase1/archive/research_notebooks/Krishna_RAG_v2_2_Sealed_Benchmark.ipynb"
BENCHMARK = ROOT / "phase1/evaluation/sealed_rag_benchmark_v1"

source_notebook = json.loads(SOURCE.read_text(encoding="utf-8"))
output_notebook = json.loads(OUTPUT.read_text(encoding="utf-8"))
assert len(source_notebook["cells"]) == 15
assert len(output_notebook["cells"]) == 17
for index, cell in enumerate(source_notebook["cells"]):
    assert output_notebook["cells"][index]["cell_type"] == cell["cell_type"]
    assert output_notebook["cells"][index]["source"] == cell["source"]
for index, cell in enumerate(output_notebook["cells"]):
    if cell["cell_type"] == "code":
        compile("".join(cell["source"]), f"sealed-notebook-cell-{index}", "exec")

manifest = json.loads((BENCHMARK / "manifest.json").read_text(encoding="utf-8"))
assert manifest["counts"]["total"] == 150
assert manifest["counts"]["groups"] == {
    "single_provision": 76,
    "multi_provision": 24,
    "missing_information": 25,
    "out_of_scope": 25,
}
assert manifest["scope"]["provision_count"] == 19
assert manifest["separation"]["exact_overlap_count"] == 0
assert manifest["separation"]["maximum_token_jaccard"] < manifest["separation"]["threshold"]
for filename, expected in manifest["files_sha256"].items():
    assert hashlib.sha256((BENCHMARK / filename).read_bytes()).hexdigest() == expected

inputs = [json.loads(line) for line in (BENCHMARK / "benchmark_inputs.jsonl").read_text(
    encoding="utf-8").splitlines()]
gold = [json.loads(line) for line in (BENCHMARK / "sealed_answer_key.jsonl").read_text(
    encoding="utf-8").splitlines()]
assert len(inputs) == len(gold) == 150
assert [row["case_id"] for row in inputs] == [row["case_id"] for row in gold]
assert all("required_provision_ids" not in row for row in inputs)

# Execute the exact benchmark cell against perfect synthetic predictions. This
# checks resume identity, scoring math, report generation and every release gate.
ipython_module = types.ModuleType("IPython")
display_module = types.ModuleType("IPython.display")
display_module.display = lambda *args, **kwargs: None
display_module.Markdown = lambda value: value
display_module.JSON = lambda value, **kwargs: value
sys.modules.setdefault("IPython", ipython_module)
sys.modules.setdefault("IPython.display", display_module)

with tempfile.TemporaryDirectory() as temporary_directory:
    project = Path(temporary_directory)
    shutil.copytree(BENCHMARK, project / "sealed_rag_benchmark_v1")
    gold_by_id = {row["case_id"]: row for row in gold}
    predictions = []
    for case in inputs:
        answer = gold_by_id[case["case_id"]]
        uncertain = [
            {"provision_id": provision_id, "missing_facts": "A material fact is absent."}
            for provision_id in answer["required_uncertain_ids"]
        ]
        final = {
            "outcome": answer["outcome"],
            "possible_provision_ids": answer["required_provision_ids"],
            "uncertain_sections": uncertain,
        }
        predictions.append({
            **case,
            "lora_only": {"raw": json.dumps(final), "parsed": final},
            "retrieved_provision_ids": answer["required_provision_ids"],
            "context_provision_ids": [],
            "candidate_assessments": [],
            "blocked_supported_candidates": [],
            "rag_v2_2": {
                "evidence_gate_actions": [], "assembly_rule": "synthetic_test",
                "final_output": final, "final_validation": {"valid": True, "errors": []},
            },
            "latency_seconds": 1.0,
        })
    prediction_payload = {
        "schema_version": 1,
        "benchmark_version": "sealed_rag_benchmark_v1",
        "rag_version": "statutory_evidence_gate_v2_2",
        "adapter_sha256": "synthetic-adapter",
        "input_sha256": manifest["files_sha256"]["benchmark_inputs.jsonl"],
        "total_cases": 150,
        "completed_cases": 150,
        "in_progress": None,
        "predictions": predictions,
    }
    (project / "sealed_rag_benchmark_v1_predictions.json").write_text(
        json.dumps(prediction_payload), encoding="utf-8"
    )
    catalogue = {
        provision_id: {
            "recommendable": True, "legal_status": "in_force", "provision_kind": "offence"
        }
        for provision_id in manifest["scope"]["recommendation_approved_provisions"]
    }
    namespace = {
        "PROJECT": project,
        "RAG_V2_2_VERSION": "statutory_evidence_gate_v2_2",
        "v2_1_payload": {"adapter_sha256": "synthetic-adapter"},
        "RAG_V2_CATALOGUE": catalogue,
    }
    benchmark_code = "".join(output_notebook["cells"][16]["source"])
    exec(compile(benchmark_code, "sealed-benchmark-cell", "exec"), namespace)
    report = json.loads((project / "sealed_rag_benchmark_v1_report.json").read_text(
        encoding="utf-8"))
    assert report["all_release_gates_passed"] is True
    assert report["rag_v2_2"]["outcome_accuracy"] == 1.0
    assert report["rag_v2_2"]["strict_exact_positive_section_accuracy"] == 1.0
    assert report["retrieval"]["required_section_recall_at_6"] == 1.0
    namespace["CANDIDATE_SYSTEM_PROMPT"] = "candidate-system"
    namespace["CANDIDATE_FEW_SHOTS"] = [
        ({"example": index}, {"decision": "supported"}) for index in range(4)
    ]
    messages = namespace["benchmark_candidate_messages"](
        "reported incident",
        {
            "provision_id": "BNS_303", "title": "Theft",
            "verified_text": "Verified theft text", "recommendable": True,
            "retrieval_score": 1.0,
        },
        [{
            "provision_id": "ITA_43", "title": "Computer access",
            "legal_status": "in_force", "provision_kind": "civil_contravention",
            "verified_text": "Verified context text",
        }],
        {"outcome": "provision_match", "possible_provision_ids": ["BNS_303"]},
    )
    assert len(messages) == 10  # system + four user/assistant examples + live user
    live_payload = json.loads(messages[-1]["content"])
    assert live_payload["reported_incident"] == "reported incident"
    assert live_payload["candidate_provision"]["provision_id"] == "BNS_303"
    assert live_payload["lora_triage_prior"]["outcome"] == "provision_match"

print("Sealed benchmark notebook checks passed")
