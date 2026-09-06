"""Layer 9: the canonical D1 (Rashi) chart representation.

    BirthChart (frozen, Layer 8) -> D1Chart (derived, immutable) -> Renderer(s)

``D1Chart`` describes the *astrological structure* of a D1 chart -- which rashi
sits in which house, which grahas occupy it, where the Lagna is -- in a form no
visual layout can bias. It computes no astronomy and applies no astrological
rule: there is no drishti, no dasha, no yoga, no dignity, no combustion, no
strength, no lordship and no interpretation of any kind here, and no
placeholders for them either. Layout, glyphs, field names and file formats all
live in renderers, which consume a ``D1Chart`` and nothing else.

**Nothing authoritative is copied.** ``BirthChart`` stays the single source of
truth; every value reachable from a ``D1Chart`` either *is* the frozen object
on the chart (identity, not equality) or is purely structural -- the house
number, the rashi that falls in it, and which grahas occupy it, all of which
are rearrangements of ``lagna.placement.rashi_index`` and ``BirthChart.houses``.
Because of that a representation cannot drift from its chart, and rebuilding it
from the same chart yields an equal object.

The only genuinely new data is structural, the constant convention descriptors
on :class:`D1Meta` (labels of the frozen specification, asserting nothing new),
and the on-demand DMS display values, which are never stored.
"""

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Mapping

from vedic_chart.chart.model import BirthChart
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.lagna.ascendant import Lagna
from vedic_chart.location.model import ResolvedLocation
from vedic_chart.vedic.divisions import RASHI_NAMES
from vedic_chart.vedic.grahas import Graha, GrahaPosition

from .dms import DMS, to_dms

HOUSE_COUNT = 12
RASHI_COUNT = 12
LAGNA_HOUSE = 1

ZODIAC = "sidereal"
AYANAMSHA = "Lahiri (Chitrapaksha), true equinox"
HOUSE_SYSTEM = "whole_sign"
NODE = "mean"
ENGINE_SPEC = "AstroLearn Calculation Specification FROZEN v1.0"


@dataclass(frozen=True)
class D1Meta:
    """Chart metadata: references to the birth data plus convention labels.

    The first five fields are the frozen ``BirthChart``'s own -- the same
    objects and the same floats, not copies of their contents. The five
    descriptor strings are constants of the frozen calculation specification;
    they let a renderer label a chart without knowing anything about the layers
    that produced it, and they assert nothing the engine does not already do.
    """

    request: BirthChartRequest
    location: ResolvedLocation
    moment_utc: datetime
    julian_day_ut: float
    ayanamsa: float
    zodiac: str = ZODIAC
    ayanamsha: str = AYANAMSHA
    house_system: str = HOUSE_SYSTEM
    node: str = NODE
    engine_spec: str = ENGINE_SPEC


@dataclass(frozen=True)
class D1Lagna:
    """The ascendant as the representation exposes it.

    A distinct type, never a ``Graha`` and never listed among a house's
    occupants (owner decision L-6): a renderer draws the ascendant marker from
    ``D1Chart.lagna`` alone. Its house is the constant 1 by the definition of
    Whole Sign houses. Every value is a pass-through to the frozen ``Lagna``;
    this class stores no number of its own.
    """

    position: Lagna
    house: int = LAGNA_HOUSE

    @property
    def sidereal_longitude(self) -> float:
        return self.position.sidereal_longitude

    @property
    def tropical_longitude(self) -> float:
        return self.position.tropical_longitude

    @property
    def ayanamsa(self) -> float:
        return self.position.ayanamsa

    @property
    def rashi_index(self) -> int:
        return self.position.placement.rashi_index

    @property
    def rashi_number(self) -> int:
        return self.position.placement.rashi_number

    @property
    def rashi_name(self) -> str:
        return self.position.placement.rashi_name

    @property
    def degrees_in_rashi(self) -> float:
        return self.position.placement.degrees_in_rashi

    @property
    def nakshatra_index(self) -> int:
        return self.position.placement.nakshatra_index

    @property
    def nakshatra_number(self) -> int:
        return self.position.placement.nakshatra_number

    @property
    def nakshatra_name(self) -> str:
        return self.position.placement.nakshatra_name

    @property
    def pada(self) -> int:
        return self.position.placement.pada

    def dms(self, seconds_decimals: int = 0) -> DMS:
        """Degrees in rashi as display DMS. Derived on call, never stored."""
        return to_dms(self.degrees_in_rashi, seconds_decimals)


