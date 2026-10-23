"""Check market selection, rolling trending data, and a real 2,000-agent population."""

import os
from playwright.sync_api import sync_playwright

base = os.getenv("NORX_TEST_URL", "http://127.0.0.1:8015")
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.getenv("BROWSER_EXECUTABLE", "/usr/bin/chromium"),
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/market.html#pulse")
    page.get_by_role("heading", name="Pulse", exact=True).wait_for()
    assert page.locator(".hot-markets,.whale-watch").count() == 0
    assert page.locator(".wordmark").inner_text() == "NORX"
    assert (
        page.locator(".wordmark > span").evaluate("el=>getComputedStyle(el).color")
        == "rgb(201, 180, 140)"
    )
    page.get_by_role("link", name="Discover", exact=True).click()
    page.locator(".hot-market-scroll button").first.wait_for(timeout=15000)
    page.get_by_role("region", name="Large trades", exact=True).wait_for()
    state = page.request.get(base + "/api/state").json()
    assert len(state["agents"]) == 2000
    assert "sky-bg.jpg" in page.evaluate(
        "getComputedStyle(document.body).backgroundImage"
    )
    assert state["trending"] and all(c["buy_usd_5m"] > 0 for c in state["trending"])
    assert state["trending"] == sorted(
        state["trending"], key=lambda c: c["heat_score"], reverse=True
    )
    page.get_by_role("link", name="Trade", exact=True).click()
    page.get_by_role("heading", name="Trade", exact=True).wait_for()
    assert page.url.endswith("#trade") and page.locator("#amount").count() == 0
    chosen = next(c for c in state["coins"] if c["id"] != "frog" and c["in_feed"])
    page.get_by_label("Search markets").fill(chosen["symbol"])
    page.locator(".market-name").filter(has_text=chosen["symbol"]).first.click()
    assert page.url.endswith("#coin/" + chosen["id"])
    page.get_by_role("heading", name="Make your move", exact=True).wait_for()
    page.get_by_role("link", name="Discover", exact=True).click()
    page.get_by_role("button", name="Trending · 5m", exact=True).click()
    page.locator(".terminal-table tbody tr").first.wait_for()
    assert page.get_by_label("Sort markets").input_value() == "heat_score"
    page.get_by_role("link", name="Agents", exact=True).click()
    page.get_by_role("button", name="Next", exact=True).click()
    assert "Page 2 of 50" in page.locator(".agent-browser").inner_text()
    page.get_by_label("Search traders").fill("Comet")
    assert page.locator(".agent-card").count() == 1
    assert "Reckless whale" in page.locator(".agent-card").inner_text()
    for route in ("pulse", "trade", "discover", "agents"):
        page.goto(base + "/market.html#" + route)
        page.wait_for_timeout(300)
        page.set_viewport_size({"width": 390, "height": 844})
        assert not page.evaluate("document.documentElement.scrollWidth>innerWidth"), (
            route
        )
        page.screenshot(path="/tmp/norx-heat-" + route + "-mobile.png", full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto(base + "/market.html#pulse")
    assert page.locator(".hot-markets,.whale-watch").count() == 0
    page.evaluate("document.fonts.ready")
    assert "DM Sans" in page.evaluate("getComputedStyle(document.body).fontFamily")
    page.screenshot(path="/tmp/norx-heat-pulse.png")
    assert not errors, errors
    print(
        "PASS: Trade picker, chosen market chart, actual hot buys, trending sort, 2,000 accounts, agent pagination/search, four mobile routes"
    )
    browser.close()
