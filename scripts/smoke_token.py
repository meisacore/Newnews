"""Check the unified token terminal, real 24-hour chart requests and billion-token supply."""

import os
from playwright.sync_api import sync_playwright

base = os.getenv("NORX_TEST_URL", "http://127.0.0.1:8020")
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.getenv("BROWSER_EXECUTABLE", "/usr/bin/chromium"),
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/market.html#coin/frog")
    page.get_by_role("heading", name="Trade token", exact=True).wait_for()
    page.locator(".token-heading-identity h2").filter(has_text="Moon Frog").wait_for()
    state = page.request.get(base + "/api/state?selected=frog").json()
    assert state["api_version"] == 5 and all(
        c["total_supply"] == 1000000000 for c in state["coins"]
    )
    assert "1,000,000,000" in page.locator(".token-info").inner_text()
    with page.expect_response(
        lambda r: "/api/candles/frog?" in r.url and "range_seconds=86400" in r.url
    ) as response:
        page.get_by_role("button", name="24h view", exact=True).click()
    assert response.value.ok and response.value.json()
    assert "24h view" in page.locator(".chart-range .active").inner_text()
    page.get_by_role("button", name="15m", exact=True).click()
    page.get_by_role("button", name="Enter local test account").first.click()
    page.locator("#amount").fill("50")
    page.get_by_role("button", name="ETH", exact=True).click()
    page.get_by_role("button", name="USD", exact=True).click()
    page.wait_for_function("document.querySelector('#amount').value === '50'")
    page.get_by_role("button", name="Preview buy", exact=True).click()
    page.get_by_role("button", name="Confirm buy", exact=True).click()
    page.get_by_role("status").filter(has_text="Bought").wait_for()
    page.get_by_role("button", name="Positions", exact=True).click()
    assert "Tokens held" in page.locator(".token-position-tab").inner_text()
    assert "Available USD" in page.locator(".token-position-tab").inner_text()
    page.get_by_role("button", name="Market trades", exact=True).click()
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    page.evaluate("document.fonts.ready")
    page.screenshot(path="/tmp/norx-token-terminal.png")
    page.set_viewport_size({"width": 390, "height": 844})
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    page.screenshot(path="/tmp/norx-token-terminal-mobile.png", full_page=True)
    assert not errors, errors
    print(
        "PASS: unified token terminal, billion supply, 24h chart and 15m candles, $50 denomination roundtrip, live buy and position, desktop/mobile"
    )
    browser.close()
