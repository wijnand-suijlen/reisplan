"""s10: build the German station set + EVA mapping for the DB Timetables poller.

Selects `--top` stations by greedy edge cover over the static timetable: a drawn edge
can colour once it lies between two polled stops of one train (the poller's ppth chain
expansion), so the objective is the station set that puts the most edges between pairs
of polled stops. The busiest `--seed` hubs are always included (FV delay localisation
and tier-A freshness); when the greedy stalls because a line has no polled station yet
to pair with, the line with the most uncoverable edges is opened by adding both of its
endpoints. Static ceiling measured 2026-08-10: 13.4k edges vs 6.7k for a plain
busiest-480 selection.

Each selected cluster name is resolved to an IRIS EVA number via the Timetables
/station endpoint, and validated to actually carry timetable data. Some hub EVAs are
empty shells whose traffic lives on a related EVA (e.g. Berlin Hbf 8011160 is empty,
the data sits on meta-EVA 8098160), so validation walks the `meta` list as fallback.

Output: data/merged/eva_stations.json, read by the aggregator's DB Timetables source.
Requires DB_CLIENT_ID and DB_API_KEY in the environment or in the repo-root .env.
Runs weekly from deploy/vernieuw.sh (after the merge step); ~15 min at ~1 req/s.
"""

import argparse
import heapq
import json
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import duckdb
import requests

ROOT = Path(__file__).resolve().parent.parent
MERGED_DB = ROOT / "data" / "merged" / "merged.duckdb"
OUTPUT = ROOT / "data" / "merged" / "eva_stations.json"
BASE = "https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1"
USER_AGENT = "reisplan-spike/0.1 (hobbyproject; wijnand.suijlen@proton.me)"
BERLIN = ZoneInfo("Europe/Berlin")

MIN_NAME_SIMILARITY = 0.5
# The aggregator polls the same 60 req/min quota at ~45 req/min while this script
# runs (weekly on the VM, next to the live poller): stay within the leftover.
REQUEST_INTERVAL_S = 4.5

# Stations the /station lookup cannot resolve (slashes, S-Bahn tunnel stations known
# only under their transit-authority id). Validated like every other EVA, so a wrong
# entry here degrades to a skip, never to bad data.
EVA_OVERRIDES = {
    "Köln Messe/Deutz Bf": "8003368",
    "Frankfurt (Main) Hauptbahnhof tief": "8098105",
    "Frankfurt (Main) Hauptwache": "8002050",
    "Frankfurt (Main) Konstablerwache": "8002051",
    "Frankfurt (Main) Taunusanlage": "8002052",
    "Frankfurt (Main) Ostendstraße": "8002042",
    # IRIS names carry qualifiers the lookup cannot bridge ("Münster(Westf)Hbf")
    "Münster Hauptbahnhof": "8000263",
    "Freiburg Hauptbahnhof": "8000107",
    "Frankfurt (Main) Flughafen Fernbahnhof": "8070003",
    "Flughafen München": "8004168",
    "Mülheim Hauptbahnhof": "8000259",
    "Dresden Bahnhof Neustadt": "8010089",
}


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        import os

        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def normalize(name: str) -> str:
    name = unicodedata.normalize("NFKD", name.lower())
    name = name.replace("ß", "ss")
    return re.sub(r"[^a-z0-9]", "", name)


# Metro areas whose feeds name stations without the city ("Pasing", "Isartor") while
# IRIS needs the railway name ("München Pasing"). Coordinates disambiguate.
CITIES = [
    ("Berlin", 52.52, 13.40), ("Hamburg", 53.55, 10.00), ("München", 48.14, 11.58),
    ("Köln", 50.94, 6.96), ("Frankfurt", 50.11, 8.68), ("Stuttgart", 48.78, 9.18),
    ("Düsseldorf", 51.23, 6.77), ("Leipzig", 51.34, 12.37), ("Dresden", 51.05, 13.74),
    ("Hannover", 52.37, 9.74), ("Nürnberg", 49.45, 11.08), ("Bremen", 53.08, 8.81),
]


