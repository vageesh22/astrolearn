"""Layer 16: the panchanga of an instant and a place.

Three modules. ``elements`` is pure arithmetic on two sidereal longitudes --
tithi, nitya yoga, karana, and the nakshatra by way of the FROZEN Layer 7
classifier. ``sunrise`` is the adapter that brackets an instant between two
geometric Hindu sunrises and names the vara from the local civil date of the
earlier one; it is the only module here that knows what a time zone is.
``compute`` composes the five elements into one immutable ``Panchanga``, either
for an explicit instant and place or for a chart the engine has already built.

The scope is the five classical elements and nothing else. Festivals, the
lunar month and year (masa, adhika, samvatsara), muhurta, Rahu Kalam and the
other kalas, hora, the transition times of a tithi or a nakshatra, sunset,
moonrise, and any CLI, HTTP or viewer surface are out of scope by decision;
see ``docs/LAYER16_PANCHANGA_SPEC.md`` section 1.

Nothing in Layers 1 to 15 imports this package: it is a consumer of the engine,
never a part of it, and the frozen calculation specification is untouched. The
one change it required below itself is additive -- Layer 5 gained the single
accessor ``calc_sunrise_hindu``, which is still the only way ``swisseph`` is
reached from anywhere.

Ephemeris lifecycle is the caller's, as for ``assemble_chart``::

    from vedic_chart.astronomy.positions import ephemeris_session
    from vedic_chart.panchanga import calculate_panchanga

    with ephemeris_session("ephe"):
        p = calculate_panchanga(moment, 31.32556, 75.57917, "Asia/Kolkata")
"""

from .compute import (
    LocationProvenance,
    LongitudeSource,
    Panchanga,
    PanchangaLocation,
    calculate_panchanga,
    panchanga_from_chart,
)
from .elements import (
    CALCULATION_CONVENTION,
    KARANA_FIXED_NAMES,
    KARANA_REPEATING_NAMES,
    TITHI_NAMES,
    VARA_LORDS,
    VARA_NAMES,
    YOGA_NAMES,
    Karana,
    KaranaKind,
    Nakshatra,
    NityaYoga,
    Paksha,
    Tithi,
    TithiHalf,
)
from .sunrise import (
    SUNRISE_CONVENTION,
    InvalidTimezoneError,
    SunriseUnavailable,
    SunriseWindow,
    Vara,
    find_sunrise_window,
)

__all__ = [
    "CALCULATION_CONVENTION",
    "InvalidTimezoneError",
    "KARANA_FIXED_NAMES",
    "KARANA_REPEATING_NAMES",
    "Karana",
    "KaranaKind",
    "LocationProvenance",
    "LongitudeSource",
    "Nakshatra",
    "NityaYoga",
    "Paksha",
    "Panchanga",
    "PanchangaLocation",
    "SUNRISE_CONVENTION",
    "SunriseUnavailable",
    "SunriseWindow",
    "TITHI_NAMES",
    "Tithi",
    "TithiHalf",
    "VARA_LORDS",
    "VARA_NAMES",
    "Vara",
    "YOGA_NAMES",
    "calculate_panchanga",
    "find_sunrise_window",
    "panchanga_from_chart",
]
