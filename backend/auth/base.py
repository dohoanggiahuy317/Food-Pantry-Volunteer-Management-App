from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


AuthMode = str


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


@dataclass(frozen=True)
class IdentityPayload:
    provider: str
    email: str
    email_verified: bool
    display_name: str | None = None


class AuthService(ABC):
    mode: AuthMode

    @abstractmethod
    def get_client_config(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def verify_google_token(self, id_token: str) -> IdentityPayload:
        raise NotImplementedError

    @abstractmethod
    def list_memory_accounts(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def resolve_memory_account(self, sample_account_id: str) -> dict[str, Any]:
        raise NotImplementedError
