"""The invitation email.

Invitations returned a link and sent nothing. The docstring on `IssuedOut` said
delivery "is not wired up anywhere in the product" — true when it was written
and stale since P3, which built the mailer and proved the whole verification
chain through it.

Handing the link back to the inviter stays, and is not redundant: an owner who
wants to paste it into a chat should be able to. But a product whose answer to
"add someone to your company" is "copy this string and send it yourself" has
made the customer the mail transport.

**The link is the company.** The token names the workspace and the role, so the
person accepting never chooses a company and structurally cannot choose the
wrong one — which is what makes the invitation safe to send to an address that
has no account yet.
"""

from __future__ import annotations

from app.mail import Email


def build_invitation_email(
    *, to: str, token: str, base_url: str, company: str, inviter: str | None = None
) -> Email:
    link = f"{base_url.rstrip('/')}/invitations/accept?token={token}"
    who = f"{inviter} has invited you" if inviter else "You have been invited"
    return Email(
        to=to,
        # The company is in the subject because an invitation that does not say
        # which company it is for reads as phishing, and the recipient may hold
        # accounts at several.
        subject=f"{who} to join {company} on NEXUS OS",
        text_body=(
            f"{who} to join {company} on NEXUS OS.\n\n"
            f"{link}\n\n"
            "The link already knows which company and which department you are "
            "joining, so there is nothing to choose.\n\n"
            "If you do not have an account yet, you will be asked to create one "
            "first — use this same address.\n\n"
            "If you were not expecting this, you can ignore it. Nothing is "
            "created in your name until you open the link."
        ),
    )
