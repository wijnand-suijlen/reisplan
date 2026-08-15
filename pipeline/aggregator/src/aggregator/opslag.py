"""SQLite-opslag: dit archief ís de punctualiteitscollector (PLAN.md §3.1).

seg_obs: delta-vertraging per segment-passage (append bij verandering).
stop_obs2: vertragingshistorie per trip/dienstdag/cluster (append bij verandering) —
de laatste rij per sleutel is de definitieve vertraging, de basis voor fase 2.
cancel_obs: eerste waarneming van een annulering per trip/dienstdag/fijn segment —
voedt de inspectiepagina; het blokkade-signaal op de kaart blijft in-memory
(BlockadeTracker, met passage-reset) en leest deze tabel niet.
stop_obs (v1) is vervangen: die overschreef per trip en had geen dienstdatum, waardoor
elke dag de vorige wiste; de tabel blijft alleen als historische data staan.
"""

import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone

from .config import RT_ARCHIEF

log = logging.getLogger("aggregator")

CACHE_MAX = 500_000          # prune/warn trigger, not a hard cap: the key space
                             # is naturally bounded by ~one service day per feed
SEG_UNSEEN_PRUNE_S = 3 * 3600
SEG_WARM_LOOKBACK_S = 30 * 3600  # feeds carry the whole service day, incl. overnight
PRUNE_INTERVAL_S = 600


