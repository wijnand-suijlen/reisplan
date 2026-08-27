"""Heap diagnostics for the 1 GB VM: where does the aggregator's memory go?

Written for a concrete question (aug 2026): RSS climbs to ~900 MB of anonymous
memory within hours of a restart, the box swap-thrashes and the minute snapshot
degrades to a p90 of 8 minutes. The process memory map ruled out the cheap
explanations — the glibc main arena is only 130 MB, there are no 64 MB per-thread
arenas, and the DuckDB wheel is plain glibc malloc, not jemalloc. What is left is
203 large anonymous mappings, the signature of big *live* allocations. The map
knows sizes but not types, so the rest has to be measured from inside.

Stage A (always on, ~free): one line every REISPLAN_DIAG_INTERVAL_S with RSS/swap,
glibc mallinfo2, DuckDB's own accounting and the entry count of every known cache.
Read as a series over hours it shows which number climbs along with RSS.

Stage B (on demand): SIGUSR1 dumps a heap histogram by type, the largest live
containers and a sampled deep size per named cache; SIGUSR2 runs malloc_trim(0)
with RSS before and after, which settles allocator retention versus live objects
for good. Both signals only set a flag — the work happens in the maintenance
thread, so a dump never stalls the poll loop.

    ssh google_micro 'pkill -USR1 -f "bin/aggregator$"'   # heap dump
    ssh google_micro 'pkill -USR2 -f "bin/aggregator$"'   # malloc_trim

The $ anchor matters: it selects the python process and not the `uv run
aggregator` parent, whose default action for SIGUSR1/2 is to terminate.

Two blind spots, both deliberate. gc.get_objects() only sees GC-tracked objects,
so str/bytes/int leaves are missing from the histogram — the sampled deep sizes
per cache compensate, since those attribute the leaves to the container holding
them. And those deep sizes are estimates from a sample, counting shared or
interned values once per reference, so read them as an upper bound.
"""

import ctypes
import gc
import logging
import os
import signal
import sys
import threading
import time
from itertools import islice

from . import inspection

log = logging.getLogger("aggregator")

INTERVAL_S = int(os.environ.get("REISPLAN_DIAG_INTERVAL_S", "600"))
SAMPLE_N = 2000          # items sampled per container for the deep-size estimate
SAMPLE_DEPTH = 3         # nesting levels followed while sampling
BIG_BYTES = 1 << 20      # a container this big (shallow) is worth naming
TOP_TYPES = 20
TOP_CONTAINERS = 15

_next_sample = 0.0
_dump_wanted = threading.Event()
_trim_wanted = threading.Event()


class _MallInfo2(ctypes.Structure):
    _fields_ = [(name, ctypes.c_size_t) for name in (
        "arena", "ordblks", "smblks", "hblks", "hblkhd", "usmblks",
        "fsmblks", "uordblks", "fordblks", "keepcost")]


_libc_handle = None


def _libc():
    """glibc with mallinfo2/malloc_trim bound, or None where unavailable."""
    global _libc_handle
    if _libc_handle is None:
        try:
            lib = ctypes.CDLL("libc.so.6")
            lib.mallinfo2.restype = _MallInfo2
            lib.mallinfo2.argtypes = []
            lib.malloc_trim.restype = ctypes.c_int
            lib.malloc_trim.argtypes = [ctypes.c_size_t]
            _libc_handle = lib
        except (OSError, AttributeError) as e:
            log.warning("diag: libc unavailable (%s) — no mallinfo/trim", e)
            _libc_handle = False
    return _libc_handle or None


def _mb(value: float) -> str:
    return f"{value / (1 << 20):.0f}M"


def _proc_mem() -> dict[str, int]:
    """VmRSS/VmSwap in bytes from /proc/self/status — no page-table walk, unlike
    smaps_rollup, so this stays cheap enough for a timer on a thrashing box."""
    out: dict[str, int] = {}
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith(("VmRSS:", "VmSwap:", "VmSize:")):
                    key, _, value = line.partition(":")
                    out[key] = int(value.split()[0]) * 1024
    except OSError:
        pass
    return out


def _mallinfo() -> dict[str, int] | None:
    lib = _libc()
    if lib is None:
        return None
    try:
        mi = lib.mallinfo2()
    except Exception:
        return None
    return {"arena": mi.arena, "mmap": mi.hblkhd, "live": mi.uordblks,
            "free": mi.fordblks, "keepcost": mi.keepcost}


