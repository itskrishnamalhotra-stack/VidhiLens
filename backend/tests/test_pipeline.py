from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path

from app.inference import Generation
from app.pipeline import LegalPipeline


PHASE1 = Path(__file__).resolve().parents[2]


class FakeInference:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, max_tokens, use_lora, response_format=None):
        self.calls += 1
        if use_lora:
            return Generation(
                text=json.dumps({
                    "outcome": "provision_match",
                    "possible_provision_ids": ["BNS_303"],
                    "uncertain_sections": [],
                }),
                seconds=0.01,
                completion_tokens=12,
            )
        payload = json.loads(messages[-1]["content"])
        assessments = [{
            "provision_id": item["provision_id"],
            "decision": "supported" if item["provision_id"] == "BNS_303" else "rejected",
        } for item in payload["candidates"]]
        return Generation(json.dumps({"assessments": assessments}), 0.01, 12)

    async def health(self):
        return {"ready": True}


class PipelineTests(unittest.TestCase):
    def test_backend_uses_exact_reviewed_rag_core(self):
        self.assertEqual(
            (PHASE1 / "scripts" / "rag_improved_core.py").read_bytes(),
            (PHASE1 / "backend" / "app" / "rag_core.py").read_bytes(),
        )

    def test_grounded_pipeline_hydrates_verified_law_source(self):
        fake = FakeInference()
        pipeline = LegalPipeline(PHASE1 / "exports" / "rag_catalogue_v1.json", fake)
        result = asyncio.run(pipeline.analyze("Someone stole my phone from my desk without my consent."))
        self.assertEqual(result["outcome"], "provision_match")
        self.assertEqual(result["possible_provision_ids"], ["BNS_303"])
        self.assertTrue(result["provisions"][0]["source_url"].startswith("http"))
        self.assertTrue(result["provisions"][0]["verified_text"])
        self.assertIs(result["can_prepare_draft"], True)
        self.assertEqual(fake.calls, 2)


if __name__ == "__main__":
    unittest.main()
