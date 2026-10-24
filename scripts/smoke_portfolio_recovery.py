"""Check that temporary server errors are labeled accurately and then clear.
Use an isolated local-test build and NORX_DEV_AUTH=1 on a temporary database.
"""

import os
from playwright.sync_api import sync_playwright, expect

base = os.getenv("NORX_TEST_URL", "http://127.0.0.1:8023")
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/usr/bin/chromium", args=["--no-sandbox"]
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    requests = []

    def temporary_failure(route):
        requests.append(route.request.url)
        if len(requests) == 1:
            route.fulfill(
                status=500, content_type="text/plain", body="Internal Server Error"
            )
        else:
            route.continue_()

    page.route("**/api/me", temporary_failure)
    page.goto(base + "/market.html#pulse")
    page.get_by_role("button", name="Enter local test account").first.click()
    banner = page.get_by_role("alert").filter(has_text="Portfolio update:")
    expect(banner).to_contain_text("server returned an error (500)")
    assert "Start the updated backend" not in banner.inner_text()
    expect(banner).to_have_count(0, timeout=20000)
    expect(page.locator(".exchange-header")).to_contain_text("$10,000.00")
    assert len(requests) >= 2
    state = page.request.get(base + "/api/state").json()
    assert state["simulation"]["running"]
    assert not errors, errors
    print(
        "PASS: real PostgreSQL worker stays live, temporary server error is accurate and clears after portfolio refresh"
    )
    browser.close()
