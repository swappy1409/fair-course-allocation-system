"""End-to-end smoke test on a phone-sized screen: sign in -> electives -> impossible pin ->
one-click fix -> ranking -> submit -> feedback -> admin final run -> result with explanation.

Run:  python -m pytest tests/e2e -q      (needs `npm run build` in app/web and
                                           `python -m playwright install chromium`)
Screenshots are written to docs/screenshots/.
"""
import csv
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "docs" / "screenshots"
ADMIN_SECRET = "e2e-admin-secret-123"


@pytest.fixture(scope="module")
def site():
    if not (ROOT / "app" / "web" / "dist" / "index.html").exists():
        pytest.skip("frontend not built: run `npm run build` in app/web")
    data = tempfile.mkdtemp(prefix="fca-e2e-")
    env = {**os.environ, "FCA_DATA_DIR": data, "ADMIN_SECRET": ADMIN_SECRET}
    run = lambda *args: subprocess.run([sys.executable, *args], cwd=ROOT / "app", env=env, check=True,
                                       capture_output=True, text=True)
    run("-m", "fca.seed")
    run("-c", "from fca import db\nwith db.connect() as c: db.set_settings(c, {'window_override': 'open'})")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "fca.server:app", "--port", str(port)],
                            cwd=ROOT / "app", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.2)
    with open(Path(data) / "invite_codes.csv", encoding="utf-8") as f:
        codes = {r["alias"]: r["invite_code"] for r in csv.DictReader(f)}
    yield url, codes
    proc.terminate()


def test_student_flow_on_a_phone(site):
    url, codes = site
    SHOTS.mkdir(parents=True, exist_ok=True)
    shot = lambda page, name: page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                                    has_touch=True)
        page = phone.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        # sign in: a wrong code is refused in plain words, the right one works
        page.goto(url)
        page.get_by_label("Invite code").fill("WRONG-CODE")
        page.get_by_role("button", name="Sign in").click()
        expect(page.get_by_role("alert")).to_contain_text("not recognised")
        page.get_by_label("Invite code").fill(codes["tester11"])
        shot(page, "01-sign-in")
        page.get_by_role("button", name="Sign in").click()

        # step 1: required courses are already there
        expect(page.get_by_role("heading", name="Your courses")).to_be_visible()
        expect(page.get_by_text("CSE4007")).to_be_visible()
        expect(page.get_by_text("Step 1 of 5")).to_be_visible()
        shot(page, "02-my-courses")
        page.get_by_role("button", name="Next").click()

        # step 2: electives by basket with a live credit count
        expect(page.get_by_text("10 credits")).to_be_visible()
        expect(page.get_by_role("button", name="Next")).to_be_disabled()
        page.get_by_role("tab", name="University Elective").click()
        for code in ("FRL1001", "MGT1040", "HUM3109", "LAW2104"):
            page.get_by_label("Search courses").fill(code)
            page.get_by_role("checkbox").first.check()
        page.get_by_label("Search courses").fill("")
        expect(page.get_by_text("21 credits")).to_be_visible()
        expect(page.get_by_text("available")).to_be_visible()
        shot(page, "03-electives")
        page.get_by_role("button", name="Next").click()

        # step 3: an impossible pin is explained and fixed with one click
        page.get_by_label("FRL1001 theory").select_option("G1")
        expect(page.get_by_text("FRL1001 pinned to G1 clashes with LAW2104")).to_be_visible()
        expect(page.get_by_text("No timetable possible")).to_be_visible()
        shot(page, "04-impossible-pin")
        page.get_by_role("button", name="Apply").first.click()
        expect(page.get_by_text("available")).to_be_visible()
        page.get_by_label("FRL1001 theory").select_option("A1")       # a pin that does work
        expect(page.get_by_text("available")).to_be_visible()
        page.get_by_role("button", name="Next").click()

        # step 4: rank patterns with the keyboard-friendly arrows
        expect(page.get_by_role("heading", name="Rank timetable patterns")).to_be_visible()
        first = page.locator(".rank li b").first.inner_text()
        page.locator(".rank li").first.get_by_role("button", name="down").click()
        expect(page.locator(".rank li b").nth(1)).to_have_text(first)
        shot(page, "05-ranking")
        page.get_by_role("button", name="Next").click()

        # step 5: timetable preview, then submit
        expect(page.get_by_text("1st choice:")).to_be_visible()
        expect(page.locator(".tt").first).to_be_visible()
        shot(page, "06-review")
        page.get_by_role("button", name="Submit").click()
        expect(page.get_by_role("heading", name="Submitted")).to_be_visible()

        # feedback form
        for i in range(11):
            page.locator(".likert").nth(i).locator("label").nth(3).click()
        page.get_by_label("What confused you?").fill("Nothing in this smoke test.")
        shot(page, "07-feedback")
        page.get_by_role("button", name="Send feedback").click()
        expect(page.get_by_text("your feedback is saved")).to_be_visible()

        # admin closes the window and runs the final allocation
        admin = browser.new_context(viewport={"width": 1100, "height": 900}).new_page()
        admin.goto(url + "/#/admin")
        admin.get_by_label("Admin secret").fill(ADMIN_SECRET)
        admin.get_by_role("button", name="Sign in").click()
        admin.get_by_role("button", name="Close now").click()
        expect(admin.get_by_role("heading", name="Registration window: closed")).to_be_visible()
        shot(admin, "08-admin-overview")
        admin.get_by_role("tab", name="Allocation").click()
        admin.once("dialog", lambda d: d.accept())
        admin.get_by_role("button", name="Final run").click()
        expect(admin.get_by_text("Fairness report")).to_be_visible()
        expect(admin.get_by_text("capacity exceeded (must be 0)")).to_be_visible()
        shot(admin, "09-admin-fairness")

        # the student sees a result with a reason
        page.reload()
        expect(page.get_by_text("You got your 1st-choice pattern")).to_be_visible()
        expect(page.get_by_text("How the order was decided")).to_be_visible()
        expect(page.get_by_role("button", name="Change my choices")).to_be_visible()
        shot(page, "10-result")
        assert errors == []
        browser.close()
