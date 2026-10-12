"""Clash model: decided by cell overlap, never by slot name."""
import itertools

import pytest

from fca.catalogue import Catalogue
from fca.timetable import Timetable, canonical_slot, cells_overlap

CAT = Catalogue.load()
TT = CAT.timetable


def test_timetable_shape_matches_annexure_one():
    assert TT.days == ["TUE", "WED", "THU", "FRI", "SAT"]
    assert sum(1 for s in TT.slots if s[0] == "L" and s[1:].isdigit()) == 60
    assert TT.cells("A1") == [("TUE", 540, 590), ("SAT", 720, 770)]  # one name, two cells
    assert TT.cells("L2") == [("TUE", 530, 580)]                      # lab clock differs from theory
    assert TT.cells("L6") == [("TUE", 750, 790)]                      # 12.30 - 01.10
    assert TT.cells("L36") == [("TUE", 1110, 1150)]                   # 6.30 - 7.10 pm
    assert TT.cells("F2") == [("TUE", 840, 890), ("FRI", 1020, 1070)]


@pytest.mark.parametrize("a,b,expected", [
    ("A1", "A1", True),
    ("A1", "B1", False),
    ("TC1", "G1", True),            # different names, shared cell
    ("E1", "SC2", True),
    ("C1+TC1", "G1", True),         # clash through one atom of a combination
    ("L2", "A1", True),             # lab 8:50-9:40 overlaps theory 9:00-9:50
    ("L1", "TFF1", True),
    ("L2", "TFF1", False),          # touching edges (8:50) do not overlap
    ("L1+L2", "B1", False),
    ("A1+TA1", "L21+L22", True),    # TA1 Fri 10:00 vs lab Fri 9:50-11:30
    ("A1", "A2", False),
    ("NILL", "A1", False),          # project courses occupy no cells
    ("NILL", "NILL", False),
])
def test_known_clashes(a, b, expected):
    assert TT.clash(a, b) is expected
    assert TT.clash(b, a) is expected


def test_mask_agrees_with_interval_overlap_for_every_pair_of_slot_names():
    names = sorted(TT.slots)
    for a, b in itertools.combinations_with_replacement(names, 2):
        brute = any(cells_overlap(x, y) for x in TT.cells(a) for y in TT.cells(b))
        assert TT.clash(a, b) is brute, (a, b)


def test_theory_slots_only_clash_when_they_share_a_cell():
    theory = [s for s in TT.slots if not (s[0] == "L" and s[1:].isdigit())]
    for a, b in itertools.combinations(theory, 2):
        assert TT.clash(a, b) is bool(set(TT.cells(a)) & set(TT.cells(b)))


def test_canonical_slot_ignores_atom_order():
    assert canonical_slot("F1+TBB2+TF1") == canonical_slot("TF1+F1+TBB2") == "F1+TBB2+TF1"
    assert canonical_slot("L22+L21") == "L21+L22"
    assert canonical_slot("L9+L10") == "L9+L10"


def test_unknown_slot_name_is_an_error_not_a_silent_no_clash():
    with pytest.raises(KeyError):
        TT.mask("ZZ9")


def test_bad_cell_rejected():
    with pytest.raises(ValueError):
        Timetable(["TUE"], {"X": [("TUE", 600, 600)]})
