"""Account for every public candidate and generate evidence-backed review gaps.

This is a deterministic preflight, not legal approval. It never changes training
eligibility or the master database. Review packets include the official text and
publisher hints so subsequent AI review can resolve only genuine exceptions.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from build_full_kb import DB_PATH, ROOT, sha256


OUT = ROOT / "review_automation"
LAW_QUEUE = ROOT / "data_drafts" / "law_review_queue.jsonl"
LAW_PREFLIGHT = ROOT / "data_drafts" / "law_preflight_packets"
PUBLIC_MANIFEST = ROOT / "external_candidates_manifest.json"
ADDITIONAL_MANIFEST = ROOT / "additional_candidates_manifest.json"
OFFICIAL_MANIFEST = ROOT / "sources_manifest.json"
SECTION_CITATION = re.compile(r"\bsection\s*\d+", re.I)
PHONE_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|(?<!\d)(?:\+91[- ]?)?[6-9]\d{9}(?!\d)")


def normalized(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def write_packets(folder: Path, rows: list[dict], size: int = 50) -> list[dict]:
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for offset in range(0, len(rows), size):
        path = folder / f"packet_{offset // size + 1:02d}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows[offset:offset + size]), encoding="utf-8")
        files.append({"path": path.relative_to(ROOT).as_posix(), "rows": min(size, len(rows) - offset), "sha256": sha256(path)})
    return files


def check_manifests() -> dict:
    results = {}
    for manifest_path in (PUBLIC_MANIFEST, ADDITIONAL_MANIFEST):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for source in manifest["files"]:
            path = ROOT / source["local_path"]
            valid = path.is_file() and path.stat().st_size == source["bytes"] and sha256(path) == source["sha256"]
            if not valid:
                raise ValueError(f"Source hash/size mismatch: {source['key']}")
            results[source["key"]] = {"license": source.get("license"), "revision": source["revision"],
                                      "sha256": source["sha256"], "url": source["url"]}
    for source in json.loads(OFFICIAL_MANIFEST.read_text(encoding="utf-8"))["sources"]:
        path = ROOT / source["path"]
        if not path.is_file() or path.stat().st_size != source["bytes"] or sha256(path) != source["sha256"]:
            raise ValueError(f"Official source hash/size mismatch: {source['source_id']}")
    return results


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source_info = check_manifests()
    preflight = {}
    for path in sorted(LAW_PREFLIGHT.glob("packet_*.jsonl")):
        for row in jsonl(path):
            if row["provision_id"] in preflight:
                raise ValueError(f"Duplicate law preflight row: {row['provision_id']}")
            preflight[row["provision_id"]] = row
    preflight_report = json.loads((LAW_PREFLIGHT / "report.json").read_text(encoding="utf-8"))
    if len(preflight) != preflight_report["queue_rows"]:
        raise ValueError("Law preflight report disagrees with packets")
    for item in preflight_report["packets"]:
        path = ROOT / item["path"]
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise ValueError(f"Law preflight packet hash mismatch: {item['path']}")

    disposition = Counter()
    source_counts = defaultdict(Counter)
    issue_counts = Counter()
    review_candidates = []
    seen_text: dict[str, tuple[str, int]] = {}
    duplicate_pairs = []
    duplicate_by_source_pair = Counter()
    decisions = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Master database integrity check failed")
        provisions = {pid: {"act_id": act, "section_number": number, "title": title,
                            "legal_status": status, "verified_text": text,
                            "source_id": source, "source_pdf_page": page, "recommendable": bool(ok)}
                      for pid, act, number, title, status, text, source, page, ok in conn.execute(
                          "SELECT provision_id,act_id,section_number,candidate_title,legal_status,verified_text,source_id,source_pdf_page,recommendable FROM provision")}
        recommendable = {pid for pid, info in provisions.items() if info["recommendable"]}
        source_urls = dict(conn.execute("SELECT source_id,url FROM source_snapshot"))
        previous_review = {(key, number): decision for key, number, decision in conn.execute(
            "SELECT source_key,row_number,decision FROM public_candidate_review")}
        accepted_text = {normalized(t) for t, in conn.execute("SELECT complaint_text FROM scenario WHERE quality_status='accepted'")}

        for key, number, input_text, record_json in conn.execute(
                "SELECT source_key,row_number,input_preview,record_json FROM public_candidate_row ORDER BY source_key,row_number"):
            row = json.loads(record_json)
            if key in {"nyaya_train", "nyaya_val"}:
                input_text = str(row.get("metadata", {}).get("rag", {}).get("question", ""))
            elif key == "bns_qa":
                input_text = str(row.get("question", ""))
            elif key == "statutory_triage":
                input_text = str(row.get("instruction", ""))
            issues = []
            if key == "bns_structured":
                state = "law_crosscheck_only"
            elif key == "bns_qa":
                state = "legal_qa_not_complaint"
            elif key in {"nyaya_val", "nyaya_eval"}:
                state = "reserved_external_evaluation"
            elif key == "statutory_triage":
                prior = previous_review.get((key, number))
                state = "approved_train" if prior == "accepted_corrected" else "reviewed_held" if prior == "held" else "publisher_labels_rejected"
                issues.append("publisher_labels_known_unreliable")
            else:
                state = "generated_qa_not_approved"
                issues.append("publisher_verified_false")
            decisions.append((key, number, state, issues, input_text))

        for key, number, input_text, label_json, issue_json, record_json in conn.execute(
                "SELECT source_key,row_number,input_text,publisher_labels_json,issue_codes_json,record_json "
                "FROM additional_candidate_row ORDER BY source_key,row_number"):
            row = json.loads(record_json)
            labels = json.loads(label_json)
            issues = json.loads(issue_json)
            if key in {"nyaya_statute_bns", "nyaya_statute_it"}:
                state = "law_crosscheck_only"
            elif key in {"nyaya_v3_val", "nyaya_v3_test"}:
                state = "reserved_external_evaluation"
            elif key in {"complaint_bns", "fraud_cyber"}:
                state = "rights_blocked"
            elif key == "nariraksha":
                state = "synthetic_topic_only"
            else:
                state = "generated_qa_not_approved"
                label_ids = [s.replace("BNS:", "BNS_").replace("IT_ACT:", "ITA_").split("(")[0]
                             for s in labels]
                if any(pid in recommendable for pid in label_ids) and len(input_text.split()) >= 25 and not SECTION_CITATION.search(input_text):
                    state = "candidate_review_queue"
                    context = []
                    for pid in label_ids:
                        if pid in provisions:
                            p = provisions[pid]
                            context.append({"provision_id": pid, "title": p["title"],
                                            "legal_status": p["legal_status"],
                                            "recommendable": p["recommendable"],
                                            "verified_text": p["verified_text"],
                                            "official_url": source_urls.get(p["source_id"]),
                                            "official_pdf_page": p["source_pdf_page"]})
                    review_candidates.append({
                        "source_key": key, "row_number": number,
                        "source_file_sha256": source_info[key]["sha256"],
                        "source_url": source_info[key]["url"],
                        "input_text": input_text, "publisher_section_hints": labels,
                        "official_section_context": context,
                        "review_questions": ["Does this input state an incident rather than just ask for a definition?",
                                             "Which facts establish or fail each section element?",
                                             "Is a follow-up or abstention required?",
                                             "Is the publisher answer accurate, and is it excluded from the model input?"],
                        "training_approved": False,
                    })
            decisions.append((key, number, state, issues, input_text))

        law_current = {row["provision_id"]: row for row in jsonl(LAW_QUEUE)}
        expected = {pid for pid, p in provisions.items() if p["legal_status"] == "pending_review" or
                    (p["legal_status"] == "in_force" and p["verified_text"] is None)}
        if set(law_current) != expected:
            raise ValueError("Law review queue is stale relative to the master")
        if not expected <= set(preflight):
            raise ValueError("Current law review queue lacks second-parser context")
        law_packets = []
        law_priority = Counter()
        for pid, row in law_current.items():
            prior = preflight[pid]
            flags = row["mechanical_flags"]
            parser_diff = prior["five_token_sequence_recall"] < 0.95
            priority = "P1_status_or_parser_conflict" if row["legal_status"] == "pending_review" or parser_diff else (
                       "P2_editorial_cleanup" if flags else "P3_clean_text_check")
            law_priority[priority] += 1
            law_packets.append({"provision_id": pid, "priority": priority,
                                "act_id": row["act_id"], "section_number": row["section_number"],
                                "title": row["candidate_title"], "current_status": row["legal_status"],
                                "official_source_url": row["source_url"],
                                "official_pdf_page": row["source_pdf_page"],
                                "official_pdf_sha256": row["source_pdf_sha256"],
                                "extracted_text": row["extracted_text"],
                                "second_parser_recall": prior["five_token_sequence_recall"],
                                "second_parser_excerpt": prior["second_extraction_excerpt"],
                                "mechanical_flags": flags,
                                "review_questions": ["Is the section currently in force, omitted, excepted or uncertain?",
                                                     "Does the extracted text exactly represent the official source?",
                                                     "Is this an offence, civil penalty, procedure, definition or support provision?"],
                                "legal_review_approved": False})
        law_packets.sort(key=lambda r: (r["priority"], r["act_id"], r["section_number"]))
        coverage = [dict(provision_id=pid, train=train, dev=dev, sealed_test=test)
                    for pid, train, dev, test in conn.execute("SELECT * FROM master_section_coverage ORDER BY provision_id")]
        languages = dict(conn.execute("SELECT language,count(*) FROM scenario WHERE quality_status='accepted' GROUP BY language"))
        actions = dict(conn.execute("SELECT assistant_action,count(*) FROM conversation_example WHERE quality_status='accepted' GROUP BY assistant_action"))
        split_counts = dict(conn.execute("SELECT split,count(*) FROM scenario WHERE quality_status='accepted' GROUP BY split"))
        silver_rows, silver_families = conn.execute("SELECT count(*),count(DISTINCT scenario_group) FROM scenario WHERE quality_status='accepted' AND split='train' AND review_tier='silver'").fetchone()

    # Cross-source exact-text accounting is separate from review disposition.
    with (OUT / "row_dispositions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["source_key", "row_number", "disposition", "word_count", "exact_duplicate_of", "issue_codes"])
        for key, number, state, issues, input_text in decisions:
            token = normalized(input_text)
            duplicate = seen_text.get(token) if token else None
            if duplicate:
                duplicate_pairs.append({"source_key": key, "row_number": number,
                                        "duplicate_of": f"{duplicate[0]}:{duplicate[1]}"})
                duplicate_by_source_pair[f"{duplicate[0]} -> {key}"] += 1
            elif token:
                seen_text[token] = (key, number)
            if token and token in accepted_text and state != "approved_train":
                issues.append("matches_existing_accepted_case")
            if PHONE_EMAIL.search(input_text):
                issues.append("possible_phone_or_email")
            disposition[state] += 1
            source_counts[key][state] += 1
            for issue in set(issues):
                issue_counts[issue] += 1
            writer.writerow([key, number, state, len(input_text.split()),
                             f"{duplicate[0]}:{duplicate[1]}" if duplicate else "", ";".join(sorted(set(issues)))])

    if len(decisions) != 17573 or sum(disposition.values()) != len(decisions):
        raise ValueError("Not every indexed public row received a disposition")
    # Keep only one copy of a question in the actionable case queue.
    unique_candidates = []
    candidate_seen = set()
    for item in review_candidates:
        token = normalized(item["input_text"])
        if token in candidate_seen or token in accepted_text:
            continue
        candidate_seen.add(token)
        unique_candidates.append(item)
    unique_candidates.sort(key=lambda x: (x["source_key"], x["row_number"]))
    case_files = write_packets(OUT / "case_review_packets", unique_candidates)
    law_files = write_packets(OUT / "law_review_packets", law_packets)
    gaps = {
        "law_open": len(law_packets),
        "law_priority": dict(law_priority),
        "recommendable_sections_now": len(recommendable),
        "sources_with_unspecified_license": {key: sum(source_counts[key].values()) for key, info in source_info.items()
                                             if info["license"] in (None, [], "")},
        "pilot_sections_without_dev_positive": [r["provision_id"] for r in coverage if r["dev"] == 0],
        "pilot_sections_with_fewer_than_10_train_positives": [r["provision_id"] for r in coverage if r["train"] < 10],
        "pilot_sections_with_fewer_than_5_sealed_positives": [r["provision_id"] for r in coverage if r["sealed_test"] < 5],
        "silver_train_rows": silver_rows,
        "silver_fact_pattern_families": silver_families,
        "languages": languages,
        "workflow_actions": actions,
        "accepted_splits": split_counts,
    }
    report = {
        "as_of": date.today().isoformat(), "automation_version": "review-preflight-v1",
        "master_database_sha256": sha256(DB_PATH),
        "public_rows_accounted_for": len(decisions),
        "dispositions": dict(disposition),
        "by_source": {key: dict(value) for key, value in source_counts.items()},
        "issue_counts": dict(issue_counts),
        "normalized_text_duplicate_rows": len(duplicate_pairs),
        "duplicate_by_source_pair": dict(duplicate_by_source_pair),
        "duplicate_examples": duplicate_pairs[:20],
        "case_review_queue": {"rows": len(unique_candidates), "packets": case_files,
                              "autoapproved_rows": 0},
        "law_review_queue": {"rows": len(law_packets), "packets": law_files,
                             "autoapproved_rows": 0},
        "gaps": gaps,
        "meaning": "Rows are accounted for and review packets prepared. No new legal text, public labels or training examples were approved.",
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Automated review output", "", f"Date: {report['as_of']}.", "",
             f"- Public rows accounted for: **{len(decisions):,}**.",
             f"- Case candidates requiring source-grounded review: **{len(unique_candidates)}**.",
             f"- Law sections requiring status/text review: **{len(law_packets)}**.",
             f"- Repeated normalized input texts: **{len(duplicate_pairs)}** (screening signal, not legal equivalence).",
             f"- Nyaya v7 question texts already present in v3: **{duplicate_by_source_pair['nyaya_train -> nyaya_v3_train'] + duplicate_by_source_pair['nyaya_val -> nyaya_v3_val']}**.",
             "- New rows approved for training by this automation: **0**.", "",
             "## Dispositions", ""]
    lines += [f"- `{key}`: {value:,}" for key, value in disposition.most_common()]
    lines += ["", "## Gaps to resolve after preflight", "",
              f"- Law priority buckets: {dict(law_priority)}.",
              f"- Source rights unresolved: {gaps['sources_with_unspecified_license']}.",
              f"- No development positive for: {', '.join(gaps['pilot_sections_without_dev_positive'])}.",
              f"- Fewer than ten train positives: {', '.join(gaps['pilot_sections_with_fewer_than_10_train_positives']) or 'none'}.",
              f"- Fewer than five sealed-test positives: {len(gaps['pilot_sections_with_fewer_than_5_sealed_positives'])} of {len(recommendable)} pilot sections.",
              f"- Silver train variants: {silver_rows:,} rows from {silver_families} fact-pattern families.",
              f"- Languages: {languages}.",
              f"- Workflow action examples: {actions}.", "",
              "Use `row_dispositions.csv` to trace each source row, the case and law packets for review context, and `report.json` for exact counts. These files are preflight outputs, not a new training export."]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"public_rows_accounted_for": len(decisions), "dispositions": dict(disposition),
                      "normalized_text_duplicate_rows": len(duplicate_pairs), "case_review_queue": len(unique_candidates),
                      "law_review_queue": len(law_packets), "law_priority": dict(law_priority),
                      "output": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
