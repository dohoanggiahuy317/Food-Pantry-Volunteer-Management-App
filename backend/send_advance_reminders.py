from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

from dotenv import load_dotenv

from backends.factory import create_backend
from notifications import build_signup_action_url, send_advance_action_reminder

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    backend = create_backend()
    now = datetime.now(timezone.utc)
    window_start = (now + timedelta(hours=23, minutes=30)).isoformat().replace("+00:00", "Z")
    window_end = (now + timedelta(hours=24, minutes=30)).isoformat().replace("+00:00", "Z")
    secret_key = os.getenv("FLASK_SECRET_KEY", "volunteer-managing-dev-secret")

    sent = 0
    candidates = backend.list_advance_reminder_candidates(window_start, window_end)
    for candidate in candidates:
        recipient = {
            "user_id": candidate["user_id"],
            "full_name": candidate["full_name"],
            "email": candidate["email"],
        }
        shift = {
            "shift_id": candidate["shift_id"],
            "shift_name": candidate["shift_name"],
            "start_time": candidate["start_time"],
            "end_time": candidate["end_time"],
        }
        pantry = {
            "pantry_id": candidate["pantry_id"],
            "name": candidate["pantry_name"],
            "location_address": candidate["location_address"],
        }
        role = {
            "shift_role_id": candidate["shift_role_id"],
            "role_title": candidate["role_title"],
        }
        confirm_url = build_signup_action_url(int(candidate["signup_id"]), "CONFIRM", secret_key)
        cancel_url = build_signup_action_url(int(candidate["signup_id"]), "CANCEL", secret_key)
        if send_advance_action_reminder(recipient, shift, pantry, role, confirm_url, cancel_url):
            backend.mark_advance_reminder_sent(int(candidate["signup_id"]), utc_now_iso())
            sent += 1

    print({"candidates": len(candidates), "sent": sent})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
