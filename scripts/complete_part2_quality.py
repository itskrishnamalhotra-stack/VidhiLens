"""Remove answer cues from Part 2 examples and pin a versioned SFT export."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import zlib
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
BASE = ROOT / "exports" / "complaint_training_v9_step1_research_candidate"
OLD_MIXED = ROOT / "exports" / "mixed-source-v20-step1-nyaya-experiment"
OUT = ROOT / "exports" / "complaint_training_v10_step2_research_candidate"
MIXED = ROOT / "exports" / "mixed-source-v21-step2-nyaya-experiment"
AUDIT = ROOT / "review_automation" / "part2_quality_final_v1"
REVISIONS = ROOT / "data_drafts" / "step2_missing_fact_revisions_v1.psv"
TAIL = " The report is incomplete, and I can provide more details about what happened if I am asked a specific follow-up question."
QUESTION_TAIL = " I need to know that detail before assessing this particular section."
NEG_INTRO = "A later check established this additional fact: "
NEG_TAIL = " Other issues may still need examination."
REASON_TAIL = " This candidate section is unsupported on the reported facts; other provisions may still apply."


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(folder: Path) -> dict:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files_sha256"].items():
        if sha(folder / name) != digest:
            raise ValueError(f"Changed input: {folder.name}/{name}")
    return manifest


def read_lines(path: Path) -> list[str]:
    rows = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not rows or any(not row.endswith("\n") for row in rows):
        raise ValueError(f"Malformed JSONL: {path}")
    return rows


def encode(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"


def main() -> None:
    if any(folder.exists() for folder in (OUT, MIXED, AUDIT)):
        raise ValueError("Versioned output exists; refuse to overwrite")
    base, old_mixed = verify(BASE), verify(OLD_MIXED)
    if base["train_total"] != 4538 or old_mixed["counts"]["train"] != 8107:
        raise ValueError("Unexpected parent sizes")
    revisions = {}
    for line in REVISIONS.read_text(encoding="utf-8").splitlines():
        pid, complaint, gap = line.split("|", 2)
        if pid in revisions or len(complaint.split()) < 20 or not gap or re.search(r"\bsection\s*\d+", complaint, re.I):
            raise ValueError(f"Invalid manual case: {pid}")
        revisions[pid] = (complaint, gap)
    if len(revisions) != 18:
        raise ValueError(f"Expected 18 concrete rewrites, got {len(revisions)}")
    with sqlite3.connect(DB) as conn:
        laws = {pid: hashlib.sha256(text.encode()).hexdigest() for pid, text in conn.execute(
            "SELECT provision_id,verified_text FROM provision WHERE legal_status='in_force' "
            "AND provision_kind='offence' AND verified_text IS NOT NULL")}
    if len(laws) != 297 or not set(revisions) <= set(laws):
        raise ValueError("Law scope changed")

    train_data = read_lines(BASE / "train_sft.jsonl")
    train_map = read_lines(BASE / "train_sft_map.jsonl")
    if len(train_data) != len(train_map):
        raise ValueError("Parent train alignment failure")
    counters = Counter()
    edit_ledger = []
    seen_manual = set()
    for index, (data_line, map_line) in enumerate(zip(train_data, train_map, strict=True)):
        row, meta = json.loads(data_line), json.loads(map_line)
        sid = meta.get("source_id", "")
        kind = meta.get("kind") or meta.get("task_family")
        edit = None
        if kind == "triage" and sid.startswith("p2-triage-"):
            complaint = row["messages"][1]["content"]
            if not complaint.endswith(TAIL):
                raise ValueError(f"Unexpected triage template: {sid}")
            pid = meta["target_provision_id"]
            output = json.loads(row["messages"][-1]["content"])
            if output["outcome"] != "insufficient_information" or output["uncertain_sections"][0]["provision_id"] != pid:
                raise ValueError(f"Incorrect triage target: {sid}")
            if pid in revisions:
                complaint, gap = revisions[pid]
                output["uncertain_sections"][0]["missing_facts"] = gap
                row["messages"][-1]["content"] = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
                seen_manual.add(pid)
                edit = "natural_uncertainty_rewrite"
            else:
                complaint = complaint[:-len(TAIL)]
                edit = "remove_generic_report_tail"
            row["messages"][1]["content"] = complaint
            counters[edit] += 1
        elif kind == "candidate_check" and sid.startswith("p2-full-"):
            user = json.loads(row["messages"][1]["content"])
            output = json.loads(row["messages"][-1]["content"])
            complaint = user["complaint"]
            pid = meta["target_provision_id"]
            if user["candidate_provision_id"] != pid or output["label"] != meta["label"]:
                raise ValueError(f"Candidate-check misalignment: {sid}")
            if output["label"] == "uncertain":
                if not complaint.endswith(QUESTION_TAIL) or len(output["missing_facts"]) != 1:
                    raise ValueError(f"Unexpected uncertain pattern: {sid}")
                complaint = complaint[:-len(QUESTION_TAIL)]
                gap = output["missing_facts"][0].rstrip(".")
                output["reason"] = "The report leaves unresolved " + gap[0].lower() + gap[1:] + "."
                edit = "remove_analysis_cue_and_specific_reason"
            elif output["label"] == "unsupported":
                if NEG_INTRO in complaint:
                    complaint = complaint.replace(NEG_INTRO, "")
                    if not complaint.endswith(NEG_TAIL):
                        raise ValueError(f"Unexpected unsupported tail: {sid}")
                    complaint = complaint[:-len(NEG_TAIL)]
                    if output["reason"].endswith(REASON_TAIL):
                        output["reason"] = output["reason"][:-len(REASON_TAIL)] + "."
                    edit = "remove_analysis_cue_from_unsupported"
                elif sid == "p2-full-BNS_65-n":
                    complaint = complaint.replace(" in BNS 65", "")
                    complaint = complaint.replace(" Other sexual-offence provisions may still need assessment.", "")
                    edit = "remove_section_hint_from_corrected_case"
                else:
                    raise ValueError(f"Unexpected unsupported pattern: {sid}")
            else:
                raise ValueError(f"Unknown candidate label: {sid}")
            user["complaint"] = complaint
            row["messages"][1]["content"] = json.dumps(user, ensure_ascii=False, separators=(",", ":"))
            row["messages"][-1]["content"] = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
            counters[edit] += 1
        if edit:
            pid = meta["target_provision_id"]
            if meta.get("verified_text_sha256") != laws[pid]:
                raise ValueError(f"Statutory hash changed: {sid}")
            meta["quality_revision"] = "part2_quality_v1"
            edit_ledger.append({"train_row": index + 1, "source_id": sid, "provision_id": pid,
                                "edit": edit, "old_data_sha256": hashlib.sha256(data_line.encode()).hexdigest(),
                                "new_data_sha256": hashlib.sha256(encode(row).encode()).hexdigest(),
                                "law_sha256": laws[pid]})
            train_data[index], train_map[index] = encode(row), encode(meta)
    if seen_manual != set(revisions) or dict(counters) != {
            "natural_uncertainty_rewrite": 18, "remove_generic_report_tail": 225,
            "remove_analysis_cue_and_specific_reason": 278,
            "remove_analysis_cue_from_unsupported": 277,
            "remove_section_hint_from_corrected_case": 1}:
        raise ValueError(f"Unanticipated edit counts: {counters}")

    OUT.mkdir(parents=True)
    (OUT / "train_sft.jsonl").write_text("".join(train_data), encoding="utf-8", newline="\n")
    (OUT / "train_sft_map.jsonl").write_text("".join(train_map), encoding="utf-8", newline="\n")
    for name in ("dev_sft.jsonl", "dev_sft_map.jsonl"):
        (OUT / name).write_bytes((BASE / name).read_bytes())
    complaint_manifest = {"status": "AI_reviewed_research_candidate_not_legal_certification",
                          "parent_manifest_sha256": sha(BASE / "manifest.json"),
                          "source_revisions_sha256": sha(REVISIONS),
                          "counts": base["counts"], "train_total": 4538, "dev_total": 60,
                          "quality_edits": dict(counters),
                          "files_sha256": {name: sha(OUT / name) for name in
                                           ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")},
                          "limits": ["Synthetic missing-fact and boundary examples still need independent model evaluation.",
                                     "This quality pass removes repeated answer cues; it does not certify all 297 legal labels.",
                                     "No sealed cases are in the trainer bundle; the app recommendation gate stays at 19."]}
    (OUT / "manifest.json").write_text(json.dumps(complaint_manifest, indent=2) + "\n", encoding="utf-8")

    mixed = {}
    for split in ("train", "dev"):
        for suffix in ("sft", "sft_map"):
            name = f"{split}_{suffix}.jsonl"
            parent_base_lines = read_lines(BASE / name)
            old_mixed_lines = read_lines(OLD_MIXED / name)
            if old_mixed_lines[:len(parent_base_lines)] != parent_base_lines:
                raise ValueError(f"Mixed parent does not contain exact v9 prefix: {name}")
            mixed[name] = read_lines(OUT / name) + old_mixed_lines[len(parent_base_lines):]
    if len(mixed["train_sft.jsonl"]) != 8107 or len(mixed["dev_sft.jsonl"]) != 60:
        raise ValueError("Mixed record count changed")
    MIXED.mkdir(parents=True)
    for name, rows in mixed.items():
        (MIXED / name).write_text("".join(rows), encoding="utf-8", newline="\n")
    mixed_manifest = {"status": "trainer_format_auxiliary_experiment_requires_model_evaluation",
                      "counts": old_mixed["counts"],
                      "complaint_bundle": OUT.relative_to(ROOT).as_posix() + "/manifest.json",
                      "parent_mixed_bundle": OLD_MIXED.relative_to(ROOT).as_posix() + "/manifest.json",
                      "input_sha256": {"complaint_manifest": sha(OUT / "manifest.json"),
                                      "mixed_parent_manifest": sha(OLD_MIXED / "manifest.json")},
                      "files_sha256": {name: sha(MIXED / name) for name in mixed},
                      "limits": ["Auxiliary legal Q&A remains experimental; use independent complaint tests to choose the mixture.",
                                 "No sealed cases are in this trainer export."]}
    (MIXED / "manifest.json").write_text(json.dumps(mixed_manifest, indent=2) + "\n", encoding="utf-8")

    counts = defaultdict(Counter)
    for row_line, meta_line in zip(train_data, train_map, strict=True):
        row, meta = json.loads(row_line), json.loads(meta_line)
        kind = meta.get("kind") or meta.get("task_family")
        if kind == "triage":
            output = json.loads(row["messages"][-1]["content"])
            if output.get("outcome") == "insufficient_information":
                for item in output.get("uncertain_sections", []):
                    counts[item["provision_id"]]["triage_uncertain"] += 1
        elif kind == "candidate_check":
            output = json.loads(row["messages"][-1]["content"])
            counts[meta["target_provision_id"]]["check_" + output["label"]] += 1
    if any(counts[pid][key] < 1 for pid in laws for key in
           ("triage_uncertain", "check_uncertain", "check_unsupported")):
        raise ValueError("A section lost its Step 2 coverage")
    if any(any(marker in line for marker in (TAIL, QUESTION_TAIL, NEG_INTRO)) for line in train_data):
        raise ValueError("A repeated Part 2 answer cue remains in training")

    AUDIT.mkdir(parents=True)
    with (AUDIT / "edit_ledger.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(edit_ledger[0]))
        writer.writeheader()
        writer.writerows(edit_ledger)
    summary = {"status": "part2_complete_with_quality_revision_as_research_data",
               "sections_with_triage_uncertainty_and_both_candidate_labels": len(laws),
               "candidate_check_train": sum(counts[pid]["check_uncertain"] + counts[pid]["check_unsupported"] for pid in laws),
               "quality_edits": dict(counters), "complaint_train": 4538,
               "mixed_train": 8107, "development": 60,
               "manual_revision_source_sha256": sha(REVISIONS),
               "edit_ledger_sha256": sha(AUDIT / "edit_ledger.csv"),
               "limits": complaint_manifest["limits"]}
    (AUDIT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    artifacts = [*(OUT / name for name in (*complaint_manifest["files_sha256"], "manifest.json")),
                 *(MIXED / name for name in (*mixed_manifest["files_sha256"], "manifest.json")),
                 AUDIT / "edit_ledger.csv", AUDIT / "summary.json", REVISIONS]
    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for path in artifacts:
            content = path.read_bytes()
            rel = path.relative_to(ROOT).as_posix()
            key = "part2quality:v1:" + rel.replace("/", ":")
            if conn.execute("SELECT 1 FROM dataset_artifact WHERE relative_path=?", (rel,)).fetchone():
                raise ValueError(f"Output path already pinned: {rel}")
            role = "trainer_format_sft" if path.parent in (OUT, MIXED) and path.suffix == ".jsonl" else "step2_audit"
            record_count = (4538 if path.parent == OUT else 8107) if path.name.startswith("train_") else (60 if path.name.startswith("dev_") else None)
            conn.execute("INSERT INTO dataset_artifact (artifact_key,role,relative_path,sha256,bytes,record_count,status,url,license) VALUES (?,?,?,?,?,?,?,NULL,NULL)",
                         (key, role, rel, sha(path), len(content), record_count, "AI_reviewed_research_candidate"))
            conn.execute("INSERT INTO dataset_artifact_blob VALUES (?,'zlib',?)", (key, zlib.compress(content, 9)))
        for key, val in (("current_complaint_training_bundle", OUT.relative_to(ROOT).as_posix() + "/manifest.json"),
                         ("part2_quality_audit", AUDIT.relative_to(ROOT).as_posix() + "/summary.json")):
            conn.execute("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)", (key, val))
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign-key failure")
        conn.commit()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
