"""Layer 7, part 2: the nine grahas of the standard D1 chart.

Calculation only. Nothing here formats anything -- degrees stay at full
precision and a display layer that renders them as degrees/minutes/seconds is
not built (rule 14). No lagna, no houses, no aspects, no dashas.

Implements the locked AstroLearn Vedic D1 calculation specification:

* rule 1 -- Rahu is the Mean Lunar Node.
* rule 2 -- Ketu is Rahu + 180 deg, normalized into [0, 360).
* rule 3 -- Ketu inherits Rahu's longitude speed.
* rule 4 -- the True Node remains available upstream but is not part of the
  standard chart, so this module does not consume it.

Retrograde is derived, never hardcoded: ``is_retrograde = speed_longitude < 0``
for every graha alike. Because Rahu is the Mean Node (rule 1), whose motion is
uniformly negative, this reproduces the classical always-retrograde convention
for Rahu and Ketu as a consequence rather than as a special case. The raw speed
is kept alongside the flag so nothing is lost.
"""

from dataclasses import dataclass
from enum import Enum

from vedic_chart.astronomy.positions import Body
from vedic_chart.sidereal.positions import SiderealPositions

from .divisions import DivisionalPlacement, classify, normalize_longitude


class Graha(Enum):
    """The nine grahas of the standard D1 chart."""

    SUN = "sun"
    MOON = "moon"
    MERCURY = "mercury"
    VENUS = "venus"
    MARS = "mars"
    JUPITER = "jupiter"
    SATURN = "saturn"
    RAHU = "rahu"
    KETU = "ketu"


# The seven non-nodal grahas map one-to-one onto the astronomical bodies.
# Body.TRUE_NODE is deliberately absent: it stays available from Layer 6 for
# callers who want it, but the standard chart uses the Mean Node only (rules
# 1 and 4).
_PLANET_BODIES = {
    Graha.SUN: Body.SUN,
    Graha.MOON: Body.MOON,
    Graha.MERCURY: Body.MERCURY,
    Graha.VENUS: Body.VENUS,
    Graha.MARS: Body.MARS,
    Graha.JUPITER: Body.JUPITER,
    Graha.SATURN: Body.SATURN,
}


@dataclass(frozen=True)
class GrahaPosition:
    """One graha's sidereal longitude, motion and divisional placement."""

    sidereal_longitude: float
    speed_longitude: float
    is_retrograde: bool
    placement: DivisionalPlacement


def _make(longitude: float, speed: float) -> GrahaPosition:
    return GrahaPosition(
        sidereal_longitude=longitude,
        speed_longitude=speed,
        is_retrograde=speed < 0.0,
        placement=classify(longitude),
    )


def derive_grahas(sidereal: SiderealPositions) -> dict[Graha, GrahaPosition]:
    """Derive the nine grahas from a set of sidereal positions.

    Returns a dict keyed by Graha in definition order.
    """
    grahas = {
        graha: _make(
            sidereal.bodies[body].sidereal_longitude,
            sidereal.bodies[body].tropical.speed_longitude,
        )
        for graha, body in _PLANET_BODIES.items()
    }

    # Rahu is the Mean Node (rule 1); Ketu is exactly opposite it and moves
    # with it (rules 2 and 3).
    mean_node = sidereal.bodies[Body.MEAN_NODE]
    rahu_longitude = mean_node.sidereal_longitude
    rahu_speed = mean_node.tropical.speed_longitude

    grahas[Graha.RAHU] = _make(rahu_longitude, rahu_speed)
    grahas[Graha.KETU] = _make(
        normalize_longitude(rahu_longitude + 180.0), rahu_speed
    )

    return {graha: grahas[graha] for graha in Graha}