@dataclass(frozen=True)
class D1House:
    """One of the twelve houses: its number, its rashi and its occupants.

    House numbers are always 1..12; there is no house 0. The rashi is carried
    both 0-based (``rashi_index``) and 1-based (``rashi_number``) with its
    Sanskrit name, mirroring ``DivisionalPlacement`` exactly.

    An empty house is present with ``occupants == ()``; it is never omitted and
    never ``None``. Occupants are listed in ``Graha`` enum order (Sun, Moon,
    Mercury, Venus, Mars, Jupiter, Saturn, Rahu, Ketu -- owner decision L-2),
    which is deterministic regardless of how the source mapping was built; a
    renderer wanting degree order has ``degrees_in_rashi`` to sort by.

    The rashi *lord* is deliberately absent (owner decision L-1): lordship is an
    astrological rule, not a structural fact of D1 geometry, and no rulership
    table exists in the frozen engine.
    """

    number: int
    rashi_index: int
    rashi_number: int
    rashi_name: str
    occupants: tuple[Graha, ...]


@dataclass(frozen=True)
class D1GrahaPlacement:
    """One graha, its frozen position and the house it occupies.

    All the values below are pass-throughs to the frozen ``GrahaPosition``;
    nothing is recomputed or overridden. ``speed_longitude`` is exposed raw
    (degrees per day) beside ``is_retrograde`` because it is the datum the flag
    was derived from (owner decision L-8). Rahu and Ketu therefore report
    ``is_retrograde is True`` at every instant, through the same field as every
    other graha -- a consequence of the Mean Node's uniformly negative motion,
    not a special case, and not a decision this layer makes.
    """

    graha: Graha
    position: GrahaPosition
    house: int

    @property
    def sidereal_longitude(self) -> float:
        return self.position.sidereal_longitude

    @property
    def speed_longitude(self) -> float:
        return self.position.speed_longitude

    @property
    def is_retrograde(self) -> bool:
        return self.position.is_retrograde

    @property
    def rashi_index(self) -> int:
        return self.position.placement.rashi_index

    @property
    def rashi_number(self) -> int:
        return self.position.placement.rashi_number

    @property
    def rashi_name(self) -> str:
        return self.position.placement.rashi_name

    @property
    def degrees_in_rashi(self) -> float:
        return self.position.placement.degrees_in_rashi

    @property
    def nakshatra_index(self) -> int:
        return self.position.placement.nakshatra_index

    @property
    def nakshatra_number(self) -> int:
        return self.position.placement.nakshatra_number

    @property
    def nakshatra_name(self) -> str:
        return self.position.placement.nakshatra_name

    @property
    def pada(self) -> int:
        return self.position.placement.pada

    def dms(self, seconds_decimals: int = 0) -> DMS:
        """Degrees in rashi as display DMS. Derived on call, never stored."""
        return to_dms(self.degrees_in_rashi, seconds_decimals)


