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


def verwerk_tripupdates(pb_bytes: bytes, feed_prefix: str, statisch: Statisch):
    """Returns (seg_obs, stop_obs, cancels, passages).

    cancels: (fine segment, trip, service_date) triples for cancelled trips and
    skipped-stop stretches; passages: fine segments with a *realized* passage (event
    time in the past, or no time given — most feeds only carry near-term updates).
    Both feed the blockade tracker; a passage is what clears a blockade. Cancels are
    also persisted (opslag.bewaar_cancels) so the inspection page can show them.
    """
    feed = parse_feed(pb_bytes)
    nu = time.time()
    seg_obs: list[SegObs] = []
    stop_obs: list[StopObs] = []
    cancels: list[tuple[str, str, str]] = []
    passages: list[str] = []
    vandaag = time.strftime("%Y%m%d", time.gmtime())
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
            stop_obs.append(StopObs(trip_id, cluster, d, service_date))
        for (c1, d1, _t1), (c2, d2, t2) in zip(expliciet, expliciet[1:]):
            if c1 != c2:
                delta = d2 - d1
                gerealiseerd = t2 is None or t2 <= nu
                # expresse-sprong uitsmeren over de fijne baanvakken (naar rato van lengte)
                for fijn, fractie in statisch.verfijn(segment_id(c1, c2)):
                    seg_obs.append(SegObs(fijn, trip_id, round(delta * fractie)))
                    if gerealiseerd:
                        passages.append(fijn)
    return seg_obs, stop_obs, cancels, passages
