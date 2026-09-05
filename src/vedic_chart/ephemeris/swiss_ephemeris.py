"""Layer 5: the astronomical calculation boundary.

This module is the ONLY place in the codebase that may import ``swisseph``.
Every call into the Swiss Ephemeris C library lives here.

Everything returned by this module is RAW TROPICAL geocentric ecliptic data,
exactly as the Swiss Ephemeris produces it: no ayanamsha has been applied, no
sidereal mode is set, and nothing is interpreted. Sidereal conversion and all
astrology (signs, houses, nakshatras, dashas, ...) belong to higher layers,
which are not built yet.
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
