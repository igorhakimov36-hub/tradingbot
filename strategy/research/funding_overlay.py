"""
Fixed-trade funding overlay for the SOL Funding Impact research sprint.
RESEARCH-ONLY, pure functions. Applies Binance USDⓈ-M perpetual futures
funding settlements to ALREADY-RECORDED, ALREADY-CLOSED trades from an
existing trade ledger, using each trade's own real entry/exit
timestamps, side, and quantity exactly as already executed - this
module never changes which trades were taken, when, or at what size.

Accounting convention (verified against Binance's own funding-fee FAQ,
https://www.binance.com/en/support/faq/detail/360033525031, checked
2026-09-05, and cross-checked against real downloaded SOLUSDT funding
records):

    funding_amount = mark_price_at_settlement * position_size * funding_rate
    payment_to_trader = -side_sign * funding_amount
        side_sign = +1 for LONG, -1 for SHORT

i.e. a positive funding rate means LONG pays / SHORT receives; a
negative rate means SHORT pays / LONG receives - the sign convention is
applied once, using the position's own signed quantity, never a second
leverage multiplication (mark_price * quantity already IS the full
notional position value, matching Binance's own "Nominal Value of
Positions = Mark Price * Size of a Contract" wording - margin balance
is never used).

A position is only liable for a funding settlement if it was open
(already entered, not yet closed) at that settlement's own real,
recorded timestamp - "if you close your position prior to the funding
time, you will not pay or receive any funding" (same FAQ). This module
never assumes an invariant 8-hour schedule; it uses each settlement's
own real, downloaded timestamp, since Binance's own documentation
discloses the interval can shift (e.g. to hourly) during extreme
volatility.

This module never uses a funding settlement that occurs AFTER a
position's own exit as information available to that trade's entry
decision - it is a fixed-trade, post-hoc cost overlay only, never an
input to any entry/exit choice.
"""

import csv
from pathlib import Path
from typing import Any, Literal

from data.historical_loader import parse_timestamp

BoundaryConvention = Literal["inclusive", "exclusive_exit"]


def load_funding_records_with_mark_price(file_path: str | Path) -> list[dict[str, Any]]:
    """
    Reads a raw funding CSV as saved by
    exchange/download_historical_funding.py (fundingTime, fundingRate,
    markPrice, symbol), keeping `markPrice` - unlike
    data/funding_loader.py's own normalize_funding_record(), which
    discards it (that loader was built for a rate-only consumer; this
    module needs mark price too, per Binance's own funding formula).
    Returns [{"timestamp", "rate", "mark_price"}, ...], chronologically
    sorted. A row with a blank markPrice/fundingRate produces `None`
    for that field - never a fabricated value.
    """

    path = Path(file_path)
    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rate = row.get("fundingRate")
            mark_price = row.get("markPrice")
            records.append({
                "timestamp": parse_timestamp(row["fundingTime"]),
                "rate": float(rate) if rate not in (None, "") else None,
                "mark_price": float(mark_price) if mark_price not in (None, "") else None,
            })

    records.sort(key=lambda r: r["timestamp"])
    return records


def funding_events_for_position(
    entry_timestamp: Any,
    exit_timestamp: Any,
    side: str,
    quantity: float,
    funding_records: list[dict[str, Any]],
    boundary: BoundaryConvention = "inclusive",
) -> list[dict[str, Any]]:
    """
    `funding_records`: chronologically-ordered list of
    {"timestamp", "rate", "mark_price"} - `rate`/`mark_price` may be
    None to represent a genuinely missing record (never silently
    treated as zero).

    `boundary`:
    - "inclusive": a settlement at exactly `entry_timestamp` or exactly
      `exit_timestamp` IS charged (entry_timestamp <= t <= exit_timestamp).
    - "exclusive_exit": a settlement at exactly `exit_timestamp` is NOT
      charged (entry_timestamp <= t < exit_timestamp), matching a
      strict reading of "if you close your position prior to the
      funding time" as "closed means the position is gone by T,
      including a close occurring exactly at T."

    Both conventions are frozen, named, and reported side by side by
    the caller (see the sprint's own required "flag ambiguous
    entry/exit timing near settlement and report sensitivity") - this
    function does not pick one as more correct.

    Returns one entry per applicable settlement:
    {"timestamp", "rate", "mark_price", "payment", "missing_data"}.
    `payment` is the signed cash flow TO the trader (positive = trader
    receives, negative = trader pays); `None` if `missing_data` is True
    - never fabricated as zero.
    """

    if side not in ("LONG", "SHORT"):
        raise ValueError(f"side must be LONG or SHORT, got {side!r}")

    side_sign = 1.0 if side == "LONG" else -1.0
    events: list[dict[str, Any]] = []

    for record in funding_records:
        t = record["timestamp"]

        if boundary == "inclusive":
            applicable = entry_timestamp <= t <= exit_timestamp
        elif boundary == "exclusive_exit":
            applicable = entry_timestamp <= t < exit_timestamp
        else:
            raise ValueError(f"unknown boundary convention: {boundary!r}")

        if not applicable:
            continue

        rate = record.get("rate")
        mark_price = record.get("mark_price")

        if rate is None or mark_price is None:
            events.append({
                "timestamp": t, "rate": rate, "mark_price": mark_price,
                "payment": None, "missing_data": True,
            })
            continue

        notional = quantity * mark_price
        payment = -side_sign * notional * rate

        events.append({
            "timestamp": t, "rate": rate, "mark_price": mark_price,
            "payment": payment, "missing_data": False,
        })

    return events


def funding_summary_for_trade(
    entry_timestamp: Any,
    exit_timestamp: Any,
    side: str,
    quantity: float,
    funding_records: list[dict[str, Any]],
    boundary: BoundaryConvention = "inclusive",
) -> dict[str, Any]:
    """
    Aggregates funding_events_for_position() into one trade-level
    summary: {"n_settlements", "n_missing", "paid", "received", "net",
    "net_available" (False if any settlement in range has missing
    data - the trade's own net figure is then incomplete, never
    silently treated as fully known), "events"}.
    """

    events = funding_events_for_position(
        entry_timestamp, exit_timestamp, side, quantity, funding_records, boundary,
    )

    n_missing = sum(1 for e in events if e["missing_data"])
    known_payments = [e["payment"] for e in events if not e["missing_data"]]

    paid = sum(-p for p in known_payments if p < 0)
    received = sum(p for p in known_payments if p > 0)
    net = received - paid

    return {
        "n_settlements": len(events),
        "n_missing": n_missing,
        "paid": paid,
        "received": received,
        "net": net,
        "net_available": n_missing == 0,
        "events": events,
    }
