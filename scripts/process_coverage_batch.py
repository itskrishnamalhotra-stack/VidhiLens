"""Run one checked coverage batch through export, audit, and master sync.

Input cases still require source-based legal review. This automates the
repeatable plumbing after a human-readable JSON batch has been authored.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EXPORTS = ROOT / "exports"
GAP_SEALED = ROOT / "data_drafts" / "gap_examples_v2" / "sealed_test.jsonl"


def run(script: str, *args: str) -> None:
    subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                   cwd=ROOT.parent, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_relative_to(ROOT) or not source.is_file():
        raise ValueError("Source must be an existing Phase 1 JSON batch")
    raw = json.loads(source.read_text(encoding="utf-8"))
    ids = {row["id"] for row in raw["cases"]}
    if len(ids) != len(raw["cases"]):
        raise ValueError("Duplicate case ID in source batch")
    exports = []
    for path in EXPORTS.glob("mixed-source-v*-research"):
        match = re.fullmatch(r"mixed-source-v(\d+)-research", path.name)
        if match and (path / "manifest.json").is_file():
            exports.append((int(match[1]), path))
    if not exports:
        raise ValueError("No baseline research export")
    version, base = max(exports)
    out = EXPORTS / f"mixed-source-v{version + 1}-research"
    if out.exists():
        raise ValueError(f"Output already exists: {out}")
    for split in ("train", "dev"):
        with (base / f"{split}_sft_map.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                if json.loads(line).get("source_id") in ids:
                    raise ValueError("This case batch was already appended to the latest export")
    checked = source.with_name(source.stem + "_checked")
    prior_sealed = sorted((ROOT / "data_drafts").glob("coverage_batch*_checked/sealed_test.jsonl"))
    if checked / "sealed_test.jsonl" in prior_sealed:
        prior_sealed.remove(checked / "sealed_test.jsonl")
    all_sealed = [GAP_SEALED, *prior_sealed, checked / "sealed_test.jsonl"]
    report_out = ROOT / "review_automation" / f"research_coverage_v{version + 1}"
    leakage_out = ROOT / "review_automation" / f"research_leakage_v{version + 1}"
    plan = {"source": str(source), "base": str(base), "new_export": str(out),
            "checked_batch": str(checked), "sealed_sources": [str(p) for p in all_sealed],
            "coverage_audit": str(report_out), "leakage_audit": str(leakage_out)}
    print(json.dumps(plan, indent=2), flush=True)
    if args.dry_run:
        return
    run("build_coverage_batch.py", "--source", source, "--base", base,
        *(arg for path in prior_sealed for arg in ("--prior-sealed", path)))
    run("append_research_batch.py", "--base", base, "--batch", checked, "--out", out)
    run("audit_research_coverage.py", "--base", out, "--out", report_out,
        *(arg for path in all_sealed for arg in ("--sealed", path)))
    run("sync_research_export_to_master.py", "--export", out,
        *(arg for path in all_sealed for arg in ("--sealed", path)))
    run("verify_research_master.py", "--export", out)
    run("audit_research_split_leakage.py", "--out", leakage_out)


if __name__ == "__main__":
    main()
