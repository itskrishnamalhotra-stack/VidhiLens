"""Flag grounded legal Q&A with omitted, uncertain or uncommenced law.

This is a source-status screen. It does not verify answer correctness.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "review_automation" / "qa_legal_status_v1"


def pid(source: str) -> str | None:
    if source.startswith("bns_2023:"):
        return "BNS_" + source.split(":", 1)[1]
    if source.startswith("it_act_2000:"):
        return "ITA_" + source.split(":", 1)[1]
    return None


def main() -> None:
    flagged = []
    issue_counts = Counter()
    scanned = 0
    with sqlite3.connect(DB) as conn:
        law_status = dict(conn.execute("SELECT provision_id,legal_status FROM provision"))
        for key, split, data_json, meta_json in conn.execute("""SELECT record_key,split,data_json,metadata_json
            FROM research_sft_record WHERE task_kind='grounded_legal_qa'"""):
            scanned += 1
            meta, data = json.loads(meta_json), json.loads(data_json)
            issues = []
            sections = meta.get("source_sections", [])
            law_ids = [pid(s) for s in sections]
            for law_id in law_ids:
                if law_id and law_status.get(law_id) != "in_force":
                    issues.append(f"source_status:{law_id}:{law_status.get(law_id, 'missing')}")
            # Ignore the supplied statute passage: it can quote an uncommenced
            # subpart even when the actual answer concerns the in-force one.
            joined = data["messages"][-1]["content"]
            if "BNS_106" in law_ids and re.search(
                    r"(?is)(?:\b106\s*\(2\)|\b106\s+sub(?:section)?\s*2\b|"
                    r"escap\w*\s+without\s+reporting|flee\w*\s+without\s+reporting|"
                    r"left\s+(?:the\s+)?scene\s+without\s+reporting)", joined):
                issues.append("BNS_106_2_uncommenced_subject")
            if issues:
                issue_counts.update(issues)
                user = "\n".join(m["content"] for m in data["messages"] if m["role"] == "user")
                question = user.rsplit("Question:", 1)[-1].strip()
                flagged.append({"record_key": key, "split": split,
                                "source_id": meta.get("source_id"),
                                "source_sections": json.dumps(sections, ensure_ascii=False),
                                "issues": "|".join(sorted(set(issues))),
                                "question": question[:500]})
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "flagged.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flagged[0]))
        writer.writeheader()
        writer.writerows(flagged)
    summary = {"qa_rows_scanned": scanned, "flagged_rows": len(flagged),
               "issues": issue_counts,
               "status": "screen_only_flagged_rows_need_review_or_exclusion"}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
