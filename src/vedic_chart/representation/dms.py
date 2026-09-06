"""Layer 9 display derivation: degrees, minutes and seconds.

Everything here is **non-authoritative display data**. The authoritative value
is always the full-precision float on the frozen ``BirthChart``; a ``DMS`` is
computed on demand, is never stored on any Layer 9 object, is never compared
against a calculated value, and is never fed back into any calculation.

Policy: **truncation toward zero at every stage**, never rounding (owner
decision L-3). Truncation guarantees the displayed value can never appear to
cross a rashi, nakshatra or pada boundary that the authoritative value did not
cross: 29.999999 deg displays as 29 deg 59' 59", never as 30 deg 00' 00".
Rounding with carry could do exactly that, so ``round()`` appears nowhere in
this package -- the test suite parses the AST to prove it.

A 60-carry is impossible by construction: minutes and seconds are each taken
from a remainder strictly below one unit of the division above, and truncation
only ever moves a value down.

Inputs are degrees *within a division* (degrees in rashi, in nakshatra, in
pada), which are non-negative by definition, so a negative value is a caller
error and is rejected rather than displayed.
"""

import math
from dataclasses import dataclass

SECONDS_PER_MINUTE = 60.0
MINUTES_PER_DEGREE = 60.0


@dataclass(frozen=True)
class DMS:
    """A degrees/minutes/seconds triple for display only.

    ``seconds`` is a float because a caller may ask for fractional seconds.
    Nothing in the engine consumes this type; it exists for renderers.
    """

    degrees: int
    minutes: int
    seconds: float

    def __str__(self) -> str:
        """Format as ``13°47'17"`` (or ``13°47'17.55"`` with decimals).

        Pure formatting: it derives no new value and rounds nothing. Whole
        seconds print without a decimal point; fractional seconds print exactly
        the digits the truncation kept.
        """
        if self.seconds == int(self.seconds):
            seconds_text = str(int(self.seconds))
        else:
            seconds_text = repr(self.seconds)
        return f"{self.degrees}°{self.minutes}'{seconds_text}\""


def _validate_degrees(value_degrees: float) -> None:
    if isinstance(value_degrees, bool) or not isinstance(
        value_degrees, (int, float)
    ):
        raise ValueError(
            f"value_degrees must be a number in degrees; got {value_degrees!r}."
        )
    if not math.isfinite(value_degrees):
        raise ValueError(f"value_degrees must be finite; got {value_degrees!r}.")
    if value_degrees < 0.0:
        raise ValueError(
            "value_degrees must not be negative: degrees within a division are "
            f"non-negative by definition; got {value_degrees!r}."
        )


def _validate_decimals(seconds_decimals: int) -> None:
    if isinstance(seconds_decimals, bool) or not isinstance(
        seconds_decimals, int
    ):
        raise ValueError(
            "seconds_decimals must be a non-negative int; got "
            f"{seconds_decimals!r}."
        )
    if seconds_decimals < 0:
        raise ValueError(
            "seconds_decimals must be a non-negative int; got "
            f"{seconds_decimals!r}."
        )


def to_dms(value_degrees: float, seconds_decimals: int = 0) -> DMS:
    """Convert a non-negative degree value to a display ``DMS``.

    Truncation toward zero is applied at every stage: the whole degrees, then
    the whole minutes of the remainder, then the seconds of what is left,
    truncated to ``seconds_decimals`` decimal places with ``math.floor`` on the
    scaled (non-negative) value. No stage rounds, so no stage can carry.
    """
    _validate_degrees(value_degrees)
    _validate_decimals(seconds_decimals)

    value = float(value_degrees)

    degrees = int(value)
    minutes_total = (value - degrees) * MINUTES_PER_DEGREE
    minutes = int(minutes_total)
    seconds_exact = (minutes_total - minutes) * SECONDS_PER_MINUTE

    scale = 10**seconds_decimals
    seconds = math.floor(seconds_exact * scale) / scale

    return DMS(degrees=degrees, minutes=minutes, seconds=seconds)
