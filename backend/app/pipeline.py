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
from .seller import FINANCE_TITLE_WORDS, PLAYBOOK, REVIEWER, SELLER

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
        ("hook", "Choose the hook"),
        ("draft", "Write the draft"),
        ("factcheck", "Independent review"),
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
            add(kind="job_post", about="company", job_title=j["job_details"]["title"], date=((j.get("metadata") or {}).get("date_added") or "")[:10] or None,
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
            "marketing, layoffs, legal, security, award, other), items (list of i), "
            "sensitive (true only if the event itself is bad news for the company or its people: layoffs, lawsuits, "
            "investigations, breaches, deaths, bankruptcy, scandals; read the headline in context, e.g. 'nearly died "
            "two years ago, now worth $20B' is a success story, not sensitive), "
            "sensitive_reason (short, or empty), "
            "about_company (false if mainly about another company, a listicle, a how-to for shoppers, a funding "
            "database page, or only a passing mention), "
            "summary (one factual sentence using only facts in the headlines). "
            'Return {"events": [...]} with every headline used at most once.', tag="news", prefer="gemini")
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
            s = add(kind="news", event_type=ev.get("type", "other"), about="company", date=first,
                    text=ev.get("summary") or ev.get("label"), label=ev.get("label"),
                    coverage=len(outlets), flags=[], amounts=sorted(set(money_usd(titles))),
                    judge1={"model": meta["model"], "sensitive": bool(ev.get("sensitive")),
                            "about_company": ev.get("about_company", True), "reason": ev.get("sensitive_reason") or ""},
                    sources=[{"label": a.get("article_publisher_name"), "url": a.get("article_url"),
                              "title": a.get("article_title"), "date": a["article_publish_date"][:10]} for a in arts[:12]])
            self.log(f"Event: {s['label']} · {len(outlets)} outlet{'s' if len(outlets) != 1 else ''} · {first}")

    # ---------------------------------------------------------------- guards
    def _second_opinion(self, events):
        """A different model judges every news event on its own, without seeing the first model's labels."""
        co = self.run["company"]["name"]
        pack = [{"id": s["id"], "date": s["date"], "headlines": [x.get("title") for x in s["sources"][:6]]} for s in events]
        data, meta = llm.ask(
            "You review news about a company for a sales team that must never open an email with bad news.",
            f"Company: {co}.\nEvents:\n{llm.src(pack)}\n\nFor each event decide, reading the headlines in context: "
            "sensitive (true only if the event is bad news for the company or its people: layoffs, lawsuits, "
            "investigations, breaches, deaths, bankruptcy, scandals), reason (short), about_company (false if it is "
            "mainly about another company, a listicle or only a passing mention). "
            'Return {"events": [{"id", "sensitive", "reason", "about_company"}]}', tag="news2", prefer="deepseek")
        return {e.get("id"): e for e in data.get("events", [])}, meta

    def s_guards(self):
        sig = self.run["signals"]
        today = self.today
        events = [s for s in sig if s["kind"] == "news"]
        j2, meta2 = self._second_opinion(events) if events else ({}, {"model": "-"})
        if events:
            m1 = events[0]["judge1"]["model"]
            self.log(f"Second opinion on {len(events)} news events from {meta2['model']} (first opinion: {m1})")
            if meta2["model"] == m1:
                self.log("Second model unavailable, the same model answered twice: treat as one opinion.", "warn")
        n_block = 0
        for s in sig:
            dt = d(s.get("date"))
            age = (today - dt).days if dt else None
            s["age_days"] = age
            if s["kind"] == "news":
                a, b = s["judge1"], j2.get(s["id"], {})
                s["judge2"] = {"model": meta2["model"], "sensitive": bool(b.get("sensitive")),
                               "about_company": b.get("about_company", True), "reason": b.get("reason") or ""}
                both_off = not a["about_company"] and not s["judge2"]["about_company"]
                if both_off:
                    s["flags"].append("off_topic")
                    self.check("off_topic", "pass", f"Ignored: “{s.get('label') or s['text'][:60]}”",
                               "Both models: not really about this company.", [s["id"]])
                elif a["sensitive"] and s["judge2"]["sensitive"]:
                    s["flags"].append("sensitive")
                    n_block += 1
                    self.check("sensitive", "block", f"Sensitive, both models agree: “{s.get('label')}”",
                               f"{a['model']}: {a['reason'] or 'sensitive'} · {s['judge2']['model']}: {s['judge2']['reason'] or 'sensitive'}",
                               [s["id"]])
                elif a["sensitive"] != s["judge2"]["sensitive"]:
                    s["flags"].append("disputed")
                    yes = a if a["sensitive"] else s["judge2"]
                    no = s["judge2"] if a["sensitive"] else a
                    self.check("disputed", "warn", f"Models disagree whether this is bad news: “{s.get('label')}”",
                               f"{yes['model']} says sensitive ({yes['reason'] or 'no reason given'}); {no['model']} says not. "
                               "Not used as a hook; the rep can judge.", [s["id"]])
            if s["kind"] not in ("background", "growth", "finance_hiring") and age is not None and age > config.STALE_DAYS:
                s["flags"].append("stale")
                self.check("stale", "warn", f"Too old to open with: {s['text'][:70]}", f"{age} days old (limit {config.STALE_DAYS}).", [s["id"]])
            if s["kind"] == "job_post" and same_title(s.get("job_title"), self.run["person"].get("title")):
                s["flags"].append("own_role")
                self.check("own_role", "block", f"Job post for the prospect's own role: “{s.get('job_title')}”",
                           "Could be their replacement or an old post for the job they hold. Never mentioned.", [s["id"]])
            text = s["text"] + " " + " ".join((x.get("title") or "") for x in s.get("sources", []))
            comp = [c for c in SELLER["competitors"] if re.search(r"\b" + re.escape(c) + r"\b", text)]
            if comp:
                s["flags"].append("competitor")
                self.check("competitor", "warn", f"Mentions a competitor ({', '.join(comp)})",
                           "Not used as a hook: it would advertise the competitor.", [s["id"]])
        # Crowded: the same event reported everywhere -> every other rep will open with it too.
        for s in sig:
            if s["kind"] == "news" and not set(s["flags"]) & {"off_topic", "sensitive"} \
                    and s.get("event_type") in ("funding", "acquisition", "product", "leadership") \
                    and s["coverage"] >= config.CROWDED_OUTLETS:
                s["flags"].append("crowded")
                self.check("crowded", "warn", f"Crowded: “{s.get('label')}” was covered by {s['coverage']} outlets",
                           "Every other rep will open with this. It can be context, not the opening line.", [s["id"]])
                fund = next((f for f in sig if f["kind"] == "funding"), None)
                if fund and s.get("event_type") == "funding":
                    fund["flags"].append("crowded")
        # Conflict: the database and the press disagree on a number.
        fund = next((f for f in sig if f["kind"] == "funding"), None)
        if fund and fund.get("amount"):
            for s in sig:
                if s["kind"] == "news" and s.get("event_type") == "funding" and s.get("amounts"):
                    close = [a for a in s["amounts"] if abs(a - fund["amount"]) / fund["amount"] < 0.5]
                    if close and all(abs(a - fund["amount"]) / fund["amount"] > 0.001 for a in close):
                        for x in (fund, s):
                            x["flags"].append("conflict")
                            x["no_numbers"] = True
                        self.check("conflict", "warn",
                                   f"Sources disagree on the amount: database {fmt_usd(fund['amount'])}, press {', '.join(fmt_usd(a) for a in close)}",
                                   "The email may mention the round but not the amount.", [fund["id"], s["id"]])
        # Suspicious statistic: open roles collapse while the press reports expansion.
        oj = [v for _, v in self.run["company_data"]["open_jobs"] if v is not None]
        expanding = [s for s in sig if s["kind"] == "news" and s.get("event_type") == "expansion"
                     and (s.get("age_days") or 999) <= 60 and "off_topic" not in s["flags"]]
        if len(oj) >= 4 and max(oj) >= 20 and oj[-1] <= 0.2 * max(oj):
            msg = f"Open roles fell from {max(oj)} to {oj[-1]} in the data"
            if expanding:
                self.check("anomaly", "warn", msg + ", but the press reports expansion",
                           f"Fresh news wins: “{expanding[0].get('label')}”. Hiring numbers are not used.",
                           [e["id"] for e in expanding])
            else:
                self.check("anomaly", "warn", msg, "Could be a freeze or a gap in the data. Hiring numbers are not used.")
            for s in sig:
                if s["kind"] == "finance_hiring":
                    s["flags"].append("unreliable")
        self.log(f"{len(self.run['checks'])} checks, {n_block} blocked")
        return f"{sum(1 for c in self.run['checks'] if c['status'] != 'pass')} findings · two models judged the news"

    # ---------------------------------------------------------------- the brief every model reads
    FLAG_TEXT = {"crowded": "reported by many outlets; never the opening line",
                 "conflict": "sources disagree on its numbers; never state the numbers",
                 "stale": "too old to open with", "sensitive": "bad news; never use",
                 "disputed": "models disagree whether this is bad news; never use",
                 "own_role": "job post for the prospect's own role; never mention",
                 "competitor": "mentions a competitor; never use", "unreliable": "statistic contradicts fresher news; ignore"}
    BLOCKING = {"sensitive", "disputed", "own_role", "competitor", "unreliable", "stale", "off_topic"}

    def _brief(self, with_flags=True):
        pr, co, cs = self.run["person"], self.run["company"], self.run["company_data"]
        facts = []
        for s in self.run["signals"]:
            if "off_topic" in s["flags"]:
                continue
            f = {"id": s["id"], "kind": s["kind"] if s["kind"] != "news" else f"news/{s.get('event_type')}",
                 "about": s["about"], "date": s.get("date"), "age_days": s.get("age_days"), "fact": s["text"]}
            if s["kind"] == "news":
                f["outlets"] = s["coverage"]
                f["headlines"] = [x.get("title") for x in s["sources"][:3]]
            if with_flags and s["flags"]:
                f["flags"] = {fl: self.FLAG_TEXT.get(fl, fl) for fl in s["flags"]}
            facts.append(f)
        return {
            "prospect": {"name": pr["name"], "title": pr["title"], "company": co["name"],
                         "in_role_since": (pr.get("start") or "")[:7], "days_in_role": pr.get("tenure_days"),
                         "headline": pr.get("headline"),
                         "past_roles": [f"{j['title']} at {j['company']} ({(j['start'] or '')[:4]}-{(j['end'] or '')[:4]})" for j in pr["past"][:5]]},
            "company": {"name": co["name"], "description": cs.get("description"), "employees": cs.get("headcount"),
                        "employee_growth_12m_pct": round(cs["headcount_yoy"]) if cs.get("headcount_yoy") is not None else None},
            "rep_notes": self.run["input"].get("notes") or None,
            "facts": facts,
            "zamp_customer_results": [{"i": i, "customer": p["customer"], "result": p["result"]} for i, p in enumerate(SELLER["proof"])],
            "today": self.today.isoformat(),
        }

    # ---------------------------------------------------------------- hook
    def s_hook(self):
        brief = self._brief()
        sig = {s["id"]: s for s in self.run["signals"]}
        ask = ("Choose the hook for this prospect. Assess EVERY fact. Return JSON: "
               '{"assessments": [{"id", "use": "hook"|"support"|"context"|"skip", "fit": 1-5, "reason": one short sentence}], '
               '"hook": [fact ids the email opens on; one id, or several of the same kind of event], '
               '"support": [person fact ids to connect in one clause, may be empty], "context": fact id or null, '
               '"angle": "the finance work this creates for this person, one sentence", '
               '"why": "why this hook beats the others, two sentences max", "confidence": "high"|"medium"|"low"}')
        problems = ""
        for attempt in range(2):
            data, meta = llm.ask(PLAYBOOK, f"Research brief:\n{llm.src(brief)}\n\n{ask}{problems}",
                                 tag="strategist", prefer="gemini", max_tokens=6000)
            hook_ids = [h for h in (data.get("hook") or []) if h in sig] if isinstance(data.get("hook"), list) \
                else [data.get("hook")] if data.get("hook") in sig else []
            bad = [h for h in hook_ids if set(sig[h]["flags"]) & self.BLOCKING or "crowded" in sig[h]["flags"]
                   or sig[h]["kind"] == "background"]
            self.log(f"Strategist ({meta['model']}{', cached' if meta['cached'] else ''}) chose {hook_ids or 'nothing'}, "
                     f"confidence {data.get('confidence')}")
            if not bad:
                break
            problems = ("\n\nYour previous choice broke the rules: " + "; ".join(
                f"{h} is flagged {', '.join(sig[h]['flags']) or sig[h]['kind']}" for h in bad) + ". Choose again.")
            self.log("Code rejected that hook: " + problems.strip(), "warn")
            hook_ids = []
        for a in data.get("assessments", []):
            s = sig.get(a.get("id"))
            if s:
                s["fit"], s["use"], s["reason"] = a.get("fit"), a.get("use"), a.get("reason")
        for s in sig.values():
            if s["id"] in hook_ids:
                s["use"] = "hook"
        self.run["hook"] = {"ids": hook_ids, "id": hook_ids[0] if hook_ids else None,
                            "support": [x for x in (data.get("support") or []) if x in sig],
                            "context": data.get("context") if data.get("context") in sig else None,
                            "angle": data.get("angle"), "why": data.get("why"),
                            "confidence": data.get("confidence"), "model": meta["model"],
                            "ranking": [a["id"] for a in sorted(data.get("assessments", []), key=lambda a: -(a.get("fit") or 0)) if a.get("id") in sig]}
        if not hook_ids or data.get("confidence") == "low":
            self.run["question"] = {"kind": "low_signal",
                                    "text": "Nothing gives a real reason to write to this person now. " + (data.get("why") or ""),
                                    "options": [{"id": "generic", "label": "Write a short role-based email, marked low personalisation"},
                                                {"id": "stop", "label": "Don't email yet", "detail": "Re-run next month."}]}
            if not self.run.get("allow_generic"):
                raise Pause("Signal too thin. Rep decides")
        for h in hook_ids:
            self.log(f"Hook: {sig[h].get('label') or sig[h]['text']}")
        self.log(f"Why: {data.get('why')}")
        first = sig[hook_ids[0]] if hook_ids else None
        return f"Hook: {(first.get('label') or first['text'])[:90]}" + (f" (+{len(hook_ids) - 1} more)" if len(hook_ids) > 1 else "") \
            if first else "No hook. Low-personalisation draft"

    # ---------------------------------------------------------------- draft
    def _write(self, notes=""):
        h = self.run["hook"]
        plan = {k: h.get(k) for k in ("ids", "support", "context", "angle", "why")}
        plan["hook"] = plan.pop("ids")
        ask = ("Write the email following the plan. Return JSON: "
               '{"subject": "under 7 words, lowercase except names", "body": str, '
               '"claims": [{"text": exact sentence from the body that states a fact, "facts": [fact ids], "proof": [customer result i]}]}. '
               "Every sentence that states a fact about the prospect, the company or a customer result must be a claim.")
        data, meta = llm.ask(PLAYBOOK, f"Research brief:\n{llm.src(self._brief())}\n\nPlan from the strategist:\n{llm.src(plan)}\n\n{ask}{notes}",
                             tag="writer", prefer="gemini", temperature=0.4)
        return data, meta

    def s_draft(self):
        sig = {s["id"]: s for s in self.run["signals"]}
        out, meta = self._write()
        issues = self._lint(out, sig)
        if issues:
            self.log(f"Draft by {meta['model']} broke {len(issues)} hard rules: " + "; ".join(issues), "warn")
            out, meta = self._write("\n\nYour previous draft broke these rules, fix all of them: " + "; ".join(issues))
            issues = self._lint(out, sig)
        self.log(f"Draft by {meta['model']}{' (cached)' if meta['cached'] else ''}: "
                 + ("passes the hard rules" if not issues else "; ".join(issues)), "info" if not issues else "warn")
        out["lint"], out["words"], out["writer"] = issues, len(out.get("body", "").split()), meta["model"]
        out["rounds"] = []
        self.run["draft"] = out
        return f"{out['words']} words · " + ("passes the hard rules" if not issues else f"{len(issues)} rule warnings")

    def _lint(self, out, sig):
        """Exact checks only: things with one right answer."""
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
        allowed = re.sub(r",", "", " ".join(s["text"] + " " + " ".join(x.get("title") or "" for x in s.get("sources", []))
                                             for s in sig.values() if not s.get("no_numbers"))
                         + " " + " ".join(p["result"] for p in SELLER["proof"]))
        for n in re.findall(r"\$?\d[\d,.]*\s?(?:%|[BbMm]\b|billion|million)?", body):
            core = re.sub(r"[^\d.]", "", n).rstrip(".")
            if core and len(core) >= 2 and core not in allowed:
                issues.append(f"number “{n.strip()}” is not in any source")
        for c in out.get("claims", []):
            for f in c.get("facts", []):
                if f not in sig:
                    issues.append(f"claim cites unknown fact {f}")
                elif set(sig[f]["flags"]) & (self.BLOCKING - {"stale"}):
                    issues.append(f"cites {f}, which is flagged {', '.join(set(sig[f]['flags']) & self.BLOCKING)}")
        return sorted(set(issues))

    # ---------------------------------------------------------------- independent review
    def _review(self, dr):
        brief = self._brief(with_flags=True)
        claims = [{"i": i, "text": c.get("text"), "cites": c.get("facts", []), "proof": c.get("proof", [])}
                  for i, c in enumerate(dr.get("claims") or [])]
        ask = ("Review this email. Return JSON: "
               '{"claims": [{"i", "verdict": "supported"|"partly"|"unsupported", "reason"}], '
               '"unlisted": [{"sentence": str, "checkable_fact": true|false, "supported": true|false}] for sentences not in claims '
               '(a checkable fact names a specific event, number, date, person or company; hedged inferences, questions, '
               'greetings and the sign-off are not checkable facts), '
               '"issues": [{"severity": "block"|"warn", "sentence": str, "problem": str}], '
               '"genericness": 0-5, "genericness_reason": str, "verdict": "pass"|"fix"}. '
               "Use severity block for anything false, illogical or embarrassing for this reader.")
        return llm.ask(REVIEWER, f"Research brief:\n{llm.src(brief)}\n\nEmail subject: {dr.get('subject')}\nEmail body:\n"
                                 f"{llm.src(dr.get('body'))}\n\nClaims with the facts they cite:\n{llm.src(claims)}\n\n{ask}",
                       tag="review", prefer="deepseek", max_tokens=4000)

    def s_factcheck(self):
        sig = {s["id"]: s for s in self.run["signals"]}
        dr = self.run["draft"]
        for rnd in range(2):
            rv, meta = self._review(dr)
            independent = meta["model"] != dr.get("writer")
            blocks = [x for x in rv.get("issues", []) if x.get("severity") == "block"]
            dr["rounds"].append({"reviewer": meta["model"], "independent": independent, "issues": rv.get("issues", []),
                                 "verdict": rv.get("verdict"), "body": dr.get("body")})
            self.log(f"Review {rnd + 1} by {meta['model']}{' (cached)' if meta['cached'] else ''}"
                     f"{'' if independent else ' (same model as the writer: not independent)'}: "
                     f"{len(blocks)} blocking, {len(rv.get('issues', [])) - len(blocks)} minor", "info" if not blocks else "warn")
            for x in rv.get("issues", []):
                self.log(f"{x.get('severity', '').upper()}: {x.get('problem')} — “{(x.get('sentence') or '')[:80]}”",
                         "warn" if x.get("severity") == "block" else "info")
            if not blocks or rnd == 1:
                break
            notes = "\n\nAn independent reviewer found these problems; fix every one and keep everything else: " + \
                    "; ".join(f"“{x.get('sentence')}”: {x.get('problem')}" for x in blocks)
            out, wmeta = self._write(notes)
            out["lint"], out["words"], out["writer"], out["rounds"] = self._lint(out, sig), len(out.get("body", "").split()), wmeta["model"], dr["rounds"]
            dr = self.run["draft"] = out
            self.log(f"Rewritten by {wmeta['model']} with the reviewer's notes")
        verdicts = {x.get("i"): x for x in rv.get("claims", [])}
        claims = dr.get("claims") or []
        for i, c in enumerate(claims):
            v = verdicts.get(i, {})
            c["verdict"], c["reason"] = v.get("verdict", "unsupported"), v.get("reason", "not checked")
            if not c.get("facts") and not c.get("proof"):
                c["verdict"], c["reason"] = "unsupported", "no source cited"
        # only specific, checkable facts the reviewer could not support count against the email
        dr["unlisted"] = [u.get("sentence") if isinstance(u, dict) else u for u in (rv.get("unlisted") or [])
                          if isinstance(u, dict) and u.get("checkable_fact") and not u.get("supported")]
        dr["issues"] = rv.get("issues") or []
        dr["reviewer"] = meta["model"]
        dr["genericness"], dr["genericness_reason"] = rv.get("genericness"), rv.get("genericness_reason")
        open_blocks = [x for x in dr["issues"] if x.get("severity") == "block"]
        bad = [c for c in claims if c["verdict"] == "unsupported"]
        if bad or dr["unlisted"] or open_blocks:
            dr["approve_blocked"] = (f"{len(bad) + len(dr['unlisted'])} unsupported claim(s), {len(open_blocks)} blocking issue(s) "
                                     "from the reviewer. Edit the email before approving.")
        warn = bad or open_blocks or dr.get("lint") or any(c["verdict"] == "partly" for c in claims) \
            or (dr["genericness"] or 0) >= 3 or dr["issues"]
        if not self.run["hook"].get("id"):
            warn, dr["low_personalisation"] = True, True
        self.run["outcome"] = "ready_with_warnings" if warn else "ready"
        ok = sum(1 for c in claims if c["verdict"] == "supported")
        return f"{meta['model']}: {ok}/{len(claims)} claims supported · {len(open_blocks)} blocking issues · rounds {len(dr['rounds'])}"


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
