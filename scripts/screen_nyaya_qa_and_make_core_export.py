"""Inventory Nyaya v3 legal Q&A and make a task-safe research export.

All publisher Q&A is retained in the prior export. This screen does not certify
answers or convert the publisher's labels into complaint supervision.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "exports" / "mixed-source-v15-gsms-aux-research"
OUT = ROOT / "exports" / "mixed-source-v16-core-gsms-research"
AUDIT = ROOT / "review_automation" / "nyaya_qa_v1"
DB = ROOT / "db" / "master_dataset.sqlite"
FILES = ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")
TARGET_ACTS = {"bns_2023", "it_act_2000"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    original = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    for filename in FILES:
        if sha(BASE / filename) != original["files_sha256"][filename]:
            raise ValueError(f"Base research export changed: {filename}")
    with sqlite3.connect(DB) as conn:
        statuses = dict(conn.execute("SELECT provision_id,legal_status FROM provision"))
    OUT.mkdir(parents=True, exist_ok=True)
    AUDIT.mkdir(parents=True, exist_ok=True)
    source_counts, issues = Counter(), Counter()
    excluded = []
    kept = Counter()
    with (AUDIT / "audit.jsonl").open("w", encoding="utf-8", newline="\n") as audit:
        for split in ("train", "dev"):
            data_in, map_in = BASE / f"{split}_sft.jsonl", BASE / f"{split}_sft_map.jsonl"
            data_out, map_out = OUT / f"{split}_sft.jsonl", OUT / f"{split}_sft_map.jsonl"
            with data_in.open(encoding="utf-8") as data, map_in.open(encoding="utf-8") as mapping, \
                 data_out.open("w", encoding="utf-8", newline="\n") as target, \
                 map_out.open("w", encoding="utf-8", newline="\n") as target_map:
                for line_no, (data_line, map_line) in enumerate(zip(data, mapping, strict=True), 1):
                    meta = json.loads(map_line)
                    family = meta.get("task_family") or meta.get("kind")
                    if family != "grounded_legal_qa":
                        target.write(data_line)
                        target_map.write(map_line)
                        kept[split] += 1
                        continue
                    if meta.get("source") != "NyayaLabs98/nyaya-train-v3":
                        raise ValueError(f"Unexpected grounded Q&A source at {split}:{line_no}")
                    record = json.loads(data_line)
                    messages = record.get("messages", [])
                    prompt = "\n".join(str(x.get("content", "")) for x in messages if x.get("role") == "user")
                    answer = "\n".join(str(x.get("content", "")) for x in messages if x.get("role") == "assistant")
                    refs = meta.get("source_sections") or []
                    act = meta.get("source_act")
                    row_issues = []
                    if act not in TARGET_ACTS:
                        row_issues.append("outside_BNS_IT_scope")
                    if not refs:
                        row_issues.append("no_source_section")
                    if not prompt.strip() or not answer.strip() or len(messages) != 3:
                        row_issues.append("malformed_chat")
                    if "Relevant provisions of current Indian law" in prompt:
                        row_issues.append("contains_supplied_statute_passage")
                    if len(prompt) > 4000:
                        row_issues.append("long_supplied_prompt_over_4000_characters")
                    if "Question:" not in prompt:
                        row_issues.append("question_boundary_missing")
                    if meta.get("review_status") != "publisher_gated_not_independently_legal_reviewed":
                        row_issues.append("unexpected_review_status")
                    bad_law = []
                    for ref in refs:
                        if ":" not in ref:
                            bad_law.append(ref)
                            continue
                        code, number = ref.split(":", 1)
                        pid = ("BNS_" if code == "bns_2023" else "ITA_" if code == "it_act_2000" else "") + number
                        if code in TARGET_ACTS and statuses.get(pid) != "in_force":
                            bad_law.append(ref)
                    if bad_law:
                        row_issues.append("source_section_not_confirmed_in_force")
                    row_issues = sorted(set(row_issues))
                    source_counts[split] += 1
                    issues.update(row_issues)
                    outcome = {"split": split, "base_line": line_no, "source_id": meta.get("source_id"),
                               "source_row": meta.get("source_row"), "source_act": act,
                               "source_sections": refs, "task_type": meta.get("task_type"),
                               "question": prompt.rsplit("Question:", 1)[-1].strip()[:400],
                               "issues": row_issues, "decision": "hold_from_core_training_pending_answer_review"}
                    audit.write(json.dumps(outcome, ensure_ascii=False) + "\n")
                    excluded.append((split, line_no, meta.get("source_id")))
    if source_counts != {"train": 5259, "dev": 280}:
        raise ValueError(f"Nyaya Q&A counts changed: {source_counts}")
    if kept != {"train": 5606, "dev": 60}:
        raise ValueError(f"Core research count changed: {kept}")
    manifest = {
        "status": "trainer_format_core_research_candidate_not_final_model_release",
        "counts": {"train": kept["train"], "dev": kept["dev"],
                   "nyaya_qa_train_held_separately": source_counts["train"],
                   "nyaya_qa_dev_held_separately": source_counts["dev"]},
        "purpose": "Core complaint/workflow/GSMS auxiliary experiment without publisher-unreviewed Nyaya Q&A.",
        "limits": ["GSMS auxiliary Q&A is screen-passed, not semantically certified.",
                   "This export is a research candidate, not a release approval for all 297 sections.",
                   "The original Nyaya Q&A remains hash-pinned in the v15 export and master source inventory.",
                   "Final Q&A mixing weight requires comparison on independent complaint development cases."],
        "input_sha256": {"base_manifest": sha(BASE / "manifest.json")},
        "files_sha256": {filename: sha(OUT / filename) for filename in FILES},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summary = {"screened_rows": sum(source_counts.values()), "split_counts": dict(source_counts),
               "held_from_core_training": len(excluded), "issue_counts": dict(issues),
               "core_training_counts": dict(kept),
               "interpretation": "Issue counts overlap; even a row with no mechanical issue remains unverified legal Q&A. All Nyaya v3 Q&A is held from the core training candidate.",
               "audit_sha256": sha(AUDIT / "audit.jsonl"),
               "base_manifest_sha256": sha(BASE / "manifest.json"),
               "core_manifest_sha256": sha(OUT / "manifest.json")}
    (AUDIT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
