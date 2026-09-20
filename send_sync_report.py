"""Send a completed GitHub Actions sync report via Resend when secrets exist."""
from __future__ import annotations

import os
from pathlib import Path

import requests


def main() -> None:
    api_key = os.environ.get("RESEND_API_KEY")
    recipient = os.environ.get("SYNC_REPORT_TO")
    sender = os.environ.get("SYNC_REPORT_FROM")
    if not all((api_key, recipient, sender)):
        print("Email skipped: RESEND_API_KEY, SYNC_REPORT_TO or SYNC_REPORT_FROM is not configured.")
        return
    report = Path("data/current/sync_report.md").read_text(encoding="utf-8")
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"from": sender, "to": [recipient], "subject": "ATP Power Ratings daily sync", "text": report},
        timeout=30,
    )
    response.raise_for_status()
    print("Daily sync email sent.")


if __name__ == "__main__":
    main()
