"""Bulk-screen Nyaya BNSS/BSA Q&A against the MHA Gazette PDFs.

Adds matching, single-Act grounded Q&A to v18 as a separate Colab experiment.
All remaining Nyaya rows receive a reason in the decision ledger.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "exports" / "mixed-source-v18-nyaya-screened-experiment"
NYAYA = ROOT / "exports" / "mixed-source-v15-gsms-aux-research"
OUT = ROOT / "exports" / "mixed-source-v19-nyaya-bnss-bsa-experiment"
AUDIT = ROOT / "review_automation" / "nyaya_v3_remaining_fast_screen"
FILES = ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")
ACTS = {
    "bnss_2023": ("Bharatiya Nagarik Suraksha Sanhita, 2023",
                  "भारतीय नागरिक सुरक्षा संहिता", "bnss_2023_mha_gazette.pdf", 531,
                  "5e60e2afe30d0fe7eca4f8126301146b76c86a444e690581f81eb564843517fe"),
    "bsa_2023": ("Bharatiya Sakshya Adhiniyam, 2023",
                 "भारतीय साक्ष्य अधिनियम", "bsa_2023_mha_gazette.pdf", 170,
                 "13e2b6eb66add222c7262ccaa0b08d58e48ca22cdf0953f6541123ef039de239"),
}
OTHER_ACT_MARKERS = (
    "Bharatiya Nyaya Sanhita", "Information Technology Act", "Constitution of India",
    "Motor Vehicles Act", "Hindu Marriage Act", "Special Marriage Act",
    "Negotiable Instruments Act", "Consumer Protection Act", "Code on Wages",
    "Indian Penal Code", "Bharatiya Sakshya Adhiniyam",
    "Bharatiya Nagarik Suraksha Sanhita",
)
HEAD = re.compile(r"^Section\s+(\d+[A-Za-z]?)\s+of\s+the\s+(.+?)\s+[—–�-]\s*", re.M)
CITE = re.compile(r"(?:Section|धारा)\s*(\d+[A-Za-z]?)", re.I)
SECTION = re.compile(r"(?m)^(\d{1,3})\.\s+(?=\(|[A-Z])")
SYSTEM = ("You provide Indian legal information from the supplied statute passages. "
          "Cite only supplied provisions. If facts are missing, explain the uncertainty. "
          "Do not promise a legal outcome.")
REJECTED_SAMPLE_IDS = {
    "raft_gen_001999_6064a52b_03_fd2b3c8f_01",
    "raft_gen_002029_1ac48be3_02_06d1b427_01",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def official_sections(path: Path, maximum: int) -> dict[str, str]:
    text = "\n".join(page.get_text() for page in fitz.open(path))
    markers = []
    expected = 1
    for match in SECTION.finditer(text):
        if int(match.group(1)) == expected:
            markers.append(match)
            expected += 1
    if expected != maximum + 1:
        raise ValueError(f"Official PDF section sequence incomplete: {path}: {expected}")
    return {str(index + 1): text[match.end():markers[index + 1].start()
                                 if index + 1 < len(markers) else len(text)]
            for index, match in enumerate(markers)}


def prompt_blocks(prompt: str) -> dict[tuple[str, str], str]:
    matches = list(HEAD.finditer(prompt))
    result = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(prompt)
        block = prompt[match.start():end].split("Using ONLY", 1)[0].strip()
        result[(match.group(2).strip(), match.group(1))] = block
    return result


def matched_official_prefix(block: str, official: str) -> bool:
    # Publisher block: heading line, then the law text. Gazette extraction has
    # page furniture after some short sections, so compare the leading text.
    body = block.split("\n", 1)[-1]
    source = words(body)[:60]
    target = words(official)[:len(source)]
    if len(source) < 8:
        return False
    return difflib.SequenceMatcher(None, source, target, autojunk=False).ratio() >= 0.95


def main() -> None:
    for source in (BASE, NYAYA):
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        for filename in FILES:
            if sha(source / filename) != manifest["files_sha256"][filename]:
                raise ValueError(f"Pinned input changed: {source.name}/{filename}")
    statutes = {}
    for act, (_, _, filename, maximum, digest) in ACTS.items():
        path = ROOT / "sources" / filename
        if sha(path) != digest:
            raise ValueError(f"Official Gazette PDF changed: {path}")
        statutes[act] = official_sections(path, maximum)
    already_selected = set()
    with (BASE / "train_sft_map.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            meta = json.loads(line)
            if meta.get("source") == "NyayaLabs98/nyaya-train-v3":
                already_selected.add(meta["source_id"])
    OUT.mkdir(parents=True, exist_ok=True)
    AUDIT.mkdir(parents=True, exist_ok=True)
    selected = []
    counts = Counter()
    by_act = Counter()
    with (NYAYA / "train_sft.jsonl").open(encoding="utf-8") as data, \
         (NYAYA / "train_sft_map.jsonl").open(encoding="utf-8") as maps, \
         (AUDIT / "decisions.jsonl").open("w", encoding="utf-8", newline="\n") as ledger:
        for record_line, map_line in zip(data, maps, strict=True):
            meta = json.loads(map_line)
            if meta.get("source") != "NyayaLabs98/nyaya-train-v3":
                continue
            act = meta.get("source_act")
            decision = None
            if meta["source_id"] in already_selected:
                decision = "already_in_v18_training"
            elif act not in ACTS:
                decision = "outside_BNSS_BSA_auxiliary_expansion"
            elif meta["source_id"] in REJECTED_SAMPLE_IDS:
                decision = "sampled_answer_semantic_error"
            else:
                name, hindi, _, _, _ = ACTS[act]
                record = json.loads(record_line)
                prompt = record["messages"][1]["content"]
                answer = record["messages"][2]["content"]
                question = prompt.rsplit("Question:", 1)[-1].strip()
                refs = meta.get("source_sections") or []
                citations = set(CITE.findall(answer))
                blocks = prompt_blocks(prompt)
                act_numbers = {number for (block_act, number) in blocks if block_act == name}
                if not refs or not all(ref.startswith(act + ":") for ref in refs):
                    decision = "missing_or_mixed_primary_reference"
                elif not citations or not any(x.casefold() in answer.casefold()
                                              for x in (name, hindi)):
                    decision = "no_target_act_citation"
                elif any(marker.casefold() in answer.casefold() for marker in OTHER_ACT_MARKERS
                         if marker not in name):
                    decision = "answer_uses_other_act"
                elif citations - act_numbers:
                    decision = "answer_cites_section_absent_from_supplied_act"
                else:
                    numbers = sorted(citations | {ref.split(":", 1)[1] for ref in refs},
                                     key=lambda x: (int(re.match(r"\d+", x).group()), x))
                    chosen = []
                    for number in numbers:
                        block = blocks.get((name, number))
                        official = statutes[act].get(number)
                        if not block or not official or not matched_official_prefix(block, official):
                            decision = "publisher_passage_does_not_match_MHA_gazette"
                            break
                        chosen.append(block)
                    if decision is None:
                        new_prompt = ("Relevant provisions (the only sections you may cite):\n\n"
                                      + "\n\n".join(chosen) + "\n\nQuestion: " + question)
                        if len(new_prompt) > 12000 or len(answer) > 6000:
                            decision = "too_long_for_colab_plan"
                        else:
                            decision = "selected_auxiliary_training"
                            selected.append(({
                                "messages": [{"role": "system", "content": SYSTEM},
                                             {"role": "user", "content": new_prompt},
                                             {"role": "assistant", "content": answer}]},
                                {**meta, "task_family": "grounded_legal_qa",
                                 "review_status": "sampled_and_MHA_prefix_screened_auxiliary_qa",
                                 "context_trimmed_to_cited_provisions": True,
                                 "source_split": "publisher_train", "selected_sections": numbers}))
                            by_act[act] += 1
            counts[decision] += 1
            ledger.write(json.dumps({"source_id": meta["source_id"],
                                     "source_row": meta["source_row"],
                                     "source_act": act, "decision": decision},
                                    ensure_ascii=False) + "\n")
    if sum(counts.values()) != 5259:
        raise ValueError(f"Unexpected publisher train count: {sum(counts.values())}")
    with (OUT / "train_sft.jsonl").open("w", encoding="utf-8", newline="\n") as train, \
         (OUT / "train_sft_map.jsonl").open("w", encoding="utf-8", newline="\n") as mapping:
        train.write((BASE / "train_sft.jsonl").read_text(encoding="utf-8"))
        mapping.write((BASE / "train_sft_map.jsonl").read_text(encoding="utf-8"))
        for record, meta in selected:
            train.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            mapping.write(json.dumps(meta, ensure_ascii=False, separators=(",", ":")) + "\n")
    for filename in ("dev_sft.jsonl", "dev_sft_map.jsonl"):
        (OUT / filename).write_bytes((BASE / filename).read_bytes())
    manifest = {
        "status": "trainer_format_auxiliary_experiment_requires_model_evaluation",
        "counts": {"train": 6932 + len(selected), "dev": 60,
                   "nyaya_from_v18": len(already_selected), "nyaya_added_bnss_bsa": len(selected),
                   "nyaya_total_train": len(already_selected) + len(selected),
                   "nyaya_publisher_train_held": 5259 - len(already_selected) - len(selected),
                   "nyaya_publisher_dev_held": 280},
        "added_by_act": dict(by_act), "decisions": dict(sorted(counts.items())),
        "limits": ["BNSS/BSA passages passed a leading-text check against the MHA Gazette PDFs; full legal answer correctness is not certified.",
                   "These are procedural/evidence Q&A, not complaint-to-BNS/IT labels.",
                   "Compare with complaint-only, v17 and v18 on independent complaint cases before selecting a model.",
                   "Publisher development and test rows are excluded."],
        "input_sha256": {"v18_manifest": sha(BASE / "manifest.json"),
                         "nyaya_manifest": sha(NYAYA / "manifest.json"),
                         "mha_bnss_pdf": sha(ROOT / "sources" / ACTS["bnss_2023"][2]),
                         "mha_bsa_pdf": sha(ROOT / "sources" / ACTS["bsa_2023"][2])},
        "files_sha256": {filename: sha(OUT / filename) for filename in FILES},
        "audit_sha256": sha(AUDIT / "decisions.jsonl"),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8")
    print(json.dumps({"counts": manifest["counts"], "added_by_act": manifest["added_by_act"],
                      "decisions": manifest["decisions"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
