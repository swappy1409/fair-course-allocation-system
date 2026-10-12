"""HTTP API and static frontend. Run: uvicorn fca.server:app (from the app/ directory)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, service
from .seed import hash_code

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
COOKIE = "fca_session"
SESSION_HOURS = 12
STUDENT_EVENTS = {"started", "courses_chosen", "pins_set", "ranking_saved", "error", "viewed_result"}

app = FastAPI(title="Preference-based course allocation (beta)", docs_url="/api/docs", openapi_url="/api/openapi.json")
db.init()


# ---- helpers ---------------------------------------------------------------------------------

def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def window_state(settings: dict, when: datetime | None = None) -> str:
    """'before', 'open' or 'closed'. An admin override wins over the dates."""
    if settings.get("window_override") in ("open", "closed"):
        return settings["window_override"]
    when = when or datetime.now(timezone.utc)
    if when < datetime.fromisoformat(settings["window_open"]):
        return "before"
    return "open" if when <= datetime.fromisoformat(settings["window_close"]) else "closed"


# ponytail: in-memory attempt counter, fine for one process; move to the database if this
# ever runs with more than one worker.
_attempts: dict[str, deque] = defaultdict(deque)
RATE_LIMIT, RATE_WINDOW_S = 8, 600


def rate_limit(request: Request, bucket: str) -> None:
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    q, t = _attempts[f"{bucket}:{ip}"], time.monotonic()
    while q and t - q[0] > RATE_WINDOW_S:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "Too many attempts. Wait ten minutes and try again.")
    q.append(t)


def start_session(con, response: Response, request: Request, student_id=None, is_admin=False) -> str:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    con.execute("DELETE FROM sessions WHERE expires < ?", (db.now(),))
    con.execute("INSERT INTO sessions(token_hash, student_id, is_admin, csrf, expires) VALUES(?,?,?,?,?)",
                (sha(token), student_id, int(is_admin), csrf, expires.isoformat(timespec="seconds")))
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True, samesite="strict",
                        secure=secure, path="/")
    return csrf


def session(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Please sign in.")
    with db.connect() as con:
        row = con.execute("SELECT * FROM sessions WHERE token_hash = ? AND expires > ?",
                          (sha(token), db.now())).fetchone()
    if not row:
        raise HTTPException(401, "Your session has ended. Please sign in again.")
    if request.method not in ("GET", "HEAD") and not hmac.compare_digest(
            request.headers.get("x-csrf-token", ""), row["csrf"]):
        raise HTTPException(403, "Security check failed. Reload the page and try again.")
    return row


def student_session(row=Depends(session)) -> dict:
    if not row["student_id"]:
        raise HTTPException(403, "Student sign-in required.")
    with db.connect() as con:
        s = con.execute("SELECT * FROM students WHERE id = ?", (row["student_id"],)).fetchone()
    if not s:
        raise HTTPException(401, "This tester no longer exists.")
    return {**dict(s), "required": json.loads(s["required"]), "backlog": json.loads(s["backlog"])}


def admin_session(row=Depends(session)):
    if not row["is_admin"]:
        raise HTTPException(403, "Admin sign-in required.")
    return row


@app.middleware("http")
async def guard(request: Request, call_next):
    # Every state-changing API call must carry a custom header. Browsers cannot add one to a
    # cross-site form post, so this blocks CSRF even on the two sign-in routes that have no
    # session yet; session routes additionally compare it with the per-session token.
    if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS") \
            and not request.headers.get("x-csrf-token"):
        return JSONResponse({"detail": "Missing security header."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ---- request bodies --------------------------------------------------------------------------

CODE = Field(pattern=r"^[A-Z]{3}\d{4}$")
PIN = Field(pattern=r"^[A-Z]{3}\d{4}:[A-Z]{2,3}:[A-Z0-9+]{1,40}$")


class LoginBody(BaseModel):
    code: str = Field(min_length=4, max_length=40)


class AdminLoginBody(BaseModel):
    secret: str = Field(min_length=1, max_length=200)


class ChoiceBody(BaseModel):
    electives: list[str] = Field(default_factory=list, max_length=20)
    pins: list[str] = Field(default_factory=list, max_length=30)
    ranking: list[str] = Field(default_factory=list, max_length=30)
    never: list[str] = Field(default_factory=list, max_length=30)

    def checked(self) -> "ChoiceBody":
        import re
        if any(not re.fullmatch(r"[A-Z]{3}\d{4}", e) for e in self.electives):
            raise HTTPException(422, "Unrecognised course code.")
        if any(not re.fullmatch(r"[A-Z]{3}\d{4}:[A-Z]{2,3}:[A-Z0-9+]{1,40}", p) for p in self.pins):
            raise HTTPException(422, "Unrecognised pin.")
        known = set(service.arch().by_id)
        if not set(self.ranking) <= known or not set(self.never) <= known:
            raise HTTPException(422, "Unrecognised timetable pattern.")
        return self


class EventBody(BaseModel):
    type: str = Field(max_length=40)
    detail: str = Field(default="", max_length=500)


class FeedbackBody(BaseModel):
    sus: list[int] = Field(min_length=10, max_length=10)
    ease: int = Field(ge=1, le=5)
    confused: str = Field(default="", max_length=2000)
    comments: str = Field(default="", max_length=4000)


# ---- sign in / out ---------------------------------------------------------------------------

@app.post("/api/login")
def login(body: LoginBody, request: Request, response: Response):
    rate_limit(request, "login")
    with db.connect() as con:
        s = con.execute("SELECT * FROM students WHERE code_hash = ?", (hash_code(body.code),)).fetchone()
        if not s:
            db.log_event(con, None, "error", {"where": "login", "reason": "invalid code"})
            con.commit()
            raise HTTPException(401, "That invite code is not recognised. Check it and try again.")
        if s["code_expires"] and s["code_expires"] < db.now():
            db.log_event(con, s["id"], "error", {"where": "login", "reason": "expired code"})
            con.commit()
            raise HTTPException(401, "That invite code has expired. Ask the organiser for a new one.")
        csrf = start_session(con, response, request, student_id=s["id"])
        db.log_event(con, s["id"], "signed_in")
    return {"csrf": csrf, "alias": s["alias"]}


@app.post("/api/admin/login")
def admin_login(body: AdminLoginBody, request: Request, response: Response):
    rate_limit(request, "admin")
    secret = os.environ.get("ADMIN_SECRET", "")
    if len(secret) < 12:
        raise HTTPException(503, "Admin access is disabled: set ADMIN_SECRET (12+ characters) in the environment.")
    if not hmac.compare_digest(body.secret.encode(), secret.encode()):
        raise HTTPException(401, "Wrong admin secret.")
    with db.connect() as con:
        csrf = start_session(con, response, request, is_admin=True)
    return {"csrf": csrf}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with db.connect() as con:
            con.execute("DELETE FROM sessions WHERE token_hash = ?", (sha(token),))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/session")
def whoami(row=Depends(session)):
    """Lets a reloaded page pick its session back up (the CSRF token lives only in memory)."""
    return {"csrf": row["csrf"], "admin": bool(row["is_admin"]), "student": bool(row["student_id"])}


# ---- student ---------------------------------------------------------------------------------

def course_view(code: str) -> dict:
    c = service.cat()
    x = c.courses[code]
    return {"code": code, "title": x.title, "credits": x.credits, "credits_source": x.credits_source,
            "basket": x.basket, "basket_source": x.basket_source,
            "components": [{"type": t, "slots": [o.slot for o in c.options(code, t)]} for t in x.types]}


def load_prefs(con, student_id: int) -> dict:
    p = con.execute("SELECT * FROM preferences WHERE student_id = ?", (student_id,)).fetchone()
    if not p:
        return {"electives": [], "pins": [], "ranking": [], "never": [], "submitted_at": None, "submit_count": 0}
    return {**{k: json.loads(p[k]) for k in ("electives", "pins", "ranking", "never")},
            "submitted_at": p["submitted_at"], "submit_count": p["submit_count"]}


@app.get("/api/me")
def me(student=Depends(student_session)):
    with db.connect() as con:
        settings = db.get_settings(con)
        prefs = load_prefs(con, student["id"])
        final = con.execute("SELECT id FROM runs WHERE kind = 'final' ORDER BY id DESC LIMIT 1").fetchone()
        fb = con.execute("SELECT 1 FROM feedback WHERE student_id = ?", (student["id"],)).fetchone()
    known = service.cat().courses
    return {
        "alias": student["alias"], "program": student["program"], "year": student["year"],
        "semester": student["semester"], "tier": student["tier"], "synthetic": bool(student["synthetic"]),
        "required": [course_view(c) for c in student["required"] if c in known],
        "backlog": [course_view(c) for c in student["backlog"] if c in known],
        "preferences": prefs,
        "window": {"state": window_state(settings), "open": settings["window_open"], "close": settings["window_close"]},
        "has_result": bool(final), "feedback_given": bool(fb),
        "credit_min": settings["credit_min"], "credit_max": settings["credit_max"],
        "capacity_source": settings["capacity_source"],
        "privacy_contact": settings["privacy_contact"],
        "archetypes": [{"id": a["id"], "label": a["label"], "description": a["description"]}
                       for a in service.arch().items],
        "allocation": {"seed": settings["allocation_seed"], "tiers": settings["tiers"]},
    }


@app.get("/api/courses")
def courses(student=Depends(student_session)):
    """Every course with a known credit value; the student's fixed courses are flagged."""
    fixed = set(student["required"]) | set(student["backlog"])
    return [{**course_view(code), "fixed": code in fixed}
            for code, c in sorted(service.cat().courses.items()) if c.credits is not None]


