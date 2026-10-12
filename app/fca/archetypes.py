"""Timetable features, archetype classification and the secondary score.

Archetypes and score weights live in app/config/archetypes.json. Nothing about a
specific archetype is coded here.

Features of a combination (all derived from its timetable cells):
  class_minutes         total minutes in class
  morning_share         share of class minutes that start before `morning_ends_at`
  theory_morning_share  the same, theory components only (0.5 if there is no theory)
  lab_morning_share     the same, lab components only (0.5 if there are no labs)
  lab_minutes           minutes in labs
  days_used             days with at least one class
  free_days             teaching days with no class
  gap_hours             idle time between the first and last class of each day, summed,
                        not counting the lunch break; includes the short breaks between periods
  early_starts          days whose first class starts at `early_start_at` or before
  late_finishes         days whose last class ends after `late_finish_after`

Secondary score (lower is better) = sum of weight x feature over `secondary_score`.
Ties are broken by offering ids, so the order is fully deterministic.
"""
from __future__ import annotations

import json
from pathlib import Path

from .catalogue import Catalogue
from .timetable import TICK_MINUTES, TICKS_PER_DAY

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "archetypes.json"
LAB_TYPES = {"ELA", "LO"}
LUNCH = (12 * 60 + 50, 14 * 60)  # between the last morning and first afternoon theory block


def _tick(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return (int(h) * 60 + int(m)) // TICK_MINUTES


def _span(lo: int, hi: int) -> int:
    return ((1 << hi) - 1) ^ ((1 << lo) - 1)


class Archetypes:
    def __init__(self, config: dict, n_days: int):
        self.config = config
        self.items = config["archetypes"]
        if self.items[-1]["when"]:
            raise ValueError("the last archetype must have no conditions so every combination is classified")
        self.weights = {k: v for k, v in config["secondary_score"].items() if not k.startswith("_")}
        self.n_days = n_days
        self._day = _span(0, TICKS_PER_DAY)
        self._morning = _span(0, _tick(config["morning_ends_at"]))
        self._not_lunch = self._day ^ _span(LUNCH[0] // TICK_MINUTES, LUNCH[1] // TICK_MINUTES)
        self._early = _tick(config["early_start_at"])
        self._late = _tick(config["late_finish_after"])
        self.by_id = {a["id"]: a for a in self.items}

    @classmethod
    def load(cls, cat: Catalogue, path=CONFIG_PATH) -> "Archetypes":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f), len(cat.timetable.days))

    def features(self, cat: Catalogue, combo) -> dict:
        total = lab = 0
        for oid in combo:
            o = cat.offerings[oid]
            total |= o.mask
            if o.type in LAB_TYPES:
                lab |= o.mask
        theory = total & ~lab
        cls_t = morn_t = th_t = th_m = lab_t = lab_m = days = gaps = early = late = 0
        for d in range(self.n_days):
            shift = d * TICKS_PER_DAY
            day = (total >> shift) & self._day
            if not day:
                continue
            days += 1
            first = (day & -day).bit_length() - 1
            last = day.bit_length()
            gaps += (_span(first, last) & ~day & self._not_lunch).bit_count()
            early += first <= self._early
            late += last > self._late
            cls_t += day.bit_count()
            morn_t += (day & self._morning).bit_count()
            t, l = (theory >> shift) & self._day, (lab >> shift) & self._day
            th_t += t.bit_count()
            th_m += (t & self._morning).bit_count()
            lab_t += l.bit_count()
            lab_m += (l & self._morning).bit_count()
        return {
            "class_minutes": cls_t * TICK_MINUTES,
            "morning_share": round(morn_t / cls_t, 3) if cls_t else 0.5,
            "theory_morning_share": round(th_m / th_t, 3) if th_t else 0.5,
            "lab_morning_share": round(lab_m / lab_t, 3) if lab_t else 0.5,
            "lab_minutes": lab_t * TICK_MINUTES,
            "days_used": days,
            "free_days": self.n_days - days,
            "gap_hours": round(gaps * TICK_MINUTES / 60, 2),
            "early_starts": early,
            "late_finishes": late,
        }

    def classify(self, f: dict) -> str:
        for a in self.items:
            if all(c.get("min", float("-inf")) <= f[name] <= c.get("max", float("inf"))
                   for name, c in a["when"].items()):
                return a["id"]
        raise AssertionError("unreachable: last archetype has no conditions")

    def score(self, f: dict) -> float:
        return round(sum(w * f[name] for name, w in self.weights.items()), 3)

    def keep(self, cat: Catalogue, combo):
        """Plug for solver.solve(keep=...): (archetype id, secondary score)."""
        f = self.features(cat, combo)
        return self.classify(f), self.score(f)
