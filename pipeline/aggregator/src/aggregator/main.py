"""Poll-loop: haalt per bron de GTFS-RT-feeds op, verwerkt ze en schrijft elke minuut
een snapshot. Per-bron exponentiële backoff bij fouten; If-Modified-Since waar mogelijk."""

import logging
import time

import requests

from .alerts import verwerk_alerts
from .config import bronnen
from .delta import verwerk_tripupdates
from .opslag import Opslag
from .snapshot import bouw_snapshot, schrijf_snapshot
from .statisch import Statisch

log = logging.getLogger("aggregator")
MAX_BACKOFF_S = 900


class Bron:
    def __init__(self, cfg):
        self.cfg = cfg
        self.volgende = 0.0
        self.backoff = cfg.interval_s
        self.laatste_ok: float | None = None
        self.last_modified: dict[str, str] = {}
        self.incidenten: list[dict] = []

    def poll(self, statisch: Statisch, opslag: Opslag) -> None:
        cfg = self.cfg
        try:
            if cfg.tu_url:
                pb = self._haal(cfg.tu_url)
                if pb is not None:
                    seg_obs, stop_obs = verwerk_tripupdates(pb, cfg.feed_prefix, statisch)
                    nieuw = opslag.bewaar(cfg.land, seg_obs, stop_obs)
                    log.info("%s: %d segment-obs, %d gewijzigde stop-obs", cfg.land, len(seg_obs), nieuw)
            if cfg.alerts_url:
                pb = self._haal(cfg.alerts_url, cfg.alerts_headers)
                if pb is not None:
                    self.incidenten = verwerk_alerts(pb, cfg.feed_prefix, cfg.land, statisch)
                    log.info("%s: %d alerts", cfg.land, len(self.incidenten))
            self.laatste_ok = time.time()
            self.backoff = cfg.interval_s
        except Exception as e:
            log.warning("%s: poll mislukt: %s — backoff %ds", cfg.land, e, self.backoff)
            self.backoff = min(self.backoff * 2, MAX_BACKOFF_S)
        self.volgende = time.time() + self.backoff

    def _haal(self, url: str, headers_override: dict | None = None) -> bytes | None:
        headers = dict(headers_override if headers_override is not None else self.cfg.headers)
        if url in self.last_modified:
            headers["If-Modified-Since"] = self.last_modified[url]
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 304:
            return None
        r.raise_for_status()
        if "Last-Modified" in r.headers:
            self.last_modified[url] = r.headers["Last-Modified"]
        return r.content

    def dekking(self) -> dict:
        if not self.cfg.enabled:
            return {"status": self.cfg.status}
        if self.laatste_ok is None:
            return {"status": "wacht"}
        return {"status": "ok", "age_s": int(time.time() - self.laatste_ok)}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    statisch = Statisch()
    opslag = Opslag()
    actief = [Bron(cfg) for cfg in bronnen()]
    log.info(
        "gestart; bronnen: %s",
        ", ".join(f"{b.cfg.land}={'aan' if b.cfg.enabled else b.cfg.status}" for b in actief),
    )
    volgende_snapshot = 0.0
    while True:
        nu = time.time()
        for bron in actief:
            if bron.cfg.enabled and nu >= bron.volgende:
                bron.poll(statisch, opslag)
        if nu >= volgende_snapshot:
            dekking = {b.cfg.land: b.dekking() for b in actief}
            incidenten = [i for b in actief for i in b.incidenten]
            snap = bouw_snapshot(dekking, opslag.venster(1800), incidenten)
            grootte = schrijf_snapshot(snap)
            log.info("snapshot: %d segmenten, %d incidenten, %d bytes", len(snap["seg"]), len(snap["inc"]), grootte)
            volgende_snapshot = nu + 60
        time.sleep(1)


if __name__ == "__main__":
    main()
