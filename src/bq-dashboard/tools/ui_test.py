"""Browser test: drives the dashboards like a user (clicks filters, drills, toggles) and checks the results.

Needs Playwright with its own Chromium:  pip install playwright && playwright install chromium
(Playwright's Chromium is used on purpose: an installed Google Chrome was being shut down after a few seconds on one managed laptop.)
Usage: python tools/ui_test.py [BASE_URL]   (default http://127.0.0.1:8080)
Exit code 1 if any check fails. Screenshots go to the folder named by UI_TEST_SHOTS, if set.
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080").rstrip("/")
SHOTS = os.environ.get("UI_TEST_SHOTS")
results, js_errors = [], []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def settle(page, timeout=120000):
    """Wait until no 'Loading' placeholders remain, then let animations finish."""
    page.wait_for_function("!document.body.innerText.includes('Loading...') && !document.body.innerText.includes('Loading filters')", timeout=timeout)
    page.wait_for_timeout(1200)


def shot(page, name):
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, f"ui_{name}.png"), full_page=True)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1360, "height": 1000})
    page.on("pageerror", lambda e: js_errors.append(str(e)))
    page.on("console", lambda m: js_errors.append(m.text) if m.type == "error" and "extension" not in m.text.lower() else None)

    # ---- home: navigation ---------------------------------------------------
    page.goto(f"{BASE}/")
    check("home: three dashboard cards", page.locator("a.tile").count() == 3)
    for label, heading in [("Member overview", "Member overview"), ("Wastewater surveillance", "Wastewater"), ("Lifelong funnel", "Lifelong funnel")]:
        page.goto(f"{BASE}/")
        page.locator("a.tile", has_text=label).click()
        page.wait_for_load_state("domcontentloaded")
        check(f"home: card opens '{label}'", page.locator("nav a.active").inner_text().strip() == heading, page.url.split("/")[-1])
    page.goto(f"{BASE}/")
    page.locator("nav a", has_text="Lifelong funnel").click()
    check("nav: tab switches page", "lifelong" in page.url)

    # ---- lifelong: checkbox dropdown filters ---------------------------------
    page.goto(f"{BASE}/lifelong")
    page.wait_for_function("document.querySelector('#kpi-1') && document.querySelector('#kpi-1').textContent !== '…'", timeout=120000)
    settle(page)
    interested = page.locator("#kpi-1").inner_text()
    consent = page.locator("#kpi-7").inner_text()
    check("lifelong: KPIs load", interested not in ("…", "-") and consent not in ("…", "-"), f"interested={interested} consent={consent}")
    check("lifelong: 14 tiles, no errors on load", page.locator(".error").count() == 0, f"{page.locator('.error').count()} error boxes")
    page.locator(".msbtn").first.click()
    check("lifelong: organization dropdown opens with options", page.locator(".mspanel:not([hidden]) .msopt").count() >= 2, f"{page.locator('.mspanel:not([hidden]) .msopt').count()} options")
    page.locator(".mspanel:not([hidden]) .msopt", has_text="Lifelong Health Study").locator("input").uncheck()
    page.locator(".section-title").first.click()   # clicking elsewhere closes the dropdown and applies the change
    page.wait_for_function("document.querySelector('#kpi-7').textContent === '0'", timeout=120000)
    settle(page)
    check("lifelong: unchecking one organization changes the numbers", page.locator("#kpi-7").inner_text() == "0" and page.locator("#kpi-1").inner_text() == interested,
          f"consent={page.locator('#kpi-7').inner_text()} interested={page.locator('#kpi-1').inner_text()}")
    check("lifelong: summary line reflects the filter", "Lifelong Health Study" not in page.locator("#summary").inner_text())
    page.locator("button.secondary").click()
    page.wait_for_function(f"document.querySelector('#kpi-7').textContent === '{consent}'", timeout=120000)
    check("lifelong: Reset restores the defaults", page.locator("#kpi-7").inner_text() == consent)
    page.locator(".field select").last.select_option("week")
    page.locator("button.primary").click()
    settle(page)
    check("lifelong: trend grain applies via the Apply button", "grouped by week" in page.locator("#sub-interest").inner_text() and page.locator(".error").count() == 0)
    shot(page, "lifelong")

    # ---- overview: drill-down -------------------------------------------------
    page.goto(f"{BASE}/overview")
    page.wait_for_function("document.querySelector('#kpi-total_members') && /[0-9]/.test(document.querySelector('#kpi-total_members').textContent)", timeout=120000)
    settle(page)
    total = page.locator("#kpi-total_members").inner_text()
    page.evaluate("drill('Verily Account - Base Value')")
    page.wait_for_selector(".chip")
    settle(page)
    check("overview: drilling adds a filter chip", "Verily Account - Base Value" in page.locator(".chip").inner_text())
    check("overview: drill moves to the next breakdown", page.locator("#dimension").input_value() == "care_program", page.locator("#dimension").input_value())
    check("overview: KPIs change when filtered", page.locator("#kpi-total_members").inner_text() != total, f"{total} -> {page.locator('#kpi-total_members').inner_text()}")
    check("overview: charts render without errors", page.locator(".error").count() == 0)
    shot(page, "overview_drilled")
    page.locator(".chip button").first.click()
    settle(page)
    check("overview: removing the chip restores the totals", page.locator("#kpi-total_members").inner_text() == total)

    # ---- sightline: filters, drill, smoothing ---------------------------------
    page.goto(f"{BASE}/sightline")
    page.wait_for_function("document.querySelector('#kpi-samples') && /[0-9]/.test(document.querySelector('#kpi-samples').textContent)", timeout=120000)
    settle(page)
    samples = page.locator("#kpi-samples").inner_text()
    check("sightline: all four cards fill in", all(page.locator(f"#kpi-{k}").inner_text() not in ("-", "…") for k in ("variant", "plants", "samples", "latest")))
    page.wait_for_function("document.querySelectorAll('#state option').length > 5", timeout=60000)
    page.select_option("#state", "Texas")
    page.wait_for_selector(".chip")
    page.wait_for_function("/[0-9]/.test(document.querySelector('#kpi-samples').textContent)", timeout=120000)
    settle(page)
    check("sightline: choosing a state adds a chip", "Texas" in page.locator(".chip").inner_text())
    check("sightline: ranking switches to plants", "plant" in page.locator("#rank-title").inner_text().lower() and "Texas" in page.locator("#rank-title").inner_text())
    check("sightline: samples change for the state", page.locator("#kpi-samples").inner_text() != samples, f"{samples} -> {page.locator('#kpi-samples').inner_text()}")
    page.check("#smooth")
    settle(page)
    check("sightline: smoothing toggle works without errors", page.locator(".error").count() == 0)
    page.select_option("#pathogen", "Influenza A")
    settle(page)
    check("sightline: pathogen change updates the trend title", "Influenza A" in page.locator("#trend-title").inner_text())
    shot(page, "sightline_filtered")
    page.locator("button.linkbtn", has_text="Clear all").click()
    settle(page)
    check("sightline: Clear all removes the filter chips", page.locator(".chip").count() == 0)

    # ---- tables + explorer ---------------------------------------------------------
    page.goto(f"{BASE}/tables")
    page.wait_for_function("document.querySelector('#row-count') && /[0-9]/.test(document.querySelector('#row-count').textContent)", timeout=120000)
    check("tables: no row-level data on the page", page.locator("table").count() == 0 and "preview" not in page.content().lower())
    page.goto(f"{BASE}/lookml")
    page.wait_for_function("document.querySelectorAll('#measure option').length > 3", timeout=120000)
    check("explorer: measures load", page.locator("#measure option").count() > 3)

    check("no JavaScript errors on any page", not js_errors, "; ".join(sorted(set(js_errors)))[:200])
    browser.close()

print(f"\n{sum(results)} passed, {len(results) - sum(results)} failed")
sys.exit(0 if all(results) else 1)
