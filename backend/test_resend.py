from __future__ import annotations

import os
import sys

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()

    api_key = str(os.getenv("RESEND_API_KEY", "")).strip()
    from_email = str(os.getenv("RESEND_FROM_EMAIL", "")).strip()
    to_email = str(os.getenv("RESEND_TEST_TO_EMAIL", "")).strip()

    missing = [
        name
        for name, value in (
            ("RESEND_API_KEY", api_key),
            ("RESEND_FROM_EMAIL", from_email),
            ("RESEND_TEST_TO_EMAIL", to_email),
        )
        if not value
    ]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}")
        return 1

    try:
        import resend
    except ImportError:
        print("The 'resend' package is not installed. Run: pip install -r requirements.txt")
        return 1

    resend.api_key = api_key

    response = resend.Emails.send(
        {
            "from": from_email,
            "to": [to_email],
            "subject": "Volunteer Managing Resend smoke test",
            "html": "<strong>Resend is configured correctly.</strong>",
            "text": "Resend is configured correctly.",
        }
    )
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
