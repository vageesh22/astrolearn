"""Layer 12, part 2: the adapter from a Layer 8 ``BirthChart``.

A deliberately thin module. It reads exactly two values off the chart -- the
Moon's sidereal longitude and the birth instant -- and hands them to the core.
It computes no astronomy, opens no ephemeris, enters no session, and never
looks at ``chart.location``, the lagna, the houses or the request: a dasha is a
function of those two numbers and nothing else, and an adapter that reached
further would quietly make it a function of more.

The one thing it does beyond forwarding is a cross-check. Section 5's decision
D1 says the core's nakshatra index is the frozen Layer 7 index *by
construction*, because it repeats Layer 7's arithmetic on the same double. That
is a claim about two pieces of code agreeing, so it is verified here rather
than assumed: the index carried by the timeline the core returns is compared
by value with the index the chart already carries in
``placement.nakshatra_index``. A mismatch cannot happen for any chart the
engine produced, so it is a ``RuntimeError`` -- an internal contradiction, not
a caller's mistake.

The core is called exactly once and the comparison reads its result. Nothing
is classified here a second time: a private re-run of the ``% 360.0`` /
``* 27.0 / 360.0`` arithmetic would make the check vacuous, testing this
module against itself rather than the core against the frozen chart.
"""

from vedic_chart.chart.model import BirthChart
from vedic_chart.vedic.grahas import Graha

from .vimshottari import VimshottariTimeline, YearConvention, build_vimshottari

__all__ = ["vimshottari_from_chart"]


def vimshottari_from_chart(
    chart: BirthChart, year: YearConvention
) -> VimshottariTimeline:
    """Build the Vimshottari timeline of one assembled birth chart.

    ``year`` is required here for the same reason it is required in the core:
    the adapter is not a place to smuggle in a default. Input validation --
    the longitude's type and finiteness, the instant's awareness, the year
    convention -- is the core's and is not repeated here.
    """
    moon = chart.grahas[Graha.MOON]
    longitude = moon.sidereal_longitude

    timeline = build_vimshottari(longitude, chart.moment_utc, year)

    recorded = moon.placement.nakshatra_index
    if timeline.nakshatra_index != recorded:
        raise RuntimeError(
            "the chart's Moon placement disagrees with the dasha layer's "
            f"classification of the same longitude {longitude!r}: the chart "
            f"records nakshatra index {recorded}, the timeline carries "
            f"{timeline.nakshatra_index}. Under decision D1 the two are the "
            "same arithmetic, so this is an internal contradiction, not an "
            "input error."
        )

    return timeline
