"""Export reviewed train/dev examples for Colab; keep sealed test local.

No file is produced until the full dataset and law readiness gates pass.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import audit_dataset
import compile_sft_data
import report_data_readiness
from build_full_kb import DB_PATH, ROOT, sha256


def write_jsonl(path: Path, rows: list[dict]) -> str:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return sha256(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final", action="store_true", help="Retained for compatibility; full readiness is always required")
    args = parser.parse_args()
    audit_dataset.main()
    audit = json.loads((ROOT / "dataset_audit_report.json").read_text(encoding="utf-8"))
    if not audit["ready_to_export"]:
        raise SystemExit("Final dataset target or dataset audit failed; export refused")
    report_data_readiness.main()
    readiness = json.loads((ROOT / "data_readiness_report.json").read_text(encoding="utf-8"))
    if not readiness["ready_for_final_colab_training"]:
        raise SystemExit("Final law and dataset readiness gate failed; export refused")

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        allowed = {row[0] for row in conn.execute("SELECT provision_id FROM recommendable_provision")}
        rows_by_split = {"train": [], "dev": []}
        for scenario in conn.execute("SELECT * FROM scenario WHERE quality_status='accepted' AND split IN ('train','dev') ORDER BY scenario_id"):
            sid = scenario["scenario_id"]
            facts = [dict(row) for row in conn.execute("SELECT * FROM scenario_fact WHERE scenario_id=? ORDER BY fact_key", (sid,))]
            labels = [dict(row) for row in conn.execute("SELECT * FROM scenario_provision_label WHERE scenario_id=? ORDER BY provision_id", (sid,))]
            actions = [dict(row) for row in conn.execute("SELECT * FROM conversation_example WHERE scenario_id=? AND quality_status='accepted' ORDER BY turn_index", (sid,))]
            positives = [row["provision_id"] for row in labels if row["label"] == "possible"]
            if any(pid not in allowed for pid in positives):
                raise SystemExit(f"Positive label outside current allowlist: {sid}")
            rows_by_split[scenario["split"]].append({
                "scenario": dict(scenario), "facts": facts, "labels": labels,
                "conversation_examples": actions,
                "possible_provision_ids": positives,
            })
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    version = "final" if args.final else "pilot"
    out = ROOT / "exports" / f"{version}-{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    hashes = {split: write_jsonl(out / f"{split}.jsonl", rows) for split, rows in rows_by_split.items()}
    with sqlite3.connect(DB_PATH) as conn:
        sft_rows = compile_sft_data.compile_records(conn)
    sft_counts = compile_sft_data.inspect(sft_rows)
    sft_hashes = compile_sft_data.export(sft_rows, out)
    manifest = {
        "created_utc": stamp,
        "type": version,
        "train_rows": len(rows_by_split["train"]),
        "dev_rows": len(rows_by_split["dev"]),
        "sealed_test_included": False,
        "kb_sha256": sha256(DB_PATH),
        "source_manifest_sha256": sha256(ROOT / "sources_manifest.json"),
        "dataset_contract_sha256": sha256(ROOT / "dataset_contract.json"),
        "files_sha256": {**{f"{split}.jsonl": digest for split, digest in hashes.items()}, **sft_hashes},
        "sft_records_by_split_and_kind": sft_counts,
        "note": "Reviewed train/dev scenarios plus conversational SFT records. Sealed test remains local until final evaluation.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {version} train/dev data to {out}; sealed test withheld")


if __name__ == "__main__":
    main()
