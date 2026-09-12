"""Layer 13, part 1: the daśā table -- rows and plain text.

Pure presentation. This module computes no daśā: it is handed a finished
:class:`~vedic_chart.dasha.vimshottari.VimshottariTimeline` and turns it into
immutable rows and one block of text. Every number it prints is already in the
timeline, every instant it prints is a ``DashaPeriod`` datetime, and the only
thing it adds is a zone conversion and a layout.

Implements ``docs/LAYER13_DASHA_OUTPUT_SPEC.md`` (DRAFT v0.2):

* section 3 -- ``DashaRow``, ``resolve_zone``, ``dasha_rows``,
  ``render_dasha_text``, their validation, and the text layout.
* section 5 -- the two birth-membership columns, ``N`` and ``Q``, kept apart
  because Layer 12 section 7 documents inputs for which the nominal chain and
  the quantized chain differ. One merged "contains birth" column would erase
  exactly the case the two queries exist to expose.

Three disciplines are worth naming.

**Rows are lossless and carry no zone.** ``start_utc`` and ``end_utc`` are the
period's own datetimes, unchanged, microseconds included; the exact ``Fraction``
offsets travel with them. A caller that wants another zone, another precision or
another format converts the rows again; nothing is recoverable only from the
text.

**Truncation, never rounding.** The displayed wall time is the local time
truncated to the second, so a printed instant is never later than the true
boundary, and the balance decimal is produced by integer arithmetic
(``numerator * 10**9 // denominator``), so it is a truncation toward zero and is
labelled as one. ``round()`` appears nowhere in the package.

**The offset is printed as the zone reports it.** Historical offsets are not
whole minutes -- Asia/Kolkata was ``+05:21:10`` before 1906 -- so the offset is
never forced into ``±HH:MM``. It is also what makes a repeated local hour
readable: a Europe/London fall-back hour prints ``+01:00`` and then ``+00:00``
for the same wall time.

``zoneinfo`` is imported here and nowhere else in the package: the Layer 12 core
has no opinion about local time and must not acquire one.
"""

from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from vedic_chart.dasha.vimshottari import (
    DashaPeriod,
    DashaRangeError,
    VimshottariTimeline,
    YearConvention,
)
from vedic_chart.vedic.grahas import Graha

__all__ = ["DashaRow", "dasha_rows", "render_dasha_text", "resolve_zone"]

#: The D1 renderer's two-letter abbreviations, repeated rather than imported:
#: this module may not reach into the render layer (specification section 2),
#: and a chain of lords is not a drawing.
ABBREVIATIONS: dict[Graha, str] = {
    Graha.SUN: "Su",
    Graha.MOON: "Mo",
    Graha.MERCURY: "Me",
    Graha.VENUS: "Ve",
    Graha.MARS: "Ma",
    Graha.JUPITER: "Ju",
    Graha.SATURN: "Sa",
    Graha.RAHU: "Ra",
    Graha.KETU: "Ke",
}

#: Level 1, 2, 3 -- Mahadasha, Antardasha, Pratyantardasha.
LEVEL_NAMES: dict[int, str] = {1: "MD", 2: "AD", 3: "PD"}

#: The depth words the CLI also uses as ``--dasha`` values.
DEPTH_WORDS: dict[int, str] = {1: "md", 2: "md-ad", 3: "md-ad-pd"}

PRECISIONS: tuple[str, ...] = ("second", "day")

MAX_DEPTH = 3

#: The exact warning the specification fixes for day precision.
DAY_WARNING = (
    "WARNING: day precision - dates omit boundary times; a period listed as "
    "ending on a date may end at any instant of that date, and half-open "
    "boundaries cannot be expressed at day resolution."
)

#: Nine decimal places, produced by integer arithmetic only.
_BALANCE_SCALE = 10**9
_BALANCE_PLACES = 9

_LEVEL_COLUMN = 5
_CHAIN_COLUMN = 8
_GAP = "  "


@dataclass(frozen=True)
class DashaRow:
    """One period, ready to present and still exact.

    ``start_utc`` and ``end_utc`` are the ``DashaPeriod``'s own instants, not a
    converted copy: the row is lossless and zone-free, and the text layer is the
    only place a zone is applied. ``in_nominal_birth_chain`` and
    ``in_quantized_birth_chain`` are set by comparing ``(level, lords)`` with the
    two chains the timeline reports -- never by proximity to the birth instant,
    which would be a second, disagreeing definition of membership.
    """

    level: int
    lords: tuple[Graha, ...]
    start_utc: datetime
    end_utc: datetime
    nominal_start: Fraction
    nominal_end: Fraction
    in_nominal_birth_chain: bool
    in_quantized_birth_chain: bool


