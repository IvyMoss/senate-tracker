"""Read the statewide U.S. Senate contest from Kansas's official canvass."""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from canvass import download, party_code, pdf_text
from snapshot import save_record

INDEX = "https://www.sos.ks.gov/elections/election-results.html"


class Archive(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href")
        if tag != "a" or not href:
            return
        url = urlsplit(urljoin(INDEX, href))
        if (url.scheme == "https" and url.netloc in {"www.sos.ks.gov", "sos.ks.gov"}
                and re.fullmatch(r"/elections/26elec/2026-General-(?:Election-)?Official-Vote-Totals\.pdf",
                                 url.path, re.IGNORECASE)):
            self.links.add(url.geturl())


def parse_kansas(text, year=2026):
    pages = [page for page in text.split("\f")
             if re.search(r"(?m)^\s*United States Senate\s*$", page)]
    if len(pages) != 1 or not all(marker in pages[0] for marker in
                                  ("Kansas Secretary of State", f"{year} General Election", "Official Vote Totals")):
        raise ValueError("Expected Kansas general-election statewide Senate report")
    block = re.split(r"(?m)^\s*United States Senate\s*$", pages[0], maxsplit=1)[1]
    lines = block.strip("\n").splitlines()
    candidates = []
    for line in lines:
        if not line.strip():
            continue
        row = re.fullmatch(r"\s*([A-Za-z]+)-(.+?)\s{2,}([0-9,]+)\s+([0-9.]+)%\s*", line)
        if not row:
            if re.match(r"^\S", line):
                break
            raise ValueError("Unexpected Kansas Senate candidate row")
        party, name, votes, _ = row.groups()
        candidates.append({"name": name.strip(), "party": party_code(party),
                           "votes": int(votes.replace(",", ""))})
    if len(candidates) < 2 or len({row["name"] for row in candidates}) != len(candidates):
        raise ValueError("Incomplete or duplicate Kansas Senate roster")
    return candidates


def main():
    archive = Archive()
    archive.feed(download(INDEX).decode("utf-8-sig"))
    archive.close()
    if not archive.links:
        print("Kansas has not listed a matching 2026 official general-election report.")
        return
    if len(archive.links) != 1:
        raise ValueError("Ambiguous Kansas official report links")
    url = archive.links.pop()
    save_record("KS", {"status": "reporting", "sourceUrl": url,
                       "candidates": parse_kansas(pdf_text(url))})


if __name__ == "__main__":
    main()
