# Morning checklist (written 2026-10-13, end of the overnight build)

Everything is committed on branch `beta-build`. All six milestones are built. 103 unit,
property and API tests pass, plus the browser smoke test and the 20-user load test.

## 1. Get it running again (2 minutes)

1. Start Docker Desktop. The app container restarts by itself.
2. Open http://localhost:8000 — you should see the sign-in page.
3. Invite codes for the 15 synthetic testers: `var/invite_codes.csv`.
4. Admin area: http://localhost:8000/#/admin. The secret is the `ADMIN_SECRET` line in
   `.env` (I generated a random one; change it if you like, then `docker compose up -d`).
5. If the container is not there: `docker compose up -d --build`.

## 2. Check these yourself (I could not)

- [ ] **Walk the student flow on your own phone.** Start the tunnel
      (`docker compose --profile tunnel up -d`, then `docker compose logs tunnel` for the
      address). I confirmed the tunnel serves the app over HTTPS and sign-in works through
      it, but only from this laptop.
- [ ] **Drag to reorder with a finger** on the ranking step. The arrow buttons are tested;
      touch dragging is not.
- [ ] **College Wi-Fi**: does the tunnel address open on it? If not, see the fallback in
      ADMIN_RUNBOOK.md section 3.
- [ ] **Read the screenshots** in `docs/screenshots/` (10 images of the whole flow) and tell
      me what looks wrong. This replaces the M4 demo stop, which I skipped as you asked.
- [ ] **Try the admin area**: Overview, a dry run, the simulation (200 students takes up to
      a minute), the exports.
- [ ] **Do the three scenarios in TESTER_GUIDE.md** as a tester would.

## 3. Decisions I made without you — confirm or change

| Decision | Where to change it |
|---|---|
| Synthetic curriculum: 3 required courses each for semesters 3, 5 and 7 of "B.Tech CSE" | `app/data/synthetic_curriculum.csv` |
| 15 synthetic testers, four with one backlog course | `app/data/synthetic_testers.csv`, or upload your own in Admin → Testers |
| Beta-scale seats are ON (2 per section) so slots fill | Admin → Settings |
| Nine timetable patterns and their thresholds | `app/config/archetypes.json` |
| "Top three" preview shows the best timetable of each of the student's top three patterns, not three near-identical timetables | `app/fca/service.py` `preview` |
| Failed sign-ins are limited per network (20 in 10 minutes); successful ones are not counted, because a class on one Wi-Fi shares an address | `app/fca/server.py` |
| Add/drop is first come, first served for the seats left, one change each | Admin → Settings for the cap |
| A final run is refused while the window is open | `app/fca/admin.py` `allocate` |
| Your VIT-AP email is the privacy contact, and is in `app/config/defaults.json` and `docs/TESTER_GUIDE.md`, which are committed | those two files |
| Added dependencies: `@dnd-kit` (dragging), Playwright (browser test), pdfplumber | `app/web/package.json`, `requirements*.txt` |
| Work is on branch `beta-build`, not merged into `master`, not pushed | `git merge beta-build` when you are happy |

## 4. Before you invite real testers (target Mon Oct 19)

- [ ] Replace the synthetic testers with your real list of aliases (Admin → Testers), or
      keep the synthetic profiles and just hand out the codes.
- [ ] Decide the priority tiers (default: one tier).
- [ ] Reset so the beta starts clean: `docker compose run --rm app python -m fca.seed --reset`
      (new invite codes are generated each time).
- [ ] Check the window dates in Admin → Settings (19 Oct 09:00 to 25 Oct 23:59 IST).
- [ ] Send each tester: the tunnel address, one invite code, and TESTER_GUIDE.md.
- [ ] Keep the laptop awake and plugged in while the window is open.

## 5. What is not done

- No connection to the real student database or login; invite codes only.
- Credits are derived; baskets, capacities, curriculum and testers are synthetic.
- The 7 project (PJT) courses cannot be selected because they have no credit value.
- Large requests (4–5 lab courses) show "at least M" combinations; the true total is not computed.
- No multi-round add/drop, waiting list or notifications.
- Not tested: touch dragging on a real phone, screen readers, the PDF upload through the
  admin page in a browser (the importer behind it is tested).
- No per-basket credit rules.

Full list: KNOWN_LIMITS.md. What a real rollout would add: FUTURE_WORK.md.
