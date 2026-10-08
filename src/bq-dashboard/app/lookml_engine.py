"""Compile LookML explores into BigQuery SQL.

Reads view files and the shared explore joins from a checkout of the LookML repo
(see sync-lookml.sh) and generates SQL for measures and dimensions across joined
views. Anything it cannot translate faithfully (unknown Liquid, missing views, unknown
filter syntax) raises Unsupported with a reason, instead of being approximated.
"""
import os
import re
import urllib.error
import urllib.request

import lkml

LOOKML_REPO = os.environ.get("LOOKML_REPO", "verily-src/analytics-internal-looker")
LOOKML_BRANCH = os.environ.get("LOOKML_BRANCH", "main")
EXPLORE_FILE = "models/_common_joins.explore.lkml"

REF = re.compile(r"\$\{([^}]+)\}")
TABLE_REF = re.compile(
    r"`\{\{[^}]*storage_project_id[^}]*\}\}\.\{\{[^}]*dataset_name[^}]*\}\}\."
    r"(?:\{\{[^}]*table_prefix[^}]*\}\})?(\w+)\{\{[^}]*table_suffix[^}]*\}\}`"
)
TAG = re.compile(r"(\{%-?.*?-?%\})", re.S)
TAG_INNER = re.compile(r"\{%(-?)\s*(.*?)\s*(-?)%\}", re.S)
COND = re.compile(r"""^([\w.]+)\s*(==|!=)\s*["']([^"']*)["']$""")
DATE_RE = r"(\d{4})/(\d{2})/(\d{2})"

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
JOIN_KEYWORDS = {
    "left_outer": "LEFT JOIN",
    "inner": "INNER JOIN",
    "full_outer": "FULL OUTER JOIN",
    "cross": "CROSS JOIN",
}


class Unsupported(Exception):
    pass


