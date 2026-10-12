"""Why a request has no combination, and the smallest changes that would fix it.

1. Conflict: a small set of the student's own constraints (courses and pins) that cannot
   all hold together. Found by deletion: start from everything, drop each item in turn and
   keep it dropped if the rest is still impossible. What remains is minimal: removing any
   one item from it makes it solvable.
2. Relaxations: single changes (drop a pin, swap an elective, drop an elective), each
   re-solved with the full rules so the number of combinations it unlocks is real.
   Ranked by how little they change, then by how much they unlock.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .catalogue import Catalogue
from .solver import Limits, Pin, feasible, solve

KIND_ORDER = {"drop_pin": 0, "drop_all_pins": 1, "swap_elective": 2, "drop_elective": 3}
MAX_SWAPS_PER_ELECTIVE = 3
MAX_SWAP_CANDIDATES = 40


@dataclass
class Relaxation:
    kind: str
    message: str
    unlocks: int
    exact: bool
    courses: list[str]          # the full request after applying this change
    pins: list[Pin]

    def unlock_text(self) -> str:
        return f"{'' if self.exact else 'at least '}{self.unlocks} combination{'s' if self.unlocks != 1 else ''}"


@dataclass
class Diagnosis:
    feasible: bool
    summary: str = ""
    conflicts: list[str] = field(default_factory=list)       # plain-language sentences
    conflict_courses: list[str] = field(default_factory=list)
    conflict_pins: list[Pin] = field(default_factory=list)
    relaxations: list[Relaxation] = field(default_factory=list)


def _when(cat: Catalogue, mask: int) -> str:
    """'Tue 11:00' for the first overlapping cell of a clash mask."""
    from .timetable import TICK_MINUTES, TICKS_PER_DAY
    bit = (mask & -mask).bit_length() - 1
    day, tick = divmod(bit, TICKS_PER_DAY)
    minute = tick * TICK_MINUTES
    return f"{cat.timetable.days[day].title()} {minute // 60:02d}:{minute % 60:02d}"


def _describe(cat: Catalogue, course: str, pins: list[Pin]) -> str:
    """'CSE2001 pinned to C1+TC1' / 'MAT1011, which is offered only in C1' / 'X (offered in A, B)'."""
    parts = []
    for ctype in cat.components(course):
        pin = next((p for p in pins if (p.course, p.type) == (course, ctype)), None)
        slots = [o.slot for o in cat.options(course, ctype)]
        label = "" if len(cat.components(course)) == 1 else f" {'lab' if ctype in ('ELA', 'LO') else 'theory'}"
        if pin:
            parts.append(f"{course}{label} pinned to {pin.slot}")
        elif len(slots) == 1:
            parts.append(f"{course}{label}, which is offered only in {slots[0]}")
        elif len(slots) <= 4:
            parts.append(f"{course}{label} (offered in {', '.join(slots)})")
    return " and ".join(parts) or course


def _minimal_conflict(cat: Catalogue, courses: list[str], pins: list[Pin]):
    """Deletion-based minimal conflicting set of courses and pins. None if undecided."""
    courses, pins = sorted(set(courses)), list(pins)
    if feasible(cat, courses, pins) is not False:
        return None
    for c in list(courses):                       # drop whole courses (and their pins) first
        rest = [x for x in courses if x != c]
        rest_pins = [p for p in pins if p.course != c]
        if rest and feasible(cat, rest, rest_pins) is False:
            courses, pins = rest, rest_pins
    for p in list(pins):                          # then pins that are not needed for the conflict
        rest_pins = [x for x in pins if x != p]
        if feasible(cat, courses, rest_pins) is False:
            pins = rest_pins
    return courses, pins


def _conflict_sentence(cat: Catalogue, courses: list[str], pins: list[Pin]) -> str:
    if len(courses) == 1:
        return f"{_describe(cat, courses[0], pins)} cannot be placed: its own theory and lab options overlap."
    if len(courses) == 2:
        a, b = courses
        doms = [[o for t in cat.components(c) for o in cat.options(c, t)
                 if not any((p.course, p.type) == (c, t) and p.slot != o.slot for p in pins)] for c in (a, b)]
        when = ""
        if all(len(d) == 1 for d in doms) and doms[0][0].mask & doms[1][0].mask:
            when = f" Both meet on {_when(cat, doms[0][0].mask & doms[1][0].mask)}."
        return f"{_describe(cat, a, pins)} clashes with {_describe(cat, b, pins)}.{when}"
    listed = "; ".join(_describe(cat, c, pins) for c in courses)
    return (f"These {len(courses)} courses cannot all fit in one timetable, although any "
            f"{len(courses) - 1} of them can: {listed}.")


def diagnose(cat: Catalogue, required: list[str], electives: list[str], pins: list[Pin] = (),
             limits: Limits = Limits(), blocked: frozenset[str] = frozenset()) -> Diagnosis:
    """`required` covers required and backlog courses: they are never offered for removal."""
    pins = list(pins)
    required, electives = sorted(set(required)), sorted(set(electives) - set(required))
    courses = required + electives
    quick = Limits(limits.credit_min, limits.credit_max, node_budget=20_000, sample_size=300)

    def attempt(cs, ps):
        r = solve(cat, cs, ps, quick, blocked=blocked)
        return (r.count, r.exact) if not r.problems else (0, True)

    base = solve(cat, courses, pins, quick, blocked=blocked)
    if base.count and not base.problems:
        return Diagnosis(True, base.summary())

    d = Diagnosis(False)
    if base.problems:
        d.conflicts = [p.message for p in base.problems]
        d.conflict_courses = sorted({c for p in base.problems for c in p.courses if p.kind != "credits_low"
                                     and p.kind != "credits_high"})
    else:
        found = _minimal_conflict(cat, courses, pins)
        if found:
            d.conflict_courses, d.conflict_pins = found
            d.conflicts = [_conflict_sentence(cat, *found)]
            fixed = [c for c in d.conflict_courses if c in required]
            if len(fixed) == len(d.conflict_courses) and not d.conflict_pins:
                d.conflicts.append("All of these are required or backlog courses, so you cannot fix this "
                                   "yourself. It is recorded for the academic office.")
        else:
            d.conflicts = ["No conflict-free timetable was found for this set of courses and pins."]
    d.summary = "No timetable is possible with these choices."

    # ---- single-change relaxations, each re-solved under the full rules --------------------
    out: list[Relaxation] = []

    def consider(kind, message, cs, ps):
        n, exact = attempt(cs, ps)
        if n:
            out.append(Relaxation(kind, message, n, exact, cs, ps))

    for p in pins:
        consider("drop_pin", f"Remove the pin on {p.course} ({p.slot})", courses, [x for x in pins if x != p])
    if len(pins) > 1 and not any(r.kind == "drop_pin" for r in out):
        consider("drop_all_pins", "Remove all pins", courses, [])

    focus = [c for c in electives if c in d.conflict_courses] or electives
    for e in focus:
        rest = [c for c in courses if c != e]
        rest_pins = [p for p in pins if p.course != e]
        if e not in cat.courses:
            consider("drop_elective", f"Drop {e}", rest, rest_pins)
            continue
        consider("drop_elective", f"Drop {e} ({cat.courses[e].title})", rest, rest_pins)
        me = cat.courses[e]
        alts = sorted(c.code for c in cat.courses.values()
                      if c.basket == me.basket and c.credits == me.credits and c.code not in courses)
        swaps = []
        for alt in alts[:MAX_SWAP_CANDIDATES]:
            n, exact = attempt(rest + [alt], rest_pins)
            if n:
                swaps.append(Relaxation("swap_elective", f"Swap {e} for {alt} ({cat.courses[alt].title})",
                                        n, exact, sorted(rest + [alt]), rest_pins))
        out += sorted(swaps, key=lambda r: (-r.unlocks, r.message))[:MAX_SWAPS_PER_ELECTIVE]

    d.relaxations = sorted(out, key=lambda r: (KIND_ORDER[r.kind], -r.unlocks, r.message))
    if not d.relaxations:
        d.conflicts.append("No single change (removing a pin, or swapping or dropping one elective) fixes this.")
    return d
