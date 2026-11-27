"""Local, non-GPU checks for the generated RAG v2.1 notebook."""
from __future__ import annotations

import ast
import json
import math
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(r"E:\term paper project")
SOURCE = ROOT / "phase1/colab/Krishna_Train_Resume.ipynb"
OUTPUT = ROOT / "phase1/archive/research_notebooks/Krishna_Train_RAG_v2_1.ipynb"


source_notebook = json.loads(SOURCE.read_text(encoding="utf-8"))
output_notebook = json.loads(OUTPUT.read_text(encoding="utf-8"))
assert len(source_notebook["cells"]) == 7
assert len(output_notebook["cells"]) == 11
for index, source_cell in enumerate(source_notebook["cells"]):
    output_cell = output_notebook["cells"][index]
    assert output_cell["cell_type"] == source_cell["cell_type"]
    assert output_cell["source"] == source_cell["source"]

for index, cell in enumerate(output_notebook["cells"]):
    if cell["cell_type"] == "code":
        compile("".join(cell["source"]), f"notebook-cell-{index}", "exec")

rag_source = "".join(output_notebook["cells"][8]["source"])
tree = ast.parse(rag_source)
namespace = {
    "json": json,
    "math": math,
    "re": re,
    "Counter": Counter,
}
wanted_assignments = {
    "CANDIDATE_SYSTEM_PROMPT",
    "CANDIDATE_FEW_SHOTS",
    "QUERY_EXPANSIONS",
    "RETRIEVAL_ANCHORS",
    "RAG_V2_MAX_OFFENCE_CANDIDATES",
    "RAG_V2_MAX_CONTEXT_CANDIDATES",
    "RAG_V2_MIN_BM25_SCORE",
}
for node in tree.body:
    if isinstance(node, ast.Assign):
        names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if names & wanted_assignments:
            exec(compile(ast.Module([node], []), "selected-assignment", "exec"), namespace)
    elif isinstance(node, ast.FunctionDef):
        exec(compile(ast.Module([node], []), "selected-function", "exec"), namespace)

assert "not a trial" in namespace["CANDIDATE_SYSTEM_PROMPT"]
assert len(namespace["CANDIDATE_FEW_SHOTS"]) == 4

catalogue_payload = json.loads(
    (ROOT / "phase1/exports/rag_catalogue_v1.json").read_text(encoding="utf-8")
)
rows = catalogue_payload["provisions"]
namespace["RAG_V2_ROWS"] = rows
namespace["RAG_V2_CATALOGUE"] = {row["provision_id"]: row for row in rows}
namespace["RAG_V2_INDEX"] = {row["provision_id"]: index for index, row in enumerate(rows)}
namespace["RAG_V2_TITLE_TOKENS"] = [
    set(namespace["rag_v2_tokens"](row.get("title", ""))) for row in rows
]
namespace["RAG_V2_DOCUMENT_TOKENS"] = [
    namespace["rag_v2_tokens"]((row.get("title", "") + " ") * 3 + row.get("verified_text", ""))
    for row in rows
]
namespace["RAG_V2_DF"] = Counter()
for tokens in namespace["RAG_V2_DOCUMENT_TOKENS"]:
    namespace["RAG_V2_DF"].update(set(tokens))
namespace["RAG_V2_DOCUMENT_COUNT"] = len(rows)
namespace["RAG_V2_AVERAGE_LENGTH"] = sum(
    map(len, namespace["RAG_V2_DOCUMENT_TOKENS"])
) / len(rows)

retrieval_checks = [
    ("A caller pretended to be my bank, obtained my OTP and transferred money.", "ITA_66D"),
    ("Someone accessed my email without permission, changed the password and downloaded files.", "ITA_66"),
    ("An online seller took payment, blocked me, deleted the ad and never delivered.", "BNS_318"),
    ("He hit me with an iron rod and the doctor confirmed a fracture.", "BNS_117"),
]
for complaint, expected_id in retrieval_checks:
    retrieval = namespace["retrieve_rag_v2"](
        complaint, {"outcome": "provision_match", "possible_provision_ids": []}
    )
    retrieved_ids = {row["provision_id"] for row in retrieval["offence_candidates"]}
    assert expected_id in retrieved_ids, (complaint, expected_id, retrieved_ids)

validate = namespace["validate_candidate_assessment"]
assert not validate({
    "provision_id": "ITA_66D", "decision": "supported",
    "missing_facts": [], "reason": "The stated conduct supports it."
}, "ITA_66D")
assert "missing_facts contains more than two questions" in validate({
    "provision_id": "ITA_66D", "decision": "missing_facts",
    "missing_facts": ["one?", "two?", "three?"], "reason": "Facts absent."
}, "ITA_66D")

namespace["RAG_V2_CATALOGUE"] = {
    provision_id: {
        "provision_id": provision_id,
        "recommendable": True,
        "legal_status": "in_force",
        "provision_kind": "offence",
    }
    for provision_id in ["BNS_115", "BNS_117", "BNS_318", "ITA_66", "ITA_66D"]
}


def supported(provision_id: str) -> dict:
    return {
        "provision_id": provision_id,
        "title": provision_id,
        "recommendable": True,
        "schema_valid": True,
        "parsed_assessment": {
            "provision_id": provision_id,
            "decision": "supported",
            "missing_facts": [],
            "reason": "Supported by the reported facts.",
        },
    }


assemble = namespace["assemble_rag_v2"]
final, _, _ = assemble(
    {"outcome": "provision_match", "possible_provision_ids": ["BNS_115", "BNS_117"]},
    {}, [supported("BNS_115"), supported("BNS_117")]
)
assert final["possible_provision_ids"] == ["BNS_117"]

final, _, _ = assemble(
    {"outcome": "provision_match", "possible_provision_ids": ["ITA_66", "ITA_66D"]},
    {}, [supported("ITA_66"), supported("ITA_66D")]
)
assert final["possible_provision_ids"] == ["ITA_66D"]

final, _, rule = assemble(
    {"outcome": "insufficient_information", "possible_provision_ids": []},
    {}, [supported("BNS_318")]
)
assert final["outcome"] == "provision_match"
assert final["possible_provision_ids"] == ["BNS_318"]
assert rule == "grounded_candidates_upgraded_incomplete_triage"

captured = {}


def fake_generate(messages, max_new_tokens, use_adapter):
    captured["messages"] = messages
    captured["use_adapter"] = use_adapter
    return json.dumps({
        "provision_id": "ITA_66D", "decision": "supported",
        "missing_facts": [], "reason": "The reported conduct supports possible personation."
    })


namespace["generate_messages"] = fake_generate
namespace["train_runner"] = SimpleNamespace(parse_json=json.loads)
assessment = namespace["assess_one_candidate"](
    "A caller pretended to be my bank and obtained my OTP.",
    {
        "provision_id": "ITA_66D", "title": "Personation",
        "verified_text": "Cheating by personation using a communication device.",
        "recommendable": True, "retrieval_score": 99.0,
    },
    [],
    {"outcome": "provision_match", "possible_provision_ids": ["ITA_66D"]},
)
assert assessment["schema_valid"]
assert captured["use_adapter"] is False
assert len(captured["messages"]) == 10  # system + four examples + live request
assert "lora_triage_prior" in json.loads(captured["messages"][-1]["content"])

print("RAG v2.1 notebook checks passed")
