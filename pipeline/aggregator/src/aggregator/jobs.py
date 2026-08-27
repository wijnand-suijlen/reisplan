"""Run the heavy maintenance builds in short-lived child processes.

Measured 2026-08-27 with diagnostics.py: the aggregator's footprint climbed from
523 to 636 MB in six hours while the live Python heap *shrank* — the shallow
histogram stayed flat (95 -> 98 MB), the named caches went from ~216 to ~173 MB,
and the dedup caches lost 394k entries between them. DuckDB held steady at 86 MB
and glibc's live bytes barely moved. So there is no leak. What grows is the
high-water mark: the inspection build allocates a large transient working set
every few minutes, and once it is freed neither obmalloc nor glibc can return
those arenas, because a handful of long-lived blocks stay scattered through them.
Every peak raises the floor. malloc_trim recovered 40 MB of 645 — the rest sits
in obmalloc arenas that glibc cannot even see.

The remedy is not to hunt an object but to stop making the peak in this address
space. Both builds now run as `python -m aggregator.jobs <name>`: the child's
working set dies with the child, and the parent's heap stays flat. Scheduling
(when is a build due) stays in the parent — inspection.due() and archive.due() —
so the child does the work once and exits.

The child inherits stdout/stderr, so its log lines land in the journal under the
same unit and read exactly as before. It also inherits the environment, which is
how REISPLAN_AGG_DUCKDB_MEM and the R2 credentials reach it; it calls laad_env()
anyway so it works when started by hand:

    cd ~/reisplan && uv run python -m aggregator.jobs inspection
"""

import logging
import subprocess
import sys
import time

from .config import ROOT, laad_env

log = logging.getLogger("aggregator")

# Generous: these bound a hung child, they are not a performance target. An
# inspection build takes 1-3 minutes; an archive run that backfills many days
# after downtime is the reason archive's cap is an hour.
TIMEOUTS = {"inspection": 900, "archive": 3600}


def run(name: str) -> bool:
    """Run one job to completion in a child process. Returns True on a clean
    exit; every failure is logged and swallowed, because the maintenance thread
    must survive anything a build does."""
    t0 = time.monotonic()
    try:
        proc = subprocess.run([sys.executable, "-m", "aggregator.jobs", name],
                              cwd=str(ROOT), timeout=TIMEOUTS[name])
    except subprocess.TimeoutExpired:
        log.warning("job %s: killed after %ds", name, TIMEOUTS[name])
        return False
    except Exception as e:
        log.warning("job %s: could not start: %s", name, e)
        return False
    took = time.monotonic() - t0
    if proc.returncode != 0:
        log.warning("job %s: exited %d after %.0fs", name, proc.returncode, took)
        return False
    log.info("job %s: done in %.0fs", name, took)
    return True


def _run_inspection() -> None:
    from . import inspection
    from .opslag import reader_connection
    from .statisch import Statisch

    statisch = Statisch()
    # single-threaded here, so the connection needs no cursor of its own
    inspection.build(statisch, reader_connection(), statisch.con)


def _run_archive() -> None:
    from . import archive

    archive.run()


def main(argv: list[str]) -> int:
    """Child entry point. Exceptions are deliberately not caught: a traceback on
    stderr lands in the journal, and the non-zero exit tells the parent."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    laad_env()
    jobs = {"inspection": _run_inspection, "archive": _run_archive}
    if len(argv) != 2 or argv[1] not in jobs:
        print(f"usage: python -m aggregator.jobs {{{'|'.join(jobs)}}}", file=sys.stderr)
        return 2
    jobs[argv[1]]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
