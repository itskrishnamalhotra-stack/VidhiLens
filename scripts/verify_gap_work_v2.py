"""Verify the new held-out examples and report full-act coverage gaps."""
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
DATA = ROOT / "data_drafts" / "gap_examples_v2"
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "review_automation" / "complaint_pool_v2"


def norm(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def read(split: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / f"{split}.jsonl").open(encoding="utf-8")]


def main() -> None:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    rows = {split: read(split) for split in ("train", "dev", "sealed_test")}
    for split, examples in rows.items():
        digest = hashlib.sha256((DATA / f"{split}.jsonl").read_text(encoding="utf-8").encode()).hexdigest()
        if digest != manifest["files_sha256"][split]: raise ValueError(f"Hash mismatch {split}")
        if len(examples) != manifest["counts"][split]: raise ValueError(f"Count mismatch {split}")
    conn = sqlite3.connect(DB)
    base = defaultdict(Counter)
    for split, pid, label in conn.execute("""SELECT s.split,l.provision_id,l.label
        FROM scenario s JOIN scenario_provision_label l USING (scenario_id)
        WHERE s.quality_status='accepted'"""):
        base[pid][f"{split}_{label}"] += 1
    seen: dict[str, str] = {}
    triage_texts = {s: [] for s in rows}
    for split, examples in rows.items():
        for row in examples:
            messages = row["messages"]
            if messages[-1]["role"] != "assistant": raise ValueError("Assistant target missing")
            target = json.loads(messages[-1]["content"])
            if row["metadata"]["kind"] == "triage":
                text = messages[1]["content"]
                key = norm(text)
                if key in seen: raise ValueError(f"Exact split leakage: {seen[key]} / {row['id']}")
                seen[key] = row["id"]
                triage_texts[split].append((row["id"], text))
                pid = row["metadata"]["target_provision_id"]
                if target["outcome"] == "provision_match":
                    if target["possible_provision_ids"] != [pid] or target["uncertain_sections"]:
                        raise ValueError(f"Bad positive target {row['id']}")
                elif target["outcome"] == "insufficient_information":
                    if target["possible_provision_ids"] or target["uncertain_sections"][0]["provision_id"] != pid:
                        raise ValueError(f"Bad uncertainty target {row['id']}")
                else: raise ValueError(f"Unexpected target {row['id']}")
                base[pid][f"new_{split}_{'uncertain' if target['outcome']=='insufficient_information' else 'possible'}"] += 1
            elif row["metadata"]["kind"] == "workflow":
                if set(target) != {"assistant_action", "assistant_message", "tool_payload"}:
                    raise ValueError(f"Bad workflow target {row['id']}")
                if target["tool_payload"].get("official_filing") is not False:
                    raise ValueError(f"Workflow wrongly claims an official filing {row['id']}")

    # A deliberately conservative similarity diagnostic. It is reported, not a
    # legal approval rule; all splits already have exact disjointness above.
    near = []
    for test_id, test_text in triage_texts["sealed_test"]:
        for train_id, train_text in triage_texts["train"]:
            ratio = difflib.SequenceMatcher(None, norm(test_text), norm(train_text)).ratio()
            if ratio >= .75: near.append({"sealed_id": test_id, "train_id": train_id,
                                           "similarity": round(ratio, 3)})
    laws = conn.execute("""SELECT provision_id,act_id,section_number,candidate_title,
        legal_status,provision_kind,verified_text IS NOT NULL,recommendable
        FROM provision ORDER BY act_id,section_number""").fetchall()
    conn.close()
    fields = ["provision_id", "act_id", "section_number", "title", "legal_status",
              "kind", "verified_text", "pilot_recommendable", "existing_train_possible",
              "existing_dev_possible", "existing_sealed_possible", "new_train_possible",
              "new_dev_possible", "new_sealed_possible", "new_train_uncertain",
              "new_sealed_uncertain"]
    with (OUT / "coverage_gaps.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for pid, act, number, title, status, kind, verified, recommendable in laws:
            x = base[pid]
            writer.writerow(dict(zip(fields, [pid, act, number, title, status, kind, int(verified),
                                               recommendable, x["train_possible"], x["dev_possible"],
                                               x["sealed_test_possible"], x["new_train_possible"],
                                               x["new_dev_possible"], x["new_sealed_test_possible"],
                                               x["new_train_uncertain"], x["new_sealed_test_uncertain"]])))
    report = {
        "new_examples_verified": {s: len(v) for s, v in rows.items()},
        "exact_cross_split_duplicates": 0,
        "new_sealed_vs_new_train_similarity_at_least_0_75": near,
        "indexed_provisions": len(laws),
        "existing_pilot_provisions": sum(bool(r[7]) for r in laws),
        "additional_provisions_with_research_examples": len(manifest["sections_added_as_research_cases"]),
        "in_force_offence_rows_still_without_either_positive_train_example": sum(
            status == "in_force" and kind == "offence" and not
            (base[pid]["train_possible"] or base[pid]["new_train_possible"])
            for pid, _, _, _, status, kind, _, _ in laws),
        "limits": "A section is not covered merely because it has one example. Official text and source-row labels still require evaluation.",
    }
    (OUT / "coverage_summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
