"""Na elke dataverversing: getekende randen + verfijnings- en randtabellen genereren.

Rand-gebaseerde kaart (dedupliceert parallelle lijnen per constructie):
1. Verfijningstabel berekenen (expresse-sprong -> keten van bladsegmenten), voor de
   delta-verdeling in de aggregator.
2. randen.json.gz laden (uit spike/s8: dissolve van OSM-knooppaden — elk stuk spoor
   waar dezelfde set segmenten overheen loopt is één getekende rand).
3. segments.geojson = de randen (naam blijft vanwege het viewer-contract), plus
   rechte-lijn-fallbacks voor bladsegmenten zonder geometrie.
4. Tabel segment_randen in merged.duckdb: segment -> rand-ids (voor de per-rand-
   aggregatie in de aggregator).
"""

import gzip
import json

import duckdb

from . import r2
from .closure_baseline import LOOKAHEAD_DAYS, build_planned_closures
from .config import DATA, MERGED_DB, WEB_DATA, laad_env
from .verfijning import bouw_verfijning

laad_env()  # R2-gegevens uit .env, anders slaat de upload/download stilletjes over

RANDEN_PAD = DATA / "geometrie" / "randen.json.gz"


def laad_randen() -> dict:
    """Dissolve-output van s8: lokaal bestand gaat voor; anders van R2 (en cachen)."""
    if RANDEN_PAD.exists():
        data = RANDEN_PAD.read_bytes()
        if r2.actief():
            try:
                r2.upload("randen.json.gz", gzip.decompress(data), "application/json", cache_s=86400)
            except Exception as e:
                print(f"waarschuwing: R2-upload randen mislukt: {e}")
        return json.loads(gzip.decompress(data))
    try:
        data = r2.download("randen.json.gz")
    except Exception as e:
        print(f"waarschuwing: R2-download randen mislukt: {e}")
        data = None
    if data:
        RANDEN_PAD.parent.mkdir(parents=True, exist_ok=True)
        RANDEN_PAD.write_bytes(gzip.compress(data))
        return json.loads(data)
    return {"randen": {}, "dekking": {}}


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

    def naam_van(seg_id: str) -> str:
        a, b = seg_id.split("|")
        return f"{info[a][0]} – {info[b][0]}" if a in info and b in info else seg_id

    randen = laad_randen()
    rand_geo, dekking = randen["randen"], randen["dekking"]

    # inverse: segment -> randen waar hij overheen loopt
    segment_randen: dict[str, list[str]] = {}
    for rid, segs in dekking.items():
        for seg in segs:
            segment_randen.setdefault(seg, []).append(rid)

    features = []
    for rid, lijn in rand_geo.items():
        if len(lijn) < 2:
            continue
        segs = dekking.get(rid, [])
        label = ", ".join(naam_van(s) for s in segs[:3]) + (f" (+{len(segs) - 3})" if len(segs) > 3 else "")
        features.append(
            {
                "type": "Feature",
                "id": rid,
                "properties": {"id": rid, "lijnen": label},
                "geometry": {"type": "LineString", "coordinates": lijn},
            }
        )

    # rechte-lijn-fallback voor bladsegmenten zonder OSM-pad
    bladen = {e for lijst in verf.values() for e, _ in lijst}
    n_fallback = 0
    for a, b in sorted(bladen):
        seg_id = f"{a}|{b}"
        if seg_id in segment_randen or a not in coords or b not in coords:
            continue
        rid = f"F:{seg_id}"
        segment_randen[seg_id] = [rid]
        n_fallback += 1
        (la, lo_a), (lb, lo_b) = coords[a], coords[b]
        features.append(
            {
                "type": "Feature",
                "id": rid,
                "properties": {"id": rid, "lijnen": naam_van(seg_id)},
                "geometry": {"type": "LineString",
                             "coordinates": [[round(lo_a, 5), round(la, 5)], [round(lo_b, 5), round(lb, 5)]]},
            }
        )

    con.execute("CREATE OR REPLACE TABLE segment_randen (segment VARCHAR, rand VARCHAR)")
    con.executemany(
        "INSERT INTO segment_randen VALUES (?, ?)",
        [(seg, rid) for seg, rids in segment_randen.items() for rid in rids],
    )

    WEB_DATA.mkdir(parents=True, exist_ok=True)
    (WEB_DATA / "segments.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"))
    )
    print(f"segments.geojson: {len(features)} getekende randen ({n_fallback} rechte-lijn-fallbacks); "
          f"{n_verfijnd} grove segmenten verfijnd; {len(segment_randen)} segmenten gemapt")

    n_closures = build_planned_closures(con)
    print(f"planned_closures: {n_closures} rand-dag-blokken (komende {LOOKAHEAD_DAYS} dagen)")


if __name__ == "__main__":
    main()
