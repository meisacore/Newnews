"""Smoke-test a running local Wrangler server; uses its configured database.

Build the frontend, run npm run dev in cloudflare, then run this script.
Login is not bypassed. Tests public pages plus private API rejection.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

base = os.getenv("NORX_TEST_URL", "http://127.0.0.1:8787").rstrip("/")
out = Path(os.getenv("NORX_SCREENSHOT_DIR", tempfile.gettempdir()))
out.mkdir(parents=True, exist_ok=True)


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(15000)
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(base + "/", wait_until="domcontentloaded")
        await page.locator("a.enter").click(no_wait_after=True)
        await page.wait_for_url("**/pulse", wait_until="domcontentloaded")
        await page.get_by_role("heading", name="Pulse", exact=True).wait_for(
            timeout=30000
        )
        await page.locator(".pulse-card").first.wait_for(timeout=20000)
        assert page.url.endswith("/pulse")
        icon = await page.request.get(base + "/favicon.svg")
        assert icon.ok and "image/svg+xml" in icon.headers.get("content-type", "")
        assert (
            await page.locator('link[rel="icon"]').get_attribute("href")
            == "/favicon.svg"
        )
        await page.get_by_role("link", name="Discover", exact=True).click()
        await page.get_by_role("heading", name="Discover", exact=True).wait_for()
        assert page.url.endswith("/discover")
        await page.reload(wait_until="domcontentloaded")
        await page.get_by_role("heading", name="Discover", exact=True).wait_for()
        await page.get_by_role("link", name="Pulse", exact=True).click()
        assert page.url.endswith("/pulse")
        await page.go_back()
        await page.get_by_role("heading", name="Discover", exact=True).wait_for()
        await page.go_forward()
        await page.get_by_role("heading", name="Pulse", exact=True).wait_for()
        await page.get_by_role("link", name="Discover", exact=True).click()
        await page.screenshot(
            path=str(out / "norx-cloudflare-discover.png"), full_page=True
        )
        await page.goto(base + "/market.html#coin/frog", wait_until="domcontentloaded")
        await (
            page.locator(".token-heading-identity h2")
            .filter(has_text="Moon Frog")
            .wait_for(timeout=30000)
        )
        assert page.url.endswith("/trade/frog")
        await page.reload(wait_until="domcontentloaded")
        await page.locator(".token-heading-identity h2").wait_for()
        await page.get_by_role("button", name="24h view", exact=True).click()
        await page.get_by_role("button", name="Expand trades").click()
        await page.get_by_role("button", name="Restore chart").wait_for()
        await page.screenshot(
            path=str(out / "norx-cloudflare-token.png"), full_page=True
        )
        await page.get_by_role("link", name="Agents", exact=True).click()
        await page.locator(".agent-card").first.wait_for()
        assert "2,000 traders" in await page.locator(".agent-browser").inner_text()
        await page.get_by_role("link", name="Pulse", exact=True).click()
        await page.locator(".pulse-card").first.wait_for()
        assert "2000 agents" in await page.locator(".exchange-footer").inner_text()
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(base + "/market.html#pulse")
        await page.get_by_role("heading", name="Pulse", exact=True).wait_for()
        assert await page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
        config = await page.request.get(base + "/api/config")
        assert not (await config.json())["dev_auth"]
        private = await page.request.get(base + "/api/me")
        assert private.status == 401
        assert not errors, errors
        print(
            json.dumps(
                {
                    "checks": "welcome, clean URLs, favicon, legacy bookmarks, refresh and history, Pulse, Discover, Agents, token chart, expandable tray, mobile, auth required",
                    "page_errors": errors,
                }
            )
        )
        await browser.close()


asyncio.run(run())
