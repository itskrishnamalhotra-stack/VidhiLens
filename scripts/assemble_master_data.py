"""Screen the complete public source pool without promoting unreviewed labels.

Sample mode is read-only and checks a balanced subset. Full mode records every
source-row screen in the single master SQLite database. Both modes validate
that existing reviewed scenarios compile to conversational SFT shape.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

from build_full_kb import DB_PATH, ROOT
from compile_sft_data import compile_records, inspect


VERSION = "source-screen-v1-2026-09-17"
OUT = ROOT / "data_drafts"
SOURCES = ("bns_structured", "bns_qa", "nyaya_train", "nyaya_val", "nyaya_eval", "statutory_triage")
PII = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|(?<!\d)(?:\+91[- ]?)?[6-9]\d{9}(?!\d)")


def text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def classify(source_key: str, number: int, record: dict, expected_hash: str,
             known: set[str], reviewed: dict[int, str], approved: set[str]) -> dict:
    normalized = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if text_sha(normalized) != expected_hash:
        raise ValueError(f"Source record changed: {source_key}:{number}")
    section = None
    issue = []
    content = ""
    approved_training = 0
    if source_key == "bns_structured":
        kind = "law_crosscheck"
        section = "BNS_" + str(record.get("section_number", ""))
        content = str(record.get("text", ""))
        issue.append("third_party_law_text_not_official_truth")
    elif source_key == "bns_qa":
        kind = "legal_qa_candidate"
        section = "BNS_" + str(record.get("section_number", ""))
        content = str(record.get("question", "")) + " " + str(record.get("answer", ""))
        issue.append("answer_requires_source_check")
    elif source_key in {"nyaya_train", "nyaya_val"}:
        kind = "generated_dialogue_candidate"
        turns = record.get("messages", [])
        content = " ".join(str(m.get("content", "")) for m in turns if m.get("role") == "user")
        issue.append("publisher_generated_unverified")
        issue.append("mixed_act_dialogue_not_complaint_label")
    elif source_key == "nyaya_eval":
        kind = "external_eval_holdout"
        content = str(record.get("question", ""))
        issue.append("never_training")
    elif source_key == "statutory_triage":
        kind = "short_triage_candidate"
        content = str(record.get("instruction", "")).strip()
        section = "BNS_" + str(record.get("bns_section_applied", "")).split("(")[0]
        issue.append("publisher_label_rejected")
        if number in reviewed:
            if reviewed[number] == "accepted_corrected":
                sid = f"TRIAGE_{number:05d}"
                if sid not in approved:
                    raise ValueError(f"Reviewed public row lacks accepted scenario: {sid}")
                approved_training = 1
                kind = "corrected_approved_train_example"
            else:
                issue.append("reviewed_held")
        else:
            issue.append("individual_review_missing")
    else:
        raise ValueError(source_key)
    if section and section not in known:
        issue.append("section_not_in_official_index")
    if len(content.split()) < 25:
        issue.append("short_content")
    if PII.search(content):
        issue.append("possible_personal_identifier")
    return {"source_key": source_key, "row_number": number,
            "source_row_sha256": expected_hash, "source_kind": kind,
            "candidate_provision_id": section, "word_count": len(content.split()),
            "issue_codes": sorted(set(issue)), "training_approved": approved_training}


def selected_rows(conn: sqlite3.Connection, sample: int | None) -> list[tuple]:
    if sample is None:
        return conn.execute("""SELECT source_key,row_number,row_sha256,record_json
            FROM public_candidate_row ORDER BY source_key,row_number""").fetchall()
    if sample < len(SOURCES):
        raise ValueError("Sample must include at least one row per source")
    per_source = sample // len(SOURCES)
    remainder = sample % len(SOURCES)
    rows = []
    for index, key in enumerate(SOURCES):
        limit = per_source + (index < remainder)
        rows.extend(conn.execute("""SELECT source_key,row_number,row_sha256,record_json
            FROM public_candidate_row WHERE source_key=? ORDER BY row_number LIMIT ?""",
            (key, limit)).fetchall())
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--sample", type=int)
    mode.add_argument("--full", action="store_true")
    args = parser.parse_args()
    sample = args.sample if args.sample is not None else None
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        known = {r[0] for r in conn.execute("SELECT provision_id FROM provision")}
        approved = {r[0] for r in conn.execute("""SELECT scenario_id FROM scenario
            WHERE quality_status='accepted' AND split='train'""")}
        reviewed = dict(conn.execute("""SELECT row_number,decision FROM public_candidate_review
            WHERE source_key='statutory_triage'"""))
        rows = selected_rows(conn, sample)
        screens = [classify(key, number, json.loads(value), digest, known, reviewed, approved)
                   for key, number, digest, value in rows]
        if sample is None and len(screens) != 6681:
            raise ValueError(f"Expected all 6,681 indexed rows, found {len(screens)}")
        sft_counts = inspect(compile_records(conn))
        accepted_count = conn.execute("SELECT count(*) FROM scenario WHERE quality_status='accepted'").fetchone()[0]
        pending_law = conn.execute("""SELECT count(*) FROM provision WHERE legal_status='pending_review'
            OR (legal_status='in_force' AND verified_text IS NULL)""").fetchone()[0]
        table_count = conn.execute("""SELECT count(*) FROM sqlite_master WHERE type='table'
            AND name NOT LIKE 'sqlite_%'""").fetchone()[0]
        if sample is None:
            conn.execute("""CREATE TABLE IF NOT EXISTS public_source_screen (
                source_key TEXT NOT NULL,
                row_number INTEGER NOT NULL,
                source_row_sha256 TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                candidate_provision_id TEXT,
                word_count INTEGER NOT NULL,
                issue_codes_json TEXT NOT NULL CHECK (json_valid(issue_codes_json)),
                training_approved INTEGER NOT NULL CHECK (training_approved IN (0,1)),
                screen_version TEXT NOT NULL,
                screened_on TEXT NOT NULL,
                PRIMARY KEY (source_key,row_number),
                FOREIGN KEY (source_key,row_number) REFERENCES public_candidate_row(source_key,row_number)
            )""")
            saved = [tuple(row) for row in conn.execute("""SELECT source_key,row_number,source_row_sha256,source_kind,
                candidate_provision_id,word_count,issue_codes_json,training_approved,screen_version
                FROM public_source_screen ORDER BY source_key,row_number""").fetchall()]
            expected = [(r["source_key"],r["row_number"],r["source_row_sha256"],r["source_kind"],
                         r["candidate_provision_id"],r["word_count"],json.dumps(r["issue_codes"],separators=(",", ":")),
                         r["training_approved"],VERSION) for r in screens]
            if saved and saved != expected:
                raise ValueError("Existing source screen differs; make a new screen version")
            if not saved:
                conn.executemany("INSERT INTO public_source_screen VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [r + (date.today().isoformat(),) for r in expected])
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Source screen foreign key failure")
            conn.commit()
    summary = {"mode": "sample" if sample is not None else "full", "screen_version": VERSION,
               "rows_screened": len(screens),
               "source_kinds": dict(Counter(r["source_kind"] for r in screens)),
               "approved_public_train_rows": sum(r["training_approved"] for r in screens),
               "issue_counts": dict(sorted(Counter(issue for r in screens for issue in r["issue_codes"]).items())),
               "conversational_sft_shape": sft_counts,
               "accepted_scenarios": accepted_count,
               "train_sft_records": sum(sft_counts["train"].values()),
               "train_sft_target": 3000,
               "train_sft_gap": max(0, 3000 - sum(sft_counts["train"].values())),
               "law_review_rows_remaining": pending_law,
               "master_sqlite_table_count": table_count,
               "first_complete_master_dataset": False,
               "new_training_examples_approved_by_automation": 0,
               "note": "Screening organizes all source rows; it does not approve unreviewed publisher labels or create fictional complaints."}
    path = OUT / ("automation_sample_report.json" if sample is not None else "automation_full_report.json")
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
