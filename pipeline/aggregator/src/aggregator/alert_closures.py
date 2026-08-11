"""NMBS service alerts -> edge groups (map improvement 8, signal D).

The Belgian alerts feed marks works (cause CONSTRUCTION, effect NO_SERVICE) but its
informed_entity is agency-only: no stops, no routes, no period (verified live
2026-08-11). The route is only in the header text ("Mol - Hasselt"), in nl and fr.
So we parse every language variant, split on " - ", and match the normalized names
against the Belgian clusters — the fr variant usually matches clusters.naam
("Liège-Guillemins"), the nl one ("Luik-Guillemins") usually does not. Endpoints
that are no station ("Franse grens") or single-station alerts are skipped: point
incidents are already on the map via `inc`."""

from google.transit import gtfs_realtime_pb2

from .alerts import TAALVOORKEUR, _tekst
from .disruptions import EdgeGroup, log
from .statisch import Statisch, normalize_name


def edge_groups_from_alerts(feed, land: str, statisch: Statisch) -> list[EdgeGroup]:
    """Called on the already-parsed alerts FeedMessage of a GTFS-RT source."""
    if land != "be":
        return []  # CH projection is a separate improvement (list items 2/7c)
    groups: list[EdgeGroup] = []
    for ent in feed.entity:
        if not ent.HasField("alert"):
            continue
        alert = ent.alert
        if gtfs_realtime_pb2.Alert.Effect.Name(alert.effect) != "NO_SERVICE":
            continue
        chain = _best_chain(alert.header_text, statisch)
        if len(chain) < 2:
            log.info("be: alert-traject niet te mappen: %r", _tekst(alert.header_text)[:80])
            continue
        edges, unmapped = statisch.chain_edges(chain)
        for seg in unmapped:
            log.info("be: trajectpaar niet op randen te mappen: %s", seg)
        if edges:
            # effect NO_SERVICE: volledige sluiting van het traject
            groups.append(("be", "closed", None, _tekst(alert.header_text)[:150], edges))
    return groups


def _best_chain(header_text, statisch: Statisch) -> list[str]:
    """The language variant that matches the most Belgian station names wins."""
    best: list[str] = []
    variants = sorted(header_text.translation,
                      key=lambda t: TAALVOORKEUR.index(t.language) if t.language in TAALVOORKEUR else 9)
    for variant in variants:
        chain = [cluster for part in variant.text.split(" - ")
                 if (cluster := statisch.be_cluster_by_name.get(normalize_name(part)))]
        if len(chain) > len(best):
            best = chain
    return best
