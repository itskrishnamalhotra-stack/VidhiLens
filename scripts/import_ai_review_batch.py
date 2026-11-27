"""Import a source-grounded, individually reviewed JSONL batch into the KB.

The review ledger is authored separately from the candidate queue. Publisher labels
are ignored. Every accepted positive ID is checked against the current allowlist.
All early reviewed examples are train-only; sealed test cases will be authored and
assigned separately before model selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

from build_full_kb import DB_PATH, ROOT, sha256


REVIEWER = "Codex AI source-grounded review"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("review_file", type=Path)
    args = parser.parse_args()
    review_path = args.review_file.resolve()
    if not review_path.is_relative_to((ROOT / "data_drafts").resolve()):
        raise SystemExit("Review file must be within phase1/data_drafts")
    queue_path = ROOT / "data_drafts" / "review_queue.jsonl"
    queue = {row["queue_id"]: row for row in read_jsonl(queue_path)}
    decisions = read_jsonl(review_path)
    if len({row["queue_id"] for row in decisions}) != len(decisions):
        raise SystemExit("Duplicate queue_id in review ledger")

    today = date.today().isoformat()
    inserted = skipped = held = 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        allowed = {
            row[0]: (row[1], row[2])
            for row in conn.execute("SELECT provision_id, source_id, verified_text FROM recommendable_provision")
        }
        known = {
            row[0]: row[1]
            for row in conn.execute("SELECT provision_id, verified_text FROM provision")
        }
        for decision in decisions:
            sid = decision["queue_id"]
            if sid not in queue:
                raise SystemExit(f"Unknown queue ID: {sid}")
            candidate = queue[sid]
            if decision["decision"] == "hold":
                held += 1
                continue
            if decision["decision"] != "accept":
                raise SystemExit(f"Unknown decision for {sid}")
            labels = decision["labels"]
            positives = [row["provision_id"] for row in labels if row["label"] == "possible"]
            outcome = decision["expected_outcome"]
            if (outcome == "provision_match") != bool(positives):
                raise SystemExit(f"Outcome/positive label mismatch: {sid}")
            if not decision.get("challenge_note") or not decision.get("followup_question"):
                raise SystemExit(f"Missing challenge/follow-up review: {sid}")
            for label in labels:
                pid = label["provision_id"]
                if pid not in known or not known[pid]:
                    raise SystemExit(f"Label lacks source-checked text: {sid}/{pid}")
                if label["label"] == "possible" and pid not in allowed:
                    raise SystemExit(f"Positive label not recommendable: {sid}/{pid}")
                if label["label"] == "uncertain" and not label.get("missing_facts"):
                    raise SystemExit(f"Uncertain label lacks missing fact: {sid}/{pid}")
                if not label.get("rationale"):
                    raise SystemExit(f"Label lacks review rationale: {sid}/{pid}")
            existing = conn.execute(
                "SELECT complaint_text, expected_outcome, review_tier FROM scenario WHERE scenario_id=?", (sid,)
            ).fetchone()
            if existing:
                if existing != (candidate["complaint_text"], outcome, "ai_reviewed"):
                    raise SystemExit(f"Existing review differs: {sid}")
                skipped += 1
                continue
            provenance = "synthetic" if candidate["source_type"] == "fictional_project_draft" else "public_licensed"
            source_hashes = {
                label["provision_id"]: hashlib.sha256(known[label["provision_id"]].encode("utf-8")).hexdigest()
                for label in labels
            }
            note = {
                "queue_id": sid,
                "candidate_text_sha256": hashlib.sha256(candidate["complaint_text"].encode("utf-8")).hexdigest(),
                "review_ledger_sha256": sha256(review_path),
                "publisher_suggestion_not_used_as_truth": True,
                "challenge_note": decision["challenge_note"],
                "followup_question": decision["followup_question"],
                "source_text_sha256_by_label": source_hashes,
            }
            conn.execute(
                """INSERT INTO scenario
                (scenario_id, complaint_text, language, provenance_type, source_url, license,
                 privacy_reviewed, quality_status, expected_outcome, review_tier, reviewer,
                 reviewed_on, split, scenario_group, created_on, review_note)
                VALUES (?, ?, 'en', ?, ?, ?, 1, 'accepted', ?, 'ai_reviewed', ?, ?,
                        'train', ?, ?, ?)""",
                (sid, candidate["complaint_text"], provenance, candidate.get("source_url"),
                 candidate.get("source_license"), outcome, REVIEWER, today,
                 candidate.get("scenario_group", sid), today, json.dumps(note, ensure_ascii=False, sort_keys=True)),
            )
            for label in labels:
                conn.execute(
                    """INSERT INTO scenario_provision_label
                    (scenario_id, provision_id, label, rationale, missing_facts, reviewer, reviewed_on)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (sid, label["provision_id"], label["label"], label["rationale"],
                     label.get("missing_facts"), REVIEWER, today),
                )
            inserted += 1
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise SystemExit("Foreign key errors; import rolled back")
        conn.commit()
    print(json.dumps({"review_file": str(review_path), "inserted": inserted,
                      "already_present": skipped, "held": held, "split": "train"}, indent=2))


if __name__ == "__main__":
    main()
