"""Eenmalig (na elke dataverversing): segments.geojson + verfijningstabel genereren.

1. Alle bereden clusterparen bepalen (opeenvolgende stops van rail-trips).
2. Segmentverfijning berekenen (zie verfijning.py): expresse-sprongen -> ketens.
3. De kaart tekent alleen de "blad"-segmenten (rechte lijnen, v1); de tabel
   segment_verfijning in merged.duckdb stuurt de delta-verdeling in de aggregator.
"""

import json

import duckdb

from .config import MERGED_DB, WEB_DATA
from .verfijning import bouw_verfijning


def main() -> None:
    con = duckdb.connect(str(MERGED_DB))
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
    coords = {cid: (lat, lon) for cid, (_, lat, lon) in info.items() if lat is not None}

    verf = bouw_verfijning(paren, coords)
    con.execute("CREATE OR REPLACE TABLE segment_verfijning (grof VARCHAR, fijn VARCHAR, fractie DOUBLE, volgorde INT)")
    con.executemany(
        "INSERT INTO segment_verfijning VALUES (?, ?, ?, ?)",
        [
            (f"{s[0]}|{s[1]}", f"{e[0]}|{e[1]}", fr, i)
            for s, bladen in verf.items()
            if len(bladen) > 1 or bladen[0][0] != s
            for i, (e, fr) in enumerate(bladen)
        ],
    )
    n_verfijnd = con.execute("SELECT count(DISTINCT grof) FROM segment_verfijning").fetchone()[0]

    bladen = {e for lijst in verf.values() for e, _ in lijst}
    features = []
    for a, b in sorted(bladen):
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
    print(f"segments.geojson: {len(features)} bladsegmenten; {n_verfijnd} grove segmenten verfijnd")


if __name__ == "__main__":
    main()
