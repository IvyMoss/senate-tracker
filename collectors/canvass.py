"""Download and extract text from an official canvass report."""
import subprocess


def download(url):
    return subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--max-time", "30",
         "--max-filesize", str(32 * 1024 * 1024), url],
        check=True, stdout=subprocess.PIPE, timeout=35,
    ).stdout


def pdf_text(url):
    data = download(url)
    if not data.startswith(b"%PDF-"):
        raise ValueError("Expected an official PDF report")
    return subprocess.run(
        ["pdftotext", "-layout", "-", "-"], input=data,
        check=True, stdout=subprocess.PIPE, timeout=30,
    ).stdout.decode("utf-8")


def party_code(code):
    return {"DEM": "D", "REP": "R"}.get(code.upper(), code.upper())
