# Publishing the dashboards as a shareable prototype (sample data)

The company prototype publisher (`go/prototypes`) hosts **static files only**, and any Verily employee can open a
published prototype after a Google sign-in. The real dashboards need a server and BigQuery, so they cannot be
published as they are. Instead, `tools/build_static_prototype.py` builds a static copy that:

- keeps all four pages (landing page, member overview, wastewater, Lifelong funnel) and their design, navigation,
  filters, drill-downs and map;
- answers the pages' data requests inside the browser with **made-up numbers** (`static-prototype/mock-api.js`);
- shows a "SAMPLE DATA" banner on every page;
- contains no production numbers, project or dataset names, real organization names or service accounts, and makes
  no request outside its own folder (both are checked by `tools/static_ui_test.py`).

The Lifelong page still shows the tile definitions taken from the LookML (internal wording, visible to employees).

## Build and check

```
python tools/build_static_prototype.py     # needs app/lookml (run sync-lookml.sh first)
python tools/static_ui_test.py             # 25 checks; needs Playwright and its Chromium
```

Output: `static-prototype/dist/` (open `index.html` to look at it) and `static-prototype/dist.zip` (the file to
publish). Both are ignored by git. Rebuild after any change to the pages or the sample-data generator.

## Publish

**Option A, web, nothing to install:** open `https://go/prototypes`, sign in, and upload `dist.zip`. Choose a name
and a display title, and decide whether the prototype should be listed in the gallery ("discoverable").

**Option B, command line:**

1. `brew install go`
2. Allow private Verily modules: `go env -w GOPRIVATE=github.com/verily-src/*` (keep any existing value).
3. `go install github.com/verily-src/ysamlan-experimental/prototype-publisher/cmd/prototype-publisher@latest`
4. Sign in once: `prototype-publisher login` (opens a browser).
5. Publish:
   `prototype-publisher publish static-prototype/dist.zip --name wb-dashboards-sample --display-name "Workbench dashboards (sample data)"`
   Add `--discoverable` to list it in the gallery, `--expires-days N` to change the expiry (default 365), and
   `--force` to overwrite when republishing.

The output is a URL of the form `https://go.verily.com/prototypes/view/<your-ldap>/<name>`.

## Things to know

- Anyone at Verily can open the link. The content is sample data only, but the Lifelong page's definitions come
  from internal LookML. Say so if that matters to you.
- The prototype shows the design and interactions. It does not demonstrate real numbers, real filtering over
  real data, or the data-access and sharing questions in `ARCHITECTURE_COMPARISON.md`.
- Publishing the real numbers instead would show production counts to every employee; that needs the data
  owners' agreement first and is not what this build does.
