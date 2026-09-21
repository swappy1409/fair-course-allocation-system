# Preference-Based Course Registration — Prototype

A lab-project prototype replacing first-come-first-served FFCS slot booking with
ranked-preference registration: students pick courses ahead of time, the system
generates every conflict-free timetable, groups the results into simple patterns
(Morning-heavy / Evening-heavy / Compact / Mixed), and lets the student rank by
pattern instead of comparing dozens of raw combinations by hand.

## Project structure

```
prototype/index.html     interactive demo (single file, no build step, no internet needed)
docs/generate_slides.py  builds the presentation deck
docs/output.pptx         generated deck (regenerate any time, see below)
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

## Regenerating the slide deck

The deck is built with `python-pptx`. From the `docs/` folder:

```
python generate_slides.py
```

This overwrites `docs/output.pptx`. If `python-pptx` isn't installed:

```
pip install python-pptx
```

## Presenter script (what to say)

"Right now, registration is a race — whoever clicks fastest gets the timetable,
even if it's not actually the best fit for them. Our prototype flips that: a
student picks the courses they want ahead of time, and instead of making them
manually compare dozens of possible timetables, we generate every conflict-free
combination against the fixed slot grid ourselves, tag each one with a simple
pattern — morning-heavy, evening-heavy, compact, or mixed — and let the student
rank by the pattern they'd actually prefer, with the option to pin one course to
a specific slot if they need to. If their choices genuinely can't be scheduled
together, we don't just show an empty list — we tell them exactly which two
courses are clashing so they know what to change. What you're about to see is
the interactive prototype with pre-loaded example scenarios, including one that
deliberately has no valid solution, so you can see how the conflict messaging
works."

## Notes

- Mock data only — no real database, no auth, no live course catalogue.
- Credit-range validation (16–27 credits) and the rest of the edge cases on the
  "Test cases and edge cases identified" slide are scoped for the next phase's
  automated test suite, not implemented in tonight's interactive prototype.
