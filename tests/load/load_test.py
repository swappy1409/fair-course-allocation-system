"""Simple load test: N simulated students register at the same moment.

    python tests/load/load_test.py [users=20]

Starts its own server on a throwaway database (never the beta one), creates N testers,
runs each through sign-in -> my courses -> course list -> 5-6 live previews -> submit, all
concurrently, and writes the numbers to docs/LOAD_TEST.md.
"""
import csv
import os
import platform
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
USERS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
# Each user gets a different mix so the solver cache cannot answer everything.
ELECTIVE_SETS = [["FRL1001", "MGT1040", "HUM3109"], ["FRL1004", "MGT1040", "LAW2104"], ["CSE3009", "FRL1001"],
                 ["CSE4047", "MGT1040"], ["ECE2001", "FRL1005"], ["CSE3002", "HUM3109"], ["CSE2025", "MGT3001", "FRL1001"]]


def user(url, code, n, timings, failures):
    try:
        with httpx.Client(base_url=url, timeout=60) as c:
            def call(name, method, path, **kw):
                t0 = time.perf_counter()
                r = c.request(method, path, **kw)
                timings.setdefault(name, []).append((time.perf_counter() - t0) * 1000)
                if r.status_code >= 400:
                    failures.append(f"{name}: {r.status_code} {r.text[:120]}")
                return r
            r = call("sign in", "POST", "/api/login", json={"code": code}, headers={"x-csrf-token": "login"})
            c.headers["x-csrf-token"] = r.json()["csrf"]
            call("my courses", "GET", "/api/me")
            call("course list", "GET", "/api/courses")
            electives = ELECTIVE_SETS[n % len(ELECTIVE_SETS)]
            body = {"electives": [], "pins": [], "ranking": [], "never": []}
            for e in electives:                         # the live count as each elective is ticked
                body["electives"] = body["electives"] + [e]
                call("preview (live count)", "POST", "/api/preview", json=body)
            for extra in (["MGT1109"], ["MGT1117"], []):
                call("preview (live count)", "POST", "/api/preview", json={**body, "electives": electives + extra})
            call("submit", "POST", "/api/submit", json=body)
    except Exception as e:      # count it, keep the other users going
        failures.append(f"exception: {type(e).__name__}: {e}")


def main():
    data = tempfile.mkdtemp(prefix="fca-load-")
    env = {**os.environ, "FCA_DATA_DIR": data, "ADMIN_SECRET": "load-test-secret-123"}
    testers = Path(data) / "testers.csv"
    with open(testers, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["synthetic", "alias", "program", "year", "semester", "tier"])
        for i in range(USERS):
            w.writerow(["SYNTHETIC", f"load{i:02d}", "B.Tech CSE", 4, 7, "All students"])
    py = lambda *a: subprocess.run([sys.executable, *a], cwd=ROOT / "app", env=env, check=True, capture_output=True)
    py("-m", "fca.seed", str(testers))
    py("-c", "from fca import db\nwith db.connect() as c: db.set_settings(c, {'window_override': 'open'})")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "fca.server:app", "--port", str(port)],
                              cwd=ROOT / "app", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/health", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        with open(Path(data) / "invite_codes.csv", encoding="utf-8") as f:
            codes = [r["invite_code"] for r in csv.DictReader(f)]
        timings, failures = {}, []
        threads = [threading.Thread(target=user, args=(url, code, n, timings, failures)) for n, code in enumerate(codes)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wall = time.perf_counter() - t0
    finally:
        server.terminate()

    total = sum(len(v) for v in timings.values())
    pct = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(len(xs) * p))]
    lines = [
        "# Load test",
        "",
        f"Last run: {date.today().isoformat()}, by `python tests/load/load_test.py {USERS}`.",
        "",
        f"**{USERS} simulated students registering at the same moment** against one server process "
        "(the same single-worker setup as the Docker container), on a throwaway database.",
        "Each student signs in, loads their courses and the course list, triggers 5 or 6 live "
        "combination counts while choosing electives, and submits.",
        "",
        "| Step | Requests | Median ms | 95th percentile ms | Slowest ms |",
        "|---|---|---|---|---|",
    ]
    for name, xs in timings.items():
        lines.append(f"| {name} | {len(xs)} | {statistics.median(xs):.0f} | {pct(xs, 0.95):.0f} | {max(xs):.0f} |")
    lines += [
        "",
        f"- Requests: {total}, failed: {len(failures)}",
        f"- Wall-clock time for all {USERS} students: {wall:.1f} s ({total / wall:.0f} requests per second)",
        f"- Machine: {platform.system()} {platform.release()}, Python {platform.python_version()}, "
        f"{os.cpu_count()} logical CPUs",
        "",
        "## Reading the numbers",
        "",
        "- The live count is the expensive call: it runs the solver. Alone it takes well under a second; "
        "with 20 students pressing at the same instant the requests queue behind each other in one Python "
        "process, which is where the higher 95th percentile comes from.",
        "- Real testers do not all click in the same second, so this is a worst case for 20 users.",
        "- Identical requests are answered from an in-memory cache, so repeated counts are near-instant.",
        "- The limit to expect: this single process is comfortable for a class-sized beta. A real rollout "
        "would need several worker processes and a shared cache (see FUTURE_WORK.md).",
    ]
    if failures:
        lines += ["", "## Failures", ""] + [f"- {f}" for f in failures[:20]]
    (ROOT / "docs" / "LOAD_TEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
