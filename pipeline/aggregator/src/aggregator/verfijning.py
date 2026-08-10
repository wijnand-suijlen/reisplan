"""Segmentverfijning: expresse-sprongen afbeelden op de fijnste keten van baanvakken.

Een segment A->D (bv. Parijs->Lyon nonstop) wordt gedecomponeerd in de keten
A->B->C->D als die keten bestaat uit strikt kortere segmenten die andere treinen
daadwerkelijk rijden, en de ketenlengte de hemelsbrede sprong niet te veel
overschrijdt (anders plakken we een HSL-sprong op een parallelle klassieke lijn).

Gebruikt door maak_segmenten (kaart tekent alleen "blad"-segmenten) en door de
aggregator (delta-vertraging naar rato van afstand over de bladen verdelen).
"""

import heapq
import math
from collections import defaultdict

ONEINDIG = float("inf")


def _afstand_m(c1, c2) -> float:
    (lat1, lon1), (lat2, lon2) = c1, c2
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bouw_verfijning(paren, coords, alpha=1.3, slack_m=3000.0, min_m=8000.0):
    """paren: iterable van (a, b)-clusterparen; coords: cluster -> (lat, lon).

    Retourneert dict (a, b) -> [((c, d), fractie), ...]: de bladsegmenten waarover
    dit segment wordt uitgesmeerd, met lengte-fracties (sommeert tot 1)."""
    lengte = {}
    buren = defaultdict(list)
    for a, b in paren:
        if a not in coords or b not in coords:
            continue
        s = (a, b)
        l = max(_afstand_m(coords[a], coords[b]), 1.0)
        lengte[s] = l
        buren[a].append((b, l, s))
        buren[b].append((a, l, s))

    decomp = {}
    for s in sorted(lengte, key=lengte.get):  # kort -> lang: expansies van kortere zijn al bekend
        l = lengte[s]
        if l < min_m:
            continue
        a, b = s
        pad = _astar(a, b, buren, coords, seg_len=l, limiet=alpha * l + slack_m, verbod=s)
        if pad and len(pad) >= 2:
            decomp[s] = pad

    verfijning = {}

    def expand(s):
        if s in verfijning:
            return verfijning[s]
        bladen = []
        for e in decomp.get(s, []):
            bladen.extend(expand(e))
        verfijning[s] = bladen or [s]
        return verfijning[s]

    resultaat = {}
    for s in lengte:
        bladen = expand(s)
        tot = sum(lengte[e] for e in bladen)
        resultaat[s] = [(e, lengte[e] / tot) for e in bladen]
    return resultaat


def _astar(start, doel, buren, coords, seg_len, limiet, verbod):
    doelco = coords[doel]

    def h(n):
        return _afstand_m(coords[n], doelco)

    beste = {start: 0.0}
    herkomst = {}
    pq = [(h(start), 0.0, start)]
    while pq:
        f, g, n = heapq.heappop(pq)
        if n == doel:
            pad = []
            while n != start:
                n, seg = herkomst[n]
                pad.append(seg)
            return list(reversed(pad))
        if g > beste.get(n, ONEINDIG):
            continue
        for nbr, l, seg in buren[n]:
            if seg == verbod or l >= seg_len:  # alleen strikt kortere randen gebruiken
                continue
            ng = g + l
            if ng < beste.get(nbr, ONEINDIG) and ng + h(nbr) <= limiet:
                beste[nbr] = ng
                herkomst[nbr] = (n, seg)
                heapq.heappush(pq, (ng + h(nbr), ng, nbr))
    return None
