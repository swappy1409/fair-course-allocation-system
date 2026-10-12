# Preference-based course and slot allocation — beta prototype

A lab-project prototype for the School of Computer Science, VIT-AP, that replaces
first-come-first-served slot booking. A student picks electives, optionally pins a course
to a slot, and ranks timetable *patterns* (morning-heavy, four-day week, …) instead of
racing for slots. The system generates the conflict-free timetables, explains impossible
requests, and allocates seats in a published, reproducible order.

It is a beta for 10 to 20 testers. It is not connected to any university system; see
[docs/KNOWN_LIMITS.md](docs/KNOWN_LIMITS.md).

## Run it

Needs Docker Desktop.

```
copy .env.example .env                               # then set ADMIN_SECRET (12+ characters)
docker compose up -d --build                         # app at http://localhost:8000
docker compose run --rm app python -m fca.seed       # 15 synthetic testers; prints invite codes
```

- Student flow: http://localhost:8000
- Admin area: http://localhost:8000/#/admin (sign in with `ADMIN_SECRET`)
- Invite codes are also saved in `var/invite_codes.csv`.

## Deploy for phones (free, no account)

```
docker compose --profile tunnel up -d
docker compose logs tunnel          # look for https://….trycloudflare.com
```

Send testers that address and their invite code. The laptop must stay on, and the address
changes if the tunnel restarts. Details and the fallback are in
[docs/ADMIN_RUNBOOK.md](docs/ADMIN_RUNBOOK.md).

## Reset the beta

```
docker compose run --rm app python -m fca.seed --reset
```

Wipes testers, choices, runs, logs, feedback and capacity overrides, then reloads the
synthetic testers with new invite codes. Settings and course data are kept. The admin
area's **Reset** tab does the same wipe and takes a backup first.

## Layout

```
app/fca/        backend: importer, clash model, solver, archetypes, diagnostics, allocation, API
app/config/     defaults.json (settings), archetypes.json (patterns and score weights)
app/data/       catalogue.json (parsed Annexures), synthetic curriculum and testers
app/web/        React frontend (student flow and admin area)
tests/unit/     unit, property-based and API tests
tests/e2e/      Playwright smoke test of the student flow on a phone-sized screen
tests/load/     20-user load test
docs/           architecture, API, test cases, runbook, tester guide, limits, load test, future work
prototype/      the earlier single-file demo, kept for reference
```

## Develop and test

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
cd app\web && npm install && npm run build && cd ..\..

.venv\Scripts\python -m pytest -q                    # unit, property and API tests
.venv\Scripts\python -m playwright install chromium  # once
.venv\Scripts\python -m pytest tests/e2e -q          # browser smoke test
.venv\Scripts\python tests/load/load_test.py 20      # writes docs/LOAD_TEST.md
```

Try the solver on its own:

```
cd app
..\.venv\Scripts\python -m fca.solver CSE1013 FRL1001 HUM3109 LAW2104 MAT1003 MGT1040 --pin FRL1001:TH:G1
```

Re-import the Annexure PDFs (they are not committed; put them in `inputs/`):

```
cd app
..\.venv\Scripts\python -m fca.importer "..\inputs\<Annexure I>.pdf" "..\inputs\<Annexure II>.pdf" data\catalogue.json
```

## What is real and what is synthetic

Slots, clock times, courses and slot combinations come from the two Annexure PDFs.
Credits are derived; baskets, seat capacities, the curriculum and the testers are
synthetic and labelled so in the data and the UI. No real student identifiers are in this
repository.

## Documents

| Document | For |
|---|---|
| [docs/TESTER_GUIDE.md](docs/TESTER_GUIDE.md) | testers: three scenarios to try |
| [docs/ADMIN_RUNBOOK.md](docs/ADMIN_RUNBOOK.md) | running the beta day to day |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | how it works |
| [docs/API.md](docs/API.md) | the HTTP API |
| [docs/TEST_CASES.md](docs/TEST_CASES.md) | edge cases and their status |
| [docs/LOAD_TEST.md](docs/LOAD_TEST.md) | 20-user load test result |
| [docs/KNOWN_LIMITS.md](docs/KNOWN_LIMITS.md) | what it does not do |
| [docs/FUTURE_WORK.md](docs/FUTURE_WORK.md) | what a real rollout would add |
