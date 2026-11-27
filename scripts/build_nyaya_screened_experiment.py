"""Add screened BNS/IT Nyaya Q&A to a separate trainer-format experiment.

This is an auxiliary grounded-Q&A experiment. It does not turn Q&A into
complaint-to-section labels or certify every publisher answer.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "exports" / "mixed-source-v17-complaint-gsms-research"
NYAYA = ROOT / "exports" / "mixed-source-v15-gsms-aux-research"
RAW = ROOT / "external_candidates" / "additional_20260917"
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "exports" / "mixed-source-v18-nyaya-screened-experiment"
AUDIT = ROOT / "review_automation" / "nyaya_v3_screened_experiment"
FILES = ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")
ACTS = {"bns_2023": ("BNS_", "Bharatiya Nyaya Sanhita, 2023"),
        "it_act_2000": ("ITA_", "Information Technology Act, 2000")}
# Semantic errors found in the reproducible sample; source line numbers are 1-based.
REJECTED_SOURCE_ROWS = {"bns_2023": {793, 946}, "it_act_2000": {}}
OTHER_ACT_MARKERS = (
    "Bharatiya Nagarik Suraksha", "Bharatiya Sakshya", "Constitution of India",
    "Motor Vehicles Act", "Hindu Marriage Act", "Special Marriage Act",
    "Negotiable Instruments Act", "Consumer Protection Act", "Code on Wages",
    "Indian Penal Code", "Criminal Procedure Code", "Protection of Women from Domestic Violence",
)
SYSTEM = ("You provide Indian legal information from the verified provisions supplied in "
          "the user's message. Cite only those provisions. If facts are missing, explain "
          "what is uncertain. Do not promise a legal outcome.")
CITE = re.compile(r"(?:Section|धारा)\s*(\d+[A-Za-z]?)", re.IGNORECASE)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def source_match(old: str, current: str) -> float:
    # The official PDF includes section number/title before the body. Compare
    # bodies, so amended monetary limits cannot hide behind matching headings.
    body = re.sub(r"^[0-9A-Za-z]+\.\s+.*?\.\s*[—–�-]\s*", "", current,
                  count=1, flags=re.S)
    return difflib.SequenceMatcher(None, tokens(old), tokens(body),
                                   autojunk=False).ratio()


def main() -> None:
    for source in (BASE, NYAYA):
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        for name in FILES:
            if sha(source / name) != manifest["files_sha256"][name]:
                raise ValueError(f"Pinned trainer file changed: {source.name}/{name}")
    with sqlite3.connect(DB) as conn:
        law = {pid: (title, text, status) for pid, title, text, status in conn.execute(
            "SELECT provision_id,candidate_title,verified_text,legal_status FROM provision")}
    source_manifest = json.loads((ROOT / "additional_candidates_manifest.json")
                                 .read_text(encoding="utf-8"))
    source_specs = {item["key"]: item for item in source_manifest["files"]}
    publisher_law = {}
    for act, suffix in (("bns_2023", "bns"), ("it_act_2000", "it")):
        source_path = RAW / f"nyaya_statute_{suffix}.jsonl"
        if sha(source_path) != source_specs[f"nyaya_statute_{suffix}"]["sha256"]:
            raise ValueError(f"Publisher statute source changed: {source_path}")
        publisher_law[act] = {row["section"]: row["text"] for row in
                              map(json.loads, source_path
                                  .read_text(encoding="utf-8").splitlines())}
    OUT.mkdir(parents=True, exist_ok=True)
    AUDIT.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    selected = []
    with (NYAYA / "train_sft.jsonl").open(encoding="utf-8") as data, \
         (NYAYA / "train_sft_map.jsonl").open(encoding="utf-8") as maps, \
         (AUDIT / "decisions.jsonl").open("w", encoding="utf-8", newline="\n") as audit:
        for record_line, map_line in zip(data, maps, strict=True):
            meta = json.loads(map_line)
            if meta.get("source") != "NyayaLabs98/nyaya-train-v3":
                continue
            record = json.loads(record_line)
            act = meta.get("source_act")
            reason = None
            if act not in ACTS:
                reason = "outside_BNS_IT_task"
            else:
                answer = record["messages"][-1]["content"]
                question = record["messages"][1]["content"].rsplit("Question:", 1)[-1].strip()
                refs = meta.get("source_sections") or []
                prefix, act_name = ACTS[act]
                target_names = ((act_name, "भारतीय न्याय संहिता") if act == "bns_2023"
                                else (act_name, "सूचना प्रौद्योगिकी अधिनियम"))
                context_numbers = set(re.findall(
                    r"Section\s+(\d+[A-Za-z]?)\s+of\s+the\s+" + re.escape(act_name),
                    record["messages"][1]["content"], re.IGNORECASE))
                citations = set(CITE.findall(answer))
                if meta["source_row"] in REJECTED_SOURCE_ROWS[act]:
                    reason = "sampled_answer_semantic_error"
                elif not refs or not all(ref.startswith(act + ":") for ref in refs):
                    reason = "missing_or_mixed_primary_reference"
                elif not citations or not any(name.casefold() in answer.casefold()
                                              for name in target_names):
                    reason = "no_target_act_citation"
                elif any(marker.casefold() in answer.casefold() for marker in OTHER_ACT_MARKERS):
                    reason = "answer_uses_unverified_other_act"
                elif act == "bns_2023" and "Information Technology Act" in answer:
                    reason = "answer_uses_unverified_other_act"
                elif act == "it_act_2000" and "Bharatiya Nyaya Sanhita" in answer:
                    reason = "answer_uses_unverified_other_act"
                elif citations - context_numbers:
                    reason = "answer_cites_section_absent_from_original_context"
                else:
                    numbers = sorted(citations | {ref.split(":", 1)[1] for ref in refs},
                                     key=lambda x: (int(re.match(r"\d+", x).group()), x))
                    provisions = []
                    for number in numbers:
                        item = law.get(prefix + number)
                        old = publisher_law[act].get(number)
                        if not item or not old or item[2] != "in_force" or not item[1]:
                            reason = "law_not_confirmed_in_force"
                            break
                        similarity = source_match(old, item[1])
                        if similarity < (0.9 if act == "bns_2023" else 0.995):
                            reason = "publisher_law_differs_from_current_official_text"
                            break
                        provisions.append(f"Section {number} of the {act_name} — {item[0]}\n"
                                          + item[1].replace("�", " ").strip())
                    if reason is None:
                        prompt = ("Relevant verified provisions (the only sections you may cite):\n\n"
                                  + "\n\n".join(provisions) + "\n\nQuestion: " + question)
                        if len(prompt) > 12000:
                            reason = "rewritten_context_too_long_for_colab_plan"
                        elif len(answer) > 6000:
                            reason = "answer_too_long_for_colab_plan"
                        else:
                            selected.append(({
                                "messages": [{"role": "system", "content": SYSTEM},
                                             {"role": "user", "content": prompt},
                                             {"role": "assistant", "content": answer}]},
                                {**meta, "review_status": "sampled_and_mechanically_screened_auxiliary_qa",
                                 "context_replaced_with_verified_current_statute": True,
                                 "source_split": "publisher_train", "selected_sections": numbers,
                                 "task_family": "grounded_legal_qa"}))
            decision = reason or "selected_auxiliary_training"
            counts[decision] += 1
            audit.write(json.dumps({"source_id": meta["source_id"],
                                    "source_row": meta["source_row"],
                                    "source_act": act, "decision": decision},
                                   ensure_ascii=False) + "\n")
    if sum(counts.values()) != 5259:
        raise ValueError(f"Unexpected Nyaya train count: {sum(counts.values())}")
    with (OUT / "train_sft.jsonl").open("w", encoding="utf-8", newline="\n") as train, \
         (OUT / "train_sft_map.jsonl").open("w", encoding="utf-8", newline="\n") as mapping:
        train.write((BASE / "train_sft.jsonl").read_text(encoding="utf-8"))
        mapping.write((BASE / "train_sft_map.jsonl").read_text(encoding="utf-8"))
        for record, meta in selected:
            train.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            mapping.write(json.dumps(meta, ensure_ascii=False, separators=(",", ":")) + "\n")
    for name in ("dev_sft.jsonl", "dev_sft_map.jsonl"):
        (OUT / name).write_bytes((BASE / name).read_bytes())
    manifest = {
        "status": "trainer_format_auxiliary_experiment_requires_model_evaluation",
        "counts": {"train": 5945 + len(selected), "dev": 60,
                   "nyaya_added_train": len(selected),
                   "nyaya_held_train": 5259 - len(selected),
                   "nyaya_publisher_dev_remains_held": 280},
        "decisions": dict(sorted(counts.items())),
        "description": "v17 complaint/GSMS baseline plus screened Nyaya BNS/IT grounded Q&A with current verified statutory context.",
        "limits": ["Sample review and mechanical screens do not certify every legal answer.",
                   "Auxiliary legal Q&A is not complaint-to-section supervision.",
                   "Use only if independent complaint evaluation improves versus v17.",
                   "Publisher dev and test rows are not included in training."],
        "input_sha256": {"base_manifest": sha(BASE / "manifest.json"),
                         "nyaya_manifest": sha(NYAYA / "manifest.json"),
                         "publisher_bns_statute": sha(RAW / "nyaya_statute_bns.jsonl"),
                         "publisher_it_statute": sha(RAW / "nyaya_statute_it.jsonl"),
                         "master_database": sha(DB)},
        "files_sha256": {name: sha(OUT / name) for name in FILES},
        "audit_sha256": sha(AUDIT / "decisions.jsonl"),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8")
    print(json.dumps(manifest["counts"] | {"decisions": manifest["decisions"]},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
