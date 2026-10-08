"""Write METRICS.md from the metrics spec. Usage: python metrics_doc.py > ../docs/METRICS.md"""
import yaml

from overview import SPEC_PATH

spec = yaml.safe_load(open(SPEC_PATH))
out = [f"# {spec['title']}: metric definitions", "", spec.get("description", ""), "",
       f"Generated from `app/metrics/patient_overview.yml`. Groups with fewer than {spec['min_group_size']} members are hidden.", "",
       "## Measures", "", "| Measure | Meaning | Rule | LookML source |", "|---|---|---|---|"]
for k, m in spec["measures"].items():
    rule = " ".join(m["sql"].split()).replace("|", "\\|")
    out.append(f"| {m['label']} | {m['description']} | `{rule}` | {m.get('lookml', '')} |")
out += ["", "## Dimensions", "", "| Dimension | Meaning | Rule | LookML source |", "|---|---|---|---|"]
for k, d in spec["dimensions"].items():
    rule = " ".join(d["sql"].split()).replace("|", "\\|")
    out.append(f"| {d['label']} | {d['description']} | `{rule}` | {d.get('lookml', '')} |")
out += ["", "## Example questions", ""]
for q in spec.get("questions", []):
    out.append(f"- {q['question']} (uses: {', '.join(q['uses'])})")
print("\n".join(out))
