"""The sidereal Lagna (ascendant).

Composes existing layers and adds no astronomy of its own:

* the tropical ascendant comes from the Layer 5 boundary;
* the ayanamsha comes from the same boundary's Lahiri accessor;
* the tropical-to-sidereal rotation reuses Layer 6's ``sidereal_longitude``;
* the classification into rashi, nakshatra and pada reuses Layer 7's
  ``classify``.

Nothing here duplicates any of those. This module never imports ``swisseph``,
and it deliberately does not import the location layer either: it takes plain
coordinates, so the calculation engine stays independent of how a place was
resolved.
"""

import math
from dataclasses import dataclass
from datetime import datetime

from vedic_chart.ephemeris.swiss_ephemeris import (
    calc_ascendant_tropical,
    get_ayanamsa_lahiri,
)
from vedic_chart.sidereal.positions import sidereal_longitude
from vedic_chart.time.julian_day import julian_day_ut
from vedic_chart.vedic.divisions import DivisionalPlacement, classify

MIN_LATITUDE = -90.0
MAX_LATITUDE = 90.0
MIN_LONGITUDE = -180.0
MAX_LONGITUDE = 180.0


@dataclass(frozen=True)
class Lagna:
    """The ascendant, tropical and sidereal, with its divisional placement."""

    tropical_longitude: float
    sidereal_longitude: float
    ayanamsa: float
    placement: DivisionalPlacement


def _validate_coordinate(
    value: float, name: str, minimum: float, maximum: float
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number in degrees; got {value!r}.")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite; got {value!r}.")
    if not minimum <= value <= maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum} degrees "
            f"inclusive; got {value!r}."
        )


def calculate_lagna(
    moment_utc: datetime, latitude: float, longitude: float
) -> Lagna:
    """Compute the sidereal Lagna for an instant and a place.

    ``latitude`` is north-positive and ``longitude`` east-positive, in degrees,
    matching both the Swiss Ephemeris convention and Layer 2's data model.
    ``moment_utc`` must be timezone-aware; Layer 4 rejects a naive datetime.

    The Julian Day and the ayanamsha are each obtained once, at the same
    instant, so the ascendant and the rotation applied to it cannot drift apart.

    Polar caveat: above roughly 66.5 degrees of latitude the ascendant remains
    mathematically defined but behaves badly. It moves extremely
    non-uniformly -- racing through some signs in minutes -- and near the poles
    whole stretches of the ecliptic never rise at all, so some Lagnas are simply
    unreachable on a given date. No special handling is applied: the value is
    returned exactly as computed, and interpreting it at such latitudes is the
    caller's problem.
    """
    _validate_coordinate(latitude, "latitude", MIN_LATITUDE, MAX_LATITUDE)
    _validate_coordinate(longitude, "longitude", MIN_LONGITUDE, MAX_LONGITUDE)

    julian_day = julian_day_ut(moment_utc)
    tropical = calc_ascendant_tropical(julian_day, latitude, longitude)
    ayanamsa = get_ayanamsa_lahiri(julian_day)
    sidereal = sidereal_longitude(tropical, ayanamsa)

    return Lagna(
        tropical_longitude=tropical,
        sidereal_longitude=sidereal,
        ayanamsa=ayanamsa,
        placement=classify(sidereal),
    )
