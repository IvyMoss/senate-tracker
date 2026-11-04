"""Read the statewide U.S. Senate contest from a Clarity ENR detail report."""
from datetime import datetime, timezone
import io
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from zoneinfo import ZoneInfo

LIMIT = 32 * 1024 * 1024
USER_AGENT = "SenateTracker/1.0 (IvyMoss/senate-tracker)"
ZONES = {"EST": "America/New_York", "EDT": "America/New_York",
         "CST": "America/Chicago", "CDT": "America/Chicago"}


class Unavailable(RuntimeError):
    pass


def download(url):
    # Clarity hosts return 502s and empty bodies under election-night load.
    return subprocess.check_output(
        ["curl", "-fsS", "--max-time", "20", "--retry", "3", "--retry-all-errors", "--retry-delay", "3",
         "--retry-max-time", "60", "--max-filesize", str(LIMIT), "--user-agent", USER_AGENT, url],
        timeout=90,
    )


def current_version(base, label):
    for attempt in range(3):
        if attempt:
            time.sleep(5)
        try:
            version = download(base + "current_ver.txt").removeprefix(b"\xef\xbb\xbf").strip()
        except subprocess.CalledProcessError:
            if attempt == 2:
                raise Unavailable(f"{label}'s report version endpoint is unavailable") from None
            continue
        if re.fullmatch(rb"[0-9]+", version):
            return version.decode("ascii")
    kind = "an HTML page" if version.startswith(b"<") else "an empty response" if not version else "a nonnumeric response"
    raise Unavailable(f"{label}'s report version endpoint returned {kind}")


def report_url(base, label):
    return base + current_version(base, label) + "/reports/detailxml.zip"


def parse_report(payload, label):
    with ZipFile(io.BytesIO(payload)) as archive:
        entries = [entry for entry in archive.infolist() if entry.filename.lower().endswith(".xml")]
        if len(entries) != 1 or entries[0].file_size > LIMIT:
            raise ValueError(f"Unexpected {label} report archive")
        xml = archive.read(entries[0])
    if b"\x00" in xml or b"<!DOCTYPE" in xml.upper():
        raise ValueError(f"Unsupported {label} results XML")
    root = ET.fromstring(xml)
    if root.tag != "ElectionResult" or re.search(r"\btest\b", root.get("ElectionName", ""), re.I):
        raise ValueError(f"Unexpected {label} election report")
    contests = [contest for contest in root.findall(".//Contest")
                if re.fullmatch(r"(?:u\.?\s*s\.?|united states)\s+(?:senate|senator)(?:\s+special(?: election)?)?",
                                contest.get("text", "").strip(), re.I)]
    if len(contests) != 1:
        raise ValueError(f"Expected one statewide {label} Senate contest")
    candidates = []
    for choice in contests[0].findall("Choice"):
        name = choice.attrib["text"].strip()
        party = choice.get("party", "").strip()
        votes = choice.attrib["totalVotes"]
        if not name or not re.fullmatch(r"[0-9]+", votes):
            raise ValueError(f"Invalid {label} Senate candidate totals")
        candidates.append({"name": name, "party": {"DEM": "D", "REP": "R"}.get(party, party or "Other"),
                           "votes": int(votes)})
    if len(candidates) < 2 or len({row["name"].casefold() for row in candidates}) != len(candidates):
        raise ValueError(f"Incomplete or duplicate {label} Senate candidates")
    return candidates, report_time(root.findtext("Timestamp", ""))


def report_time(text):
    """Return the report's publication time in UTC, or None when it is missing or unrecognized."""
    stamp = re.fullmatch(r"(\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} [AP]M) ([A-Z]{3})", text.strip())
    if not stamp or stamp[2] not in ZONES:
        return None
    local = datetime.strptime(stamp[1], "%m/%d/%Y %I:%M:%S %p").replace(tzinfo=ZoneInfo(ZONES[stamp[2]]))
    return local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def collect(base, label):
    """Return a reporting record, or None when the report has no Senate votes yet."""
    url = report_url(base, label)
    candidates, updated = parse_report(download(url), label)
    if not any(row["votes"] for row in candidates):
        return None
    record = {"status": "reporting", "candidates": candidates, "sourceUrl": url}
    if updated:
        record["sourceUpdatedAt"] = updated
    return record
