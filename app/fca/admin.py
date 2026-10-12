"""Admin area, allocation runs, results, add/drop, exports, backups. Imported by server.py."""
from __future__ import annotations

import csv
import io
import json
import shutil
import sqlite3
import statistics
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from . import db, seed as seeding, service
from .allocation import (METHOD, Allocator, miss_history, run_allocation, seats_for, simulate)
from .server import (ChoiceBody, admin_session, app, load_prefs, student_session, window_state)

SETTING_RULES = {
    "credit_min": int, "credit_max": int, "seats_per_section": int, "beta_seats_per_section": int,
    "use_beta_seats": bool, "tiers": list, "window_open": str, "window_close": str, "window_override": str,
    "allocation_seed": str, "earlier_miss_weight": (int, float), "add_drop_changes_per_student": int,
    "privacy_contact": str, "invite_code_valid_days": int, "survey_baseline_minutes": (int, float),
}


# ---- shared helpers ----------------------------------------------------------------------------

def latest_final(con):
    return con.execute("SELECT * FROM runs WHERE kind = 'final' ORDER BY id DESC LIMIT 1").fetchone()


def capacity_now(con, settings) -> dict[str, int]:
    overrides = {r["offering_id"]: r["seats"] for r in con.execute("SELECT * FROM capacity")}
    return seats_for(service.cat(), settings, overrides)


def free_seats(con, settings, run_id: int, exclude_student: int | None = None) -> dict[str, int]:
    free = capacity_now(con, settings)
    for r in con.execute("SELECT student_id, combo FROM allocations WHERE run_id = ?", (run_id,)):
        if r["student_id"] != exclude_student:
            for oid in json.loads(r["combo"]):
                if oid in free:
                    free[oid] -= 1
    return free


def submitted_students(con) -> list[dict]:
    rows = con.execute("SELECT s.*, p.electives, p.pins, p.ranking, p.never FROM students s "
                       "JOIN preferences p ON p.student_id = s.id WHERE p.submitted_at IS NOT NULL").fetchall()
    return [{"id": r["id"], "alias": r["alias"], "tier": r["tier"],
             **{k: json.loads(r[k]) for k in ("required", "backlog", "electives", "pins", "ranking", "never")}}
            for r in rows]


def history_before(con, round_no: int) -> dict:
    rounds = []
    for r in range(1, round_no):
        run = con.execute("SELECT id FROM runs WHERE kind='final' AND round=? ORDER BY id DESC LIMIT 1", (r,)).fetchone()
        if run:
            rounds.append([{"alias": a["alias"], "choice_rank": a["choice_rank"]} for a in con.execute(
                "SELECT s.alias, a.choice_rank FROM allocations a JOIN students s ON s.id = a.student_id "
                "WHERE a.run_id = ?", (run["id"],))])
    return miss_history(rounds)


def csv_response(name: str, header: list[str], rows) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for row in rows:
        # A leading quote stops spreadsheet programs treating tester-typed text as a formula.
        w.writerow([("'" + v) if isinstance(v, str) and v[:1] in "=+-@" else v for v in row])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


def sus_score(answers: list[int]) -> float:
    """Standard System Usability Scale score, 0-100."""
    return sum((a - 1) if i % 2 == 0 else (5 - a) for i, a in enumerate(answers)) * 2.5


def timings(con) -> list[dict]:
    """Minutes from a tester's first step to their first submission."""
    out = []
    for s in con.execute("SELECT id, alias FROM students ORDER BY alias"):
        ev = con.execute("SELECT ts, type FROM events WHERE student_id = ? ORDER BY id", (s["id"],)).fetchall()
        start = next((e["ts"] for e in ev if e["type"] in ("started", "signed_in")), None)
        done = next((e["ts"] for e in ev if e["type"] == "submitted"), None)
        minutes = None
        if start and done:
            minutes = round((datetime.fromisoformat(done) - datetime.fromisoformat(start)).total_seconds() / 60, 2)
        out.append({"alias": s["alias"], "started": start, "submitted": done, "minutes": minutes,
                    "steps": [e["type"] for e in ev if e["type"] in
                              ("started", "courses_chosen", "pins_set", "ranking_saved", "submitted")],
                    "errors": sum(1 for e in ev if e["type"] == "error")})
    return out


# ---- overview and settings ---------------------------------------------------------------------

