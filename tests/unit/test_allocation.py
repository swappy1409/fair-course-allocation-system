"""Allocation: order, capacity, determinism, explanations, simulation."""
from collections import Counter

from hypothesis import given, settings as hsettings, strategies as st

from fca.allocation import (Allocator, miss_history, run_allocation, seats_for, simulate, student_order,
                            tie_break)
from fca.archetypes import Archetypes
from fca.catalogue import Catalogue
from fca.seed import read_curriculum
from helpers import tiny_catalogue

SLOTS = {"M": [("TUE", 540, 590)], "M2": [("WED", 540, 590)], "E": [("TUE", 900, 950)], "E2": [("WED", 900, 950)]}
CAT = tiny_catalogue({"X": {"TH": ["M", "E"]}, "Y": {"TH": ["M2", "E2"]}}, SLOTS)
ARCH = Archetypes.load(CAT)
SETTINGS = {"credit_min": 0, "credit_max": 99, "tiers": ["Final year", "Others"], "allocation_seed": "seed-1",
            "earlier_miss_weight": 1.0, "seats_per_section": 60, "beta_seats_per_section": 2, "use_beta_seats": False}
MORNING_FIRST = ["all_morning", "all_evening"]


def student(alias, tier="Others", electives=("X",), ranking=MORNING_FIRST, never=(), pins=()):
    return {"alias": alias, "tier": tier, "required": [], "backlog": [], "electives": list(electives),
            "pins": list(pins), "ranking": list(ranking), "never": list(never)}


def run(students, capacity, **kw):
    return run_allocation(CAT, ARCH, SETTINGS | kw.pop("settings", {}), students, capacity, **kw)


def by_alias(result):
    return {a["alias"]: a for a in result["assignments"]}


def test_two_identical_students_same_tier_capacity_one():
    cap = {"X|TH|M": 1, "X|TH|E": 1}
    res = run([student("ann"), student("bob")], cap)
    a = by_alias(res)
    first, second = sorted(a, key=lambda k: a[k]["position"])
    assert first == min(["ann", "bob"], key=lambda x: tie_break("seed-1", 1, x))   # the published order
    assert (a[first]["choice_rank"], a[first]["combo"]) == (1, ["X|TH|M"])
    assert (a[second]["choice_rank"], a[second]["combo"]) == (2, ["X|TH|E"])
    assert a[second]["explanation"] == ("Your 1st-choice pattern (All morning) was full in X M, so you got "
                                        "your 2nd-choice pattern (All evening).")
    assert a[first]["explanation"] == "You got your 1st-choice pattern (All morning)."
    assert res["report"]["first_choice"] == 1 and res["report"]["second_choice"] == 1
    assert res["report"]["capacity_exceeded"] == 0 and res["report"]["course_slots_full"] == 2


def test_full_course_marks_student_for_add_drop_instead_of_failing():
    res = run([student("ann"), student("bob"), student("cy")], {"X|TH|M": 1, "X|TH|E": 1})
    statuses = Counter(a["status"] for a in res["assignments"])
    assert statuses == {"placed": 2, "unplaced": 1}
    last = res["assignments"][-1]
    assert last["status"] == "unplaced" and "add/drop" in last["explanation"] and "X " in last["explanation"]
    assert res["report"]["unplaced"] == 1


def test_never_is_respected_even_if_it_means_unplaced():
    res = run([student("ann"), student("bob", never=["all_evening"])], {"X|TH|M": 1, "X|TH|E": 5},
              settings={"allocation_seed": "s"})
    a = by_alias(res)
    loser = max(a.values(), key=lambda v: v["position"])
    if loser["alias"] == "bob":
        assert loser["status"] == "unplaced"
    assert all("X|TH|E" not in a["bob"]["combo"] for _ in [0])


def test_tiers_come_before_everything_else():
    students = [student(f"s{i}", tier="Others") for i in range(6)] + [student("senior", tier="Final year")]
    order = student_order(students, SETTINGS, 1, {f"s{i}": 9 for i in range(6)})
    assert order[0]["alias"] == "senior"


def test_students_who_missed_out_earlier_move_up_and_weight_is_configurable():
    students = [student(f"s{i}") for i in range(8)]
    plain = [s["alias"] for s in student_order(students, SETTINGS, 2)]
    unlucky = plain[-1]
    moved = [s["alias"] for s in student_order(students, SETTINGS, 2, {unlucky: 2})]
    assert moved[0] == unlucky and moved[1:] == plain[:-1]
    off = [s["alias"] for s in student_order(students, SETTINGS | {"earlier_miss_weight": 0}, 2, {unlucky: 2})]
    assert off == plain


def test_miss_history_counts_places_below_first_choice():
    r1 = [{"alias": "a", "choice_rank": 1}, {"alias": "b", "choice_rank": 3}, {"alias": "c", "choice_rank": None}]
    assert miss_history([r1]) == {"a": 0, "b": 2, "c": 3}


