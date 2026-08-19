# ADR 0014 — Registration issues a session, at the cost of an enumeration oracle

- **Status:** Accepted
- **Date:** 18 August 2026
- **Decider:** Parul Bhoite ("if the email creds are not available, skip sending email for now and directly move to dashboard")
- **Supersedes:** the registration behaviour described in doc 07 M3

## Context

`POST /auth/register` answered `{"status": "check_your_email"}` for every request,
identical whether or not the address was already registered. That was deliberate:
a distinct "already registered" reply is a membership oracle, confirming which
addresses hold accounts here.

It was also, in practice, a dead end — and the failure is worth stating precisely,
because it was reproduced against the live API before anything was changed:

```
1. register with password A      -> 201 {"status":"check_your_email"}
2. re-register with password B   -> 201 {"status":"check_your_email"}   <- silently did nothing
3. login with password B         -> 401 Invalid email or password
4. login with password A         -> 200  but  workspaces: []
```

Three separate gaps compounded. **No email is ever sent** (task 3.1 — delivery was
never wired up), so "check your email" was advice nobody could follow. **A
duplicate registration is swallowed**, so step 2 looked like it worked and did not.
**There is no password reset anywhere in the codebase**, so after step 2 a user who
believed their password was B had no route back to the account at all.

Step 4 shows the second, separate problem this ADR does not solve: signing in
succeeded and still landed nowhere, because a workspace required a verified domain.
That is ADR 0013.

## Decision

**Registration creates the account and signs the caller straight in**, returning
the same `SessionResponse` login returns and setting the same two cookies.

A duplicate address is not special-cased into a friendly message. It falls through
to `authenticate`:

| Case | Result |
|---|---|
| New address | 201 with a session |
| Taken address, **same** password | 201 with a session — re-submitting the form is idempotent |
| Taken address, **different** password | 401, with login's exact wording |

**A local-only `POST /auth/dev/reset-password`** provides the missing way out of a
lockout. It refuses with **404, not 403**, outside `local`/`ci`: a 403 would confirm
that a route setting arbitrary passwords with no proof of ownership is deployed,
which is worth more to an attacker than the refusal costs them. Same reasoning
`routes/dashboards.py` applies to a department the caller does not hold.

## What this gives up

**An account-enumeration oracle, and it cannot be avoided.** A new address returns
201; a taken address with the wrong password returns 401. No amount of care hides
that difference while registration also ends in a usable session — the two outcomes
*are* different, because one of them has a session in it.

What survives is narrower and worth keeping: the 401 is byte-identical to login's,
so registration is never a *better* oracle than login. It cannot separate "exists
under another password" from "no such account", which is the distinction
`authenticate` refuses to make and equalises timing for.
`test_the_refusal_is_indistinguishable_from_login` asserts this by comparing the two
responses rather than by copying the string.

**The compensating control is login rate limiting, which does not exist yet.** It is
already open as **D14** in `DECISIONS-REQUIRED.md`, alongside the finding that argon2
blocks the event loop. Both are owed before this surface is public: without a rate
limit the oracle is not merely present, it is cheap.

## Consequences

- The register form's two explanatory panels — "Check your email" and "no email is
  actually sent yet" — are deleted rather than reworded. Both had become false.
- `_sign_in` in `routes/auth.py` is now shared by login and register, so the
  auto-select rule (only when exactly one membership, per doc 06 §2.1's agency case)
  cannot drift between them.
- **A real password-reset flow is still owed.** The dev endpoint is not one: no
  token, no expiry, no proof of address ownership. It is a development tool that
  refuses to be deployed, and it does not discharge the product requirement.
- `POST /auth/register` stays outside the CSRF guard, unchanged — an anonymous
  visitor has no CSRF cookie yet, and requiring one would make account creation
  impossible.

## Revisit when

Login rate limiting lands (D14), at which point the oracle's cost to an attacker
should be measured rather than assumed. Also when a production email provider is
chosen (D4): verification becomes possible, and it should then gate *privileged*
actions rather than sign-in — blocking sign-in on it is what produced the dead end
this ADR removes.
