"""Serve the planned_closures table (built by closure_baseline.py in the weekly ETL)
to the poll loop: which drawn edges have zero scheduled service right now against
their baseline. Loaded once at startup — vernieuw.sh restarts the aggregator after
every merge, which refreshes the data."""

import logging
import zoneinfo
from datetime import datetime

import duckdb

from .config import MERGED_DB

log = logging.getLogger("aggregator")
# One zone for all five countries: NL/BE/FR/DE/CH share CET/CEST anyway.
TZ = zoneinfo.ZoneInfo("Europe/Amsterdam")


class PlannedClosures:
    def __init__(self) -> None:
        # (date, hour_start, hour_end) blocks per edge, from the weekly ETL
        self._blocks: dict[str, list[tuple[str, int, int]]] = {}
        try:
            con = duckdb.connect(str(MERGED_DB), read_only=True)
            for d, rand, h0, h1 in con.execute(
                "SELECT date, rand, hour_start, hour_end FROM planned_closures"
            ).fetchall():
                self._blocks.setdefault(rand, []).append((d, h0, h1))
            con.close()
        except duckdb.CatalogException:
            log.info("planned_closures ontbreekt in merged.duckdb — baseline-signaal uit")
        log.info("planned closures geladen: %d randen", len(self._blocks))

    def active_edges(self, now: float) -> set[str]:
        local = datetime.fromtimestamp(now, TZ)
        d, hour = local.strftime("%Y%m%d"), local.hour
        return {rand for rand, blocks in self._blocks.items()
                if any(bd == d and h0 <= hour <= h1 for bd, h0, h1 in blocks)}
