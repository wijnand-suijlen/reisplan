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
        con = duckdb.connect(str(MERGED_DB), read_only=True)
        self.cluster_van_stop: dict[str, str] = dict(
            con.execute("SELECT stop_id, cluster_id FROM stop_cluster").fetchall()
        )
        self.clusters: dict[str, Cluster] = {
            cid: Cluster(cid, naam, lat, lon, land)
            for cid, naam, lat, lon, land in con.execute(
                """SELECT c.cluster_id, c.naam, c.lat, c.lon, coalesce(cl.land, '??')
                   FROM clusters c LEFT JOIN cluster_land cl USING (cluster_id)"""
            ).fetchall()
        }
        con.close()

    def cluster(self, feed_prefix: str, rt_stop_id: str) -> str | None:
        """RT-feeds gebruiken feed-eigen stop_ids; merged is geprefixt."""
        return self.cluster_van_stop.get(f"{feed_prefix}:{rt_stop_id}")


def segment_id(cluster_a: str, cluster_b: str) -> str:
    return "|".join(sorted((cluster_a, cluster_b)))
