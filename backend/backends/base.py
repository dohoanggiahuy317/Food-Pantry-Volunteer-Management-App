from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StoreBackend(ABC):
    @abstractmethod
    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def get_user_roles(self, user_id: int) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def list_users(self, role_filter: str | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_roles(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def create_user(
        self,
        full_name: str,
        email: str,
        password_hash: str,
        is_active: bool,
        roles: list[str],
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_pantries(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_pantry_by_id(self, pantry_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def get_pantry_by_slug(self, slug: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def get_pantry_leads(self, pantry_id: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def is_pantry_lead(self, pantry_id: int, user_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def create_pantry(self, name: str, location_address: str, lead_ids: list[int]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def add_pantry_lead(self, pantry_id: int, user_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def remove_pantry_lead(self, pantry_id: int, user_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_shifts_by_pantry(self, pantry_id: int, include_cancelled: bool = True) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_shift_by_id(self, shift_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def create_shift(
        self,
        pantry_id: int,
        shift_name: str,
        start_time: str,
        end_time: str,
        status: str,
        created_by: int,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def update_shift(self, shift_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def delete_shift(self, shift_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_shift_roles(self, shift_id: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_shift_role_by_id(self, shift_role_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def create_shift_role(self, shift_id: int, role_title: str, required_count: int) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def update_shift_role(self, shift_role_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def delete_shift_role(self, shift_role_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_shift_signups(self, shift_role_id: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_signups_by_user(self, user_id: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_signup_by_id(self, signup_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def create_signup(self, shift_role_id: int, user_id: int, signup_status: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def delete_signup(self, signup_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_signup(self, signup_id: int, signup_status: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def is_empty(self) -> bool:
        raise NotImplementedError
