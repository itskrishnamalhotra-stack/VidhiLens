"""Run the exact RAG v2.2 notebook postprocessor locally without loading a model."""
from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path


ROOT = Path(r"E:\term paper project")
PROJECT = ROOT / "phase1/exports"
NOTEBOOK = ROOT / "phase1/archive/research_notebooks/Krishna_Train_RAG_v2_2.ipynb"
CATALOGUE = PROJECT / "rag_catalogue_v1.json"
V21_RESULT = PROJECT / "rag_v2_1_comparison_results.json"

notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
v21_payload = json.loads(V21_RESULT.read_text(encoding="utf-8"))
catalogue_payload = json.loads(CATALOGUE.read_text(encoding="utf-8"))

namespace = {
    "PROJECT": PROJECT,
    "TEST_CASES": [
        {"case_id": row["case_id"], "complaint": row["complaint"]}
        for row in v21_payload["comparisons"]
    ],
    "RAG_V2_CATALOGUE": {
        row["provision_id"]: row for row in catalogue_payload["provisions"]
    },
}

# The notebook displays a summary through IPython. Supply harmless local stubs
# so the exact batch cell can run in the project's lightweight Python runtime.
ipython_module = types.ModuleType("IPython")
display_module = types.ModuleType("IPython.display")
display_module.display = lambda *args, **kwargs: None
display_module.Markdown = lambda value: value
display_module.JSON = lambda value, **kwargs: value
sys.modules.setdefault("IPython", ipython_module)
sys.modules.setdefault("IPython.display", display_module)

# Use the exact final-output validator embedded in the notebook.
rag_v21_source = "".join(notebook["cells"][8]["source"])
rag_v21_tree = ast.parse(rag_v21_source)
for node in rag_v21_tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == "validate_final_rag_v2":
        exec(compile(ast.Module([node], []), "v2.1-validator", "exec"), namespace)
        break
else:
    raise RuntimeError("validate_final_rag_v2 was not found")

# Execute the exact v2.2 batch cell. It performs no model calls.
v22_source = "".join(notebook["cells"][12]["source"])
exec(compile(v22_source, "rag-v2.2-batch-cell", "exec"), namespace)

output = PROJECT / "rag_v2_2_comparison_results.json"
payload = json.loads(output.read_text(encoding="utf-8"))
assert payload["completed_test_cases"] == 21
assert all(row["rag_v2_2"]["final_validation"]["valid"] for row in payload["comparisons"])
print(output)