def nearby_city(lat: float, lon: float) -> str | None:
    for city, clat, clon in CITIES:
        if abs(lat - clat) < 0.15 and abs(lon - clon) < 0.22:  # ~15 km box
            return city
    return None


def query_variants(name: str, lat: float, lon: float) -> list[str]:
    """Lookup variants for feed-style station names. gtfs.de uses transit-network naming
    ("S Ostkreuz Bhf (Berlin)", "Hamburg, Reeperbahn"), IRIS uses railway naming
    ("Berlin Ostkreuz", "Hamburg Reeperbahn") and matches queries near-exactly.
    A DELFI-based merge would mostly obsolete this — see PLAN.md (flankerend punt)."""
    variants: list[str] = []

    def add(v: str) -> None:
        v = re.sub(r"\s+", " ", v).strip()
        if v and v not in variants:
            variants.append(v)

    add(name)
    m = re.match(r"^(?:S\+U|S|U)\s+(.+?)(?:\s+Bhf)?\s*\((.+)\)$", name)
    if m:  # "S Ostkreuz Bhf (Berlin)" -> "Berlin Ostkreuz" / "Berlin-Ostkreuz"
        add(f"{m.group(2)} {m.group(1)}")
        add(f"{m.group(2)}-{m.group(1)}")
    m = re.match(r"^(?:S\+U|S|U)\s+(.+)$", name)
    if m:  # "S+U Berlin Hauptbahnhof" -> "Berlin Hauptbahnhof"
        add(m.group(1))
    if name.startswith("D-"):  # Rheinland feed abbreviation for Düsseldorf
        rest = re.sub(r"\s+S$", "", name[2:])  # trailing " S" = S-Bahn marker
        add(f"Düsseldorf-{rest}")
        add(f"Düsseldorf {rest}")
    m = re.match(r"^(.+?),\s*(.+)$", name)
    if m:  # "Hamburg, Reeperbahn" -> "Reeperbahn" / "Hamburg Reeperbahn" / "Hamburg-Altona"
        add(m.group(2))
        if not m.group(2).lower().startswith(m.group(1).lower()):
            add(f"{m.group(1)} {m.group(2)}")
            add(f"{m.group(1)}-{m.group(2)}")
    m = re.match(r"^(.+?)\s*\((.+)\)$", name)
    if m and not m.group(2).islower():  # "(Berlin)" is a city; "(tief)" etc. is not
        add(f"{m.group(2)} {m.group(1)}")
    city = nearby_city(lat, lon)
    if city and not any(city.lower() in v.lower() for v in variants):
        base = re.sub(r"\s*\(.*\)$", "", name)
        add(f"{city} {base}")
        add(f"{city}-{base}")
        if base.lower().endswith("bahnhof"):  # "Ostbahnhof" is "München Ost" in IRIS
            add(f"{city} {base[: -len('bahnhof')].strip()}")
    for v in list(variants):  # spelling variants; IRIS doesn't fuzzy-match these
        if re.search(r"[Ss]tr\.", v):
            add(re.sub(r"([Ss])tr\.", r"\1traße", v))
        if "Hauptbahnhof" in v:
            add(v.replace("Hauptbahnhof", "Hbf"))
        if re.search(r"\s+(Bf|Bhf|Bahnhof)$", v):
            add(re.sub(r"\s+(Bf|Bhf|Bahnhof)$", "", v))
        if v.lower().endswith("bahnhof") and not v.lower().endswith("hauptbahnhof"):
            add(v[: -len("bahnhof")].rstrip(" -"))  # "…Südbahnhof" is "…Süd" in IRIS
    for v in list(variants):
        if "(" in v:  # IRIS writes "Frankfurt(Main)Hbf" without spaces...
            add(re.sub(r"\s*\(", "(", re.sub(r"\)\s*", ") ", v)).replace(") ", ")"))
    for v in list(variants):
        if "(" in v:  # ...and as a last resort, drop the qualifier entirely
            add(re.sub(r"\s*\([^)]*\)\s*", " ", v))
    return variants


