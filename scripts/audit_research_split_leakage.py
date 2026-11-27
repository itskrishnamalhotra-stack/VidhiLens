"""Find exact and lexical train/development/test overlap in complaint triage.

This is a screening tool. A low lexical score cannot rule out shared scenario
families or semantic leakage, and a high score needs contextual review.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "review_automation" / "research_leakage_v14"


def norm(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    out = args.out.resolve()
    rows = []
    with sqlite3.connect(DB) as conn:
        for key, split, data, meta in conn.execute("""SELECT record_key,split,data_json,metadata_json
            FROM research_sft_record WHERE task_kind='triage'"""):
            data, meta = json.loads(data), json.loads(meta)
            prompt = " ".join(m["content"] for m in data["messages"] if m["role"] == "user")
            rows.append((key, split, norm(prompt),
                         meta.get("source_id") or meta.get("scenario_id") or key))
        for key, prompt in conn.execute("""SELECT scenario_id,complaint_text FROM scenario
            WHERE split='sealed_test' AND quality_status='accepted'"""):
            rows.append(("legacy:" + key, "sealed_test", norm(prompt), key))
    train = [r for r in rows if r[1] == "train"]
    held = [r for r in rows if r[1] != "train"]
    choices = [r[2] for r in train]
    results = []
    for key, split, prompt, source_id in held:
        if not prompt:
            raise ValueError(f"Empty held-out prompt: {key}")
        hit = process.extractOne(prompt, choices, scorer=fuzz.ratio)
        nearest = train[hit[2]]
        results.append({"held_key": key, "held_split": split, "held_source_id": source_id,
                        "train_key": nearest[0], "train_source_id": nearest[3],
                        "lexical_similarity": round(hit[1] / 100, 3),
                        "exact_match": int(prompt == nearest[2])})
    out.mkdir(parents=True, exist_ok=True)
    with (out / "nearest_train.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    summary = {"train_triage": len(train), "held_out_triage": len(held),
               "held_by_split": dict(Counter(r[1] for r in held)),
               "exact_matches": sum(r["exact_match"] for r in results),
               "lexical_similarity_at_least_0_75": sum(r["lexical_similarity"] >= .75 for r in results),
               "highest_similarity": sorted(results, key=lambda r: r["lexical_similarity"],
                                            reverse=True)[:20],
               "interpretation": "Screen only; semantic or family leakage still needs review."}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "highest_similarity"}, indent=2))


if __name__ == "__main__":
    main()
