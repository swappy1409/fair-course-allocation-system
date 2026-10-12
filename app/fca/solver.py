"""Combination generation: every conflict-free way to seat one student's courses.

The course set is fixed before solving (required + backlog + the electives the student
chose); the solver picks one offering per course component (e.g. one ETH and one ELA).

Hard constraints
  * every selected course is included, one offering per component
  * no two chosen offerings overlap in any timetable cell
  * total credits within [credit_min, credit_max] (a property of the course set)
  * every pin holds; pins shrink a component's options before the search starts
  * offerings in `blocked` (e.g. full ones during allocation) are never used

Search: backtracking with forward checking. Variables are ordered smallest domain first,
so theory choices are fixed before the many lab choices and dead ends are cut early.

Explosion guard, all deterministic (budgets count search nodes, not seconds):
  1. Exact pass. Full enumeration within `node_budget`. If it finishes, `count` is the
     true number of combinations and `exact` is True.
  2. Spread pass, only if the exact pass ran out of budget. A quota-limited search
     that shares `sample_size` results evenly across the options of each variable, so
     the kept set spans the whole space instead of one corner of it. `count` is then a
     lower bound ("at least M").
`deadline_s` is a wall-clock safety net only; if it ever fires, `timed_out` is set
because that one result is machine-dependent.

Symmetry removal: Annexure II lists parallel sections as repeated rows. They are merged
into one offering with a section count, so identical timetables are generated once.

Kept results: `keep` is a function (catalogue, combo) -> (bucket, score); the best
`per_bucket` combinations of each bucket (lowest score, ties by offering ids) are kept
and `buckets` counts what was found per bucket. Without it everything is one bucket.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .catalogue import Catalogue, Offering
from .timetable import canonical_slot

COMPONENT_ORDER = {"TH": 0, "ETH": 0, "ELA": 1, "LO": 1, "PJT": 2}


@dataclass(frozen=True)
class Pin:
    course: str
    type: str
    slot: str

    @classmethod
    def parse(cls, text: str) -> "Pin":
        course, ctype, slot = text.split(":")
        return cls(course.strip().upper(), ctype.strip().upper(), canonical_slot(slot))


@dataclass(frozen=True)
class Limits:
    credit_min: int = 16
    credit_max: int = 27
    node_budget: int = 120_000
    sample_size: int = 4_000
    per_bucket: int = 200
    deadline_s: float = 8.0


@dataclass
class Problem:
    """A reason the request cannot be solved as stated, found before or instead of searching."""
    kind: str      # unknown_course, no_credits, credits_low, credits_high, bad_pin, pin_conflict
    message: str
    courses: tuple[str, ...] = ()


@dataclass
class Result:
    variables: list[tuple[str, str]]            # (course, component) in output column order
    combos: list[tuple[str, ...]]               # offering ids, one per variable
    buckets: dict[str, int]                     # bucket -> number of combinations found in it
    count: int = 0
    exact: bool = True
    timed_out: bool = False
    gave_up: bool = False                       # first_only search hit its budget undecided
    nodes: int = 0
    credits: int = 0
    problems: list[Problem] = field(default_factory=list)
    scored: list[tuple[str, float, tuple[str, ...]]] = field(default_factory=list)  # (bucket, score, combo)

    def summary(self) -> str:
        if self.problems:
            return "No combinations: " + "; ".join(p.message for p in self.problems)
        if self.count == 0:
            return "No conflict-free combination exists for these courses and pins."
        shown = len(self.combos)
        if self.exact and shown == self.count:
            return f"{self.count} combination{'s' if self.count != 1 else ''} available."
        if self.exact:
            return f"Showing the best {shown} of {self.count} combinations."
        return (f"Showing the best {shown} of at least {self.count} combinations "
                f"(the full set is too large to count).")


class _Budget(Exception):
    pass


class _Found(Exception):
    pass


def build_domains(cat: Catalogue, courses: list[str], pins: list[Pin], limits: Limits,
                  blocked: frozenset[str] = frozenset()):
    """Validate the request and return (variables, domains, credits, problems)."""
    problems: list[Problem] = []
    codes = sorted(set(courses))
    for code in codes:
        if code not in cat.courses:
            problems.append(Problem("unknown_course", f"{code} is not offered this semester.", (code,)))
        elif cat.courses[code].credits is None:
            problems.append(Problem("no_credits", f"{code} has no credit value in the source data.", (code,)))
    if problems:
        return [], [], 0, problems

    credits = sum(cat.courses[c].credits for c in codes)
    if credits < limits.credit_min:
        problems.append(Problem("credits_low", f"{credits} credits selected; the minimum is "
                                f"{limits.credit_min}. Add {limits.credit_min - credits} more.", tuple(codes)))
    if credits > limits.credit_max:
        problems.append(Problem("credits_high", f"{credits} credits selected; the maximum is "
                                f"{limits.credit_max}. Remove {credits - limits.credit_max}.", tuple(codes)))

    pinned: dict[tuple[str, str], str] = {}
    for p in pins:
        key = (p.course, p.type)
        ids = {o.slot for o in cat.options(p.course, p.type)}
        if p.course not in codes:
            problems.append(Problem("bad_pin", f"{p.course} is pinned but is not one of your courses.", (p.course,)))
        elif p.slot not in ids:
            problems.append(Problem("bad_pin", f"{p.course} ({p.type}) is not offered in {p.slot}.", (p.course,)))
        elif pinned.get(key, p.slot) != p.slot:
            problems.append(Problem("pin_conflict", f"{p.course} ({p.type}) is pinned to both "
                                    f"{pinned[key]} and {p.slot}.", (p.course,)))
        else:
            pinned[key] = p.slot

    variables = sorted(((c, t) for c in codes for t in cat.components(c)),
                       key=lambda v: (v[0], COMPONENT_ORDER[v[1]], v[1]))
    domains = []
    for var in variables:
        dom = [o for o in cat.options(*var) if o.id not in blocked]
        if var in pinned:
            dom = [o for o in dom if o.slot == pinned[var]]
        domains.append(sorted(dom, key=lambda o: o.id))
    return variables, domains, credits, problems


def solve(cat: Catalogue, courses: list[str], pins: list[Pin] = (), limits: Limits = Limits(),
          keep=None, blocked: frozenset[str] = frozenset(), first_only: bool = False) -> Result:
    variables, domains, credits, problems = build_domains(cat, courses, list(pins), limits, blocked)
    result = Result(variables, [], {}, credits=credits, problems=problems)
    if problems or not variables:
        return result

    # Search order: smallest domain first; ties broken by position so it is deterministic.
    order = sorted(range(len(variables)), key=lambda i: (len(domains[i]), i))
    search_domains = [[(o.mask, o.id) for o in domains[i]] for i in order]
    unorder = sorted(range(len(order)), key=lambda k: order[k])  # search position of each variable
    started = time.monotonic()
    state = {"nodes": 0}

    def tick(budget):
        state["nodes"] += 1
        if budget and state["nodes"] > budget:
            raise _Budget
        if not state["nodes"] & 0x3FFF and time.monotonic() - started > limits.deadline_s:
            result.timed_out = True
            raise _Budget

    def narrowed(doms, mask):
        """Forward checking: drop clashing options from every later variable; None on a wipe-out."""
        out = []
        for d in doms:
            d2 = [v for v in d if not v[0] & mask]
            if not d2:
                return None
            out.append(d2)
        return out

    def exact(i, doms, chosen, out):
        if i == len(order):
            out.append(tuple(chosen[k] for k in unorder))
            if first_only:
                raise _Found
            return
        for mask, oid in doms[0]:
            tick(limits.node_budget)
            rest = narrowed(doms[1:], mask)
            if rest is not None:
                chosen.append(oid)
                exact(i + 1, rest, chosen, out)
                chosen.pop()

    def spread(i, doms, chosen, out, quota):
        if i == len(order):
            out.append(tuple(chosen[k] for k in unorder))
            return 1
        found, dom = 0, doms[0]
        for k, (mask, oid) in enumerate(dom):
            share = -(-(quota - found) // (len(dom) - k))  # ceiling: unused quota rolls forward
            if share <= 0:
                break
            tick(0)
            rest = narrowed(doms[1:], mask)
            if rest is not None:
                chosen.append(oid)
                found += spread(i + 1, rest, chosen, out, share)
                chosen.pop()
        return found

    found: list[tuple[str, ...]] = []
    try:
        exact(0, search_domains, [], found)
        result.count = len(found)
    except _Found:
        result.count, result.exact = 1, False
    except _Budget:
        result.exact = False
        lower_bound, found = len(found), []
        if not result.timed_out and not first_only:
            try:
                spread(0, search_domains, [], found, limits.sample_size)
            except _Budget:
                pass
        result.count = max(len(found), lower_bound)
        result.gave_up = first_only

    # Bucket and order what was found. Scoring happens after the search so an abandoned
    # exact pass costs nothing.
    if keep:
        scored = sorted((keep(cat, c), c) for c in found)
        for (bucket, _), _c in scored:
            result.buckets[bucket] = result.buckets.get(bucket, 0) + 1
        kept: dict[str, int] = {}
        for (bucket, _score), c in scored:
            if kept.get(bucket, 0) < limits.per_bucket:
                kept[bucket] = kept.get(bucket, 0) + 1
                result.combos.append(c)
                result.scored.append((bucket, _score, c))
    else:
        result.buckets = {"all": len(found)} if found else {}
        result.combos = sorted(found)[: limits.sample_size]
    result.nodes = state["nodes"]
    return result


def feasible(cat: Catalogue, courses, pins=(), blocked: frozenset[str] = frozenset(),
             node_budget: int = 60_000) -> bool | None:
    """Does any conflict-free combination exist, ignoring credit limits? None if the
    search gave up before finding one or proving there is none."""
    res = solve(cat, courses, pins, Limits(credit_min=0, credit_max=10 ** 6, node_budget=node_budget),
                blocked=blocked, first_only=True)
    if res.problems:
        return False
    return None if res.gave_up else res.count > 0


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="Generate conflict-free combinations for a set of courses.")
    ap.add_argument("courses", nargs="+")
    ap.add_argument("--pin", action="append", default=[], help="COURSE:TYPE:SLOT, e.g. CSE2001:ETH:D1+TD1")
    ap.add_argument("--show", type=int, default=3)
    args = ap.parse_args(argv)
    cat = Catalogue.load()
    t0 = time.perf_counter()
    res = solve(cat, [c.upper() for c in args.courses], [Pin.parse(p) for p in args.pin])
    ms = (time.perf_counter() - t0) * 1000
    print(f"courses: {', '.join(sorted(set(c.upper() for c in args.courses)))}  ({res.credits} credits)")
    for p in args.pin:
        print(f"pin:     {p}")
    print(res.summary())
    print(f"[{res.nodes} search nodes, {ms:.0f} ms, exact={res.exact}]")
    for n, combo in enumerate(res.combos[: args.show], 1):
        print(f"  #{n}")
        for (course, ctype), oid in zip(res.variables, combo):
            o = cat.offerings[oid]
            cells = " ".join(f"{d} {s // 60:02d}:{s % 60:02d}" for d, s, _ in cat.timetable.cells(o.slot))
            print(f"     {course} {ctype:<3} {o.slot:<16} {cells}")


if __name__ == "__main__":
    main()
