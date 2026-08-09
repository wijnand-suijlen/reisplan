"""s0: download de zes GTFS-feeds en pak ze uit naar data/raw/<feed>/.

Meet downloadtijd, zip-grootte en uitgepakte grootte per feed; append naar data/metingen.csv.
"""

import csv
import sys
import time
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
METINGEN = DATA / "metingen.csv"

USER_AGENT = "reisplan-spike/0.1 (hobbyproject; wijnand.suijlen@proton.me)"

FEEDS = {
    "nl": "https://gtfs.ovapi.nl/nl/gtfs-nl.zip",
    "be": "https://gtfs.irail.be/nmbs/gtfs/latest.zip",
    "fr": "https://eu.ftp.opendatasoft.com/sncf/plandata/Export_OpenData_SNCF_GTFS_NewTripId.zip",
    "de_fv": "https://download.gtfs.de/germany/fv_free/latest.zip",
    "de_rv": "https://download.gtfs.de/germany/rv_free/latest.zip",
    "ch": "https://data.opentransportdata.swiss/en/dataset/timetable-2026-gtfs2020/permalink",
}


def meet(stap: str, feed: str, metric: str, waarde) -> None:
    METINGEN.parent.mkdir(parents=True, exist_ok=True)
    nieuw = not METINGEN.exists()
    with METINGEN.open("a", newline="") as f:
        w = csv.writer(f)
        if nieuw:
            w.writerow(["stap", "feed", "metric", "waarde"])
        w.writerow([stap, feed, metric, waarde])


def download(feed: str, url: str) -> Path:
    doel = RAW / f"{feed}.zip"
    doel.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    with requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=120) as r:
        r.raise_for_status()
        with doel.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    duur = time.monotonic() - t0
    grootte = doel.stat().st_size
    print(f"{feed}: {grootte / 1e6:.1f} MB in {duur:.0f} s", flush=True)
    meet("s0", feed, "download_s", f"{duur:.1f}")
    meet("s0", feed, "zip_bytes", grootte)
    return doel


def uitpakken(feed: str, zippad: Path) -> None:
    doelmap = RAW / feed
    doelmap.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zippad) as z:
        z.extractall(doelmap)
    totaal = sum(p.stat().st_size for p in doelmap.rglob("*") if p.is_file())
    meet("s0", feed, "uitgepakt_bytes", totaal)
    for p in sorted(doelmap.iterdir()):
        if p.is_file():
            meet("s0", feed, f"bestand:{p.name}", p.stat().st_size)
    print(f"{feed}: uitgepakt {totaal / 1e6:.1f} MB", flush=True)


def main() -> None:
    alleen = sys.argv[1:] or list(FEEDS)
    for feed in alleen:
        zippad = download(feed, FEEDS[feed])
        uitpakken(feed, zippad)


if __name__ == "__main__":
    main()
