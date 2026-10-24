"""Check public request sharing, hidden tabs, world isolation and real trades.
Build with VITE_PRIVY_APP_ID= first. Uses only a temporary local SQLite database.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8024"
HARNESS = """
from collections import Counter
import uvicorn
from server import app
counts=Counter()
@app.middleware("http")
async def count_requests(request,call_next):
    if request.url.path.startswith('/api/'):
        counts[request.headers.get('x-norx-world','balanced')+':'+request.url.path] += 1
    return await call_next(request)
@app.get('/test/counts')
def metrics():return dict(counts)
app.router.routes.insert(0, app.router.routes.pop())
uvicorn.run(app,host='127.0.0.1',port=8024,log_level='error')
"""


def hidden(page, value):
    page.evaluate(
        """value => {
      window.testHidden = value;
      Object.defineProperty(document, 'hidden', {configurable:true,get:()=>window.testHidden});
      document.dispatchEvent(new Event('visibilitychange'));
    }""",
        value,
    )


with tempfile.TemporaryDirectory() as folder:
    env = {
        **os.environ,
        "NORX_DB": str(Path(folder) / "world.sqlite3"),
        "NORX_DEV_AUTH": "1",
        "NORX_AUTO_WORKER": "0",
    }
    env.pop("DATABASE_URL", None)
    with open(Path(folder) / "server.log", "w") as log:
        server = subprocess.Popen(
            [sys.executable, "-c", HARNESS], cwd=ROOT, env=env, stdout=log, stderr=log
        )
        try:
            for _ in range(100):
                try:
                    if httpx.get(BASE + "/api/config", timeout=1).is_success:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Smoke backend did not start")

            def counts():
                return httpx.get(BASE + "/test/counts").json()

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path="/usr/bin/chromium", args=["--no-sandbox"]
                )
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                a = context.new_page()
                b = context.new_page()
                errors = []
                for page in [a, b]:
                    page.on("pageerror", lambda error: errors.append(str(error)))
                a.goto(BASE + "/market.html#pulse")
                a.get_by_role("button", name="Enter local test account").first.click()
                expect(a.locator(".exchange-header")).to_contain_text("$10,000.00")
                expect(a.locator(".exchange-footer")).to_contain_text(
                    "3 markets", timeout=15000
                )
                b.goto(BASE + "/market.html#pulse")
                b.get_by_role("button", name="Enter local test account").first.click()
                expect(b.locator(".exchange-header")).to_contain_text("$10,000.00")
                expect(b.locator(".exchange-footer")).to_contain_text(
                    "3 markets", timeout=15000
                )
                assert counts().get("balanced:/api/state", 0) == 1, counts()
                assert counts()["balanced:/api/me"] == 2, counts()
                a.wait_for_timeout(10500)
                assert counts()["balanced:/api/state"] == 2, counts()
                assert counts()["balanced:/api/me"] == 2, counts()
                for page in [a, b]:
                    hidden(page, True)
                    page.clock.install()
                    page.clock.fast_forward(70000)
                a.wait_for_timeout(200)
                sleeping = counts()
                a.clock.fast_forward(70000)
                b.clock.fast_forward(70000)
                a.wait_for_timeout(200)
                assert counts() == sleeping, (sleeping, counts())
                hidden(a, False)
                expect(a.locator(".exchange-header")).to_contain_text("$10,000.00")
                a.wait_for_timeout(200)
                assert counts()["balanced:/api/me"] == 3, counts()
                hidden(b, False)
                b.get_by_role("button", name="Economy: Balanced").click()
                b.get_by_role("button", name="Bull run", exact=False).click()
                b.get_by_role("button", name="Economy: Bull run").wait_for()
                expect(b.locator(".exchange-header")).to_contain_text("$10,000.00")
                # Changing localStorage in B must not switch A's API world.
                previous = counts().get("balanced:/api/me", 0)
                a.evaluate(
                    "window.dispatchEvent(new CustomEvent('norx:portfolio-refresh',{detail:{world:'balanced'}}))"
                )
                a.wait_for_timeout(200)
                assert counts()["balanced:/api/me"] == previous + 1, counts()
                a.goto(BASE + "/market.html#coin/frog")
                a.get_by_role("heading", name="Trade token", exact=True).wait_for()
                # Hash navigation keeps A's world, despite B's stored preference.
                a.get_by_role("button", name="Economy: Balanced").wait_for()
                a.locator("#amount").fill("50")
                a.get_by_role("button", name="Preview buy", exact=True).click()
                a.get_by_role("button", name="Confirm buy", exact=True).click()
                try:
                    a.get_by_role("status").filter(has_text="Bought").wait_for(
                        timeout=10000
                    )
                except Exception:
                    print(
                        "Trade diagnostic:",
                        a.get_by_role("alert").all_text_contents(),
                        counts(),
                        errors,
                    )
                    raise
                account = httpx.get(
                    BASE + "/api/me",
                    headers={
                        "Authorization": "Bearer local-demo",
                        "X-Norx-World": "balanced",
                    },
                ).json()
                assert 9949.99 <= account["cash"] <= 9950.01, account["cash"]
                assert account["holdings"].get("frog", 0) > 0
                assert counts()["balanced:/api/trade"] == 1, counts()
                assert not errors, errors
                print(
                    "PASS: two tabs share public requests; private accounts stay separate; 10s polling; hidden tabs stop; focus refreshes; worlds stay isolated; buy updates immediately"
                )
                fallback_context = browser.new_context()
                fallback_context.add_init_script("window.SharedWorker = undefined")
                fallback_page = fallback_context.new_page()
                fallback_page.goto(BASE + "/market.html#pulse")
                expect(fallback_page.locator(".exchange-footer")).to_contain_text(
                    "3 markets"
                )
                print(
                    "PASS: browsers without SharedWorker load via the per-tab fallback"
                )
                fallback_context.close()
                browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=25)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
