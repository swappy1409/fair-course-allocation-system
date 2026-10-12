"""Glue between the solver and the API: caching, a student's ranked order, JSON shapes."""
from __future__ import annotations

from functools import lru_cache

from .archetypes import Archetypes
from .catalogue import Catalogue
from .diagnostics import diagnose
from .solver import Limits, Pin, Result, solve

_loaded: dict = {}


def cat() -> Catalogue:
    if "cat" not in _loaded:
        from .db import data_dir
        uploaded = data_dir() / "catalogue.json"      # written by an admin re-import; else the bundled one
        _loaded["cat"] = Catalogue.load(uploaded) if uploaded.exists() else Catalogue.load()
        _loaded["arch"] = Archetypes.load(_loaded["cat"])
    return _loaded["cat"]


def arch() -> Archetypes:
    cat()
    return _loaded["arch"]


def reload() -> None:
    _loaded.clear()
    _solve.cache_clear()


@lru_cache(maxsize=512)
def _solve(courses: tuple, pins: tuple, cmin: int, cmax: int, blocked: frozenset) -> Result:
    return solve(cat(), list(courses), list(pins), Limits(credit_min=cmin, credit_max=cmax),
                 keep=arch().keep, blocked=blocked)


def evaluate(settings: dict, courses, pins, blocked=frozenset()) -> Result:
    return _solve(tuple(sorted(set(courses))), tuple(sorted(pins, key=lambda p: (p.course, p.type, p.slot))),
                  settings["credit_min"], settings["credit_max"], frozenset(blocked))


def parse_pins(texts) -> list[Pin]:
    return [Pin.parse(t) for t in texts]


def pin_text(p: Pin) -> str:
    return f"{p.course}:{p.type}:{p.slot}"


def rank_order(ranking, never) -> list[str]:
    """The student's archetype order: ranked ones first, then any they did not rank in
    the configured order. Archetypes marked 'never' are left out entirely."""
    ids = [a["id"] for a in arch().items]
    ranked = [a for a in dict.fromkeys(ranking) if a in ids and a not in never]
    return ranked + [a for a in ids if a not in ranked and a not in never]


def in_student_order(res: Result, order: list[str]):
    """(choice rank, archetype, score, combo), best first. Rank counts only archetypes that
    actually contain a combination for this student, so '1st choice' is always achievable."""
    present = [a for a in order if res.buckets.get(a)]
    pos = {a: i + 1 for i, a in enumerate(present)}
    rows = [(pos[b], b, s, c) for b, s, c in res.scored if b in pos]
    return sorted(rows, key=lambda r: (r[0], r[2], r[3]))


def combo_view(combo) -> dict:
    c, a = cat(), arch()
    f = a.features(c, combo)
    aid = a.classify(f)
    classes = []
    for oid in combo:
        o = c.offerings[oid]
        classes.append({"offering": oid, "course": o.course, "title": c.courses[o.course].title,
                        "type": o.type, "slot": o.slot, "cells": c.timetable.cells(o.slot)})
    return {"archetype": aid, "label": a.by_id[aid]["label"], "score": a.score(f), "features": f,
            "classes": classes}


def clean_electives(student: dict, electives) -> list[str]:
    fixed = set(student["required"]) | set(student["backlog"])
    return sorted({e for e in electives if e in cat().courses and e not in fixed})


def preview(settings: dict, student: dict, electives, pin_texts, ranking=(), never=()) -> dict:
    c, a = cat(), arch()
    fixed = sorted(set(student["required"]) | set(student["backlog"]))
    electives = clean_electives(student, electives)
    pins = parse_pins(pin_texts)
    res = evaluate(settings, fixed + electives, pins)
    out = {
        "credits": sum(c.courses[x].credits or 0 for x in fixed + electives),
        "credit_min": settings["credit_min"], "credit_max": settings["credit_max"],
        "count": 0 if res.problems else res.count, "exact": res.exact, "summary": res.summary(),
        "archetypes": [], "top": [], "diagnosis": None,
    }
    if res.problems or res.count == 0:
        d = diagnose(c, fixed, electives, pins,
                     Limits(credit_min=settings["credit_min"], credit_max=settings["credit_max"]))
        out["summary"] = d.summary
        out["diagnosis"] = {
            "summary": d.summary, "conflicts": d.conflicts, "courses": d.conflict_courses,
            "relaxations": [{"kind": r.kind, "message": r.message, "unlocks": r.unlocks,
                             "unlocks_text": r.unlock_text(),
                             "electives": clean_electives(student, r.courses),
                             "pins": [pin_text(p) for p in r.pins]} for r in d.relaxations],
        }
        return out
    out["archetypes"] = [{"id": x["id"], "label": x["label"], "description": x["description"],
                          "count": res.buckets[x["id"]]} for x in a.items if res.buckets.get(x["id"])]
    seen = set()
    for rank, bucket, _score, combo in in_student_order(res, rank_order(ranking, never)):
        if bucket not in seen:            # the best timetable of each of the top three patterns
            seen.add(bucket)
            out["top"].append({"choice": rank, **combo_view(combo)})
            if len(seen) == 3:
                break
    return out
