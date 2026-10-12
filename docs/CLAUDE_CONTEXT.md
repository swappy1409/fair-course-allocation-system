# CLAUDE_CONTEXT — Fair Course Allocation System

**Last Updated:** 2026-10-13

## What this is

Beta-testable preference-based course and slot allocation system for VIT-AP SCOPE,
replacing first-come-first-served registration. Beta on phones by Mon 2026-10-19; lab
demo Tue 2026-10-27. The full brief was pasted in chat on 2026-10-13 (not in the repo).
The old single-file demo in `prototype/` is left untouched.

## Current Phase

**M1 and M2 done and committed on branch `beta-build`. Stopped for the M2 demo; next is M3.**

Milestones: M1 data+clash (done), M2 combinations+pins (done, demo shown), M3 archetypes
+diagnostics, M4 student screens (then demo), M5 allocation+simulation+admin,
M6 instrumentation+deploy+docs. Commit after each; tests must pass before moving on.

## Confirmed decisions (user answered "defaults" on 2026-10-13)

- Stack: FastAPI + SQLite WAL + React/Vite served by the same app; one Docker container.
- Hosting: user's laptop + free Cloudflare quick tunnel. No accounts, no spending.
- Repeated Annexure II rows = parallel sections; capacity = sections x seats per section.
- Seats per section 60 (synthetic) with a "beta scale" override of 2 so slots fill.
- Credits derived (Annexure I credit table + 1 per two lab blocks), labelled "derived".
  The 7 PJT courses have no credits and are left out of the synthetic curriculum.
- Baskets, curriculum (required/backlog) and 15 testers are synthetic and labelled so.
- One ETH + one ELA of the same course, any non-clashing pair, counted as one course.
- 16-27 credits inclusive. Tiers configurable, default one tier.
- Window: open 2026-10-19 09:00 IST, close 2026-10-25 23:59 IST, one round on 10-26,
  then add/drop capped at one change per student.
- Wording rule: never "lottery", "random draw" or "luck" anywhere (UI, docs, identifiers);
  say "equal-priority order" / "fair tie-break".
- Privacy contact: user's VIT-AP student email.

## Architecture so far

| Path | Purpose |
|---|---|
| `app/fca/timetable.py` | slot -> cells; 5-minute bit mask per slot combination; `clash` = mask AND |
| `app/fca/importer.py` | pdfplumber parse of both Annexures -> `app/data/catalogue.json` + parse report |
| `app/fca/catalogue.py` | `Catalogue.load()`: courses, offerings (id `CODE|TYPE|SLOT`), `options(code, type)` |
| `app/fca/solver.py` | `solve(cat, courses, pins, limits, keep, blocked)` -> `Result`; CLI `python -m fca.solver` |
| `tests/helpers.py` | `tiny_catalogue()` for exact-answer tests |

Solver notes: course set is fixed (required + backlog + chosen electives); credits are a
property of the set. Exact pass within `node_budget` (120k), else a quota-spread pass
keeping `sample_size` (4000) and reporting "at least M". `keep(cat, combo) -> (bucket,
score)` hook is where M3 archetypes plug in (top `per_bucket` per bucket). `blocked` is
for full offerings during allocation (plan: re-solve live with full offerings blocked).

## Commands

- Tests: `.venv/Scripts/python -m pytest -q` (44 pass, ~7 s)
- Re-import: `cd app && ../.venv/Scripts/python -m fca.importer <A1.pdf> <A2.pdf> data/catalogue.json`
- Solver demo: `cd app && ../.venv/Scripts/python -m fca.solver CSE1013 FRL1001 HUM3109 LAW2104 MAT1003 MGT1040 --pin FRL1001:TH:G1`

## Next Task

M3: `app/config/archetypes.json` (features: morning/evening share, days used, gaps, lab
placement, free days), classifier + secondary score wired through `keep`, infeasibility
diagnostics (small conflicting set, ranked relaxations with unlock counts), tests, commit.

## Known Issues

- Lab-heavy requests (4-5 lab courses) always exceed the node budget, so their count is a
  lower bound, not the true total.
- Git warns about LF->CRLF on Windows; harmless.

## Tests Last Run

2026-10-13: 44 passed.

## Blockers

None. Waiting for the user's reaction to the M2 demo.

### Input PDFs (`inputs/`, untracked) — parsed with pdfplumber in `.venv`, clean tables

- Annexure I (1 page): Tue–Sat grid, 10 theory blocks and 12 lab blocks per day with
  different clock times, so clashes must use real time intervals. Shared theory cells
  (e.g. `TC1/G1`, `E1/SC2`, `TAA1/ECS`). Labs L1–L60. Credit-to-slot-pattern table.
- Annexure II (26 pages): 1399 rows, 227 courses, 802 distinct (course, type, slot)
  offerings; 597 rows repeat an offering (probably parallel sections). Types ETH 520,
  ELA 456, TH 412, PJT 7 (slot `NILL`), LO 4. 0 unparsed rows.
- Not in the PDFs: credits, baskets, capacities, section/faculty, theory–lab pairing.
