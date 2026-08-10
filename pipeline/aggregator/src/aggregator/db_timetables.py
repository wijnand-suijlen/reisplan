"""Germany realtime source: DB Timetables API (station-based, IRIS XML).

DE has no official nationwide GTFS-RT. Instead we poll /fchg/{eva} ("full changes") for
a fixed station set built by spike/s10: tier A hubs every ~5 min, tier B round-robin
every ~25 min. fchg entries usually carry only the changed time (ct), so planned times
come from cached /plan hour slices, joined on the IRIS stop id.

IRIS stop ids are "{tripid}-{startdatetime}-{stopindex}" and identical across stations,
so consecutive polled stops of one train give per-segment delay deltas — the same model
as the GTFS-RT sources. The static refinement table spreads express jumps over the
intermediate edges, and Opslag deduplicates repeated identical observations.

Only events within a window around now count (PLAN.md, venstersemantiek): fchg also
contains predictions hours ahead and stale changes hours back.
"""

import heapq
import json
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from .config import EVA_STATIONS
from .delta import SegObs, StopObs
from .statisch import Statisch, segment_id

log = logging.getLogger("aggregator")

BASE = "https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1"
BERLIN = ZoneInfo("Europe/Berlin")

TIER_INTERVAL_S = {"A": 300, "B": 1500}
POLL_TICK_S = 10             # how often the main loop offers us a slot
BATCH_SIZE = 4               # stations per tick, to smooth the request rate
REQUEST_BUDGET_PER_MIN = 45  # plan limit is 60; keep headroom
EVENT_WINDOW_PAST_S = 2700
EVENT_WINDOW_FUTURE_S = 900
PLAN_SLICE_TTL_S = 3 * 3600
TRIP_STATE_TTL_S = 4 * 3600
MAX_SANE_DELTA_S = 7200
MAX_BACKOFF_S = 900


def parse_iris_time(value: str) -> int | None:
    """IRIS times are 'yymmddHHMM' in local German time."""
    try:
        return int(datetime.strptime(value, "%y%m%d%H%M").replace(tzinfo=BERLIN).timestamp())
    except ValueError:
        return None


@dataclass
class PlanStop:
    pt_arr: int | None
    pt_dep: int | None


@dataclass
class _StopState:
    cluster: str
    delay_s: int
    event_ts: int
    seen: float


