# API

All routes are under `/api`. Bodies and replies are JSON unless noted. Interactive
reference: `/api/docs` on a running server.

**Sessions.** Sign-in sets an HttpOnly cookie and returns a `csrf` token. Every request
that is not a GET must send `X-CSRF-Token: <token>` (for the two sign-in routes any
non-empty value). Errors are `{"detail": "plain-language message"}`.

| Status | Meaning |
|---|---|
| 401 | not signed in, or bad/expired invite code |
| 403 | missing or wrong CSRF token, or wrong role |
| 409 | not allowed right now (window closed, no timetable, add/drop used, …) |
| 422 | invalid input |
| 429 | too many failed sign-ins from this network |

## Sign in

| Method | Path | Body | Reply |
|---|---|---|---|
| POST | `/api/login` | `{code}` | `{csrf, alias}` |
| POST | `/api/admin/login` | `{secret}` | `{csrf}` |
| POST | `/api/logout` | – | `{ok}` |
| GET | `/api/session` | – | `{csrf, admin, student}` (restores a session after reload) |
| GET | `/api/health` | – | `{ok}` |

## Student

The choice body used by several routes:

```json
{"electives": ["FRL1001"], "pins": ["FRL1001:TH:A1"], "ranking": ["morning_heavy"], "never": ["all_evening"]}
```

A pin is `COURSE:TYPE:SLOT`. `ranking` and `never` hold archetype ids.

| Method | Path | Body | Reply |
|---|---|---|---|
| GET | `/api/me` | – | profile, required and backlog courses, saved preferences, window, credit limits, archetypes, seed |
| GET | `/api/courses` | – | every course with credits: code, title, credits, basket, components with slots, `fixed` |
| POST | `/api/preview` | choice | `{credits, count, exact, summary, archetypes[{id,label,description,count}], top[...], diagnosis}` |
| PUT | `/api/preferences` | choice | saves a draft (window must be open) |
| POST | `/api/submit` | choice | `{ok, submission}`; repeat submissions replace the earlier one |
| POST | `/api/event` | `{type, detail}` | step log; type is one of `started, courses_chosen, pins_set, ranking_saved, error, viewed_result` |
| POST | `/api/feedback` | `{sus:[10 x 1..5], ease:1..5, confused, comments}` | `{ok}` |
| GET | `/api/result` | – | `{ready:false}` or status, explanation, position, choice_rank, timetable, seed, method, add_drop |
| POST | `/api/adddrop` | choice | seats the new choice from the seats left; 409 with a reason if it cannot |

`top` holds the best timetable of each of the student's top three patterns:
`{choice, archetype, label, score, features, classes[{course, title, type, slot, cells[[day,start,end]]}]}`.

`diagnosis` (only when `count` is 0):
`{summary, conflicts[], courses[], relaxations[{kind, message, unlocks, unlocks_text, electives, pins}]}`.
Sending a relaxation's `electives` and `pins` back as the new choice applies it.

## Admin (admin session required)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/overview` | settings, window state, counts, timing vs baseline, mean SUS, parse report, saved runs |
| PUT | `/api/admin/settings` | change any of: tiers, credit limits, seats, window dates and override, seed, weight, add/drop cap, privacy contact |
| GET | `/api/admin/testers` | list testers |
| POST | `/api/admin/testers/import` | `{csv}` → `{created, updated, problems, codes}`; codes are shown once |
| POST | `/api/admin/testers/{id}/code` | new invite code (old one stops working) |
| PUT | `/api/admin/testers/{id}/tier` | `{tier}` |
| DELETE | `/api/admin/testers/{id}` | remove a tester and their data |
| POST | `/api/admin/import` | multipart `timetable`, `courses` (PDF) → parse report; nothing applied yet |
| POST | `/api/admin/import/confirm` | make the uploaded data live |
| GET | `/api/admin/capacity?course=CSE2001` | seats per course-slot (no course: list overrides) |
| PUT | `/api/admin/capacity` | `{offering_id, seats}`; `seats: null` removes the override |
| POST | `/api/admin/allocate` | `{kind: "dry"|"final", round}` → assignments + fairness report; only final is saved |
| GET | `/api/admin/runs/{id}` | a saved final run |
| POST | `/api/admin/simulate` | `{students, seats_per_section, rounds}` → synthetic fairness report, nothing saved |
| GET | `/api/admin/diagnostics` | latest 200 diagnosis and error events |
| GET | `/api/admin/timing` | minutes from first step to first submission, per tester |
| GET | `/api/admin/export/{results|feedback|timing|events}.csv` | CSV downloads |
| POST | `/api/admin/backup` | back up the database now |
| POST | `/api/admin/reset` | `{confirm: "RESET"}` wipes beta data (backup taken first) |

## Fairness report fields

`students, placed, unplaced, first_choice, second_choice, third_choice, fourth_or_lower,
first_choice_share, mean_choice, choice_spread` (standard deviation of the choice number),
`worst_choice, mean_choice_first_quarter, mean_choice_last_quarter` (does going early
matter?), `by_tier, seats_used, course_slots_used, course_slots_full, capacity_exceeded`
(always 0), `seed, method, round, order[{position, alias, tier, priority}]`.
