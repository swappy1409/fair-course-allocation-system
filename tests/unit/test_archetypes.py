"""Features, archetype classification and the secondary score."""
import json

import pytest

from fca.archetypes import CONFIG_PATH, Archetypes
from fca.catalogue import Catalogue
from fca.solver import Limits, solve
from helpers import tiny_catalogue

REAL = Catalogue.load()
ARCH = Archetypes.load(REAL)
LIGHT = ["CSE1013", "FRL1001", "HUM3109", "LAW2104", "MAT1003", "MGT1040"]
HEAVY = ["CSE2001", "CSE2008", "CSE3002", "CSE3003", "CSE3004", "MAT1003"]

SLOTS = {
    "M8": [("TUE", 480, 530)], "M10": [("TUE", 600, 650)], "M12": [("TUE", 720, 770)],
    "E2": [("TUE", 840, 890)], "E6": [("WED", 1080, 1130)],
    "LM": [("THU", 480, 580)], "LE": [("THU", 840, 940)],
}


def feats(spec):
    cat = tiny_catalogue(spec, SLOTS)
    combo = tuple(sorted(cat.offerings))
    return Archetypes.load(cat).features(cat, combo)


def test_features_of_a_hand_built_timetable():
    f = feats({"X": {"TH": ["M8"]}, "Y": {"TH": ["M10"]}, "Z": {"TH": ["E6"]}, "W": {"ELA": ["LE"]}})
    assert f["class_minutes"] == 50 * 3 + 100
    assert f["days_used"] == 3 and f["free_days"] == 2
    assert f["gap_hours"] == round(70 / 60, 2)          # Tue 8:50 -> 10:00
    assert f["early_starts"] == 1                        # Tue starts 08:00
    assert f["late_finishes"] == 1                       # Wed ends 18:50
    assert f["morning_share"] == round(100 / 250, 3)
    assert (f["theory_morning_share"], f["lab_morning_share"], f["lab_minutes"]) == (round(100 / 150, 3), 0.0, 100)


def test_lunch_break_is_not_a_gap():
    assert feats({"X": {"TH": ["M12"]}, "Y": {"TH": ["E2"]}})["gap_hours"] == 0
    assert feats({"X": {"TH": ["M10"]}, "Y": {"TH": ["E2"]}})["gap_hours"] == 2.0   # 10:50-12:50 only


def test_no_labs_gives_neutral_lab_share():
    assert feats({"X": {"TH": ["M8"]}})["lab_morning_share"] == 0.5


BASE = {"morning_share": 0.5, "theory_morning_share": 0.5, "lab_morning_share": 0.5, "lab_minutes": 100,
        "days_used": 5, "free_days": 0, "gap_hours": 0, "early_starts": 0, "late_finishes": 0, "class_minutes": 900}

RULES = [
    ({"morning_share": 0.95}, "all_morning"),
    ({"morning_share": 0.05}, "all_evening"),
    ({"days_used": 3}, "compact_3_day"),
    ({"theory_morning_share": 0.8, "lab_morning_share": 0.0}, "morning_classes_evening_labs"),
    ({"theory_morning_share": 0.1, "lab_morning_share": 1.0}, "evening_classes_morning_labs"),
    ({"theory_morning_share": 0.8, "lab_morning_share": 0.0, "lab_minutes": 0}, "mixed"),
    ({"days_used": 4}, "four_day_week"),
    ({"morning_share": 0.7}, "morning_heavy"),
    ({"morning_share": 0.3}, "evening_heavy"),
    ({}, "mixed"),
    ({"morning_share": 0.95, "days_used": 3}, "all_morning"),   # first match wins
]


@pytest.mark.parametrize("change,expected", RULES)
def test_classification_rules(change, expected):
    assert ARCH.classify(BASE | change) == expected


def test_every_configured_archetype_is_covered_by_the_table_above():
    assert {expected for _, expected in RULES} == set(ARCH.by_id)


def test_secondary_score_is_the_documented_weighted_sum():
    f = BASE | {"gap_hours": 3, "days_used": 4, "early_starts": 2, "late_finishes": 1}
    assert ARCH.score(f) == 3 * 1.0 + 4 * 2.0 + 2 * 0.5 + 1 * 0.5


def test_config_must_end_with_a_catch_all():
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg["archetypes"] = cfg["archetypes"][:-1]
    with pytest.raises(ValueError):
        Archetypes(cfg, 5)


def test_real_request_is_bucketed_counted_and_ordered():
    res = solve(REAL, LIGHT, keep=ARCH.keep)
    assert sum(res.buckets.values()) == res.count == 36 and set(res.buckets) <= set(ARCH.by_id)
    seen = [ARCH.keep(REAL, c) + (c,) for c in res.combos]
    assert seen == sorted(seen)                      # by archetype, then score, then ids
    assert solve(REAL, LIGHT, keep=ARCH.keep).combos == res.combos


def test_large_request_keeps_at_most_per_bucket_and_offers_several_archetypes():
    res = solve(REAL, HEAVY, keep=ARCH.keep, limits=Limits(per_bucket=50))
    assert len(res.buckets) >= 3
    for bucket in res.buckets:
        assert sum(1 for c in res.combos if ARCH.keep(REAL, c)[0] == bucket) <= 50
