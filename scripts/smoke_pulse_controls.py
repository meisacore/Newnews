"""Controlled-stream UI regression tests; no trading or fabricated production events."""

import copy
import json
import os
import time
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
    # Page-level fixture routes do not intercept SharedWorker requests.
    page.add_init_script("window.SharedWorker = undefined")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    actual = page.request.get(base + "/api/state").json()
    source = {c["id"]: c for c in actual["coins"]}
    for coin in ("frog", "rocket", "pebble"):
        if coin not in source:
            selected = page.request.get(base + "/api/state?selected=" + coin).json()
            source.update({c["id"]: c for c in selected["coins"]})
    records = []
    for index, coin in enumerate(("frog", "rocket", "pebble")):
        record = copy.deepcopy(source[coin])
        record.update(
            stage="new",
            in_feed=True,
            created_at=int(time.time()) - 15 + index,
            market_cap=(index + 1) * 20000,
            volume_24h=1000,
            holders=10,
        )
        records.append(record)
    fixture = copy.deepcopy(actual)
    fixture.update(
        coins=records[:2],
        pulse_counts={"new": 2, "stretch": 0, "migrated": 0},
        total_coins=2,
    )
    calls = {"count": 0}

    def stream(route):
        calls["count"] += 1
        if calls["count"] == 1:
            time.sleep(4.2)
        fixture["server_time"] = int(time.time())
        fixture["next_launch_at"] = int(time.time()) + 60
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(fixture)
        )

    page.route("**/api/state*", stream)
    page.add_init_script("""(() => {
      const original=window.fetch;window.__marketInFlight=0;window.__marketMax=0;window.__marketRequests=0;
      window.fetch=async function(...args){
        if(!String(args[0]).includes('/api/state'))return original.apply(this,args);
        window.__marketRequests++;window.__marketInFlight++;
        window.__marketMax=Math.max(window.__marketMax,window.__marketInFlight);
        try{return await original.apply(this,args);}finally{window.__marketInFlight--;}
      };
    })();""")
    page.goto(base + "/market.html#pulse", wait_until="domcontentloaded")
    page.locator(".feed-status").filter(has_text="Live simulation").wait_for()
    page.wait_for_function("window.__marketRequests>=2", timeout=20000)
    assert page.evaluate("window.__marketMax") == 1
    column = page.get_by_role("region", name="New pairs", exact=True)
    assert column.locator(".pulse-card").count() == 2
    column.get_by_role("button", name="Hold arrivals in New pairs", exact=True).click()
    fixture.update(
        coins=records,
        pulse_counts={"new": 3, "stretch": 0, "migrated": 0},
        total_coins=3,
    )
    column.locator(".column-held").filter(has_text="1 new").wait_for(timeout=15000)
    assert column.locator(".pulse-card").count() == 2
    assert "Live simulation" in page.locator(".feed-status").inner_text()
    column.get_by_role("button", name="Resume New pairs feed", exact=True).click()
    assert column.locator(".pulse-card").count() == 3
    column.get_by_role(
        "button", name="Use 25 USD preset for New pairs", exact=True
    ).click()
    column.get_by_role("button", name="Prepare 25 USD buy of FROG", exact=True).click()
    page.get_by_label("Spend virtual USD").wait_for()
    assert page.locator("#amount").input_value() == "25"
    page.get_by_role("link", name="Back to Pulse").click()
    column = page.get_by_role("region", name="New pairs", exact=True)
    assert (
        column.get_by_role(
            "button", name="Use 25 USD preset for New pairs"
        ).get_attribute("aria-pressed")
        == "true"
    )
    column.get_by_role("button", name="Filters for New pairs", exact=True).click()
    column.get_by_label("Min market cap · USD for New pairs").fill("50000")
    assert column.locator(".pulse-card").count() == 1
    assert (
        not page.get_by_role("region", name="Final stretch", exact=True)
        .locator(".column-filters")
        .count()
    )
    column.get_by_role("button", name="Clear", exact=True).click()
    assert column.locator(".pulse-card").count() == 3
    fixture["simulation"] = {
        "running": True,
        "status": "delayed",
        "last_tick_at": int(time.time()) - 15,
        "age_seconds": 15,
    }
    page.locator(".feed-status").filter(has_text="Updating").wait_for(timeout=15000)
    assert "Simulation paused" not in page.locator(".feed-status").inner_text()
    fixture["simulation"] = {
        "running": False,
        "status": "paused",
        "last_tick_at": int(time.time()) - 40,
        "age_seconds": 40,
    }
    page.locator(".feed-status").filter(has_text="Simulation paused").wait_for(
        timeout=15000
    )
    fixture["simulation"] = {
        "running": True,
        "status": "live",
        "last_tick_at": int(time.time()),
        "age_seconds": 0,
    }
    page.locator(".feed-status").filter(has_text="Live simulation").wait_for(
        timeout=15000
    )
    assert page.locator(".pulse .whale-watch-trades,.pulse .hot-markets").count() == 0
    page.get_by_role("link", name="Discover", exact=True).click()
    page.get_by_role("button", name="Whale watch", exact=True).click()
    page.locator(".whale-watch-trades").wait_for()
    assert page.locator(".whale-watch-trades").count(), (
        "Need at least one actual large trade to test its scrollbar"
    )
    color = page.locator(".whale-watch-trades").evaluate(
        "(el)=>getComputedStyle(el).scrollbarColor"
    )
    assert "120, 109, 85" in color, color
    page.get_by_role("button", name="Close whale watch", exact=True).click()
    page.set_viewport_size({"width": 390, "height": 844})
    assert not page.evaluate("document.documentElement.scrollWidth>window.innerWidth")
    assert not errors, errors
    print(
        json.dumps(
            {
                "max_parallel_feed_requests": 1,
                "held_arrivals_resume": True,
                "presets_and_filters": True,
                "delayed_and_paused_distinct": True,
                "scrollbar_color": color,
                "mobile_overflow": False,
                "browser_errors": errors,
            }
        )
    )
    # Capture the real stream separately: no intercepted or reconstructed reference data.
    page.get_by_role("link", name="Pulse", exact=True).click()
    page.unroute("**/api/state*")
    page.reload(wait_until="domcontentloaded")
    page.locator(".feed-status").filter(has_text="Live simulation").wait_for()
    page.screenshot(path="/tmp/norx-themed-pulse-mobile.png", full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1100})
    page.screenshot(path="/tmp/norx-themed-pulse.png", full_page=True)
    browser.close()
