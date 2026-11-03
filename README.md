# 2026 Senate Election Tracker

The tracker is a static website built with **plain HTML, CSS, and vanilla JavaScript**. GitHub Pages serves the files in `frontend/` directly. Visitors need only a modern browser. There is no framework, bundler, npm install, Node.js runtime, or application server for the deployed site.

The dashboard covers nine Senate races and includes a separate scenario calculator. **Show test data** previews synthetic returns without changing the results-based tally. See the [project specification](senate-election-tracker-spec.md) for requirements and implementation status.

## Run locally

Use Python's built-in static server for a local preview. This command works from any folder.

```sh
python3 -m http.server 8766 --bind 127.0.0.1 --directory "/Users/michaelreno/Documents/Senate Tracker/frontend"
```

Keep the terminal open and visit <http://127.0.0.1:8766/>. Python serves the files during local preview. The dashboard logic runs in the browser.

## How results reach the site

| State or source | Where collection runs | Current behavior |
| --- | --- | --- |
| North Carolina | Visitor's browser | Downloads the official ZIP on page load and checks again about every five minutes. The browser decompresses and parses the file. An all-zero archive supplies the roster with blank vote counts. |
| Ohio | GitHub Actions | Downloads official XML with `curl`, uses Python to extract statewide Senate totals, and skips reports marked as tests. The site also offers an XML import for the current browser tab. |
| Alaska | GitHub Actions | Parses the official CSV for statewide first-choice totals. The seat remains unresolved pending ranked-choice tabulation. The parser was tested with the 2026 primary CSV. The linked general-election CSV returned 404 during validation. |
| Texas | GitHub Actions | Parses the official statewide U.S. Senate table and the reported percentage of polling locations. Blank counts remain blank. |
| Maine | GitHub Actions | Looks for the official general-election U.S. Senate workbook and reads its statewide totals. The 2020 and 2024 archives passed validation. The 2026 workbook was not listed at verification. |
| Iowa | GitHub Actions | Reads the rendered statewide Senate table from the official election-night page using headless Chromium on the runner. |
| Kansas | GitHub Actions | Checks the official archive for a 2026 general-election statewide vote totals PDF. |
| Michigan | GitHub Actions | Reads the statewide U.S. Senate totals from Michigan’s results portal. The 2026 page showed no results at verification. |
| Georgia | GitHub Actions | Reads statewide U.S. Senate totals, county coverage, and the timestamp from the official general-election page. Runoff and certification are outside this adapter. |

The **Ohio results and Pages** workflow is configured to run about every five minutes, on relevant pushes to `main`, and on manual dispatch. It runs each collector in a separate step, commits changed results to `frontend/results.json`, and deploys `frontend/`. GitHub can delay scheduled runs. Scheduled collection runs on GitHub's runner, including when nobody has the page open.

The browser checks `results.json` on page load and about every 30 seconds while open. Failed checks preserve the last accepted data in the tab. The calculator counts only published certified results with a known caucus affiliation.

## Publish changes

Set **Settings → Pages → Build and deployment → Source** to **GitHub Actions**. Push changes to `main` and check **Actions → Ohio results and Pages**. Use **Run workflow** there for a manual run. If the collector has committed a snapshot to `main` since your last pull, sync your local branch before pushing.

## Developer checks

```sh
node --test tests/*.test.mjs
python3 -B collectors/ohio.py --check
```

Node.js is used for the JavaScript tests and the optional North Carolina snapshot publisher, which also uses `unzip`. The site and its normal collection paths require no Node.js. The Ohio check uses Python and `curl` and leaves the local snapshot untouched.

Iowa uses the [official statewide Senate page](https://electionresults.iowa.gov/IA/127077/web.345435/#/detail/1000). Direct HTTP requests returned 403 during verification, while the page rendered in the browser. The scheduled job uses Python Playwright and Chromium. If live collection fails, `IOWA_CANVASS_URL` can supply an official Iowa PDF as a fallback. Kansas checks its official archive automatically. The PDF paths use `pdftotext`.
