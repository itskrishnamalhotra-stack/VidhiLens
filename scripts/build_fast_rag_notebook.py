"""Build the single-call candidate assessment notebook for Colab T4 latency."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_improved_rag_notebook as base


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "scripts" / "rag_improved_core.py"
TAG_PREFIX = "legalai-fast-rag-"


JOINT_FUNCTIONS = r'''def improved_candidate_messages(complaint, candidates, context_candidates, triage):
    payload = {
        "reported_incident": complaint,
        "candidates": [{
            "provision_id": item["provision_id"],
            "title": item["title"],
            "legal_text": re.sub(r"\s+", " ", item["verified_text"]).strip()[:1800],
            "element_checklist": item["element_checklist"],
            "retrieval_signals": {
                "concept_hit_count": item["concept_hit_count"],
                "uncertainty_hit_count": item["uncertainty_hit_count"],
                "triage_seed": item["triage_seed"],
                "companion_candidate": item["companion_candidate"],
            },
        } for item in candidates],
        "supporting_context": [{
            "provision_id": item["provision_id"],
            "title": item["title"],
            "legal_text": re.sub(r"\s+", " ", item["verified_text"]).strip()[:1500],
        } for item in context_candidates],
        "lora_triage_prior": triage if isinstance(triage, dict) else None,
    }
    return [
        {"role": "system", "content": JOINT_CANDIDATE_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def validate_improved_assessment(parsed, expected_id, complaint):
    errors = []
    if not isinstance(parsed, dict):
        return ["assessment is not an object"]
    if parsed.get("provision_id") != expected_id:
        errors.append("wrong provision_id")
    decision = parsed.get("decision")
    if decision not in {"supported", "missing_facts", "rejected"}:
        errors.append("invalid decision")
    evidence = parsed.get("evidence_spans")
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        errors.append("evidence_spans is not a string list")
        evidence = []
    if len(evidence) > 2:
        errors.append("too many evidence spans")
    if decision == "supported" and not evidence:
        errors.append("supported requires evidence")
    complaint_normal = normalise_text(complaint)
    if any(normalise_text(span) not in complaint_normal for span in evidence):
        errors.append("evidence is not an exact complaint quote")
    missing = parsed.get("missing_facts")
    if not isinstance(missing, list) or not all(isinstance(item, str) for item in missing):
        errors.append("missing_facts is not a string list")
        missing = []
    if len(missing) > 1:
        errors.append("too many missing-fact questions")
    if decision == "missing_facts" and not missing:
        errors.append("missing_facts decision requires one question")
    if decision != "missing_facts" and missing:
        errors.append("only missing_facts decision may contain a question")
    return errors


def _joint_records(candidates, complaint, raw):
    parsed = train_runner.parse_json(raw)
    assessments = parsed.get("assessments") if isinstance(parsed, dict) else None
    if not isinstance(assessments, list):
        return [], ["root must contain an assessments list"]
    by_id = {
        item.get("provision_id"): item for item in assessments
        if isinstance(item, dict) and isinstance(item.get("provision_id"), str)
    }
    expected_ids = [item["provision_id"] for item in candidates]
    root_errors = []
    if set(by_id) != set(expected_ids):
        root_errors.append("assessment IDs must exactly equal candidate IDs")
    records = []
    for candidate in candidates:
        item = by_id.get(candidate["provision_id"])
        errors = validate_improved_assessment(item, candidate["provision_id"], complaint)
        records.append({
            **{key: candidate[key] for key in (
                "provision_id", "title", "recommendable", "retrieval_score",
                "concept_hit_count", "uncertainty_hit_count", "triage_seed", "companion_candidate"
            )},
            "raw_model_output": raw,
            "parsed_assessment": item,
            "schema_valid": not errors,
            "schema_errors": errors,
        })
    return records, root_errors + [
        error for record in records for error in record["schema_errors"]
    ]


def generate_joint_assessment(messages, max_new_tokens=650):
    input_ids = rag_v2_tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt"
    ).to(rag_v2_model.device)
    attention_mask = torch.ones_like(input_ids, dtype=torch.long)
    with rag_v2_model.disable_adapter(), torch.inference_mode():
        generated = rag_v2_model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=rag_v2_tokenizer.eos_token_id,
            eos_token_id=rag_v2_tokenizer.eos_token_id,
        )
    return rag_v2_tokenizer.decode(
        generated[0, input_ids.shape[-1]:], skip_special_tokens=True
    ).strip()


def assess_improved_candidates(complaint, candidates, context_candidates, triage,
                               completed=None, save_progress=None):
    expected_ids = [item["provision_id"] for item in candidates]
    completed = list(completed or [])
    if {item.get("provision_id") for item in completed} == set(expected_ids) and all(
            item.get("schema_valid") for item in completed):
        return sorted(completed, key=lambda item: expected_ids.index(item["provision_id"]))

    messages = improved_candidate_messages(complaint, candidates, context_candidates, triage)
    raw = generate_joint_assessment(messages)
    records, errors = _joint_records(candidates, complaint, raw)
    if errors:
        repair_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content":
             "The JSON failed validation: " + "; ".join(dict.fromkeys(errors)) +
             ". Return the complete corrected JSON for every candidate. JSON only."},
        ]
        repaired_raw = generate_joint_assessment(repair_messages)
        repaired_records, repaired_errors = _joint_records(candidates, complaint, repaired_raw)
        if not repaired_errors:
            records = repaired_records
    if save_progress:
        save_progress(records)
    return records


'''


def make_setup(core_sha256: str) -> str:
    prefix, remainder = base.SETUP_CODE.split("def improved_candidate_messages", 1)
    _, suffix = remainder.split("def assemble_improved", 1)
    prefix = prefix.replace(
        'IMPROVED_PREDICTIONS = PROJECT / "rag_improved_regression_predictions.json"',
        'IMPROVED_PREDICTIONS = PROJECT / "rag_fast_regression_predictions.json"',
    ).replace(
        'IMPROVED_REPORT = PROJECT / "rag_improved_regression_report.json"',
        'IMPROVED_REPORT = PROJECT / "rag_fast_regression_report.json"',
    ).replace(
        'IMPROVED_INTERACTIVE_LOG = PROJECT / "interactive_rag_improved_tests.jsonl"',
        'IMPROVED_INTERACTIVE_LOG = PROJECT / "interactive_rag_fast_tests.jsonl"',
    )
    # The joint prompt is intentionally compact: one model call assesses every
    # retrieved candidate, which is the main latency reduction.
    joint_prompt = r'''
ASSESSMENT_MODE = "single_joint_candidate_call"
PIPELINE_ID = PIPELINE_ID + "_joint"
JOINT_CANDIDATE_SYSTEM_PROMPT = """Assess every supplied candidate provision against the reported incident.
This is cautious possible-section triage, not guilt and not legal advice.
For each candidate return provision_id, decision, evidence_spans and missing_facts.
decision is supported, missing_facts, or rejected.
supported requires all material checklist elements and one or two short exact quotations copied from the incident.
missing_facts requires exactly one short factual question and no evidence quote is required.
rejected is used for contradiction, a shared keyword, or no reasonable factual link.
Do not infer cheating from delay alone, breach of trust from late return alone, physical theft from a bank transfer, or sexually explicit conduct from merely private or obscene material.
Return compact JSON only in this exact form:
{"assessments":[{"provision_id":"...","decision":"supported|missing_facts|rejected","evidence_spans":["exact quote"],"missing_facts":[]}]}
Return exactly one assessment for every supplied candidate and no extra IDs."""

'''
    return f'IMPROVED_CORE_SHA256 = "{core_sha256}"\n' + prefix + joint_prompt + JOINT_FUNCTIONS + "def assemble_improved" + suffix


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
    if not any("SEALED RAG V2.2 BENCHMARK" in "".join(cell.get("source", [])) for cell in cells):
        raise ValueError("Source notebook does not contain the completed benchmark workflow")
    core_source = CORE.read_text(encoding="utf-8")
    core_sha256 = hashlib.sha256(core_source.encode("utf-8")).hexdigest()
    setup = make_setup(core_sha256)
    regression = base.REGRESSION_CODE.replace(
        "PIPELINE_ID + IMPROVED_CORE_SHA256 + IMPROVED_CANDIDATE_SYSTEM_PROMPT +",
        "PIPELINE_ID + ASSESSMENT_MODE + IMPROVED_CORE_SHA256 + JOINT_CANDIDATE_SYSTEM_PROMPT +",
    ).replace("IMPROVED_CANDIDATE_SYSTEM_PROMPT", "JOINT_CANDIDATE_SYSTEM_PROMPT")
    cells.extend([
        base.markdown("""# Fast grounded RAG regression

The legal retrieval, evidence gate and validator are unchanged. The speed fix assesses all retrieved candidates in **one compact model call per complaint** instead of up to three large calls. The completed LoRA is reused and no training is repeated.

The earlier 150 cases remain regression evidence rather than fresh unseen final accuracy.
""", "legalai-fast-rag-intro"),
        base.code(core_source, "legalai-fast-rag-core"),
        base.code(setup, "legalai-fast-rag-setup"),
        base.code(regression, "legalai-fast-rag-regression"),
        # Keep the tested function and widget variable names. Only change the
        # visible button label; a blanket text replacement would rename
        # run_improved_pipeline without defining a corresponding function.
        base.code(base.INTERACTIVE_CODE.replace(
            'description="Run improved RAG"', 'description="Run fast RAG"'
        ), "legalai-fast-rag-interactive"),
    ])
    notebook["cells"] = cells
    metadata = notebook.setdefault("metadata", {})
    metadata.pop("widgets", None)
    metadata["accelerator"] = "GPU"
    metadata.setdefault("colab", {})["gpuType"] = "T4"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
