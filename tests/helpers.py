"""Small hand-built catalogues so tests can state exact expected answers."""
from fca.catalogue import Catalogue

DAYS = ["TUE", "WED", "THU", "FRI", "SAT"]


def tiny_catalogue(courses: dict, slots: dict | None = None) -> Catalogue:
    """courses: {"C1": {"credits": 4, "ETH": ["A", "B"], "ELA": ["L1"]}, ...}
    slots default to one-hour cells on Tuesday: A=8:00, B=9:00, ... ; override to build overlaps."""
    names = sorted({s for spec in courses.values() for k, v in spec.items() if k != "credits"
                    for combo in v for s in combo.split("+")})
    if slots is None:
        slots = {n: [("TUE", 480 + 60 * i, 530 + 60 * i)] for i, n in enumerate(names)}
    data = {"days": DAYS, "slots": {k: [list(c) for c in v] for k, v in slots.items()}, "courses": [], "offerings": []}
    for code, spec in courses.items():
        types = sorted(k for k in spec if k != "credits")
        data["courses"].append({"code": code, "title": code, "types": types, "credits": spec.get("credits", 4),
                                "credits_source": "test", "basket": "Program Core", "basket_source": "test"})
        for t in types:
            for slot in spec[t]:
                data["offerings"].append({"id": f"{code}|{t}|{slot}", "course": code, "type": t,
                                          "slot": slot, "sections": 1})
    return Catalogue(data)
