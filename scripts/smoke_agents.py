"""Check personality dashboard and naturally occurring large trades in local mode."""

import json
import os
from playwright.sync_api import sync_playwright

base = os.getenv("NORX_TEST_URL", "http://127.0.0.1:5173")
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
    page.goto(base + "/market.html#agents")
    page.get_by_role("heading", name="Meet the traders.").wait_for()
    comet = page.locator(".agent-card").filter(
        has=page.get_by_role("heading", name="Comet", exact=True)
    )
    comet.wait_for()
    assert "Reckless whale" in comet.inner_text()
    assert "$1,500,000 initial grant" in comet.inner_text()
    assert page.locator(".agent-card").count() == 36
    page.screenshot(path="/tmp/norx-agent-personalities.png", full_page=True)
    page.get_by_role("link", name="Pulse", exact=True).click()
    page.get_by_role("region", name="Large trades", exact=True).wait_for(timeout=60000)
    state = page.request.get(base + "/api/state").json()
    assert state["api_version"] == 3
    assert any(t["amount"] >= 1000 * 1e6 for t in state["large_trades"])
    largest = max(state["agents"], key=lambda a: a["biggest_buy"])
    first = page.locator(".whale-watch-trades button").first
    assert first.get_attribute("title")
    page.screenshot(path="/tmp/norx-whale-watch.png", full_page=True)
    first.click()
    page.get_by_role("heading", name="Make your move").wait_for()
    assert page.locator("canvas").count() > 0
    page.get_by_role("link", name="Agents", exact=True).click()
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("heading", name="Meet the traders.").wait_for()
    assert not page.evaluate("document.documentElement.scrollWidth>window.innerWidth")
    page.screenshot(path="/tmp/norx-agent-personalities-mobile.png", full_page=True)
    assert not errors, errors
    print(
        json.dumps(
            {
                "population": len(state["agents"]),
                "largest_buy_usd": largest["biggest_buy"] / 1e6,
                "largest_buyer": largest["name"],
                "personality": largest["personality"],
                "browser_errors": errors,
                "mobile_overflow": False,
            }
        )
    )
    browser.close()