class DbTimetablesSource:
    """Drop-in peer of main.Bron for sources with cfg.kind == "db-timetables"."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.volgende = 0.0
        self.incidenten: list[dict] = []  # no alert mapping yet (blockades: PLAN.md pt 7)
        self.laatste_ok: float | None = None
        self.backoff = POLL_TICK_S
        self.session = requests.Session()
        self.session.headers.update(cfg.headers)
        self.request_log: list[float] = []       # sliding-window rate limiter
        self.plan: dict[str, dict[str, PlanStop]] = {}   # eva -> stop_id -> PlanStop
        self.plan_slices: dict[tuple, float] = {}        # (eva, date, hour) -> fetched at
        self.trip_labels: dict[str, str] = {}            # trip head -> "ICE 228"
        self.trip_state: dict[str, dict[int, _StopState]] = {}
        self.stations: dict[str, dict] = {}
        self.queue: list[tuple[float, str]] = []         # (due, eva)
        self.last_prune = 0.0
        self._load_stations()

    def _load_stations(self) -> None:
        if not EVA_STATIONS.exists():
            log.warning("de: %s missing — run spike/s10_station_eva_map.py first", EVA_STATIONS)
            return
        entries = json.loads(EVA_STATIONS.read_text())["stations"]
        now = time.time()
        for i, st in enumerate(entries):
            self.stations[st["eva"]] = st
            interval = TIER_INTERVAL_S[st["tier"]]
            heapq.heappush(self.queue, (now + (i * 37) % interval, st["eva"]))
        tier_a = sum(1 for s in entries if s["tier"] == "A")
        log.info("de: %d stations loaded (%d tier A)", len(entries), tier_a)

    # -- HTTP ---------------------------------------------------------------

    def _budget_left(self) -> int:
        cutoff = time.time() - 60
        self.request_log = [t for t in self.request_log if t > cutoff]
        return REQUEST_BUDGET_PER_MIN - len(self.request_log)

    def _get(self, path: str) -> bytes | None:
        self.request_log.append(time.time())
        r = self.session.get(f"{BASE}{path}", timeout=25)
        if r.status_code in (404, 410):
            return None
        r.raise_for_status()
        return r.content

    # -- plan slices (planned times + train labels) --------------------------

    def _ensure_plan(self, eva: str, now: float) -> None:
        local = datetime.fromtimestamp(now, BERLIN)
        # previous hour too: events up to EVENT_WINDOW_PAST_S back need their planned time
        for slot in (local - timedelta(hours=1), local, local + timedelta(hours=1)):
            key = (eva, slot.strftime("%y%m%d"), slot.strftime("%H"))
            if key in self.plan_slices or self._budget_left() <= 1:
                continue
            self.plan_slices[key] = now
            data = self._get(f"/plan/{key[0]}/{key[1]}/{key[2]}")
            if data is None:
                continue
            target = self.plan.setdefault(eva, {})
            for sid, plan_stop, label in self._parse_plan(data):
                target[sid] = plan_stop
                if label:
                    self.trip_labels[sid.rpartition("-")[0]] = label

    @staticmethod
    def _parse_plan(data: bytes):
        for s in ET.fromstring(data).iter("s"):
            sid = s.get("id")
            if not sid:
                continue
            tl = s.find("tl")
            label = f"{tl.get('c')} {tl.get('n')}" if tl is not None and tl.get("n") else None
            ar, dp = s.find("ar"), s.find("dp")
            yield sid, PlanStop(
                parse_iris_time(ar.get("pt")) if ar is not None and ar.get("pt") else None,
                parse_iris_time(dp.get("pt")) if dp is not None and dp.get("pt") else None,
            ), label

    # -- fchg processing ------------------------------------------------------

    def _process_station(self, eva: str, now: float, statisch: Statisch):
        seg_obs: list[SegObs] = []
        stop_obs: list[StopObs] = []
        data = self._get(f"/fchg/{eva}")
        if data is None:
            return seg_obs, stop_obs
        self._ensure_plan(eva, now)
        plan = self.plan.get(eva, {})
        cluster = self.stations[eva]["cluster_id"]
        for s in ET.fromstring(data).iter("s"):
            sid = s.get("id") or ""
            head, _, idx_str = sid.rpartition("-")
            if not idx_str.isdigit():
                continue
            start = head.rpartition("-")[2]  # trip start "yymmddHHMM" -> service date
            service_date = f"20{start[:6]}" if len(start) == 10 and start.isdigit() else ""
            delay = event_ts = None
            plan_stop = plan.get(sid)
            for kind in ("ar", "dp"):  # prefer arrival
                el = s.find(kind)
                if el is None or el.get("cs") == "c" or not el.get("ct"):
                    continue
                ct = parse_iris_time(el.get("ct"))
                pt = (parse_iris_time(el.get("pt")) if el.get("pt") else None) or (
                    plan_stop and (plan_stop.pt_arr if kind == "ar" else plan_stop.pt_dep))
                if ct is None or pt is None:
                    continue
                delay, event_ts = ct - pt, pt
                break
            if delay is None or not (
                now - EVENT_WINDOW_PAST_S <= event_ts <= now + EVENT_WINDOW_FUTURE_S
            ):
                continue
            trip_ref = self.trip_labels.get(head, f"iris:{head}")
            stop_obs.append(StopObs(trip_ref, cluster, delay, service_date))
            state = self.trip_state.setdefault(head, {})
            state[int(idx_str)] = _StopState(cluster, delay, event_ts, now)
            self._emit_deltas(head, int(idx_str), statisch, seg_obs)
        return seg_obs, stop_obs

    def _emit_deltas(self, head: str, idx: int, statisch: Statisch, seg_obs: list) -> None:
        """Pair the updated stop with its nearest known neighbours along the trip."""
        state = self.trip_state[head]
        known = sorted(state)
        pos = known.index(idx)
        pairs = []
        if pos > 0:
            pairs.append((known[pos - 1], idx))
        if pos + 1 < len(known):
            pairs.append((idx, known[pos + 1]))
        trip_ref = self.trip_labels.get(head, f"iris:{head}")
        for a, b in pairs:
            s_from, s_to = state[a], state[b]
            delta = s_to.delay_s - s_from.delay_s
            if s_from.cluster == s_to.cluster or abs(delta) > MAX_SANE_DELTA_S:
                continue
            for fine, fraction in statisch.verfijn(segment_id(s_from.cluster, s_to.cluster)):
                seg_obs.append(SegObs(fine, trip_ref, round(delta * fraction)))

    def _prune(self, now: float) -> None:
        if now - self.last_prune < 600:
            return
        self.last_prune = now
        for key, fetched in list(self.plan_slices.items()):
            if now - fetched > PLAN_SLICE_TTL_S:
                del self.plan_slices[key]
        # plan entries and labels age out with their trips; rebuild coarsely via TTL
        for head, stops in list(self.trip_state.items()):
            if all(now - st.seen > TRIP_STATE_TTL_S for st in stops.values()):
                del self.trip_state[head]
                self.trip_labels.pop(head, None)
        for eva, entries in self.plan.items():
            if len(entries) > 20_000:  # safety valve; plan ids are not individually dated
                self.plan[eva] = {}

    # -- main-loop interface ---------------------------------------------------

    def poll(self, statisch: Statisch, opslag) -> None:
        now = time.time()
        if not self.stations:
            self.volgende = now + 300
            return
        try:
            seg_all: list[SegObs] = []
            stop_all: list[StopObs] = []
            handled = 0
            while (self.queue and handled < BATCH_SIZE
                   and self.queue[0][0] <= now and self._budget_left() > 3):
                _, eva = heapq.heappop(self.queue)
                seg, stops = self._process_station(eva, now, statisch)
                seg_all += seg
                stop_all += stops
                handled += 1
                interval = TIER_INTERVAL_S[self.stations[eva]["tier"]]
                heapq.heappush(self.queue, (now + interval, eva))
            if handled:
                changed = opslag.bewaar(self.cfg.land, seg_all, stop_all)
                self.laatste_ok = now
                log.info("de: %d stations, %d segment obs, %d changed stop obs",
                         handled, len(seg_all), changed)
            self._prune(now)
            self.backoff = POLL_TICK_S
        except Exception as e:
            log.warning("de: poll failed: %s — backoff %ds", e, self.backoff)
            self.backoff = min(self.backoff * 2, MAX_BACKOFF_S)
        self.volgende = time.time() + self.backoff

    def dekking(self) -> dict:
        if not self.cfg.enabled:
            return {"status": self.cfg.status}
        if not self.stations or self.laatste_ok is None:
            return {"status": "wacht"}
        return {"status": "deels", "age_s": int(time.time() - self.laatste_ok)}
