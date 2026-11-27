"""Download and hash the LeSICiN text dataset for local research screening.

Only text/label files are needed for assessing transfer to BNS complaint intake.
The authors' pretrained model, sent2vec binary and citation graph are omitted.
No downloaded row is approved for training by this script.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_candidates" / "lesicin_6053791"
BASE = "https://zenodo.org/api/records/6053791/files/"
FILES = {
    "train.jsonl": "a1994d1aaa8ae7a987fcb1c2e2dc52f1",
    "dev.jsonl": "237b1776f5a535eb3f079bfd0ea0b200",
    "test.jsonl": "09a554405680830c6d3818320eb055af",
    "secs.jsonl": "b2768e06377ab032df2d8f8c323886ff",
    "label_vocab.json": "5758e3117c37788045308e03a531a03d",
}


def hashes(path: Path) -> tuple[str, str]:
    md5, sha256 = hashlib.md5(), hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            md5.update(block)
            sha256.update(block)
    return md5.hexdigest(), sha256.hexdigest()


def download(name: str, expected_md5: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / name
    partial = OUT / (name + ".partial")
    if not target.is_file():
        start = partial.stat().st_size if partial.exists() else 0
        headers = {"Range": f"bytes={start}-"} if start else {}
        with requests.get(BASE + name + "/content", headers=headers, stream=True, timeout=(20, 90)) as response:
            response.raise_for_status()
            if start and (response.status_code != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {start}-")):
                raise ValueError(f"Server refused safe resume for {name}")
            with partial.open("ab" if start else "wb") as stream:
                for block in response.iter_content(chunk_size=1024 * 1024):
                    if block:
                        stream.write(block)
        md5, _ = hashes(partial)
        if md5 != expected_md5:
            raise ValueError(f"MD5 mismatch for {name}: {md5}")
        os.replace(partial, target)
    md5, sha256 = hashes(target)
    if md5 != expected_md5:
        raise ValueError(f"Existing file MD5 mismatch for {name}: {md5}")
    result = {"name": name, "bytes": target.stat().st_size,
              "source_url": BASE + name + "/content", "md5": md5,
              "sha256": sha256, "training_approved": False}
    print(json.dumps(result), flush=True)
    return result


def main() -> None:
    results = [download(name, md5) for name, md5 in FILES.items()]
    manifest = {"record_url": "https://zenodo.org/records/6053791",
                "dataset": "LeSICiN/ILSI IPC court-fact text",
                "rights_status": "Zenodo API metadata lists CC-BY-4.0; research screening only until suitability audit",
                "files": results}
    (OUT / "screening_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
