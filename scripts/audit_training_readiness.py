"""Audit the current research SFT without promoting unreviewed labels.

This is a deterministic quality screen, not an assessment of legal correctness.
It keeps the source export unchanged and writes a complaint-only candidate export.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import argparse
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "exports" / "mixed-source-v14-research"
DEFAULT_OUT = ROOT / "review_automation" / "training_readiness_v6"
DEFAULT_TRAIN_CANDIDATE = ROOT / "exports" / "complaint_only_v6_research_candidate"
DEFAULT_SUPERSESSIONS = ROOT / "data_drafts" / "positive_repair_supersessions_v2.json"
DEFAULT_ACCEPTED_FLOOR = ROOT / "review_automation" / "positive_step1_v1" / "accepted_floor_ids.json"
DB = ROOT / "db" / "master_dataset.sqlite"
TARGET_ACTS = {"bns_2023", "it_act_2000"}
SOURCE = DEFAULT_SOURCE
OUT = DEFAULT_OUT
TRAIN_CANDIDATE = DEFAULT_TRAIN_CANDIDATE


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_pair(split: str):
    with (SOURCE / f"{split}_sft.jsonl").open(encoding="utf-8") as data, \
            (SOURCE / f"{split}_sft_map.jsonl").open(encoding="utf-8") as mapping:
        for line_no, (data_line, meta_line) in enumerate(zip(data, mapping, strict=True), 1):
            yield line_no, data_line, meta_line, json.loads(data_line), json.loads(meta_line)


def main() -> None:
    global SOURCE, OUT, TRAIN_CANDIDATE
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_TRAIN_CANDIDATE)
    parser.add_argument("--supersessions", type=Path, default=DEFAULT_SUPERSESSIONS)
    parser.add_argument("--accepted-floor", type=Path, default=DEFAULT_ACCEPTED_FLOOR)
    args = parser.parse_args()
    SOURCE, OUT, TRAIN_CANDIDATE = (p.resolve() for p in (args.source, args.out, args.candidate))
    supersessions = json.loads(args.supersessions.read_text(encoding="utf-8"))
    accepted_floor = set(json.loads(args.accepted_floor.read_text(encoding="utf-8")))
    if len(accepted_floor) != 263:
        raise ValueError("Reviewed floor allowlist count changed")
    if len(set(supersessions.values())) != len(supersessions):
        raise ValueError("A replacement case is reused")
    source_manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in source_manifest["files_sha256"].items():
        if sha(SOURCE / name) != expected:
            raise ValueError(f"Changed source export: {name}")

    OUT.mkdir(parents=True, exist_ok=True)
    TRAIN_CANDIDATE.mkdir(parents=True, exist_ok=True)
    weak, qa, structural = [], [], []
    counts = Counter()
    positives = defaultdict(list)
    candidate_positives = Counter()
    candidate_uncertainty = Counter()
    candidate_source_ids = set()
    source_ids = set()
    candidate_files = {}
    for split in ("train", "dev"):
        data_path = TRAIN_CANDIDATE / f"{split}_sft.jsonl"
        map_path = TRAIN_CANDIDATE / f"{split}_sft_map.jsonl"
        candidate_files[split] = [data_path, map_path]
        with data_path.open("w", encoding="utf-8", newline="\n") as data_out, \
                map_path.open("w", encoding="utf-8", newline="\n") as map_out:
            for line_no, data_line, meta_line, data, meta in read_pair(split):
                family = meta.get("task_family") or meta.get("kind")
                counts[f"{split}_{family}"] += 1
                messages = data.get("messages", [])
                if not messages or messages[-1].get("role") != "assistant":
                    structural.append({"split": split, "line": line_no,
                                       "source_id": meta.get("source_id", ""),
                                       "issue": "missing_assistant_answer"})
                    continue
                if family == "grounded_legal_qa":
                    sections = meta.get("source_sections", [])
                    acts = {s.split(":", 1)[0] for s in sections}
                    question = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
                    answer = messages[-1].get("content", "")
                    issues = []
                    if not sections:
                        issues.append("no_source_section")
                    if acts - TARGET_ACTS:
                        issues.append("outside_BNS_IT_scope")
                    if "\ufffd" in question or "\ufffd" in answer:
                        issues.append("replacement_character")
                    if not answer.strip() or len(answer.split()) < 10:
                        issues.append("short_or_empty_answer")
                    source_numbers = {s.split(":", 1)[1].upper() for s in sections if ":" in s}
                    cited_numbers = {x.upper() for x in re.findall(
                        r"(?i)\b(?:section|sec\.?)\s*(\d+[A-Z]?)\b", answer)}
                    if sections and cited_numbers - source_numbers:
                        issues.append("answer_mentions_other_section_number_check_context")
                    qa.append({"split": split, "line": line_no,
                               "source_id": meta.get("source_id", ""),
                               "source_sections": "|".join(sections),
                               "task_type": meta.get("task_type", ""),
                               "issues": "|".join(issues),
                               "decision": "hold_separate_from_complaint_training"})
                    counts["qa_with_any_screen_issue"] += bool(issues)
                    for issue in issues:
                        counts[f"qa_issue_{issue}"] += 1
                    continue
                if family == "triage":
                    try:
                        answer = json.loads(messages[-1]["content"])
                    except (ValueError, KeyError, TypeError):
                        structural.append({"split": split, "line": line_no,
                                           "source_id": meta.get("source_id", ""),
                                           "issue": "invalid_triage_json"})
                        continue
                    text = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
                    source_id = (meta.get("case_id") or meta.get("incident_family")
                                 or meta.get("source_id") or meta.get("scenario_id") or "")
                    source_ids.add(source_id)
                    ids = answer.get("possible_provision_ids", [])
                    issues = []
                    if source_id in supersessions:
                        issues.append("superseded_after_statutory_element_review")
                    if len(text.split()) < 18 and source_id not in accepted_floor:
                        issues.append("under_18_words")
                    if source_id.startswith("section-floor-") and source_id not in accepted_floor:
                        issues.append("section_floor_single_sentence_needs_fact_review")
                    if answer.get("outcome") == "provision_match" and not ids:
                        issues.append("positive_without_section")
                    if answer.get("outcome") == "insufficient_information" and ids:
                        issues.append("uncertainty_with_positive_section")
                    for provision_id in ids:
                        positives[provision_id].append((split, line_no, source_id, text, bool(issues)))
                    if issues:
                        weak.append({"split": split, "line": line_no,
                                     "source_id": source_id,
                                     "possible_provision_ids": "|".join(ids),
                                     "word_count": len(text.split()),
                                     "issues": "|".join(issues),
                                     "disposition": "excluded_from_complaint_training_candidate",
                                     "complaint": text})
                        for issue in issues:
                            counts[f"triage_issue_{issue}"] += 1
                        continue
                    counts[f"{split}_triage_candidate_kept"] += 1
                    candidate_source_ids.add(source_id)
                    for provision_id in ids:
                        candidate_positives[(split, provision_id)] += 1
                    if answer.get("outcome") == "insufficient_information":
                        for item in answer.get("uncertain_sections", []):
                            provision_id = item.get("provision_id")
                            if provision_id:
                                candidate_uncertainty[(split, provision_id)] += 1
                elif family == "workflow":
                    counts[f"{split}_workflow_candidate_kept"] += 1
                else:
                    structural.append({"split": split, "line": line_no,
                                       "source_id": meta.get("source_id", ""),
                                       "issue": f"unrecognized_task_family:{family}"})
                    continue
                data_out.write(data_line)
                map_out.write(meta_line)

    if not set(supersessions).issubset(source_ids):
        raise ValueError("Superseded source case missing")
    if not set(supersessions.values()).issubset(candidate_source_ids):
        raise ValueError("Replacement case missing from complaint candidate")
    if not accepted_floor.issubset(candidate_source_ids):
        raise ValueError("Accepted floor case missing from complaint candidate")

    write_csv(OUT / "weak_triage.csv", weak,
              ["split", "line", "source_id", "possible_provision_ids",
               "word_count", "issues", "disposition", "complaint"])
    write_csv(OUT / "qa_screen.csv", qa,
              ["split", "line", "source_id", "source_sections", "task_type", "issues", "decision"])
    write_csv(OUT / "structural_failures.csv", structural,
              ["split", "line", "source_id", "issue"])
    with sqlite3.connect(DB) as conn:
        laws = conn.execute("""SELECT provision_id,candidate_title FROM provision
            WHERE legal_status='in_force' AND provision_kind='offence'
            ORDER BY act_id,CAST(section_number AS INTEGER),section_number""").fetchall()
    per_section = []
    for provision_id, title in laws:
        old_train = sum(r[0] == "train" for r in positives[provision_id])
        train = candidate_positives[("train", provision_id)]
        dev = candidate_positives[("dev", provision_id)]
        per_section.append({"provision_id": provision_id, "title": title,
                            "source_train_positive": old_train,
                            "candidate_train_positive": train,
                            "candidate_dev_positive": dev,
                            "candidate_train_missing_fact": candidate_uncertainty[("train", provision_id)],
                            "needs_realistic_positive": int(train == 0),
                            "needs_independent_dev": int(dev == 0)})
    write_csv(OUT / "per_section.csv", per_section,
              ["provision_id", "title", "source_train_positive", "candidate_train_positive",
               "candidate_dev_positive", "candidate_train_missing_fact",
               "needs_realistic_positive", "needs_independent_dev"])
    summary = {
        "source_export": str(SOURCE.relative_to(ROOT)),
        "source_manifest_sha256": sha(SOURCE / "manifest.json"),
        "supersessions_sha256": sha(args.supersessions),
        "superseded_rows": len(supersessions),
        "accepted_floor_sha256": sha(args.accepted_floor),
        "accepted_floor_rows": len(accepted_floor),
        "counts": dict(sorted(counts.items())),
        "weak_triage_rows": len(weak),
        "qa_rows_held_separately": len(qa),
        "structural_failures": len(structural),
        "single_positive_sections_in_source_export": sum(
            len([r for r in rows if r[0] == "train"]) == 1 for rows in positives.values()),
        "candidate_sections_with_train_positive": sum(r["candidate_train_positive"] > 0 for r in per_section),
        "candidate_sections_without_train_positive": sum(r["needs_realistic_positive"] for r in per_section),
        "candidate_sections_with_at_least_two_train_positives": sum(
            r["candidate_train_positive"] >= 2 for r in per_section),
        "candidate_min_train_positives_per_section": min(
            r["candidate_train_positive"] for r in per_section),
        "candidate_sections_with_dev_positive": sum(r["candidate_dev_positive"] > 0 for r in per_section),
        "candidate_sections_with_train_missing_fact": sum(r["candidate_train_missing_fact"] > 0 for r in per_section),
        "candidate_export": str(TRAIN_CANDIDATE.relative_to(ROOT)),
        "candidate_sha256": {p.name: sha(p) for pair in candidate_files.values() for p in pair},
        "limits": [
            "Mechanical screens do not validate legal elements, exceptions, or answer accuracy.",
            "The candidate export excludes Q&A and unapproved short, floor, or superseded triage rows; it is not a final approved training set.",
            "No sealed cases are in this export and no sealed prompts were read by this audit.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (TRAIN_CANDIDATE / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
