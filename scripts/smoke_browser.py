"""Exercise welcome, Pulse, real timed launches, charts, and saved USD trades.

Run against Vite and an API with NORX_DEV_AUTH=1 which starts the simulation automatically.
Requires Playwright. Set BROWSER_EXECUTABLE to use a system Chromium binary.
"""

import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

base = os.getenv("NORX_TEST_URL", "http://127.0.0.1:5173")
out = Path(os.getenv("NORX_SCREENSHOT_DIR", "/tmp"))
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    executable = os.getenv("BROWSER_EXECUTABLE")
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox"],
        **({"executable_path": executable} if executable else {}),
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base, wait_until="domcontentloaded")
    page.get_by_role("heading", name="Welcome to").wait_for()
    assert page.locator("#sky").count() == 1
    assert page.request.get(base + "/sky-bg.jpg").ok
    page.wait_for_timeout(1500)
    page.screenshot(path=str(out / "norx-welcome.png"))
    page.get_by_role("link", name="ENTER WORLD").click()
    page.get_by_role("heading", name="Pulse", exact=True).wait_for()
    for name in ("New pairs", "Final stretch", "Migrated"):
        page.get_by_role("heading", name=name, exact=True).wait_for()
    page.get_by_role("button", name="Enter local test account").first.click()
    page.get_by_role("button", name="Open Moon Frog FROG", exact=True).click()
    page.get_by_role("button", name="Preview buy").click()
    page.get_by_role("button", name="Confirm buy").click()
    page.get_by_role("status").filter(has_text="Bought").wait_for()
    buy = page.get_by_role("status").inner_text()
    page.reload()
    page.get_by_role("button", name="Enter local test account").first.click()
    page.get_by_role("button", name="My trades", exact=True).wait_for()
    page.get_by_role("button", name="sell", exact=True).click()
    page.locator("#amount").fill("1")
    page.get_by_role("button", name="Preview sell").click()
    page.get_by_role("button", name="Confirm sell").click()
    page.get_by_role("status").filter(has_text="Sold").wait_for()
    sell = page.get_by_role("status").inner_text()
    page.screenshot(path=str(out / "norx-chart.png"), full_page=True)
    page.get_by_role("link", name="Back to Pulse").click()
    initial = page.request.get(base + "/api/state").json()["total_coins"]
    deadline = time.monotonic() + 70
    while True:
        state = page.request.get(base + "/api/state").json()
        if state["total_coins"] >= initial + 5:
            break
        if time.monotonic() > deadline:
            raise AssertionError("Worker did not launch five coins within 70 seconds")
        time.sleep(1)
    assert state["total_coins"] == initial + 5, (initial, state["total_coins"])
    newest = max(state["coins"], key=lambda c: (c["created_at"], c["id"]))
    target = page.get_by_role(
        "button", name=f"Open {newest['name']} {newest['symbol']}", exact=True
    )
    target.wait_for(timeout=10000)
    page.get_by_label("Search coins").fill(newest["symbol"])
    assert page.locator(".pulse-card").count() == 1
    page.get_by_label("Search coins").fill("")
    page.screenshot(path=str(out / "norx-pulse.png"), full_page=True)
    target.click()
    page.get_by_role("button", name="buy", exact=True).click()
    page.locator("#amount").fill("50")
    page.get_by_role("button", name="Preview buy").click()
    page.get_by_role("button", name="Confirm buy").click()
    page.get_by_role("status").filter(has_text="Bought").wait_for()
    assert page.request.get(base + "/api/candles/" + newest["id"]).json()
    page.get_by_role("link", name="Back to Pulse").click()
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="Final stretch").click()
    assert page.get_by_role("region", name="Final stretch", exact=True).is_visible()
    page.get_by_role("button", name="New pairs").click()
    page.screenshot(path=str(out / "norx-pulse-mobile.png"), full_page=True)
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert not overflow
    assert not errors, errors
    print(
        json.dumps(
            {
                "buy": buy,
                "sell": sell,
                "real_launch_count": state["total_coins"] - initial,
                "new_coin_traded": newest["symbol"],
                "browser_errors": errors,
                "mobile_overflow": overflow,
            }
        )
    )
    browser.close()
