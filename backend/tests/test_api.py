from __future__ import annotations

import tempfile
import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.inference import Generation


PHASE1 = Path(__file__).resolve().parents[2]


class FakeConversationModel:
    async def chat(self, messages, max_tokens, use_lora, response_format=None):
        schema_name = (response_format or {}).get("json_schema", {}).get("name")
        if schema_name == "single_draft_value":
            narrative = messages[-1]["content"]
            prompt = messages[0]["content"]
            field = prompt.split("Target field: ", 1)[1].split(".", 1)[0]
            values = {
                "reporter_name": ("Krishna Malhotra" if "Krishna Malhotra" in narrative else
                                  "Krishna" if "my name is krishna" in narrative.lower() else
                                  "Alice" if "I am Alice" in narrative else ""),
                "incident_date": "Yesterday" if "Yesterday" in narrative else
                                 "29-09-2026" if "29-09-2026" in narrative else "",
                "location": "college" if "at college" in narrative.lower() else "",
                "property_or_account": "phone" if "phone" in narrative.lower() else "",
            }
            return Generation(text=json.dumps({"value": values.get(field, "")}),
                              seconds=0.01, completion_tokens=20)
        if schema_name == "complaint_incident_narrative":
            narrative = messages[-1]["content"]
            return Generation(text=json.dumps({"text": (
                "My phone went missing at college. I believe it may have been taken without my consent."
                if "phone" in narrative.lower() else "I reported the incident."
            )}), seconds=0.01, completion_tokens=35)
        if schema_name == "draft_followup_question":
            prompt = messages[0]["content"]
            question = ("What name should appear on your report?" if "reporter name" in prompt else
                        "When did this happen?" if "incident date" in prompt else
                        "Where did this happen?" if "location" in prompt else "What detail can you add?")
            return Generation(text=json.dumps({"question": question}), seconds=0.01, completion_tokens=20)
        if schema_name == "grounded_next_reply":
            return Generation(text=json.dumps({
                "reply": "I'm sorry your phone was taken at college. The facts may relate to theft.",
                "question": "When did this happen?",
                "options": ["Today", "Yesterday", "I don't know"],
            }), seconds=0.01, completion_tokens=35)
        if "assist a VidhiLens reviewer" in messages[0]["content"]:
            return Generation(text=(
                "The report says a phone was taken without consent. BNS_303 may relate to theft. "
                "Verify who possessed the phone, where it was kept, when it went missing, "
                "and whether anyone saw it being taken. The report remains unverified."
            ), seconds=0.01, completion_tokens=50)
        current = json.loads(messages[-1]["content"])["message"]
        if "stole" in current.lower():
            result = {"route": "incident", "reply": ""}
        else:
            result = {"route": "casual", "reply": "I can help you think through what happened, one step at a time."}
        return Generation(text=json.dumps(result), seconds=0.01, completion_tokens=20)


class FakePipeline:
    model_version = "test-model"
    kb_version = "test-kb"
    valid_ids = {"BNS_303"}
    inference = FakeConversationModel()

    async def analyze(self, complaint: str):
        if "stole" not in complaint.lower():
            return {
                "outcome": "out_of_scope", "possible_provision_ids": [],
                "provisions": [], "uncertain_sections": [], "can_prepare_draft": False,
                "model_version": self.model_version, "kb_version": self.kb_version,
                "pipeline_id": "test", "audit": {}, "timing": {}, "notice": "test",
            }
        return {
            "outcome": "provision_match",
            "possible_provision_ids": ["BNS_303"],
            "provisions": [{
                "provision_id": "BNS_303", "title": "Theft", "legal_status": "in_force",
                "verified_text": "Verified text", "source_url": "https://example.test/law",
                "source_pdf_page": 1,
            }],
            "uncertain_sections": [], "can_prepare_draft": True,
            "model_version": self.model_version, "kb_version": self.kb_version,
            "pipeline_id": "test", "audit": {}, "timing": {}, "notice": "test",
        }


def make_client(tmp_path: Path, demo_access_token: str | None = None, admin_access_token: str | None = None) -> TestClient:
    settings = Settings(
        project_root=PHASE1,
        database_path=tmp_path / "api.sqlite",
        catalogue_path=PHASE1 / "exports" / "rag_catalogue_v1.json",
        auth_mode="dev",
        demo_access_token=demo_access_token,
        admin_access_token=admin_access_token,
    )
    return TestClient(create_app(settings=settings, pipeline=FakePipeline()))


