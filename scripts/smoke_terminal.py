"""Check terminal navigation, market filters, USD ticket, and execution isolation."""

import os
from playwright.sync_api import sync_playwright

base = os.getenv("NORX_TEST_URL", "http://127.0.0.1:8013")
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.getenv("BROWSER_EXECUTABLE", "/usr/bin/chromium"),
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/market.html#discover")
    page.get_by_label("Search markets").fill("FROG")
    row = page.locator("tbody tr")
    assert row.count() == 1
    page.get_by_label("Sort markets").select_option("market_cap")
    page.get_by_role("button", name="Moon Frog FROG").click()
    page.get_by_role("button", name="Enter local test account").first.click()
    page.get_by_role("button", name="$250", exact=True).click()
    assert page.locator("#amount").input_value() == "250"
    page.get_by_role("button", name="Preview buy", exact=True).click()
    page.get_by_role("button", name="Confirm buy", exact=True).click()
    page.get_by_role("status").filter(has_text="Bought").wait_for()
    page.get_by_role("button", name="My trades", exact=True).click()
    page.locator(".execution-feed tbody tr").first.wait_for()
    assert page.locator(".execution-feed tbody tr").count() >= 1
    page.get_by_label("Filter trades").select_option("sell")
    assert page.locator(".execution-feed tbody tr").count() == 0
    page.get_by_label("Filter trades").select_option("all")
    state = page.request.get(base + "/api/state?selected=frog").json()
    assert state["coin_trades"] and all(
        t["coin"] == "frog" for t in state["coin_trades"]
    )
    assert all(
        t["account"] == "Player" or t["account"].startswith("agent-")
        for t in state["coin_trades"]
    )
    page.screenshot(path="/tmp/norx-terminal-chart.png", full_page=True)
    for route in ("pulse", "discover", "portfolio", "agents", "coin/frog"):
        page.goto(base + "/market.html#" + route)
        page.wait_for_timeout(500)
        page.set_viewport_size({"width": 390, "height": 844})
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), (
            route
        )
        page.screenshot(
            path="/tmp/norx-terminal-" + route.replace("/", "-") + "-mobile.png",
            full_page=True,
        )
        page.set_viewport_size({"width": 1440, "height": 1000})
    assert not errors, errors
    print(
        "PASS: search, sorting, $250 buy, private executions, side filter, five mobile routes, no browser errors"
    )
    browser.close()
