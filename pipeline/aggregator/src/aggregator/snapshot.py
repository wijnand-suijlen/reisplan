"""Snapshot-JSON schrijven (atomisch) + gzip-archief. Contract: docs/snapshot-schema.md."""

import gzip
import json
import os
import time
from datetime import datetime, timezone

from .config import RT_ARCHIEF, WEB_DATA


def kleurklasse(p90_delta_s: int) -> int:
    if p90_delta_s <= 0:
        return 0  # groen
    if p90_delta_s <= 120:
        return 1  # geel
    if p90_delta_s <= 600:
        return 2  # oranje
    return 3      # rood


def bouw_snapshot(dekking: dict, venster: dict, incidenten: list[dict]) -> dict:
    return {
        "v": 1,
        "t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dekking": dekking,
        "seg": [
            [segment, kleurklasse(p90), p90, n]
            for segment, (p90, n) in sorted(venster.items())
        ],
        "inc": [i for i in incidenten if i["pos"] is not None],
    }


def schrijf_snapshot(snap: dict) -> int:
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    data = json.dumps(snap, separators=(",", ":")).encode()
    tmp = WEB_DATA / "snapshot.json.tmp"
    tmp.write_bytes(data)
    os.replace(tmp, WEB_DATA / "snapshot.json")

    nu = time.gmtime()
    archiefmap = RT_ARCHIEF / "snapshots" / time.strftime("%Y/%m/%d", nu)
    archiefmap.mkdir(parents=True, exist_ok=True)
    (archiefmap / time.strftime("%H%M.json.gz", nu)).write_bytes(gzip.compress(data))
    return len(data)
