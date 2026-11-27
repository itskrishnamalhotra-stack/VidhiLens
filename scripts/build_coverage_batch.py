"""Check and export an AI-authored section coverage batch.

Sealed cases are written separately and must never enter Colab training data.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
DEFAULT_SOURCE = ROOT / "data_drafts" / "coverage_batch08.json"
DEFAULT_BASE = ROOT / "exports" / "mixed-source-v4-research"
DEFAULT_PRIOR_SEALED = ROOT / "data_drafts" / "gap_examples_v2" / "sealed_test.jsonl"
SYSTEM = ("Read the reported incident. Return JSON only with outcome, possible_provision_ids, "
          "and uncertain_sections. A section is only a possibility, never a finding of guilt. "
          "Never invent missing facts.")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(s: str) -> str:
    return " ".join(re.findall(r"\w+", s.casefold()))


def existing_inputs(base: Path, prior_sealed: list[Path]) -> tuple[dict[str, list[tuple[str, str]]], list[tuple[str, str]]]:
    found = defaultdict(list)
    all_prior = []
    for split in ("train", "dev"):
        with (base / f"{split}_sft.jsonl").open(encoding="utf-8") as data, \
             (base / f"{split}_sft_map.jsonl").open(encoding="utf-8") as mapping:
            for line, meta_line in zip(data, mapping, strict=True):
                meta = json.loads(meta_line)
                if meta.get("kind") != "triage":
                    continue
                row = json.loads(line)
                messages = row["messages"]
                user = " ".join(x["content"] for x in messages if x["role"] == "user")
                entry = (meta.get("source_id") or meta.get("scenario_id") or "prior", norm(user))
                all_prior.append(entry)
                targets = set()
                pid = meta.get("target_provision_id") or meta.get("corrected_provision_id")
                if pid:
                    targets.add(pid)
                answer = json.loads(messages[-1]["content"])
                targets.update(answer.get("possible_provision_ids", []))
                for target in targets:
                    found[target].append(entry)
    for sealed_path in prior_sealed:
        for line in sealed_path.open(encoding="utf-8"):
            row = json.loads(line)
            pid = row["metadata"].get("target_provision_id")
            if pid and row["metadata"].get("kind") == "triage":
                entry = (row["id"], norm(row["messages"][1]["content"]))
                found[pid].append(entry)
                all_prior.append(entry)
    return found, all_prior


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--prior-sealed", type=Path, action="append")
    args = parser.parse_args()
    source = args.source.resolve()
    base = args.base.resolve()
    prior_sealed = [DEFAULT_PRIOR_SEALED, *(args.prior_sealed or [])]
    out = source.with_name(source.stem + "_checked")
    raw = json.loads(source.read_text(encoding="utf-8"))
    cases = raw["cases"]
    if "case_targets" in raw:
        expected = raw["case_targets"]
    else:
        expected = {pid: {"train_provision_match": n,
                          "train_insufficient_information": 1,
                          "sealed_test_provision_match": 1}
                    for pid, n in raw["positive_train_targets"].items()}
    expected_total = sum(sum(kinds.values()) for kinds in expected.values())
    if len(cases) != expected_total or len({x["id"] for x in cases}) != expected_total:
        raise ValueError("Case count or IDs do not match declared per-section targets")
    original, all_prior = existing_inputs(base, prior_sealed)
    new_inputs = defaultdict(list)
    output = {"train": [], "dev": [], "sealed_test": []}
    near = []
    by_section = defaultdict(Counter)
    new_nonsealed = []
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        for case in cases:
            pid = case["provision_id"]
            law = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            if (law is None or law["legal_status"] != "in_force"
                    or law["provision_kind"] != "offence" or not law["verified_text"]):
                raise ValueError(f"Non-eligible provision: {pid}")
            if case["split"] not in output:
                raise ValueError(f"Wrong split: {case['id']}")
            key = norm(case["input"])
            if len(case["input"].split()) < 18 or any(s in case["input"] for s in ("@", "http://")):
                raise ValueError(f"Short or identifying case: {case['id']}")
            for prior_id, prior in original[pid] + new_inputs[pid]:
                if key == prior:
                    raise ValueError(f"Duplicate: {case['id']} / {prior_id}")
                ratio = difflib.SequenceMatcher(None, key, prior).ratio()
                if ratio >= .75:
                    near.append({"id": case["id"], "other_id": prior_id,
                                 "similarity": round(ratio, 3)})
            new_inputs[pid].append((case["id"], key))
            if case["split"] != "sealed_test":
                new_nonsealed.append((case["id"], key))
            if case["outcome"] == "provision_match":
                target = {"outcome": "provision_match", "possible_provision_ids": [pid],
                          "uncertain_sections": []}
            elif case["outcome"] == "insufficient_information" and case["split"] != "sealed_test":
                target = {"outcome": "insufficient_information", "possible_provision_ids": [],
                          "uncertain_sections": [{"provision_id": pid,
                                                  "missing_facts": case["missing_facts"]}]}
            else:
                raise ValueError(f"Invalid outcome or sealed uncertainty: {case['id']}")
            row = {"id": case["id"], "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": case["input"]},
                {"role": "assistant", "content": json.dumps(target, separators=(",", ":"))}],
                "metadata": {"kind": "triage", "split": case["split"],
                             "target_provision_id": pid, "source_id": law["source_id"],
                             "source_pdf_page": law["source_pdf_page"],
                             "verified_text_sha256": hashlib.sha256(
                                 law["verified_text"].encode()).hexdigest(),
                             "review_status": raw["review_status"],
                             "review_note": case["review_note"],
                             "incident_family": case["id"]}}
            output[case["split"]].append(row)
            by_section[pid][f"{case['split']}_{case['outcome']}"] += 1
    if near:
        raise ValueError(f"High lexical similarity requiring rewrite: {near[:12]}")
    all_train = all_prior + new_nonsealed
    choices = [entry[1] for entry in all_train]
    sealed_similarity = []
    for row in output["sealed_test"]:
        key = norm(row["messages"][1]["content"])
        hit = process.extractOne(key, choices, scorer=fuzz.ratio)
        score = round(hit[1] / 100, 3)
        sealed_similarity.append({"sealed_id": row["id"],
                                  "nearest_train_or_prior_id": all_train[hit[2]][0],
                                  "similarity": score})
        if score >= .75:
            raise ValueError(f"Sealed/train near duplicate: {sealed_similarity[-1]}")
    for pid, targets in expected.items():
        x = by_section[pid]
        if any(x[kind] != n for kind, n in targets.items()):
            raise ValueError(f"Incomplete target section: {pid} {x}")
        if any(n != targets.get(kind, 0) for kind, n in x.items()):
            raise ValueError(f"Unexpected case type for {pid}: {x}")
    out.mkdir(parents=True, exist_ok=True)
    for split, rows in output.items():
        with (out / f"{split}.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    manifest = {"status": "source_checked_research_not_recommendation_approval",
                "counts": {k: len(v) for k, v in output.items()},
                "positive_train": sum(x["train_provision_match"] for x in by_section.values()),
                "missing_fact_train": sum(x["train_insufficient_information"] for x in by_section.values()),
                "positive_dev": sum(x["dev_provision_match"] for x in by_section.values()),
                "missing_fact_dev": sum(x["dev_insufficient_information"] for x in by_section.values()),
                "positive_sealed": sum(x["sealed_test_provision_match"] for x in by_section.values()),
                "sections": list(expected), "near_lexical_duplicates": near,
                "global_sealed_train_similarity": sealed_similarity,
                "limits": ["AI-only legal review, no independent lawyer labels.",
                           "Count coverage does not prove case-law applicability or model accuracy.",
                           "Sealed cases must never enter training or prompt tuning."],
                "files_sha256": {"source": sha(source),
                                 "train": sha(out / "train.jsonl"),
                                 "dev": sha(out / "dev.jsonl"),
                                 "sealed_test": sha(out / "sealed_test.jsonl")}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
