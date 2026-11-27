"""Source-check the Phase 1 priority text against pinned official PDFs.

This is an AI-assisted source audit for an academic prototype, not a legal opinion.
Every deletion below is an explicitly identified PDF layout artifact. The report
records both the removed lines and the resulting text hash for later human review.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT, SCOPE


REMOVED_LINES = {
    "BNS_77": ["41"],
    "BNS_303": ["89"],
    "BNS_316": ["94", "95", "Of receiving stolen property"],
    "BNS_318": ["96"],
    "BNS_319": ["Of fraudulent deeds and dispositions of property"],
    "BNS_351": ["107"],
    "ITA_65": [
        "1. Subs. by 7 of 2017, s. 169, for “Cyber Appellate Tribunal” (w.e.f. 26-5-2017).",
        "2. Subs. by notification No. S.O. 1015(E) (w.e.f. 19-9-2002).",
        "3. Subs. by Act 10 of 2009, s. 31, for marginal heading (w.e.f. 27-10-2009).",
        "4. Subs. by s. 31, ibid., for “penalty imposed” (w.e.f. 27-10-2009).",
        "5. Subs. by s. 2, ibid., for “digital signature” (w.e.f. 27-10-2009).",
        "24",
    ],
    "ITA_66E": [
        "1. Subs. by Act 10 of 2009, s. 32, for sections 66 and 67 (w.e.f. 27-10-2009).",
        "2. Section 66A has been struck down by supreme Court’s Order dated 24-3-2015 in the Shreya Singhal Vs. Union of India, AIR",
        "2015 SC. 1523.",
        "25",
    ],
    "ITA_43": [
        "1. The word “then” omitted by notification No. S.O. 1015(E) (w.e.f. 19-9-2002).",
        "2. Subs. ibid., for “the key” (w.e.f. 19-9-2002).",
        "3. Ins. by Act 10 of 2009, s. 19 (w.e.f. 27-10-2009).",
        "4. The words “to a person not authorised to affix the digital signature of the subscriber” omitted by notification No. S.O.1015(E)",
        "(w.e.f. 19-9-2002).",
        "5. Subs. by Act 10 of 2009, s. 20, for “PENALTIES AND ADJUDICATION” (w.e.f. 27-10-2009).",
        "6. Subs. by s. 21, ibid., for “Penalty” (w.e.f. 27-10-2009).",
        "7. Ins. by s. 21, ibid. (w.e.f. 27-10-2009).",
        "19",
    ],
}

SOURCE_NOTES = {
    "ITA_66": "The pinned consolidation still cites IPC sections 24 and 25; do not silently rewrite this cross-reference.",
    "ITA_66E": "Pinned India Code consolidation prints 'public area' in Explanation (c); other official reproductions print 'pubic area'. Keep this section out of recommendations pending authoritative reconciliation.",
    "BNS_117": "Preserve the source's wording in its illustration; no editorial correction applied.",
    "BNS_319": "Preserve the source's wording in subsection (1); no editorial correction applied.",
}


def cleaned_text(provision_id: str, raw: str) -> tuple[str, list[str]]:
    lines = raw.splitlines()
    removed = REMOVED_LINES.get(provision_id, [])
    for expected in removed:
        if lines.count(expected) != 1:
            raise ValueError(f"Expected one exact artifact in {provision_id}: {expected!r}")
        lines.remove(expected)
    if provision_id == "ITA_66":
        if not lines[0].startswith("1[66."):
            raise ValueError("Expected editorial footnote marker on ITA_66")
        lines[0] = lines[0][2:]
    result = "\n".join(lines).strip()
    if provision_id == "ITA_43":
        replacements = {
            "43. 6[Penalty and compensation]": "43. Penalty and compensation",
            "7[or computer resource]": "or computer resource",
            "1[(i) destroys": "(i) destroys",
            "damage;]": "damage;",
            "2[he shall": "he shall",
            "person so affected.]": "person so affected.",
            "1[(v) “computer source code”": "(v) “computer source code”",
            "any form.]": "any form.",
        }
        for old, new in replacements.items():
            if result.count(old) != 1:
                raise ValueError(f"Expected one editorial marker in ITA_43: {old!r}")
            result = result.replace(old, new)
    if not result.startswith(provision_id.split("_")[1] + "."):
        raise ValueError(f"Section heading mismatch: {provision_id}")
    if not result.endswith("."):
        raise ValueError(f"Unexpected final character: {provision_id}")
    if re.search(r"(?m)^\d{1,3}$|^\d+\. (?:Subs\.|Ins\.|Section 66A)", result):
        raise ValueError(f"Residual page number or editorial footnote: {provision_id}")
    extra = ["leading editorial footnote marker 1[ removed"] if provision_id == "ITA_66" else []
    if provision_id == "ITA_43":
        extra.append("eight exact amendment footnote brackets removed")
    return result, removed + extra


def main() -> None:
    report = []
    today = date.today().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("INSERT OR IGNORE INTO blocked_provision VALUES (?, ?)",
                     ("ITA_66E", "Official text conflict in Explanation (c) requires authoritative reconciliation"))
        for item in SCOPE["candidate_sections"]:
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (item["id"],)).fetchone()
            assert row is not None and row["priority_review"] == 1
            assert row["source_pdf_page"] == item["source_pdf_page"]
            assert row["source_id"] in {"BNS_INDIA_CODE_2025_10_06", "ITA_INDIA_CODE_CURRENT_2026_09_16"}
            text, removed = cleaned_text(row["provision_id"], row["extracted_text"])
            # This conflict changes the meaning of an element of the offence.
            # It requires an authoritative resolution before app recommendation.
            conflicted = row["provision_id"] == "ITA_66E"
            conn.execute(
                """UPDATE provision SET verified_text=?, provision_kind='offence',
                   legal_status=?, text_reviewed_on=?, status_reviewed_on=?,
                   reviewed_by='Codex AI source audit', recommendable=?, review_note=?
                   WHERE provision_id=?""",
                (text, "uncertain" if conflicted else "in_force", today, today,
                 0 if conflicted else 1,
                 SOURCE_NOTES.get(row["provision_id"], "Official central text source-checked for academic prototype; no state-specific amendment review."),
                 row["provision_id"]),
            )
            report.append({
                "id": row["provision_id"],
                "source_id": row["source_id"],
                "source_pdf_page": row["source_pdf_page"],
                "reviewed_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "removed_layout_artifacts": removed,
                "status": "needs_authoritative_text_reconciliation" if conflicted else "source_checked_for_academic_prototype",
                "recommendable": not conflicted,
                "note": SOURCE_NOTES.get(row["provision_id"]),
            })
        support = []
        for provision_id, kind in (("BNS_114", "definition"), ("BNS_116", "definition"), ("ITA_43", "civil_penalty")):
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (provision_id,)).fetchone()
            assert row is not None and row["source_id"] in {"BNS_INDIA_CODE_2025_10_06", "ITA_INDIA_CODE_CURRENT_2026_09_16"}
            text, removed = cleaned_text(provision_id, row["extracted_text"])
            conn.execute(
                """UPDATE provision SET verified_text=?, provision_kind=?, legal_status='in_force',
                   text_reviewed_on=?, status_reviewed_on=?, reviewed_by='Codex AI source audit',
                   recommendable=0, review_note=? WHERE provision_id=?""",
                (text, kind, today, today, "Support provision for a priority section; not a standalone criminal complaint suggestion.", provision_id),
            )
            support.append({"id": provision_id, "source_id": row["source_id"],
                            "source_pdf_page": row["source_pdf_page"],
                            "reviewed_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                            "removed_layout_artifacts": removed, "recommendable": False})
        assert conn.execute("SELECT count(*) FROM recommendable_provision").fetchone()[0] == 19
        conn.commit()
    output = {
        "reviewed_on": today,
        "reviewer": "Codex AI source audit",
        "scope": "central Acts and pinned source snapshots; academic prototype",
        "not_covered": "State amendments, case law, local procedure, and later legal changes require separate review before real-world deployment.",
        "recommendable_count": 19,
        "held_count": 1,
        "entries": report,
        "support_entries": support,
    }
    path = ROOT / "priority_source_audit.json"
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Source-checked {len(report)} priority entries: 19 enabled, ITA_66E held; report {path}")


if __name__ == "__main__":
    main()
