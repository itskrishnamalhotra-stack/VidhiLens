"""Cross-check Part 2 research coverage, trainer bundle, source hashes, and SQLite pins."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import zlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
BUNDLE = ROOT / "exports" / "complaint_training_v8_research_candidate"
PER_SECTION = ROOT / "review_automation" / "training_readiness_v6" / "per_section.csv"
OUT = ROOT / "review_automation" / "part2_final_v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files_sha256"].items():
        if sha(BUNDLE / name) != expected:
            raise ValueError(f"Bundle hash mismatch: {name}")
    laws = {}
    with sqlite3.connect(DB) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Master database integrity failure")
        laws = {pid: (status, kind, text) for pid, status, kind, text in conn.execute(
            "SELECT provision_id,legal_status,provision_kind,verified_text FROM provision")}
        pointer = conn.execute("SELECT value FROM master_dataset_info WHERE key='current_complaint_training_bundle'").fetchone()[0]
        if pointer != BUNDLE.relative_to(ROOT).as_posix() + "/manifest.json":
            raise ValueError("Master database points to a different training bundle")
        pinned = 0
        for name in (*manifest["files_sha256"], "manifest.json"):
            path = BUNDLE / name
            record = conn.execute("""SELECT a.sha256,b.content FROM dataset_artifact a
                JOIN dataset_artifact_blob b USING (artifact_key) WHERE a.relative_path=?""",
                (path.relative_to(ROOT).as_posix(),)).fetchone()
            if not record or record[0] != sha(path) or zlib.decompress(record[1]) != path.read_bytes():
                raise ValueError(f"Master artifact mismatch: {name}")
            pinned += 1
        research_counts = dict(conn.execute("SELECT split,count(*) FROM research_sft_record GROUP BY split"))
        research_pointer = conn.execute(
            "SELECT value FROM master_dataset_info WHERE key='current_research_export'").fetchone()[0]
        research_manifest = json.loads((ROOT / research_pointer).read_text(encoding="utf-8"))
        if research_counts != {"train": research_manifest["counts"]["train"],
                               "dev": research_manifest["counts"]["dev"], "sealed_test": 55}:
            raise ValueError(f"Research database counts changed: {research_counts}")
    rows = list(csv.DictReader(PER_SECTION.open(encoding="utf-8")))
    eligible = {pid for pid, (status, kind, text) in laws.items()
                if status == "in_force" and kind == "offence" and text}
    if len(rows) != 297 or {r["provision_id"] for r in rows} != eligible:
        raise ValueError("Readiness audit misses eligible offence sections")
    if any(int(r["candidate_train_positive"]) < 2 or int(r["candidate_train_missing_fact"]) < 1 for r in rows):
        raise ValueError("Part 2 positive or uncertainty floor not met")
    counts = {"train": Counter(), "dev": Counter()}
    checks = Counter()
    ids = set()
    for split in ("train", "dev"):
        with (BUNDLE / f"{split}_sft.jsonl").open(encoding="utf-8") as data, \
             (BUNDLE / f"{split}_sft_map.jsonl").open(encoding="utf-8") as mapping:
            for data_line, map_line in zip(data, mapping, strict=True):
                row, meta = json.loads(data_line), json.loads(map_line)
                family = meta.get("kind") or meta.get("task_family")
                if family not in ("triage", "workflow", "candidate_check"):
                    raise ValueError(f"Unknown task family: {family}")
                counts[split][family] += 1
                if family == "candidate_check":
                    if split != "train" or meta["split"] != "train":
                        raise ValueError("Candidate check appears outside training")
                    pid = meta["target_provision_id"]
                    answer = json.loads(row["messages"][-1]["content"])
                    if answer["label"] != meta["label"] or pid not in eligible:
                        raise ValueError(f"Candidate-check target mismatch: {meta['source_id']}")
                    if hashlib.sha256(laws[pid][2].encode()).hexdigest() != meta["verified_text_sha256"]:
                        raise ValueError(f"Statutory text changed: {pid}")
                    sid = meta["source_id"]
                    if sid in ids:
                        raise ValueError(f"Repeated candidate-check ID: {sid}")
                    ids.add(sid)
                    checks[(pid, answer["label"])] += 1
    if dict(counts["train"]) != {"triage": 3866, "workflow": 52, "candidate_check": 605}:
        raise ValueError(f"Training task counts changed: {counts['train']}")
    if dict(counts["dev"]) != {"triage": 57, "workflow": 3}:
        raise ValueError(f"Development task counts changed: {counts['dev']}")
    if any(checks[(pid, "uncertain")] < 1 or checks[(pid, "unsupported")] < 1 for pid in eligible):
        raise ValueError("A section lacks unknown or contradicted fact checks")
    report = {"status": "part2_research_dataset_complete_for_current_297_offence_scope",
              "eligible_offence_sections": len(eligible),
              "sections_with_positive_train_floor_2": sum(int(r["candidate_train_positive"]) >= 2 for r in rows),
              "sections_with_missing_fact_triage_train": sum(int(r["candidate_train_missing_fact"]) >= 1 for r in rows),
              "sections_with_unknown_and_unsupported_candidate_checks": len(eligible),
              "counts": {k: dict(v) for k, v in counts.items()},
              "research_db_counts": research_counts,
              "bundle_files_pinned_in_master": pinned,
              "bundle_manifest_sha256": sha(BUNDLE / "manifest.json"),
              "remaining": ["Independent positive, uncertainty, and confuser development/sealed complaints (Part 3).",
                            "Separate legal-Q&A quality screen and mixture decision (Part 4).",
                            "Real model evaluation in Colab before any app reliability claim."],
              "limits": ["All new Part 2 labels are AI-authored research candidates, not legal certification.",
                         "The 278-section matrix uses compact, similar wording; performance must be measured on independently written cases.",
                         "The 19-section recommendation release gate is unchanged."]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