def _duckdb_mem(con) -> tuple[int, int] | None:
    try:
        used, tmp = con.execute(
            "SELECT coalesce(sum(memory_usage_bytes), 0),"
            " coalesce(sum(temporary_storage_bytes), 0) FROM duckdb_memory()"
        ).fetchone()
        return int(used), int(tmp)
    except Exception:
        return None


def _caches(statisch, opslag, blokkades) -> dict[str, object]:
    """Entry counts of every container that could plausibly grow. Each probe is
    guarded: the poll loop mutates these dicts concurrently, and a diagnostic
    must never be the thing that kills the maintenance thread."""
    probes = {
        "seg": lambda: len(opslag._laatste_seg),
        "stop": opslag._n_stop,
        "cancel": opslag._n_cancel,
        "stopdays": lambda: len(opslag._laatste),
        "tripseg": lambda: len(statisch._trip_segments_cache),
        "meta": lambda: len(inspection._meta_cache),
        "blocked": lambda: len(blokkades._cancels),
        "blockedtrips": lambda: sum(map(len, blokkades._cancels.values())),
        "stops": lambda: len(statisch.cluster_van_stop),
        "clusters": lambda: len(statisch.clusters),
        "randen": lambda: len(statisch.segment_randen),
        "verfijn": lambda: len(statisch.verfijning),
        "names": lambda: len(statisch.cluster_by_name),
        "adj": lambda: len(statisch._adjacency or ()),
    }
    out: dict[str, object] = {}
    for name, probe in probes.items():
        try:
            out[name] = probe()
        except Exception:
            out[name] = "?"
    return out


def _sample(statisch, opslag, blokkades, con) -> None:
    parts = []
    mem = _proc_mem()
    if mem:
        parts.append(f"rss={_mb(mem.get('VmRSS', 0))} swap={_mb(mem.get('VmSwap', 0))}")
    mi = _mallinfo()
    if mi:
        parts.append("glibc arena={} mmap={} live={} free={}".format(
            _mb(mi["arena"]), _mb(mi["mmap"]), _mb(mi["live"]), _mb(mi["free"])))
    duck = _duckdb_mem(con)
    if duck:
        parts.append(f"duckdb={_mb(duck[0])} tmp={_mb(duck[1])}")
    parts.append(f"pyblocks={sys.getallocatedblocks()}")
    parts.append("caches " + " ".join(
        f"{k}={v}" for k, v in _caches(statisch, opslag, blokkades).items()))
    log.info("diag: %s", " | ".join(parts))


def _estimate_size(obj, depth: int = SAMPLE_DEPTH) -> int:
    """Deep size from a bounded sample: the container itself plus the mean size
    of SAMPLE_N entries times its length. Sampling avoids both a full walk and
    the id()-set a precise walk would need — that set alone would be hundreds of
    megabytes here, which is exactly the problem being measured."""
    try:
        base = sys.getsizeof(obj)
    except Exception:
        return 0
    if depth <= 0:
        return base
    try:
        if isinstance(obj, dict):
            n = len(obj)
            if not n:
                return base
            items = list(islice(obj.items(), SAMPLE_N))
            taken = sum(_estimate_size(k, depth - 1) + _estimate_size(v, depth - 1)
                        for k, v in items)
            return base + round(taken / len(items) * n)
        if isinstance(obj, (list, tuple, set, frozenset)):
            n = len(obj)
            if not n:
                return base
            items = list(islice(iter(obj), SAMPLE_N))
            taken = sum(_estimate_size(v, depth - 1) for v in items)
            return base + round(taken / len(items) * n)
    except (RuntimeError, TypeError):
        return base  # mutated under us; the shallow size is still honest
    return base


def _describe(obj) -> str:
    kind = type(obj).__name__
    try:
        size = len(obj)
    except Exception:
        return kind
    head = ""
    try:
        if isinstance(obj, dict):
            keys = [repr(k)[:40] for k in islice(obj, 3)]
            head = " keys=" + ",".join(keys)
        elif isinstance(obj, (list, tuple, set, frozenset)):
            head = " head=" + ",".join(repr(v)[:40] for v in islice(iter(obj), 2))
    except (RuntimeError, TypeError):
        head = " (mutating)"
    return f"{kind} len={size}{head}"


