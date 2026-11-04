"""Read Iowa Senate totals from the official election-night page or canvass."""
from datetime import datetime, timezone
import os
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from canvass import party_code, pdf_text
from snapshot import save_record


def columns(line):
    return re.split(r"\s{2,}", line.strip())


def parse_iowa(text, year=2026):
    pages = text.split("\f")
    if not any("IOWA SECRETARY OF STATE" in page.upper()
               and f"{year} GENERAL ELECTION CANVASS SUMMARY" in " ".join(page.upper().split())
               for page in pages):
        raise ValueError("Unexpected Iowa election report")
    senate = False
    matches = []
    for page in pages:
        if re.search(r"(?m)^\s*United States Senator\s*$", page):
            senate = True
        if not senate:
            continue
        if re.search(r"(?m)^\s*United States Representative\b", page):
            break
        rows = [columns(line) for line in page.splitlines() if line.strip()]
        for index, row in enumerate(rows):
            if row[:2] != ["TOTAL", "Election Day"]:
                continue
            headers = [entry for entry in rows[:index] if entry[-3:] == ["Under Votes", "Over Votes", "Total"]]
            if len(headers) != 1 or index + 2 >= len(rows):
                raise ValueError("Missing Iowa statewide totals header")
            absentee, total = rows[index + 1:index + 3]
            if absentee[0] != "Absentee" or total[0] != "Total":
                raise ValueError("Incomplete Iowa statewide totals")
            header = headers[0]
            counts = total[1:]
            if len(counts) != len(header) or any(not re.fullmatch(r"[0-9,]+", count) for count in counts):
                raise ValueError("Invalid Iowa statewide counts")
            counts = [int(count.replace(",", "")) for count in counts]
            if sum(counts[:-1]) != counts[-1]:
                raise ValueError("Iowa statewide totals do not reconcile")
            candidates = []
            for label, votes in zip(header[:-3], counts[:-3]):
                if label.casefold() == "write-in":
                    name, party = label, "Write-in"
                else:
                    name, separator, party = label.rpartition(", ")
                    if not separator or not name or not re.fullmatch(r"[A-Z]{2,4}", party):
                        raise ValueError("Unexpected Iowa candidate header")
                    party = party_code(party)
                candidates.append({"name": name, "party": party, "votes": votes})
            matches.append(candidates)
            break
        if matches:
            break
    if len(matches) != 1 or len(matches[0]) < 2:
        raise ValueError("Expected Iowa statewide Senate totals")
    return matches[0]



LIVE_URL = "https://electionresults.iowa.gov/IA/127077/web.345435/#/detail/1000"
COUNT = r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)"


def parse_live(rows, reporting_text, update_text):
    rows = [row for row in rows if len(row) == 2]
    if not rows or rows[0] != ["Party / Candidate", "Votes"] or rows[-1][0] != "Vote Cast":
        raise ValueError("Unexpected Iowa statewide table")
    candidates = []
    for label, result in rows[1:-1]:
        fields = [part.strip() for part in label.splitlines() if part.strip()]
        if len(fields) == 1 and fields[0].casefold() == "write-in":
            party, name = "Write-in", fields[0]
        elif len(fields) == 2 and re.fullmatch(r"[A-Z]{2,4}", fields[0]):
            party, name = party_code(fields[0]), fields[1]
        else:
            raise ValueError("Unexpected Iowa candidate row")
        count = re.fullmatch(rf"({COUNT})\s*\([0-9]+(?:\.[0-9]+)?%\)", result)
        if not count:
            raise ValueError("Invalid Iowa vote count")
        candidates.append({"name": name, "party": party, "votes": int(count[1].replace(",", ""))})
    total = rows[-1][1]
    if (len(candidates) < 2 or len({row["name"] for row in candidates}) != len(candidates)
            or not re.fullmatch(COUNT, total)
            or sum(row["votes"] for row in candidates) != int(total.replace(",", ""))):
        raise ValueError("Iowa candidate totals do not reconcile")
    reporting = re.fullmatch(r"([0-9]+)\s*/\s*(99)\s+Counties reporting", " ".join(reporting_text.split()), re.I)
    if not reporting or int(reporting[1]) > 99:
        raise ValueError("Invalid Iowa county reporting")
    updated = re.search(r"\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} [AP]M", update_text)
    if not updated:
        raise ValueError("Missing Iowa publication timestamp")
    timestamp = datetime.strptime(updated[0], "%m/%d/%Y %I:%M:%S %p").replace(tzinfo=ZoneInfo("America/Chicago"))
    has_votes = any(row["votes"] for row in candidates)
    if not has_votes and reporting[1] == "0":
        for row in candidates:
            row["votes"] = None
    return {
        "status": "reporting" if has_votes or reporting[1] != "0" else "unresolved",
        "candidates": candidates,
        "reporting": int(reporting[1]),
        "reportingTotal": 99,
        "reportingUnit": "counties",
        "sourceUpdatedAt": timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sourceUrl": LIVE_URL,
    }


def collect_live():
    from playwright.sync_api import Error, sync_playwright

    try:
        return read_browser(sync_playwright)
    except Error as error:
        raise RuntimeError("Iowa browser request or page validation failed") from error


def read_browser(sync_playwright):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(20_000)
        response = page.goto(LIVE_URL, wait_until="domcontentloaded")
        if response is None or not response.ok or page.url != LIVE_URL:
            raise ValueError("Official Iowa page unavailable or redirected")
        # The page shows only this banner while the state publishes a new batch.
        election = page.get_by_role("heading", name="2026 General Election", exact=True)
        processing = page.get_by_text("Currently Processing New Results", exact=True)
        for attempt in range(3):
            election.or_(processing).first.wait_for()
            if election.is_visible():
                break
            if attempt == 2:
                raise ValueError("Iowa is still processing new results")
            page.wait_for_timeout(15_000)
            page.reload(wait_until="domcontentloaded")
        election.wait_for()
        page.get_by_role("heading", name="United States Senator", exact=True).wait_for()
        page.get_by_text("November 3, 2026", exact=True).wait_for()
        table = page.get_by_role("tabpanel", name="Results", exact=True).locator("table")
        table.get_by_text("Vote Cast", exact=True).wait_for()
        rows = table.locator("tr").evaluate_all(
            "rows => rows.map(row => Array.from(row.cells, cell => cell.innerText.trim()))"
        )
        reporting = page.locator("enr-editor[key=countiesreporting]").first.locator("..").inner_text()
        timestamps = page.locator("enr-editor[key=websitelastupdated]").locator("..").all_text_contents()
        return parse_live(rows, reporting, " ".join(timestamps))


def main():
    try:
        record = collect_live()
    except (ImportError, ValueError, RuntimeError) as error:
        print(f"Iowa live collection unavailable: {error}", flush=True)
        if not os.environ.get("IOWA_CANVASS_URL"):
            raise
    else:
        save_record("IA", record)
        return
    collect_canvass()


def collect_canvass():
    url = os.environ.get("IOWA_CANVASS_URL", "")
    if not url:
        print("Iowa awaits a published 2026 canvass URL.")
        return
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.netloc not in {"sos.iowa.gov", "www.sos.iowa.gov"}
            or not parts.path.lower().endswith(".pdf")):
        raise ValueError("Iowa canvass URL must be a PDF on the Secretary of State site")
    save_record("IA", {"status": "reporting", "sourceUrl": url,
                       "candidates": parse_iowa(pdf_text(url))})


if __name__ == "__main__":
    main()
