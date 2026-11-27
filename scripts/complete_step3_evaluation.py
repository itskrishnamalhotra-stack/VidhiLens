"""Build source-grounded development and sealed research evaluation sets.

The publisher-labelled public pool is excluded: its section labels did not
survive a fact-to-law review. Evaluation labels remain research candidates.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
import zlib
from collections import Counter, defaultdict
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
BASE = ROOT / "exports" / "mixed-source-v21-step2-nyaya-experiment"
OUT = ROOT / "exports" / "evaluation-step3-v4"
MIXED = ROOT / "exports" / "mixed-source-v25-step3-evaluation"
MANUAL = ROOT / "data_drafts" / "step3_manual_eval_cases_v1.psv"
REPLACEMENTS = ROOT / "data_drafts" / "step3_dev_replacements_v1.psv"
SEALED_DIRS = [ROOT / "data_drafts" / "gap_examples_v2", *[
    ROOT / "data_drafts" / f"coverage_batch{i:02}_checked" for i in range(8, 17)]]
SYSTEM = ("Read the reported incident. Return JSON only with outcome, possible_provision_ids, "
          "and uncertain_sections. A section is only a possibility, never a finding of guilt. "
          "Never invent missing facts.")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records),
                    encoding="utf-8", newline="\n")


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def normal(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def make_record(pid: str, complaint: str, split: str, source: str, source_id: str,
                page: int, text_hash: str, note: str) -> dict:
    return {"id": source_id, "messages": [
        {"role": "system", "content": SYSTEM}, {"role": "user", "content": complaint},
        {"role": "assistant", "content": json.dumps({"outcome": "provision_match", "possible_provision_ids": [pid],
                                                          "uncertain_sections": []}, separators=(",", ":"))}],
        "metadata": {"kind": "triage", "split": split, "target_provision_id": pid,
                     "source": source, "source_id": source_id, "source_pdf_page": page,
                     "verified_text_sha256": text_hash, "review_status": "AI_reviewed_research_evaluation_candidate",
                     "incident_family": source_id, "review_note": note}}


def main() -> None:
    if OUT.exists() or MIXED.exists():
        raise ValueError("Versioned evaluation output already exists")
    base_manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in base_manifest["files_sha256"].items():
        if sha(BASE / name) != digest:
            raise ValueError(f"Changed base export: {name}")
    manual = defaultdict(dict)
    for line in MANUAL.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        split, pid, complaint = line.split("|", 2)
        if split not in ("dev", "sealed_test") or pid in manual[split] or len(complaint.split()) < 12:
            raise ValueError(f"Bad manual case: {line[:80]}")
        manual[split][pid] = complaint
    if len(manual["dev"]) != 54 or len(manual["sealed_test"]) != 25:
        raise ValueError("Manual case counts changed")

    with sqlite3.connect(DB) as conn:
        laws = {pid: (source, page, hashlib.sha256(text.encode()).hexdigest()) for pid, source, page, text in conn.execute(
            "SELECT provision_id,source_id,source_pdf_page,verified_text FROM provision "
            "WHERE legal_status='in_force' AND provision_kind='offence' AND verified_text IS NOT NULL")}
    if len(laws) != 297 or not set(manual["dev"]) <= set(laws) or not set(manual["sealed_test"]) <= set(laws):
        raise ValueError("Manual/law scope mismatch")

    base_train = jsonl(BASE / "train_sft.jsonl")
    base_train_map = jsonl(BASE / "train_sft_map.jsonl")
    base_dev = jsonl(BASE / "dev_sft.jsonl")
    base_dev_map = jsonl(BASE / "dev_sft_map.jsonl")
    train_prompts = [normal(r["messages"][1]["content"]) for r, m in zip(base_train, base_train_map, strict=True)
                     if (m.get("kind") or m.get("task_family")) == "triage"]
    current_dev_ids = set()
    for r, m in zip(base_dev, base_dev_map, strict=True):
        if (m.get("kind") or m.get("task_family")) != "triage":
            continue
        ans = json.loads(r["messages"][-1]["content"])
        current_dev_ids.update(ans.get("possible_provision_ids", []))
    missing = set(laws) - current_dev_ids
    if len(missing) != 256:
        raise ValueError(f"Expected 256 missing development positives, found {len(missing)}")

    selected = {}
    for line in REPLACEMENTS.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        pid, complaint = line.split("|", 1)
        if pid in selected or not (12 <= len(complaint.split()) <= 110):
            raise ValueError(f"Bad replacement for {pid}")
        if re.search(r"\b(section\s*\d+|BNS|IT Act)\b", complaint, re.I):
            raise ValueError(f"Legal identifier in replacement {pid}")
        selected[pid] = complaint
    needed_source = missing - set(manual["dev"])
    if set(selected) != needed_source:
        absent = sorted(needed_source - set(selected))
        raise ValueError(f"Replacement coverage mismatch: {absent}")

    dev_new = []
    for pid in sorted(missing):
        source, page, text_hash = laws[pid]
        if pid in manual["dev"]:
            dev_new.append(make_record(pid, manual["dev"][pid], "dev", "manual_step3_source_grounded",
                                       f"step3-dev-manual-{pid}", page, text_hash,
                                       "New independently authored incident; source-grounded research evaluation case."))
        else:
            dev_new.append(make_record(pid, selected[pid], "dev", "manual_step3_source_grounded",
                                       f"step3-dev-replacement-{pid}", page, text_hash,
                                       "AI-authored fact pattern for a verified provision; research evaluation label."))
    if len(dev_new) != 256 or {r["metadata"]["target_provision_id"] for r in dev_new} != missing:
        raise ValueError("Development coverage build failed")

    old_sealed = []
    for folder in SEALED_DIRS:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        path = folder / "sealed_test.jsonl"
        if sha(path) != manifest["files_sha256"]["sealed_test"]:
            raise ValueError(f"Changed sealed source: {folder.name}")
        old_sealed.extend(jsonl(path))
    sealed_ids = {pid for r in old_sealed for pid in json.loads(r["messages"][-1]["content"]).get("possible_provision_ids", [])}
    additions = []
    for pid, complaint in sorted(manual["sealed_test"].items()):
        source, page, text_hash = laws[pid]
        if pid in sealed_ids:
            raise ValueError(f"Manual sealed case duplicates existing section: {pid}")
        additions.append(make_record(pid, complaint, "sealed_test", "manual_step3_source_grounded",
                                     f"step3-sealed-manual-{pid}", page, text_hash,
                                     "New held-out incident for the release-scope and coverage test."))
    if len(old_sealed) != 55 or len(additions) != 25 or len(old_sealed) + len(additions) != 80:
        raise ValueError("Sealed-test target is not 80")
    all_dev = base_dev + dev_new
    if len(all_dev) != 316:
        raise ValueError("Unexpected development count")
    eval_manifest = {"status": "AI_reviewed_research_evaluation_candidate_not_legal_gold",
                     "counts": {"dev": len(all_dev), "sealed_test": len(old_sealed) + len(additions),
                                "new_dev_positive": len(dev_new), "new_sealed_positive": len(additions)},
                     "development_positive_sections": 297,
                     "sealed_positive_sections": len(sealed_ids | set(manual["sealed_test"])),
                     "manual_source_sha256": sha(MANUAL), "replacement_source_sha256": sha(REPLACEMENTS),
                     "public_source_dev": 0, "authored_replacement_dev": len(selected), "manual_dev": len(manual["dev"]),
                     "limits": ["All new development cases are AI-authored research labels; they are not independently certified legal gold.",
                                "The publisher-labelled public prompt pool was excluded after fact-to-law review found incorrect labels.",
                                "The sealed file must not be used during training, prompt tuning, or threshold selection."]}
    OUT.mkdir(parents=True)
    write_jsonl(OUT / "dev_sft.jsonl", all_dev)
    write_jsonl(OUT / "sealed_test.jsonl", old_sealed + additions)
    eval_manifest["files_sha256"] = {p.name: sha(p) for p in (OUT / "dev_sft.jsonl", OUT / "sealed_test.jsonl")}
    (OUT / "manifest.json").write_text(json.dumps(eval_manifest, indent=2) + "\n", encoding="utf-8")

    # The train data stay identical; only the complete development split changes.
    MIXED.mkdir(parents=True)
    for name in ("train_sft.jsonl", "train_sft_map.jsonl"):
        (MIXED / name).write_bytes((BASE / name).read_bytes())
    write_jsonl(MIXED / "dev_sft.jsonl", all_dev)
    # Development maps are included only for the original 60 records; added test records carry self-contained metadata.
    write_jsonl(MIXED / "dev_sft_map.jsonl", base_dev_map + [r["metadata"] for r in dev_new])
    mixed_manifest = {"status": "trainer_format_with_expanded_dev_requires_model_evaluation",
                      "counts": {"train": len(base_train), "dev": len(all_dev)},
                      "parent_train_export": BASE.relative_to(ROOT).as_posix() + "/manifest.json",
                      "evaluation_manifest": OUT.relative_to(ROOT).as_posix() + "/manifest.json",
                      "files_sha256": {name: sha(MIXED / name) for name in ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")},
                      "limits": ["Use the expanded development set to select model configuration; never include the separate sealed test in tuning."]}
    (MIXED / "manifest.json").write_text(json.dumps(mixed_manifest, indent=2) + "\n", encoding="utf-8")
    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for path in [OUT / "dev_sft.jsonl", OUT / "sealed_test.jsonl", OUT / "manifest.json",
                     MIXED / "train_sft.jsonl", MIXED / "train_sft_map.jsonl", MIXED / "dev_sft.jsonl", MIXED / "dev_sft_map.jsonl", MIXED / "manifest.json"]:
            data = path.read_bytes(); rel = path.relative_to(ROOT).as_posix(); key = "step3:v1:" + rel.replace("/", ":")
            if conn.execute("SELECT 1 FROM dataset_artifact WHERE relative_path=?", (rel,)).fetchone():
                raise ValueError(f"Artifact already pinned: {rel}")
            count = len(base_train) if path.name.startswith("train_") else len(all_dev) if path.name.startswith("dev_") else len(old_sealed)+len(additions) if path.name=="sealed_test.jsonl" else None
            conn.execute("INSERT INTO dataset_artifact (artifact_key,role,relative_path,sha256,bytes,record_count,status,url,license) VALUES (?,?,?,?,?,?,?,NULL,NULL)",
                         (key, "evaluation" if path.parent == OUT else "trainer_format_sft", rel, sha(path), len(data), count, "AI_reviewed_research_candidate"))
            conn.execute("INSERT INTO dataset_artifact_blob VALUES (?,'zlib',?)", (key, zlib.compress(data, 9)))
        conn.execute("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)", ("current_evaluation_export", OUT.relative_to(ROOT).as_posix() + "/manifest.json"))
        conn.execute("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)", ("current_research_export", MIXED.relative_to(ROOT).as_posix() + "/manifest.json"))
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key failure")
        conn.commit()
    print(json.dumps(eval_manifest, indent=2))


if __name__ == "__main__":
    main()
