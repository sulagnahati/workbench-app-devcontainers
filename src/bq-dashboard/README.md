# bq-dashboard: LookML-driven dashboard proof of concept

A Flask app that reads LookML from `verily-src/analytics-internal-looker` and rebuilds part of the
Looker "OneVerily Lifelong Dashboard" on BigQuery, to test whether dashboard logic can stay in LookML
while the UI lives in a Workbench app.

Status: **proof of concept.** Works when run locally with a user's own credentials. Not yet verified
end to end inside Workbench (see "Outstanding issues").

## What it does

| Page | What it shows |
|---|---|
| `/` | Generic dashboard over the tables in `BQ_TABLES` (filters, charts, 50-row preview) |
| `/lifelong` | 14 interest and consent funnel tiles from the Lifelong dashboard, with its default filters (built from LookML) |
| `/overview` | Member overview: KPIs, sign-up trend, drill-down by organization, program, state, age and sex (built from a metrics file, no LookML) |
| `/sightline` | Wastewater surveillance: SARS-CoV-2 variant mix, pathogen levels, state and plant drill-down, plant map (built from a metrics file, no LookML) |
| `/lookml` | Explorer: pick a measure and a dimension from the `patient_gold_latest` view; shows generated SQL |

Two ways of defining a dashboard are shown side by side. `/lifelong` reads existing LookML and compiles it to
SQL. `/overview` and `/sightline` read a small metrics file (`app/metrics/*.yml`) written for the dashboard.
The second route is what is needed when there is no LookML (see "Building a dashboard without LookML").

How `/lifelong` works:
1. `lifelong.dashboard.lookml` supplies the tiles, filters and their defaults.
2. `views/*.view.lkml` and `models/_common_joins.explore.lkml` supply measures, dimensions and joins.
3. `app/lookml_engine.py` compiles these to BigQuery SQL (joins, derived tables, a subset of Liquid,
   Looker filter expressions). Anything it cannot translate is reported as unsupported, not guessed.
4. Tiles are queried in BigQuery and drawn with Plotly. Every tile has a "SQL" expander.

Target data: `prj-p-1v-s0i.gold_basevalue_lifelong.*_bv_ll` (prod). Config is in `docker-compose.yaml`
(`BQ_TABLES`); the model name defaults to `basevalue_lifelong_data`, the explore the dashboard uses.

## Steps taken

### Local run (works today)
1. `git checkout overview-dashboard` (branch on the `sulagnahati` fork; it contains all pages. `add-bq-dashboard`
   has only the table, Lifelong and explorer pages).
2. `gh auth login`, then `src/bq-dashboard/sync-lookml.sh` to copy the LookML into `app/lookml/`
   (gitignored).
3. `python3 -m venv ~/bq-dash-venv` and `~/bq-dash-venv/bin/pip install -r src/bq-dashboard/app/requirements.txt`.
4. `gcloud auth application-default login`.
5. From `src/bq-dashboard/app` (on the `overview-dashboard` branch, which contains every page), set
   `BQ_TABLES` and `GOOGLE_CLOUD_PROJECT=wb-warm-greens-7036` and start the server so that it listens on this
   computer only:
   `python -c "import app; app.app.run(host='127.0.0.1', port=8080, debug=False, threaded=True)"`
   Then open `http://localhost:8080/lifelong`, `/overview` or `/sightline`.
   Do not run `python app.py` on a laptop: it listens on every network interface (which the Workbench proxy
   needs) and would let anyone on the same network open the dashboards.

### Workbench CLI on a managed Mac (no admin rights)
- Java 17 via `brew install openjdk@17` (the `temurin` cask and SDKMAN need `sudo` or Bash 4).
- Installer URL comes from `https://workbench.verily.com/api/axon/version`
  (`cliDistributionPath` + `latestSupportedCli`); download `download-install.sh`, check it is a shell
  script, run with `WORKBENCH_CLI_VERSION` set.
- Move `wb` to `~/bin` and add that to `PATH`; then `wb auth login` and `wb workspace set --id=<workspace>`.

### Deploying as a Workbench app
Create a custom app: repository = the fork, branch `add-bq-dashboard`, folder `src/bq-dashboard`.
The container name must be `application-server`, the network `app-network`, and `.devcontainer.json`
sits inside the folder (monorepo layout).

## Building a dashboard without LookML

LookML gave the Lifelong dashboard its definitions for free: someone had already decided what "consented" or
"eligible" means. Without it, those decisions have to be made and written down before anything is built. In the
Sightline demo the assistant drafted the questions, metrics and defaults to show what the artifacts look like.
**Those drafts are examples only. In a real project analysts own them, working with product managers, and
nothing in the demo has been validated by an owner.**

