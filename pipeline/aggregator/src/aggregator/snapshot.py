"""Snapshot-JSON schrijven (atomisch) + gzip-archief. Contract: docs/snapshot-schema.md."""

import gzip
import json
import os
import time
from datetime import datetime, timezone

from .config import RT_ARCHIEF, WEB_DATA


def kleurklasse(p90_delta_s: int) -> int:
    if p90_delta_s < 60:
        return 0  # green: under a minute does not count as delay (owner decision 2026-08-10)
    if p90_delta_s <= 120:
        return 1  # yellow
    if p90_delta_s <= 600:
        return 2  # orange
    return 3      # red


def bouw_snapshot(dekking: dict, venster: dict, incidenten: list[dict],
                  blokkades: list[str] | None = None,
                  werkzaamheden: list | None = None) -> dict:
    return {
        "v": 1,
        "t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dekking": dekking,
        "seg": [
            [segment, kleurklasse(p90), p90, n]
            for segment, (p90, n) in sorted(venster.items())
        ],
        "inc": [i for i in incidenten if i["pos"] is not None],
        "blk": blokkades or [],  # getekende randen die feitelijk versperd zijn
        # geplande buitendienststellingen/aangepaste dienst, gegroepeerd per melding
        "wrk": [[src, sev, until, txt, sorted(randen)]
                for src, sev, until, txt, randen in (werkzaamheden or [])],
    }


def schrijf_snapshot(snap: dict) -> bytes:
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    data = json.dumps(snap, separators=(",", ":")).encode()
    tmp = WEB_DATA / "snapshot.json.tmp"
    tmp.write_bytes(data)
    os.replace(tmp, WEB_DATA / "snapshot.json")

    nu = time.gmtime()
    archiefmap = RT_ARCHIEF / "snapshots" / time.strftime("%Y/%m/%d", nu)
    archiefmap.mkdir(parents=True, exist_ok=True)
    (archiefmap / time.strftime("%H%M.json.gz", nu)).write_bytes(gzip.compress(data))
    return data
