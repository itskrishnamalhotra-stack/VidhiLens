from __future__ import annotations

import unittest

from app.inference import Generation
from app.workflow import (
    format_draft_narrative,
    model_conversational_response,
)


class FakeInference:
    def __init__(self, payload: str):
        self.payload = payload
        self.calls: list[dict] = []

    async def chat(self, messages, max_tokens, use_lora, response_format=None):
        self.calls.append({
            "messages": messages,
            "max_tokens": max_tokens,
            "use_lora": use_lora,
            "response_format": response_format,
        })
        return Generation(text=self.payload, seconds=0.01, completion_tokens=12)


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_greeting_goes_to_the_base_model(self):
        inference = FakeInference('{"route":"casual","reply":"Hello! Tell me what is on your mind."}')
        response = await model_conversational_response(inference, "Hello", False, None)
        self.assertEqual(response[0], "Hello! Tell me what is on your mind.")  # type: ignore[index]
        self.assertFalse(inference.calls[0]["use_lora"])

    async def test_base_model_can_handle_open_ended_small_talk(self):
        inference = FakeInference(
            '{"route":"casual","reply":"Here is a short one: why did the file go to court? It had too many cases. If something happened to you, I can help organise the facts."}'
        )
        response = await model_conversational_response(
            inference, "Tell me more", False, "conversation",
            [{"role": "user", "text": "Who are you?"},
             {"role": "assistant", "text": "I am VidhiLens."}],
        )
        self.assertIsNotNone(response)
        text, structured = response  # type: ignore[misc]
        self.assertIn("short one", text)
        self.assertEqual(structured["conversation_kind"], "casual")
        self.assertFalse(inference.calls[0]["use_lora"])
        self.assertIsNotNone(inference.calls[0]["response_format"])
        self.assertIn("recent_conversation", inference.calls[0]["messages"][1]["content"])

    async def test_model_routed_incident_continues_to_legal_pipeline(self):
        inference = FakeInference('{"route":"incident","reply":""}')
        response = await model_conversational_response(
            inference, "My employer did something wrong", False, None
        )
        self.assertIsNone(response)

    async def test_legal_advice_capability_claim_is_corrected(self):
        inference = FakeInference('{"route":"casual","reply":"I can help with legal advice and drafts."}')
        response = await model_conversational_response(inference, "What can you do?", False, None)
        self.assertIn("legal research guidance", response[0])  # type: ignore[index]
        self.assertNotIn("help with legal advice", response[0])  # type: ignore[index]

    def test_draft_keeps_follow_up_answer_readable(self):
        narrative = "My phone was stolen.\nAdditional information from the user: Was it snatched?\nAnswer: No"
        self.assertEqual(format_draft_narrative(narrative),
                         'My phone was stolen.\n\nI said it was not snatched.')


if __name__ == "__main__":
    unittest.main()
