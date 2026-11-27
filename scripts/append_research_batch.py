"""Append a reviewed coverage batch's train rows; keep sealed cases separate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT / "exports" / "mixed-source-v4-research"
DEFAULT_BATCH = ROOT / "data_drafts" / "coverage_batch08_checked"
DEFAULT_OUT = ROOT / "exports" / "mixed-source-v5-research"
NAMES = ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    for line in path.open(encoding="utf-8"):
        yield json.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    base, batch_dir, out = (p.resolve() for p in (args.base, args.batch, args.out))
    if out in (base, batch_dir):
        raise ValueError("Output must be a distinct directory")
    old = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    batch = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
    if (batch["counts"]["train"] != batch["positive_train"] + batch["missing_fact_train"]
            or batch["counts"]["dev"] != batch["positive_dev"] + batch["missing_fact_dev"]
            or batch["counts"]["sealed_test"] != batch["positive_sealed"]):
        raise ValueError("Coverage batch internal counts disagree")
    for name in NAMES:
        if sha(base / name) != old["files_sha256"][name]:
            raise ValueError(f"Base export changed: {name}")
    if sha(batch_dir / "train.jsonl") != batch["files_sha256"]["train"]:
        raise ValueError("Batch train changed")
    if sha(batch_dir / "dev.jsonl") != batch["files_sha256"]["dev"]:
        raise ValueError("Batch dev changed")
    if sha(batch_dir / "sealed_test.jsonl") != batch["files_sha256"]["sealed_test"]:
        raise ValueError("Batch sealed test changed")
    new_train = list(read(batch_dir / "train.jsonl"))
    new_dev = list(read(batch_dir / "dev.jsonl"))
    if (len(new_train) != batch["counts"]["train"]
            or any(r["metadata"]["split"] != "train" for r in new_train)
            or len(new_dev) != batch["counts"]["dev"]
            or any(r["metadata"]["split"] != "dev" for r in new_dev)):
        raise ValueError("Unexpected rows in batch train")
    out.mkdir(parents=True, exist_ok=True)
    for split, new_rows in (("train", new_train), ("dev", new_dev)):
        with (out / f"{split}_sft.jsonl").open("w", encoding="utf-8", newline="\n") as data, \
             (out / f"{split}_sft_map.jsonl").open("w", encoding="utf-8", newline="\n") as mapping:
            data.write((base / f"{split}_sft.jsonl").read_text(encoding="utf-8"))
            mapping.write((base / f"{split}_sft_map.jsonl").read_text(encoding="utf-8"))
            for row in new_rows:
                data.write(json.dumps({"messages": row["messages"]}, ensure_ascii=False,
                                      separators=(",", ":")) + "\n")
                mapping.write(json.dumps({"source": "local_coverage_batch",
                                          **row["metadata"],
                                          "law_source_id": row["metadata"]["source_id"],
                                          "source_id": row["id"],
                                          "case_id": row["id"]},
                                         ensure_ascii=False, separators=(",", ":")) + "\n")
    manifest = {
        "status": "trainer_format_research_candidate_not_final_model_release",
        "counts": {"train": old["counts"]["train"] + len(new_train),
                   "dev": old["counts"]["dev"] + len(new_dev),
                   "new_train_positive": batch["positive_train"],
                   "new_train_missing_fact": batch["missing_fact_train"],
                   "new_dev_positive": batch["positive_dev"],
                   "new_dev_missing_fact": batch["missing_fact_dev"],
                   "new_sealed_test_kept_separate": batch["positive_sealed"]},
        "limits": ["Publisher QA and complaint triage are distinct tasks.",
                   "Many sections still have only one positive training case.",
                   "Sealed cases are excluded from the training export.",
                   "Recommendation approval still requires source and evaluation gates."],
        "input_sha256": {"base_manifest": sha(base / "manifest.json"),
                         "batch_manifest": sha(batch_dir / "manifest.json")},
        "files_sha256": {name: sha(out / name) for name in NAMES},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
