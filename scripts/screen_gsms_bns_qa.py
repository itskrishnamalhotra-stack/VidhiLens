"""Screen pinned GSMS BNS Q&A for a separate auxiliary training pool.

Passing this screen establishes provenance, structure and known-law-status
compatibility. It does not establish that a paraphrased legal answer is true.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from difflib import SequenceMatcher
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
MANIFEST = ROOT / "external_candidates_manifest.json"
OUT = ROOT / "review_automation" / "gsms_bns_qa_v1"
TYPES = {"definitional_topic", "definitional_section", "scenario", "elements", "exceptions", "consequence"}
TRAIN_TYPES = TYPES - {"scenario", "consequence"}
SUBPART_106_2 = re.compile(
    r"(?i)\b106\s*\(?2\)?\b|\bsub[ -]?section\s*\(?2\)?\b|"
    r"\bhit[ -]?and[ -]?run\b|\bten[ -]?year\b|\b10[ -]?year\b|"
    r"\b(?:flee|flees|fled|escaping|escapes|escape)\b.*\b(?:report|scene)\b|"
    r"\b(?:report|scene)\b.*\b(?:flee|flees|fled|escaping|escapes|escape)\b"
)
SOURCE_TAG = re.compile(r"\[Source:\s*([^\]]+)\]", re.I)
SOURCE_SECTION = re.compile(r"Section\s+(\d+)(?:\s*\(\d+\))?", re.I)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def recorded_cleanup(extracted: str, verified: str, note: str) -> bool:
    """Allow only small deletions documented by the project's source review."""
    if "Removed" not in note:
        return False
    a, b = norm(extracted).split(), norm(verified).split()
    if a == b:
        return True
    if a == ["date1" if x == "date" else x for x in b] and "footnote" in note:
        return True
    edits = [op for op in SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]
    return bool(edits) and all(tag == "delete" for tag, *_ in edits) and sum(j - i for _, i, j, _, _ in edits) <= 20


def read_pinned() -> tuple[list[dict], list[dict], dict]:
    files = {x["key"]: x for x in json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]}
    paths = {}
    for key in ("bns_structured", "bns_qa"):
        item = files[key]
        path = ROOT / item["local_path"]
        if not path.is_file() or sha(path) != item["sha256"]:
            raise ValueError(f"Pinned GSMS source changed: {key}")
        paths[key] = path
    structured = json.loads(paths["bns_structured"].read_text(encoding="utf-8"))
    with paths["bns_qa"].open(encoding="utf-8") as stream:
        qa = [json.loads(line) for line in stream if line.strip()]
    if len(structured) != 358 or len(qa) != 2148:
        raise ValueError("Unexpected GSMS BNS row count")
    return structured, qa, files


