import datetime
import decimal
import json
import os
import threading
import time

from werkzeug.exceptions import HTTPException
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from google.cloud import bigquery

import lifelong_dashboard
import overview
import sightline
import lookml_engine

app = Flask(__name__)
app.config["STRICT_SLASHES"] = False  # Prevents 308 redirects behind the proxy
CORS(app)

TABLES = [t.strip() for t in os.environ.get("BQ_TABLES", "").split(",") if t.strip()]
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "600"))
MAX_CATEGORIES = 50
PREVIEW_ROWS = 50
# Columns that identify individuals: never shown in the preview table
HIDDEN_COLUMNS = {"id", "pendo_visitor_id", "identifier_system_value_list", "group_id_list"}

_client = None
_cache = {}
_lock = threading.Lock()


def client():
    global _client
    if _client is None:
        _client = bigquery.Client()
    return _client


def cached(key, fn):
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
    value = fn()
    with _lock:
        _cache[key] = (now, value)
    return value


def get_table(name):
    if name not in TABLES:
        raise ValueError(f"Unknown table: {name}")
    return name


def get_schema(table):
    def load():
        t = client().get_table(table)
        return [{"name": f.name, "type": f.field_type} for f in t.schema]

    return cached(("schema", table), load)


def column_kind(col_type):
    if col_type in ("INTEGER", "INT64", "FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC"):
        return "numeric"
    if col_type in ("TIMESTAMP", "DATE", "DATETIME"):
        return "time"
    if col_type in ("STRING", "BOOLEAN", "BOOL"):
        return "category"
    return "other"


def valid_column(table, col, kinds=None):
    for f in get_schema(table):
        if f["name"] == col and (kinds is None or column_kind(f["type"]) in kinds):
            return f
    raise ValueError(f"Invalid column: {col}")


def build_where(table):
    """Filters come in as repeated ?filter=column:value params (values are query parameters)."""
    clauses, params = [], []
    for i, item in enumerate(request.args.getlist("filter")):
        col, _, value = item.partition(":")
        f = valid_column(table, col, kinds={"category"})
        ptype = "BOOL" if f["type"] in ("BOOLEAN", "BOOL") else "STRING"
        if value == "__null__":
            clauses.append(f"`{col}` IS NULL")
        else:
            pval = (value.lower() == "true") if ptype == "BOOL" else value
            clauses.append(f"`{col}` = @p{i}")
            params.append(bigquery.ScalarQueryParameter(f"p{i}", ptype, pval))
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def run(sql, params=None):
    cfg = bigquery.QueryJobConfig(query_parameters=params or [])
    return [dict(r) for r in client().query(sql, job_config=cfg).result()]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/tables")
def api_tables():
    return jsonify(TABLES)


@app.route("/api/schema")
def api_schema():
    table = get_table(request.args.get("table", ""))
    return jsonify([dict(f, kind=column_kind(f["type"])) for f in get_schema(table)])


@app.route("/api/filters")
def api_filters():
    """Distinct values for low-cardinality categorical columns, for filter dropdowns."""
    table = get_table(request.args.get("table", ""))

    def load():
        out = {}
        for f in get_schema(table):
            if column_kind(f["type"]) != "category" or f["name"] in HIDDEN_COLUMNS:
                continue
            rows = run(
                f"SELECT CAST(`{f['name']}` AS STRING) AS v FROM `{table}` "
                f"GROUP BY v ORDER BY v LIMIT {MAX_CATEGORIES + 1}"
            )
            values = [r["v"] for r in rows if r["v"] is not None]
            if 0 < len(values) <= MAX_CATEGORIES:
                out[f["name"]] = values
        return out

    return jsonify(cached(("filters", table), load))


@app.route("/api/summary")
def api_summary():
    table = get_table(request.args.get("table", ""))
    where, params = build_where(table)
    row = run(f"SELECT COUNT(*) AS n FROM `{table}` {where}", params)[0]
    return jsonify({"row_count": row["n"]})


@app.route("/api/breakdown")
def api_breakdown():
    """Row counts grouped by one categorical column."""
    table = get_table(request.args.get("table", ""))
    col = request.args.get("column", "")
    valid_column(table, col, kinds={"category"})
    where, params = build_where(table)
    rows = run(
        f"SELECT CAST(`{col}` AS STRING) AS label, COUNT(*) AS n FROM `{table}` {where} "
        f"GROUP BY label ORDER BY n DESC LIMIT {MAX_CATEGORIES}",
        params,
    )
    return jsonify(rows)


