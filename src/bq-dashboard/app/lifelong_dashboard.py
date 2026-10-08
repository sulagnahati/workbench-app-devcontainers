"""Tiles of the Looker lifelong dashboard, driven by its LookML dashboard file."""
import yaml

import lookml_engine as lk

DASHBOARD_FILE = "lifelong.dashboard.lookml"
# Interest + consent funnel tiles included in the proof of concept
TILE_TITLES = [
    "Total Lifelong Eligible",
    "Lifelong Interest Completion",
    "Interest Deferred",
    "Lifelong Non-Responders",
    "Lifelong Interest Rates",
    "Lifelong Interest Over Time",
    "Total Consent Eligible",
    "Lifelong Consent Completion",
    "Lifelong Consent Declined",
    "Lifelong Consent Proposed",
    "Lifelong Consent Draft",
    "Lifelong Consent Revoked",
    "Lifelong Consent Rates",
    "Lifelong Consented Over Time",
]
GRAIN_FILTER_FIELD = "dataset_config.global_time_grain_selector"
SUPPORTED_TYPES = {"single_value": "single_value", "looker_donut_multiples": "donut", "looker_line": "line"}


class Dashboard:
    def __init__(self, project):
        self.project = project
        with open(project._path(DASHBOARD_FILE)) as f:
            raw = yaml.safe_load(f)[0]
        self.title = raw.get("title", "")
        by_title = {e.get("title"): e for e in raw["elements"] if e.get("title")}
        self.tiles = []
        for title in TILE_TITLES:
            e = by_title.get(title)
            if e is None:
                continue
            self.tiles.append({
                "id": len(self.tiles),
                "title": title,
                "type": SUPPORTED_TYPES.get(e.get("type"), "unsupported"),
                "fields": [f for f in e.get("fields", []) if "." in f],
                "filters": e.get("filters") or {},
                "listen": e.get("listen") or {},
                "row": e.get("row", 0),
                "col": e.get("col", 0),
            })
        listened = {name for t in self.tiles for name in t["listen"]}
        self.filters = [
            {"name": f["name"], "field": f["field"], "default": str(f.get("default_value", "") or "")}
            for f in raw.get("filters", [])
            if f["name"] in listened
        ]

    def config(self):
        return {
            "title": self.title,
            "filters": self.filters,
            "tiles": [{k: t[k] for k in ("id", "title", "type", "row", "col")} for t in self.tiles],
        }

    # ---------------------------------------------------------------------

    def tile_query(self, tile_id, filter_values):
        """Return (kind, columns, sql, bq_params). Raises lk.Unsupported."""
        tile = self.tiles[tile_id]
        if tile["type"] == "unsupported":
            raise lk.Unsupported("tile type not supported")

        overrides, c_filters = {}, []
        for name, field in tile["listen"].items():
            value = filter_values.get(name, "")
            if field == GRAIN_FILTER_FIELD:
                if value:
                    overrides["global_time_grain_selector"] = value
            elif value:
                c_filters.append((field, value))
        for field, expr in tile["filters"].items():
            c_filters.append((field, expr))

        c = lk.Compiler(self.project, overrides)
        base = self.project.base_alias
        measures, dims = [], []
        for f in tile["fields"]:
            alias, _, name = f.partition(".")
            view = self.project.view_for_alias(alias)
            (measures if name in view.measures else dims).append((alias, name, view))

        select, columns = [], []
        for i, (alias, name, view) in enumerate(measures):
            select.append(f"{c.field_sql(alias, name)} AS m{i}")
            columns.append(lk.label_of(view.measures[name]))
        group = ""
        order = ""
        if tile["type"] == "line":
            if not dims or not measures:
                raise lk.Unsupported("line tile needs one dimension and one measure")
            alias, name, _ = dims[0]
            select.insert(0, f"CAST({c.field_sql(alias, name)} AS STRING) AS d")
            group, order = "d", "d"
        elif dims:
            raise lk.Unsupported("tile groups by a dimension but is not a line chart")

        where = [c.condition(base, field, expr, use_params=True) for field, expr in c_filters]
        sql = c.assemble(select, where, group, order, limit=1000 if group else 1)
        return tile["type"], columns, sql, c.bq_params
