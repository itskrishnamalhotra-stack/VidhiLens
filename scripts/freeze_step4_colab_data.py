"""Freeze two task-focused, directly trainable Colab datasets and provenance."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import zipfile
import zlib
from collections import Counter
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
SOURCE = ROOT / "exports" / "mixed-source-v27-step3-evaluation"
EVALUATION = ROOT / "exports" / "evaluation-step3-v6"
COMPLAINT = ROOT / "exports" / "complaint_training_v10_step2_research_candidate"
OUT = ROOT / "exports" / "colab-step4-v1"
ZIP = ROOT / "exports" / "colab-step4-v1.zip"
FILES = ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")
NYAYA = "NyayaLabs98/nyaya-train-v3"
GSMS = "GSMS-B/Indian-Legal-QA-BNS-BNSS-BSA"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_lines(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if any(not line for line in lines):
        raise ValueError(f"Blank JSONL row: {path}")
    return lines


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def normal(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def main() -> None:
    if OUT.exists() or ZIP.exists():
        raise ValueError("Frozen output already exists")
    for folder in (SOURCE, EVALUATION, COMPLAINT):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for name, digest in manifest["files_sha256"].items():
            if sha(folder / name) != digest:
                raise ValueError(f"Pinned source changed: {folder.name}/{name}")
    train_data = read_lines(SOURCE / "train_sft.jsonl")
    train_map = read_lines(SOURCE / "train_sft_map.jsonl")
    dev_data = read_lines(SOURCE / "dev_sft.jsonl")
    dev_map = read_lines(SOURCE / "dev_sft_map.jsonl")
    sealed = read_lines(EVALUATION / "sealed_test.jsonl")
    if (len(train_data), len(train_map), len(dev_data), len(dev_map), len(sealed)) != (8107, 8107, 326, 326, 90):
        raise ValueError("Unexpected frozen source counts")
    selected = {"complaint_only": ([], []), "complaint_plus_bns_it_qa": ([], [])}
    excluded = Counter()
    nyaya_ids = set()
    for record_line, map_line in zip(train_data, train_map, strict=True):
        record, meta = json.loads(record_line), json.loads(map_line)
        roles = [m.get("role") for m in record["messages"]]
        if (len(roles) < 3 or roles[0] != "system" or roles[-1] != "assistant" or
                "user" not in roles[1:] or any(role not in ("user", "assistant") for role in roles[1:])):
            raise ValueError(f"Malformed training roles: {meta.get('source_id')}")
        source = meta.get("source")
        if source == NYAYA:
            act = meta.get("source_act")
            if act in ("bns_2023", "it_act_2000"):
                if meta.get("review_status") != "sampled_and_mechanically_screened_auxiliary_qa":
                    raise ValueError("Unscreened Nyaya row")
                sid = meta.get("source_id")
                if not sid or sid in nyaya_ids:
                    raise ValueError("Duplicate Nyaya source ID")
                nyaya_ids.add(sid)
                selected["complaint_plus_bns_it_qa"][0].append(record_line)
                selected["complaint_plus_bns_it_qa"][1].append(map_line)
            else:
                excluded["BNSS_BSA_auxiliary_QA"] += 1
        elif source == GSMS:
            excluded["GSMS_auxiliary_QA_held_for_later_ablation"] += 1
        else:
            for data_rows, map_rows in selected.values():
                data_rows.append(record_line)
                map_rows.append(map_line)
    if len(nyaya_ids) != 987 or excluded != {
        "BNSS_BSA_auxiliary_QA": 1160,
        "GSMS_auxiliary_QA_held_for_later_ablation": 1422,
    }:
        raise ValueError(f"Unexpected auxiliary counts: {excluded}")
    baseline = selected["complaint_only"][0]
    if len(baseline) != 4538 or baseline != read_lines(COMPLAINT / "train_sft.jsonl"):
        raise ValueError("Complaint baseline differs from approved Step 2 training file")
    if len(selected["complaint_plus_bns_it_qa"][0]) != 5525:
        raise ValueError("Auxiliary experiment count mismatch")
    dev_prompts = [normal(json.loads(line)["messages"][1]["content"]) for line in dev_data]
    nyaya_q = [normal(json.loads(line)["messages"][1]["content"].rsplit("Question:", 1)[-1])
               for line, meta_line in zip(*selected["complaint_plus_bns_it_qa"], strict=True)
               if json.loads(meta_line).get("source") == NYAYA]
    for question in nyaya_q:
        hit = process.extractOne(question, dev_prompts, scorer=fuzz.ratio)
        if hit and hit[1] >= 75:
            raise ValueError("Auxiliary question too similar to a development complaint")
    all_eval = dev_data + sealed
    eval_ids = {json.loads(line).get("id") for line in all_eval if json.loads(line).get("id")}
    for variant, (records, maps) in selected.items():
        if len(records) != len(maps):
            raise ValueError(f"Misaligned {variant}")
        for line in records:
            if json.loads(line).get("id") in eval_ids:
                raise ValueError("Evaluation ID in training")
        folder = OUT / variant
        folder.mkdir(parents=True)
        write_lines(folder / "train_sft.jsonl", records)
        write_lines(folder / "train_sft_map.jsonl", maps)
        write_lines(folder / "dev_sft.jsonl", dev_data)
        write_lines(folder / "dev_sft_map.jsonl", dev_map)
        manifest = {"status": "frozen_trainer_format_research_candidate",
                    "variant": variant, "counts": {"train": len(records), "dev": len(dev_data)},
                    "contents": {"complaint_train": 4538, "screened_BNS_IT_auxiliary_QA": len(records) - 4538},
                    "sealed_test": "../evaluation-step3-v6/sealed_test.jsonl; excluded from this training folder",
                    "files_sha256": {name: sha(folder / name) for name in FILES}}
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    root_manifest = {"status": "Step_4_data_freeze_complete_model_choice_pending_Colab_evaluation",
                     "variants": {name: {"train": len(pair[0]), "dev": len(dev_data)} for name, pair in selected.items()},
                     "sealed_test_count": len(sealed), "screened_auxiliary_in_experiment": 987,
                     "held_from_first_Colab_runs": dict(excluded),
                     "source_manifest_sha256": sha(SOURCE / "manifest.json"),
                     "evaluation_manifest_sha256": sha(EVALUATION / "manifest.json"),
                     "files_sha256": {str(p.relative_to(OUT)).replace("\\", "/"): sha(p)
                                      for p in OUT.rglob("*") if p.is_file()},
                     "limits": ["Q&A rows are auxiliary, not complaint-to-section supervision.",
                                "The 987 Nyaya answers passed sampling and mechanical screens, not individual legal certification.",
                                "Use complaint_only first; keep the auxiliary variant only if development evaluation improves.",
                                "Do not train on or tune against the sealed 90-case file."]}
    (OUT / "manifest.json").write_text(json.dumps(root_manifest, indent=2) + "\n", encoding="utf-8")
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(OUT.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(OUT.parent))
    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for path in [*OUT.rglob("*"), ZIP]:
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            key = "step4:freeze:v1:" + rel.replace("/", ":")
            if conn.execute("SELECT 1 FROM dataset_artifact WHERE relative_path=?", (rel,)).fetchone():
                raise ValueError(f"Already pinned: {rel}")
            data = path.read_bytes()
            n = len(selected[path.parent.name][0]) if path.parent.name in selected and path.name.startswith("train_") else len(dev_data) if path.parent.name in selected and path.name.startswith("dev_") else None
            conn.execute("INSERT INTO dataset_artifact (artifact_key,role,relative_path,sha256,bytes,record_count,status,url,license) VALUES (?,?,?,?,?,?,?,NULL,NULL)",
                         (key, "trainer_format_sft", rel, sha(path), len(data), n, "frozen_research_candidate"))
            conn.execute("INSERT INTO dataset_artifact_blob VALUES (?,'zlib',?)", (key, zlib.compress(data, 9)))
        conn.execute("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)",
                     ("current_colab_training_manifest", (OUT / "manifest.json").relative_to(ROOT).as_posix()))
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key failure")
        conn.commit()
    print(json.dumps({"manifest": str(OUT / "manifest.json"), "zip": str(ZIP),
                      "variants": root_manifest["variants"], "held": dict(excluded)}, indent=2))


if __name__ == "__main__":
    main()
