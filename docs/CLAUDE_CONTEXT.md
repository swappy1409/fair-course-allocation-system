# CLAUDE_CONTEXT — Fair Course Allocation System

**Last Updated:** 2026-10-13 (end of overnight build)

## What this is

Beta-testable preference-based course and slot allocation system for VIT-AP SCOPE,
replacing first-come-first-served registration. Beta on phones by Mon 2026-10-19; lab
demo Tue 2026-10-27. The full brief was pasted in chat on 2026-10-13 (not in the repo).
The old single-file demo in `prototype/` is left untouched.

## Current Phase

**All six milestones (M1–M6) built and committed on branch `beta-build`** (not merged to
`master`, not pushed). User asked to run to the end overnight and review in the morning;
`docs/MORNING_CHECKLIST.md` lists what they must check and the decisions made for them.

## Confirmed decisions (user answered "defaults" on 2026-10-13)

- Stack: FastAPI + SQLite WAL + React/Vite served by the same app; one Docker container.
- Hosting: user's laptop + free Cloudflare quick tunnel. No accounts, no spending.
- Repeated Annexure II rows = parallel sections; capacity = sections x seats per section.
- Seats per section 60 (synthetic) with a beta-scale override of 2 (on by default).
- Credits derived (Annexure I credit table + 1 per two lab blocks). 7 PJT courses have no
  credits and cannot be selected.
- Baskets, curriculum, testers and capacity are synthetic and labelled so.
- One ETH + one ELA of the same course, any non-clashing pair.
- Course set is fixed before solving (user confirmed "keep that in mind").
- 16–27 credits inclusive. Tiers configurable, default one tier.
- Window 2026-10-19 09:00 to 2026-10-25 23:59 IST, one round, add/drop capped at 1.
- **Wording rule:** never "lottery", "random draw" or "luck" anywhere (UI, docs,
  identifiers); say "equal-priority order" / "fair tie-break". Enforced by
  `test_api::test_wording_rule_holds_across_the_code_base` (scans app/fca, app/config,
  app/web/src, docs/*.md except this file, README).

## Architecture (details in docs/ARCHITECTURE.md)

| Path | Purpose |
|---|---|
| `app/fca/timetable.py` | slot -> cells; 5-minute bit mask; clash = mask AND |
| `app/fca/importer.py` | Annexure PDFs -> `app/data/catalogue.json` + parse report |
| `app/fca/catalogue.py` | `Catalogue.load()`; offering id `CODE|TYPE|SLOT` |
| `app/fca/solver.py` | `solve(...)` exact pass (120k nodes) then spread pass (4000); `feasible()` |
| `app/fca/archetypes.py` + `app/config/archetypes.json` | features, 9 archetypes, secondary score |
| `app/fca/diagnostics.py` | minimal conflict + ranked single-change relaxations |
| `app/fca/allocation.py` | order (tier, earlier-miss, SHA-256 seed), `Allocator.place`, fairness report, `simulate` |
| `app/fca/service.py` | solver LRU cache, student ranked order, preview JSON |
| `app/fca/server.py` | FastAPI app, invite-code sign-in, sessions, CSRF, student routes |
| `app/fca/admin.py` | admin routes, allocate, result, add/drop, exports, backups (imported at end of server.py) |
| `app/fca/db.py`, `seed.py` | SQLite schema/settings; tester import, invite codes, `--reset` |
| `app/web/src/` | React: `Student.jsx`, `Admin.jsx`, `Timetable.jsx`, `api.js` |
| `var/` (ignored) | `fca.db`, `invite_codes.csv`, `backups/`; overridden by `FCA_DATA_DIR` |

## Commands

- Tests: `.venv/Scripts/python -m pytest -q` (103 pass, ~16 s)
- E2E: `.venv/Scripts/python -m pytest tests/e2e -q` (needs `npm run build` in `app/web`)
- Load: `.venv/Scripts/python tests/load/load_test.py 20` (rewrites docs/LOAD_TEST.md)
- Run: `docker compose up -d --build`; tunnel: `docker compose --profile tunnel up -d`
- Seed / reset: `docker compose run --rm app python -m fca.seed [--reset]`
- Local dev server: `cd app && ../.venv/Scripts/python -m uvicorn fca.server:app --port 8000`

## Last Completed

- M1 import + clash model; M2 solver + pins; M3 archetypes + diagnostics.
- Backend API, allocation, admin, add/drop, exports, backups.
- Student and admin screens; Playwright smoke test with screenshots in `docs/screenshots/`.
- Dockerfile, compose with optional tunnel, `.env.example`; container built and verified;
  tunnel verified once (HTTPS sign-in worked) then stopped.
- Docs: ARCHITECTURE, API, TEST_CASES, ADMIN_RUNBOOK, TESTER_GUIDE, KNOWN_LIMITS,
  LOAD_TEST, FUTURE_WORK, README, MORNING_CHECKLIST.

## Currently Working On

Nothing. Waiting for the user's morning review.

## Next Task

Act on the user's feedback from `docs/MORNING_CHECKLIST.md`: likely real tester list,
tier policy, UI fixes after they try it on a phone, then merge `beta-build`.

## Known Issues

- Lab-heavy requests report "at least M"; pattern counts are then counts of the sample.
- Touch drag-reorder untested on a real phone (arrow buttons are tested).
- Admin PDF upload not exercised through the browser.
- Local `.env` holds a generated `ADMIN_SECRET` (not committed). Value is not recorded here.
- User's email is the privacy contact in `app/config/defaults.json` and TESTER_GUIDE.md.
- Heredocs with many quotes fail in the Bash tool on this machine; use Write/Edit or a
  python script instead.

## Tests Last Run

2026-10-13: 103 unit/property/API passed; 1 e2e passed; load test 20 users, 0 failures.

## Blockers

None.
