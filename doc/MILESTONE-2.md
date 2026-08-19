# Milestone 2 — Landing integration, URL capture, Preview audit

**Status:** ✅ complete — **ready for validation**
**Date:** 16 August 2026 · 267 tests · CI green
**Amended:** 17 August 2026 — the NAT64 gap below, found while bringing the real database up

Doc 07 M2: *"Done when a URL produces a reduced audit and every SSRF test case is blocked."*

---

## Acceptance

**Both met.** 79 SSRF cases, all blocked. A real URL produces a real audit.

```
POST /preview  {"url":"example.com"}

domain      : example.com
final_url   : https://example.com
overall     : 61  across 3 scored categories
  brand           30/70   43%
  technical_seo   35/65   54%
  performance     45/45  100%
locked      : 7 categories, each naming its unlock
```

```
=== api: ruff check ===   PASS      === web: tsc ===    PASS
=== api: ruff format ===  PASS      === web: lint ===   PASS
=== api: mypy strict ===  PASS      === web: build ===  PASS
=== api: pytest ===       PASS  (267 tests)
CI GREEN
```

---

## The SSRF guard

The pre-registration analysis is a **server-side fetch of a URL a stranger typed**, on an **unauthenticated** endpoint. The attacker picks the destination; we supply the network position. On a cloud host the prize is the instance metadata endpoint.

Two decisions carry most of the weight:

**1. The validated IP is pinned, and the crawler connects to that address.** Validating a hostname and then handing the hostname to an HTTP client resolves DNS twice — once for the check, once for the connection — and an attacker's nameserver is free to answer publicly the first time and `169.254.169.254` the second. `Host` and SNI carry the original name so virtual hosting and certificate validation still work.

**2. Redirects are followed by hand, and every hop is re-validated.** A client following them itself would connect to hops the guard never saw. Validating only the first URL is the single most common way this is got wrong.

Also covered: non-HTTP schemes including `gopher` and `dict` (which can drive plaintext protocols like Redis); credentials in the authority (`http://expected.com@evil.com/`); a port **allowlist** rather than a blocklist; octal, decimal and hex literal forms; metadata hostnames blocked by name as well as by address; and mixed DNS answers refused outright rather than cherry-picked.

**The corpus caught a real gap.** `is_public_ip` originally tested the individual flags, which pass carrier-grade NAT (`100.64.0.0/10`) — `is_private` is `False` for it, but it is emphatically not the public internet. It now gates on `is_global`, with the explicit checks kept as documented defence in depth.

**A second gap, found later by a false positive rather than by the corpus** (recorded here because it belongs with the guard, not with the milestone that surfaced it). Three encodings put an IPv4 address inside an IPv6 one; the guard unwrapped two of them. The third, **NAT64** (`64:ff9b::/96`, RFC 6052), it did not.

It surfaced from the honest end. `omantel.om` was refused. The machine's network runs DNS64, so the resolver synthesised `64:ff9b::d448:ad3` alongside the real A record — and that address embeds `212.72.10.211`, the *same public address* the A record gives. Since every answer must be public, the synthesised one failed the whole set, and on such a network **every IPv4-only site was unreachable**. Environment-dependent, so CI was green throughout.

The reason it was refused is the interesting part: Python reports the whole `64:ff9b::/96` block as `is_reserved`, so NAT64 addresses were being rejected — correctly, but *by accident*, with the embedded address never examined. `64:ff9b::a9fe:a9fe` is the cloud metadata endpoint, and it was one semantic change to `is_reserved` away from being reachable. Unwrapping makes it a decision instead: the embedded address is classified on its own merits, so a NAT64 address wrapping loopback is refused because loopback is refused. Six new cases assert exactly that, plus one for the false positive and one documenting the limit — RFC 6052's site-chosen Network-Specific Prefixes cannot be recognised from an address alone and are treated as the ordinary global unicast they resemble.

Fixing a false positive closed a latent bypass. Both directions are now tested.

---

## Rate limiting

Doc 06 §1.2 — a metered API on an unauthenticated path is a way for a script to exhaust a paid quota and degrade the product for paying tenants.

| Limit | Stops |
|---|---|
| **Per IP** | one client hammering the endpoint |
| **Per domain** | many clients pointed at one victim — the reflected-DoS shape a per-IP limit does *not* stop, since each attacker IP stays under its own allowance |
| **Global daily** | the bill. The first two bound any single abuser; only this one bounds spend |

