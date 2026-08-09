"""s4: dekkingsmatrix internationale treinen.

Kent per cluster een land toe (UIC-prefix, fallback point-in-polygon Natural Earth 50m),
vindt grensoverschrijdende trips, en rapporteert per corridor x feed welke series er
rijden — plus een checklist van verwachte internationale diensten met per-feed-dekking.
Output: data/rapporten/dekkingsmatrix.md; tabel cluster_land in merged.duckdb.
"""

import json
from collections import defaultdict
from pathlib import Path

import duckdb
import requests
from shapely.geometry import Point, shape
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parent.parent
MERGED = ROOT / "data" / "merged" / "merged.duckdb"
RAPPORT = ROOT / "data" / "rapporten" / "dekkingsmatrix.md"
NE_PAD = ROOT / "data" / "ne_50m_landen.geojson"
NE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"

UIC_LAND = {"84": "NL", "88": "BE", "87": "FR", "80": "DE", "85": "CH"}
FEEDS = ["nl", "be", "fr", "de_fv", "de_rv", "ch"]

CHECKLIST = [
    ("Eurostar (Adam-Brussel-Parijs/Londen)", ["eurostar"]),
    ("ICE (International)", ["ice"]),
    ("IC Berlijn (Adam-Berlijn)", ["berlin"]),
    ("IC/EC Adam-Brussel", ["brussel", "bruxelles"]),
    ("TGV Lyria (Parijs-CH)", ["lyria"]),
    ("TGV (overig internationaal)", ["tgv"]),
    ("EuroCity / ECE", ["eurocity", "ec "]),
    ("Nightjet / nachttrein", ["nightjet", "nj ", "en "]),
    ("European Sleeper", ["sleeper"]),
    ("FlixTrain", ["flix"]),
]


def landpolygonen():
    if not NE_PAD.exists():
        NE_PAD.write_bytes(requests.get(NE_URL, timeout=120).content)
    fc = json.loads(NE_PAD.read_text())
    interessant = {"NL", "BE", "FR", "DE", "CH", "GB", "LU", "AT", "IT", "ES", "DK", "PL", "CZ"}
    polys = {}
    for f in fc["features"]:
        iso = f["properties"].get("ISO_A2_EH") or f["properties"].get("ISO_A2")
        if iso in interessant:
            polys[iso] = prep(shape(f["geometry"]))
    return polys


def main():
    con = duckdb.connect(str(MERGED))
    polys = landpolygonen()

    clusters = con.execute("SELECT cluster_id, uic, lat, lon FROM clusters").fetchall()
    land_van = {}
    for cid, uic, lat, lon in clusters:
        land = UIC_LAND.get(uic[:2]) if uic else None
        if land is None and lat is not None:
            p = Point(lon, lat)
            land = next((iso for iso, poly in polys.items() if poly.contains(p)), "??")
        land_van[cid] = land or "??"
    con.execute("CREATE OR REPLACE TABLE cluster_land (cluster_id VARCHAR, land VARCHAR)")
    con.executemany("INSERT INTO cluster_land VALUES (?, ?)", list(land_van.items()))

    # events over ALLE clusters (niet alleen multi-feed) voor landbepaling per trip
    con.execute(
        """CREATE OR REPLACE TABLE trip_landen AS
           SELECT t.trip_id, t.feed, list_sort(list_distinct(list(cl.land))) AS landen
           FROM stop_times st
           JOIN stop_cluster sc USING (stop_id)
           JOIN cluster_land cl USING (cluster_id)
           JOIN trips t USING (trip_id)
           GROUP BY 1, 2"""
    )
    intl = con.execute(
        """CREATE OR REPLACE TABLE intl_trips AS
           SELECT tl.trip_id, tl.feed, array_to_string(tl.landen, '-') AS corridor,
                  t.route_id, t.trip_headsign
           FROM trip_landen tl JOIN trips t USING (trip_id)
           WHERE len(tl.landen) >= 2;
           SELECT count(*) FROM intl_trips"""
    ).fetchone()[0]

    out = ["# Dekkingsmatrix internationale treinen\n", f"Internationale trips totaal: {intl}\n"]

    out.append("## Corridors per feed (aantal trips)\n")
    rows = con.execute(
        """SELECT corridor, feed, count(*) FROM intl_trips GROUP BY 1, 2 ORDER BY 1, 2"""
    ).fetchall()
    per_corridor = defaultdict(dict)
    for corridor, feed, n in rows:
        per_corridor[corridor][feed] = n
    out.append("| corridor | " + " | ".join(FEEDS) + " |")
    out.append("|" + "---|" * (len(FEEDS) + 1))
    for corridor in sorted(per_corridor):
        cel = [str(per_corridor[corridor].get(f, "")) for f in FEEDS]
        out.append(f"| {corridor} | " + " | ".join(cel) + " |")

    out.append("\n## Series per corridor (route + agency, top 8 per feed)\n")
    series = con.execute(
        """SELECT i.corridor, i.feed,
                  coalesce(a.agency_name, '?') || ' / ' ||
                  coalesce(nullif(r.route_short_name, ''), nullif(r.route_long_name, ''), r.route_id) AS serie,
                  count(*) AS n
           FROM intl_trips i
           JOIN routes r USING (route_id)
           LEFT JOIN agency a ON r.agency_id = a.agency_id
           GROUP BY 1, 2, 3 ORDER BY 1, 2, 4 DESC"""
    ).fetchall()
    per = defaultdict(list)
    for corridor, feed, serie, n in series:
        per[(corridor, feed)].append(f"{serie} ({n})")
    for (corridor, feed), lst in sorted(per.items()):
        out.append(f"- **{corridor} / {feed}**: " + "; ".join(lst[:8]) + ("…" if len(lst) > 8 else ""))

    out.append("\n## Checklist verwachte diensten (zoekterm in route/headsign/agency van intl. trips)\n")
    out.append("| dienst | " + " | ".join(FEEDS) + " |")
    out.append("|" + "---|" * (len(FEEDS) + 1))
    for naam, termen in CHECKLIST:
        cel = []
        for feed in FEEDS:
            clause = " OR ".join(
                f"lower(coalesce(r.route_short_name,'') || ' ' || coalesce(r.route_long_name,'') || ' ' || "
                f"coalesce(i.trip_headsign,'') || ' ' || coalesce(a.agency_name,'')) LIKE '%{t}%'"
                for t in termen
            )
            n = con.execute(
                f"""SELECT count(*) FROM intl_trips i
                    JOIN routes r USING (route_id)
                    LEFT JOIN agency a ON r.agency_id = a.agency_id
                    WHERE i.feed = '{feed}' AND ({clause})"""
            ).fetchone()[0]
            cel.append(str(n) if n else "—")
        out.append(f"| {naam} | " + " | ".join(cel) + " |")

    RAPPORT.write_text("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
