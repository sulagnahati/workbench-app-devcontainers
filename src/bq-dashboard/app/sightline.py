"""Wastewater surveillance dashboard built from a metrics spec (metrics/sightline.yml)."""
import os

import yaml

SPEC_PATH = os.path.join(os.path.dirname(__file__), "metrics", "sightline.yml")


class Sightline:
    def __init__(self, spec_path=SPEC_PATH):
        with open(spec_path) as f:
            self.spec = yaml.safe_load(f)
        src = self.spec["sources"]
        self.path = os.environ.get("SIGHTLINE_PATHOGEN_TABLE") or src["pathogens"]["table"]
        self.var = os.environ.get("SIGHTLINE_VARIANT_TABLE") or src["variants"]["table"]
        self.presets = {k: int(v["months"]) for k, v in self.spec["date_presets"].items()}
        self.default_preset = self.spec["default_preset"]
        self.m = self.spec["measures"]
        self.d = self.spec["dimensions"]
        self.min_samples = int(self.spec["min_samples_for_ranking"])

    def config(self):
        return {
            "title": self.spec["title"],
            "description": self.spec["description"],
            "presets": {k: v["label"] for k, v in self.spec["date_presets"].items()},
            "default_preset": self.default_preset,
            "default_pathogen": self.spec["default_pathogen"],
            "top_variants": int(self.spec["top_variants"]),
            "measures": {k: {"label": v["label"], "description": " ".join(v["description"].split())} for k, v in self.m.items()},
            "questions": self.spec["questions"],
        }

    # ---- helpers ---------------------------------------------------------

    def _since(self, preset):
        if preset not in self.presets:
            raise ValueError(f"Unknown date range: {preset}")
        return f"DATE_SUB(CURRENT_DATE(), INTERVAL {self.presets[preset]} MONTH)"

    def _r_where(self, preset, pathogen=None, state=None, plant=None):
        clauses = [f"{self.spec['sources']['pathogens']['date']} >= {self._since(preset)}"]
        params = {}
        for key, expr, value in (("pathogen", self.d["pathogen"]["sql"], pathogen),
                                 ("state", self.d["state"]["sql"], state),
                                 ("plant", self.d["plant"]["sql"], plant)):
            if value:
                clauses.append(f"{expr} = @{key}")
                params[key] = value
        return " AND ".join(clauses), params

    # ---- pathogen queries ------------------------------------------------

    def kpis(self, preset, pathogen, state, plant):
        where, params = self._r_where(preset, pathogen, state, plant)
        sql = (
            f"SELECT {self.m['plants_reporting']['sql']} AS plants, {self.m['samples']['sql']} AS samples, "
            f"CAST({self.m['latest_sample']['sql']} AS STRING) AS latest\n"
            f"FROM `{self.path}` AS r\nWHERE {where}"
        )
        return sql, params

    def trend(self, preset, pathogen, state=None, plant=None):
        if not pathogen:
            raise ValueError("pathogen is required")
        where, params = self._r_where(preset, pathogen, state, plant)
        sql = (
            f"SELECT CAST({self.d['week']['pathogens_sql']} AS STRING) AS d, "
            f"{self.m['pathogen_level']['sql']} AS level, {self.m['samples']['sql']} AS samples\n"
            f"FROM `{self.path}` AS r\nWHERE {where}\nGROUP BY d\nORDER BY d"
        )
        return sql, params

    def ranking(self, preset, pathogen, state=None):
        """Highest levels by state, or by plant once a state is chosen."""
        if not pathogen:
            raise ValueError("pathogen is required")
        dim = self.d["plant" if state else "state"]["sql"]
        where, params = self._r_where(preset, pathogen, state)
        sql = (
            f"SELECT {dim} AS d, {self.m['pathogen_level']['sql']} AS level, "
            f"{self.m['plants_reporting']['sql']} AS plants, {self.m['samples']['sql']} AS samples\n"
            f"FROM `{self.path}` AS r\nWHERE {where}\nGROUP BY d\n"
            f"HAVING samples >= {self.min_samples} AND d IS NOT NULL AND level IS NOT NULL\n"
            f"ORDER BY level DESC\nLIMIT 40"
        )
        return sql, params

    def plants(self, preset, pathogen, state=None):
        if not pathogen:
            raise ValueError("pathogen is required")
        where, params = self._r_where(preset, pathogen, state)
        sql = (
            f"SELECT r.plant_name AS name, ANY_VALUE(r.plant_state) AS state, ANY_VALUE(r.plant_latitude) AS lat, "
            f"ANY_VALUE(r.plant_longitude) AS lon, ANY_VALUE(r.plant_sewershed_population) AS population, "
            f"{self.m['pathogen_level']['sql']} AS level, {self.m['samples']['sql']} AS samples\n"
            f"FROM `{self.path}` AS r\nWHERE {where}\nGROUP BY name\n"
            f"HAVING samples >= {self.min_samples} AND level IS NOT NULL AND lat IS NOT NULL\nLIMIT 400"
        )
        return sql, params

    def values(self, kind, state=None):
        where, params = self._r_where("24m")
        if kind == "pathogen":
            sql = f"SELECT r.pathogen AS v, COUNT(*) AS n FROM `{self.path}` AS r WHERE {where} GROUP BY v ORDER BY n DESC"
        elif kind == "state":
            sql = f"SELECT r.plant_state AS v FROM `{self.path}` AS r WHERE {where} AND r.plant_state IS NOT NULL GROUP BY v ORDER BY v"
        else:
            raise ValueError(f"Unknown list: {kind}")
        return sql, params

    # ---- variant mix -----------------------------------------------------

    def variants(self, preset, state=None, plant=None):
        v = self.spec["sources"]["variants"]
        since = self._since(preset)
        params = {}
        join = ""
        where = [f"{v['date']} >= {since}"]
        if state or plant:
            # plant details live in the pathogen table; the recent-date filter keeps the scan small
            join = (
                f"\nJOIN (SELECT r.plant_code, ANY_VALUE(r.plant_state) AS plant_state, ANY_VALUE(r.plant_name) AS plant_name "
                f"FROM `{self.path}` AS r WHERE r.sample_collection_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 36 MONTH) "
                f"GROUP BY r.plant_code) AS p ON {v['plant_key']} = p.plant_code"
            )
            if state:
                where.append("p.plant_state = @state")
                params["state"] = state
            if plant:
                where.append("p.plant_name = @plant")
                params["plant"] = plant
        sql = (
            f"SELECT CAST({self.d['week']['variants_sql']} AS STRING) AS d, {self.d['lineage']['sql']} AS lineage, "
            f"{self.m['variant_share']['sql']} AS share\n"
            f"FROM `{self.var}` AS v{join}\nWHERE {' AND '.join(where)}\nGROUP BY d, lineage\nORDER BY d"
        )
        return sql, params
