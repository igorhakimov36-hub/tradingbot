from strategy.trade_setup import (
    create_risk_based_trade_setup,
    TradeSetup,
)

MIN_RISK_PERCENT = 0.006


def trade_setup_callback(
    decision: str,
    current_candle: dict,
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

        # Round-trip fees + slippage cost ~0.12% of price
        # (see ExecutionConfig). A stop tighter than that
        # gets mostly eaten by friction before it reflects
        # real market risk, so the floor keeps friction under
        # roughly a fifth of the planned risk per trade.
        if risk < entry * MIN_RISK_PERCENT:
            stop = entry * (1 - MIN_RISK_PERCENT)
            risk = entry - stop

        take_profit = entry + (risk * 2)

    elif decision == "SHORT":

        stop = max(
            current_candle["high"],
            entry * 1.005,
        )

        risk = stop - entry

        if risk < entry * MIN_RISK_PERCENT:
            stop = entry * (1 + MIN_RISK_PERCENT)
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
