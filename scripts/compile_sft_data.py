"""Compile reviewed SQLite rows into conversational SFT JSONL records.

Check mode writes nothing and may run before full law readiness. Export mode is
called only by export_colab_data after its existing readiness gates pass.
The train/dev SFT files contain only messages; sidecar maps preserve provenance.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

from build_full_kb import DB_PATH, ROOT, sha256


TRIAGE_INSTRUCTION = (
    "Read the reported incident. Return JSON only with outcome, "
    "possible_provision_ids, and uncertain_sections. A section is only a "
    "possibility, never a finding of guilt. Never invent missing facts."
)
WORKFLOW_INSTRUCTION = (
    "Continue this complaint-intake conversation. Return JSON only with "
    "assistant_action, assistant_message, and tool_payload. Treat selected "
    "options as reported facts, never verified facts. Do not claim an official "
    "filing; save a local draft only after explicit confirmation."
)


def encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compile_records(conn: sqlite3.Connection) -> dict[str, list[tuple[dict, dict]]]:
    conn.row_factory = sqlite3.Row
    outputs: dict[str, list[tuple[dict, dict]]] = {"train": [], "dev": []}
    allowed = {r[0] for r in conn.execute("SELECT provision_id FROM recommendable_provision")}
    scenarios = conn.execute("""SELECT * FROM scenario WHERE quality_status='accepted'
        AND privacy_reviewed=1 AND split IN ('train','dev')
        AND (review_tier='ai_reviewed' OR (review_tier='silver' AND split='train'))
        ORDER BY split,scenario_id""").fetchall()
    for scenario in scenarios:
        sid, split = scenario["scenario_id"], scenario["split"]
        labels = conn.execute("""SELECT provision_id,label,missing_facts
            FROM scenario_provision_label WHERE scenario_id=? ORDER BY provision_id""", (sid,)).fetchall()
        possible = [r["provision_id"] for r in labels if r["label"] == "possible"]
        uncertain = [{"provision_id": r["provision_id"], "missing_facts": r["missing_facts"]}
                     for r in labels if r["label"] == "uncertain"]
        outcome = scenario["expected_outcome"]
        if ((outcome == "provision_match") != bool(possible) or
                any(pid not in allowed for pid in possible) or
                any(not item["missing_facts"] for item in uncertain)):
            raise ValueError(f"Invalid supervised target: {sid}")
        target = {"outcome": outcome, "possible_provision_ids": possible,
                  "uncertain_sections": uncertain}
        messages = [
            {"role": "system", "content": TRIAGE_INSTRUCTION},
            {"role": "user", "content": scenario["complaint_text"]},
            {"role": "assistant", "content": encode(target)},
        ]
        outputs[split].append(({"messages": messages},
                               {"scenario_id": sid, "kind": "triage", "split": split,
                                "review_tier": scenario["review_tier"],
                                "scenario_group": scenario["scenario_group"]}))
        actions = conn.execute("""SELECT turn_index,user_message,assistant_action,
            assistant_message,tool_payload_json FROM conversation_example
            WHERE scenario_id=? AND quality_status='accepted' ORDER BY turn_index""", (sid,)).fetchall()
        history = [{"role": "system", "content": WORKFLOW_INSTRUCTION},
                   {"role": "user", "content": scenario["complaint_text"]}]
        for action in actions:
            user_message = action["user_message"]
            if user_message and (not history or history[-1]["content"] != user_message):
                history.append({"role": "user", "content": user_message})
            payload = json.loads(action["tool_payload_json"] or "{}")
            target = {"assistant_action": action["assistant_action"],
                      "assistant_message": action["assistant_message"],
                      "tool_payload": payload}
            message = {"role": "assistant", "content": encode(target)}
            outputs[split].append(({"messages": history + [message]},
                                   {"scenario_id": sid, "kind": "workflow",
                                    "turn_index": action["turn_index"], "split": split,
                                    "review_tier": scenario["review_tier"],
                                    "scenario_group": scenario["scenario_group"]}))
            history.append(message)
    return outputs


def inspect(outputs: dict[str, list[tuple[dict, dict]]]) -> dict:
    counts = {}
    for split, records in outputs.items():
        counts[split] = dict(Counter(m["kind"] for _, m in records))
        for record, mapping in records:
            messages = record["messages"]
            if not messages or messages[-1]["role"] != "assistant":
                raise ValueError(f"Invalid conversational record: {mapping}")
            json.loads(messages[-1]["content"])
            if mapping["split"] != split:
                raise ValueError("Split mismatch")
    return counts


def export(outputs: dict[str, list[tuple[dict, dict]]], directory: Path) -> dict[str, str]:
    if not directory.is_dir() or not directory.resolve().is_relative_to((ROOT / "exports").resolve()):
        raise ValueError("SFT output must be a created directory under phase1/exports")
    hashes = {}
    for split, records in outputs.items():
        for suffix, items in (("sft", [r for r, _ in records]),
                              ("sft_map", [m for _, m in records])):
            path = directory / f"{split}_{suffix}.jsonl"
            path.write_text("".join(encode(row) + "\n" for row in items), encoding="utf-8")
            hashes[path.name] = sha256(path)
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true", required=True)
    parser.parse_args()
    with sqlite3.connect(DB_PATH) as conn:
        result = inspect(compile_records(conn))
    print(json.dumps({"sft_shape_valid": True, "records_by_split_and_kind": result,
                      "files_written": 0}, indent=2))


if __name__ == "__main__":
    main()
