"""Shared plumbing for disruption feeds (NS, SNCF): polling with backoff, and the
edge-group shape the snapshot consumes.

An edge group is one disruption mapped onto the drawn map:
    (src, sev, until, txt, edges)
with src a short source tag ("ns", "sncf", "be", "plan"); sev the severity:
"closed" (no trains at all — planned full closure), "reduced" (adapted/thinned
service, track open) or "intl" (only international trains hindered, domestic
service unaffected); until a local "YYYY-MM-DD HH:MM" string or None; txt a short
human description or None; and edges the set of drawn-edge ids. These feeds carry
no per-segment delay data, so they deliberately live outside the Bron/dekking
machinery of main.py."""

import logging
import time
from datetime import datetime

import requests

from .planned_closures import TZ
from .statisch import Statisch

log = logging.getLogger("aggregator")
MAX_BACKOFF_S = 3600

EdgeGroup = tuple[str, str, str | None, str | None, set[str]]


def fmt_local(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M")


class DisruptionSource:
    src = "?"
    interval_s = 600

    def __init__(self) -> None:
        self.volgende = 0.0
        self.backoff = self.interval_s
        self.groups: list[EdgeGroup] = []

    def poll(self, statisch: Statisch) -> None:
        try:
            self.groups = self._fetch(statisch)
            n_edges = len({e for *_, edges in self.groups for e in edges})
            log.info("%s: %d werkzaamheden-groepen, %d randen", self.src, len(self.groups), n_edges)
            self.backoff = self.interval_s
        except Exception as e:
            log.warning("%s: disruptions-poll mislukt: %s — backoff %ds", self.src, e, self.backoff)
            self.backoff = min(self.backoff * 2, MAX_BACKOFF_S)
        self.volgende = time.time() + self.backoff

    def _fetch(self, statisch: Statisch) -> list[EdgeGroup]:
        raise NotImplementedError

    def _get(self, url: str, **kwargs) -> requests.Response:
        r = requests.get(url, timeout=30, **kwargs)
        r.raise_for_status()
        return r
