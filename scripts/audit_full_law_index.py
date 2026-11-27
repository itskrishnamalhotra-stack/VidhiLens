"""Check extraction integrity across the complete, unverified Acts index.

This audit is mechanical. It never promotes extracted text to verified law.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter

from build_full_kb import DB_PATH, ROOT, sha256


def main() -> None:
    issues: list[dict] = []
    short_omitted_notices: list[str] = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""SELECT p.provision_id, p.act_id, p.section_number,
            p.source_pdf_page, p.extracted_text, p.verified_text, p.recommendable,
            p.legal_status,
            s.file_path, s.sha256 AS source_sha256
            FROM provision p JOIN source_snapshot s ON s.source_id=p.source_id
            ORDER BY p.act_id, CAST(p.section_number AS INTEGER), p.section_number""").fetchall()
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    source_hashes = {}
    for row in rows:
        path = ROOT / row["file_path"]
        if row["file_path"] not in source_hashes:
            source_hashes[row["file_path"]] = sha256(path) if path.is_file() else None
        if source_hashes[row["file_path"]] != row["source_sha256"]:
            issues.append({"id": row["provision_id"], "kind": "source_hash_mismatch"})
        txt = row["extracted_text"]
        first = txt.splitlines()[0].strip() if txt else ""
        number = re.escape(row["section_number"])
        if not re.match(rf"^(?:\d+\[)?{number}\.(?:\s|\ufffd|\u2014|\u2013)", first):
            # The IT Act PDF prints the footnote marker adjacent to section 66A.
            if not (row["provision_id"] == "ITA_66A" and first.startswith("266A.")):
                issues.append({"id": row["provision_id"], "kind": "heading_mismatch", "sample": first[:100]})
        if len(txt) < 80:
            if row["legal_status"] == "omitted" and re.search(r'\bOmitted by\b', txt):
                short_omitted_notices.append(row["provision_id"])
            else:
                issues.append({"id": row["provision_id"], "kind": "short_extraction", "length": len(txt)})
        if re.match(r'^\d+[A-Z]?\.\s*\[[^]]+\]\W*Omitted by\b',
                    ' '.join(txt.splitlines()[:3])) and row["legal_status"] != "omitted":
            issues.append({"id": row["provision_id"], "kind": "explicit_omission_status_conflict"})
        if "\ufffd" in txt:
            issues.append({"id": row["provision_id"], "kind": "replacement_character", "count": txt.count("\ufffd")})
        if row["recommendable"] and not row["verified_text"]:
            issues.append({"id": row["provision_id"], "kind": "recommendable_without_verified_text"})
    counts = Counter(r["act_id"] for r in rows)
    if counts != {"BNS_2023": 358, "ITA_2000": 125}:
        issues.append({"kind": "section_count_mismatch", "counts": dict(counts)})
    if fk_errors:
        issues.append({"kind": "foreign_key_errors", "count": len(fk_errors)})
    report = {
        "total_indexed_sections": len(rows),
        "by_act": dict(counts),
        "source_hashes_match": all(source_hashes[p] is not None for p in source_hashes)
            and not any(x["kind"] == "source_hash_mismatch" for x in issues),
        "source_checked_text_sections": sum(bool(r["verified_text"]) for r in rows),
        "recommendable_sections": sum(r["recommendable"] for r in rows),
        "legal_status_counts": dict(Counter(r["legal_status"] for r in rows)),
        "short_omitted_notices": short_omitted_notices,
        "mechanical_issue_counts": dict(Counter(x["kind"] for x in issues)),
        "mechanical_issues": issues,
        "interpretation": "Mechanical checks do not verify legal text or current legal status. Only verified_text is approved for display.",
    }
    path = ROOT / "full_law_index_audit.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "mechanical_issues"}, indent=2))
    print(f"Issue details: {path}")


if __name__ == "__main__":
    main()
