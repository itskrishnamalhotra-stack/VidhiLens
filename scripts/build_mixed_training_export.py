"""Build a transparent, trainer-format export from the scoped pilot and Nyaya v3.

This does not independently approve the external legal answers. It preserves their
grounding context and keeps task/source labels in a sidecar for later evaluation.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "exports" / "scoped-pilot-20260917T204748Z"
SOURCE = ROOT / "external_candidates" / "additional_20260917" / "nyaya_v3_train.jsonl"
OUTPUT = ROOT / "exports" / "mixed-source-v1"
MANIFEST = ROOT / "additional_candidates_manifest.json"
DB = ROOT / "db" / "master_dataset.sqlite"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def lines(path: Path):
    with path.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream, 1):
            yield index, json.loads(line)


def norm(value: str) -> str:
    return " ".join(value.casefold().split())


def main() -> None:
    source_spec = next(x for x in json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
                       if x["key"] == "nyaya_v3_train")
    if source_spec["license"] != "apache-2.0" or sha(SOURCE) != source_spec["sha256"]:
        raise ValueError("The pinned licensed Nyaya source changed")
    pilot_manifest = json.loads((PILOT / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in pilot_manifest["files_sha256"].items():
        if sha(PILOT / name) != digest:
            raise ValueError(f"Pilot file changed: {name}")

    conn = sqlite3.connect(DB)
    held_local = {norm(row[0]) for row in conn.execute(
        "SELECT complaint_text FROM scenario WHERE split IN ('dev','test')")}
    conn.close()
    held_source = set()
    for name in ("nyaya_v3_val.jsonl", "nyaya_v3_test.jsonl"):
        for _, row in lines(SOURCE.with_name(name)):
            held_source.add(norm(row["metadata"]["rag"]["question"]))

    existing_inputs = set()
    pilot_rows = []
    pilot_maps = []
    for (_, row), (_, mapping) in zip(lines(PILOT / "train_sft.jsonl"),
                                      lines(PILOT / "train_sft_map.jsonl"), strict=True):
        if not row.get("messages") or row["messages"][-1]["role"] != "assistant":
            raise ValueError("Invalid pilot chat row")
        pilot_rows.append(row)
        pilot_maps.append({**mapping, "task_family": mapping["kind"],
                           "source": "local_reviewed_pilot", "review_status": mapping["review_tier"]})
        if mapping["kind"] == "triage":
            existing_inputs.add(norm(row["messages"][1]["content"]))

    OUTPUT.mkdir(parents=True, exist_ok=True)
    counters = Counter()
    external_questions = set()
    external_tasks = Counter()
    external_acts = Counter()
    with (OUTPUT / "train_sft.jsonl").open("w", encoding="utf-8", newline="\n") as train, \
         (OUTPUT / "train_sft_map.jsonl").open("w", encoding="utf-8", newline="\n") as mapping_file:
        def write(row: dict, mapping: dict) -> None:
            train.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            mapping_file.write(json.dumps(mapping, ensure_ascii=False, separators=(",", ":")) + "\n")

        for row, mapping in zip(pilot_rows, pilot_maps, strict=True):
            write(row, mapping)
            counters["local_pilot"] += 1

        for line_no, row in lines(SOURCE):
            meta = row.get("metadata", {})
            messages = row.get("messages", [])
            question = norm(meta.get("rag", {}).get("question", ""))
            if (not question or len(messages) != 3 or
                    [m.get("role") for m in messages] != ["system", "user", "assistant"] or
                    any(not isinstance(m.get("content"), str) or not m["content"].strip()
                        for m in messages)):
                raise ValueError(f"Malformed Nyaya source row {line_no}")
            if question in external_questions:
                raise ValueError(f"Repeated Nyaya train question {line_no}")
            external_questions.add(question)
            if question in held_local or question in held_source:
                counters["heldout_overlap_excluded"] += 1
                continue
            if question in existing_inputs:
                counters["local_train_overlap_excluded"] += 1
                continue
            write({"messages": messages}, {
                "task_family": "grounded_legal_qa",
                "source": "NyayaLabs98/nyaya-train-v3",
                "source_revision": source_spec["revision"],
                "source_row": line_no,
                "source_id": row["id"],
                "license": source_spec["license"],
                "review_status": "publisher_gated_not_independently_legal_reviewed",
                "source_act": meta.get("source_act"),
                "source_sections": meta.get("source_sections", []),
                "language": meta.get("language"),
                "task_type": meta.get("task_type"),
            })
            counters["external_grounded_qa"] += 1
            external_tasks[meta.get("task_type")] += 1
            external_acts[meta.get("source_act")] += 1

    val_spec = next(x for x in json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
                    if x["key"] == "nyaya_v3_val")
    val_path = SOURCE.with_name("nyaya_v3_val.jsonl")
    if val_spec["license"] != "apache-2.0" or sha(val_path) != val_spec["sha256"]:
        raise ValueError("The pinned Nyaya validation source changed")
    dev_counts = Counter()
    with (OUTPUT / "dev_sft.jsonl").open("w", encoding="utf-8", newline="\n") as dev, \
         (OUTPUT / "dev_sft_map.jsonl").open("w", encoding="utf-8", newline="\n") as dev_map:
        for (_, row), (_, mapping) in zip(lines(PILOT / "dev_sft.jsonl"),
                                          lines(PILOT / "dev_sft_map.jsonl"), strict=True):
            dev.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            dev_map.write(json.dumps({**mapping, "task_family": mapping["kind"],
                                      "source": "local_reviewed_pilot"}, ensure_ascii=False,
                                     separators=(",", ":")) + "\n")
            dev_counts["local_pilot"] += 1
        for line_no, row in lines(val_path):
            question = norm(row["metadata"]["rag"]["question"])
            if question in existing_inputs or question in external_questions or question in held_local:
                raise ValueError(f"Validation overlaps local or external train/holdout: {line_no}")
            dev.write(json.dumps({"messages": row["messages"]}, ensure_ascii=False,
                                 separators=(",", ":")) + "\n")
            dev_map.write(json.dumps({
                "task_family": "grounded_legal_qa",
                "source": "NyayaLabs98/nyaya-train-v3",
                "source_revision": val_spec["revision"],
                "source_row": line_no,
                "source_id": row["id"],
                "license": "apache-2.0",
                "review_status": "publisher_gated_not_independently_legal_reviewed",
                "source_act": row["metadata"].get("source_act"),
                "source_sections": row["metadata"].get("source_sections", []),
                "language": row["metadata"].get("language"),
                "task_type": row["metadata"].get("task_type"),
            }, ensure_ascii=False, separators=(",", ":")) + "\n")
            dev_counts["external_grounded_qa"] += 1
    output_manifest = {
        "purpose": "Trainer-format candidate for two explicitly different tasks; evaluation required before model use",
        "records_by_source": dict(counters),
        "train_records": counters["local_pilot"] + counters["external_grounded_qa"],
        "dev_records": sum(dev_counts.values()),
        "dev_records_by_source": dict(dev_counts),
        "external_task_types": dict(external_tasks),
        "external_source_acts": {str(k): v for k, v in external_acts.items()},
        "external_license_and_attribution": {
            "title": "Nyaya-Train-v3",
            "publisher": "NyayaLabs98",
            "url": "https://huggingface.co/datasets/NyayaLabs98/nyaya-train-v3",
            "license": "Apache-2.0",
            "revision": source_spec["revision"],
            "source_sha256": source_spec["sha256"],
        },
        "limits": [
            "External answers are publisher-gated synthetic legal QA, not independently checked complaint triage labels.",
            "The external prompts contain supplied legal context; deployed QA needs matching retrieval and source checks.",
            "The local pilot covers only 19 recommendable BNS/IT provisions and contains silver variants.",
            "Neither this row count nor trainer-compatible JSONL proves model accuracy or full-Act coverage.",
        ],
        "files_sha256": {name: sha(OUTPUT / name) for name in
                         ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")},
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(output_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output_manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
