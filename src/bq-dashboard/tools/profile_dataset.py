"""Profile the tables in a BigQuery dataset and print a Markdown report.

Read-only. For each table: size, schema, null share, approximate distinct counts, min/max of
numbers and dates, and the most common values of low-cardinality text columns. Use it to decide
what a dashboard can show before writing any metric definitions.

Usage:
  python tools/profile_dataset.py PROJECT.DATASET [--billing-project P] [--tables a,b]
         [--max-gb 20] [--exclude col1,col2] [--where "SQL condition"] [--dry-run] > profile.md

--exclude skips wide columns (such as GeoJSON text) to cut cost; --where limits the rows profiled
(for example a recent date range on a partitioned table). Both also bypass the --max-gb check.
"""
import argparse

from google.cloud import bigquery

NUMERIC = {"INTEGER", "INT64", "FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC"}
TIME = {"DATE", "DATETIME", "TIMESTAMP"}
TEXT = {"STRING", "BOOLEAN", "BOOL"}
LOW_CARDINALITY = 30


def q(name):
    return f"`{name}`"


def profile_table(client, ref, table, args):
    gb = (table.num_bytes or 0) / 1e9
    print(f"\n## {table.table_id}\n")
    print(f"- Rows: {table.num_rows:,}   Size: {gb:.2f} GB   Type: {table.table_type}")
    if table.time_partitioning:
        print(f"- Partitioned by: {table.time_partitioning.field or '_PARTITIONTIME'}")
    if table.modified:
        print(f"- Last modified: {table.modified:%Y-%m-%d}")
    excluded = set(args.exclude.split(",")) if args.exclude else set()
    cols = [f for f in table.schema if f.mode != "REPEATED" and f.field_type not in ("RECORD", "STRUCT", "JSON", "GEOGRAPHY", "BYTES") and f.name not in excluded]
    if excluded:
        print(f"- Excluded columns: {', '.join(sorted(excluded))}")
    if args.where:
        print(f"- Profiled rows matching: `{args.where}`")
    skipped = len(table.schema) - len(cols)
    if skipped:
        print(f"- Skipped {skipped} nested/repeated/binary columns")
    if table.table_type == "VIEW" and gb == 0:
        print("- View: size unknown, profiling anyway")
    elif gb > args.max_gb and not (args.exclude or args.where):
        print(f"- Too large to scan (over {args.max_gb} GB); schema only. Use --max-gb to override.")
        print("\n| Column | Type |\n|---|---|")
        for f in cols:
            print(f"| {f.name} | {f.field_type} |")
        return
    exprs = ["COUNT(*) AS _rows"]
    for i, f in enumerate(cols):
        c = q(f.name)
        exprs.append(f"COUNTIF({c} IS NULL) AS n{i}")
        exprs.append(f"APPROX_COUNT_DISTINCT({c}) AS d{i}")
        if f.field_type in NUMERIC | TIME:
            exprs.append(f"CAST(MIN({c}) AS STRING) AS lo{i}")
            exprs.append(f"CAST(MAX({c}) AS STRING) AS hi{i}")
    where = f" WHERE {args.where}" if args.where else ""
    sql = f"SELECT {', '.join(exprs)} FROM {q(ref)}{where}"
    cfg = bigquery.QueryJobConfig(dry_run=args.dry_run, use_query_cache=True)
    job = client.query(sql, job_config=cfg)
    if args.dry_run:
        print(f"- Dry run: profiling would scan {job.total_bytes_processed / 1e9:.2f} GB")
        return
    row = list(job.result())[0]
    total = row["_rows"] or 0
    print("\n| Column | Type | Null % | Distinct (approx) | Min | Max |\n|---|---|---|---|---|---|")
    low = []
    for i, f in enumerate(cols):
        nulls = row[f"n{i}"] / total * 100 if total else 0
        d = row[f"d{i}"]
        lo = row[f"lo{i}"] if f.field_type in NUMERIC | TIME else ""
        hi = row[f"hi{i}"] if f.field_type in NUMERIC | TIME else ""
        print(f"| {f.name} | {f.field_type} | {nulls:.1f} | {d:,} | {lo or ''} | {hi or ''} |")
        if f.field_type in TEXT and 0 < d <= LOW_CARDINALITY:
            low.append(f)
    for f in low:
        c = q(f.name)
        rows = client.query(
            f"SELECT CAST({c} AS STRING) AS v, COUNT(*) AS n FROM {q(ref)}{where} GROUP BY v ORDER BY n DESC LIMIT 10"
        ).result()
        vals = ", ".join(f"{r['v']} ({r['n']:,})" for r in rows)
        print(f"\n- **{f.name}** top values: {vals}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("dataset", help="PROJECT.DATASET")
    p.add_argument("--billing-project", help="project that runs the queries (default: the dataset's project)")
    p.add_argument("--tables", help="comma-separated table names (default: all)")
    p.add_argument("--max-gb", type=float, default=20)
    p.add_argument("--exclude", help="comma-separated columns to skip")
    p.add_argument("--where", help="SQL condition limiting the rows profiled")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    project, _, dataset = args.dataset.partition(".")
    client = bigquery.Client(project=args.billing_project or project)
    names = args.tables.split(",") if args.tables else [t.table_id for t in client.list_tables(f"{project}.{dataset}")]
    print(f"# Profile of {project}.{dataset}\n\n{len(names)} tables.")
    for name in sorted(names):
        ref = f"{project}.{dataset}.{name}"
        try:
            profile_table(client, ref, client.get_table(ref), args)
        except Exception as e:
            print(f"\n## {name}\n\n- Could not profile: {str(e)[:900]}")


if __name__ == "__main__":
    main()
