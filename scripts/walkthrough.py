"""Drive the whole completed flow through a running API, as a client would.

Not a replacement for the suite — a complement to it. The suite runs against a
container built from this repository's own bootstrap; this runs against whatever
the API is actually pointed at, through HTTP, with cookies and CSRF, in the order
a founder meets the product. Findings 19–23 all came from it, and none of the 755
tests had anything to say about them.

    .venv/bin/python scripts/walkthrough.py        # expects an API on 127.0.0.1:8001

It found findings 19-23 on its first run. 19, 20 and 21 are fixed and this now
asserts the corrected contract, so it goes green. **22 and 23 stay open and this
does not catch either**: 22 needs a question with no assumption and all five
company questions have one, and 23 is a latency budget the BFF pays and this
script does not go through the BFF. Green here is not "no known defects".
"""
import re, sys, time, pathlib, httpx

API = "http://127.0.0.1:8001"
MAIL = pathlib.Path("/Users/parul.bhoite/Developer/NEXUSOS/nexus-os/.mail")
stamp = str(int(time.time()))
EMAIL = f"founder+{stamp}@walkthrough-{stamp}.om"
DOMAIN = f"walkthrough-{stamp}.om"
PW = "correct horse battery staple 9"
ok = fail = 0

def check(label, cond, detail=""):
    global ok, fail
    if cond: ok += 1;  print(f"  \033[32mPASS\033[0m {label}")
    else:    fail += 1; print(f"  \033[31mFAIL\033[0m {label} — {detail}")

c = httpx.Client(base_url=API, timeout=30.0)
def csrf(): return {"X-CSRF-Token": c.cookies.get("nexus_csrf") or ""}

