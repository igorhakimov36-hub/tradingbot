from datetime import datetime, timezone

import pytest

from analytics.performance import PerformanceReport
from backtesting.experiment_manager import ExperimentManager


def utc_time(hour: int = 12) -> datetime:
    return datetime(
        2025,
        1,
        1,
        hour,
        0,
        tzinfo=timezone.utc,
    )


def create_report(
    total_net_pnl: float = 100.0,
    win_rate: float = 50.0,
    max_drawdown: float = 50.0,
    max_drawdown_percent: float = 0.5,
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

        max_drawdown=max_drawdown,
        max_drawdown_percent=max_drawdown_percent,

        sharpe_ratio=sharpe_ratio,
    )


def record_experiment(
    manager: ExperimentManager,
    experiment_id: str,
    version: str = "V1",
    performance: PerformanceReport | None = None,
):
    return manager.record_experiment(
        experiment_id=experiment_id,
        version=version,
        timestamp=utc_time(),
        window_name="VALIDATION",
        parameters={
            "decision_threshold": 80,
            "latency_bars": 1,
        },
        performance=performance or create_report(),
    )


# =========================================================
# BASIC
# =========================================================

def test_new_manager_is_empty():
    manager = ExperimentManager()

    assert len(manager) == 0
    assert manager.experiments() == []


def test_valid_experiment_is_recorded():
    manager = ExperimentManager()

    result = record_experiment(
        manager=manager,
        experiment_id="exp_001",
    )

    assert len(manager) == 1
    assert result.experiment_id == "exp_001"
    assert result.version == "V1"
    assert result.window_name == "VALIDATION"


def test_experiments_returns_copy():
    manager = ExperimentManager()

    record_experiment(
        manager,
        "exp_001",
    )

    external = manager.experiments()
    external.clear()

    assert len(external) == 0
    assert len(manager) == 1


# =========================================================
# HELD-OUT PROTECTION
# =========================================================

def test_held_out_experiment_is_rejected():
    manager = ExperimentManager()

    with pytest.raises(ValueError):
        manager.record_experiment(
            experiment_id="bad_held_out",
            version="V1",
            timestamp=utc_time(),
            window_name="HELD_OUT",
            parameters={},
            performance=create_report(),
        )


def test_train_experiment_is_rejected():
    manager = ExperimentManager()

    with pytest.raises(ValueError):
        manager.record_experiment(
            experiment_id="bad_train",
            version="V1",
            timestamp=utc_time(),
            window_name="TRAIN",
            parameters={},
            performance=create_report(),
        )


# =========================================================
# ID / VERSION VALIDATION
# =========================================================

def test_duplicate_experiment_id_is_rejected():
    manager = ExperimentManager()

    record_experiment(
        manager,
        "exp_001",
    )

    with pytest.raises(ValueError):
        record_experiment(
            manager,
            "exp_001",
        )


def test_empty_experiment_id_is_rejected():
    manager = ExperimentManager()

    with pytest.raises(ValueError):
        record_experiment(
            manager,
            "   ",
        )


def test_non_string_experiment_id_is_rejected():
    manager = ExperimentManager()

    with pytest.raises(TypeError):
        record_experiment(
            manager,
            123,
        )


def test_empty_version_is_rejected():
    manager = ExperimentManager()

    with pytest.raises(ValueError):
        record_experiment(
            manager=manager,
            experiment_id="exp_001",
            version="   ",
        )


def test_non_string_version_is_rejected():
    manager = ExperimentManager()

    with pytest.raises(TypeError):
        record_experiment(
            manager=manager,
            experiment_id="exp_001",
            version=123,
        )


# =========================================================
# TIMESTAMP
# =========================================================

def test_naive_timestamp_is_rejected():
    manager = ExperimentManager()

    with pytest.raises(ValueError):
        manager.record_experiment(
            experiment_id="exp_001",
            version="V1",
            timestamp=datetime(
                2025,
                1,
                1,
                12,
                0,
            ),
            window_name="VALIDATION",
            parameters={},
            performance=create_report(),
        )


def test_invalid_timestamp_type_is_rejected():
    manager = ExperimentManager()

    with pytest.raises(TypeError):
        manager.record_experiment(
            experiment_id="exp_001",
            version="V1",
            timestamp="2025-01-01T12:00:00Z",
            window_name="VALIDATION",
            parameters={},
            performance=create_report(),
        )


# =========================================================
# INPUT VALIDATION
# =========================================================

def test_non_dictionary_parameters_are_rejected():
    manager = ExperimentManager()

    with pytest.raises(TypeError):
        manager.record_experiment(
            experiment_id="exp_001",
            version="V1",
            timestamp=utc_time(),
            window_name="VALIDATION",
            parameters=[],
            performance=create_report(),
        )


def test_invalid_performance_type_is_rejected():
    manager = ExperimentManager()

    with pytest.raises(TypeError):
        manager.record_experiment(
            experiment_id="exp_001",
            version="V1",
            timestamp=utc_time(),
            window_name="VALIDATION",
            parameters={},
            performance={},
        )


