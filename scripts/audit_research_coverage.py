"""Audit case coverage across the current research export and held-out sets.

Positive counts are inventory only, not model accuracy or legal approval.
"""

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "exports" / "mixed-source-v14-research"
DB = ROOT / "db" / "master_dataset.sqlite"
DEFAULT_SEALED = [ROOT / "data_drafts" / "gap_examples_v2" / "sealed_test.jsonl",
                  ROOT / "data_drafts" / "coverage_batch08_checked" / "sealed_test.jsonl",
                  ROOT / "data_drafts" / "coverage_batch09_checked" / "sealed_test.jsonl",
                  ROOT / "data_drafts" / "coverage_batch10_checked" / "sealed_test.jsonl",
                  ROOT / "data_drafts" / "coverage_batch11_checked" / "sealed_test.jsonl",
                  ROOT / "data_drafts" / "coverage_batch12_checked" / "sealed_test.jsonl",
                  ROOT / "data_drafts" / "coverage_batch13_checked" / "sealed_test.jsonl",
                  ROOT / "data_drafts" / "coverage_batch14_checked" / "sealed_test.jsonl",
                  ROOT / "data_drafts" / "coverage_batch15_checked" / "sealed_test.jsonl",
                  ROOT / "data_drafts" / "coverage_batch16_checked" / "sealed_test.jsonl"]
OUT = ROOT / "review_automation" / "research_coverage_v14"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--sealed", type=Path, action="append")
    args = parser.parse_args()
    base, out = args.base.resolve(), args.out.resolve()
    sealed_paths = [p.resolve() for p in (args.sealed or DEFAULT_SEALED)]
    if len(sealed_paths) != len(set(sealed_paths)):
        raise ValueError("Duplicate sealed file")
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files_sha256"].items():
        if sha(base / name) != expected:
            raise ValueError(f"Research export changed: {name}")
    for sealed_path in sealed_paths:
        batch_manifest = sealed_path.with_name("manifest.json")
        if batch_manifest.exists():
            expected = json.loads(batch_manifest.read_text(encoding="utf-8"))["files_sha256"].get("sealed_test")
            if expected != sha(sealed_path):
                raise ValueError(f"Sealed file changed: {sealed_path}")
    count = defaultdict(Counter)
    for split in ("train", "dev"):
        with (base / f"{split}_sft.jsonl").open(encoding="utf-8") as data, \
             (base / f"{split}_sft_map.jsonl").open(encoding="utf-8") as mapping:
            for row_line, meta_line in zip(data, mapping, strict=True):
                meta = json.loads(meta_line)
                if meta.get("kind") != "triage":
                    continue
                answer = json.loads(json.loads(row_line)["messages"][-1]["content"])
                for pid in answer.get("possible_provision_ids", []):
                    count[pid][split] += 1
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        laws = conn.execute("""SELECT provision_id,act_id,section_number,candidate_title,
            source_id,source_pdf_page,verified_text,recommendable FROM provision
            WHERE legal_status='in_force' AND provision_kind='offence'
            ORDER BY act_id,CAST(section_number AS INTEGER),section_number""").fetchall()
        for pid, n in conn.execute("""SELECT l.provision_id,count(*) FROM scenario_provision_label l
            JOIN scenario s USING(scenario_id) WHERE l.label='possible'
            AND s.split='sealed_test' AND s.quality_status='accepted'
            GROUP BY l.provision_id"""):
            count[pid]["sealed"] += n
    for sealed_path in sealed_paths:
        for line in sealed_path.open(encoding="utf-8"):
            answer = json.loads(json.loads(line)["messages"][-1]["content"])
            for pid in answer.get("possible_provision_ids", []):
                count[pid]["sealed"] += 1
    rows = []
    for law in laws:
        pid = law["provision_id"]
        if not law["verified_text"]:
            raise ValueError(f"Missing verified text: {pid}")
        x = count[pid]
        rows.append({"provision_id": pid, "act_id": law["act_id"],
                     "section_number": law["section_number"], "title": law["candidate_title"],
                     "source_id": law["source_id"], "source_pdf_page": law["source_pdf_page"],
                     "verified_text_sha256": hashlib.sha256(law["verified_text"].encode()).hexdigest(),
                     "recommendable": law["recommendable"], "train_positive": x["train"],
                     "dev_positive": x["dev"], "sealed_positive": x["sealed"],
                     "train_needed_for_count_floor": max(0, 5 - x["train"]),
                     "dev_needed_for_count_floor": max(0, 1 - x["dev"]),
                     "sealed_needed_for_count_floor": max(0, 2 - x["sealed"])})
    if len(rows) != 297 or any(r["train_positive"] == 0 for r in rows):
        raise ValueError("Expected one research positive for each of 297 in-force offences")
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "per_offence.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "in_force_offences": len(rows),
        "currently_recommendable": sum(r["recommendable"] for r in rows),
        "research_positive_train_coverage": sum(r["train_positive"] > 0 for r in rows),
        "only_one_positive_train": sum(r["train_positive"] == 1 for r in rows),
        "no_positive_dev": sum(r["dev_positive"] == 0 for r in rows),
        "no_positive_sealed": sum(r["sealed_positive"] == 0 for r in rows),
        "meeting_positive_count_floor": sum(r["train_positive"] >= 5 and
                                            r["dev_positive"] >= 1 and
                                            r["sealed_positive"] >= 2 for r in rows),
        "minimum_additional_cases_for_count_floor": {
            split: sum(r[f"{split}_needed_for_count_floor"] for r in rows)
            for split in ("train", "dev", "sealed")},
        "limits": ["Count floors do not prove legal accuracy or model reliability.",
                   "Distinct negative and missing-fact cases, family split checks, and later model evaluation remain necessary."],
        "research_manifest_sha256": sha(base / "manifest.json"),
        "sealed_sources_sha256": {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): sha(p)
                                  for p in sealed_paths},
        "coverage_csv_sha256": sha(csv_path),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
