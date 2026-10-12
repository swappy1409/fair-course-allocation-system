# CLAUDE_CONTEXT — Fair Course Allocation System

**Last Updated:** 2026-10-13

## What this is

Lab-project prototype replacing first-come-first-served FFCS slot booking with
preference-based registration. Student picks courses, the system enumerates every
conflict-free timetable, labels each with a pattern, and the student filters by pattern.

## Architecture

- Entire project is one file: `prototype/index.html` (~490 lines, inline CSS + JS).
- No build step, no dependencies, no backend, no tests. Open the file in a browser.
- `README.md` describes the demo flow. `docs/` is gitignored (this file is local only).

### Layout of `prototype/index.html`

| Section | Lines (approx) | Contents |
|---|---|---|
| CSS | 7–181 | navy/amber theme, panels, cards |
| Markup | 185–229 | 4 panels: examples, course picker + pin, results |
| Data | 233–252 | `COURSES` (12 mock courses with slot options), `EXAMPLES` (ex1–ex3) |
| Scheduling logic | 255–320 | `atoms`, `slotsConflict`, `periodOf`, `daysOf`, `classifyPattern`, `optionsFor`, `generateCombinations` (backtracking), `findHardConflict` |
| UI wiring | 323–486 | render course grid, pin dropdowns, example buttons, validation, `renderResults` |

### Domain rules as implemented

- A slot option is one or more atoms joined by `+` (e.g. `D1+TD1`); two options clash if they share an atom.
- Period: atom ending in `2` = evening, otherwise morning.
- Pattern: >=65% morning atoms -> Morning-heavy; >=65% evening -> Evening-heavy; else <=3 distinct days -> Compact; else Mixed.
- Selection must be 5–7 courses. Optional pin forces one course into one slot.
- Zero results: `findHardConflict` names the first pair whose every option pair clashes; otherwise a generic "no combination" message.
- Results list is capped at 50 cards, sorted by pattern name then generation order.

## Current Phase

**New brief received 2026-10-13: Step 0 (questions) in progress, no code written yet.**
Build a beta-testable preference-based allocation system for VIT-AP SCOPE from scratch
in this folder. Beta usable on phones by Mon 2026-10-19; lab demo Tue 2026-10-27.
Milestones M1 data+clash, M2 combinations+pins (demo), M3 archetypes+diagnostics,
M4 student screens (demo), M5 allocation+simulation+admin, M6 instrumentation+deploy+docs.
Commit after each milestone; tests must pass before moving on.
Wording rule: never use "lottery", "random draw" or "luck" anywhere (UI, docs, identifiers);
say "equal-priority order" / "fair tie-break".
Proposed default stack (unconfirmed): FastAPI + SQLite WAL + React/Vite, one Docker container.

### Input PDFs (`inputs/`, untracked) — parsed with pdfplumber in `.venv`, clean tables

- Annexure I (1 page): Tue–Sat grid, 10 theory blocks and 12 lab blocks per day with
  different clock times, so clashes must use real time intervals. Shared theory cells
  (e.g. `TC1/G1`, `E1/SC2`, `TAA1/ECS`). Labs L1–L60. Credit-to-slot-pattern table.
- Annexure II (26 pages): 1399 rows, 227 courses, 802 distinct (course, type, slot)
  offerings; 597 rows repeat an offering (probably parallel sections). Types ETH 520,
  ELA 456, TH 412, PJT 7 (slot `NILL`), LO 4. 0 unparsed rows.
- Not in the PDFs: credits, baskets, capacities, section/faculty, theory–lab pairing.
- Waiting on user: parse-report confirmation and answers to the Step 0 question batch.

## Last Completed

- `e2b6d74` Add preference-based course registration prototype
- `96eb64f` Remove slide deck instructions and presenter script from README

## Currently Working On

Nothing in progress.

## Next Task

Not defined by the user. README names the next phase as an automated test suite
covering credit-range validation (16–27 credits) and the remaining edge cases.

## Known Issues / Gaps

- Credit-range validation (16–27) is not implemented.
- No actual allocation across students: no seat capacities, no multi-student fairness
  logic, despite the repo name. Only single-student timetable enumeration exists.
- "Rank by pattern" is a filter only; the student cannot order or submit preferences.
- No automated tests; scheduling functions are only reachable inside the page script.
- Mock data only (12 hard-coded CSE courses).

## Important Decisions

- Single self-contained HTML file so the demo runs offline by double-click.
- Mock data, no auth, no database.

## Recently Changed Files

- `prototype/index.html`, `README.md`

## Tests Last Run

None exist.

## Blockers

None.