@app.get("/api/admin/overview")
def overview(_=Depends(admin_session)):
    with db.connect() as con:
        settings = db.get_settings(con)
        t = timings(con)
        done = [x["minutes"] for x in t if x["minutes"] is not None]
        fb = [json.loads(r["sus"]) for r in con.execute("SELECT sus FROM feedback")]
        runs = [{"id": r["id"], "kind": r["kind"], "round": r["round"], "seed": r["seed"], "created": r["created"]}
                for r in con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 10")]
        counts = {
            "testers": con.execute("SELECT COUNT(*) FROM students").fetchone()[0],
            "submitted": con.execute("SELECT COUNT(*) FROM preferences WHERE submitted_at IS NOT NULL").fetchone()[0],
            "feedback": len(fb),
        }
    return {
        "settings": settings, "window_state": window_state(settings), "counts": counts, "runs": runs,
        "timing": {"completed": len(done), "median_minutes": round(statistics.median(done), 2) if done else None,
                   "mean_minutes": round(statistics.mean(done), 2) if done else None,
                   "baseline_minutes": settings["survey_baseline_minutes"]},
        "sus_mean": round(statistics.mean(sus_score(a) for a in fb), 1) if fb else None,
        "catalogue_report": service.cat().report, "method": METHOD,
        "archetypes": service.arch().items,
    }


@app.put("/api/admin/settings")
def update_settings(body: dict, _=Depends(admin_session)):
    for k, v in body.items():
        if k not in SETTING_RULES or not isinstance(v, SETTING_RULES[k]) or isinstance(v, bool) != (SETTING_RULES[k] is bool):
            raise HTTPException(422, f"Setting '{k}' is unknown or has the wrong type.")
    with db.connect() as con:
        new = {**db.get_settings(con), **body}
        if not 0 <= new["credit_min"] <= new["credit_max"]:
            raise HTTPException(422, "Credit minimum must not exceed the maximum.")
        if min(new["seats_per_section"], new["beta_seats_per_section"]) < 0:
            raise HTTPException(422, "Seats cannot be negative.")
        tiers = new["tiers"]
        if not tiers or len(set(tiers)) != len(tiers) or any(not isinstance(t, str) or not t.strip() for t in tiers):
            raise HTTPException(422, "Tiers must be a non-empty list of distinct names.")
        if new["window_override"] not in ("", "open", "closed"):
            raise HTTPException(422, "Window override must be empty, 'open' or 'closed'.")
        try:
            if datetime.fromisoformat(new["window_open"]).tzinfo is None or \
                    datetime.fromisoformat(new["window_close"]).tzinfo is None:
                raise ValueError
        except ValueError:
            raise HTTPException(422, "Window dates must be ISO date-times with a time zone, "
                                     "for example 2026-10-19T09:00:00+05:30.")
        stray = con.execute(f"SELECT COUNT(*) FROM students WHERE tier NOT IN ({','.join('?' * len(tiers))})",
                            tiers).fetchone()[0]
        if stray:
            raise HTTPException(409, f"{stray} tester(s) are in a tier you are removing. Move them first.")
        db.set_settings(con, body)
        return {"settings": db.get_settings(con), "window_state": window_state(new)}


# ---- testers and invite codes ------------------------------------------------------------------

class TesterCsv(BaseModel):
    csv: str = Field(max_length=200_000)


class TierBody(BaseModel):
    tier: str = Field(max_length=80)


@app.get("/api/admin/testers")
def testers(_=Depends(admin_session)):
    with db.connect() as con:
        rows = con.execute(
            "SELECT s.*, p.submitted_at, p.submit_count FROM students s LEFT JOIN preferences p "
            "ON p.student_id = s.id ORDER BY s.alias").fetchall()
    return [{"id": r["id"], "alias": r["alias"], "program": r["program"], "year": r["year"],
             "semester": r["semester"], "tier": r["tier"], "required": json.loads(r["required"]),
             "backlog": json.loads(r["backlog"]), "synthetic": bool(r["synthetic"]),
             "code_expires": r["code_expires"], "submitted_at": r["submitted_at"],
             "submit_count": r["submit_count"] or 0} for r in rows]


@app.post("/api/admin/testers/import")
def testers_import(body: TesterCsv, _=Depends(admin_session)):
    with db.connect() as con:
        report = seeding.import_testers(con, body.csv, service.cat().courses)
    return report          # invite codes appear here once; only hashes are stored


@app.post("/api/admin/testers/{student_id}/code")
def new_invite_code(student_id: int, _=Depends(admin_session)):
    code = seeding.new_code()
    with db.connect() as con:
        settings = db.get_settings(con)
        from datetime import timedelta
        expires = (datetime.now(timezone.utc) + timedelta(days=settings["invite_code_valid_days"])).isoformat(timespec="seconds")
        n = con.execute("UPDATE students SET code_hash = ?, code_expires = ? WHERE id = ?",
                        (seeding.hash_code(code), expires, student_id)).rowcount
        con.execute("DELETE FROM sessions WHERE student_id = ?", (student_id,))
    if not n:
        raise HTTPException(404, "No such tester.")
    return {"code": code, "expires": expires}


@app.put("/api/admin/testers/{student_id}/tier")
def set_tier(student_id: int, body: TierBody, _=Depends(admin_session)):
    with db.connect() as con:
        if body.tier not in db.get_settings(con)["tiers"]:
            raise HTTPException(422, "That tier does not exist.")
        con.execute("UPDATE students SET tier = ? WHERE id = ?", (body.tier, student_id))
    return {"ok": True}


@app.delete("/api/admin/testers/{student_id}")
def delete_tester(student_id: int, _=Depends(admin_session)):
    with db.connect() as con:
        for t in ("preferences", "feedback", "sessions", "allocations", "add_drop", "events"):
            con.execute(f"DELETE FROM {t} WHERE student_id = ?", (student_id,))
        con.execute("DELETE FROM students WHERE id = ?", (student_id,))
    return {"ok": True}


# ---- data import with parse report ---------------------------------------------------------------

def pending_path() -> Path:
    return db.data_dir() / "catalogue.pending.json"


@app.post("/api/admin/import")
async def import_pdfs(timetable: UploadFile = File(...), courses: UploadFile = File(...), _=Depends(admin_session)):
    """Parse the two Annexure PDFs and return the parse report. Nothing changes until confirmed."""
    from .importer import build_catalogue
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for name, up in (("a1.pdf", timetable), ("a2.pdf", courses)):
            data = await up.read()
            if len(data) > 20_000_000 or not data.startswith(b"%PDF"):
                raise HTTPException(422, "Both files must be PDFs under 20 MB.")
            (Path(tmp) / name).write_bytes(data)
            paths.append(Path(tmp) / name)
        try:
            catalogue = build_catalogue(*paths)
        except Exception as e:      # a PDF with an unexpected layout: report it, change nothing
            raise HTTPException(422, f"Could not read these PDFs as Annexure I and II: {type(e).__name__}: {e}")
    pending_path().write_text(json.dumps(catalogue), encoding="utf-8")
    return {"report": catalogue["report"], "pending": True}


@app.post("/api/admin/import/confirm")
def import_confirm(_=Depends(admin_session)):
    if not pending_path().exists():
        raise HTTPException(409, "Upload the two PDFs first.")
    shutil.move(pending_path(), db.data_dir() / "catalogue.json")
    service.reload()
    return {"ok": True, "report": service.cat().report}


# ---- capacity --------------------------------------------------------------------------------------

class CapacityBody(BaseModel):
    offering_id: str = Field(max_length=80)
    seats: int | None = Field(default=None, ge=0, le=100_000)


@app.get("/api/admin/capacity")
def capacity(course: str = "", _=Depends(admin_session)):
    c = service.cat()
    with db.connect() as con:
        settings = db.get_settings(con)
        overrides = {r["offering_id"]: r["seats"] for r in con.execute("SELECT * FROM capacity")}
        seats = seats_for(c, settings, overrides)
        final = latest_final(con)
        free = free_seats(con, settings, final["id"]) if final else seats
    course = course.strip().upper()
    rows = [o for o in c.offerings.values() if (o.course == course if course else o.id in overrides)]
    return {"source": settings["capacity_source"], "per_section":
            settings["beta_seats_per_section"] if settings["use_beta_seats"] else settings["seats_per_section"],
            "offerings": [{"id": o.id, "course": o.course, "type": o.type, "slot": o.slot, "sections": o.sections,
                           "seats": seats[o.id], "taken": seats[o.id] - free[o.id],
                           "overridden": o.id in overrides} for o in sorted(rows, key=lambda o: o.id)]}


@app.put("/api/admin/capacity")
def set_capacity(body: CapacityBody, _=Depends(admin_session)):
    if body.offering_id not in service.cat().offerings:
        raise HTTPException(404, "No such course-slot.")
    with db.connect() as con:
        if body.seats is None:
            con.execute("DELETE FROM capacity WHERE offering_id = ?", (body.offering_id,))
        else:
            con.execute("INSERT INTO capacity(offering_id, seats) VALUES(?, ?) ON CONFLICT(offering_id) "
                        "DO UPDATE SET seats = excluded.seats", (body.offering_id, body.seats))
    return {"ok": True}


# ---- allocation runs -------------------------------------------------------------------------------

class AllocateBody(BaseModel):
    kind: str = Field(pattern="^(dry|final)$")
    round: int = Field(default=1, ge=1, le=20)


class SimulateBody(BaseModel):
    students: int = Field(default=200, ge=10, le=600)
    seats_per_section: int = Field(default=3, ge=1, le=200)
    rounds: int = Field(default=2, ge=1, le=4)


@app.post("/api/admin/allocate")
def allocate(body: AllocateBody, _=Depends(admin_session)):
    with db.connect() as con:
        settings = db.get_settings(con)
        if body.kind == "final" and window_state(settings) == "open":
            raise HTTPException(409, "Close the registration window before a final run. A dry run works any time.")
        students = submitted_students(con)
        capacity = capacity_now(con, settings)
        history = history_before(con, body.round)
    result = run_allocation(service.cat(), service.arch(), settings, students, capacity, body.round, history)
    result["report"]["kind"] = body.kind
    result["report"]["not_submitted"] = None
    with db.connect() as con:
        result["report"]["not_submitted"] = con.execute(
            "SELECT COUNT(*) FROM students s LEFT JOIN preferences p ON p.student_id = s.id "
            "WHERE p.submitted_at IS NULL").fetchone()[0]
        run_id = None
        if body.kind == "final":
            ids = {s["alias"]: s["id"] for s in students}
            run_id = con.execute("INSERT INTO runs(kind, round, seed, created, report) VALUES(?,?,?,?,?)",
                                 ("final", body.round, settings["allocation_seed"], db.now(),
                                  json.dumps(result["report"]))).lastrowid
            con.executemany(
                "INSERT INTO allocations(run_id, student_id, status, combo, archetype, choice_rank, position, "
                "explanation) VALUES(?,?,?,?,?,?,?,?)",
                [(run_id, ids[a["alias"]], a["status"], json.dumps(a["combo"]), a["archetype"], a["choice_rank"],
                  a["position"], a["explanation"]) for a in result["assignments"]])
    return {"run_id": run_id, "saved": body.kind == "final", **result}


@app.get("/api/admin/runs/{run_id}")
def run_detail(run_id: int, _=Depends(admin_session)):
    with db.connect() as con:
        run = con.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "No such run.")
        rows = con.execute("SELECT a.*, s.alias, s.tier FROM allocations a JOIN students s ON s.id = a.student_id "
                           "WHERE run_id = ? ORDER BY position", (run_id,)).fetchall()
    return {"run_id": run_id, "saved": True, "report": json.loads(run["report"]),
            "assignments": [{"alias": r["alias"], "tier": r["tier"], "position": r["position"],
                             "status": r["status"], "combo": json.loads(r["combo"]), "archetype": r["archetype"],
                             "choice_rank": r["choice_rank"], "explanation": r["explanation"]} for r in rows]}


