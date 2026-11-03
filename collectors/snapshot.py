"""Save one state record without replacing other states."""
from datetime import datetime
import json
from pathlib import Path

DATE = "2026-11-03"
SNAPSHOT = Path(__file__).resolve().parents[1] / "frontend" / "results.json"


def save_record(state, record):
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if snapshot["electionDate"] != DATE:
        raise ValueError("Unexpected snapshot election date")
    previous = snapshot["records"].get(state, {})
    previous_time = previous.get("sourceUpdatedAt")
    if (previous.get("status") == "certified"
            or (previous_time and (not record.get("sourceUpdatedAt") or datetime.fromisoformat(previous_time) >
                datetime.fromisoformat(record["sourceUpdatedAt"])))
            or (record["status"] == "unresolved" and any(
                candidate["votes"] is not None for candidate in previous.get("candidates", [])
            ))
            or record == previous):
        print(f"Kept the existing {state} snapshot.")
        return
    snapshot["records"][state] = record
    temporary = SNAPSHOT.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(SNAPSHOT)
    print(f"Updated {state} snapshot with {len(record['candidates'])} candidates.")

