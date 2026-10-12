"""Notifications. For now emails are not sent; they are collected in an outbox you can look at
(GET /dev/outbox) and printed to the console. Later: send real email (Gmail API or SMTP).
Calendar updates to attendees are NOT sent by us: the calendar itself does that.
"""
from __future__ import annotations

from datetime import datetime

OUTBOX: list[dict] = []


def send_email(to: str, subject: str, body: str, now: datetime) -> None:
    msg = {"to": to, "subject": subject, "body": body, "at": now.isoformat()}
    OUTBOX.append(msg)
    print(f"[email] to={to} subject={subject}")


def clear() -> None:
    OUTBOX.clear()
