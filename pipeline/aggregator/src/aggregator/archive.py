"""Daily export of the observation log to Parquet on R2, plus local retention.

The SQLite file on the VM is the working store; once a day every completed UTC
day is exported to Parquet and uploaded (rt-archive/seg/<day>.parquet,
rt-archive/stops/<day>.parquet, rt-archive/cancels/<day>.parquet) so the
punctuality history — cancellations included — survives the VM. Uploaded days
are recorded in SQLite, so backfill after downtime is automatic. Cancels have
their own bookkeeping table because they were added to the export later: days
already marked in exported_days still get their cancels backfilled.

After exporting, local rows older than RETAIN_DAYS whose day is on R2 are
deleted: live consumers look back ~30h at most (dedup-cache warming; the
inspection date floor is 2 days), and an unbounded file (1.6 GB by Aug 2026)
made every scan disk-bound on the 1 GB VM. Without R2 nothing is exported and
therefore nothing is pruned.

Note: r2.upload gzips objects and sets Content-Encoding, so fetch them through
r2.download (or gunzip after a raw GET).
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
RETAIN_DAYS = 3        # local working set; > every consumer's lookback
DELETE_CHUNK = 50_000  # keeps the write lock short next to the poll-loop writer
_next_check = 0.0


def due() -> bool:
    """Whether an export is due. Only the scheduling lives in the aggregator
    process; run() itself happens in a short-lived child (jobs.py), because a
    day's export pulls over a million rows into memory at once."""
    global _next_check
    now = time.time()
    if now < _next_check:
        return False
    _next_check = now + CHECK_INTERVAL_S
    # nothing to do locally without R2; the sqlite file itself is the local store
    return r2.actief()


def run() -> None:
    _export_completed_days()


def _export_completed_days() -> None:
    db_path = RT_ARCHIEF / "observaties.sqlite"
    if not db_path.exists():
        return
    db = sqlite3.connect(str(db_path))
    db.execute("PRAGMA busy_timeout = 15000")
    db.execute("CREATE TABLE IF NOT EXISTS exported_days (day TEXT PRIMARY KEY, ts INT)")
    db.execute("CREATE TABLE IF NOT EXISTS exported_cancel_days"
               " (day TEXT PRIMARY KEY, ts INT)")
    exported = {r[0] for r in db.execute("SELECT day FROM exported_days")}
    exported_cancels = {r[0] for r in db.execute("SELECT day FROM exported_cancel_days")}
    today = datetime.now(timezone.utc).date().isoformat()
    days = {
        r[0] for r in db.execute(
            "SELECT DISTINCT date(ts, 'unixepoch') FROM seg_obs"
        )
    } | {
        _iso(r[0]) for r in db.execute(
            "SELECT DISTINCT service_date FROM stop_obs2 WHERE service_date != ''"
        )
    }
    cancel_days = {
        _iso(r[0]) for r in db.execute(
            "SELECT DISTINCT service_date FROM cancel_obs WHERE service_date != ''"
        )
    }
    todo = sorted(
        {d for d in days if d and d < today and d not in exported}
        | {d for d in cancel_days if d and d < today and d not in exported_cancels})
    for day in todo[:MAX_DAYS_PER_RUN]:
        _export_day(db, day, day not in exported, day not in exported_cancels)
    _prune_exported(db)
    db.close()


def _iso(service_date: str) -> str | None:
    try:
        return date(int(service_date[:4]), int(service_date[4:6]),
                    int(service_date[6:8])).isoformat()
    except (ValueError, IndexError):
        return None


