# Building external dashboards on Workbench: with LookML or without

**Status:** draft for review. Findings come from the prototype work only; the shared-app and dbt-chart spike
findings still need to be merged in (see section 7).
**Prepared by:** [name]   **Date:** [date]   **Ticket:** [link]

Written for: product, analytics and engineering leads who need to decide how Verily builds dashboards for
external reporting on Workbench.

---

## 1. Decision and recommendation

**The decision.** When a team needs an interactive dashboard for external reporting, should it be built from
existing LookML, or from definitions written for the dashboard without LookML?

**Recommendation (summary).**

1. **Do not make "re-implement LookML inside the app" the long-term path.** It works for a demonstration, but
   it means maintaining our own copy of Looker's SQL generation, it only covers part of the LookML, and its
   numbers have not been checked against Looker.
2. **Where LookML already exists, use Looker as the source of the numbers** (ask Looker for the results, or for
   the SQL), and use the app only for presentation. This keeps one definition of each metric. It is not yet
   proven: it needs Looker API access, which we could not obtain during the spike.
3. **Where no LookML exists, a metrics file owned by analysts is a good, fast option for a small number of
   dashboards.** It produced a second dashboard with far less effort than the first. It should be treated as
   a stopgap unless the organisation also decides where definitions will live long term (section 5).
4. **Nothing here can be shared with external users until Workbench offers shareable apps** and the data-use
   launch covers the audience. Those two items, not the dashboard technology, decide the timeline.

The remaining open questions that could change this recommendation are listed in section 6.

## 2. What was built and compared

Three dashboards were built with the same design, navigation and charts, so that stakeholders can judge the
**architecture** and not the appearance.

| Dashboard | Data | How the numbers are defined |
|---|---|---|
| Lifelong funnel | Lifelong study interest and consent (14 tiles) | Existing LookML, compiled to BigQuery SQL by the app |
| Member overview | Member counts, activity, sign-ups | A metrics file written for this dashboard (no LookML) |
| Wastewater surveillance | Pathogen levels and SARS-CoV-2 variants from wastewater plants | A metrics file written for this dashboard (no LookML) |

All three read live from BigQuery, show counts and averages only, share one landing page, and can be run from
one server.

## 3. Side-by-side comparison

| | **A. LookML-backed** (app compiles the LookML) | **B. Metrics file** (no LookML) | **C. Looker as the engine** (not tested) |
|---|---|---|---|
| **Development effort** | High at the start: a purpose-built SQL compiler was needed (about 640 lines of code) plus a dashboard reader (about 150) before one tile worked. Each new LookML feature that appears (templating, derived tables, filter syntax) may need more compiler work. | Low once the pattern exists: about 80 to 140 lines of query code and 100 to 130 lines of YAML per dashboard. The second dashboard reused the first one's pattern. New chart types still need engineering. | Expected to be low if API access exists: no compiler, no definitions to write. Unknown until tried. |
| **Metric consistency** | Definitions are the same ones Looker uses, so they are consistent in principle. But the app interprets them with its own compiler, so results can drift from Looker. **Not yet compared with Looker's numbers.** | Definitions exist only in the metrics file. They are consistent within the dashboard, but nothing links them to other reports or to Looker. A metric defined twice can differ. | Same engine as Looker, so numbers should match. |
| **Governance** | Definitions already live in the reviewed LookML repository (40 dashboards, 122 views, 12 models; the repo has code owners). The app adds no access rules of its own. | Definitions are reviewed as a pull request on the metrics file. Each entry can record an owner, status and validation, but this is a convention, not enforced. No access rules in the app. | Looker's permissions and row-level rules would apply, which is the strongest governance of the three. |
| **Maintainability** | Fragile. 6 of the 36 measures in the main view cannot be translated yet, only 14 of 60 data tiles on the dashboard are rebuilt, and each LookML change may need a code change. The app also holds a copy of the LookML that can go stale. | Simple and readable by analysts. But every dashboard still needs its own query module, so it does not yet scale without engineers. | Least code to maintain here; depends on Looker's own upkeep. |
| **Refresh behaviour** | Data is live (results cached 10 minutes). **Definitions are a copy and do not update when LookML changes** unless someone re-syncs it. The Looker models define 24-hour caching rules (datagroups), so Looker may show results up to a day old while the app shows live ones; whether the Lifelong explore uses them was not checked. | Data is live. Definitions change when the file is changed and the app is redeployed. | Follows whatever is deployed in Looker, including its caching. |
| **Scalability** | Poor as a general route: each dashboard needs bespoke layout, and the compiler would need to cover far more LookML. Heavy tiles scan about 9 GB per query. | Good for a handful of dashboards, then limited by engineering time for new chart types. A single server with an in-memory cache is enough for demonstrations only. | Scales with Looker; the app stays thin. |
| **Sharing and access** | Same for all three today: apps are not shareable, and an app's service account needs its own data grant. | Same | Same, plus Looker credentials to store as a secret |
| **Cost** | Queries are cheap except a few heavy tiles (roughly 10 to 15 cents for a full uncached Lifelong load, assuming standard on-demand BigQuery pricing). | Cheap: 5 to 40 MB per query in the tests. | Looker licensing and query cost already exist. |

## 4. Evidence from the prototypes