def _heap_dump(statisch, opslag, blokkades) -> None:
    t0 = time.monotonic()
    before = _proc_mem()
    gc.collect()
    objects = gc.get_objects()
    by_type: dict[str, list[int]] = {}
    big: list[tuple[int, str]] = []
    total = 0
    for obj in objects:
        try:
            size = sys.getsizeof(obj)
        except Exception:
            continue
        total += size
        entry = by_type.setdefault(type(obj).__name__, [0, 0])
        entry[0] += 1
        entry[1] += size
        if size >= BIG_BYTES:
            big.append((size, _describe(obj)))
    n_objects = len(objects)
    del objects

    log.info("diag: heap dump — %d tracked objects, %s shallow, rss=%s",
             n_objects, _mb(total), _mb(before.get("VmRSS", 0)))
    for name, (count, size) in sorted(
            by_type.items(), key=lambda kv: -kv[1][1])[:TOP_TYPES]:
        log.info("diag:   type %-24s n=%-9d %s", name, count, _mb(size))
    for size, description in sorted(big, key=lambda item: -item[0])[:TOP_CONTAINERS]:
        log.info("diag:   big  %8s  %s", _mb(size), description)

    named = {
        "opslag._laatste": getattr(opslag, "_laatste", None),
        "opslag._laatste_seg": getattr(opslag, "_laatste_seg", None),
        "opslag._cancel_gezien": getattr(opslag, "_cancel_gezien", None),
        "statisch.cluster_van_stop": getattr(statisch, "cluster_van_stop", None),
        "statisch.cluster_by_name": getattr(statisch, "cluster_by_name", None),
        "statisch.clusters": getattr(statisch, "clusters", None),
        "statisch.segment_randen": getattr(statisch, "segment_randen", None),
        "statisch.verfijning": getattr(statisch, "verfijning", None),
        "statisch._trip_segments_cache": getattr(statisch, "_trip_segments_cache", None),
        "statisch._adjacency": getattr(statisch, "_adjacency", None),
        "inspection._meta_cache": inspection._meta_cache,
        "blokkades._cancels": getattr(blokkades, "_cancels", None),
    }
    for name, obj in named.items():
        if obj is None:
            continue
        try:
            length = len(obj)
        except Exception:
            length = -1
        log.info("diag:   cache %-30s len=%-9d ~%s (sampled)",
                 name, length, _mb(_estimate_size(obj)))
    log.info("diag: heap dump done in %.1fs", time.monotonic() - t0)


def _trim() -> None:
    lib = _libc()
    if lib is None:
        log.warning("diag: malloc_trim unavailable")
        return
    before, mi_before = _proc_mem(), _mallinfo()
    rc = lib.malloc_trim(0)
    after, mi_after = _proc_mem(), _mallinfo()
    log.info("diag: malloc_trim rc=%d rss %s -> %s, swap %s -> %s", rc,
             _mb(before.get("VmRSS", 0)), _mb(after.get("VmRSS", 0)),
             _mb(before.get("VmSwap", 0)), _mb(after.get("VmSwap", 0)))
    if mi_before and mi_after:
        log.info("diag: malloc_trim arena %s -> %s, free %s -> %s, live %s -> %s",
                 _mb(mi_before["arena"]), _mb(mi_after["arena"]),
                 _mb(mi_before["free"]), _mb(mi_after["free"]),
                 _mb(mi_before["live"]), _mb(mi_after["live"]))


def install_handlers() -> None:
    """Must run on the main thread (signal.signal's rule). The handlers only set
    a flag; run_if_due does the work on the maintenance thread."""
    for sig, event, what in ((signal.SIGUSR1, _dump_wanted, "heap dump"),
                             (signal.SIGUSR2, _trim_wanted, "malloc_trim")):
        try:
            signal.signal(sig, lambda *_, _e=event: _e.set())
        except (ValueError, OSError, AttributeError) as e:
            log.warning("diag: no handler for %s (%s): %s", what, sig, e)


def run_if_due(statisch, opslag, blokkades, con) -> None:
    global _next_sample
    now = time.time()
    if now >= _next_sample:
        _next_sample = now + INTERVAL_S
        try:
            _sample(statisch, opslag, blokkades, con)
        except Exception as e:
            log.warning("diag: sample failed: %s", e)
    if _dump_wanted.is_set():
        _dump_wanted.clear()
        try:
            _heap_dump(statisch, opslag, blokkades)
        except Exception as e:
            log.warning("diag: heap dump failed: %s", e)
    if _trim_wanted.is_set():
        _trim_wanted.clear()
        try:
            _trim()
        except Exception as e:
            log.warning("diag: malloc_trim failed: %s", e)