def _export_day(db: sqlite3.Connection, day: str,
                do_obs: bool, do_cancels: bool) -> None:
    day_start = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
    jobs = []
    if do_obs:
        jobs.append(("seg", {"ts": "BIGINT", "country": "VARCHAR", "segment": "VARCHAR",
                             "trip_id": "VARCHAR", "delta_s": "BIGINT"},
                     db.execute(
                         "SELECT ts, land, segment, trip_id, delta_s FROM seg_obs"
                         " WHERE ts >= ? AND ts < ?",
                         (day_start, day_start + 86400)).fetchall()))
        jobs.append(("stops", {"ts": "BIGINT", "country": "VARCHAR", "trip_id": "VARCHAR",
                               "service_date": "VARCHAR", "cluster": "VARCHAR",
                               "delay_s": "BIGINT"},
                     db.execute(
                         "SELECT ts, country, trip_id, service_date, cluster, delay_s"
                         " FROM stop_obs2 WHERE service_date = ?",
                         (day.replace("-", ""),)).fetchall()))
    if do_cancels:
        jobs.append(("cancels", {"ts": "BIGINT", "country": "VARCHAR",
                                 "trip_id": "VARCHAR", "service_date": "VARCHAR",
                                 "segment": "VARCHAR"},
                     db.execute(
                         "SELECT ts, country, trip_id, service_date, segment"
                         " FROM cancel_obs WHERE service_date = ?",
                         (day.replace("-", ""),)).fetchall()))
    for name, columns, rows in jobs:
        # via CSV: duckdb's executemany prepares per row and is far too slow for this
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "obs.csv"
            with csv_path.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
            out = Path(tmp) / f"{day}.parquet"
            con = duckdb.connect()
            con.execute("SET memory_limit = '150MB'")  # in-memory db defaults to 80% of RAM
            con.execute(
                f"COPY (SELECT * FROM read_csv('{csv_path}', header=true, columns={columns!r}))"
                f" TO '{out}' (FORMAT PARQUET, COMPRESSION zstd)"
            )
            con.close()
            r2.upload(f"rt-archive/{name}/{day}.parquet", out.read_bytes(),
                      "application/octet-stream", cache_s=86400)
    with db:
        if do_obs:
            db.execute("INSERT OR REPLACE INTO exported_days VALUES (?, ?)",
                       (day, int(time.time())))
        if do_cancels:
            db.execute("INSERT OR REPLACE INTO exported_cancel_days VALUES (?, ?)",
                       (day, int(time.time())))
    log.info("archive: exported %s (%s) to R2", day,
             ", ".join(f"{len(rows)} {name} rows" for name, _, rows in jobs))


def _prune_exported(db: sqlite3.Connection) -> None:
    """Local retention (see module docstring): delete rows of days that are both
    older than RETAIN_DAYS and already exported to R2."""
    floor = (datetime.now(timezone.utc).date()
             - timedelta(days=RETAIN_DAYS)).isoformat()
    exported = {r[0] for r in db.execute("SELECT day FROM exported_days")}
    exported_cancels = {r[0] for r in db.execute("SELECT day FROM exported_cancel_days")}
    n_seg = n_stop = n_cancel = 0
    for day in sorted(d for d in exported if d < floor):
        day_start = int(datetime.fromisoformat(day)
                        .replace(tzinfo=timezone.utc).timestamp())
        n_seg += _chunked_delete(db, "seg_obs", "ts >= ? AND ts < ?",
                                 (day_start, day_start + 86400))
        n_stop += _chunked_delete(db, "stop_obs2", "service_date = ?",
                                  (day.replace("-", ""),))
    for day in sorted(d for d in exported_cancels if d < floor):
        n_cancel += _chunked_delete(db, "cancel_obs", "service_date = ?",
                                    (day.replace("-", ""),))
    if n_seg or n_stop or n_cancel:
        log.info("archive: pruned %d seg, %d stop, %d cancel rows (days < %s)",
                 n_seg, n_stop, n_cancel, floor)


def _chunked_delete(db: sqlite3.Connection, table: str, where: str, params) -> int:
    total = 0
    while True:
        with db:
            cur = db.execute(
                f"DELETE FROM {table} WHERE rowid IN"
                f" (SELECT rowid FROM {table} WHERE {where} LIMIT {DELETE_CHUNK})",
                params)
        if cur.rowcount <= 0:
            return total
        total += cur.rowcount
