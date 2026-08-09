"""s2: filter elke feed op treinverkeer en schrijf naar data/filtered/<feed>/ (CSV + parquet).

Whitelist: route_type = 2 of 100-117 (extended rail types). Alles daarbuiten wordt
gelogd met aantallen zodat de beslissing controleerbaar is (o.a. 714 = treinvervangende
bus valt er bewust buiten). Cascade: routes -> trips -> stop_times -> stops (incl.
parent_stations) -> calendar/calendar_dates -> transfers/shapes/agency.
"""

import csv
import resource
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
FILTERED = ROOT / "data" / "filtered"
METINGEN = ROOT / "data" / "metingen.csv"

FEEDS = ["nl", "be", "fr", "de_fv", "de_rv", "ch"]
RAIL_FILTER = "(route_type::INT = 2 OR route_type::INT BETWEEN 100 AND 117)"


def meet(stap, feed, metric, waarde):
    with METINGEN.open("a", newline="") as f:
        csv.writer(f).writerow([stap, feed, metric, waarde])


def lees(con, map_, naam):
    """Registreer <naam> als view op de CSV (alles varchar; GTFS-ids zijn strings)."""
    pad = map_ / f"{naam}.txt"
    if not pad.exists():
        return False
    con.execute(
        f"""CREATE OR REPLACE VIEW {naam} AS SELECT * FROM read_csv_auto('{pad}',
            header=true, all_varchar=true, quote='"', escape='"', null_padding=true)"""
    )
    return True


def schrijf(con, feed, naam):
    doel = FILTERED / feed
    doel.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY {naam}_f TO '{doel / (naam + '.txt')}' (HEADER, DELIMITER ',')")
    con.execute(f"COPY {naam}_f TO '{doel / (naam + '.parquet')}' (FORMAT PARQUET)")
    n = con.execute(f"SELECT count(*) FROM {naam}_f").fetchone()[0]
    meet("s2", feed, f"na:{naam}", n)
    return n


def filter_feed(feed):
    map_ = RAW / feed
    con = duckdb.connect()
    import os
    if os.environ.get("REISPLAN_DUCKDB_MEM"):  # kleine VM's: spillen i.p.v. swappen
        con.execute(f"SET memory_limit='{os.environ['REISPLAN_DUCKDB_MEM']}'")
    t0 = time.monotonic()

    for naam in ["routes", "trips", "stop_times", "stops", "agency"]:
        lees(con, map_, naam)

    buiten = con.execute(
        f"SELECT route_type, count(*) FROM routes WHERE NOT {RAIL_FILTER} GROUP BY 1 ORDER BY 1"
    ).fetchall()
    if buiten:
        meet("s2", feed, "uitgesloten_route_types", "; ".join(f"{t}:{n}" for t, n in buiten))

    voor = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ["routes", "trips", "stop_times", "stops"]}
    for t, n in voor.items():
        meet("s2", feed, f"voor:{t}", n)

    con.execute(f"CREATE TABLE routes_f AS SELECT * FROM routes WHERE {RAIL_FILTER}")
    con.execute("CREATE TABLE trips_f AS SELECT * FROM trips SEMI JOIN routes_f USING (route_id)")
    con.execute("CREATE TABLE stop_times_f AS SELECT * FROM stop_times SEMI JOIN trips_f USING (trip_id)")
    con.execute(
        """CREATE TABLE stops_f AS
           WITH gebruikt AS (SELECT DISTINCT stop_id FROM stop_times_f),
           incl_parent AS (
             SELECT stop_id FROM gebruikt
             UNION
             SELECT s.parent_station FROM stops s SEMI JOIN gebruikt USING (stop_id)
             WHERE s.parent_station IS NOT NULL AND s.parent_station <> ''
           )
           SELECT s.* FROM stops s SEMI JOIN incl_parent USING (stop_id)"""
    )
    con.execute("CREATE TABLE agency_f AS SELECT DISTINCT a.* FROM agency a SEMI JOIN routes_f ON a.agency_id = routes_f.agency_id")

    for naam in ["calendar", "calendar_dates"]:
        if lees(con, map_, naam):
            con.execute(f"CREATE TABLE {naam}_f AS SELECT * FROM {naam} SEMI JOIN trips_f USING (service_id)")
    if lees(con, map_, "transfers"):
        con.execute(
            """CREATE TABLE transfers_f AS SELECT t.* FROM transfers t
               SEMI JOIN stops_f ON t.from_stop_id = stops_f.stop_id"""
        )
        con.execute("DELETE FROM transfers_f WHERE to_stop_id NOT IN (SELECT stop_id FROM stops_f)")
    if lees(con, map_, "shapes") and "shape_id" in [
        r[0] for r in con.execute("SELECT column_name FROM (DESCRIBE trips_f)").fetchall()
    ]:
        con.execute("CREATE TABLE shapes_f AS SELECT s.* FROM shapes s SEMI JOIN trips_f ON s.shape_id = trips_f.shape_id")

    tabellen = [r[0][:-2] for r in con.execute("SHOW TABLES").fetchall() if r[0].endswith("_f")]
    for naam in tabellen:
        schrijf(con, feed, naam)

    duur = time.monotonic() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # bytes op macOS
    meet("s2", feed, "duur_s", f"{duur:.1f}")
    meet("s2", feed, "piek_rss_mb", f"{rss / 1e6:.0f}")
    na_trips = con.execute("SELECT count(*) FROM trips_f").fetchone()[0]
    print(f"{feed}: {voor['trips']} -> {na_trips} trips, {duur:.1f} s, piek {rss / 1e6:.0f} MB", flush=True)


def main():
    for feed in sys.argv[1:] or FEEDS:
        filter_feed(feed)


if __name__ == "__main__":
    main()
