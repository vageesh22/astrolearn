"""The assembled birth chart.

``BirthChart`` is the stable surface every future layer reads. A caller works
with ``chart.lagna``, ``chart.grahas`` and ``chart.houses`` and needs to know
nothing about how any of them were produced -- which ephemeris was consulted,
which ayanamsha was applied, how a place was resolved. That is the point of
assembling one object: the composition details stop here.

Nothing is rounded. Every value is carried at the precision the layer below
produced it.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Mapping

from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.lagna.ascendant import Lagna
from vedic_chart.location.model import ResolvedLocation
from vedic_chart.vedic.grahas import Graha, GrahaPosition

MIN_HOUSE = 1
MAX_HOUSE = 12


@dataclass(frozen=True)
class BirthChart:
    """One birth, resolved and computed, in a single immutable object.

    ``frozen=True`` stops the attributes being rebound, but it does nothing for
    the *contents* of a mapping field: a plain dict would still let a caller
    write ``chart.grahas[Graha.SUN] = ...`` and silently corrupt a chart other
    code is holding. So ``__post_init__`` replaces both mappings with a
    ``MappingProxyType`` over a private copy. The copy matters as much as the
    proxy: without it the dict the caller passed in would remain a live handle
    into the chart's insides.
    """

    request: BirthChartRequest
    location: ResolvedLocation
    moment_utc: datetime
    julian_day_ut: float
    ayanamsa: float
    lagna: Lagna
    grahas: Mapping[Graha, GrahaPosition]
    houses: Mapping[Graha, int]

    def __post_init__(self) -> None:
        graha_keys = set(self.grahas)
        house_keys = set(self.houses)
        expected = set(Graha)

        if graha_keys != expected:
            raise ValueError(
                "grahas must contain exactly the nine grahas; missing "
                f"{sorted(g.name for g in expected - graha_keys)}, unexpected "
                f"{sorted(getattr(g, 'name', g) for g in graha_keys - expected)}."
            )
        if house_keys != expected:
            raise ValueError(
                "houses must contain exactly the nine grahas; missing "
                f"{sorted(g.name for g in expected - house_keys)}, unexpected "
                f"{sorted(getattr(g, 'name', g) for g in house_keys - expected)}."
            )

        for graha, house in self.houses.items():
            if isinstance(house, bool) or not isinstance(house, int):
                raise ValueError(
                    f"house for {graha.name} must be an int; got {house!r}."
                )
            if not MIN_HOUSE <= house <= MAX_HOUSE:
                raise ValueError(
                    f"house for {graha.name} must be in "
                    f"{MIN_HOUSE}..{MAX_HOUSE}; got {house}."
                )

        if not isinstance(self.ayanamsa, (int, float)) or not math.isfinite(
            self.ayanamsa
        ):
            raise ValueError(f"ayanamsa must be finite; got {self.ayanamsa!r}.")

        # Copy first, then proxy: the proxy must not be a window onto a dict
        # the caller still holds a reference to.
        object.__setattr__(self, "grahas", MappingProxyType(dict(self.grahas)))
        object.__setattr__(self, "houses", MappingProxyType(dict(self.houses)))
