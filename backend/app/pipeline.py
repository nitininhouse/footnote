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
from .seller import DO_NOT_CONTACT, FINANCE_TITLE_WORDS, PLAYBOOK, SELLER

NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
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
        ("signals", "Number every fact"),
        ("hook", "Agent: choose the hook and write"),
        ("factcheck", "Check the citations"),
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
        # Existing customer? Checked before any paid lookup.
        hit = DO_NOT_CONTACT.get(norm(inp["company"]))
        if not hit and cands[0].get("domain") in DO_NOT_CONTACT.values():
            hit = cands[0]["domain"]
        if hit:
            self.check("customer", "block", f"{inp['company']} is already a Zamp customer",
                       "Existing customers go to their account team, not cold outreach. No credits spent.")
            raise Stop(f"{inp['company']} ({hit}) is already a Zamp customer. Hand this to the account team instead "
                       "of sending a cold email. No credits were spent.", "blocked")
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
            "description": ((c.get("basic_info") or {}).get("description") or "")[:600],
            "country": h.get("largest_headcount_country"),
            "company_type": (c.get("basic_info") or {}).get("company_type"),
            "revenue_usd": [((c.get("revenue") or {}).get("estimated") or {}).get(k) for k in ("lower_bound_usd", "upper_bound_usd")],
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

    # ---------------------------------------------------------------- facts (code only: number every Crustdata fact)
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
        for j in pr["past"][:5]:
            if j["company"]:
                add(kind="background", about="person", date=(j["end"] or "")[:10] or None,
                    text=f"Previously {j['title']} at {j['company']} ({(j['start'] or '')[:4]}–{(j['end'] or '')[:4] or 'now'})"
                         + (f": “{j['description'][:200]}”" if j["description"] else "."),
                    sources=[{"label": "LinkedIn profile (via Crustdata)", "url": pr["url"]}])
        if cs["last_round"] and cs["last_round"]["date"]:
            lr = cs["last_round"]
            add(kind="funding", about="company", date=lr["date"],
                text=f"{co['name']} raised a {lr['type']}" + (f" of {fmt_usd(lr['amount'])}" if lr["amount"] else "")
                     + f" on {lr['date']}" + (f", led by {lr['investors']}" if lr.get("investors") else "") + ".",
                sources=[{"label": "Crustdata funding record", "url": None}])
        if cs["headcount"]:
            add(kind="growth", about="company", date=self.today.isoformat(),
                text=f"{co['name']} has {cs['headcount']:,} employees"
                     + (f", {cs['headcount_yoy']:+.0f}% in the last 12 months." if cs["headcount_yoy"] is not None else "."),
                sources=[{"label": "Crustdata headcount", "url": None}])
        for j in getattr(self, "jobs", []):
            desc = " ".join(((j.get("content") or {}).get("description") or "").split())
            add(kind="job_post", about="company", job_title=j["job_details"]["title"],
                date=((j.get("metadata") or {}).get("date_added") or "")[:10] or None,
                text=f"{co['name']} is hiring a {j['job_details']['title']}.", excerpt=desc[:700],
                sources=[{"label": "Job post", "url": j["job_details"].get("url")}])
        news = [n for n in (self.cdata.get("news") or []) if d(n.get("article_publish_date"))
                and (self.today - d(n["article_publish_date"])).days <= config.NEWS_WINDOW_DAYS]
        seen = set()
        for n in sorted(news, key=lambda n: n["article_publish_date"], reverse=True):
            key = norm(n.get("article_title"))[:80]
            if key in seen:
                continue
            seen.add(key)
            add(kind="news", about="company", date=n["article_publish_date"][:10], text=n.get("article_title") or "",
                label=n.get("article_title"),
                sources=[{"label": n.get("article_publisher_name"), "url": n.get("article_url"),
                          "title": n.get("article_title"), "date": n["article_publish_date"][:10]}])
            if len([s for s in sig if s["kind"] == "news"]) >= 40:
                break
        for s in sig:
            dt = d(s.get("date"))
            s["age_days"] = (self.today - dt).days if dt else None
        self.run["signals"] = sig
        counts = {}
        for s in sig:
            counts[s["kind"]] = counts.get(s["kind"], 0) + 1
        self.log("Facts: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items()))
        return f"{len(sig)} facts, each with a source number"

    # ---------------------------------------------------------------- the agent
    def _brief(self):
        pr, co, cs = self.run["person"], self.run["company"], self.run["company_data"]
        facts = []
        for s in self.run["signals"]:
            f = {"id": s["id"], "kind": s["kind"], "date": s.get("date"), "fact": s["text"]}
            if s.get("excerpt"):
                f["job_description_excerpt"] = s["excerpt"]
            if s["kind"] == "news":
                f["outlet"] = s["sources"][0].get("label")
            facts.append(f)
        return {
            "prospect": {"name": pr["name"], "title": pr["title"], "company": co["name"],
                         "in_role_since": (pr.get("start") or "")[:7], "days_in_role": pr.get("tenure_days"),
                         "headline": pr.get("headline")},
            "company": {"name": co["name"], "what_it_does": cs.get("description"), "main_country": cs.get("country"),
                        "ownership": cs.get("company_type"), "estimated_revenue_usd": cs.get("revenue_usd"),
                        "employees": cs.get("headcount")},
            "rep_notes": self.run["input"].get("notes") or None,
            "facts": facts,
            "zamp_customer_results": [{"i": i, "customer": p["customer"], "result": p["result"]} for i, p in enumerate(SELLER["proof"])],
            "today": self.today.isoformat(),
        }

    def s_hook(self):
        sig = {s["id"]: s for s in self.run["signals"]}
        ask = ("Read the whole brief, choose the hook and write the email. Cite fact ids for every factual sentence. "
               "Return JSON: {"
               '"hook": [fact ids the email opens on: one, or several about the same kind of event], '
               '"why": "why this hook, in two sentences", "angle": "the finance work it creates for this person", '
               '"not_chosen": [{"id", "reason"}] for the 5 strongest alternatives, '
               '"confidence": "high"|"medium"|"low", '
               '"subject": str, "body": str, '
               '"claims": [{"text": exact sentence from the body, "facts": [fact ids], "proof": [customer result i]}]}. '
               "Claims are ONLY sentences that state a fact from the brief or a customer result. Do not list questions, "
               "guesses about their work, greetings or the ask.")
        data, meta = llm.ask(PLAYBOOK, f"Research brief:\n{llm.src(self._brief())}\n\n{ask}",
                             tag="agent", prefer="gemini", temperature=0.4, max_tokens=8000,
                             required=("subject", "body", "hook"))
        self.log(f"Agent: {meta['model']}{' (cached)' if meta['cached'] else ''}, {meta['ms'] / 1000:.1f} s")
        if meta.get("fallback_reason"):
            self.log(f"Gemini did not answer ({meta['fallback_reason'][:160]}), so {meta['model']} wrote this draft.", "warn")
        hook_ids = [h for h in (data.get("hook") or []) if h in sig]
        for x in data.get("not_chosen") or []:
            if x.get("id") in sig:
                sig[x["id"]]["reason"] = x.get("reason")
                sig[x["id"]]["use"] = "not chosen"
        for h in hook_ids:
            sig[h]["use"] = "hook"
        bad = [x for x in data.get("not_chosen") or [] if x.get("id") in sig and str(x.get("reason", "")).lower().startswith("bad news")]
        for x in bad:
            sig[x["id"]]["use"] = "left out"
            self.check("sensitive", "pass", "Bad news found and left out", f"{sig[x['id']].get('label') or sig[x['id']]['text']}", [x["id"]])
            self.log(f"Left out (bad news): {(sig[x['id']].get('label') or sig[x['id']]['text'])[:90]}", "warn")
        self.run["hook"] = {"ids": hook_ids, "id": hook_ids[0] if hook_ids else None, "why": data.get("why"),
                            "angle": data.get("angle"), "confidence": data.get("confidence"), "model": meta["model"],
                            "not_chosen": [x.get("id") for x in data.get("not_chosen") or [] if x.get("id") in sig],
                            "support": [], "context": None, "ranking": []}
        body = data.get("body") or ""
        self.run["draft"] = {"subject": data.get("subject") or "", "body": body, "claims": data.get("claims") or [],
                             "words": len(body.split()), "writer": meta["model"], "lint": [], "issues": [],
                             "fallback_reason": meta.get("fallback_reason") or ""}
        for h in hook_ids:
            self.log(f"Hook: {sig[h].get('label') or sig[h]['text']}")
        self.log(f"Why: {data.get('why')}")
        self.log(f"Confidence: {data.get('confidence')}")
        first = sig[hook_ids[0]] if hook_ids else None
        return (f"Hook: {(first.get('label') or first['text'])[:90]}" if first else "No clear hook") + \
            f" · {self.run['draft']['words']}-word draft"

    # ---------------------------------------------------------------- citations (code: does each cited source exist?)
    def s_factcheck(self):
        sig = {s["id"]: s for s in self.run["signals"]}
        dr = self.run["draft"]
        notes = []
        dr["claims"] = [c for c in dr["claims"] if c.get("facts") or c.get("proof")]   # facts only
        for c in dr["claims"]:
            known = [f for f in c.get("facts", []) if f in sig]
            proof = [p for p in c.get("proof", []) if isinstance(p, int) and 0 <= p < len(SELLER["proof"])]
            c["facts"], c["proof"] = known, proof
            in_body = (c.get("text") or "") in dr["body"]
            if (known or proof) and in_body:
                c["verdict"], c["reason"] = "cited", "Cites " + ", ".join(known + [f"Zamp result {p + 1}" for p in proof])
            else:
                c["verdict"] = "uncited"
                c["reason"] = "Sentence not found in the email (it may have been edited)" if not in_body else "Cited source not found"
        # Numbers: every number in a factual sentence must appear in what it cites.
        def nums(t):
            return {n.replace(",", "").rstrip(".") for n in NUM.findall(t or "")}
        proof_text = [f"{p['customer']} {p['result']}" for p in SELLER["proof"]]
        all_src = " ".join([s["text"] + " " + (s.get("excerpt") or "") for s in sig.values()] + proof_text)
        for c in dr["claims"]:
            if c["verdict"] != "cited":
                continue
            cited = " ".join([sig[f]["text"] + " " + (sig[f].get("excerpt") or "") for f in c["facts"]] +
                             [proof_text[p] for p in c["proof"]])
            missing = nums(c["text"]) - nums(cited)
            if missing:
                c["verdict"] = "uncited"
                c["reason"] = f"The number {', '.join(sorted(missing))} is not in the cited source"
        body_missing = {n for n in nums(dr["body"]) - nums(all_src) if not (len(n) == 4 and n.startswith("20"))}
        if body_missing:
            notes.append(f"Number not found in any source: {', '.join(sorted(body_missing))}")
        low = (dr["subject"] + " " + dr["body"]).lower()
        hits = [b for b in config.BANNED if b in low]
        if hits:
            notes.append("Sales clichés: " + ", ".join(f"“{b}”" for b in hits))
        if dr["words"] > config.MAX_WORDS:
            notes.append(f"{dr['words']} words, longer than {config.MAX_WORDS}")
        if dr.get("fallback_reason") and not str(dr.get("writer", "")).startswith("gemini"):
            notes.append(f"Written by the backup model ({dr['writer']}) because Gemini did not answer. Read it carefully")
        if self.run["hook"].get("confidence") == "low" or not self.run["hook"].get("ids"):
            dr["low_personalisation"] = True
            notes.append("The agent found no strong reason to write")
        dr["lint"] = notes
        dr["proofs"] = [f"{p['customer']} {p['result']}" for p in SELLER["proof"]]
        ok = sum(1 for c in dr["claims"] if c["verdict"] == "cited")
        self.run["outcome"] = "ready" if ok == len(dr["claims"]) and not notes else "ready_with_warnings"
        for c in dr["claims"]:
            self.log(f"{c['verdict'].upper():8} {c['text'][:90]}", "info" if c["verdict"] == "cited" else "warn")
        return f"{ok}/{len(dr['claims'])} sentences cite a source"


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
