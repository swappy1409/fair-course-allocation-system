"""Combination generation, pins, credit limits and the explosion guard."""
import itertools
import time

from hypothesis import given, settings, strategies as st

from fca.catalogue import Catalogue
from fca.solver import Limits, Pin, solve
from helpers import tiny_catalogue

REAL = Catalogue.load()
ANY_CREDITS = Limits(credit_min=0, credit_max=99)
HEAVY = ["CSE2001", "CSE2008", "CSE3002", "CSE3003", "CSE3004", "MAT1003"]   # 5 lab courses, 24 credits
LIGHT = ["CSE1013", "FRL1001", "HUM3109", "LAW2104", "MAT1003", "MGT1040"]   # theory only, 18 credits


def brute_force(cat, courses):
    variables = sorted((c, t) for c in sorted(set(courses)) for t in cat.components(c))
    out = set()
    for pick in itertools.product(*(cat.options(*v) for v in variables)):
        if all(not a.mask & b.mask for a, b in itertools.combinations(pick, 2)):
            out.add(frozenset(o.id for o in pick))
    return out


def assert_valid(cat, res, courses):
    assert len(set(res.combos)) == len(res.combos)
    for combo in res.combos:
        offs = [cat.offerings[i] for i in combo]
        assert sorted((o.course, o.type) for o in offs) == sorted(
            (c, t) for c in set(courses) for t in cat.components(c))
        used = 0
        for o in offs:
            assert not used & o.mask, combo
            used |= o.mask


# ---- TC-01..03: zero, exactly one, many ------------------------------------------------

def test_zero_combinations_when_two_courses_share_their_only_slot():
    cat = tiny_catalogue({"X": {"TH": ["A"]}, "Y": {"TH": ["A"]}})
    res = solve(cat, ["X", "Y"], limits=ANY_CREDITS)
    assert (res.count, res.combos, res.exact) == (0, [], True)
    assert "No conflict-free combination" in res.summary()


def test_exactly_one_combination():
    cat = tiny_catalogue({"X": {"TH": ["A"]}, "Y": {"TH": ["A", "B"]}})
    res = solve(cat, ["X", "Y"], limits=ANY_CREDITS)
    assert res.combos == [("X|TH|A", "Y|TH|B")] and res.count == 1
    assert res.summary() == "1 combination available."


def test_small_real_request_is_exact_and_matches_brute_force():
    res = solve(REAL, LIGHT)
    assert res.exact and res.count == 36 == len(res.combos)
    assert {frozenset(c) for c in res.combos} == brute_force(REAL, LIGHT)
    assert_valid(REAL, res, LIGHT)


def test_very_large_space_is_capped_honestly_and_spread_across_options():
    res = solve(REAL, HEAVY)
    assert not res.exact and not res.timed_out
    assert len(res.combos) <= Limits().sample_size <= res.count
    assert "at least" in res.summary()
    assert_valid(REAL, res, HEAVY)
    # the kept set is not one corner of the space: every theory slot of every course that
    # can appear at all does appear
    for i, (course, ctype) in enumerate(res.variables):
        if ctype == "ETH":
            seen = {c[i] for c in res.combos}
            assert len(seen) >= 4, (course, seen)


# ---- pins ----------------------------------------------------------------------------

def test_pin_is_applied_before_generation():
    pin = Pin.parse("CSE1013:TH:E2+TE2")
    res = solve(REAL, LIGHT, [pin])
    assert res.count > 0 and all("CSE1013|TH|E2+TE2" in c for c in res.combos)
    assert res.count < solve(REAL, LIGHT).count


def test_pin_on_lab_component_and_atom_order_insensitive():
    courses = ["CSE2001", "CSE1013", "MAT1003", "MGT1040", "FRL1001"]
    res = solve(REAL, courses, [Pin.parse("CSE2001:ELA:L4+L3")])
    assert res.count > 0 and all("CSE2001|ELA|L3+L4" in c for c in res.combos)


def test_all_pins_on_one_slot_gives_zero():
    cat = tiny_catalogue({"X": {"TH": ["A", "B"]}, "Y": {"TH": ["A", "C"]}})
    res = solve(cat, ["X", "Y"], [Pin("X", "TH", "A"), Pin("Y", "TH", "A")], ANY_CREDITS)
    assert res.count == 0 and not res.problems


def test_invalid_pins_are_reported_not_ignored():
    kinds = lambda pins: [p.kind for p in solve(REAL, LIGHT, pins).problems]
    assert kinds([Pin("CSE1013", "TH", "A1")]) == ["bad_pin"]             # not offered there
    assert kinds([Pin("CSE2001", "ETH", "D1+TD1")]) == ["bad_pin"]        # course not selected
    assert kinds([Pin("CSE1013", "TH", "E1+TE1"), Pin("CSE1013", "TH", "E2+TE2")]) == ["pin_conflict"]


# ---- required course with a single slot; backlog clashing with required ------------------

