"""Read comparable statewide Senate totals from Open America's public relay."""
from datetime import datetime
import json
import subprocess

from snapshot import save_record

URL = "https://openamerica.io/elections/results.json?year=2026&office=Senate"
RACES = {"FL": "FL", "FL-special": "FL", "GA": "GA", "IA": "IA", "MI": "MI",
         "NC": "NC", "SC": "SC", "TX": "TX"}


def parse_feed(payload, year=2026):
    if (payload.get("api"), payload.get("year"), payload.get("office")) != (1, year, "Senate"):
        raise ValueError("Unexpected Open America Senate feed")
    races = payload["races"]
    expected_source = "state" if year == 2026 else f"state-{year}"
    if races and payload.get("source") != expected_source:
        raise ValueError("Unexpected Open America provenance")
    for key in sorted(RACES.keys() & races.keys()):
        state = RACES[key]
        race = races[key]
        try:
            candidates = []
            names = set()
            for candidate in race["cands"]:
                name = candidate["n"].strip()
                party = candidate["p"].strip()
                votes = candidate["v"]
                if not name or name.casefold() in names or type(votes) is not int or not 0 <= votes <= 2**53 - 1:
                    raise ValueError("Invalid candidate row")
                names.add(name.casefold())
                candidates.append({"name": name, "party": party or "Other", "votes": votes})
            total = race["total"]
            if len(candidates) < 2 or type(total) is not int or sum(row["votes"] for row in candidates) != total:
                raise ValueError("Candidate counts do not reconcile")
            if total == 0:
                continue
            record = {
                "status": "reporting", "candidates": candidates,
                "sourceName": "State election office via Open America",
                "sourceUrl": "https://openamerica.io/elections/api/",
            }
            # The documented top-level as_of is shared across all states.
            # Only an explicitly race-level timestamp can break a tie.
            timestamp = race.get("as_of")
            if timestamp:
                parsed = datetime.fromisoformat(timestamp)
                if parsed.tzinfo is None:
                    raise ValueError("Missing time zone")
                record["sourceUpdatedAt"] = parsed.isoformat()
            yield state, record
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            print(f"{state}: rejected Open America record: {error}")


def main():
    response = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--compressed", "--max-time", "20",
         "--max-filesize", str(4 * 1024 * 1024), "--user-agent", "SenateTracker/1.0 (IvyMoss/senate-tracker)", URL],
        check=True, stdout=subprocess.PIPE, timeout=25,
    )
    collected = set()
    for state, record in parse_feed(json.loads(response.stdout)):
        save_record(state, record, source="open-america")
        collected.add(state)
    print("Open America usable returns:", ", ".join(sorted(collected)) or "none")
    print("Open America no usable returns:", ", ".join(sorted(set(RACES.values()) - collected)) or "none")


if __name__ == "__main__":
    main()
