# Load test

Last run: 2026-10-13, by `python tests/load/load_test.py 20`.

**20 simulated students registering at the same moment** against one server process (the same single-worker setup as the Docker container), on a throwaway database.
Each student signs in, loads their courses and the course list, triggers 5 or 6 live combination counts while choosing electives, and submits.

| Step | Requests | Median ms | 95th percentile ms | Slowest ms |
|---|---|---|---|---|
| sign in | 20 | 83 | 276 | 276 |
| my courses | 20 | 102 | 462 | 462 |
| course list | 20 | 101 | 519 | 519 |
| preview (live count) | 108 | 662 | 1163 | 1549 |
| submit | 20 | 126 | 850 | 850 |

- Requests: 188, failed: 0
- Wall-clock time for all 20 students: 4.0 s (47 requests per second)
- Machine: Windows 11, Python 3.14.6, 16 logical CPUs

## Reading the numbers

- The live count is the expensive call: it runs the solver. Alone it takes well under a second; with 20 students pressing at the same instant the requests queue behind each other in one Python process, which is where the higher 95th percentile comes from.
- Real testers do not all click in the same second, so this is a worst case for 20 users.
- Identical requests are answered from an in-memory cache, so repeated counts are near-instant.
- The limit to expect: this single process is comfortable for a class-sized beta. A real rollout would need several worker processes and a shared cache (see FUTURE_WORK.md).
