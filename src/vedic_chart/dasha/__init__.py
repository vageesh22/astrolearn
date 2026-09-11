"""Layer 12: the Vimshottari dasha.

Two modules and one public surface. ``vimshottari`` is the pure core -- exact
rational nominal arithmetic, one documented quantization to ``datetime``, and
the two queries. ``from_chart`` is the adapter that reads the core's two inputs
off an assembled ``BirthChart``.

This layer computes the standard Moon-based Vimshottari cycle at three levels
(Mahadasha, Antardasha, Pratyantardasha), from the *true* start of the birth
Mahadasha before the birth. Sukshma and prana levels, starting bodies other
than the Moon, compressed cycles, reversed sub-orders, Tribhagi and any
rendering or CLI exposure are out of scope; see
``docs/LAYER12_VIMSHOTTARI_SPEC.md`` section 1.
"""

from .from_chart import vimshottari_from_chart
from .vimshottari import (
    CYCLE_YEARS,
    LORD_SEQUENCE,
    LORD_YEARS,
    MICROSECONDS_PER_DAY,
    NAKSHATRA_COUNT,
    DashaPeriod,
    DashaRangeError,
    VimshottariTimeline,
    YearConvention,
    build_vimshottari,
)

__all__ = [
    "CYCLE_YEARS",
    "DashaPeriod",
    "DashaRangeError",
    "LORD_SEQUENCE",
    "LORD_YEARS",
    "MICROSECONDS_PER_DAY",
    "NAKSHATRA_COUNT",
    "VimshottariTimeline",
    "YearConvention",
    "build_vimshottari",
    "vimshottari_from_chart",
]
