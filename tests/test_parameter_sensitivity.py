import pytest

from analytics.performance import PerformanceReport
from backtesting.parameter_sensitivity import (
    ParameterSensitivity,
    SensitivityResult,
)


def create_report(
    total_net_pnl: float = 100.0,
    win_rate: float = 50.0,
    profit_factor: float | None = 2.0,
    sharpe_ratio: float | None = 1.0,
) -> PerformanceReport:

    return PerformanceReport(
        total_trades=10,
        winning_trades=5,
        losing_trades=5,
        breakeven_trades=0,

        win_rate=win_rate,

        total_net_pnl=total_net_pnl,
        average_net_pnl=10.0,

        average_win=30.0,
        average_loss=-10.0,

        gross_profit=150.0,
        gross_loss=50.0,
        profit_factor=profit_factor,

        total_fees=5.0,

        max_drawdown=50.0,
        max_drawdown_percent=0.5,

        sharpe_ratio=sharpe_ratio,
    )


# =========================================================
# INITIALIZATION
# =========================================================

def test_evaluator_must_be_callable():
    with pytest.raises(TypeError):
        ParameterSensitivity(
            evaluator=123
        )


def test_valid_evaluator_is_accepted():
    def evaluator(parameters):
        return create_report()

    sensitivity = ParameterSensitivity(
        evaluator=evaluator
    )

    assert sensitivity.evaluator is evaluator


# =========================================================
# RUN VALIDATION
# =========================================================

def test_parameter_name_must_be_string():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report()
    )

    with pytest.raises(TypeError):
        sensitivity.run(
            parameter_name=123,
            values=[1, 2, 3],
            base_parameters={},
        )


def test_parameter_name_cannot_be_empty():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report()
    )

    with pytest.raises(ValueError):
        sensitivity.run(
            parameter_name="   ",
            values=[1, 2, 3],
            base_parameters={},
        )


def test_values_must_be_list():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report()
    )

    with pytest.raises(TypeError):
        sensitivity.run(
            parameter_name="threshold",
            values=(75, 80, 85),
            base_parameters={},
        )


def test_values_cannot_be_empty():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report()
    )

    with pytest.raises(ValueError):
        sensitivity.run(
            parameter_name="threshold",
            values=[],
            base_parameters={},
        )


def test_base_parameters_must_be_dictionary():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report()
    )

    with pytest.raises(TypeError):
        sensitivity.run(
            parameter_name="threshold",
            values=[75, 80, 85],
            base_parameters=[],
        )


# =========================================================
# RUN BEHAVIOR
# =========================================================

def test_every_parameter_value_is_evaluated():
    received_parameters = []

    def evaluator(parameters):
        received_parameters.append(
            dict(parameters)
        )
        return create_report()

    sensitivity = ParameterSensitivity(
        evaluator=evaluator
    )

    results = sensitivity.run(
        parameter_name="decision_threshold",
        values=[75, 80, 85],
        base_parameters={
            "latency_bars": 1,
        },
    )

    assert len(results) == 3
    assert len(received_parameters) == 3

    assert (
        received_parameters[0]
        ["decision_threshold"]
        == 75
    )

    assert (
        received_parameters[1]
        ["decision_threshold"]
        == 80
    )

    assert (
        received_parameters[2]
        ["decision_threshold"]
        == 85
    )


def test_other_base_parameters_are_preserved():
    received_parameters = []

    def evaluator(parameters):
        received_parameters.append(
            dict(parameters)
        )
        return create_report()

    sensitivity = ParameterSensitivity(
        evaluator=evaluator
    )

    sensitivity.run(
        parameter_name="decision_threshold",
        values=[75, 80],
        base_parameters={
            "decision_threshold": 80,
            "latency_bars": 2,
            "fill_probability": 0.9,
        },
    )

    for parameters in received_parameters:
        assert parameters["latency_bars"] == 2
        assert (
            parameters["fill_probability"]
            == 0.9
        )


def test_base_parameters_are_not_mutated():
    base_parameters = {
        "decision_threshold": 80,
        "latency_bars": 1,
    }

    original = dict(base_parameters)

    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report()
    )

    sensitivity.run(
        parameter_name="decision_threshold",
        values=[75, 80, 85],
        base_parameters=base_parameters,
    )

    assert base_parameters == original


def test_run_returns_sensitivity_results():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report(
            total_net_pnl=float(
                parameters["threshold"]
            )
        )
    )

    results = sensitivity.run(
        parameter_name="threshold",
        values=[70, 80],
        base_parameters={},
    )

    assert len(results) == 2

    assert all(
        isinstance(
            result,
            SensitivityResult,
        )
        for result in results
    )

    assert results[0].parameter_name == "threshold"
    assert results[0].parameter_value == 70

    assert (
        results[0].performance.total_net_pnl
        == 70.0
    )