def test_same_seed_same_result_and_input_order_does_not_matter():
    students = [student(f"s{i}", electives=["X", "Y"]) for i in range(7)]
    cap = {o: 2 for o in CAT.offerings}
    a, b = run(students, cap), run(list(reversed(students)), cap)
    assert a == b
    c = run(students, cap, settings={"allocation_seed": "another"})
    assert [x["alias"] for x in c["assignments"]] != [x["alias"] for x in a["assignments"]]
    assert a["report"]["seed"] == "seed-1" and "SHA-256" in a["report"]["method"]


def test_solver_is_rerun_without_full_slots_so_no_valid_seat_is_missed():
    # 30 students, 2 courses, 4 offerings with 15 seats each: exactly enough for everyone.
    students = [student(f"s{i:02d}", electives=["X", "Y"], ranking=[]) for i in range(15)]
    res = run(students, {o: 15 for o in CAT.offerings})
    assert res["report"]["unplaced"] == 0


def test_capacity_comes_from_sections_setting_and_overrides():
    real = Catalogue.load()
    seats = seats_for(real, SETTINGS, {"CSE2001|ETH|E1+TE1": 5})
    assert seats["CSE2001|ETH|E1+TE1"] == 5
    assert seats["CSE2001|ETH|D1+TD1"] == 7 * 60
    assert seats_for(real, SETTINGS | {"use_beta_seats": True})["CSE2001|ETH|D1+TD1"] == 7 * 2


def test_report_has_the_fairness_numbers():
    res = run([student(f"s{i}") for i in range(4)], {"X|TH|M": 2, "X|TH|E": 2})
    r = res["report"]
    assert (r["students"], r["placed"], r["first_choice"], r["second_choice"]) == (4, 4, 2, 2)
    assert r["mean_choice"] == 1.5 and r["choice_spread"] == 0.5 and r["first_choice_share"] == 0.5
    assert r["mean_choice_first_quarter"] == 1 and r["mean_choice_last_quarter"] == 2
    assert [o["position"] for o in r["order"]] == [1, 2, 3, 4]
    assert r["by_tier"]["Others"]["students"] == 4


def test_simulation_on_the_real_catalogue_is_labelled_and_within_capacity():
    real = Catalogue.load()
    arch = Archetypes.load(real)
    s = {"credit_min": 16, "credit_max": 27, "tiers": ["All students"], "allocation_seed": "sim",
         "earlier_miss_weight": 1.0, "seats_per_section": 60, "beta_seats_per_section": 2, "use_beta_seats": True}
    out = simulate(real, arch, s, read_curriculum(), n=25, seats_per_section=1, rounds=2)
    assert out["synthetic"] and "SYNTHETIC" in out["label"] and len(out["rounds"]) == 2
    assert all(r["capacity_exceeded"] == 0 for r in out["rounds"])
    assert out == simulate(real, arch, s, read_curriculum(), n=25, seats_per_section=1, rounds=2)


# ---- properties: capacity is never exceeded; result is a pure function of its inputs ---------------

BIG = tiny_catalogue({"X": {"TH": ["M", "E"]}, "Y": {"TH": ["M2", "E2"], "ELA": ["M", "E"]},
                      "Z": {"TH": ["M", "M2", "E", "E2"]}}, SLOTS)
BIG_ARCH = Archetypes.load(BIG)
IDS = [a["id"] for a in BIG_ARCH.items]
a_student = st.fixed_dictionaries({
    "tier": st.sampled_from(["Final year", "Others"]),
    "electives": st.lists(st.sampled_from(["X", "Y", "Z"]), min_size=1, max_size=3, unique=True),
    "ranking": st.lists(st.sampled_from(IDS), max_size=4, unique=True),
    "never": st.lists(st.sampled_from(IDS), max_size=2, unique=True),
})


@hsettings(max_examples=120, deadline=None)
@given(st.lists(a_student, min_size=1, max_size=12),
       st.dictionaries(st.sampled_from(sorted(BIG.offerings)), st.integers(0, 3)),
       st.text("abc", min_size=1, max_size=3), st.integers(1, 3))
def test_allocation_never_exceeds_capacity_and_is_deterministic(specs, caps, seed, round_no):
    students = [{"alias": f"s{i}", "required": [], "backlog": [], "pins": [], **s} for i, s in enumerate(specs)]
    capacity = {o: caps.get(o, 1) for o in BIG.offerings}
    cfg = SETTINGS | {"allocation_seed": seed}
    res = run_allocation(BIG, BIG_ARCH, cfg, students, capacity, round_no)
    used = Counter(o for a in res["assignments"] for o in a["combo"])
    assert all(used[o] <= capacity[o] for o in used)
    assert res["report"]["capacity_exceeded"] == 0 and res["report"]["seats_used"] == sum(used.values())
    assert len(res["assignments"]) == len(students)
    for a in res["assignments"]:
        s = students[int(a["alias"][1:])]
        if a["status"] == "placed":
            offs = [BIG.offerings[o] for o in a["combo"]]
            assert sorted({o.course for o in offs}) == sorted(s["electives"])
            mask = 0
            for o in offs:
                assert not mask & o.mask
                mask |= o.mask
            assert a["archetype"] not in s["never"]
        else:
            assert a["combo"] == [] and a["explanation"]
    assert res == run_allocation(BIG, BIG_ARCH, cfg, list(reversed(students)), capacity, round_no)