def name_similarity(query: str, candidate: str) -> float:
    """Max similarity over naming conventions; IRIS often uses "Name, City"."""
    forms = [candidate]
    if "," in candidate:
        head, _, city = candidate.rpartition(",")
        forms.append(f"{city.strip()} {head.strip()}")
    return max(SequenceMatcher(None, normalize(query), normalize(f)).ratio() for f in forms)


class Client:
    def __init__(self) -> None:
        import os

        load_env()
        client_id, api_key = os.environ.get("DB_CLIENT_ID"), os.environ.get("DB_API_KEY")
        if not (client_id and api_key):
            sys.exit("DB_CLIENT_ID and DB_API_KEY must be set (env or .env)")
        self.session = requests.Session()
        self.session.headers.update(
            {"DB-Client-Id": client_id, "DB-Api-Key": api_key,
             "Accept": "application/xml", "User-Agent": USER_AGENT}
        )
        self.last_request = 0.0
        self.requests_made = 0

    def get(self, path: str) -> bytes | None:
        wait = self.last_request + REQUEST_INTERVAL_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.last_request = time.monotonic()
        self.requests_made += 1
        r = self.session.get(f"{BASE}{path}", timeout=30)
        if r.status_code == 404:
            return None
        if r.status_code == 429:  # back off once, then let it raise if it persists
            time.sleep(30)
            r = self.session.get(f"{BASE}{path}", timeout=30)
        r.raise_for_status()
        return r.content


def station_candidates(client: Client, name: str) -> list[dict]:
    """Resolve a station name via /station/{pattern}; returns [{eva, name, meta: [...]}]."""
    data = client.get(f"/station/{quote(name)}")
    if data is None:
        return []
    root = ET.fromstring(data)
    out = []
    for st in root.iter("station"):
        if st.get("eva"):
            out.append(
                {"eva": st.get("eva"), "name": st.get("name", ""),
                 "meta": [m for m in (st.get("meta") or "").split("|") if m]}
            )
    return out


def plan_has_data(client: Client, eva: str, when: datetime) -> bool:
    data = client.get(f"/plan/{eva}/{when.strftime('%y%m%d')}/{when.strftime('%H')}")
    return data is not None and b"<s " in data


def resolve(client: Client, cluster_name: str, lat: float, lon: float,
            when: datetime) -> tuple[dict | None, str]:
    """Find a validated EVA for a cluster name. Returns (result, reason-if-skipped)."""
    if cluster_name in EVA_OVERRIDES:
        eva = EVA_OVERRIDES[cluster_name]
        if plan_has_data(client, eva, when):
            return {"eva": eva, "iris_name": cluster_name, "similarity": 1.0}, ""
        return None, "override-no-plan-data"
    best, similarity, reason = None, 0.0, "no-match"
    for query in query_variants(cluster_name, lat, lon):
        candidates = station_candidates(client, query)
        if not candidates:
            continue
        cand = max(candidates, key=lambda c: name_similarity(query, c["name"]))
        sim = name_similarity(query, cand["name"])
        if sim > similarity:
            best, similarity = cand, sim
        if sim >= 0.9:  # good enough, skip remaining lookup variants
            break
    if best is None:
        return None, reason
    if similarity < MIN_NAME_SIMILARITY:
        return None, f"name-mismatch:{best['name']}"
    # The looked-up EVA is not always the one carrying IRIS data — walk meta EVAs too.
    for eva in [best["eva"], *best["meta"]]:
        if plan_has_data(client, eva, when):
            return {"eva": eva, "iris_name": best["name"], "similarity": round(similarity, 2)}, ""
    return None, "no-plan-data"


DE_FEEDS = "('de_fv', 'de_rv', 'de_delfi')"
SERVICE_HOURS = 19  # rough operating day, for the duty-cycle weighting


def active_services(con, day: datetime) -> set[tuple]:
    """(feed, service_id) pairs running on `day` — calendar plus exceptions."""
    date, weekday = day.strftime("%Y%m%d"), day.strftime("%A").lower()
    active = set(con.execute(
        f"""SELECT feed, service_id FROM calendar
            WHERE feed IN {DE_FEEDS} AND start_date <= ? AND end_date >= ?
              AND {weekday} = '1'""", [date, date]).fetchall())
    for feed, sid, exception in con.execute(
        f"SELECT feed, service_id, exception_type FROM calendar_dates"
        f" WHERE feed IN {DE_FEEDS} AND date = ?", [date]).fetchall():
        (active.add if exception == "1" else active.discard)((feed, sid))
    return active


