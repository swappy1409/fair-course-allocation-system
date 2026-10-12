"""Seat allocation in rounds.

Order of students
  1. Priority tier, in the order the tiers are listed in settings.
  2. Inside a tier, students who missed their top pattern in earlier rounds go first:
     priority = earlier_miss_weight x (sum over earlier rounds of how many places below
     their first choice they landed; not being placed counts as one more than the worst).
  3. Remaining ties use the equal-priority order: students are sorted by
     SHA-256("<seed>|<round>|<alias>"). The seed and this method are published to students,
     so anyone can recompute the order. Nothing about it depends on when someone submitted.

Assignment
  Each student in turn gets the best combination, in their own ranked order of patterns,
  whose every course-slot still has a seat. Full course-slots are removed and the solver is
  run again, so a student is only left unplaced when no conflict-free combination with free
  seats exists at all. Unplaced students go to the add/drop step; the run never fails.

Everything is a pure function of (students, capacities, settings, round, history): the same
inputs give the same result, and no course-slot is ever filled beyond its capacity.
"""
from __future__ import annotations

import hashlib
import random
import statistics
from collections import Counter

from .archetypes import Archetypes
from .catalogue import Catalogue
from .solver import Limits, Pin, solve

METHOD = ("Students are ordered by priority tier. Inside a tier, anyone who missed their top pattern in an "
          "earlier round is moved up. Remaining ties use the equal-priority order: a fixed, published seed is "
          "combined with the round number and each alias, hashed with SHA-256, and sorted. The same seed "
          "always gives the same order, and submitting earlier or later makes no difference.")
ORDINAL = {1: "1st", 2: "2nd", 3: "3rd"}


def ordinal(n: int) -> str:
    return ORDINAL.get(n, f"{n}th")


def tie_break(seed: str, round_no: int, alias: str) -> str:
    return hashlib.sha256(f"{seed}|{round_no}|{alias}".encode()).hexdigest()


def seats_for(cat: Catalogue, settings: dict, overrides: dict | None = None) -> dict[str, int]:
    """Capacity per offering: an explicit override, else sections x seats per section."""
    per = settings["beta_seats_per_section"] if settings.get("use_beta_seats") else settings["seats_per_section"]
    overrides = overrides or {}
    return {oid: int(overrides.get(oid, o.sections * per)) for oid, o in cat.offerings.items()}


def student_order(students: list[dict], settings: dict, round_no: int, history: dict | None = None) -> list[dict]:
    tiers = settings["tiers"]
    weight = float(settings.get("earlier_miss_weight", 1.0))
    history = history or {}

    def key(s):
        tier = tiers.index(s["tier"]) if s["tier"] in tiers else len(tiers)
        return tier, -weight * history.get(s["alias"], 0), tie_break(settings["allocation_seed"], round_no, s["alias"])

    return sorted(students, key=key)


