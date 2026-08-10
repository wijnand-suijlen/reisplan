"""Statische lookups uit de spike-output (merged.duckdb): stop -> cluster, clusterinfo."""

from dataclasses import dataclass

import duckdb

from .config import MERGED_DB


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

    def trip_segments(self, feed_prefix: str, rt_trip_id: str) -> list[str]:
        """Fine segments along a static trip — for feeds that cancel a trip without
        listing its stops (blockade detection, PLAN.md verbeterpunt 7)."""
        key = (feed_prefix, rt_trip_id)
        if key not in self._trip_segments_cache:
            rows = self.con.execute(
                "SELECT stop_id FROM stop_times WHERE feed = ? AND trip_id = ?"
                " ORDER BY stop_sequence::INT", [feed_prefix, rt_trip_id]
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


def segment_id(cluster_a: str, cluster_b: str) -> str:
    return "|".join(sorted((cluster_a, cluster_b)))
