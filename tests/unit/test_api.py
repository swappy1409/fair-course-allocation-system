"""HTTP API: sign-in, window, submission, allocation, result, add/drop, admin, exports."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from fca import db, seed, server

TESTERS = """alias,program,year,semester,tier,required_courses,backlog_courses
ann,B.Tech CSE,4,7,All students,CSE1013 LAW2104 MAT1003,
bob,B.Tech CSE,4,7,All students,CSE1013 LAW2104 MAT1003,
cy,B.Tech CSE,4,7,All students,CSE1013 LAW2104 MAT1003,
"""
CHOICE = {"electives": ["FRL1001", "HUM3109", "MGT1040"], "pins": [], "ranking": ["morning_heavy", "mixed"], "never": []}
ADMIN = "test-admin-secret-123"


@pytest.fixture()
def codes():
    """Fresh database with three testers and the window forced open. Returns alias -> invite code."""
    server._attempts.clear()
    with db.connect() as con:
        seed.reset_beta(con)
        con.execute("DELETE FROM settings")
    db.init()
    with db.connect() as con:
        db.set_settings(con, {"window_override": "open", "use_beta_seats": False})
        return dict(seed.import_testers(con, TESTERS)["codes"])


def sign_in(code) -> TestClient:
    c = TestClient(server.app)
    r = c.post("/api/login", json={"code": code}, headers={"x-csrf-token": "login"})
    assert r.status_code == 200, r.text
    c.headers["x-csrf-token"] = r.json()["csrf"]
    return c


def admin() -> TestClient:
    c = TestClient(server.app)
    r = c.post("/api/admin/login", json={"secret": ADMIN}, headers={"x-csrf-token": "login"})
    assert r.status_code == 200, r.text
    c.headers["x-csrf-token"] = r.json()["csrf"]
    return c


# ---- sign-in -----------------------------------------------------------------------------------

def test_invite_code_is_stored_hashed_and_signs_in(codes):
    with db.connect() as con:
        stored = [r[0] for r in con.execute("SELECT code_hash FROM students")]
    assert all(len(h) == 64 and h not in codes.values() for h in stored)
    c = sign_in(codes["ann"].lower())                       # case-insensitive
    me = c.get("/api/me").json()
    assert me["alias"] == "ann" and [x["code"] for x in me["required"]] == ["CSE1013", "LAW2104", "MAT1003"]
    assert me["window"]["state"] == "open" and me["privacy_contact"]


def test_invalid_and_expired_invite_codes_are_refused(codes):
    c = TestClient(server.app)
    r = c.post("/api/login", json={"code": "ZZZZ-ZZZZ"}, headers={"x-csrf-token": "login"})
    assert r.status_code == 401 and "not recognised" in r.json()["detail"]
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    with db.connect() as con:
        con.execute("UPDATE students SET code_expires = ? WHERE alias = 'ann'", (past,))
    r = c.post("/api/login", json={"code": codes["ann"]}, headers={"x-csrf-token": "login"})
    assert r.status_code == 401 and "expired" in r.json()["detail"]
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM events WHERE type = 'error'").fetchone()[0] == 2


def test_sign_in_attempts_are_rate_limited(codes):
    c = TestClient(server.app)
    statuses = [c.post("/api/login", json={"code": "NOPE-NOPE"}, headers={"x-csrf-token": "x"}).status_code
                for _ in range(server.RATE_LIMIT + 1)]
    assert statuses[:-1] == [401] * server.RATE_LIMIT and statuses[-1] == 429


def test_csrf_header_is_required_and_must_match_the_session(codes):
    c = sign_in(codes["ann"])
    assert TestClient(server.app).post("/api/login", json={"code": codes["ann"]}).status_code == 403
    assert c.post("/api/submit", json=CHOICE, headers={"x-csrf-token": "wrong"}).status_code == 403
    assert c.post("/api/submit", json=CHOICE).status_code == 200


def test_no_session_no_data_and_student_cannot_reach_admin(codes):
    assert TestClient(server.app).get("/api/me").status_code == 401
    assert sign_in(codes["ann"]).get("/api/admin/overview").status_code == 403
    bad = TestClient(server.app).post("/api/admin/login", json={"secret": "guess"}, headers={"x-csrf-token": "x"})
    assert bad.status_code == 401


def test_input_validation(codes):
    c = sign_in(codes["ann"])
    assert c.post("/api/preview", json={**CHOICE, "electives": ["'; DROP TABLE students;--"]}).status_code == 422
    assert c.post("/api/preview", json={**CHOICE, "pins": ["nonsense"]}).status_code == 422
    assert c.post("/api/preview", json={**CHOICE, "ranking": ["not_a_pattern"]}).status_code == 422
    assert c.post("/api/event", json={"type": "made_up"}).status_code == 422
    assert c.post("/api/feedback", json={"sus": [9] * 10, "ease": 3}).status_code == 422


# ---- preview, diagnostics, submit --------------------------------------------------------------------

def test_preview_counts_archetypes_and_top_three(codes):
    out = sign_in(codes["ann"]).post("/api/preview", json=CHOICE).json()
    assert out["count"] == 36 and out["exact"] and out["credits"] == 18
    assert {a["id"]: a["count"] for a in out["archetypes"]} == {"morning_heavy": 12, "mixed": 24}
    assert [t["archetype"] for t in out["top"]] == ["morning_heavy", "mixed"]
    assert out["top"][0]["choice"] == 1 and out["top"][0]["classes"][0]["cells"]


def test_impossible_pin_returns_diagnosis_with_one_click_fix_and_is_logged(codes):
    c = sign_in(codes["ann"])
    out = c.post("/api/preview", json={**CHOICE, "pins": ["FRL1001:TH:G1"]}).json()
    assert out["count"] == 0 and "FRL1001 pinned to G1 clashes with LAW2104" in out["diagnosis"]["conflicts"][0]
    fix = out["diagnosis"]["relaxations"][0]
    assert fix["kind"] == "drop_pin" and fix["pins"] == [] and fix["unlocks"] == 36
    again = c.post("/api/preview", json={**CHOICE, "electives": fix["electives"], "pins": fix["pins"]}).json()
    assert again["count"] == 36
    assert c.post("/api/submit", json={**CHOICE, "pins": ["FRL1001:TH:G1"]}).status_code == 409
    log = admin().get("/api/admin/diagnostics").json()
    assert log[0]["type"] == "diagnosis" and log[0]["alias"] == "ann"


def test_duplicate_submission_and_change_after_submitting(codes):
    c = sign_in(codes["ann"])
    assert c.post("/api/submit", json=CHOICE).json()["submission"] == 1
    assert c.post("/api/submit", json=CHOICE).json()["submission"] == 2          # same again: no error, one row
    changed = {**CHOICE, "electives": ["FRL1004", "HUM3109", "MGT1040"], "ranking": ["mixed"]}
    assert c.post("/api/submit", json=changed).json()["submission"] == 3
    prefs = c.get("/api/me").json()["preferences"]
    assert prefs["electives"] == ["FRL1004", "HUM3109", "MGT1040"] and prefs["ranking"] == ["mixed"]
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM preferences").fetchone()[0] == 1


def test_window_closed_and_not_yet_open(codes):
    c = sign_in(codes["ann"])
    with db.connect() as con:
        db.set_settings(con, {"window_override": "closed"})
    r = c.post("/api/submit", json=CHOICE)
    assert r.status_code == 409 and "closed" in r.json()["detail"]
    assert c.put("/api/preferences", json=CHOICE).status_code == 409
    assert c.post("/api/preview", json=CHOICE).status_code == 200              # looking is still allowed
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(timespec="seconds")
    with db.connect() as con:
        db.set_settings(con, {"window_override": "", "window_open": future,
                              "window_close": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()})
    assert "not opened" in c.post("/api/submit", json=CHOICE).json()["detail"]


def test_every_pattern_marked_never_is_refused(codes):
    r = sign_in(codes["ann"]).post("/api/submit", json={**CHOICE, "never": ["morning_heavy", "mixed"]})
    assert r.status_code == 409


# ---- allocation, result, add/drop ------------------------------------------------------------------------

def test_full_flow_dry_run_final_run_result_add_drop_and_exports(codes):
    students = {a: sign_in(codes[a]) for a in ("ann", "bob")}
    for c in students.values():
        c.post("/api/event", json={"type": "started"})
        assert c.post("/api/submit", json=CHOICE).status_code == 200
    a = admin()
    # every morning-heavy timetable needs MAT1003 in B1+TB1+TBB1; one seat there forces the second student off their first choice
    assert a.put("/api/admin/capacity", json={"offering_id": "MAT1003|TH|B1+TB1+TBB1", "seats": 1}).status_code == 200

    dry = a.post("/api/admin/allocate", json={"kind": "dry"}).json()
    assert not dry["saved"] and dry["report"]["students"] == 2 and dry["report"]["not_submitted"] == 1
    assert students["ann"].get("/api/result").json() == {"ready": False}        # a dry run saves nothing

    assert a.post("/api/admin/allocate", json={"kind": "final"}).status_code == 409   # window still open
    a.put("/api/admin/settings", json={"window_override": "closed"})
    final = a.post("/api/admin/allocate", json={"kind": "final"}).json()
    assert final["saved"] and final["report"]["capacity_exceeded"] == 0
    assert [x["alias"] for x in final["assignments"]] == [x["alias"] for x in dry["assignments"]]   # same seed
    assert final["report"]["first_choice"] == 1 and final["report"]["second_choice"] == 1

    second = final["assignments"][1]["alias"]
    res = students[second].get("/api/result").json()
    assert res["status"] == "placed" and res["choice_rank"] == 2 and res["position"] == 2
    assert "was full in MAT1003 B1+TB1+TBB1" in res["explanation"] and res["seed"] and res["timetable"]["classes"]
    assert students["ann"].get("/api/result").json()["add_drop"] == {"allowed": 1, "used": 0}

    # add/drop: one change allowed, seated immediately, then capped
    change = {**CHOICE, "electives": ["FRL1004", "HUM3109", "MGT1040"]}
    assert students[second].post("/api/adddrop", json=change).status_code == 200
    assert any(c["course"] == "FRL1004" for c in students[second].get("/api/result").json()["timetable"]["classes"])
    r = students[second].post("/api/adddrop", json=CHOICE)
    assert r.status_code == 409 and "used your add/drop" in r.json()["detail"]

    cy = sign_in(codes["cy"])                                    # never submitted
    assert cy.get("/api/result").json()["status"] == "not_included"

    students["ann"].post("/api/feedback", json={"sus": [5, 1] * 5, "ease": 5, "confused": "=nothing", "comments": "ok"})
    fb = a.get("/api/admin/export/feedback.csv").text
    assert "100.0" in fb and "'=nothing" in fb                    # SUS score; formula neutralised
    assert "ann" in a.get("/api/admin/export/results.csv").text
    assert "submitted" in a.get("/api/admin/export/events.csv").text
    timing = a.get("/api/admin/export/timing.csv").text
    assert "25.7" in timing and "started > submitted" in timing
    over = a.get("/api/admin/overview").json()
    assert over["counts"] == {"testers": 3, "submitted": 2, "feedback": 1} and over["sus_mean"] == 100.0
    assert over["timing"]["completed"] == 2 and over["timing"]["baseline_minutes"] == 25.7
    assert a.get("/api/admin/export/secret.csv").status_code == 404


def test_add_drop_never_overbooks_a_full_slot(codes):
    cs = {x: sign_in(codes[x]) for x in ("ann", "bob")}
    for c in cs.values():
        c.post("/api/submit", json={**CHOICE, "pins": ["CSE1013:TH:E1+TE1"]})
    a = admin()
    a.put("/api/admin/capacity", json={"offering_id": "CSE1013|TH|E1+TE1", "seats": 1})
    a.put("/api/admin/settings", json={"window_override": "closed"})
    final = a.post("/api/admin/allocate", json={"kind": "final"}).json()
    assert final["report"]["unplaced"] == 1
    loser = cs[final["assignments"][1]["alias"]]
    r = loser.post("/api/adddrop", json={**CHOICE, "pins": ["CSE1013:TH:E1+TE1"]})     # still full
    assert r.status_code == 409 and "No change made" in r.json()["detail"]
    assert loser.post("/api/adddrop", json=CHOICE).status_code == 200                   # without the pin: seated
    cap = a.get("/api/admin/capacity", params={"course": "CSE1013"}).json()["offerings"]
    assert all(o["taken"] <= o["seats"] for o in cap)


# ---- admin ---------------------------------------------------------------------------------------------

def test_admin_settings_tiers_and_validation(codes):
    a = admin()
    r = a.put("/api/admin/settings", json={"tiers": ["Final year", "All students"], "earlier_miss_weight": 2})
    assert r.status_code == 200 and r.json()["settings"]["tiers"][0] == "Final year"
    assert a.put("/api/admin/settings", json={"tiers": ["Final year"]}).status_code == 409   # testers still in the other
    assert a.put("/api/admin/settings", json={"credit_min": 30}).status_code == 422
    assert a.put("/api/admin/settings", json={"window_open": "tomorrow"}).status_code == 422
    assert a.put("/api/admin/settings", json={"made_up": 1}).status_code == 422
    tid = a.get("/api/admin/testers").json()[0]["id"]
    assert a.put(f"/api/admin/testers/{tid}/tier", json={"tier": "Final year"}).status_code == 200
    assert a.put(f"/api/admin/testers/{tid}/tier", json={"tier": "Nope"}).status_code == 422


def test_admin_testers_import_new_code_and_real_registration_numbers_refused(codes):
    a = admin()
    rep = a.post("/api/admin/testers/import", json={"csv": "alias,program,semester\ndee,B.Tech CSE,5\n23BCB7031,B.Tech CSE,5\n"}).json()
    assert rep["created"] == 1 and "registration number" in rep["problems"][0]
    assert sign_in(rep["codes"][0][1]).get("/api/me").json()["required"][0]["code"] == "CSE2008"   # from curriculum
    tid = next(t["id"] for t in a.get("/api/admin/testers").json() if t["alias"] == "ann")
    fresh = a.post(f"/api/admin/testers/{tid}/code").json()["code"]
    assert TestClient(server.app).post("/api/login", json={"code": codes["ann"]},
                                       headers={"x-csrf-token": "x"}).status_code == 401   # old code is dead
    assert sign_in(fresh).get("/api/me").json()["alias"] == "ann"


def test_simulation_is_labelled_synthetic_and_saves_nothing(codes):
    out = admin().post("/api/admin/simulate", json={"students": 12, "seats_per_section": 1, "rounds": 2}).json()
    assert out["synthetic"] and len(out["rounds"]) == 2 and out["rounds"][0]["capacity_exceeded"] == 0
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 3


def test_reset_wipes_beta_data_keeps_settings_and_takes_a_backup(codes):
    sign_in(codes["ann"]).post("/api/submit", json=CHOICE)
    a = admin()
    assert a.post("/api/admin/reset", json={"confirm": "yes"}).status_code == 422
    out = a.post("/api/admin/reset", json={"confirm": "RESET"}).json()
    assert out["backup"].startswith("fca-") and (db.data_dir() / "backups" / out["backup"]).exists()
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
        assert db.get_settings(con)["credit_max"] == 27


def test_wording_rule_holds_across_the_code_base():
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[2]
    banned = re.compile("lott" + "ery|random" + r"[\s_-]*draw|\bl" + "uck", re.I)
    files = [p for sub, pat in (("app/fca", "*.py"), ("app/config", "*.json"), ("app/web/src", "*.*"), ("docs", "*.md"))
             for p in (root / sub).glob(pat)] + [root / "README.md"]
    files = [p for p in files if p.name != "CLAUDE_CONTEXT.md"]
    assert files
    for p in files:
        assert not banned.search(p.read_text(encoding="utf-8")), p