### Who owns what

| Step | Product manager | Analyst | Data owner | Engineer |
|---|---|---|---|---|
| Audience, decisions the dashboard supports | **Owns** | Advises | | |
| Questions to answer, priority order | **Owns** | Co-writes | | |
| Find the data, check access and the data-use launch | Starts | Does the data discovery | **Approves** | Supports |
| Profile the data, record quirks and quality issues | | **Owns** | Reviews | Runs the profiling tool |
| Metric definitions (rule, grain, filters, caveats) | Reviews meaning | **Owns** | Confirms | |
| Data-quality rules (outliers, zeros, missing data) | | **Owns** | **Confirms** | |
| Mock-up and chart choices | **Owns** | Co-designs | | Builds |
| Validate numbers against a trusted source | | **Owns** | Confirms | |
| Privacy review and launch | Coordinates | Supplies the facts | **Approves** | |
| Build, deploy, keep running | | | | **Owns** |
| Change control after launch | Approves scope | **Owns definitions** | | Owns the platform |

### Steps, with the artifact each one produces

1. **Frame the audience and the decisions.** Who uses it, what they decide with it. *Artifact: a one-paragraph brief.*
2. **Write the questions.** Five to ten plain-language questions in priority order, for example "Is the level of
   influenza A rising or falling?". *Artifact: a numbered question list. Every chart must answer one.*
3. **Take inventory of the data and get access.** Which datasets and tables, who owns them, what access exists,
   and whether a data-use launch covers this use. *Artifact: a data inventory with owner and access status.*
4. **Profile the data.** Run `tools/profile_dataset.py` and read the report: size, date range, null shares,
   distinct values, how tables join. *Artifact: a data profile (see `docs/sightline_profile.md`).*
5. **Record data-quality issues and the rule for each.** For example: outliers, zeros that mean "not detected",
   impossible dates, unmatched keys. *Artifact: a list of issues, each with a decision and who made it.*
6. **Write the metric definitions.** One entry per measure and dimension. Fields:
   name, business meaning, exact rule (SQL), grain (what one row is), source table, filters, owner,
   status (draft, reviewed, approved), who validated it and when, known caveats.
   *Artifact: the metrics file (`app/metrics/*.yml`) plus its readable version (`docs/*_METRICS.md`).*
7. **Mock up the dashboard** from the questions and metrics. Cheap and reversible; agree it before polishing.
   *Artifact: the first running version.*
8. **Validate.** Compare numbers with a trusted source (an existing report, a spreadsheet the owner trusts, a
   hand-checked sample). *Artifact: a validation log with the differences and how each was resolved.*
9. **Review privacy and sign off.** Small groups, sensitive columns, who may see it, the launch. *Artifact: sign-off.*
10. **Deploy and maintain.** Changes to a definition are changes to the metrics file and go through review by the
    metric owner, like code. *Artifact: a change history in git.*

### What the engineer provides once, so analysts do not need to code

The metrics file format, the query builder that turns it into BigQuery SQL, the chart pages, the profiling tool,
the generator for the readable metric documentation, and the small-group suppression. Analysts edit YAML and
review documents; they do not edit the Python or HTML.

A new data source may still need new chart types (Sightline needed a stacked variant chart and a state map).
That is engineering work and should be scoped separately from the definitions.

## Learnings from Sightline

Sightline data (wastewater) was used to test the process on a dataset with no LookML and no repository.

- **Start with the profile.** In under an hour it showed the size of each table, the date range, the keys that
  join the two datasets (44 of 50 sites match), and that the pathogen table is 100 GB, almost all of it one map
  column. Without the profile the first dashboard query would have scanned the whole 100 GB.
- **Cost controls belong in the definitions.** The metrics file records "always filter by date, never select the
  GeoJSON column". Partitioned tables are cheap if the partition column is always in the filter.
- **Data-quality rules are a science decision, not a coding one.** The profile found a 1970 creation date,
  concentrations up to about 2 billion copies, and medians of zero when a pathogen is not detected. The demo used
  defaults (median of the PMMoV-normalised value, negatives ignored); an analyst and the data owner should set
  the real rule.
- **Access was the longest step.** The datasets are controlled resources in another workspace, readable with a
  person's own login, but the app's service account would need its own grant (the workspace description says a
  wastewater admin adds users to a group). Plan for this at the start.
- **Reuse worked.** `/overview` was built first; `/sightline` reused the same pattern (metrics file, query builder,
  ECharts pages, privacy rule, documentation generator). The second dashboard took a fraction of the effort.