class Allocator:
    def __init__(self, cat: Catalogue, arch: Archetypes, settings: dict):
        self.cat, self.arch, self.settings = cat, arch, settings
        self.limits = Limits(credit_min=settings["credit_min"], credit_max=settings["credit_max"],
                             node_budget=30_000, sample_size=1_500, per_bucket=100)
        self._cache: dict = {}

    def options(self, s: dict, blocked: frozenset = frozenset()):
        """(result, rows) with rows = (choice rank, archetype, score, combo) in the student's order."""
        courses = tuple(sorted(set(s["required"]) | set(s["backlog"]) | set(s["electives"])))
        pins = tuple(sorted(s["pins"]))
        key = (courses, pins, blocked)
        if key not in self._cache:
            self._cache[key] = solve(self.cat, list(courses), [Pin.parse(p) for p in pins], self.limits,
                                     keep=self.arch.keep, blocked=blocked)
        return self._cache[key]

    def order_of(self, s: dict) -> list[str]:
        ids = [a["id"] for a in self.arch.items]
        ranked = [a for a in dict.fromkeys(s.get("ranking", [])) if a in ids and a not in s.get("never", [])]
        return ranked + [a for a in ids if a not in ranked and a not in s.get("never", [])]

    def place(self, s: dict, free: dict[str, int]) -> dict:
        """Choose a combination for one student given the free seats. Does not change `free`."""
        base = self.options(s)
        order = self.order_of(s)
        wanted = [a for a in order if base.buckets.get(a)]          # patterns that exist for this student
        if base.problems or not wanted:
            why = "; ".join(p.message for p in base.problems) or "No timetable is possible for these courses and pins."
            return {"status": "unplaced", "combo": [], "archetype": None, "choice_rank": None,
                    "explanation": f"{why} Use the add/drop step to change your choices."}
        rank = {a: i + 1 for i, a in enumerate(wanted)}

        def best(result):
            rows = [(rank[b], sc, c) for b, sc, c in result.scored
                    if b in rank and all(free.get(o, 0) > 0 for o in c)]
            return min(rows) if rows else None

        pick = best(base)
        if pick is None or pick[0] > 1:
            full = frozenset(o for o, n in free.items() if n <= 0)
            again = best(self.options(s, full))
            if again and (pick is None or again < pick):
                pick = again
        top = self.arch.by_id[wanted[0]]["label"]
        if pick is None:
            blockers = Counter(o for b, _, c in base.scored for o in c if free.get(o, 0) <= 0)
            name = self._offering_name(blockers.most_common(1)[0][0]) if blockers else "one of your courses"
            return {"status": "unplaced", "combo": [], "archetype": None, "choice_rank": None,
                    "explanation": f"Every timetable for your courses needs a seat that was already taken "
                                   f"(for example {name}). You can change your choices in the add/drop step."}
        r, _score, combo = pick
        label = self.arch.by_id[next(a for a in wanted if rank[a] == r)]["label"]
        if r == 1:
            text = f"You got your 1st-choice pattern ({label})."
        else:
            blockers = Counter(o for b, _, c in base.scored if rank.get(b) == 1 for o in c if free.get(o, 0) <= 0)
            name = self._offering_name(blockers.most_common(1)[0][0]) if blockers else "at least one course-slot"
            text = (f"Your 1st-choice pattern ({top}) was full in {name}, so you got your "
                    f"{ordinal(r)}-choice pattern ({label}).")
        return {"status": "placed", "combo": list(combo), "archetype": next(a for a in wanted if rank[a] == r),
                "choice_rank": r, "explanation": text}

    def _offering_name(self, oid: str) -> str:
        o = self.cat.offerings[oid]
        return f"{o.course} {o.slot}"


def run_allocation(cat: Catalogue, arch: Archetypes, settings: dict, students: list[dict],
                   capacity: dict[str, int], round_no: int = 1, history: dict | None = None,
                   allocator: Allocator | None = None) -> dict:
    """students: dicts with alias, tier, required, backlog, electives, pins, ranking, never.
    Returns {"assignments": [...], "report": {...}}. Saves nothing."""
    allocator = allocator or Allocator(cat, arch, settings)
    free = dict(capacity)
    assignments = []
    for position, s in enumerate(student_order(students, settings, round_no, history), 1):
        a = allocator.place(s, free)
        for oid in a["combo"]:
            assert free[oid] > 0, f"capacity exceeded for {oid}"   # cannot happen: place() checks every seat
            free[oid] -= 1
        assignments.append({"alias": s["alias"], "tier": s["tier"], "position": position,
                            "priority": float(settings.get("earlier_miss_weight", 1.0)) * (history or {}).get(s["alias"], 0),
                            **a})
    return {"assignments": assignments,
            "report": fairness_report(cat, settings, assignments, capacity, free, round_no)}