def test_parameters_are_copied_when_recorded():
    manager = ExperimentManager()

    parameters = {
        "decision_threshold": 80
    }

    result = manager.record_experiment(
        experiment_id="exp_001",
        version="V1",
        timestamp=utc_time(),
        window_name="VALIDATION",
        parameters=parameters,
        performance=create_report(),
    )

    parameters["decision_threshold"] = 999

    assert (
        result.parameters["decision_threshold"]
        == 80
    )


# =========================================================
# LOOKUP
# =========================================================

def test_get_experiment_returns_correct_result():
    manager = ExperimentManager()

    record_experiment(
        manager,
        "exp_001",
        version="V1",
    )

    record_experiment(
        manager,
        "exp_002",
        version="V2",
    )

    result = manager.get_experiment(
        "exp_002"
    )

    assert result is not None
    assert result.experiment_id == "exp_002"
    assert result.version == "V2"


def test_unknown_experiment_returns_none():
    manager = ExperimentManager()

    assert (
        manager.get_experiment("does_not_exist")
        is None
    )


def test_by_version_returns_only_requested_version():
    manager = ExperimentManager()

    record_experiment(
        manager,
        "exp_001",
        version="V1",
    )

    record_experiment(
        manager,
        "exp_002",
        version="V2",
    )

    record_experiment(
        manager,
        "exp_003",
        version="V1",
    )

    results = manager.by_version("V1")

    assert len(results) == 2
    assert all(
        result.version == "V1"
        for result in results
    )


# =========================================================
# BEST BY METRIC
# =========================================================

def test_best_by_total_net_pnl():
    manager = ExperimentManager()

    record_experiment(
        manager,
        "exp_001",
        performance=create_report(
            total_net_pnl=100.0
        ),
    )

    record_experiment(
        manager,
        "exp_002",
        performance=create_report(
            total_net_pnl=250.0
        ),
    )

    best = manager.best_by(
        "total_net_pnl"
    )

    assert best is not None
    assert best.experiment_id == "exp_002"


def test_best_by_sharpe_ignores_none_values():
    manager = ExperimentManager()

    record_experiment(
        manager,
        "exp_001",
        performance=create_report(
            sharpe_ratio=None
        ),
    )

    record_experiment(
        manager,
        "exp_002",
        performance=create_report(
            sharpe_ratio=1.5
        ),
    )

    best = manager.best_by(
        "sharpe_ratio"
    )

    assert best is not None
    assert best.experiment_id == "exp_002"


def test_best_by_returns_none_when_all_values_are_none():
    manager = ExperimentManager()

    record_experiment(
        manager,
        "exp_001",
        performance=create_report(
            sharpe_ratio=None
        ),
    )

    record_experiment(
        manager,
        "exp_002",
        performance=create_report(
            sharpe_ratio=None
        ),
    )

    assert (
        manager.best_by("sharpe_ratio")
        is None
    )


def test_best_by_empty_manager_returns_none():
    manager = ExperimentManager()

    assert (
        manager.best_by("total_net_pnl")
        is None
    )


def test_best_by_unknown_metric_is_rejected():
    manager = ExperimentManager()

    record_experiment(
        manager,
        "exp_001",
    )

    with pytest.raises(ValueError):
        manager.best_by(
            "made_up_metric"
        )


# =========================================================
# COMPARISON
# =========================================================

def test_compare_calculates_deltas_correctly():
    manager = ExperimentManager()

    record_experiment(
        manager,
        "v1_test",
        version="V1",
        performance=create_report(
            total_net_pnl=100.0,
            win_rate=50.0,
            max_drawdown=200.0,
            max_drawdown_percent=2.0,
        ),
    )

    record_experiment(
        manager,
        "v2_test",
        version="V2",
        performance=create_report(
            total_net_pnl=160.0,
            win_rate=60.0,
            max_drawdown=150.0,
            max_drawdown_percent=1.5,
        ),
    )

    result = manager.compare(
        "v1_test",
        "v2_test",
    )

    assert (
        result["delta_total_net_pnl"]
        == pytest.approx(60.0)
    )

    assert (
        result["delta_win_rate"]
        == pytest.approx(10.0)
    )

    assert (
        result["delta_max_drawdown"]
        == pytest.approx(-50.0)
    )

    assert (
        result["delta_max_drawdown_percent"]
        == pytest.approx(-0.5)
    )


def test_compare_rejects_unknown_first_experiment():
    manager = ExperimentManager()

    record_experiment(
        manager,
        "exp_002",
    )

    with pytest.raises(ValueError):
        manager.compare(
            "missing",
            "exp_002",
        )


def test_compare_rejects_unknown_second_experiment():
    manager = ExperimentManager()

    record_experiment(
        manager,
        "exp_001",
    )

    with pytest.raises(ValueError):
        manager.compare(
            "exp_001",
            "missing",
        )


# =========================================================
# EXPORT
# =========================================================

def test_to_dicts_exports_experiments():
    manager = ExperimentManager()

    record_experiment(
        manager,
        "exp_001",
        version="V1",
    )

    result = manager.to_dicts()

    assert isinstance(result, list)
    assert len(result) == 1

    assert (
        result[0]["experiment_id"]
        == "exp_001"
    )

    assert result[0]["version"] == "V1"

    assert (
        result[0]["window_name"]
        == "VALIDATION"
    )