# Preference-Based Course Registration — Prototype

A lab-project prototype replacing first-come-first-served FFCS slot booking with
ranked-preference registration: students pick courses ahead of time, the system
generates every conflict-free timetable, groups the results into simple patterns
(Morning-heavy / Evening-heavy / Compact / Mixed), and lets the student rank by
pattern instead of comparing dozens of raw combinations by hand.

## Project structure

```
prototype/index.html     interactive demo (single file, no build step, no internet needed)
```

## Running the prototype

Just open [prototype/index.html](prototype/index.html) in any browser (double-click it, or
`File > Open`). No server, no install, no internet connection required — everything
(HTML/CSS/JS and the mock course catalogue) is inline in the one file.

Use the three **Load example** buttons instead of clicking through course selection
live:

1. **Balanced mix** — six courses, no pin, produces ~100 valid combinations across
   all four patterns.
2. **Pinned & tricky** — pins Data Structures and Algorithms to slot D1 and mixes
   in a soft slot overlap, narrowing (not zeroing) the result set.
3. **Impossible combo** — selects two core courses that are both only ever offered
   around slot D1, so the system reports zero valid timetables and names the exact
   conflicting pair instead of showing an empty list.


## Notes

- Mock data only — no real database, no auth, no live course catalogue.
- Credit-range validation (16–27 credits) and the rest of the edge cases on the
  "Test cases and edge cases identified" slide are scoped for the next phase's
  automated test suite, not implemented in tonight's interactive prototype.
