"""Delta-vertraging per segment uit een GTFS-RT TripUpdates-feed.

Alleen paren van opeenvolgende stop_time_updates met een EXPLICIETE delay tellen mee:
GTFS-RT propageert een delay impliciet naar volgende stops, en impliciete paren zijn
per definitie delta 0 — die zouden het beeld vervuilen.
"""

import json
import time
from dataclasses import dataclass

from google.protobuf import json_format
from google.transit import gtfs_realtime_pb2

from .statisch import Statisch, segment_id


def _ontlong(obj):
    """BE serialiseert int64 als JavaScript-Long-object {low, high, unsigned} — terug naar int."""
    if isinstance(obj, dict):
        if set(obj) >= {"low", "high"} and isinstance(obj.get("low"), int):
            return obj["low"] + (obj["high"] << 32)
        return {k: _ontlong(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ontlong(v) for v in obj]
    return obj


def parse_feed(data: bytes) -> gtfs_realtime_pb2.FeedMessage:
    """GTFS-RT als protobuf óf als JSON-codering (BE levert alleen JSON, met Long-objecten)."""
    feed = gtfs_realtime_pb2.FeedMessage()
    if data[:1] in (b"{", b" "):
        json_format.ParseDict(_ontlong(json.loads(data)), feed, ignore_unknown_fields=True)
    else:
        feed.ParseFromString(data)
    return feed


@dataclass
class SegObs:
    segment: str
    trip_id: str
    delta_s: int


@dataclass
class StopObs:
    trip_id: str
    cluster: str
    delay_s: int
    service_date: str = ""  # "YYYYMMDD"; keeps days apart in the punctuality log


def _delay(stu) -> int | None:
    if stu.HasField("arrival") and stu.arrival.HasField("delay"):
        return stu.arrival.delay
    if stu.HasField("departure") and stu.departure.HasField("delay"):
        return stu.departure.delay
    return None


def _event_time(stu) -> int | None:
    if stu.HasField("arrival") and stu.arrival.HasField("time"):
        return stu.arrival.time
    if stu.HasField("departure") and stu.departure.HasField("time"):
        return stu.departure.time
    return None


def verwerk_tripupdates(pb_bytes: bytes, feed_prefix: str, statisch: Statisch,
                        closed_edges: frozenset[str] = frozenset()):
    """Returns (seg_obs, stop_obs, cancels, passages).

    cancels: (fine segment, trip, service_date) triples for cancelled trips and
    skipped-stop stretches; passages: fine segments with a *realized* passage (event
    time in the past, or no time given — most feeds only carry near-term updates).
    Both feed the blockade tracker; a passage is what clears a blockade. Cancels are
    also persisted (opslag.bewaar_cancels) so the inspection page can show them.

    closed_edges: drawn edges an operator's disruption feed reports closed. A closed
    stretch is taken as closed even when the trip update still lists the full
    service: on 14 Sep 2026 NS had "no trains between Putten and Nunspeet" while
    OVapi kept SPR 5669 scheduled through Ermelo and Harderwijk to Zwolle, on time,
    and the map coloured the closure green. A fine segment lying entirely on closed
    edges counts as cancelled, and a stop with closed segments on every side as not
    served.
    """
    feed = parse_feed(pb_bytes)
    nu = time.time()
    seg_obs: list[SegObs] = []
    stop_obs: list[StopObs] = []
    cancels: list[tuple[str, str, str]] = []
    passages: list[str] = []
    vandaag = time.strftime("%Y%m%d", time.gmtime())

    def closed(fijn: str) -> bool:
        edges = statisch.randen(fijn)
        return bool(edges) and all(edge in closed_edges for edge in edges)

    for ent in feed.entity:
        if not ent.HasField("trip_update"):
            continue
        tu = ent.trip_update
        trip_id = tu.trip.trip_id
        service_date = tu.trip.start_date or vandaag  # start_date is not set by every feed
        if tu.trip.schedule_relationship == tu.trip.CANCELED:
            # cancelled trips usually come without stop list -> static route lookup
            for fijn in statisch.trip_segments(feed_prefix, trip_id):
                cancels.append((fijn, trip_id, service_date))
            continue
        expliciet = []  # (cluster, delay, event_time)
        vorige_geskipt: str | None = None
        for stu in tu.stop_time_update:
            cluster = statisch.cluster(feed_prefix, stu.stop_id) if stu.stop_id else None
            if cluster is None:
                continue
            if stu.schedule_relationship == stu.SKIPPED:
                if vorige_geskipt and vorige_geskipt != cluster:
                    for fijn, _ in statisch.verfijn(segment_id(vorige_geskipt, cluster)):
                        cancels.append((fijn, trip_id, service_date))
                vorige_geskipt = cluster
                continue
            vorige_geskipt = None
            d = _delay(stu)
            if d is None:
                continue
            expliciet.append((cluster, d, _event_time(stu)))
        # per hop between explicit stops: None for a same-cluster hop, else whether
        # the whole hop runs over closed edges
        hop_closed: list[bool | None] = []
        for (c1, d1, _t1), (c2, d2, t2) in zip(expliciet, expliciet[1:]):
            if c1 == c2:
                hop_closed.append(None)
                continue
            delta = d2 - d1
            gerealiseerd = t2 is None or t2 <= nu
            # expresse-sprong uitsmeren over de fijne baanvakken (naar rato van lengte)
            fijne = statisch.verfijn(segment_id(c1, c2))
            hop_closed.append(bool(closed_edges) and all(closed(fijn) for fijn, _ in fijne))
            for fijn, fractie in fijne:
                if closed_edges and closed(fijn):
                    cancels.append((fijn, trip_id, service_date))
                    continue
                seg_obs.append(SegObs(fijn, trip_id, round(delta * fractie)))
                if gerealiseerd:
                    passages.append(fijn)
        for i, (cluster, d, _t) in enumerate(expliciet):
            around = [h for h in (hop_closed[i - 1] if i > 0 else None,
                                  hop_closed[i] if i < len(hop_closed) else None)
                      if h is not None]
            if around and all(around):
                continue  # between two closed stretches: this train does not call here
            stop_obs.append(StopObs(trip_id, cluster, d, service_date))
    return seg_obs, stop_obs, cancels, passages
