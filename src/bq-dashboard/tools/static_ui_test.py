"""Browser test of the static sample-data prototype (the folder built by build_static_prototype.py).

Serves the folder on a local port, drives each page like a user, and checks that:
 - nothing is requested from outside the folder (no CDN, no server calls),
 - no real names or identifiers appear on any page,
 - the filters, drill-downs and charts work on the sample data.
Usage: python tools/static_ui_test.py [DIST_DIR]   (needs Playwright and its Chromium, as ui_test.py)
"""
import functools
import http.server
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "static-prototype", "dist")
FORBIDDEN = ["prj-", "wb-arctic", "wb-warm", "gold_basevalue", "Verily Account", "Lifelong Health Study", "ddpcr_dbt", "freyja_summary"]
results, problems, external = [], [], []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=DIST))
BASE = f"http://127.0.0.1:{server.server_address[1]}"
threading.Thread(target=server.serve_forever, daemon=True).start()


def ready(page, js, timeout=60000):
    """Wait for a condition, treating a not-yet-created element as 'not ready' instead of an error."""
    page.wait_for_function(f"(() => {{ try {{ return !!({js}); }} catch (e) {{ return false; }} }})()", timeout=timeout)
    page.wait_for_timeout(900)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1360, "height": 1000})
    page.on("pageerror", lambda e: problems.append(str(e)))
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
    page.on("request", lambda r: external.append(r.url) if not r.url.startswith(BASE) and not r.url.startswith("data:") else None)

    # landing + navigation
    page.goto(f"{BASE}/index.html")
    check("home: sample-data banner is shown", "SAMPLE DATA" in page.locator("body").inner_text())
    check("home: three dashboard cards", page.locator("a.tile").count() == 3)
    for label in ("Member overview", "Wastewater surveillance", "Lifelong funnel"):
        page.goto(f"{BASE}/index.html")
        page.locator("a.tile", has_text=label).click()
        page.wait_for_load_state("domcontentloaded")
        check(f"home: card opens '{label}'", page.url.endswith(".html") and "index" not in page.url, page.url.split("/")[-1])

    # overview
    page.goto(f"{BASE}/overview.html")
    ready(page, "/[0-9]/.test(document.querySelector('#kpi-total_members').textContent)")
    total = page.locator("#kpi-total_members").inner_text()
    check("overview: cards show sample numbers", total not in ("-", "…"), total)
    check("overview: charts drew (no error boxes)", page.locator(".error").count() == 0)
    page.evaluate("drill('Sample Org A')")
    page.wait_for_selector(".chip")
    ready(page, "/[0-9]/.test(document.querySelector('#kpi-total_members').textContent) && document.querySelector('#kpi-total_members').textContent !== '…'")
    check("overview: drill adds a chip and changes the total", "Sample Org A" in page.locator(".chip").inner_text() and page.locator("#kpi-total_members").inner_text() != total,
          f"{total} -> {page.locator('#kpi-total_members').inner_text()}")
    check("overview: drill moves to the next breakdown", page.locator("#dimension").input_value() == "care_program")
    page.locator(".chip button").first.click()
    ready(page, "document.querySelector('#kpi-total_members').textContent !== '…'")
    check("overview: removing the chip restores the total", page.locator("#kpi-total_members").inner_text() == total)

    # wastewater
    page.goto(f"{BASE}/sightline.html")
    ready(page, "/[0-9]/.test(document.querySelector('#kpi-samples').textContent) && document.querySelectorAll('#state option').length > 5")
    samples = page.locator("#kpi-samples").inner_text()
    check("sightline: cards fill in", all(page.locator(f"#kpi-{k}").inner_text() not in ("-", "…") for k in ("variant", "plants", "samples", "latest")))
    check("sightline: map, variant chart and trend drew", page.locator(".error").count() == 0 and page.locator("canvas").count() >= 4, f"{page.locator('canvas').count()} canvases")
    page.select_option("#state", "Texas")
    page.wait_for_selector(".chip")
    ready(page, "/[0-9]/.test(document.querySelector('#kpi-samples').textContent)")
    check("sightline: choosing a state adds a chip and changes the numbers", "Texas" in page.locator(".chip").inner_text() and page.locator("#kpi-samples").inner_text() != samples)
    check("sightline: ranking switches to plants", "Texas" in page.locator("#rank-title").inner_text())
    page.select_option("#pathogen", "RSV")
    ready(page, "document.querySelector('#trend-title').textContent.includes('RSV')")
    check("sightline: pathogen change updates the trend title", "RSV" in page.locator("#trend-title").inner_text())
    page.check("#smooth")
    page.wait_for_timeout(800)
    check("sightline: smoothing works without errors", page.locator(".error").count() == 0)

    # lifelong
    page.goto(f"{BASE}/lifelong.html")
    ready(page, "document.querySelector('#kpi-1') && /[0-9]/.test(document.querySelector('#kpi-1').textContent) && /[0-9]/.test(document.querySelector('#kpi-7').textContent)")
    consent = page.locator("#kpi-7").inner_text()
    check("lifelong: all 14 tiles load", page.locator(".error").count() == 0 and consent not in ("-", "…"), f"consent={consent}")
    page.locator(".msbtn").first.click()
    page.locator(".mspanel:not([hidden]) .msopt", has_text="Sample Lifelong Org").locator("input").uncheck()
    page.locator(".section-title").first.click()
    page.wait_for_function("document.querySelector('#kpi-7').textContent === '0'", timeout=60000)
    check("lifelong: unchecking an organization changes the numbers", page.locator("#kpi-7").inner_text() == "0")
    page.locator("button.secondary").click()
    page.wait_for_function(f"document.querySelector('#kpi-7').textContent === '{consent}'", timeout=60000)
    check("lifelong: Reset restores the defaults", page.locator("#kpi-7").inner_text() == consent)

    # hygiene
    for name in ("index", "overview", "sightline", "lifelong"):
        page.goto(f"{BASE}/{name}.html")
        page.wait_for_timeout(2500)
        text = page.content()
        bad = [w for w in FORBIDDEN if w.lower() in text.lower()]
        check(f"hygiene: no real names or identifiers on {name}", not bad, ", ".join(bad))
    check("nothing was requested from outside the folder", not external, ", ".join(sorted(set(external))[:3]))
    check("no JavaScript errors on any page", not problems, "; ".join(sorted(set(problems)))[:200])
    browser.close()

server.shutdown()
print(f"\n{sum(results)} passed, {len(results) - sum(results)} failed")
sys.exit(0 if all(results) else 1)
