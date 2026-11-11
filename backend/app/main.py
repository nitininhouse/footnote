"""HTTP API + the built frontend. One process, one port."""
import asyncio
import json
import statistics
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, crust, pipeline, store
from .seller import SELLER

app = FastAPI(title="Hookline")
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class NewRun(BaseModel):
    name: str = ""
    company: str = ""
    title: str = ""
    linkedin: str = ""
    notes: str = ""
    mode: str = ""
    access_code: str = ""


class Answer(BaseModel):
    option: str
    value: str = ""


class Review(BaseModel):
    action: str            # approve | reject | save
    subject: str | None = None
    body: str | None = None
    reason: str = ""
    reviewer: str = ""


def public(run):
    """Strip internals before sending a run to the browser."""
    r = {k: v for k, v in run.items() if k not in ("calls_before", "credits_before", "company_candidates_raw")}
    if r.get("error"):
        r["error"] = {k: v for k, v in r["error"].items() if k != "trace"}
    return r


@app.get("/api/config")
def get_config():
    return {"default_mode": config.DEFAULT_MODE, "live_needs_code": bool(config.ACCESS_CODE),
            "live_available": bool(config.CRUSTDATA_KEY), "seller": SELLER["company"],
            "run_cap": config.RUN_CREDIT_CAP, "spent_today": round(crust.spent_today(), 2),
            "daily_cap": config.DAILY_CREDIT_CAP}


@app.post("/api/runs")
def new_run(body: NewRun):
    mode = body.mode or config.DEFAULT_MODE
    if mode not in ("live", "replay"):
        raise HTTPException(400, "mode must be live or replay")
    if mode == "live" and config.ACCESS_CODE and body.access_code.strip() != config.ACCESS_CODE:
        raise HTTPException(403, "Live mode needs the access code. Replay mode is open to everyone.")
    run = store.create({"name": body.name, "company": body.company, "title": body.title,
                        "linkedin": body.linkedin, "notes": body.notes}, mode)
    pipeline.start(run)
    return {"id": run["id"]}


@app.get("/api/runs")
def list_runs():
    rows = []
    for r in store.all_runs():
        dr = r.get("draft") or {}
        claims = dr.get("claims") or []
        hook = next((s for s in r.get("signals", []) if s["id"] == (r.get("hook") or {}).get("id")), None)
        dur = sum((s.get("ms") or 0) for s in r.get("stages", []))
        rows.append({"id": r["id"], "created": r["created"], "updated": r["updated"], "mode": r["mode"],
                     "status": r["status"], "name": (r.get("person") or {}).get("name") or r["input"].get("name"),
                     "title": (r.get("person") or {}).get("title") or r["input"].get("title"),
                     "company": (r.get("company") or {}).get("name") or r["input"].get("company"),
                     "hook": (hook or {}).get("label") or ((hook or {}).get("text") or "")[:80] or None,
                     "hook_kind": (hook or {}).get("event_type") or (hook or {}).get("kind"),
                     "claims_ok": sum(1 for c in claims if c.get("verdict") in ("supported", "cited")),
                     "claims": len(claims), "credits": r.get("credits", 0), "ms": dur,
                     "edge": sorted({c["kind"] for c in r.get("checks", []) if c["status"] != "pass"}),
                     "reviewer": (r.get("review") or {}).get("reviewer"),
                     "question": (r.get("question") or {}).get("kind")})
    return rows


@app.get("/api/stats")
def stats():
    runs = store.all_runs()
    done = [r for r in runs if r.get("draft")]
    reviewed = [r for r in runs if r["status"] in ("approved", "rejected")]
    durs = [sum((s.get("ms") or 0) for s in r["stages"]) for r in done]
    claims = [c for r in done for c in (r["draft"].get("claims") or [])]
    edited = [r for r in runs if r["status"] == "approved" and (r.get("review") or {}).get("edited")]
    return {"runs": len(runs),
            "awaiting": sum(1 for r in runs if r["status"] in ("ready", "ready_with_warnings", "needs_input")),
            "approved": sum(1 for r in runs if r["status"] == "approved"),
            "approval_rate": (sum(1 for r in reviewed if r["status"] == "approved") / len(reviewed)) if reviewed else None,
            "edit_rate": (len(edited) / max(1, sum(1 for r in runs if r["status"] == "approved"))) if reviewed else None,
            "median_ms": statistics.median(durs) if durs else None,
            "claim_pass": (sum(1 for c in claims if c.get("verdict") in ("supported", "cited")) / len(claims)) if claims else None,
            "credits": round(sum(r.get("credits", 0) for r in runs), 2)}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    r = store.get(run_id)
    if not r:
        raise HTTPException(404, "No such run")
    return public(r)


@app.get("/api/runs/{run_id}/stream")
async def stream(run_id: str, request: Request):
    """Server-sent events: the whole run document every time it changes."""
    async def gen():
        last = -1
        idle = 0
        while not await request.is_disconnected():
            r = store.get(run_id)
            if not r:
                yield "event: gone\ndata: {}\n\n"
                return
            if r.get("version") != last:
                last = r.get("version")
                idle = 0
                yield f"data: {json.dumps(public(r))}\n\n"
                if r["status"] not in ("running",):
                    return
            else:
                idle += 1
                if idle % 40 == 0:
                    yield ": keep-alive\n\n"
            await asyncio.sleep(0.25)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"cache-control": "no-cache", "x-accel-buffering": "no"})


@app.post("/api/runs/{run_id}/answer")
def answer(run_id: str, body: Answer):
    r = store.get(run_id)
    if not r:
        raise HTTPException(404, "No such run")
    if r["status"] != "needs_input":
        raise HTTPException(409, "This run is not waiting for an answer")
    try:
        pipeline.answer(r, body.option, body.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/runs/{run_id}/review")
def review(run_id: str, body: Review):
    r = store.get(run_id)
    if not r or not r.get("draft"):
        raise HTTPException(404, "No draft to review")
    dr = r["draft"]
    if body.subject is not None or body.body is not None:
        new_s = body.subject if body.subject is not None else dr["subject"]
        new_b = body.body if body.body is not None else dr["body"]
        if (new_s, new_b) != (dr.get("subject"), dr.get("body")):
            dr.setdefault("original", {"subject": dr["subject"], "body": dr["body"]})
            dr["subject"], dr["body"] = new_s, new_b
            dr["edited"] = True
            # claims whose sentence disappeared are no longer in the email
            for c in dr.get("claims", []):
                c["removed"] = c.get("text", "") not in new_b
            still_bad = [c for c in dr.get("claims", []) if c.get("verdict") == "unsupported" and not c.get("removed")]
            if not still_bad and not any(u in new_b for u in dr.get("unlisted", [])):
                dr.pop("approve_blocked", None)
    if body.action == "approve":
        if dr.get("approve_blocked"):
            raise HTTPException(409, dr["approve_blocked"])
        r["status"] = "approved"
        r["review"] = {"action": "approved", "at": store.now(), "reviewer": body.reviewer or "Rep",
                       "edited": bool(dr.get("edited"))}
    elif body.action == "reject":
        r["status"] = "rejected"
        r["review"] = {"action": "rejected", "at": store.now(), "reviewer": body.reviewer or "Rep",
                       "reason": body.reason}
    elif body.action != "save":
        raise HTTPException(400, "action must be approve, reject or save")
    store.save(r)
    return public(r)


@app.get("/api/health")
def health():
    return {"ok": True}


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
