"""Real browser checks for world isolation and adjustable trade tray."""

import os
from playwright.sync_api import sync_playwright

base = os.getenv("NORX_TEST_URL", "http://127.0.0.1:8021")
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/usr/bin/chromium", args=["--no-sandbox"]
    )
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/market.html#coin/frog")
    page.get_by_role("heading", name="Trade token", exact=True).wait_for()
    chart = page.locator(".chart-frame")
    initial = chart.bounding_box()["height"]
    page.get_by_role("button", name="Expand trades").click()
    assert chart.bounding_box()["height"] < initial
    assert page.locator(".execution-feed").bounding_box()["height"] > 350
    page.get_by_role("button", name="Restore chart").click()
    handle = page.get_by_role("separator", name="Resize trade tray")
    handle.focus()
    handle.press("ArrowUp")
    assert float(handle.get_attribute("aria-valuenow")) == 37
    page.get_by_role("button", name="Economy: Balanced").click()
    page.get_by_role("button", name="Bull run", exact=False).click()
    page.get_by_role("button", name="Economy: Bull run").wait_for()
    page.get_by_role("heading", name="Pulse", exact=True).wait_for()
    page.get_by_role("button", name="Enter local test account").first.click()
    page.wait_for_timeout(1500)
    page.goto(base + "/market.html#coin/frog")
    page.get_by_role("heading", name="Trade token", exact=True).wait_for()
    page.locator("#amount").fill("50")
    page.get_by_role("button", name="Preview buy", exact=True).click()
    page.get_by_role("button", name="Confirm buy", exact=True).click()
    page.get_by_role("status").filter(has_text="Bought").wait_for()
    headers = {"Authorization": "Bearer local-demo", "X-Norx-World": "bull"}
    bull = page.request.get(base + "/api/me", headers=headers).json()
    headers["X-Norx-World"] = "bear"
    bear = page.request.get(base + "/api/me", headers=headers).json()
    assert bull["holdings"].get("frog", 0) > 0 and not bear["holdings"].get("frog", 0)
    assert bear["cash"] == 10000
    assert (
        page.request.get(
            base + "/api/state", headers={"X-Norx-World": "invalid"}
        ).status
        == 400
    )
    page.get_by_role("button", name="Expand trades").click()
    page.screenshot(path="/tmp/norx-worlds-tray.png")
    page.reload()
    page.get_by_role("button", name="Economy: Bull run").wait_for()
    page.set_viewport_size({"width": 390, "height": 844})
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    page.get_by_role("button", name="Economy: Bull run").click()
    page.get_by_role("dialog", name="Choose economy").wait_for()
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    page.screenshot(path="/tmp/norx-economies-mobile.png")
    assert not errors, errors
    print(
        "PASS: expanded tray, keyboard resize, scenario persistence, isolated real trades and mobile economy picker"
    )
    browser.close()
