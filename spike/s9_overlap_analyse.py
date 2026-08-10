"""s9: inventaris van baanvakken die visueel dubbel getekend worden.

Methode: elke segmentpolyline wordt om de ~250 m gesampled in een gridindex;
paren segmenten waarvan >60% van de punten van de kortste binnen ~150 m van de
ander liggen gelden als 'overlappend'. Classificatie per paar:
  - duplicaat-stations: beide eindpunten van A liggen <400 m bij die van B
    (zelfde fysieke stations, verschillende clusters -> stationsdedup-falen)
  - expres-over-keten:  beide eindpunten van A liggen op de polyline van B of
    andersom-in-ketens (verfijning had A moeten ontleden maar deed dat niet)
  - overig/parallel:    rest (parallelle sporen, gedeelde corridor)
Output: aantallen per categorie + steekproef van >=12 gevallen met details.
"""

import json
import math
import random
from collections import defaultdict
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
GEOJSON = ROOT / "web" / "vertragingskaart" / "data" / "segments.geojson"
MERGED = ROOT / "data" / "merged" / "merged.duckdb"

CEL = 0.004          # ~330 m
SAMPLE_M = 250.0
NABIJ_M = 150.0
OVERLAP_MIN = 0.6
EIND_M = 400.0


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def sample(coords):
    punten = []
    rest = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        l = haversine_m(y1, x1, y2, x2)
        if l == 0:
            continue
        d = rest
        while d < l:
            f = d / l
            punten.append((y1 + f * (y2 - y1), x1 + f * (x2 - x1)))
            d += SAMPLE_M
        rest = d - l
    punten.append((coords[-1][1], coords[-1][0]))
    return punten


def main():
    fc = json.loads(GEOJSON.read_text())
    segs = {}
    for f in fc["features"]:
        segs[f["id"]] = {
            "coords": f["geometry"]["coordinates"],
            "van": f["properties"].get("van") or f["properties"].get("lijnen", f["id"]),
            "naar": f["properties"].get("naar", ""),
        }

    grid = defaultdict(set)
    punten_van = {}
    for sid, s in segs.items():
        pts = sample(s["coords"])
        punten_van[sid] = pts
        for lat, lon in pts:
            grid[(round(lat / CEL), round(lon / CEL))].add(sid)

    con = duckdb.connect(str(MERGED), read_only=True)
    clusterinfo = {
        cid: (naam, lat, lon, feeds)
        for cid, naam, lat, lon, feeds in con.execute(
            "SELECT cluster_id, naam, lat, lon, feeds FROM clusters"
        ).fetchall()
    }

    overlap = {}
    for sid, pts in punten_van.items():
        if len(pts) < 4:
            continue
        raak = defaultdict(int)
        for lat, lon in pts:
            c = (round(lat / CEL), round(lon / CEL))
            kandidaten = set()
            for dl1 in (-1, 0, 1):
                for dl2 in (-1, 0, 1):
                    kandidaten |= grid.get((c[0] + dl1, c[1] + dl2), set())
            geraakt = set()
            for ander in kandidaten:
                if ander == sid or ander in geraakt:
                    continue
                for alat, alon in punten_van[ander]:
                    if haversine_m(lat, lon, alat, alon) <= NABIJ_M:
                        geraakt.add(ander)
                        break
            for ander in geraakt:
                raak[ander] += 1
        for ander, n in raak.items():
            if sid < ander and n / len(pts) >= OVERLAP_MIN:
                overlap[(sid, ander)] = n / len(pts)

    def eindpunten(sid):
        if "|" not in sid:
            return None, None, sid, sid  # rand-id (geen stationspaar)
        a, b = sid.replace("F:", "").split("|")
        return clusterinfo.get(a), clusterinfo.get(b), a, b

    def dichtbij_lijn(cl, pts):
        _, lat, lon, _ = cl
        return any(haversine_m(lat, lon, plat, plon) <= 300 for plat, plon in pts)

    per_cat = defaultdict(list)
    for (s1, s2), frac in overlap.items():
        a1, a2, ida1, ida2 = eindpunten(s1)
        b1, b2, idb1, idb2 = eindpunten(s2)
        if not all([a1, a2, b1, b2]):
            per_cat["onbekend"].append((s1, s2, frac))
            continue
        d_recht = min(
            max(haversine_m(a1[1], a1[2], b1[1], b1[2]), haversine_m(a2[1], a2[2], b2[1], b2[2])),
            max(haversine_m(a1[1], a1[2], b2[1], b2[2]), haversine_m(a2[1], a2[2], b1[1], b1[2])),
        )
        if d_recht <= EIND_M:
            per_cat["duplicaat-stations"].append((s1, s2, frac))
        elif dichtbij_lijn(a1, punten_van[s2]) and dichtbij_lijn(a2, punten_van[s2]):
            per_cat["expres-over-keten"].append((s1, s2, frac))
        elif dichtbij_lijn(b1, punten_van[s1]) and dichtbij_lijn(b2, punten_van[s1]):
            per_cat["expres-over-keten"].append((s1, s2, frac))
        else:
            per_cat["overig-parallel"].append((s1, s2, frac))

    print(f"overlappende paren totaal: {len(overlap)}")
    for cat, lijst in sorted(per_cat.items(), key=lambda kv: -len(kv[1])):
        print(f"  {cat}: {len(lijst)}")

    random.seed(42)
    print("\n=== steekproef ===")
    for cat, lijst in per_cat.items():
        for s1, s2, frac in random.sample(lijst, min(5, len(lijst))):
            a1, a2, ida1, ida2 = eindpunten(s1)
            b1, b2, idb1, idb2 = eindpunten(s2)
            print(f"\n[{cat}] overlap {frac:.0%}")
            print(f"  A: {a1[0]} – {a2[0]}   ({ida1} [{a1[3]}] | {ida2} [{a2[3]}])")
            print(f"  B: {b1[0]} – {b2[0]}   ({idb1} [{b1[3]}] | {idb2} [{b2[3]}])")


if __name__ == "__main__":
    main()
