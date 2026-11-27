"""Validate common-section contrasts as section-conditioned train-only cases."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
SOURCE = ROOT / "data_drafts" / "part2_confusers_v1.jsonl"
OUT = ROOT / "exports" / "part2_confusers_v1_research"
PRIOR = ROOT / "exports" / "part2_candidate_checks_v3_research"
HELD = ROOT / "exports" / "complaint_only_v6_research_candidate"
SYSTEM = ("Assess only the named BNS or IT Act candidate section against the reported facts. "
          "Return JSON with label, missing_facts, and reason. Unsupported for one candidate does not "
          "mean no other law applies. Do not invent missing facts.")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise ValueError("Output exists; refuse to overwrite confusers")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != 11 or len({r["id"] for r in rows}) != 11:
        raise ValueError("Expected 11 distinct contrast cases")
    with sqlite3.connect(DB) as conn:
        laws = {r[0]: r[1:] for r in conn.execute("""SELECT provision_id,legal_status,
            provision_kind,verified_text,source_id,source_pdf_page FROM provision""")}
    prior_texts = []
    for line in (PRIOR / "train_sft.jsonl").open(encoding="utf-8"):
        prior_texts.append(json.loads(json.loads(line)["messages"][1]["content"])["complaint"])
    held_texts = [json.loads(line)["messages"][-2]["content"] for line in
                  (HELD / "dev_sft.jsonl").open(encoding="utf-8")]
    near = []
    data, mapping = [], []
    for row in rows:
        pid = row["target"]
        if len(row["complaint"].split()) < 32 or not row["reason"] or len(row["other_possible_ids"]) != 1:
            raise ValueError(f"Incomplete contrast: {row['id']}")
        for provision_id in (pid, *row["other_possible_ids"]):
            status, kind, verified, _, _ = laws[provision_id]
            if status != "in_force" or kind != "offence" or not verified:
                raise ValueError(f"Invalid contrast provision: {row['id']}/{provision_id}")
        for source, texts in (("prior", prior_texts), ("dev", held_texts)):
            hit = process.extractOne(row["complaint"], texts, scorer=fuzz.ratio)
            if hit and hit[1] >= 75:
                near.append({"id": row["id"], "source": source, "similarity": round(hit[1]/100, 3)})
        law = laws[pid]
        data.append({"messages": [{"role": "system", "content": SYSTEM},
                                  {"role": "user", "content": json.dumps(
                                      {"complaint": row["complaint"], "candidate_provision_id": pid},
                                      ensure_ascii=False, separators=(",", ":"))},
                                  {"role": "assistant", "content": json.dumps(
                                      {"label": "unsupported", "missing_facts": [], "reason": row["reason"]},
                                      ensure_ascii=False, separators=(",", ":"))}]})
        mapping.append({"source_id": row["id"], "split": "train", "kind": "candidate_check",
                        "target_provision_id": pid, "label": "unsupported",
                        "other_possible_ids": row["other_possible_ids"],
                        "review_status": "AI_authored_research_candidate",
                        "source_id_of_law": law[3], "source_pdf_page": law[4],
                        "verified_text_sha256": hashlib.sha256(law[2].encode()).hexdigest()})
    if near:
        raise ValueError(f"Lexical overlap requires rewrite: {near}")
    OUT.mkdir(parents=True)
    for name, contents in (("train_sft.jsonl", data), ("train_sft_map.jsonl", mapping)):
        (OUT / name).write_text("".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n"
                                        for x in contents), encoding="utf-8")
    report = {"status": "AI_authored_research_candidate", "train_only_contrasts": len(rows),
              "source_sha256": sha(SOURCE), "lexical_overlap_at_0_75": len(near),
              "files_sha256": {name: sha(OUT / name) for name in ("train_sft.jsonl", "train_sft_map.jsonl")},
              "limit": "An alternative section is a research possibility, not a confirmed legal finding."}
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
