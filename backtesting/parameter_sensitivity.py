from dataclasses import dataclass
from typing import Any, Callable

from analytics.performance import PerformanceReport


@dataclass(frozen=True)
class SensitivityResult:
    parameter_name: str
    parameter_value: Any
    performance: PerformanceReport


@dataclass(frozen=True)
class SensitivitySummary:
    parameter_name: str
    results: list[SensitivityResult]

    best_value: Any | None
    best_metric_value: float | None

    worst_value: Any | None
    worst_metric_value: float | None

    metric: str


class ParameterSensitivity:
    """
    Runs one-parameter-at-a-time sensitivity analysis.

    The purpose is NOT to find one magical parameter.

    The purpose is to see whether strategy performance
    remains reasonably stable when a parameter changes.
    """

    def __init__(
        self,
        evaluator: Callable[
            [dict[str, Any]],
            PerformanceReport,
        ],
    ):
        if not callable(evaluator):
            raise TypeError(
                "evaluator must be callable"
            )

        self.evaluator = evaluator


    def run(
        self,
        parameter_name: str,
        values: list[Any],
        base_parameters: dict[str, Any],
    ) -> list[SensitivityResult]:

        if not isinstance(parameter_name, str):
            raise TypeError(
                "parameter_name must be a string"
            )

        if not parameter_name.strip():
            raise ValueError(
                "parameter_name cannot be empty"
            )

        if not isinstance(values, list):
            raise TypeError(
                "values must be a list"
            )

        if not values:
            raise ValueError(
                "values cannot be empty"
            )

        if not isinstance(base_parameters, dict):
            raise TypeError(
                "base_parameters must be a dictionary"
            )

        results: list[SensitivityResult] = []

        for value in values:
            parameters = dict(base_parameters)

            parameters[parameter_name] = value

            performance = self.evaluator(
                parameters
            )

            if not isinstance(
                performance,
                PerformanceReport,
            ):
                raise TypeError(
                    "evaluator must return "
                    "a PerformanceReport"
                )

            results.append(
                SensitivityResult(
                    parameter_name=parameter_name,
                    parameter_value=value,
                    performance=performance,
                )
            )

        return results


    def summarize(
        self,
        results: list[SensitivityResult],
        metric: str,
    ) -> SensitivitySummary:

        if not isinstance(results, list):
            raise TypeError(
                "results must be a list"
            )

        if not results:
            raise ValueError(
                "results cannot be empty"
            )

        if not isinstance(metric, str):
            raise TypeError(
                "metric must be a string"
            )

        first_result = results[0]

        if not isinstance(
            first_result,
            SensitivityResult,
        ):
            raise TypeError(
                "results must contain "
                "SensitivityResult objects"
            )

        if not hasattr(
            first_result.performance,
            metric,
        ):
            raise ValueError(
                f"Unknown performance metric: {metric}"
            )

        parameter_name = (
            first_result.parameter_name
        )

        for result in results:

            if not isinstance(
                result,
                SensitivityResult,
            ):
                raise TypeError(
                    "results must contain "
                    "SensitivityResult objects"
                )

            if (
                result.parameter_name
                != parameter_name
            ):
                raise ValueError(
                    "All sensitivity results must "
                    "use the same parameter"
                )

        valid_results = [
            result
            for result in results
            if getattr(
                result.performance,
                metric,
            ) is not None
        ]

        if not valid_results:
            return SensitivitySummary(
                parameter_name=parameter_name,
                results=list(results),

                best_value=None,
                best_metric_value=None,

                worst_value=None,
                worst_metric_value=None,

                metric=metric,
            )

        best = max(
            valid_results,
            key=lambda result: getattr(
                result.performance,
                metric,
            ),
        )

        worst = min(
            valid_results,
            key=lambda result: getattr(
                result.performance,
                metric,
            ),
        )

        return SensitivitySummary(
            parameter_name=parameter_name,
            results=list(results),

            best_value=best.parameter_value,
            best_metric_value=getattr(
                best.performance,
                metric,
            ),

            worst_value=worst.parameter_value,
            worst_metric_value=getattr(
                worst.performance,
                metric,
            ),

            metric=metric,
        )