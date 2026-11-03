"""Collect Alaska's first-choice Senate totals for the static snapshot."""
from collections import defaultdict
import csv
import io
import re
import subprocess

from snapshot import save_record

FEED = "https://www.elections.alaska.gov/enr/26GENR/results/GA_ENR_Precinct_State%20of%20Alaska.csv"
LIMIT = 16 * 1024 * 1024


def parse_alaska(payload):
    rows = csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline=""), strict=True)
    required = {"Contest_title", "Contest_Id", "Selectable_Options", "Aggregation_ID",
                "Pct_seq_nbr", "Precinct_name", "candidate_id", "candidate_name",
                "Party_Code", "total_votes"}
    if not required.issubset(rows.fieldnames or []):
        raise ValueError("Unexpected Alaska results header")
    candidates = {}
    votes = defaultdict(int)
    seen = set()
    contests = set()
    for row in rows:
        if row["Contest_title"] != "U.S. Senator":
            continue
        if (any(row[key] is None for key in required) or row["Aggregation_ID"].strip()
                or row["Selectable_Options"] != "1"):
            raise ValueError("Unexpected Alaska Senate reporting unit")
        candidate_id = row["candidate_id"].strip()
        name = row["candidate_name"].strip()
        party = row["Party_Code"].strip() or "Other"
        contest = row["Contest_Id"].strip()
        unit = row["Pct_seq_nbr"].strip()
        count = row["total_votes"].strip()
        if not all((candidate_id, name, contest, unit, row["Precinct_name"].strip())) or not re.fullmatch(r"[0-9]+", count):
            raise ValueError("Invalid Alaska Senate row")
        contests.add(contest)
        key = (unit, candidate_id)
        if key in seen:
            raise ValueError("Duplicate Alaska Senate row")
        seen.add(key)
        if candidates.setdefault(candidate_id, (name, party)) != (name, party):
            raise ValueError("Inconsistent Alaska candidate identity")
        votes[candidate_id] += int(count)
        if votes[candidate_id] > 2**53 - 1:
            raise ValueError("Alaska vote total exceeds safe range")
    if len(contests) != 1 or len(candidates) < 2:
        raise ValueError("Expected one Alaska Senate contest with at least two candidates")
    has_votes = any(votes.values())
    return {
        "status": "ranked_choice_pending" if has_votes else "unresolved",
        "sourceUrl": FEED,
        "candidates": [
            {"name": name, "party": {"DEM": "D", "REP": "R"}.get(party, party),
             "votes": votes[candidate_id] if has_votes else None}
            for candidate_id, (name, party) in candidates.items()
        ],
    }


def main():
    download = subprocess.run(
        ["curl", "--silent", "--show-error", "--max-time", "30", "--max-filesize", str(LIMIT),
         "--write-out", "\n%{http_code}", FEED],
        check=True, stdout=subprocess.PIPE, timeout=35,
    )
    payload, _, code = download.stdout.rpartition(b"\n")
    if code == b"404":
        print("Alaska has not published the linked CSV. Kept the last snapshot.")
        return
    if code != b"200":
        raise ValueError(f"Alaska download returned HTTP {code.decode('ascii')}")
    save_record("AK", parse_alaska(payload))


if __name__ == "__main__":
    main()
