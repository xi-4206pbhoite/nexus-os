# 0065. The password minimum is eight characters, as one shared policy

- **Status:** Accepted
- **Date:** 3 October 2026
- **Deciders:** Parul (requested in session, onboarding pass)
- **Affects:** `services/api/app/auth/passwords.py` (`MIN_PASSWORD_LENGTH`, the
  authority), `services/api/app/routes/auth.py` (the `min_length` on register and
  password-reset-confirm), `apps/web/lib/auth-client.ts` (the client mirror),
  `apps/web/components/auth/RegisterForm.tsx` and
  `apps/web/components/auth/ResetPasswordForm.tsx` (what the forms say)

> The previous 12-character minimum was an undocumented constant, not a recorded
> decision, so there is no earlier ADR to supersede — this is the first time the
> password floor is written down.

## Context

The password floor was twelve characters. It lives in exactly one authoritative
place — `MIN_PASSWORD_LENGTH` in `app/auth/passwords.py`, checked by
`validate_password` and declared again as the Pydantic `Field(min_length=…)` on
both `/auth/register` and `/auth/password-reset/confirm`. The web app mirrors the
same constant in `auth-client.ts` purely so the form can refuse early; the comment
there says as much. So the policy is one number, enforced server-side and echoed
client-side, and it governs every place a password is set.

During the onboarding pass Parul asked to lower the register floor to eight, to cut
signup friction — twelve characters is a real stop on the first screen of the
product. Because the floor is a single shared constant that also governs the
password-reset flow, changing it is a policy decision rather than a per-screen copy
tweak, and it is an auth-mechanism change, so it is recorded here.

## Options considered

### A. Lower the one shared minimum to eight

One edit to `MIN_PASSWORD_LENGTH` (and its web mirror). Register and reset both
require eight. One policy, one number, no drift.

### B. A register-only minimum of eight, twelve kept elsewhere

A second constant so the signup screen is more permissive than the rest. Removes
friction exactly where it was reported, and keeps a longer floor for everything
else.

### C. Keep twelve

No change. Keeps the stronger floor and the friction that prompted the request.

## Decision

Option A. `MIN_PASSWORD_LENGTH` becomes eight, in the one authoritative place, and
the web mirror follows. Register and password-reset share the floor, as they did at
twelve. The upper bound (1024) and the argon2 cost parameters are untouched.

## Reasoning

**Eight is a weaker floor, and the account-security posture does not rest on length
alone — which is what makes the trade acceptable.** Passwords are argon2id-hashed;
login is account-enumeration-resistant and answers an identical 401 whatever the
counters say, with backoff rather than a 429 or a lockout (D14); the register
endpoint returns 201 for a new and a taken address alike. None of that changes with
the floor. What eight costs is entropy against an offline attacker who already has
the hash — a real but second-order risk behind the hashing and the rate limiting,
and the price of a signup screen people actually clear.

**B was rejected because a split floor is incoherent where the two screens meet.**
A person who sets an eight-character password at signup and is later told their
*new* password needs twelve at reset is being contradicted by the same product. A
second constant is also a second thing to keep in step with the first — the exact
drift this codebase already fights between its server value and its web mirror. The
friction B removes is removed by A too; the incoherence B adds is A's to avoid.

**C keeps the defect the request was about.** The floor was the friction.

The accompanying copy change — register no longer prints the "at least N
characters / a passphrase beats a short complicated one" hint, by the same request
— is a copy decision, not recorded here. It does mean the encouragement toward
passphrases is now gone from the screen, which is noted under consequences.

## Consequences

- The minimum acceptable password is now eight characters everywhere a password is
  set — register and password-reset both.
- The entropy floor is lower. Combined with the removal of the passphrase hint on
  register, the product no longer nudges users toward length at the point of
  choosing. There is no strength meter and no breach-list check; length was the
  only strength signal, and it is now shorter.
- The server stays the authority; the web mirror is advisory and must track it. The
  weak-password test asserts `MIN_PASSWORD_LENGTH - 1`, so it follows the constant
  rather than pinning the old number.
- The argon2 DoS ceiling (1024) and memory/time cost are unchanged — the lower
  bound moved, nothing else.

## Revisit trigger

Raise the floor again — or, better, add a real strength check (a breach-list lookup
or a zxcvbn-style estimator) rather than a longer raw minimum — if credential
stuffing or weak-password account takeovers show up in abuse signals, or if a
compliance or enterprise requirement mandates a specific minimum. A strength
estimator is the right answer at that point because it buys more than the same
number of extra characters would, and it is the thing length was standing in for.
