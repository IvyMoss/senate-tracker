"""Store each feed separately and publish one complete record per race."""
from datetime import datetime, timezone
import json
from pathlib import Path

DATE = "2026-11-03"
SNAPSHOT = Path(__file__).resolve().parents[1] / "frontend" / "results.json"
UNKNOWN_TIME = datetime.min.replace(tzinfo=timezone.utc)


def source_time(record):
    value = record.get("sourceUpdatedAt")
    return datetime.fromisoformat(value) if value else UNKNOWN_TIME


def vote_total(record):
    votes = [candidate["votes"] for candidate in record["candidates"]]
    return sum(votes) if votes and all(value is not None for value in votes) else -1


def choose_record(sources):
    """Compare whole snapshots. Verified certification takes precedence."""
    return max(sources.items(), key=lambda entry: (
        entry[1]["status"] == "certified",
        vote_total(entry[1]),
        source_time(entry[1]),
        entry[0] == "official",
    ))[1]


def save_record(state, record, source="official"):
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if snapshot["electionDate"] != DATE:
        raise ValueError("Unexpected snapshot election date")
    records = snapshot["records"]
    sources = snapshot.setdefault("sourceRecords", {}).setdefault(state, {})
    if not sources and state in records:
        sources["official"] = records[state]
    previous = sources.get(source)
    if previous and (previous["status"] == "certified" or source_time(previous) > source_time(record)
                     or (record["status"] == "unresolved" and vote_total(previous) >= 0)
                     or previous == record):
        return
    sources[source] = record
    records[state] = choose_record(sources)
    temporary = SNAPSHOT.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(SNAPSHOT)
    print(f"{state}: updated {source}; displaying {records[state].get('sourceName', 'state election office')}.")
