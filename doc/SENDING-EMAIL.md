# Sending email

Three states, and the product supports all three deliberately.

| Where | Backend | What happens |
|---|---|---|
| **Local dev** | `file` | Written to `.mail/` as `.eml`. Nothing is sent. |
| **CI** | `smtp` → Mailpit | Really sent, over STARTTLS, to a sink the E2E job reads. |
| **Production** | `smtp` → **a provider you choose** | Not configured. This is **D4**. |

## Why nothing has reached your inbox

Local is on the `file` backend. Every verification link and invitation from
every walkthrough is sitting in `.mail/` — real, correct, and undelivered. That
is the intended local behaviour, not a bug: it lets the whole verification chain
be exercised with no provider and no credentials (ADR 0011's pattern).

To read the most recent one:

```bash
ls -t .mail/*.eml | head -1 | xargs cat
```

## To send real email locally

Add these to `.env`. **Never commit them** — `.env` is gitignored and the secret
scanner runs on every push.

```
NEXUS_MAILER_BACKEND=smtp
NEXUS_SMTP_HOST=smtp.gmail.com
NEXUS_SMTP_PORT=587
NEXUS_SMTP_USERNAME=parulbhoite315@gmail.com
NEXUS_SMTP_PASSWORD=<a Google app password, not your account password>
NEXUS_SMTP_FROM=NEXUS OS <parulbhoite315@gmail.com>
NEXUS_SMTP_TLS=true
```

Gmail needs an **app password** (Google Account → Security → 2-Step
Verification → App passwords). Your normal password will be rejected, and
putting it here would give the application your whole Google account rather than
one narrow capability.

Restart the API and register an account. The link arrives in the real inbox.

## For production, pick a provider (D4)

Gmail SMTP is fine for testing and wrong for production: it rate-limits, it
sends from a personal identity, and mail from it to strangers lands in spam.
A transactional provider — Resend, Postmark, SES — gives you a verified sending
domain, delivery logs and bounce handling. The application needs no code change:
they all speak SMTP, and only the five variables above differ.

`NEXUS_ENV=production` **refuses the `file` backend outright**, so a deployment
cannot accidentally ship with mail going to a directory nobody reads.

## What a failure looks like now

A send that fails is logged as `mail.send_failed` with the error and the
recipient's **domain** — never the address, because which addresses receive mail
from us is the membership fact the anti-enumeration design protects. The domain
is enough to tell "our SMTP is down" from "that one corporate server rejects us".

Before this, a failure was swallowed by the background task: the user saw "check
your email", nothing arrived, and nothing anywhere said why.
