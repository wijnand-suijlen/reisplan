"""Delta-vertraging per segment uit een GTFS-RT TripUpdates-feed.

Alleen paren van opeenvolgende stop_time_updates met een EXPLICIETE delay tellen mee:
GTFS-RT propageert een delay impliciet naar volgende stops, en impliciete paren zijn
per definitie delta 0 — die zouden het beeld vervuilen.
"""

import json
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


def _delay(stu) -> int | None:
    if stu.HasField("arrival") and stu.arrival.HasField("delay"):
        return stu.arrival.delay
    if stu.HasField("departure") and stu.departure.HasField("delay"):
        return stu.departure.delay
    return None


def verwerk_tripupdates(pb_bytes: bytes, feed_prefix: str, statisch: Statisch):
    feed = parse_feed(pb_bytes)
    seg_obs: list[SegObs] = []
    stop_obs: list[StopObs] = []
    for ent in feed.entity:
        if not ent.HasField("trip_update"):
            continue
        tu = ent.trip_update
        trip_id = tu.trip.trip_id
        expliciet = []  # (cluster, delay)
        for stu in tu.stop_time_update:
            d = _delay(stu)
            if d is None or not stu.stop_id:
                continue
            cluster = statisch.cluster(feed_prefix, stu.stop_id)
            if cluster is None:
                continue
            expliciet.append((cluster, d))
            stop_obs.append(StopObs(trip_id, cluster, d))
        for (c1, d1), (c2, d2) in zip(expliciet, expliciet[1:]):
            if c1 != c2:
                delta = d2 - d1
                # expresse-sprong uitsmeren over de fijne baanvakken (naar rato van lengte)
                for fijn, fractie in statisch.verfijn(segment_id(c1, c2)):
                    seg_obs.append(SegObs(fijn, trip_id, round(delta * fractie)))
    return seg_obs, stop_obs
