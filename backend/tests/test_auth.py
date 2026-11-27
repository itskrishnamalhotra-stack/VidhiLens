from __future__ import annotations

import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from app.auth import authenticated_user
from app.config import Settings


class FirebaseRolesTest(unittest.IsolatedAsyncioTestCase):
    async def principal(self, claims):
        firebase = types.ModuleType("firebase_admin")
        auth = types.ModuleType("firebase_admin.auth")
        firebase.get_app = lambda: object()
        auth.verify_id_token = lambda token, check_revoked: claims
        firebase.auth = auth
        settings = Settings(
            auth_mode="firebase",
            firebase_project_id="nyayasetu-legal-ai-km",
            reviewer_emails=("its.krishnamalhotra@gmail.com",),
        )
        request = Request({
            "type": "http",
            "headers": [(b"authorization", b"Bearer test-token")],
            "app": SimpleNamespace(state=SimpleNamespace(settings=settings)),
        })
        with patch.dict(sys.modules, {"firebase_admin": firebase, "firebase_admin.auth": auth}):
            return await authenticated_user(request)

    async def test_verified_google_reviewer_is_admin(self):
        principal = await self.principal({
            "uid": "reviewer-uid", "aud": "nyayasetu-legal-ai-km",
            "email": "Its.KrishnaMalhotra@gmail.com", "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        })
        self.assertTrue(principal.is_admin)
        self.assertEqual(principal.uid, "reviewer-uid")

    async def test_other_google_user_is_citizen(self):
        principal = await self.principal({
            "uid": "citizen-uid", "aud": "nyayasetu-legal-ai-km",
            "email": "citizen@example.com", "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        })
        self.assertFalse(principal.is_admin)
        self.assertEqual(principal.uid, "citizen-uid")

    async def test_unverified_or_anonymous_account_is_rejected(self):
        for claims in (
            {"uid": "u1", "aud": "nyayasetu-legal-ai-km", "email": "its.krishnamalhotra@gmail.com",
             "email_verified": False, "firebase": {"sign_in_provider": "google.com"}},
            {"uid": "u2", "aud": "nyayasetu-legal-ai-km", "firebase": {"sign_in_provider": "anonymous"}},
        ):
            with self.assertRaises(HTTPException) as result:
                await self.principal(claims)
            self.assertEqual(result.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
