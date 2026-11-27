"""Apply stricter text-only quality filters to LeSICiN train candidates.

This is a screening heuristic, not a legal-label approval. It flags how many
court excerpts still look procedural after removing obvious section citations.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
TRAIN = ROOT / "external_candidates" / "lesicin_6053791" / "train.jsonl"
OUT = ROOT / "lesicin_narrative_screen.json"
LABEL = re.compile(r"^Section (\d+[A-Z]?)")
DIRECT_CITATION = re.compile(r"\b(?:sections?|secs?\.?|u/s)\s*\d|\bI\.?P\.?C\.?\b|\bCr\.?P\.?C\.?\b", re.I)
PROCEDURE = re.compile(r"\b(?:court|judg(?:e|ment)|petitions?|petitioners?|applicants?|appellants?|respondents?|magistrates?|counsel|bail|appeals?|convictions?|sentences?|trials?|orders?|accused|police station|fir|certified copy|proceedings?)\b", re.I)
PII = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|(?<!\d)(?:\+91[- ]?)?[6-9]\d{9}(?!\d)")


def main() -> None:
    with sqlite3.connect(DB) as conn:
        pilot = {r[0] for r in conn.execute("SELECT provision_id FROM recommendable_provision")}
        links = defaultdict(set)
        for ipc, bns in conn.execute("SELECT ipc_section,bns_provision_id FROM ipc_bns_crosswalk_candidate"):
            links[ipc].add(bns)
    counts = Counter()
    sample = []
    with TRAIN.open("r", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            counts["all_train"] += 1
            labels = [LABEL.match(raw)[1] for raw in row["labels"]]
            if not any(links[label] & pilot for label in labels):
                continue
            counts["any_pilot_crosswalk_candidate"] += 1
            text = " ".join(row["text"])
            word_count = len(text.split())
            if not 50 <= word_count <= 800 or PII.search(text):
                continue
            counts["reasonable_length_no_simple_pii"] += 1
            if DIRECT_CITATION.search(text):
                continue
            counts["no_obvious_statute_citation"] += 1
            if PROCEDURE.search(text):
                continue
            counts["no_obvious_procedural_word"] += 1
            if len(sample) < 8:
                sample.append({"id": str(row["id"]), "labels": labels,
                               "words": word_count})
    report = {"counts": dict(counts), "examples_for_ai_inspection": sample,
              "interpretation": "The last filter is intentionally strict and may reject useful facts. Passing it does not verify the IPC label, BNS mapping, privacy, or complaint style."}
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
