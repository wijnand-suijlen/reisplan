"""Statische lookups uit de spike-output (merged.duckdb): stop -> cluster, clusterinfo."""

import unicodedata
from collections import deque
from dataclasses import dataclass

import duckdb

from .config import MERGED_DB


def normalize_name(name: str) -> str:
    """Station-name key for matching disruption texts: casefolded, unaccented,
    hyphens/spaces collapsed ("Liège-Guillemins" == "liege guillemins")."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return " ".join(name.casefold().replace("-", " ").split())


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
        self._adjacency: dict[str, set[str]] | None = None

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
        directly (e.g. a months-long closure has no through trains left in the
        feed) a hop-limited BFS over the leaf-segment graph bridges the gap.
        Returns (edges, unmapped pair descriptions) so the caller can log."""
        edges: set[str] = set()
        unmapped: list[str] = []
        for a, b in zip(cluster_ids, cluster_ids[1:]):
            if a == b:
                continue
            segment = segment_id(a, b)
            parts = [fijn for fijn, _ in self.verfijn(segment)]
            found = [rand for p in parts for rand in self.randen(p)]
            if not found:
                found = [rand for p in self._bfs_path(a, b) for rand in self.randen(p)]
            if found:
                edges.update(found)
            else:
                unmapped.append(segment)
        return edges, unmapped

    def _bfs_path(self, a: str, b: str, max_hops: int = 25) -> list[str]:
        """Shortest hop-path a->b over the leaf-segment graph, as segment ids."""
        adj = self._leaf_adjacency()
        if a not in adj or b not in adj:
            return []
        prev: dict[str, str | None] = {a: None}
        queue: deque[tuple[str, int]] = deque([(a, 0)])
        while queue:
            node, dist = queue.popleft()
            if node == b:
                path = []
                while prev[node] is not None:
                    path.append(segment_id(prev[node], node))
                    node = prev[node]
                return path
            if dist >= max_hops:
                continue
            for nxt in adj[node]:
                if nxt not in prev:
                    prev[nxt] = node
                    queue.append((nxt, dist + 1))
        return []

    def _leaf_adjacency(self) -> dict[str, set[str]]:
        if self._adjacency is None:
            segments = set(self.segment_randen)
            for bladen in self.verfijning.values():
                segments.update(fijn for fijn, _ in bladen)
            adj: dict[str, set[str]] = {}
            for segment in segments:
                a, _, b = segment.partition("|")
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
            self._adjacency = adj
        return self._adjacency


def segment_id(cluster_a: str, cluster_b: str) -> str:
    return "|".join(sorted((cluster_a, cluster_b)))
