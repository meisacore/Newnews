import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:5173")
    page.get_by_role("heading", name="Your next move.").wait_for()
    page.get_by_role("button", name="Enter local test account").first.click()
    page.get_by_role("button", name="Preview buy").click()
    page.get_by_role("button", name="Confirm buy").click()
    page.get_by_role("status").filter(has_text="Bought").wait_for()
    notice = page.get_by_role("status").inner_text()
    page.reload()
    page.get_by_role("button", name="Enter local test account").first.click()
    page.get_by_role("button", name="Preview buy").wait_for()
    page.get_by_role("heading", name="Your recent trades").wait_for()
    page.get_by_role("button", name="sell", exact=True).click()
    page.locator("#amount").fill("1")
    page.get_by_role("button", name="Preview sell").click()
    page.get_by_role("button", name="Confirm sell").click()
    page.get_by_role("status").filter(has_text="Sold").wait_for()
    page.screenshot(path="/tmp/norx-desktop.png", full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path="/tmp/norx-mobile.png", full_page=True)
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    print(
        json.dumps(
            {
                "buy": notice,
                "sell": page.get_by_role("status").inner_text(),
                "browser_errors": errors,
                "mobile_overflow": overflow,
            }
        )
    )
    assert not errors, errors
    assert not overflow
    browser.close()
