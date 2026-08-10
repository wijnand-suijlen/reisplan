"""Eenmalig (na elke dataverversing): segments.geojson + verfijningstabel genereren.

1. Alle bereden clusterparen bepalen (opeenvolgende stops van rail-trips).
2. Segmentverfijning berekenen (zie verfijning.py): expresse-sprongen -> ketens.
3. De kaart tekent alleen de "blad"-segmenten (rechte lijnen, v1); de tabel
   segment_verfijning in merged.duckdb stuurt de delta-verdeling in de aggregator.
"""

import gzip
import json
from pathlib import Path

import duckdb

from . import r2
from .config import DATA, MERGED_DB, WEB_DATA, laad_env
from .verfijning import bouw_verfijning

laad_env()  # R2-gegevens uit .env, anders slaat de geometrie-upload stilletjes over

GEOMETRIE_PAD = DATA / "geometrie" / "paar_geometrie.json.gz"


def laad_geometrie() -> dict:
    """v2-geometrie (spike/s8): "a|b" -> polyline over het echte spoor.
    Lokaal bestand gaat voor; anders van R2 (en lokaal cachen); anders leeg (rechte lijnen)."""
    if GEOMETRIE_PAD.exists():
        geometrie = json.loads(gzip.decompress(GEOMETRIE_PAD.read_bytes()))
        if r2.actief():
            try:
                r2.upload("paar_geometrie.json.gz", json.dumps(geometrie, separators=(",", ":")).encode(),
                          "application/json", cache_s=86400)
            except Exception as e:
                print(f"waarschuwing: R2-upload geometrie mislukt: {e}")
        return geometrie
    data = None
    try:
        data = r2.download("paar_geometrie.json.gz")
    except Exception as e:
        print(f"waarschuwing: R2-download geometrie mislukt: {e}")
    if data:
        GEOMETRIE_PAD.parent.mkdir(parents=True, exist_ok=True)
        GEOMETRIE_PAD.write_bytes(gzip.compress(data))
        return json.loads(data)
    return {}


def main() -> None:
    import os

    con = duckdb.connect(str(MERGED_DB))
    if os.environ.get("REISPLAN_DUCKDB_MEM"):  # kleine VM's: spillen i.p.v. OOM
        con.execute(f"SET memory_limit='{os.environ['REISPLAN_DUCKDB_MEM']}'")
        con.execute("SET threads=2")
        con.execute("SET preserve_insertion_order=false")
    # opeenvolgende stops via lead() — lineair en spillbaar, i.t.t. een gecorreleerde subquery
    paren = con.execute(
        """WITH volgorde AS (
             SELECT st.trip_id, sc.cluster_id, CAST(st.stop_sequence AS INT) AS seq
             FROM stop_times st JOIN stop_cluster sc USING (stop_id)
           ),
           opv AS (
             SELECT cluster_id AS a,
                    lead(cluster_id) OVER (PARTITION BY trip_id ORDER BY seq) AS b
             FROM volgorde
           )
           SELECT DISTINCT least(a, b), greatest(a, b) FROM opv
           WHERE b IS NOT NULL AND a <> b"""
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

    geometrie = laad_geometrie()
    bladen = {e for lijst in verf.values() for e, _ in lijst}
    features = []
    n_echt = 0
    for a, b in sorted(bladen):
        na, la, lo_a = info.get(a, (None, None, None))
        nb, lb, lo_b = info.get(b, (None, None, None))
        if la is None or lb is None:
            continue
        seg_id = f"{a}|{b}"
        lijn = geometrie.get(seg_id)
        if lijn and len(lijn) >= 2:
            n_echt += 1
        else:
            lijn = [[round(lo_a, 5), round(la, 5)], [round(lo_b, 5), round(lb, 5)]]
        features.append(
            {
                "type": "Feature",
                "id": seg_id,
                "properties": {"id": seg_id, "van": na, "naar": nb},
                "geometry": {"type": "LineString", "coordinates": lijn},
            }
        )
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    (WEB_DATA / "segments.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"))
    )
    print(f"segments.geojson: {len(features)} bladsegmenten ({n_echt} met echte spoorgeometrie); "
          f"{n_verfijnd} grove segmenten verfijnd")


if __name__ == "__main__":
    main()
