"""Layer 3: normalization of a local civil birth time to an exact UTC instant.

This module and :mod:`vedic_chart.time.julian_day` are two distinct layers that
happen to share the ``time`` package. Layer 3 (here) turns a wall-clock date,
a wall-clock time and an IANA timezone identifier into an exact aware-UTC
datetime. Layer 4 (``julian_day``) turns such an instant into a Julian Day.
Nothing here knows about Julian Days, and nothing there knows about timezones.

Standard library only: ``datetime`` and ``zoneinfo``. No other vedic_chart
module is imported, and ``swisseph`` certainly is not.

Two deliberate refusals:

* **No timezone inference.** The zone comes only from ``timezone_id``, and only
  identifiers the IANA database accepts are accepted. Nothing is guessed from a
  country, a city, a place name or an offset, and this module defines no
  aliases of its own. Mapping a birth place to a timezone is Layer 2's job and
  Layer 2 is not built.
* **No silent disambiguation.** A wall time that does not exist, or that occurs
  twice, is rejected with a typed error naming both candidate offsets. Picking
  one for the caller would bury an hour-sized error inside a chart.

Offsets, including historical ones, come from the operating system's tzdata
database via ``zoneinfo``. Results for historical dates therefore depend on the
installed tzdata version.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InvalidTimezoneError(ValueError):
    """The timezone identifier is not one the IANA database accepts."""


class NonexistentLocalTimeError(ValueError):
    """The wall time never occurred: it falls in a DST spring-forward gap."""


class AmbiguousLocalTimeError(ValueError):
    """The wall time occurred twice: it falls in a DST fall-back overlap."""


def _format_offset(offset: timedelta | None) -> str:
    """Render a UTC offset as +HH:MM, for error messages only.

    ``timedelta`` renders a negative offset as "-1 day, 19:00:00", which is
    correct but unreadable in a message a person has to act on.
    """
    if offset is None:
        return "unknown"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "-" if total_minutes < 0 else "+"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


def _resolve_zone(timezone_id: str) -> ZoneInfo:
    """Resolve an IANA identifier, or raise InvalidTimezoneError.

    ``ZoneInfo`` signals bad input in several ways: ZoneInfoNotFoundError for an
    unknown key, ValueError for a non-normalized or escaping path, KeyError in
    some builds. All of them mean the same thing to a caller, so all of them
    become InvalidTimezoneError.
    """
    if not isinstance(timezone_id, str):
        raise InvalidTimezoneError(
            "timezone_id must be a string IANA identifier such as "
            f"'Asia/Kolkata'; got {type(timezone_id).__name__}."
        )

    try:
        return ZoneInfo(timezone_id)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise InvalidTimezoneError(
            f"Unknown timezone identifier {timezone_id!r}. It must be an IANA "
            "identifier accepted by the system tzdata database, for example "
            "'Asia/Kolkata' or 'America/New_York'. No inference from place or "
            "country names is performed here."
        ) from exc


def normalize_birth_time(
    birth_date: date, birth_time: time, timezone_id: str
) -> datetime:
    """Convert a local civil birth date and time into an exact aware-UTC instant.

    ``birth_time`` must be naive: the zone comes only from ``timezone_id``, so
    an already-aware time would mean two possibly-conflicting sources of truth
    and is rejected.

    The returned datetime is exact. Seconds and microseconds are carried through
    untouched -- nothing is rounded, truncated or snapped to a minute, because
    the result feeds a Julian Day and any adjustment here would move every
    computed position.

    Gap and overlap are detected with the standard ``fold`` technique. The same
    wall time is interpreted twice, once with ``fold=0`` and once with
    ``fold=1``. In a zone with no transition at that moment both give the same
    UTC offset. If the offsets differ, the wall time is either ambiguous or
    nonexistent, and the two cases are told apart by a round trip: converting to
    UTC and back yields the original wall time only if that wall time really
    occurred. If it does not survive the round trip it never existed (a
    spring-forward gap); if it does, it occurred twice (a fall-back overlap).

    Raises:
        InvalidTimezoneError: the identifier is not in the IANA database.
        NonexistentLocalTimeError: the wall time falls in a spring-forward gap.
        AmbiguousLocalTimeError: the wall time falls in a fall-back overlap.
        ValueError: ``birth_time`` is timezone-aware.
    """
    if birth_time.tzinfo is not None:
        raise ValueError(
            "birth_time must be a naive time; the timezone is taken only from "
            "timezone_id. Drop the tzinfo from birth_time, or pass an exact "
            "UTC datetime to Layer 4 directly."
        )

    zone = _resolve_zone(timezone_id)

    naive = datetime.combine(birth_date, birth_time)
    first = naive.replace(fold=0, tzinfo=zone)
    second = naive.replace(fold=1, tzinfo=zone)

    first_offset = first.utcoffset()
    second_offset = second.utcoffset()

    if first_offset != second_offset:
        round_trip = first.astimezone(timezone.utc).astimezone(zone)
        if round_trip.replace(tzinfo=None) != naive:
            raise NonexistentLocalTimeError(
                f"Local time {naive.isoformat()} does not exist in "
                f"{timezone_id}: the clock jumps from offset "
                f"{_format_offset(first_offset)} to "
                f"{_format_offset(second_offset)} across it. The caller must "
                "supply a wall time "
                "that occurred, or pass an exact UTC instant instead; this "
                "layer will not choose one."
            )
        raise AmbiguousLocalTimeError(
            f"Local time {naive.isoformat()} occurs twice in {timezone_id}: "
            f"once at offset {_format_offset(first_offset)} and again at "
            f"{_format_offset(second_offset)}. The "
            "caller must disambiguate, for example by passing an exact UTC "
            "instant; this layer will not choose one."
        )

    return first.astimezone(timezone.utc)