def sql_str(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def label_of(field):
    return field.get("label") or field["name"].replace("_", " ").title()


# --------------------------------------------------------------------------
# Project: files, views, joins, table naming
# --------------------------------------------------------------------------

class Project:
    def __init__(self, root=None, storage_project=None, dataset=None, suffix="", prefix="", model_name=""):
        self.root = root or os.environ.get("LOOKML_DIR") or os.path.join(os.path.dirname(__file__), "lookml")
        self.storage_project = storage_project
        self.dataset = dataset
        self.suffix = suffix
        self.prefix = prefix
        self.model_name = model_name
        self._views = {}
        self._table_sql = {}
        self._parse_explore()
        self._global_params = self._load_global_params()

    # files ---------------------------------------------------------------

    def _path(self, rel):
        path = os.path.join(self.root, rel)
        if os.path.exists(path):
            return path
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise Unsupported(
                f"{rel} not found in {self.root}. Run ./sync-lookml.sh, or set GITHUB_TOKEN so the app "
                "can download it from GitHub."
            )
        url = f"https://api.github.com/repos/{LOOKML_REPO}/contents/{rel}?ref={LOOKML_BRANCH}"
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            raise Unsupported(f"could not download {rel}: HTTP {e.code}") from e
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(body)
        return path

    def read_lkml(self, rel):
        with open(self._path(rel)) as f:
            return lkml.load(f)

    # explore -------------------------------------------------------------

    def _parse_explore(self):
        explore = self.read_lkml(EXPLORE_FILE)["explores"][0]
        self.joins = {}
        self.join_order = []
        self.base_alias = None
        for j in explore.get("joins", []):
            if j["name"] == "table_config":
                continue
            if self.base_alias is None and j.get("sql_on", "").strip() == "1=1":
                self.base_alias = j["name"]
            self.joins[j["name"]] = j
            self.join_order.append(j["name"])

    def _load_global_params(self):
        params = {}
        try:
            parsed = self.read_lkml("views/_shared_logic.view.lkml")
        except Unsupported:
            return params
        for v in parsed.get("views", []):
            if v["name"] == "dataset_config":
                for p in v.get("parameters", []):
                    params[p["name"]] = p
        return params

    # views ---------------------------------------------------------------

    def view_for_alias(self, alias):
        join = self.joins.get(alias)
        if join is None:
            raise Unsupported(f"needs join to view '{alias}'")
        return self.view(join.get("from") or alias)

    def view(self, name):
        if name not in self._views:
            parsed = self.read_lkml(f"views/{name}.view.lkml")
            raw = next((v for v in parsed.get("views", []) if v["name"] == name), None)
            if raw is None:
                raise Unsupported(f"view {name} not found")
            self._views[name] = ViewDef(raw)
        return self._views[name]

    def table_sql(self, view_name):
        """SQL for the view's table or derived table, usable after FROM/JOIN."""
        if view_name in self._table_sql:
            return self._table_sql[view_name]
        raw = self.view(view_name).raw

        def concrete(m):
            return f"`{self.storage_project}.{self.dataset}.{self.prefix}{m.group(1)}{self.suffix}`"

        if raw.get("sql_table_name"):
            sql = TABLE_REF.sub(concrete, raw["sql_table_name"])
            wrapped = sql.strip()
        elif raw.get("derived_table", {}).get("sql"):
            sql = TABLE_REF.sub(concrete, raw["derived_table"]["sql"])
            sql = REF.sub(self._sql_table_name_ref, sql)
            wrapped = f"(\n{sql.strip()}\n)"
        else:
            raise Unsupported(f"view {view_name} has no table definition")
        if "{{" in wrapped or "{%" in wrapped:
            raise Unsupported(f"view {view_name} table uses Liquid templating")
        self._table_sql[view_name] = wrapped
        return wrapped

    def concretize_tables(self, sql):
        return TABLE_REF.sub(
            lambda m: f"`{self.storage_project}.{self.dataset}.{self.prefix}{m.group(1)}{self.suffix}`", sql
        )

    def _sql_table_name_ref(self, m):
        ref = m.group(1).strip()
        if ref.endswith(".SQL_TABLE_NAME"):
            return self.table_sql(ref.split(".")[0])
        raise Unsupported(f"unsupported reference {ref} in derived table")

    # liquid --------------------------------------------------------------

    def render_liquid(self, text, view, overrides):
        parts = TAG.split(text)
        out = []
        stack = []
        active = True
        trim_next = False
        for part in parts:
            m = TAG_INNER.fullmatch(part) if part.startswith("{%") else None
            if m is None:
                if trim_next:
                    part = part.lstrip()
                    trim_next = False
                if active:
                    out.append(part)
                continue
            left_trim, tag, right_trim = m.groups()
            if left_trim and out:
                out[-1] = out[-1].rstrip()
            trim_next = bool(right_trim)
            if tag.startswith("if "):
                cond = active and self._cond(tag[3:], view, overrides)
                stack.append({"parent": active, "taken": cond})
                active = cond
            elif tag.startswith("elsif "):
                s = stack[-1]
                cond = s["parent"] and not s["taken"] and self._cond(tag[6:], view, overrides)
                s["taken"] = s["taken"] or cond
                active = cond
            elif tag == "else":
                s = stack[-1]
                active = s["parent"] and not s["taken"]
                s["taken"] = True
            elif tag == "endif":
                active = stack.pop()["parent"]
            elif tag.startswith("parameter "):
                if active:
                    out.append(self._param_sql(tag[10:].strip(), view, overrides))
            else:
                raise Unsupported(f"unsupported Liquid tag: {tag[:40]}")
        text = "".join(out)
        if "{{" in text or "{%" in text:
            raise Unsupported("uses Liquid templating or parameters")
        return text

    def _cond(self, cond, view, overrides):
        m = COND.match(cond.strip())
        if not m:
            raise Unsupported(f"unsupported Liquid condition: {cond[:50]}")
        left, op, right = m.groups()
        if left == "_model._name":
            actual = self.model_name
        elif left.endswith("._parameter_value"):
            actual = self._param_value(left[: -len("._parameter_value")], view, overrides)[0]
        else:
            raise Unsupported(f"unsupported Liquid condition: {cond[:50]}")
        return (actual == right) == (op == "==")

    def _param_value(self, ref, view, overrides):
        name = ref.split(".")[-1]
        pdef = view.parameters.get(name) or self._global_params.get(name)
        if pdef is None and name not in overrides:
            raise Unsupported(f"unknown parameter {name}")
        value = overrides.get(name)
        if value is None:
            value = (pdef or {}).get("default_value", "")
        return str(value), (pdef or {}).get("type", "string")

    def _param_sql(self, ref, view, overrides):
        value, ptype = self._param_value(ref, view, overrides)
        if ptype == "unquoted":
            if not re.fullmatch(r"\w*", value):
                raise Unsupported("invalid unquoted parameter value")
            return value
        return sql_str(value)


class ViewDef:
    def __init__(self, raw):
        self.raw = raw
        self.name = raw["name"]
        self.dimensions = {}
        self.measures = {}
        self.parameters = {p["name"]: p for p in raw.get("parameters", [])}
        self.skipped = []
        for d in raw.get("dimensions", []):
            self.dimensions[d["name"]] = dict(d, kind="dimension")
        for g in raw.get("dimension_groups", []):
            if g.get("type") != "time":
                self.skipped.append((g["name"], "dimension_group", f"type {g.get('type')}"))
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


# --------------------------------------------------------------------------
# Compiler: one query
# --------------------------------------------------------------------------

class Compiler:
    """Builds one query. Resolve fields first, then call assemble()."""

    def __init__(self, project, overrides=None):
        self.project = project
        self.overrides = overrides or {}
        self.used = {}  # alias -> None (ordered set)
        self.bq_params = {}
        self._inline = True

    # field resolution ----------------------------------------------------

    def field_sql(self, alias, name, _stack=()):
        """SQL for a dimension or measure of the view joined as `alias`."""
        view = self.project.view_for_alias(alias)
        self.used[alias] = None
        if name in view.measures:
            return self._measure_sql(alias, view, name, _stack)
        if name in view.dimensions:
            return self._dimension_sql(alias, view, name, _stack)
        raise Unsupported(f"unknown field {alias}.{name}")

    def _substitute(self, sql, alias, key, _stack):
        def sub(m):
            ref = m.group(1).strip()
            if ref == "TABLE":
                return alias
            if ref.endswith(".SQL_TABLE_NAME") or ref.upper() == "SQL_TABLE_NAME":
                raise Unsupported("references another view's table")
            if "." in ref:
                a, _, f = ref.partition(".")
                return f"({self.field_sql(a, f, _stack + (key,))})"
            return f"({self.field_sql(alias, ref, _stack + (key,))})"

        return REF.sub(sub, sql)

    def _rendered(self, field, view):
        sql = field.get("sql", "")
        if not sql:
            return ""
        return self.project.render_liquid(self.project.concretize_tables(sql), view, self.overrides)

    def _dimension_sql(self, alias, view, name, _stack):
        key = (alias, name)
        if key in _stack:
            raise Unsupported("circular reference")
        field = view.dimensions[name]
        sql = self._substitute(self._rendered(field, view), alias, key, _stack)
        if field.get("type") == "time":
            sql = TIMEFRAME_SQL[field["timeframe"]].format(e=f"({sql})")
        return sql

    def _measure_sql(self, alias, view, name, _stack):
        key = (alias, name)
        if key in _stack:
            raise Unsupported("circular reference")
        m = view.measures[name]
        mtype = m.get("type")
        sql = self._substitute(self._rendered(m, view), alias, key, _stack)
        cond = self._measure_filters(alias, m)

        def guarded(expr):
            return f"IF({cond}, {expr}, NULL)" if cond else expr

        if mtype == "count":
            if alias == self.project.base_alias:
                return f"COUNTIF({cond})" if cond else "COUNT(*)"
            # Looker counts distinct primary keys so joined rows are not double counted
            pk = next((n for n, d in view.dimensions.items() if d.get("primary_key") == "yes"), None)
            if pk is None:
                raise Unsupported("count over a joined view needs a primary key")
            return f"COUNT(DISTINCT {guarded(self._dimension_sql(alias, view, pk, _stack + (key,)))})"
        if mtype == "count_distinct":
            return f"COUNT(DISTINCT {guarded(sql)})"
        if mtype in AGGREGATES:
            return f"{AGGREGATES[mtype]}({guarded(sql)})"
        if mtype == "number":
            return sql
        if mtype in ("date", "string") and sql:
            return sql
        raise Unsupported(f"measure type {mtype}")

    def _measure_filters(self, alias, m):
        pairs = [(k, v) for group in m.get("filters__all", []) for item in group for k, v in item.items()]
        if not pairs:
            return ""
        saved, self._inline = self._inline, True
        try:
            return " AND ".join(self.condition(alias, k, v) for k, v in pairs)
        finally:
            self._inline = saved

    # filters -------------------------------------------------------------

    def condition(self, alias, field_ref, expression, use_params=False):
        """SQL condition for a Looker filter expression on a field."""
        a, f = (field_ref.split(".", 1) + [None])[:2] if "." in field_ref else (alias, field_ref)
        view = self.project.view_for_alias(a)
        dim = view.dimensions.get(f)
        if dim is None:
            raise Unsupported(f"filter on unknown field {field_ref}")
        expr = f"({self.field_sql(a, f)})"
        saved, self._inline = self._inline, not use_params
        try:
            return self._filter_sql(expr, self._ftype(dim), str(expression).strip())
        finally:
            self._inline = saved

    @staticmethod
    def _ftype(dim):
        t = dim.get("type", "string")
        if t == "time":
            return "timestamp" if dim.get("timeframe") in ("raw", "time") else "date"
        if t in ("date_time",):
            return "timestamp"
        return t

    def _lit(self, value):
        if self._inline:
            return sql_str(value)
        name = f"p{len(self.bq_params)}"
        self.bq_params[name] = value
        return f"@{name}"

    def _filter_sql(self, expr, ftype, v):
        if ftype == "yesno":
            if v.lower() == "yes":
                return f"COALESCE({expr}, FALSE)"
            if v.lower() == "no":
                return f"NOT COALESCE({expr}, FALSE)"
            raise Unsupported(f"unsupported yesno filter: {v}")
        if v == "NULL":
            return f"{expr} IS NULL"
        if v == "-NULL":
            return f"{expr} IS NOT NULL"
        if ftype in ("date", "timestamp"):
            return self._date_filter(f"DATE({expr})", v)
        if ftype == "number":
            m = re.fullmatch(r"(<=|>=|<|>|=)?\s*(-?\d+(\.\d+)?)", v)
            if not m:
                raise Unsupported(f"unsupported number filter: {v}")
            return f"{expr} {m.group(1) or '='} {m.group(2)}"
        m = re.fullmatch(r"(<=|>=|<|>)\s*(-?\d+(\.\d+)?)", v)
        if m:  # numeric comparison on a string-typed numeric column
            return f"SAFE_CAST({expr} AS FLOAT64) {m.group(1)} {m.group(2)}"
        values = self._split_values(v)
        if not values:
            return "TRUE"
        positives = [x for x in values if not x.startswith("-")]
        negatives = [x[1:] for x in values if x.startswith("-")]
        parts = []
        text = f"CAST({expr} AS STRING)"
        if positives:
            parts.append("(" + " OR ".join(self._match(text, x) for x in positives) + ")")
        for x in negatives:
            parts.append(f"NOT COALESCE({self._match(text, x)}, FALSE)")
        return " AND ".join(parts)

    def _match(self, text, value):
        if "%" in value:
            return f"{text} LIKE {self._lit(value)}"
        return f"{text} = {self._lit(value)}"

    @staticmethod
    def _split_values(v):
        values, cur, quoted = [], "", False
        for ch in v:
            if ch == '"':
                quoted = not quoted
            elif ch == "," and not quoted:
                values.append(cur.strip())
                cur = ""
            else:
                cur += ch
        values.append(cur.strip())
        return [x for x in values if x]

    @staticmethod
    def _date_filter(date_expr, v):
        def d(y, mo, da):
            return f"DATE('{y}-{mo}-{da}')"

        m = re.fullmatch(rf"after {DATE_RE}", v)
        if m:
            return f"{date_expr} >= {d(*m.groups())}"
        m = re.fullmatch(rf"before {DATE_RE}", v)
        if m:
            return f"{date_expr} < {d(*m.groups())}"
        m = re.fullmatch(rf"{DATE_RE} to {DATE_RE}", v)
        if m:
            g = m.groups()
            return f"{date_expr} >= {d(*g[:3])} AND {date_expr} < {d(*g[3:])}"
        m = re.fullmatch(DATE_RE, v)
        if m:
            return f"{date_expr} = {d(*m.groups())}"
        m = re.fullmatch(r"(\d+) days?", v)
        if m:
            return f"{date_expr} >= DATE_SUB(CURRENT_DATE(), INTERVAL {int(m.group(1))} DAY)"
        raise Unsupported(f"unsupported date filter: {v}")

    # query assembly ------------------------------------------------------

    def assemble(self, select, where=(), group="", order="", limit=100):
        base = self.project.base_alias
        self.used.setdefault(base, None)
        joins = {}
        changed = True
        while changed:
            changed = False
            for alias in list(self.used):
                if alias == base or alias in joins:
                    continue
                j = self.project.joins.get(alias)
                if j is None:
                    raise Unsupported(f"needs join to view '{alias}'")
                on = self._substitute(self.project.render_liquid(j["sql_on"], self.project.view_for_alias(alias), self.overrides), alias, ("join", alias), ())
                joins[alias] = (j, on)
                changed = True
        from_sql = f"FROM {self.project.table_sql(self.project.joins[base].get('from') or base)} AS {base}"
        for alias in self.project.join_order:
            if alias in joins:
                j, on = joins[alias]
                kw = JOIN_KEYWORDS.get(j.get("type", "left_outer"), "LEFT JOIN")
                table = self.project.table_sql(j.get("from") or alias)
                from_sql += f"\n{kw} {table} AS {alias}\n  ON {on}"
        sql = f"SELECT {', '.join(select)}\n{from_sql}"
        if where:
            sql += "\nWHERE " + "\n  AND ".join(f"({w})" for w in where)
        if group:
            sql += f"\nGROUP BY {group}"
        if order:
            sql += f"\nORDER BY {order}"
        if limit:
            sql += f"\nLIMIT {int(limit)}"
        return sql


# --------------------------------------------------------------------------
# Explorer: group a measure of the base view by one of its dimensions
# --------------------------------------------------------------------------

class Explorer:
    def __init__(self, project):
        self.project = project
        self.base = project.base_alias
        self.view = project.view_for_alias(self.base)
        self.supported_dimensions, self.supported_measures, self.unsupported = {}, {}, []
        for name, f in self.view.dimensions.items():
            self._probe(name, f, self.supported_dimensions, "dimension")
        for name, f in self.view.measures.items():
            self._probe(name, f, self.supported_measures, "measure")
        self.unsupported += [(n, k, r) for n, k, r in self.view.skipped]

    def _probe(self, name, field, bucket, kind):
        try:
            c = Compiler(self.project)
            sql = c.field_sql(self.base, name)
            c.assemble([f"{sql} AS x"], limit=1)
            bucket[name] = field
        except Unsupported as e:
            self.unsupported.append((name, kind, str(e)))

    def describe(self):
        def meta(f):
            return {
                "name": f["name"],
                "label": label_of(f),
                "group": f.get("group_label", ""),
                "type": f.get("type"),
                "description": f.get("description", ""),
            }

        return {
            "view": self.base,
            "dimensions": [meta(f) for f in self.supported_dimensions.values() if not f.get("hidden")],
            "measures": [meta(f) for f in self.supported_measures.values() if not f.get("hidden")],
            "unsupported": [{"name": n, "kind": k, "reason": r} for n, k, r in self.unsupported],
        }

    def _check_dim(self, dim):
        if dim not in self.supported_dimensions or self.view.dimensions[dim].get("hidden"):
            raise ValueError(f"Unsupported dimension: {dim}")

    def _dim_select(self, c, dim):
        expr = c.field_sql(self.base, dim)
        t = self.view.dimensions[dim].get("type", "string")
        if t == "yesno":
            return f"IF(COALESCE({expr}, FALSE), 'Yes', 'No')"
        return f"CAST({expr} AS STRING)"

    def compile(self, measure, dimension, filters, limit=100):
        if measure not in self.supported_measures:
            raise ValueError(f"Unsupported measure: {measure}")
        c = Compiler(self.project)
        select = [f"{c.field_sql(self.base, measure)} AS measure_value"]
        group, order = "", "measure_value DESC"
        if dimension:
            self._check_dim(dimension)
            select.insert(0, f"{self._dim_select(c, dimension)} AS dimension_value")
            group = "dimension_value"
            if self.view.dimensions[dimension].get("type") == "time":
                order = "dimension_value"
        where = []
        for dim, value in filters:
            self._check_dim(dim)
            where.append(self._eq(c, dim, value))
        sql = c.assemble(select, where, group, order, limit)
        return sql, c.bq_params

    def _eq(self, c, dim, value):
        c._inline = False
        try:
            return f"{self._dim_select(c, dim)} = {c._lit(value)}"
        finally:
            c._inline = True

    def distinct_values_sql(self, dim, limit=51):
        self._check_dim(dim)
        if self.view.dimensions[dim].get("type") == "time":
            raise ValueError("Time dimensions are not filterable here")
        c = Compiler(self.project)
        return c.assemble([f"{self._dim_select(c, dim)} AS v"], group="v", order="v", limit=limit)


# --------------------------------------------------------------------------
# Construction from environment
# --------------------------------------------------------------------------

def project_from_env():
    first = os.environ.get("BQ_TABLES", "").split(",")[0].strip()
    parts = first.split(".")
    if len(parts) != 3:
        raise Unsupported("BQ_TABLES must start with project.dataset.table")
    project, dataset, table = parts
    suffix = os.environ.get("LOOKML_TABLE_SUFFIX")
    if suffix is None:
        suffix = table[len("patient_gold_latest"):] if table.startswith("patient_gold_latest") else ""
    return Project(
        storage_project=os.environ.get("LOOKML_STORAGE_PROJECT", project),
        dataset=os.environ.get("LOOKML_DATASET", dataset),
        suffix=suffix,
        prefix=os.environ.get("LOOKML_TABLE_PREFIX", ""),
        model_name=os.environ.get("LOOKML_MODEL_NAME", "basevalue_lifelong_data"),
    )
