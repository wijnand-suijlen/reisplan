"""Inspection artifacts: per-train table and full-service details.

Feeds the inspectie.html page next to the delay map. Every BUILD_INTERVAL_S the
last 24h of stop_obs2 is aggregated into two static artifacts (contract:
docs/inspectie-schema.md):

- inspect/trains.json   one row per (country, trip_id, service_date)
- inspect/details.json  scheduled stops + observed delays per train
- inspect/edges.json    per drawn edge the trains that passed it (seg_obs deltas)

The client filters the 30min/4h/24h windows itself on last_ts, so one 24h
artifact serves all windows. Schedule metadata comes from merged.duckdb through
the existing read-only Statisch connection. stop_obs2.trip_id is the raw RT id
while merged trip_ids are feed-prefixed ("nl:123"), hence the explicit prefix in
the join. DE trip_ids are IRIS labels ("ICE 228") that never match GTFS; those
trains get sched_known=false and their observed stops in ts order.
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import r2
from .config import WEB_DATA, bronnen

log = logging.getLogger("aggregator")

BUILD_INTERVAL_S = 300
WINDOW_S = 86400
SERVICE_DATE_DAYS_BACK = 2  # date floor keeps overnight trains with yesterday's service_date
META_CACHE_MAX = 20_000

COLS = ["country", "trip_id", "service_date", "train_number", "route",
        "origin", "destination", "sched_dep", "sched_arr",
        "delay_s", "last_stop", "first_ts", "last_ts", "n_obs", "sched_known"]
COUNTRY_I, TRIP_I = COLS.index("country"), COLS.index("trip_id")
FIRST_TS_I, LAST_TS_I = COLS.index("first_ts"), COLS.index("last_ts")

_next_build = 0.0
_meta_cache: dict[tuple[str, str], "TripMeta | None"] = {}  # None = known miss (e.g. DE)
_feed_by_country: dict[str, str] | None = None


@dataclass
class TripMeta:
    train_number: str
    route: str | None
    stops: list[list]  # [cluster_id | None, station_name, arrival_time, departure_time]


def run_if_due(statisch, opslag) -> None:
    global _next_build
    now = time.time()
    if now < _next_build:
        return
    _next_build = now + BUILD_INTERVAL_S
    try:
        _build(statisch, opslag)
    except Exception as e:
        log.warning("inspection build failed: %s", e)


def _build(statisch, opslag) -> None:
    ts_floor = int(time.time()) - WINDOW_S
    date_floor = (datetime.now(timezone.utc)
                  - timedelta(days=SERVICE_DATE_DAYS_BACK)).strftime("%Y%m%d")
    # the service_date index bounds both scans to a few days regardless of table size
    train_stats = {
        (country, trip_id, service_date): (first_ts, n_obs)
        for country, trip_id, service_date, first_ts, n_obs in opslag.db.execute(
            """SELECT country, trip_id, service_date, min(ts), count(*)
               FROM stop_obs2 WHERE service_date >= ? AND ts >= ?
               GROUP BY country, trip_id, service_date""",
            (date_floor, ts_floor))
    }
    # exactly one max() aggregate, so the bare delay_s comes from the latest row
    observed: dict[tuple[str, str, str], dict[str, tuple[int, int]]] = {}
    for country, trip_id, service_date, cluster, delay_s, ts in opslag.db.execute(
            """SELECT country, trip_id, service_date, cluster, delay_s, max(ts)
               FROM stop_obs2 WHERE service_date >= ? AND ts >= ?
               GROUP BY country, trip_id, service_date, cluster""",
            (date_floor, ts_floor)):
        observed.setdefault((country, trip_id, service_date), {})[cluster] = (delay_s, ts)

    _resolve_missing_meta(statisch, {(c, t) for c, t, _ in observed})

    rows = []
    details = {}
    n_stops = 0
    for key, per_cluster in sorted(observed.items()):
        country, trip_id, service_date = key
        first_ts, n_obs = train_stats[key]
        last_cluster, (delay_s, last_ts) = max(per_cluster.items(), key=lambda kv: kv[1][1])
        by_ts = sorted(per_cluster.items(), key=lambda kv: kv[1][1])
        meta = _meta_cache.get((country, trip_id))
        sched_known = bool(meta and meta.stops)
        if sched_known:
            origin, destination = meta.stops[0][1], meta.stops[-1][1]
            sched_dep, sched_arr = meta.stops[0][3], meta.stops[-1][2]
        else:
            origin = _cluster_name(statisch, by_ts[0][0])
            destination = _cluster_name(statisch, by_ts[-1][0])
            sched_dep = sched_arr = None
        rows.append([country, trip_id, service_date,
                     meta.train_number if meta else trip_id,
                     meta.route if meta else None,
                     origin, destination, sched_dep, sched_arr,
                     delay_s, _cluster_name(statisch, last_cluster),
                     first_ts, last_ts, n_obs, sched_known])
        stops = _detail_stops(statisch, meta if sched_known else None, per_cluster, by_ts)
        details[f"{country}|{trip_id}|{service_date}"] = {
            "sched_known": sched_known, "stops": stops}
        n_stops += len(stops)

    edges = _edge_pairs(statisch, opslag, ts_floor, rows)

    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    size_t = _write_artifact("trains.json", {
        "v": 1, "built_at": built_at, "window_s": WINDOW_S, "cols": COLS, "rows": rows})
    size_d = _write_artifact("details.json", {
        "v": 1, "built_at": built_at, "window_s": WINDOW_S, "trains": details})
    size_e = _write_artifact("edges.json", {
        "v": 1, "built_at": built_at, "window_s": WINDOW_S, "edges": edges})
    log.info("inspection: %d trains, %d detail stops, %d edges, %d + %d + %d bytes",
             len(rows), n_stops, len(edges), size_t, size_d, size_e)


def _edge_pairs(statisch, opslag, ts_floor, rows) -> dict[str, list[list[int]]]:
    """Per drawn edge the trains that passed it: [row_index, last_delta_s, last_ts],
    sorted by delta descending. Deltas are *incurred* delay per passage (seg_obs) —
    the numbers behind the map colour, unlike the absolute delays in trains.json.

    seg_obs has no service_date; a trip_id seen on two service days within the
    window is attributed to the row whose observation span is nearest to the
    passage timestamp."""
    row_index: dict[tuple[str, str], list[int]] = {}
    for i, row in enumerate(rows):
        row_index.setdefault((row[COUNTRY_I], row[TRIP_I]), []).append(i)
    per_pair: dict[tuple[str, str, str], tuple[int, int]] = {}
    for land, segment, trip_id, delta_s, ts in opslag.db.execute(
            """SELECT land, segment, trip_id, delta_s, max(ts)
               FROM seg_obs WHERE ts >= ? GROUP BY land, segment, trip_id""",
            (ts_floor,)):
        for rand in statisch.randen(segment):
            cur = per_pair.get((rand, land, trip_id))
            if cur is None or ts > cur[1]:
                per_pair[(rand, land, trip_id)] = (delta_s, ts)

    def span_distance(i: int, ts: int) -> int:
        first_ts, last_ts = rows[i][FIRST_TS_I], rows[i][LAST_TS_I]
        return 0 if first_ts <= ts <= last_ts else min(abs(ts - first_ts), abs(ts - last_ts))

    edges: dict[str, list[list[int]]] = {}
    for (rand, land, trip_id), (delta_s, ts) in per_pair.items():
        candidates = row_index.get((land, trip_id))
        if not candidates:  # deltas without any stop observation in the window
            continue
        idx = min(candidates, key=lambda i: span_distance(i, ts))
        edges.setdefault(rand, []).append([idx, delta_s, ts])
    for pairs in edges.values():
        pairs.sort(key=lambda p: -p[1])
    return edges


def _detail_stops(statisch, meta, per_cluster, by_ts) -> list[list]:
    """[station_name, sched_arr, sched_dep, delay_s|None] per stop; without a
    schedule (or for observed clusters missing from it) in observation order."""
    stops = []
    covered = set()
    if meta:
        for cluster_id, name, arr, dep in meta.stops:
            delay = per_cluster.get(cluster_id, (None, 0))[0] if cluster_id else None
            covered.add(cluster_id)
            stops.append([name, arr, dep, delay])
    for cluster_id, (delay, _ts) in by_ts:
        if cluster_id not in covered:
            stops.append([_cluster_name(statisch, cluster_id), None, None, delay])
    return stops


def _resolve_missing_meta(statisch, keys) -> None:
    global _feed_by_country
    if _feed_by_country is None:
        _feed_by_country = {cfg.land: cfg.feed_prefix for cfg in bronnen()}
    if len(_meta_cache) > META_CACHE_MAX:
        _meta_cache.clear()
    todo: dict[str, dict[str, tuple[str, str]]] = {}  # feed -> prefixed id -> cache key
    for country, trip_id in keys:
        if (country, trip_id) in _meta_cache:
            continue
        feed = _feed_by_country.get(country)
        if feed is None:
            _meta_cache[(country, trip_id)] = None
        else:
            todo.setdefault(feed, {})[f"{feed}:{trip_id}"] = (country, trip_id)
    for feed, prefixed in todo.items():
        ids = list(prefixed)
        # batched per feed: point lookups per trip would make a cold-cache build
        # (thousands of new trips after a restart) take minutes on the VM
        trip_rows = statisch.con.execute(
            """SELECT t.trip_id, t.trip_short_name, t.trip_headsign, r.route_short_name
               FROM trips t LEFT JOIN routes r USING (feed, route_id)
               WHERE t.feed = ? AND t.trip_id IN (SELECT unnest(?))""",
            [feed, ids]).fetchall()
        stop_rows = statisch.con.execute(
            """SELECT st.trip_id, st.arrival_time, st.departure_time, st.stop_id, s.stop_name
               FROM stop_times st LEFT JOIN stops s USING (feed, stop_id)
               WHERE st.feed = ? AND st.trip_id IN (SELECT unnest(?))
               ORDER BY st.trip_id, st.stop_sequence::INT""",
            [feed, ids]).fetchall()
        stops_by_trip: dict[str, list[list]] = {}
        for trip_id, arr, dep, stop_id, stop_name in stop_rows:
            cluster_id = statisch.cluster_van_stop.get(stop_id)
            name = _cluster_name(statisch, cluster_id) if cluster_id else (stop_name or stop_id)
            stops = stops_by_trip.setdefault(trip_id, [])
            if stops and cluster_id and stops[-1][0] == cluster_id:
                stops[-1][3] = dep  # same cluster again: first arrival, last departure
            else:
                stops.append([cluster_id, name, arr, dep])
        for prefixed_id, short_name, headsign, route_short in trip_rows:
            country, trip_id = prefixed[prefixed_id]
            _meta_cache[(country, trip_id)] = TripMeta(
                short_name or headsign or route_short or trip_id,
                route_short, stops_by_trip.get(prefixed_id, []))
        for cache_key in prefixed.values():
            _meta_cache.setdefault(cache_key, None)  # not in this feed's GTFS


def _cluster_name(statisch, cluster_id: str) -> str:
    cluster = statisch.clusters.get(cluster_id)
    return cluster.naam if cluster else cluster_id


def _write_artifact(name: str, payload: dict) -> int:
    out_dir = WEB_DATA / "inspect"
    out_dir.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, separators=(",", ":")).encode()
    tmp = out_dir / (name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, out_dir / name)
    r2.upload(f"inspect/{name}", data, "application/json", cache_s=60)
    return len(data)
