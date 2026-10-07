"""Compile LookML view definitions into BigQuery SQL.

Scope: a single view at a time. Fields that need joins to other views, Liquid
templating beyond `_model._name` conditionals, or parameters are reported as
unsupported (with a reason) instead of being silently approximated.
"""
import os
import re
import urllib.error
import urllib.request

import lkml

LIQUID_IF = re.compile(
    r"\{%\s*if\s+_model\._name\s*(==|!=)\s*'([^']*)'\s*%\}(.*?)"
    r"(?:\{%\s*else\s*%\}(.*?))?\{%\s*endif\s*%\}",
    re.S,
)
REF = re.compile(r"\$\{([^}]+)\}")
TABLE_REF = re.compile(r"`\{\{[^`]*\}\}`")

TIMEFRAME_SQL = {
    "raw": "{e}",
    "time": "TIMESTAMP({e})",
    "date": "DATE({e})",
    "week": "DATE_TRUNC(DATE({e}), WEEK(MONDAY))",
    "month": "DATE_TRUNC(DATE({e}), MONTH)",
    "quarter": "DATE_TRUNC(DATE({e}), QUARTER)",
    "year": "DATE_TRUNC(DATE({e}), YEAR)",
}
AGGREGATES = {"sum": "SUM", "average": "AVG", "min": "MIN", "max": "MAX"}


class Unsupported(Exception):
    pass


