"""Small CPU regression check for Colab evaluation resume behavior."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "colab"))
import train_runner


class FakeTokenizer:
    eos_token_id = 2

    def apply_chat_template(self, messages, *, add_generation_prompt, return_tensors):
        assert add_generation_prompt and return_tensors == "pt"
        return torch.tensor([[1, 2, 3]])

    def decode(self, tokens, *, skip_special_tokens):
        assert skip_special_tokens and tokens.tolist() == [42]
        return json.dumps({"outcome": "provision_match", "possible_provision_ids": ["BNS_303"]})


class FakeModel:
    device = torch.device("cpu")

    def generate(self, *, input_ids, attention_mask, **kwargs):
        assert input_ids.tolist() == [[1, 2, 3]]
        assert attention_mask.tolist() == [[1, 1, 1]]
        assert kwargs["do_sample"] is False
        return torch.cat([input_ids, torch.tensor([[42]])], dim=1)


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        variant = "complaint_only"
        input_dir = root / "input"
        drive_root = root / "drive"
        dev_file = input_dir / variant / "dev_sft.jsonl"
        dev_file.parent.mkdir(parents=True)
        row = {"messages": [
            {"role": "user", "content": "My phone was stolen."},
            {"role": "assistant", "content": json.dumps({
                "outcome": "provision_match", "possible_provision_ids": ["BNS_303"]})},
        ]}
        dev_file.write_text(json.dumps(row) + "\n", encoding="utf-8")
        run_dir = drive_root / "runs" / variant
        run_dir.mkdir(parents=True)
        (run_dir / "dev_predictions.jsonl").write_text(json.dumps({
            "index": 0, "text": "old", "parsed": {"outcome": "wrong"}}) + "\n", encoding="utf-8")
        (run_dir / "dev_metrics.json").write_text(json.dumps({"selection_score": 0}), encoding="utf-8")
        with patch.object(train_runner, "load_adapter", return_value=(FakeModel(), FakeTokenizer())):
            first = train_runner.evaluate(input_dir, drive_root, root / "local", variant,
                                          "dev", {"BNS_303"})
        assert first["selection_score"] == 1
        assert first["generation_version"] == train_runner.EVAL_VERSION
        saved = train_runner.read_jsonl(run_dir / "dev_predictions.jsonl")
        assert saved[0]["generation_version"] == train_runner.EVAL_VERSION
        with patch.object(train_runner, "load_adapter", side_effect=AssertionError("should reuse")):
            second = train_runner.evaluate(input_dir, drive_root, root / "local", variant,
                                           "dev", {"BNS_303"})
        assert second == first
        print("Evaluation mask, stale prediction reset, and completed result reuse: PASS")


if __name__ == "__main__":
    main()