def test_evaluator_must_return_performance_report():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: {
            "pnl": 100
        }
    )

    with pytest.raises(TypeError):
        sensitivity.run(
            parameter_name="threshold",
            values=[80],
            base_parameters={},
        )


# =========================================================
# SUMMARY VALIDATION
# =========================================================

def test_summary_results_must_be_list():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report()
    )

    with pytest.raises(TypeError):
        sensitivity.summarize(
            results=(),
            metric="total_net_pnl",
        )


def test_summary_results_cannot_be_empty():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report()
    )

    with pytest.raises(ValueError):
        sensitivity.summarize(
            results=[],
            metric="total_net_pnl",
        )


def test_summary_metric_must_be_string():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report()
    )

    results = sensitivity.run(
        parameter_name="threshold",
        values=[80],
        base_parameters={},
    )

    with pytest.raises(TypeError):
        sensitivity.summarize(
            results=results,
            metric=123,
        )


def test_unknown_metric_is_rejected():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report()
    )

    results = sensitivity.run(
        parameter_name="threshold",
        values=[80],
        base_parameters={},
    )

    with pytest.raises(ValueError):
        sensitivity.summarize(
            results=results,
            metric="made_up_metric",
        )


def test_summary_rejects_invalid_result_objects():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report()
    )

    with pytest.raises(TypeError):
        sensitivity.summarize(
            results=["invalid"],
            metric="total_net_pnl",
        )


# =========================================================
# BEST / WORST
# =========================================================

def test_summary_finds_best_and_worst_values():
    def evaluator(parameters):
        threshold = parameters[
            "decision_threshold"
        ]

        pnl_by_threshold = {
            75: 80.0,
            80: 150.0,
            85: 100.0,
        }

        return create_report(
            total_net_pnl=(
                pnl_by_threshold[threshold]
            )
        )

    sensitivity = ParameterSensitivity(
        evaluator=evaluator
    )

    results = sensitivity.run(
        parameter_name="decision_threshold",
        values=[75, 80, 85],
        base_parameters={},
    )

    summary = sensitivity.summarize(
        results=results,
        metric="total_net_pnl",
    )

    assert (
        summary.parameter_name
        == "decision_threshold"
    )

    assert summary.best_value == 80
    assert summary.best_metric_value == 150.0

    assert summary.worst_value == 75
    assert summary.worst_metric_value == 80.0

    assert summary.metric == "total_net_pnl"


def test_summary_works_with_negative_values():
    def evaluator(parameters):
        value = parameters["x"]

        return create_report(
            total_net_pnl=float(value)
        )

    sensitivity = ParameterSensitivity(
        evaluator=evaluator
    )

    results = sensitivity.run(
        parameter_name="x",
        values=[-100, -20, -50],
        base_parameters={},
    )

    summary = sensitivity.summarize(
        results,
        metric="total_net_pnl",
    )

    assert summary.best_value == -20
    assert summary.best_metric_value == -20.0

    assert summary.worst_value == -100
    assert summary.worst_metric_value == -100.0


# =========================================================
# NONE METRICS
# =========================================================

def test_summary_ignores_none_metric_values():
    def evaluator(parameters):
        value = parameters["x"]

        if value == 1:
            return create_report(
                sharpe_ratio=None
            )

        if value == 2:
            return create_report(
                sharpe_ratio=1.5
            )

        return create_report(
            sharpe_ratio=0.5
        )

    sensitivity = ParameterSensitivity(
        evaluator=evaluator
    )

    results = sensitivity.run(
        parameter_name="x",
        values=[1, 2, 3],
        base_parameters={},
    )

    summary = sensitivity.summarize(
        results,
        metric="sharpe_ratio",
    )

    assert summary.best_value == 2
    assert summary.best_metric_value == 1.5

    assert summary.worst_value == 3
    assert summary.worst_metric_value == 0.5


def test_summary_returns_none_when_all_metric_values_are_none():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report(
            sharpe_ratio=None
        )
    )

    results = sensitivity.run(
        parameter_name="threshold",
        values=[75, 80, 85],
        base_parameters={},
    )

    summary = sensitivity.summarize(
        results,
        metric="sharpe_ratio",
    )

    assert summary.best_value is None
    assert summary.best_metric_value is None

    assert summary.worst_value is None
    assert summary.worst_metric_value is None


# =========================================================
# PARAMETER CONSISTENCY
# =========================================================

def test_summary_rejects_mixed_parameter_names():
    sensitivity = ParameterSensitivity(
        evaluator=lambda parameters: create_report()
    )

    results = [
        SensitivityResult(
            parameter_name="threshold",
            parameter_value=80,
            performance=create_report(),
        ),
        SensitivityResult(
            parameter_name="latency_bars",
            parameter_value=1,
            performance=create_report(),
        ),
    ]

    with pytest.raises(ValueError):
        sensitivity.summarize(
            results=results,
            metric="total_net_pnl",
        )