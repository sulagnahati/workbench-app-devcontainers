# Where we maintain our semantic layer, and how we build external dashboards

**Status:** proposed position for the demo meeting. **Prepared by:** [name]   **Date:** [date]
**Ticket:** [link]   **Evidence:** `ARCHITECTURE_COMPARISON.md`, `VALIDATION.md`, `sightline_profile.md`
**Related:** ONEVERILY-152005 (hosting spike), ONEVERILY-150812 (Looker scaling, closed), ONEVERILY-151935 (ARI metrics)

Written for: analytics, product and engineering leads in the demo meeting.

---

## The 30-second version

- **The real question is not which tool draws the chart. It is where our business definitions live.** Every
  dashboard, internal or external, is only as trustworthy as the definitions behind its numbers.
- **Our position:** keep one semantic layer, in version control, owned by analytics, upstream of any
  dashboard tool. Today the only layer of that kind that exists at scale is LookML, so **LookML is the system of
  record for business definitions**. Workbench apps present those numbers; they do not redefine them.
- **How we scale:** analysts own the definitions and the process; engineering provides a reusable app and the
  hosting fixes; each new external dashboard becomes a definition and a layout, not a new build.
- **What stops us from launching externally is hosting, not definitions.** Shareable apps, sponsor access, certified
  refresh and export are the critical path, and they are outside analytics' control.

## 1. The question: where do we maintain the semantic layer?

A semantic layer is the written-down meaning of our numbers: what "active", "eligible" or "pathogen level"
means, which table and filters it uses, and who is responsible for it. Where it lives decides whether two
reports can disagree, who can change a number, and how much work each new dashboard costs.

### Options