@app.route("/api/histogram")
def api_histogram():
    """Row counts per value of a numeric column (e.g. age)."""
    table = get_table(request.args.get("table", ""))
    col = request.args.get("column", "")
    valid_column(table, col, kinds={"numeric"})
    where, params = build_where(table)
    rows = run(
        f"SELECT `{col}` AS x, COUNT(*) AS n FROM `{table}` {where} "
        f"GROUP BY x HAVING x IS NOT NULL ORDER BY x",
        params,
    )
    return jsonify(rows)


@app.route("/api/timeseries")
def api_timeseries():
    """Row counts per month of a time column."""
    table = get_table(request.args.get("table", ""))
    col = request.args.get("column", "")
    valid_column(table, col, kinds={"time"})
    where, params = build_where(table)
    rows = run(
        f"SELECT FORMAT_TIMESTAMP('%Y-%m', TIMESTAMP(`{col}`)) AS month, COUNT(*) AS n "
        f"FROM `{table}` {where} GROUP BY month HAVING month IS NOT NULL ORDER BY month",
        params,
    )
    return jsonify(rows)


@app.route("/api/preview")
def api_preview():
    table = get_table(request.args.get("table", ""))
    cols = [f["name"] for f in get_schema(table) if f["name"] not in HIDDEN_COLUMNS]
    where, params = build_where(table)
    select = ", ".join(f"CAST(`{c}` AS STRING) AS `{c}`" for c in cols)
    rows = run(f"SELECT {select} FROM `{table}` {where} LIMIT {PREVIEW_ROWS}", params)
    return jsonify({"columns": cols, "rows": rows})


# ---- LookML-driven explorer and dashboard -----------------------------------

_lookml = {}


def lookml_project():
    if "project" not in _lookml:
        _lookml["project"] = lookml_engine.project_from_env()
    return _lookml["project"]


def lookml_explorer():
    if "explorer" not in _lookml:
        _lookml["explorer"] = lookml_engine.Explorer(lookml_project())
    return _lookml["explorer"]


def lifelong():
    if "dashboard" not in _lookml:
        _lookml["dashboard"] = lifelong_dashboard.Dashboard(lookml_project())
    return _lookml["dashboard"]


def lookml_params(params):
    return [bigquery.ScalarQueryParameter(k, "STRING", v) for k, v in params.items()]


def jsonable(v):
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v


@app.route("/lookml")
def lookml_page():
    return render_template("lookml.html")


@app.route("/lifelong")
def lifelong_page():
    return render_template("lifelong.html")


@app.route("/api/lookml/fields")
def api_lookml_fields():
    return jsonify(lookml_explorer().describe())


@app.route("/api/lookml/values")
def api_lookml_values():
    sql = lookml_explorer().distinct_values_sql(request.args.get("dimension", ""))
    rows = cached(("lookml-values", sql), lambda: run(sql))
    return jsonify([r["v"] for r in rows if r["v"] is not None])


@app.route("/api/lookml/query")
def api_lookml_query():
    filters = []
    for item in request.args.getlist("filter"):
        dim, _, value = item.partition(":")
        filters.append((dim, value))
    sql, params = lookml_explorer().compile(
        request.args.get("measure", ""), request.args.get("dimension") or None, filters
    )
    rows = run(sql, lookml_params(params))
    for r in rows:
        r["measure_value"] = jsonable(r["measure_value"])
    return jsonify({"sql": sql, "params": params, "rows": rows})


# ---- Dashboard built from a metrics file (no LookML) -----------------------------

def member_overview():
    if "overview" not in _lookml:
        table = os.environ.get("BQ_TABLES", "").split(",")[0].strip()
        _lookml["overview"] = overview.Overview(table)
    return _lookml["overview"]


def overview_filters():
    out = []
    for item in request.args.getlist("filter"):
        dim, _, value = item.partition(":")
        out.append((dim, value))
    return out


def overview_run(sql, params):
    key = ("overview", sql, tuple(sorted(params.items())))
    return cached(key, lambda: run(sql, lookml_params(params)))


@app.route("/overview")
def overview_page():
    return render_template("overview.html")


@app.route("/api/overview/config")
def api_overview_config():
    return jsonify(member_overview().config())


@app.route("/api/overview/kpis")
def api_overview_kpis():
    ov = member_overview()
    sql, params = ov.kpis(overview_filters())
    row = overview_run(sql, params)[0]
    suppressed = (row["_n"] or 0) < ov.min_size
    values = {k: (None if suppressed else jsonable(row[k])) for k in ov.dash["kpis"]}
    return jsonify({"values": values, "suppressed": suppressed, "sql": sql})