@app.post("/api/preview")
def preview(body: ChoiceBody, student=Depends(student_session)):
    body.checked()
    with db.connect() as con:
        settings = db.get_settings(con)
    out = service.preview(settings, student, body.electives, body.pins, body.ranking, body.never)
    if out["diagnosis"]:
        with db.connect() as con:
            db.log_event(con, student["id"], "diagnosis", {"conflicts": out["diagnosis"]["conflicts"],
                                                           "electives": body.electives, "pins": body.pins})
    return out


def save_prefs(con, student_id: int, body: ChoiceBody, submit: bool) -> None:
    vals = [json.dumps(v) for v in (sorted(set(body.electives)), sorted(set(body.pins)), body.ranking, body.never)]
    con.execute(
        "INSERT INTO preferences(student_id, electives, pins, ranking, never, updated_at) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(student_id) DO UPDATE SET electives=excluded.electives, pins=excluded.pins, "
        "ranking=excluded.ranking, never=excluded.never, updated_at=excluded.updated_at",
        (student_id, *vals, db.now()))
    if submit:
        con.execute("UPDATE preferences SET submitted_at = ?, submit_count = submit_count + 1 WHERE student_id = ?",
                    (db.now(), student_id))


def require_open(settings: dict) -> None:
    state = window_state(settings)
    if state == "before":
        raise HTTPException(409, "Registration has not opened yet.")
    if state == "closed":
        raise HTTPException(409, "The registration window has closed. Your last submitted choices stand.")


