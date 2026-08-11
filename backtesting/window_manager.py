from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TimeWindow:
    name: str
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.start >= self.end:
            raise ValueError(
                f"Invalid window '{self.name}': "
                f"start must be before end"
            )

    def contains(self, timestamp: datetime) -> bool:
        """
        Window convention:
        start is inclusive, end is exclusive.

        start <= timestamp < end
        """
        return self.start <= timestamp < self.end


class WindowManager:
    """
    Separates historical data into isolated time windows.

    Typical use:
    TRAIN -> parameter development
    VALIDATION -> model/experiment comparison
    HELD_OUT -> final untouched evaluation
    """

    def __init__(
        self,
        train: TimeWindow,
        validation: TimeWindow,
        held_out: TimeWindow,
        timestamp_key: str = "timestamp"
    ):
        self.train = train
        self.validation = validation
        self.held_out = held_out
        self.timestamp_key = timestamp_key

        self._validate_windows()


    def _validate_windows(self) -> None:
        """
        Ensure that TRAIN, VALIDATION and HELD_OUT
        are chronological and never overlap.
        """

        if self.train.end > self.validation.start:
            raise ValueError(
                "TRAIN and VALIDATION windows overlap"
            )

        if self.validation.end > self.held_out.start:
            raise ValueError(
                "VALIDATION and HELD_OUT windows overlap"
            )

        if not (
            self.train.start
            < self.validation.start
            < self.held_out.start
        ):
            raise ValueError(
                "Windows must be ordered: "
                "TRAIN -> VALIDATION -> HELD_OUT"
            )


    def get_window(
        self,
        name: str
    ) -> TimeWindow:
        """
        Return a configured window by name.
        """

        normalized_name = name.upper()

        if normalized_name == "TRAIN":
            return self.train

        if normalized_name == "VALIDATION":
            return self.validation

        if normalized_name in {"HELD_OUT", "HELD-OUT"}:
            return self.held_out

        raise ValueError(
            f"Unknown window: {name}"
        )


    def get_records(
        self,
        records: list[dict[str, Any]],
        window_name: str
    ) -> list[dict[str, Any]]:
        """
        Return only records belonging to the requested window.
        """

        window = self.get_window(window_name)

        result = []

        for record in records:
            if self.timestamp_key not in record:
                raise KeyError(
                    f"Missing timestamp key: "
                    f"{self.timestamp_key}"
                )

            timestamp = record[self.timestamp_key]

            if not isinstance(timestamp, datetime):
                raise TypeError(
                    f"{self.timestamp_key} "
                    f"must be a datetime object"
                )

            if window.contains(timestamp):
                result.append(record)

        return sorted(
            result,
            key=lambda record: record[self.timestamp_key]
        )


    def identify_window(
        self,
        timestamp: datetime
    ) -> str | None:
        """
        Identify which configured window owns a timestamp.
        """

        if self.train.contains(timestamp):
            return "TRAIN"

        if self.validation.contains(timestamp):
            return "VALIDATION"

        if self.held_out.contains(timestamp):
            return "HELD_OUT"

        return None