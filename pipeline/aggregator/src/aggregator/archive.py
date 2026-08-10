"""Daily export of the observation log to Parquet on R2.

The SQLite file on the VM is the working store; once a day every completed UTC day is
exported to Parquet and uploaded (rt-archive/seg/<day>.parquet, rt-archive/stops/
<day>.parquet) so the punctuality history survives the VM. Uploaded days are recorded
in SQLite, so backfill after downtime is automatic. Note: r2.upload gzips objects and
sets Content-Encoding, so fetch them through r2.download (or gunzip after a raw GET).
"""

import csv
import logging
import sqlite3
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

from . import r2
from .config import RT_ARCHIEF

log = logging.getLogger("aggregator")

CHECK_INTERVAL_S = 3600
MAX_DAYS_PER_RUN = 40  # bounded backfill per run
_next_check = 0.0


def run_if_due() -> None:
    global _next_check
    now = time.time()
    if now < _next_check:
        return
    _next_check = now + CHECK_INTERVAL_S
    if not r2.actief():
        return  # nothing to do locally; the sqlite file itself is the local store
    try:
        _export_completed_days()
    except Exception as e:
        log.warning("archive export failed: %s", e)


def _export_completed_days() -> None:
    db_path = RT_ARCHIEF / "observaties.sqlite"
    if not db_path.exists():
        return
    db = sqlite3.connect(str(db_path))
    db.execute("CREATE TABLE IF NOT EXISTS exported_days (day TEXT PRIMARY KEY, ts INT)")
    exported = {r[0] for r in db.execute("SELECT day FROM exported_days")}
    today = datetime.now(timezone.utc).date()
    days = {
        r[0] for r in db.execute(
            "SELECT DISTINCT date(ts, 'unixepoch') FROM seg_obs"
        )
    } | {
        _iso(r[0]) for r in db.execute(
            "SELECT DISTINCT service_date FROM stop_obs2 WHERE service_date != ''"
        )
    }
    todo = sorted(d for d in days if d and d < today.isoformat() and d not in exported)
    for day in todo[:MAX_DAYS_PER_RUN]:
        _export_day(db, day)
        with db:
            db.execute("INSERT OR REPLACE INTO exported_days VALUES (?, ?)",
                       (day, int(time.time())))
    db.close()


def _iso(service_date: str) -> str | None:
    try:
        return date(int(service_date[:4]), int(service_date[4:6]),
                    int(service_date[6:8])).isoformat()
    except (ValueError, IndexError):
        return None


def _export_day(db: sqlite3.Connection, day: str) -> None:
    day_start = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
    seg_rows = db.execute(
        "SELECT ts, land, segment, trip_id, delta_s FROM seg_obs WHERE ts >= ? AND ts < ?",
        (day_start, day_start + 86400),
    ).fetchall()
    stop_rows = db.execute(
        "SELECT ts, country, trip_id, service_date, cluster, delay_s FROM stop_obs2"
        " WHERE service_date = ?",
        (day.replace("-", ""),),
    ).fetchall()
    for name, columns, rows in (
        ("seg", {"ts": "BIGINT", "country": "VARCHAR", "segment": "VARCHAR",
                 "trip_id": "VARCHAR", "delta_s": "BIGINT"}, seg_rows),
        ("stops", {"ts": "BIGINT", "country": "VARCHAR", "trip_id": "VARCHAR",
                   "service_date": "VARCHAR", "cluster": "VARCHAR",
                   "delay_s": "BIGINT"}, stop_rows),
    ):
        # via CSV: duckdb's executemany prepares per row and is far too slow for this
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "obs.csv"
            with csv_path.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
            out = Path(tmp) / f"{day}.parquet"
            con = duckdb.connect()
            con.execute(
                f"COPY (SELECT * FROM read_csv('{csv_path}', header=true, columns={columns!r}))"
                f" TO '{out}' (FORMAT PARQUET, COMPRESSION zstd)"
            )
            con.close()
            r2.upload(f"rt-archive/{name}/{day}.parquet", out.read_bytes(),
                      "application/octet-stream", cache_s=86400)
    log.info("archive: exported %s (%d seg rows, %d stop rows) to R2",
             day, len(seg_rows), len(stop_rows))
