"""Write a metrics document from a metrics spec.

Usage: python metrics_doc.py [spec.yml] > ../docs/METRICS.md   (default: metrics/patient_overview.yml)
"""
import sys

import yaml

from overview import SPEC_PATH

spec = yaml.safe_load(open(sys.argv[1] if len(sys.argv) > 1 else SPEC_PATH))
spec.setdefault("min_group_size", "n/a")
out = [f"# {spec['title']}: metric definitions", "", spec.get("description", ""), "",
       "Generated from the metrics file (see `app/metrics/`)." + (f" Groups with fewer than {spec['min_group_size']} members are hidden." if isinstance(spec["min_group_size"], int) else ""), "",
       "## Measures", "", "| Measure | Meaning | Rule | Source |", "|---|---|---|---|"]
for k, m in spec["measures"].items():
    rule = " ".join(m["sql"].split()).replace("|", "\\|")
    out.append(f"| {m['label']} | {' '.join(m['description'].split())} | `{rule}` | {m.get('lookml', m.get('source', ''))} |")
out += ["", "## Dimensions", "", "| Dimension | Meaning | Rule | Source |", "|---|---|---|---|"]
for k, d in spec["dimensions"].items():
    raw = d.get("sql") or " / ".join(f"{k.replace('_sql', '')}: {v}" for k, v in d.items() if k.endswith("_sql"))
    rule = " ".join(raw.split()).replace("|", "\\|")
    out.append(f"| {d['label']} | {' '.join(d['description'].split())} | `{rule}` | {d.get('lookml', '')} |")
out += ["", "## Example questions", ""]
for q in spec.get("questions", []):
    out.append(f"- {q['question']} (uses: {', '.join(q['uses'])})")
print("\n".join(out))
