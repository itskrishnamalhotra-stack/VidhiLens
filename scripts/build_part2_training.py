"""Validate Part 2 fact-gap/section-boundary cases and create train-only artifacts.

The triage uncertainty subset can enter the existing research SFT pipeline.
Candidate checks have a distinct task schema: unsupported for one provision
must never be converted to a global out_of_scope answer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
SOURCE = ROOT / "data_drafts" / "part2_v1_cases.jsonl"
COVERAGE_BATCH = ROOT / "data_drafts" / "coverage_batch15.json"
OUT = ROOT / "exports" / "part2_candidate_checks_v1_research"
SYSTEM = (
    "Assess only the named BNS or IT Act candidate section against the reported facts. "
    "Return JSON with label, missing_facts, and reason. Labels are possible, uncertain, "
    "or unsupported. Unsupported for this section does not mean no other law applies. "
    "Treat allegations as reported facts, not proven facts; do not invent missing facts."
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                            for row in rows), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate Part 2 ID")
    ids = {r["target"] for r in rows}
    counts = Counter((r["target"], r["label"]) for r in rows)
    if len(ids) != 19 or any(counts[(pid, label)] != 1 for pid in ids
                              for label in ("uncertain", "unsupported")) or len(rows) != 38:
        raise ValueError("Expected exactly one uncertainty and one boundary case for each of 19 release sections")
    with sqlite3.connect(DB) as conn:
        laws = {pid: (status, kind, verified_text, source_id, source_page)
                for pid, status, kind, verified_text, source_id, source_page in conn.execute(
                    "SELECT provision_id,legal_status,provision_kind,verified_text,source_id,source_pdf_page FROM provision")}
        release = {x[0] for x in conn.execute("SELECT provision_id FROM recommendable_provision")}
    if ids != release:
        raise ValueError(f"Part 2 coverage differs from release scope: missing={release-ids}, extra={ids-release}")
    seen_text = set()
    sft, mapping, uncertainty = [], [], []
    for row in rows:
        pid, label, complaint = row["target"], row["label"], row["complaint"]
        if label not in ("uncertain", "unsupported") or len(complaint.split()) < 26:
            raise ValueError(f"Invalid label or short case: {row['id']}")
        if re.search(r"https?://|\b\S+@\S+\b", complaint, re.I):
            raise ValueError(f"URL or personal identifier: {row['id']}")
        normal = " ".join(re.findall(r"\w+", complaint.casefold()))
        if normal in seen_text:
            raise ValueError(f"Repeated complaint: {row['id']}")
        seen_text.add(normal)
        status, kind, law_text, source_id, page = laws[pid]
        if status != "in_force" or kind != "offence" or not law_text:
            raise ValueError(f"Noneligible law: {pid}")
        if not row["reason"] or (label == "uncertain") != bool(row["missing_fact"]):
            raise ValueError(f"Invalid rationale/fact gap: {row['id']}")
        alternatives = row.get("other_possible_ids", [])
        if any(a not in laws or laws[a][0] != "in_force" for a in alternatives):
            raise ValueError(f"Invalid alternative section: {row['id']}")
        answer = {"label": label,
                  "missing_facts": [row["missing_fact"]] if label == "uncertain" else [],
                  "reason": row["reason"]}
        user = json.dumps({"complaint": complaint, "candidate_provision_id": pid},
                          ensure_ascii=False, separators=(",", ":"))
        sft.append({"messages": [{"role": "system", "content": SYSTEM},
                                  {"role": "user", "content": user},
                                  {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False,
                                                                               separators=(",", ":"))}]})
        mapping.append({"source_id": row["id"], "split": "train", "kind": "candidate_check",
                        "target_provision_id": pid, "label": label, "review_status": "AI_authored_research_candidate",
                        "source_id_of_law": source_id, "source_pdf_page": page,
                        "verified_text_sha256": sha(law_text.encode()),
                        "other_possible_ids": alternatives})
        if label == "uncertain":
            uncertainty.append({"id": row["id"], "split": "train", "provision_id": pid,
                                "outcome": "insufficient_information", "input": complaint,
                                "missing_facts": row["missing_fact"],
                                "review_note": row["reason"] + " AI-authored research candidate; no app approval."})
    coverage = {"review_status": "AI_authored_part2_statutory_gap_research_candidate",
                "scope": "Train-only missing-fact examples for 19 release sections; boundary checks remain a separate task",
                "case_targets": {pid: {"train_insufficient_information": 1} for pid in sorted(ids)},
                "cases": uncertainty}
    report = {"source": str(SOURCE.relative_to(ROOT)), "case_count": len(rows),
              "uncertainty_train": len(uncertainty), "unsupported_candidate_checks": len(rows)-len(uncertainty),
              "covered_release_sections": len(ids), "source_sha256": sha(SOURCE.read_bytes()),
              "limits": ["AI-authored research examples; no independent lawyer validation.",
                         "These cases cover the 19 release sections, not all 297 research offence sections.",
                         "A section-specific unsupported label never means globally out of scope."]}
    if not args.check_only:
        if COVERAGE_BATCH.exists() or OUT.exists():
            raise ValueError("Part 2 output already exists; refusing to overwrite pinned data")
        COVERAGE_BATCH.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUT.mkdir(parents=True)
        write_jsonl(OUT / "train_sft.jsonl", sft)
        write_jsonl(OUT / "train_sft_map.jsonl", mapping)
        report["files_sha256"] = {p.name: sha(p.read_bytes()) for p in
                                  (COVERAGE_BATCH, OUT / "train_sft.jsonl", OUT / "train_sft_map.jsonl")}
        (OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
