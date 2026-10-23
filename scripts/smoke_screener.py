"""Check dense rankings, window controls, a separate whale panel and ETH-funded virtual trades."""

import os
from playwright.sync_api import sync_playwright

base = os.getenv("NORX_TEST_URL", "http://127.0.0.1:8018")
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.getenv("BROWSER_EXECUTABLE", "/usr/bin/chromium"),
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors = []
    quotes = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on(
        "request",
        lambda r: (
            quotes.append(r.post_data_json)
            if r.method == "POST" and "/api/quote" in r.url
            else None
        ),
    )
    page.goto(base + "/market.html#discover")
    page.locator(".screener-table tbody tr").first.wait_for(timeout=15000)
    assert page.locator(".hot-markets,.discover-overview").count() == 0
    assert not page.get_by_role("dialog", name="Whale watch panel").is_visible()
    page.get_by_role("button", name="1H", exact=True).click()
    assert (
        page.get_by_role("button", name="1H", exact=True).get_attribute("aria-pressed")
        == "true"
    )
    page.get_by_role("button", name="Sort by Volume", exact=True).click()
    page.get_by_role("button", name="Whale watch", exact=True).click()
    drawer = page.get_by_role("dialog", name="Whale watch panel")
    assert drawer.is_visible()
    page.get_by_role("button", name="Close whale watch").click()
    assert not drawer.is_visible()
    page.get_by_role("button", name="ETH", exact=True).click()
    assert "ETH" in page.locator(".screener-table tbody tr").first.inner_text()
    assert "1 ETH = $3,000" in page.locator(".screener-caption").inner_text()
    page.reload()
    assert (
        page.get_by_role("button", name="ETH", exact=True).get_attribute("aria-pressed")
        == "true"
    )
    page.get_by_role("button", name="Enter local test account").first.click()
    page.locator(".screener-token").first.click()
    page.get_by_role("button", name="Preview buy", exact=True).wait_for()
    page.locator("#amount").fill("0.1")
    page.get_by_role("button", name="Preview buy", exact=True).click()
    page.get_by_role("button", name="Confirm buy", exact=True).wait_for()
    assert quotes[-1]["budget"] == 300000000, quotes[-1]
    page.get_by_role("button", name="Confirm buy", exact=True).click()
    page.get_by_role("status").filter(has_text="Bought").wait_for()
    assert "ETH" in page.get_by_role("status").inner_text()
    page.get_by_role("button", name="sell", exact=True).click()
    page.locator("#amount").fill("1")
    page.get_by_role("button", name="Preview sell", exact=True).click()
    page.get_by_role("button", name="Confirm sell", exact=True).click()
    page.get_by_role("status").filter(has_text="Sold").wait_for()
    assert quotes[-1]["qty"] == 1 and "budget" not in quotes[-1]
    assert "ETH" in page.get_by_role("status").inner_text()
    page.get_by_role("button", name="USD", exact=True).click()
    page.get_by_role("link", name="Discover", exact=True).click()
    page.screenshot(path="/tmp/norx-screener-desktop.png")
    for route in ("discover", "pulse", "portfolio", "agents", "trade"):
        page.goto(base + "/market.html#" + route)
        page.wait_for_timeout(350)
        page.set_viewport_size({"width": 390, "height": 844})
        assert not page.evaluate("document.documentElement.scrollWidth>innerWidth"), (
            route
        )
        assert page.get_by_role("button", name="ETH", exact=True).is_visible()
        page.screenshot(
            path="/tmp/norx-screener-" + route + "-mobile.png", full_page=True
        )
        page.set_viewport_size({"width": 1600, "height": 1000})
    assert not errors, errors
    print(
        "PASS: dense screener, window sorting, separate whale panel, persistent USD/ETH, 0.1 ETH = $300 quote and buy, ETH sell proceeds, five mobile routes, no browser errors"
    )
    browser.close()
