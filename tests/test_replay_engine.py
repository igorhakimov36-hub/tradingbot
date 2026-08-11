from datetime import datetime, timedelta

from backtesting.replay_engine import ReplayEngine


def create_test_records():
    start_time = datetime(2026, 1, 1, 12, 0)

    return [
        {
            "timestamp": start_time,
            "close": 100.0
        },
        {
            "timestamp": start_time + timedelta(minutes=1),
            "close": 101.0
        },
        {
            "timestamp": start_time + timedelta(minutes=2),
            "close": 102.0
        },
        {
            "timestamp": start_time + timedelta(minutes=3),
            "close": 103.0
        }
    ]


def test_replay_starts_at_beginning():
    engine = ReplayEngine(create_test_records())

    assert engine.current_index == 0
    assert engine.current_time is None
    assert engine.has_next() is True


def test_step_moves_forward_one_record():
    engine = ReplayEngine(create_test_records())

    first_record = engine.step()

    assert first_record["close"] == 100.0
    assert engine.current_index == 1
    assert engine.current_time == first_record["timestamp"]


def test_visible_history_does_not_include_future():
    engine = ReplayEngine(create_test_records())

    engine.step()

    visible_history = engine.get_visible_history()

    assert len(visible_history) == 1
    assert visible_history[0]["close"] == 100.0


def test_visible_history_grows_one_step_at_a_time():
    engine = ReplayEngine(create_test_records())

    engine.step()
    assert len(engine.get_visible_history()) == 1

    engine.step()
    assert len(engine.get_visible_history()) == 2

    engine.step()
    assert len(engine.get_visible_history()) == 3


def test_replay_sorts_records_by_timestamp():
    records = create_test_records()

    reversed_records = list(reversed(records))

    engine = ReplayEngine(reversed_records)

    first_record = engine.step()

    assert first_record["close"] == 100.0


def test_reset_returns_engine_to_start():
    engine = ReplayEngine(create_test_records())

    engine.step()
    engine.step()

    assert engine.current_index == 2

    engine.reset()

    assert engine.current_index == 0
    assert engine.current_time is None


def test_step_returns_none_when_finished():
    engine = ReplayEngine(create_test_records())

    while engine.has_next():
        engine.step()

    result = engine.step()

    assert result is None
    assert engine.has_next() is False


def test_run_processes_every_record():
    engine = ReplayEngine(create_test_records())

    processed = []

    def callback(current_record, visible_history):
        processed.append(
            {
                "close": current_record["close"],
                "visible_count": len(visible_history)
            }
        )

    engine.run(callback)

    assert len(processed) == 4

    assert processed[0]["close"] == 100.0
    assert processed[0]["visible_count"] == 1

    assert processed[1]["close"] == 101.0
    assert processed[1]["visible_count"] == 2

    assert processed[2]["close"] == 102.0
    assert processed[2]["visible_count"] == 3

    assert processed[3]["close"] == 103.0
    assert processed[3]["visible_count"] == 4


def test_callback_never_sees_future_record():
    engine = ReplayEngine(create_test_records())

    future_data_detected = False

    def callback(current_record, visible_history):
        nonlocal future_data_detected

        current_time = current_record["timestamp"]

        for record in visible_history:
            if record["timestamp"] > current_time:
                future_data_detected = True

    engine.run(callback)

    assert future_data_detected is False