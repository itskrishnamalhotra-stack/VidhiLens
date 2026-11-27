"""Index every pinned public-source row inside the canonical master database.

This creates a searchable review pool. It never converts publisher labels into
accepted complaint labels or adds public rows to any training split.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from datetime import date

from build_full_kb import DB_PATH, ROOT, sha256


MANIFEST = ROOT / "external_candidates_manifest.json"
EXPECTED_COUNTS = {
    "bns_structured": 358,
    "bns_qa": 2148,
    "nyaya_train": 1293,
    "nyaya_val": 163,
    "nyaya_eval": 500,
    "statutory_triage": 2219,
}


def rows(path):
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array: {path}")
        yield from enumerate(data, 1)
    elif path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    raise ValueError(f"Blank source row: {path}:{number}")
                yield number, json.loads(line)
    else:
        raise ValueError(f"Unsupported source type: {path}")


def project_fields(key, row):
    if key == "bns_structured":
        return "law_crosscheck", str(row.get("section_number", "")), row.get("text", "")[:400]
    if key == "bns_qa":
        return "law_qa", str(row.get("section_number", "")), row.get("question", "")[:400]
    if key in {"nyaya_train", "nyaya_val"}:
        user_turns = [m.get("content", "") for m in row.get("messages", []) if m.get("role") == "user"]
        return "dialogue", None, (user_turns[-1] if user_turns else "")[:400]
    if key == "nyaya_eval":
        return "external_eval", None, row.get("question", "")[:400]
    if key == "statutory_triage":
        return "complaint_or_question", str(row.get("bns_section_applied", "")), row.get("instruction", "")[:400]
    raise ValueError(key)


def main():
    sources = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    if {source["key"] for source in sources} != set(EXPECTED_COUNTS):
        raise SystemExit("Public source manifest set changed; review index mapping")
    counts = Counter()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("""CREATE TABLE IF NOT EXISTS public_candidate_row (
            source_key TEXT NOT NULL,
            row_number INTEGER NOT NULL CHECK (row_number > 0),
            artifact_key TEXT NOT NULL REFERENCES dataset_artifact(artifact_key),
            row_sha256 TEXT NOT NULL,
            task_family TEXT NOT NULL,
            source_section_hint TEXT,
            input_preview TEXT NOT NULL,
            record_json TEXT NOT NULL CHECK (json_valid(record_json)),
            review_status TEXT NOT NULL CHECK (review_status IN
                ('quarantined_unreviewed','publisher_labels_rejected','external_eval_holdout')),
            PRIMARY KEY (source_key, row_number)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS public_candidate_row_task_idx ON public_candidate_row(task_family,source_section_hint)")
        conn.execute("""CREATE TABLE IF NOT EXISTS public_candidate_review (
            source_key TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            decision TEXT NOT NULL CHECK (decision IN ('accepted_corrected','held')),
            decision_note TEXT NOT NULL,
            review_ledger_sha256 TEXT NOT NULL,
            reviewed_on TEXT NOT NULL,
            PRIMARY KEY (source_key,row_number),
            FOREIGN KEY (source_key,row_number) REFERENCES public_candidate_row(source_key,row_number)
        )""")
        for source in sources:
            key = source["key"]
            path = ROOT / source["local_path"]
            if not path.is_file() or sha256(path) != source["sha256"]:
                raise SystemExit(f"Pinned public source differs: {key}")
            artifact_key = "public:" + key
            artifact = conn.execute("SELECT sha256 FROM dataset_artifact WHERE artifact_key=?", (artifact_key,)).fetchone()
            if not artifact or artifact[0] != source["sha256"]:
                raise SystemExit(f"Missing embedded source artifact: {key}")
            status = ("publisher_labels_rejected" if key == "statutory_triage" else
                      "external_eval_holdout" if key == "nyaya_eval" else
                      "quarantined_unreviewed")
            batch = []
            for number, record in rows(path):
                if not isinstance(record, dict):
                    raise SystemExit(f"Non-object row: {key}:{number}")
                family, section, preview = project_fields(key, record)
                content = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                batch.append((key, number, artifact_key, hashlib.sha256(content.encode("utf-8")).hexdigest(),
                              family, section, preview, content, status))
            if len(batch) != EXPECTED_COUNTS[key]:
                raise SystemExit(f"Source row count changed: {key}: {len(batch)}")
            existing = conn.execute("SELECT count(*) FROM public_candidate_row WHERE source_key=?", (key,)).fetchone()[0]
            if existing not in (0, len(batch)):
                raise SystemExit(f"Partial index exists for {key}: {existing}")
            if existing:
                saved = conn.execute("SELECT row_number,row_sha256,review_status FROM public_candidate_row WHERE source_key=? ORDER BY row_number", (key,)).fetchall()
                if saved != [(r[1], r[3], r[8]) for r in batch]:
                    raise SystemExit(f"Indexed source changed: {key}")
            else:
                conn.executemany("INSERT INTO public_candidate_row VALUES (?,?,?,?,?,?,?,?,?)", batch)
            counts[key] = len(batch)
        review_path = ROOT / "data_drafts" / "triage_review_batch01.jsonl"
        if review_path.exists():
            ledger_hash = sha256(review_path)
            review_rows = []
            for line in review_path.read_text(encoding="utf-8").splitlines():
                decision = json.loads(line)
                sid = decision["queue_id"]
                if not sid.startswith("TRIAGE_"):
                    raise SystemExit(f"Unexpected triage review ID: {sid}")
                number = int(sid.split("_")[1])
                record = conn.execute("SELECT record_json FROM public_candidate_row WHERE source_key='statutory_triage' AND row_number=?", (number,)).fetchone()
                if not record:
                    raise SystemExit(f"Missing indexed source row: {sid}")
                source_text = json.loads(record[0])["instruction"].strip()
                saved = conn.execute("SELECT complaint_text FROM scenario WHERE scenario_id=?", (sid,)).fetchone()
                if decision["decision"] == "accept":
                    if not saved or saved[0] != source_text:
                        raise SystemExit(f"Accepted review not linked to source text: {sid}")
                    status = "accepted_corrected"
                    note = decision["challenge_note"]
                elif decision["decision"] == "hold":
                    if saved:
                        raise SystemExit(f"Held public row entered scenario table: {sid}")
                    status = "held"
                    note = decision["hold_reason"]
                else:
                    raise SystemExit(f"Invalid review decision: {sid}")
                review_rows.append(("statutory_triage", number, status, note, ledger_hash, date.today().isoformat()))
            if len(review_rows) != 104 or len({r[1] for r in review_rows}) != 104:
                raise SystemExit("Triage review must cover 104 unique queued source rows")
            existing = conn.execute("SELECT source_key,row_number,decision,decision_note,review_ledger_sha256 FROM public_candidate_review").fetchall()
            expected = [r[:5] for r in review_rows]
            if existing and sorted(existing) != sorted(expected):
                raise SystemExit("Pinned public review decisions changed")
            conn.executemany("INSERT OR IGNORE INTO public_candidate_review VALUES (?,?,?,?,?,?)", review_rows)
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise SystemExit("Public row index foreign-key error")
        conn.commit()
        assert conn.execute("SELECT count(*) FROM public_candidate_row").fetchone()[0] == sum(EXPECTED_COUNTS.values())
        assert conn.execute("SELECT count(*) FROM public_candidate_row WHERE review_status NOT IN ('quarantined_unreviewed','publisher_labels_rejected','external_eval_holdout')").fetchone()[0] == 0
    print(json.dumps({"indexed_rows": sum(counts.values()), "by_source": dict(counts),
                      "training_rows_added": 0}, indent=2))


if __name__ == "__main__":
    main()
