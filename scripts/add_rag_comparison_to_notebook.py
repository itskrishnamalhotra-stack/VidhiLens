"""Append a lightweight RAG comparison and interactive tester to Krishna's notebook."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


RAG_TAGS = {"legalai-rag-comparison", "legalai-rag-interactive"}


def markdown(source: str, tag: str) -> dict:
    return {"cell_type": "markdown", "metadata": {"tags": [tag]},
            "source": source.splitlines(keepends=True)}


def code(source: str, tag: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {"tags": [tag]},
            "outputs": [], "source": source.splitlines(keepends=True)}


RAG_CODE = r'''# ============================================================
# LIGHTWEIGHT RAG + LoRA-ONLY VERSUS LoRA+RAG COMPARISON
# ============================================================

import hashlib
import json
import math
import os
import re
import torch
from collections import Counter
from pathlib import Path
from IPython.display import display, Markdown, JSON as DisplayJSON

RAG_VERSION = "verified_catalogue_hybrid_bm25_v2"
RAG_TOP_K = 8
RESTART_RAG_COMPARISON = False
RAG_RESULTS_PATH = PROJECT / "rag_comparison_results_v1.json"
RAG_CATALOGUE_FILE = PROJECT / "rag_catalogue_v1.json"
RAG_CATALOGUE_SHA256 = "7e29261f71d494d2846d6ac6a170548191853fe7b1d90940cde3e240053c3cfe"
RAG_WORK = Path("/content/legal_ai_rag_test")
RAG_WORK.mkdir(parents=True, exist_ok=True)

RAG_SYSTEM_PROMPT = """You analyse a reported incident using only the retrieved candidate provisions supplied by the application.
Return JSON only with outcome, possible_provision_ids, and uncertain_sections.
outcome must be provision_match, insufficient_information, or out_of_scope.
possible_provision_ids must contain only supplied candidate IDs whose material requirements are supported by stated facts.
Each uncertain_sections item must contain provision_id and missing_facts.
Treat every provision as a possibility, never a finding of guilt.
Do not infer gender, consent, dishonest intention, use of credentials, injury severity, repetition, payment, publication, or any other missing fact.
Do not put a candidate with uncertain legal status into possible_provision_ids.
Definitions, procedures, powers, exceptions and civil penalties may explain another offence but are not themselves offence suggestions.
Retrieved candidates are possibilities, not conclusions. Include multiple provisions only when their separate requirements are supported."""

# Ordinary-language additions only improve candidate retrieval. They do not decide the answer.
QUERY_EXPANSIONS = (
    (("bus", "train", "metro", "taxi"), "means of transport passengers article goods theft"),
    (("stole", "stolen", "steal", "removed", "took"), "theft movable property possession consent dishonestly"),
    (("snatched", "grabbed", "seized"), "snatching suddenly quickly forcibly grabs takes away"),
    (("hacked", "unauthorised", "unauthorized", "accessed"), "computer access without permission data download computer related offence"),
    (("password", "otp", "login"), "password unique identification identity theft computer resource"),
    (("pretending", "impersonating", "fake profile", "fake account"), "cheating personation communication device computer resource"),
    (("private photograph", "private image", "intimate", "changing clothes"), "privacy private area image capture publish transmit voyeurism"),
    (("sexual", "sexually"), "sexual harassment explicit sexual act obscene material"),
    (("followed", "following", "monitoring"), "stalking follows contacts repeatedly monitors electronic communication"),
    (("fracture", "fractured", "broken bone"), "grievous hurt fracture dangerous weapon"),
    (("threat", "threatening", "blackmail"), "criminal intimidation fear injury extortion demand property"),
    (("repair", "entrusted", "returning"), "entrusted property criminal breach of trust misappropriates"),
    (("forged", "fabricated", "false document"), "forgery forged document cheating"),
)

# Anchors keep closely related provisions in the comparison set. They retrieve candidates only;
# the model must still compare the complaint against the supplied official text.
RETRIEVAL_ANCHORS = (
    (("bus", "train", "metro", "backpack", "stole", "stolen", "snatched"),
     ("BNS_303", "BNS_304", "BNS_305")),
    (("hacked", "unauthorised", "unauthorized", "accessed", "login history"),
     ("ITA_43", "ITA_66", "ITA_66C")),
    (("otp", "password"), ("ITA_66", "ITA_66C", "ITA_66D")),
    (("pretending", "impersonating", "fake profile", "fake account"),
     ("BNS_319", "ITA_66C", "ITA_66D")),
    (("private photograph", "private image", "intimate", "changing clothes"),
     ("BNS_77", "ITA_66E", "ITA_67", "ITA_67A")),
    (("sexual favour", "sexual remark", "sexual harassment"), ("BNS_75",)),
    (("followed", "following", "monitoring"), ("BNS_78",)),
    (("fracture", "fractured", "iron rod", "weapon"), ("BNS_117", "BNS_118")),
    (("threat", "threatening", "blackmail"), ("BNS_308", "BNS_351")),
    (("repair", "entrusted"), ("BNS_316",)),
    (("forged", "fabricated", "false document"), ("BNS_318", "BNS_336", "BNS_340")),
)


def rag_tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def expand_rag_query(text):
    lower = text.lower()
    additions = [addition for triggers, addition in QUERY_EXPANSIONS
                 if any(trigger in lower for trigger in triggers)]
    return text + " " + " ".join(additions)


if not RAG_CATALOGUE_FILE.is_file():
    raise FileNotFoundError(
        "Upload rag_catalogue_v1.json beside the notebook in MyDrive/LegalAI, then run this cell again"
    )
rag_catalogue_bytes = RAG_CATALOGUE_FILE.read_bytes()
if hashlib.sha256(rag_catalogue_bytes).hexdigest() != RAG_CATALOGUE_SHA256:
    raise ValueError("rag_catalogue_v1.json failed its SHA-256 integrity check")
rag_catalogue_payload = json.loads(rag_catalogue_bytes)
if rag_catalogue_payload.get("counts") != {
        "total": 467, "in_force": 466, "uncertain": 1, "recommendable": 19}:
    raise ValueError("Unexpected RAG catalogue scope")
RAG_CATALOGUE_ROWS = rag_catalogue_payload["provisions"]
RAG_CATALOGUE = {row["provision_id"]: row for row in RAG_CATALOGUE_ROWS}
RAG_DOCUMENT_TOKENS = []
RAG_TITLE_TOKENS = []

for row in RAG_CATALOGUE_ROWS:
    title = row.get("title", "")
    text = row.get("verified_text", "")
    RAG_TITLE_TOKENS.append(set(rag_tokens(title)))
    # Repeating the short title gives it more weight without changing the source text.
    RAG_DOCUMENT_TOKENS.append(rag_tokens((title + " ") * 3 + text))

RAG_DOCUMENT_FREQUENCY = Counter()
for tokens in RAG_DOCUMENT_TOKENS:
    RAG_DOCUMENT_FREQUENCY.update(set(tokens))

RAG_DOCUMENT_COUNT = len(RAG_DOCUMENT_TOKENS)
RAG_AVERAGE_LENGTH = sum(map(len, RAG_DOCUMENT_TOKENS)) / RAG_DOCUMENT_COUNT


def bm25_idf(term):
    frequency = RAG_DOCUMENT_FREQUENCY.get(term, 0)
    return math.log(1 + (RAG_DOCUMENT_COUNT - frequency + 0.5) / (frequency + 0.5))


def retrieve_provisions(complaint, top_k=RAG_TOP_K):
    query_counts = Counter(rag_tokens(expand_rag_query(complaint)))
    scored = []
    k1 = 1.5
    b = 0.75

    for index, document_tokens in enumerate(RAG_DOCUMENT_TOKENS):
        frequencies = Counter(document_tokens)
        length = len(document_tokens)
        score = 0.0

        for term, query_frequency in query_counts.items():
            term_frequency = frequencies.get(term, 0)
            if not term_frequency:
                continue
            denominator = term_frequency + k1 * (1 - b + b * length / RAG_AVERAGE_LENGTH)
            score += bm25_idf(term) * (term_frequency * (k1 + 1) / denominator) * min(query_frequency, 2)
            if term in RAG_TITLE_TOKENS[index]:
                score += 1.25 * bm25_idf(term)

        scored.append((score, index))

    lower = complaint.lower()
    anchor_ids = []
    for triggers, provision_ids in RETRIEVAL_ANCHORS:
        if any(trigger in lower for trigger in triggers):
            for provision_id in provision_ids:
                if provision_id in RAG_CATALOGUE and provision_id not in anchor_ids:
                    anchor_ids.append(provision_id)
    catalogue_index = {row["provision_id"]: index for index, row in enumerate(RAG_CATALOGUE_ROWS)}
    score_by_index = {index: score for score, index in scored}
    selected_indices = [catalogue_index[provision_id] for provision_id in anchor_ids]
    for _, index in sorted(scored, key=lambda item: (-item[0], item[1])):
        if index not in selected_indices:
            selected_indices.append(index)
        if len(selected_indices) == top_k:
            break
    results = []

    for index in selected_indices[:top_k]:
        row = RAG_CATALOGUE_ROWS[index]
        results.append({
            "provision_id": row["provision_id"],
            "title": row.get("title"),
            "recommendable": bool(row.get("recommendable")),
            "legal_status": row.get("legal_status"),
            "provision_kind": row.get("provision_kind"),
            "anchor_matched": row["provision_id"] in anchor_ids,
            "retrieval_score": round(score_by_index[index], 6),
            "verified_text": row.get("verified_text", "")
        })

    return results


def compact_provision_for_prompt(row, limit=1800):
    legal_text = re.sub(r"\s+", " ", row.get("verified_text", "")).strip()
    return {
        "provision_id": row["provision_id"],
        "title": row.get("title"),
        "legal_status": row.get("legal_status"),
        "provision_kind": row.get("provision_kind"),
        "legal_text": legal_text[:limit]
    }


def ensure_rag_model_loaded():
    global rag_model, rag_tokenizer
    if "rag_model" not in globals():
        if "batch_test_model" in globals() and "batch_test_tokenizer" in globals():
            rag_model = batch_test_model
            rag_tokenizer = batch_test_tokenizer
            print("Reusing the LoRA already loaded by the 21-complaint test.")
        else:
            print("Loading the selected LoRA for RAG testing...")
            torch.cuda.empty_cache()
            training_results = json.loads(
                (PROJECT / "training_results.json").read_text(encoding="utf-8")
            )
            selected_run = PROJECT / "runs" / training_results["chosen"]
            rag_model, rag_tokenizer = train_runner.load_adapter(selected_run, RAG_WORK)
            print("RAG test model loaded.")


def generate_rag_answer(complaint, candidates):
    candidate_context = [compact_provision_for_prompt(row) for row in candidates]
    user_prompt = (
        "Reported incident:\n" + complaint +
        "\n\nRetrieved candidate provisions:\n" +
        json.dumps(candidate_context, ensure_ascii=False)
    )
    messages = [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]
    input_ids = rag_tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt"
    ).to(rag_model.device)
    attention_mask = torch.ones_like(input_ids, dtype=torch.long)
    with torch.inference_mode():
        generated = rag_model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=240,
            do_sample=False,
            pad_token_id=rag_tokenizer.eos_token_id,
            eos_token_id=rag_tokenizer.eos_token_id
        )
    raw = rag_tokenizer.decode(
        generated[0, input_ids.shape[-1]:], skip_special_tokens=True
    ).strip()
    return raw, train_runner.parse_json(raw)


def validate_rag_answer(parsed, candidates):
    candidate_ids = {row["provision_id"] for row in candidates}
    if not isinstance(parsed, dict):
        return {
            "json_valid": False,
            "schema_errors": ["output is not a JSON object"],
            "invalid_provision_ids": [],
            "unsupported_by_retrieval": [],
            "non_recommendable_provision_ids": [],
            "release_gate_passed": False
        }
    schema_errors = []
    if parsed.get("outcome") not in {"provision_match", "insufficient_information", "out_of_scope"}:
        schema_errors.append("invalid outcome")
    provision_ids = parsed.get("possible_provision_ids", [])
    if not isinstance(provision_ids, list):
        schema_errors.append("possible_provision_ids is not a list")
        provision_ids = []
    if not isinstance(parsed.get("uncertain_sections"), list):
        schema_errors.append("uncertain_sections is not a list")
    invalid = [pid for pid in provision_ids if pid not in RAG_CATALOGUE]
    unsupported = [pid for pid in provision_ids if pid not in candidate_ids]
    non_recommendable = [pid for pid in provision_ids
                         if pid in RAG_CATALOGUE and not RAG_CATALOGUE[pid].get("recommendable")]
    uncertain_status = [pid for pid in provision_ids if pid in RAG_CATALOGUE and
                        RAG_CATALOGUE[pid].get("legal_status") != "in_force"]
    non_offence = [pid for pid in provision_ids if pid in RAG_CATALOGUE and
                   RAG_CATALOGUE[pid].get("provision_kind") != "offence"]
    return {
        "json_valid": not schema_errors,
        "schema_errors": schema_errors,
        "invalid_provision_ids": invalid,
        "unsupported_by_retrieval": unsupported,
        "non_recommendable_provision_ids": non_recommendable,
        "uncertain_status_provision_ids": uncertain_status,
        "non_offence_provision_ids": non_offence,
        "release_gate_passed": not schema_errors and not invalid and not unsupported and not non_recommendable and
                               not uncertain_status and not non_offence
    }


def run_rag_test_case(case):
    candidates = retrieve_provisions(case["complaint"])
    raw, parsed = generate_rag_answer(case["complaint"], candidates)
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "review_goal": case["review_goal"],
        "complaint": case["complaint"],
        "retrieved_candidates": [{
            "provision_id": row["provision_id"],
            "title": row["title"],
            "recommendable": row["recommendable"],
            "legal_status": row["legal_status"],
            "provision_kind": row["provision_kind"],
            "anchor_matched": row["anchor_matched"],
            "retrieval_score": row["retrieval_score"]
        } for row in candidates],
        "raw_model_output": raw,
        "parsed_output": parsed,
        "validation": validate_rag_answer(parsed, candidates)
    }


def atomic_write_rag_results(comparisons, baseline_payload, adapter_hash):
    ordered_by_id = {row["case_id"]: row for row in comparisons}
    ordered = [ordered_by_id[case["case_id"]] for case in TEST_CASES
               if case["case_id"] in ordered_by_id]
    payload = {
        "schema_version": 1,
        "rag_version": RAG_VERSION,
        "chosen_variant": baseline_payload["chosen_variant"],
        "base_model": baseline_payload["base_model"],
        "adapter_sha256": adapter_hash,
        "top_k": RAG_TOP_K,
        "total_test_cases": len(TEST_CASES),
        "completed_test_cases": len(ordered),
        "comparisons": ordered
    }
    temporary = RAG_RESULTS_PATH.with_suffix(".json.part")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    os.replace(temporary, RAG_RESULTS_PATH)
    return ordered


BASELINE_PATH = PROJECT / "manual_batch_test_results_v1.json"
if not BASELINE_PATH.exists():
    raise FileNotFoundError("Run the 21-complaint batch-test cell above first")
baseline_payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
if baseline_payload.get("completed_test_cases") != len(TEST_CASES):
    raise ValueError("The LoRA-only batch is incomplete")
baseline_by_id = {row["case_id"]: row for row in baseline_payload["cases"]}
adapter_hash = baseline_payload["adapter_sha256"]

comparisons = []
if RAG_RESULTS_PATH.exists() and not RESTART_RAG_COMPARISON:
    previous = json.loads(RAG_RESULTS_PATH.read_text(encoding="utf-8"))
    if previous.get("rag_version") != RAG_VERSION or previous.get("adapter_sha256") != adapter_hash:
        raise RuntimeError("Existing RAG results use a different method or adapter. Set RESTART_RAG_COMPARISON=True.")
    comparisons = previous.get("comparisons", [])
    print(f"Resuming RAG comparison: {len(comparisons)}/{len(TEST_CASES)} complete")
elif RESTART_RAG_COMPARISON and RAG_RESULTS_PATH.exists():
    RAG_RESULTS_PATH.unlink()

completed_ids = {row["case_id"] for row in comparisons}
pending = [case for case in TEST_CASES if case["case_id"] not in completed_ids]

if pending:
    ensure_rag_model_loaded()

for case in pending:
    print(f"RAG testing {case['case_id']} ({len(comparisons) + 1}/{len(TEST_CASES)})")
    rag_result = run_rag_test_case(case)
    baseline = baseline_by_id[case["case_id"]]
    comparison = {
        "case_id": case["case_id"],
        "category": case["category"],
        "review_goal": case["review_goal"],
        "complaint": case["complaint"],
        "lora_only": {
            "raw_model_output": baseline.get("raw_model_output"),
            "parsed_output": baseline.get("parsed_output"),
            "database_validation": baseline.get("database_validation")
        },
        "lora_plus_rag": rag_result,
        "outputs_differ": baseline.get("parsed_output") != rag_result.get("parsed_output")
    }
    comparisons.append(comparison)
    comparisons = atomic_write_rag_results(comparisons, baseline_payload, adapter_hash)
    print("LoRA only:", json.dumps(comparison["lora_only"]["parsed_output"], ensure_ascii=False))
    print("LoRA + RAG:", json.dumps(rag_result["parsed_output"], ensure_ascii=False))
    print("Saved to Drive.\n")

comparisons = atomic_write_rag_results(comparisons, baseline_payload, adapter_hash)
rag_valid = sum(row["lora_plus_rag"]["validation"]["json_valid"] for row in comparisons)
rag_invalid_ids = sum(bool(row["lora_plus_rag"]["validation"]["invalid_provision_ids"])
                      for row in comparisons)
rag_unsupported = sum(bool(row["lora_plus_rag"]["validation"]["unsupported_by_retrieval"])
                      for row in comparisons)
rag_release_failures = sum(not row["lora_plus_rag"]["validation"]["release_gate_passed"]
                           for row in comparisons)
changed = sum(row["outputs_differ"] for row in comparisons)

display(Markdown("## LoRA-only versus LoRA-plus-RAG batch summary"))
display(DisplayJSON({
    "completed_cases": len(comparisons),
    "rag_valid_json_outputs": rag_valid,
    "rag_cases_with_invalid_ids": rag_invalid_ids,
    "rag_cases_with_ids_outside_retrieved_candidates": rag_unsupported,
    "rag_cases_blocked_by_release_gate": rag_release_failures,
    "outputs_changed_by_rag": changed,
    "comparison_file": str(RAG_RESULTS_PATH)
}, expanded=True))
print("Attach rag_comparison_results_v1.json from MyDrive/LegalAI for detailed review.")
'''


INTERACTIVE_CODE = r'''# ============================================================
# INTERACTIVE LoRA-ONLY VERSUS LoRA+RAG TESTER
# ============================================================

import json
from datetime import datetime, timezone
import ipywidgets as widgets
from IPython.display import display, Markdown, JSON as DisplayJSON, clear_output

INTERACTIVE_LOG = PROJECT / "interactive_rag_tests_v1.jsonl"
LORA_ONLY_SYSTEM_PROMPT = (
    "Read the reported incident. Return JSON only with outcome, "
    "possible_provision_ids, and uncertain_sections. "
    "A section is only a possibility, never a finding of guilt. "
    "Never invent missing facts."
)


def run_lora_only_interactive(complaint):
    messages = [
        {"role": "system", "content": LORA_ONLY_SYSTEM_PROMPT},
        {"role": "user", "content": complaint}
    ]
    input_ids = rag_tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt"
    ).to(rag_model.device)
    attention_mask = torch.ones_like(input_ids, dtype=torch.long)
    with torch.inference_mode():
        generated = rag_model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=180,
            do_sample=False,
            pad_token_id=rag_tokenizer.eos_token_id,
            eos_token_id=rag_tokenizer.eos_token_id
        )
    raw = rag_tokenizer.decode(
        generated[0, input_ids.shape[-1]:], skip_special_tokens=True
    ).strip()
    return raw, train_runner.parse_json(raw)


def append_interactive_result(record):
    with INTERACTIVE_LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


ensure_rag_model_loaded()

complaint_input = widgets.Textarea(
    value="",
    placeholder="Describe an incident in ordinary language...",
    description="Complaint:",
    layout=widgets.Layout(width="100%", height="170px"),
    style={"description_width": "90px"}
)
compare_button = widgets.Button(
    description="Compare both systems",
    button_style="primary",
    icon="search"
)
interactive_output = widgets.Output()


def compare_custom_complaint(_):
    complaint = complaint_input.value.strip()
    with interactive_output:
        clear_output(wait=True)
        if not complaint:
            print("Enter a complaint first.")
            return
        compare_button.disabled = True
        try:
            print("Running LoRA-only analysis...")
            baseline_raw, baseline_parsed = run_lora_only_interactive(complaint)
            print("Retrieving verified provisions and running RAG analysis...")
            candidates = retrieve_provisions(complaint)
            rag_raw, rag_parsed = generate_rag_answer(complaint, candidates)
            rag_validation = validate_rag_answer(rag_parsed, candidates)
            record = {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "rag_version": RAG_VERSION,
                "complaint": complaint,
                "retrieved_candidates": [{
                    "provision_id": row["provision_id"],
                    "title": row["title"],
                    "recommendable": row["recommendable"],
                    "legal_status": row["legal_status"],
                    "provision_kind": row["provision_kind"],
                    "anchor_matched": row["anchor_matched"],
                    "retrieval_score": row["retrieval_score"]
                } for row in candidates],
                "lora_only": {"raw": baseline_raw, "parsed": baseline_parsed},
                "lora_plus_rag": {
                    "raw": rag_raw,
                    "parsed": rag_parsed,
                    "validation": rag_validation
                }
            }
            append_interactive_result(record)
            display(Markdown("## Retrieved candidates"))
            display(DisplayJSON(record["retrieved_candidates"], expanded=True))
            display(Markdown("## LoRA-only output"))
            display(DisplayJSON(record["lora_only"], expanded=True))
            display(Markdown("## LoRA-plus-RAG output"))
            display(DisplayJSON(record["lora_plus_rag"], expanded=True))
            print("Saved to:", INTERACTIVE_LOG)
        except Exception as error:
            print(type(error).__name__ + ":", error)
        finally:
            compare_button.disabled = False


compare_button.on_click(compare_custom_complaint)
display(Markdown("# Test your own complaint"))
display(Markdown(
    "This compares the trained LoRA by itself with the same LoRA grounded in retrieved "
    "verified provisions. Results are research suggestions, not findings of guilt or legal advice."
))
display(complaint_input, compare_button, interactive_output)
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
        tags = set(cell.get("metadata", {}).get("tags", []))
        if tags & RAG_TAGS:
            continue
        cell["execution_count"] = None if cell.get("cell_type") == "code" else cell.get("execution_count")
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
        cells.append(cell)
    if len(cells) < 7 or "AUTOMATIC 21-COMPLAINT BATCH TEST" not in "".join(cells[6].get("source", [])):
        raise ValueError("The source notebook does not contain Krishna's extra batch-test cell")
    cells.extend([
        markdown("""# Lightweight RAG evaluation

Before running it, upload `rag_catalogue_v1.json` beside the notebook in `MyDrive/LegalAI`. The cell verifies its hash, then builds an in-memory hybrid lexical/BM25 retriever over 467 BNS and IT Act entries with verified text. It compares the saved LoRA-only answers with answers grounded in the top retrieved statutory candidates. It saves after every case and can resume after a disconnect.
""", "legalai-rag-comparison"),
        code(RAG_CODE, "legalai-rag-comparison"),
        markdown("""# Interactive comparison

Use the final cell after the automatic comparison. Enter any new complaint to view the retrieved candidates, LoRA-only answer, grounded answer and database validation together.
""", "legalai-rag-interactive"),
        code(INTERACTIVE_CODE, "legalai-rag-interactive")
    ])
    notebook["cells"] = cells
    notebook.get("metadata", {}).pop("widgets", None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
