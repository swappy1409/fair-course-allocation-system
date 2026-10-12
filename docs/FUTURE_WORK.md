# Future work

None of this is part of the beta. It is what a real rollout would need.

## Real data and identity

- **Authentication against the student database** (university single sign-on) instead of
  invite codes, with roles for students, the academic office and administrators.
- **The real curriculum**: required courses per program and semester, real backlog lists,
  prerequisites, official credits and the real four baskets with their credit rules.
- **Real capacities** per section, from the timetabling office.
- **Faculty and room data**: section identifiers, faculty per section, rooms and room
  sizes, so students can pin or avoid a faculty and capacity follows the room.
- **Theory–lab pairing rules** as the university actually applies them.

## Allocation

- **Multiple rounds** with a proper add/drop cycle between them, waiting lists, and
  automatic filling of seats that are released.
- **Priority tiers from policy**: final-year students, backlog status, programme rules, and
  an audit record of the tier assigned to each student.
- **A global assignment** (for example a matching or integer-programming formulation)
  to compare with the current greedy pass on first-choice share and spread.
- **Published verification**: a page where any student can recompute the equal-priority
  order from the seed.
- Fairness reporting broken down by programme, year and backlog status, across semesters.

## Solver

- An exact count for large requests (counting without listing), so "at least M" becomes a number.
- Letting the solver choose among shortlisted electives, not only among slots.
- Diagnostics that propose two-step fixes and explain every conflict, not just one.
- Student-defined patterns (for example "no class before 10", "Saturday free").

## Scale and operations

- Several worker processes behind a proper web server, a shared cache, and PostgreSQL in
  place of SQLite. The load test covers 20 simultaneous users, not a registration day.
- Hosting on a university server with a fixed address, monitoring, off-machine backups and
  a tested restore.
- Email or SMS notifications for window opening, results and add/drop.
- An audit log of admin actions and per-person admin accounts.

## Product

- Accessibility audit and fixes (screen readers, contrast, touch targets on small phones).
- Localisation.
- A comparison view: what a student would have got under first-come-first-served.
- A larger, properly sampled usability study with a control group on the current system.
