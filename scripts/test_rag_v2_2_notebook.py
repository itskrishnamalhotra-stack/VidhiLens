"""Local, non-GPU checks for RAG v2.2 evidence gating."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path


ROOT = Path(r"E:\term paper project")
V21 = ROOT / "phase1/archive/research_notebooks/Krishna_Train_RAG_v2_1.ipynb"
V22 = ROOT / "phase1/archive/research_notebooks/Krishna_Train_RAG_v2_2.ipynb"
RESULT = ROOT / "phase1/exports/rag_v2_1_comparison_results.json"

v21 = json.loads(V21.read_text(encoding="utf-8"))
v22 = json.loads(V22.read_text(encoding="utf-8"))
assert len(v21["cells"]) == 11
assert len(v22["cells"]) == 15
for index, source_cell in enumerate(v21["cells"][:10]):
    assert v22["cells"][index]["cell_type"] == source_cell["cell_type"]
    assert v22["cells"][index]["source"] == source_cell["source"]
interactive_source = "".join(v22["cells"][10]["source"])
assert "ensure_rag_v2_model_loaded()\n\nv2_complaint_input" not in interactive_source
assert "try:\n            ensure_rag_v2_model_loaded()\n            print(\"Running LoRA triage...\")" in interactive_source
for index, cell in enumerate(v22["cells"]):
    if cell["cell_type"] == "code":
        compile("".join(cell["source"]), f"v2.2-cell-{index}", "exec")

source = "".join(v22["cells"][12]["source"])
tree = ast.parse(source)
namespace = {"re": re}
for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        exec(compile(ast.Module([node], []), "v2.2-function", "exec"), namespace)

postprocess = namespace["postprocess_rag_v2_2"]
payload = json.loads(RESULT.read_text(encoding="utf-8"))
by_id = {row["case_id"]: row for row in payload["comparisons"]}


def final_for(case_id: str):
    row = by_id[case_id]
    return postprocess(
        row["complaint"], row["lora_only"], row["rag_v2"]["candidate_assessments"],
        row["rag_v2"].get("blocked_supported_candidates", [])
    )


final, actions, _ = final_for("TEST_001")
assert final["possible_provision_ids"] == ["BNS_303"]
assert any(item["provision_id"] == "BNS_304" for item in actions)

final, actions, _ = final_for("TEST_015")
assert final["possible_provision_ids"] == ["BNS_316"]
assert any(item["provision_id"] == "BNS_303" for item in actions)

final, actions, _ = final_for("TEST_008")
assert final["possible_provision_ids"] == ["ITA_66"]
assert any(item["provision_id"] == "ITA_66C" for item in actions)

for case_id in ("TEST_005", "TEST_009"):
    final, actions, _ = final_for(case_id)
    assert final["possible_provision_ids"] == ["BNS_77"]
    assert any(item["provision_id"] == "ITA_67A" for item in actions)

for case_id in ("TEST_007", "TEST_018"):
    final, actions, _ = final_for(case_id)
    assert "ITA_66C" in final["possible_provision_ids"]

for case_id in ("TEST_019", "TEST_020", "TEST_021"):
    final, _, _ = final_for(case_id)
    assert final == {"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}

print("RAG v2.2 notebook checks passed")
