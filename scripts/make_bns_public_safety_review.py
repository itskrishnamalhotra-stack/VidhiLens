"""Write the AI-reviewed ledger for 15 visually checked BNS sections.

Only the exact pages and IDs inspected on 17 September 2026 are included.
The generic importer independently verifies the source hash and each edit.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from build_full_kb import DB_PATH, ROOT


REVIEW = {
    271: (83, "Likely infection spread, unlawful or negligent act, and knowledge or reason to believe are material."),
    273: (84, "Requires knowing disobedience of a government quarantine rule; an ordinary illness report alone is insufficient."),
    274: (84, "Food or drink is made noxious with intended or likely sale; the sale element must not be assumed."),
    275: (84, "Requires sale or offer of noxious or unfit food or drink with knowledge or reason to believe."),
    276: (84, "Drug adulteration must affect efficacy, operation, or safety and be intended or likely for medicinal sale or use."),
    277: (84, "Requires knowledge of drug adulteration and sale, offer, dispensing, or unknowing medicinal use."),
    278: (84, "Requires knowing sale, offer, or dispensing of a drug as a different drug or preparation."),
    279: (84, "Requires voluntary fouling of water in a public spring or reservoir so it is less fit for its ordinary use."),
    280: (84, "Requires voluntary atmosphere contamination affecting persons generally in the described area."),
    281: (84, "Requires rash or negligent driving or riding on a public way with endangerment or likely injury."),
    283: (85, "Requires a false light, mark, or buoy displayed intending or knowing it will likely mislead a navigator."),
    284: (85, "Requires conveyance by water for hire in a dangerous vessel, knowingly or negligently."),
    285: (85, "Requires danger, obstruction, or injury in a public way or navigation line from an act or property-related omission."),
    286: (85, "Requires rash or negligent conduct with poison or failure to guard a possessed poisonous substance."),
    287: (85, "Requires rash or negligent conduct with fire or combustible matter or failure to guard it in possession."),
}


def main() -> None:
    packets = ROOT / "data_drafts" / "law_preflight_packets"
    preflight = {row["provision_id"]: row for path in sorted(packets.glob("packet_*.jsonl"))
                 for row in map(json.loads, path.read_text(encoding="utf-8").splitlines())}
    editorial = {"embedded_page_number", "chapter_heading_lines", "editorial_amendment_markers",
                 "amendment_footnote_lines", "possible_civil_penalty_wording"}
    decisions = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        for number, (page, element_note) in REVIEW.items():
            pid = f"BNS_{number}"
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            check = preflight[pid]
            if (row["source_id"] != "BNS_INDIA_CODE_2025_10_06" or
                    row["source_pdf_page"] != page or row["legal_status"] != "in_force" or
                    row["verified_text"] is not None or row["recommendable"] or
                    check["five_token_sequence_recall"] != 1.0 or
                    editorial.intersection(check["mechanical_flags"]) or
                    row["extracted_text"].count("\u2014") != 1 or
                    "\ufffd" in row["extracted_text"] or
                    check["extracted_text"] != row["extracted_text"]):
                raise ValueError(f"Review precondition failed: {pid}")
            decisions.append({"provision_id": pid, "source_id": row["source_id"],
                              "source_pdf_page": page,
                              "extracted_text_sha256": hashlib.sha256(row["extracted_text"].encode("utf-8")).hexdigest(),
                              "provision_kind": "offence", "legal_status": "in_force",
                              "visually_checked_pdf_pages": [page], "remove_lines": [],
                              "replace": [],
                              "review_note": (f"Official BNS PDF page {page} visually checked; dual-parser five-token recall is 1.0. "
                                              + element_note + " No complaint suggestion approved by this text review.")})
    output = ROOT / "data_drafts" / "bns_public_safety_review_batch04.jsonl"
    output.write_text("".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
                              for item in decisions), encoding="utf-8")
    print(json.dumps({"reviewed_ledger": str(output), "sections": len(decisions)}, indent=2))


if __name__ == "__main__":
    main()