- **Branding is cheap when it is central.** The Verily palette lives in one stylesheet (`app/static/verily.css`)
  and a few constants in each page.
- **Bundle what the demo needs.** The US state outline is saved in the app so the map does not depend on a
  download at presentation time.
- **Run locally on localhost.** The Workbench-style server listens on every network interface. For laptop demos
  use the `127.0.0.1` command above.

## Outstanding issues

### 1. We keep a copy of the LookML, and it does not update itself
- The LookML is deliberately not committed (it comes from an internal repo). `sync-lookml.sh` clones it
  into `app/lookml/`; in a deployed app it would be downloaded on first use and cached on the container's
  disk.
- **If the LookML changes in GitHub the app will not notice.** Locally you must re-run
  `sync-lookml.sh`; in Workbench the cached file stays until the container is rebuilt.
- In Workbench the download needs a `GITHUB_TOKEN` with read access to the repo. No secret has been
  set up, so `/lifelong` currently shows a "not found" error there.
- Even with fresh LookML, the *interpretation* lives in our engine, a second implementation of
  Looker's SQL generation. It can drift from Looker's results.

Ways to get to "update the LookML and the app follows":

| Option | Pros | Cons |
|---|---|---|
| Re-fetch from GitHub on a schedule or on each deploy (token as a Workbench secret) | Small change to this code; no Looker dependency | Still our engine; only as accurate as it is |
| Looker API: ask Looker to run the query | Exact Looker semantics, no engine to maintain, follows whatever is deployed in Looker | Needs API credentials and network access from the app (not obtained); reads the version deployed in Looker, not GitHub directly |
| Hybrid: Looker API returns the generated SQL (`run_inline_query` with `result_format="sql"`), app runs it in BigQuery | Looker's logic, our identity and UI; data access stays in BigQuery | Needs the same Looker API access; not tested |

The Looker API options were not tried because API keys could not be obtained in time.

### 2. The app's identity does not have access to the data
- Apps run as the user's pet service account; for this workspace:
  `pet-277187115716144e61104@wb-warm-greens-7036.iam.gserviceaccount.com`. (Inferred from the repo's
  startup scripts; not confirmed on a running app.)
- It needs BigQuery Data Viewer on `prj-p-1v-s0i:gold_basevalue_lifelong` and Job User on the project
  that runs the queries. Until this is granted, the deployed app returns "Access Denied" (the dev
  dataset returned exactly this). Local runs work because they use the user's own login.
- **Getting this granted requires a data-use launch** (the company's approval process for using the
  data in a new way). The launch has to cover this app and its service account as a consumer of the
  data, and has to be approved before the data owners can grant the service account access. This is the
  critical-path dependency for any deployed version, and is a process step, not a technical one.
- Until a launch is approved, the dashboard can only be demonstrated with a user's own credentials
  (the local run above). Check that showing prod-derived numbers in a demo is acceptable under the
  user's current access.
- Running "as the user" in the app is not supported cleanly. The Workbench login token is not a Google
  token, and a manual OAuth login inside the container would expose the data to anyone with app access.
- Workaround to consider: copy the needed tables into a workspace-owned dataset. This duplicates
  patient-level data outside its home project, so it would also need to be covered by the launch; it is
  not a way around the approval.

### 3. Sharing: shareable apps do not exist yet
- Workbench does not currently offer shareable apps; they are on the roadmap. Today an app runs inside
  one user's workspace, so someone else can only see the dashboard by running their own copy.
- This is critical for the user experience. Stakeholders and external users should be able to open a
  link, authenticate, and see the dashboard, without cloning a repo, installing tools or running anything.
- Until then, the realistic options are: a live demo on the owner's screen, a static snapshot of the
  tile results, or each viewer running the app in their own workspace (which also needs their own
  data access).
- Once sharing exists, it will raise the questions this PoC does not answer: whose identity queries the
  data (the app owner's service account or each viewer's), how viewers authenticate, and how access is
  limited to the people covered by the data-use launch.

### 4. Correctness is not yet validated
- Tile numbers have not been compared with the Looker dashboard. They are internally consistent
  (Interested + Deferred + Non-responders = Eligible = 42,094 on the day tested).
- Only the interest and consent funnel is covered (14 tiles). Not covered: baseline survey, PROMIS,
  CMC and cardiometabolic tiles, table calculations (e.g. `total_eligible_string`), Looker layout.
- The engine supports a subset of Liquid (`if/elsif/else` on model name and parameters, `parameter`).
  Fields that need `condition`, user attributes or other templating are reported as unsupported.

