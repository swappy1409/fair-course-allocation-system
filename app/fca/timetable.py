"""Slot timetable and clash model.

Every slot name maps to a set of cells (day, start minute, end minute) read from
Annexure I. Clashes are decided by time overlap of cells, never by comparing names:
two different names can clash (TC1 and G1 share a cell; lab L2 overlaps theory A1),
and one name can occupy several cells (A1 meets on two days).

Each slot combination is reduced to an integer bit mask with one bit per 5-minute
tick of the week, so a clash test is a single `a & b`.
"""
from __future__ import annotations

import re

TICK_MINUTES = 5
TICKS_PER_DAY = 24 * 60 // TICK_MINUTES
NO_SLOT = "NILL"  # Annexure II uses this for project courses with no timetable cells

Cell = tuple[str, int, int]  # (day, start minute, end minute), end exclusive


def _natural_key(atom: str):
    m = re.fullmatch(r"([A-Z]+)(\d*)", atom)
    return (m.group(1), int(m.group(2) or 0)) if m else (atom, 0)


def atoms(slot: str) -> list[str]:
    return [a for a in slot.split("+") if a]


def canonical_slot(slot: str) -> str:
    """Same atoms in any order are the same slot combination (F1+TBB2+TF1 == F1+TF1+TBB2)."""
    return "+".join(sorted(set(atoms(slot.replace(" ", "").upper())), key=_natural_key))


def cells_overlap(a: Cell, b: Cell) -> bool:
    return a[0] == b[0] and a[1] < b[2] and b[1] < a[2]


class Timetable:
    def __init__(self, days: list[str], slots: dict[str, list[Cell]]):
        self.days = list(days)
        self.slots = {name: [tuple(c) for c in cells] for name, cells in slots.items()}
        self._atom_mask = {name: self._mask_of(cells) for name, cells in self.slots.items()}
        self._atom_mask[NO_SLOT] = 0

    def _mask_of(self, cells) -> int:
        mask = 0
        for day, start, end in cells:
            if start % TICK_MINUTES or end % TICK_MINUTES or end <= start:
                raise ValueError(f"bad cell {(day, start, end)}")
            base = self.days.index(day) * TICKS_PER_DAY
            for t in range(start // TICK_MINUTES, end // TICK_MINUTES):
                mask |= 1 << (base + t)
        return mask

    def knows(self, atom: str) -> bool:
        return atom in self._atom_mask

    def cells(self, slot: str) -> list[Cell]:
        """All cells a slot combination occupies, in day/time order."""
        out = [c for a in atoms(slot) for c in self.slots.get(a, [])]
        return sorted(set(out), key=lambda c: (self.days.index(c[0]), c[1], c[2]))

    def mask(self, slot: str) -> int:
        m = 0
        for a in atoms(slot):
            m |= self._atom_mask[a]  # KeyError on an unknown slot name is deliberate
        return m

    def clash(self, slot_a: str, slot_b: str) -> bool:
        return bool(self.mask(slot_a) & self.mask(slot_b))
