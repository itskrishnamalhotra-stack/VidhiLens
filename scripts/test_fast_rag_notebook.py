"""Static checks for the single-call fast grounded RAG notebook."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "archive" / "research_notebooks" / "Krishna_RAG_v2_2_Sealed_Benchmark.ipynb"
OUTPUT = ROOT / "archive" / "research_notebooks" / "Krishna_RAG_Fast_Regression.ipynb"

source = json.loads(SOURCE.read_text(encoding="utf-8"))
notebook = json.loads(OUTPUT.read_text(encoding="utf-8"))
assert len(notebook["cells"]) == len(source["cells"]) + 5
assert notebook["metadata"]["accelerator"] == "GPU"
assert notebook["metadata"]["colab"]["gpuType"] == "T4"

tags = []
for index, cell in enumerate(notebook["cells"]):
    tags.extend(cell.get("metadata", {}).get("tags", []))
    if cell["cell_type"] == "code":
        compile("".join(cell["source"]), f"fast-notebook-cell-{index}", "exec")

required_tags = {
    "legalai-fast-rag-intro",
    "legalai-fast-rag-core",
    "legalai-fast-rag-setup",
    "legalai-fast-rag-regression",
    "legalai-fast-rag-interactive",
}
assert required_tags.issubset(tags)

all_source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
for required in (
    'ASSESSMENT_MODE = "single_joint_candidate_call"',
    "def generate_joint_assessment",
    "def run_improved_pipeline",
    'description="Run fast RAG"',
    "rag_fast_regression_predictions.json",
    "rag_fast_regression_report.json",
    "interactive_rag_fast_tests.jsonl",
    "completed_assessments=prior_assessments",
):
    assert required in all_source

assert "run_fast_pipeline" not in all_source

# This archived experiment may differ from the later production core. Check
# its own saved source and syntax without comparing it to today's script.
core_cell = next(
    cell for cell in notebook["cells"]
    if "legalai-fast-rag-core" in cell.get("metadata", {}).get("tags", [])
)
assert "PIPELINE_ID = \"multilingual_grounded_rag_2026_09\"" in "".join(core_cell["source"])
assert "def normalise_text" in "".join(core_cell["source"])

print("Fast RAG notebook checks passed")
