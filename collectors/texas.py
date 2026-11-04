"""Collect statewide Texas Senate results from the Secretary of State."""
from base64 import b64decode
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import re
import subprocess
from zoneinfo import ZoneInfo

from snapshot import DATE, save_record

FEED = "https://electionresults.sos.state.tx.us/results.html"


PORTAL = "https://goelect.txelections.civixapps.com/ivis-enr-ui/races"
PORTAL_FEED = "https://goelect.txelections.civixapps.com/api-ivis-system/api/s3/enr/election/53815"


def parse_portal(payload):
    report = json.loads(payload)
    home = json.loads(b64decode(report["Home"], validate=True))
    if home["ElecDate"] != "11032026" or not re.fullmatch(r"enr/53815/[0-9]+/", report["Version"]):
        raise ValueError("Unexpected Texas portal election")
    federal = json.loads(b64decode(report["Federal"], validate=True))
    senate, = (race for race in federal["Races"] if race["id"] == 5075
               and race["N"].strip() == "U. S. SENATOR")
    candidates = []
    for row in senate["Candidates"]:
        name, party, votes = row["N"].strip(), row["P"].strip(), row["V"]
        if not name or not party or type(votes) is not int or not 0 <= votes <= 2**53 - 1:
            raise ValueError("Invalid Texas portal candidate row")
        candidates.append({"name": name, "party": {"REP": "R", "DEM": "D", "W": "Write-in"}.get(party, party),
                           "votes": votes})
    total = senate["T"]
    if (len(candidates) < 2 or len({row["name"] for row in candidates}) != len(candidates)
            or type(total) is not int or sum(row["votes"] for row in candidates) != total):
        raise ValueError("Texas portal Senate counts do not reconcile")
    if not total:
        return None
    return {"status": "reporting", "candidates": candidates,
            "sourceName": "Texas Secretary of State", "sourceUrl": PORTAL}


class ResultsPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.contest = ""
        self.senate_tables = []
        self.table = None
        self.row = None
        self.capture = None
        self.parts = []
        self.progress = []

    def handle_starttag(self, tag, attrs):
        css = dict(attrs).get("class")
        if tag == "div" and css in {"election", "polling"}:
            self.capture = css
            self.parts = []
        if tag == "table" and css == "election" and self.contest == "U. S. SENATOR":
            self.table = []
        if self.table is not None and tag == "tr":
            self.row = []
        if self.row is not None and tag in {"th", "td"}:
            self.capture = tag
            self.parts = []

    def handle_data(self, data):
        self.text.append(data)
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        capture = self.capture
        if capture == tag or (tag == "div" and capture in {"election", "polling"}):
            content = " ".join("".join(self.parts).split())
            if capture == "election":
                self.contest = content
            elif capture == "polling" and self.contest == "U. S. SENATOR":
                self.progress.append(content)
            elif capture in {"th", "td"}:
                self.row.append(content)
            self.capture = None
        if tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        if tag == "table" and self.table is not None:
            self.senate_tables.append(self.table)
            self.table = None


def parse_texas(payload):
    page = ResultsPage()
    page.feed(payload.decode("utf-8-sig"))
    page.close()
    text = " ".join(" ".join(page.text).split())
    updated = re.findall(r"2026 NOVEMBER GENERAL ELECTION\s*\(Updated (\d{2}/\d{2}/\d{4} \d{2}:\d{2} [AP]M)\)", text)
    if "Election Results - Tuesday, November 3, 2026" not in text or len(updated) != 1:
        raise ValueError("Unexpected Texas election or publication timestamp")
    if len(page.senate_tables) != 1 or len(page.progress) != 1:
        raise ValueError("Expected one statewide Texas U.S. Senate table")
    progress = re.fullmatch(r"Polling Locations Reporting:\s*(\d+(?:\.\d+)?)%", page.progress[0])
    if not progress or float(progress[1]) > 100:
        raise ValueError("Invalid Texas polling locations percentage")
    header, *rows = page.senate_tables[0]
    if header != ["Party", "Candidate", "Ballots Cast"] or len(rows) < 2:
        raise ValueError("Unexpected Texas results columns")
    candidates = []
    names = set()
    for party, name, count in rows:
        if not party or not name or name in names:
            raise ValueError("Invalid or duplicate Texas candidate")
        names.add(name)
        if count and not re.fullmatch(r"[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+", count):
            raise ValueError("Invalid Texas vote count")
        votes = int(count.replace(",", "")) if count else None
        if votes is not None and votes > 2**53 - 1:
            raise ValueError("Texas vote count exceeds safe range")
        candidates.append({"name": name, "party": {"DEMOCRATIC": "D", "REPUBLICAN": "R"}.get(party, party),
                           "votes": votes})
    timestamp = datetime.strptime(updated[0], "%m/%d/%Y %I:%M %p").replace(tzinfo=ZoneInfo("America/Chicago"))
    return {
        "status": "reporting" if any(candidate["votes"] is not None for candidate in candidates) else "unresolved",
        "candidates": candidates,
        "reportingPercent": float(progress[1]),
        "sourceUpdatedAt": timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sourceUrl": FEED,
    }


def download(url):
    return subprocess.check_output(
        ["curl", "--fail", "--silent", "--show-error", "--max-time", "20",
         "--max-filesize", str(8 * 1024 * 1024), url],
        timeout=25,
    )


def main():
    try:
        record = parse_portal(download(PORTAL_FEED))
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"Texas portal results unavailable: {error}. Checking the legacy state page.")
    else:
        if record is not None:
            save_record("TX", record, source="official-portal")
            return
        print("Texas portal has no reported Senate votes. Checking the legacy state page.")

    cache_key = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    record = parse_texas(download(f"{FEED}?refresh={cache_key}"))
    updated = datetime.fromisoformat(record["sourceUpdatedAt"]).astimezone(ZoneInfo("America/Chicago"))
    if updated.date().isoformat() < DATE:
        print(f"Texas served a pre-election page dated {updated.date()}. Kept the last snapshot.")
        return
    if record["status"] == "unresolved":
        print("Texas has not posted Senate vote counts on this page. Kept the last snapshot.")
        return
    save_record("TX", record)


if __name__ == "__main__":
    main()
