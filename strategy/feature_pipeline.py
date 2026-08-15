from typing import Any


def build_market_structure(
    current_candle: dict[str, Any],
    visible_history: list[dict[str, Any]],
) -> dict[str, Any]:
    pass


def build_liquidity(
    current_candle: dict[str, Any],
    visible_history: list[dict[str, Any]],
) -> dict[str, Any]:
    pass


def build_volume(
    current_candle: dict[str, Any],
    visible_history: list[dict[str, Any]],
) -> dict[str, Any]:
    pass


def build_open_interest(
    market_snapshot: dict[str, Any],
) -> dict[str, Any]:
    pass


def build_funding(
    market_snapshot: dict[str, Any],
) -> dict[str, Any]:
    pass


def build_features(
    current_candle: dict[str, Any],
    visible_history: list[dict[str, Any]],
    market_snapshot: dict[str, Any],
) -> dict[str, Any]:
    pass
