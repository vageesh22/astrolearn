"""Layer 2, part 1: the birth-place data model and the resolver boundary.

This module defines what a resolved birth place *is* and the protocol any
resolver must satisfy. It performs no lookups of its own and makes no network
calls.

It imports the standard library plus exactly one thing from the rest of the
project: :class:`~vedic_chart.time.local_time.InvalidTimezoneError`. A bad IANA
identifier is one condition, so it gets one exception type across the codebase
rather than a near-duplicate per layer. Nothing else from vedic_chart is
imported here -- not the ephemeris, not the astronomy, sidereal or vedic layers.
"""

import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from vedic_chart.time.local_time import InvalidTimezoneError

MIN_LATITUDE = -90.0
MAX_LATITUDE = 90.0
MIN_LONGITUDE = -180.0
MAX_LONGITUDE = 180.0


class InvalidCoordinateError(ValueError):
    """A latitude or longitude is out of range, or is not a finite number."""


class PlaceNotFoundError(LookupError):
    """A resolver could not resolve the place query it was given."""


def _validate_coordinate(
    value: float, name: str, minimum: float, maximum: float
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidCoordinateError(
            f"{name} must be a number in degrees; got {value!r}."
        )
    if not math.isfinite(value):
        raise InvalidCoordinateError(
            f"{name} must be a finite number; got {value!r}."
        )
    if not minimum <= value <= maximum:
        raise InvalidCoordinateError(
            f"{name} must be between {minimum} and {maximum} degrees "
            f"inclusive; got {value!r}."
        )


@dataclass(frozen=True)
class ResolvedLocation:
    """A birth place resolved to coordinates and a timezone.

    Latitude is north-positive and longitude is east-positive, both in degrees.

    The timezone is stored as an IANA identifier and **never** as a UTC offset.
    A place's offset is not a property of the place: it changes with the date,
    because zones revise their rules and their daylight-saving behaviour over
    time. India ran +06:30 during the second world war and +05:30 since. An
    offset frozen into this model would silently be wrong for some birth dates.
    Resolving an identifier to an offset *for a particular instant* is Layer 3's
    job, and only Layer 3 has the instant needed to do it correctly.
    """

    canonical_name: str
    latitude: float
    longitude: float
    timezone_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_name, str) or not self.canonical_name.strip():
            raise ValueError(
                "canonical_name must be a non-blank string; got "
                f"{self.canonical_name!r}."
            )

        _validate_coordinate(self.latitude, "latitude", MIN_LATITUDE, MAX_LATITUDE)
        _validate_coordinate(
            self.longitude, "longitude", MIN_LONGITUDE, MAX_LONGITUDE
        )

        if not isinstance(self.timezone_id, str):
            raise InvalidTimezoneError(
                "timezone_id must be a string IANA identifier; got "
                f"{type(self.timezone_id).__name__}."
            )
        try:
            ZoneInfo(self.timezone_id)
        except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
            raise InvalidTimezoneError(
                f"Unknown timezone identifier {self.timezone_id!r} for place "
                f"{self.canonical_name!r}. It must be an IANA identifier "
                "accepted by the system tzdata database."
            ) from exc


@runtime_checkable
class LocationResolver(Protocol):
    """The boundary between the calculation engine and place lookup.

    An implementation takes a free-text place query and returns a validated
    :class:`ResolvedLocation`, or raises :class:`PlaceNotFoundError` if it
    cannot. An external geocoding provider will implement this protocol later;
    the choice of provider is deliberately deferred and nothing in the
    calculation engine should ever depend on a concrete one -- only on this
    protocol and on ResolvedLocation.
    """

    def resolve(self, place_query: str) -> ResolvedLocation:
        """Resolve a place query, or raise PlaceNotFoundError."""
        ...


@dataclass(frozen=True)
class PlaceCandidate:
    """One scored possibility for a place query.

    Returned by the richer search API (see :class:`LocationResolver`) and
    carried by :class:`AmbiguousPlaceError` so a caller can present the choices.
    ``timezone_id`` may be None when a candidate has not had its timezone
    resolved yet -- ranking happens before the spatial lookup, which is only
    performed for a place that is actually returned.
    """

    geoname_id: int
    name: str
    admin1_name: str | None
    country_name: str | None
    latitude: float
    longitude: float
    timezone_id: str | None
    population: int
    feature_code: str | None
    score: float
    matched_name: str


class AmbiguousPlaceError(LookupError):
    """A query matched several materially different places.

    Materially different means a different country or a different first-level
    administrative division -- "Springfield" in Illinois and in Missouri are
    genuinely different answers, and no resolver should silently pick one.
    ``candidates`` holds the ranked possibilities, best first.
    """

    def __init__(self, message: str, candidates: "list[PlaceCandidate]") -> None:
        super().__init__(message)
        self.candidates = candidates