@dataclass(frozen=True)
class D1Chart:
    """A derived, immutable view of one ``BirthChart`` as a D1 chart.

    ``frozen=True`` stops the attributes being rebound, ``houses`` is a tuple of
    frozen houses whose ``occupants`` are tuples, and ``grahas`` is replaced in
    ``__post_init__`` by a ``MappingProxyType`` over a private copy -- the copy
    matters as much as the proxy, exactly as on ``BirthChart``, or the dict the
    builder was holding would stay a live handle into the representation.

    ``source`` keeps the authoritative chart one attribute away (owner decision
    L-4), which is what lets this layer reference frozen values instead of
    copying them.

    The consistency checks below are guards over a rearrangement that must be
    total: twelve houses in order, nine grahas, and every graha in exactly one
    house whose number is the one its own placement reports.
    """

    source: BirthChart
    meta: D1Meta
    lagna: D1Lagna
    houses: tuple[D1House, ...]
    grahas: Mapping[Graha, D1GrahaPlacement]

    def __post_init__(self) -> None:
        if not isinstance(self.houses, tuple):
            raise ValueError(
                "houses must be a tuple of D1House; got "
                f"{type(self.houses).__name__}."
            )
        if len(self.houses) != HOUSE_COUNT:
            raise ValueError(
                f"houses must hold exactly {HOUSE_COUNT} houses; got "
                f"{len(self.houses)}."
            )
        for index, house in enumerate(self.houses):
            if house.number != index + 1:
                raise ValueError(
                    "houses must be numbered 1..12 in order; position "
                    f"{index} holds house {house.number}."
                )

        expected = set(Graha)
        if set(self.grahas) != expected:
            raise ValueError(
                "grahas must contain exactly the nine grahas; missing "
                f"{sorted(g.name for g in expected - set(self.grahas))}, "
                "unexpected "
                f"{sorted(getattr(g, 'name', g) for g in set(self.grahas) - expected)}."
            )

        house_of_occupant: dict[Graha, int] = {}
        for house in self.houses:
            if not isinstance(house.occupants, tuple):
                raise ValueError(
                    f"house {house.number} occupants must be a tuple; got "
                    f"{type(house.occupants).__name__}."
                )
            for graha in house.occupants:
                if graha in house_of_occupant:
                    raise ValueError(
                        f"{graha.name} occupies both house "
                        f"{house_of_occupant[graha]} and house {house.number}."
                    )
                house_of_occupant[graha] = house.number

        if set(house_of_occupant) != expected:
            raise ValueError(
                "every graha must occupy exactly one house; missing "
                f"{sorted(g.name for g in expected - set(house_of_occupant))}."
            )

        for graha, placement in self.grahas.items():
            if placement.house != house_of_occupant[graha]:
                raise ValueError(
                    f"{graha.name} is placed in house {placement.house} but is "
                    f"listed among the occupants of house "
                    f"{house_of_occupant[graha]}."
                )

        # Copy first, then proxy: the proxy must not be a window onto a dict
        # the caller still holds a reference to.
        object.__setattr__(self, "grahas", MappingProxyType(dict(self.grahas)))

    def house(self, number: int) -> D1House:
        """Return house ``number`` (1..12)."""
        if isinstance(number, bool) or not isinstance(number, int):
            raise ValueError(f"house number must be an int 1..12; got {number!r}.")
        if not 1 <= number <= HOUSE_COUNT:
            raise ValueError(f"house number must be in 1..12; got {number}.")
        return self.houses[number - 1]

    def house_of(self, graha: Graha) -> D1House:
        """Return the house the given graha occupies."""
        return self.house(self.grahas[graha].house)


def build_d1_chart(chart: BirthChart) -> D1Chart:
    """Build the canonical D1 representation of a ``BirthChart``.

    A pure function: it reads the chart, rearranges it and returns; equal
    inputs give equal outputs. The only arithmetic is the inverse of the frozen
    Whole Sign formula -- house *n* holds the rashi
    ``(lagna_rashi_index + n - 1) mod 12`` -- two lines that belong to this
    layer, which is why nothing from ``lagna.whole_sign`` is imported here.
    """
    lagna_rashi_index = chart.lagna.placement.rashi_index

    houses = tuple(
        D1House(
            number=number,
            rashi_index=(lagna_rashi_index + number - 1) % RASHI_COUNT,
            rashi_number=(lagna_rashi_index + number - 1) % RASHI_COUNT + 1,
            rashi_name=RASHI_NAMES[
                (lagna_rashi_index + number - 1) % RASHI_COUNT
            ],
            # Iterating the enum, not the source mapping, is what makes the
            # order independent of how the chart's dicts were built.
            occupants=tuple(
                graha for graha in Graha if chart.houses[graha] == number
            ),
        )
        for number in range(1, HOUSE_COUNT + 1)
    )

    grahas = {
        graha: D1GrahaPlacement(
            graha=graha,
            position=chart.grahas[graha],
            house=chart.houses[graha],
        )
        for graha in Graha
    }

    meta = D1Meta(
        request=chart.request,
        location=chart.location,
        moment_utc=chart.moment_utc,
        julian_day_ut=chart.julian_day_ut,
        ayanamsa=chart.ayanamsa,
    )

    return D1Chart(
        source=chart,
        meta=meta,
        lagna=D1Lagna(position=chart.lagna),
        houses=houses,
        grahas=grahas,
    )
