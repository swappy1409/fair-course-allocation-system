"""Catalogue import. The committed catalogue.json is checked always; the PDF parse
is re-run and compared only where the (untracked) Annexure PDFs are present."""
import json
from pathlib import Path

import pytest

from fca.catalogue import DEFAULT_PATH, Catalogue
from fca.importer import _minutes, build_catalogue, synthetic_basket
from fca.timetable import atoms

CAT = Catalogue.load()
INPUTS = Path(__file__).resolve().parents[2] / "inputs"


def test_counts_match_confirmed_parse_report():
    r = CAT.report["courses"]
    assert (r["rows"], r["courses"], r["offerings"]) == (1399, 227, 802)
    assert r["by_type"] == {"ETH": 520, "ELA": 456, "TH": 412, "PJT": 7, "LO": 4}
    assert CAT.report["unparsed_rows"] == [] and CAT.report["unknown_slot_names"] == []
    assert sum(o.sections for o in CAT.offerings.values()) == 1399


def test_every_offering_uses_known_slots_and_ids_are_unique():
    assert len(CAT.offerings) == 802
    for o in CAT.offerings.values():
        assert all(CAT.timetable.knows(a) for a in atoms(o.slot))
        assert o.id == f"{o.course}|{o.type}|{o.slot}"


def test_repeated_rows_become_sections():
    assert CAT.offerings["CSE2001|ETH|E1+TE1"].sections == 13


def test_credits_are_derived_and_labelled():
    dsa = CAT.courses["CSE2001"]          # theory D1+TD1 is a 3-credit pattern, plus a 2-block lab
    assert (dsa.credits, dsa.credits_source, dsa.types) == (4, "derived", ("ELA", "ETH"))
    cap = CAT.courses["CAP4001"]          # project: not derivable, never invented
    assert (cap.credits, cap.credits_source) == (None, "unknown")
    assert sum(1 for c in CAT.courses.values() if c.credits is None) == 7


def test_baskets_are_labelled_synthetic():
    assert {c.basket_source for c in CAT.courses.values()} == {"synthetic"}
    assert synthetic_basket("CSE2001") == "Program Core"
    assert synthetic_basket("CSE4006") == "Program Elective"
    assert synthetic_basket("MAT1003") == "University Core"
    assert synthetic_basket("LAW2104") == "University Elective"


def test_clock_parsing():
    assert _minutes("8.50 - 9.40", afternoon=False) == (530, 580)
    assert _minutes("12.30 - 01.10", afternoon=False) == (750, 790)
    assert _minutes("2.00 - 2.50", afternoon=True) == (840, 890)
    assert _minutes("3.50 - 04.40", afternoon=True) == (950, 1000)


@pytest.mark.skipif(not list(INPUTS.glob("*.pdf")), reason="Annexure PDFs not present")
def test_reimport_from_pdfs_reproduces_committed_catalogue():
    a1 = next(INPUTS.glob("ANNEXURE-I*.pdf"))
    a2 = next(INPUTS.glob("ANNEXURE -II*.pdf"))
    fresh = json.loads(json.dumps(build_catalogue(a1, a2)))
    assert fresh == json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