@app.route("/api/overview/grouped")
def api_overview_grouped():
    ov = member_overview()
    measures = [m for m in request.args.get("measures", "").split(",") if m]
    sql, params = ov.grouped(request.args.get("dimension", ""), measures, overview_filters())
    rows = overview_run(sql, params)
    return jsonify({"rows": [{k: jsonable(v) for k, v in r.items()} for r in rows], "sql": sql})


# ---- Wastewater surveillance (Sightline) ------------------------------------

def sightline_model():
    if "sightline" not in _lookml:
        _lookml["sightline"] = sightline.Sightline()
    return _lookml["sightline"]


def sl_args():
    a = request.args
    model = sightline_model()
    return {
        "preset": a.get("preset") or model.default_preset,
        "pathogen": a.get("pathogen") or None,
        "state": a.get("state") or None,
        "plant": a.get("plant") or None,
    }


def sl_run(sql, params):
    key = ("sightline", sql, tuple(sorted(params.items())))
    return cached(key, lambda: run(sql, lookml_params(params)))


def sl_rows(rows):
    return [{k: jsonable(v) for k, v in r.items()} for r in rows]


@app.route("/sightline")
def sightline_page():
    return render_template("sightline.html")


@app.route("/api/sightline/config")
def api_sl_config():
    return jsonify(sightline_model().config())


@app.route("/api/sightline/values")
def api_sl_values():
    sql, params = sightline_model().values(request.args.get("kind", ""))
    return jsonify([r["v"] for r in sl_run(sql, params)])


@app.route("/api/sightline/kpis")
def api_sl_kpis():
    sql, params = sightline_model().kpis(**sl_args())
    return jsonify({"row": sl_rows(sl_run(sql, params))[0], "sql": sql})


@app.route("/api/sightline/trend")
def api_sl_trend():
    a = sl_args()
    sql, params = sightline_model().trend(a["preset"], a["pathogen"], a["state"], a["plant"])
    return jsonify({"rows": sl_rows(sl_run(sql, params)), "sql": sql})


@app.route("/api/sightline/ranking")
def api_sl_ranking():
    a = sl_args()
    sql, params = sightline_model().ranking(a["preset"], a["pathogen"], a["state"])
    return jsonify({"rows": sl_rows(sl_run(sql, params)), "by": "plant" if a["state"] else "state", "sql": sql})


@app.route("/api/sightline/plants")
def api_sl_plants():
    a = sl_args()
    sql, params = sightline_model().plants(a["preset"], a["pathogen"], a["state"])
    return jsonify({"rows": sl_rows(sl_run(sql, params)), "sql": sql})


@app.route("/api/sightline/variants")
def api_sl_variants():
    a = sl_args()
    sql, params = sightline_model().variants(a["preset"], a["state"], a["plant"])
    return jsonify({"rows": sl_rows(sl_run(sql, params)), "sql": sql})


@app.route("/api/lifelong/config")
def api_lifelong_config():
    return jsonify(lifelong().config())


@app.route("/api/lifelong/values")
def api_lifelong_values():
    sql = lifelong().values_query(request.args.get("field", ""))
    rows = cached(("lifelong-values", sql), lambda: run(sql))
    return jsonify([r["v"] for r in rows if r["v"] is not None])


@app.route("/api/lifelong/tile")
def api_lifelong_tile():
    tile_id = int(request.args.get("id", "-1"))
    values = json.loads(request.args.get("filters", "{}"))
    if not 0 <= tile_id < len(lifelong().tiles):
        raise ValueError("Unknown tile")
    kind, columns, sql, params = lifelong().tile_query(tile_id, values)
    rows = cached(("tile", sql, tuple(sorted(params.items()))), lambda: run(sql, lookml_params(params)))
    if kind == "single_value":
        value = jsonable(rows[0]["m0"]) if rows else None
        return jsonify({"type": kind, "label": columns[0], "value": value, "sql": sql})
    if kind == "donut":
        row = rows[0] if rows else {}
        slices = [{"label": col, "value": jsonable(row.get(f"m{i}")) or 0} for i, col in enumerate(columns)]
        return jsonify({"type": kind, "slices": slices, "sql": sql})
    points = [{"x": r["d"], "y": jsonable(r["m0"])} for r in rows if r["d"] is not None]
    return jsonify({"type": kind, "label": columns[0], "points": points, "sql": sql})


@app.errorhandler(Exception)
def handle_error(e):
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code
    code = 400 if isinstance(e, (ValueError, lookml_engine.Unsupported)) else 500
    return jsonify({"error": str(e)}), code


if __name__ == "__main__":
    # host 0.0.0.0 is required for Workbench proxy access
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
