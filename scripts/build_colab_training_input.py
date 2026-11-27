"""Create one upload archive for the self-contained Colab training notebook."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "exports" / "colab-step4-v1"
SEALED = ROOT / "exports" / "evaluation-step3-v6" / "sealed_test.jsonl"
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "exports" / "colab_training_input_v5.zip"
RUNNER = ROOT / "colab" / "train_runner.py"
TEMPLATE = ROOT / "colab" / "qwen3_instruct_2507_assistant_mask.jinja"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    if OUT.exists():
        raise ValueError(f"Frozen bundle already exists: {OUT}")
    root_manifest = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
    files: dict[str, bytes] = {}
    for rel, expected in root_manifest["files_sha256"].items():
        data = (SRC / rel).read_bytes()
        if digest(data) != expected:
            raise ValueError(f"Source changed: {rel}")
        files[rel] = data
    files["dataset_manifest.json"] = (SRC / "manifest.json").read_bytes()
    eval_manifest = json.loads((SEALED.parent / "manifest.json").read_text(encoding="utf-8"))
    sealed = SEALED.read_bytes()
    if digest(sealed) != eval_manifest["files_sha256"][SEALED.name]:
        raise ValueError("Sealed source changed")
    if len(sealed.splitlines()) != 90:
        raise ValueError("Unexpected sealed count")
    files["evaluation/sealed_test.jsonl"] = sealed
    with sqlite3.connect(DB) as conn:
        rows = conn.execute("""SELECT p.provision_id,p.candidate_title,p.verified_text,p.source_pdf_page,
            s.url,p.recommendable FROM provision p JOIN source_snapshot s ON p.source_id=s.source_id
            WHERE p.legal_status='in_force' AND p.provision_kind='offence' AND p.verified_text IS NOT NULL
            ORDER BY p.provision_id""").fetchall()
    if len(rows) != 297 or sum(r[5] for r in rows) != 19:
        raise ValueError("Law snapshot scope changed")
    catalogue = [{"provision_id": pid, "title": title, "verified_text": text,
                  "source_pdf_page": page, "source_url": url, "recommendable": bool(allowed)}
                 for pid, title, text, page, url, allowed in rows]
    files["evaluation/offence_catalogue.json"] = (json.dumps(catalogue, ensure_ascii=False,
                                                               separators=(",", ":")) + "\n").encode("utf-8")
    files["train_runner.py"] = RUNNER.read_bytes()
    files[TEMPLATE.name] = TEMPLATE.read_bytes()
    manifest = {"status": "frozen_colab_training_input", "version": 5,
                "counts": {"complaint_train": 4538, "complaint_plus_qa_train": 5525,
                           "development": 326, "sealed_test": 90,
                           "law_offences": 297, "live_recommendable": 19},
                "files_sha256": {name: digest(data) for name, data in sorted(files.items())},
                "separation": "Sealed test is outside both train variants and is read only after model selection."}
    files["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            archive.writestr("colab_training_input_v5/" + name, data)
    with zipfile.ZipFile(OUT) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity failure")
    print(json.dumps({"path": str(OUT), "bytes": OUT.stat().st_size,
                      "entries": len(files), "counts": manifest["counts"]}, indent=2))


if __name__ == "__main__":
    main()
