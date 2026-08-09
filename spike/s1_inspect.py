"""s1: feedinventaris vóór het filteren.

Per feed: route_type-verdeling, agencies, aanwezige bestanden/optionele kolommen,
kalenderhorizon. Output naar stdout en data/rapporten/s1_inventaris.md.
"""

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RAPPORT = ROOT / "data" / "rapporten" / "s1_inventaris.md"

FEEDS = ["nl", "be", "fr", "de_fv", "de_rv", "ch"]

OPTIONELE_KOLOMMEN = {
    "routes.txt": ["route_color"],
    "trips.txt": ["trip_short_name", "bikes_allowed", "wheelchair_accessible", "shape_id", "block_id"],
    "stops.txt": ["stop_code", "parent_station", "location_type", "platform_code", "wheelchair_boarding"],
    "stop_times.txt": ["pickup_type", "drop_off_type"],
}


def kolommen(con, pad: Path) -> list[str]:
    rows = con.execute(
        "SELECT column_name FROM (DESCRIBE SELECT * FROM read_csv_auto(?, header=true, sample_size=1000))",
        [str(pad)],
    ).fetchall()
    return [r[0] for r in rows]


def main() -> None:
    con = duckdb.connect()
    out = ["# s1 — feedinventaris\n"]
    for feed in FEEDS:
        map_ = RAW / feed
        if not map_.exists():
            out.append(f"## {feed}\nONTBREEKT\n")
            continue
        out.append(f"## {feed}\n")
        bestanden = sorted(p.name for p in map_.iterdir() if p.is_file())
        out.append(f"Bestanden: {', '.join(bestanden)}\n")

        rt = con.execute(
            f"SELECT route_type, count(*) FROM read_csv_auto('{map_}/routes.txt', header=true) GROUP BY 1 ORDER BY 1"
        ).fetchall()
        out.append("route_type-verdeling: " + ", ".join(f"{t}: {n}" for t, n in rt) + "\n")

        ag = con.execute(
            f"SELECT agency_id, agency_name FROM read_csv_auto('{map_}/agency.txt', header=true) ORDER BY 2 LIMIT 60"
        ).fetchall()
        n_ag = con.execute(
            f"SELECT count(*) FROM read_csv_auto('{map_}/agency.txt', header=true)"
        ).fetchone()[0]
        out.append(f"Agencies ({n_ag}): " + "; ".join(f"{a or ''}={b}" for a, b in ag[:25]) + ("…" if n_ag > 25 else "") + "\n")

        for bestand, kols in OPTIONELE_KOLOMMEN.items():
            pad = map_ / bestand
            if pad.exists():
                aanwezig = set(kolommen(con, pad))
                out.append(f"{bestand}: " + ", ".join(f"{k}={'JA' if k in aanwezig else 'nee'}" for k in kols) + "\n")

        horizon = []
        if (map_ / "calendar.txt").exists():
            r = con.execute(
                f"SELECT min(start_date), max(end_date) FROM read_csv_auto('{map_}/calendar.txt', header=true, all_varchar=true)"
            ).fetchone()
            horizon.append(f"calendar {r[0]}–{r[1]}")
        if (map_ / "calendar_dates.txt").exists():
            r = con.execute(
                f"SELECT min(date), max(date) FROM read_csv_auto('{map_}/calendar_dates.txt', header=true, all_varchar=true)"
            ).fetchone()
            horizon.append(f"calendar_dates {r[0]}–{r[1]}")
        out.append("Horizon: " + "; ".join(horizon) + "\n")

        n = {}
        for t in ["routes", "trips", "stops"]:
            n[t] = con.execute(
                f"SELECT count(*) FROM read_csv_auto('{map_}/{t}.txt', header=true)"
            ).fetchone()[0]
        out.append(f"Aantallen: routes={n['routes']}, trips={n['trips']}, stops={n['stops']}\n")

        stops_kols = kolommen(con, map_ / "stops.txt")
        code_expr = "coalesce(stop_code,'')" if "stop_code" in stops_kols else "''"
        voorbeeld = con.execute(
            f"SELECT stop_id, {code_expr} FROM read_csv_auto('{map_}/stops.txt', header=true, all_varchar=true) LIMIT 5"
        ).fetchall()
        out.append("Voorbeeld stop_id/stop_code: " + "; ".join(f"{a}/{b}" for a, b in voorbeeld) + "\n")

    RAPPORT.parent.mkdir(parents=True, exist_ok=True)
    RAPPORT.write_text("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
