"""Export a truthful, directly trainable 19-section pilot from reviewed rows.

The full BNS/IT Act export stays gated in export_colab_data.py. This pilot is
for a later limited-scope LoRA experiment, not a full-Act completion claim.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import audit_dataset
import compile_sft_data
from build_full_kb import DB_PATH, ROOT, sha256


def main() -> None:
    audit = audit_dataset.audit()
    if audit["issues"] or not audit["pilot_split_ready"]:
        raise SystemExit("Reviewed pilot audit failed; no export written")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise SystemExit("Foreign key errors")
        scope = [r[0] for r in conn.execute("SELECT provision_id FROM recommendable_provision ORDER BY provision_id")]
        if len(scope) != 19:
            raise SystemExit("Pilot allowlist changed; review export scope")
        if conn.execute("""SELECT count(*) FROM provision WHERE recommendable=1
            AND (verified_text IS NULL OR legal_status!='in_force')""").fetchone()[0]:
            raise SystemExit("Pilot law text/status is not verified")
        outputs = compile_sft_data.compile_records(conn)
        counts = compile_sft_data.inspect(outputs)
        if counts["train"].get("triage", 0) < 70 or counts["dev"].get("triage", 0) < 15:
            raise SystemExit("Pilot training or development split too small")
        sealed_count = conn.execute("""SELECT count(*) FROM scenario WHERE quality_status='accepted'
            AND split='sealed_test'""").fetchone()[0]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "exports" / f"scoped-pilot-{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    hashes = compile_sft_data.export(outputs, out)
    manifest = {
        "created_utc": stamp,
        "scope": "19 source-checked, recommendable BNS and IT Act sections only",
        "full_BNS_IT_Act_coverage": False,
        "model_training_run": False,
        "reviewed_scope_provision_ids": scope,
        "records_by_split_and_kind": counts,
        "sealed_test_records_exported": 0,
        "sealed_test_scenarios_kept_local": sealed_count,
        "master_database_sha256": sha256(DB_PATH),
        "dataset_contract_sha256": sha256(ROOT / "dataset_contract.json"),
        "files_sha256": hashes,
        "warning": "Trainer-compatible format does not establish sufficient data, legal scope or model accuracy.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"directory": str(out), "records": counts,
                      "sealed_test_exported": 0, "full_act_ready": False}, indent=2))


if __name__ == "__main__":
    main()
