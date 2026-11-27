"""Make a reproducible, stratified Nyaya v3 answer review packet."""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "external_candidates" / "additional_20260917"
BASE = ROOT / "exports" / "mixed-source-v15-gsms-aux-research"
OUT = ROOT / "review_automation" / "nyaya_v3_sample_20260919"
SEED = 20260919
SAMPLE_PER_GROUP = 10


def group(meta: dict) -> str:
    act = meta.get("source_act")
    language = meta.get("language")
    if meta.get("task_type") == "safety_abstention":
        return "safety_abstention"
    if language == "hindi":
        return "hindi"
    if language == "hinglish":
        return "hinglish"
    if act == "bns_2023":
        return "bns"
    if act == "it_act_2000":
        return "it_act"
    if act in {"bnss_2023", "bsa_2023"}:
        return "other_new_codes"
    if act == "constitution_1950":
        return "constitution"
    return "other_acts"


def main() -> None:
    groups: dict[str, list[dict]] = defaultdict(list)
    full_counts = Counter()
    source_metadata = {
        split: [json.loads(line)["metadata"] for line in
                (SOURCE / f"nyaya_v3_{'train' if split == 'train' else 'val'}.jsonl")
                .read_text(encoding="utf-8").splitlines()]
        for split in ("train", "dev")
    }
    for split in ("train", "dev"):
        with (BASE / f"{split}_sft.jsonl").open(encoding="utf-8") as handle, \
             (BASE / f"{split}_sft_map.jsonl").open(encoding="utf-8") as maps:
            for line, map_line in zip(handle, maps, strict=True):
                mapping = json.loads(map_line)
                if mapping.get("source") != "NyayaLabs98/nyaya-train-v3":
                    continue
                record = json.loads(line)
                source_row = mapping["source_row"]
                meta = source_metadata[split][source_row - 1]
                messages = record["messages"]
                prompt = messages[1]["content"]
                answer = messages[2]["content"]
                question = meta.get("rag", {}).get("question") or prompt.rsplit("Question:", 1)[-1].strip()
                item = {
                    "id": mapping["source_id"], "split": split, "source_row": source_row,
                    "group": group(meta), "act": meta.get("source_act"),
                    "language": meta.get("language"), "task_type": meta.get("task_type"),
                    "refs": meta.get("source_sections") or [],
                    "context_keys": meta.get("rag", {}).get("context_keys") or [],
                    "question": question, "answer": answer,
                    "prompt_chars": len(prompt), "answer_chars": len(answer),
                    "question_in_prompt": question in prompt,
                    "chat_shape_ok": [m.get("role") for m in messages] == ["system", "user", "assistant"],
                }
                groups[item["group"]].append(item)
                full_counts[item["group"]] += 1
    rng = random.Random(SEED)
    sample = []
    for key in sorted(groups):
        sample.extend(rng.sample(groups[key], min(SAMPLE_PER_GROUP, len(groups[key]))))
    rng.shuffle(sample)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "sample.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for index, item in enumerate(sample, 1):
            item["sample_index"] = index
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    (OUT / "summary.json").write_text(json.dumps({
        "seed": SEED, "sample_size": len(sample), "group_sample_size": SAMPLE_PER_GROUP,
        "full_group_counts": dict(sorted(full_counts.items())),
        "sample_group_counts": dict(Counter(x["group"] for x in sample)),
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sample_size": len(sample), "full_group_counts": dict(full_counts)}, indent=2))


if __name__ == "__main__":
    main()
