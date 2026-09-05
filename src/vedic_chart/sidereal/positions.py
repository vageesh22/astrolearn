"""Layer 6: conversion of tropical longitudes into the sidereal frame.

The whole of this layer is one rotation:

    sidereal_longitude = (tropical_longitude - ayanamsha) mod 360

The ayanamsha itself is not computed here -- it is asked of Swiss Ephemeris
through the Layer 5 accessor, which uses the library's built-in Lahiri mode.
This module never imports ``swisseph``.

Tropical data is preserved unchanged: every result carries the original
:class:`PlanetPosition` alongside the derived sidereal longitude, so nothing
downstream has to trust this layer to have kept the raw numbers intact.

Naming the result -- signs, nakshatras, houses -- is Layer 7's job and is not
built. Nothing here interprets anything.
"""

from dataclasses import dataclass
from datetime import datetime

from vedic_chart.astronomy.positions import (
    Body,
    PlanetPosition,
    calculate_positions,
)
from vedic_chart.ephemeris.swiss_ephemeris import get_ayanamsa_lahiri
from vedic_chart.time.julian_day import julian_day_ut


def sidereal_longitude(tropical_longitude: float, ayanamsa: float) -> float:
    """Rotate a tropical longitude into the sidereal frame, wrapping to [0, 360)."""
    return (tropical_longitude - ayanamsa) % 360.0


@dataclass
class SiderealBodyPosition:
    """One body's sidereal longitude beside the untouched tropical position.

    Latitude, distance and all three speeds live in ``tropical`` and are
    unchanged by the frame rotation. The ayanamsha drifts by roughly
    0.000038 deg/day, which is negligible against any speed of interest, so it
    is deliberately not applied to the speeds.
    """

    tropical: PlanetPosition
    sidereal_longitude: float


@dataclass
class SiderealPositions:
    """A full set of sidereal positions plus the inputs they were derived from."""

    julian_day_ut: float
    ayanamsa: float
    bodies: dict[Body, SiderealBodyPosition]


def calculate_sidereal_positions(moment_utc: datetime) -> SiderealPositions:
    """Compute Lahiri sidereal longitudes for every body at a UTC instant.

    The Julian Day, the tropical positions and the ayanamsha are each obtained
    once, at the same instant, so every body is rotated by the same value.
    """
    julian_day = julian_day_ut(moment_utc)
    tropical_positions = calculate_positions(moment_utc)
    ayanamsa = get_ayanamsa_lahiri(julian_day)

    bodies = {
        body: SiderealBodyPosition(
            tropical=position,
            sidereal_longitude=sidereal_longitude(position.longitude, ayanamsa),
        )
        for body, position in tropical_positions.items()
    }

    return SiderealPositions(
        julian_day_ut=julian_day,
        ayanamsa=ayanamsa,
        bodies=bodies,
    )
