"""s8: v2-geometrie — baanvakken routeren over het echte OSM-spoornetwerk.

Pipeline:
  1. (vooraf) Geofabrik-extracten in data/osm/<land>.osm.pbf
  2. osmium tags-filter railway=rail,narrow_gauge  ->  data/osm/rail_<land>.osm.pbf
  3. parse ways+nodes (pyosmium), dedupliceer over landsgrenzen (Geofabrik clipt met overlap)
  4. topologische graaf: knopen met graad != 2 worden knooppunten; kettingen van
     graad-2-punten klappen in tot één rand met polyline en lengte
  5. stations (clusters uit merged.duckdb) snappen op de dichtstbijzijnde ruwe knoop
     (<= 1500 m), als virtuele knoop op de rand waar die knoop op ligt
  6. per baanvak (clusterpaar) A* over de graaf; accepteer als padlengte <= 2.2x
     hemelsbreed + 2 km, anders geen geometrie (kaart valt terug op rechte lijn)
  7. output: data/geometrie/paar_geometrie.json.gz  ("a|b" -> vereenvoudigde polyline)
"""

import gzip
import heapq
import json
import math
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import duckdb
import osmium
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parent.parent
OSM = ROOT / "data" / "osm"
MERGED = ROOT / "data" / "merged" / "merged.duckdb"
UIT = ROOT / "data" / "geometrie"
LANDEN = ["netherlands", "belgium", "france", "germany", "switzerland", "luxembourg"]

SNAP_MAX_M = 1500.0
PAD_FACTOR = 2.2
PAD_SLACK_M = 2000.0
SIMPLIFY_GRADEN = 0.0003  # ~30 m

ONEINDIG = float("inf")


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def filter_rail():
    for land in LANDEN:
        bron, doel = OSM / f"{land}.osm.pbf", OSM / f"rail_{land}.osm.pbf"
        if doel.exists() or not bron.exists():
            continue
        print(f"osmium-filter {land}…", flush=True)
        subprocess.run(
            ["osmium", "tags-filter", str(bron), "w/railway=rail,narrow_gauge", "-o", str(doel), "--overwrite"],
            check=True,
        )


