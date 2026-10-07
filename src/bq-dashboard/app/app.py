import os
import threading
import time

from werkzeug.exceptions import HTTPException
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from google.cloud import bigquery

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


@app.errorhandler(Exception)
def handle_error(e):
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code
    code = 400 if isinstance(e, ValueError) else 500
    return jsonify({"error": str(e)}), code


if __name__ == "__main__":
    # host 0.0.0.0 is required for Workbench proxy access
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
