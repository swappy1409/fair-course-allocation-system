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

Kept results: `keep` is a function combo -> (bucket, score); the best `per_bucket`
combinations of each bucket (lowest score, ties by offering ids) are kept. Without it
everything goes in one bucket, up to `sample_size`, in generation order.
"""
from __future__ import annotations

import heapq
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
    nodes: int = 0
    credits: int = 0
    problems: list[Problem] = field(default_factory=list)

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
          keep=None, blocked: frozenset[str] = frozenset()) -> Result:
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

    class Collector:
        def __init__(self):
            self.count, self.buckets, self.heaps, self.seq = 0, {}, {}, 0

        def add(self, chosen):
            combo = tuple(chosen[k] for k in unorder)
            self.count += 1
            bucket, score = keep(cat, combo) if keep else ("all", self.count)
            self.buckets[bucket] = self.buckets.get(bucket, 0) + 1
            heap = self.heaps.setdefault(bucket, [])
            item = (-score, _Rev(combo), combo)  # max-heap on (score, ids): worst on top
            if len(heap) < cap:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)

        def combos(self):
            out = []
            for bucket in sorted(self.heaps):
                out += [c for _, _, c in sorted(self.heaps[bucket], key=lambda it: (-it[0], it[2]))]
            return out

    def exact(i, doms, chosen, col):
        if i == len(order):
            col.add(chosen)
            return
        for mask, oid in doms[0]:
            tick(limits.node_budget)
            rest = narrowed(doms[1:], mask)
            if rest is not None:
                chosen.append(oid)
                exact(i + 1, rest, chosen, col)
                chosen.pop()

    def spread(i, doms, chosen, col, quota):
        if i == len(order):
            col.add(chosen)
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
                found += spread(i + 1, rest, chosen, col, share)
                chosen.pop()
        return found

    cap = limits.per_bucket if keep else limits.sample_size
    col = Collector()
    try:
        exact(0, search_domains, [], col)
    except _Budget:
        result.exact = False
        lower_bound, col = col.count, Collector()
        if not result.timed_out:
            try:
                spread(0, search_domains, [], col, limits.sample_size)
            except _Budget:
                pass
        col.count = max(col.count, lower_bound)
    result.count, result.buckets, result.combos, result.nodes = col.count, col.buckets, col.combos(), state["nodes"]
    return result


class _Rev:
    """Reverses string order inside the max-heap so ties keep the smallest offering ids."""
    __slots__ = ("s",)

    def __init__(self, s):
        self.s = s

    def __lt__(self, other):
        return self.s > other.s

    def __gt__(self, other):
        return self.s < other.s

    def __eq__(self, other):
        return self.s == other.s


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
