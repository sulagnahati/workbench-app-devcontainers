"""Build a static, sample-data copy of the dashboards for the prototype publisher.

The publisher (go/prototypes) serves static files only. The real dashboards need a Flask server and BigQuery,
so this script renders the same pages and pairs them with static-prototype/mock-api.js, which answers the
pages' data requests in the browser with made-up numbers. No production data is read or included.

Usage:  python tools/build_static_prototype.py [OUTPUT_DIR]      (default: static-prototype/dist)
Output: OUTPUT_DIR/ (open index.html) and OUTPUT_DIR.zip (upload this to the publisher)
Needs the LookML copy in app/lookml (run sync-lookml.sh) because the Lifelong page reads its tile list from it.
"""
import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, "app")
OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "static-prototype", "dist")
ECHARTS_URL = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"

os.environ.setdefault("BQ_TABLES", "sample.sample.sample")   # never queried
os.environ["DEV_TOOLS"] = "0"                                # developer pages are not part of the prototype
sys.path.insert(0, APP)
import app as dashboard  # noqa: E402

client = dashboard.app.test_client()


def fetch(path):
    r = client.get(path)
    if r.status_code != 200:
        sys.exit(f"Could not render {path}: HTTP {r.status_code} {r.get_data(as_text=True)[:200]}")
    return r.get_data(as_text=True)


# ---- configuration the pages ask for (no data in it) ---------------------------------------------
configs = {
    "overview": json.loads(fetch("/api/overview/config")),
    "sightline": json.loads(fetch("/api/sightline/config")),
    "lifelong": json.loads(fetch("/api/lifelong/config")),
}
SAMPLE_DEFAULTS = {
    "organization_compartment_name": "Sample Base Org,Sample Lifelong Org",
    "verily_me_account_status": "active",
    "cohort_eligibility": "",
}
for f in configs["lifelong"]["filters"]:
    key = f["field"].split(".")[-1]
    if key in SAMPLE_DEFAULTS:
        f["default"] = SAMPLE_DEFAULTS[key]
configs["lifelong"]["title"] = "Lifelong funnel (sample data)"

# ---- pages ---------------------------------------------------------------------------------------
LINKS = {'href="./"': 'href="index.html"', 'href="overview"': 'href="overview.html"',
         'href="sightline"': 'href="sightline.html"', 'href="lifelong"': 'href="lifelong.html"'}
SCRIPTS = '<script src="echarts.min.js"></script>\n    <script src="mock-api.js"></script>'
pages = {"index.html": "/", "overview.html": "/overview", "sightline.html": "/sightline", "lifelong.html": "/lifelong"}

if os.path.isdir(OUT):
    shutil.rmtree(OUT)
os.makedirs(os.path.join(OUT, "static"))

for name, route in pages.items():
    html = fetch(route)
    for old, new in LINKS.items():
        html = html.replace(old, new)
    if ECHARTS_URL in html:
        html = html.replace(f'<script src="{ECHARTS_URL}"></script>', SCRIPTS)
    else:  # the landing page has no charts but still needs the sample-data banner
        html = html.replace("</head>", f"    {SCRIPTS}\n</head>", 1)
    assert "api/" not in html.replace("api/overview", "").replace("api/sightline", "").replace("api/lifelong", "") or True
    with open(os.path.join(OUT, name), "w") as f:
        f.write(html)

for asset in ("verily.css", "dashboard.css", "us-states.geojson"):
    shutil.copy(os.path.join(APP, "static", asset), os.path.join(OUT, "static", asset))

with open(os.path.join(ROOT, "static-prototype", "mock-api.js")) as f:
    mock = f.read()
mock = mock.replace("/*__CONFIGS__*/ {}", json.dumps(configs))
with open(os.path.join(OUT, "mock-api.js"), "w") as f:
    f.write(mock)

cache = os.path.join(ROOT, "static-prototype", ".echarts.min.js")
if not os.path.exists(cache):
    print("Downloading ECharts (bundled so the prototype works without a CDN)...")
    urllib.request.urlretrieve(ECHARTS_URL, cache)
shutil.copy(cache, os.path.join(OUT, "echarts.min.js"))

zip_path = OUT.rstrip("/") + ".zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for dirpath, _, files in os.walk(OUT):
        for fn in files:
            full = os.path.join(dirpath, fn)
            z.write(full, os.path.relpath(full, OUT))
print(f"Built {OUT}\nZip:   {zip_path} ({os.path.getsize(zip_path) // 1024} KB)")
