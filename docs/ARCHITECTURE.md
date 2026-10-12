# Architecture

One process, one file database, no external services.

```
phone / laptop browser
        |  HTTPS (Cloudflare quick tunnel) or http://localhost:8000
        v
  FastAPI app (uvicorn, 1 worker)  ---- serves ---->  React build (app/web/dist)
        |
        +-- fca.server      sign-in, sessions, CSRF, student routes
        +-- fca.admin       admin routes, allocation runs, result, add/drop, exports, backups
        +-- fca.service     solver cache, a student's ranked order, JSON shapes
        +-- fca.solver      combination generation (backtracking + forward checking)
        +-- fca.archetypes  timetable features, classification, secondary score
        +-- fca.diagnostics minimal conflict + ranked relaxations
        +-- fca.allocation  order, seat assignment, fairness report, simulation
        +-- fca.timetable   slot -> cells -> bit mask; clash = mask overlap
        +-- fca.importer    Annexure PDFs -> catalogue.json + parse report
        +-- fca.db          SQLite (WAL) schema and helpers
        v
  var/fca.db (SQLite, WAL)   var/backups/   var/invite_codes.csv
```

## Data

**Catalogue** (`app/data/catalogue.json`, rebuilt by the importer): days, slot cells,
courses, offerings and the parse report. An admin re-import writes `var/catalogue.json`,
which takes precedence.

| What | Source | Label shown |
|---|---|---|
| Slots, cells, clock times | Annexure I | real |
| Courses, types, slot combinations | Annexure II | real |
| Sections per offering | repeated rows in Annexure II | real count, interpretation assumed |
| Credits | Annexure I credit table + 1 per two lab blocks | derived |
| Baskets | rule on the course code prefix and level | synthetic |
| Seat capacity | sections x seats per section (setting) | synthetic |
| Curriculum, testers | `app/data/synthetic_*.csv` | synthetic |

**Database tables**: `settings`, `students` (alias, program, tier, required, backlog, hashed
invite code), `preferences` (electives, pins, ranking, never, submitted_at), `capacity`
(overrides), `runs` and `allocations` (final runs only), `events`, `feedback`, `sessions`,
`add_drop`.

## Clash model

Each slot name maps to one or more cells `(day, start minute, end minute)`. A slot
combination such as `A1+TA1` is the union of its cells, stored as an integer with one bit
per 5-minute tick of the week. Two offerings clash when `mask_a & mask_b != 0`. Slot names
are never compared. This handles shared cells (`TC1/G1`), names with several cells (`A1`
meets twice) and labs whose clock differs from theory (`L2` 8:50–9:40 overlaps `A1`
9:00–9:50).

## Combination generation

The course set is fixed before solving: required + backlog + the electives the student
chose. Variables are course components (one theory offering, one lab offering); values are
offerings.

- Pins and blocked (full) offerings shrink domains before the search.
- Credits are checked on the course set (16–27 inclusive by default).
- Search: backtracking, smallest domain first, forward checking after every assignment.
- Symmetry removal: parallel sections with the same slot are one offering with a section count.
- Explosion guard, deterministic because it counts search nodes rather than seconds:
  1. exact pass within `node_budget` (120,000): if it finishes, the count is exact;
  2. otherwise a spread pass shares `sample_size` (4,000) results evenly across the options
     of each variable, and the count is reported as "at least M".
- A wall-clock deadline (8 s) is a safety net only and is flagged if it ever fires.

## Archetypes

`app/config/archetypes.json` holds the ordered list of archetypes, their conditions and
the secondary-score weights. A combination gets the first archetype whose conditions all
hold; the last one has none. Features: morning share (overall, theory, lab), days used,
free days, idle hours, early starts, late finishes. Secondary score (lower is better):
`1.0 x idle hours + 2.0 x days used + 0.5 x early starts + 0.5 x late finishes`; ties by
offering id. The solver keeps the best 200 per archetype.

## Diagnostics

When nothing fits: a deletion-based minimal conflicting set of courses and pins (removing
any one member makes it solvable), turned into a sentence. Then single-change relaxations
(drop a pin, swap an elective for one in the same basket with the same credits, drop an
elective), each re-solved under the full rules so the unlock count is real.

## Allocation

1. Order: tier, then earlier-miss priority (`earlier_miss_weight x places below first
   choice in earlier rounds`), then the equal-priority order
   `SHA-256("<seed>|<round>|<alias>")`.
2. Each student gets their best combination (own pattern order, then secondary score) whose
   every course-slot has a free seat. If the stored combinations are blocked, the solver is
   run again with the full course-slots removed.
3. No combination: the student is marked unplaced and uses add/drop. The run never fails.
4. Dry runs save nothing. Final runs are stored and become what students see.
5. Add/drop: one database write lock at a time; the new choice is seated from the seats
   left, or refused without using up the change.

## Security (beta level)

- Invite codes: 8 characters from a 31-letter alphabet, stored as SHA-256 hashes, expiring.
- Sessions: random token in an HttpOnly, SameSite=Strict cookie (Secure over HTTPS); only
  its hash is stored. Per-session CSRF token required on every change.
- Failed sign-ins are limited per network address (20 per 10 minutes).
- Admin: separate secret from `ADMIN_SECRET`; disabled if unset or under 12 characters.
- All request bodies validated; SQL is parameterised; CSV exports neutralise formulas.
- Daily SQLite backup to `var/backups/` (14 kept), plus one before every reset.
- HTTPS comes from the tunnel; the app itself speaks plain HTTP on port 8000.