@app.put("/api/preferences")
def save_draft(body: ChoiceBody, student=Depends(student_session)):
    body.checked()
    with db.connect() as con:
        require_open(db.get_settings(con))
        save_prefs(con, student["id"], body, submit=False)
    return {"ok": True}


@app.post("/api/submit")
def submit(body: ChoiceBody, student=Depends(student_session)):
    """Submitting again simply replaces the earlier submission (allowed until the window closes)."""
    body.checked()
    with db.connect() as con:
        settings = db.get_settings(con)
        require_open(settings)
    body.electives = service.clean_electives(student, body.electives)
    out = service.preview(settings, student, body.electives, body.pins, body.ranking, body.never)
    if out["count"] == 0:
        raise HTTPException(409, "These choices have no possible timetable, so they cannot be submitted. "
                            + " ".join(out["diagnosis"]["conflicts"][:1]))
    if set(body.never) >= {a["id"] for a in out["archetypes"]}:
        raise HTTPException(409, "You marked every available pattern as 'never'. Allow at least one.")
    with db.connect() as con:
        save_prefs(con, student["id"], body, submit=True)
        n = con.execute("SELECT submit_count FROM preferences WHERE student_id = ?", (student["id"],)).fetchone()[0]
        db.log_event(con, student["id"], "submitted", {"submission": n, "credits": out["credits"],
                                                        "combinations": out["count"]})
    return {"ok": True, "submission": n}


@app.post("/api/event")
def event(body: EventBody, student=Depends(student_session)):
    if body.type not in STUDENT_EVENTS:
        raise HTTPException(422, "Unknown event.")
    with db.connect() as con:
        db.log_event(con, student["id"], body.type, {"detail": body.detail} if body.detail else None)
    return {"ok": True}


@app.post("/api/feedback")
def feedback(body: FeedbackBody, student=Depends(student_session)):
    if any(not 1 <= v <= 5 for v in body.sus):
        raise HTTPException(422, "Each answer must be between 1 and 5.")
    with db.connect() as con:
        con.execute("INSERT INTO feedback(student_id, ts, sus, ease, confused, comments) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(student_id) DO UPDATE SET ts=excluded.ts, sus=excluded.sus, ease=excluded.ease, "
                    "confused=excluded.confused, comments=excluded.comments",
                    (student["id"], db.now(), json.dumps(body.sus), body.ease, body.confused, body.comments))
        db.log_event(con, student["id"], "feedback_given")
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True}


# ---- static frontend (single-page app) ---------------------------------------------------------

def mount_frontend() -> None:
    if not WEB_DIST.exists():
        return
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        file = (WEB_DIST / path).resolve()
        if path and file.is_file() and WEB_DIST.resolve() in file.parents:
            return FileResponse(file)
        return FileResponse(WEB_DIST / "index.html", headers={"Cache-Control": "no-cache"})


from . import admin  # noqa: E402,F401  (registers the admin, result and add/drop routes on `app`)

mount_frontend()
