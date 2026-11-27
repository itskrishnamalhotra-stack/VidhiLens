"""Prepare the complete in-scope quarantined complaint wording queue for review.

Never imports online labels into the KB or treats source metadata as legal truth.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter

from build_full_kb import DB_PATH, ROOT, sha256


def main() -> None:
    manifest = json.loads((ROOT / "external_candidates_manifest.json").read_text(encoding="utf-8"))
    source = next(x for x in manifest["files"] if x["key"] == "statutory_triage")
    path = ROOT / source["local_path"]
    if sha256(path) != source["sha256"]:
        raise SystemExit("External candidate source hash mismatch")
    with sqlite3.connect(DB_PATH) as conn:
        allowed = {r[0] for r in conn.execute("SELECT provision_id FROM recommendable_provision")}
        accepted_count = conn.execute("SELECT count(*) FROM scenario WHERE quality_status='accepted'").fetchone()[0]
    seed_path = ROOT / "data_drafts" / "seed_scenarios.jsonl"
    seeds = [json.loads(line) for line in seed_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    queue = []
    for row in seeds:
        queue.append({
            "queue_id": row["draft_id"],
            "complaint_text": row["complaint_text"],
            "source_type": "fictional_project_draft",
            "source_key": "make_seed_drafts.py",
            "source_row": row["draft_id"],
            "source_license": "project_created",
            "source_suggested_section": row["focus_id"],
            "source_suggested_outcome": row["candidate_outcome"],
            "review_status": "pending_review",
            "imported_to_kb": False,
        })
    selected = Counter()
    seen = {hashlib.sha256(row["complaint_text"].casefold().encode()).hexdigest() for row in queue}
    with path.open(encoding="utf-8") as stream:
        for row_number, line in enumerate(stream, 1):
            item = json.loads(line)
            section = "BNS_" + str(item.get("bns_section_applied", "")).split("(")[0]
            if section not in allowed:
                continue
            complaint = str(item.get("instruction", "")).strip()
            digest = hashlib.sha256(complaint.casefold().encode()).hexdigest()
            if len(complaint) < 40 or digest in seen:
                continue
            seen.add(digest)
            selected[section] += 1
            queue.append({
                "queue_id": f"TRIAGE_{row_number:05d}",
                "complaint_text": complaint,
                "source_type": "public_licensed_unreviewed",
                "source_key": "statutory_triage",
                "source_row": row_number,
                "source_sha256": source["sha256"],
                "source_url": source["url"],
                "source_license": source["license"],
                "source_suggested_section": section,
                "source_suggested_outcome": "unverified",
                "review_status": "pending_review",
                "imported_to_kb": False,
            })
    out = ROOT / "data_drafts" / "review_queue.jsonl"
    out.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in queue) + "\n", encoding="utf-8")
    report = {"queue_rows": len(queue), "fictional_project_drafts": len(seeds),
              "public_unreviewed_candidates": len(queue) - len(seeds),
              "public_candidates_by_suggested_section": dict(sorted(selected.items())),
              "accepted_kb_scenarios": accepted_count,
              "warning": "Publisher section IDs and outcomes are unverified. Review privacy, wording, facts, legal labels and provenance before KB import."}
    (ROOT / "data_drafts" / "review_queue_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