### 5. Data sensitivity
- The `/` page shows a 50-row preview of patient-level rows (identifier columns hidden). Remove or
  restrict this before sharing the app.
- The explorer can group by any non-hidden dimension, so small cells (for example 12 revoked) can
  appear. Review before wider sharing.
- The app has no authentication of its own. Anyone who can open it sees data via its identity.

### 6. Performance and cost
- BigQuery latency was high during testing (tens of seconds per query). The page fires about 14
  queries at once. Two tiles scan about 9 GB each because eligibility joins the task table.
- Results are cached in memory for 10 minutes per app process only.

### 7. Sightline-specific
- The datasets are in workspace `wastewater-internal-data-delivery` (project `wb-arctic-date-2446`, a data
  collection). The user's login can read them. A deployed app's service account would need its own grant;
  the workspace description says a wastewater admin adds members to the `wastewater-users` group.
- The questions, the pathogen-level definition (median of `copies_per_pmmov`), the handling of zeros and the
  12-month default are drafts written by the assistant. They have not been reviewed by an analyst or the
  data owner.
- Alaska and Hawaii plants (3 of 148) are not drawn on the map. Six variant-data sites have no matching plant.
- Not yet compared with any trusted report.

### 8. Operational
- Lives on a personal fork branch, not merged into `verily-src/workbench-app-devcontainers`.
- The app's repository, branch and folder cannot be edited after creation as far as we could tell;
  changing `BQ_TABLES` means recreating the app.
- Needs a first full launch and test inside Workbench once the data-use launch is approved, the service
  account has access and the `GITHUB_TOKEN` secret exists.

## Next steps

Ordered by value for the proof of concept.

1. **Compare tiles with Looker automatically.** A test that runs each tile and checks it against the
   Looker dashboard with the same filters. Until this exists, the numbers cannot be trusted for decisions.
2. **Settle access.** Data-use launch, service account grant, and the `GITHUB_TOKEN` secret (see outstanding
   issues 1 and 2). Nothing runs in Workbench without these.
3. **Decide how the LookML stays current.** Pick between scheduled re-fetch from GitHub and the Looker
   API options in outstanding issue 1.
4. **Cover more of the dashboard.** The baseline survey, PROMIS, CMC and cardiometabolic sections, and the
   table calculations (e.g. `total_eligible_string`).
5. **Remove or restrict the row preview** on `/` before the app is shared with anyone.
6. **Drill-down.** Click a donut slice or point to break it down by age, state or organization, using the
   same LookML measures.
7. **Trends and alerts.** Week-over-week change, and a flag when a funnel step drops.
8. **Export.** CSV of the aggregates, or a scheduled summary.
9. **Show LookML definitions.** Display each measure's description beside its number so viewers know what
   "eligible" or "consented" means.
10. **Move to a shareable app** when Workbench supports it (outstanding issue 3).
11. **Hand the artifacts to analysts and PMs.** Replace the assistant-drafted questions, definitions and
    defaults with reviewed ones, and fill in owner, status and validation for each metric (see "Building a
    dashboard without LookML").

## Exploration: an agent that answers questions about the metrics

Status: **idea only, nothing built.**

Goal: let someone ask "how many people consented to Lifelong last month?" and get an answer based on the
same LookML definitions as the dashboard.

### Proposed design
- The agent gets a small set of tools, not database access: list the available measures and dimensions,
  describe one (its LookML description and SQL), and run a measure with an optional breakdown and filters.
- The tools call the existing engine in `app/lookml_engine.py`. The agent never writes its own SQL, so
  "consented" always means whatever `count_lifelong_signed_consents` means in LookML. This keeps the
  logic in one place and limits what the agent can reach.
- Each answer shows the measure, filters and generated SQL used, so a person can check it.

### Questions to settle before building
- **Model and data sharing.** The question text and aggregate results go to a model provider. Which model
  and provider are approved for this data, and does the data-use launch cover it? Not yet checked.
- **Small numbers.** Add a minimum group size (for example, never report groups under 11) so narrow
  filters cannot expose individuals.
- **Accuracy.** Build a set of questions with known answers, ideally checked against Looker, and measure
  the agent against it before anyone relies on it.
- **Cost and latency.** Queries scan GB and were slow in testing. Caching helps with repeated questions.
- **Secrets.** A model API key needs the same Workbench secrets setup that is still missing for
  `GITHUB_TOKEN`.
- **Scope.** Start with 3 or 4 tools over the 14 funnel tiles; widen only after the accuracy test passes.
