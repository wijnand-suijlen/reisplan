"""Service alerts -> incidenten met GTFS-RT cause/effect en een kaartpositie."""

from google.transit import gtfs_realtime_pb2

from .delta import parse_feed
from .statisch import Statisch

TAALVOORKEUR = ["nl", "fr", "de", "en"]


def _tekst(vert) -> str:
    per_taal = {t.language: t.text for t in vert.translation}
    for taal in TAALVOORKEUR:
        if taal in per_taal:
            return per_taal[taal]
    return next(iter(per_taal.values()), "")


def verwerk_alerts(pb_bytes: bytes, feed_prefix: str, land: str, statisch: Statisch) -> list[dict]:
    feed = parse_feed(pb_bytes)
    incidenten = []
    for ent in feed.entity:
        if not ent.HasField("alert"):
            continue
        a = ent.alert
        pos = None
        cluster_id = None
        for ie in a.informed_entity:
            if ie.stop_id:
                cid = statisch.cluster(feed_prefix, ie.stop_id)
                if cid and statisch.clusters[cid].lat is not None:
                    c = statisch.clusters[cid]
                    pos, cluster_id = [round(c.lon, 4), round(c.lat, 4)], cid
                    break
        incidenten.append(
            {
                "land": land,
                "cause": gtfs_realtime_pb2.Alert.Cause.Name(a.cause),
                "effect": gtfs_realtime_pb2.Alert.Effect.Name(a.effect),
                "txt": _tekst(a.header_text)[:200],
                "pos": pos,
                "cluster": cluster_id,
            }
        )
    return incidenten
