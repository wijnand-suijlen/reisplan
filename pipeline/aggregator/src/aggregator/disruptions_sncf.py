"""SNCF Navitia disruptions -> edge groups (map improvement 8, signal C).

Only NO_SERVICE disruptions whose application period covers now. The since/until
query keeps the result to currently-active disruptions (the unfiltered endpoint
serves thousands, mostly past). Impacted stops arrive per trip; consecutive runs of
"deleted" stops form the closed chain. Stop ids carry the UIC number
("stop_point:SNCF:87686006") which maps via clusters.uic."""

import os
import re
from datetime import datetime, timedelta

from .disruptions import DisruptionSource, EdgeGroup, fmt_local, log
from .planned_closures import TZ
from .statisch import Statisch

PAGE_COUNT = 200
MAX_PAGES = 10
UIC_RE = re.compile(r"(\d{7,8})$")


class SncfDisruptionsSource(DisruptionSource):
    src = "sncf"
    interval_s = 600

    def _fetch(self, statisch: Statisch) -> list[EdgeGroup]:
        base = os.environ.get("SNCF_ENDPOINT", "https://api.sncf.com/v1").rstrip("/")
        auth = (os.environ["SNCF_API_KEY"], "")
        now = datetime.now(TZ)
        params = {
            "count": PAGE_COUNT,
            "since": now.strftime("%Y%m%dT%H%M%S"),
            "until": (now + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S"),
        }
        groups: list[EdgeGroup] = []
        for page in range(MAX_PAGES):
            data = self._get(f"{base}/coverage/sncf/disruptions",
                             params={**params, "start_page": page}, auth=auth).json()
            disruptions = data.get("disruptions") or []
            for disruption in disruptions:
                if (disruption.get("severity") or {}).get("effect") != "NO_SERVICE":
                    continue
                group = _edge_group(disruption, statisch)
                if group:
                    groups.append(group)
            pagination = data.get("pagination") or {}
            seen = (pagination.get("start_page", page) + 1) * pagination.get("items_per_page", PAGE_COUNT)
            if seen >= pagination.get("total_result", 0) or not disruptions:
                break
        else:
            log.warning("sncf: paginacap (%d) bereikt — disruptions afgekapt", MAX_PAGES)
        return groups


def _edge_group(disruption: dict, statisch: Statisch) -> EdgeGroup | None:
    edges: set[str] = set()
    for obj in disruption.get("impacted_objects") or []:
        chain: list[str] = []
        for stop in obj.get("impacted_stops") or []:
            if stop.get("stop_time_effect") != "deleted":
                # a run of deleted stops ends: map it and start over
                _extend(edges, chain, statisch)
                chain = []
                continue
            m = UIC_RE.search((stop.get("stop_point") or {}).get("id") or "")
            if m:
                cluster = statisch.cluster_by_uic.get(m.group(1)) \
                    or statisch.cluster_by_uic.get(m.group(1)[:-1])
                if cluster:
                    chain.append(cluster)
        _extend(edges, chain, statisch)
    if not edges:
        return None
    until = None
    periods = disruption.get("application_periods") or []
    ends = [p.get("end") for p in periods if p.get("end")]
    if ends:
        try:
            until = fmt_local(datetime.strptime(max(ends), "%Y%m%dT%H%M%S").replace(tzinfo=TZ))
        except ValueError:
            pass
    messages = disruption.get("messages") or []
    txt = (messages[0].get("text") or "")[:150] if messages else None
    # trip-level cancellations prove a hindered service, not a closed track:
    # the GTFS-RT blockade tracker (>= 2 trips) is the "closed" signal for FR
    return ("sncf", "reduced", until, txt, edges)


def _extend(edges: set[str], chain: list[str], statisch: Statisch) -> None:
    if len(chain) < 2:
        return
    found, unmapped = statisch.chain_edges(chain)
    edges |= found
    for seg in unmapped:
        log.info("sncf: stoppaar niet op randen te mappen: %s", seg)
