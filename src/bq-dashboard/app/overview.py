"""Dashboard built from a metrics spec (metrics/patient_overview.yml) instead of LookML."""
import os

import yaml

SPEC_PATH = os.path.join(os.path.dirname(__file__), "metrics", "patient_overview.yml")


class Overview:
    def __init__(self, table, spec_path=SPEC_PATH):
        with open(spec_path) as f:
            self.spec = yaml.safe_load(f)
        self.table = table
        self.alias = self.spec["source"]["alias"]
        self.base_filter = self.spec["source"].get("base_filter", "TRUE")
        self.min_size = int(self.spec.get("min_group_size", 11))
        self.measures = self.spec["measures"]
        self.dimensions = self.spec["dimensions"]
        self.dash = self.spec["dashboard"]
        self.count_sql = self.measures["total_members"]["sql"]

    def config(self):
        def meta(d):
            return {k: d[k] for k in ("label", "description") if k in d}

        d = self.dash
        return {
            "title": self.spec["title"],
            "description": self.spec.get("description", ""),
            "min_group_size": self.min_size,
            "kpis": [dict(meta(self.measures[k]), key=k, format=self.measures[k].get("format", "number")) for k in d["kpis"]],
            "measures": {k: dict(meta(v), format=v.get("format", "number")) for k, v in self.measures.items()},
            "dimensions": {k: dict(meta(v), type=v.get("type", "category"), order=v.get("order")) for k, v in self.dimensions.items()},
            "trend": d["trend"],
            "breakdown": d["breakdown"],
            "questions": self.spec.get("questions", []),
        }

    # ---- SQL -------------------------------------------------------------

    def _where(self, filters):
        clauses, params = [self.base_filter], {}
        for i, (dim, value) in enumerate(filters):
            d = self.dimensions.get(dim)
            if d is None or d.get("type") == "time":
                raise ValueError(f"Cannot filter on {dim}")
            name = f"f{i}"
            clauses.append(f"CAST({d['sql']} AS STRING) = @{name}")
            params[name] = value
        return " AND ".join(f"({c})" for c in clauses), params

    def _from(self):
        return f"FROM `{self.table}` AS {self.alias}"

    def kpis(self, filters):
        where, params = self._where(filters)
        cols = [f"{self.measures[k]['sql']} AS {k}" for k in self.dash["kpis"]]
        cols.append(f"{self.count_sql} AS _n")
        sql = f"SELECT {', '.join(cols)}\n{self._from()}\nWHERE {where}"
        return sql, params

    def grouped(self, dimension, measure_keys, filters):
        """Measures grouped by one dimension. Groups smaller than min_group_size are dropped."""
        dim = self.dimensions.get(dimension)
        if dim is None:
            raise ValueError(f"Unknown dimension: {dimension}")
        for k in measure_keys:
            if k not in self.measures:
                raise ValueError(f"Unknown measure: {k}")
        where, params = self._where(filters)
        is_time = dim.get("type") == "time"
        dim_expr = f"CAST({dim['sql']} AS STRING)"
        cols = [f"{dim_expr} AS d"] + [f"{self.measures[k]['sql']} AS {k}" for k in measure_keys]
        order = "d" if is_time else f"{measure_keys[0]} DESC"
        sql = (
            f"SELECT {', '.join(cols)}\n{self._from()}\nWHERE {where}\n"
            f"GROUP BY d\nHAVING {self.count_sql} >= {self.min_size} AND d IS NOT NULL\n"
            f"ORDER BY {order}\nLIMIT {1000 if is_time else 60}"
        )
        return sql, params
