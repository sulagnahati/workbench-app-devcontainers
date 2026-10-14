"""End-to-end smoke test: loads every page and calls every data endpoint of a running dashboard server.

Usage: python tools/smoke_test.py [BASE_URL] [--external]   (default http://127.0.0.1:8080)
--external is for a server started with DEV_TOOLS=0: it checks that the developer pages and their data
endpoints are not reachable, and skips the checks that need them.
Runs real BigQuery queries, so expect a minute or more. Exit code 1 if any check fails.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
EXTERNAL = "--external" in sys.argv
BASE = (ARGS[0] if ARGS else "http://127.0.0.1:8080").rstrip("/")
results = []


def get(path, params=None, timeout=240):
    url = f"{BASE}/{path}" + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    t = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read().decode()
            return r.status, body, time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), time.time() - t
    except Exception as e:  # connection problems
        return 0, str(e), time.time() - t


def check(name, path, params=None, expect=None):
    status, body, secs = get(path, params)
    ok = status == 200
    detail = ""
    if ok and expect:
        try:
            data = json.loads(body)
            ok, detail = expect(data)
        except Exception as e:
            ok, detail = False, f"unexpected response: {e}"
    elif not ok:
        detail = body[:160].replace("\n", " ")
    results.append((ok, name, f"{secs:.1f}s", detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<48} {secs:5.1f}s  {detail}")
    return json.loads(body) if status == 200 and body[:1] in "[{" else None


def nonempty(key):
    return lambda d: (bool(d.get(key)), f"{len(d.get(key, []))} rows")


# pages
for p in ["", "overview", "sightline", "lifelong"] + ([] if EXTERNAL else ["tables", "lookml"]):
    check(f"page /{p}", p)
check("stylesheet", "static/dashboard.css")
check("map file", "static/us-states.geojson")

# member overview
cfg = check("overview config", "api/overview/config", expect=lambda d: (len(d["kpis"]) > 0, f"{len(d['kpis'])} kpis"))
check("overview kpis", "api/overview/kpis", expect=lambda d: (d["values"]["total_members"] is not None, str(d["values"]["total_members"])))
check("overview trend", "api/overview/grouped", {"dimension": "signup_month", "measures": "total_members,active_members"}, nonempty("rows"))
for dim in cfg["breakdown"]["selectable"]:
    check(f"overview breakdown: {dim}", "api/overview/grouped", {"dimension": dim, "measures": "total_members,active_members"}, nonempty("rows"))
check("overview drill (organization filter)", "api/overview/grouped",
      {"dimension": "care_program", "measures": "total_members", "filter": "organization:Verily Account - Base Value"}, nonempty("rows"))

# wastewater
sl = check("sightline config", "api/sightline/config")
pathogens = check("sightline pathogen list", "api/sightline/values", {"kind": "pathogen"}, lambda d: (len(d) > 5, f"{len(d)} pathogens"))
states = check("sightline state list", "api/sightline/values", {"kind": "state"}, lambda d: (len(d) > 20, f"{len(d)} states"))
base = {"preset": sl["default_preset"], "pathogen": sl["default_pathogen"]}
check("sightline kpis", "api/sightline/kpis", base, lambda d: (d["row"]["samples"] > 0, f"{d['row']['samples']} samples"))
check("sightline variants", "api/sightline/variants", {"preset": base["preset"]}, nonempty("rows"))
check("sightline variants (state)", "api/sightline/variants", {"preset": base["preset"], "state": states[0]})
check("sightline trend", "api/sightline/trend", base, nonempty("rows"))
check("sightline ranking by state", "api/sightline/ranking", base, nonempty("rows"))
check("sightline ranking by plant", "api/sightline/ranking", dict(base, state="Texas"), nonempty("rows"))
check("sightline plants (map)", "api/sightline/plants", base, nonempty("rows"))

# lifelong (every tile with the dashboard defaults)
lcfg = check("lifelong config", "api/lifelong/config", expect=lambda d: (len(d["tiles"]) >= 14, f"{len(d['tiles'])} tiles"))
defaults = {f["name"]: f["default"] for f in lcfg["filters"]}
for t in lcfg["tiles"]:
    check(f"lifelong tile: {t['title']}", "api/lifelong/tile", {"id": t["id"], "filters": json.dumps(defaults)})
for f in lcfg["filters"]:
    if f["kind"] == "select":
        check(f"lifelong options: {f['name']}", "api/lifelong/values", {"field": f["field"]}, lambda d: (len(d) > 0, f"{len(d)} values"))

def expect_404(name, path, params=None):
    status, body, secs = get(path, params)
    ok = status == 404
    results.append((ok, name, f"{secs:.1f}s", f"status {status}"))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<48} {secs:5.1f}s  status {status}")


if EXTERNAL:
    for path in ["tables", "lookml", "api/tables", "api/schema", "api/filters", "api/summary", "api/breakdown",
                 "api/histogram", "api/timeseries", "api/lookml/fields", "api/lookml/query", "api/lookml/values"]:
        expect_404(f"developer path hidden: /{path}", path, {"table": "x"})
    status, body, _ = get("")
    ok = 'href="tables"' not in body and 'href="lookml"' not in body
    results.append((ok, "navigation hides developer links", "0.0s", ""))
    print(f"{'PASS' if ok else 'FAIL'}  navigation hides developer links")
else:
    # explorer and tables
    fields = check("explorer fields", "api/lookml/fields", expect=lambda d: (len(d["measures"]) > 5, f"{len(d['measures'])} measures"))
    check("explorer query", "api/lookml/query", {"measure": fields["measures"][0]["name"], "dimension": "birth_sex"}, nonempty("rows"))
    tables = check("tables list", "api/tables", expect=lambda d: (len(d) > 0, str(d)))
    check("tables summary", "api/summary", {"table": tables[0]})


failed = [r for r in results if not r[0]]
print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
