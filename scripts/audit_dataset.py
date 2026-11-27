"""Audit reviewed scenario data before any Colab export.

Read-only: reports problems and exits nonzero when accepted data is inconsistent.
An empty database is a valid pre-labeling state, never a ready training set.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from difflib import SequenceMatcher

try:
    from rapidfuzz.fuzz import ratio as fast_ratio
except ImportError:
    fast_ratio = None

from build_full_kb import DB_PATH, ROOT


def normalize(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def audit() -> dict:
    issues: list[str] = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        scenarios = conn.execute("SELECT * FROM scenario WHERE quality_status='accepted' ORDER BY scenario_id").fetchall()
        allowed = {r[0] for r in conn.execute("SELECT provision_id FROM recommendable_provision")}
        labels = defaultdict(list)
        for row in conn.execute("SELECT * FROM scenario_provision_label"):
            labels[row["scenario_id"]].append(row)
        actions = defaultdict(list)
        for row in conn.execute("SELECT * FROM conversation_example WHERE quality_status='accepted'"):
            actions[row["scenario_id"]].append(row)
        facts = defaultdict(list)
        for row in conn.execute("SELECT * FROM scenario_fact"):
            facts[row["scenario_id"]].append(row)
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            issues.append("foreign key errors")

    split_by_group: dict[str, str] = {}
    by_normalized: dict[str, tuple[str, str]] = {}
    split_counts = Counter()
    outcome_counts = Counter()
    positive_counts = Counter()
    texts = []
    for s in scenarios:
        sid, split = s["scenario_id"], s["split"]
        split_counts[split] += 1
        outcome_counts[s["expected_outcome"]] += 1
        previous = split_by_group.setdefault(s["scenario_group"], split)
        if previous != split:
            issues.append(f"group leakage: {s['scenario_group']}")
        norm = normalize(s["complaint_text"])
        if len(norm) < 20:
            issues.append(f"complaint too short: {sid}")
        if norm in by_normalized and by_normalized[norm][1] != split:
            issues.append(f"exact text leakage: {sid} versus {by_normalized[norm][0]}")
        by_normalized.setdefault(norm, (sid, split))
        texts.append((sid, split, norm))
        if not s["privacy_reviewed"] or not s["reviewer"] or not s["reviewed_on"]:
            issues.append(f"missing scenario review: {sid}")
        if s["review_tier"] == "silver" and split != "train":
            issues.append(f"silver in evaluation split: {sid}")
        if s["provenance_type"] == "public_licensed" and (not s["source_url"] or not s["license"]):
            issues.append(f"public data lacks source/license: {sid}")
        if s["provenance_type"] == "consented_anonymized" and not s["review_note"]:
            issues.append(f"consent/de-identification note missing: {sid}")
        possible = []
        for label in labels[sid]:
            if not label["reviewer"] or not label["reviewed_on"] or not label["rationale"].strip():
                issues.append(f"unreviewed label: {sid}/{label['provision_id']}")
            if label["label"] == "possible":
                possible.append(label["provision_id"])
                positive_counts[label["provision_id"]] += 1
                if label["provision_id"] not in allowed:
                    issues.append(f"positive label outside allowlist: {sid}/{label['provision_id']}")
            if label["label"] == "uncertain" and not label["missing_facts"]:
                issues.append(f"uncertain label lacks missing facts: {sid}/{label['provision_id']}")
        if s["expected_outcome"] == "provision_match" and not possible:
            issues.append(f"match has no possible label: {sid}")
        if s["expected_outcome"] in {"insufficient_information", "out_of_scope"} and possible:
            issues.append(f"abstention has possible label: {sid}")
        for fact in facts[sid]:
            if fact["state"] in {"present", "absent"} and (not fact["evidence_span"] or fact["evidence_span"] not in s["complaint_text"]):
                issues.append(f"fact evidence span missing from complaint: {sid}/{fact['fact_key']}")
            if fact["state"] in {"unknown", "disputed"} and fact["fact_value"]:
                issues.append(f"unknown/disputed fact has asserted value: {sid}/{fact['fact_key']}")
        for action in actions[sid]:
            if not action["reviewer"] or not action["reviewed_on"]:
                issues.append(f"conversation action unreviewed: {action['example_id']}")
            if action["tool_payload_json"]:
                try:
                    payload = json.loads(action["tool_payload_json"])
                    if action["assistant_action"] == "ask_followup":
                        purpose = payload.get("purpose", "legal_missing_fact") if isinstance(payload, dict) else None
                        if purpose == "legal_missing_fact" and s["expected_outcome"] != "insufficient_information":
                            issues.append(f"legal-missing-fact follow-up on non-missing scenario: {action['example_id']}")
                        if purpose == "draft_detail" and s["expected_outcome"] != "provision_match":
                            issues.append(f"draft-detail follow-up on non-match scenario: {action['example_id']}")
                        if purpose not in {"legal_missing_fact", "draft_detail"}:
                            issues.append(f"unknown follow-up purpose: {action['example_id']}")
                        if (not isinstance(payload, dict) or
                            payload.get("response_mode") != "choice_or_free_text" or
                            not isinstance(payload.get("options"), list) or
                            "Not sure" not in payload["options"] or
                            "Other" not in payload["options"] or
                            payload.get("allow_free_text") is not True or
                            payload.get("selected_option_is_reported_fact_not_verified") is not True):
                            issues.append(f"invalid follow-up options: {action['example_id']}")
                    if action["assistant_action"] == "confirm_draft" and (
                        not isinstance(payload, dict) or
                        payload.get("command") != "save_local_draft" or
                        payload.get("explicit_user_confirmation") is not True or
                        payload.get("require_current_version") is not True):
                        issues.append(f"unguarded local save: {action['example_id']}")
                    if action["assistant_action"] == "cancel_draft" and (
                        not isinstance(payload, dict) or
                        payload.get("command") != "discard_unsaved_draft"):
                        issues.append(f"invalid draft cancellation: {action['example_id']}")
                    if isinstance(payload, dict) and payload.get("official_filing") is True:
                        issues.append(f"unsupported official filing: {action['example_id']}")
                    if action["assistant_action"] == "edit_draft" and isinstance(payload, dict):
                        earlier = [a for a in actions[sid] if a["turn_index"] < action["turn_index"]
                                   and a["assistant_action"] in {"draft", "edit_draft"}]
                        if not earlier:
                            issues.append(f"edit has no earlier draft: {action['example_id']}")
                        else:
                            previous = max(earlier, key=lambda a: a["turn_index"])
                            patch = payload.get("patch", {})
                            old, new = patch.get("old_text"), patch.get("new_text")
                            prior = previous["assistant_message"]
                            if not old or not new or prior.count(old) != 1:
                                issues.append(f"edit patch is ambiguous: {action['example_id']}")
                            else:
                                expected = prior.replace(
                                    f"Draft, version {payload.get('from_version')}:",
                                    f"Draft, version {payload.get('to_version')}:", 1).replace(old, new, 1)
                                if expected != action["assistant_message"]:
                                    issues.append(f"edit changed unrequested draft text: {action['example_id']}")
                except json.JSONDecodeError:
                    issues.append(f"invalid tool JSON: {action['example_id']}")

    # A comparison across different splits only. Threshold is a review flag, not
    # a proof of leakage; with <=500 distinct scenarios this is inexpensive.
    for i, (sid, split, norm) in enumerate(texts):
        for other_sid, other_split, other_norm in texts[i + 1:]:
            if split == other_split:
                continue
            if abs(len(norm) - len(other_norm)) > max(len(norm), len(other_norm)) * 0.25:
                continue
            # RapidFuzz's LCS score is an upper bound for the matching-block
            # score below. This cheap filter leaves the existing decision rule
            # unchanged while avoiding most Python comparisons at scale.
            if fast_ratio is not None and fast_ratio(norm, other_norm, score_cutoff=92) < 92:
                continue
            score = SequenceMatcher(None, norm, other_norm, autojunk=False).ratio()
            if score >= 0.92:
                issues.append(f"near duplicate across splits ({score:.2f}): {sid}/{other_sid}")

    report = {
        "accepted_scenarios": len(scenarios),
        "by_split": dict(split_counts),
        "by_outcome": dict(outcome_counts),
        "positive_labels_by_provision": dict(sorted(positive_counts.items())),
        "structured_fact_rows": sum(len(v) for v in facts.values()),
        "accepted_conversation_actions": dict(Counter(a["assistant_action"] for group in actions.values() for a in group)),
        "issues": sorted(set(issues)),
        "pilot_minimum": {"train": 70, "dev": 15, "sealed_test": 15},
        "pilot_split_ready": all(split_counts.get(split, 0) >= minimum for split, minimum in
                                 (("train", 70), ("dev", 15), ("sealed_test", 15))) and not issues,
        "ready_to_export": len(scenarios) >= 300 and split_counts.get("sealed_test", 0) >= 80
                           and sum(outcome_counts.get(x, 0) for x in
                                   ("insufficient_information", "out_of_scope")) >= 60 and not issues,
        "note": "This checks the scenario count, split and internal consistency only. It does not prove legal accuracy, case diversity, workflow adequacy or readiness for full BNS and IT Act coverage; consult data_readiness_report.json.",
    }
    return report


def main() -> None:
    report = audit()
    out = ROOT / "dataset_audit_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["issues"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
