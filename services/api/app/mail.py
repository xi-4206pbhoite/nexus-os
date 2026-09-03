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

import smtplib
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path

from app.config import Settings
from app.logging import get_logger

log = get_logger(__name__)


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
        # Sortable UTC prefix so the directory reads in send order.
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        name = f"{stamp}-{uuid.uuid4().hex[:8]}.eml"
        (self._root / name).write_bytes(bytes(msg))
        return message_id

    def sent_messages(self) -> list[Path]:
        """Test and debug helper — the local equivalent of opening mailpit."""
        return sorted(self._root.glob("*.eml"))


class SmtpMailer(Mailer):
    """Sends over SMTP. `doc/11` settled the transport; D4 settles the provider.

    Synchronous, and called from a background task rather than from a request
    (`app/routes/auth.py`). That is not a convenience: a reset request that
    waits for a relay takes measurably longer for a real address than for one
    with no account, which turns an endpoint built to reveal nothing into a
    timing oracle for whether an account exists.

    STARTTLS by default and non-optional in a deployed environment — see the
    validator in `config.py`. Without it the username, the password and every
    single-use token in the body cross the network in clear text.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        use_tls: bool,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._use_tls = use_tls
        self._timeout = timeout_seconds

    def send(self, message: Email) -> str:
        msg = _build(message, self._sender)
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(msg)
        # The recipient is not logged. Which addresses receive mail from us is
        # the membership fact the whole anti-enumeration design protects.
        log.info("mail.sent", transport="smtp", subject=message.subject)
        return str(msg["Message-ID"])


def build_mailer(settings: Settings) -> Mailer:
    """Select the transport. Unknown values raise rather than defaulting.

    Falling back to `FileMailer` on a typo would put a deployed environment into
    the state where every email is written to a directory nobody reads — silent,
    and indistinguishable from a working system until a customer says nobody
    received anything. `config.py` already refuses `file` outside local and ci;
    this refuses a value that is neither.
    """
    if settings.mailer_backend == "file":
        return FileMailer(settings.mail_root, sender=settings.smtp_from)
    if settings.mailer_backend == "smtp":
        return SmtpMailer(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password.get_secret_value(),
            sender=settings.smtp_from,
            use_tls=settings.smtp_tls,
        )
    raise ValueError(
        f"NEXUS_MAILER_BACKEND={settings.mailer_backend!r} is not a transport. "
        "Use 'file' (local and ci) or 'smtp'."
    )
