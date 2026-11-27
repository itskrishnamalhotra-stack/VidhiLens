"""Index every BNS and IT Act section from saved official PDFs.

PDF extraction is explicitly unverified. It is stored for review/search only;
the application view stays empty until text and status are source checked.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "sources_manifest.json").read_text(encoding="utf-8"))
SCOPE = json.loads((ROOT / "scope_candidates.json").read_text(encoding="utf-8"))
DB_PATH = ROOT / "db" / "master_dataset.sqlite"
HEADING = re.compile(r"^(?:\d+\[)?(?P<number>\d{1,3}[A-Z]?)\.(?:\s|\ufffd|\u2014|\u2013)(?P<rest>.*)$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sort_key(number: str) -> tuple[int, str]:
    match = re.fullmatch(r"(\d+)([A-Z]?)", number)
    assert match is not None
    return int(match[1]), match[2]


def candidate_title(number: str, extracted: str) -> str:
    opening = " ".join(extracted.splitlines()[:5])
    opening = re.sub(r"^(?:\d+\[)?" + re.escape(number) + r"\.[\s\ufffd\u2014\u2013]*", "", opening)
    if opening.startswith("[") and ".]" in opening:
        title = opening.split(".]", 1)[0].lstrip("[")
    else:
        title = re.split(r"\.[\s]*[\ufffd\u2014\u2013]", opening, maxsplit=1)[0]
        title = re.split(r"[\u2014\u2013\ufffd](?=Whoever|Where|The )", title, maxsplit=1)[0]
    return " ".join(title.strip(" .\ufffd\u2014\u2013").split()) or f"Section {number}"


IT_FOOTNOTE_STARTS = (
    "Subs.", "Ins.", "Clause ", "Clauses ", "The word ", "The words ",
    "Certain words ", "Section 66A has",
)
EXPLICIT_IT_OMISSIONS = frozenset(
    '20 49 50 51 52 52A 52B 52C 53 54 56 91 92 93 94'.split()
)


def extract_sections(path: Path, first_page: int, last_page: int, *, skip_it_footnotes: bool = False) -> list[dict]:
    document = fitz.open(path)
    sections: list[dict] = []
    current: dict | None = None
    last_key = (0, "")
    for page_index in range(first_page - 1, last_page):
        for line in document[page_index].get_text().splitlines():
            stripped = line.strip()
            match = HEADING.match(stripped)
            if match and skip_it_footnotes and match["rest"].startswith(IT_FOOTNOTE_STARTS):
                match = None
            # This India Code PDF glues footnote marker 2 to heading 66A: "266A.".
            number = "66A" if match and skip_it_footnotes and match["number"] == "266A" else (match["number"] if match else None)
            if match and sort_key(number) > last_key:
                if current:
                    current["extracted_text"] = "\n".join(current.pop("lines")).strip()
                    current["candidate_title"] = candidate_title(current["section_number"], current["extracted_text"])
                    sections.append(current)
                current = {"section_number": number, "source_pdf_page": page_index + 1, "lines": [stripped]}
                last_key = sort_key(number)
            elif current and stripped:
                current["lines"].append(stripped)
    if current:
        current["extracted_text"] = "\n".join(current.pop("lines")).strip()
        current["candidate_title"] = candidate_title(current["section_number"], current["extracted_text"])
        sections.append(current)
    return sections


def validate_source_files() -> None:
    for source in MANIFEST["sources"]:
        path = ROOT / source["path"]
        if not path.is_file() or sha256(path) != source["sha256"]:
            raise SystemExit(f"Source missing or hash mismatch: {path}")


def main() -> None:
    validate_source_files()
    bns = extract_sections(ROOT / "sources/bns_2023_indiacode_2025-10-06.pdf", 16, 111)
    ita = extract_sections(ROOT / "sources/it_act_2000_indiacode_current.pdf", 5, 35, skip_it_footnotes=True)
    if [x["section_number"] for x in bns] != [str(n) for n in range(1, 359)]:
        raise SystemExit("BNS extraction is not a complete ordered 1–358 sequence")
    ita_numbers = {x["section_number"] for x in ita}
    if len(ita) != 125 or "3A" not in ita_numbers or any(str(n) not in ita_numbers for n in range(1, 95)):
        raise SystemExit("IT Act extraction does not contain expected 94 base and 31 inserted sections")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        existing = sqlite3.connect(DB_PATH)
        try:
            reviewed = existing.execute("SELECT count(*) FROM provision WHERE verified_text IS NOT NULL OR recommendable = 1").fetchone()[0]
            examples = existing.execute("SELECT count(*) FROM scenario").fetchone()[0]
        finally:
            existing.close()
        if reviewed or examples:
            raise SystemExit("Refusing to replace a KB with reviewed law or examples")
        DB_PATH.unlink()

    priority = {item["id"]: item for item in SCOPE["candidate_sections"]}
    source_by_act = {
        "BNS_2023": "BNS_INDIA_CODE_2025_10_06",
        "ITA_2000": "ITA_INDIA_CODE_CURRENT_2026_09_16",
    }
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
        conn.executemany("INSERT INTO act VALUES (?, ?, ?)", [
            ("BNS_2023", "Bharatiya Nyaya Sanhita, 2023", 2023),
            ("ITA_2000", "Information Technology Act, 2000", 2000),
        ])
        for source in MANIFEST["sources"]:
            conn.execute("INSERT INTO source_snapshot VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                source["source_id"], source["act_id"], source["title"], source["url"],
                source["path"], MANIFEST["retrieved_on"], source["printed_as_of"], source["sha256"],
            ))
        for act_id, prefix, sections in [("BNS_2023", "BNS", bns), ("ITA_2000", "ITA", ita)]:
            for section in sections:
                provision_id = f"{prefix}_{section['section_number']}"
                title = priority.get(provision_id, {}).get("title", section["candidate_title"])
                omitted = provision_id == "ITA_66A" or (act_id == "ITA_2000" and section["section_number"] in EXPLICIT_IT_OMISSIONS)
                if omitted and provision_id != "ITA_66A":
                    if not re.match(r'^\d+[A-Z]?\.\s*\[[^]]+\]\W*Omitted by\b',
                                    " ".join(section["extracted_text"].splitlines()[:3])):
                        raise SystemExit(f"Expected omission wording absent: {provision_id}")
                status = "omitted" if omitted else "pending_review"
                kind = "omitted" if omitted else ("civil_penalty" if provision_id == "ITA_72A" else "pending_review")
                note = ("Section 66A was struck down and then omitted by Jan Vishwas 2023."
                        if provision_id == "ITA_66A" else
                        "Jan Vishwas 2023 replaced 72A imprisonment/fine with civil penalty; exclude from criminal complaint recommendations."
                        if provision_id == "ITA_72A" else
                        "Pinned IT Act PDF explicitly states this section was omitted."
                        if omitted else
                        "PDF text extraction may include footnotes or errors; verify before display.")
                conn.execute(
                    """INSERT INTO provision
                    (provision_id, act_id, section_number, candidate_title, source_id,
                     source_pdf_page, extracted_text, provision_kind, legal_status, priority_review, review_note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (provision_id, act_id, section["section_number"], title,
                     source_by_act[act_id], section["source_pdf_page"], section["extracted_text"],
                     kind, status, int(provision_id in priority), note),
                )
        conn.execute(
            """INSERT INTO provision_subpart_status VALUES (?, ?, ?, ?, ?)""",
            ("BNS_106", "(2)", "uncommenced", "BNS_COMMENCEMENT_SO_850E_2024",
             "MHA S.O. 850(E) commenced BNS except section 106(2) on 1 July 2024; recheck later status."),
        )
        conn.executemany("INSERT INTO blocked_provision VALUES (?, ?)", [
            ("ITA_66A", "Struck down and omitted by Jan Vishwas 2023"),
            ("ITA_72A", "Civil penalty after Jan Vishwas 2023; outside criminal complaint recommendations"),
        ] + [(f"ITA_{n}", "Pinned official IT Act PDF explicitly marks this section omitted")
             for n in sorted(EXPLICIT_IT_OMISSIONS, key=sort_key)])
        for from_id, to_id in [("BNS_115", "BNS_114"), ("BNS_117", "BNS_116"), ("ITA_66", "ITA_43")]:
            conn.execute("INSERT INTO provision_relation VALUES (?, ?, 'cross_references', ?, NULL)",
                         (from_id, to_id, "Priority review dependency"))
        conn.commit()

    with sqlite3.connect(DB_PATH) as conn:
        totals = conn.execute("SELECT act_id, count(*) FROM provision GROUP BY act_id").fetchall()
        priority_count = conn.execute("SELECT count(*) FROM provision WHERE priority_review = 1").fetchone()[0]
        approved = conn.execute("SELECT count(*) FROM recommendable_provision").fetchone()[0]
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert totals == [("BNS_2023", 358), ("ITA_2000", 125)]
    assert priority_count == 20 and approved == 0 and not fk_errors
    print(f"Built {DB_PATH}: BNS 358, IT Act 125, priority 20, recommendable 0")


if __name__ == "__main__":
    main()
