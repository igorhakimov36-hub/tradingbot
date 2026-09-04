from datetime import datetime
from typing import Any, Callable

from backtesting.point_in_time import get_available_data_sorted


class ReplayEngine:
    """
    Replays historical market data one record at a time.

    At every step, the strategy can only access data
    that was available at or before the current replay time.

    Complexity: get_visible_history() is O(log n) per call via binary
    search over `self.records` (sorted once here, in __init__, and
    never mutated afterward) - a full replay of n steps is therefore
    O(n log n) total, not O(n^2). Previously, get_visible_history()
    rescanned the full records list from scratch on every single step
    (O(n) per call, O(n^2) total) - this is the specific bottleneck an
    earlier phase of this project measured producing a ~180x slowdown
    for a 12x larger dataset. Sprint 1 of docs/phase5_strategic_roadmap_decision.md
    fixed this without changing any observable behavior - see that
    document and tests/test_replay_engine_performance.py for the
    equivalence proof and benchmark.
    """

    def __init__(
        self,
        records: list[dict[str, Any]],
        timestamp_key: str = "timestamp"
    ):
        self.timestamp_key = timestamp_key
        self.records = sorted(
            records,
            key=lambda record: record[self.timestamp_key]
        )

        self.current_index = 0
        self.current_time: datetime | None = None


    def reset(self) -> None:
        """
        Reset the replay back to the beginning.
        """

        self.current_index = 0
        self.current_time = None


    def has_next(self) -> bool:
        """
        Return True while more historical records remain.
        """

        return self.current_index < len(self.records)


    def step(self) -> dict[str, Any] | None:
        """
        Move forward by exactly one historical record.
        """

        if not self.has_next():
            return None

        current_record = self.records[self.current_index]

        self.current_time = current_record[self.timestamp_key]

        self.current_index += 1

        return current_record


    def get_visible_history(self) -> list[dict[str, Any]]:
        """
        Return only data that was available up to
        the current replay time.

        O(log n) via binary search (get_available_data_sorted) - safe
        because self.records is sorted exactly once in __init__ and
        never mutated afterward. Correct regardless of call pattern:
        a fresh replay, a reset(), a repeated query at the same
        current_time, or an out-of-order query all resolve correctly,
        since this recomputes the prefix from the sorted array every
        call rather than relying on any monotonic assumption.
        """

        if self.current_time is None:
            return []

        return get_available_data_sorted(
            sorted_records=self.records,
            current_time=self.current_time,
            timestamp_key=self.timestamp_key,
        )


    def run(
        self,
        callback: Callable[
            [dict[str, Any], list[dict[str, Any]]],
            None
        ]
    ) -> None:
        """
        Replay the complete dataset.

        callback receives:
        1. The current record.
        2. The historical data visible at that moment.
        """

        self.reset()

        while self.has_next():
            current_record = self.step()

            if current_record is None:
                break

            visible_history = self.get_visible_history()

            callback(
                current_record,
                visible_history
            )