class RailLezer(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.coords = {}       # node_id -> (lat, lon)
        self.ways = {}         # way_id -> [node_ids]

    def node(self, n):
        self.coords[n.id] = (n.location.lat, n.location.lon)

    def way(self, w):
        if w.id in self.ways:
            return  # zelfde way in twee landen-extracten (grensoverlap)
        self.ways[w.id] = [nd.ref for nd in w.nodes]


def bouw_graaf(lezer):
    """Topologische graaf: kettingen van graad-2-knopen inklappen tot randen met polyline."""
    graad = defaultdict(int)
    for nodes in lezer.ways.values():
        for i, n in enumerate(nodes):
            graad[n] += 1 if i in (0, len(nodes) - 1) else 2

    knooppunt = {n for n, g in graad.items() if g != 2}
    randen = []                      # (a, b, lengte_m, polyline[(lat,lon)])
    op_rand = {}                     # raw node_id -> (rand_idx, positie_in_polyline)
    buren = defaultdict(list)       # knoop -> [(buur, lengte, rand_idx, richting)]

    for nodes in lezer.ways.values():
        ketting = []
        for n in nodes:
            if n not in lezer.coords:
                if ketting:
                    _sluit(ketting, knooppunt, lezer, randen, op_rand, buren)
                    ketting = []
                continue
            ketting.append(n)
            if n in knooppunt and len(ketting) > 1:
                _sluit(ketting, knooppunt, lezer, randen, op_rand, buren)
                ketting = [n]
        if len(ketting) > 1:
            _sluit(ketting, knooppunt, lezer, randen, op_rand, buren)
    return randen, op_rand, buren


def _sluit(ketting, knooppunt, lezer, randen, op_rand, buren):
    a, b = ketting[0], ketting[-1]
    poly = [lezer.coords[n] for n in ketting]
    lengte = sum(haversine_m(*poly[i], *poly[i + 1]) for i in range(len(poly) - 1))
    idx = len(randen)
    randen.append((a, b, lengte, poly))
    for pos, n in enumerate(ketting):
        op_rand.setdefault(n, (idx, pos))
    buren[a].append((b, lengte, idx, +1))
    buren[b].append((a, lengte, idx, -1))


def snap_stations(con, lezer, op_rand):
    """Cluster -> dichtstbijzijnde ruwe spoorknoop (grid-index), max SNAP_MAX_M."""
    grid = defaultdict(list)
    for n, (lat, lon) in lezer.coords.items():
        if n in op_rand:
            grid[(round(lat, 2), round(lon, 2))].append((n, lat, lon))

    snap = {}
    for cid, lat, lon in con.execute(
        "SELECT cluster_id, lat, lon FROM clusters WHERE lat IS NOT NULL"
    ).fetchall():
        beste, beste_d = None, SNAP_MAX_M
        for dlat in (-0.02, -0.01, 0, 0.01, 0.02):
            for dlon in (-0.02, -0.01, 0, 0.01, 0.02):
                for n, nlat, nlon in grid.get((round(lat + dlat, 2), round(lon + dlon, 2)), []):
                    d = haversine_m(lat, lon, nlat, nlon)
                    if d < beste_d:
                        beste, beste_d = n, d
        if beste is not None:
            snap[cid] = beste
    return snap


def route(start_n, doel_n, doel_co, lezer, randen, op_rand, buren, limiet):
    """A* van ruwe knoop naar ruwe knoop: virtuele start/eindknopen op hun rand."""
    def h(n):
        lat, lon = lezer.coords[n]
        return haversine_m(lat, lon, *doel_co)

    def virtueel(n):
        """Verbind een ruwe (mogelijk mid-rand) knoop met de knooppunten van zijn rand."""
        idx, pos = op_rand[n]
        a, b, _, poly = randen[idx]
        la = sum(haversine_m(*poly[i], *poly[i + 1]) for i in range(pos))
        lb = sum(haversine_m(*poly[i], *poly[i + 1]) for i in range(pos, len(poly) - 1))
        return [(a, la, (idx, pos, "voor")), (b, lb, (idx, pos, "na"))]

    beste = {start_n: 0.0}
    herkomst = {}
    pq = [(h(start_n), 0.0, start_n)]
    start_links = {kn: (l, tag) for kn, l, tag in virtueel(start_n)}
    doel_links = {kn: (l, tag) for kn, l, tag in virtueel(doel_n)}

    def expandeer(n, g):
        uit = []
        if n == start_n:
            for kn, (l, tag) in start_links.items():
                if kn != n:
                    uit.append((kn, l, tag))
        # knooppunten expanderen altijd ook via de gewone graaf (een gesnapt station
        # kan zelf een knooppunt zijn en moet dan alle richtingen op kunnen)
        for buur, l, idx, richting in buren.get(n, []):
            uit.append((buur, l, (idx, richting)))
        if n != start_n and n in doel_links:
            l, tag = doel_links[n]
            uit.append((doel_n, l, tag))
        return uit

    while pq:
        f, g, n = heapq.heappop(pq)
        if n == doel_n:
            pad = []
            while n in herkomst:
                n, stap = herkomst[n]
                pad.append(stap)
            return list(reversed(pad))
        if g > beste.get(n, ONEINDIG) or f > limiet:
            continue
        for buur, l, stap in expandeer(n, g):
            ng = g + l
            if ng < beste.get(buur, ONEINDIG) and ng + h(buur) <= limiet:
                beste[buur] = ng
                herkomst[buur] = (n, (stap, buur))
                heapq.heappush(pq, (ng + h(buur), ng, buur))
    return None


def pad_naar_polyline(pad, start_n, randen, op_rand, lezer):
    punten = [lezer.coords[start_n]]
    for stap, bereikt in pad:
        if len(stap) == 2:                      # hele rand
            idx, richting = stap
            poly = randen[idx][3]
            punten.extend(poly if richting == +1 else poly[::-1])
        else:                                    # deelrand vanaf/naar virtuele knoop
            idx, pos, kant = stap
            a, b, _, poly = randen[idx]
            deel = poly[: pos + 1][::-1] if kant == "voor" else poly[pos:]
            if punten and haversine_m(*punten[-1], *deel[0]) > haversine_m(*punten[-1], *deel[-1]):
                deel = deel[::-1]
            punten.extend(deel)
    return punten


def main():
    global LANDEN
    if len(sys.argv) > 1:
        LANDEN = sys.argv[1:]
    t0 = time.monotonic()
    filter_rail()

    lezer = RailLezer()
    for land in LANDEN:
        pad = OSM / f"rail_{land}.osm.pbf"
        if pad.exists():
            print(f"parse {pad.name}…", flush=True)
            lezer.apply_file(str(pad), locations=False)
    print(f"OSM: {len(lezer.ways)} ways, {len(lezer.coords)} knopen", flush=True)

    randen, op_rand, buren = bouw_graaf(lezer)
    print(f"graaf: {len(randen)} randen, {len(buren)} knooppunten ({time.monotonic()-t0:.0f} s)", flush=True)

    con = duckdb.connect(str(MERGED), read_only=True)
    snap = snap_stations(con, lezer, op_rand)
    print(f"stations gesnapt: {len(snap)}", flush=True)

    paren = con.execute("SELECT DISTINCT least(a,b), greatest(a,b) FROM (SELECT split_part(fijn,'|',1) a, split_part(fijn,'|',2) b FROM segment_verfijning UNION ALL SELECT split_part(grof,'|',1), split_part(grof,'|',2) FROM segment_verfijning)").fetchall()
    # plus alle bladsegmenten die niet in de verfijningstabel voorkomen
    alle = con.execute(
        """WITH volgorde AS (
             SELECT st.trip_id, sc.cluster_id, CAST(st.stop_sequence AS INT) seq
             FROM stop_times st JOIN stop_cluster sc USING (stop_id)),
           opv AS (
             SELECT cluster_id a, lead(cluster_id) OVER (PARTITION BY trip_id ORDER BY seq) b
             FROM volgorde)
           SELECT DISTINCT least(a, b), greatest(a, b) FROM opv WHERE b IS NOT NULL AND a <> b"""
    ).fetchall()
    coords = {
        cid: (lat, lon)
        for cid, lat, lon in con.execute("SELECT cluster_id, lat, lon FROM clusters WHERE lat IS NOT NULL").fetchall()
    }
    paren = sorted(set(tuple(p) for p in paren) | set(tuple(p) for p in alle))

    resultaat = {}
    mislukt = 0
    for i, (a, b) in enumerate(paren):
        if a not in snap or b not in snap or a not in coords or b not in coords:
            continue
        if snap[a] == snap[b]:
            mislukt += 1  # beide stations op dezelfde spoorknoop gesnapt
            continue
        hemelsbreed = haversine_m(coords[a][0], coords[a][1], coords[b][0], coords[b][1])
        limiet = PAD_FACTOR * hemelsbreed + PAD_SLACK_M
        pad = route(snap[a], snap[b], lezer.coords[snap[b]], lezer, randen, op_rand, buren, limiet)
        if pad is None:
            mislukt += 1
            continue
        punten = pad_naar_polyline(pad, snap[a], randen, op_rand, lezer)
        if len(punten) < 2:
            mislukt += 1
            continue
        lijn = LineString([(lon, lat) for lat, lon in punten]).simplify(SIMPLIFY_GRADEN)
        resultaat[f"{a}|{b}"] = [[round(x, 5), round(y, 5)] for x, y in lijn.coords]
        if (i + 1) % 2000 == 0:
            print(f"  {i+1}/{len(paren)} paren, {mislukt} zonder pad ({time.monotonic()-t0:.0f} s)", flush=True)

    UIT.mkdir(parents=True, exist_ok=True)
    uitpad = UIT / "paar_geometrie.json.gz"
    uitpad.write_bytes(gzip.compress(json.dumps(resultaat, separators=(",", ":")).encode()))
    print(
        f"klaar: {len(resultaat)} paren met geometrie, {mislukt} fallback-rechte-lijn, "
        f"{uitpad.stat().st_size/1e6:.1f} MB gz, totaal {time.monotonic()-t0:.0f} s",
        flush=True,
    )


if __name__ == "__main__":
    main()
