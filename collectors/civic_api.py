"""Read the nine statewide Senate races from civicAPI's public race endpoint."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import subprocess

from snapshot import DATE, save_record

RACES = {
    "AK": 86916, "GA": 87087, "IA": 87151, "KS": 87162, "ME": 87188,
    "MI": 87214, "NC": 87346, "OH": 87527, "TX": 87438,
}


def parse_race(state, race, url):
    if (race.get("country"), race.get("province"), race.get("election_type"),
            race.get("election_scope")) != ("US", state, "US Senate", "General"):
        raise ValueError("Unexpected civicAPI race")
    if (race.get("district") is not None or race.get("municipality") is not None
            or datetime.fromisoformat(race["election_date"]).date().isoformat() != DATE
            or race.get("test_data") is not False or race.get("is_disputed") is not False
            or race.get("round") != 1):
        raise ValueError("Ineligible civicAPI election, test data, or counting round")
    updated = datetime.fromisoformat(race["last_updated"])
    if updated.tzinfo is None:
        raise ValueError("Missing civicAPI time zone")
    candidates = []
    seen = set()
    for row in race["candidates"]:
        name = row["name"].strip()
        party = row["party"].strip()
        votes = row["votes"]
        if not name or name.casefold() in seen or type(votes) is not int or not 0 <= votes <= 2**53 - 1:
            raise ValueError("Invalid or duplicate civicAPI candidate")
        seen.add(name.casefold())
        candidates.append({"name": name, "party": {"Democratic": "D", "Republican": "R"}.get(party, party or "Other"),
                           "votes": votes})
    if len(candidates) < 2:
        raise ValueError("Incomplete civicAPI candidate roster")
    has_votes = any(candidate["votes"] for candidate in candidates)
    if not has_votes:
        for candidate in candidates:
            candidate["votes"] = None
    status = "unresolved"
    if has_votes:
        status = "ranked_choice_pending" if state in {"AK", "ME"} else "reporting"
    return {"status": status, "candidates": candidates,
            "sourceUpdatedAt": updated.astimezone(timezone.utc).isoformat(),
            "sourceName": "civicAPI", "sourceUrl": url}


def collect(item):
    state, race_id = item
    url = f"https://civicapi.org/api/v2/race/{race_id}"
    try:
        response = subprocess.run(
            ["curl", "--fail", "--silent", "--show-error", "--compressed", "--max-time", "15",
             "--max-filesize", str(8 * 1024 * 1024), url],
            check=True, stdout=subprocess.PIPE, timeout=20,
        )
        return state, parse_race(state, json.loads(response.stdout), url)
    except (AttributeError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as error:
        print(f"{state}: civicAPI unavailable or rejected: {error}")
        return state, None


def main():
    with ThreadPoolExecutor(max_workers=3) as pool:
        for state, record in pool.map(collect, RACES.items()):
            if record:
                save_record(state, record, source="civicapi")


if __name__ == "__main__":
    main()
