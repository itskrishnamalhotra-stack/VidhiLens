"""Read-only full-pass profile of the 6,681 pinned public candidate rows."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "external_training_potential_report.json"
PII = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|(?<!\d)(?:\+91[- ]?)?[6-9]\d{9}(?!\d)")


def norm(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def main() -> None:
    with sqlite3.connect(DB) as conn:
        approved = {r[0] for r in conn.execute("SELECT provision_id FROM recommendable_provision")}
        known = {r[0] for r in conn.execute("SELECT provision_id FROM provision")}
        reviewed = dict(conn.execute("SELECT row_number,decision FROM public_candidate_review WHERE source_key='statutory_triage'"))
        rows = conn.execute("SELECT source_key,row_number,record_json FROM public_candidate_row ORDER BY source_key,row_number").fetchall()
    stats: dict[str, dict] = {}
    seen: dict[str, set[str]] = {}
    for key, number, payload in rows:
        row = json.loads(payload)
        x = stats.setdefault(key, {"count": 0, "short_under_25_words": 0,
                                   "possible_phone_or_email": 0, "exact_content_duplicates": 0,
                                   "publisher_section_in_19_section_pilot": 0,
                                   "publisher_section_in_full_index": 0,
                                   "candidate_25plus_words_in_pilot_no_simple_pii": 0,
                                   "reviewed_corrected": 0, "reviewed_held": 0,
                                   "unreviewed": 0, "verified_false_metadata": 0,
                                   "legal_domains": Counter(), "task_types": Counter(),
                                   "question_types": Counter(), "source_acts": Counter(),
                                   "role_shapes": Counter()})
        x["count"] += 1
        if key == "bns_structured":
            content = str(row.get("text", ""))
            section = "BNS_" + str(row.get("section_number", ""))
        elif key == "bns_qa":
            content = str(row.get("question", "")) + " " + str(row.get("answer", ""))
            section = "BNS_" + str(row.get("section_number", ""))
            x["question_types"][str(row.get("question_type"))] += 1
        elif key in ("nyaya_train", "nyaya_val"):
            metadata = row.get("metadata", {})
            messages = row.get("messages", [])
            content = str(metadata.get("rag", {}).get("question", ""))
            section = None
            x["legal_domains"][str(metadata.get("legal_domain"))] += 1
            x["task_types"][str(metadata.get("task_type"))] += 1
            x["source_acts"][str(metadata.get("source_act"))] += 1
            x["role_shapes"]["-".join(str(m.get("role")) for m in messages)] += 1
            if metadata.get("verified") is False:
                x["verified_false_metadata"] += 1
        elif key == "nyaya_eval":
            content = str(row.get("question", ""))
            section = None
            x["legal_domains"][str(row.get("legal_domain"))] += 1
            x["task_types"][str(row.get("task_type"))] += 1
        else:
            content = str(row.get("instruction", ""))
            section = "BNS_" + str(row.get("bns_section_applied", "")).split("(")[0]
            if number in reviewed:
                x["reviewed_corrected" if reviewed[number] == "accepted_corrected" else "reviewed_held"] += 1
            else:
                x["unreviewed"] += 1
        words = len(content.split())
        pii = bool(PII.search(content))
        x["short_under_25_words"] += words < 25
        x["possible_phone_or_email"] += pii
        normalized = norm(content)
        source_seen = seen.setdefault(key, set())
        x["exact_content_duplicates"] += normalized in source_seen
        source_seen.add(normalized)
        x["publisher_section_in_19_section_pilot"] += section in approved
        x["publisher_section_in_full_index"] += section in known
        x["candidate_25plus_words_in_pilot_no_simple_pii"] += bool(section in approved and words >= 25 and not pii)
    report = {"rows_scanned": len(rows), "sources": {},
              "interpretation": "Counts are mechanical filters, not permission to auto-approve legal labels. Candidate counts overlap with already reviewed and rejected records."}
    for key, x in stats.items():
        report["sources"][key] = {k: dict(v) if isinstance(v, Counter) else v for k, v in x.items()}
    if len(rows) != 6681:
        raise SystemExit("Source pool size changed")
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
