"""Layer 1: the validated natal-chart calculation request.

This layer defines and validates *what the caller asked for*, and nothing about
what it means. It resolves no places (Layer 2), converts no timezones (Layer 3),
does no calendar arithmetic (Layer 4) and knows no astronomy (Layer 5 and
above).

Pure standard library, and unlike Layer 2 it shares nothing with any other
layer -- not even an exception type. Timezone concepts do not exist here at all,
so ``zoneinfo`` is deliberately absent: a request that could carry a timezone
would let one slip past Layer 3, which is the only layer entitled to resolve
one.

Values pass through exactly as supplied. Nothing is rounded, trimmed,
normalized or converted; the place query in particular is stored verbatim,
because normalizing queries is the resolver's business.

Python's ``date`` is proleptic Gregorian -- it extends the Gregorian rules back
past their 1582 adoption -- the same assumption Layer 4 documents for its
Julian Day conversion.
"""

from dataclasses import dataclass
from datetime import date, datetime, time


class InvalidBirthDateError(ValueError):
    """The birth date is malformed, impossible, or carries a time component."""


class InvalidBirthTimeError(ValueError):
    """The birth time is malformed, impossible, or carries a timezone."""


class InvalidPlaceQueryError(ValueError):
    """The place query is missing, blank, or not a string."""


@dataclass(frozen=True)
class BirthChartRequest:
    """A caller's request for a natal chart, validated but not interpreted.

    Three fields and no more. There is deliberately no latitude, longitude, UTC
    offset or timezone identifier here: a request describes a birth *as stated*,
    and turning a place into coordinates and a zone is Layer 2's job, while
    turning a wall time into an instant is Layer 3's. Accepting any of those
    here would let a caller bypass those layers and their validation.
    """

    birth_date: date
    birth_time: time
    place_query: str

    def __post_init__(self) -> None:
        if not isinstance(self.birth_date, date):
            raise InvalidBirthDateError(
                "birth_date must be a datetime.date; got "
                f"{type(self.birth_date).__name__}."
            )
        if isinstance(self.birth_date, datetime):
            raise InvalidBirthDateError(
                "birth_date must be a plain datetime.date, not a datetime. A "
                "datetime carries a time and possibly a timezone, which would "
                "smuggle zone information past Layer 3 -- the only layer "
                "entitled to resolve one. Pass the calendar date and the wall "
                "time separately."
            )

        if not isinstance(self.birth_time, time):
            raise InvalidBirthTimeError(
                "birth_time must be a datetime.time; got "
                f"{type(self.birth_time).__name__}."
            )
        if self.birth_time.tzinfo is not None:
            raise InvalidBirthTimeError(
                "birth_time must be naive. The timezone comes only from "
                "resolving the place (Layer 2) and normalizing the wall time "
                "against it (Layer 3); a timezone embedded here would be a "
                "second, competing source of truth."
            )

        if not isinstance(self.place_query, str):
            raise InvalidPlaceQueryError(
                "place_query must be a string; got "
                f"{type(self.place_query).__name__}."
            )
        if not self.place_query.strip():
            raise InvalidPlaceQueryError(
                "place_query must not be blank; got "
                f"{self.place_query!r}."
            )

    @classmethod
    def from_components(
        cls,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
        second: int = 0,
        microsecond: int = 0,
        *,
        place_query: str,
    ) -> "BirthChartRequest":
        """Build a request from raw numeric components.

        This factory is where impossible calendar dates and wall times get their
        typed rejection. An already-constructed ``date`` or ``time`` object
        cannot be invalid -- the standard library refuses to build one -- so
        ``__post_init__`` can only check *kinds* of value, never ranges. Callers
        holding raw numbers (a form submission, a parsed record) come through
        here instead, and get InvalidBirthDateError or InvalidBirthTimeError
        rather than a bare ValueError from deep inside ``datetime``.
        """
        try:
            birth_date = date(year, month, day)
        except (ValueError, TypeError) as exc:
            raise InvalidBirthDateError(
                f"Invalid birth date (year={year!r}, month={month!r}, "
                f"day={day!r}): {exc}"
            ) from exc

        try:
            birth_time = time(hour, minute, second, microsecond)
        except (ValueError, TypeError) as exc:
            raise InvalidBirthTimeError(
                f"Invalid birth time (hour={hour!r}, minute={minute!r}, "
                f"second={second!r}, microsecond={microsecond!r}): {exc}"
            ) from exc

        return cls(
            birth_date=birth_date,
            birth_time=birth_time,
            place_query=place_query,
        )