def headers(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev:{user}"}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_sessions_are_isolated_and_message_runs_analysis(self):
      with make_client(self.tmp_path) as client:
        created = client.post("/sessions", headers=headers("alice"), json={"title": "Phone"})
        self.assertEqual(created.status_code, 201)
        session_id = created.json()["session_id"]

        denied = client.get(f"/sessions/{session_id}", headers=headers("bob"))
        self.assertEqual(denied.status_code, 404)

        answer = client.post(
            f"/sessions/{session_id}/messages", headers=headers("alice"),
            json={"text": "Someone stole my phone from my desk."},
        )
        self.assertEqual(answer.status_code, 200)
        structured = answer.json()["assistant_message"]["structured"]
        self.assertEqual(structured["action"], "ask_question")
        self.assertEqual(structured["next_question"]["text"], "When did this happen?")
        self.assertIs(structured["official_filing_performed"], False)

        session = client.get(f"/sessions/{session_id}", headers=headers("alice")).json()
        self.assertEqual([item["role"] for item in session["messages"]], ["user", "assistant"])

        follow_up = client.post(
            f"/sessions/{session_id}/messages", headers=headers("alice"),
            json={"text": "When did this happen?\nAnswer: Today"},
        )
        self.assertEqual(follow_up.status_code, 200)
        self.assertIsNotNone(follow_up.json()["analysis_id"])
        self.assertIn("BNS_303", follow_up.json()["assistant_message"]["structured"]["analysis"]["possible_provision_ids"])
        self.assertIsNone(follow_up.json()["assistant_message"]["structured"]["next_question"])

    def test_greeting_stays_conversational_and_first_incident_sets_title(self):
      with make_client(self.tmp_path) as client:
        created = client.post(
            "/sessions", headers=headers("alice"), json={"title": "New complaint"}
        ).json()
        session_id = created["session_id"]

        greeting = client.post(
            f"/sessions/{session_id}/messages", headers=headers("alice"),
            json={"text": "HI THERE"},
        )
        self.assertEqual(greeting.status_code, 200)
        greeting_body = greeting.json()
        self.assertIsNone(greeting_body["analysis_id"])
        self.assertEqual(
            greeting_body["assistant_message"]["structured"]["action"], "conversation"
        )
        self.assertTrue(greeting_body["assistant_message"]["structured"]["suggestions"])
        after_greeting = client.get(
            f"/sessions/{session_id}", headers=headers("alice")
        ).json()
        self.assertEqual(after_greeting["active_narrative"], "")
        self.assertEqual(after_greeting["title"], "New complaint")

        for casual_text in (
            "How are you?", "Who are you?", "Okay great", "I don't understand",
        ):
            casual = client.post(
                f"/sessions/{session_id}/messages", headers=headers("alice"),
                json={"text": casual_text},
            )
            self.assertEqual(casual.status_code, 200)
            self.assertIsNone(casual.json()["analysis_id"])
            self.assertEqual(
                casual.json()["assistant_message"]["structured"]["action"],
                "conversation",
            )
        after_small_talk = client.get(
            f"/sessions/{session_id}", headers=headers("alice")
        ).json()
        self.assertEqual(after_small_talk["active_narrative"], "")
        self.assertEqual(after_small_talk["title"], "New complaint")

        incident = client.post(
            f"/sessions/{session_id}/messages", headers=headers("alice"),
            json={"text": "SOMEONE STOLE MY PHONE FROM MY DESK WITHOUT CONSENT"},
        )
        self.assertEqual(incident.status_code, 200)
        self.assertEqual(
            incident.json()["assistant_message"]["structured"]["action"], "ask_question"
        )
        after_incident = client.get(
            f"/sessions/{session_id}", headers=headers("alice")
        ).json()
        self.assertEqual(
            after_incident["title"], "Someone stole my phone from my desk without consent"
        )

    def test_explicit_filing_request_opens_draft_without_repeating_analysis(self):
      with make_client(self.tmp_path) as client:
        owner = headers("alice")
        session_id = client.post("/sessions", headers=owner, json={"title": "New chat"}).json()["session_id"]
        client.post(f"/sessions/{session_id}/messages", headers=owner,
                    json={"text": "Someone stole my phone at college."})
        declined = client.post(f"/sessions/{session_id}/messages", headers=owner,
                               json={"text": "I don't want to file a complaint yet."})
        self.assertNotEqual(declined.json()["assistant_message"]["structured"]["action"], "review_draft")
        self.assertEqual(client.get("/drafts", headers=owner).json(), [])
        response = client.post(f"/sessions/{session_id}/messages", headers=owner,
                               json={"text": "I am Krishna Malhotra. Please prepare and register my complaint."})
        self.assertEqual(response.status_code, 200)
        structured = response.json()["assistant_message"]["structured"]
        self.assertEqual(structured["action"], "collect_draft_details")
        self.assertIn("When", structured["next_question"]["text"])
        self.assertIsNone(response.json()["analysis_id"])
        follow_up = client.post(f"/sessions/{session_id}/messages", headers=owner,
                                json={"text": "Yesterday"})
        structured = follow_up.json()["assistant_message"]["structured"]
        self.assertEqual(structured["action"], "review_draft")
        self.assertEqual(len(client.get("/drafts", headers=owner).json()), 1)
        self.assertEqual(client.get(f"/drafts/{structured['draft_id']}", headers=owner).json()["fields"]["reporter_name"], "Krishna Malhotra")
        self.assertEqual(client.get(f"/drafts/{structured['draft_id']}", headers=owner).json()["fields"]["incident_date"], "Yesterday")
        repeated = client.post(f"/sessions/{session_id}/messages", headers=owner,
                               json={"text": "Please prepare the report."})
        self.assertEqual(repeated.json()["assistant_message"]["structured"]["draft_id"], structured["draft_id"])

    def test_phone_report_intake_creates_clean_draft_and_where_is_report_reopens_it(self):
      with make_client(self.tmp_path) as client:
        owner = headers("krishna")
        session_id = client.post("/sessions", headers=owner, json={"title": "New chat"}).json()["session_id"]
        for text in (
            "Actually I lost my phone.",
            "I think someone stole my phone in the collage.",
            "Yes please prepare it for me",
            "my name is krishna",
            "29-09-2026",
            "maharaja surajmal college janakpuri delhi",
        ):
            reply = client.post(f"/sessions/{session_id}/messages", headers=owner, json={"text": text})
            self.assertEqual(reply.status_code, 200)
        structured = reply.json()["assistant_message"]["structured"]
        self.assertEqual(structured["action"], "review_draft")
        draft_id = structured["draft_id"]
        draft = client.get(f"/drafts/{draft_id}", headers=owner).json()
        self.assertEqual(draft["fields"]["reporter_name"], "Krishna")
        self.assertEqual(draft["fields"]["incident_date"], "29-09-2026")
        self.assertEqual(draft["fields"]["location"], "maharaja surajmal college janakpuri delhi")
        self.assertNotIn("Follow-up clarification", draft["fields"]["incident_description"])
        self.assertNotIn("Additional information", draft["fields"]["incident_description"])
        lookup = client.post(f"/sessions/{session_id}/messages", headers=owner,
                             json={"text": "where is the report??"}).json()
        self.assertEqual(lookup["assistant_message"]["structured"]["action"], "review_draft")
        self.assertEqual(lookup["assistant_message"]["structured"]["draft_id"], draft_id)
        self.assertEqual(len(client.get("/drafts", headers=owner).json()), 1)

    def test_reviewer_can_research_but_cannot_create_or_submit_complaints(self):
      with make_client(self.tmp_path, admin_access_token="reviewer-secret") as client:
        reviewer = {"Authorization": "Bearer reviewer-secret"}
        session_id = client.post("/sessions", headers=reviewer, json={"title": "Research"}).json()["session_id"]
        researched = client.post(f"/sessions/{session_id}/messages", headers=reviewer,
                                 json={"text": "Someone stole my phone at college."})
        self.assertEqual(researched.status_code, 200)
        self.assertEqual(researched.json()["assistant_message"]["structured"]["action"], "review_research")
        denied = client.post("/drafts", headers=reviewer, json={"session_id": session_id})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(client.post("/cases", headers=reviewer, json={
            "draft_id": "any", "reporter_role": "self", "declaration_accepted": True,
        }).status_code, 403)

    def test_skipped_name_is_not_treated_as_a_valid_reporter(self):
      with make_client(self.tmp_path) as client:
        owner = headers("alice")
        session_id = client.post("/sessions", headers=owner, json={"title": "New chat"}).json()["session_id"]
        client.post(f"/sessions/{session_id}/messages", headers=owner,
                    json={"text": "Someone stole my phone at college."})
        for text in ("Please prepare my complaint.", "I don't know", "Yesterday"):
            answer = client.post(f"/sessions/{session_id}/messages", headers=owner, json={"text": text})
        structured = answer.json()["assistant_message"]["structured"]
        self.assertEqual(structured["action"], "review_draft")
        draft = client.get(f"/drafts/{structured['draft_id']}", headers=owner).json()
        self.assertEqual(draft["fields"].get("reporter_name", ""), "")
        confirmed = client.post(f"/drafts/{draft['draft_id']}/confirm", headers=owner,
                                json={"expected_version": draft["version"], "explicit_confirmation": True}).json()
        blocked = client.post("/cases", headers=owner, json={
            "draft_id": confirmed["draft_id"], "reporter_role": "self", "declaration_accepted": True,
        })
        self.assertEqual(blocked.status_code, 422)

    def test_public_demo_mode_requires_random_shared_token(self):
      with make_client(self.tmp_path, demo_access_token="long-random-test-secret") as client:
        rejected = client.post(
            "/sessions", headers=headers("alice"), json={"title": "Rejected"}
        )
        self.assertEqual(rejected.status_code, 401)
        accepted = client.post(
            "/sessions",
            headers={
                "Authorization": "Bearer long-random-test-secret",
                "X-LegalAI-Demo-User": "krishna",
            },
            json={"title": "Accepted"},
        )
        self.assertEqual(accepted.status_code, 201)
        impersonation = client.get(
            "/sessions",
            headers={"Authorization": "Bearer long-random-test-secret", "X-LegalAI-Demo-User": "alice"},
        )
        self.assertEqual(impersonation.status_code, 401)


    def test_draft_edit_confirm_and_delete_are_versioned(self):
      with make_client(self.tmp_path) as client:
        session_id = client.post(
            "/sessions", headers=headers("alice"), json={"title": "Draft"}
        ).json()["session_id"]
        client.post(
            f"/sessions/{session_id}/messages", headers=headers("alice"),
            json={"text": "Someone stole my phone."},
        )
        draft = client.post(
            "/drafts", headers=headers("alice"),
            json={"session_id": session_id, "details": {"reporter_name": "Alice"}},
        )
        self.assertEqual(draft.status_code, 201)
        draft_id = draft.json()["draft_id"]

        edited = client.patch(
            f"/drafts/{draft_id}", headers=headers("alice"),
            json={"expected_version": 1, "changes": {"contact": "alice@example.test"}},
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["version"], 2)
        self.assertEqual(edited.json()["status"], "preview")

        stale = client.post(
            f"/drafts/{draft_id}/confirm", headers=headers("alice"),
            json={"expected_version": 1, "explicit_confirmation": True},
        )
        self.assertEqual(stale.status_code, 409)

        saved = client.post(
            f"/drafts/{draft_id}/confirm", headers=headers("alice"),
            json={"expected_version": 2, "explicit_confirmation": True},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["status"], "saved")
        self.assertTrue(saved.json()["internal_reference"].startswith("LAI-"))
        self.assertIn("not an FIR", saved.json()["filing_notice"])

        removed = client.delete(f"/drafts/{draft_id}", headers=headers("alice"))
        self.assertEqual(removed.status_code, 204)


    def test_legally_relevant_edit_requires_reanalysis(self):
      with make_client(self.tmp_path) as client:
        session_id = client.post(
            "/sessions", headers=headers("alice"), json={"title": "Edit"}
        ).json()["session_id"]
        client.post(
            f"/sessions/{session_id}/messages", headers=headers("alice"),
            json={"text": "Someone stole my phone."},
        )
        draft = client.post(
            "/drafts", headers=headers("alice"), json={"session_id": session_id}
        ).json()
        changed = client.patch(
            f"/drafts/{draft['draft_id']}", headers=headers("alice"),
            json={"expected_version": 1, "changes": {"incident_description": "Nobody stole anything."}},
        ).json()
        self.assertEqual(changed["status"], "needs_reanalysis")
        blocked = client.post(
            f"/drafts/{draft['draft_id']}/confirm", headers=headers("alice"),
            json={"expected_version": 2, "explicit_confirmation": True},
        )
        self.assertEqual(blocked.status_code, 409)

    def test_case_submission_review_messages_evidence_and_archive(self):
      with make_client(self.tmp_path, admin_access_token="reviewer-secret") as client:
        owner = headers("alice")
        reviewer = {"Authorization": "Bearer reviewer-secret"}
        session_id = client.post("/sessions", headers=owner, json={"title": "Phone"}).json()["session_id"]
        client.post(f"/sessions/{session_id}/messages", headers=owner,
                    json={"text": "Someone stole my phone at college."})
        draft = client.post("/drafts", headers=owner,
                            json={"session_id": session_id, "details": {"reporter_name": "Alice"}}).json()
        draft = client.post(f"/drafts/{draft['draft_id']}/confirm", headers=owner,
                            json={"expected_version": 1, "explicit_confirmation": True}).json()
        missing_affected_person = client.post("/cases", headers=owner,
                             json={"draft_id": draft["draft_id"], "reporter_role": "on_behalf",
                                   "reporter_relationship": "Parent", "declaration_accepted": True})
        self.assertEqual(missing_affected_person.status_code, 422)
        result = client.post("/cases", headers=owner,
                             json={"draft_id": draft["draft_id"], "reporter_role": "self",
                                   "declaration_accepted": True})
        self.assertEqual(result.status_code, 201)
        case_id = result.json()["case_id"]
        self.assertIn("internal review only", result.json()["filing_notice"])
        self.assertEqual(client.get(f"/cases/{case_id}", headers=headers("bob")).status_code, 404)
        self.assertEqual(client.get("/review/cases", headers=owner).status_code, 403)
        self.assertEqual(len(client.get("/review/cases", headers=reviewer).json()), 1)
        decision = client.post(f"/review/cases/{case_id}/decision", headers=reviewer,
                               json={"action": "request_information",
                                     "reason": "Please tell us where the phone was last seen."})
        self.assertEqual(decision.json()["status"], "information_requested")
        self.assertEqual(client.post(f"/cases/{case_id}/messages", headers=owner,
                                     json={"text": "It was in the library."}).status_code, 201)
        after_reply = client.get(f"/cases/{case_id}", headers=owner).json()
        self.assertEqual(after_reply["status"], "under_review")
        evidence = client.post(f"/cases/{case_id}/evidence", headers=owner,
                               json={"filename": "note.pdf", "content_type": "application/pdf",
                                     "data_base64": "JVBERi0xLjQK"})
        self.assertEqual(evidence.status_code, 201)
        history = client.get(f"/cases/{case_id}", headers=owner).json()
        self.assertEqual(len(history["messages"]), 1)
        self.assertEqual(len(history["evidence"]), 1)
        closed = client.post(f"/review/cases/{case_id}/decision", headers=reviewer,
                             json={"action": "close", "reason": "The internal review is complete."})
        self.assertEqual(closed.json()["status"], "closed")
        requested = client.post(f"/cases/{case_id}/review-request", headers=owner,
                                json={"reason": "I have new evidence about where my phone was last seen."})
        self.assertEqual(requested.status_code, 200)
        self.assertEqual(requested.json()["status"], "under_review")
        self.assertEqual(client.post(f"/cases/{case_id}/review-request", headers=owner,
                                     json={"reason": "Again with no closure yet."}).status_code, 409)
        self.assertEqual(client.delete(f"/drafts/{draft['draft_id']}", headers=owner).status_code, 409)
        removed = client.delete(f"/sessions/{session_id}", headers=owner)
        self.assertEqual(removed.json()["outcome"], "archived")
        self.assertEqual(len(client.get("/cases", headers=owner).json()), 1)
        self.assertEqual(client.get(f"/sessions/{session_id}", headers=owner).status_code, 200)


if __name__ == "__main__":
    unittest.main()
