"""Track de-facto track blockades (PLAN.md, vertragingskaart verbeterpunt 7).

A segment counts as blocked when at least MIN_CANCELLED_TRIPS distinct trips have been
reported cancelled or skipped over it within WINDOW_S, and nothing has demonstrably
passed since: one *realized* passage wipes the segment's cancellation history and so
clears the dash. Predictions never clear a blockade — reopening requires evidence that
the track actually carries trains again. The state is in-memory only; after an
aggregator restart the picture rebuilds within one polling cycle.
"""

WINDOW_S = 5400          # cancellations older than this stop counting (quiet lines!)
MIN_CANCELLED_TRIPS = 2  # one cancelled train is an incident, two start to be a pattern


class BlockadeTracker:
    def __init__(self) -> None:
        self._cancels: dict[str, dict[str, float]] = {}  # segment -> trip -> last seen

    def note_cancels(self, items: list[tuple[str, str, str]], now: float) -> None:
        """items: (segment, trip, service_date); the date only matters for the
        persisted cancel log (opslag), the blockade signal ignores it."""
        for segment, trip, _service_date in items:
            self._cancels.setdefault(segment, {})[trip] = now

    def note_passages(self, segments: list[str], now: float) -> None:
        for segment in segments:
            self._cancels.pop(segment, None)

    def blocked_segments(self, now: float) -> set[str]:
        blocked = set()
        for segment, trips in list(self._cancels.items()):
            for trip, ts in list(trips.items()):
                if now - ts > WINDOW_S:
                    del trips[trip]
            if not trips:
                del self._cancels[segment]
            elif len(trips) >= MIN_CANCELLED_TRIPS:
                blocked.add(segment)
        return blocked
