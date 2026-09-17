"""Layer 5: the astronomical calculation boundary.

This module is the ONLY place in the codebase that may import ``swisseph``.
Every call into the Swiss Ephemeris C library lives here.

Everything returned by this module is RAW TROPICAL geocentric ecliptic data,
exactly as the Swiss Ephemeris produces it: no ayanamsha has been applied, no
sidereal mode is set, and nothing is interpreted. Sidereal conversion and all
astrology (signs, houses, nakshatras, dashas, ...) belong to higher layers,
which are not built yet.

One event accessor was added later, for Layer 16: ``calc_sunrise_hindu``. It is
still raw astronomy -- it returns a Julian Day, not a vara -- but unlike the
functions above it asks the library for an *event* rather than for a position,
so the rising convention it encodes (``RISE_HINDU_FLAGS``, disc centre, no
refraction, geocentric Sun with its ecliptic latitude ignored, 0 m altitude) is
stated here rather than chosen by a caller who cannot see this boundary.
"""

from dataclasses import dataclass

import swisseph as swe

# Body identifiers, re-exported so that callers never import swisseph itself.
# These are plain astronomical bodies; no Vedic naming or interpretation here.
SUN = swe.SUN
MOON = swe.MOON
MERCURY = swe.MERCURY
VENUS = swe.VENUS
MARS = swe.MARS
JUPITER = swe.JUPITER
SATURN = swe.SATURN
MEAN_NODE = swe.MEAN_NODE
TRUE_NODE = swe.TRUE_NODE

_CALC_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED


@dataclass
class PlanetPosition:
    """Raw tropical geocentric ecliptic position and its rates of change."""

    longitude: float
    latitude: float
    distance_au: float
    speed_longitude: float
    speed_latitude: float
    speed_distance: float


def init_ephemeris(ephe_path: str) -> None:
    """Point the Swiss Ephemeris at the directory holding the .se1 files."""
    swe.set_ephe_path(ephe_path)


def close_ephemeris() -> None:
    """Release the Swiss Ephemeris file handles and cached data."""
    swe.close()


def get_version() -> str:
    """Return the version of the underlying Swiss Ephemeris library."""
    return swe.version


def calc_planet_position(julian_day_ut: float, planet: int) -> PlanetPosition:
    """Compute a body's raw tropical geocentric position at a Julian Day (UT).

    Raises RuntimeError if the library did not actually use the Swiss
    Ephemeris .se1 files -- without this guard it would silently fall back to
    the built-in Moshier approximation when the data files cannot be found.
    """
    values, ret_flags = swe.calc_ut(julian_day_ut, planet, _CALC_FLAGS)

    if not ret_flags & swe.FLG_SWIEPH:
        raise RuntimeError(
            "Swiss Ephemeris did not use the .se1 data files "
            f"(returned flags {ret_flags}); refusing the Moshier fallback."
        )

    return PlanetPosition(
        longitude=values[0],
        latitude=values[1],
        distance_au=values[2],
        speed_longitude=values[3],
        speed_latitude=values[4],
        speed_distance=values[5],
    )


def get_ayanamsa_lahiri(julian_day_ut: float) -> float:
    """Return the Lahiri ayanamsha in degrees at a Julian Day (UT).

    The ayanamsha VALUE comes entirely from Swiss Ephemeris' built-in Lahiri
    mode (``SIDM_LAHIRI``) -- the standard Lahiri/Chitrapaksha ayanamsha, the
    one used by the Indian national ephemeris. No formula is implemented or
    hardcoded here; we only ask the library for its value.

    ``set_sid_mode`` sets global library state, so this function sets the mode
    on every call to guarantee it regardless of what any prior call did. The
    ``t0`` and ``ayan_t0`` arguments are 0 because SIDM_LAHIRI is a predefined
    mode that supplies its own reference epoch.

    Reference frame (Core Engine Audit OPEN-1, resolved 2026-09-05): the value
    is taken from ``swe.get_ayanamsa_ex_ut(jd, 0)``, i.e. the ayanamsha referred
    to the TRUE equinox of date, nutation included. This is the same frame as
    the apparent tropical longitudes returned by ``calc_planet_position`` and
    the apparent ascendant from ``calc_ascendant_tropical``, so subtracting it
    yields nutation-free sidereal longitudes identical to Swiss Ephemeris' own
    ``SEFLG_SIDEREAL`` results and to Jagannatha Hora's published Lahiri values.
    The legacy ``swe.get_ayanamsa_ut`` returns the MEAN-equinox value (equal to
    ``get_ayanamsa_ex_ut(jd, SEFLG_NONUT)``) and is deliberately NOT used: mixing
    it with true-equinox positions offsets every sidereal longitude by the
    nutation in longitude, up to about 17 arcseconds.
    """
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    _retflags, ayanamsa = swe.get_ayanamsa_ex_ut(julian_day_ut, 0)
    return ayanamsa