@app.post("/api/admin/simulate")
def run_simulation(body: SimulateBody, _=Depends(admin_session)):
    with db.connect() as con:
        settings = db.get_settings(con)
    return simulate(service.cat(), service.arch(), settings, seeding.read_curriculum(), body.students,
                    body.seats_per_section, body.rounds)


# ---- logs and exports -------------------------------------------------------------------------------

@app.get("/api/admin/diagnostics")
def diagnostics_log(_=Depends(admin_session)):
    with db.connect() as con:
        rows = con.execute("SELECT e.ts, e.type, e.detail, s.alias FROM events e LEFT JOIN students s "
                           "ON s.id = e.student_id WHERE e.type IN ('diagnosis', 'error') "
                           "ORDER BY e.id DESC LIMIT 200").fetchall()
    return [{"ts": r["ts"], "type": r["type"], "alias": r["alias"],
             "detail": json.loads(r["detail"]) if r["detail"] else None} for r in rows]


@app.get("/api/admin/timing")
def timing(_=Depends(admin_session)):
    with db.connect() as con:
        return timings(con)


@app.get("/api/admin/export/{name}")
def export(name: str, _=Depends(admin_session)):
    c = service.cat()
    with db.connect() as con:
        if name == "results.csv":
            run = latest_final(con)
            rows = con.execute("SELECT a.*, s.alias, s.tier FROM allocations a JOIN students s ON s.id = "
                               "a.student_id WHERE run_id = ? ORDER BY position", (run["id"] if run else -1,))
            return csv_response(name, ["alias", "tier", "position", "status", "choice_rank", "archetype",
                                       "course_slots", "explanation"],
                                [[r["alias"], r["tier"], r["position"], r["status"], r["choice_rank"], r["archetype"],
                                  "; ".join(f"{c.offerings[o].course} {c.offerings[o].type} {c.offerings[o].slot}"
                                            for o in json.loads(r["combo"]) if o in c.offerings),
                                  r["explanation"]] for r in rows])
        if name == "feedback.csv":
            rows = con.execute("SELECT f.*, s.alias FROM feedback f JOIN students s ON s.id = f.student_id ORDER BY s.alias")
            out = []
            for r in rows:
                sus = json.loads(r["sus"])
                out.append([r["alias"], r["ts"], *sus, sus_score(sus), r["ease"], r["confused"], r["comments"]])
            return csv_response(name, ["alias", "ts", *[f"sus_{i}" for i in range(1, 11)], "sus_score", "ease_1_to_5",
                                       "what_confused_you", "comments"], out)
        if name == "events.csv":
            rows = con.execute("SELECT e.*, s.alias FROM events e LEFT JOIN students s ON s.id = e.student_id ORDER BY e.id")
            return csv_response(name, ["ts", "alias", "type", "detail"],
                                [[r["ts"], r["alias"], r["type"], r["detail"]] for r in rows])
        if name == "timing.csv":
            base = db.get_settings(con)["survey_baseline_minutes"]
            return csv_response(name, ["alias", "started", "submitted", "minutes", "survey_baseline_minutes",
                                       "steps", "errors"],
                                [[t["alias"], t["started"], t["submitted"], t["minutes"], base, " > ".join(t["steps"]),
                                  t["errors"]] for t in timings(con)])
    raise HTTPException(404, "Unknown export. Use results.csv, feedback.csv, events.csv or timing.csv.")


