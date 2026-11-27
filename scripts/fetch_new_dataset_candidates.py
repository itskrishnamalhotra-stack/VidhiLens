"""Pin selected additional public datasets for an evidence-based source audit."""

import hashlib
import json
from datetime import date
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_candidates" / "additional_20260917"
SOURCES = [
    ("nariraksha", "vikhram-labs/NariRaksha-1K", "data/train-00000-of-00001.parquet"),
    ("complaint_bns", "navaneeth005/complaint-relevant-bns", "generated_bns_complaints_ref_format.jsonl"),
    ("nyaya_v3_train", "NyayaLabs98/nyaya-train-v3", "train.jsonl"),
    ("nyaya_v3_val", "NyayaLabs98/nyaya-train-v3", "val.jsonl"),
    ("nyaya_v3_test", "NyayaLabs98/nyaya-train-v3", "test.jsonl"),
    ("fraud_cyber", "sidddd625/adaption-fraud-and-cyber-safety", "data/train_0.jsonl"),
    ("nyaya_statute_bns", "NyayaLabs98/nyaya-statute-db", "bns_2023.jsonl"),
    ("nyaya_statute_it", "NyayaLabs98/nyaya-statute-db", "it_act_2000.jsonl"),
]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    repos = {}
    manifest = []
    for key, repo, remote in SOURCES:
        if repo not in repos:
            response = session.get(f"https://huggingface.co/api/datasets/{repo}", timeout=40)
            response.raise_for_status()
            repos[repo] = response.json()
        info = repos[repo]
        revision = info["sha"]
        url = f"https://huggingface.co/datasets/{repo}/resolve/{revision}/{remote}"
        target = OUT / f"{key}{Path(remote).suffix}"
        if not target.exists():
            with session.get(url, timeout=120, stream=True) as response:
                response.raise_for_status()
                with target.open("wb") as output:
                    for block in response.iter_content(1024 * 1024):
                        if block:
                            output.write(block)
        record = {
            "key": key, "repo": repo, "revision": revision, "remote_path": remote,
            "url": url, "local_path": target.relative_to(ROOT).as_posix(),
            "license": info.get("cardData", {}).get("license"),
            "bytes": target.stat().st_size, "sha256": digest(target),
            "retrieved_on": date.today().isoformat(),
        }
        manifest.append(record)
        print(f"{key}: {record['bytes']:,} bytes", flush=True)
    path = ROOT / "additional_candidates_manifest.json"
    path.write_text(json.dumps({"files": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
