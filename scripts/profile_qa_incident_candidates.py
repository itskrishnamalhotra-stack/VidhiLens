"""Find source-grounded QA questions that could be reviewed as triage cases.

No row is approved or exported for triage by this screen.
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
OUT = ROOT / "review_automation" / "qa_incident_screen_v1"


def provision_id(source_section: str) -> str | None:
    if source_section.startswith("bns_2023:"):
        return "BNS_" + source_section.split(":", 1)[1]
    if source_section.startswith("it_act_2000:"):
        return "ITA_" + source_section.split(":", 1)[1]
    return None


def main() -> None:
    candidates = []
    counts = Counter()
    with sqlite3.connect(DB) as conn:
        offences = {row[0] for row in conn.execute("""SELECT provision_id FROM provision
            WHERE legal_status='in_force' AND provision_kind='offence'""")}
        for key, data_json, meta_json in conn.execute("""SELECT record_key,data_json,metadata_json
            FROM research_sft_record WHERE split='train' AND task_kind='grounded_legal_qa'"""):
            counts["qa_train_scanned"] += 1
            data, meta = json.loads(data_json), json.loads(meta_json)
            ids = [provision_id(s) for s in meta.get("source_sections", [])]
            ids = [pid for pid in ids if pid in offences]
            if len(set(ids)) != 1:
                continue
            counts["single_target_offence"] += 1
            user = "\n".join(m["content"] for m in data["messages"] if m["role"] == "user")
            question = user.rsplit("Question:", 1)[-1].strip()
            if question == user or len(question.split()) < 18:
                continue
            counts["question_18_words"] += 1
            if not re.search(r"\b(my|our|someone|person|neighbour|neighbor|friend|relative|husband|wife|child|police|shop|employer|employee|he|she|they|I)\b",
                             question, re.I):
                continue
            counts["incident_lexical_cue"] += 1
            if re.search(r"\b(section|act|punish(?:ment|ed)?|penalty|law|provision|IPC|BNS)\b",
                         question, re.I):
                counts["contains_explicit_law_question"] += 1
            candidates.append({"record_key": key, "provision_id": ids[0],
                               "source_id": meta.get("source_id"),
                               "task_type": meta.get("task_type"),
                               "word_count": len(question.split()),
                               "question": question})
    by_section = Counter(r["provision_id"] for r in candidates)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "candidates.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(candidates[0]))
        writer.writeheader()
        writer.writerows(candidates)
    summary = {**counts, "candidate_rows": len(candidates),
               "candidate_sections": len(by_section),
               "sections_with_at_least_2": sum(n >= 2 for n in by_section.values()),
               "sections_with_at_least_4": sum(n >= 4 for n in by_section.values()),
               "top_sections": by_section.most_common(20),
               "status": "candidate_only_no_legal_or_privacy_approval"}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
