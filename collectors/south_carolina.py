"""Collect the statewide U.S. Senate contest from South Carolina's ENR report."""
import subprocess

from clarity import Unavailable, collect
from snapshot import save_record

BASE = "https://www.enr-scvotes.org/SC/127300/"


def main():
    try:
        record = collect(BASE, "South Carolina")
    except (Unavailable, subprocess.CalledProcessError) as error:
        raise SystemExit(f"{error}. Kept the last snapshot.") from None
    if record is None:
        print("South Carolina state report has no reported Senate votes yet.")
        return
    save_record("SC", {**record, "sourceName": "South Carolina Election Commission"})


if __name__ == "__main__":
    main()