- **Coverage of LookML.** The Lifelong dashboard has 74 elements, 60 of them showing data. 14 were rebuilt
  (23%). In the main LookML view, 30 of 36 measures translate; the other 6 use constructs the compiler does not
  handle.
- **LookML descriptions are sparse.** Only 2 of the 14 tiles' measures have a description in LookML. The other
  12 had to borrow the description of the field they filter on. Stakeholder-readable definitions need
  deliberate writing in either approach.
- **Metrics files are fast to write when the data is understood.** Profiling the two wastewater datasets
  needed only a few small queries (the 100 GB table was profiled by scanning about 0.07 GB) and found the join
  between them, a 100 GB column to avoid, and several data-quality issues.
  The definitions then went into one short YAML file.
- **Automated checks.** An API smoke test (52 checks: every page and data endpoint) and a browser test
  (27 checks: navigation, filters, drill-downs) pass on the final build. See `VALIDATION.md`.
- **Not measured.** Agreement with Looker's numbers; behaviour under many users; accessibility; the shared-app
  experience.

## 5. Why this recommendation

- **One definition per metric is the main prize.** Approach A gets it by reusing LookML, but it pays for it by
  keeping a second interpreter that must track Looker. Approach C keeps one definition and one interpreter,
  which is why it is preferred where LookML exists, once access is available.
- **Approach B is honest about its limits.** It is quick, readable and owned by analysts, and it is what
  teams can do today when there is no LookML. Its risk is a second source of definitions. If the organisation
  expects many such dashboards, a shared place for definitions is needed. Options include writing LookML for
  the new data so Looker governs it, or adopting a dbt-based semantic layer. The dbt-chart spike should inform
  this choice (section 7).
- **The right answer may differ by case.** Use this rule of thumb until the open questions are settled:
  - LookML exists and the numbers must match Looker: approach C (or A only for a demonstration).
  - No LookML, small audience, a handful of dashboards: approach B with analyst ownership.
  - No LookML, many dashboards expected: decide on a shared definition layer first, then build on it.

## 6. Risks, dependencies and open questions

| # | Item | Why it matters | Suggested owner | Status |
|---|---|---|---|---|
| 1 | **Shareable apps do not exist yet** | External users cannot open a link, sign in and see a dashboard. Today the dashboard runs on one person's computer or workspace. | Workbench team | On the roadmap; no date known |
| 2 | **Data-use launch** | Required before the app's service account can be granted access to the data, and covers who may see what. | Product manager with data owners | Not started |
| 3 | **Service-account access** | The deployed app returns "access denied" until its identity is granted read access (the wastewater workspace uses an admin-managed group). | Data owners | Not granted |
| 4 | **Looker API access** | Needed for approach C. Keys could not be obtained during the spike. | Looker admins | Open |
| 5 | **Numbers not compared with Looker** | Approach A's accuracy is unknown. | Analyst | Open |
| 6 | **Definitions are drafts** | Questions, the pathogen-level rule (median of the PMMoV-normalised value), zero handling and default date ranges were drafted by the assistant. | Analyst and data owner | Not reviewed |
| 7 | **Data-quality rules** | The wastewater data has outliers up to about 2 billion copies, a 1970 date, and many zero medians. | Analyst and data owner | Not decided |
| 8 | **The LookML repository already has five Sightline dashboards** and a Sightline model. Confirm whether they cover the wastewater datasets used here. If so, the "no LookML" premise for that data needs checking, and Looker numbers exist to compare against. | Could change which approach applies and give a ready validation source. | Analytics lead | Open |
| 9 | **No access control inside the app** | Anyone who can open the app sees the same data through the app's identity; row-level rules from Looker are not reproduced. | Engineering with data owners | Open |
| 10 | **Small-group protection** | Only the member overview hides groups under 11; the others show aggregated counts without that rule (for example 12 revoked consents). | Product manager with privacy | Open |
| 11 | **Performance and cost at scale** | One server, in-memory cache, a few 9 GB tiles. Fine for demonstrations. | Engineering | Not tested |
| 12 | **Alaska and Hawaii** | Three plants are not drawn on the map (they appear in the ranking). | Engineering | Known limitation |

## 7. Spike inputs still to be merged

The ticket refers to a Workbench shared-app and dbt-chart spike. Those findings were not available when this
document was drafted and are **not reflected above**. Please add:

- **Shared-app findings:** what sharing model was evaluated, how authentication and the viewer's identity work,
  and any constraints or dates.
- **dbt-chart findings:** what was built, how metrics were defined (dbt models or a semantic layer), the effort
  it took, and how it compares with approach B.
- **External-reporting needs evaluated in the spike:** the list used to judge the dashboards. `VALIDATION.md`
  has a table ready for it.

Once added, revisit the recommendation in section 1, especially the choice of a shared definition layer.

## Appendix: where things are

- Dashboards: run from one server (steps in `DEMO.md`); pages `/`, `/overview`, `/sightline`, `/lifelong`.
- Definitions: `app/metrics/patient_overview.yml`, `app/metrics/sightline.yml`; readable versions in
  `docs/METRICS.md` and `docs/SIGHTLINE_METRICS.md`; data profile in `docs/sightline_profile.md`.
- Tests: `tools/smoke_test.py` (API) and `tools/ui_test.py` (browser); results in `VALIDATION.md`.
- Process for building a dashboard without LookML, with roles: the README, "Building a dashboard without LookML".
