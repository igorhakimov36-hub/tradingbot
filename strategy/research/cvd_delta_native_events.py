"""
Native CVD/Delta event conversion for the Signal-Value research sprint.
RESEARCH-ONLY, pure functions, no tracker/production dependency.

Every currently-published directional Delta/CVD field
(`cvd_direction`, `price_cvd_divergence_flag`, `cvd_exhaustion_flag`,
`delta_direction`) is a PERSISTENT, per-bar reading in production - it
can read the same directional value on many consecutive bars (measured
directly in docs/cvd_delta_module_logic_audit.md, Section 6: mean
consecutive-run length 1.4-1.6 bars, longest observed run 4-7 bars
across four full TRAIN months). Treating every one of those bars as an
independent "event" would wildly overcount evidence. This module
converts a persistent reading series into one-shot, edge-triggered
RESEARCH events: an event begins only on the bar where the field's
value causally CHANGES into a directional (non-neutral) reading,
relative to the immediately preceding bar's own value - never
backdated to an earlier bar, since every reading already reflects only
information available at its own bar (proven no-lookahead in the
completed audit).
"""

from typing import Any, Literal

DirectionLabel = Literal["bullish", "bearish"]

_DIRECTIONAL_VALUES: dict[str, dict[str, DirectionLabel]] = {
    "cvd_direction": {"BULLISH": "bullish", "BEARISH": "bearish"},
    "delta_direction": {"BULLISH": "bullish", "BEARISH": "bearish"},
    "price_cvd_divergence_flag": {"bullish_divergence": "bullish", "bearish_divergence": "bearish"},
    "cvd_exhaustion_flag": {"bullish_exhaustion": "bullish", "bearish_exhaustion": "bearish"},
}

KNOWN_FIELDS = tuple(_DIRECTIONAL_VALUES.keys())


def classify_directional(field_name: str, value: Any) -> DirectionLabel | None:
    """
    Maps a field's raw published value to "bullish"/"bearish", or None
    for any non-directional reading (NEUTRAL, "none", or missing/None
    before warmup). Unknown field names raise - this module only ever
    interprets the four fields it was built for, never guesses at a
    new one.
    """

    if field_name not in _DIRECTIONAL_VALUES:
        raise ValueError(f"unknown field: {field_name!r} - expected one of {KNOWN_FIELDS}")

    return _DIRECTIONAL_VALUES[field_name].get(value)


def edge_trigger_events(field_name: str, readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    `readings`: chronologically ordered list of {"bar_i", "timestamp",
    "value"} - one entry per bar, `value` being that field's own
    published raw reading at that bar (already causally correct by
    construction - see module docstring).

    Returns one-shot events: {"field", "direction", "confirmed_at",
    "bar_i", "event_id"}. An event fires at bar i iff this bar's own
    value is directional AND differs from the immediately preceding
    bar's own value (a genuine causal transition - persistence,
    including a same-direction value repeating, produces zero
    additional events; a direct flip from bullish to bearish with no
    intervening neutral bar is its own new event, matching "one causal
    transition" without requiring an intervening opposite-direction
    reading first).
    """

    _UNSET = object()
    events: list[dict[str, Any]] = []
    previous_value: Any = _UNSET

    for reading in readings:
        direction = classify_directional(field_name, reading["value"])

        if direction is not None and reading["value"] != previous_value:
            events.append({
                "field": field_name,
                "direction": direction,
                "confirmed_at": reading["timestamp"],
                "bar_i": reading["bar_i"],
                "event_id": (field_name, reading["bar_i"], reading["timestamp"]),
            })

        previous_value = reading["value"]

    return events


def raw_directional_bar_count(field_name: str, readings: list[dict[str, Any]]) -> dict[str, int]:
    """
    The un-deduplicated "every bar this field reads directional" count
    (Step 5's "raw event count", for contrast against the one-shot
    `edge_trigger_events` count) - split bullish/bearish.
    """

    counts = {"bullish": 0, "bearish": 0}

    for reading in readings:
        direction = classify_directional(field_name, reading["value"])
        if direction is not None:
            counts[direction] += 1

    return counts
