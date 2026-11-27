from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from .config import Settings


@dataclass(frozen=True, slots=True)
class Principal:
    uid: str
    auth_mode: str
    is_admin: bool = False
    phone_number: str | None = None


_DEV_UID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _bearer_token(request: Request) -> str:
    value = request.headers.get("authorization", "")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    return token.strip()


async def authenticated_user(request: Request) -> Principal:
    settings: Settings = request.app.state.settings
    token = _bearer_token(request)
    if settings.auth_mode == "dev":
        if settings.admin_access_token and secrets.compare_digest(token, settings.admin_access_token):
            return Principal(uid="reviewer", auth_mode="dev", is_admin=True)
        if settings.demo_access_token:
            if not secrets.compare_digest(token, settings.demo_access_token):
                raise HTTPException(status_code=401, detail="Invalid demonstration access token")
            uid = request.headers.get("x-legalai-demo-user", "krishna").strip()
            if uid != "krishna":
                raise HTTPException(status_code=401, detail="This private demonstration token belongs to Krishna")
            return Principal(uid="krishna", auth_mode="dev")
        uid = token.removeprefix("dev:")
        if not _DEV_UID.fullmatch(uid):
            raise HTTPException(status_code=401, detail="Invalid development user token")
        return Principal(uid=uid, auth_mode="dev")

    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth
    except ImportError as error:
        raise HTTPException(
            status_code=503,
            detail="Firebase authentication is configured but firebase-admin is not installed",
        ) from error
    try:
        try:
            firebase_admin.get_app()
        except ValueError:
            options = {"projectId": settings.firebase_project_id} if settings.firebase_project_id else None
            firebase_admin.initialize_app(options=options)
        claims = firebase_auth.verify_id_token(token, check_revoked=True)
    except Exception as error:
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase ID token") from error
    uid = claims.get("uid") or claims.get("sub")
    if not isinstance(uid, str) or not uid:
        raise HTTPException(status_code=401, detail="Firebase token has no user ID")
    if settings.firebase_project_id:
        audience = claims.get("aud")
        if audience != settings.firebase_project_id:
            raise HTTPException(status_code=401, detail="Firebase token is for another project")
    email = claims.get("email")
    provider = claims.get("firebase", {}).get("sign_in_provider") if isinstance(claims.get("firebase"), dict) else None
    if not isinstance(email, str) or claims.get("email_verified") is not True or provider != "google.com":
        raise HTTPException(status_code=403, detail="Sign in with a verified Google account")
    is_admin = email.strip().lower() in settings.reviewer_emails
    return Principal(
        uid=uid, auth_mode="firebase",
        is_admin=is_admin,
        phone_number=claims.get("phone_number") if isinstance(claims.get("phone_number"), str) else None,
    )
