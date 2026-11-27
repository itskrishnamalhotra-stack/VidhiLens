"""Read a granted IPC complaint file locally and report candidate quality safely.

No complaint text is copied into a report or approved for training. JSONL streams
with the standard library; large JSON arrays require optional ``ijson``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from build_full_kb import DB_PATH, ROOT, sha256


IPC = re.compile(r"^(?:IPC\s*(?:section\s*)?)?(\d{1,3}[A-Z]?)$", re.I)
EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?<!\d)(?:\+91[- ]?)?[6-9]\d{9}(?!\d)")
AADHAAR_LIKE = re.compile(r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)")
PAN_LIKE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")


def records(path: Path):
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8-sig") as stream:
            for number, line in enumerate(stream, start=1):
                if line.strip():
                    yield number, json.loads(line)
        return
    if path.suffix.lower() != ".json":
        raise ValueError("Supply a .jsonl or .json file")
    try:
        import ijson
    except ImportError as exc:
        raise RuntimeError("For JSON arrays, install ijson for low-memory streaming: python -m pip install ijson") from exc
    with path.open("rb") as stream:
        for number, row in enumerate(ijson.items(stream, "item"), start=1):
            yield number, row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path, help="Granted dataset .jsonl or .json under phase1/external_candidates")
    args = parser.parse_args()
    path = args.file.resolve()
    if not path.is_file() or not path.is_relative_to((ROOT / "external_candidates").resolve()):
        raise SystemExit("Input must be a local file under phase1/external_candidates")
    with sqlite3.connect(DB_PATH) as conn:
        crosswalk = {}
        for ipc, bns in conn.execute("SELECT ipc_section,bns_provision_id FROM ipc_bns_crosswalk_candidate"):
            crosswalk.setdefault(ipc, []).append(bns)
    counts = Counter()
    issues = Counter()
    seen_ids = set()
    seen_text = set()
    output = ROOT / "data_drafts" / "restricted_ipc_complaints_preflight.jsonl"
    with output.open("w", encoding="utf-8") as result:
        for number, row in records(path):
            counts["rows"] += 1
            flags = []
            if not isinstance(row, dict):
                flags.append("not_an_object")
                row = {}
            rid, complaint, labels = row.get("id"), row.get("text"), row.get("labels")
            if not isinstance(rid, (str, int)) or not str(rid).strip():
                flags.append("missing_id")
            elif str(rid) in seen_ids:
                flags.append("duplicate_id")
            else:
                seen_ids.add(str(rid))
            if not isinstance(complaint, str) or not complaint.strip():
                flags.append("missing_complaint_text")
                complaint = ""
            normalized = " ".join(complaint.casefold().split())
            complaint_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            if normalized in seen_text:
                flags.append("duplicate_complaint_text")
            elif normalized:
                seen_text.add(normalized)
            if len(complaint.split()) < 25:
                flags.append("short_complaint")
            if EMAIL.search(complaint) or PHONE.search(complaint) or AADHAAR_LIKE.search(complaint) or PAN_LIKE.search(complaint):
                flags.append("possible_personal_identifier")
            if not isinstance(labels, list) or not labels:
                flags.append("missing_ipc_labels")
                labels = []
            ipc_labels = []
            for value in labels:
                parsed = IPC.fullmatch(str(value).strip())
                if parsed:
                    ipc_labels.append(parsed.group(1).upper())
                else:
                    flags.append("unparsed_ipc_label")
            candidates = sorted({bns for ipc in ipc_labels for bns in crosswalk.get(ipc, [])})
            if ipc_labels and not candidates:
                flags.append("no_official_bns_correspondence")
            if len(candidates) > 1:
                flags.append("multiple_bns_candidates")
            if not flags:
                counts["shape_pass_rows"] += 1
            for flag in set(flags):
                issues[flag] += 1
            result.write(json.dumps({"row_number": number,
                                     "source_id_sha256": hashlib.sha256(str(rid).encode("utf-8")).hexdigest(),
                                     "normalized_complaint_sha256": complaint_hash,
                                     "word_count": len(complaint.split()),
                                     "ipc_labels": sorted(set(ipc_labels)),
                                     "bns_correspondence_candidates": candidates,
                                     "issue_codes": sorted(set(flags)),
                                     "privacy_review_required": True,
                                     "legal_label_review_required": True,
                                     "training_approved": False}, ensure_ascii=False) + "\n")
    report = {"input_path": str(path), "input_sha256": sha256(path),
              "rows": counts["rows"], "shape_pass_rows": counts["shape_pass_rows"],
              "issue_counts": dict(sorted(issues.items())),
              "preflight_path": str(output), "preflight_sha256": sha256(output),
              "training_approved": 0,
              "note": "Shape and identifier scans are a lower bound on privacy and legal problems. Raw complaints remain quarantined until access terms, de-identification, IPC/BNS elements, and labels are reviewed."}
    destination = ROOT / "data_drafts" / "restricted_ipc_complaints_preflight_report.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("input_path", "input_sha256")}, indent=2))


if __name__ == "__main__":
    main()
