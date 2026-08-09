"""s6: naïef RAPTOR-prototype op de gemergde dataset.

Bewust simpel (bovengrens-meting): kalender vooraf uitgevouwen naar één dienstdag,
stations = clusters, overstaptijd 300 s overal, max 6 rounds, geen voetpaden buiten
clusters, duplicaat-trips niet ontdubbeld. Meet laadtijd/RSS en querytijden.
"""

import datetime as dt
import resource
import statistics
import time
from collections import defaultdict
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
MERGED = ROOT / "data" / "merged" / "merged.duckdb"

DATUM = "20260812"  # woensdag, binnen alle horizonten (DE-free loopt t/m 20260907)
OVERSTAP_S = 300
MAX_ROUNDS = 6
ONEINDIG = float("inf")

QUERIES = [
    ("Amsterdam Centraal", "Lyon Part Dieu", 8 * 3600),
    ("Utrecht Centraal", "Basel SBB", 7 * 3600 + 1800),
    ("Amsterdam Centraal", "Maastricht", 9 * 3600),
    ("Maastricht", "Liège-Guillemins", 9 * 3600),
]


def laad():
    con = duckdb.connect(str(MERGED), read_only=True)
    wd = dt.datetime.strptime(DATUM, "%Y%m%d").weekday()  # 0=ma
    dagkolom = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][wd]

    actieve = con.execute(
        f"""WITH basis AS (
              SELECT service_id FROM calendar
              WHERE {dagkolom} = '1' AND start_date <= '{DATUM}' AND end_date >= '{DATUM}'
            ),
            plus AS (SELECT service_id FROM calendar_dates WHERE date = '{DATUM}' AND exception_type = '1'),
            min AS (SELECT service_id FROM calendar_dates WHERE date = '{DATUM}' AND exception_type = '2')
            SELECT service_id FROM (SELECT * FROM basis UNION SELECT * FROM plus)
            WHERE service_id NOT IN (SELECT service_id FROM min)"""
    ).fetchall()
    actieve_set = {r[0] for r in actieve}
    print(f"actieve services op {DATUM}: {len(actieve_set)}")

    rows = con.execute(
        """SELECT st.trip_id, sc.cluster_id, st.dep_s, CAST(st.stop_sequence AS INT)
           FROM stop_times st
           JOIN stop_cluster sc USING (stop_id)
           JOIN trips t USING (trip_id)
           WHERE t.service_id IN (SELECT service_id FROM actieve_services)"""
        .replace("(SELECT service_id FROM actieve_services)", f"(SELECT unnest(?::VARCHAR[]))"),
        [list(actieve_set)],
    ).fetchall()

    per_trip = defaultdict(list)
    for trip_id, cluster, dep_s, seq in rows:
        if dep_s is not None:
            per_trip[trip_id].append((seq, cluster, dep_s))
    for v in per_trip.values():
        v.sort()

    # RAPTOR-"routes": groepeer trips op identieke clustervolgorde
    route_trips = defaultdict(list)
    for trip_id, sts in per_trip.items():
        volgorde = tuple(c for _, c, _ in sts)
        if len(volgorde) >= 2:
            route_trips[volgorde].append([t for _, _, t in sts])
    routes = []
    routes_van = defaultdict(list)  # cluster -> [(route_idx, positie)]
    for volgorde, tripslijst in route_trips.items():
        tripslijst.sort(key=lambda ts: ts[0])
        idx = len(routes)
        routes.append((volgorde, tripslijst))
        for pos, c in enumerate(volgorde):
            routes_van[c].append((idx, pos))

    naam_van = dict(con.execute("SELECT cluster_id, naam FROM clusters").fetchall())
    trips_per_dag = len(per_trip)
    print(f"trips op dienstdag: {trips_per_dag}, RAPTOR-routes: {len(routes)}")
    return routes, routes_van, naam_van, trips_per_dag


def vind_cluster(naam_van, zoek):
    kandidaten = [cid for cid, n in naam_van.items() if n and zoek.lower() in n.lower()]
    if not kandidaten:
        raise SystemExit(f"station niet gevonden: {zoek}")
    return kandidaten[0]


def raptor(routes, routes_van, start, doel, vertrek_s):
    best = defaultdict(lambda: ONEINDIG)   # beste aankomst ooit (pruning)
    rondes = [dict()]                      # per ronde: cluster -> (aankomst, herkomstinfo)
    rondes[0][start] = (vertrek_s, None)
    best[start] = vertrek_s

    for _ in range(MAX_ROUNDS):
        vorige = rondes[-1]
        huidige = {}
        te_scannen = defaultdict(int)  # route_idx -> vroegste instappositie
        for c in vorige:
            for ridx, pos in routes_van[c]:
                te_scannen[ridx] = min(te_scannen.get(ridx, 1 << 30), pos)
        for ridx, startpos in te_scannen.items():
            volgorde, tripslijst = routes[ridx]
            actieve_trip = None
            instap = None
            for pos in range(startpos, len(volgorde)):
                c = volgorde[pos]
                if actieve_trip is not None:
                    aank = actieve_trip[pos]
                    if aank < best[c] and aank < best[doel]:
                        best[c] = aank
                        huidige[c] = (aank, (ridx, instap, pos))
                # (opnieuw) instappen als we hier eerder kunnen zijn
                if c in vorige:
                    klaar = vorige[c][0] + (0 if pos == 0 and vorige[c][1] is None else OVERSTAP_S)
                    if actieve_trip is None or klaar < actieve_trip[pos]:
                        for ts in tripslijst:
                            if ts[pos] >= klaar:
                                if actieve_trip is None or ts[pos] < actieve_trip[pos]:
                                    actieve_trip = ts
                                    instap = pos
                                break
        if not huidige:
            break
        rondes.append(huidige)

    aankomsten = [(r, ronde[doel][0]) for r, ronde in enumerate(rondes) if doel in ronde]
    return aankomsten, best[doel]


def main():
    t0 = time.monotonic()
    routes, routes_van, naam_van, trips_per_dag = laad()
    laadtijd = time.monotonic() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    print(f"laadtijd: {laadtijd:.1f} s, piek-RSS: {rss:.0f} MB")

    for van, naar, t_vertrek in QUERIES:
        c_van, c_naar = vind_cluster(naam_van, van), vind_cluster(naam_van, naar)
        tijden = []
        resultaat = None
        for _ in range(10):
            q0 = time.perf_counter()
            resultaat = raptor(routes, routes_van, c_van, c_naar, t_vertrek)
            tijden.append(time.perf_counter() - q0)
        aankomsten, beste = resultaat
        beste_str = "geen route" if beste == ONEINDIG else f"{int(beste) // 3600:02d}:{int(beste) % 3600 // 60:02d}"
        per_ronde = ", ".join(f"r{r}={int(a) // 3600:02d}:{int(a) % 3600 // 60:02d}" for r, a in aankomsten)
        print(f"{van} -> {naar} ({t_vertrek // 3600:02d}:00): beste aankomst {beste_str} "
              f"[{per_ronde}] — mediaan {statistics.median(tijden) * 1000:.0f} ms")


if __name__ == "__main__":
    main()
