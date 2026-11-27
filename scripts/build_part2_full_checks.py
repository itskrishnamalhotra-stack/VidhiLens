"""Build section-conditioned uncertainty and boundary examples for all research offences.

These are a distinct task from open-ended complaint triage. A section-specific
unsupported judgment must never become a global out-of-scope training target.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
RELEASE_SOURCE = ROOT / "data_drafts" / "part2_v1_cases.jsonl"
REMAINING_SOURCE = ROOT / "data_drafts" / "part2_remaining_fact_checks.psv"
CORRECTIONS_SOURCE = ROOT / "data_drafts" / "part2_corrections_v1.json"
OUT = ROOT / "exports" / "part2_candidate_checks_v3_research"
TRIAGE = ROOT / "exports" / "complaint_only_v5_research_candidate"
SEALED = ROOT / "data_drafts" / "gap_examples_v2" / "sealed_test.jsonl"
SYSTEM = (
    "Assess only the named BNS or IT Act candidate section against the reported facts. "
    "Return JSON with label, missing_facts, and reason. Labels are possible, uncertain, "
    "or unsupported. Unsupported for this section does not mean no other law applies. "
    "Treat allegations as reported facts, not proven facts; do not invent missing facts."
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                            for row in rows), encoding="utf-8")


def prior_held_out() -> list[tuple[str, str]]:
    result = []
    for split in ("dev",):
        for line in (TRIAGE / f"{split}_sft.jsonl").open(encoding="utf-8"):
            row = json.loads(line)
            result.append((split, row["messages"][-2]["content"]))
    for line in SEALED.open(encoding="utf-8"):
        row = json.loads(line)
        if row["metadata"].get("kind") == "triage":
            result.append(("sealed", row["messages"][-2]["content"]))
    return result


def main() -> None:
    if OUT.exists():
        raise ValueError("Output already exists; refusing to replace pinned Part 2 data")
    release = [json.loads(line) for line in RELEASE_SOURCE.read_text(encoding="utf-8").splitlines()]
    remaining = []
    for line_number, line in enumerate(REMAINING_SOURCE.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("|")
        if len(parts) != 4:
            raise ValueError(f"Invalid fact-check line {line_number}")
        pid, known, gap, exclusion = parts
        if not gap.startswith("I do not know ") or len(known.split()) < 5 or len(exclusion.split()) < 5:
            raise ValueError(f"Incomplete fact-check: {pid}")
        remaining.append((pid, known, gap, exclusion))
    with sqlite3.connect(DB) as conn:
        laws = {row[0]: row[1:] for row in conn.execute("""SELECT provision_id,legal_status,
            provision_kind,verified_text,source_id,source_pdf_page FROM provision""")}
        release_ids = {r[0] for r in conn.execute("SELECT provision_id FROM recommendable_provision")}
    eligible = {pid for pid, (status, kind, verified, _, _) in laws.items()
                if status == "in_force" and kind == "offence" and verified}
    if len(eligible) != 297 or len(release) != 38 or len(remaining) != 278:
        raise ValueError("Coverage source counts differ from reviewed plan")
    if {r["target"] for r in release} != release_ids:
        raise ValueError("Release section list changed")
    if {r[0] for r in remaining} != eligible - release_ids:
        raise ValueError("Remaining sections do not equal non-release offence scope")
    cases = []
    for row in release:
        cases.append({"id": row["id"], "target": row["target"], "label": row["label"],
                      "complaint": row["complaint"], "missing_fact": row["missing_fact"],
                      "reason": row["reason"], "other_possible_ids": row.get("other_possible_ids", []),
                      "authoring": "individually_authored"})
    for pid, known, gap, exclusion in remaining:
        cases.append({"id": f"p2-full-{pid}-u", "target": pid, "label": "uncertain",
                      "complaint": f"{known} {gap} I need to know that detail before assessing this particular section.",
                      "missing_fact": gap.removeprefix("I do not know ").rstrip("."),
                      "reason": "A material element of this candidate section remains unknown on the stated facts.",
                      "other_possible_ids": [], "authoring": "section_specific_fact_matrix"})
        cases.append({"id": f"p2-full-{pid}-n", "target": pid, "label": "unsupported",
                      "complaint": f"{known} A later check established this additional fact: {exclusion} Other issues may still need examination.",
                      "missing_fact": "", "reason": f"{exclusion} This candidate section is unsupported on the reported facts; other provisions may still apply.",
                      "other_possible_ids": [], "authoring": "section_specific_fact_matrix"})
    corrections = json.loads(CORRECTIONS_SOURCE.read_text(encoding="utf-8"))
    case_by_id = {case["id"]: case for case in cases}
    if not corrections or not set(corrections).issubset(case_by_id):
        raise ValueError("Unknown or absent Part 2 correction IDs")
    for case_id, patch in corrections.items():
        if set(patch) != {"complaint", "reason"}:
            raise ValueError(f"Invalid correction fields: {case_id}")
        case_by_id[case_id].update(patch)
        case_by_id[case_id]["authoring"] = "corrected_after_AI_review"
    if len(cases) != 594 or len({r["id"] for r in cases}) != 594:
        raise ValueError("Part 2 record count or IDs invalid")
    by_section = Counter((r["target"], r["label"]) for r in cases)
    if any(by_section[(pid, label)] != 1 for pid in eligible for label in ("uncertain", "unsupported")):
        raise ValueError("Missing or repeated section-label pair")
    held = prior_held_out()
    choices = [x[1] for x in held]
    high = []
    sft, mapping = [], []
    for row in cases:
        pid, label = row["target"], row["label"]
        if not row["complaint"] or not row["reason"] or (label == "uncertain") != bool(row["missing_fact"]):
            raise ValueError(f"Invalid target content: {row['id']}")
        if re.search(r"https?://|\b\S+@\S+\b", row["complaint"], re.I):
            raise ValueError(f"Identifying text: {row['id']}")
        hit = process.extractOne(row["complaint"], choices, scorer=fuzz.ratio)
        if hit and hit[1] >= 75:
            high.append({"id": row["id"], "split": held[hit[2]][0], "similarity": round(hit[1]/100, 3)})
        status, kind, verified, source_id, page = laws[pid]
        answer = {"label": label, "missing_facts": [row["missing_fact"]] if label == "uncertain" else [],
                  "reason": row["reason"]}
        user = {"complaint": row["complaint"], "candidate_provision_id": pid}
        sft.append({"messages": [{"role": "system", "content": SYSTEM},
                                  {"role": "user", "content": json.dumps(user, ensure_ascii=False, separators=(",", ":"))},
                                  {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False,
                                                                               separators=(",", ":"))}]})
        mapping.append({"source_id": row["id"], "split": "train", "kind": "candidate_check",
                        "target_provision_id": pid, "label": label,
                        "review_status": "AI_authored_research_candidate",
                        "authoring": row["authoring"], "source_id_of_law": source_id,
                        "source_pdf_page": page, "verified_text_sha256": hashlib.sha256(verified.encode()).hexdigest(),
                        "other_possible_ids": row["other_possible_ids"]})
    if high:
        raise ValueError(f"Part 2 train/held-out lexical overlap: {high[:15]}")
    OUT.mkdir(parents=True)
    write_jsonl(OUT / "train_sft.jsonl", sft)
    write_jsonl(OUT / "train_sft_map.jsonl", mapping)
    write_jsonl(OUT / "review_ledger.jsonl", cases)
    report = {"status": "AI_authored_research_candidate_not_legal_release",
              "candidate_check_train_records": len(sft), "eligible_offence_sections": len(eligible),
              "uncertain_per_section": 1, "unsupported_per_section": 1,
              "train_held_out_lexical_similarity_at_least_0_75": len(high),
              "source_sha256": {RELEASE_SOURCE.name: sha(RELEASE_SOURCE),
                                REMAINING_SOURCE.name: sha(REMAINING_SOURCE),
                                CORRECTIONS_SOURCE.name: sha(CORRECTIONS_SOURCE)},
              "files_sha256": {name: sha(OUT / name) for name in
                               ("train_sft.jsonl", "train_sft_map.jsonl", "review_ledger.jsonl")},
              "limits": ["These are candidate-section checks, not global triage conclusions.",
                         "All 594 examples are AI-authored research candidates and train-only.",
                         "Per-section coverage and lexical screening do not prove legal correctness or model accuracy.",
                         "The 278-section matrix uses compact fact patterns; model testing must measure whether it helps."]}
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
