"""Planned-closure detection from the static timetable (PLAN.md, map improvement 8).

Planned engineering works are already baked into the daily GTFS exports: the trains
simply do not exist, so GTFS-RT never reports cancellations and the map falls back to
grey "no data". This module detects such closures from absence: for every drawn edge
it builds an expected-service baseline (over same day-types within the feed horizon)
and flags hours where the timetable schedules zero trains against that baseline. Runs
of >= MIN_RUN_HOURS consecutive closed hours within the next LOOKAHEAD_DAYS are
written to the planned_closures table, which the aggregator reads at startup.

The baseline is a majority vote: an (edge, hour, daytype) normally carries service iff
more than half of the sampled same-daytype days schedule at least one train there.
That is the "median over zero-densified daily counts >= 1" of the original design,
but computable from day-level *presence* alone — the dense day x edge x hour count
matrix (~17M rows) blew past the VM's 600 MB DuckDB budget, since TEMP-table storage
is memory-only. The one remaining big intermediate (cb_served) therefore also goes
into a regular, disk-backed table, dropped afterwards.

Known simplifications (accepted): departures past midnight (dep_s >= 86400) wrap onto
the wrong clock hour — night hours rarely reach the baseline anyway; public holidays
pollute their day-type but the majority vote absorbs that; closures spanning (nearly)
the whole feed horizon push the baseline itself to zero and are invisible here — the
disruption feeds (NS/SNCF/NMBS) are the signal for those.
"""

from datetime import date, timedelta

import duckdb

SAMPLE_DAYS = 35     # horizon for the baseline (>= 5 samples per weekday)
LOOKAHEAD_DAYS = 14  # closures further out are refreshed by the next weekly run
MIN_RUN_HOURS = 2    # shorter gaps are night pauses or thin-service noise

DAYTYPES = {5: "sat", 6: "sun"}  # date.weekday(); everything else is 'wd'


def build_planned_closures(con: duckdb.DuckDBPyConnection) -> int:
    today = date.today()
    days = [today + timedelta(days=i) for i in range(SAMPLE_DAYS)]
    horizon_end = (today + timedelta(days=LOOKAHEAD_DAYS)).strftime("%Y%m%d")
    con.execute("CREATE OR REPLACE TEMP TABLE cb_dates (d VARCHAR, daytype VARCHAR)")
    con.executemany(
        "INSERT INTO cb_dates VALUES (?, ?)",
        [(d.strftime("%Y%m%d"), DAYTYPES.get(d.weekday(), "wd")) for d in days],
    )

    # (date, rand, hour) pairs with at least one scheduled train. A regular table,
    # NOT temp: temp storage is memory-only and this does not fit the VM's budget.
    # Built per feed: one all-feeds query needs more working set (window sort +
    # parallel hash joins) than the VM's DuckDB limit allows, even with spilling.
    con.execute("CREATE OR REPLACE TABLE cb_served (d VARCHAR, rand VARCHAR, hour BIGINT)")
    feeds = [f for (f,) in con.execute("SELECT DISTINCT feed FROM trips").fetchall()]
    for feed in feeds:
        con.execute(
            """INSERT INTO cb_served
           WITH stop_seq AS (
             SELECT st.feed, st.trip_id, sc.cluster_id, st.dep_s,
                    CAST(st.stop_sequence AS INT) AS seq
             FROM stop_times st JOIN stop_cluster sc USING (stop_id)
             WHERE st.feed = ?
           ),
           hops AS (
             SELECT feed, trip_id, cluster_id AS a, dep_s,
                    lead(cluster_id) OVER (PARTITION BY feed, trip_id ORDER BY seq) AS b
             FROM stop_seq
           ),
           edge_hour_service AS (
             SELECT DISTINCT h.feed, t.service_id, sr.rand,
                    (h.dep_s // 3600) % 24 AS hour
             FROM hops h
             JOIN trips t ON t.feed = h.feed AND t.trip_id = h.trip_id
             JOIN segment_verfijning sv
               ON sv.grof = least(h.a, h.b) || '|' || greatest(h.a, h.b)
             JOIN segment_randen sr ON sr.segment = sv.fijn
             WHERE h.b IS NOT NULL AND h.a <> h.b AND h.dep_s IS NOT NULL
             UNION
             SELECT DISTINCT h.feed, t.service_id, sr.rand,
                    (h.dep_s // 3600) % 24 AS hour
             FROM hops h
             JOIN trips t ON t.feed = h.feed AND t.trip_id = h.trip_id
             JOIN segment_randen sr
               ON sr.segment = least(h.a, h.b) || '|' || greatest(h.a, h.b)
             WHERE h.b IS NOT NULL AND h.a <> h.b AND h.dep_s IS NOT NULL
           ),
           service_days AS (
             SELECT c.feed, c.service_id, d.d
             FROM calendar c JOIN cb_dates d
               ON d.d BETWEEN c.start_date AND c.end_date
              AND CASE isodow(strptime(d.d, '%Y%m%d'))
                    WHEN 1 THEN c.monday WHEN 2 THEN c.tuesday WHEN 3 THEN c.wednesday
                    WHEN 4 THEN c.thursday WHEN 5 THEN c.friday WHEN 6 THEN c.saturday
                    ELSE c.sunday END = '1'
             WHERE c.feed = ?
             UNION
             SELECT feed, service_id, date AS d
             FROM calendar_dates JOIN cb_dates ON d = date
             WHERE exception_type = '1' AND feed = ?
           ),
           service_days_net AS (
             SELECT sd.* FROM service_days sd
             ANTI JOIN (SELECT feed, service_id, date AS d FROM calendar_dates
                        WHERE exception_type = '2') x USING (feed, service_id, d)
           )
           SELECT DISTINCT sd.d, es.rand, es.hour
           FROM edge_hour_service es JOIN service_days_net sd USING (feed, service_id)""",
            [feed, feed, feed],
        )

    # candidate = day without service on an edge-hour that a majority of
    # same-daytype days serves; only those (few) rows reach Python
    candidates = con.execute(
        """WITH totals AS (SELECT daytype, count(*) AS total FROM cb_dates GROUP BY 1),
           -- DISTINCT: border edges can be served by more than one feed
           served_m AS (
             SELECT s.rand, s.hour, cd.daytype, count(DISTINCT s.d) AS m
             FROM cb_served s JOIN cb_dates cd USING (d)
             GROUP BY s.rand, s.hour, cd.daytype
           ),
           strong AS (
             SELECT rand, hour, daytype
             FROM served_m JOIN totals USING (daytype)
             WHERE m * 2 > total
           )
           SELECT cd.d, st.rand, st.hour
           FROM strong st
           JOIN cb_dates cd USING (daytype)
           ANTI JOIN cb_served sv
             ON sv.d = cd.d AND sv.rand = st.rand AND sv.hour = st.hour
           WHERE cd.d < ?
           ORDER BY cd.d, st.rand, st.hour""",
        [horizon_end],
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
    con.execute("DROP TABLE cb_served")
    con.execute("DROP TABLE cb_dates")
    return len(rows)
