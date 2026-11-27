"""Append source-grounded section-floor research cases to the mixed trainer export."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "exports" / "mixed-source-v2-research"
FLOOR = ROOT / "data_drafts" / "section_floor_v1"
GAP = ROOT / "data_drafts" / "gap_examples_v2"
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "exports" / "mixed-source-v3-research"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def normalize(s: str) -> str:
    return " ".join(re.findall(r"\w+", s.casefold()))


def main() -> None:
    base_manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    floor_manifest = json.loads((FLOOR / "manifest.json").read_text(encoding="utf-8"))
    gap_manifest = json.loads((GAP / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in base_manifest["files_sha256"].items():
        if digest(BASE / name) != expected:
            raise ValueError(f"Base export changed: {name}")
    if digest(FLOOR / "train.jsonl") != floor_manifest["train_sha256"]:
        raise ValueError("Section-floor examples changed")
    if digest(GAP / "sealed_test.jsonl") != gap_manifest["files_sha256"]["sealed_test"]:
        raise ValueError("Sealed test changed")

    floor_rows = list(read(FLOOR / "train.jsonl"))
    existing_rows = list(read(BASE / "train_sft.jsonl"))
    dev_rows = list(read(BASE / "dev_sft.jsonl"))
    sealed_rows = list(read(GAP / "sealed_test.jsonl"))
    if len(floor_rows) != 269 or len(existing_rows) != base_manifest["counts"]["train"]["total"]:
        raise ValueError("Unexpected counts")
    seen_texts = set()
    for row in existing_rows + dev_rows + sealed_rows:
        user_text = " ".join(m["content"] for m in row["messages"] if m["role"] == "user")
        seen_texts.add(normalize(user_text))
    with sqlite3.connect(DB) as conn:
        eligible = {p for (p,) in conn.execute("SELECT provision_id FROM provision WHERE legal_status='in_force' AND provision_kind='offence'")}
        pilot = {p for (p,) in conn.execute("SELECT provision_id FROM recommendable_provision")}
    prior = set(gap_manifest["sections_added_as_research_cases"])
    floor_ids = set()
    for row in floor_rows:
        pid = row["metadata"]["target_provision_id"]
        if pid in floor_ids:
            raise ValueError(f"Duplicate floor provision: {pid}")
        floor_ids.add(pid)
        user_text = " ".join(m["content"] for m in row["messages"] if m["role"] == "user")
        normal = normalize(user_text)
        if normal in seen_texts:
            raise ValueError(f"Duplicate or leaked input: {pid}")
        seen_texts.add(normal)
    if floor_ids & (pilot | prior):
        raise ValueError("Floor overlaps an existing provision group")
    if pilot | prior | floor_ids != eligible:
        raise ValueError(f"Provision coverage mismatch: {sorted(eligible - (pilot | prior | floor_ids))}")

    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("dev_sft.jsonl", "dev_sft_map.jsonl"):
        (OUT / name).write_bytes((BASE / name).read_bytes())
    with (OUT / "train_sft.jsonl").open("w", encoding="utf-8", newline="\n") as data, \
         (OUT / "train_sft_map.jsonl").open("w", encoding="utf-8", newline="\n") as mapping:
        data.write((BASE / "train_sft.jsonl").read_text(encoding="utf-8"))
        mapping.write((BASE / "train_sft_map.jsonl").read_text(encoding="utf-8"))
        for row in floor_rows:
            data.write(json.dumps({"messages": row["messages"]}, ensure_ascii=False, separators=(",", ":")) + "\n")
            mapping.write(json.dumps({"source": "local_section_floor_research", "source_id": row["id"],
                                      **row["metadata"]}, ensure_ascii=False, separators=(",", ":")) + "\n")

    names = ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")
    manifest = {
        "status": "trainer_format_research_candidate_not_final_model_release",
        "counts": {"train": len(existing_rows) + len(floor_rows), "dev": len(dev_rows),
                   "new_section_floor_train": len(floor_rows), "sealed_test_kept_separate": len(sealed_rows)},
        "in_force_offence_coverage": {"total": len(eligible), "pilot": len(pilot),
                                       "earlier_research": len(prior), "section_floor_research": len(floor_ids)},
        "limits": ["The 269 section-floor cases are one AI-authored example per provision, not validated performance.",
                   "Some section examples are unnatural or overlap nearby legal provisions; evaluate before any live recommendation.",
                   "The 1,338 noisy public complaint rows were excluded by source-level rule, not individually fact-to-law reviewed.",
                   "External legal QA records have different supervision from complaint-to-provision records."],
        "files_sha256": {name: digest(OUT / name) for name in names},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
