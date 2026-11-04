"""Collect the statewide U.S. Senate contest from South Carolina's ENR report."""
import io
import re
import subprocess
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from snapshot import save_record

BASE = "https://www.enr-scvotes.org/SC/127300/"
LIMIT = 32 * 1024 * 1024


def download(url):
    return subprocess.check_output(
        ["curl", "-fsS", "--max-time", "20", "--max-filesize", str(LIMIT), url], timeout=25,
    )


def parse_report(payload):
    with ZipFile(io.BytesIO(payload)) as archive:
        entries = [entry for entry in archive.infolist() if entry.filename.lower().endswith(".xml")]
        if len(entries) != 1 or entries[0].file_size > LIMIT:
            raise ValueError("Unexpected South Carolina report archive")
        xml = archive.read(entries[0])
    if b"\x00" in xml or b"<!DOCTYPE" in xml.upper():
        raise ValueError("Unsupported South Carolina results XML")
    root = ET.fromstring(xml)
    if root.tag != "ElectionResult" or re.search(r"\btest\b", root.get("ElectionName", ""), re.I):
        raise ValueError("Unexpected South Carolina election report")
    contests = [contest for contest in root.findall(".//Contest")
                if re.fullmatch(r"(?:u\.?\s*s\.?|united states)\s+(?:senate|senator)(?:\s+special(?: election)?)?",
                                contest.get("text", "").strip(), re.I)]
    if len(contests) != 1:
        raise ValueError("Expected one statewide South Carolina Senate contest")
    candidates = []
    for choice in contests[0].findall("Choice"):
        name = choice.attrib["text"].strip()
        party = choice.get("party", "").strip()
        votes = choice.attrib["totalVotes"]
        if not name or not re.fullmatch(r"[0-9]+", votes):
            raise ValueError("Invalid South Carolina Senate candidate totals")
        candidates.append({"name": name, "party": {"DEM": "D", "REP": "R"}.get(party, party or "Other"),
                           "votes": int(votes)})
    if len(candidates) < 2 or len({row["name"].casefold() for row in candidates}) != len(candidates):
        raise ValueError("Incomplete or duplicate South Carolina Senate candidates")
    return candidates


def main():
    response = download(BASE + "current_ver.txt")
    version = response.removeprefix(b"\xef\xbb\xbf").strip()
    if not re.fullmatch(rb"[0-9]+", version):
        kind = "an HTML page" if version.startswith(b"<") else "an empty response" if not version else "a nonnumeric response"
        raise SystemExit(f"South Carolina's report version endpoint returned {kind}. Kept the last snapshot.")
    version = version.decode("ascii")
    url = BASE + version + "/reports/detailxml.zip"
    candidates = parse_report(download(url))
    if not any(row["votes"] for row in candidates):
        print("South Carolina state report has no reported Senate votes yet.")
        return
    save_record("SC", {"status": "reporting", "candidates": candidates,
                       "sourceName": "South Carolina Election Commission", "sourceUrl": url})


if __name__ == "__main__":
    main()
