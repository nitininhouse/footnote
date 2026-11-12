"""The only place that talks to Crustdata.

Live mode always asks Crustdata fresh. An answer is reused only inside the same run (so
picking a person or following a job change doesn't pay twice). Replay mode answers only
from recorded responses and is used by the offline test set.
"""
import hashlib
import json
import time
from datetime import datetime, timezone

import requests

from . import config

API = "https://api.crustdata.com"


class CrustError(RuntimeError):
    def __init__(self, msg, code="error"):
        super().__init__(msg)
        self.code = code


def _key(path, body):
    h = hashlib.sha1((path + json.dumps(body, sort_keys=True)).encode()).hexdigest()[:12]
    return config.CACHE / f"{path.strip('/').replace('/', '_')}_{h}.json"


def spent_today():
    log = config.DATA / "credits.jsonl"
    if not log.exists():
        return 0.0
    today = datetime.now(timezone.utc).date().isoformat()
    total = 0.0
    for line in log.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("at", "").startswith(today):
            total += e.get("credits", 0)
    return total


class Client:
    """One client per run: knows the mode and counts this run's credits."""

    def __init__(self, mode="replay", cap=config.RUN_CREDIT_CAP, run_id=None):
        self.mode, self.cap, self.spent, self.calls, self.run_id = mode, cap, 0.0, [], run_id

    def call(self, path, body, estimate=1.0, label=""):
        f = _key(path, body)
        rec = json.loads(f.read_text()) if f.exists() else None
        if rec and (self.mode != "live" or (self.run_id and rec.get("run") == self.run_id)):
            self.calls.append({"path": path, "label": label, "credits": 0, "cached": True,
                               "recorded_credits": rec.get("credits", 0)})
            return rec["data"]
        if self.mode != "live":
            raise CrustError(f"{label or path}: not recorded yet. Switch to live mode to fetch it.", "not_recorded")
        if not config.CRUSTDATA_KEY:
            raise CrustError("Crustdata key is not set on the server.", "config")
        if self.spent + estimate > self.cap:
            raise CrustError(f"Run credit cap reached ({self.cap}).", "budget")
        if config.DAILY_CREDIT_CAP and spent_today() + estimate > config.DAILY_CREDIT_CAP:
            raise CrustError("Today's credit budget is used up. Replay mode still works.", "budget")
        last = None
        for attempt in range(3):
            try:
                r = requests.post(API + path, json=body, timeout=60, headers={
                    "authorization": f"Bearer {config.CRUSTDATA_KEY}",
                    "content-type": "application/json", "x-api-version": "2025-11-01"})
            except requests.RequestException as e:
                last = CrustError(f"Could not reach Crustdata ({e.__class__.__name__}).", "network")
                time.sleep(1.5 * (attempt + 1))
                continue
            credits = float(r.headers.get("x-credits-used") or 0)
            self.spent += credits
            if credits:
                with open(config.DATA / "credits.jsonl", "a") as log:
                    log.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "path": path,
                                          "credits": credits}) + "\n")
            if r.status_code == 200:
                data = r.json()
                f.write_text(json.dumps({"path": path, "body": body, "credits": credits, "run": self.run_id,
                                         "at": datetime.now(timezone.utc).isoformat(), "data": data}))
                self.calls.append({"path": path, "label": label, "credits": credits, "cached": False})
                return data
            if r.status_code in (429, 500, 502, 503, 504):
                wait = float(r.headers.get("x-ratelimit-reset") or 2 * (attempt + 1))
                time.sleep(min(wait, 10))
                last = CrustError(f"Crustdata busy ({r.status_code}).", "busy")
                continue
            if r.status_code == 402:
                raise CrustError("Crustdata balance is empty.", "budget")
            try:
                msg = r.json().get("error", {}).get("message", "")
            except ValueError:
                msg = r.text[:200]
            raise CrustError(f"Crustdata rejected {path}: {msg[:200]}", "bad_request")
        raise last or CrustError("Crustdata failed.")

    # ---- typed helpers -------------------------------------------------
    def identify_company(self, name):
        r = self.call("/company/identify", {"names": [name]}, 0, "Find company")
        out = []
        for m in (r[0].get("matches") or []) if r else []:
            cd = m.get("company_data") or {}
            bi = cd.get("basic_info") or {}
            out.append({"id": cd.get("crustdata_company_id"), "name": bi.get("name"),
                        "domain": bi.get("primary_domain"), "size": bi.get("employee_count_range"),
                        "linkedin": bi.get("professional_network_url"), "founded": bi.get("year_founded"),
                        "description": (bi.get("description") or "")[:300],
                        "confidence": m.get("confidence_score")})
        return out

    PERSON_FIELDS = ["crustdata_person_id", "basic_profile.name", "basic_profile.headline",
                     "basic_profile.location", "social_handles.professional_network_identifier.profile_url",
                     "experience.employment_details.current", "experience.employment_details.past"]

    def search_people(self, conditions, label, limit=config.PEOPLE_PER_SEARCH):
        body = {"filters": {"op": "and", "conditions": conditions}, "fields": self.PERSON_FIELDS, "limit": limit}
        return self.call("/person/search", body, 0.1 * limit, label).get("profiles", [])

    def enrich_person(self, linkedin_url):
        r = self.call("/person/enrich", {"professional_network_profile_urls": [linkedin_url],
                                         "fields": ["basic_profile", "experience", "education", "skills",
                                                    "professional_network"]}, 1, "Read profile")
        m = (r[0].get("matches") or []) if r else []
        return m[0]["person_data"] if m else None

    def enrich_company(self, company_id):
        r = self.call("/company/enrich", {"crustdata_company_ids": [company_id],
                                          "fields": ["basic_info", "funding", "headcount", "hiring", "news",
                                                     "public_launches", "web_traffic", "revenue"]}, 2, "Read company")
        m = (r[0].get("matches") or []) if r else []
        return m[0]["company_data"] if m else None

    def search_jobs(self, company_id, words):
        body = {"filters": {"op": "and", "conditions": [
            {"field": "company.basic_info.crustdata_company_id", "type": "=", "value": company_id},
            {"op": "or", "conditions": [{"field": "job_details.title", "type": "(.)", "value": w} for w in words]}]},
            "fields": ["job_details.title", "job_details.url", "metadata.date_added", "location.raw",
                       "content.description"], "limit": config.JOBS_PER_SEARCH}
        return self.call("/job/search", body, 0.03 * config.JOBS_PER_SEARCH, "Open roles").get("job_listings", [])
