# External dashboards on Workbench: LookML-governed definitions versus none

**Status:** draft for review.
**Prepared by:** [name]   **Date:** [date]   **Ticket:** [link]
**Related:** ONEVERILY-152005 (where external dashboards should be hosted: Workbench apps versus dbt Charts),
ONEVERILY-150812 (Looker scaling, closed), ONEVERILY-151935 (ARI metric definitions).

Written for: product, analytics and engineering leads deciding how Verily defines and builds dashboards for
external reporting on Workbench.

---

## 1. Decision and recommendation

**Where we start.** Workbench custom apps are the chosen place to host external dashboards. This document is
about the other half of the choice: **where the numbers come from**. Either they are defined in LookML, which
Verily already uses and reviews, or they are defined separately for each dashboard.

**Recommendation: any metric shown to an external reader should be defined in LookML.**

- **One governed definition.** A number shown to an outside partner is a commitment. If its definition lives
  in a reviewed, owned, version-controlled place that internal reporting already uses, then the external
  number and the internal number cannot quietly disagree. LookML is that place today: the LookML repository
  holds 40 dashboards, 122 views and 12 models, with code owners and review.
- **The app presents; it does not redefine.** The Workbench app should show results that come from the
  LookML definitions, not hold its own copy of the business rules.
- **Data with no LookML gets LookML first.** For datasets such as the wastewater data, write the LookML (or
  have the owning analysts do so) before the dashboard goes to an external reader. A metrics file is acceptable
  as a prototype, as we used it, but it should come with an agreed path to LookML and not become the permanent
  home of external definitions.
- **Do not make our own LookML compiler the production path.** The prototype compiler proved the idea and was
  enough for a demonstration. Maintaining a second interpreter of LookML in the app is the wrong long-term
  cost. The preferred route is to have Looker produce the numbers (or the SQL) for the app. That route is not
  yet proven; it needs Looker API access, which we could not get during the spike.

**What this does not solve.** LookML governs definitions. It does not give external readers access, enforce
aggregate-only views, certify refreshes or provide export. Those gaps belong to the hosting platform and are
the critical path to an external launch (section 5).

### What the prototypes proved and did not prove

| Proved | Not proved |
|---|---|
| A dashboard can be driven from LookML definitions and look identical to one built without them | That the app's numbers match Looker's |
| A metrics file produces a good dashboard quickly, with analysts owning the definitions | That Looker can serve the app through its API, at the volume external use would need |
| All three share one design, navigation and chart library, so they are comparable on architecture | That external readers can sign in and view the dashboard |
| Automated checks pass on every page and data call (see `VALIDATION.md`) | Behaviour under many users, accessibility, or the hosted Workbench experience |

LookML is also not a complete governance answer by itself. Only 2 of the 14 tiles' measures carry a
description in LookML (the other 12 borrowed the description of the field they filter on), so readable
definitions need deliberate writing whichever approach is used.

## 2. What was built and compared

Three dashboards were built with the same design so that stakeholders can judge the **architecture**, not the
appearance.

| Dashboard | Data | How the numbers are defined |
|---|---|---|
| Lifelong funnel | Lifelong study interest and consent (14 tiles) | Existing LookML, compiled to BigQuery SQL by the app |
| Member overview | Member counts, activity, sign-ups | A metrics file written for this dashboard (no LookML) |
| Wastewater surveillance | Pathogen levels and SARS-CoV-2 variants from wastewater plants | A metrics file written for this dashboard (no LookML) |

All three read live from BigQuery, show counts and averages only, share one landing page, and run from one
server.

## 3. Side-by-side comparison

