"""Collect Florida's statewide Senate special election from the state TSV."""
import csv
from datetime import datetime, timezone
import io
import subprocess

from snapshot import save_record

URL = "https://flelectionfiles.floridados.gov/enightfilespublic/20261103_ElecResultsFL.txt"


def parse_florida(payload):
    candidates = {}
    counties = {}
    for row in csv.DictReader(io.StringIO(payload.decode("utf-8-sig")), delimiter="\t"):
        if row["RaceCode"] != "USS":
            continue
        if row["ElectionDate"] != "11/03/2026" or row["RaceName"] != "United States Senator":
            raise ValueError("Unexpected Florida Senate contest")
        name = " ".join(row[field].strip() for field in
                        ("CanNameFirst", "CanNameMiddle", "CanNameLast") if row[field].strip())
        party = row["PartyCode"].strip()
        county = row["CountyCode"].strip()
        votes = row["CanVotes"].strip()
        key = (name, party)
        candidate_counties = counties.setdefault(key, set())
        if not name or not county or county in candidate_counties or not votes.isascii() or not votes.isdecimal():
            raise ValueError("Invalid or duplicate Florida Senate county row")
        candidate_counties.add(county)
        candidates[key] = candidates.get(key, 0) + int(votes)
    if len(candidates) < 2 or any(len(items) != 67 for items in counties.values()):
        raise ValueError("Incomplete Florida Senate county totals")
    return [{"name": name, "party": {"DEM": "D", "REP": "R"}.get(party, party or "Other"),
             "votes": votes} for (name, party), votes in candidates.items()]


def main():
    # The unversioned URL can serve a cached pre-election file.
    cache_key = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    download_url = f"{URL}?refresh={cache_key}"
    payload = subprocess.check_output(
        ["curl", "-fsS", "--max-time", "20", "--max-filesize", str(16 * 1024 * 1024), download_url],
        timeout=25,
    )
    candidates = parse_florida(payload)
    if not any(row["votes"] for row in candidates):
        print("Florida state file has no reported Senate votes yet.")
        return
    save_record("FL", {"status": "reporting", "candidates": candidates,
                       "sourceName": "Florida Division of Elections", "sourceUrl": URL})


if __name__ == "__main__":
    main()
