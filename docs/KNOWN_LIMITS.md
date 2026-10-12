# Known limits

This is a beta prototype for a lab project. What it does not do, stated plainly.

## Not connected to anything real

- **No connection to the university student database or login.** Testers sign in with an
  invite code. Nothing here registers anyone for a real course.
- **No real student data.** Testers are aliases. The curriculum (which courses are
  required in which semester) is synthetic.

## Data that is not from the Annexures

| Data | What the prototype uses | Effect |
|---|---|---|
| Credits | Derived from the slot pattern (Annexure I credit table) plus 1 per two lab blocks | May differ from the official credit value of a course |
| Baskets | A rule on the course code (CSE/SWE level 1–2 = Program Core, level 3–4 = Program Elective; MAT, PHY, CHY, ENG, STS, ECS, CAP = University Core; the rest = University Elective) | Does not match the real curriculum; no per-basket credit rules are enforced |
| Seat capacity | Sections × a configurable number (2 at beta scale, 60 otherwise) | Which slots fill, and so who gets which pattern, is not realistic |
| Sections | A repeated row in Annexure II is treated as a parallel section | An assumption; the PDF has no section or faculty column |
| Theory–lab pairing | Any theory offering with any lab offering of the same course | The real system may tie a lab batch to a theory section |
| Project courses (7) | No credits could be derived, so they cannot be selected | CAP4001, ECS2003, ECS3001, LAW5116, MGT1119, MGT1121, MGT1123 |

## Combination generation

- **Large requests are sampled, not fully listed.** With four or five lab courses there are
  far more combinations than can be enumerated. The solver then keeps 4,000 spread evenly
  across every slot option and reports "at least M". The true total is not computed.
- **Pattern counts are counts of that sample** in those cases, not of the full space. A
  rare pattern can be missing from the list even though a timetable of that kind exists.
- **The course set is fixed before solving.** The student chooses electives; the solver
  chooses slots. It does not decide which elective to drop to make things fit, though the
  diagnostics suggest single swaps and drops.
- **Diagnostics give one minimal conflict**, not every conflict, and only single-change
  fixes. If two changes are needed it says no single change works.
- Swap suggestions look only at the first 40 courses (alphabetically) in the same basket
  with the same credits.

## Allocation

- **One round plus a capped add/drop window.** Further rounds can be run by hand and do
  move up students who missed out, but there is no multi-round add/drop, no waiting list
  and no automatic re-run when a seat frees up.
- **Add/drop is first come, first served** for the seats left after allocation, capped at
  one change per student by default.
- Allocation is greedy in the published order. It does not search for the assignment that
  is best for everyone overall, so a different order could give a better total.
- A student who had not submitted when the final run happened is not allocated; they can
  only use add/drop.
- "Choice number" counts only the patterns that exist for that student's courses.

## Beta instrumentation

- Completion time is measured from the first step to the **first** submission. It includes
  time the tester spent away from the phone. It is not directly comparable with the 25.7
  minute survey figure, which was self-reported for a different system.
- 10 to 20 testers is too few for the SUS mean to be more than indicative.
- The simulation uses generated students with arbitrary preferences. It shows how the
  mechanism behaves, not how real students would choose.

## Operations and security

- Runs as one process on one laptop. If the laptop sleeps or the tunnel restarts, testers
  are cut off, and the public address changes.
- Sign-in attempt counting and the solver cache are in memory and reset on restart.
- An invite code is a bearer secret: anyone who has it can act as that tester.
- No email or notifications; codes and addresses are sent by hand.
- Admin access is a single shared secret with no audit trail of admin actions.
- Backups stay on the same laptop.
- Not audited for accessibility or security. Keyboard use, labels and visible focus are in
  place; screen-reader behaviour and touch dragging on real phones were not tested.

## Not tested

Listed at the end of TEST_CASES.md.