# ---- reset and backup --------------------------------------------------------------------------------

class ResetBody(BaseModel):
    confirm: str


def backup_now() -> Path:
    folder = db.data_dir() / "backups"
    folder.mkdir(exist_ok=True)
    target = folder / f"fca-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.db"
    src, dst = sqlite3.connect(db.db_path()), sqlite3.connect(target)
    try:
        src.backup(dst)        # consistent copy even while the app is writing
    finally:
        src.close()
        dst.close()
    for old in sorted(folder.glob("fca-*.db"))[:-14]:   # keep two weeks
        old.unlink()
    return target


@app.post("/api/admin/backup")
def backup(_=Depends(admin_session)):
    return {"file": backup_now().name}


@app.post("/api/admin/reset")
def reset(body: ResetBody, _=Depends(admin_session)):
    if body.confirm != "RESET":
        raise HTTPException(422, "Type RESET to confirm.")
    saved = backup_now().name
    with db.connect() as con:
        seeding.reset_beta(con)
    return {"ok": True, "backup": saved}


def _daily_backup() -> None:
    while True:
        folder = db.data_dir() / "backups"
        today = f"fca-{datetime.now(timezone.utc):%Y%m%d}"
        try:
            if not any(folder.glob(today + "-*.db")):
                backup_now()
        except Exception as e:           # never let the backup thread take the app down
            print("backup failed:", e)
        time.sleep(3600)


