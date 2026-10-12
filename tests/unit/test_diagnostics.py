"""Infeasibility explanations and ranked relaxations."""
from fca.catalogue import Catalogue
from fca.diagnostics import diagnose
from fca.solver import Limits, Pin, feasible, solve
from helpers import tiny_catalogue

REAL = Catalogue.load()
ANY = Limits(credit_min=0, credit_max=99)
REQUIRED = ["CSE1013", "LAW2104", "MAT1003"]
ELECTIVES = ["FRL1001", "HUM3109", "MGT1040"]


def test_feasible_request_needs_no_diagnosis():
    d = diagnose(REAL, REQUIRED, ELECTIVES)
    assert d.feasible and not d.conflicts and not d.relaxations


def test_pin_clash_names_both_courses_the_slots_and_the_time():
    d = diagnose(REAL, REQUIRED, ELECTIVES, [Pin.parse("FRL1001:TH:G1")])
    assert not d.feasible
    assert d.conflict_courses == ["FRL1001", "LAW2104"] and len(d.conflict_pins) == 1
    assert d.conflicts[0] == ("FRL1001 pinned to G1 clashes with LAW2104, which is offered only in "
                              "C1+TC1. Both meet on Tue 11:00.")


def test_relaxations_are_ranked_and_their_unlock_counts_are_true():
    d = diagnose(REAL, REQUIRED, ELECTIVES, [Pin.parse("FRL1001:TH:G1")])
    assert d.relaxations[0].kind == "drop_pin" and d.relaxations[0].unlocks == 36
    order = ["drop_pin", "drop_all_pins", "swap_elective", "drop_elective"]
    kinds = [r.kind for r in d.relaxations]
    assert kinds == sorted(kinds, key=order.index)
    for r in d.relaxations:                       # one-click apply gives exactly what was promised
        res = solve(REAL, r.courses, r.pins)
        assert not res.problems and res.count == r.unlocks and r.exact
        assert set(REQUIRED) <= set(r.courses)    # required courses are never offered for removal


def test_conflict_set_is_minimal():
    cat = tiny_catalogue({k: {"TH": ["A", "B"]} for k in "XYZ"} | {"W": {"TH": ["C", "D"]}})
    d = diagnose(cat, [], list("WXYZ"), limits=ANY)
    assert d.conflict_courses == ["X", "Y", "Z"]              # W is irrelevant and left out
    assert "any 2 of them can" in d.conflicts[0]
    for drop in "XYZ":
        assert feasible(cat, [c for c in "XYZ" if c != drop])


def test_backlog_clashing_with_required_is_not_fixable_by_the_student():
    cat = tiny_catalogue({"REQ": {"TH": ["A+B"]}, "BACK": {"TH": ["B+C"]}, "EL": {"TH": ["D", "E"]}})
    d = diagnose(cat, ["REQ", "BACK"], ["EL"], limits=ANY)
    assert d.conflict_courses == ["BACK", "REQ"]
    assert "BACK, which is offered only in B+C clashes with REQ, which is offered only in A+B" in d.conflicts[0]
    assert any("cannot fix this yourself" in c for c in d.conflicts)
    assert d.relaxations == []


def test_swap_is_suggested_before_drop_and_only_within_the_same_basket_and_credits():
    cat = tiny_catalogue({"REQ": {"TH": ["A"]}, "EL": {"TH": ["A"]}, "ALT": {"TH": ["B"]},
                          "BIG": {"credits": 3, "TH": ["C"]}})
    d = diagnose(cat, ["REQ"], ["EL"], limits=ANY)
    assert [(r.kind, r.unlocks) for r in d.relaxations] == [("swap_elective", 1), ("drop_elective", 1)]
    assert d.relaxations[0].courses == ["ALT", "REQ"]


def test_drop_is_not_offered_when_it_breaks_the_credit_minimum():
    cat = tiny_catalogue({"REQ": {"credits": 12, "TH": ["A"]}, "EL": {"TH": ["A"]}, "ALT": {"TH": ["B"]}})
    d = diagnose(cat, ["REQ"], ["EL"], limits=Limits(credit_min=16, credit_max=27))
    assert [r.kind for r in d.relaxations] == ["swap_elective"]


def test_pin_to_a_slot_not_offered_is_explained_and_fixable():
    d = diagnose(REAL, REQUIRED, ELECTIVES, [Pin("MGT1040", "ETH", "C1+TC1")])
    assert d.conflicts[0] == "MGT1040 (ETH) is not offered in C1+TC1."
    assert d.relaxations[0].kind == "drop_pin" and d.relaxations[0].unlocks == 36


def test_two_pins_on_the_same_cell():
    cat = tiny_catalogue({"X": {"TH": ["A", "B"]}, "Y": {"TH": ["A", "C"]}})
    pins = [Pin("X", "TH", "A"), Pin("Y", "TH", "A")]
    d = diagnose(cat, [], ["X", "Y"], pins, ANY)
    assert d.conflicts[0].startswith("X pinned to A clashes with Y pinned to A.")
    assert [r.kind for r in d.relaxations[:2]] == ["drop_pin", "drop_pin"]


def test_credit_problem_is_reported_in_plain_language():
    d = diagnose(REAL, REQUIRED, [])
    assert "minimum is 16" in d.conflicts[0]
