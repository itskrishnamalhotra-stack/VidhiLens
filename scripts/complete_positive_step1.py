"""Version the complaint bundle after a full positive-example quality audit.

This is an AI-authored research review. It checks structure, coverage, source
hashes and lexical diversity; it does not certify a legal training set.
"""
from __future__ import annotations

import csv
import difflib
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "exports" / "complaint_training_v8_research_candidate"
OUT = ROOT / "exports" / "complaint_training_v9_step1_research_candidate"
AUDIT = ROOT / "review_automation" / "positive_step1_final_v1"
REVISIONS = ROOT / "data_drafts" / "step1_positive_revisions_v1.psv"
OLD_LEDGER = ROOT / "review_automation" / "training_readiness_v6" / "weak_triage.csv"
ACCEPTED_FLOOR = ROOT / "review_automation" / "positive_step1_v1" / "accepted_floor_ids.json"
DB = ROOT / "db" / "master_dataset.sqlite"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_split(split: str) -> list[tuple[dict, dict]]:
    data = (BASE / f"{split}_sft.jsonl").open(encoding="utf-8")
    mapping = (BASE / f"{split}_sft_map.jsonl").open(encoding="utf-8")
    with data, mapping:
        return [(json.loads(a), json.loads(b)) for a, b in zip(data, mapping, strict=True)]


def answer(row: dict) -> dict:
    return json.loads(row["messages"][-1]["content"])


def family(meta: dict) -> str:
    return meta.get("kind") or meta.get("task_family")


def positive_ids(row: dict, meta: dict) -> list[str]:
    if family(meta) != "triage":
        return []
    result = answer(row)
    return result.get("possible_provision_ids", []) if result.get("outcome") == "provision_match" else []


