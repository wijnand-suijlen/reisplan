"""SQLite-opslag: dit archief ís de punctualiteitscollector (PLAN.md §3.1).

seg_obs: delta-vertraging per segment-passage; stop_obs: laatst bekende vertraging per
trip/cluster (alleen appenden bij verandering, om groei te beperken).
"""

import sqlite3
import time

from .config import RT_ARCHIEF


class Opslag:
    def __init__(self) -> None:
        RT_ARCHIEF.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(RT_ARCHIEF / "observaties.sqlite"))
        self.db.executescript(
            """CREATE TABLE IF NOT EXISTS seg_obs (
                 ts INT, land TEXT, segment TEXT, trip_id TEXT, delta_s INT);
               CREATE INDEX IF NOT EXISTS seg_obs_ts ON seg_obs (ts);
               CREATE TABLE IF NOT EXISTS stop_obs (
                 ts INT, land TEXT, trip_id TEXT, cluster TEXT, delay_s INT,
                 PRIMARY KEY (land, trip_id, cluster));
            """
        )
        self._laatste: dict[tuple, int] = {}
        self._laatste_seg: dict[tuple, int] = {}

    def bewaar(self, land: str, seg_obs, stop_obs) -> int:
        """Alleen gewijzigde waarden opslaan — elke poll herhaalt dezelfde STU's,
        en ongewijzigd elke minuut appenden zou ~75M rijen/dag worden."""
        ts = int(time.time())
        nieuw = 0
        if len(self._laatste_seg) > 500_000 or len(self._laatste) > 500_000:
            self._laatste_seg.clear()
            self._laatste.clear()  # hooguit wat dubbele rijen na een reset
        vers = []
        for o in seg_obs:
            sleutel = (land, o.trip_id, o.segment)
            if self._laatste_seg.get(sleutel) != o.delta_s:
                self._laatste_seg[sleutel] = o.delta_s
                vers.append((ts, land, o.segment, o.trip_id, o.delta_s))
        with self.db:
            self.db.executemany("INSERT INTO seg_obs VALUES (?, ?, ?, ?, ?)", vers)
            for o in stop_obs:
                sleutel = (land, o.trip_id, o.cluster)
                if self._laatste.get(sleutel) != o.delay_s:
                    self._laatste[sleutel] = o.delay_s
                    self.db.execute(
                        "INSERT OR REPLACE INTO stop_obs VALUES (?, ?, ?, ?, ?)",
                        (ts, land, o.trip_id, o.cluster, o.delay_s),
                    )
                    nieuw += 1
        return nieuw

    def venster_ruw(self, seconden: int = 1800):
        """Per segment over het venster: (lijst delta's, set trips) — de aggregatie
        naar getekende randen gebeurt in main (per rand over álle segmenten erop)."""
        sinds = int(time.time()) - seconden
        rows = self.db.execute(
            """SELECT segment, delta_s, trip_id FROM seg_obs WHERE ts >= ?""", (sinds,)
        ).fetchall()
        per_seg: dict[str, tuple[list, set]] = {}
        for segment, delta, trip in rows:
            deltas, trips = per_seg.setdefault(segment, ([], set()))
            deltas.append(delta)
            trips.add(trip)
        return per_seg
