"""Astronomical position API: an exact UTC instant to raw body positions.

This module sits on top of two layers and imports nothing else of substance:
Layer 4 (:mod:`vedic_chart.time.julian_day`) for the calendar arithmetic and
Layer 5 (:mod:`vedic_chart.ephemeris.swiss_ephemeris`) for the astronomy. It
never imports ``swisseph`` itself -- that stays behind the Layer 5 boundary.

Everything returned here is raw tropical geocentric data, passed through from
Layer 5 unchanged. No ayanamsha, no signs, no houses, no retrograde
interpretation. Both lunar nodes are computed; which one is used, and how, is a
decision for the Vedic layer that does not exist yet.
"""

from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from typing import Iterator

from vedic_chart.ephemeris import swiss_ephemeris
from vedic_chart.ephemeris.swiss_ephemeris import PlanetPosition
from vedic_chart.time.julian_day import julian_day_ut


class Body(Enum):
    """The bodies this API computes. Astronomical names only."""

    SUN = "sun"
    MOON = "moon"
    MERCURY = "mercury"
    VENUS = "venus"
    MARS = "mars"
    JUPITER = "jupiter"
    SATURN = "saturn"
    MEAN_NODE = "mean_node"
    TRUE_NODE = "true_node"


# Body -> the Layer 5 constant it corresponds to.
_EPHEMERIS_IDS = {
    Body.SUN: swiss_ephemeris.SUN,
    Body.MOON: swiss_ephemeris.MOON,
    Body.MERCURY: swiss_ephemeris.MERCURY,
    Body.VENUS: swiss_ephemeris.VENUS,
    Body.MARS: swiss_ephemeris.MARS,
    Body.JUPITER: swiss_ephemeris.JUPITER,
    Body.SATURN: swiss_ephemeris.SATURN,
    Body.MEAN_NODE: swiss_ephemeris.MEAN_NODE,
    Body.TRUE_NODE: swiss_ephemeris.TRUE_NODE,
}


@contextmanager
def ephemeris_session(ephe_path: str) -> Iterator[None]:
    """Open the ephemeris for the duration of a block and close it after."""
    swiss_ephemeris.init_ephemeris(ephe_path)
    try:
        yield
    finally:
        swiss_ephemeris.close_ephemeris()


def calculate_positions(moment_utc: datetime) -> dict[Body, PlanetPosition]:
    """Compute raw tropical geocentric positions for every :class:`Body`.

    ``moment_utc`` must be a timezone-aware datetime; naive values are rejected
    by Layer 4 with a ValueError. The returned dict is keyed by Body in
    definition order.
    """
    julian_day = julian_day_ut(moment_utc)
    return {
        body: swiss_ephemeris.calc_planet_position(julian_day, ephemeris_id)
        for body, ephemeris_id in _EPHEMERIS_IDS.items()
    }