threading.Thread(target=_daily_backup, daemon=True, name="daily-backup").start()


# ---- student: result and add/drop ----------------------------------------------------------------------

def changes_used(con, student_id: int, run_created: str) -> int:
    return con.execute("SELECT COUNT(*) FROM add_drop WHERE student_id = ? AND ts >= ?",
                       (student_id, run_created)).fetchone()[0]


@app.get("/api/result")
def result(student=Depends(student_session)):
    with db.connect() as con:
        settings = db.get_settings(con)
        run = latest_final(con)
        if not run:
            return {"ready": False}
        a = con.execute("SELECT * FROM allocations WHERE run_id = ? AND student_id = ?",
                        (run["id"], student["id"])).fetchone()
        used = changes_used(con, student["id"], run["created"])
        total = con.execute("SELECT COUNT(*) FROM allocations WHERE run_id = ?", (run["id"],)).fetchone()[0]
        db.log_event(con, student["id"], "viewed_result")
    out = {"ready": True, "round": run["round"], "seed": run["seed"], "method": METHOD, "students": total,
           "add_drop": {"allowed": settings["add_drop_changes_per_student"], "used": used},
           "capacity_source": settings["capacity_source"]}
    if not a:
        return {**out, "status": "not_included", "explanation":
                "You had not submitted when the allocation ran. You can still use the add/drop step.", "timetable": None}
    combo = [o for o in json.loads(a["combo"]) if o in service.cat().offerings]
    return {**out, "status": a["status"], "explanation": a["explanation"], "position": a["position"],
            "choice_rank": a["choice_rank"], "timetable": service.combo_view(combo) if combo else None}


