"""Join reviewed public-source positives and clarifications to the research SFT."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "exports" / "mixed-source-v3-research"
REVIEW = ROOT / "review_automation" / "complaint_pool_v2" / "remaining_1338_review"
OUT = ROOT / "exports" / "mixed-source-v4-research"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def normalize(s: str) -> str:
    return " ".join(re.findall(r"\w+", s.casefold()))


def user_text(row: dict) -> str:
    return " ".join(m["content"] for m in row["messages"] if m["role"] == "user")


def main() -> None:
    base_manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    review_manifest = json.loads((REVIEW / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in base_manifest["files_sha256"].items():
        if digest(BASE / name) != expected:
            raise ValueError(f"Base file changed: {name}")
    for name, expected in review_manifest["file_sha256"].items():
        if digest(REVIEW / name) != expected:
            raise ValueError(f"Reviewed source changed: {name}")
    new = list(read(REVIEW / "positive_train.jsonl")) + list(read(REVIEW / "clarification_train.jsonl"))
    if len(new) != review_manifest["positive_train"] + review_manifest["clarification_train"]:
        raise ValueError("Reviewed case count changed")
    old_train = list(read(BASE / "train_sft.jsonl"))
    old_dev = list(read(BASE / "dev_sft.jsonl"))
    seen = {normalize(user_text(row)) for row in old_train + old_dev}
    for row in new:
        key = normalize(user_text(row))
        if key in seen:
            raise ValueError(f"Duplicate input: {row['id']}")
        seen.add(key)
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("dev_sft.jsonl", "dev_sft_map.jsonl"):
        (OUT / name).write_bytes((BASE / name).read_bytes())
    with (OUT / "train_sft.jsonl").open("w", encoding="utf-8", newline="\n") as data, \
         (OUT / "train_sft_map.jsonl").open("w", encoding="utf-8", newline="\n") as mapping:
        data.write((BASE / "train_sft.jsonl").read_text(encoding="utf-8"))
        mapping.write((BASE / "train_sft_map.jsonl").read_text(encoding="utf-8"))
        for row in new:
            data.write(json.dumps({"messages": row["messages"]}, ensure_ascii=False, separators=(",", ":")) + "\n")
            mapping.write(json.dumps({"source_id": row["id"], **row["metadata"]},
                                     ensure_ascii=False, separators=(",", ":")) + "\n")
    names = ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")
    manifest = {
        "status": "trainer_format_research_candidate_not_final_model_release",
        "counts": {"train": len(old_train) + len(new), "dev": len(old_dev),
                   "reviewed_source_positive_added": review_manifest["positive_train"],
                   "reviewed_source_clarification_added": review_manifest["clarification_train"],
                   "reviewed_source_unlabelled_challenges_separate": review_manifest["unlabelled_challenges"],
                   "sealed_test_kept_separate": base_manifest["counts"]["sealed_test_kept_separate"]},
        "limits": ["Publisher answers are not training targets.",
                   "Unlabelled challenge prompts are not supervised training or scored evaluation records.",
                   "The reviewed short cases remain research candidates pending model evaluation and current-law checks."],
        "files_sha256": {name: digest(OUT / name) for name in names},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
