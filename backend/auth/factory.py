from __future__ import annotations

import os

from auth.base import AuthService
from auth.firebase_auth_service import FirebaseAuthService
from auth.memory_auth_service import MemoryAuthService


def create_auth_service() -> AuthService:
    provider = os.getenv("AUTH_PROVIDER", "memory").strip().lower()
    if provider == "firebase":
        return FirebaseAuthService()
    return MemoryAuthService()
