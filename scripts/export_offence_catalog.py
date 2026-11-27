"""Export every verified in-force offence as a source-linked retrieval record.

This provides full law-text coverage for later retrieval. It does not approve
any provision for complaint recommendations or invent new complaint labels.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "exports" / "full-offence-catalog-v2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        laws = conn.execute("""SELECT provision_id,act_id,section_number,candidate_title,
            verified_text,source_id,source_pdf_page,recommendable FROM provision
            WHERE legal_status='in_force' AND provision_kind='offence'
            ORDER BY act_id, CAST(section_number AS INTEGER), section_number""").fetchall()
        if len(laws) != 297 or any(not row["verified_text"] for row in laws):
            raise ValueError("The full verified in-force offence set is incomplete")
        records = []
        for law in laws:
            subparts = [dict(zip(("subpart", "legal_status", "source_id", "note"), row))
                        for row in conn.execute("""SELECT subpart,legal_status,source_id,note
                            FROM provision_subpart_status WHERE provision_id=?""",
                                                (law["provision_id"],))]
            retrieval_text = law["verified_text"]
            if any(item["legal_status"] != "in_force" for item in subparts):
                if (law["provision_id"] != "BNS_106" or len(subparts) != 1
                        or subparts[0]["subpart"] != "(2)"
                        or subparts[0]["legal_status"] != "uncommenced"):
                    raise ValueError(f"No safe retrieval trim for {law['provision_id']}")
                parts = retrieval_text.split("\n(2) Whoever causes death", 1)
                if len(parts) != 2:
                    raise ValueError("Could not isolate uncommenced BNS 106(2)")
                retrieval_text = parts[0].rstrip()
            record = {key: law[key] for key in
                      ("provision_id", "act_id", "section_number", "candidate_title",
                       "verified_text", "source_id", "source_pdf_page")}
            record["verified_text_sha256"] = hashlib.sha256(
                law["verified_text"].encode()).hexdigest()
            record["retrieval_text"] = retrieval_text
            record["subpart_status"] = subparts
            record["app_recommendable"] = bool(law["recommendable"])
            record["use_rule"] = "Use retrieval_text for possible law evidence; never suggest an uncommenced subpart. App suggestions require separate approval and factual checks."
            records.append(record)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "offences.jsonl"
    with target.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    manifest = {"status": "full_source_checked_retrieval_catalog_not_full_complaint_dataset",
                "offence_records": len(records),
                "by_act": {act: sum(r["act_id"] == act for r in records)
                           for act in sorted({r["act_id"] for r in records})},
                "app_recommendable": sum(r["app_recommendable"] for r in records),
                "records_with_blocked_subparts": sum(any(
                    item["legal_status"] != "in_force" for item in r["subpart_status"])
                    for r in records),
                "law_file_sha256": sha(target),
                "limits": ["Retrieval coverage is not complaint-label coverage.",
                           "Source snapshots require current-law checking before real-world use."]}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
