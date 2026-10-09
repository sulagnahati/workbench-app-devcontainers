# Sightline data profile

Profiled 2026-10-09 with `tools/profile_dataset.py` (read-only). Both datasets are controlled resources
in workspace `wastewater-internal-data-delivery` (Google project `wb-arctic-date-2446`).

## Findings

- **Pathogen concentrations** (`ddpcr_dbt_commercializable_all.all`): 1.35M result rows, July 2020 to
  September 2026, 192 plants and 30 pathogens. About 148 plants and 16,000 samples per year recently.
  One row per pathogen per sample. Includes plant name, state, city, coordinates, sewershed population,
  concentration (`copies_per_unit`) and PMMoV-normalised concentration (`copies_per_pmmov`).
- **Variant mix** (`compbio_freyja_summary_abundances.freyja_summary_abundances`): 203,000 rows, January
  2022 to August 2026, 50 sites, 29 lineages. Shares add up to 1 for every sample (7,000 samples checked).
  Recent months are led by XFG (about 40%), LF.7 (21%) and NB.1.8.1 (9%).
- **The datasets join.** Freyja's `site` equals the pathogen table's `plant_code` for 44 of 50 sites.
- **Cost warning.** The pathogen table is 100 GB, almost all of it the `plant_sewershed_geojson` column.
  Never select that column, and always filter by `sample_collection_date` (the partition column).
  A one-year profile without the column scans about 0.07 GB.
- **Data quality to resolve with the data owners.** `plant_created_at` has a 1970 value; concentrations
  range up to about 2 billion copies; many pathogens have weekly medians of zero when not detected; the
  only unit is `gram`. Decide the outlier and zero rules before relying on the numbers.

## Pathogen table (2026 rows only, geojson column excluded)

| Column | Type | Null % | Distinct (approx) | Min | Max |
|---|---|---|---|---|---|
| plant_id | INTEGER | 0.0 | 148 | 2 | 627 |
| plant_created_at | TIMESTAMP | 0.0 | 2 | 1970-01-01 00:00:00+00 | 2026-05-15 20:10:48.648533+00 |
| plant_updated_at | TIMESTAMP | 0.0 | 148 | 2026-06-16 15:59:32.564223+00 | 2026-08-12 17:41:15.044550+00 |
| plant_uid | STRING | 0.0 | 148 |  |  |
| plant_code | STRING | 0.0 | 148 |  |  |
| plant_name | STRING | 0.0 | 148 |  |  |
| plant_city | STRING | 0.0 | 125 |  |  |
| plant_state | STRING | 0.0 | 40 |  |  |
| plant_country | STRING | 0.0 | 1 |  |  |
| plant_zipcode | STRING | 0.0 | 144 |  |  |
| plant_sewershed_population | INTEGER | 0.0 | 109 | 10100 | 4000000 |
| plant_latitude | FLOAT | 0.0 | 148 | 21.307998814013505 | 61.196392165304822 |
| plant_longitude | FLOAT | 0.0 | 148 | -158.03811607787785 | -68.7833074456301 |
| plant_county_fips | STRING | 0.0 | 104 |  |  |
| sample_id | STRING | 0.0 | 16,043 |  |  |
| sample_created_at | TIMESTAMP | 0.0 | 16,046 | 2026-01-03 08:04:02.076321+00 | 2026-09-09 04:49:15.761868+00 |
| sample_updated_at | TIMESTAMP | 0.0 | 16,040 | 2026-01-03 08:04:02.076338+00 | 2026-09-09 04:49:15.761883+00 |
| sample_collection_date | DATE | 0.0 | 250 | 2026-01-01 | 2026-09-07 |
| result_created_at | TIMESTAMP | 0.0 | 317,869 | 2026-01-03 08:10:07.636355+00 | 2026-09-09 04:49:54.878318+00 |
| result_updated_at | TIMESTAMP | 0.0 | 316,672 | 2026-01-03 08:10:07.636359+00 | 2026-09-09 04:49:54.878322+00 |
| amplicon | STRING | 0.0 | 22 |  |  |
| pathogen | STRING | 0.0 | 21 |  |  |
| unit | STRING | 0.0 | 1 |  |  |
| copies_per_unit | FLOAT | 0.0 | 104,450 | 0 | 2018024999.5294118 |
| copies_per_pmmov | FLOAT | 0.0 | 104,916 | 0 | 10.75193245592868 |

- **plant_country** top values: United States (316,045)

- **amplicon** top values: Rota (16,049), InfA_H3_V2 (16,049), Parvo_B19 (16,049), MPXV_dD14-16 (16,049), Noro_G2 (16,049), WNV (16,049), HMPV_4 (16,049), C_auris (16,049), HAdV_F (16,049), InfA_H1_V2 (16,049)

- **pathogen** top values: Mpox virus (16,049), InfA_H1 (16,049), MPXV Clade Ib (16,049), Human metapneumovirus (16,049), InfA_H3 (16,049), Influenza B (16,049), West Nile Virus (16,049), Influenza A (16,049), Candida auris (16,049), Measles (16,049)

- **unit** top values: gram (316,045)

## Variant table (all rows)

| Column | Type | Null % | Distinct (approx) | Min | Max |
|---|---|---|---|---|---|
| sample_id | STRING | 0.0 | 6,996 |  |  |
| experiment | STRING | 0.0 | 287 |  |  |
| site | STRING | 0.0 | 50 |  |  |
| collection_date | DATE | 0.0 | 1,284 | 2022-01-09 | 2026-08-28 |
| extraction_date | DATE | 0.0 | 876 | 2022-01-10 | 2026-08-28 |
| prep_version | STRING | 0.0 | 4 |  |  |
| lineage | STRING | 0.0 | 29 |  |  |
| abundance | FLOAT | 0.0 | 18,505 | 0 | 1.0000000000000013 |

- **prep_version** top values: SOL.1 (141,665), SOL.0 (40,281), INF.0 (20,184), INF.1 (870)

- **lineage** top values: JN.1 (7,000), BA.5 (7,000), BA.2 (7,000), JN.1.11 (7,000), XBB.2.3 (7,000), XBB.1.5 (7,000), LF.7 (7,000), Other (7,000), XFG (7,000), JN.1.13 (7,000)
