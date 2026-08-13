"""Poll-loop: haalt per bron de GTFS-RT-feeds op, verwerkt ze en schrijft elke minuut
een snapshot. Per-bron exponentiële backoff bij fouten; If-Modified-Since waar mogelijk."""

import logging
import os
import time

import requests

from . import archive, inspection, r2
from .alert_closures import edge_groups_from_alerts
from .alerts import verwerk_alerts
from .blockades import BlockadeTracker
from .config import WEB_DATA, bronnen
from .db_timetables import DbTimetablesSource
from .delta import parse_feed, verwerk_tripupdates
from .disruptions_ns import NsDisruptionsSource
from .disruptions_sncf import SncfDisruptionsSource
from .opslag import Opslag
from .planned_closures import PlannedClosures
from .snapshot import bouw_snapshot, schrijf_snapshot
from .statisch import Statisch

log = logging.getLogger("aggregator")
MAX_BACKOFF_S = 900


class Bron:
    def __init__(self, cfg):
        self.cfg = cfg
        self.volgende = 0.0
        self.volgende_alerts = 0.0
        self.backoff = cfg.interval_s
        self.laatste_ok: float | None = None
        self.last_modified: dict[str, str] = {}
        self.incidenten: list[dict] = []
        self.alert_groups: list = []  # werkzaamheden uit alerts (BE), zie alert_closures

    def poll(self, statisch: Statisch, opslag: Opslag, blokkades: BlockadeTracker) -> None:
        cfg = self.cfg
        try:
            if cfg.tu_url:
                pb = self._haal(cfg.tu_url)
                if pb is not None:
                    seg_obs, stop_obs, cancels, passages = verwerk_tripupdates(
                        pb, cfg.feed_prefix, statisch)
                    nieuw = opslag.bewaar(cfg.land, seg_obs, stop_obs)
                    nu = time.time()
                    blokkades.note_cancels(cancels, nu)
                    blokkades.note_passages(passages, nu)
                    log.info("%s: %d segment-obs, %d gewijzigde stop-obs, %d cancel-obs",
                             cfg.land, len(seg_obs), nieuw, len(cancels))
            if cfg.alerts_url and time.time() >= self.volgende_alerts:
                pb = self._haal(cfg.alerts_url, cfg.alerts_headers)
                if pb is not None:
                    self.incidenten = verwerk_alerts(pb, cfg.feed_prefix, cfg.land, statisch)
                    self.alert_groups = edge_groups_from_alerts(parse_feed(pb), cfg.land, statisch)
                    log.info("%s: %d alerts, %d werkzaamheden-groepen",
                             cfg.land, len(self.incidenten), len(self.alert_groups))
                self.volgende_alerts = time.time() + (cfg.alerts_interval_s or cfg.interval_s)
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
    blokkades = BlockadeTracker()
    actief = [DbTimetablesSource(cfg) if cfg.kind == "db-timetables" else Bron(cfg)
              for cfg in bronnen()]
    closures = PlannedClosures()
    # disruption feeds (werkzaamheden/storingen) — aan zodra hun key in .env staat
    disrupties = []
    if os.environ.get("NS_API_KEY"):
        disrupties.append(NsDisruptionsSource())
    if os.environ.get("SNCF_API_KEY"):
        disrupties.append(SncfDisruptionsSource())
    log.info(
        "gestart; bronnen: %s; disruptions: %s; R2-upload: %s",
        ", ".join(f"{b.cfg.land}={'aan' if b.cfg.enabled else b.cfg.status}" for b in actief),
        ", ".join(d.src for d in disrupties) or "geen",
        "aan" if r2.actief() else "uit",
    )
    if r2.actief() and (WEB_DATA / "segments.geojson").exists():
        try:
            r2.upload("segments.geojson", (WEB_DATA / "segments.geojson").read_bytes(),
                      "application/geo+json", cache_s=3600)
            log.info("segments.geojson naar R2 geüpload")
        except Exception as e:
            log.warning("R2-upload segments mislukt: %s", e)
    volgende_snapshot = 0.0
    while True:
        nu = time.time()
        for bron in actief:
            if bron.cfg.enabled and nu >= bron.volgende:
                bron.poll(statisch, opslag, blokkades)
        for disruptie in disrupties:
            if nu >= disruptie.volgende:
                disruptie.poll(statisch)
        if nu >= volgende_snapshot:
            dekking = {b.cfg.land: b.dekking() for b in actief}
            incidenten = [i for b in actief for i in b.incidenten]
            # per getekende rand aggregeren over álle segmenten die eroverheen lopen
            rand_deltas: dict[str, list] = {}
            rand_trips: dict[str, set] = {}
            for segment, (deltas, trips) in opslag.venster_ruw(1800).items():
                for rand in statisch.randen(segment):
                    rand_deltas.setdefault(rand, []).extend(deltas)
                    rand_trips.setdefault(rand, set()).update(trips)
            venster = {}
            for rand, deltas in rand_deltas.items():
                deltas.sort()
                p90 = deltas[min(len(deltas) - 1, int(0.9 * len(deltas)))]
                venster[rand] = (p90, len(rand_trips[rand]))
            geblokkeerd = sorted({rand for seg in blokkades.blocked_segments(nu)
                                  for rand in statisch.randen(seg)})
            # werkzaamheden: disruption-feeds + BE-alerts; het generieke baseline-
            # signaal vult aan waar geen feed iets meldt (rijkere info wint)
            werk = [g for d in disrupties for g in d.groups]
            werk += [g for b in actief for g in getattr(b, "alert_groups", [])]
            gedekt = {rand for *_, randen in werk for rand in randen}
            plan_randen = closures.active_edges(nu) - gedekt
            if plan_randen:
                # nul geplande treinen tegen de baseline = volledige sluiting
                werk.insert(0, ("plan", "closed", None, None, sorted(plan_randen)))
            snap = bouw_snapshot(dekking, venster, incidenten, geblokkeerd, werk)
            data = schrijf_snapshot(snap)
            try:
                r2.upload("snapshot.json", data, "application/json")
            except Exception as e:
                log.warning("R2-upload snapshot mislukt: %s", e)
            log.info("snapshot: %d segmenten, %d incidenten, %d versperd, %d werk-randen, %d bytes",
                     len(snap["seg"]), len(snap["inc"]), len(geblokkeerd),
                     len({r for w in snap["wrk"] for r in w[4]}), len(data))
            volgende_snapshot = nu + 60
        archive.run_if_due()
        inspection.run_if_due(statisch, opslag)
        time.sleep(1)


if __name__ == "__main__":
    main()
