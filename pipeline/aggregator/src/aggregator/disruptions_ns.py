"""NS Reisinformatie API v3 disruptions -> edge groups (map improvement 8, signal B).

Planned works and disruptions with their section as an ordered station list. Station
codes map via stations.stop_code (feed nl); uicCode is the fallback and also catches
foreign stations of cross-border sections. Pairs entirely outside NL are skipped:
sections like "Amsterdam - München - Innsbruck" describe one affected (night) train,
not a closed corridor, and would paint half of Germany orange.

Severity comes from the situation text of the timespans that are valid *right now*
(a disruption record can be active while tonight's actual closure has not started):
- "tussen X en Y rijden er bussen" / "... geen treinen"  -> those subsections are
  "closed" (red on the map); X/Y are matched by station name, and if that fails the
  whole section counts as closed — over-marking beats under-marking here.
- "internationale dienstregeling (is) aangepast"          -> "intl": only
  international trains are hindered, domestic service runs (blue on the map).
- anything else ("rijden er minder treinen", "aangepaste dienstregeling", ...)
  -> "reduced": track open, thinned service (orange on the map)."""

import os
import re
from datetime import datetime, timezone

from .disruptions import DisruptionSource, EdgeGroup, fmt_local, log
from .statisch import Statisch, normalize_name

URL = "https://gateway.apiportal.ns.nl/reisinformatie-api/api/v3/disruptions"
TYPES = {"MAINTENANCE", "DISRUPTION", "CALAMITY"}
USER_AGENT = "reisplan-aggregator/0.1 (hobbyproject)"

CLOSED_RE = re.compile(r"[Tt]ussen (.+?) en (.+?) rijden er (?:geen treinen|(?:\S+ )*bussen)")
INTL_RE = re.compile(r"internationale dienstregeling", re.IGNORECASE)


class NsDisruptionsSource(DisruptionSource):
    src = "ns"
    interval_s = 300

    def _fetch(self, statisch: Statisch) -> list[EdgeGroup]:
        r = self._get(URL, params={"isActive": "true"},
                      headers={"Ocp-Apim-Subscription-Key": os.environ["NS_API_KEY"],
                               "User-Agent": USER_AGENT})
        now = datetime.now(timezone.utc)
        groups: list[EdgeGroup] = []
        for disruption in r.json():
            if disruption.get("type") not in TYPES or not disruption.get("isActive"):
                continue
            situations = _current_situations(disruption, now)
            if not situations:
                continue  # actieve melding, maar geen tijdvak dat nú geldt
            closed_pairs = [m for s in situations for m in CLOSED_RE.findall(s)]
            intl = any(INTL_RE.search(s) for s in situations)

            section_edges = _section_edges(disruption, statisch)
            closed_edges: set[str] = set()
            for name_a, name_b in closed_pairs:
                pair = [statisch.cluster_by_name.get(normalize_name(n)) for n in (name_a, name_b)]
                if all(pair):
                    found, _ = statisch.chain_edges(pair)
                    closed_edges |= found
                else:
                    # onherleidbaar deeltraject: hele sectie als dicht rekenen
                    log.info("ns: deeltraject %r – %r niet op naam te mappen", name_a, name_b)
                    closed_edges |= section_edges
            until = _until(disruption)
            txt = (disruption.get("title") or "")[:150]
            if closed_edges & section_edges:
                groups.append(("ns", "closed", until, txt, closed_edges & section_edges))
            rest = section_edges - closed_edges
            if rest:
                groups.append(("ns", "intl" if intl else "reduced", until, txt, rest))
        return groups


def _current_situations(disruption: dict, now: datetime) -> list[str]:
    """Situation texts of timespans covering now; top-level period as fallback."""
    timespans = disruption.get("timespans") or []
    texts = []
    for ts in timespans:
        if _covers(ts.get("start"), ts.get("end"), now):
            label = ((ts.get("situation") or {}).get("label") or "").strip()
            if label:
                texts.append(label)
    if not timespans and _covers(disruption.get("start"), disruption.get("end"), now):
        texts.append(disruption.get("title") or "")
    return texts


def _covers(start: str | None, end: str | None, now: datetime) -> bool:
    try:
        if start and datetime.fromisoformat(start) > now:
            return False
        if end and datetime.fromisoformat(end) < now:
            return False
    except ValueError:
        return False
    return bool(start or end)


def _section_edges(disruption: dict, statisch: Statisch) -> set[str]:
    edges: set[str] = set()
    for section in disruption.get("publicationSections") or []:
        stations = (section.get("section") or {}).get("stations") or []
        chain: list[str] = []
        in_nl: list[bool] = []
        for st in stations:
            cluster = (statisch.cluster_by_ns_code.get((st.get("stationCode") or "").lower())
                       or statisch.cluster_by_uic.get(st.get("uicCode") or ""))
            if cluster:
                chain.append(cluster)
                in_nl.append(st.get("countryCode") == "NL")
        # keep only pairs touching NL (see module docstring)
        for i in range(len(chain) - 1):
            if in_nl[i] or in_nl[i + 1]:
                pair_edges, unmapped = statisch.chain_edges(chain[i:i + 2])
                edges |= pair_edges
                for seg in unmapped:
                    log.info("ns: sectiepaar niet op randen te mappen: %s", seg)
    return edges


def _until(disruption: dict) -> str | None:
    end = disruption.get("end")
    if not end:
        return None
    try:
        return fmt_local(datetime.fromisoformat(end))
    except ValueError:
        return None
