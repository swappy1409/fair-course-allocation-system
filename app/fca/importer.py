"""Read Annexure I (slot timetable) and Annexure II (courses and slots) into a catalogue.

Nothing here invents course, slot or capacity data. What the PDFs do not contain
(credits, baskets) is filled by documented rules and labelled with a `*_source`
field so the UI can show it as derived or synthetic.

Usage:  python -m fca.importer <annexure-I.pdf> <annexure-II.pdf> <out.json>
"""
from __future__ import annotations

import collections
import json
import re
import sys

from .timetable import NO_SLOT, Timetable, atoms, canonical_slot

DAY_NAMES = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}
COURSE_TYPES = {"TH", "ETH", "ELA", "LO", "PJT"}
THEORY_TYPES = {"TH", "ETH"}
LAB_TYPES = {"ELA", "LO"}
NON_TEACHING = {"ECS", "CLUB"}  # activity names that share a cell with a real slot

# Synthetic basket rule (Annexure II has no baskets). Labelled synthetic everywhere.
UNIVERSITY_CORE_PREFIXES = {"MAT", "PHY", "CHY", "ENG", "STS", "ECS", "CAP"}
PROGRAM_PREFIXES = {"CSE", "SWE"}


def _clean(cell) -> str:
    return (cell or "").replace("\n", " ").strip()


def _minutes(text: str, afternoon: bool) -> tuple[int, int]:
    """'8.50 - 9.40' -> (530, 580). The PDF uses a 12-hour clock without am/pm."""
    out = []
    for part in text.split("-"):
        h, m = (int(x) for x in part.strip().split("."))
        if afternoon and h < 12 or not afternoon and h < 8:
            h += 12
        out.append(h * 60 + m)
    return out[0], out[1]


def parse_timetable(pdf_path) -> dict:
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        tables = [t for page in pdf.pages for t in page.extract_tables()]
    grid = next(t for t in tables if _clean(t[0][0]).lower().startswith("theory hours"))
    credit_rows = next(t for t in tables if _clean(t[0][0]).upper().startswith("CREDIT"))

    theory_hours, lab_hours = grid[0], grid[1]
    lunch_col = next(j for j, c in enumerate(theory_hours) if "L" in _clean(c) and "H" in _clean(c))
    days, slots, shared = [], collections.defaultdict(list), []
    day = None
    for row in grid[2:]:
        if _clean(row[0]).upper() in DAY_NAMES:
            day = _clean(row[0]).upper()
            days.append(day)
        hours = theory_hours if _clean(row[1]).lower() == "theory" else lab_hours
        for j in range(2, len(row)):
            names = [n for n in _clean(row[j]).split("/") if n]
            if not names or j == lunch_col:
                continue
            start, end = _minutes(_clean(hours[j]), afternoon=j > lunch_col)
            if len(names) > 1:
                shared.append("/".join(names))
            for name in names:
                slots[name].append((day, start, end))

    credit_table, credit = {}, None
    for row in credit_rows[1:]:
        m = re.match(r"(\d)\s*CREDI", _clean(row[0]).upper())
        if m:
            credit = int(m.group(1))
        for cell in row[1:]:
            if _clean(cell):
                credit_table[canonical_slot(_clean(cell))] = credit
    return {"days": days, "slots": dict(slots), "shared_cells": shared, "credit_table": credit_table}


def parse_courses(pdf_path) -> tuple[list[dict], list[str]]:
    import pdfplumber

    rows, unparsed = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            if not tables:
                unparsed.append(f"page {page_no}: no table found")
            for table in tables:
                for raw in table:
                    r = [_clean(c) for c in raw]
                    if r and r[0].upper().startswith("COURSE"):
                        continue
                    ok = (len(r) == 4 and re.fullmatch(r"[A-Z]{3}\d{4}", r[0]) and r[1]
                          and r[2] in COURSE_TYPES and r[3])
                    if not ok:
                        unparsed.append(f"page {page_no}: {r}")
                        continue
                    rows.append({"code": r[0], "title": r[1], "type": r[2], "slot": canonical_slot(r[3])})
    return rows, unparsed


def synthetic_basket(code: str) -> str:
    prefix, level = code[:3], int(code[3])
    if prefix in PROGRAM_PREFIXES:
        return "Program Core" if level <= 2 else "Program Elective"
    return "University Core" if prefix in UNIVERSITY_CORE_PREFIXES else "University Elective"