class View:
    def __init__(self, path, table, model_name):
        with open(path) as f:
            parsed = lkml.load(f)
        raw = parsed["views"][0]
        self.name = raw["name"]
        self.model_name = model_name
        self.table_sql = self._table_sql(raw.get("sql_table_name", ""), table)
        self.dimensions = {}
        self.measures = {}
        self.unsupported = []  # (name, kind, reason)

        for d in raw.get("dimensions", []):
            self.dimensions[d["name"]] = dict(d, kind="dimension")
        for g in raw.get("dimension_groups", []):
            if g.get("type") != "time":
                self.unsupported.append((g["name"], "dimension_group", f"type {g.get('type')}"))
                continue
            for tf in g.get("timeframes", ["raw", "date", "week", "month", "quarter", "year", "time"]):
                if tf not in TIMEFRAME_SQL:
                    continue
                name = f"{g['name']}_{tf}"
                self.dimensions[name] = dict(
                    g, name=name, kind="dimension", type="time", timeframe=tf,
                    label=f"{g.get('label', g['name'])} ({tf})",
                )
        for m in raw.get("measures", []):
            self.measures[m["name"]] = dict(m, kind="measure")

        self._classify()

    def _table_sql(self, sql_table_name, table):
        s = sql_table_name.strip()
        if "`" not in s and "{{" not in s:
            return f"`{s}`" if s else f"`{table}`"
        # Keep the view's own filtering (e.g. excluded ids); only point the
        # templated table reference at the real BigQuery table.
        return TABLE_REF.sub(f"`{table}`", s)

    # ---- SQL resolution -------------------------------------------------

    def _liquid(self, sql):
        def repl(m):
            op, model, then, other = m.groups()
            hit = (self.model_name == model) == (op == "==")
            return then if hit else (other or "")

        sql = LIQUID_IF.sub(repl, sql)
        if "{%" in sql or "{{" in sql:
            raise Unsupported("uses Liquid templating or parameters")
        return sql

    def resolve(self, name, _stack=()):
        """Return the SQL expression for a dimension or measure of this view."""
        if name in _stack:
            raise Unsupported("circular reference")
        field = self.dimensions.get(name) or self.measures.get(name)
        if field is None:
            raise Unsupported(f"unknown field {name}")
        sql = self._liquid(field.get("sql", "")) if field.get("sql") else ""

        def sub(m):
            ref = m.group(1).strip()
            if ref == "TABLE":
                return self.name
            if "." in ref:
                view, _, ref = ref.partition(".")
                if view != self.name:
                    raise Unsupported(f"needs join to view '{view}'")
            elif ref.upper() == "SQL_TABLE_NAME":
                raise Unsupported("references another view's table")
            return f"({self.resolve(ref, _stack + (name,))})"

        sql = REF.sub(sub, sql)

        if field["kind"] == "dimension":
            if field.get("type", "string") == "time":
                sql = TIMEFRAME_SQL[field["timeframe"]].format(e=f"({sql})")
            return sql
        return sql

    # ---- Measures -------------------------------------------------------

    def _condition(self, dim_name, value, params):
        d = self.dimensions.get(dim_name)
        if d is None:
            raise Unsupported(f"filter on unknown field {dim_name}")
        expr = f"({self.resolve(dim_name)})"
        v = str(value).strip()
        if d.get("type") == "yesno":
            if v.lower() == "yes":
                return f"COALESCE({expr}, FALSE)"
            if v.lower() == "no":
                return f"NOT COALESCE({expr}, FALSE)"
        if v == "-NULL":
            return f"{expr} IS NOT NULL"
        if v == "NULL":
            return f"{expr} IS NULL"
        m = re.fullmatch(r"(<=|>=|<|>)\s*(-?\d+(\.\d+)?)", v)
        if m:
            return f"{expr} {m.group(1)} {m.group(2)}"
        values = [x.strip() for x in v.split(",")]
        names = []
        for x in values:
            names.append(params.add(x))
        return f"CAST({expr} AS STRING) IN ({', '.join(names)})"

    def measure_sql(self, name, params):
        m = self.measures[name]
        mtype = m.get("type")
        sql = self.resolve(name) if m.get("sql") else ""
        filters = [
            (k, v)
            for group in m.get("filters__all", [])
            for item in group
            for k, v in item.items()
        ]
        cond = " AND ".join(self._condition(k, v, params) for k, v in filters)

        def guarded(expr):
            return f"IF({cond}, {expr}, NULL)" if cond else expr

        if mtype == "count":
            return f"COUNTIF({cond})" if cond else "COUNT(*)"
        if mtype == "count_distinct":
            return f"COUNT(DISTINCT {guarded(sql)})"
        if mtype in AGGREGATES:
            return f"{AGGREGATES[mtype]}({guarded(sql)})"
        if mtype == "number":
            # Expression over other measures: resolve measure refs to aggregates
            return self._number_sql(name, params)
        raise Unsupported(f"measure type {mtype}")

    def _number_sql(self, name, params, _stack=()):
        m = self.measures[name]
        if name in _stack:
            raise Unsupported("circular reference")
        sql = self._liquid(m.get("sql", ""))

        def sub(mm):
            ref = mm.group(1).strip()
            if "." in ref:
                view, _, ref = ref.partition(".")
                if view != self.name:
                    raise Unsupported(f"needs join to view '{view}'")
            if ref in self.measures:
                if self.measures[ref].get("type") == "number":
                    return f"({self._number_sql(ref, params, _stack + (name,))})"
                return f"({self.measure_sql(ref, params)})"
            if ref in self.dimensions:
                return f"({self.resolve(ref)})"
            raise Unsupported(f"unknown field {ref}")

        return REF.sub(sub, sql)

    # ---- Support check & metadata --------------------------------------

    def _classify(self):
        probe = _Params()
        self.supported_dimensions, self.supported_measures = {}, {}
        for name in self.dimensions:
            try:
                self.resolve(name)
                self.supported_dimensions[name] = self.dimensions[name]
            except Unsupported as e:
                self.unsupported.append((name, "dimension", str(e)))
        for name in self.measures:
            try:
                self.measure_sql(name, probe)
                self.supported_measures[name] = self.measures[name]
            except Unsupported as e:
                self.unsupported.append((name, "measure", str(e)))

    def describe(self):
        def meta(f):
            return {
                "name": f["name"],
                "label": f.get("label") or f["name"].replace("_", " ").title(),
                "group": f.get("group_label", ""),
                "type": f.get("type"),
                "description": f.get("description", ""),
            }

        return {
            "view": self.name,
            "dimensions": [meta(f) for f in self.supported_dimensions.values() if not f.get("hidden")],
            "measures": [meta(f) for f in self.supported_measures.values() if not f.get("hidden")],
            "unsupported": [{"name": n, "kind": k, "reason": r} for n, k, r in self.unsupported],
        }

    # ---- Query compilation ---------------------------------------------

    def compile(self, measure, dimension, filters, limit=100):
        """filters: list of (dimension_name, value). Returns (sql, params)."""
        if measure not in self.supported_measures:
            raise ValueError(f"Unsupported measure: {measure}")
        if dimension and (dimension not in self.supported_dimensions or self.dimensions[dimension].get("hidden")):
            raise ValueError(f"Unsupported dimension: {dimension}")
        params = _Params()
        m_sql = self.measure_sql(measure, params)

        select = [f"{m_sql} AS measure_value"]
        group = ""
        order = "measure_value DESC"
        if dimension:
            d_expr = self._dimension_select(dimension)
            select.insert(0, f"{d_expr} AS dimension_value")
            group = "GROUP BY dimension_value"
            if self.dimensions[dimension].get("type") == "time":
                order = "dimension_value"

        where = []
        for dim, value in filters:
            if dim not in self.supported_dimensions or self.dimensions[dim].get("hidden"):
                raise ValueError(f"Unsupported filter: {dim}")
            where.append(self._user_filter(dim, value, params))
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        sql = (
            f"SELECT {', '.join(select)}\n"
            f"FROM {self.table_sql} AS {self.name}\n"
            f"{where_sql}\n{group}\nORDER BY {order}\nLIMIT {int(limit)}"
        )
        return sql, params.items

    def _dimension_select(self, dim):
        expr = self.resolve(dim)
        t = self.dimensions[dim].get("type", "string")
        if t == "yesno":
            return f"IF(COALESCE({expr}, FALSE), 'Yes', 'No')"
        if t == "time":
            return f"CAST({expr} AS STRING)"
        return f"CAST({expr} AS STRING)"

    def _user_filter(self, dim, value, params):
        expr = self.resolve(dim)
        if self.dimensions[dim].get("type") == "yesno":
            return f"IF(COALESCE({expr}, FALSE), 'Yes', 'No') = {params.add(value)}"
        return f"CAST({expr} AS STRING) = {params.add(value)}"

    def distinct_values_sql(self, dim, limit=51):
        if dim not in self.supported_dimensions or self.dimensions[dim].get("hidden"):
            raise ValueError(f"Unsupported dimension: {dim}")
        if self.dimensions[dim].get("type") == "time":
            raise ValueError("Time dimensions are not filterable here")
        return (
            f"SELECT {self._dimension_select(dim)} AS v FROM {self.table_sql} AS {self.name} "
            f"GROUP BY v ORDER BY v LIMIT {limit}"
        )