def fairness_report(cat, settings, assignments, capacity, free, round_no) -> dict:
    placed = [a for a in assignments if a["status"] == "placed"]
    ranks = [a["choice_rank"] for a in placed]
    by_rank = Counter(min(r, 4) for r in ranks)
    n = len(assignments)
    used = {o: capacity[o] - free[o] for o in capacity if capacity[o] != free[o]}
    quarter = max(1, n // 4)
    mean = lambda xs: round(statistics.mean(xs), 2) if xs else None

    by_tier = {}
    for tier in dict.fromkeys(a["tier"] for a in assignments):
        rs = [a["choice_rank"] for a in placed if a["tier"] == tier]
        by_tier[tier] = {"students": sum(1 for a in assignments if a["tier"] == tier),
                         "placed": len(rs), "first_choice": sum(1 for r in rs if r == 1), "mean_choice": mean(rs)}
    return {
        "round": round_no, "seed": settings["allocation_seed"], "method": METHOD,
        "earlier_miss_weight": settings.get("earlier_miss_weight", 1.0),
        "students": n, "placed": len(placed), "unplaced": n - len(placed),
        "first_choice": by_rank[1], "second_choice": by_rank[2], "third_choice": by_rank[3],
        "fourth_or_lower": by_rank[4],
        "first_choice_share": round(by_rank[1] / n, 3) if n else None,
        "mean_choice": mean(ranks),
        "choice_spread": round(statistics.pstdev(ranks), 2) if len(ranks) > 1 else 0.0,
        "worst_choice": max(ranks) if ranks else None,
        # Does going early in the order matter much? Compare the first and last quarter.
        "mean_choice_first_quarter": mean([a["choice_rank"] for a in assignments[:quarter] if a["choice_rank"]]),
        "mean_choice_last_quarter": mean([a["choice_rank"] for a in assignments[-quarter:] if a["choice_rank"]]),
        "by_tier": by_tier,
        "seats_used": sum(used.values()),
        "course_slots_used": len(used),
        "course_slots_full": sum(1 for o in used if free[o] == 0),
        "capacity_exceeded": sum(1 for o in capacity if free[o] < 0),   # must always be 0
        "capacity_source": settings.get("capacity_source", "synthetic"),
        "order": [{"position": a["position"], "alias": a["alias"], "tier": a["tier"], "priority": a["priority"]}
                  for a in assignments],
    }


def miss_history(rounds: list[list[dict]]) -> dict[str, float]:
    """alias -> total places below first choice over earlier rounds (unplaced = worst + 1)."""
    out: Counter = Counter()
    for assignments in rounds:
        worst = max((a["choice_rank"] or 0 for a in assignments), default=0)
        for a in assignments:
            out[a["alias"]] += (a["choice_rank"] - 1) if a["choice_rank"] else worst
    return dict(out)


# ---- simulation: synthetic students, clearly labelled, nothing saved ------------------------------

def synthetic_students(cat: Catalogue, arch: Archetypes, settings: dict, curriculum: dict, n: int,
                       seed: str) -> list[dict]:
    """n generated students with varied electives and pattern rankings. Reproducible from `seed`."""
    rng = random.Random(f"simulation|{seed}")
    allocator = Allocator(cat, arch, settings)
    pool = sorted(c.code for c in cat.courses.values() if c.credits)
    programmes = sorted(curriculum)
    ids = [a["id"] for a in arch.items]
    out = []
    for i in range(n):
        key = programmes[rng.randrange(len(programmes))]
        required = sorted(curriculum[key]["required"])
        target = rng.randint(settings["credit_min"], min(settings["credit_max"], settings["credit_min"] + 6))
        student = None
        for _ in range(30):                                   # retry until the choice has a timetable
            electives, credits = [], sum(cat.courses[c].credits for c in required)
            for code in rng.sample(pool, len(pool)):
                if credits >= target:
                    break
                if code not in required and credits + cat.courses[code].credits <= settings["credit_max"]:
                    electives.append(code)
                    credits += cat.courses[code].credits
            ranking = rng.sample(ids, len(ids))
            cand = {"alias": f"SIM-{i + 1:04d}", "tier": settings["tiers"][rng.randrange(len(settings['tiers']))],
                    "required": required, "backlog": [], "electives": sorted(electives), "pins": [],
                    "ranking": ranking, "never": ranking[-1:] if rng.random() < 0.2 else [], "synthetic": True}
            res = allocator.options(cand)
            if not res.problems and res.count:
                student = cand
                break
        if student:
            out.append(student)
    return out


def simulate(cat, arch, settings, curriculum, n: int = 200, seats_per_section: int = 3, rounds: int = 2,
             seed: str | None = None) -> dict:
    seed = seed or settings["allocation_seed"]
    settings = {**settings, "allocation_seed": seed, "use_beta_seats": True, "beta_seats_per_section": seats_per_section}
    students = synthetic_students(cat, arch, settings, curriculum, n, seed)
    capacity = seats_for(cat, settings)
    allocator = Allocator(cat, arch, settings)
    history, done, reports = {}, [], []
    for r in range(1, rounds + 1):
        result = run_allocation(cat, arch, settings, students, capacity, r, history, allocator)
        if done:
            before = {a["alias"]: a["choice_rank"] for a in done[-1]}
            missed = [a for a in result["assignments"] if before[a["alias"]] != 1]
            better = [a for a in missed if a["choice_rank"] and (before[a["alias"]] is None or a["choice_rank"] < before[a["alias"]])]
            result["report"]["missed_top_choice_last_round"] = len(missed)
            result["report"]["of_those_improved_this_round"] = len(better)
        result["report"].pop("order")
        reports.append(result["report"])
        done.append(result["assignments"])
        history = miss_history(done)
    return {"synthetic": True, "label": "SYNTHETIC simulation: generated students, not real testers",
            "students": len(students), "seats_per_section": seats_per_section, "seed": seed, "rounds": reports}
