"""Export the verified BNS/IT provision catalogue used by the Colab RAG prototype."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "exports" / "rag_catalogue_v1.json"


def main() -> None:
    with sqlite3.connect(DB) as connection:
        rows = connection.execute("""
            SELECT p.provision_id, p.candidate_title, p.verified_text,
                   p.legal_status, p.provision_kind, p.recommendable,
                   p.source_pdf_page, s.url
            FROM provision AS p
            JOIN source_snapshot AS s ON s.source_id = p.source_id
            WHERE p.verified_text IS NOT NULL
              AND p.legal_status IN ('in_force', 'uncertain')
            ORDER BY p.provision_id
        """).fetchall()
    catalogue = [{
        "provision_id": provision_id,
        "title": title,
        "verified_text": text,
        "legal_status": status,
        "provision_kind": kind,
        "recommendable": bool(recommendable),
        "source_pdf_page": page,
        "source_url": source_url,
    } for provision_id, title, text, status, kind, recommendable, page, source_url in rows]
    counts = {
        "total": len(catalogue),
        "in_force": sum(row["legal_status"] == "in_force" for row in catalogue),
        "uncertain": sum(row["legal_status"] == "uncertain" for row in catalogue),
        "recommendable": sum(row["recommendable"] for row in catalogue),
    }
    if counts != {"total": 467, "in_force": 466, "uncertain": 1, "recommendable": 19}:
        raise ValueError(f"Unexpected catalogue scope: {counts}")
    payload = {
        "schema_version": 1,
        "purpose": "Colab retrieval research; legal_status and recommendation gates remain authoritative",
        "counts": counts,
        "provisions": catalogue,
    }
    data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(json.dumps({"path": str(OUT), "bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest(), "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
