"""Freeze a research export after excluding source-status-flagged legal Q&A.

The flagged inputs remain in the prior immutable export and audit ledger.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT / "exports" / "mixed-source-v8-research"
DEFAULT_OUT = ROOT / "exports" / "mixed-source-v9-research"
FLAGS = ROOT / "review_automation" / "qa_legal_status_v1" / "flagged.csv"
NAMES = ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    base, out = args.base.resolve(), args.out.resolve()
    if out == base:
        raise ValueError("Output must differ from base")
    prior = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    for name in NAMES:
        if sha(base / name) != prior["files_sha256"][name]:
            raise ValueError(f"Base export changed: {name}")
    with FLAGS.open(encoding="utf-8", newline="") as stream:
        flagged = {row["record_key"]: row for row in csv.DictReader(stream)}
    if not flagged:
        raise ValueError("Expected a nonempty flagged QA audit")
    out.mkdir(parents=True, exist_ok=True)
    removed = []
    counts = {}
    for split in ("train", "dev"):
        data_in, map_in = base / f"{split}_sft.jsonl", base / f"{split}_sft_map.jsonl"
        data_out, map_out = out / f"{split}_sft.jsonl", out / f"{split}_sft_map.jsonl"
        n = 0
        with data_in.open(encoding="utf-8") as data, map_in.open(encoding="utf-8") as mapping, \
             data_out.open("w", encoding="utf-8", newline="\n") as dst_data, \
             map_out.open("w", encoding="utf-8", newline="\n") as dst_map:
            for row_number, (data_line, meta_line) in enumerate(zip(data, mapping, strict=True), 1):
                key = f"{split}:{row_number:07d}"
                if key in flagged:
                    meta = json.loads(meta_line)
                    if meta.get("task_family") != "grounded_legal_qa":
                        raise ValueError(f"Flag unexpectedly targets non-QA: {key}")
                    removed.append({"old_record_key": key, "source_id": meta.get("source_id"),
                                    "issues": flagged[key]["issues"]})
                    continue
                dst_data.write(data_line)
                dst_map.write(meta_line)
                n += 1
        counts[split] = n
    if len(removed) != len(flagged):
        raise ValueError("Not every flagged record was found")
    (out / "excluded_qa.json").write_text(json.dumps(removed, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "status": "trainer_format_research_candidate_status_filtered_not_final_model_release",
        "counts": {**counts, "excluded_grounded_qa_train": sum(x["old_record_key"].startswith("train:")
                                                           for x in removed),
                   "excluded_grounded_qa_dev": sum(x["old_record_key"].startswith("dev:")
                                                         for x in removed)},
        "filter": "Exclude QA rows citing omitted/uncertain sections or the uncommenced BNS 106(2).",
        "limits": ["This filter does not verify remaining QA answers or complaint labels.",
                   "Sealed tests remain separate and unchanged."],
        "input_sha256": {"base_manifest": sha(base / "manifest.json"),
                         "flagged_csv": sha(FLAGS)},
        "files_sha256": {name: sha(out / name) for name in NAMES},
        "excluded_qa_sha256": sha(out / "excluded_qa.json"),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