class _Params:
    """Collects values as BigQuery named parameters; returns the @name to use in SQL."""

    def __init__(self):
        self.items = {}

    def add(self, value):
        key = f"p{len(self.items)}"
        self.items[key] = value
        return f"@{key}"


LOOKML_REPO = os.environ.get("LOOKML_REPO", "verily-src/analytics-internal-looker")
LOOKML_BRANCH = os.environ.get("LOOKML_BRANCH", "main")


def _ensure_view_file(view_name):
    """Return the path to the view file, downloading it from GitHub if it isn't present.

    The LookML is not bundled in this repo. Locally, run ./sync-lookml.sh. In a deployed
    app, set GITHUB_TOKEN to a token with read access to LOOKML_REPO.
    """
    directory = os.environ.get("LOOKML_DIR") or os.path.join(os.path.dirname(__file__), "lookml")
    path = os.path.join(directory, f"{view_name}.view.lkml")
    if os.path.exists(path):
        return path
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise FileNotFoundError(
            f"{view_name}.view.lkml not found in {directory}. Run ./sync-lookml.sh, "
            "or set GITHUB_TOKEN so the app can download it from GitHub."
        )
    url = f"https://api.github.com/repos/{LOOKML_REPO}/contents/views/{view_name}.view.lkml?ref={LOOKML_BRANCH}"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Could not download {view_name} from {LOOKML_REPO}: HTTP {e.code}") from e
    os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    return path


def load_view(view_name="patient_gold_latest"):
    table = os.environ.get("LOOKML_TABLE") or os.environ.get("BQ_TABLES", "").split(",")[0].strip()
    model = os.environ.get("LOOKML_MODEL_NAME", "verilyme_self_serve")
    return View(_ensure_view_file(view_name), table, model)
