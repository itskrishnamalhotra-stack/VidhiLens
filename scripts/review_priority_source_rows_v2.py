"""Record an AI review of all 78 source rows labelled with seven new BNS sections.

Only a small, explicit correction set enters trainer-format data. Publisher
answers are discarded. This source is too noisy for general auto-promotion.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "external_candidates" / "statutory_triage_bns_ipc_dataset_final_dense.jsonl"
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "review_automation" / "complaint_pool_v2"
SCOPE = {"BNS_109", "BNS_124", "BNS_140", "BNS_305", "BNS_308", "BNS_309", "BNS_324"}
SYSTEM = ("Read the reported incident. Return JSON only with outcome, possible_provision_ids, "
          "and uncertain_sections. A section is only a possibility, never a finding of guilt. "
          "Never invent missing facts.")

# Decision after reading every scoped row against its official section. The
# first item is the corrected target section, the second is the outcome, and
# the third is the legal reason or missing fact. All other rows are held.
CORRECTED = {
    23: ("BNS_305", "insufficient_information", "whether_the_item_was_taken_dishonestly_without_consent"),
    28: ("BNS_309", "provision_match", "Gunpoint threat was immediate and property was taken."),
    228: ("BNS_305", "provision_match", "The reported theft occurred inside a dwelling."),
    837: ("BNS_140", "provision_match", "Kidnapping plus a ransom demand is reported."),
    884: ("BNS_308", "provision_match", "Threat of hurt used to demand money supports the attempt branch even without reported delivery."),
    885: ("BNS_308", "provision_match", "Threatened false accusation used to demand money supports a possible extortion-attempt branch."),
    1342: ("BNS_305", "provision_match", "The reported theft was from inside a dwelling."),
    1881: ("BNS_140", "provision_match", "Kidnapping plus a demand to compel the government is reported."),
    2207: ("BNS_308", "provision_match", "Threat to reputation used to demand money supports a possible extortion-attempt branch."),
}


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> None:
    conn = sqlite3.connect(DB)
    law = {p: (status, kind, text, page) for p, status, kind, text, page in conn.execute(
        "SELECT provision_id,legal_status,provision_kind,verified_text,source_pdf_page FROM provision")}
    prior = {(k, n) for k, n in conn.execute("SELECT source_key,row_number FROM public_candidate_review")}
    conn.close()
    audit = {int(r["row_number"]): r for r in csv.DictReader(
        (OUT / "row_audit.csv").open(encoding="utf-8", newline=""))
        if r["source"] == "statutory_triage" and r["disposition"] == "semantic_review_needed"
        and r["parsed_section_ids"] in SCOPE}
    if len(audit) != 78: raise ValueError(f"Scoped source count changed: {len(audit)}")
    source = {n: json.loads(line) for n, line in enumerate(SOURCE.open(encoding="utf-8"), 1) if n in audit}
    if set(source) != set(audit): raise ValueError("Missing source rows")
    if any(("statutory_triage", n) in prior for n in CORRECTED):
        raise ValueError("A corrected row was previously reviewed")
    decisions, accepted = [], []
    for n, row in sorted(source.items()):
        complaint = row["instruction"]
        label = audit[n]["parsed_section_ids"]
        if n in CORRECTED:
            pid, outcome, rationale = CORRECTED[n]
            if pid != label or law[pid][0] != "in_force" or law[pid][1] != "offence" or not law[pid][2]:
                raise ValueError(f"Section check failed: {n}")
            uncertain = outcome == "insufficient_information"
            target = {"outcome": outcome, "possible_provision_ids": [] if uncertain else [pid],
                      "uncertain_sections": [{"provision_id": pid, "missing_facts": rationale}] if uncertain else []}
            accepted.append({"id": f"corrected-public-{n}",
                             "messages": [{"role": "system", "content": SYSTEM},
                                          {"role": "user", "content": complaint},
                                          {"role": "assistant", "content": json.dumps(target, ensure_ascii=False, separators=(",", ":"))}],
                             "metadata": {"kind": "triage", "split": "train", "source": "statutory_triage",
                                          "source_row": n, "input_sha256": sha(complaint),
                                          "corrected_provision_id": pid,
                                          "verified_text_sha256": sha(law[pid][2]),
                                          "source_pdf_page": law[pid][3],
                                          "review_status": "AI_reviewed_corrected_source_case"}})
            decision, reason = "accepted_corrected", rationale
        else:
            decision, reason = "held", ("The short account does not establish this section's elements, "
                                        "uses a different legal concept, or repeats a near-identical case. "
                                        "Do not use the publisher answer as a triage target.")
        decisions.append({"source_row": n, "publisher_section": label, "decision": decision,
                          "review_reason": reason, "input_sha256": sha(complaint),
                          "input_preview": complaint})
    with (OUT / "priority_source_decisions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(decisions[0]));writer.writeheader();writer.writerows(decisions)
    with (OUT / "corrected_source_train.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in accepted: stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    result = {"reviewed_rows": len(decisions), "accepted_corrected": len(accepted),
              "held": len(decisions)-len(accepted), "accepted_ids": sorted(CORRECTED),
              "source_dataset_note": "All publisher answers discarded; this is not a bulk endorsement of source labels.",
              "corrected_train_sha256": hashlib.sha256((OUT / "corrected_source_train.jsonl").read_bytes()).hexdigest()}
    (OUT / "priority_source_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