def norm(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    if OUT.exists() or AUDIT.exists():
        raise ValueError("Versioned output exists; refuse to overwrite")
    base_manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in base_manifest["files_sha256"].items():
        if digest(BASE / name) != expected:
            raise ValueError(f"Base bundle changed: {name}")
    with sqlite3.connect(DB) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity check failed")
        laws = {pid: (source, page, text) for pid, source, page, text in conn.execute(
            "SELECT provision_id,source_id,source_pdf_page,verified_text FROM provision "
            "WHERE legal_status='in_force' AND provision_kind='offence' AND verified_text IS NOT NULL")}
    if len(laws) != 297:
        raise ValueError(f"Expected 297 in-force offences, found {len(laws)}")

    revisions = {}
    for line in REVISIONS.read_text(encoding="utf-8").splitlines():
        action, pid, complaint = line.split("|", 2)
        if action not in {"replace", "add"} or pid not in laws or (action, pid) in revisions:
            raise ValueError(f"Invalid revision: {line[:70]}")
        if len(complaint.split()) < 25 or "?" in complaint:
            raise ValueError(f"Revision is too short or is a question: {pid}")
        revisions[action, pid] = complaint
    replace = {pid for action, pid in revisions if action == "replace"}
    add = {pid for action, pid in revisions if action == "add"}
    if len(replace) != 28 or len(add) != 15:
        raise ValueError(f"Unexpected revision scope: {len(replace)} replace, {len(add)} add")

    train = read_split("train")
    dev = read_split("dev")
    before = defaultdict(list)
    for index, (row, meta) in enumerate(train, 1):
        for pid in positive_ids(row, meta):
            before[pid].append((index, row, meta))
    if set(before) != set(laws):
        raise ValueError("Base positive labels do not cover exactly 297 offences")
    removable = {}
    for pid in replace:
        matches = [(i, row, meta) for i, row, meta in before[pid]
                   if meta.get("source") == "statutory_triage"]
        if len(before[pid]) != 2 or len(matches) != 1:
            raise ValueError(f"Expected one statutory question among two positives: {pid}")
        removable[matches[0][0]] = pid

    final = []
    ledger = []
    for index, (row, meta) in enumerate(train, 1):
        ids = positive_ids(row, meta)
        if ids:
            for pid in ids:
                source, page, law_text = laws[pid]
                old_hash = meta.get("verified_text_sha256")
                if old_hash and old_hash != hashlib.sha256(law_text.encode()).hexdigest():
                    raise ValueError(f"Statutory hash mismatch: {pid} at row {index}")
                ledger.append({"base_train_row": index, "provision_id": pid,
                               "source": meta.get("source", ""),
                               "source_id": meta.get("source_id", ""),
                               "word_count": len(row["messages"][1]["content"].split()),
                               "decision": "replace_with_fact_complete_incident" if index in removable else "retain_research_positive",
                               "quality_note": "concise_source_grounded_supplement" if meta.get("source") == "local_section_floor_research" else "incident_or_reported_question",
                               "verified_text_sha256": hashlib.sha256(law_text.encode()).hexdigest()})
        if index not in removable:
            final.append((row, meta))
    if set(removable.values()) != replace:
        raise ValueError("Replacement accounting failed")

    system = train[0][0]["messages"][0]["content"]
    for (action, pid), complaint in revisions.items():
        source, page, law_text = laws[pid]
        row = {"messages": [{"role": "system", "content": system},
                            {"role": "user", "content": complaint},
                            {"role": "assistant", "content": json.dumps({
                                "outcome": "provision_match", "possible_provision_ids": [pid],
                                "uncertain_sections": []}, separators=(",", ":"))}]}
        meta = {"kind": "triage", "split": "train", "source": "step1_fact_review_v1",
                "source_id": f"step1-{action}-{pid}", "target_provision_id": pid,
                "source_id_of_law": source, "source_pdf_page": page,
                "verified_text_sha256": hashlib.sha256(law_text.encode()).hexdigest(),
                "review_status": "AI_authored_source_grounded_research_candidate",
                "quality_note": "Fact-based positive replaces a vague question or supplements a close paraphrase."}
        final.append((row, meta))
        ledger.append({"base_train_row": "", "provision_id": pid, "source": meta["source"],
                       "source_id": meta["source_id"], "word_count": len(complaint.split()),
                       "decision": "add_fact_complete_incident", "quality_note": action,
                       "verified_text_sha256": meta["verified_text_sha256"]})

    by_section = defaultdict(list)
    seen_train = set()
    for row, meta in final:
        text = row["messages"][1]["content"]
        for pid in positive_ids(row, meta):
            by_section[pid].append((text, meta))
            key = (pid, norm(text))
            if key in seen_train:
                raise ValueError(f"Repeated positive complaint: {pid}")
            seen_train.add(key)
    if set(by_section) != set(laws) or min(map(len, by_section.values())) < 2:
        raise ValueError("A section lost its two-positive floor")
    if any(len(by_section[pid]) < 3 for pid in add):
        raise ValueError("Close-paraphrase improvement did not yield three positives")
    dev_positive = {norm(row["messages"][1]["content"]) for row, meta in dev
                    if positive_ids(row, meta)}
    if any(norm(text) in dev_positive for cases in by_section.values() for text, _ in cases):
        raise ValueError("Positive train text appears in development")
    for pid, cases in by_section.items():
        if len(cases) == 2 and any(meta.get("source") == "statutory_triage" for _, meta in cases):
            raise ValueError(f"Unreviewed statutory row still supplies a two-case floor: {pid}")

    OUT.mkdir(parents=True)
    AUDIT.mkdir(parents=True)
    for split, paired in (("train", final), ("dev", dev)):
        write_jsonl(OUT / f"{split}_sft.jsonl", [a for a, _ in paired])
        write_jsonl(OUT / f"{split}_sft_map.jsonl", [b for _, b in paired])
    with (AUDIT / "positive_ledger.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ledger[0]))
        writer.writeheader()
        writer.writerows(ledger)
    section_rows = []
    for pid in sorted(by_section):
        cases = by_section[pid]
        similarity = difflib.SequenceMatcher(None, cases[0][0].casefold(), cases[1][0].casefold()).ratio() if len(cases) == 2 else 0
        section_rows.append({"provision_id": pid, "positive_train": len(cases),
                             "min_words": min(len(text.split()) for text, _ in cases),
                             "compact_supplements": sum(meta.get("source") == "local_section_floor_research" for _, meta in cases),
                             "first_pair_similarity": round(similarity, 3),
                             "law_sha256": hashlib.sha256(laws[pid][2].encode()).hexdigest()})
    with (AUDIT / "per_section.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(section_rows[0]))
        writer.writeheader()
        writer.writerows(section_rows)
    old_weak = list(csv.DictReader(OLD_LEDGER.open(encoding="utf-8", newline="")))
    accepted_floor = set(json.loads(ACCEPTED_FLOOR.read_text(encoding="utf-8")))
    retained_floor = {meta["source_id"] for _, meta in final
                      if meta.get("source") == "local_section_floor_research"}
    if retained_floor != accepted_floor or len(retained_floor) != 263:
        raise ValueError("Compact floor rows differ from the prior source-review allowlist")
    excluded_weak = {row["source_id"] for row in old_weak}
    retained_ids = {meta.get("source_id") for _, meta in final}
    if len(old_weak) != 266 or excluded_weak & retained_ids:
        raise ValueError("A held weak or superseded source row was promoted")
    counts = {split: dict(Counter(family(meta) for _, meta in paired))
              for split, paired in (("train", final), ("dev", dev))}
    manifest = {"status": "AI_reviewed_research_candidate_not_legal_certification",
                "parent_bundle": BASE.relative_to(ROOT).as_posix(),
                "parent_manifest_sha256": digest(BASE / "manifest.json"),
                "revision_source": REVISIONS.relative_to(ROOT).as_posix(),
                "revision_source_sha256": digest(REVISIONS),
                "counts": counts, "train_total": len(final), "dev_total": len(dev),
                "positive_sections": len(by_section), "min_positive_train_per_section": 2,
                "replaced_question_or_vague_rows": len(removable),
                "additional_distinct_incidents": len(add),
                "files_sha256": {p.name: digest(p) for p in OUT.glob("*.jsonl")},
                "limits": ["Source-grounded AI research review, not independent legal certification.",
                           "Compact supplemental cases remain in training; unseen complaint evaluation is required.",
                           "This bundle does not expand the 19-section app recommendation gate."]}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summary = {"result": "step1_positive_review_complete_as_research_dataset",
               "eligible_sections_reviewed": len(by_section),
               "positive_rows_audited": sum(bool(positive_ids(row, meta)) for row, meta in train),
               "positive_labels_audited": len(ledger) - len(revisions),
               "previously_excluded_weak_rows_accounted_for": len(old_weak),
               "replaced_vague_or_question_rows": len(removable),
               "new_distinct_cases_for_close_pairs": len(add),
               "sections_with_two_or_more_positives": sum(len(v) >= 2 for v in by_section.values()),
               "sections_with_only_two_positives": sum(len(v) == 2 for v in by_section.values()),
               "compact_supplements_retained": sum(r["compact_supplements"] for r in section_rows),
               "remaining_two_case_pairs_with_similarity_above_0_70": sum(float(r["first_pair_similarity"]) > .70 for r in section_rows),
               "train_counts": counts["train"], "dev_counts": counts["dev"],
               "bundle_manifest": (OUT / "manifest.json").relative_to(ROOT).as_posix(),
               "per_section_sha256": digest(AUDIT / "per_section.csv"),
               "ledger_sha256": digest(AUDIT / "positive_ledger.csv"),
               "limits": manifest["limits"]}
    (AUDIT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
