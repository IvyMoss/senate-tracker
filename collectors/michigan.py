"""Read Michigan's statewide U.S. Senate results from the state portal."""
import re

from snapshot import save_record

SOURCE = "https://mvic.sos.state.mi.us/votehistory/Index?electionDate=11-3-2026&type=C"
SENATE = re.compile(r"UNITED STATES SENATOR(?:\s+6 YEAR TERM\s+\(1\) POSITION)?", re.I)
COUNT = re.compile(r"[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+")


def parse_michigan(rows):
    starts = [index for index, row in enumerate(rows) if len(row) == 1 and SENATE.fullmatch(row[0])]
    if len(starts) != 1:
        raise ValueError("Expected one Michigan U.S. Senate contest")
    candidates = []
    total = None
    for row in rows[starts[0] + 1:]:
        if len(row) == 1:
            break
        if len(row) < 3 or not COUNT.fullmatch(row[2]):
            raise ValueError("Invalid Michigan Senate vote row")
        party, name, count = row[:3]
        votes = int(count.replace(",", ""))
        if votes > 2**53 - 1:
            raise ValueError("Michigan count exceeds safe range")
        if name == "TOTAL VOTES:" and not party:
            total = votes
            break
        if not name or not party:
            raise ValueError("Missing Michigan candidate or party")
        candidates.append({"name": name, "party": {"DEMOCRATIC": "D", "REPUBLICAN": "R"}.get(party, party),
                           "votes": votes})
    if (len(candidates) < 2 or len({candidate["name"] for candidate in candidates}) != len(candidates)
            or sum(candidate["votes"] for candidate in candidates) != total):
        raise ValueError("Michigan Senate totals do not reconcile")
    if total == 0:
        for candidate in candidates:
            candidate["votes"] = None
    return {"status": "reporting" if total else "unresolved", "candidates": candidates, "sourceUrl": SOURCE}


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(20_000)
        response = page.goto(SOURCE, wait_until="domcontentloaded", timeout=30_000)
        if response is None or not response.ok or page.url != SOURCE:
            raise ValueError("Official Michigan results page unavailable or redirected")
        empty = page.get_by_role("heading", name="No election results for selected election date", exact=True)
        panel = page.locator("#tab-target-voteResults")
        empty.or_(panel).first.wait_for(state="attached")
        if empty.is_visible():
            print("Michigan has no results for the requested election date. Kept the last snapshot.")
            return
        if not re.search(r"Date:\s*11/3/2026\s+Type:\s*STATE GENERAL\b", page.locator("body").inner_text(), re.I):
            raise ValueError("Unexpected Michigan election date or type")
        rows = panel.locator(":scope > .row").evaluate_all(
            """rows => rows.map(row => row.children.length
                ? Array.from(row.children, cell => cell.innerText.trim())
                : [row.innerText.trim()])"""
        )
        save_record("MI", parse_michigan(rows))


if __name__ == "__main__":
    main()
