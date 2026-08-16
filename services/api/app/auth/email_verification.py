"""Email verification.

Tokens are hashed at rest and single-use, for the same reason session tokens
are: a leaked database must not yield working verification links, and a consumed
link must not verify a second account.

The flow is deliberately silent about whether an address exists. `POST /register`
already returns the same body either way (M1), so the *email itself* is what
tells the real owner what happened — including telling them if someone else
tried to register their address.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import hash_token, new_token
from app.mail import Email, Mailer

TOKEN_TTL = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class IssuedVerification:
    token: str
    expires_at: datetime


async def issue(
    db: AsyncSession, *, user_id: UUID, email: str, ttl: timedelta = TOKEN_TTL
) -> IssuedVerification:
    token = new_token()
    expires_at = datetime.now(UTC) + ttl

    # Supersede any outstanding token so a forwarded old email stops working.
    await db.execute(
        text(
            "UPDATE email_verification SET consumed_at = now()"
            " WHERE user_id = :u AND consumed_at IS NULL"
        ),
        {"u": str(user_id)},
    )
    await db.execute(
        text(
            "INSERT INTO email_verification (user_id, token_hash, email, expires_at)"
            " VALUES (:u, :h, :e, :x)"
        ),
        {"u": str(user_id), "h": hash_token(token), "e": email.strip().lower(), "x": expires_at},
    )
    return IssuedVerification(token=token, expires_at=expires_at)


async def consume(db: AsyncSession, *, token: str) -> UUID | None:
    """Verify and burn a token. Returns the user id, or None.

    The update is conditional and returns the row, so two simultaneous clicks
    cannot both succeed — the database decides, not our read-then-write.
    """
    row = (
        await db.execute(
            text(
                "UPDATE email_verification SET consumed_at = now()"
                " WHERE token_hash = :h AND consumed_at IS NULL AND expires_at > now()"
                " RETURNING user_id, email"
            ),
            {"h": hash_token(token)},
        )
    ).first()

    if row is None:
        return None

    user_id = UUID(str(row.user_id))
    await db.execute(
        text(
            "UPDATE app_user SET email_verified_at = now()"
            " WHERE id = :u AND email_verified_at IS NULL"
        ),
        {"u": str(user_id)},
    )
    return user_id


def build_email(*, to: str, token: str, base_url: str) -> Email:
    link = f"{base_url.rstrip('/')}/verify-email?token={token}"
    return Email(
        to=to,
        subject="Confirm your email for NEXUS OS",
        text_body=(
            "Confirm your email address to finish setting up NEXUS OS.\n\n"
            f"{link}\n\n"
            "This link works once and expires in 24 hours.\n\n"
            "If you did not create this account, you can ignore this email — "
            "nothing has been set up in your name."
        ),
    )


async def send_verification(
    db: AsyncSession, mailer: Mailer, *, user_id: UUID, email: str, base_url: str
) -> None:
    issued = await issue(db, user_id=user_id, email=email)
    mailer.send(build_email(to=email, token=issued.token, base_url=base_url))
