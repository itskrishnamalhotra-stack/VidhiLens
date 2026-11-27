"""Create one SFT entry point while preserving triage, workflow, and candidate-check tasks."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "exports" / "complaint_only_v6_research_candidate"
CHECKS = ROOT / "exports" / "part2_candidate_checks_v3_research"
CONFUSERS = ROOT / "exports" / "part2_confusers_v1_research"
OUT = ROOT / "exports" / "complaint_training_v8_research_candidate"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paired(folder: Path, split: str) -> list[tuple[str, str]]:
    data = (folder / f"{split}_sft.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
    mapping = (folder / f"{split}_sft_map.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
    if len(data) != len(mapping):
        raise ValueError(f"Misaligned source: {folder}/{split}")
    return list(zip(data, mapping, strict=True))


def main() -> None:
    if OUT.exists():
        raise ValueError("Output exists; refuse to overwrite training bundle")
    check_manifest = json.loads((CHECKS / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in check_manifest["files_sha256"].items():
        if digest(CHECKS / name) != expected:
            raise ValueError(f"Candidate check hash mismatch: {name}")
    confuser_manifest = json.loads((CONFUSERS / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in confuser_manifest["files_sha256"].items():
        if digest(CONFUSERS / name) != expected:
            raise ValueError(f"Confuser hash mismatch: {name}")
    train = paired(BASE, "train") + paired(CHECKS, "train") + paired(CONFUSERS, "train")
    dev = paired(BASE, "dev")
    counts = {"train": Counter(), "dev": Counter()}
    source_ids = set()
    for split, records in (("train", train), ("dev", dev)):
        for data_line, meta_line in records:
            data, meta = json.loads(data_line), json.loads(meta_line)
            kind = meta.get("kind") or meta.get("task_family")
            if kind not in ("triage", "workflow", "candidate_check") or not data.get("messages"):
                raise ValueError(f"Bad task family in {split}")
            if kind == "candidate_check":
                if split != "train" or meta.get("split") != "train":
                    raise ValueError("Candidate check leaked out of train")
                answer = json.loads(data["messages"][-1]["content"])
                if answer.get("label") not in ("uncertain", "unsupported"):
                    raise ValueError("Invalid candidate check label")
                sid = meta["source_id"]
                if sid in source_ids:
                    raise ValueError(f"Repeated candidate case: {sid}")
                source_ids.add(sid)
            counts[split][kind] += 1
    if counts["train"]["candidate_check"] != 605 or counts["dev"]["candidate_check"]:
        raise ValueError("Incorrect Part 2 bundle counts")
    OUT.mkdir(parents=True)
    for split, records in (("train", train), ("dev", dev)):
        for suffix, index in (("sft", 0), ("sft_map", 1)):
            (OUT / f"{split}_{suffix}.jsonl").write_text(
                "".join(row[index] for row in records), encoding="utf-8")
    report = {"status": "AI_reviewed_research_candidate_not_model_release",
              "counts": {split: dict(counter) for split, counter in counts.items()},
              "train_total": len(train), "dev_total": len(dev),
              "training_tasks": ["triage", "workflow", "candidate_check"],
              "source_manifest_sha256": digest(CHECKS / "manifest.json"),
              "confuser_manifest_sha256": digest(CONFUSERS / "manifest.json"),
              "files_sha256": {p.name: digest(p) for p in OUT.glob("*.jsonl")},
              "limits": ["The candidate-check task is section-conditioned; its unsupported answer is not global out_of_scope.",
                         "No sealed cases are in this bundle.",
                         "Compact research checks do not prove legal correctness; select task mixture using independent dev evaluation.",
                         "The 5,259 legal Q&A records remain held outside this complaint training bundle."]}
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
