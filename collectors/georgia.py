"""Read Georgia's statewide U.S. Senate general-election results."""
from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo

from snapshot import save_record

SOURCE = "https://results.sos.ga.gov/results/public/Georgia/11032026GeneralAndSpecialElection"
TITLE = "November 3, 2026 - General & Special Elections"
COUNT = re.compile(r"[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+")


def parse_georgia(rows, coverage, update_text):
    reporting = re.fullmatch(r"([0-9]+)\s*/\s*159", coverage)
    if not reporting or int(reporting[1]) > 159:
        raise ValueError("Invalid Georgia county coverage")
    reported = int(reporting[1])
    updated = re.search(
        r"Last Updated\s+(\w+, \w+ \d{1,2}, \d{4} at \d{1,2}:\d{2}:\d{2} [AP]M)",
        update_text,
    )
    if not updated:
        raise ValueError("Missing Georgia source timestamp")
    stamp = datetime.strptime(updated[1], "%A, %B %d, %Y at %I:%M:%S %p")
    stamp = stamp.replace(tzinfo=ZoneInfo("America/New_York"))
    if stamp.date() < datetime(2026, 11, 3).date():
        raise ValueError("Georgia source timestamp predates election day")
    candidates = []
    names = set()
    for label, party, count in rows:
        name = label.removesuffix(f" ({party})").strip() if party else label
        if not name or name in names or not COUNT.fullmatch(count):
            raise ValueError("Invalid or duplicate Georgia candidate row")
        names.add(name)
        votes = int(count.replace(",", ""))
        if votes > 2**53 - 1:
            raise ValueError("Georgia vote count exceeds safe range")
        code = party.casefold()
        candidates.append({"name": name, "party": {"dem": "D", "rep": "R"}.get(code, party or "Other"),
                           "votes": votes})
    if len(candidates) < 2:
        raise ValueError("Incomplete Georgia Senate roster")
    has_returns = reported > 0 or any(candidate["votes"] for candidate in candidates)
    if not has_returns:
        for candidate in candidates:
            candidate["votes"] = None
    return {
        "status": "reporting" if has_returns else "unresolved",
        "candidates": candidates,
        "reporting": reported,
        "reportingTotal": 159,
        "reportingUnit": "counties",
        "sourceUpdatedAt": stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sourceUrl": SOURCE,
    }


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(20_000)
        response = page.goto(SOURCE, wait_until="domcontentloaded", timeout=30_000)
        if response is None or not response.ok or page.url != SOURCE:
            raise ValueError("Official Georgia results page unavailable or redirected")
        page.get_by_role("heading", name=TITLE, exact=True).wait_for()
        contest = page.get_by_role("article").filter(
            has=page.get_by_role("heading", name="US Senate", exact=True)
        )
        contest.locator(".ballot-option .vote-total > span:not(.visually-hidden)").first.wait_for()
        rows = contest.locator(".ballot-option").evaluate_all(
            """options => options.map(option => [
                option.querySelector('.candidate .flex-fill .d-flex > div')?.textContent.trim() ?? '',
                option.querySelector('.candidate .text-muted.small')?.textContent.trim() ?? '',
                option.querySelector('.vote-total > span:not(.visually-hidden)')?.textContent.trim() ?? ''
            ])"""
        )
        coverage = contest.locator(".units-reporting + span").inner_text()
        updated = page.get_by_text("Last Updated", exact=True).locator("..").inner_text()
        save_record("GA", parse_georgia(rows, coverage.strip(), updated))


if __name__ == "__main__":
    main()
