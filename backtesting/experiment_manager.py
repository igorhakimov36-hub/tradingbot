from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from analytics.performance import PerformanceReport


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: str
    version: str
    timestamp: datetime
    window_name: str

    parameters: dict[str, Any]
    performance: PerformanceReport

    notes: str | None = None


class ExperimentManager:
    """
    Stores and compares strategy experiments.

    Important design rule:
    Experiments are allowed on VALIDATION only.

    HELD_OUT must remain untouched until the final
    strategy version has been selected.
    """

    ALLOWED_WINDOW = "VALIDATION"

    def __init__(self):
        self._experiments: list[ExperimentResult] = []


    def _validate_timestamp(
        self,
        timestamp: datetime,
    ) -> None:

        if not isinstance(timestamp, datetime):
            raise TypeError(
                "timestamp must be a datetime"
            )

        if (
            timestamp.tzinfo is None
            or timestamp.utcoffset() is None
        ):
            raise ValueError(
                "timestamp must be timezone-aware"
            )


    def _validate_window(
        self,
        window_name: str,
    ) -> None:

        if window_name != self.ALLOWED_WINDOW:
            raise ValueError(
                "Experiments may run on VALIDATION only"
            )


    def _validate_experiment_id(
        self,
        experiment_id: str,
    ) -> None:

        if not isinstance(experiment_id, str):
            raise TypeError(
                "experiment_id must be a string"
            )

        if not experiment_id.strip():
            raise ValueError(
                "experiment_id cannot be empty"
            )

        if any(
            experiment.experiment_id == experiment_id
            for experiment in self._experiments
        ):
            raise ValueError(
                f"Duplicate experiment_id: {experiment_id}"
            )


    def record_experiment(
        self,
        experiment_id: str,
        version: str,
        timestamp: datetime,
        window_name: str,
        parameters: dict[str, Any],
        performance: PerformanceReport,
        notes: str | None = None,
    ) -> ExperimentResult:

        self._validate_experiment_id(
            experiment_id
        )

        self._validate_timestamp(
            timestamp
        )

        self._validate_window(
            window_name
        )

        if not isinstance(version, str):
            raise TypeError(
                "version must be a string"
            )

        if not version.strip():
            raise ValueError(
                "version cannot be empty"
            )

        if not isinstance(parameters, dict):
            raise TypeError(
                "parameters must be a dictionary"
            )

        if not isinstance(
            performance,
            PerformanceReport,
        ):
            raise TypeError(
                "performance must be a PerformanceReport"
            )

        result = ExperimentResult(
            experiment_id=experiment_id,
            version=version,
            timestamp=timestamp,
            window_name=window_name,
            parameters=dict(parameters),
            performance=performance,
            notes=notes,
        )

        self._experiments.append(result)

        return result


    def experiments(
        self,
    ) -> list[ExperimentResult]:
        """
        Return a copy of the experiment list.
        """

        return list(self._experiments)


    def get_experiment(
        self,
        experiment_id: str,
    ) -> ExperimentResult | None:

        for experiment in self._experiments:
            if (
                experiment.experiment_id
                == experiment_id
            ):
                return experiment

        return None


    def by_version(
        self,
        version: str,
    ) -> list[ExperimentResult]:

        return [
            experiment
            for experiment in self._experiments
            if experiment.version == version
        ]


    def best_by(
        self,
        metric: str,
    ) -> ExperimentResult | None:
        """
        Return the experiment with the highest value
        for a selected performance metric.

        Examples:
        - total_net_pnl
        - profit_factor
        - sharpe_ratio
        - win_rate

        Metrics whose value is None are ignored.
        """

        if not self._experiments:
            return None

        if not hasattr(
            self._experiments[0].performance,
            metric,
        ):
            raise ValueError(
                f"Unknown performance metric: {metric}"
            )

        valid_experiments = [
            experiment
            for experiment in self._experiments
            if getattr(
                experiment.performance,
                metric,
            ) is not None
        ]

        if not valid_experiments:
            return None

        return max(
            valid_experiments,
            key=lambda experiment: getattr(
                experiment.performance,
                metric,
            ),
        )


    def compare(
        self,
        experiment_id_a: str,
        experiment_id_b: str,
    ) -> dict[str, Any]:

        experiment_a = self.get_experiment(
            experiment_id_a
        )

        experiment_b = self.get_experiment(
            experiment_id_b
        )

        if experiment_a is None:
            raise ValueError(
                f"Unknown experiment: {experiment_id_a}"
            )

        if experiment_b is None:
            raise ValueError(
                f"Unknown experiment: {experiment_id_b}"
            )

        performance_a = experiment_a.performance
        performance_b = experiment_b.performance

        return {
            "experiment_a": experiment_a,
            "experiment_b": experiment_b,

            "delta_total_net_pnl": (
                performance_b.total_net_pnl
                - performance_a.total_net_pnl
            ),

            "delta_win_rate": (
                performance_b.win_rate
                - performance_a.win_rate
            ),

            "delta_max_drawdown": (
                performance_b.max_drawdown
                - performance_a.max_drawdown
            ),

            "delta_max_drawdown_percent": (
                performance_b.max_drawdown_percent
                - performance_a.max_drawdown_percent
            ),
        }


    def to_dicts(
        self,
    ) -> list[dict[str, Any]]:

        return [
            asdict(experiment)
            for experiment in self._experiments
        ]


    def __len__(
        self,
    ) -> int:

        return len(self._experiments)