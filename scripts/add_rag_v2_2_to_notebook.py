"""Append a deterministic statutory-evidence gate to Krishna's RAG v2.1 notebook."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


TAG_PREFIX = "legalai-rag-v2-2-"


def markdown(source: str, tag: str) -> dict:
    return {"cell_type": "markdown", "metadata": {"tags": [tag]},
            "source": source.splitlines(keepends=True)}


def code(source: str, tag: str) -> dict:
    return {"cell_type": "code", "execution_count": None,
            "metadata": {"tags": [tag]}, "outputs": [],
            "source": source.splitlines(keepends=True)}


RAG_V2_2_CODE = r'''# ============================================================
# RAG V2.2: STATUTORY-EVIDENCE GATE OVER COMPLETED V2.1 RESULTS
# ============================================================

import copy
import json
import os
import re
from collections import Counter
from pathlib import Path
from IPython.display import display, Markdown, JSON as DisplayJSON

RAG_V2_2_VERSION = "statutory_evidence_gate_v2_2"
RAG_V2_1_RESULT_PATH = PROJECT / "rag_v2_1_comparison_results.json"
RAG_V2_2_RESULT_PATH = PROJECT / "rag_v2_2_comparison_results.json"


def phrase_present(text, patterns):
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def postprocess_rag_v2_2(complaint, triage, assessments, blocked_supported=None):
    """Apply general statutory element checks to recommendation-approved candidates.

    These checks encode distinguishing facts from the statute. They do not encode
    case IDs or expected benchmark answers.
    """
    if isinstance(triage, dict) and triage.get("outcome") == "out_of_scope":
        return {
            "outcome": "out_of_scope",
            "possible_provision_ids": [],
            "uncertain_sections": [],
        }, [], "triage_out_of_scope_guard"

    supported = []
    missing = []
    for item in assessments:
        parsed = item.get("parsed_assessment")
        if not item.get("schema_valid") or not item.get("recommendable") or not isinstance(parsed, dict):
            continue
        if parsed.get("decision") == "supported":
            supported.append(item)
        elif parsed.get("decision") == "missing_facts":
            missing.append(item)

    supported_ids = {item["provision_id"] for item in supported}
    actions = []
    downgraded_questions = {}

    snatching_facts = phrase_present(complaint, (
        r"\bsnatch", r"\bgrab", r"\bseiz", r"\bforc", r"\bsudden",
        r"\bquickly\b", r"\byank", r"\bwrest", r"\bpull(?:ed|s|ing)?\b.{0,30}\b(hand|neck|shoulder|person)\b",
    ))
    if "BNS_304" in supported_ids and "BNS_303" in supported_ids and not snatching_facts:
        supported_ids.remove("BNS_304")
        actions.append({
            "provision_id": "BNS_304", "action": "removed",
            "reason": "The complaint states theft but no sudden, quick, forcible, seizure or grabbing fact required to distinguish snatching."
        })

    entrustment_facts = phrase_present(complaint, (
        r"\bentrust", r"\bgave\b.{0,50}\b(repair|return|keep|hold|store)",
        r"\bhanded\b.{0,50}\b(repair|return|keep|hold|store)",
        r"\bfor repairs?\b", r"\brepair[- ]shop", r"\bdeposited\b", r"\bloaned\b",
    ))
    conversion_after_entrustment = phrase_present(complaint, (
        r"\bsold\b", r"\bkept the money\b", r"\brefused to return\b",
        r"\bconverted\b", r"\bpawned\b", r"\bdisposed\b",
    ))
    if ("BNS_303" in supported_ids and "BNS_316" in supported_ids and
            entrustment_facts and conversion_after_entrustment):
        supported_ids.remove("BNS_303")
        actions.append({
            "provision_id": "BNS_303", "action": "removed",
            "reason": "The property was voluntarily entrusted before its alleged dishonest disposal; BNS 316 is the grounded provision."
        })

    explicit_identity_use = phrase_present(complaint, (
        r"\b(us(?:e|ed|ing)|obtain(?:ed|ing)|stole|stolen|misus(?:e|ed|ing))\b.{0,35}\b(password|otp|credential|electronic signature|aadhaar|biometric)",
        r"\b(us(?:e|ed|ing)|stole|stolen|misus(?:e|ed|ing))\b.{0,25}\b(my|his|her|their)\b.{0,20}\b(identity|name|photograph|photo)",
        r"\bfake profile\b.{0,50}\b(my|his|her|their)\b.{0,20}\b(identity|name|photograph|photo)",
    ))
    if "ITA_66C" in supported_ids and not explicit_identity_use:
        supported_ids.remove("ITA_66C")
        downgraded_questions["ITA_66C"] = (
            "Did the person fraudulently use your password, electronic signature, or another unique identification feature?"
        )
        actions.append({
            "provision_id": "ITA_66C", "action": "downgraded_to_uncertain",
            "reason": "Unauthorised access alone does not state use of another person's password or unique identification feature."
        })

    explicit_sexual_conduct = phrase_present(complaint, (
        r"\bsexually explicit\b", r"\bsexual act\b", r"\bhaving sex\b",
        r"\bintercourse\b", r"\bnude\b", r"\bnaked\b", r"\bgenitals?\b",
        r"\bporn(?:ographic|ography)?\b",
    ))
    if "ITA_67A" in supported_ids and not explicit_sexual_conduct:
        supported_ids.remove("ITA_67A")
        downgraded_questions["ITA_67A"] = (
            "Did the transmitted material contain a sexually explicit act or conduct?"
        )
        actions.append({
            "provision_id": "ITA_67A", "action": "downgraded_to_uncertain",
            "reason": "Private or intimate material is not automatically material containing a sexually explicit act or conduct."
        })

    specificity = {
        "BNS_115": {"BNS_117"},
        "BNS_314": {"BNS_316"},
        "BNS_318": {"BNS_319"},
    }
    for general_id, specific_ids in specificity.items():
        if general_id in supported_ids and supported_ids & specific_ids:
            supported_ids.remove(general_id)
            actions.append({
                "provision_id": general_id, "action": "removed",
                "reason": "A supported, recommendation-approved more specific provision is present."
            })

    ordered_supported = [
        item["provision_id"] for item in supported
        if item["provision_id"] in supported_ids
    ]
    ordered_supported = list(dict.fromkeys(ordered_supported))

    uncertain = []
    uncertain_ids = set()
    for item in missing:
        provision_id = item["provision_id"]
        if provision_id in supported_ids or provision_id in uncertain_ids:
            continue
        questions = item["parsed_assessment"].get("missing_facts", [])[:2]
        if questions:
            uncertain.append({"provision_id": provision_id, "missing_facts": "; ".join(questions)})
            uncertain_ids.add(provision_id)
    for provision_id, question in downgraded_questions.items():
        if provision_id not in supported_ids and provision_id not in uncertain_ids:
            uncertain.append({"provision_id": provision_id, "missing_facts": question})
            uncertain_ids.add(provision_id)

    if ordered_supported:
        final = {
            "outcome": "provision_match",
            "possible_provision_ids": ordered_supported,
            "uncertain_sections": uncertain,
        }
        return final, actions, "supported_candidates_after_statutory_evidence_gates"
    if uncertain:
        final = {
            "outcome": "insufficient_information",
            "possible_provision_ids": [],
            "uncertain_sections": uncertain,
        }
        return final, actions, "only_missing_or_downgraded_candidates"
    return {
        "outcome": "out_of_scope",
        "possible_provision_ids": [],
        "uncertain_sections": [],
    }, actions, "no_grounded_recommendable_candidate"


if not RAG_V2_1_RESULT_PATH.is_file():
    raise FileNotFoundError("Complete RAG v2.1 before running the v2.2 evidence gate")
v2_1_payload = json.loads(RAG_V2_1_RESULT_PATH.read_text(encoding="utf-8"))
if v2_1_payload.get("completed_test_cases") != len(TEST_CASES) or v2_1_payload.get("in_progress"):
    raise ValueError("RAG v2.1 results are incomplete")

v2_2_comparisons = []
for row in v2_1_payload["comparisons"]:
    triage = row["lora_only"]
    assessments = row["rag_v2"]["candidate_assessments"]
    final, actions, rule = postprocess_rag_v2_2(
        row["complaint"], triage, assessments,
        row["rag_v2"].get("blocked_supported_candidates", [])
    )
    validation = validate_final_rag_v2(final)
    if not validation["valid"]:
        raise ValueError(f"RAG v2.2 validation failed for {row['case_id']}: {validation['errors']}")
    updated = copy.deepcopy(row)
    updated["rag_v2_2"] = {
        "source_rag_version": v2_1_payload["rag_version"],
        "evidence_gate_actions": actions,
        "assembly_rule": rule,
        "final_output": final,
        "final_validation": validation,
    }
    updated["v2_2_differs_from_v2_1"] = final != row["rag_v2"]["final_output"]
    v2_2_comparisons.append(updated)

v2_2_payload = {
    "schema_version": 3,
    "rag_version": RAG_V2_2_VERSION,
    "source_rag_version": v2_1_payload["rag_version"],
    "chosen_variant": v2_1_payload["chosen_variant"],
    "base_model": v2_1_payload["base_model"],
    "adapter_sha256": v2_1_payload["adapter_sha256"],
    "total_test_cases": len(TEST_CASES),
    "completed_test_cases": len(v2_2_comparisons),
    "comparisons": v2_2_comparisons,
}
temporary = RAG_V2_2_RESULT_PATH.with_suffix(".json.part")
temporary.write_text(json.dumps(v2_2_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
os.replace(temporary, RAG_V2_2_RESULT_PATH)

display(Markdown("## RAG v2.2 evidence-gate summary"))
display(DisplayJSON({
    "completed_cases": len(v2_2_comparisons),
    "valid_outputs": sum(row["rag_v2_2"]["final_validation"]["valid"] for row in v2_2_comparisons),
    "changed_cases": [row["case_id"] for row in v2_2_comparisons if row["v2_2_differs_from_v2_1"]],
    "outcomes": dict(Counter(row["rag_v2_2"]["final_output"]["outcome"] for row in v2_2_comparisons)),
    "output_file": str(RAG_V2_2_RESULT_PATH),
}, expanded=True))
print("RAG v2.2 reused the completed v2.1 assessments; it made no new batch model calls.")
'''


INTERACTIVE_V2_2_CODE = r'''# ============================================================
# INTERACTIVE LoRA / RAG V2.1 / EVIDENCE-GATED RAG V2.2
# ============================================================

import json
from datetime import datetime, timezone
import ipywidgets as widgets
from IPython.display import display, Markdown, JSON as DisplayJSON, clear_output

RAG_V2_2_INTERACTIVE_LOG = PROJECT / "interactive_rag_v2_2_tests.jsonl"

v2_2_complaint_input = widgets.Textarea(
    value="", placeholder="Describe an incident in ordinary language...",
    description="Complaint:", layout=widgets.Layout(width="100%", height="180px"),
    style={"description_width": "90px"}
)
v2_2_button = widgets.Button(description="Run RAG v2.2", button_style="primary", icon="search")
v2_2_output = widgets.Output()


def run_interactive_v2_2(_):
    complaint = v2_2_complaint_input.value.strip()
    with v2_2_output:
        clear_output(wait=True)
        if not complaint:
            print("Enter a complaint first.")
            return
        v2_2_button.disabled = True
        try:
            ensure_rag_v2_model_loaded()
            print("Running LoRA triage...")
            triage_raw, triage = run_live_lora_triage(complaint)
            if not isinstance(triage, dict):
                raise ValueError("LoRA triage did not produce a JSON object: " + triage_raw)

            def progress(index, total, candidate):
                print(f"Assessing candidate {index}/{total}: {candidate['provision_id']}")

            v2_1_result = run_live_rag_v2(complaint, triage, progress)
            v2_2_final, actions, rule = postprocess_rag_v2_2(
                complaint, triage, v2_1_result["candidate_assessments"],
                v2_1_result.get("blocked_supported_candidates", [])
            )
            validation = validate_final_rag_v2(v2_2_final)
            record = {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "rag_version": RAG_V2_2_VERSION,
                "complaint": complaint,
                "lora_only": {"raw": triage_raw, "parsed": triage},
                "rag_v2_1": v2_1_result,
                "rag_v2_2": {
                    "evidence_gate_actions": actions,
                    "assembly_rule": rule,
                    "final_output": v2_2_final,
                    "final_validation": validation,
                },
            }
            with RAG_V2_2_INTERACTIVE_LOG.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            display(Markdown("## LoRA-only triage"))
            display(DisplayJSON(record["lora_only"], expanded=True))
            display(Markdown("## RAG v2.1 candidate assessment"))
            display(DisplayJSON(v2_1_result, expanded=True))
            display(Markdown("## Final RAG v2.2 evidence-gated output"))
            display(DisplayJSON(record["rag_v2_2"], expanded=True))
            print("Saved to:", RAG_V2_2_INTERACTIVE_LOG)
        except Exception as error:
            print(type(error).__name__ + ":", error)
        finally:
            v2_2_button.disabled = False


v2_2_button.on_click(run_interactive_v2_2)
display(Markdown("# Test your own complaint with RAG v2.2"))
display(Markdown(
    "This runs the trained LoRA, candidate assessment, and the statutory-evidence gate. "
    "The gate records every candidate it removes or downgrades."
))
display(v2_2_complaint_input, v2_2_button, v2_2_output)
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    notebook = json.loads(args.source.read_text(encoding="utf-8"))
    if notebook.get("nbformat") != 4:
        raise ValueError("Expected a v4 Jupyter notebook")
    cells = []
    for cell in notebook.get("cells", []):
        tags = cell.get("metadata", {}).get("tags", [])
        if any(tag.startswith(TAG_PREFIX) for tag in tags):
            continue
        if cell.get("cell_type") == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
            # In v2.2, batch postprocessing needs no model. Defer the inherited
            # v2.1 interactive model load until its button is actually clicked.
            source = "".join(cell.get("source", []))
            if "INTERACTIVE LoRA-ONLY VERSUS RAG V2.1 TESTER" in source:
                source = source.replace(
                    "ensure_rag_v2_model_loaded()\n\nv2_complaint_input",
                    "v2_complaint_input",
                    1,
                )
                source = source.replace(
                    "        try:\n            print(\"Running LoRA triage...\")",
                    "        try:\n            ensure_rag_v2_model_loaded()\n            print(\"Running LoRA triage...\")",
                    1,
                )
                cell["source"] = source.splitlines(keepends=True)
        cells.append(cell)
    if not any("RAG V2.1" in "".join(cell.get("source", [])) for cell in cells):
        raise ValueError("Source notebook does not contain RAG v2.1")
    cells.extend([
        markdown("""# RAG v2.2 statutory-evidence gate

This fast stage reuses the completed v2.1 candidate assessments and applies explicit distinguishing facts from the statutory text. It records every removal or downgrade and makes no new batch model calls.
""", "legalai-rag-v2-2-comparison"),
        code(RAG_V2_2_CODE, "legalai-rag-v2-2-comparison"),
        markdown("""# Interactive RAG v2.2 testing

Use this final tester for new complaints. It displays the LoRA output, v2.1 candidate assessments, every evidence-gate action, and the final v2.2 result.
""", "legalai-rag-v2-2-interactive"),
        code(INTERACTIVE_V2_2_CODE, "legalai-rag-v2-2-interactive"),
    ])
    notebook["cells"] = cells
    notebook.get("metadata", {}).pop("widgets", None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
