"""Load testers and print their invite codes.

    python -m fca.seed                 load app/data/synthetic_testers.csv (keeps existing testers)
    python -m fca.seed testers.csv     load your own CSV
    python -m fca.seed --reset         wipe ALL beta data (testers, choices, runs, logs) first

Tester CSV columns: alias, program, year, semester, tier, required_courses, backlog_courses
(course lists separated by spaces or semicolons; an optional `synthetic` column marks
generated rows). If required_courses is empty it is filled from the curriculum CSV for
that program and semester. Invite codes are shown once and stored only as hashes; they
are also written to <data dir>/invite_codes.csv, which is never committed.
"""
from __future__ import annotations

import csv
import io
import json
import re
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db

DATA = Path(__file__).resolve().parent.parent / "data"
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
BETA_TABLES = ("students", "preferences", "runs", "allocations", "events", "feedback", "sessions", "add_drop", "capacity")


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def hash_code(code: str) -> str:
    import hashlib
    return hashlib.sha256(("invite:" + code.strip().upper()).encode()).hexdigest()


def _codes(text: str) -> list[str]:
    return sorted(set(re.findall(r"[A-Z]{3}\d{4}", (text or "").upper())))


def read_curriculum(path=DATA / "synthetic_curriculum.csv") -> dict:
    out: dict = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            out.setdefault((r["program"].strip(), str(r["semester"]).strip()), {"required": [], "backlog": []})[
                r["kind"].strip().lower()].append(r["course_code"].strip().upper())
    return out


def import_testers(con, csv_text: str, known_courses=None) -> dict:
    """Insert or update testers. New testers get an invite code. Returns a report."""
    settings = db.get_settings(con)
    curriculum = read_curriculum()
    expires = (datetime.now(timezone.utc) + timedelta(days=settings["invite_code_valid_days"])).isoformat(timespec="seconds")
    codes, problems, updated = [], [], 0
    for n, r in enumerate(csv.DictReader(io.StringIO(csv_text.lstrip("﻿"))), 2):
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        alias = r.get("alias", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{2,40}", alias):
            problems.append(f"line {n}: alias '{alias}' must be 2-40 letters, digits, '_', '.' or '-'")
            continue
        if re.fullmatch(r"\d{2}[A-Za-z]{3}\d{4,5}", alias):
            problems.append(f"line {n}: '{alias}' looks like a real registration number; use an alias instead")
            continue
        program, semester = r.get("program", ""), r.get("semester", "")
        required = _codes(r.get("required_courses")) or curriculum.get((program, semester), {}).get("required", [])
        backlog = [c for c in _codes(r.get("backlog_courses")) if c not in required]
        if known_courses is not None:
            unknown = [c for c in required + backlog if c not in known_courses]
            if unknown:
                problems.append(f"line {n}: {alias} lists courses not offered this semester: {', '.join(unknown)}")
                continue
        tier = r.get("tier") or settings["tiers"][0]
        if tier not in settings["tiers"]:
            problems.append(f"line {n}: {alias} has tier '{tier}', which is not one of {settings['tiers']}")
            continue
        fields = (program, int(r.get("year") or 0), int(semester or 0), tier, json.dumps(sorted(required)),
                  json.dumps(backlog), int(bool(r.get("synthetic"))))
        if con.execute("SELECT 1 FROM students WHERE alias = ?", (alias,)).fetchone():
            con.execute("UPDATE students SET program=?, year=?, semester=?, tier=?, required=?, backlog=?, "
                        "synthetic=? WHERE alias=?", (*fields, alias))
            updated += 1
        else:
            code = new_code()
            con.execute("INSERT INTO students(program, year, semester, tier, required, backlog, synthetic, alias, "
                        "code_hash, code_expires, created) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (*fields, alias, hash_code(code), expires, db.now()))
            codes.append((alias, code))
    return {"created": len(codes), "updated": updated, "problems": problems, "codes": codes, "expires": expires}


def reset_beta(con) -> None:
    for t in BETA_TABLES:
        con.execute(f"DELETE FROM {t}")


def main(argv) -> None:
    from .catalogue import Catalogue
    db.init()
    path = next((a for a in argv if not a.startswith("--")), DATA / "synthetic_testers.csv")
    with db.connect() as con:
        if "--reset" in argv:
            reset_beta(con)
            print("Beta data wiped.")
        report = import_testers(con, Path(path).read_text(encoding="utf-8-sig"), Catalogue.load().courses)
    out = db.data_dir() / "invite_codes.csv"
    if report["codes"]:
        new = not out.exists() or "--reset" in argv
        with open(out, "w" if new else "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["alias", "invite_code", "expires"])
            w.writerows([a, c, report["expires"]] for a, c in report["codes"])
    print(f"{report['created']} testers created, {report['updated']} updated.")
    for p in report["problems"]:
        print("  PROBLEM:", p)
    for alias, code in report["codes"]:
        print(f"  {alias:<12} {code}")
    if report["codes"]:
        print(f"Codes saved to {out} (shown once; only hashes are stored in the database).")


if __name__ == "__main__":
    main(sys.argv[1:])
