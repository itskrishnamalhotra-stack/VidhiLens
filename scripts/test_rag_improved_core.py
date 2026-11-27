"""Local, non-GPU checks for the improved multilingual RAG core."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "scripts" / "rag_improved_core.py"
CATALOGUE_PATH = ROOT / "exports" / "rag_catalogue_v1.json"
BENCHMARK_DIR = ROOT / "evaluation" / "sealed_rag_benchmark_v1"
PREDICTIONS_PATH = ROOT / "evaluation" / "sealed_rag_benchmark_v1_predictions.json"


spec = importlib.util.spec_from_file_location("rag_improved_core", CORE_PATH)
core = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(core)

catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))["provisions"]
retriever = core.build_retriever(catalogue)
inputs = {
    row["case_id"]: row
    for row in map(json.loads, (BENCHMARK_DIR / "benchmark_inputs.jsonl").read_text(
        encoding="utf-8").splitlines())
}
gold = {
    row["case_id"]: row
    for row in map(json.loads, (BENCHMARK_DIR / "sealed_answer_key.jsonl").read_text(
        encoding="utf-8").splitlines())
}
old_predictions = json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8"))["predictions"]
old_triage = {row["case_id"]: row["lora_only"]["parsed"] for row in old_predictions}

required = found = all_found = positive_cases = 0
misses: list[dict] = []
retrieval_rows: list[dict] = []
for case_id, case in inputs.items():
    result = core.retrieve_candidates(case["complaint"], old_triage[case_id], retriever)
    retrieved = [row["provision_id"] for row in result["offence_candidates"]]
    expected = set(gold[case_id]["required_provision_ids"])
    if expected:
        positive_cases += 1
        required += len(expected)
        found += len(expected & set(retrieved))
        all_found += int(expected.issubset(retrieved))
        if not expected.issubset(retrieved):
            misses.append({
                "case_id": case_id,
                "complaint": case["complaint"],
                "required": sorted(expected),
                "retrieved": retrieved,
            })
    retrieval_rows.append({"case_id": case_id, "retrieved": retrieved})

recall = found / required
case_accuracy = all_found / positive_cases
print(json.dumps({
    "required_sections": required,
    "required_found": found,
    "recall_at_6": recall,
    "positive_cases": positive_cases,
    "all_required_case_accuracy": case_accuracy,
    "misses": misses,
}, indent=2, ensure_ascii=False))

# The local regression target is deliberately stronger than the release gate;
# the later model assessment is only useful when retrieval preserves candidates.
assert recall >= 0.97, recall
assert case_accuracy >= 0.95, case_accuracy
assert len(core.CONCEPT_PATTERNS) == 19
assert all(len(row["retrieved"]) <= core.MAX_CANDIDATES for row in retrieval_rows)

# General behaviour checks independent of benchmark IDs.
cases = [
    ("A stranger broke into my locked home and carried away my laptop.", {"BNS_329", "BNS_303"}),
    ("A caller pretended to be my bank manager and used my OTP to transfer money.",
     {"BNS_319", "ITA_66C", "ITA_66D"}),
    ("A man secretly recorded a sexual act in a private room and uploaded the video.",
     {"BNS_77", "ITA_67A"}),
    ("Mera phone nahi mil raha; pata nahi chori hua ya main bhool gaya.", {"BNS_303"}),
    ("एक व्यक्ति ने मेरा पीछा किया और मना करने के बाद भी बार बार संपर्क किया।", {"BNS_78"}),
    ("Woh roz office tak follow karta hai aur ghar ke bahar wait karta hai.", {"BNS_78"}),
    ("Usne WhatsApp par bank employee bankar mujhe payment bhejne ko kaha.",
     {"BNS_319", "ITA_66D"}),
    ("उसने मेरे पासवर्ड और डिजिटल हस्ताक्षर का धोखाधड़ी से उपयोग किया।", {"ITA_66C"}),
    ("A colleague deliberately displayed pornography after being told to stop.", {"BNS_75"}),
]
for complaint, expected in cases:
    result = core.retrieve_candidates(
        complaint,
        {"outcome": "insufficient_information", "possible_provision_ids": [],
         "uncertain_sections": []},
        retriever,
    )
    retrieved = {row["provision_id"] for row in result["offence_candidates"]}
    assert expected.issubset(retrieved), (complaint, expected, retrieved)

# Strong evidence is stricter than retrieval and supports deterministic recovery
# of multi-provision complaints without inventing new candidates.
strong_cases = [
    ("He punched me and caused bruising.", ["BNS_115"], {"BNS_115"}),
    ("A fake investment scheme deceived me into paying money.", ["BNS_318"], {"BNS_318"}),
    ("She impersonated my employer in messages.", ["BNS_319"], {"BNS_319"}),
    ("An intruder hacked my email account.", ["ITA_66"], {"ITA_66"}),
    ("Usne mera OTP aur password use karke account access kiya.", ["ITA_66C"], {"ITA_66C"}),
    ("A dealer knowingly bought a stolen phone for resale.", ["ITA_66B"], {"ITA_66B"}),
]
for complaint, candidate_ids, expected in strong_cases:
    assert expected <= core.strong_grounded_ids(complaint, candidate_ids), complaint

# "Without permission" states lack of consent and must not erase later facts.
assert "punched me" in core.explicit_negative_clauses(
    "He entered without permission and deliberately punched me."
)

cleaned, questions, actions = core.apply_output_cleaner(
    "A dealer knowingly bought a stolen phone and kept it for resale.",
    ["BNS_303", "ITA_66B"],
    {"BNS_318": core.DEFAULT_MISSING_QUESTIONS["BNS_318"]},
    ["BNS_303", "ITA_66B", "BNS_318"],
)
assert cleaned == ["ITA_66B"], (cleaned, actions)
assert not questions, questions

cleaned, _, actions = core.apply_output_cleaner(
    "Someone fraudulently entered my cloud account without authorisation.",
    ["ITA_66", "ITA_66C"], {}, ["ITA_66", "ITA_66C"]
)
assert cleaned == ["ITA_66"], (cleaned, actions)

assert core.explicit_transaction_uncertainty(
    "A product I paid for is delayed and I have no facts showing dishonest intention."
)
assert core.has_scoped_legal_subject(
    "My password stopped working but I have no evidence another person used it."
)
assert not core.has_scoped_legal_subject(
    "My friend stopped replying and there were no threats or account access."
)

print("Improved RAG core checks passed")

# Also check the 19 recommendation-approved positives in the independent
# development split without using any LoRA seed. This protects natural wording
# that is different from the 150-case regression set.
development_path = ROOT / "exports" / "colab-step4-v1" / "complaint_only" / "dev_sft.jsonl"
development_required = development_found = development_cases = 0
development_misses = []
approved_ids = set(core.CONCEPT_PATTERNS)
empty_triage = {"outcome": "out_of_scope", "possible_provision_ids": [], "uncertain_sections": []}
for line in development_path.read_text(encoding="utf-8").splitlines():
    row = json.loads(line)
    complaint = row["messages"][1]["content"]
    answer = json.loads(row["messages"][2]["content"])
    expected = set(answer.get("possible_provision_ids", [])) & approved_ids
    if not expected:
        continue
    retrieved = {
        item["provision_id"] for item in core.retrieve_candidates(
            complaint, empty_triage, retriever
        )["offence_candidates"]
    }
    development_cases += 1
    development_required += len(expected)
    development_found += len(expected & retrieved)
    if not expected.issubset(retrieved):
        development_misses.append((complaint, expected, retrieved))
assert development_cases == 19
assert development_found == development_required == 19, development_misses
print("Independent development retrieval checks passed")
