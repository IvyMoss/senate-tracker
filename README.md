# 2026 Senate Election Tracker

Local Phase 1 dashboard for nine U.S. Senate races. The default view shows awaiting-results placeholders with links to the state election authorities listed in the spec. Enable **Show test data** to preview synthetic returns, margins, and reporting progress. The results-based tally is separate from the scenario calculator.

## Run locally

```sh
python3 -m http.server 8766 --bind 127.0.0.1 --directory "/Users/michaelreno/Documents/Senate Tracker/frontend"
```

Keep the terminal running and open http://127.0.0.1:8766/ in a browser. The command works from any folder. Check **Show test data** to populate six race cards, starting with Michigan.

## Check calculations

```sh
node --test tests/*.test.mjs
```

The starting alignment assigns 45 Democratic caucus seats and 46 Republican seats outside the nine tracked races. Certified tracked outcomes with a known caucus affiliation add to those figures. The scenario calculator starts with Democratic holds in Michigan and Georgia and a pickup in North Carolina, for 48 seats.

## Publish results on a static host

Deploy the contents of `frontend/`, including `results.json` and `results.mjs`. The browser checks the snapshot on load and every 30 seconds after each request completes. It keeps the last accepted snapshot in memory if a refresh fails.

A results publisher should replace `results.json` with a complete snapshot for the election date. Use a `records` object keyed by state abbreviation. Each record supplies `status` and a `candidates` array with `name`, `party`, and `votes` (an integer or null). Include `sourceUpdatedAt` as an ISO timestamp when available. For reporting progress, provide `reporting`, `reportingTotal`, and `reportingUnit`. Set `status` to `certified` and `winnerCaucus` to `D` or `R` only for verified certified outcomes with a known caucus affiliation.

## Collect North Carolina results

Run from the project root with Node.js and the `unzip` command installed.

```sh
node collectors/update-results.mjs
```

The job downloads the [official NCSBE results archive](https://www.ncsbe.gov/results-data/election-results/historical-election-results-data), sums the Senate contest across precincts and administrative reporting units, and updates `frontend/results.json` atomically. An archive with only zeroes supplies the candidate roster with blank vote totals until voting returns appear. The archive does not provide reporting progress or establish certification, so the job leaves both out.

This command runs once. For automatic public updates, schedule it on a host that can reach the state archive and publish the updated static files. North Carolina's [election night dashboard](https://www.ncsbe.gov/results-data/election-results/about-election-results-dashboard) has a documented refresh cadence. The archive's publication cadence still needs verification. Ohio, Alaska, and Texas remain the next planned adapters.

## Collect results in the browser

The static dashboard checks North Carolina's official ZIP on load and every five minutes while open. It uses browser-native raw DEFLATE decompression. The command above is an optional snapshot publisher. The dashboard itself requires no Node.js or build step.

Ohio's XML endpoint does not grant cross-origin access to the static dashboard. Under **State results**, open **Load an Ohio results file**, download the official XML, then select the downloaded file. Imports last for the current tab session. The adapter accepts statewide totals for the November 2026 general election, rejects reports marked as tests, and leaves certification to a verified published snapshot.
