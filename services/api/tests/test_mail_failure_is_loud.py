"""A failed send is loud in the log and silent to the caller.

The failure this prevents: SMTP credentials expire, `background.add_task`
swallows the exception, FastAPI has already returned "check your email", and
nothing anywhere says why. Every new account is stuck unverified and the first
signal is a support message a week later.
"""

from __future__ import annotations

import pytest

from app.mail import Email, Mailer, send_safely


class Broken(Mailer):
    def send(self, message: Email) -> str:
        raise OSError("[Errno 61] Connection refused")


class Working(Mailer):
    def __init__(self) -> None:
        self.sent: list[Email] = []

    def send(self, message: Email) -> str:
        self.sent.append(message)
        return "id-1"


MESSAGE = Email(to="someone@example.om", subject="Confirm your email", text_body="link")


def test_a_failure_does_not_escape_the_background_task() -> None:
    """Re-raising would produce an unhandled-task warning naming the framework
    rather than the problem — and there is nobody left to tell either way."""
    assert send_safely(Broken(), MESSAGE) is None


def test_a_failure_is_logged_with_enough_to_diagnose(
    capfd: pytest.CaptureFixture[str],
) -> None:
    """`capfd`, not `caplog`: structlog writes to the stream directly rather
    than through stdlib handlers, so `caplog` sees nothing while the line is
    plainly on stderr. A test asserting on `caplog` here would pass the day
    somebody removed the logging entirely."""
    send_safely(Broken(), MESSAGE)
    output = capfd.readouterr()
    combined = output.out + output.err

    assert "mail.send_failed" in combined
    assert "Connection refused" in combined, "the operator needs the actual error"


def test_the_recipient_is_not_logged_but_its_domain_is(
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Which addresses receive mail from us is the membership fact the whole
    anti-enumeration design protects — a log line naming them undoes it for
    anybody with log access.

    The domain is enough to tell "our SMTP is down" from "that one corporate
    mail server rejects us", which is the question an operator actually has.
    """
    send_safely(Broken(), MESSAGE)
    output = capfd.readouterr()
    combined = output.out + output.err

    assert "someone@example.om" not in combined
    assert "someone" not in combined
    assert "example.om" in combined


def test_a_successful_send_still_returns_its_id() -> None:
    mailer = Working()
    assert send_safely(mailer, MESSAGE) == "id-1"
    assert mailer.sent == [MESSAGE]
