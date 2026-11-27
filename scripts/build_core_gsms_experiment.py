"""Build the task-separated complaint plus GSMS auxiliary research experiment."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPLAINT = ROOT / "exports" / "complaint_training_v8_research_candidate"
GSMS = ROOT / "review_automation" / "gsms_bns_qa_v1"
NYAYA_AUDIT = ROOT / "review_automation" / "nyaya_qa_v1" / "summary.json"
OUT = ROOT / "exports" / "mixed-source-v17-complaint-gsms-research"
FILES = ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pair(data: Path, mapping: Path):
    with data.open(encoding="utf-8") as stream, mapping.open(encoding="utf-8") as meta_stream:
        for index, (d, m) in enumerate(zip(stream, meta_stream, strict=True), 1):
            yield index, json.loads(d), json.loads(m)


def question_key(data: dict) -> str:
    user = " ".join(m["content"] for m in data["messages"] if m["role"] == "user")
    return " ".join(re.findall(r"[a-z0-9]+", user.casefold()))


def main() -> None:
    complaint_manifest = json.loads((COMPLAINT / "manifest.json").read_text(encoding="utf-8"))
    gsms_summary = json.loads((GSMS / "summary.json").read_text(encoding="utf-8"))
    nyaya_summary = json.loads(NYAYA_AUDIT.read_text(encoding="utf-8"))
    for name in FILES:
        if sha(COMPLAINT / name) != complaint_manifest["files_sha256"][name]:
            raise ValueError(f"Complaint bundle changed: {name}")
    for name, digest in gsms_summary["file_sha256"].items():
        if sha(GSMS / name) != digest:
            raise ValueError(f"GSMS audit changed: {name}")
    if gsms_summary["selected_auxiliary_train"] != 1422 or nyaya_summary["held_from_core_training"] != 5539:
        raise ValueError("Upstream screening totals changed")
    complaint_counts = Counter()
    seen = set()
    for split in ("train", "dev"):
        for _, row, meta in pair(COMPLAINT / f"{split}_sft.jsonl", COMPLAINT / f"{split}_sft_map.jsonl"):
            if meta.get("split", split) != split:
                raise ValueError("Complaint split mismatch")
            kind = meta.get("task_family") or meta.get("kind")
            if kind not in {"triage", "candidate_check", "workflow"}:
                raise ValueError(f"Unexpected complaint task: {kind}")
            complaint_counts[(split, kind)] += 1
            seen.add(question_key(row))
    if complaint_counts != {("train", "triage"): 3866, ("train", "workflow"): 52,
                            ("train", "candidate_check"): 605,
                            ("dev", "triage"): 57, ("dev", "workflow"): 3}:
        raise ValueError("Complaint task counts changed")
    gsms_rows = list(pair(GSMS / "auxiliary_train_sft.jsonl", GSMS / "auxiliary_train_map.jsonl"))
    selected = {r["source_row"] for r in (json.loads(line) for line in (GSMS / "audit.jsonl").read_text(encoding="utf-8").splitlines())
                if r["decision"] == "screen_pass_train"}
    if len(gsms_rows) != len(selected):
        raise ValueError("GSMS selection audit differs from training rows")
    for _, row, meta in gsms_rows:
        if (meta.get("source_row") not in selected or meta.get("task_family") != "auxiliary_legal_qa" or
                meta.get("review_status") != "automated_screen_pass_not_semantically_certified"):
            raise ValueError("Unscreened GSMS row found")
        key = question_key(row)
        if not key or key in seen:
            raise ValueError(f"Repeated GSMS input: {meta.get('source_id')}")
        seen.add(key)
    OUT.mkdir(parents=True, exist_ok=True)
    for filename in ("dev_sft.jsonl", "dev_sft_map.jsonl"):
        (OUT / filename).write_bytes((COMPLAINT / filename).read_bytes().replace(b"\r\n", b"\n"))
    for filename, index in (("train_sft.jsonl", 1), ("train_sft_map.jsonl", 2)):
        original = (COMPLAINT / filename).read_bytes().replace(b"\r\n", b"\n")
        if not original.endswith(b"\n"):
            raise ValueError("Complaint JSONL lacks a final newline")
        with (OUT / filename).open("wb") as target:
            target.write(original)
            for item in gsms_rows:
                target.write((json.dumps(item[index], ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
    manifest = {
        "status": "trainer_format_research_candidate_not_final_model_release",
        "counts": {"train": 5945, "dev": 60,
                   "train_triage": 3866, "train_candidate_check": 605,
                   "train_workflow": 52, "train_auxiliary_legal_qa": 1422,
                   "nyaya_qa_train_held": 5259, "nyaya_qa_dev_held": 280},
        "description": "Complaint v8 task cases plus mechanically screened GSMS BNS Q&A. No Nyaya v3 Q&A, no weak triage from the old mixed export, no sealed cases in trainer files.",
        "limits": ["GSMS auxiliary answers are not semantically certified or complaint labels.",
                   "The 605 candidate checks are section-conditioned; unsupported does not mean no other offence applies.",
                   "Use the complaint-only v8 bundle as a baseline and compare this mixed variant on independent development cases.",
                   "This is a research experiment, not an app recommendation release."],
        "input_sha256": {"complaint_manifest": sha(COMPLAINT / "manifest.json"),
                         "gsms_summary": sha(GSMS / "summary.json"),
                         "nyaya_audit_summary": sha(NYAYA_AUDIT)},
        "files_sha256": {filename: sha(OUT / filename) for filename in FILES},
    }
    actual = {"train": sum(1 for _ in (OUT / "train_sft.jsonl").open(encoding="utf-8")),
              "dev": sum(1 for _ in (OUT / "dev_sft.jsonl").open(encoding="utf-8"))}
    if actual != {"train": manifest["counts"]["train"], "dev": manifest["counts"]["dev"]}:
        raise ValueError(f"Combined export count differs: {actual}")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"export": str(OUT), "counts": manifest["counts"]}, indent=2))


if __name__ == "__main__":
    main()
