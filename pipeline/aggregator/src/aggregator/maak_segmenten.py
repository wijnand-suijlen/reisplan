"""Eenmalig: segments.geojson genereren uit de spike-merge (rechte lijnen tussen clusters).

Segment = geordend clusterpaar dat door >=1 trip aansluitend bereden wordt.
NL zou echte shapes kunnen gebruiken; v1 houdt het bewust uniform recht (PLAN.md fase 0.5).
"""

import json

import duckdb

from .config import MERGED_DB, WEB_DATA


def main() -> None:
    con = duckdb.connect(str(MERGED_DB), read_only=True)
    paren = con.execute(
        """WITH volgorde AS (
             SELECT st.trip_id, sc.cluster_id, CAST(st.stop_sequence AS INT) AS seq
             FROM stop_times st JOIN stop_cluster sc USING (stop_id)
           ),
           paren AS (
             SELECT v1.cluster_id AS a, v2.cluster_id AS b
             FROM volgorde v1 JOIN volgorde v2
               ON v1.trip_id = v2.trip_id AND v2.seq = (
                 SELECT min(v3.seq) FROM volgorde v3 WHERE v3.trip_id = v1.trip_id AND v3.seq > v1.seq)
             WHERE v1.cluster_id <> v2.cluster_id
           )
           SELECT DISTINCT least(a, b), greatest(a, b) FROM paren"""
    ).fetchall()
    info = {
        cid: (naam, lat, lon)
        for cid, naam, lat, lon in con.execute("SELECT cluster_id, naam, lat, lon FROM clusters").fetchall()
    }
    features = []
    for a, b in paren:
        na, la, lo_a = info.get(a, (None, None, None))
        nb, lb, lo_b = info.get(b, (None, None, None))
        if la is None or lb is None:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"{a}|{b}",
                "properties": {"id": f"{a}|{b}", "van": na, "naar": nb},
                "geometry": {"type": "LineString",
                             "coordinates": [[round(lo_a, 5), round(la, 5)], [round(lo_b, 5), round(lb, 5)]]},
            }
        )
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    (WEB_DATA / "segments.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"))
    )
    print(f"segments.geojson: {len(features)} segmenten")


if __name__ == "__main__":
    main()
