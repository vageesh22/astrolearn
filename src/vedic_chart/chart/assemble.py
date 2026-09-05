"""Layer 8: assemble a birth chart from a validated request.

This module computes nothing. Every value in the finished chart is produced by
the layer that owns it, and assembly is only the wiring:

    request -> place -> instant -> sidereal positions -> grahas
                                -> lagna -> houses

The location resolver is **injected** rather than chosen here. It is used
through the ``LocationResolver`` protocol, so the static resolver, the offline
geocoder, or any future provider all work without a change to this module.
There is deliberately no default: picking one would bury a real decision.

The Julian Day and the ayanamsha are taken from the ``SiderealPositions``
already computed, never recomputed. Recomputing them would introduce a second
path to the same numbers and, with it, the possibility of the chart's stated
ayanamsha disagreeing with the one its planets were actually rotated by.

Ephemeris lifecycle remains the caller's responsibility: wrap calls in
``ephemeris_session`` (or ``init_ephemeris``/``close_ephemeris``). Assembly does
not open or close the ephemeris, because a caller assembling many charts should
not pay to reopen it for each one.
"""

from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.lagna.ascendant import calculate_lagna
from vedic_chart.lagna.whole_sign import assign_houses
from vedic_chart.location.model import LocationResolver
from vedic_chart.sidereal.positions import calculate_sidereal_positions
from vedic_chart.time.local_time import normalize_birth_time
from vedic_chart.vedic.grahas import derive_grahas

from .model import BirthChart


def assemble_chart(
    request: BirthChartRequest, resolver: LocationResolver
) -> BirthChart:
    """Compose a complete birth chart.

    Errors from the layers below propagate untouched: an ambiguous or unknown
    place, a nonexistent or ambiguous local time, a coordinate off the globe.
    Assembly has no better answer to any of them than the layer that raised it,
    and swallowing one here would hide a real problem behind a half-built chart.
    """
    location = resolver.resolve(request.place_query)

    moment = normalize_birth_time(
        request.birth_date, request.birth_time, location.timezone_id
    )

    sidereal = calculate_sidereal_positions(moment)
    grahas = derive_grahas(sidereal)
    lagna = calculate_lagna(moment, location.latitude, location.longitude)

    # Both were taken from the same accessor at the same Julian Day. If they
    # ever differ, something upstream has drifted and the chart would be
    # internally inconsistent -- better to fail than to publish it.
    if lagna.ayanamsa != sidereal.ayanamsa:
        raise RuntimeError(
            "Internal inconsistency: the Lagna was computed with ayanamsha "
            f"{lagna.ayanamsa!r} but the planetary positions with "
            f"{sidereal.ayanamsa!r}, at the same instant."
        )

    houses = assign_houses(
        lagna.placement.rashi_index,
        {
            graha: position.placement.rashi_index
            for graha, position in grahas.items()
        },
    )

    return BirthChart(
        request=request,
        location=location,
        moment_utc=moment,
        julian_day_ut=sidereal.julian_day_ut,
        ayanamsa=sidereal.ayanamsa,
        lagna=lagna,
        grahas=grahas,
        houses=houses,
    )
