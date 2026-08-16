"""Outbound email.

ADR 0001 removed the mailpit container, so the local driver writes RFC-822
`.eml` files to `.mail/`. M3's verification flow is then testable end to end with
no external provider and no account.

Note for later: doc 06 §4.10 restricts the morning brief to workspace users and
requires per-recipient scope resolution at send time. That rule belongs to the
brief, not to this transport — but any future caller should be aware that
delivering to a free-text address is not a decision this module may make.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None


class Mailer(ABC):
    @abstractmethod
    def send(self, message: Email) -> str:
        """Send, returning a provider message id."""


def _build(message: Email, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = message.to
    msg["Subject"] = message.subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = f"<{uuid.uuid4().hex}@nexusos.local>"
    msg.set_content(message.text_body)
    if message.html_body:
        msg.add_alternative(message.html_body, subtype="html")
    return msg


class FileMailer(Mailer):
    """Writes each message to disk instead of sending it."""

    def __init__(self, root: Path, sender: str = "NEXUS OS <no-reply@nexusos.local>") -> None:
        self._root = root
        self._sender = sender
        self._root.mkdir(parents=True, exist_ok=True)

    def send(self, message: Email) -> str:
        msg = _build(message, self._sender)
        message_id = str(msg["Message-ID"])
        # Timestamp-prefixed so the directory reads in send order.
        name = f"{formatdate(localtime=True)[:25].replace(' ', '_').replace(':', '')}-{uuid.uuid4().hex[:8]}.eml"
        (self._root / name).write_bytes(bytes(msg))
        return message_id

    def sent_messages(self) -> list[Path]:
        """Test and debug helper — the local equivalent of opening mailpit."""
        return sorted(self._root.glob("*.eml"))
