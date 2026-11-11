"""The process. Each stage writes what it did into the run, so the live view can show it.

Rule of thumb used everywhere: the model suggests, code decides.
  - The model reads messy text (news headlines, drafts) and scores relevance.
  - Code resolves identity, checks dates and numbers, applies every hard rule,
    computes the final hook score and blocks anything it cannot verify.
"""
import re
import threading
import time
import traceback
from datetime import date, datetime

from . import config, llm, store
from .crust import Client, CrustError
from .seller import FINANCE_TITLE_WORDS, SELLER

SENSITIVE = re.compile(r"\b(lay ?offs?|laid off|job cuts|cuts? \d+ jobs|lawsuit|sued|sues|probe|investigation|"
                       r"breach|hack(ed)?|bankrupt\w*|insolven\w*|died|death|passed away|recall|fraud|scandal|"
                       r"resign\w*|fired|restructur\w*|delist\w*|misconduct)\b", re.I)
MONEY = re.compile(r"\$\s?(\d+(?:\.\d+)?)\s?(billion|bn|b|million|mn|m)\b", re.I)


# ---------------------------------------------------------------- helpers
def d(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


ABBR = {"cfo": "chief financial officer", "ceo": "chief executive officer", "coo": "chief operating officer",
        "cto": "chief technology officer", "vp": "vice president", "svp": "senior vice president",
        "evp": "executive vice president", "head of ap": "head of accounts payable", "ap": "accounts payable"}


def same_title(a, b):
    def x(t):
        t = norm(t)
        for k, v in ABBR.items():
            t = re.sub(r"\b" + k + r"\b", v, t)
        return t
    a, b = x(a), x(b)
    return bool(a and b) and (a in b or b in a)


def same_name(a, b):
    a, b = norm(a).split(), norm(b).split()
    return bool(a and b) and a[0] == b[0] and a[-1] == b[-1]


def money_usd(text):
    out = []
    for n, unit in MONEY.findall(text or ""):
        v = float(n) * (1e9 if unit.lower().startswith("b") else 1e6)
        out.append(v)
    return out


def fmt_usd(v):
    return f"${v / 1e9:.1f}B" if v >= 1e9 else f"${v / 1e6:.0f}M"


def month(dt):
    return dt.strftime("%b %Y") if dt else "unknown date"


def current_job(person, company_id=None, company_name=None):
    cur = ((person.get("experience") or {}).get("employment_details") or {}).get("current") or []
    for j in cur:
        if company_id and j.get("crustdata_company_id") == company_id:
            return j
    for j in cur:
        if company_name and norm(j.get("name")) == norm(company_name):
            return j
    return None


def profile_url(p):
    return (((p.get("social_handles") or {}).get("professional_network_identifier") or {}).get("profile_url"))


class Pause(Exception):
    """The process needs the rep to decide something. Not an error."""


# ---------------------------------------------------------------- runner
class Runner:
    STAGES = [
        ("intake", "Check the request"),
        ("company", "Find the company"),
        ("person", "Confirm the person"),
        ("profile", "Read their profile"),
        ("company_data", "Read company data"),
        ("roles", "Scan open roles"),
        ("signals", "Turn data into signals"),
        ("guards", "Run the safety checks"),
        ("hook", "Pick the hook"),
        ("draft", "Write the draft"),
        ("factcheck", "Fact-check every claim"),
    ]

    def __init__(self, run):
        self.run = run
        self.client = Client(run["mode"])
        self.today = d(run["created"]) or date.today()
        self.cur = None

    # -- bookkeeping
    def log(self, msg, level="info"):
        if self.cur is not None:
            self.cur["log"].append({"t": round(time.time() - self.cur["_t0"], 2), "msg": msg, "level": level})
            self.save()

    def save(self):
        self.run["credits"] = round(self.run.get("credits_before", 0) + self.client.spent, 2)
        self.run["calls"] = self.run.get("calls_before", []) + self.client.calls
        store.save(self.run)

    def check(self, kind, status, title, detail="", signal_ids=()):
        self.run["checks"].append({"kind": kind, "status": status, "title": title, "detail": detail,
                                   "signal_ids": list(signal_ids)})

    def go(self, start="intake"):
        keys = [k for k, _ in self.STAGES]
        self.run["status"] = "running"
        self.run["question"] = None
        self.run["credits_before"] = self.run.get("credits", 0)
        self.run["calls_before"] = self.run.get("calls", [])
        # drop stages from a previous attempt that will run again
        self.run["stages"] = [s for s in self.run["stages"] if keys.index(s["key"]) < keys.index(start)]
        for key, title in self.STAGES[keys.index(start):]:
            st = {"key": key, "title": title, "status": "running", "started": store.now(), "ms": None,
                  "summary": "", "log": [], "_t0": time.time()}
            self.run["stages"].append(st)
            self.cur = st
            self.save()
            try:
                st["summary"] = getattr(self, "s_" + key)() or ""
                st["status"] = "done"
            except Pause as p:
                st["status"], st["summary"] = "waiting", str(p)
                self.run["status"] = "needs_input"
                self._close(st)
                return
            except Stop as s:
                st["status"], st["summary"] = s.stage_status, str(s)
                self.run["status"] = s.run_status
                self._close(st)
                return
            except CrustError as e:
                st["status"], st["summary"] = "failed", str(e)
                self.run["status"] = "failed"
                self.run["error"] = {"code": e.code, "msg": str(e)}
                self._close(st)
                return
            except Exception as e:  # noqa: BLE001 - a crash must still end the run visibly
                st["status"], st["summary"] = "failed", f"{e.__class__.__name__}: {e}"
                self.run["status"] = "failed"
                self.run["error"] = {"code": "crash", "msg": str(e), "trace": traceback.format_exc()[-1500:]}
                self._close(st)
                return
            self._close(st)
        self.run["status"] = self.run.get("outcome") or "ready"
        self.save()

    def _close(self, st):
        st["ms"] = int((time.time() - st.pop("_t0")) * 1000)
        st["ended"] = store.now()
        self.save()

    # ================================================================ stages
    def s_intake(self):
        inp = self.run["input"]
        inp["name"] = " ".join((inp.get("name") or "").split())
        inp["company"] = " ".join((inp.get("company") or "").split())
        url = (inp.get("linkedin") or "").strip()
        if url and "linkedin.com/in/" not in url:
            raise Stop("That LinkedIn link is not a profile link (it should contain linkedin.com/in/).", "blocked")
        if not url and (len(inp["name"].split()) < 2 or not inp["company"]):
            raise Stop("Need a full name and a company, or a LinkedIn profile link.", "blocked")
        self.log(f"Prospect: {inp['name'] or url} at {inp['company'] or '(company from profile)'}")
        self.log(f"Mode: {self.run['mode']} ({'recorded answers only, no credits' if self.run['mode'] == 'replay' else 'new lookups cost Crustdata credits'})")
        # Recently drafted?
        for r in store.all_runs(200):
            if r["id"] == self.run["id"] or not r.get("person"):
                continue
            if same_name(r["person"].get("name"), inp["name"]) and norm(r["input"].get("company")) == norm(inp["company"]):
                age = (self.today - (d(r["created"]) or self.today)).days
                if age <= config.RECONTACT_DAYS and r.get("status") in ("ready", "ready_with_warnings", "approved"):
                    self.check("recontact", "warn", f"Already drafted {age} days ago",
                               f"Run {r['id']} has a {r['status'].replace('_', ' ')} draft for this person.")
                    self.log(f"Note: this person already has a draft from {age} days ago (run {r['id']}).", "warn")
                    break
        return "Request looks complete"

    def s_company(self):
        inp = self.run["input"]
        if not inp["company"]:
            self.run["company_candidates"] = []
            return "Will take the company from the profile"
        cands = [c for c in self.client.identify_company(inp["company"]) if c["id"]]
        self.run["company_candidates"] = cands[:5]
        if not cands:
            if inp.get("linkedin"):
                self.log("No company with that name; will trust the profile's current employer.", "warn")
                return "Company not found by name"
            raise Stop(f"No company called “{inp['company']}” in the data. Check the spelling or add a LinkedIn link.",
                       "not_found")
        for c in cands[:5]:
            self.log(f"Match: {c['name']} · {c['domain'] or 'no domain'} · {c['size'] or 'size unknown'}")
        if len(cands) > 1:
            self.log(f"{len(cands)} companies share this name; the person's current job will decide which one.", "warn")
            return f"{len(cands)} companies named “{inp['company']}”. Deciding by the person's employer"
        return f"{cands[0]['name']} ({cands[0]['domain']})"

    def s_person(self):
        inp, cands = self.run["input"], self.run.get("company_candidates") or []
        ids = [c["id"] for c in cands]
        chosen = self.run.get("chosen_person_url")
        if chosen or inp.get("linkedin"):
            self.run["person_url"] = chosen or inp["linkedin"].split("?")[0].rstrip("/")
            if self.run.get("followed"):
                self.log(self.run.get("note") or "Following the person to their new company.")
                return f"Following {self.run['moved']['name']} to {self.run['moved']['new_company']}"
            self.log("Using the LinkedIn profile given; employer is checked in the next step.")
            return "Profile link given"
        name = inp["name"]
        people = self.client.search_people([
            {"field": "basic_profile.name", "type": "(.)", "value": name},
            {"field": "experience.employment_details.current.company_id", "type": "in", "value": ids}],
            "Search people at company")
        people = [p for p in people if same_name(p["basic_profile"].get("name"), name)]
        if len(people) == 1:
            p = people[0]
            job = next((j for j in p["experience"]["employment_details"].get("current", [])
                        if j.get("crustdata_company_id") in ids), {})
            self.run["person_url"] = profile_url(p)
            co = next((c for c in cands if c["id"] == job.get("crustdata_company_id")), cands[0])
            self.run["company"] = co
            if len(cands) > 1:
                others = ", ".join(c["domain"] or c["name"] for c in cands if c["id"] != co["id"])
                self.check("identity", "pass", f"Picked {co['domain']} over {others}",
                           f"{p['basic_profile']['name']}'s current job is at {co['domain']}.")
            self.log(f"Found {p['basic_profile']['name']}, {job.get('title')} (profile {self.run['person_url']})")
            return f"{p['basic_profile']['name']} · {job.get('title')}"
        if len(people) > 1:
            self.run["question"] = {
                "kind": "pick_person",
                "text": f"{len(people)} people called {name} work at {inp['company']}. Which one?",
                "options": [{"id": profile_url(p), "label": p["basic_profile"]["name"],
                             "detail": "; ".join(j.get("title") or "" for j in p["experience"]["employment_details"].get("current", [])[:2]),
                             "url": profile_url(p)} for p in people]}
            raise Pause("Several people match. Rep picks one")
        # Not at the company now. Did they work there before?
        past = self.client.search_people([
            {"field": "basic_profile.name", "type": "(.)", "value": name},
            {"field": "experience.employment_details.past.company_id", "type": "in", "value": ids}],
            "Search past employees")
        past = [p for p in past if same_name(p["basic_profile"].get("name"), name)]
        if past:
            p = past[0]
            old = next((j for j in p["experience"]["employment_details"].get("past", [])
                        if j.get("crustdata_company_id") in ids), {})
            now_jobs = p["experience"]["employment_details"].get("current", [])
            nj = now_jobs[0] if now_jobs else {}
            left = d(old.get("end_date"))
            self.run["moved"] = {"url": profile_url(p), "name": p["basic_profile"]["name"],
                                 "old_title": old.get("title"), "old_company": old.get("name") or inp["company"],
                                 "left": old.get("end_date"), "new_title": nj.get("title"),
                                 "new_company": nj.get("name"), "new_company_id": nj.get("crustdata_company_id"),
                                 "new_start": nj.get("start_date")}
            self.check("job_change", "block", f"{name} left {inp['company']} in {month(left)}",
                       f"Now {nj.get('title') or 'in a new role'} at {nj.get('name') or 'another company'}"
                       f" since {month(d(nj.get('start_date')))}.")
            opts = []
            if nj.get("name"):
                opts.append({"id": "follow", "label": f"Write to {name.split()[0]} at {nj.get('name')}",
                             "detail": f"New in the job since {month(d(nj.get('start_date')))}: new leaders pick new tools."})
            opts.append({"id": "replace", "label": f"Find who is {old.get('title') or inp.get('title') or 'in that role'} at {inp['company']} now",
                         "detail": "Same account, the person who owns the problem today."})
            opts.append({"id": "stop", "label": "Stop here", "detail": "No credits spent."})
            self.run["question"] = {"kind": "job_change",
                                    "text": f"{name} no longer works at {inp['company']}. They left in {month(left)}"
                                            f"{' and are now ' + nj.get('title') + ' at ' + nj.get('name') if nj.get('name') else ''}.",
                                    "options": opts}
            raise Pause("Person has changed jobs. Rep chooses what to do")
        self.run["question"] = {"kind": "not_found",
                                "text": f"Couldn't find {name} at {inp['company']}. Paste their LinkedIn profile link to continue.",
                                "options": [{"id": "linkedin", "label": "Use a LinkedIn link", "input": True},
                                            {"id": "stop", "label": "Stop here"}]}
        raise Pause("Person not found. Rep can paste a profile link")

    def s_profile(self):
        p = self.client.enrich_person(self.run["person_url"])
        if not p:
            raise Stop("Crustdata has no profile at that link.", "not_found")
        cands = self.run.get("company_candidates") or []
        co = self.run.get("company")
        job = None
        for c in ([co] if co else []) + cands:
            job = current_job(p, c["id"], c["name"])
            if job:
                co = c
                break
        cur = ((p.get("experience") or {}).get("employment_details") or {}).get("current") or []
        if not job and cur:
            if self.run["input"].get("company") and cands and not self.run.get("followed"):
                # the link points to someone who is not at the requested company now
                j = cur[0]
                raise Stop(f"This profile's current job is {j.get('title')} at {j.get('name')}, not {self.run['input']['company']}.",
                           "needs_review")
            job = cur[0]
            co = {"id": job.get("crustdata_company_id"), "name": job.get("name"), "domain": job.get("company_website_domain")}
        self.run["company"] = co
        bp = p.get("basic_profile") or {}
        start = d(job.get("start_date")) if job else None
        past = (((p.get("experience") or {}).get("employment_details") or {}).get("past") or [])
        self.run["person"] = {
            "name": bp.get("name"), "headline": bp.get("headline"), "url": self.run["person_url"],
            "title": job.get("title") if job else bp.get("current_title"),
            "start": job.get("start_date") if job else None,
            "tenure_days": (self.today - start).days if start else None,
            "location": ((p.get("professional_network") or {}).get("location") or {}).get("raw"),
            "past": [{"title": j.get("title"), "company": j.get("name"), "start": j.get("start_date"),
                      "end": j.get("end_date"), "description": (j.get("description") or "")[:300]} for j in past[:6]],
            "education": [s.get("school") for s in (p.get("education") or {}).get("schools", [])][:3],
        }
        t_in = (self.run["input"].get("title") or "").strip()
        if t_in and job and not same_title(t_in, job.get("title")):
            self.check("title", "warn", f"Title differs: you typed “{t_in}”, profile says “{job.get('title')}”",
                       "Using the profile's title.")
            self.log(f"Title on profile is “{job.get('title')}”, not “{t_in}”. Using the profile.", "warn")
        pr = self.run["person"]
        self.log(f"{pr['title']} at {co['name']} since {month(start)}" +
                 (f" ({pr['tenure_days']} days)" if pr["tenure_days"] is not None else ""))
        for j in pr["past"][:3]:
            self.log(f"Before: {j['title']} at {j['company']} ({(j['start'] or '')[:4]}–{(j['end'] or '')[:4]})")
        return f"{pr['title']} at {co['name']}, {pr['tenure_days']} days in role" if pr["tenure_days"] is not None else pr["title"]

    def s_company_data(self):
        c = self.client.enrich_company(self.run["company"]["id"])
        if not c:
            raise Stop("No company data available.", "low_signal")
        self.cdata = c
        self.run["company_data"] = self._company_summary(c)
        cs = self.run["company_data"]
        self.log(f"Headcount {cs['headcount']} ({cs['headcount_yoy']:+.0f}% in a year)" if cs["headcount_yoy"] is not None
                 else f"Headcount {cs['headcount']}")
        if cs["last_round"]:
            self.log(f"Last round: {cs['last_round']['type']} {fmt_usd(cs['last_round']['amount']) if cs['last_round']['amount'] else ''} on {cs['last_round']['date']}")
        self.log(f"{cs['news_count']} news items in the last {config.NEWS_WINDOW_DAYS} days")
        return f"{cs['headcount']} people · {cs['news_count']} recent news items"

    def _company_summary(self, c):
        h = c.get("headcount") or {}
        f = c.get("funding") or {}
        ms = sorted(f.get("milestones") or [], key=lambda m: m.get("funding_date") or m.get("date") or "", reverse=True)
        last = ms[0] if ms else None
        news = [n for n in (c.get("news") or []) if d(n.get("article_publish_date"))
                and (self.today - d(n["article_publish_date"])).days <= config.NEWS_WINDOW_DAYS]
        hi = c.get("hiring") or {}
        return {
            "name": (c.get("basic_info") or {}).get("name"),
            "domain": (c.get("basic_info") or {}).get("primary_domain"),
            "description": ((c.get("basic_info") or {}).get("description") or "")[:400],
            "headcount": h.get("total"),
            "headcount_yoy": (h.get("growth_percent") or {}).get("yoy"),
            "last_round": {"type": (last.get("round_type") or "").replace("_", " ").title(),
                           "amount": last.get("amount_usd"), "date": (last.get("funding_date") or last.get("date") or "")[:10],
                           "investors": last.get("lead_investors")} if last else None,
            "total_raised": f.get("total_investment_usd"),
            "news_count": len(news),
            "open_jobs": [(t.get("date", "")[:7], t.get("open_jobs")) for t in (hi.get("open_jobs_timeseries") or [])][-8:],
            "hiring_6m": {k: v for k, v in (hi.get("by_function_6m_pct") or {}).items() if v is not None},
        }

    def s_roles(self):
        jobs = self.client.search_jobs(self.run["company"]["id"], FINANCE_TITLE_WORDS)
        kept, dropped = [], []
        rx = re.compile(r"\b(" + "|".join(re.escape(w) for w in FINANCE_TITLE_WORDS) + r")\b", re.I)
        for j in jobs:
            t = (j.get("job_details") or {}).get("title") or ""
            (kept if rx.search(t) and not re.search(r"\bintern(ship)?\b", t, re.I) else dropped).append(j)
        for j in dropped:
            why = "internships say little about the team's workload" if re.search(r"\bintern", j['job_details']['title'], re.I) \
                else "search matched it loosely, title isn't a finance role"
            self.log(f"Ignored “{j['job_details']['title']}”: {why}", "warn")
        self.jobs = kept
        for j in kept:
            self.log(f"{(j.get('metadata') or {}).get('date_added', '')[:10]} · {j['job_details']['title']}")
        return f"{len(kept)} relevant roles ({len(dropped)} ignored)"

    # ---------------------------------------------------------------- signals
    def s_signals(self):
        sig, pr, co = [], self.run["person"], self.run["company"]
        cs = self.run["company_data"]

        def add(**k):
            k.setdefault("flags", [])
            k.setdefault("coverage", 1)
            k["id"] = f"s{len(sig) + 1}"
            sig.append(k)
            return k

        if pr.get("start"):
            add(kind="new_role", about="person", date=pr["start"][:10],
                text=f"{pr['name']} became {pr['title']} at {co['name']} in {month(d(pr['start']))} ({pr['tenure_days']} days ago).",
                sources=[{"label": "LinkedIn profile (via Crustdata)", "url": pr["url"]}])
        for j in pr["past"][:4]:
            if j["company"] and any(w in norm(j["title"]) for w in ("cfo", "chief financial", "finance", "controller", "accounting", "founder", "ceo", "coo")):
                add(kind="background", about="person", date=(j["end"] or "")[:10] or None,
                    text=f"Previously {j['title']} at {j['company']} ({(j['start'] or '')[:4]}–{(j['end'] or '')[:4] or 'now'})"
                         + (f": “{j['description'][:160]}”" if j["description"] else "."),
                    sources=[{"label": "LinkedIn profile (via Crustdata)", "url": pr["url"]}])
        if cs["last_round"] and cs["last_round"]["date"]:
            lr = cs["last_round"]
            add(kind="funding", about="company", date=lr["date"], amount=lr["amount"],
                text=f"{co['name']} raised a {lr['type']}" + (f" of {fmt_usd(lr['amount'])}" if lr["amount"] else "")
                     + f" on {lr['date']}" + (f", led by {lr['investors']}" if lr.get("investors") else "") + ".",
                sources=[{"label": "Crustdata funding record", "url": None}])
        if cs["headcount"] and cs["headcount_yoy"]:
            add(kind="growth", about="company", date=self.today.isoformat(),
                text=f"{co['name']} has {cs['headcount']:,} employees, {cs['headcount_yoy']:+.0f}% in the last 12 months.",
                sources=[{"label": "Crustdata headcount", "url": None}])
        for fn in ("Finance", "Accounting"):
            v = cs["hiring_6m"].get(fn)
            if v:
                add(kind="finance_hiring", about="company", date=self.today.isoformat(),
                    text=f"{fn} hiring at {co['name']} changed {v * 100:+.0f}% over 6 months.",
                    sources=[{"label": "Crustdata hiring data", "url": None}])
        for j in getattr(self, "jobs", []):
            desc = (j.get("content") or {}).get("description") or ""
            m = re.search(r"[^.\n]{0,140}\b(manual|reconcil\w*|automat\w*|spreadsheet|handoffs?)\b[^.\n]{0,140}", desc, re.I)
            add(kind="job_post", about="company", date=((j.get("metadata") or {}).get("date_added") or "")[:10] or None,
                text=f"{co['name']} is hiring a {j['job_details']['title']}" + (f": “{m.group(0).strip()}”" if m else "."),
                sources=[{"label": "Job post", "url": j["job_details"].get("url")}])
        self._news_events(add)
        self.run["signals"] = sig
        self.log(f"{len(sig)} signals: " + ", ".join(sorted({s['kind'].replace('_', ' ') for s in sig})))
        return f"{len(sig)} signals from profile, company data, roles and news"

    def _news_events(self, add):
        news = [n for n in (self.cdata.get("news") or []) if d(n.get("article_publish_date"))
                and (self.today - d(n["article_publish_date"])).days <= config.NEWS_WINDOW_DAYS]
        news.sort(key=lambda n: n["article_publish_date"], reverse=True)
        news = news[:80]
        if not news:
            self.log("No recent news.")
            return
        items = [{"i": i, "date": n["article_publish_date"][:10], "title": n.get("article_title"),
                  "outlet": n.get("article_publisher_name")} for i, n in enumerate(news)]
        co = self.run["company"]["name"]
        data, meta = llm.ask(
            "You group news headlines about one company into distinct real-world events for a B2B sales researcher.",
            f"Company: {co}. Headlines (JSON list):\n{llm.src(items)}\n\n"
            "Group headlines that report the same event. For each event return: label (short, factual), "
            "type (one of funding, expansion, product, partnership, pricing, leadership, acquisition, customer, "
            "marketing, layoffs, legal, security, award, other), items (list of i), sensitive (true for layoffs, "
            "lawsuits, investigations, breaches, deaths, bankruptcy, scandals), "
            "about_company (false if the headline is mainly about another company, a listicle, a how-to for shoppers, "
            "a funding database page, or only mentions this company in passing), "
            "summary (one factual sentence using only facts in the headlines). "
            'Return {"events": [...]} with every headline used at most once.', tag="news")
        self.log(f"Grouped {len(news)} headlines into events ({meta['model']}{', cached' if meta['cached'] else ''})")
        used = set()
        for ev in data.get("events", []):
            idx = [i for i in ev.get("items", []) if isinstance(i, int) and 0 <= i < len(news) and i not in used]
            if not idx:
                continue
            used.update(idx)
            arts = [news[i] for i in idx]
            outlets = sorted({a.get("publisher_domain") or a.get("article_publisher_name") for a in arts})
            first = min(a["article_publish_date"][:10] for a in arts)
            titles = " ".join(a.get("article_title") or "" for a in arts)
            flags = []
            if not ev.get("about_company", True):
                flags.append("off_topic")
            kw_hits = [a.get("article_title") for a in arts if SENSITIVE.search(a.get("article_title") or "")]
            if ev.get("sensitive") or ev.get("type") in ("layoffs", "legal", "security") \
                    or (kw_hits and len(kw_hits) / len(arts) >= 0.5):
                flags.append("sensitive")
            elif kw_hits:
                flags.append("keyword_only")
            s = add(kind="news", event_type=ev.get("type", "other"), about="company", date=first,
                    text=ev.get("summary") or ev.get("label"), label=ev.get("label"), keyword_hits=kw_hits[:3] if kw_hits else [],
                    coverage=len(outlets), flags=flags, amounts=sorted(set(money_usd(titles))),
                    sources=[{"label": a.get("article_publisher_name"), "url": a.get("article_url"),
                              "title": a.get("article_title"), "date": a["article_publish_date"][:10]} for a in arts[:12]])
            self.log(f"Event: {s['label']} · {len(outlets)} outlet{'s' if len(outlets) != 1 else ''} · {first}"
                     + (" · " + ", ".join(flags) if flags else ""))

    # ---------------------------------------------------------------- guards
    def s_guards(self):
        sig = self.run["signals"]
        by_id = {s["id"]: s for s in sig}
        today = self.today
        n_block = 0
        for s in sig:
            dt = d(s.get("date"))
            age = (today - dt).days if dt else None
            s["age_days"] = age
            if "off_topic" in s["flags"]:
                self.check("off_topic", "pass", f"Ignored: “{s.get('label') or s['text'][:60]}”",
                           "Not really about this company (listicle, database page or passing mention).", [s["id"]])
            if "keyword_only" in s["flags"]:
                self.check("keyword", "pass", f"Kept despite a sensitive word: “{s['keyword_hits'][0][:80]}”",
                           "The keyword filter flagged it, the model read the headline in context and found nothing sensitive. "
                           f"{len(s['keyword_hits'])} of {s['coverage']} outlets used such a word.", [s["id"]])
            if "sensitive" in s["flags"]:
                n_block += 1
                self.check("sensitive", "block", f"Sensitive news is never a hook: “{s.get('label') or s['text'][:60]}”",
                           "Layoffs, lawsuits, breaches and similar news stay out of the email.", [s["id"]])
            if s["kind"] not in ("background", "growth", "finance_hiring") and age is not None and age > config.STALE_DAYS:
                s["flags"].append("stale")
                self.check("stale", "warn", f"Too old to open with: {s['text'][:70]}", f"{age} days old (limit {config.STALE_DAYS}).", [s["id"]])
            text = s["text"] + " " + " ".join((x.get("title") or "") for x in s.get("sources", []))
            comp = [c for c in SELLER["competitors"] if re.search(r"\b" + re.escape(c) + r"\b", text)]
            if comp:
                s["flags"].append("competitor")
                self.check("competitor", "warn", f"Mentions a competitor ({', '.join(comp)})",
                           "Not used as a hook: it would advertise the competitor.", [s["id"]])
        # Crowded: same event reported everywhere -> every other rep will open with it too.
        for s in sig:
            if s["kind"] == "news" and "off_topic" not in s["flags"] and s.get("event_type") in ("funding", "acquisition", "product", "leadership") \
                    and s["coverage"] >= config.CROWDED_OUTLETS:
                s["flags"].append("crowded")
                self.check("crowded", "warn", f"Crowded: “{s.get('label')}” was covered by {s['coverage']} outlets",
                           f"Every other rep will open with this. It can be context, not the opening line (−{config.CROWDED_PENALTY} points).",
                           [s["id"]])
                fund = next((f for f in sig if f["kind"] == "funding"), None)
                if fund and s.get("event_type") == "funding":
                    fund["flags"].append("crowded")
                    fund["crowded_by"] = s["id"]
        # Conflict: the database and the press disagree on a number.
        fund = next((f for f in sig if f["kind"] == "funding"), None)
        if fund and fund.get("amount"):
            for s in sig:
                if s["kind"] == "news" and s.get("event_type") == "funding" and s.get("amounts"):
                    close = [a for a in s["amounts"] if abs(a - fund["amount"]) / fund["amount"] < 0.25]
                    if close and all(abs(a - fund["amount"]) / fund["amount"] > 0.001 for a in close):
                        for x in (fund, s):
                            x["flags"].append("conflict")
                            x["no_numbers"] = True
                        self.check("conflict", "warn",
                                   f"Sources disagree on the amount: database {fmt_usd(fund['amount'])}, press {', '.join(fmt_usd(a) for a in close)}",
                                   "The email may mention the round but not the amount.", [fund["id"], s["id"]])
        # Suspicious statistic: open roles collapse while the press reports hiring or expansion.
        oj = [v for _, v in self.run["company_data"]["open_jobs"] if v is not None]
        expanding = [s for s in sig if s["kind"] == "news" and s.get("event_type") == "expansion" and (s.get("age_days") or 999) <= 60]
        if len(oj) >= 4 and max(oj) >= 20 and oj[-1] <= 0.2 * max(oj):
            msg = f"Open roles fell from {max(oj)} to {oj[-1]} in the data"
            if expanding:
                self.check("anomaly", "warn", msg + ", but the press reports expansion",
                           f"Fresh news wins: “{expanding[0].get('label')}”. Hiring numbers are not used as a hook.",
                           [e["id"] for e in expanding])
                for s in sig:
                    if s["kind"] == "finance_hiring":
                        s["flags"].append("unreliable")
            else:
                self.check("anomaly", "warn", msg, "Could be a hiring freeze or a gap in the data. Not used as a hook.")
        self.log(f"{len(self.run['checks'])} checks, {n_block} blocking")
        return f"{sum(1 for c in self.run['checks'] if c['status'] != 'pass')} findings · {n_block} sensitive items excluded"

    # ---------------------------------------------------------------- hook
    def s_hook(self):
        sig = [s for s in self.run["signals"] if "off_topic" not in s["flags"]]
        pr, co = self.run["person"], self.run["company"]
        brief = [{"id": s["id"], "kind": s["kind"], "about": s["about"], "date": s.get("date"), "text": s["text"]}
                 for s in sig if "sensitive" not in s["flags"]]
        data, meta = llm.ask(
            "You are a senior B2B sales researcher. You judge how strongly each fact about a prospect gives a "
            "reason to talk about the seller's product now.",
            f"Seller: {SELLER['company']}: {SELLER['one_liner']}. Workflows: {', '.join(SELLER['workflows'])}.\n"
            f"Why a fact can matter to the seller (trigger keys): {SELLER['pain_triggers']}\n\n"
            f"Prospect: {pr['name']}, {pr['title']} at {co['name']} ({pr.get('tenure_days')} days in role).\n"
            f"Facts:\n{llm.src(brief)}\n\n"
            "For EACH fact return: id, relevance (0-5: how directly it creates or reveals finance back-office work "
            "this person owns; 0 = unrelated), trigger (one key from the list or null), "
            "consequence (one plain sentence: what extra work this fact plausibly creates for this person; hedge with "
            "'usually' or 'tends to'; no new facts). Return {\"scores\": [...]}", tag="relevance")
        rel = {x.get("id"): x for x in data.get("scores", [])}
        self.log(f"Relevance scored by {meta['model']}{' (cached)' if meta['cached'] else ''}")
        lo, hi = config.NEW_ROLE_WINDOW
        for s in sig:
            r = rel.get(s["id"], {})
            relevance = float(r.get("relevance") or 0)
            age = s.get("age_days")
            if s["kind"] == "background":
                recency = 2.0
            elif age is None:
                recency = 1.0
            else:
                recency = 5 if age <= 30 else 4 if age <= 60 else 3 if age <= 120 else 2 if age <= config.STALE_DAYS else 0
            personal = 5 if s["about"] == "person" else 3 if s["kind"] in ("news", "job_post") else 2
            source = min(5, 3 + s.get("coverage", 1)) if s["kind"] == "news" else 4
            bonus = 0.5 if s["kind"] == "new_role" and pr.get("tenure_days") and lo <= pr["tenure_days"] <= hi else 0
            score = (config.W_RELEVANCE * min(5, relevance + bonus) + config.W_RECENCY * recency
                     + config.W_PERSONAL * personal + config.W_SOURCE * source)
            penalty = config.CROWDED_PENALTY if "crowded" in s["flags"] else 0
            s["score"] = {"relevance": relevance, "recency": recency, "personal": personal, "source": source,
                          "bonus": bonus, "penalty": penalty, "total": round(max(0, score - penalty), 2)}
            s["trigger"], s["consequence"] = r.get("trigger"), r.get("consequence")
            blocked = [f for f in s["flags"] if f in ("sensitive", "stale", "competitor", "unreliable")]
            s["eligible"] = not blocked and s["kind"] != "background" and relevance >= 2
            if blocked:
                s["why_not"] = "Excluded: " + ", ".join(blocked)
            elif s["kind"] == "background":
                s["why_not"] = "Background: supports the message, never opens it"
            elif relevance < 2:
                s["why_not"] = "Not connected to what Zamp solves"
        ranked = sorted([s for s in sig if s.get("eligible")], key=lambda s: -s["score"]["total"])
        for s in sig:
            if "score" in s:
                self.log(f"{s['id']} {s['score']['total']:.2f} · {s['text'][:80]}"
                         + (f" · {s['why_not']}" if s.get("why_not") else ""))
        if not ranked or ranked[0]["score"]["total"] < config.MIN_HOOK_SCORE:
            best = ranked[0]["score"]["total"] if ranked else 0
            self.run["question"] = {"kind": "low_signal",
                                    "text": f"Nothing specific enough to write a personal email (best hook scored {best:.1f}, needs {config.MIN_HOOK_SCORE}).",
                                    "options": [{"id": "generic", "label": "Write a short role-based email, marked low personalisation"},
                                                {"id": "stop", "label": "Don't email yet", "detail": "Re-run next month."}]}
            if not self.run.get("allow_generic"):
                raise Pause("Signal too thin. Rep decides")
        hook = ranked[0] if ranked else None
        support = next((s for s in sig if s["about"] == "person" and s is not hook
                        and not set(s["flags"]) & {"sensitive", "stale"}), None)
        crowded = [s for s in sig if "crowded" in s["flags"] and s["kind"] == "news"
                   and not set(s["flags"]) & {"sensitive", "off_topic", "competitor"} and s is not hook]
        context = crowded[0] if crowded else next((s for s in ranked[1:] if s is not support and s["about"] == "company"), None)
        for i, s in enumerate(ranked[1:], 2):
            if not s.get("why_not"):
                s["why_not"] = f"Ranked #{i}: lower score than the chosen hook"
        self.run["hook"] = {"id": hook["id"] if hook else None, "support": support["id"] if support else None,
                            "context": context["id"] if context else None,
                            "ranking": [s["id"] for s in ranked]}
        if hook:
            hook["why_chosen"] = "Highest score among eligible signals" + (
                ", after the crowded story lost points" if any("crowded" in s["flags"] for s in sig) else "")
            self.log(f"Hook: {hook['text']}")
            return f"Hook: {hook.get('label') or hook['text'][:90]}"
        return "No hook. Low-personalisation draft"

    # ---------------------------------------------------------------- draft
    def s_draft(self):
        sig = {s["id"]: s for s in self.run["signals"]}
        h = self.run["hook"]
        pr, co = self.run["person"], self.run["company"]
        bg = next((s for s in self.run["signals"] if s["kind"] == "background"), None)
        roles = [(h["id"], "hook"), (h["support"], "person"), (bg["id"] if bg else None, "person_background"),
                 (h["context"], "optional_context")]
        facts = [{"id": sig[i]["id"], "role": role, "text": sig[i]["text"], "date": sig[i].get("date"),
                  "consequence": sig[i].get("consequence"),
                  "rules": (["do not state any amount or number from this fact"] if sig[i].get("no_numbers") else [])
                           + (["never use this in the first sentence"] if "crowded" in sig[i]["flags"] else [])}
                 for i, role in roles if i]
        first = (pr["name"] or "").split()[0]
        proof = [{"i": i, **p} for i, p in enumerate(SELLER["proof"])]
        issues, out = [], None
        for attempt in range(2):
            prompt = (
                f"Write a first-touch cold email from an SDR at {SELLER['company']} ({SELLER['one_liner']}).\n"
                f"Recipient: {pr['name']}, {pr['title']} at {co['name']}.\n"
                f"Facts you may use (and nothing else about the prospect):\n{llm.src(facts)}\n"
                f"Customer results you may cite (pick at most two that fit this company best):\n{llm.src(proof)}\n\n"
                f"Structure: 'Hi {first},' on its own line. Sentence 1: the hook fact in plain words. Sentence 2: the "
                "work it usually creates for this person, hedged ('usually', 'tends to'), not asserted. If person or "
                "person_background facts are given, connect to them in one short clause (e.g. their time in the role, or "
                "that they have run finance at a similar company before) without flattery. Then ONE customer result "
                f"that fits this company best (two only if both fit). Then one low-friction ask ({SELLER['ask']}). "
                f"Under 100 words in the body. Tone: {SELLER['tone']}. Use absolute dates or none, never 'last week'. "
                "Write results as the customer's result ('Instacart cut ...'), not 'we cut'. "
                "Never narrate the reader's own life back to them ('You became CFO in July'); refer to it naturally "
                "('A few months into the CFO seat', 'Coming from Tesla's finance team'). The optional_context fact, if "
                "used, goes in sentence 2 or later, never first. "
                "No flattery, no 'congrats', no 'I noticed', no 'I hope', no exclamation marks, no emojis, no placeholders "
                "except sign the email '[Your name]'. Subject: under 7 words, lowercase except names, no clickbait.\n"
                "Return {\"subject\": str, \"body\": str, \"claims\": [{\"text\": exact sentence from the body that states a fact, "
                "\"facts\": [fact ids], \"proof\": [proof i]}]}. Every sentence with a fact about the prospect or a "
                "customer result must appear in claims."
                + (f"\n\nYour previous draft broke these rules, fix all of them: {issues}" if issues else ""))
            out, meta = llm.ask("You write short, specific B2B emails that a senior finance leader would actually read.",
                                prompt, temperature=0.4, tag="draft")
            issues = self._lint(out, sig)
            self.log(f"Draft {attempt + 1} by {meta['model']}{' (cached)' if meta['cached'] else ''}: "
                     + ("passes the rules" if not issues else f"{len(issues)} rule problems: " + "; ".join(issues)),
                     "info" if not issues else "warn")
            if not issues:
                break
        out["lint"] = issues
        out["words"] = len(out.get("body", "").split())
        self.run["draft"] = out
        return f"{out['words']} words · " + ("all writing rules pass" if not issues else f"{len(issues)} rule warnings")

    def _lint(self, out, sig):
        body, subj = out.get("body") or "", out.get("subject") or ""
        low = (subj + " " + body).lower()
        issues = []
        words = len(body.split())
        if words > config.MAX_WORDS:
            issues.append(f"body is {words} words (max {config.MAX_WORDS})")
        for b in config.BANNED:
            if b in low:
                issues.append(f"uses the phrase “{b}”")
        if "!" in body:
            issues.append("contains an exclamation mark")
        for c in SELLER["competitors"]:
            if re.search(r"\b" + re.escape(c) + r"\b", body):
                issues.append(f"names a competitor ({c})")
        # numbers must come from a cited fact or proof point
        allowed = " ".join(s["text"] for s in sig.values() if not s.get("no_numbers")) + " " + \
                  " ".join(p["result"] for p in SELLER["proof"])
        for n in re.findall(r"\$?\d[\d,.]*\s?(?:%|[BbMm]\b|billion|million)?", body):
            core = re.sub(r"[^\d.]", "", n).rstrip(".")
            if core and len(core) >= 2 and core not in re.sub(r",", "", allowed):
                issues.append(f"number “{n.strip()}” is not in any source")
        first = re.split(r"(?<=[.?])\s", body.split("\n", 2)[-1].strip() if body.lower().startswith("hi") else body, 1)[0]
        for s in sig.values():
            if "crowded" in s["flags"] and s.get("event_type", s["kind"]) in ("funding",) and re.search(r"\b(raise|raised|funding|series|round)\b", first, re.I):
                issues.append("opens with the crowded funding story")
                break
        ids = set(sig)
        for c in out.get("claims", []):
            for f in c.get("facts", []):
                if f not in ids:
                    issues.append(f"claim cites unknown fact {f}")
                elif "sensitive" in sig[f]["flags"]:
                    issues.append("uses sensitive news")
        return sorted(set(issues))

    # ---------------------------------------------------------------- fact check
    def s_factcheck(self):
        sig = {s["id"]: s for s in self.run["signals"]}
        dr = self.run["draft"]
        claims = dr.get("claims") or []
        pack = []
        for i, c in enumerate(claims):
            srcs = [sig[f]["text"] + " | " + "; ".join(x.get("title") or "" for x in sig[f].get("sources", [])[:3])
                    for f in c.get("facts", []) if f in sig]
            srcs += [f"{SELLER['proof'][p]['customer']} is a {SELLER['company']} customer and, using {SELLER['company']}, {SELLER['proof'][p]['result']}"
                     for p in c.get("proof", []) if isinstance(p, int) and 0 <= p < len(SELLER["proof"])]
            srcs.append(f"About the seller: {SELLER['company']} makes {SELLER['one_liner']} "
                        f"(workflows: {', '.join(SELLER['workflows'])}).")
            pack.append({"i": i, "claim": c.get("text"), "sources": srcs})
        data, meta = llm.ask(
            "You are a strict fact-checker. A claim is supported only if the sources state it or it is a clearly "
            "hedged inference ('usually', 'tends to') from them.",
            f"Claims with their sources:\n{llm.src(pack)}\n\nEmail body:\n{llm.src(dr.get('body'))}\n\n"
            "For each claim return i, verdict (supported | partly | unsupported) and reason (short). Also find any "
            "sentence in the email that states a fact about the prospect but is NOT listed as a claim: return them as "
            "unlisted (list of sentences). Then rate genericness 0-5: could this email be sent to a different company "
            "by changing only the names (5 = fully generic). Return {\"claims\": [...], \"unlisted\": [...], "
            "\"genericness\": int, \"genericness_reason\": str}", tag="factcheck")
        verdicts = {x.get("i"): x for x in data.get("claims", [])}
        for i, c in enumerate(claims):
            v = verdicts.get(i, {})
            c["verdict"], c["reason"] = v.get("verdict", "unsupported"), v.get("reason", "not checked")
            if not c.get("facts") and not c.get("proof"):
                c["verdict"], c["reason"] = "unsupported", "no source cited"
            self.log(f"{c['verdict'].upper():11} {c['text'][:90]}", "info" if c["verdict"] == "supported" else "warn")
        dr["unlisted"] = data.get("unlisted") or []
        for u in dr["unlisted"]:
            self.log(f"Unsourced sentence: {u[:90]}", "warn")
        dr["genericness"] = data.get("genericness")
        dr["genericness_reason"] = data.get("genericness_reason")
        bad = [c for c in claims if c["verdict"] == "unsupported"] + [None] * len(dr["unlisted"])
        if bad:
            dr["approve_blocked"] = f"{len(bad)} claim(s) have no source. Edit or remove them before approving."
        warn = bad or dr.get("lint") or any(c["verdict"] == "partly" for c in claims) or (dr["genericness"] or 0) >= 3
        if self.run["hook"].get("id") is None:
            warn = True
            dr["low_personalisation"] = True
        self.run["outcome"] = "ready_with_warnings" if warn else "ready"
        ok = sum(1 for c in claims if c["verdict"] == "supported")
        return f"{ok}/{len(claims)} claims supported · genericness {dr['genericness']}/5"


class Stop(Exception):
    def __init__(self, msg, run_status="blocked", stage_status="stopped"):
        super().__init__(msg)
        self.run_status, self.stage_status = run_status, stage_status


# ---------------------------------------------------------------- entry points
def start(run, from_stage="intake"):
    t = threading.Thread(target=lambda: Runner(run).go(from_stage), daemon=True)
    t.start()
    return t


def answer(run, option, value=None):
    """Continue a paused run with the rep's choice."""
    q = run.get("question") or {}
    kind = q.get("kind")
    if option == "stop":
        run["status"], run["question"] = "stopped", None
        store.save(run)
        return run
    if kind == "pick_person":
        run["chosen_person_url"] = option
        return start(run, "person") and run
    if kind == "not_found" and option == "linkedin":
        run["input"]["linkedin"] = (value or "").strip()
        return start(run, "intake") and run
    if kind == "job_change":
        mv = run["moved"]
        if option == "follow":
            run["chosen_person_url"] = mv["url"]
            run["followed"] = True
            run["company_candidates"] = [{"id": mv["new_company_id"], "name": mv["new_company"], "domain": None}]
            run["company"] = None
            run["note"] = f"Followed {mv['name']} from {mv['old_company']} to {mv['new_company']}."
            return start(run, "person") and run
        if option == "replace":
            run["replace_title"] = mv.get("old_title") or run["input"].get("title")
            return _replace(run)
    if kind == "low_signal" and option == "generic":
        run["allow_generic"] = True
        return start(run, "hook") and run
    raise ValueError("unknown option")


def _replace(run):
    """Find who holds the departed person's role now, then continue with them."""
    c = Client(run["mode"])
    title = run["replace_title"] or ""
    words = [w for w in re.split(r"[,/|&]| and | of ", title) if len(w.strip()) > 2][:3] or [title]
    ids = [x["id"] for x in run.get("company_candidates") or []]
    try:
        people = c.search_people([
            {"field": "experience.employment_details.current.company_id", "type": "in", "value": ids},
            {"op": "or", "conditions": [{"field": "experience.employment_details.current.title", "type": "(.)",
                                         "value": w.strip()} for w in words]}], "Find current role holder", limit=3)
    except CrustError as e:
        run["status"], run["error"] = "failed", {"code": e.code, "msg": str(e)}
        store.save(run)
        return run
    run["credits"] = round(run.get("credits", 0) + c.spent, 2)
    run["calls"] = run.get("calls", []) + c.calls
    if not people:
        run["status"], run["question"] = "not_found", None
        run["error"] = {"code": "not_found", "msg": f"No one at the company has a title like “{title}”."}
        store.save(run)
        return run
    p = sorted(people, key=lambda p: max((j.get("start_date") or "" for j in p["experience"]["employment_details"]["current"]), default=""),
               reverse=True)[0]
    run["chosen_person_url"] = profile_url(p)
    run["note"] = f"{run['moved']['name']} left; continuing with {p['basic_profile']['name']}, who holds the role now."
    run["input"]["name"] = p["basic_profile"]["name"]
    return start(run, "person") and run
