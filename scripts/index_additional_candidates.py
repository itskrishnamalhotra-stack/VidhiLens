"""Index newly audited datasets without promoting publisher claims to gold labels.

This script is idempotent. The original files and revision hashes are pinned in
additional_candidates_manifest.json. Training approval stays at zero.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from build_full_kb import DB_PATH, ROOT, sha256


MANIFEST = ROOT / "additional_candidates_manifest.json"
REPORT = ROOT / "additional_candidates_screening_report.json"


def entries(path: Path):
    if path.suffix == ".parquet":
        for i, row in enumerate(pd.read_parquet(path).to_dict("records"), 1):
            yield i, row
    else:
        with path.open(encoding="utf-8") as stream:
            for i, line in enumerate(stream, 1):
                if not line.strip():
                    raise ValueError(f"Blank row {path}:{i}")
                yield i, json.loads(line)


def canonical_labels(key: str, row: dict):
    if key == "nariraksha":
        source = row["legal_context"]
        pattern = r"\b(BNS|IT Act)\s+Sections?\s+(\d+[A-Z]?(?:\(\d+\))?)"
        return [("BNS" if act == "BNS" else "IT_ACT") + ":" + sec
                for act, sec in re.findall(pattern, source, re.I)]
    if key == "complaint_bns":
        return ["BNS:" + token.strip() for token in row["output"].split(",") if token.strip()]
    if key.startswith("nyaya_v3_"):
        return [s.upper().replace("IT_ACT_2000:", "IT_ACT:").replace("BNS_2023:", "BNS:")
                for s in row.get("metadata", {}).get("source_sections", [])
                if s.startswith(("bns_2023:", "it_act_2000:"))]
    if key == "nyaya_statute_bns":
        return ["BNS:" + str(row["section"])]
    if key == "nyaya_statute_it":
        return ["IT_ACT:" + str(row["section"])]
    return []  # Citations inside cyber answers are not validated labels.


def screen(key: str, row: dict, known: set[str]):
    labels = canonical_labels(key, row)
    issues = []
    if key == "nariraksha":
        text = row["scenario"]
        family = "synthetic_scenario"
        issues += ["synthetic_template", "publisher_labels_unverified"]
    elif key == "complaint_bns":
        text = row["input"]
        family = "synthetic_complaint"
        issues += ["publisher_labels_unverified", "license_unspecified"]
        if "while I was carrying out my usual activities" in text:
            issues.append("generic_allegation_template")
        if re.search(r"\bsection\s*\d+", text, re.I):
            issues.append("section_answer_in_input")
        if re.search(r"\b(?:0[1-6])-\d{2}-2024\b", text):
            issues.append("pre_bns_commencement_date")
    elif key.startswith("nyaya_v3_"):
        text = row.get("metadata", {}).get("rag", {}).get("question", "")
        family = "grounded_qa"
        issues.append("publisher_verified_false" if row.get("metadata", {}).get("verified") is False else "publisher_verification_unknown")
        if key == "nyaya_v3_test":
            issues.append("publisher_test_split_do_not_train")
    elif key == "fraud_cyber":
        text = row["user_query"]
        family = "cyber_question"
        issues += ["license_unspecified", "answer_citations_not_labels"]
    else:
        text = row["text"]
        family = "third_party_statute_crosscheck"
        issues.append("official_source_required")
    if not text.strip():
        issues.append("empty_input")
    for label in labels:
        if label not in known and label.split("(")[0] not in known:
            issues.append("section_not_in_canonical_index")
            break
    return text, family, labels, sorted(set(issues))


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    totals = Counter()
    by_source = defaultdict(Counter)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        known = {("BNS:" if act == "BNS_2023" else "IT_ACT:") + section.upper()
                 for act, section in conn.execute("SELECT act_id,section_number FROM provision")}
        conn.execute("""CREATE TABLE IF NOT EXISTS additional_candidate_source (
            source_key TEXT PRIMARY KEY, repo TEXT NOT NULL, revision TEXT NOT NULL,
            remote_path TEXT NOT NULL, relative_path TEXT NOT NULL, sha256 TEXT NOT NULL,
            bytes INTEGER NOT NULL, license_json TEXT NOT NULL, source_url TEXT NOT NULL,
            row_count INTEGER NOT NULL, training_approved INTEGER NOT NULL DEFAULT 0
                CHECK(training_approved=0)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS additional_candidate_row (
            source_key TEXT NOT NULL REFERENCES additional_candidate_source(source_key),
            row_number INTEGER NOT NULL, row_sha256 TEXT NOT NULL,
            task_family TEXT NOT NULL, input_text TEXT NOT NULL,
            publisher_labels_json TEXT NOT NULL CHECK(json_valid(publisher_labels_json)),
            issue_codes_json TEXT NOT NULL CHECK(json_valid(issue_codes_json)),
            record_json TEXT NOT NULL CHECK(json_valid(record_json)),
            training_approved INTEGER NOT NULL DEFAULT 0 CHECK(training_approved=0),
            PRIMARY KEY(source_key,row_number)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS additional_candidate_task_idx ON additional_candidate_row(task_family,source_key)")
        for source in manifest:
            key = source["key"]
            path = ROOT / source["local_path"]
            if not path.is_file() or sha256(path) != source["sha256"] or path.stat().st_size != source["bytes"]:
                raise ValueError(f"Pinned source mismatch: {key}")
            expected = (key, source["repo"], source["revision"], source["remote_path"],
                        source["local_path"], source["sha256"], source["bytes"],
                        json.dumps(source["license"]), source["url"])
            saved = conn.execute("SELECT source_key,repo,revision,remote_path,relative_path,sha256,bytes,license_json,source_url FROM additional_candidate_source WHERE source_key=?", (key,)).fetchone()
            if saved and saved != expected:
                raise ValueError(f"Source metadata changed: {key}")
            conn.execute("INSERT OR IGNORE INTO additional_candidate_source(source_key,repo,revision,remote_path,relative_path,sha256,bytes,license_json,source_url,row_count) VALUES(?,?,?,?,?,?,?,?,?,0)", expected)
            batch = []
            for number, row in entries(path):
                if not isinstance(row, dict):
                    raise ValueError(f"Not an object: {key}:{number}")
                text, family, labels, issues = screen(key, row, known)
                record = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                row_hash = hashlib.sha256(record.encode("utf-8")).hexdigest()
                batch.append((key, number, row_hash, family, text,
                              json.dumps(labels, ensure_ascii=False), json.dumps(issues), record))
                totals["rows"] += 1
                by_source[key]["rows"] += 1
                by_source[key]["rows_with_bns_it_hint"] += bool(labels)
                for issue in issues:
                    by_source[key][issue] += 1
                if len(batch) >= 500:
                    conn.executemany("INSERT OR IGNORE INTO additional_candidate_row(source_key,row_number,row_sha256,task_family,input_text,publisher_labels_json,issue_codes_json,record_json) VALUES(?,?,?,?,?,?,?,?)", batch)
                    batch.clear()
            if batch:
                conn.executemany("INSERT OR IGNORE INTO additional_candidate_row(source_key,row_number,row_sha256,task_family,input_text,publisher_labels_json,issue_codes_json,record_json) VALUES(?,?,?,?,?,?,?,?)", batch)
            actual = conn.execute("SELECT count(*) FROM additional_candidate_row WHERE source_key=?", (key,)).fetchone()[0]
            if actual != by_source[key]["rows"]:
                raise ValueError(f"Indexed row count mismatch: {key}")
            conn.execute("UPDATE additional_candidate_source SET row_count=? WHERE source_key=?", (actual, key))
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key check failed")
        if conn.execute("SELECT count(*) FROM additional_candidate_row WHERE training_approved!=0").fetchone()[0]:
            raise ValueError("Unreviewed source entered training")
        conn.commit()
    report = {"indexed_rows": totals["rows"], "training_rows_approved": 0,
              "source_counts": {k: dict(v) for k, v in by_source.items()},
              "warning": "Publisher labels and third-party statute text are candidate research only. Legal verification requires official law text and fact review."}
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
