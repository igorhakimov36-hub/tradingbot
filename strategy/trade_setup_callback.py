from strategy.trade_setup import (
    create_risk_based_trade_setup,
    TradeSetup,
)


def trade_setup_callback(
    decision: str,
    current_candle: dict,
    visible_history: list[dict],
    market_snapshot: dict,
    current_equity: float,
) -> TradeSetup:

    entry = current_candle["close"]

    if decision == "LONG":

        stop = min(
            current_candle["low"],
            entry * 0.995,
        )

        risk = entry - stop

        if risk < entry * 0.002:
            stop = entry * 0.998
            risk = entry - stop

        take_profit = entry + (risk * 2)

    elif decision == "SHORT":

        stop = max(
            current_candle["high"],
            entry * 1.005,
        )

        risk = stop - entry

        if risk < entry * 0.002:
            stop = entry * 1.002
            risk = stop - entry

        take_profit = entry - (risk * 2)

    else:
        raise ValueError("decision must be LONG or SHORT")

    print("CURRENT EQUITY:", current_equity)
    print("DECISION:", decision)
    print("ENTRY:", entry)
    print("STOP:", stop)
    print("RISK:", risk)

    return create_risk_based_trade_setup(
        side=decision,
        entry_price=entry,
        stop_loss=stop,
        take_profit=take_profit,
        equity=current_equity,
        risk_percent=1.0,
    )
