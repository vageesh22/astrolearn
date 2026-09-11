"""Layer 12, part 1: the Vimshottari dasha core.

Pure module. It reads two constants modules from Layer 7 -- the nakshatra names
and the ``Graha`` enum -- and otherwise nothing but the standard library. No
ephemeris is opened, no session is entered, no chart is consulted, nothing is
written and no clock is read: every instant this module produces is a function
of the birth anchor and an exact rational offset, so there is no implicit
"now" anywhere in the layer.

Implements ``docs/LAYER12_VIMSHOTTARI_SPEC.md`` (DRAFT v0.2):

* section 4  -- the nine lords, their years, and the cyclic order, all
  immutable: a tuple for the sequence, a ``MappingProxyType`` for the years,
  ``Fraction`` members for the two year conventions.
* section 5  -- decision D1. The nakshatra index is the one Layer 7 would
  compute, because it is computed the same way: normalise with ``% 360.0``,
  form the double ``normalized * 27.0 / 360.0``, floor it. The elapsed fraction
  then continues *from that same double*, exactly, as ``Fraction(p) - index``.
  This is the only way to keep the index identical to the frozen chart's while
  never producing a negative elapsed fraction (see the spec's analysis of the
  four doubles that classify one nakshatra higher in float than in exact
  rational arithmetic).
* section 6  -- every nominal duration and offset is an exact ``Fraction`` of
  nominal years measured from the birth instant, negative before birth. Nine
  children partition every parent exactly, because the nine lord-years sum to
  120 and the arithmetic is rational.
* section 7  -- decision D2. One quantization rule for every boundary:
  ``floor(offset * year_days * MICROSECONDS_PER_DAY)`` microseconds from the
  anchor, floored toward minus infinity for negative offsets too. Shared
  boundaries are therefore literally the same arithmetic on the same
  ``Fraction`` and come out equal, and the intervals are contiguous and
  monotone. Intervals are half-open ``[start_utc, end_utc)``.
* section 8  -- the public surface, and the two deliberately different
  queries: ``periods_at_birth`` answers from the exact nominal offsets,
  ``active_periods_at`` from the quantized datetimes. Where a post-birth
  remainder is shorter than one microsecond the two disagree, and no special
  case is added to hide that.

Nothing is rounded anywhere (rule 12 of the frozen calculation contract): the
only deliberate loss of information is the single documented floor to whole
microseconds, which is a presentation step -- the ``Fraction`` fields remain
the exact quantities and no arithmetic is ever done on the datetimes.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from fractions import Fraction
from types import MappingProxyType
from typing import Mapping

from vedic_chart.vedic.divisions import NAKSHATRA_NAMES
from vedic_chart.vedic.grahas import Graha

__all__ = [
    "CYCLE_YEARS",
    "DashaPeriod",
    "DashaRangeError",
    "LORD_SEQUENCE",
    "LORD_YEARS",
    "MICROSECONDS_PER_DAY",
    "NAKSHATRA_COUNT",
    "VimshottariTimeline",
    "YearConvention",
    "build_vimshottari",
]


#: The cyclic order of the nine lords, rotated so that index 0 (Ashwini) is
#: Ketu. BPHS lists the order from Krittika -- Sun, Moon, Mars, Rahu, Jupiter,
#: Saturn, Mercury, Ketu, Venus -- and Krittika is index 2, so rotating that
#: list back by two gives the sequence below and makes the lord of a nakshatra
#: simply ``LORD_SEQUENCE[index % 9]`` with no offset table.
LORD_SEQUENCE: tuple[Graha, ...] = (
    Graha.KETU,
    Graha.VENUS,
    Graha.SUN,
    Graha.MOON,
    Graha.MARS,
    Graha.RAHU,
    Graha.JUPITER,
    Graha.SATURN,
    Graha.MERCURY,
)

# Proxied, not exposed: a caller who could write ``LORD_YEARS[Graha.SUN] = 7``
# would silently change every later calculation in the process. The private
# dict is never handed out, so the proxy is not a window onto anything a
# caller holds.
_LORD_YEARS: dict[Graha, int] = {
    Graha.KETU: 7,
    Graha.VENUS: 20,
    Graha.SUN: 6,
    Graha.MOON: 10,
    Graha.MARS: 7,
    Graha.RAHU: 18,
    Graha.JUPITER: 16,
    Graha.SATURN: 19,
    Graha.MERCURY: 17,
}

LORD_YEARS: Mapping[Graha, int] = MappingProxyType(_LORD_YEARS)

#: The 120 years of the cycle. Equal to ``sum(LORD_YEARS.values())`` by
#: construction, and asserted to be so by the tests rather than computed here,
#: so that a typo in the table cannot quietly redefine the cycle.
CYCLE_YEARS: int = 120

NAKSHATRA_COUNT: int = 27

MICROSECONDS_PER_DAY: int = 86_400_000_000

_LORD_COUNT = len(LORD_SEQUENCE)

#: Levels of the timeline: 1 Mahadasha, 2 Antardasha, 3 Pratyantardasha.
_MAX_LEVEL = 3

_MIN_UTC = datetime.min.replace(tzinfo=timezone.utc)
_MAX_UTC = datetime.max.replace(tzinfo=timezone.utc)
_ONE_MICROSECOND = timedelta(microseconds=1)


class YearConvention(Enum):
    """The length of one nominal dasha-year, in days, exactly.

    Both members are built from integer ratios. ``Fraction(365.256363)`` would
    be the *binary neighbour* of the decimal, not the decimal, and the two
    differ in the 17th digit -- enough to move a 120-year boundary by
    microseconds. The classical text fixes the lords, the years and the
    proportional rule but not the length of a year in days, so the convention
    is a required argument with no default: nothing in this layer picks one
    for the caller.
    """

    FIXED_365_25 = Fraction(1461, 4)
    FIXED_365_256363 = Fraction(365256363, 1000000)


class DashaRangeError(ValueError):
    """A boundary of the cycle falls outside ``datetime``'s supported range.

    A ``ValueError`` because it is a statement about the inputs, not an
    arithmetic surprise: the cycle reaches up to 20 nominal years before the
    birth and up to 120 after it, so births in the first approximately twenty
    calendar years of ``datetime``'s supported range (the pre-birth start would
    underflow ``datetime.min``) or in roughly its last 120 years (the cycle end
    would overflow ``datetime.max``) cannot carry a whole cycle. Raised instead
    of letting ``OverflowError`` escape, and raised *before* any datetime
    arithmetic is attempted; also raised when converting an aware non-UTC
    instant to UTC would itself overflow.

    Also raised by ``active_periods_at`` for an instant outside the cycle
    (decision D3): the timeline covers one cycle and nothing else, so there is
    no period to return and no honest way to invent one.
    """


def _classify_moon(longitude: float) -> tuple[float, int, Fraction]:
    """Normalise a longitude and split it into nakshatra index and fraction.

    The single place in this layer where a float becomes a rational. Returns
    ``(normalized, nakshatra_index, elapsed_fraction)`` where ``normalized`` is
    the ``% 360.0`` value actually classified, the index is 0-based and
    identical to what ``vedic_chart.vedic.divisions.classify`` stores for the
    same double, and the elapsed fraction is the exact rational part of the
    very double Layer 7 floors, hence always in ``[0, 1)``.

    ``Fraction(p)`` is exact: every finite double is a dyadic rational. So the
    only approximation in the whole layer is the one already present in the
    input longitude.

    The rejected class matters. Negative doubles of magnitude at most 2**-45 --
    half an ULP of 360 -- normalise under Python's float ``%`` to ``360.0``
    itself, for which the frozen classifier's own assertion fails with index
    27. Rather than index 27 or nudge the value (rule 12 forbids nudging),
    this raises.

    Exceptions, by kind of failure:

    * ``TypeError`` -- the value is not an ``int`` or ``float`` (``bool`` is
      excluded explicitly, being an ``int`` subclass).
    * ``ValueError`` -- an ``int`` too large to convert to a ``float`` (the
      ``OverflowError`` that ``float()`` raises is translated so that it never
      escapes this layer); a non-finite value; a value whose ``% 360.0`` is
      ``360.0`` (the rejected class above); and, as a guard, a computed index
      outside ``0..26``. That last guard mirrors the assertion in the frozen
      ``classify`` but is a real exception, so ``python -O`` cannot strip it;
      with the ``360.0`` rejection in place it is unreachable from any
      accepted input.
    """
    if isinstance(longitude, bool) or not isinstance(longitude, (int, float)):
        raise TypeError(
            "moon_sidereal_longitude must be a float or an int; got "
            f"{type(longitude).__name__}."
        )

    try:
        value = float(longitude)
    except OverflowError as error:  # an int far too large to be a longitude
        raise ValueError(
            "moon_sidereal_longitude is too large to represent as a float."
        ) from error

    if not math.isfinite(value):
        raise ValueError(
            f"moon_sidereal_longitude must be finite; got {value!r}."
        )

    normalized = value % 360.0
    if not normalized < 360.0:
        raise ValueError(
            "longitude normalises to 360.0, which no nakshatra contains; got "
            f"{longitude!r}."
        )

    product = normalized * 27.0 / 360.0
    index = int(product)
    if not 0 <= index < NAKSHATRA_COUNT:
        raise ValueError(
            f"longitude {longitude!r} classifies to nakshatra index {index}."
        )

    return normalized, index, Fraction(product) - index


def _lord_order(first: Graha) -> tuple[Graha, ...]:
    """The nine lords starting at ``first``, then ``LORD_SEQUENCE`` cyclically.

    Own lord first at every level, which is the classical subdivision order and
    the one deva.guru labels "Default".
    """
    start = LORD_SEQUENCE.index(first)
    return tuple(
        LORD_SEQUENCE[(start + step) % _LORD_COUNT]
        for step in range(_LORD_COUNT)
    )


def _quantize(offset_years: Fraction, year_days: Fraction) -> int:
    """Whole microseconds from the anchor for one exact nominal offset (D2).

    ``math.floor`` on a ``Fraction`` is exact and floors toward minus infinity,
    so a negative offset -- the pre-birth Mahadasha start -- lands no later
    than its exact instant, exactly as a positive one does. One rule, no sign
    branch, hence monotone: a larger offset never yields an earlier instant.
    """
    return math.floor(offset_years * year_days * MICROSECONDS_PER_DAY)


def _microseconds_between(earlier: datetime, later: datetime) -> int:
    return (later - earlier) // _ONE_MICROSECOND


def _normalize_instant(value: datetime, label: str) -> datetime:
    """Validate one instant and convert it to UTC (the Layer 4 convention).

    A ``date`` is not a ``datetime`` and is rejected by type; a naive datetime,
    or one whose ``tzinfo.utcoffset()`` returns ``None``, is rejected by value,
    because either would leave the instant undetermined. The conversion itself
    can overflow for an aware non-UTC value within a few hours of
    ``datetime``'s limits; that becomes ``DashaRangeError`` so no
    ``OverflowError`` escapes this layer.
    """
    if not isinstance(value, datetime):
        raise TypeError(
            f"{label} must be a datetime.datetime; got "
            f"{type(value).__name__}."
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{label} must be timezone-aware; got the naive value {value!r}."
        )
    try:
        return value.astimezone(timezone.utc)
    except OverflowError as error:
        raise DashaRangeError(
            f"{label} {value!r} cannot be converted to UTC without leaving "
            "the datetime range."
        ) from error


@dataclass(frozen=True)
class DashaPeriod:
    """One period at one level, with both its exact and its quantized form.

    The ``Fraction`` fields are the arithmetic; the datetimes are their
    presentation, produced by the single rule of section 7 and never used to
    compute anything. ``nominal_years`` is the *full* length of the period
    whether or not the birth falls inside it -- the birth Mahadasha is its
    lord's full span, and the post-birth balance is a separate quantity on the
    timeline.
    """

    level: int
    lords: tuple[Graha, ...]
    nominal_years: Fraction
    nominal_start: Fraction
    nominal_end: Fraction
    start_utc: datetime
    end_utc: datetime
    children: tuple["DashaPeriod", ...]

    @property
    def lord(self) -> Graha:
        """The lord of this period itself: the last link of the chain."""
        return self.lords[-1]


def _contains_offset(period: DashaPeriod, offset: Fraction) -> bool:
    return period.nominal_start <= offset < period.nominal_end


def _contains_instant(period: DashaPeriod, instant: datetime) -> bool:
    return period.start_utc <= instant < period.end_utc


@dataclass(frozen=True)
class VimshottariTimeline:
    """One Vimshottari cycle: nine Mahadashas, each 9 x 9 subdivided.

    The cycle begins at the *true* start of the birth Mahadasha,
    ``elapsed_years`` before the birth, and ends ``120 - elapsed_years``
    nominal years after it. It is not "120 years from birth" and it is not a
    requested window; there is no second cycle.
    """

    birth_utc: datetime
    year: YearConvention
    moon_sidereal_longitude: float
    normalized_longitude: float
    nakshatra_index: int
    nakshatra_number: int
    nakshatra_name: str
    lord: Graha
    elapsed_fraction: Fraction
    remaining_fraction: Fraction
    elapsed_years: Fraction
    balance_years: Fraction
    cycle_start_utc: datetime
    cycle_end_utc: datetime
    mahadashas: tuple[DashaPeriod, ...]

    def periods_at_birth(
        self,
    ) -> tuple[DashaPeriod, DashaPeriod, DashaPeriod]:
        """The chain the Moon longitude defines, by exact nominal membership.

        Offset 0 -- the birth -- located in ``[nominal_start, nominal_end)`` at
        each level in turn. The subdivision is of the *full* parent from its
        pre-birth start: it is never restarted at the birth and the balance is
        never subdivided on its own, both of which would give a different
        chain (the tests show that they do).

        This answer always exists and is always the astrologically intended
        one. It can differ from ``active_periods_at(birth_utc)`` when a
        post-birth remainder is shorter than one microsecond; see section 7.
        """
        chain: list[DashaPeriod] = []
        candidates = self.mahadashas
        offset = Fraction(0)
        for _level in range(_MAX_LEVEL):
            for period in candidates:
                if _contains_offset(period, offset):
                    chain.append(period)
                    candidates = period.children
                    break
            else:  # pragma: no cover - the children partition the parent
                raise RuntimeError(
                    "the nominal subdivision does not cover the birth offset."
                )
        return (chain[0], chain[1], chain[2])

    def active_periods_at(
        self, instant: datetime
    ) -> tuple[DashaPeriod, DashaPeriod, DashaPeriod]:
        """The chain in force at ``instant``, by the quantized intervals.

        ``instant`` is validated and normalised exactly like ``birth_utc``.
        Intervals are half-open, so an instant equal to a ``start_utc`` belongs
        to that period and one equal to an ``end_utc`` belongs to the next;
        a period whose quantized interval collapsed to nothing is skipped by
        that rule alone, with no special case. Outside the cycle -- before
        ``cycle_start_utc`` or at or after ``cycle_end_utc`` -- there is no
        period, so this raises ``DashaRangeError`` (decision D3) rather than
        clamping to an end.
        """
        moment = _normalize_instant(instant, "instant")
        if moment < self.cycle_start_utc or moment >= self.cycle_end_utc:
            raise DashaRangeError(
                f"{moment!r} lies outside the cycle "
                f"[{self.cycle_start_utc!r}, {self.cycle_end_utc!r})."
            )

        chain: list[DashaPeriod] = []
        candidates = self.mahadashas
        for _level in range(_MAX_LEVEL):
            for period in candidates:
                if _contains_instant(period, moment):
                    chain.append(period)
                    candidates = period.children
                    break
            else:  # pragma: no cover - the children tile the parent exactly
                raise RuntimeError(
                    f"the quantized subdivision does not cover {moment!r}."
                )
        return (chain[0], chain[1], chain[2])


def _check_range(
    anchor: datetime,
    lowest_offset: Fraction,
    highest_offset: Fraction,
    year_days: Fraction,
) -> None:
    """Refuse a birth whose cycle would leave ``datetime``'s range.

    Checked on the two extreme offsets only, and before any datetime
    arithmetic: the quantization is monotone, so if both ends fit, everything
    between them fits. Doing it this way means no ``OverflowError`` is ever
    raised and caught mid-construction.
    """
    lowest = _quantize(lowest_offset, year_days)
    highest = _quantize(highest_offset, year_days)
    floor_room = _microseconds_between(_MIN_UTC, anchor)
    ceiling_room = _microseconds_between(anchor, _MAX_UTC)

    if lowest < -floor_room:
        raise DashaRangeError(
            f"the cycle starting {lowest_offset} nominal years from birth "
            f"{anchor!r} falls before datetime.min."
        )
    if highest > ceiling_room:
        raise DashaRangeError(
            f"the cycle ending {highest_offset} nominal years from birth "
            f"{anchor!r} falls after datetime.max."
        )


def build_vimshottari(
    moon_sidereal_longitude: float,
    birth_utc: datetime,
    year: YearConvention,
) -> VimshottariTimeline:
    """Build one Vimshottari cycle from a Moon longitude and a birth instant.

    ``year`` is required and has no default (section 1): the two conventions
    move a 120-year boundary by days, and picking one silently would make the
    result depend on an invisible choice.
    """
    if not isinstance(year, YearConvention):
        raise TypeError(
            "year must be a YearConvention member; got "
            f"{type(year).__name__}."
        )

    normalized, index, elapsed_fraction = _classify_moon(
        moon_sidereal_longitude
    )
    anchor = _normalize_instant(birth_utc, "birth_utc")

    birth_lord = LORD_SEQUENCE[index % _LORD_COUNT]
    remaining_fraction = 1 - elapsed_fraction
    elapsed_years = elapsed_fraction * LORD_YEARS[birth_lord]
    balance_years = remaining_fraction * LORD_YEARS[birth_lord]

    year_days = year.value
    cycle_start_offset = -elapsed_years
    cycle_end_offset = CYCLE_YEARS - elapsed_years
    _check_range(anchor, cycle_start_offset, cycle_end_offset, year_days)

    def instant(offset: Fraction) -> datetime:
        return anchor + timedelta(microseconds=_quantize(offset, year_days))

    mahadashas: list[DashaPeriod] = []
    mahadasha_cursor = cycle_start_offset
    for mahadasha_lord in _lord_order(birth_lord):
        mahadasha_years = Fraction(LORD_YEARS[mahadasha_lord])
        mahadasha_start = mahadasha_cursor
        mahadasha_end = mahadasha_start + mahadasha_years

        antardashas: list[DashaPeriod] = []
        antardasha_cursor = mahadasha_start
        for antardasha_lord in _lord_order(mahadasha_lord):
            antardasha_years = (
                mahadasha_years * LORD_YEARS[antardasha_lord] / CYCLE_YEARS
            )
            antardasha_start = antardasha_cursor
            antardasha_end = antardasha_start + antardasha_years

            pratyantars: list[DashaPeriod] = []
            pratyantar_cursor = antardasha_start
            for pratyantar_lord in _lord_order(antardasha_lord):
                pratyantar_years = (
                    antardasha_years
                    * LORD_YEARS[pratyantar_lord]
                    / CYCLE_YEARS
                )
                pratyantar_start = pratyantar_cursor
                pratyantar_end = pratyantar_start + pratyantar_years
                pratyantars.append(
                    DashaPeriod(
                        level=3,
                        lords=(
                            mahadasha_lord,
                            antardasha_lord,
                            pratyantar_lord,
                        ),
                        nominal_years=pratyantar_years,
                        nominal_start=pratyantar_start,
                        nominal_end=pratyantar_end,
                        start_utc=instant(pratyantar_start),
                        end_utc=instant(pratyantar_end),
                        children=(),
                    )
                )
                pratyantar_cursor = pratyantar_end

            antardashas.append(
                DashaPeriod(
                    level=2,
                    lords=(mahadasha_lord, antardasha_lord),
                    nominal_years=antardasha_years,
                    nominal_start=antardasha_start,
                    nominal_end=antardasha_end,
                    start_utc=instant(antardasha_start),
                    end_utc=instant(antardasha_end),
                    children=tuple(pratyantars),
                )
            )
            antardasha_cursor = antardasha_end

        mahadashas.append(
            DashaPeriod(
                level=1,
                lords=(mahadasha_lord,),
                nominal_years=mahadasha_years,
                nominal_start=mahadasha_start,
                nominal_end=mahadasha_end,
                start_utc=instant(mahadasha_start),
                end_utc=instant(mahadasha_end),
                children=tuple(antardashas),
            )
        )
        mahadasha_cursor = mahadasha_end

    return VimshottariTimeline(
        birth_utc=anchor,
        year=year,
        moon_sidereal_longitude=float(moon_sidereal_longitude),
        normalized_longitude=normalized,
        nakshatra_index=index,
        nakshatra_number=index + 1,
        nakshatra_name=NAKSHATRA_NAMES[index],
        lord=birth_lord,
        elapsed_fraction=elapsed_fraction,
        remaining_fraction=remaining_fraction,
        elapsed_years=elapsed_years,
        balance_years=balance_years,
        cycle_start_utc=mahadashas[0].start_utc,
        cycle_end_utc=mahadashas[-1].end_utc,
        mahadashas=tuple(mahadashas),
    )
