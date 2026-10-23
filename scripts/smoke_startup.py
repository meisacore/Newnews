"""Verify first paint and startup failure UI on a running Vite dev server."""

import os
from playwright.sync_api import sync_playwright

base = os.getenv("NORX_TEST_URL", "http://127.0.0.1:5174")
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.getenv("BROWSER_EXECUTABLE", "/usr/bin/chromium"),
        args=["--no-sandbox"],
    )
    page = browser.new_page()
    # Hold the app module: HTML alone must already display the branded loader.
    page.route("**/src/main.jsx*", lambda route: route.abort())
    page.goto(base + "/market.html#pulse", wait_until="domcontentloaded")
    page.get_by_text("The exchange could not start.", exact=True).wait_for()
    assert page.locator(".startup-brand").inner_text() == "NORX"
    assert page.get_by_role("link", name="Reload exchange").is_visible()
    assert (
        page.evaluate("getComputedStyle(document.body).backgroundColor")
        == "rgb(9, 17, 24)"
    )
    page.unroute("**/src/main.jsx*")
    # No external fonts may block the welcome or exchange in local mode.
    external = []
    page.on(
        "request",
        lambda r: (
            external.append(r.url)
            if "fonts.googleapis.com" in r.url or "fonts.gstatic.com" in r.url
            else None
        ),
    )
    page.goto(base, wait_until="domcontentloaded")
    page.get_by_role("link", name="ENTER WORLD").click()
    page.get_by_role("heading", name="Pulse", exact=True).wait_for()
    assert not page.locator("#startup").count()
    assert not external, external
    assert page.locator(".pulse-column").count() == 3
    print(
        "PASS: branded HTML loader, failed module recovery, Enter World in Vite, no external fonts"
    )
    browser.close()