def resolve_zone(key: str) -> ZoneInfo:
    """The single zone validator of this layer.

    ``zoneinfo`` reports two unrelated failures for a key it will not load: an
    unknown key raises ``ZoneInfoNotFoundError`` (a ``KeyError`` subclass) and a
    malformed one -- empty, absolute, or containing ``..`` -- raises
    ``ValueError``. A caller should not have to catch two kinds to learn one
    thing, so both become one ``ValueError`` naming the key, chained from the
    original so nothing is hidden.

    No zone is ever inferred from coordinates or from a country: the key is the
    caller's, and this function only says whether it names a zone.
    """
    if not isinstance(key, str):
        raise TypeError(f"zone must be a str; got {type(key).__name__}.")
    try:
        return ZoneInfo(key)
    except ZoneInfoNotFoundError as error:
        raise ValueError(
            f"unknown time zone key {key!r}; it names no zone in this "
            "installation's IANA database."
        ) from error
    except ValueError as error:
        raise ValueError(
            f"malformed time zone key {key!r}: {error}"
        ) from error


def _check_timeline(timeline: object) -> None:
    if not isinstance(timeline, VimshottariTimeline):
        raise TypeError(
            "timeline must be a VimshottariTimeline; got "
            f"{type(timeline).__name__}."
        )


def _check_depth(depth: object) -> None:
    """``type(depth) is int``, then 1, 2 or 3.

    ``True`` is an ``int`` and equals 1, and ``1.0`` equals 1 as well; both are
    refused by type rather than quietly accepted, because a depth that arrived
    as a bool or a float came from somewhere that was not thinking about levels.
    """
    if type(depth) is not int:
        raise TypeError(
            f"depth must be an int; got {type(depth).__name__} ({depth!r})."
        )
    if not 1 <= depth <= MAX_DEPTH:
        raise ValueError(f"depth must be 1, 2 or 3; got {depth!r}.")


def _check_precision(precision: object) -> None:
    if not isinstance(precision, str):
        raise TypeError(
            "precision must be a str; got "
            f"{type(precision).__name__} ({precision!r})."
        )
    if precision not in PRECISIONS:
        raise ValueError(
            f"precision must be one of {PRECISIONS}; got {precision!r}."
        )


def _walk(period: DashaPeriod, depth: int) -> Iterable[DashaPeriod]:
    """The period, then its children, to ``depth`` -- pre-order."""
    yield period
    if period.level < depth:
        for child in period.children:
            yield from _walk(child, depth)


def dasha_rows(
    timeline: VimshottariTimeline, *, depth: int
) -> tuple[DashaRow, ...]:
    """Every period down to ``depth``, in pre-order: 9, 90 or 819 rows.

    The two birth chains are read once, from the timeline's own queries, and
    reduced to ``(level, lords)`` keys. A chain is unique by that key -- one
    lord per level per parent -- so comparing keys is comparing periods, without
    relying on object identity, which Layer 12 section 8 explicitly does not
    promise.
    """
    _check_timeline(timeline)
    _check_depth(depth)

    nominal_chain = {
        (period.level, period.lords)
        for period in timeline.periods_at_birth()
    }
    quantized_chain = {
        (period.level, period.lords)
        for period in timeline.active_periods_at(timeline.birth_utc)
    }

    rows: list[DashaRow] = []
    for mahadasha in timeline.mahadashas:
        for period in _walk(mahadasha, depth):
            key = (period.level, period.lords)
            rows.append(
                DashaRow(
                    level=period.level,
                    lords=period.lords,
                    start_utc=period.start_utc,
                    end_utc=period.end_utc,
                    nominal_start=period.nominal_start,
                    nominal_end=period.nominal_end,
                    in_nominal_birth_chain=key in nominal_chain,
                    in_quantized_birth_chain=key in quantized_chain,
                )
            )
    return tuple(rows)


def _chain_text(lords: tuple[Graha, ...]) -> str:
    return "-".join(ABBREVIATIONS[lord] for lord in lords)


def _lord_name(lord: Graha) -> str:
    """``Graha.JUPITER`` -> ``Jupiter``: the enum's own value, capitalised."""
    return lord.value.capitalize()


def _year_days_text(year: YearConvention) -> str:
    """``FIXED_365_256363`` -> ``365.256363``, without touching a float.

    The member names carry the decimal the convention is defined by, so the
    string is read off the name rather than formatted from ``Fraction.value``:
    no float conversion, no rounding decision, and nothing to keep in step with
    the enum but the naming rule itself.
    """
    digits = year.name.removeprefix("FIXED_")
    whole, _, rest = digits.partition("_")
    return f"{whole}.{rest}" if rest else whole


def _balance_text(balance: Fraction) -> str:
    """The exact fraction and a nine-place decimal, truncated toward zero.

    Integer arithmetic only: ``numerator * 10**9 // denominator`` is exact, so
    the decimal is a truncation of the true value and never a rounding of it.
    The string is a display artefact and is never parsed back.
    """
    scaled = balance.numerator * _BALANCE_SCALE // balance.denominator
    whole, remainder = divmod(scaled, _BALANCE_SCALE)
    decimal = f"{whole}.{remainder:0{_BALANCE_PLACES}d}"
    return f"{balance.numerator}/{balance.denominator} = {decimal}"


