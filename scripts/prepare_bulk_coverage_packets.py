"""Prepare two 128-section, source-grounded review packets in one pass.

This does not convert a publisher QA question into an approved complaint label.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
COVERAGE = ROOT / "review_automation" / "research_coverage_v9" / "per_offence.csv"
QA = ROOT / "review_automation" / "qa_incident_screen_v1" / "candidates.csv"
OUT = ROOT / "review_automation" / "bulk_coverage_packets_v3"


def strict_qa(row: dict) -> bool:
    question = row["question"].lower()
    return (int(row["word_count"]) >= 25
            and not any(term in question for term in
                        ("section ", "ipc", "bns", "punishment", "penalty", "provision"))
            and "@" not in question and "http" not in question)


def main() -> None:
    with COVERAGE.open(encoding="utf-8", newline="") as stream:
        coverage = list(csv.DictReader(stream))
    gap = [row for row in coverage if not
           (int(row["train_positive"]) >= 5 and int(row["dev_positive"]) >= 1
            and int(row["sealed_positive"]) >= 2)]
    if len(gap) != 256:
        raise ValueError(f"Expected 256 count-floor gaps, found {len(gap)}")
    candidates = defaultdict(list)
    with QA.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if strict_qa(row):
                candidates[row["provision_id"]].append(row)
    packets = []
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        examples_by_pid = defaultdict(list)
        for record in conn.execute("""SELECT target_provision_id,data_json,metadata_json
            FROM research_sft_record WHERE split='train' AND task_kind='triage'
            AND target_provision_id IS NOT NULL ORDER BY source_line"""):
            pid = record["target_provision_id"]
            if len(examples_by_pid[pid]) >= 6:
                continue
            data, meta = json.loads(record["data_json"]), json.loads(record["metadata_json"])
            answer = json.loads(data["messages"][-1]["content"])
            if pid not in answer.get("possible_provision_ids", []):
                continue
            examples_by_pid[pid].append({
                "source_id": meta.get("source_id") or meta.get("scenario_id"),
                "complaint": next(m["content"] for m in data["messages"] if m["role"] == "user")})
        for summary in gap:
            pid = summary["provision_id"]
            law = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            if not law or law["legal_status"] != "in_force" or law["provision_kind"] != "offence":
                raise ValueError(f"Coverage law mismatch: {pid}")
            blocked_subparts = [dict(zip(("subpart", "legal_status", "source_id", "note"), row))
                                for row in conn.execute("""SELECT subpart,legal_status,source_id,note
                                    FROM provision_subpart_status WHERE provision_id=?
                                    AND legal_status!='in_force'""", (pid,))]
            packet = {
                "provision_id": pid, "act_id": law["act_id"],
                "section_number": law["section_number"], "title": law["candidate_title"],
                "source_id": law["source_id"], "source_pdf_page": law["source_pdf_page"],
                "verified_text_sha256": hashlib.sha256(law["verified_text"].encode()).hexdigest(),
                "verified_text": law["verified_text"],
                "blocked_subparts": blocked_subparts,
                "current_positive_counts": {k: int(summary[f"{k}_positive"])
                                            for k in ("train", "dev", "sealed")},
                "minimum_new_positive_counts": {k: int(summary[f"{k}_needed_for_count_floor"])
                                                for k in ("train", "dev", "sealed")},
                "existing_positive_train_examples": examples_by_pid[pid],
                "publisher_qa_incident_candidates": [
                    {"record_key": row["record_key"], "source_id": row["source_id"],
                     "question": row["question"]} for row in
                    ([] if blocked_subparts else candidates[pid])],
                "review_rule": "Read the verified statute and each question. Approve only if the question states all material elements, exceptions and mental state; otherwise mark it missing-fact or reject. Do not put a pre-existing QA question in dev/sealed because its answer is already in train.",
            }
            packets.append(packet)
    packets.sort(key=lambda p: (-len(p["publisher_qa_incident_candidates"]),
                                -p["current_positive_counts"]["train"],
                                p["act_id"], p["section_number"]))
    OUT.mkdir(parents=True, exist_ok=True)
    for number, subset in ((1, packets[:128]), (2, packets[128:])):
        with (OUT / f"half_{number:02d}.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
            for packet in subset:
                stream.write(json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + "\n")
    summary = {"status": "review_packets_only_no_training_approval",
               "total_sections": len(packets), "sections_per_half": [128, 128],
               "sections_with_strict_qa_candidates": sum(bool(p["publisher_qa_incident_candidates"])
                                                       for p in packets),
               "strict_qa_candidate_rows": sum(len(p["publisher_qa_incident_candidates"])
                                               for p in packets),
               "minimum_new_positive_cases": {
                   k: sum(p["minimum_new_positive_counts"][k] for p in packets)
                   for k in ("train", "dev", "sealed")},
               "half_one_candidate_sections": sum(bool(p["publisher_qa_incident_candidates"])
                                                  for p in packets[:128]),
               "half_one_train_positive_needed": sum(p["minimum_new_positive_counts"]["train"]
                                                     for p in packets[:128]),
               "input_sha256": {"coverage": hashlib.sha256(COVERAGE.read_bytes()).hexdigest(),
                                "qa_candidates": hashlib.sha256(QA.read_bytes()).hexdigest()},
               "file_sha256": {f"half_{number:02d}.jsonl": hashlib.sha256(
                   (OUT / f"half_{number:02d}.jsonl").read_bytes()).hexdigest()
                   for number in (1, 2)}}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
