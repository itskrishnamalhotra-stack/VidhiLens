"""Add the nine-section research expansion to the existing mixed SFT candidate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "exports" / "mixed-source-v1"
GAP = ROOT / "data_drafts" / "gap_examples_v2"
CORRECTED = ROOT / "review_automation" / "complaint_pool_v2" / "corrected_source_train.jsonl"
CORRECTED_SUMMARY = ROOT / "review_automation" / "complaint_pool_v2" / "priority_source_summary.json"
OUT = ROOT / "exports" / "mixed-source-v2-research"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream: yield json.loads(line)


def main() -> None:
    old = json.loads((V1 / "manifest.json").read_text(encoding="utf-8"))
    gap = json.loads((GAP / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in old["files_sha256"].items():
        if digest(V1 / name) != expected: raise ValueError(f"V1 changed: {name}")
    for split, expected in gap["files_sha256"].items():
        if digest(GAP / f"{split}.jsonl") != expected: raise ValueError(f"Gap set changed: {split}")
    source_review = json.loads(CORRECTED_SUMMARY.read_text(encoding="utf-8"))
    if digest(CORRECTED) != source_review["corrected_train_sha256"]:
        raise ValueError("Corrected public source rows changed")
    OUT.mkdir(parents=True, exist_ok=True)
    counts = {}
    for split in ("train", "dev"):
        source_rows = list(read(V1 / f"{split}_sft.jsonl"))
        source_maps = list(read(V1 / f"{split}_sft_map.jsonl"))
        if len(source_rows) != len(source_maps): raise ValueError("V1 mapping mismatch")
        gap_rows = list(read(GAP / f"{split}.jsonl"))
        with (OUT / f"{split}_sft.jsonl").open("w", encoding="utf-8", newline="\n") as data_file, \
             (OUT / f"{split}_sft_map.jsonl").open("w", encoding="utf-8", newline="\n") as map_file:
            for row, mapping in zip(source_rows, source_maps, strict=True):
                data_file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                map_file.write(json.dumps(mapping, ensure_ascii=False, separators=(",", ":")) + "\n")
            for row in gap_rows:
                data_file.write(json.dumps({"messages": row["messages"]}, ensure_ascii=False,
                                           separators=(",", ":")) + "\n")
                map_file.write(json.dumps({"source": "local_nine_section_research",
                                           "source_id": row["id"], **row["metadata"]},
                                          ensure_ascii=False, separators=(",", ":")) + "\n")
            if split == "train":
                for row in read(CORRECTED):
                    data_file.write(json.dumps({"messages": row["messages"]}, ensure_ascii=False,
                                               separators=(",", ":")) + "\n")
                    map_file.write(json.dumps({"source_id": row["id"], **row["metadata"]},
                                              ensure_ascii=False, separators=(",", ":")) + "\n")
        counts[split] = {"prior": len(source_rows), "new_research": len(gap_rows),
                         "corrected_public": source_review["accepted_corrected"] if split == "train" else 0,
                         "total": len(source_rows) + len(gap_rows) +
                                  (source_review["accepted_corrected"] if split == "train" else 0)}
    manifest = {
        "status": "trainer_format_research_candidate_not_final_model_release",
        "counts": counts,
        "new_sections": gap["sections_added_as_research_cases"],
        "sealed_test_excluded": gap["counts"]["sealed_test"],
        "sealed_test_location": gap["sealed_test_path"],
        "limits": [
            "New section examples are AI-authored research cases and require evaluation before app suggestions are enabled.",
            "External grounded QA answers are publisher-gated and not individually legal-checked by this project.",
            "The expanded file is ready to load into a trainer, but its size does not prove model reliability or full-Act coverage.",
        ],
        "files_sha256": {name: digest(OUT / name) for name in
                         ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
