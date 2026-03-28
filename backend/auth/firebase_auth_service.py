from __future__ import annotations

import os
from typing import Any

from auth.base import AuthError, AuthService, IdentityPayload


class FirebaseAuthService(AuthService):
    mode = "firebase"

    def __init__(self) -> None:
        self._client_config = {
            "apiKey": os.getenv("FIREBASE_API_KEY", "").strip(),
            "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", "").strip(),
            "projectId": os.getenv("FIREBASE_PROJECT_ID", "").strip(),
            "appId": os.getenv("FIREBASE_APP_ID", "").strip(),
        }
        self._admin_credentials = os.getenv("FIREBASE_ADMIN_CREDENTIALS", "").strip()
        self._firebase_auth = self._initialize_admin_auth()

    def _initialize_admin_auth(self) -> Any:
        missing = [key for key, value in self._client_config.items() if not value]
        if missing:
            raise RuntimeError(f"Missing Firebase client configuration: {', '.join(missing)}")
        if not self._admin_credentials:
            raise RuntimeError("Missing FIREBASE_ADMIN_CREDENTIALS")

        try:
            import firebase_admin
            from firebase_admin import auth as firebase_auth
            from firebase_admin import credentials
        except ImportError as exc:
            raise RuntimeError("firebase-admin is required for AUTH_PROVIDER=firebase") from exc

        if not firebase_admin._apps:
            credential = credentials.Certificate(self._admin_credentials)
            firebase_admin.initialize_app(credential)
        return firebase_auth

    def get_client_config(self) -> dict[str, Any]:
        return {
            "provider": self.mode,
            "firebase": dict(self._client_config),
        }

    def verify_google_token(self, id_token: str) -> IdentityPayload:
        token = str(id_token or "").strip()
        if not token:
            raise AuthError("Missing Firebase ID token", 400, "MISSING_ID_TOKEN")

        try:
            decoded = self._firebase_auth.verify_id_token(token)
        except Exception as exc:
            raise AuthError("Invalid or expired Firebase ID token", 401, "INVALID_ID_TOKEN") from exc

        email = str(decoded.get("email", "")).strip().lower()
        firebase_uid = str(decoded.get("uid", "")).strip()
        email_verified = bool(decoded.get("email_verified"))
        display_name = decoded.get("name")

        if not email or not firebase_uid:
            raise AuthError("Firebase token did not include a valid email identity", 400, "INVALID_IDENTITY")
        if not email_verified:
            raise AuthError("Google account email must be verified", 403, "EMAIL_NOT_VERIFIED")

        return IdentityPayload(
            provider="firebase",
            provider_user_id=firebase_uid,
            email=email,
            email_verified=email_verified,
            display_name=str(display_name).strip() if display_name else None,
        )

    def list_memory_accounts(self) -> list[dict[str, Any]]:
        return []

    def resolve_memory_account(self, sample_account_id: str) -> dict[str, Any]:
        raise AuthError("Memory login is unavailable in firebase auth mode", 400, "MEMORY_AUTH_DISABLED")
