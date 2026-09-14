"""Statische lookups uit de spike-output (merged.duckdb): stop -> cluster, clusterinfo."""

import heapq
import math
import os
import unicodedata
from dataclasses import dataclass

import duckdb

from .config import MERGED_DB


def normalize_name(name: str) -> str:
    """Station-name key for matching disruption texts: casefolded, unaccented,
    hyphens/spaces collapsed ("Liège-Guillemins" == "liege guillemins")."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return " ".join(name.casefold().replace("-", " ").split())


# How far off the straight u -> b line a station may lie and still count as on the
# way (Statisch._through_edges). This bounds the station's position, not a detour:
# Maarn lies within 0.5 % of the Driebergen-Zeist -> Veenendaal-De Klomp line.
ON_ROUTE_FACTOR = 1.1


@dataclass
class Cluster:
    cluster_id: str
    naam: str
    lat: float
    lon: float
    land: str


class Statisch:
    def __init__(self) -> None:
        # connection stays open: trip_segments() looks up routes on demand
        con = self.con = duckdb.connect(str(MERGED_DB), read_only=True)
        # DuckDB's default limit is 80% of RAM; on the 1 GB VM that let the
        # buffer cache (inspection's trips/stop_times joins) crowd out the
        # Python heap and push the whole box into swap. Instance-wide setting,
        # so it also covers cursors handed to the maintenance thread.
        con.execute(f"SET memory_limit = '{os.environ.get('REISPLAN_AGG_DUCKDB_MEM', '150MB')}'")
        self._trip_segments_cache: dict[tuple, list[str]] = {}
        self.cluster_van_stop: dict[str, str] = dict(
            con.execute("SELECT stop_id, cluster_id FROM stop_cluster").fetchall()
        )
        try:
            rows = con.execute(
                """SELECT c.cluster_id, c.naam, c.lat, c.lon, coalesce(cl.land, '??')
                   FROM clusters c LEFT JOIN cluster_land cl USING (cluster_id)"""
            ).fetchall()
        except duckdb.CatalogException:
            # cluster_land komt uit spike-stap s4 en ontbreekt op de VM — land is optioneel
            rows = con.execute(
                "SELECT cluster_id, naam, lat, lon, '??' FROM clusters"
            ).fetchall()
        self.clusters: dict[str, Cluster] = {
            cid: Cluster(cid, naam, lat, lon, land) for cid, naam, lat, lon, land in rows
        }
        self.verfijning: dict[str, list[tuple[str, float]]] = {}
        try:
            for grof, fijn, fractie in con.execute(
                "SELECT grof, fijn, fractie FROM segment_verfijning ORDER BY grof, volgorde"
            ).fetchall():
                self.verfijning.setdefault(grof, []).append((fijn, fractie))
        except duckdb.CatalogException:
            pass  # tabel bestaat nog niet (oudere merge) — geen verfijning
        self.segment_randen: dict[str, list[str]] = {}
        try:
            for seg, rand in con.execute("SELECT segment, rand FROM segment_randen").fetchall():
                self.segment_randen.setdefault(seg, []).append(rand)
        except duckdb.CatalogException:
            pass  # nog geen randtabel — segmenten kleuren dan niet
        # disruption-feed lookups (map improvement 8); each optional on older merges
        self.cluster_by_ns_code: dict[str, str] = {}
        try:
            self.cluster_by_ns_code = {
                code.lower(): cid for code, cid in con.execute(
                    """SELECT s.stop_code, sc.cluster_id
                       FROM stations s JOIN station_cluster sc USING (station_id)
                       WHERE s.feed = 'nl' AND s.stop_code IS NOT NULL"""
                ).fetchall()
            }
        except duckdb.CatalogException:
            pass
        self.cluster_by_uic: dict[str, str] = {}
        try:
            self.cluster_by_uic = dict(con.execute(
                "SELECT uic, cluster_id FROM clusters WHERE uic IS NOT NULL").fetchall())
        except (duckdb.CatalogException, duckdb.BinderException):
            pass
        self.be_cluster_by_name: dict[str, str] = {}
        try:
            self.be_cluster_by_name = {
                normalize_name(naam): cid for naam, cid in con.execute(
                    """SELECT naam, cluster_id FROM clusters
                       WHERE list_contains(string_split(feeds, ','), 'be')"""
                ).fetchall()
            }
        except (duckdb.CatalogException, duckdb.BinderException):
            pass
        # any-country name lookup (NS situation texts name border stations too).
        # Duplicate clusters make names ambiguous ("Heerlen" exists as nl- and
        # de_rv-cluster); an nl-feed cluster wins those, the rest maps to None.
        candidates: dict[str, list[tuple[str, str]]] = {}
        try:
            for naam, cid, feeds in con.execute(
                    "SELECT naam, cluster_id, coalesce(feeds, '') FROM clusters").fetchall():
                candidates.setdefault(normalize_name(naam), []).append((cid, feeds))
        except duckdb.BinderException:
            for cid, c in self.clusters.items():
                candidates.setdefault(normalize_name(c.naam), []).append((cid, ""))
        self.cluster_by_name: dict[str, str | None] = {}
        for key, opties in candidates.items():
            nl = [cid for cid, feeds in opties if "nl" in feeds.split(",")]
            self.cluster_by_name[key] = (opties[0][0] if len(opties) == 1
                                         else nl[0] if len(nl) == 1 else None)
        self._adjacency: dict[str, list[tuple[str, float]]] | None = None

    def trip_segments(self, feed_prefix: str, rt_trip_id: str) -> list[str]:
        """Fine segments along a static trip — for feeds that cancel a trip without
        listing its stops (blockade detection, PLAN.md verbeterpunt 7)."""
        key = (feed_prefix, rt_trip_id)
        if key not in self._trip_segments_cache:
            # merged trip_ids zijn feed-geprefixt; RT geeft de kale id
            rows = self.con.execute(
                "SELECT stop_id FROM stop_times WHERE feed = ? AND trip_id = ?"
                " ORDER BY stop_sequence::INT", [feed_prefix, f"{feed_prefix}:{rt_trip_id}"]
            ).fetchall()
            clusters: list[str] = []
            for (stop_id,) in rows:
                cluster = self.cluster_van_stop.get(stop_id)
                if cluster and (not clusters or clusters[-1] != cluster):
                    clusters.append(cluster)
            segments: list[str] = []
            for a, b in zip(clusters, clusters[1:]):
                segments += [fijn for fijn, _ in self.verfijn(segment_id(a, b))]
            if len(self._trip_segments_cache) > 20_000:
                self._trip_segments_cache.clear()
            self._trip_segments_cache[key] = segments
        return self._trip_segments_cache[key]

    def randen(self, segment: str) -> list[str]:
        """Getekende randen waar dit segment overheen loopt (leeg als onbekend)."""
        return self.segment_randen.get(segment, [])

    def verfijn(self, segment: str) -> list[tuple[str, float]]:
        """Expresse-segment -> bladsegmenten met lengte-fracties; identiteit als onbekend."""
        return self.verfijning.get(segment) or [(segment, 1.0)]

    def cluster(self, feed_prefix: str, rt_stop_id: str) -> str | None:
        """RT-feeds gebruiken feed-eigen stop_ids; merged is geprefixt."""
        return self.cluster_van_stop.get(f"{feed_prefix}:{rt_stop_id}")

    def chain_edges(self, cluster_ids: list[str]) -> tuple[set[str], list[str]]:
        """Drawn edges along a chain of station clusters (disruption sections).

        Refinement covers express jumps; for pairs no scheduled train serves
        directly (stopping trains only, or a closure that left no through trains in
        the feed) the shortest path over the leaf-segment graph bridges the gap,
        and failing that a segment that runs past one of the two stations.
        Returns (edges, unmapped pair descriptions) so the caller can log."""
        edges: set[str] = set()
        unmapped: list[str] = []
        for a, b in zip(cluster_ids, cluster_ids[1:]):
            if a == b:
                continue
            segment = segment_id(a, b)
            found = self._segment_edges(segment)
            if not found:
                found = [rand for p in self._leaf_path(a, b) for rand in self.randen(p)]
            if not found:
                found = self._through_edges(a, b)
            if found:
                edges.update(found)
            else:
                unmapped.append(segment)
        return edges, unmapped

    def _segment_edges(self, segment: str) -> list[str]:
        return [rand for fijn, _ in self.verfijn(segment) for rand in self.randen(fijn)]

    def _through_edges(self, a: str, b: str) -> list[str]:
        """Edges between a and b when no train runs from one to the other and the
        only leaf path doubles back.

        Maarn - Veenendaal-De Klomp (NS lists every station along the track):
        intercities pass Maarn without stopping, the stopping trains that call
        there branch off to Veenendaal West. Maarn's only other neighbour is
        Driebergen-Zeist, behind it. So take the segment from such a neighbour u to
        the far station, provided the near station lies on the way (u -> a -> b no
        longer than ON_ROUTE_FACTOR times u -> b), and drop the edges it shares
        with u - a. Edges are dissolved stretches of track and one may run past a
        in a single piece; the result can then reach back towards u, never past it.
        """
        adj = self._leaf_adjacency()
        candidates = []
        for near, far in ((a, b), (b, a)):
            for u, km_u_near in adj.get(near, []):
                if u == far:
                    continue
                km_u_far = self._km(u, far)
                if km_u_near + self._km(near, far) <= ON_ROUTE_FACTOR * km_u_far:
                    candidates.append((km_u_far, u, near, far))
        for _, u, near, far in sorted(candidates):
            shared = set(self._segment_edges(segment_id(u, near)))
            rest = [rand for rand in self._segment_edges(segment_id(u, far))
                    if rand not in shared]
            if rest:
                return rest
        return []

    def _leaf_path(self, a: str, b: str) -> list[str]:
        """Shortest a->b path over the leaf-segment graph, in km, as segment ids.

        A disruption section is a contiguous stretch of track heading one way, so
        the search only steps to stations closer to b than the current one. That
        rule is also what rejects detours: when the line itself is absent from the
        feed, any path over another line has to move away from b somewhere, and
        the result is no path instead of a wrong one.

        Hop count is not a usable distance: on 14 Sep 2026 "Mol - Hasselt" (eight
        stopping-train hops) mapped onto Mol > Leuven > Hasselt, two express
        segments, and painted Lier - Mol and Aarschot - Diest closed."""
        adj = self._leaf_adjacency()
        if a not in adj or b not in adj:
            return []
        to_b = {a: self._km(a, b)}
        dist = {a: 0.0}
        prev: dict[str, str] = {}
        queue = [(0.0, a)]
        while queue:
            d, node = heapq.heappop(queue)
            if node == b:
                path = []
                while node != a:
                    path.append(segment_id(prev[node], node))
                    node = prev[node]
                return path
            if d > dist[node]:
                continue
            for nxt, km in adj[node]:
                if nxt not in to_b:
                    to_b[nxt] = self._km(nxt, b)
                if to_b[nxt] < to_b[node] and d + km < dist.get(nxt, math.inf):
                    dist[nxt] = d + km
                    prev[nxt] = node
                    heapq.heappush(queue, (d + km, nxt))
        return []

    def _leaf_adjacency(self) -> dict[str, list[tuple[str, float]]]:
        """Stations joined by leaf segments, weighted by great-circle distance.
        Express segments with a refinement are left out: they would let a path
        jump past the stations of the line it is supposed to follow."""
        if self._adjacency is None:
            segments = {s for s in self.segment_randen if s not in self.verfijning}
            for bladen in self.verfijning.values():
                segments.update(fijn for fijn, _ in bladen)
            adj: dict[str, list[tuple[str, float]]] = {}
            for segment in segments:
                a, _, b = segment.partition("|")
                ca, cb = self.clusters.get(a), self.clusters.get(b)
                if ca is None or cb is None or ca.lat is None or cb.lat is None:
                    continue
                km = self._km(a, b)
                adj.setdefault(a, []).append((b, km))
                adj.setdefault(b, []).append((a, km))
            self._adjacency = adj
        return self._adjacency

    def _km(self, a: str, b: str) -> float:
        ca, cb = self.clusters[a], self.clusters[b]
        return haversine_km(ca.lat, ca.lon, cb.lat, cb.lon)

def segment_id(cluster_a: str, cluster_b: str) -> str:
    return "|".join(sorted((cluster_a, cluster_b)))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 12742.0 * math.asin(math.sqrt(h))