@app.post("/api/adddrop")
def add_drop(body: ChoiceBody, student=Depends(student_session)):
    """One capped change after allocation: new choices are seated straight away from the seats left."""
    body.checked()
    body.electives = service.clean_electives(student, body.electives)
    con = sqlite3.connect(db.db_path(), timeout=15, isolation_level=None)
    con.row_factory = sqlite3.Row
    try:
        con.execute("BEGIN IMMEDIATE")        # one add/drop at a time, so seats cannot be double-booked
        settings = db.get_settings(con)
        run = latest_final(con)
        if not run:
            raise HTTPException(409, "Add/drop opens after the allocation has run.")
        if changes_used(con, student["id"], run["created"]) >= settings["add_drop_changes_per_student"]:
            raise HTTPException(409, "You have used your add/drop change for this round.")
        free = free_seats(con, settings, run["id"], exclude_student=student["id"])
        s = {"alias": student["alias"], "tier": student["tier"], "required": student["required"],
             "backlog": student["backlog"], "electives": body.electives, "pins": body.pins,
             "ranking": body.ranking, "never": body.never}
        placed = Allocator(service.cat(), service.arch(), settings).place(s, free)
        if placed["status"] != "placed":
            raise HTTPException(409, "No change made. " + placed["explanation"])
        old = con.execute("SELECT combo FROM allocations WHERE run_id = ? AND student_id = ?",
                          (run["id"], student["id"])).fetchone()
        text = "After your add/drop change: " + placed["explanation"]
        con.execute("INSERT INTO allocations(run_id, student_id, status, combo, archetype, choice_rank, position, "
                    "explanation) VALUES(?,?,?,?,?,?,NULL,?) ON CONFLICT(run_id, student_id) DO UPDATE SET "
                    "status=excluded.status, combo=excluded.combo, archetype=excluded.archetype, "
                    "choice_rank=excluded.choice_rank, explanation=excluded.explanation",
                    (run["id"], student["id"], "placed", json.dumps(placed["combo"]), placed["archetype"],
                     placed["choice_rank"], text))
        con.execute("INSERT INTO add_drop(student_id, ts, before, after) VALUES(?,?,?,?)",
                    (student["id"], db.now(), old["combo"] if old else "[]", json.dumps(placed["combo"])))
        vals = [json.dumps(v) for v in (body.electives, sorted(set(body.pins)), body.ranking, body.never)]
        con.execute("INSERT INTO preferences(student_id, electives, pins, ranking, never, updated_at) "
                    "VALUES(?,?,?,?,?,?) ON CONFLICT(student_id) DO UPDATE SET electives=excluded.electives, "
                    "pins=excluded.pins, ranking=excluded.ranking, never=excluded.never, "
                    "updated_at=excluded.updated_at", (student["id"], *vals, db.now()))
        db.log_event(con, student["id"], "add_drop", {"combo": placed["combo"]})
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK") if con.in_transaction else None
        raise
    finally:
        con.close()
    return {"ok": True, "explanation": text}