def _format_instant(
    moment: datetime, zone: ZoneInfo, key: str, precision: str
) -> str:
    """One boundary, converted once and printed per section 3(a) or 3(b).

    Within a zone offset of ``datetime``'s limits the conversion itself cannot
    be done -- a positive offset overflows near ``datetime.max``, a negative one
    underflows near ``datetime.min`` -- and ``astimezone`` raises
    ``OverflowError``. That becomes ``DashaRangeError``, the core's own type for
    "this instant is outside the representable range", naming the timestamp and
    the zone. Nothing else in this module catches ``OverflowError``, and nothing
    catches ``ValueError``.
    """
    try:
        local = moment.astimezone(zone)
    except OverflowError as error:
        raise DashaRangeError(
            f"the timestamp {moment!r} cannot be shown in the zone {key!r}: "
            "the converted local time would fall outside the datetime range."
        ) from error
    if precision == "day":
        return local.date().isoformat()
    return local.replace(microsecond=0).isoformat(sep=" ", timespec="seconds")


def _header(
    timeline: VimshottariTimeline,
    key: str,
    depth: int,
    precision: str,
    birth_text: str,
) -> list[str]:
    """Section 3's header block.

    It states what the timeline holds and nothing more. In particular there is
    no pada: ``VimshottariTimeline`` carries no pada field, and inventing one
    here would be a classification calculation in a presentation module.
    """
    lines = [
        f"Vimshottari dasha  |  Moon {timeline.moon_sidereal_longitude!r} "
        f"({timeline.nakshatra_name} #{timeline.nakshatra_number})  |  "
        f"lord {_lord_name(timeline.lord)}",
        f"Birth {birth_text} ({key})  |  "
        f"year {_year_days_text(timeline.year)} days  |  "
        f"depth {DEPTH_WORDS[depth]}",
        "Nominal balance of the first Mahadasha at birth: "
        f"{_balance_text(timeline.balance_years)} years "
        "(nominal; decimal truncated to 9 places)",
    ]
    if precision == "day":
        lines.append(
            "Intervals are half-open [start, end). Dates are the local "
            f"calendar dates of the boundaries in {key}."
        )
        lines.append(DAY_WARNING)
    else:
        lines.append(
            "Intervals are half-open [start, end). Timestamps are truncated "
            f"to the second and shown in {key} with the UTC offset."
        )
    lines.append(
        "The first Mahadasha begins at or before birth (before birth unless "
        "the core's elapsed nakshatra fraction is zero); its pre-birth part "
        "is listed."
    )
    lines.append(
        "Columns: N = period contains the birth instant by exact nominal "
        "offset; Q = period contains the birth timestamp after microsecond "
        "quantization."
    )
    return lines


def render_dasha_text(
    timeline: VimshottariTimeline,
    *,
    zone: str,
    depth: int = 2,
    precision: str = "second",
) -> str:
    """The daśā table as plain text: a header block and one line per period.

    Computes nothing about daśās. Every quantity comes from ``timeline``; the
    only transformations are the zone conversion, the truncation to the second
    (or to the local date) and the layout. The text ends with exactly one
    newline and carries no diagnostics -- a caller writing it to a file or to
    stdout writes the table and nothing else.
    """
    _check_timeline(timeline)
    _check_depth(depth)
    _check_precision(precision)
    resolved = resolve_zone(zone)

    rows = dasha_rows(timeline, depth=depth)
    starts = [
        _format_instant(row.start_utc, resolved, zone, precision)
        for row in rows
    ]
    ends = [
        _format_instant(row.end_utc, resolved, zone, precision) for row in rows
    ]
    # The Birth line is always at second precision with its exact UTC offset:
    # --dasha-precision / ``precision`` governs the period rows only.
    birth_text = _format_instant(timeline.birth_utc, resolved, zone, "second")

    stamp_width = max(
        [len("Start"), len("End")] + [len(text) for text in starts + ends]
    )

    lines = _header(timeline, zone, depth, precision, birth_text)
    lines.append("")
    lines.append(
        _GAP.join(
            (
                f"{'Level':<{_LEVEL_COLUMN}}",
                f"{'Chain':<{_CHAIN_COLUMN}}",
                f"{'Start':<{stamp_width}}",
                f"{'End':<{stamp_width}}",
                "N",
                "Q",
            )
        ).rstrip()
    )
    for row, start, end in zip(rows, starts, ends):
        lines.append(
            _GAP.join(
                (
                    f"{LEVEL_NAMES[row.level]:<{_LEVEL_COLUMN}}",
                    f"{_chain_text(row.lords):<{_CHAIN_COLUMN}}",
                    f"{start:<{stamp_width}}",
                    f"{end:<{stamp_width}}",
                    "N" if row.in_nominal_birth_chain else " ",
                    "Q" if row.in_quantized_birth_chain else " ",
                )
            ).rstrip()
        )

    return "\n".join(lines) + "\n"
