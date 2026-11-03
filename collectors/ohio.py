"""Refresh the Ohio record in the static Pages snapshot."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

FEED = "https://liveresults.ohiosos.gov/Api/v1/download?filename=VSSC1622XmlFileBlob"
DATE = "2026-11-03"
NS = "{http://grouper.ieee.org/groups/1622/groups/2/V1/1622_2-election_results_reporting.xsd}"
LIMIT = 32 * 1024 * 1024
SNAPSHOT = Path(__file__).resolve().parents[1] / "frontend" / "results.json"


def elements(parent, name):
    return parent.findall(f".//{NS}{name}")


def only(items, label):
    matches = list(items)
    if len(matches) != 1:
        raise ValueError(f"Expected one Ohio {label}")
    return matches[0]


def value(parent, name):
    return (only(elements(parent, name), name).text or "").strip()


def parse_report(xml):
    if len(xml) > LIMIT or b"\x00" in xml or b"<!DOCTYPE" in xml.upper():
        raise ValueError("Unsupported Ohio XML")
    report = ET.fromstring(xml)
    if report.tag != f"{NS}ElectionReport" or report.get("IssuerAbbreviation") != "OH":
        raise ValueError("Expected an Ohio election report")
    if report.get("IsTest") in {"true", "1"}:
        return None
    if report.get("IsTest") not in {"false", "0"}:
        raise ValueError("Missing or invalid Ohio test flag")
    election = only((node for node in elements(report, "Election")
                     if node.get("Date") == DATE and node.get("Type") == "General"),
                    "2026 general election")
    state = only((node for node in elements(report, "GpUnit")
                  if node.get("Type") == "State"), "statewide reporting unit")
    state_id = state.attrib["ObjectId"]
    contest = only((node for node in elements(election, "Contest")
                    if node.get("Name") == "U.S. Senator"
                    and node.findtext(f"{NS}JurisdictionalScopeId", "").strip() == state_id),
                   "statewide U.S. Senate contest")
    timestamp = datetime.fromisoformat(report.attrib["GeneratedDate"])
    if timestamp.tzinfo is None:
        raise ValueError("Ohio timestamp lacks a timezone")

    roster = elements(election, "Candidate")
    parties = elements(report, "Party")
    candidates = []
    seen = set()
    for selection in elements(contest, "BallotSelection"):
        candidate_id = value(selection, "CandidateId")
        if not candidate_id or candidate_id in seen:
            raise ValueError("Duplicate or missing Ohio candidate ID")
        seen.add(candidate_id)
        candidate = only((node for node in roster if node.get("ObjectId") == candidate_id), "candidate")
        name = "".join(only(elements(candidate, "BallotName"), "ballot name").itertext()).strip()
        party_id = candidate.findtext(f"{NS}PartyId", "").strip()
        party = "Other"
        if party_id:
            party = only((node for node in parties if node.get("ObjectId") == party_id),
                         "party").attrib["Abbreviation"]
        count = only((node for node in elements(selection, "VoteCounts")
                      if node.get("Type") == "Total"
                      and node.findtext(f"{NS}GpUnitId", "").strip() == state_id),
                     "statewide candidate total").attrib["Count"]
        if not name or not party or not re.fullmatch(r"[0-9]+", count) or int(count) > 2**53 - 1:
            raise ValueError("Invalid Ohio candidate result")
        candidates.append({"name": name, "party": {"DEM": "D", "REP": "R"}.get(party, party),
                           "votes": int(count)})
    if len(candidates) < 2:
        raise ValueError("Incomplete Ohio Senate contest")
    has_votes = any(candidate["votes"] for candidate in candidates)
    if not has_votes:
        for candidate in candidates:
            candidate["votes"] = None
    return {
        "status": "reporting" if has_votes else "unresolved",
        "sourceUpdatedAt": timestamp.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "candidates": candidates,
        "sourceUrl": FEED,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate the feed without changing the snapshot")
    args = parser.parse_args()
    download = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--max-time", "30",
         "--max-filesize", str(LIMIT), FEED],
        check=True, stdout=subprocess.PIPE, timeout=35,
    )
    record = parse_report(download.stdout)
    if record is None:
        print("Ohio marked the feed as a test. Kept the last snapshot.")
        return
    if args.check:
        print(f"Validated Ohio feed with {len(record['candidates'])} candidates.")
        return
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if snapshot["electionDate"] != DATE:
        raise ValueError("Unexpected snapshot election date")
    previous = snapshot["records"].get("OH", {})
    previous_time = previous.get("sourceUpdatedAt")
    if (previous.get("status") == "certified"
            or (previous_time and datetime.fromisoformat(previous_time) >
                datetime.fromisoformat(record["sourceUpdatedAt"]))
            or (record["status"] == "unresolved" and previous.get("status") == "reporting")
            or record == previous):
        print("Kept the existing Ohio snapshot.")
        return
    snapshot["records"]["OH"] = record
    temporary = SNAPSHOT.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(SNAPSHOT)
    print(f"Updated Ohio snapshot with {len(record['candidates'])} candidates.")


if __name__ == "__main__":
    main()
