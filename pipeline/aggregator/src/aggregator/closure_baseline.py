"""Planned-closure detection from the static timetable (PLAN.md, map improvement 8).

Planned engineering works are already baked into the daily GTFS exports: the trains
simply do not exist, so GTFS-RT never reports cancellations and the map falls back to
grey "no data". This module detects such closures from absence: for every drawn edge
it builds an expected-trains-per-hour baseline (median over same day-types within the
feed horizon) and flags hours where the timetable schedules zero trains against a
baseline of at least one. Runs of >= MIN_RUN_HOURS consecutive closed hours within the
next LOOKAHEAD_DAYS are written to the planned_closures table, which the aggregator
reads at startup.

Known simplifications (accepted): departures past midnight (dep_s >= 86400) wrap onto
the wrong clock hour — night hours rarely reach the baseline anyway; public holidays
pollute their day-type but the median absorbs that; closures spanning (nearly) the
whole feed horizon push the median itself to zero and are invisible here — the
disruption feeds (NS/SNCF/NMBS) are the signal for those.
"""

from datetime import date, timedelta

import duckdb

SAMPLE_DAYS = 35     # horizon for the median baseline (>= 5 samples per weekday)
LOOKAHEAD_DAYS = 14  # closures further out are refreshed by the next weekly run
MIN_BASELINE = 1     # trains/hour a closed hour must normally carry
MIN_RUN_HOURS = 2    # shorter gaps are night pauses or thin-service noise


def build_planned_closures(con: duckdb.DuckDBPyConnection) -> int:
    today = date.today()
    dates = [(today + timedelta(days=i)).strftime("%Y%m%d") for i in range(SAMPLE_DAYS)]
    horizon_end = (today + timedelta(days=LOOKAHEAD_DAYS)).strftime("%Y%m%d")
    con.execute("CREATE OR REPLACE TEMP TABLE cb_dates (d VARCHAR)")
    con.executemany("INSERT INTO cb_dates VALUES (?)", [(d,) for d in dates])

    # (date, rand, hour) -> scheduled train count, densified with zeros; stays in SQL
    con.execute(
        """CREATE OR REPLACE TEMP TABLE cb_counts AS
           WITH stop_seq AS (
             SELECT st.feed, st.trip_id, sc.cluster_id, st.dep_s,
                    CAST(st.stop_sequence AS INT) AS seq
             FROM stop_times st JOIN stop_cluster sc USING (stop_id)
           ),
           hops AS (
             SELECT feed, trip_id, cluster_id AS a, dep_s,
                    lead(cluster_id) OVER (PARTITION BY feed, trip_id ORDER BY seq) AS b
             FROM stop_seq
           ),
           trip_edge_hour AS (
             SELECT DISTINCT h.feed, h.trip_id, sr.rand,
                    (h.dep_s // 3600) % 24 AS hour
             FROM hops h
             JOIN segment_verfijning sv
               ON sv.grof = least(h.a, h.b) || '|' || greatest(h.a, h.b)
             JOIN segment_randen sr ON sr.segment = sv.fijn
             WHERE h.b IS NOT NULL AND h.a <> h.b AND h.dep_s IS NOT NULL
             UNION
             SELECT DISTINCT h.feed, h.trip_id, sr.rand,
                    (h.dep_s // 3600) % 24 AS hour
             FROM hops h
             JOIN segment_randen sr
               ON sr.segment = least(h.a, h.b) || '|' || greatest(h.a, h.b)
             WHERE h.b IS NOT NULL AND h.a <> h.b AND h.dep_s IS NOT NULL
           ),
           -- collapse to service level first: trips of one service share their calendar
           service_counts AS (
             SELECT t.feed, t.service_id, teh.rand, teh.hour,
                    count(DISTINCT teh.trip_id) AS n
             FROM trip_edge_hour teh
             JOIN trips t ON t.feed = teh.feed AND t.trip_id = teh.trip_id
             GROUP BY ALL
           ),
           service_days AS (
             SELECT c.feed, c.service_id, d.d
             FROM calendar c JOIN cb_dates d
               ON d.d BETWEEN c.start_date AND c.end_date
              AND CASE isodow(strptime(d.d, '%Y%m%d'))
                    WHEN 1 THEN c.monday WHEN 2 THEN c.tuesday WHEN 3 THEN c.wednesday
                    WHEN 4 THEN c.thursday WHEN 5 THEN c.friday WHEN 6 THEN c.saturday
                    ELSE c.sunday END = '1'
             UNION
             SELECT feed, service_id, date AS d
             FROM calendar_dates JOIN cb_dates ON d = date
             WHERE exception_type = '1'
           ),
           service_days_net AS (
             SELECT sd.* FROM service_days sd
             ANTI JOIN (SELECT feed, service_id, date AS d FROM calendar_dates
                        WHERE exception_type = '2') x USING (feed, service_id, d)
           ),
           day_counts AS (
             SELECT sd.d, sc.rand, sc.hour, sum(sc.n) AS n
             FROM service_counts sc
             JOIN service_days_net sd USING (feed, service_id)
             GROUP BY ALL
           ),
           -- densify: a closed day must count as 0, not silently disappear
           edge_hours AS (SELECT DISTINCT rand, hour FROM day_counts)
           SELECT d.d, eh.rand, eh.hour, coalesce(dc.n, 0) AS n,
                  CASE isodow(strptime(d.d, '%Y%m%d'))
                    WHEN 6 THEN 'sat' WHEN 7 THEN 'sun' ELSE 'wd' END AS daytype
           FROM cb_dates d CROSS JOIN edge_hours eh
           LEFT JOIN day_counts dc ON dc.d = d.d AND dc.rand = eh.rand AND dc.hour = eh.hour"""
    )

    # only candidate hours (scheduled 0 against baseline >= MIN_BASELINE) reach Python
    candidates = con.execute(
        """SELECT c.d, c.rand, c.hour
           FROM cb_counts c
           JOIN (SELECT rand, hour, daytype, median(n) AS baseline
                 FROM cb_counts GROUP BY ALL) b USING (rand, hour, daytype)
           WHERE c.n = 0 AND b.baseline >= ? AND c.d < ?
           ORDER BY c.d, c.rand, c.hour""",
        [MIN_BASELINE, horizon_end],
    ).fetchall()

    # merge consecutive closed hours into runs; keep runs of >= MIN_RUN_HOURS
    rows: list[tuple[str, str, int, int]] = []
    run: list[int] = []
    prev_key: tuple[str, str] | None = None

    def flush() -> None:
        if len(run) >= MIN_RUN_HOURS:
            rows.append((*prev_key, run[0], run[-1]))

    for d, rand, hour in candidates:
        if (d, rand) != prev_key or (run and hour != run[-1] + 1):
            if prev_key is not None:
                flush()
            run = []
            prev_key = (d, rand)
        run.append(int(hour))
    if prev_key is not None:
        flush()

    con.execute("CREATE OR REPLACE TABLE planned_closures"
                " (date VARCHAR, rand VARCHAR, hour_start INT, hour_end INT)")
    con.executemany("INSERT INTO planned_closures VALUES (?, ?, ?, ?)", rows)
    con.execute("DROP TABLE cb_counts")
    con.execute("DROP TABLE cb_dates")
    return len(rows)
