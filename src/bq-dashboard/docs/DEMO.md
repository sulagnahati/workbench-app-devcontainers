# Running the dashboards for a demo

All three dashboards run from one server on your own computer. No cloud app is needed, and a server nobody is
using costs nothing. Queries cost a fraction of a cent each, except the Lifelong page (about 10 to 15 cents per
uncached load).

## Before the demo (the day before)

1. Make sure nothing is already running on the ports:
   `lsof -nP -iTCP -sTCP:LISTEN | grep -E ":80[0-9][0-9] "; echo done`
   Only `done` should print. If a server is listed, stop it with `Ctrl+C` in its window.
2. Start a fresh terminal window (one with a `%` prompt, not one that is busy) and paste:
   ```
   cd ~/wad-overview/src/bq-dashboard/app
   export BQ_TABLES=prj-p-1v-s0i.gold_basevalue_lifelong.patient_gold_latest_bv_ll GOOGLE_CLOUD_PROJECT=wb-warm-greens-7036
   ~/bq-dash-venv/bin/python -c "import app; app.app.run(host='127.0.0.1', port=8080, debug=False, threaded=True)"
   ```
   Wait for `Running on http://127.0.0.1:8080`. The prompt does not come back; that is normal.
3. Open each page once and wait for it to fill in (the first load can take a while):
   - http://localhost:8080/lifelong
   - http://localhost:8080/overview
   - http://localhost:8080/sightline
4. If a page shows a permissions error, your Google login has expired: run
   `gcloud auth application-default login` in another terminal and reload.

## What to check on each page

- **Lifelong:** Organization dropdown has both organizations selected (use Cmd-click to change). Total Lifelong
  Eligible is about 42,000 with the default filters (numbers move as the data refreshes).
- **Overview:** the cards show numbers; click a bar in "Members" and a filter chip appears; remove it with the x.
- **Sightline:** the variant chart fills in, the trend line draws, clicking a state bar or a state on the map adds
  a state chip.

## After the demo

Press `Ctrl+C` in the server window and close it. Nothing else needs to be turned off, except the Workbench
app you created earlier if it is still running (it costs money while it runs; check the Apps list).

## If something looks wrong

Copy the red error text or the last lines from the server window. Slow pages are usually BigQuery latency:
wait a minute and reload (the second load is cached for 10 minutes).
