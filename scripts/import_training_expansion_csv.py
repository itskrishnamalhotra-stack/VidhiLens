"""Import one family-reviewed synthetic CSV batch as train-only silver examples."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
CSV_PATH = ROOT / "data_drafts" / "synthetic_training_expansion_v1.csv"


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normal(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def main() -> None:
    data = CSV_PATH.read_bytes()
    csv_hash = sha(data)
    with CSV_PATH.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 2760:
        raise SystemExit(f"Expected one complete 2,760-row batch, got {len(rows)}")
    if len({r["scenario_id"] for r in rows}) != len(rows):
        raise SystemExit("Duplicate CSV IDs")
    if len({normal(r["complaint_text"]) for r in rows}) != len(rows):
        raise SystemExit("Duplicate CSV complaint text")

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["family_id"]].append(row)
    if len(groups) != 115 or any(len(group) != 24 for group in groups.values()):
        raise SystemExit("Incomplete or imbalanced fact-pattern families")
    for family, members in groups.items():
        constant = ("expected_outcome", "possible_provision_ids", "uncertain_provision_ids",
                    "missing_facts", "rationale", "family_pattern_sha256", "source_pages")
        if any(any(row[field] != members[0][field] for field in constant) for row in members):
            raise SystemExit(f"Inconsistent labels within family: {family}")

    today = date.today().isoformat()
    inserted = skipped = 0
    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        allowed = {r[0]: r[1] for r in conn.execute(
            "SELECT provision_id,source_pdf_page FROM recommendable_provision")}
        verified = {r[0] for r in conn.execute(
            "SELECT provision_id FROM provision WHERE verified_text IS NOT NULL")}
        occupied = {normal(text): sid for sid, text in conn.execute(
            "SELECT scenario_id,complaint_text FROM scenario WHERE quality_status='accepted'")}
        for row in rows:
            sid, text = row["scenario_id"], row["complaint_text"]
            if row["scenario_group"] != row["family_id"] or row["language"] != "en":
                raise SystemExit(f"Invalid family/language: {sid}")
            if row["provenance_type"] != "synthetic" or row["review_tier"] != "silver":
                raise SystemExit(f"Invalid provenance or tier: {sid}")
            if len(text.split()) < 20 or any(ch in text for ch in ("@", "\n", "\r")):
                raise SystemExit(f"Bad text or possible personal data: {sid}")
            positives = json.loads(row["possible_provision_ids"])
            uncertain = json.loads(row["uncertain_provision_ids"])
            source_pages = json.loads(row["source_pages"])
            outcome = row["expected_outcome"]
            if outcome not in ("provision_match", "insufficient_information", "out_of_scope"):
                raise SystemExit(f"Invalid outcome: {sid}")
            if (outcome == "provision_match") != bool(positives):
                raise SystemExit(f"Outcome/positive mismatch: {sid}")
            if outcome == "out_of_scope" and uncertain:
                raise SystemExit(f"Out-of-scope row has uncertain section: {sid}")
            if uncertain and not row["missing_facts"]:
                raise SystemExit(f"Uncertain row has no missing fact: {sid}")
            if len(set(positives + uncertain)) != len(positives + uncertain):
                raise SystemExit(f"Duplicate section label: {sid}")
            if any(pid not in allowed for pid in positives):
                raise SystemExit(f"Positive section outside pilot: {sid}")
            if any(pid not in verified for pid in uncertain):
                raise SystemExit(f"Uncertain section lacks verified text: {sid}")
            if source_pages != {pid: allowed[pid] for pid in positives + uncertain}:
                raise SystemExit(f"Source page mismatch: {sid}")
            existing = conn.execute("SELECT complaint_text,expected_outcome,review_tier,split "
                                    "FROM scenario WHERE scenario_id=?", (sid,)).fetchone()
            if existing:
                if existing != (text, outcome, "silver", "train"):
                    raise SystemExit(f"Existing row differs: {sid}")
                skipped += 1
                continue
            norm = normal(text)
            if norm in occupied:
                raise SystemExit(f"Duplicate complaint text: {sid}/{occupied[norm]}")
            occupied[norm] = sid
            note = {
                "batch_csv_sha256": csv_hash,
                "fact_pattern_family": row["family_id"],
                "family_pattern_sha256": row["family_pattern_sha256"],
                "source_pages": source_pages,
                "variation_note": row["variation_note"],
                "review_scope": "AI-authored and source-checked fact-pattern family; surface variants mechanically checked, not individually legal-reviewed",
            }
            conn.execute("""INSERT INTO scenario
                (scenario_id,complaint_text,language,provenance_type,privacy_reviewed,
                 quality_status,expected_outcome,review_tier,reviewer,reviewed_on,
                 split,scenario_group,created_on,review_note)
                VALUES (?,?,'en','synthetic',1,'accepted',?,'silver',?,?,'train',?,?,?)""",
                (sid, text, outcome, "Codex AI family review plus deterministic variant audit", today,
                 row["family_id"], today, json.dumps(note, sort_keys=True)))
            for pid in positives + uncertain:
                label = "possible" if pid in positives else "uncertain"
                conn.execute("""INSERT INTO scenario_provision_label
                    (scenario_id,provision_id,label,rationale,missing_facts,reviewer,reviewed_on)
                    VALUES (?,?,?,?,?,?,?)""",
                    (sid, pid, label, row["rationale"], row["missing_facts"] if label == "uncertain" else None,
                     "Codex AI family review plus deterministic variant audit", today))
            inserted += 1
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise SystemExit("Foreign key check failed")
        conn.commit()
    print(json.dumps({"csv": str(CSV_PATH), "sha256": csv_hash,
                      "inserted": inserted, "already_present": skipped,
                      "families": len(groups), "review_tier": "silver",
                      "counts": dict(Counter(r["expected_outcome"] for r in rows))}, indent=2))


if __name__ == "__main__":
    main()