The counter is an atomic upsert returning the new count, so two concurrent requests cannot both read a value below the limit and both proceed. A test drives that from two real connections rather than trusting the SQL by inspection.

Verified live: the 4th request for one domain returns `429` with `Retry-After`.

**One design issue I created and then fixed.** The web proxy forwards `X-Forwarded-For`, but the API deliberately ignored it — so every visitor would have shared a single bucket and the per-IP limit would have collapsed into a global 5/hour. The header is now honoured **only** when the direct peer is a configured trusted proxy (`NEXUS_TRUSTED_PROXY_IPS`), with nine tests including one that fires twenty spoofed headers and asserts they all collapse to one key. The default trusts nothing — the safe failure, but a real deployment behind a proxy must set it.

---

## The audit — no model, anywhere

**Every figure comes from a pure function.** `test_no_model_call_is_reachable_from_preview` walks the route's transitive import graph and fails if any model layer appears. A model here would not merely be a cost problem: it would mean a number on the screen came from a language model (I1).

The split is structural:

- `connectors/extract.py` — **observation only.** Records what the HTML contains. An extractor that returned a "brand score" would make the number's origin a matter of trust.
- `calculators/audit.py` — **pure scoring.** No IO, no clock, no randomness. Every category returns the checks and evidence that produced it, so a card can answer "why are you telling me this?" (I9).

29 calculator tests cover boundaries in both directions, and two properties beyond the arithmetic: every score is reconstructible from its checks, and every check carries evidence.

**Locked is not zero.** Marketing, Sales, Finance, Operations, People, Customer Experience and Competitors render as named unlocks (I10). Doc 05 §3.1 is explicit that Marketing is not scoreable without GA4 and that Brand and SEO must not be merged into a Marketing score to manufacture a number — there is a test for exactly that.

**Preview scope is enforced, not just intended.** Competitor discovery and keyword data sit behind domain verification because they have intelligence value about a third party. Anyone can type a competitor's URL; without that limit NEXUS would be a competitive-intelligence product sold by accident.

---

## The landing page

The hero's primary action is now the one doc 06 §1 specifies: *"Analyse my business — enter your website."* Verified in-browser end to end — type a domain, see the running state, get a real audit with expandable per-check evidence and locked categories naming their unlocks.

The Next.js route proxies server-side so the browser never learns the API address and there is no CORS surface. **It adds no checks of its own** and says so in a comment — every guard lives in the API, and this route must never be mistaken for where they happen.

---

## What does not exist

- **PageSpeed Insights is not wired** (`D3`). The performance category scores *structural* weight only — page size and resource counts — and is documented as explicitly not a Core Web Vitals measurement. Presenting resource counts as a performance grade would be inventing a number by relabelling a different one.
- **`robots.txt` is not yet fetched.** The crawler sends an identifying User-Agent and takes one page; polite crawling of multi-page sites belongs with the full audit in M7.
- **The preview TTL sweep is not scheduled.** `expires_at` is set and indexed; the job that deletes expired rows arrives with the scheduler. Until then rows persist past their TTL — a real gap, and it is the deletion path doc 06 §10 requires for a company that has no account here.
- **No `GET /preview/{id}`.** Results are returned once, not retrievable later. M3 claims a Preview into a verified workspace.

---

## How to validate

```powershell
.\scripts\verify.ps1
```

Then, with both services running, open http://localhost:3000 and enter a domain.

To attack it directly:

```powershell
$body = @{ url = 'http://169.254.169.254/latest/meta-data/' } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/preview -Method Post -Body $body -ContentType 'application/json'
```

Expect `400 That address cannot be analysed.` — the same message for every refusal, because a specific reason would confirm internal network shape to whoever supplied the URL.

**The most useful thing you can do is add an SSRF case.** The corpus is meant to be attacked; a bypass it does not cover is worth more than another passing test.

---

## Invariants

| | Status |
|---|---|
| **I1** never invent a number | Enforced — no model reachable from Preview, asserted by test |
| **I9** every number auditable | Every check returns its evidence; surfaced in the UI |
| **I10** never a zero | 7 categories render as named unlocks, asserted by test |
| **I7** untrusted content | Crawled text is captured but never yet reaches a model — the boundary itself is M12 |

---

## Next

**M3 — registration and domain verification.** DNS TXT and file-at-path as strong methods, same-domain email as weak (flagging Owner-claim review), workspace creation gated on verification, and the two-workspaces-one-domain dispute path. The partial unique index on `lower(domain) WHERE domain_verified_at IS NOT NULL` already exists from M1, so a second claim cannot land while that flow is built.
