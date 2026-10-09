# Wastewater Surveillance: metric definitions

Pathogen levels and SARS-CoV-2 variant mix from wastewater treatment plants.

Generated from the metrics file (see `app/metrics/`).

## Measures

| Measure | Meaning | Rule | Source |
|---|---|---|---|
| Pathogen level | Median PMMoV-normalised concentration (copies per PMMoV) across results. The median is used because raw concentrations range up to billions of copies. Negative and missing values are ignored. Default; confirm the preferred normalisation and outlier rule. | `APPROX_QUANTILES(IF(r.copies_per_pmmov >= 0, r.copies_per_pmmov, NULL), 100)[OFFSET(50)]` | pathogens |
| Plants reporting | Treatment plants with at least one result in the period. | `COUNT(DISTINCT r.plant_code)` | pathogens |
| Samples | Distinct wastewater samples collected in the period. | `COUNT(DISTINCT r.sample_id)` | pathogens |
| Latest sample date | Most recent collection date in the period. | `MAX(r.sample_collection_date)` | pathogens |
| Variant share | Average share of a lineage across samples. Each sample's shares add up to 100%, so the averages for a week also add up to 100%. Samples are weighted equally, not by population. | `AVG(v.abundance)` | variants |

## Dimensions

| Dimension | Meaning | Rule | Source |
|---|---|---|---|
| Week | Week starting Monday. | `pathogens: DATE_TRUNC(r.sample_collection_date, WEEK(MONDAY)) / variants: DATE_TRUNC(v.collection_date, WEEK(MONDAY))` |  |
| Pathogen | Pathogen name from the lab results. | `r.pathogen` |  |
| State | State of the treatment plant. | `r.plant_state` |  |
| Plant | Treatment plant name. | `r.plant_name` |  |
| Lineage | SARS-CoV-2 lineage reported by Freyja. The lineages beyond the top few are grouped as Other on the page. | `v.lineage` |  |

## Example questions

- Which SARS-CoV-2 variants are circulating, and how is the mix changing? (uses: variant_share, lineage, week)
- Is the level of a pathogen (for example influenza A or RSV) rising or falling? (uses: pathogen_level, pathogen, week)
- Which states and plants currently have the highest levels of a pathogen? (uses: pathogen_level, state, plant)
- Is a state's trend different from the national trend? (uses: pathogen_level, state, week)
- How many plants and samples are behind these numbers? (uses: plants_reporting, samples, latest_sample)
