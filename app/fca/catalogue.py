"""In-memory catalogue: courses, offerings and the timetable they sit on."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .timetable import Timetable

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "catalogue.json"


@dataclass(frozen=True)
class Offering:
    id: str          # "CSE2001|ETH|D1+TD1"
    course: str
    type: str        # TH, ETH, ELA, LO, PJT
    slot: str        # canonical slot combination
    sections: int    # identical rows in Annexure II, treated as parallel sections
    mask: int        # timetable bit mask, see timetable.py


@dataclass(frozen=True)
class Course:
    code: str
    title: str
    types: tuple[str, ...]
    credits: int | None
    credits_source: str
    basket: str
    basket_source: str


class Catalogue:
    def __init__(self, data: dict):
        self.timetable = Timetable(data["days"], data["slots"])
        self.report = data.get("report", {})
        self.courses = {
            c["code"]: Course(c["code"], c["title"], tuple(c["types"]), c["credits"],
                              c["credits_source"], c["basket"], c["basket_source"])
            for c in data["courses"]
        }
        self.offerings: dict[str, Offering] = {}
        self._by_component: dict[tuple[str, str], list[Offering]] = {}
        for o in data["offerings"]:
            off = Offering(o["id"], o["course"], o["type"], o["slot"], o["sections"],
                           self.timetable.mask(o["slot"]))
            self.offerings[off.id] = off
            self._by_component.setdefault((off.course, off.type), []).append(off)

    @classmethod
    def load(cls, path=DEFAULT_PATH) -> "Catalogue":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def components(self, code: str) -> list[str]:
        """The parts a student must take for a course, e.g. ['ETH', 'ELA']: one offering of each."""
        return list(self.courses[code].types)

    def options(self, code: str, ctype: str) -> list[Offering]:
        return self._by_component.get((code, ctype), [])