| | **A. LookML-backed** (app compiles the LookML) | **B. Metrics file** (no LookML) | **C. Looker as the engine** (not tested) |
|---|---|---|---|
| **Governance** | **Strongest of the tested options.** Definitions already live in the reviewed LookML repository with owners and history, and are shared with internal reporting. The app adds no access rules of its own. | **Weakest.** Definitions live only in the metrics file. Review is by pull request and each entry can record an owner, status and validation, but nothing enforces it, and the definition is not tied to anything else in the company. | **Strongest overall.** Same definitions, and Looker's own permissions and row-level rules can apply. |
| **Metric consistency** | Same definitions as Looker in principle; but the app interprets them with its own compiler, so results can drift. **Not compared with Looker.** | A metric defined here and elsewhere can differ, and no one would be told. | Same engine as Looker, so numbers should match. |
| **Development effort** | High at the start: a purpose-built compiler (about 640 lines) plus a dashboard reader (about 150) before one tile worked; each new LookML feature may need more compiler work. | Low once the pattern exists: about 80 to 140 lines of query code and 100 to 130 lines of definitions per dashboard. | Expected low if API access exists: no compiler. Unknown until tried. |
| **Maintainability** | Fragile: 6 of 36 measures in the main view cannot be translated, 14 of 60 data tiles on the dashboard are rebuilt, and the app holds a copy of the LookML that goes stale. | Readable by analysts, but every dashboard still needs its own query module. | Least code to maintain in the app. |
| **Refresh behaviour** | Data is live (10-minute cache). **Definitions are a copy and do not update when LookML changes** unless re-synced. The Looker models define 24-hour caching rules, so Looker may show older results than the app; whether the Lifelong explore uses them was not checked. | Data is live. Definitions change with the file and a redeploy. | Follows what is deployed in Looker, including its caching. |
| **Scalability** | Poor as a general route: bespoke layout per dashboard, compiler coverage must keep growing; heavy tiles scan about 9 GB per query. | Good for a handful of dashboards, then limited by engineering time for new chart types. | Scales with Looker, which carries its own capacity questions (ONEVERILY-150812). |
| **Cost** | Cheap queries, except a few heavy tiles (roughly 10 to 15 cents for a full uncached Lifelong load at standard on-demand BigQuery pricing). | 5 to 40 MB per query in the tests. | Existing Looker licensing and query cost. |

## 4. Evidence from the prototypes

- **Coverage of LookML.** The Lifelong dashboard has 74 elements, 60 showing data; 14 were rebuilt (23%). In the
  main LookML view, 30 of 36 measures translate.
- **Metrics files are fast to write when the data is understood.** Profiling the two wastewater datasets
  needed only a few small queries (the 100 GB table was profiled by scanning about 0.07 GB). It found the
  join between them, a 100 GB column to avoid, and several data-quality issues.
- **Automated checks.** 52 API checks and 27 browser checks pass in local mode, and 59 checks pass for an
  external deployment with the developer pages turned off. See `VALIDATION.md`.
- **Not measured.** Agreement with Looker's numbers; behaviour under many users; accessibility; Looker API
  performance.

## 5. The hosting facts that matter more than the definition choice

These come from the earlier spike (ONEVERILY-152005) and from what the prototypes ran into. They hold
whichever way definitions are written, and they decide whether an external reader can use any of this.

| Need | What we know | Our prototypes |
|---|---|---|
| **Analytics owns the build end to end** | Analysts can own definitions and review. New chart types, deployment and support need engineers. | Partly: analysts own the metrics file or LookML; engineering wrote all chart and query code. |
| **Named external users** | Per ONEVERILY-152005: a workspace share needs an existing Workbench account for that email; a Reader cannot create apps and cannot see another user's running app; each reader would launch their own VM. Whether a sponsor may hold an account is untested. | **Not met.** We did not test Reader and Writer sharing. |
| **Aggregate-only** | The platform does not enforce it. The app queries BigQuery as the workspace service account. A Writer can edit an app. | **Met by design, untested on the platform.** Fixed aggregate queries, no SQL box, no page shows rows, and the developer pages (tables, LookML explorer) can be switched off with `DEV_TOOLS=0`, which the deployment configuration sets. |
| **Scheduled or certified refresh** | Missing as a Workbench feature: live queries while the VM is up, no frozen render, a restart does not pull the latest code. | **Not met.** Live queries with a 10-minute cache. No "data as of" stamp. |
| **Export (PDF or image)** | No platform PDF. | **Not built.** |

