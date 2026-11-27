"""Fetch pinned public datasets into a quarantine folder, never into gold data.

Publisher labels are unreviewed. Run only after reading DATASET_CATALOG.md.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "external_candidates"
SOURCES = [
    {"key": "bns_structured", "repo": "GSMS-B/indian-legal-sections-bns-bnss-bsa-2023", "revision": "b2680e920dc25fcc9aa504015cf0660256af2a6c", "path": "bns_sections.json", "license": "apache-2.0", "intended_use": "statute_parse_crosscheck"},
    {"key": "bns_qa", "repo": "GSMS-B/Indian-Legal-QA-BNS-BNSS-BSA", "revision": "5aae2c71ef9d369df663ff32b4c73e98982c00b2", "path": "bns_legal_qa.jsonl", "license": "apache-2.0", "intended_use": "unreviewed_qa_candidate"},
    {"key": "nyaya_train", "repo": "NyayaLabs98/nyaya-train-v7-raft", "revision": "d8e85637a2a80ee770fb8672b0ff4381c91ffcfc", "path": "train.jsonl", "license": "apache-2.0", "intended_use": "unreviewed_dialogue_candidate"},
    {"key": "nyaya_val", "repo": "NyayaLabs98/nyaya-train-v7-raft", "revision": "d8e85637a2a80ee770fb8672b0ff4381c91ffcfc", "path": "val.jsonl", "license": "apache-2.0", "intended_use": "unreviewed_dialogue_candidate"},
    {"key": "nyaya_eval", "repo": "NyayaLabs98/nyaya-eval-v0", "revision": "e396be04640ca3449ad865c877cf21d9cd85ec2e", "path": "nyaya_eval_v0.jsonl", "license": "cc-by-4.0", "intended_use": "external_audit_only_never_training_or_gold_test"},
    {"key": "statutory_triage", "repo": "legalnlpresearcher/legal-statutory-triage-sft", "revision": "98b942e5afe250a4163b61d80c1fadd2279580e1", "path": "bns_ipc_dataset_final_dense.jsonl", "license": "cc-by-4.0", "intended_use": "unreviewed_triage_candidate"},
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    DEST.mkdir(exist_ok=True)
    prior_path = ROOT / "external_candidates_manifest.json"
    prior = {row["key"]: row for row in json.loads(prior_path.read_text(encoding="utf-8"))["files"]} if prior_path.exists() else {}
    entries = []
    for source in SOURCES:
        target = DEST / f"{source['key']}_{Path(source['path']).name}"
        expected = prior.get(source["key"])
        if target.exists() and expected and sha256(target) == expected["sha256"]:
            entries.append({**expected, "local_path": target.relative_to(ROOT).as_posix()})
            print(f"verified existing: {target.name}")
            continue
        url = f"https://huggingface.co/datasets/{source['repo']}/resolve/{source['revision']}/{source['path']}"
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        partial = target.with_suffix(target.suffix + ".partial")
        partial.write_bytes(response.content)
        partial.replace(target)
        entry = {**source, "url": url, "local_path": target.relative_to(ROOT).as_posix(),
                 "bytes": target.stat().st_size, "sha256": sha256(target),
                 "retrieved_on": date.today().isoformat(), "review_status": "quarantined_unreviewed"}
        entries.append(entry)
        print(f"downloaded: {target.name} ({entry['bytes']} bytes)")
    prior_path.write_text(json.dumps({"files": entries}, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {prior_path}")


if __name__ == "__main__":
    main()
