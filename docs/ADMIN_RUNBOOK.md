# Admin runbook

Commands are run in the project folder. The admin area is at `<address>/#/admin`.

## 1. Start

```
copy .env.example .env        (first time only; set ADMIN_SECRET to 12+ characters)
docker compose up -d --build
```

The app is at http://localhost:8000. Your data lives in `var/` (database, invite codes,
backups), outside the container.

## 2. Create testers and get invite codes

Either load the 15 synthetic testers:

```
docker compose run --rm app python -m fca.seed
```

or, in the admin area, **Testers → Add or update testers**, paste or choose your CSV:

```
alias,program,year,semester,tier,required_courses,backlog_courses
riya,B.Tech CSE,3,5,All students,,MAT1003
```

- Use aliases, not registration numbers (they are refused).
- Leave `required_courses` empty to use `app/data/synthetic_curriculum.csv` for that
  program and semester.
- Invite codes are shown **once**. Copy them straight away. The seed command also writes
  them to `var/invite_codes.csv`. Lost a code: **Testers → New code**.

## 3. Get a public address for phones

```
docker compose --profile tunnel up -d
docker compose logs tunnel
```

Look for a line with `https://….trycloudflare.com`. Send that address and one invite code
to each tester. No account or payment is needed.

- The laptop must stay on and awake while testers use it.
- The address changes if the tunnel restarts. Send the new one if that happens.
- If the college network blocks the tunnel, use the laptop's address on the Wi-Fi instead
  (`http://<laptop-ip>:8000`), which works but without HTTPS.

## 4. Open the window

**Overview** shows the window state. It follows the schedule in **Settings**
(default 19 Oct 09:00 to 25 Oct 23:59 IST). To open or close it by hand use
**Open now / Close now**; **Follow the schedule** removes the override.

## 5. Before testers start: settings worth checking

| Setting | Why |
|---|---|
| Priority tiers | One per line, highest first. Default is one tier. Set each tester's tier under **Testers**. |
| Use the beta-scale seats | On by default: 2 seats per section, so slots actually fill with 15 testers. Turn off for 60 per section. |
| Published seed | Decides the equal-priority order. Tell testers what it is; do not change it after they submit. |
| Weight for moving up | How strongly students who missed their top pattern in an earlier round are moved up. 0 turns it off. |
| Capacity | **Capacity** tab: type a course code to override seats for single course-slots. |

## 6. During the beta

- **Overview**: testers, submissions, median time to submit against the 25.7-minute survey
  baseline, mean SUS score.
- **Logs**: per-tester time and steps reached; every "no timetable" explanation and error.
- **Allocation → Dry run** any time to see what would happen. It saves nothing.

## 7. Allocate

1. **Overview → Close now** (or wait for the schedule).
2. **Allocation → Dry run**, read the fairness report.
3. **Allocation → Final run**. Testers now see their result and can make one add/drop change.

A second round: set **Round** to 2 and run again. Students who missed their top pattern in
round 1 are moved up. The latest final run is what testers see.

## 8. Collect the data

**Exports**: `results.csv`, `feedback.csv` (with SUS scores), `timing.csv`, `events.csv`.

## 9. Simulation for the lab demo

**Allocation → Simulation**: for example 200 students, 3 seats per section, 2 rounds.
Everything it shows is synthetic and nothing is saved.

## 10. Re-import course data

**Data**: upload both Annexure PDFs, read the parse report, then **Confirm**. Nothing
changes until you confirm. Do this before testers submit, not after.

## 11. Back up, reset, stop

| Task | How |
|---|---|
| Back up now | **Reset → Back up now**, or copy `var/fca.db`. A backup is also taken daily into `var/backups/` (14 kept). |
| Reset the beta | **Reset** tab, type RESET; or `docker compose run --rm app python -m fca.seed --reset` (this also reloads the synthetic testers). Settings and course data are kept. |
| Restore a backup | `docker compose down`, copy a file from `var/backups/` over `var/fca.db`, delete `var/fca.db-wal` and `var/fca.db-shm` if present, `docker compose up -d`. |
| Stop | `docker compose --profile tunnel down` |
| Logs | `docker compose logs app` |

## Without Docker

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd app\web && npm install && npm run build && cd ..\..
set ADMIN_SECRET=your-long-secret
cd app && ..\.venv\Scripts\python -m fca.seed && ..\.venv\Scripts\python -m uvicorn fca.server:app --port 8000
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "Admin access is disabled" | `ADMIN_SECRET` missing or under 12 characters in `.env`; fix it and `docker compose up -d`. |
| Tester: "invite code is not recognised" | Typo (codes have no 0, 1, O, I or L), or the beta was reset. Issue a new code. |
| Tester: "Too many failed attempts from this network" | 20 wrong codes from one network in 10 minutes. Wait, or restart the app. |
| "Close the registration window before a final run" | Use **Close now** first. |
| Tester sees "Security check failed" | Stale page; reload. |
| Nothing at the tunnel address | Check `docker compose logs tunnel`; the address may have changed. |