| | **LookML** (in Looker, in the existing repository) | **Definitions kept with each dashboard** (what we did for member overview and wastewater) | **In the data pipeline** (for example dbt) |
|---|---|---|---|
| What it is | Business definitions in code, reviewed and shared with internal reporting | A small definitions file next to each app | Metric definitions next to the data models |
| Exists today at scale | **Yes:** 40 dashboards, 122 views, 12 models, with code owners | No. Two files, written for the prototypes | Models exist (the wastewater dataset's name indicates a dbt output). Metric definitions were **not evaluated** |
| One definition across tools | Yes for Looker. For apps it needs the Looker API (**untested**) or a compiler we would have to maintain | No: each dashboard holds its own copy | Possible for any tool that can read it; depends on the tooling chosen |
| Governance | Strong: reviewed, owned, versioned, tied to internal reporting | Weak by default: a convention, not enforced | Strong if reviewed like code |
| Cost to add a dashboard | Low once definitions exist | Low per dashboard, but each is a new copy of the rules | Not assessed |
| Biggest risk | Our apps cannot use it directly yet | Many copies of definitions that drift | A second system to learn; not yet proven here |

### Our proposed position

1. **System of record now: LookML.** It is where definitions already live and are reviewed. New data that will
   be reported externally gets LookML first (or alongside), so Looker governs it from day one.
2. **Apps consume definitions; they do not own them.** The preferred route is for the app to ask Looker for the
   numbers or the SQL. This is the single most important thing to prove next (section 6).
3. **Per-dashboard definition files are a prototyping tool,** useful for speed (our second dashboard came
   together quickly), never the permanent home of an external metric.
4. **Revisit the home of the layer once, with evidence.** If the Looker route proves unworkable (access,
   capacity, or API limits), the fallback is to move definitions down into the data pipeline so any tool can read
   them. The decision gate is in section 6.

What would change our mind: the Looker proof failing on accuracy or capacity; Looker scaling limits
(ONEVERILY-150812) ruling out external-volume use; or the organisation standardising on a pipeline-level layer.

## 2. Our opinion on how we build external dashboards

- **Definitions first, in the governed layer, reviewed by an analyst and the data owner.**
- **One reusable app, not one build per dashboard.** A dashboard is a definition set plus a layout, using shared
  navigation, branding, charts, privacy rules and tests. The prototypes already work this way.
- **Aggregate-only by construction.** Fixed queries, no user SQL, no row-level pages, small-group rules, and
  developer tools off in any deployed app.
- **Every number carries its definition and its date.** The page shows what each number means and when the
  data was produced. (The definitions are on the pages today; the date stamp and a certified refresh are not
  built.)
- **Hosted on Workbench** (already decided), with the hosting gaps closed before any external launch.

## 3. Why it matters that analytics owns this

- **Definitions are business decisions, not code.** In the wastewater example, the choice between median and
  average, how zeros are treated, and which normalisation to use change what a sponsor concludes. Those belong to
  the people who know the data and answer for it.
- **One number, everywhere.** An external partner who sees a figure that differs from one our own team quotes is
  a trust problem. Owning the definitions in one place is how that is prevented.
- **Speed without bottlenecks.** If every new dashboard needs an engineer to write queries and layout code,
  analytics waits on engineering. With owned definitions and a reusable app, analysts add a dashboard by writing
  and reviewing definitions. The ticket's own first need is that analytics can own the process end to end.
- **Accountability and audit.** Version control shows who changed a definition, when and why. That history is what
  answers a sponsor's "why did this number change?"
- **It scales with the organisation.** The existing repository already holds 40 dashboards and 122 views. A copy of
  the rules per external dashboard multiplies the number of places to fix.

Today analytics cannot own the whole chain: chart code, deployment and fixing a deployed app still need engineers.
Section 5 sets out how that changes.

## 4. What the Sightline use case shows

Sightline (wastewater) is a good stress test because it had no obvious definitions, data in another workspace
and a domain with real technical choices. It surfaced these issues:

| Issue | What we found | Why it argues for owned, governed definitions |
|---|---|---|
| **Definitions were not written down** | The level of a pathogen, the treatment of zero and negative results, and the default date window all had to be chosen. We drafted defaults. | These are scientific decisions that an analyst and the data owner must make and record, not an engineer or an assistant. |
| **Data quality** | A 1970 creation date, concentrations up to about 2 billion copies, many weekly medians of zero when a pathogen is not detected, and a single unit. | Rules for outliers and zeros must live with the definition so every dashboard applies them the same way. |
| **Possible duplicate definitions** | The LookML repository already contains five Sightline dashboards and a Sightline model. We built the wastewater dashboard from a metrics file without confirming whether they cover the same data. | If they do, we have created exactly the second version of the truth that a governed layer exists to prevent. This needs checking before anything goes external. |
| **Two datasets from two pipelines** | Variant shares and pathogen concentrations join on a key that matches for 44 of 50 sites. | Shared concepts (plant, sample, site) need one definition across datasets. |
| **Cost and shape of the data** | The main table is 100 GB, almost all one map column; every query must filter by date and skip that column. | Cost controls belong in the definition so a new dashboard cannot accidentally scan 100 GB. |
| **Specialised charts** | A variant mix chart and a plant map were not in any template. | New chart types are engineering work. Definitions can be analyst-owned; novel visuals still need a builder. |
| **Access in another workspace** | The data is in a workspace whose membership is an admin-managed group. The app's service account needs its own grant. | Access and the data-use launch must be planned at the start, per dataset. |
| **Refresh and certification** | The tables were last modified on 9 September and no refresh schedule is stated. The dashboards show live queries with no "data as of" stamp. | A sponsor view needs a dated, certifiable number; this is not built. |
| **Small counts** | Aggregates at plant level can be small. | A small-group rule has to be defined once and applied everywhere (it exists only on the member overview today). |

## 5. Long-term plan for scaling

| Step | What happens | Owner | Done when |
|---|---|---|---|
| **1. Settle ownership and process** | Analysts own definitions and their review; product managers own questions and priorities; data owners confirm data-quality rules; engineering owns the app and hosting. Use the process and role table in the README. | Analytics lead | Roles agreed; definitions have an owner, status and validation field |
| **2. Prove the consumption path** | With Looker API access, ask Looker for the SQL or result of one Lifelong tile and compare it with the app's number. | Analytics with Looker admins | A written yes or no on accuracy, capacity and access. **Decision gate for the home of the layer** |
| **3. Close the hosting gaps** | Shared apps or an equivalent way for a named sponsor to open a link; sponsor account roles; a dated "data as of" and a PDF export; support path for a deployed app. | Workbench team, engineering | A sponsor can open a dashboard from a link, see only their view, and cite the date |
| **4. Turn the prototype into a product** | One app that reads a definition set and a layout, with shared charts, privacy rules and automated tests. A new standard dashboard needs no new code. | Engineering, with analytics reviewing | An analyst adds a dashboard from definitions and layout alone |
| **5. Scale out** | Add dashboards and sponsors; per-sponsor views with access control; monitoring of cost and speed; certified snapshots. | Analytics owns content; engineering owns the platform | A growing set of external dashboards with no copies of definitions |

Principles for scaling: definitions live once; analytics owns them and the review; the app is shared, not rebuilt;
aggregate-only is a rule of the platform and not a promise per dashboard; every external number is dated.

## 6. What we ask the meeting to decide

1. **Agree the position:** business definitions for external reporting live in one governed layer owned by analytics,
   and LookML is that layer for now.
2. **Approve the proof:** get Looker API access and run the one-tile comparison (step 2), as the gate for the long-term home.
3. **Name the owners:** an analytics owner for the definitions process, and an engineering owner for the shared app.
4. **Unblock hosting:** get answers from the Workbench team on shareable apps and sponsor accounts, and start the
   data-use launch for the service account.
5. **Check Sightline first:** confirm whether the existing Sightline LookML covers the wastewater data before more is built.

## 7. Risks and what we do not know

- Looker as the engine for the app is **untested**: access, accuracy and capacity are unknown.
- The prototype numbers have **not been compared with Looker**.
- Shareable apps do not exist and sponsor access is unconfirmed; this could delay an external launch whatever we choose.
- The pipeline-level option was not evaluated; the position above could change if it proves better.
- Definitions in the prototypes, especially the wastewater ones, are drafts awaiting analyst and data-owner review.
- The full list, with owners, is in `ARCHITECTURE_COMPARISON.md`, section 6.