def main() -> None:
    structured, qa, files = read_pinned()
    sections = {str(x["section_number"]): x for x in structured}
    if len(sections) != 358:
        raise ValueError("Structured BNS section IDs are not unique")
    with sqlite3.connect(DB) as conn:
        provisions = {
            row[0]: dict(zip(("title", "status", "verified_text", "text_reviewed_on", "review_note"), row[1:]))
            for row in conn.execute("""SELECT section_number,candidate_title,legal_status,
                verified_text,text_reviewed_on,review_note FROM provision WHERE act_id='BNS_2023'""")
        }
    if len(provisions) != 358:
        raise ValueError("Master BNS section index is incomplete")

    counts_by_section = Counter(str(x.get("section_number")) for x in qa)
    counts_by_type = Counter(x.get("question_type") for x in qa)
    if set(counts_by_section) != set(sections) or set(counts_by_section.values()) != {6}:
        raise ValueError("GSMS Q&A has unexpected section coverage")
    if set(counts_by_type) != TYPES or set(counts_by_type.values()) != {358}:
        raise ValueError("GSMS Q&A has unexpected question-type coverage")
    duplicate_question = defaultdict(list)
    for line, row in enumerate(qa, 1):
        duplicate_question[norm(str(row.get("question", "")))].append(line)

    OUT.mkdir(parents=True, exist_ok=True)
    issue_counts = Counter()
    text_relation_counts = Counter()
    passed = 0
    selected = 0
    with (OUT / "audit.jsonl").open("w", encoding="utf-8", newline="\n") as audit, \
         (OUT / "auxiliary_train_sft.jsonl").open("w", encoding="utf-8", newline="\n") as train, \
         (OUT / "auxiliary_train_map.jsonl").open("w", encoding="utf-8", newline="\n") as mapping:
        for line, row in enumerate(qa, 1):
            sid = str(row.get("section_number", ""))
            provision = provisions.get(sid)
            statute = sections.get(sid)
            question = str(row.get("question", "")).strip()
            answer = str(row.get("answer", "")).strip()
            issues = []
            relation = "missing"
            title_relation = "missing"
            expected_keys = {"chunk_id", "act", "section_number", "section_title", "question", "answer", "question_type"}
            if set(row) != expected_keys:
                issues.append("schema_mismatch")
            if not question or not answer:
                issues.append("blank_qa")
            if len(duplicate_question[norm(question)]) > 1:
                issues.append("duplicate_question")
            if row.get("question_type") not in TYPES:
                issues.append("unknown_question_type")
            if row.get("act") != "BNS 2023" or row.get("chunk_id") != "BNS_" + sid:
                issues.append("act_or_chunk_mismatch")
            if provision is None or statute is None:
                issues.append("unknown_section")
            else:
                given_title, official_title = norm(str(row.get("section_title", ""))), norm(provision["title"])
                if given_title == official_title:
                    title_relation = "same_title"
                elif len(given_title) >= 25 and official_title.startswith(given_title + " "):
                    title_relation = "publisher_title_truncated"
                else:
                    title_relation = "unresolved_difference"
                    issues.append("title_mismatch")
                if provision["status"] != "in_force" or not provision["verified_text"] or not provision["text_reviewed_on"]:
                    issues.append("official_law_not_ready")
                extracted = statute["text"].split("\n\n", 1)[-1]
                official = provision["verified_text"] or ""
                a, b = norm(extracted), norm(official)
                if a == b:
                    relation = "same_normalized_text"
                elif b and recorded_cleanup(extracted, official, provision["review_note"] or ""):
                    relation = "recorded_official_cleanup"
                else:
                    relation = "unresolved_difference"
                    issues.append("statute_text_difference")
            text_relation_counts[relation] += 1
            tags = SOURCE_TAG.findall(answer)
            cited = {x for tag in tags for x in SOURCE_SECTION.findall(tag)}
            if not tags or sid not in cited or any(x not in provisions for x in cited):
                issues.append("citation_missing_or_invalid")
            elif any(provisions[x]["status"] != "in_force" for x in cited):
                issues.append("cross_citation_status")
            if sid == "106" and SUBPART_106_2.search(question + " " + answer):
                issues.append("BNS_106_2_uncommenced_subject")
            issues = sorted(set(issues))
            issue_counts.update(issues)
            decision = ("hold" if issues else "screen_pass_train" if row.get("question_type") in TRAIN_TYPES
                        else "screen_pass_research_only")
            audit.write(json.dumps({"source_row": line, "section_number": sid,
                                    "question_type": row.get("question_type"),
                                    "text_relation": relation, "title_relation": title_relation,
                                    "decision": decision,
                                    "issues": issues, "question": question}, ensure_ascii=False) + "\n")
            if issues:
                continue
            passed += 1
            if decision != "screen_pass_train":
                continue
            selected += 1
            record = {"messages": [
                {"role": "system", "content": "Answer the Indian BNS legal question accurately. Cite the section when relevant. A section citation alone does not establish that it applies to a real complaint."},
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ]}
            meta = {"task_family": "auxiliary_legal_qa", "source": files["bns_qa"]["repo"],
                    "source_revision": files["bns_qa"]["revision"], "source_row": line,
                    "source_id": f"GSMS_BNS_QA_{line:04d}", "source_sections": [f"bns_2023:{sid}"],
                    "target_provision_id": "BNS_" + sid, "question_type": row["question_type"],
                    "license": files["bns_qa"]["license"], "split": "train",
                    "review_status": "automated_screen_pass_not_semantically_certified",
                    "legal_text_relation": relation, "legal_title_relation": title_relation}
            train.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            mapping.write(json.dumps(meta, ensure_ascii=False, separators=(",", ":")) + "\n")
    summary = {"source": files["bns_qa"]["repo"], "revision": files["bns_qa"]["revision"],
               "total_bns_qa": len(qa), "screen_passed": passed,
               "selected_auxiliary_train": selected, "screen_passed_research_only": passed - selected,
               "held": len(qa) - passed, "issues": dict(issue_counts),
               "text_relations": dict(text_relation_counts),
               "trust_level": "automated_screen_pass_not_semantically_certified",
               "scope": "BNS legal Q&A only; no complaint labels or IT Act rows. Scenario/consequence answers held from training because the task wording can teach overconfident or speculative responses.",
               "input_sha256": {key: files[key]["sha256"] for key in ("bns_structured", "bns_qa")},
               "file_sha256": {name: sha(OUT / name) for name in
                               ("audit.jsonl", "auxiliary_train_sft.jsonl", "auxiliary_train_map.jsonl")}}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "file_sha256"}, indent=2))


if __name__ == "__main__":
    main()
