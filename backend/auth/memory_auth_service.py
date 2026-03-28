from __future__ import annotations

from typing import Any

from auth.base import AuthError, AuthService


class MemoryAuthService(AuthService):
    mode = "memory"

    def __init__(self) -> None:
        self._accounts = [
            {
                "id": "admin",
                "label": "Admin User",
                "email": "super@example.org",
                "description": "Full admin access",
            },
            {
                "id": "lead",
                "label": "Pantry Lead",
                "email": "courtney@licking-county-pantry.org",
                "description": "Pantry lead access",
            },
            {
                "id": "volunteer",
                "label": "Volunteer",
                "email": "alice@volunteer.org",
                "description": "Volunteer shift signup flow",
            },
        ]

    def get_client_config(self) -> dict[str, Any]:
        return {
            "provider": self.mode,
            "memory_accounts": self.list_memory_accounts(),
        }

    def verify_google_token(self, id_token: str) -> Any:
        raise AuthError("Google sign-in is unavailable in memory auth mode", 400, "GOOGLE_AUTH_DISABLED")

    def list_memory_accounts(self) -> list[dict[str, Any]]:
        return [dict(account) for account in self._accounts]

    def resolve_memory_account(self, sample_account_id: str) -> dict[str, Any]:
        for account in self._accounts:
            if account["id"] == sample_account_id:
                return dict(account)
        raise AuthError("Unknown sample account", 404, "MEMORY_ACCOUNT_NOT_FOUND")
