# Validation of the prototype dashboards

Validated on the final build of the `overview-dashboard` branch, on a laptop, with the dashboards reading
the production patient table and the two wastewater datasets using one person's own Google login.
Section C judges the dashboards against the five sponsor-view needs defined in ONEVERILY-152005.

## A. Automated checks (all passing)

| Suite | What it covers | Result |
|---|---|---|
| `tools/smoke_test.py` | Every page and every data endpoint, with real BigQuery queries: 6 pages, styles and map file, the member overview (KPIs, trend, all 8 breakdowns, a drill-down), wastewater (lists, KPIs, variants, trend, ranking by state and plant, plant map), all 14 Lifelong tiles and the 3 filter option lists, the LookML explorer, the tables page | **52 of 52 passed** |
| `tools/smoke_test.py --external` | The same server started the way the deployment configuration starts it (`DEV_TOOLS=0`): the three dashboards and their data work; the 2 developer pages and 10 of their data endpoints return "not found"; the navigation hides the developer links | **59 of 59 passed** |
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

## C. Sponsor-view needs from the earlier spike (ONEVERILY-152005)

The spike scored hosting options against five needs. This is how the prototype dashboards score. "Met by
design" means the prototype is built to meet it but it was not tested on the hosted platform.

| Need | What "good" means | Status | Evidence and gaps |
|---|---|---|---|
| **Resourcing** | Analytics can own the dashboard build end to end | **Partly met** | Analysts can own the definitions (metrics file or LookML) and review the documents. All chart, query and deployment code was written by engineering; new chart types and fixing a deployed app need engineers. |
| **Named external users** | A named person outside Verily can open the board, cannot see other partners' boards, cannot change it | **Not met** | Apps are not shareable. Per the spike, a Workbench reader cannot see another user's running app and each reader would launch their own VM. Reader and Writer sharing was **not tested**. Depends on whether a sponsor may hold a Workbench account. |
| **Aggregate-only** | Counts and rates only; no person-level rows, no user SQL, no export of the table | **Met by design; untested on the platform** | Fixed aggregate queries; no SQL box; no page shows rows (the old 50-row preview was removed); identifier fields are excluded. The developer pages that let a viewer choose any column are off in the deployment configuration (`DEV_TOOLS=0`, verified by 59 checks). Gaps: the platform does not enforce this and the app queries as the workspace service account; a Writer could edit the app; only the member overview hides groups under 11. |
| **Scheduled or certified refresh** | Numbers update on a cadence, or a dated frozen render exists | **Not met** | Live queries with a 10-minute cache. No schedule, no frozen render and no "data as of" stamp (the wastewater page shows the latest sample date only). A restart or cache expiry is not a certification. |
| **Export** | PDF or image of the board; no export of underlying rows | **Not met** | No PDF, image or data export is built. Browser print was not tested. Charts hold only aggregates, so an export of what is on screen would be safe to add. |

### The spike's proofs for Workbench, and where we are

| Proof the spike asked for | Status |
|---|---|
| Smallest custom app showing one fixed count, with no SQL box | The dashboards are built and run locally with fixed queries and no SQL box. Running them as a Workbench-hosted app was **not completed**: the app's service account has no data access yet. |
| Share the workspace as Reader and record what that account sees | **Not done** |
| Repeat as Writer and record what else it can change | **Not done** |
| Stop the app, push a change, record what a visitor sees before anyone pulls | **Not formally tested.** In practice the app's repository, branch and folder could not be edited after creation, so a change meant creating a new app. |
| Can the app emit a PDF; are rows reachable from the page | No PDF is built. No rows are reachable from the dashboards, and the developer pages can be turned off. |

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
