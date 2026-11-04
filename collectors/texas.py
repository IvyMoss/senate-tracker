"""Collect statewide Texas Senate results from the Secretary of State."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import subprocess
from zoneinfo import ZoneInfo

from snapshot import DATE, save_record

FEED = "https://electionresults.sos.state.tx.us/results.html"


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


def main():
    cache_key = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    result = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--max-time", "30",
         "--max-filesize", str(8 * 1024 * 1024), f"{FEED}?refresh={cache_key}"],
        check=True, stdout=subprocess.PIPE, timeout=35,
    )
    record = parse_texas(result.stdout)
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
