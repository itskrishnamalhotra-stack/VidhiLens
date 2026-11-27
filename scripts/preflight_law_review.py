"""Prepare 100-section law review packets with an independent PDF text check.

Run with the bundled workspace Python that provides pypdf. This is a screening
step only: parser agreement never promotes text or legal status to verified.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "sources_manifest.json"
QUEUE = ROOT / "data_drafts" / "law_review_queue.jsonl"
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "data_drafts" / "law_preflight_packets_v2"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def ngrams(words: list[str], width: int = 5) -> set[tuple[str, ...]]:
    return set(zip(*(words[i:] for i in range(width)))) if len(words) >= width else set()


def main() -> None:
    manifest = {row["source_id"]: row for row in json.loads(MANIFEST.read_text(encoding="utf-8"))["sources"]}
    queue = [json.loads(line) for line in QUEUE.read_text(encoding="utf-8").splitlines() if line.strip()]
    with sqlite3.connect(DB) as conn:
        expected_queue = conn.execute("""SELECT count(*) FROM provision WHERE legal_status='pending_review'
            OR (legal_status='in_force' AND verified_text IS NULL)""").fetchone()[0]
    if len(queue) != expected_queue:
        raise SystemExit(f"Stale law review queue: file has {len(queue)}, database has {expected_queue}")
    readers = {}
    page_text = {}
    for source_id in {row["source_id"] for row in queue}:
        source = manifest[source_id]
        path = ROOT / source["path"]
        if digest(path) != source["sha256"]:
            raise SystemExit(f"Official PDF hash mismatch: {source_id}")
        reader = PdfReader(str(path))
        if len(reader.pages) != source["pages"]:
            raise SystemExit(f"Official PDF page count mismatch: {source_id}")
        readers[source_id] = reader
        page_text[source_id] = {}
    with sqlite3.connect(DB) as conn:
        provision_pages = {}
        for source_id in readers:
            provision_pages[source_id] = [(pid, page) for pid, page in conn.execute(
                "SELECT provision_id,source_pdf_page FROM provision WHERE source_id=? "
                "ORDER BY CAST(section_number AS INTEGER),section_number", (source_id,))]
    next_page = {}
    for source_id, rows in provision_pages.items():
        for index, (pid, start) in enumerate(rows):
            next_page[pid] = rows[index + 1][1] if index + 1 < len(rows) else len(readers[source_id].pages)
    OUT.mkdir(parents=True, exist_ok=True)
    prepared = []
    buckets = Counter()
    for row in queue:
        source_id = row["source_id"]
        start = row["source_pdf_page"]
        end = min(max(start, next_page[row["provision_id"]]), len(readers[source_id].pages), start + 5)
        pages = []
        for page_number in range(start, end + 1):
            if page_number not in page_text[source_id]:
                page_text[source_id][page_number] = readers[source_id].pages[page_number - 1].extract_text() or ""
            pages.append(page_text[source_id][page_number])
        first = ngrams(tokens(row["extracted_text"]))
        second = ngrams(tokens("\n".join(pages)))
        recall = round(len(first & second) / len(first), 4) if first else 0.0
        bucket = "parser_agreement" if recall >= 0.95 else "parser_difference"
        if row["mechanical_flags"]:
            bucket += "_with_flags"
        buckets[bucket] += 1
        prepared.append({
            "provision_id": row["provision_id"], "act_id": row["act_id"],
            "section_number": row["section_number"], "title": row["candidate_title"],
            "legal_status": row["legal_status"], "official_source_id": source_id,
            "official_pdf_sha256": row["source_pdf_sha256"],
            "official_pdf_page": start, "second_extraction_pages": [start, end],
            "five_token_sequence_recall": recall, "screen_bucket": bucket,
            "mechanical_flags": row["mechanical_flags"],
            "extracted_text": row["extracted_text"],
            "second_extraction_excerpt": " ".join("\n".join(pages).split())[:700],
            "review_required": True,
            "note": "A second parser checks transcription only. It does not establish legal status, offence kind, or amendment correctness.",
        })
    files = []
    for offset in range(0, len(prepared), 100):
        path = OUT / f"packet_{offset // 100 + 1:02d}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in prepared[offset:offset + 100]), encoding="utf-8")
        files.append({"path": path.relative_to(ROOT).as_posix(), "rows": min(100, len(prepared) - offset), "sha256": digest(path)})
    editorial_flags = {"embedded_page_number", "chapter_heading_lines",
                       "editorial_amendment_markers", "amendment_footnote_lines",
                       "possible_civil_penalty_wording"}
    report = {"queue_rows": len(prepared), "packet_size": 100, "packets": files,
              "screen_buckets": dict(buckets), "legal_rows_autoapproved": 0,
              "clean_parser_agreement": sum(r["five_token_sequence_recall"] >= 0.95
                  and not editorial_flags.intersection(r["mechanical_flags"]) for r in prepared),
              "agreement_with_editorial_flags": sum(r["five_token_sequence_recall"] >= 0.95
                  and bool(editorial_flags.intersection(r["mechanical_flags"])) for r in prepared),
              "parser_differences": sum(r["five_token_sequence_recall"] < 0.95 for r in prepared),
              "official_source_ids": sorted(readers)}
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
