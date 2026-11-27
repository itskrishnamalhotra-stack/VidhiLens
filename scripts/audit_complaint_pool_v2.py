"""Full-pass, conservative complaint-source audit; never auto-approves legal labels."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "review_automation" / "complaint_pool_v2"
DB = ROOT / "db" / "master_dataset.sqlite"
PII = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|(?<!\d)(?:\+91[- ]?)?[6-9]\d{9}(?!\d)")
INCIDENT_DATE = re.compile(r"(?:incident occurred on|this incident occurred on|happened on)\s+(\d{1,2})[-/](\d{1,2})[-/](\d{4})", re.I)
QUESTION = re.compile(r"^(?:what|which|under which|can|could|is|does|how|if|would|why|tell me|explain)\b", re.I)


def norm(s: str) -> str:
    return " ".join(re.findall(r"\w+", s.casefold()))


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def audit() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    laws = {p: (status, kind, bool(text), bool(recommendable))
            for p, status, kind, text, recommendable in conn.execute(
                "SELECT provision_id,legal_status,provision_kind,verified_text,recommendable FROM provision")}
    old = {(k, n): d for k, n, d in conn.execute(
        "SELECT source_key,row_number,decision FROM public_candidate_review")}
    seen: dict[str, tuple[str, int]] = {}
    counts = Counter()
    flags_count = Counter()
    eligible_by_section = Counter()
    records = []

    sources = [
        ("statutory_triage", ROOT / "external_candidates" / "statutory_triage_bns_ipc_dataset_final_dense.jsonl"),
        ("complaint_bns", ROOT / "external_candidates" / "additional_20260917" / "complaint_bns.jsonl"),
    ]
    for source, path in sources:
        with path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                raw = json.loads(line)
                complaint = str(raw.get("instruction", "")) if source == "statutory_triage" else str(raw.get("input", ""))
                label_text = str(raw.get("bns_section_applied", "")) if source == "statutory_triage" else str(raw.get("output", ""))
                label_numbers = re.findall(r"(?<!\d)(\d{1,3})(?:\([\da-z]+\))?", label_text)
                pids = [f"BNS_{n}" for n in label_numbers]
                flags = set()
                if not complaint.strip(): flags.add("empty_input")
                if QUESTION.match(complaint.strip()): flags.add("legal_question_or_hypothetical")
                if len(complaint.split()) < 12: flags.add("thin_incident")
                if PII.search(complaint): flags.add("possible_personal_data")
                if source == "complaint_bns":
                    flags.add("generic_generated_narrative")
                    for day, month, year in INCIDENT_DATE.findall(complaint):
                        if (int(year), int(month), int(day)) < (2024, 7, 1):
                            flags.add("pre_BNS_commencement_date")
                            break
                if not pids: flags.add("no_parseable_section")
                if any(p not in laws for p in pids): flags.add("section_missing_from_index")
                if any(p in laws and laws[p][0] != "in_force" for p in pids): flags.add("section_not_in_force")
                if any(p in laws and laws[p][1] != "offence" for p in pids): flags.add("label_is_not_offence_section")
                if any(p in laws and not laws[p][2] for p in pids): flags.add("section_text_not_verified")
                key = norm(complaint)
                if key in seen: flags.add("duplicate_input")
                else: seen[key] = (source, number)
                if (source, number) in old:
                    flags.add("already_reviewed_" + old[(source, number)])
                if source == "statutory_triage" and not flags:
                    disposition = "semantic_review_needed"
                    for p in pids: eligible_by_section[p] += 1
                else:
                    disposition = "hold_or_recast"
                counts[(source, disposition)] += 1
                flags_count.update(flags)
                records.append({"source": source, "row_number": number, "input_sha256": sha(complaint),
                                "publisher_labels": label_text, "parsed_section_ids": ";".join(pids),
                                "disposition": disposition, "flags": ";".join(sorted(flags)),
                                "input_preview": complaint[:180]})

    path = ROOT / "external_candidates" / "additional_20260917" / "nariraksha.parquet"
    for number, row in enumerate(pq.read_table(path).to_pylist(), 1):
        complaint = row["scenario"] or ""
        flags = {"template_topic_not_section_label"}
        if norm(complaint) in seen: flags.add("duplicate_input")
        else: seen[norm(complaint)] = ("nariraksha", number)
        flags_count.update(flags)
        counts[("nariraksha", "hold_or_recast")] += 1
        records.append({"source": "nariraksha", "row_number": number, "input_sha256": sha(complaint),
                        "publisher_labels": row.get("legal_context", ""), "parsed_section_ids": "",
                        "disposition": "hold_or_recast", "flags": ";".join(sorted(flags)),
                        "input_preview": complaint[:180]})

    with (OUT / "row_audit.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader(); writer.writerows(records)
    summary = {
        "rows_checked": len(records),
        "source_dispositions": [{"source": s, "disposition": d, "count": n}
                                for (s, d), n in sorted(counts.items())],
        "flag_counts": dict(flags_count.most_common()),
        "semantic_review_queue_size": sum(n for (_, d), n in counts.items() if d == "semantic_review_needed"),
        "semantic_review_queue_top_sections": eligible_by_section.most_common(30),
        "meaning": "Mechanical flags eliminate obvious bad inputs/labels. Remaining rows still require fact-to-section review; no source label is approved here.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    audit()
