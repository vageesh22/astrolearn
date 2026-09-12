"""Layer 12 and its presentation: the Vimshottari dasha.

Three modules of arithmetic and one of presentation. ``vimshottari`` is the
pure core -- exact rational nominal arithmetic, one documented quantization to
``datetime``, and the two queries. ``from_chart`` is the adapter that reads the
core's two inputs off an assembled ``BirthChart``. ``table`` (Layer 13) presents
a finished timeline as immutable rows and plain text, and is the only module
here that knows what a time zone is.

This layer computes the standard Moon-based Vimshottari cycle at three levels
(Mahadasha, Antardasha, Pratyantardasha), from the *true* start of the birth
Mahadasha before the birth. Sukshma and prana levels, starting bodies other
than the Moon, compressed cycles, reversed sub-orders and Tribhagi are out of
scope; see ``docs/LAYER12_VIMSHOTTARI_SPEC.md`` section 1. Drawing dasas on a
chart, and every export format other than the plain text table, are out of
scope of ``docs/LAYER13_DASHA_OUTPUT_SPEC.md`` section 1.
"""

from .from_chart import vimshottari_from_chart
from .table import DashaRow, dasha_rows, render_dasha_text, resolve_zone
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
    "DashaRow",
    "LORD_SEQUENCE",
    "LORD_YEARS",
    "MICROSECONDS_PER_DAY",
    "NAKSHATRA_COUNT",
    "VimshottariTimeline",
    "YearConvention",
    "build_vimshottari",
    "dasha_rows",
    "render_dasha_text",
    "resolve_zone",
    "vimshottari_from_chart",
]