def select_stations(top: int, seed: int) -> list[tuple]:
    """Greedy edge-cover selection; returns (cluster_id, naam, lat, lon, n_trips)
    sorted busiest-first (the poller makes the first `--tier-a` entries tier A).
    Patterns and weights come from one representative service day, so dormant
    timetable variants don't attract anchors."""
    con = duckdb.connect(str(MERGED_DB), read_only=True)
    active = active_services(con, datetime.now(BERLIN) + timedelta(days=1))
    rows = con.execute(
        f"""SELECT st.feed, st.trip_id, t.service_id, sc.cluster_id
            FROM stop_times st
            JOIN trips t ON t.feed = st.feed AND t.trip_id = st.trip_id
            JOIN stop_cluster sc USING (stop_id)  -- stop_times.stop_id is feed-prefixed
            WHERE st.feed IN {DE_FEEDS}
            ORDER BY st.feed, st.trip_id, st.stop_sequence::INT"""
    ).fetchall()
    trips: dict[tuple, list[str]] = defaultdict(list)
    trip_service: dict[tuple, tuple] = {}
    for feed, trip, sid, cluster in rows:
        key = (feed, trip)
        trip_service[key] = (feed, sid)
        seq = trips[key]
        if not seq or seq[-1] != cluster:
            seq.append(cluster)
    patterns = Counter(
        tuple(seq) for key, seq in trips.items()
        if len(seq) >= 2 and trip_service[key] in active
    )
    print(f"service day: {sum(patterns.values())} trips, {len(patterns)} patterns")

    verfijn: dict[str, list[str]] = defaultdict(list)
    for grof, fijn in con.execute("SELECT grof, fijn FROM segment_verfijning").fetchall():
        verfijn[grof].append(fijn)
    randen: dict[str, list[str]] = defaultdict(list)
    for seg, rand in con.execute("SELECT segment, rand FROM segment_randen").fetchall():
        randen[seg].append(rand)

    def pair_edges(a: str, b: str) -> list[str]:
        seg = "|".join(sorted((a, b)))
        return [r for f in (verfijn.get(seg) or [seg]) for r in randen.get(f, [])]

    pat_edges = {pat: [pair_edges(a, b) for a, b in zip(pat, pat[1:])] for pat in patterns}
    n_trips_at: Counter = Counter()
    for pat, weight in patterns.items():
        for cluster in pat:
            n_trips_at[cluster] += weight
    pat_positions: dict[str, dict[tuple, list[int]]] = defaultdict(lambda: defaultdict(list))
    for pat in patterns:
        for i, cluster in enumerate(pat):
            pat_positions[cluster][pat].append(i)

    covered: set[str] = set()
    sel_range: dict[tuple, tuple[int, int]] = {}
    selected: set[str] = set()

    def add_station(cluster: str) -> None:
        for pat, positions in pat_positions[cluster].items():
            cur = sel_range.get(pat)
            lo = min(positions) if cur is None else min(cur[0], *positions)
            hi = max(positions) if cur is None else max(cur[1], *positions)
            if cur is not None:
                for i in range(lo, hi):
                    if not (cur[0] <= i < cur[1]):
                        covered.update(pat_edges[pat][i])
            sel_range[pat] = (lo, hi)
        selected.add(cluster)

    def gain_of(cluster: str) -> int:
        gain: set[str] = set()
        for pat, positions in pat_positions[cluster].items():
            cur = sel_range.get(pat)
            if cur is None:
                continue  # first station of a line has no pair yet; see open_best_pattern
            lo, hi = min(cur[0], *positions), max(cur[1], *positions)
            for i in range(lo, hi):
                if not (cur[0] <= i < cur[1]):
                    gain.update(e for e in pat_edges[pat][i] if e not in covered)
        return len(gain)

    def run_greedy() -> None:
        pq = [(-(10**9), c) for c in pat_positions if c not in selected]
        heapq.heapify(pq)
        while len(selected) < top and pq:
            _, cluster = heapq.heappop(pq)
            if cluster in selected:
                continue
            gain = gain_of(cluster)
            if pq and -pq[0][0] > gain:
                heapq.heappush(pq, (-gain, cluster))
                continue
            if gain == 0:
                return
            add_station(cluster)

    def open_best_pattern() -> bool:
        """Line without any polled station yet: add both endpoints of the best one.
        Weighted by expected colouring time, not raw edge count: an edge served n
        times per day is coloured ~min(1, n * 30min / service day) of the time, so
        a frequent line beats a longer but near-empty one."""
        best, best_value = None, 0.0
        for pat, edge_lists in pat_edges.items():
            if sel_range.get(pat):
                continue
            duty = min(1.0, patterns[pat] * 30 / (SERVICE_HOURS * 60))
            value = duty * len({e for lst in edge_lists for e in lst if e not in covered})
            if value > best_value:
                best, best_value = pat, value
        if best is None or len(selected) + 2 > top:
            return False
        add_station(best[0])
        add_station(best[-1])
        return True

    for cluster, _ in n_trips_at.most_common(seed):
        add_station(cluster)
    while len(selected) < top:
        before = len(selected)
        run_greedy()
        if len(selected) >= top or not open_best_pattern():
            if len(selected) == before:
                break
    print(f"selected {len(selected)} stations covering {len(covered)} drawn edges (static)")

    info = {cid: (naam, lat, lon) for cid, naam, lat, lon in con.execute(
        "SELECT cluster_id, naam, lat, lon FROM clusters WHERE cluster_id IN "
        f"({', '.join('?' * len(selected))})", list(selected)).fetchall()}
    con.close()
    ranked = sorted(selected, key=lambda c: -n_trips_at[c])
    return [(c, *info[c], n_trips_at[c]) for c in ranked if c in info]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=480, help="number of stations to map")
    ap.add_argument("--tier-a", type=int, default=80, help="hubs polled at the fast interval")
    ap.add_argument("--seed", type=int, default=60, help="busiest hubs always included")
    ap.add_argument("--reuse", action="store_true",
                    help="keep previously mapped stations; only resolve new/skipped ones")
    args = ap.parse_args()

    previous = {}
    if args.reuse and OUTPUT.exists():
        previous = {s["cluster_id"]: s for s in json.loads(OUTPUT.read_text())["stations"]}

    ranked = select_stations(args.top, args.seed)
    print(f"{len(ranked)} candidate clusters from merged.duckdb")

    client = Client()
    # Validate against a daytime plan slice so quiet stations aren't skipped at night.
    when = datetime.now(BERLIN) + timedelta(hours=2)
    if not 7 <= when.hour <= 21:
        when = when.replace(hour=12)

    stations, skipped = [], []
    for rank, (cluster_id, name, lat, lon, n_trips) in enumerate(ranked):
        if cluster_id in previous:
            prev = previous[cluster_id]
            result, reason = {k: prev[k] for k in ("eva", "iris_name", "similarity")}, ""
        else:
            result, reason = resolve(client, name, lat, lon, when)
        if result is None:
            skipped.append({"cluster_id": cluster_id, "name": name, "reason": reason})
            continue
        stations.append(
            {**result, "cluster_id": cluster_id, "name": name, "n_trips": n_trips,
             "tier": "A" if len(stations) < args.tier_a else "B"}
        )
        if (rank + 1) % 50 == 0:
            print(f"  {rank + 1}/{len(ranked)} processed, {len(skipped)} skipped")

    OUTPUT.write_text(json.dumps(
        {"built": datetime.now(BERLIN).isoformat(timespec="seconds"),
         "stations": stations, "skipped": skipped}, ensure_ascii=False, indent=1))
    print(f"{len(stations)} stations mapped ({sum(s['tier'] == 'A' for s in stations)} tier A), "
          f"{len(skipped)} skipped, {client.requests_made} API requests -> {OUTPUT}")
    for s in skipped[:15]:
        print(f"  skipped: {s['name']} ({s['reason']})")


if __name__ == "__main__":
    main()
