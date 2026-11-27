"""Append screened GSMS BNS Q&A to a new research-only SFT version."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "exports" / "mixed-source-v14-research"
SCREEN = ROOT / "review_automation" / "gsms_bns_qa_v1"
OUT = ROOT / "exports" / "mixed-source-v15-gsms-aux-research"
NAMES = ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                raise ValueError(f"Blank JSONL row: {path}")
            yield json.loads(line)


def user_key(data: dict) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", " ".join(
        m["content"] for m in data["messages"] if m["role"] == "user").lower()))


def main() -> None:
    base_manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    screening = json.loads((SCREEN / "summary.json").read_text(encoding="utf-8"))
    for name in NAMES:
        if sha(BASE / name) != base_manifest["files_sha256"][name]:
            raise ValueError(f"Base export changed: {name}")
    for name, digest in screening["file_sha256"].items():
        if sha(SCREEN / name) != digest:
            raise ValueError(f"GSMS screening output changed: {name}")
    if screening["trust_level"] != "automated_screen_pass_not_semantically_certified":
        raise ValueError("GSMS trust level unexpectedly changed")
    selected = {r["source_row"] for r in rows(SCREEN / "audit.jsonl")
                if r["decision"] == "screen_pass_train"}
    if len(selected) != screening["selected_auxiliary_train"]:
        raise ValueError("GSMS selected-row count mismatch")
    gsms_data = list(rows(SCREEN / "auxiliary_train_sft.jsonl"))
    gsms_map = list(rows(SCREEN / "auxiliary_train_map.jsonl"))
    if len(gsms_data) != len(gsms_map) or len(gsms_data) != len(selected):
        raise ValueError("GSMS data/map count mismatch")
    seen = {user_key(data) for split in ("train", "dev")
            for data in rows(BASE / f"{split}_sft.jsonl")}
    for data, meta in zip(gsms_data, gsms_map, strict=True):
        if (meta["source_row"] not in selected or meta["split"] != "train" or
                meta["task_family"] != "auxiliary_legal_qa" or
                meta["review_status"] != screening["trust_level"]):
            raise ValueError(f"Unselected or mislabelled GSMS row: {meta}")
        key = user_key(data)
        if not key or key in seen:
            raise ValueError(f"Duplicate or blank GSMS question: {meta['source_id']}")
        seen.add(key)
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("dev_sft.jsonl", "dev_sft_map.jsonl"):
        (OUT / name).write_bytes((BASE / name).read_bytes())
    for name, source in (("train_sft.jsonl", gsms_data), ("train_sft_map.jsonl", gsms_map)):
        with (OUT / name).open("wb") as target:
            target.write((BASE / name).read_bytes())
            if (BASE / name).stat().st_size and not (BASE / name).read_bytes().endswith(b"\n"):
                raise ValueError(f"Base JSONL lacks terminal newline: {name}")
            for row in source:
                target.write((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
    manifest = {
        "status": "trainer_format_research_candidate_not_final_model_release",
        "counts": {"train": base_manifest["counts"]["train"] + len(gsms_data),
                   "dev": base_manifest["counts"]["dev"],
                   "gsms_auxiliary_qa_added_train": len(gsms_data),
                   "gsms_screen_passed_research_only": screening["screen_passed_research_only"],
                   "gsms_held": screening["held"]},
        "source_review_status": screening["trust_level"],
        "training_note": "GSMS rows are BNS explanatory Q&A, not complaint-to-section labels. Control their mixing weight and test whether they improve held-out complaints before using them in a final Colab run.",
        "limits": ["No automated screen establishes semantic legal correctness of every paraphrased answer.",
                   "Scenario and consequence questions remain out of training because of overconfident or speculative answers.",
                   "The 17 flagged source rows remain excluded; no GSMS row enters dev or sealed tests.",
                   "Adding these rows does not expand IT Act or complaint coverage."],
        "input_sha256": {"base_manifest": sha(BASE / "manifest.json"),
                         "screening_summary": sha(SCREEN / "summary.json")},
        "files_sha256": {name: sha(OUT / name) for name in NAMES},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"export": str(OUT), "counts": manifest["counts"],
                      "source_review_status": manifest["source_review_status"]}, indent=2))


if __name__ == "__main__":
    main()
