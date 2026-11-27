"""One-time development-only diagnostic of full-scope section retrieval.

Never read sealed-test records here. This is not a tuned model or an app gate.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
CATALOG = ROOT / "exports" / "full-offence-catalog-v2" / "offences.jsonl"
OUT = ROOT / "review_automation" / "retrieval_feasibility_v1"


def target(row: dict) -> tuple[list[str], str]:
    answer = json.loads(row["messages"][-1]["content"])
    prompt = " ".join(m["content"] for m in row["messages"] if m["role"] == "user")
    return answer.get("possible_provision_ids", []), prompt


def rank_top5(corpus: list[str], corpus_ids: list[str], queries: list[str]) -> list[list[str]]:
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                 min_df=1, sublinear_tf=True)
    matrix = vectorizer.fit_transform(corpus)
    query_matrix = vectorizer.transform(queries)
    ranked = []
    for q in query_matrix:
        scores = (q @ matrix.T).toarray().ravel()
        best = defaultdict(float)
        for index, score in enumerate(scores):
            key = corpus_ids[index]
            if score > best[key]:
                best[key] = float(score)
        ranked.append([pid for pid, _ in sorted(best.items(), key=lambda item: item[1],
                                               reverse=True)[:5]])
    return ranked


def main() -> None:
    laws = [json.loads(line) for line in CATALOG.read_text(encoding="utf-8").splitlines()]
    law_ids = {law["provision_id"] for law in laws}
    dev = []
    train_prompts = []
    train_ids = []
    with sqlite3.connect(DB) as conn:
        for split, data_json, meta_json in conn.execute("""SELECT split,data_json,metadata_json
            FROM research_sft_record WHERE task_kind='triage' AND split IN ('train','dev')"""):
            row = json.loads(data_json)
            ids, prompt = target(row)
            ids = [pid for pid in ids if pid in law_ids]
            if split == "dev":
                dev.append((prompt, ids, json.loads(meta_json).get("source_id")))
            elif len(ids) == 1:
                train_prompts.append(prompt)
                train_ids.append(ids[0])
    if not dev or not train_prompts:
        raise ValueError("No development or training complaints")
    prompts = [p for p, _, _ in dev]
    statute = rank_top5(
        [law["candidate_title"] + "\n" + law["retrieval_text"] for law in laws],
        [law["provision_id"] for law in laws], prompts)
    prototype = rank_top5(train_prompts, train_ids, prompts)
    rows = []
    for i, (prompt, gold, source_id) in enumerate(dev):
        if not gold:
            continue
        section_hint = bool(re.search(r"(?i)\b(?:section|sec\.?|bns|ipc|it act)\s*\d", prompt))
        rows.append({"source_id": source_id, "gold": "|".join(gold),
                     "explicit_section_hint": int(section_hint),
                     "statute_top5": "|".join(statute[i]),
                     "prototype_top5": "|".join(prototype[i]),
                     "statute_hit1": int(statute[i][0] in gold),
                     "statute_hit5": int(bool(set(statute[i]) & set(gold))),
                     "prototype_hit1": int(prototype[i][0] in gold),
                     "prototype_hit5": int(bool(set(prototype[i]) & set(gold)))})
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "per_development_case.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summaries = {}
    for name, subset in (("all", rows), ("no_section_hint", [r for r in rows if not r["explicit_section_hint"]])):
        summaries[name] = {"positive_dev_cases": len(subset),
                           **{key: round(sum(r[key] for r in subset) / len(subset), 3)
                              for key in ("statute_hit1", "statute_hit5",
                                          "prototype_hit1", "prototype_hit5")}} if subset else {}
    summary = {"scope": "development_only_no_sealed_cases_read",
               "law_sections": len(laws), "train_positive_prototypes": len(train_prompts),
               "dev_triage_records": len(dev), "dev_positive_records": len(rows),
               "metrics": summaries,
               "limits": ["Tiny dev set and many sections have no positive dev case.",
                          "Retrieval hit is not legal accuracy or calibrated abstention.",
                          "Parameters were fixed before inspecting development results."]}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