def newest_mail(since):
    """Decode it as mail. The sink writes quoted-printable, so a raw read
    soft-wraps the token at column 76 and every regex over it lies."""
    import email, email.policy
    for _ in range(20):
        files = sorted(MAIL.glob("*.eml"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files and files[0].stat().st_mtime > since:
            msg = email.message_from_bytes(files[0].read_bytes(), policy=email.policy.default)
            parts = [msg] if not msg.is_multipart() else list(msg.walk())
            return "\n".join(
                part.get_content() for part in parts
                if part.get_content_maintype() == "text"
            )
        time.sleep(0.25)
    return ""

print("\n\033[1m1. Register, and verify by email\033[0m")
t0 = time.time()
r = c.post("/auth/register", json={"email": EMAIL, "password": PW, "full_name": "Walk Through"})
check("POST /auth/register -> 201", r.status_code == 201, r.text[:200])
body = newest_mail(t0)
m = re.search(r"token=([A-Za-z0-9_\-\.]{16,})", body) or re.search(r"verify-email\?token=([^\s\"'&<]+)", body)
check("verification email arrived with a token", bool(m), body[:200].replace("\n", " "))
r2 = c.post("/auth/register", json={"email": EMAIL, "password": PW, "full_name": "Walk Through"})
check("duplicate register is indistinguishable", r2.status_code == r.status_code and r2.json() == r.json(),
      f"{r2.status_code} {r2.text[:120]}")
if not m: sys.exit("cannot continue without a token")
tok = m.group(1)
r = c.post("/auth/verify-email", json={"token": tok})
check("POST /auth/verify-email -> 200", r.status_code == 200, r.text[:200])
r = c.post("/auth/verify-email", json={"token": tok})
check("the same token cannot be replayed", r.status_code == 400, f"{r.status_code}")

print("\n\033[1m2. Log in\033[0m")
r = c.post("/auth/login", json={"email": EMAIL, "password": PW})
check("POST /auth/login -> 200", r.status_code == 200, r.text[:200])
check("session cookie set", bool(c.cookies.get("nexus_session")))
check("csrf cookie set", bool(c.cookies.get("nexus_csrf")))
check("no workspace yet", r.json().get("workspaces") == [], r.text[:200])
bad = httpx.Client(base_url=API, timeout=30.0)
rb = bad.post("/auth/login", json={"email": EMAIL, "password": "wrong password entirely"})
ru = bad.post("/auth/login", json={"email": f"nobody-{stamp}@nowhere.om", "password": PW})
check("wrong password and unknown user both 401", rb.status_code == ru.status_code == 401, f"{rb.status_code}/{ru.status_code}")
check("...with an identical body", rb.text == ru.text, f"{rb.text[:60]} vs {ru.text[:60]}")

print("\n\033[1m3. Create the company\033[0m")
COMPANY = {"name": f"Walkthrough Trading {stamp}", "website_url": f"https://{DOMAIN}",
           "country": "OM", "reporting_currency": "OMR", "headcount_band": "11-50"}
r = c.post("/companies", json=COMPANY, headers=csrf())
check("POST /companies -> 201", r.status_code == 201, r.text[:300])
ws = r.json().get("workspace_id") if r.status_code == 201 else None
r_nocsrf = c.post("/companies", json=COMPANY)
check("the same call without the CSRF header is refused", r_nocsrf.status_code == 403, f"{r_nocsrf.status_code}")
r = c.post("/companies", json={**COMPANY, "name": "Second Company",
                               "website_url": f"https://second-{stamp}.om"}, headers=csrf())
check("a second company is refused (one company per founder)", r.status_code in (409, 403, 422), f"{r.status_code} {r.text[:150]}")

print("\n\033[1m4. Onboarding — state, company answers, departments\033[0m")
r = c.get("/onboarding/state")
check("GET /onboarding/state -> 200", r.status_code == 200, r.text[:200])
st = r.json() if r.status_code == 200 else {}
print(f"       stage={st.get('stage')!r}")
cq = st.get("company_questions", [])
print(f"       {len(cq)} company questions: {', '.join(q['key'] for q in cq)}")
check("every company question carries a why", all(q.get("why") for q in cq), "one has no why")
skippable = [q for q in cq if q.get("assumption_when_unsure")]
check("at least one may be skipped with a stated assumption", bool(skippable), "none is skippable")
answers = [{"key": q["key"], "value": None, "unsure": True}
           if q.get("assumption_when_unsure") else {"key": q["key"], "value": "A real answer"}
           for q in cq]
r = c.post("/onboarding/company", json={"answers": answers}, headers=csrf())
check("POST /onboarding/company -> 200", r.status_code == 200, r.text[:300])
if r.status_code == 200: print(f"       stage now {r.json().get('current')!r}")
r = c.post("/onboarding/company", json={"answers": [{"key": "not_a_real_key", "value": "x"}]}, headers=csrf())
check("an unknown question key is refused", r.status_code == 400, f"{r.status_code}")
required_no_assumption = [q for q in cq if not q.get("assumption_when_unsure")]
if required_no_assumption:
    k = required_no_assumption[0]["key"]
    r = c.post("/onboarding/company", json={"answers": [{"key": k, "value": None, "unsure": True}]}, headers=csrf())
    check(f"'not sure' on {k}, which has no assumption, is a client error not a 500",
          r.status_code in (400, 422), f"{r.status_code}")
r = c.post("/onboarding/departments", json={"departments": ["finance", "sales", "operations"]}, headers=csrf())
check("POST /onboarding/departments -> 200", r.status_code == 200, r.text[:300])
r = c.post("/onboarding/departments", json={"departments": ["astrology"]}, headers=csrf())
check("an unknown department is refused", r.status_code == 400, f"{r.status_code}")

print("\n\033[1m5. The department block (P7)\033[0m")
r = c.get("/onboarding/departments/finance/block")
check("GET .../finance/block -> 200", r.status_code == 200, r.text[:300])
blk = r.json() if r.status_code == 200 else {}
bq = blk.get("questions", [])
check("the owner may answer, and it binds", blk.get("may_answer") is True and blk.get("binds") is True, str(blk)[:200])
check("every question carries a why", all(q.get("why") for q in bq), "a question has no why")
check("every question names what consumes it", all(q.get("consumed_by") for q in bq), "a question has no consumed_by")
print(f"       {len(bq)} questions; first: {bq[0]['key'] if bq else '—'}")
r = c.get("/onboarding/departments/hr/block")
check("a department the workspace did not choose -> 404", r.status_code == 404, f"{r.status_code}")
r = c.get("/onboarding/departments/astrology/block")
check("a department that does not exist -> 404/422", r.status_code in (404, 422), f"{r.status_code}")
if bq:
    two = [{"key": bq[0]["key"], "value": "Answered in the walkthrough"},
           {"key": bq[1]["key"], "value": "Also answered"}]
    r = c.post("/onboarding/departments/finance/block", json={"answers": two}, headers=csrf())
    check("POST .../finance/block -> 200", r.status_code == 200, r.text[:300])
    after = r.json() if r.status_code == 200 else {}
    aq = {q["key"]: q for q in after.get("questions", [])}
    check("the answer came back", aq.get(bq[0]["key"], {}).get("answer") == "Answered in the walkthrough",
          str(aq.get(bq[0]["key"]))[:200])
    check("the second answer came back too", aq.get(bq[1]["key"], {}).get("answer") == "Also answered",
          str(aq.get(bq[1]["key"]))[:200])
    for blank in ("", "   "):
        r = c.post("/onboarding/departments/finance/block",
                   json={"answers": [{"key": bq[2]["key"], "value": blank}]}, headers=csrf())
        check(f"a blank answer ({blank!r}) is refused rather than stored", r.status_code == 422,
              f"{r.status_code}")
    r = c.get("/onboarding/departments/finance/block")
    third = {q["key"]: q for q in r.json()["questions"]}[bq[2]["key"]]
    check("...and the blank did not mark it answered", third["answered"] is False, str(third)[:160])
    r = c.post("/onboarding/departments/finance/block",
               json={"answers": [{"key": "nope_not_real", "value": "x"}]}, headers=csrf())
    check("an unknown key in a block is refused", r.status_code == 400, f"{r.status_code}")

print("\n\033[1m6. Dashboards\033[0m")
r = c.get("/dashboards")
check("GET /dashboards -> 200", r.status_code == 200, r.text[:200])
d = r.json() if r.status_code == 200 else {}
dirs = d.get("directors", [])
print(f"       {len(dirs)} directors: {', '.join(x['department'] for x in dirs)}")
check("the directors are the chosen three plus the automatic Chief of Staff",
      {x["department"] for x in dirs} == {"finance", "sales", "operations", "executive"},
      str(sorted(x["department"] for x in dirs)))
fin = next((x for x in dirs if x["department"] == "finance"), {})
ua = fin.get("unanswered_questions")
check("finance reports a real unanswered count", isinstance(ua, int), f"got {ua!r}")
check("...and answering lowered it", isinstance(ua, int) and ua < len(bq), f"{ua} of {len(bq)}")
r = c.get("/dashboards/finance")
check("GET /dashboards/finance -> 200", r.status_code == 200, r.text[:200])
if r.status_code == 200:
    offs = r.json().get("offerings", [])
    check("every offering says it is planned", all(o["state"] == "planned" for o in offs), "an offering claims to be built")
    print(f"       {len(offs)} offerings, all planned")
r = c.get("/dashboards/hr")
check("a dashboard the list did not offer -> 404", r.status_code == 404, f"{r.status_code}")

print("\n\033[1m7. The audit trail (I9)\033[0m")
r = c.get("/audit-log")
check("GET /audit-log -> 200", r.status_code == 200, r.text[:200])
if r.status_code == 200:
    ev = r.json().get("entries", [])
    kinds = [e.get("action") for e in ev]
    print(f"       {len(ev)} events: {', '.join(str(k) for k in kinds[:8])}")
    check("the trail is not empty", bool(ev), "no events recorded")
    check("the onboarding answers are in the trail",
          any("answer" in str(k).lower() for k in kinds), str(kinds)[:200])

print("\n\033[1m8. Logged out, everything closes\033[0m")
r = c.post("/auth/logout", headers=csrf())
check("POST /auth/logout -> 204", r.status_code == 204, f"{r.status_code}")
anon = httpx.Client(base_url=API, timeout=30.0)
for path in ["/onboarding/state", "/dashboards", "/dashboards/finance",
             "/onboarding/departments/finance/block", "/audit-log", "/auth/me"]:
    rr = anon.get(path)
    check(f"anonymous GET {path} -> 401", rr.status_code == 401, f"{rr.status_code}")

print(f"\n\033[1m{ok} passed, {fail} failed\033[0m")
sys.exit(1 if fail else 0)
