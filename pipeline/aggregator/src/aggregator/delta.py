"""Delta-vertraging per segment uit een GTFS-RT TripUpdates-feed.

Alleen paren van opeenvolgende stop_time_updates met een EXPLICIETE delay tellen mee:
GTFS-RT propageert een delay impliciet naar volgende stops, en impliciete paren zijn
per definitie delta 0 — die zouden het beeld vervuilen.
"""

from dataclasses import dataclass

from google.transit import gtfs_realtime_pb2

from .statisch import Statisch, segment_id


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
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(pb_bytes)
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
                seg_obs.append(SegObs(segment_id(c1, c2), trip_id, d2 - d1))
    return seg_obs, stop_obs
