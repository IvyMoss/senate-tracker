"""Collect Alaska's first-choice Senate totals for the static snapshot."""
from collections import defaultdict
import csv
import io
import json
from pathlib import Path
import re
import ssl
import subprocess
import tempfile

from snapshot import save_record

RESULTS = "https://www.elections.alaska.gov/enr/26GENR/results/"
FEED = RESULTS + "GA_ENR_Precinct_State_of_Alaska.csv"
LIMIT = 16 * 1024 * 1024
# The state's server omits the intermediate that issued its certificate.
# Browsers fetch it from the certificate's AIA link; curl needs it supplied.
INTERMEDIATE = Path(__file__).resolve().parent / "certs" / "globalsign-gcc-r46-ov-tls-ca-2025.pem"
SYSTEM_BUNDLES = ("/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem")


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


def ca_bundle():
    defaults = ssl.get_default_verify_paths()
    system = next((path for path in (defaults.cafile, *SYSTEM_BUNDLES) if path and Path(path).is_file()), None)
    if system is None:
        raise SystemExit("No system CA bundle found for the Alaska download.")
    bundle = tempfile.NamedTemporaryFile("wb", suffix=".pem", delete=False)
    with bundle:
        bundle.write(Path(system).read_bytes() + b"\n" + INTERMEDIATE.read_bytes())
    return bundle.name


def fetch(url, bundle):
    download = subprocess.run(
        ["curl", "--silent", "--show-error", "--max-time", "30", "--cacert", bundle,
         "--max-filesize", str(LIMIT), "--write-out", "\n%{http_code}", url],
        stdout=subprocess.PIPE, timeout=35,
    )
    if download.returncode:
        raise SystemExit(f"Alaska download failed (curl exit {download.returncode}). Kept the last snapshot.")
    payload, _, code = download.stdout.rpartition(b"\n")
    return payload, code


def precinct_report_url(bundle):
    """Use the CSV link the state's results page publishes, which has been renamed before."""
    payload, code = fetch(RESULTS + "statewide.js", bundle)
    try:
        url = json.loads(payload)["precinctReportUrl"] if code == b"200" else None
    except (KeyError, TypeError, ValueError):
        url = None
    if isinstance(url, str) and url.startswith(RESULTS) and url.lower().endswith(".csv"):
        return url
    print("Alaska's results page did not list a precinct CSV. Trying the last known link.")
    return FEED


def main():
    bundle = ca_bundle()
    try:
        url = precinct_report_url(bundle)
        payload, code = fetch(url, bundle)
    finally:
        Path(bundle).unlink()
    if code == b"404":
        print("Alaska has not published the linked CSV. Kept the last snapshot.")
        return
    if code != b"200":
        raise ValueError(f"Alaska download returned HTTP {code.decode('ascii')}")
    record = parse_alaska(payload)
    record["sourceUrl"] = url
    save_record("AK", record)


if __name__ == "__main__":
    main()