def calc_ascendant_tropical(
    julian_day_ut: float, latitude: float, longitude: float
) -> float:
    """Return the tropical ecliptic longitude of the Ascendant.

    This is the only house-related Swiss Ephemeris call in the codebase, and it
    is here rather than in a higher layer because it is a ``swisseph`` call like
    every other one at this boundary.

    ``swe.houses_ex`` returns twelve house cusps alongside the ascendant, and
    **the cusps are deliberately discarded**. They are tropical, and they are
    computed for whichever house system was requested; the Whole Sign houses
    this project uses are derived instead in the Vedic layer from the *sidereal*
    Lagna's sign. Using the library's tropical cusps would be simply wrong for
    that scheme. The ascendant point itself is house-system-independent -- it is
    where the ecliptic meets the eastern horizon -- so the ``b'W'`` argument
    only avoids an arbitrary choice, it does not affect the returned value.

    The value is raw and tropical, consistent with everything else this module
    returns: no ayanamsha has been applied. Swiss Ephemeris computes the
    apparent ascendant using true obliquity; whatever ``houses_ex`` does by
    default is what is reported here.
    """
    _cusps, ascmc = swe.houses_ex(julian_day_ut, latitude, longitude, b"W")
    return ascmc[0]


RISE_HINDU_FLAGS = swe.CALC_RISE | swe.BIT_HINDU_RISING


def calc_sunrise_hindu(
    julian_day_ut: float, latitude: float, longitude: float
) -> float | None:
    """First geometric Hindu sunrise at or after a Julian Day (UT), or None.

    "Geometric Hindu rising" is Swiss Ephemeris' own documented convention:
    ``SE_CALC_RISE | SE_BIT_HINDU_RISING``, which is
    ``SE_BIT_DISC_CENTER | SE_BIT_NO_REFRACTION | SE_BIT_GEOCTR_NO_ECL_LAT`` on
    top of the rising event -- the centre of the solar disc crossing the
    geometric horizon, with no atmospheric refraction, using the geocentric Sun
    with its ecliptic latitude ignored. The site is taken to be at 0 m. The
    pressure and temperature arguments are passed as 0.0 because refraction is
    switched off and they cannot affect the result; they are still passed
    explicitly rather than defaulted, so the whole convention is visible in one
    place. This sunrise is a few minutes LATER than the upper-limb, refracted
    sunrise printed by almanacs and newspapers; that is the convention, not an
    error, and it is not adjustable from here.

    ``latitude`` is north-positive and ``longitude`` east-positive, in degrees,
    as everywhere else in this project; they are handed to the library in its
    own ``(longitude, latitude, altitude)`` order, which is the reverse.

    ``swe.rise_trans`` does not report which ephemeris it used, so the Moshier
    guard cannot be applied to its result directly. ``calc_planet_position`` is
    therefore called for the Sun at the same instant first: it raises
    RuntimeError if the .se1 files are missing, before any rising is computed.

    Returns the Julian Day (UT) of the rising on return code 0, and None on
    return code -2, which the library uses for "event not found" -- the Sun is
    circumpolar over the search window, as it is inside a polar day or night.
    A fatal library error surfaces as ``swisseph.Error`` and is not caught: an
    unreadable ephemeris is not the same fact as a Sun that does not rise.
    """
    calc_planet_position(julian_day_ut, SUN)

    return_code, tret = swe.rise_trans(
        julian_day_ut,
        SUN,
        RISE_HINDU_FLAGS,
        (longitude, latitude, 0.0),
        0.0,
        0.0,
        swe.FLG_SWIEPH,
    )

    # -2 is the library's "event not found because the object is circumpolar".
    if return_code == -2:
        return None

    # A guard, not a clamp: the documented return codes are 0 and -2, and a
    # third value would mean this boundary no longer understands the library.
    assert return_code == 0, (julian_day_ut, latitude, longitude, return_code)

    return tret[0]
