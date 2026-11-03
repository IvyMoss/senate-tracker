"""Discover Maine's general-election Senate workbook and read statewide totals."""
from html.parser import HTMLParser
import io
import re
import subprocess
from urllib.parse import urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from snapshot import save_record

INDEX = "https://www1.maine.gov/sos/elections-voting/election-results-data"
HOSTS = {"www.maine.gov", "www1.maine.gov"}
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
LIMIT = 8 * 1024 * 1024


class ResultsIndex(HTMLParser):
    def __init__(self, date):
        super().__init__()
        self.date = date
        self.section = None
        self.tag = None
        self.parts = []
        self.href = None
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if re.fullmatch(r"h[1-6]", tag) or tag == "a":
            self.tag = tag
            self.parts = []
            self.href = dict(attrs).get("href")

    def handle_data(self, data):
        if self.tag:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag != self.tag:
            return
        label = " ".join("".join(self.parts).lower().split())
        if tag.startswith("h"):
            level = int(tag[1])
            if self.date in label and "general election" in label:
                self.section = level
            elif self.section is not None and level <= self.section:
                self.section = None
        elif self.section is not None and self.href and re.fullmatch(
            r"(?:united states|u\.?\s*s\.?) senator(?: \(excel\))?", label
        ):
            url = urlsplit(urljoin(INDEX, self.href))
            if (url.scheme == "https" and url.netloc in HOSTS and
                    url.path.startswith("/sos/sites/") and url.path.lower().endswith(".xlsx")):
                self.links.add(urlunsplit(("https", "www1.maine.gov", url.path, url.query, "")))
        self.tag = None


def workbook_totals(payload):
    with ZipFile(io.BytesIO(payload)) as workbook:
        def read_xml(path):
            entry = workbook.getinfo(path)
            if entry.file_size > LIMIT:
                raise ValueError("Maine workbook entry exceeds size limit")
            xml = workbook.read(entry)
            if b"\x00" in xml or b"<!DOCTYPE" in xml.upper():
                raise ValueError("Unsupported Maine workbook XML")
            return ET.fromstring(xml)

        sheets = [name for name in workbook.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)]
        if len(sheets) != 1:
            raise ValueError("Expected one Maine results worksheet")
        strings = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            strings = ["".join(node.text or "" for node in item.iter(NS + "t"))
                       for item in read_xml("xl/sharedStrings.xml")]
        rows = {}
        for row in read_xml(sheets[0]).iter(NS + "row"):
            cells = {}
            for cell in row.findall(NS + "c"):
                address = re.fullmatch(r"([A-Z]+)[0-9]+", cell.get("r", ""))
                if not address:
                    raise ValueError("Invalid Maine worksheet cell address")
                value = cell.findtext(NS + "v", "")
                if cell.get("t") == "s":
                    value = strings[int(value)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter(NS + "t"))
                cells[address[1]] = value.strip()
            rows[row.get("r")] = cells

    header = rows.get("1", {})
    if header.get("A") not in {"COUNTY", "CTY"} or header.get("B") != "MUNICIPALITY":
        raise ValueError("Unexpected Maine workbook header")
    totals = [row for row in rows.values()
              if row.get("B", "").upper() in {"STATE TOTAL", "STATEWIDE TOTALS"}]
    if len(totals) != 1:
        raise ValueError("Expected one Maine statewide total row")
    parties = rows.get("3", {})
    candidates = []
    for column, name in header.items():
        if column in {"A", "B"} or not name or name.upper() in {"BLANK", "TBC"}:
            continue
        party = parties.get(column) or ("Write-in" if name.lower() == "others" else "")
        count = totals[0].get(column, "")
        if not party or not re.fullmatch(r"[0-9]+", count) or int(count) > 2**53 - 1:
            raise ValueError("Invalid Maine candidate total")
        candidates.append({"name": name, "party": {"Democratic": "D", "Republican": "R"}.get(party, party),
                           "votes": int(count)})
    if len(candidates) < 2 or len({candidate["name"] for candidate in candidates}) != len(candidates):
        raise ValueError("Incomplete or duplicate Maine candidate roster")
    summary = {label: totals[0].get(column, "") for column, label in header.items()
               if label in {"BLANK", "TBC"}}
    if (summary.keys() != {"BLANK", "TBC"}
            or any(not re.fullmatch(r"[0-9]+", value) for value in summary.values())
            or sum(candidate["votes"] for candidate in candidates) + int(summary["BLANK"]) != int(summary["TBC"])):
        raise ValueError("Maine statewide totals do not reconcile")
    return candidates


def download(url):
    return subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--max-time", "30",
         "--max-filesize", str(LIMIT), url],
        check=True, stdout=subprocess.PIPE, timeout=35,
    ).stdout


def main():
    index = ResultsIndex("november 3, 2026")
    index.feed(download(INDEX).decode("utf-8"))
    index.close()
    if not index.links:
        print("No matching Maine 2026 general-election Senate workbook listed. Kept the last snapshot.")
        return
    if len(index.links) != 1:
        raise ValueError("Ambiguous Maine Senate workbook links")
    source = index.links.pop()
    candidates = workbook_totals(download(source))
    if not any(candidate["votes"] for candidate in candidates):
        print("Maine workbook has no reported votes. Kept the last snapshot.")
        return
    save_record("ME", {"status": "reporting", "candidates": candidates, "sourceUrl": source})


if __name__ == "__main__":
    main()
