"""Structure/coverage audit for downloaded public data, not a legal correctness check."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "external_candidates"
DB = ROOT / "db" / "master_dataset.sqlite"
OUTPUT = ROOT / "external_audit_report.json"


def jsonl(name: str) -> list[dict]:
    return [json.loads(line) for line in (BASE / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    with sqlite3.connect(DB) as conn:
        bns_ids = {row[0] for row in conn.execute("SELECT section_number FROM provision WHERE act_id='BNS_2023'")}
        priority_bns = {row[0] for row in conn.execute("SELECT section_number FROM provision WHERE act_id='BNS_2023' AND priority_review=1")}

    structured = json.loads((BASE / "bns_structured_bns_sections.json").read_text(encoding="utf-8"))
    qa = jsonl("bns_qa_bns_legal_qa.jsonl")
    triage = jsonl("statutory_triage_bns_ipc_dataset_final_dense.jsonl")
    nyaya_train = jsonl("nyaya_train_train.jsonl")
    nyaya_val = jsonl("nyaya_val_val.jsonl")
    nyaya_eval = jsonl("nyaya_eval_nyaya_eval_v0.jsonl")

    triage_roots = []
    for row in triage:
        match = re.match(r"^(\d{1,3})", str(row.get("bns_section_applied", "")))
        triage_roots.append(match[1] if match else None)
    triage_root_set = set(triage_roots)
    report = {
        "warning": "Counts and valid IDs do not establish legal correctness, privacy clearance, or fitness for training.",
        "bns_structured": {
            "rows": len(structured),
            "unique_section_ids": len({str(row.get("section_number")) for row in structured}),
            "missing_from_official_index": sorted({str(row.get("section_number")) for row in structured} - bns_ids),
        },
        "bns_qa": {
            "rows": len(qa),
            "unique_sections": len({str(row.get("section_number")) for row in qa}),
            "question_types": dict(Counter(row.get("question_type") for row in qa)),
            "priority_bns_sections_covered": len({str(row.get("section_number")) for row in qa} & priority_bns),
        },
        "bns_triage": {
            "rows": len(triage),
            "distinct_base_sections": len(triage_root_set - {None}),
            "non_section_or_unknown_label_rows": sum(root not in bns_ids for root in triage_roots),
            "priority_bns_sections_covered": len(triage_root_set & priority_bns),
        },
        "nyaya_train": {
            "rows": len(nyaya_train),
            "primary_bns_rows": sum(row["metadata"].get("legal_domain") == "bns_2023" for row in nyaya_train),
            "primary_it_act_rows": sum(row["metadata"].get("legal_domain") == "it_act_2000" for row in nyaya_train),
            "metadata_verified_true_rows": sum(row["metadata"].get("verified") is True for row in nyaya_train),
        },
        "nyaya_val": {
            "rows": len(nyaya_val),
            "primary_bns_rows": sum(row["metadata"].get("legal_domain") == "bns_2023" for row in nyaya_val),
            "primary_it_act_rows": sum(row["metadata"].get("legal_domain") == "it_act_2000" for row in nyaya_val),
        },
        "nyaya_eval": {
            "rows": len(nyaya_eval),
            "bns_rows": sum(row.get("legal_domain") == "bns" for row in nyaya_eval),
            "cyber_law_rows": sum(row.get("legal_domain") == "cyber_law" for row in nyaya_eval),
            "known_content_discrepancy": "nyaya_eval_000019: BNS 75(1)(iv) remarks penalty differs from official BNS 75(3)",
        },
    }
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