def build_catalogue(timetable_pdf, courses_pdf) -> dict:
    tt = parse_timetable(timetable_pdf)
    rows, unparsed = parse_courses(courses_pdf)
    table = Timetable(tt["days"], tt["slots"])

    unknown_atoms = sorted({a for r in rows for a in atoms(r["slot"]) if not table.knows(a)})
    rows = [r for r in rows if all(table.knows(a) for a in atoms(r["slot"]))]

    sections = collections.Counter((r["code"], r["type"], r["slot"]) for r in rows)
    titles = collections.defaultdict(collections.Counter)
    for r in rows:
        titles[r["code"]][r["title"]] += 1

    offerings = [
        {"id": f"{code}|{ctype}|{slot}", "course": code, "type": ctype, "slot": slot, "sections": n}
        for (code, ctype, slot), n in sorted(sections.items())
    ]

    by_course = collections.defaultdict(list)
    for o in offerings:
        by_course[o["course"]].append(o)

    courses, credit_notes = [], []
    for code in sorted(by_course):
        offs = by_course[code]
        types = sorted({o["type"] for o in offs})
        theory = collections.Counter()
        for o in offs:
            if o["type"] in THEORY_TYPES:
                theory[tt["credit_table"].get(o["slot"])] += o["sections"]
        lab = collections.Counter(len(atoms(o["slot"])) // 2 for o in offs if o["type"] in LAB_TYPES)
        credits, source = None, "unknown"
        if "PJT" not in types and None not in theory:
            # Credits are not in Annexure II. Theory credits come from the Annexure I credit
            # table for the slot pattern; a lab adds 1 credit per two lab blocks.
            credits = (theory.most_common(1)[0][0] if theory else 0) + (lab.most_common(1)[0][0] if lab else 0)
            source = "derived"
            if len(theory) > 1 or len(lab) > 1:
                credit_notes.append(f"{code}: offerings imply different credits "
                                    f"(theory {dict(theory)}, lab {dict(lab)}); used the most common")
        elif "PJT" in types:
            credit_notes.append(f"{code}: project course, credits cannot be derived")
        else:
            credit_notes.append(f"{code}: theory slot pattern is not in the Annexure I credit table")
        courses.append({
            "code": code,
            "title": titles[code].most_common(1)[0][0],
            "types": types,
            "credits": credits,
            "credits_source": source,
            "basket": synthetic_basket(code),
            "basket_source": "synthetic",
        })

    report = {
        "timetable": {
            "days": tt["days"],
            "slot_names": len(tt["slots"]),
            "lab_slots": sum(1 for s in tt["slots"] if re.fullmatch(r"L\d+", s)),
            "multi_cell_slots": sum(1 for c in tt["slots"].values() if len(c) > 1),
            "shared_cells": tt["shared_cells"],
            "credit_patterns": len(tt["credit_table"]),
        },
        "courses": {
            "rows": len(rows),
            "courses": len(courses),
            "offerings": len(offerings),
            "rows_repeating_an_offering": len(rows) - len(offerings),
            "by_type": dict(collections.Counter(r["type"] for r in rows)),
            "slot_combinations": len({o["slot"] for o in offerings}),
            "courses_without_credits": sum(1 for c in courses if c["credits"] is None),
        },
        "unparsed_rows": unparsed,
        "unknown_slot_names": unknown_atoms,
        "title_variants": {c: dict(t) for c, t in titles.items() if len(t) > 1},
        "credit_notes": credit_notes,
        "not_in_source": ["credits (derived)", "baskets (synthetic)", "capacities (synthetic)",
                          "section and faculty identifiers", "theory-lab pairing"],
    }
    return {
        "days": tt["days"],
        "slots": {k: [list(c) for c in v] for k, v in sorted(tt["slots"].items())},
        "non_teaching": sorted(NON_TEACHING & set(tt["slots"])),
        "no_slot": NO_SLOT,
        "courses": courses,
        "offerings": offerings,
        "report": report,
    }


if __name__ == "__main__":
    cat = build_catalogue(sys.argv[1], sys.argv[2])
    with open(sys.argv[3], "w", encoding="utf-8") as f:
        json.dump(cat, f, indent=1)
    print(json.dumps(cat["report"], indent=1))