def test_required_course_with_single_slot_is_always_in_that_slot():
    res = solve(REAL, LIGHT)
    i = res.variables.index(("LAW2104", "ETH"))
    assert {c[i] for c in res.combos} == {"LAW2104|ETH|C1+TC1"}


def test_backlog_course_clashing_with_required_course_gives_zero():
    cat = tiny_catalogue({"REQ": {"TH": ["A+B"]}, "BACKLOG": {"TH": ["B+C"]}, "FREE": {"TH": ["D", "E"]}})
    assert solve(cat, ["REQ", "BACKLOG", "FREE"], limits=ANY_CREDITS).count == 0


# ---- credits ---------------------------------------------------------------------------

def test_credit_limits_are_inclusive_at_16_and_27():
    cat = tiny_catalogue({f"C{i}": {"credits": 4, "TH": [chr(65 + i)]} for i in range(7)}
                         | {"T3": {"credits": 3, "TH": ["Z"]}, "T1": {"credits": 1, "TH": ["Y"]}})
    four = [f"C{i}" for i in range(4)]
    assert solve(cat, four).count == 1                                   # exactly 16
    assert solve(cat, four[:3] + ["T3"]).problems[0].kind == "credits_low"   # 15
    six = [f"C{i}" for i in range(6)]
    assert solve(cat, six + ["T3"]).count == 1                           # exactly 27
    assert solve(cat, six + ["T3", "T1"]).problems[0].kind == "credits_high"  # 28
    assert solve(cat, six + ["T3"]).credits == 27


def test_unknown_course_and_project_course_without_credits():
    assert [p.kind for p in solve(REAL, LIGHT + ["XXX0000"]).problems] == ["unknown_course"]
    assert [p.kind for p in solve(REAL, LIGHT + ["CAP4001"]).problems] == ["no_credits"]


# ---- determinism, symmetry, blocked ----------------------------------------------------------

def test_same_inputs_same_output_regardless_of_input_order():
    a, b = solve(REAL, HEAVY), solve(REAL, list(reversed(HEAVY)) + HEAVY[:2])
    assert (a.combos, a.count, a.buckets, a.variables) == (b.combos, b.count, b.buckets, b.variables)


def test_parallel_sections_are_generated_once():
    assert REAL.offerings["CSE2001|ETH|E1+TE1"].sections == 13
    res = solve(REAL, ["CSE2001", "CSE1013", "MAT1003", "MGT1040", "FRL1001"])
    assert len(set(res.combos)) == len(res.combos)


def test_blocked_offerings_are_never_used():
    blocked = frozenset({"CSE1013|TH|E1+TE1"})
    res = solve(REAL, LIGHT, blocked=blocked)
    assert res.count > 0 and not any(blocked & set(c) for c in res.combos)


def test_keep_function_buckets_and_orders_results():
    keep = lambda cat, combo: ("early" if "CSE1013|TH|E1+TE1" in combo else "late", len(combo[1]))
    res = solve(REAL, LIGHT, keep=keep, limits=Limits(per_bucket=5))
    assert sum(res.buckets.values()) == res.count == 36
    assert len(res.combos) == 10 and set(res.buckets) == {"early", "late"}


# ---- performance -----------------------------------------------------------------------------

def test_typical_generation_is_under_two_seconds():
    for courses in (HEAVY, LIGHT, ["CSE2001", "CSE3003", "CSE3004", "MAT1003", "ECE2002"]):
        t0 = time.perf_counter()
        solve(REAL, courses)
        assert time.perf_counter() - t0 < 2.0


# ---- property: solver == brute force on random small catalogues ------------------------------

SLOTS = {n: [("TUE", 480 + 30 * i, 540 + 30 * i)] for i, n in enumerate("ABCDEFGH")}  # neighbours overlap
slot_combo = st.lists(st.sampled_from(sorted(SLOTS)), min_size=1, max_size=2, unique=True).map("+".join)
course_spec = st.fixed_dictionaries(
    {"TH": st.lists(slot_combo, min_size=1, max_size=4, unique=True)},
    optional={"ELA": st.lists(slot_combo, min_size=1, max_size=3, unique=True)})


@settings(max_examples=150, deadline=None)
@given(st.lists(course_spec, min_size=1, max_size=5))
def test_solver_finds_exactly_the_conflict_free_combinations(specs):
    from fca.timetable import canonical_slot
    specs = [{k: sorted({canonical_slot(s) for s in v}) for k, v in spec.items()} for spec in specs]
    cat = tiny_catalogue({f"K{i}": spec for i, spec in enumerate(specs)}, SLOTS)
    courses = list(cat.courses)
    res = solve(cat, courses, limits=ANY_CREDITS)
    assert res.exact
    assert {frozenset(c) for c in res.combos} == brute_force(cat, courses)
    assert res.count == len(res.combos)
    assert_valid(cat, res, courses)