Two practical points from our own deployment attempts match the spike: the app definition could not be edited
after creation as far as we could tell (a new repository, branch or folder meant creating a new app), and the
deployed app's service account had no data access until a grant is made. With one VM per reader, cost and
support grow with the number of sponsors.

**dbt Charts.** The spike looked at it as the alternative host. Because Workbench is the chosen platform, we did
not pursue it. Two ideas carry over: a dashboard as one readable definition file (our metrics file works the
same way), and a validation step that fails when a defined column does not exist. The Security question about
a third party holding a BigQuery credential matters only if the Workbench route falls through.

## 6. Risks, dependencies and open questions

| # | Item | Why it matters | Suggested owner | Status |
|---|---|---|---|---|
| 1 | **No shareable apps in Workbench** | An external reader cannot open a link, sign in and see a dashboard. This is the critical path. | Workbench team | On the roadmap, no date |
| 2 | **Can sponsors hold a Workbench account, and at what role?** | A Reader cannot launch an app or see another's. Without sharing, a custom app does not meet "named external users". | Workbench team, product | Unknown |
| 3 | **Data-use launch** | Required before the service account is granted data access, and covers who may see what. | Product with data owners | Not started |
| 4 | **Service-account data access** | The deployed app returns "access denied" until granted. | Data owners | Not granted |
| 5 | **Looker API access and capacity** | Needed for the preferred route; keys could not be obtained. External use also raises the scaling question from ONEVERILY-150812. | Looker admins | Open |
| 6 | **Numbers not compared with Looker** | Accuracy of approach A is unknown. | Analyst | Open |
| 7 | **No certified refresh or export** | An external audience often needs a dated, citable number and a PDF. | Product, engineering | Not built |
| 8 | **Definitions are drafts** | The wastewater rules (median of the PMMoV-normalised value, zero handling, 12-month window) were drafted by the assistant. | Analyst, data owner | Not reviewed |
| 9 | **Data-quality rules** | Outliers up to about 2 billion copies, a 1970 date, many zero medians. | Analyst, data owner | Not decided |
| 10 | **Five Sightline dashboards already exist in the LookML repository**, with a Sightline model. Confirm whether they cover the wastewater datasets. If so, LookML exists for this data, and Looker numbers exist to compare against. | May change which approach applies. | Analytics lead | Open |
| 11 | **Writers can edit a running app** | Anyone with write access to the workspace can change what the app queries. Aggregate-only depends on controlling that role. | Workbench team, security | Open |
| 12 | **Small-group protection** | Only the member overview hides groups under 11. The others show counts such as 12 revoked consents. | Product with privacy | Open |
| 13 | **Support burden** | A hosted app is supported by checking logs on a VM and recreating it to update. That is an analyst or engineer cost per dashboard. | Engineering | Open |
| 14 | **Performance at scale** | One server, in-memory cache, a few 9 GB tiles. Fine for demonstrations. | Engineering | Not tested |

## 7. Next steps (suggested order)

1. Get an answer on items 1 and 2 (shared apps, sponsor accounts). Nothing external can launch without them.
2. Start the data-use launch (item 3) and the service-account grant (item 4).
3. Obtain Looker API access and run a short proof: ask Looker for the SQL or the result of one Lifelong tile and
   compare it with the app's number. This settles items 5 and 6 and tests the preferred route.
4. Check the existing Sightline LookML (item 10) before writing anything new for that data.
5. Have analysts review and own the drafted definitions and data-quality rules (items 8 and 9).
6. Add a "data as of" date and a PDF export if a sponsor view needs them (item 7).

## Appendix: where things are

- Dashboards: one server, steps in `DEMO.md`. Pages `/`, `/overview`, `/sightline`, `/lifelong`.
- Definitions: `app/metrics/patient_overview.yml`, `app/metrics/sightline.yml`; readable versions in
  `METRICS.md` and `SIGHTLINE_METRICS.md`; data profile in `sightline_profile.md`.
- Tests: `tools/smoke_test.py` (API) and `tools/ui_test.py` (browser); results and the sponsor-view needs table
  in `VALIDATION.md`.
- Process for building a dashboard without LookML, with roles: the README, "Building a dashboard without LookML".
