"""s3: merge de gefilterde feeds, dedupliceer stations, detecteer dubbele internationale trips.

Output: data/merged/merged.duckdb met tabellen routes/trips/stop_times/stops/calendar/
calendar_dates/agency (id's geprefixt met feedcode), plus:
  - stations: één rij per station (parent_station of losse stop) met uic (nullable)
  - clusters: stationclusters over feeds heen (ronde A: UIC; ronde B: naam+afstand<=300m)
  - stop_cluster: stop_id -> cluster_id
  - dup_trips: kandidaat-duplicaatparen van trips uit verschillende feeds
Rapporten: data/rapporten/grensstations.md
"""

import csv
import math
import re
import resource
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
FILTERED = ROOT / "data" / "filtered"
MERGED = ROOT / "data" / "merged"
RAPPORTEN = ROOT / "data" / "rapporten"
METINGEN = ROOT / "data" / "metingen.csv"

FEEDS = ["nl", "be", "fr", "de_fv", "de_rv", "ch"]
UIC_RE = re.compile(r"(?<!\d)((?:80|84|85|87|88)\d{5,6})(?!\d)")

KOLOMMEN = {
    "routes": ["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
    "trips": ["trip_id", "route_id", "service_id", "trip_short_name", "trip_headsign", "shape_id"],
    "stop_times": ["trip_id", "stop_sequence", "arrival_time", "departure_time", "stop_id"],
    "stops": ["stop_id", "stop_code", "stop_name", "stop_lat", "stop_lon", "parent_station", "location_type"],
    "calendar": ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"],
    "calendar_dates": ["service_id", "date", "exception_type"],
    "agency": ["agency_id", "agency_name"],
}
PREFIX_KOLS = {"route_id", "agency_id", "trip_id", "service_id", "shape_id", "stop_id", "parent_station"}


def meet(stap, metric, waarde, feed=""):
    with METINGEN.open("a", newline="") as f:
        csv.writer(f).writerow([stap, feed, metric, waarde])


def normaliseer_naam(naam: str) -> str:
    n = unicodedata.normalize("NFKD", naam or "").encode("ascii", "ignore").decode().lower()
    n = re.sub(r"\b(centraal|central|hbf|hauptbahnhof|gare de|gare du|gare d'|station|bahnhof|railway station|sncb|sncf|cff|sbb)\b", " ", n)
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    return n


def uic_uit(*teksten) -> str | None:
    for t in teksten:
        if not t:
            continue
        m = UIC_RE.search(str(t))
        if m:
            code = m.group(1)
            return code[:7]  # 8-cijferige FR-codes: checkdigit strippen
    return None


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def merge(con):
    """Union alle gefilterde feeds met feed-prefix op id-kolommen."""
    for tabel, kols in KOLOMMEN.items():
        delen = []
        for feed in FEEDS:
            pad = FILTERED / feed / f"{tabel}.parquet"
            if not pad.exists():
                continue
            beschikbaar = {
                r[0] for r in con.execute(f"SELECT column_name FROM (DESCRIBE SELECT * FROM read_parquet('{pad}'))").fetchall()
            }
            sel = []
            for k in kols:
                if k not in beschikbaar:
                    sel.append(f"NULL AS {k}")
                elif k in PREFIX_KOLS:
                    sel.append(f"CASE WHEN {k} IS NULL OR {k} = '' THEN NULL ELSE '{feed}:' || {k} END AS {k}")
                else:
                    sel.append(k)
            delen.append(f"SELECT '{feed}' AS feed, {', '.join(sel)} FROM read_parquet('{pad}')")
        con.execute(f"CREATE OR REPLACE TABLE {tabel} AS " + " UNION ALL BY NAME ".join(delen))
        n = con.execute(f"SELECT count(*) FROM {tabel}").fetchone()[0]
        meet("s3", f"merged:{tabel}", n)
        print(f"merged {tabel}: {n}", flush=True)
    # tijden naar seconden (kan >24:00:00 zijn)
    con.execute(
        """ALTER TABLE stop_times ADD COLUMN IF NOT EXISTS dep_s INT;
           UPDATE stop_times SET dep_s =
             CAST(split_part(coalesce(nullif(departure_time,''), arrival_time), ':', 1) AS INT) * 3600
           + CAST(split_part(coalesce(nullif(departure_time,''), arrival_time), ':', 2) AS INT) * 60
           + CAST(split_part(coalesce(nullif(departure_time,''), arrival_time), ':', 3) AS INT)"""
    )


def bouw_stations(con):
    """Station = parent_station als die er is, anders de stop zelf."""
    con.execute(
        """CREATE OR REPLACE TABLE stations AS
           WITH stationskeuze AS (
             SELECT coalesce(parent_station, stop_id) AS station_id FROM stops GROUP BY 1
           )
           SELECT s.stop_id AS station_id, s.feed, s.stop_name,
                  CAST(s.stop_lat AS DOUBLE) AS lat, CAST(s.stop_lon AS DOUBLE) AS lon,
                  s.stop_code
           FROM stops s SEMI JOIN stationskeuze ON s.stop_id = stationskeuze.station_id"""
    )
    rows = con.execute("SELECT station_id, feed, stop_name, lat, lon, stop_code FROM stations").fetchall()
    return rows


def cluster_stations(con, rows):
    cluster_van = {}
    clusters = {}  # cluster_id -> dict

    # Ronde A: UIC
    for station_id, feed, naam, lat, lon, code in rows:
        # station_id is geprefixt ("nl:xyz"); uic zoeken in ongeprefixt id + stop_code
        uic = uic_uit(station_id.split(":", 1)[1], code)
        if uic:
            cid = f"uic:{uic}"
            cluster_van[station_id] = cid
            c = clusters.setdefault(cid, {"uic": uic, "naam": naam, "lat": lat, "lon": lon, "feeds": set()})
            c["feeds"].add(feed)

    # Ronde B: naam + afstand <= 300 m, via grid-index
    grid = defaultdict(list)
    for station_id, feed, naam, lat, lon, code in rows:
        if station_id in cluster_van or lat is None:
            continue
        grid[(round(lat, 2), round(lon, 2), normaliseer_naam(naam))].append((station_id, feed, naam, lat, lon))

    # ook UIC-clusters als kandidaat-ankers voor naamloze matches op afstand
    ankers = defaultdict(list)
    for cid, c in clusters.items():
        if c["lat"] is not None:
            ankers[(round(c["lat"], 2), round(c["lon"], 2), normaliseer_naam(c["naam"]))].append(cid)

    teller = 0
    for sleutel, groep in grid.items():
        lat0, lon0, nnaam = sleutel
        # match met bestaand UIC-cluster in buurcellen?
        kandidaat = None
        for dlat in (-0.01, 0, 0.01):
            for dlon in (-0.01, 0, 0.01):
                for cid in ankers.get((round(lat0 + dlat, 2), round(lon0 + dlon, 2), nnaam), []):
                    c = clusters[cid]
                    if haversine_m(groep[0][3], groep[0][4], c["lat"], c["lon"]) <= 300:
                        kandidaat = cid
        if kandidaat is None:
            teller += 1
            kandidaat = f"nm:{teller}"
            clusters[kandidaat] = {"uic": None, "naam": groep[0][2], "lat": groep[0][3], "lon": groep[0][4], "feeds": set()}
        for station_id, feed, naam, lat, lon in groep:
            if haversine_m(lat, lon, clusters[kandidaat]["lat"], clusters[kandidaat]["lon"]) <= 300 or clusters[kandidaat]["uic"] is None:
                cluster_van[station_id] = kandidaat
                clusters[kandidaat]["feeds"].add(feed)
            else:
                teller += 1
                los = f"nm:{teller}"
                clusters[los] = {"uic": None, "naam": naam, "lat": lat, "lon": lon, "feeds": {feed}}
                cluster_van[station_id] = los

    con.execute("CREATE OR REPLACE TABLE clusters (cluster_id VARCHAR, uic VARCHAR, naam VARCHAR, lat DOUBLE, lon DOUBLE, n_feeds INT, feeds VARCHAR)")
    con.executemany(
        "INSERT INTO clusters VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(cid, c["uic"], c["naam"], c["lat"], c["lon"], len(c["feeds"]), ",".join(sorted(c["feeds"]))) for cid, c in clusters.items()],
    )
    con.execute("CREATE OR REPLACE TABLE station_cluster (station_id VARCHAR, cluster_id VARCHAR)")
    con.executemany("INSERT INTO station_cluster VALUES (?, ?)", list(cluster_van.items()))
    con.execute(
        """CREATE OR REPLACE TABLE stop_cluster AS
           SELECT s.stop_id, sc.cluster_id
           FROM stops s JOIN station_cluster sc ON coalesce(s.parent_station, s.stop_id) = sc.station_id"""
    )

    # metingen
    n_uic = sum(1 for c in clusters.values() if c["uic"])
    meet("s3", "clusters_totaal", len(clusters))
    meet("s3", "clusters_met_uic", n_uic)
    for feed in FEEDS:
        totaal = sum(1 for r in rows if r[1] == feed)
        met_uic = sum(1 for r in rows if r[1] == feed and cluster_van.get(r[0], "").startswith("uic:"))
        if totaal:
            meet("s3", "uic_dekking_pct", f"{100 * met_uic / totaal:.1f}", feed)
    print(f"clusters: {len(clusters)} (met uic: {n_uic})", flush=True)


def rapport_grensstations(con):
    rows = con.execute(
        """SELECT cluster_id, naam, uic, feeds FROM clusters WHERE n_feeds >= 2 ORDER BY naam"""
    ).fetchall()
    RAPPORTEN.mkdir(parents=True, exist_ok=True)
    regels = ["# Stations in meerdere feeds (grens-/deelde stations)\n", f"Totaal: {len(rows)}\n"]
    regels += [f"- {naam} (uic={uic}, feeds={feeds})" for _, naam, uic, feeds in rows]
    (RAPPORTEN / "grensstations.md").write_text("\n".join(regels))
    meet("s3", "clusters_multi_feed", len(rows))
    print(f"multi-feed-clusters: {len(rows)}", flush=True)


def dup_trips(con):
    """Kandidaat-duplicaten: trips uit verschillende feeds met >=80% overlappende
    (cluster, tijd±2min)-events, beperkt tot trips die een multi-feed-cluster aandoen."""
    con.execute(
        """CREATE OR REPLACE TABLE events AS
           SELECT st.trip_id, t.feed, sc.cluster_id, st.dep_s
           FROM stop_times st
           JOIN stop_cluster sc USING (stop_id)
           JOIN trips t USING (trip_id)
           SEMI JOIN (SELECT cluster_id FROM clusters WHERE n_feeds >= 2) mc USING (cluster_id)"""
    )
    con.execute(
        """CREATE OR REPLACE TABLE dup_trips AS
           WITH triplen AS (SELECT trip_id, count(*) AS n FROM events GROUP BY 1),
           paren AS (
             SELECT e1.trip_id AS trip_a, e2.trip_id AS trip_b, count(*) AS gedeeld
             FROM events e1 JOIN events e2
               ON e1.cluster_id = e2.cluster_id
              AND abs(e1.dep_s - e2.dep_s) <= 120
              AND e1.feed < e2.feed
             GROUP BY 1, 2
           )
           SELECT p.trip_a, p.trip_b, p.gedeeld, la.n AS n_a, lb.n AS n_b
           FROM paren p JOIN triplen la ON p.trip_a = la.trip_id
                        JOIN triplen lb ON p.trip_b = lb.trip_id
           WHERE p.gedeeld >= 0.8 * least(la.n, lb.n) AND least(la.n, lb.n) >= 2"""
    )
    n = con.execute("SELECT count(*) FROM dup_trips").fetchone()[0]
    per_paar = con.execute(
        """SELECT split_part(trip_a, ':', 1) || '<->' || split_part(trip_b, ':', 1), count(*)
           FROM dup_trips GROUP BY 1 ORDER BY 2 DESC"""
    ).fetchall()
    meet("s3", "dup_trip_paren", n)
    for combo, cnt in per_paar:
        meet("s3", f"dup:{combo}", cnt)
    print(f"duplicaat-tripparen: {n} — " + ", ".join(f"{c}:{n2}" for c, n2 in per_paar), flush=True)


def main():
    t0 = time.monotonic()
    MERGED.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(MERGED / "merged.duckdb"))
    merge(con)
    rows = bouw_stations(con)
    cluster_stations(con, rows)
    rapport_grensstations(con)
    dup_trips(con)
    duur = time.monotonic() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    meet("s3", "duur_s", f"{duur:.1f}")
    meet("s3", "piek_rss_mb", f"{rss / 1e6:.0f}")
    print(f"s3 klaar in {duur:.1f} s, piek {rss / 1e6:.0f} MB", flush=True)


if __name__ == "__main__":
    main()
