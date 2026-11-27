"""Read-only profile of downloaded LeSICiN court facts for BNS transfer."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "external_candidates" / "lesicin_6053791"
DB = ROOT / "db" / "master_dataset.sqlite"
REPORT = ROOT / "lesicin_screening_report.json"
LABEL = re.compile(r"^Section (\d+[A-Z]?(?:\([0-9a-z]+\))?) in The Indian Penal Code$")
SECTION_MENTION = re.compile(r"\b(?:section|sec\.?|u/s)\s*(\d+[A-Z]?)\b", re.I)
PHONE_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|(?<!\d)(?:\+91[- ]?)?[6-9]\d{9}(?!\d)")


def percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def base(label: str) -> str:
    return label.split("(", 1)[0]


def main() -> None:
    if not all((DATA / name).is_file() for name in ("train.jsonl", "dev.jsonl", "test.jsonl", "secs.jsonl", "label_vocab.json")):
        raise SystemExit("LeSICiN text data is not fully downloaded")
    with sqlite3.connect(DB) as conn:
        crosswalk = defaultdict(set)
        changed = set()
        for ipc, bns, marker in conn.execute("SELECT ipc_section,bns_provision_id,change_marker FROM ipc_bns_crosswalk_candidate"):
            crosswalk[ipc].add(bns)
            if marker:
                changed.add(ipc)
        pilot = {r[0] for r in conn.execute("SELECT provision_id FROM recommendable_provision")}

    result = {"source": "https://zenodo.org/records/6053791",
              "data_role": "quarantined_research_only_no_training_approval",
              "splits": {}, "all_labels": Counter(), "duplicate_ids_across_splits": 0,
              "duplicate_texts_across_splits": 0, "unparsed_labels": Counter()}
    ids_seen: dict[str, str] = {}
    text_seen: dict[bytes, str] = {}
    all_labels = Counter()
    for split in ("train", "dev", "test"):
        count = total_words = mentioned = target_mentioned = pii = duplicate_ids = duplicate_texts = 0
        cross_split_ids = cross_split_texts = 0
        promising_pilot_candidates = 0
        word_counts = []
        label_counts = []
        label_freq = Counter()
        mapped_any = mapped_unique = mapped_pilot = changed_any = 0
        with (DATA / (split + ".jsonl")).open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                row = json.loads(line)
                if set(row) != {"id", "text", "labels"}:
                    raise ValueError(f"Unexpected schema: {split}:{line_number}")
                count += 1
                rid = str(row["id"])
                duplicate_ids += rid in ids_seen
                cross_split_ids += rid in ids_seen and ids_seen[rid] != split
                ids_seen.setdefault(rid, split)
                sentences = row["text"]
                if not isinstance(sentences, list) or not all(isinstance(s, str) for s in sentences):
                    raise ValueError(f"Unexpected text shape: {split}:{line_number}")
                text = " ".join(sentences)
                token_count = len(text.split())
                word_counts.append(token_count)
                total_words += token_count
                hash_text = hashlib.sha256(" ".join(text.casefold().split()).encode("utf-8")).digest()
                duplicate_texts += hash_text in text_seen
                cross_split_texts += hash_text in text_seen and text_seen[hash_text] != split
                text_seen.setdefault(hash_text, split)
                mentioned_sections = set(SECTION_MENTION.findall(text))
                mentioned += bool(mentioned_sections)
                has_pii = bool(PHONE_EMAIL.search(text))
                pii += has_pii
                labels = row["labels"]
                if not isinstance(labels, list):
                    raise ValueError(f"Unexpected label shape: {split}:{line_number}")
                label_counts.append(len(labels))
                ipc_labels = []
                for raw in labels:
                    match = LABEL.fullmatch(raw)
                    if match:
                        ipc_labels.append(match[1])
                        label_freq[match[1]] += 1
                        all_labels[match[1]] += 1
                    else:
                        result["unparsed_labels"][str(raw)] += 1
                target_mentioned += any(base(n) in mentioned_sections for n in ipc_labels)
                mapped = [crosswalk[base(n)] for n in ipc_labels if crosswalk[base(n)]]
                mapped_any += bool(mapped)
                mapped_unique += bool(mapped) and all(len(options) == 1 for options in mapped)
                mapped_pilot += any(options & pilot for options in mapped)
                changed_any += any(base(n) in changed for n in ipc_labels)
                promising_pilot_candidates += (any(options & pilot for options in mapped)
                    and not mentioned_sections and not has_pii and 50 <= token_count <= 800)
        result["splits"][split] = {
            "rows": count, "mean_words": round(total_words / count, 1),
            "median_words": median(word_counts), "p90_words": percentile(word_counts, .9),
            "under_250_words": sum(n < 250 for n in word_counts),
            "has_explicit_section_reference_in_fact_text": mentioned,
            "has_target_ipc_section_number_in_fact_text": target_mentioned,
            "possible_phone_or_email": pii,
            "mean_ipc_labels": round(sum(label_counts) / count, 2),
            "multi_label_rows": sum(n > 1 for n in label_counts),
            "distinct_ipc_labels": len(label_freq),
            "rows_with_any_official_crosswalk_candidate": mapped_any,
            "rows_where_all_mapped_labels_have_single_candidate": mapped_unique,
            "rows_with_any_candidate_in_current_19_section_pilot": mapped_pilot,
            "rows_with_any_changed_ipc_crosswalk_marker": changed_any,
            "pilot_candidate_no_section_reference_simple_pii_or_extreme_length": promising_pilot_candidates,
            "duplicate_ids_found_so_far": duplicate_ids,
            "duplicate_texts_found_so_far": duplicate_texts,
            "duplicate_ids_from_other_split": cross_split_ids,
            "duplicate_texts_from_other_split": cross_split_texts,
        }
        result["duplicate_ids_across_splits"] += cross_split_ids
        result["duplicate_texts_across_splits"] += cross_split_texts
    result["all_labels"] = dict(all_labels.most_common())
    result["unparsed_labels"] = dict(result["unparsed_labels"])
    result["distinct_ipc_labels"] = len(all_labels)
    result["label_crosswalk"] = {
        "ipc_labels_with_no_bns_candidate": sorted(n for n in all_labels if not crosswalk[base(n)]),
        "ipc_labels_with_multiple_bns_candidates": sorted(n for n in all_labels if len(crosswalk[base(n)]) > 1),
        "ipc_labels_with_changed_marker": sorted(n for n in all_labels if base(n) in changed),
        "ipc_labels_with_candidate_in_current_19_section_pilot": sorted(n for n in all_labels if crosswalk[base(n)] & pilot),
    }
    secs = [json.loads(line) for line in (DATA / "secs.jsonl").read_text(encoding="utf-8").splitlines()]
    result["section_text_rows"] = len(secs)
    result["section_text_schema"] = sorted(secs[0]) if secs else []
    result["label_vocab_entries"] = len(json.loads((DATA / "label_vocab.json").read_text(encoding="utf-8")))
    result["decision_note"] = "IPC citations in older court judgments are not automatically correct BNS complaint labels. Crosswalk statistics are candidate counts only. Explicit section references in fact text may cause label leakage."
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("all_labels", "unparsed_labels")}, indent=2))


if __name__ == "__main__":
    main()
