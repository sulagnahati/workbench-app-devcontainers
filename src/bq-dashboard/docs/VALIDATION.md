# Validation of the prototype dashboards

Validated on the final build of the `overview-dashboard` branch, on a laptop, with the dashboards reading
the production patient table and the two wastewater datasets using one person's own Google login.
Section C must be completed with the external-reporting needs listed in the spike.

## A. Automated checks (all passing)

| Suite | What it covers | Result |
|---|---|---|
| `tools/smoke_test.py` | Every page and every data endpoint, with real BigQuery queries: 6 pages, styles and map file, the member overview (KPIs, trend, all 8 breakdowns, a drill-down), wastewater (lists, KPIs, variants, trend, ranking by state and plant, plant map), all 14 Lifelong tiles and the 3 filter option lists, the LookML explorer, the tables page | **52 of 52 passed** |
| `tools/ui_test.py` | A real browser: landing-page cards and top navigation; Lifelong dropdown filters (choose, apply on close, reset, trend grain); member overview drill-down and chips; wastewater state and pathogen filters, smoothing, clear filters; no row-level data on the tables page; no JavaScript errors on any page | **27 of 27 passed** |

Response times in the smoke test were low on the day tested: 33 data requests, median 0.6 seconds, slowest
2.3 seconds (BigQuery latency varied a lot between days; on another day plain queries took 40 seconds).

To repeat: start the server (see `DEMO.md`), then run
`python tools/smoke_test.py http://127.0.0.1:8080` and
`python tools/ui_test.py http://127.0.0.1:8080` (the second needs `pip install playwright` and
`playwright install chromium`).

### What the tests caught during polish

Two real defects were found and fixed by running the tests rather than by reading the code:
a backend edit had removed helper functions (every data call on the Lifelong page failed while the page itself
loaded), and the open filter panel covered the Apply button. Both are fixed and covered by the checks above.

## B. Polish for a broader stakeholder demo

| Area | Status | Notes |
|---|---|---|
| Navigation | Done | One header on every page, tabs for each dashboard with the current one highlighted, a landing page with a card per dashboard and a short "about these prototypes" panel. Developer tools (Tables, LookML explorer) are separate small links. |
| Consistent look | Done | All pages use one stylesheet, the Verily palette sampled from the deck template, and the same chart library. The Lifelong page was rebuilt to match the other two. |
| Labels and formatting | Done | Plain-language filter labels, grouped sections (Interest funnel, Consent funnel), formatted numbers, readable donut and slice names, the trend grain stated under each chart, loading and "no data" messages. |
| Definitions on the page | Done | Each dashboard lists the questions it answers; the Lifelong page shows each tile's definition from the LookML (hover the "i" or open the definitions list); the metric definitions are also available as documents. |
| Filters | Done | Lifelong: checkbox dropdowns (a plain click toggles one value), date presets, summary line, Reset. Wastewater: date range, pathogen, state. Overview: drill chips with Clear all. |
| Drill-down | Done | Overview: organization to program, state, age and sex. Wastewater: state to plant, on the chart, ranking or map. |
| Charts | Done | Stacked variant mix with an optional 3-week smoothing, trend lines with zoom, rankings, donuts, a US state map with plant bubbles (Alaska and Hawaii not drawn). |
| Privacy | Partly | The 50-row patient preview was removed from the tables page. The member overview hides groups under 11; the other dashboards do not apply that rule. |
| Presentation views | Not done | No print or PDF layout and no export of the numbers. |
| Accessibility | Not tested | Colours were chosen from the brand palette, not checked for contrast or screen-reader use. |

Screenshots of the final pages are in `docs/screenshots/` (kept out of git because they show production
counts).

## C. Key external-reporting needs from the spike (to complete)

The spike's list was not available when this was written. Fill the first column from the spike, then the
other two. Pre-filled rows are the needs that the ticket and this work imply, so they are a starting point and
not a substitute for the spike's own list.

| Need (from the spike) | How the dashboards address it | Status | Evidence |
|---|---|---|---|
| *[from spike]* | | | |
| Open a link, sign in, and see the dashboard | Not possible: apps are not shareable yet | **Not met** | Depends on Workbench shared apps |
| Same numbers as the existing Looker reporting | Lifelong tiles are built from the same LookML but not compared with Looker | **Not verified** | Needs a Looker comparison |
| Interactive filtering | Filters on all three dashboards | Met | UI tests |
| Drill from a summary to detail | Overview and wastewater | Met | UI tests |
| Trend over time | All three dashboards | Met | Smoke and UI tests |
| Clear definitions of each number | Questions and definitions on the pages; metric documents | Met for the metrics shown; definitions are drafts pending analyst review | `METRICS.md`, `SIGHTLINE_METRICS.md` |
| Appropriate for an external audience (privacy, access control) | Counts only, small-group rule on one dashboard, no in-app access control | **Partly met** | See open items 9 and 10 in `ARCHITECTURE_COMPARISON.md` |
| Reasonable speed | Median 0.6 seconds on a good day; slow on bad days | Met on the day tested | Smoke test |
| Data stays current | Live queries with a 10-minute cache | Met for data; LookML definitions are a copy that must be re-synced | Architecture document, section 3 |

## D. Known limitations and items for the owner

- Numbers were **not compared with Looker**; the Lifelong dashboard's Consent breakdown total (3,370) differs
  from Total Consent Eligible (3,141) because each slice is counted separately. This is stated under the
  chart, but an analyst should confirm it matches the Looker dashboard.
- The wastewater definitions are drafts: median of the PMMoV-normalised value, negative values ignored, a
  12-month default window. Many pathogens show zero medians when not detected.
- Three of 148 plants (Alaska and Hawaii) are not drawn on the map.
- The wastewater LookML repository already contains five Sightline dashboards; see item 8 in
  `ARCHITECTURE_COMPARISON.md`.
- The tests were run from a laptop with one person's credentials. Running as the app's service account in
  Workbench has not been tested and depends on the data-use launch and data grants.