def _date_floor() -> str:
    """Oldest service_date a feed may still carry: the current service day,
    which rolls over ~8h after midnight UTC so overnight trains keep their
    yesterday-dated keys until they are done."""
    return (datetime.now(timezone.utc) - timedelta(hours=8)).strftime("%Y%m%d")


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
               CREATE TABLE IF NOT EXISTS stop_obs2 (
                 ts INT, country TEXT, trip_id TEXT, service_date TEXT,
                 cluster TEXT, delay_s INT);
               CREATE INDEX IF NOT EXISTS stop_obs2_date ON stop_obs2 (service_date);
               CREATE TABLE IF NOT EXISTS cancel_obs (
                 ts INT, country TEXT, trip_id TEXT, service_date TEXT,
                 segment TEXT);
               CREATE INDEX IF NOT EXISTS cancel_obs_date ON cancel_obs (service_date);
            """
        )
        # dedup state: last stored value per key. Losing this state is not
        # harmless: the next poll then re-logs everything the feed still carries
        # (the whole service day) with ts=now — phantom observations that shadow
        # the real timestamps everywhere downstream (map window, "last seen",
        # edge passages). Hence: warmed from the DB at startup, and pruned
        # selectively instead of cleared.
        self._laatste: dict[tuple, int] = {}
        self._laatste_seg: dict[tuple, tuple[int, int]] = {}  # key -> (delta_s, last_seen_ts)
        self._cancel_gezien: set[tuple] = set()  # (country, trip, service_date, segment)
        self._next_prune = 0.0
        self._warm_caches()

    def _warm_caches(self) -> None:
        t0 = time.monotonic()
        now = int(time.time())
        date_floor = _date_floor()
        # bare value next to max(ts) = SQLite's latest-row-wins semantics
        for country, trip_id, service_date, cluster, delay_s, _ in self.db.execute(
                """SELECT country, trip_id, service_date, cluster, delay_s, max(ts)
                   FROM stop_obs2 WHERE service_date >= ?
                   GROUP BY country, trip_id, service_date, cluster""", (date_floor,)):
            self._laatste[(country, trip_id, service_date, cluster)] = delay_s
        # capped at the freshest keys so a backlog can never balloon startup memory
        for land, trip_id, segment, delta_s, _ in self.db.execute(
                """SELECT land, trip_id, segment, delta_s, max(ts)
                   FROM seg_obs WHERE ts >= ?
                   GROUP BY land, trip_id, segment
                   ORDER BY max(ts) DESC LIMIT ?""",
                (now - SEG_WARM_LOOKBACK_S, CACHE_MAX)):
            # seen=now: only entries that stay absent from the feed may age out
            self._laatste_seg[(land, trip_id, segment)] = (delta_s, now)
        # same phantom concern as above: without warming, a restart would re-log
        # every cancellation the feed still carries with ts=now
        self._cancel_gezien = set(self.db.execute(
            """SELECT DISTINCT country, trip_id, service_date, segment
               FROM cancel_obs WHERE service_date >= ?""", (date_floor,)))
        log.info("dedup-cache gewarmd: %d stop, %d seg, %d cancel (%.1fs)",
                 len(self._laatste), len(self._laatste_seg),
                 len(self._cancel_gezien), time.monotonic() - t0)

    def _prune(self, now: int) -> None:
        """Drop only entries the feeds can no longer send: stop keys of finished
        service days, seg keys unseen in any poll for hours. Never clear."""
        date_floor = _date_floor()
        for key in [k for k in self._laatste
                    if len(k[2]) == 8 and k[2] < date_floor]:
            del self._laatste[key]
        self._cancel_gezien = {k for k in self._cancel_gezien
                               if len(k[2]) != 8 or k[2] >= date_floor}
        unseen_floor = now - SEG_UNSEEN_PRUNE_S
        for key in [k for k, (_, seen) in self._laatste_seg.items()
                    if seen < unseen_floor]:
            del self._laatste_seg[key]
        if len(self._laatste_seg) > CACHE_MAX or len(self._laatste) > CACHE_MAX:
            log.warning("dedup-cache boven %d na pruning: %d stop, %d seg",
                        CACHE_MAX, len(self._laatste), len(self._laatste_seg))

    def bewaar(self, land: str, seg_obs, stop_obs) -> int:
        """Alleen gewijzigde waarden opslaan — elke poll herhaalt dezelfde STU's,
        en ongewijzigd elke minuut appenden zou ~75M rijen/dag worden."""
        ts = int(time.time())
        nieuw = 0
        if ((len(self._laatste_seg) > CACHE_MAX or len(self._laatste) > CACHE_MAX)
                and ts >= self._next_prune):
            self._prune(ts)
            self._next_prune = ts + PRUNE_INTERVAL_S
        vers = []
        for o in seg_obs:
            sleutel = (land, o.trip_id, o.segment)
            cur = self._laatste_seg.get(sleutel)
            if cur is None or cur[0] != o.delta_s:
                vers.append((ts, land, o.segment, o.trip_id, o.delta_s))
            self._laatste_seg[sleutel] = (o.delta_s, ts)
        with self.db:
            self.db.executemany("INSERT INTO seg_obs VALUES (?, ?, ?, ?, ?)", vers)
            for o in stop_obs:
                sleutel = (land, o.trip_id, o.service_date, o.cluster)
                if self._laatste.get(sleutel) != o.delay_s:
                    self._laatste[sleutel] = o.delay_s
                    self.db.execute(
                        "INSERT INTO stop_obs2 VALUES (?, ?, ?, ?, ?, ?)",
                        (ts, land, o.trip_id, o.service_date, o.cluster, o.delay_s),
                    )
                    nieuw += 1
        return nieuw

    def bewaar_cancels(self, land: str, cancels: list[tuple[str, str, str]]) -> int:
        """Log de éérste waarneming per (trip, dienstdag, segment): feeds herhalen
        een annulering elke poll, en anders dan bij vertragingen verandert de
        waarde niet — één rij per sleutel volstaat voor de inspectie."""
        ts = int(time.time())
        vers = []
        for segment, trip_id, service_date in cancels:
            sleutel = (land, trip_id, service_date, segment)
            if sleutel not in self._cancel_gezien:
                self._cancel_gezien.add(sleutel)
                vers.append((ts, land, trip_id, service_date, segment))
        if vers:
            with self.db:
                self.db.executemany(
                    "INSERT INTO cancel_obs VALUES (?, ?, ?, ?, ?)", vers)
        return len(vers)

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
