"""
Instrument-scale configuration helpers - Sprint 1, Part B (SOL scaling
correction).

Purpose
-------
`MarketIntelligenceCoordinator`'s `round_number_spacing` (default 500.0)
and `volume_profile_bucket_size` (default 50.0) are absolute price
levels, hardcoded for BTC's ~$40,000-100,000 range in this project's
data. Confirmed by direct inspection (not assumed): `LiquidityPoolTracker`
itself defaults `round_number_spacing` to `None` (already symbol-agnostic
- disables the round-number sub-detector rather than guessing), and
`VolumeProfileTracker.bucket_size` is a REQUIRED constructor argument
with NO default at all (also already symbol-agnostic). The BTC-specific
numbers exist in exactly one place: `MarketIntelligenceCoordinator`'s
own default parameter values. This module does not touch either
tracker - both were already correctly designed.

This module does NOT change MarketIntelligenceCoordinator's defaults.
BTC callers that construct it without passing these parameters
explicitly (every BTC script used in this project so far) are
completely unaffected - zero regression risk. Instead, this module
gives any caller (a future SOL research script, or eventually a live
symbol-agnostic wiring layer) a principled, non-fitted way to compute a
scale-appropriate value to pass in EXPLICITLY, making the effective
configuration visible in that caller's own code/output rather than a
silent, buried default.

The rule
--------
A "round number" level is, by definition, a psychologically simple
price a market participant would actually place an order around - this
is inherently a function of the instrument's OWN price scale, not a
fixed dollar amount. `nice_round_number()` snaps any positive value to
the nearest {1, 2, 5, 10} x 10^k - the standard "nice number" sequence
used for chart gridlines and round-number psychology alike.

`default_round_number_spacing()` targets 1% of a given reference price;
`default_volume_profile_bucket_size()` targets 0.1% (matching the
existing ~10:1 ratio between BTC's own 500/50 defaults, but derived
independently from each target percentage, not forced as a fixed
ratio between outputs). Both percentages were chosen from round-number
convention BEFORE checking against BTC's existing values, not fitted
to reproduce them - the fact that both independently reproduce BTC's
existing 500/50 exactly, for BTC's actual January 2024 opening price
(~$42,314), is presented as consistency evidence, not proof of
optimality: it most plausibly reflects that BTC's original 500/50 were
themselves already "nice numbers" for BTC's typical price level, which
a reasonably-chosen percentage in a fairly wide neighborhood will
naturally reproduce.

Point-in-time safety
---------------------
Both functions are pure computations over a single already-known price
- the caller is responsible for choosing a point-in-time-safe
`reference_price` (e.g., the first available close in the dataset being
replayed, never a value chosen by looking at how the choice affects
strategy performance). No historical data is scanned here, and nothing
in this module runs per-bar - the intended usage is to compute a value
ONCE, before a backtest run begins, and pass it into
MarketIntelligenceCoordinator's constructor for the life of that run,
avoiding any in-run instability (never recomputed mid-run, never
changes during an open trade).

Deliberately not implemented here: any per-bar or dynamic
recomputation as price drifts far from the reference over a long
backtest. That would introduce exactly the "unstable bucket
boundaries" risk explicitly flagged as needing its own explicit design
- not decided in this sprint. A long SOL backtest spanning a wide price
range (e.g., $80 to $260 across 2024-2025) will use one fixed value for
its entire run; whether that remains adequate across the whole range is
an open question for the SOL-scale tests below, not assumed either way.
"""

from math import floor, log10

_NICE_FRACTIONS = (1.0, 2.0, 5.0, 10.0)

DEFAULT_ROUND_NUMBER_TARGET_PCT = 0.01   # 1% of reference price
DEFAULT_BUCKET_SIZE_TARGET_PCT = 0.001   # 0.1% of reference price


def nice_round_number(value: float) -> float:
    """
    Snap a positive value to the nearest {1, 2, 5, 10} x 10^k.

    Deterministic, pure, no historical or future data involved.
    """

    if value <= 0:
        raise ValueError("value must be positive")

    exponent = floor(log10(value))
    fraction = value / (10 ** exponent)

    nice_fraction = min(_NICE_FRACTIONS, key=lambda candidate: abs(candidate - fraction))

    return nice_fraction * (10 ** exponent)


def default_round_number_spacing(
    reference_price: float,
    target_pct: float = DEFAULT_ROUND_NUMBER_TARGET_PCT,
) -> float:
    """
    A principled, scale-appropriate `round_number_spacing` for
    MarketIntelligenceCoordinator, derived from a single already-known
    reference price - never from strategy performance.
    """

    if reference_price <= 0:
        raise ValueError("reference_price must be positive")

    return nice_round_number(reference_price * target_pct)


def default_volume_profile_bucket_size(
    reference_price: float,
    target_pct: float = DEFAULT_BUCKET_SIZE_TARGET_PCT,
) -> float:
    """
    A principled, scale-appropriate `volume_profile_bucket_size` for
    MarketIntelligenceCoordinator, derived from a single already-known
    reference price - never from strategy performance.
    """

    if reference_price <= 0:
        raise ValueError("reference_price must be positive")

    return nice_round_number(reference_price * target_pct)
