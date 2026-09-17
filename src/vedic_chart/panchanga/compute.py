"""Layer 16, part 3: composition of the five elements into one panchanga.

Two entry points onto the same assembly:

* ``calculate_panchanga(moment_utc, latitude, longitude, timezone_id)`` -- for
  an instant and a place that no chart exists for. It obtains the two sidereal
  longitudes through the existing Layer 6 ``calculate_sidereal_positions``, one
  call at one Julian Day with one ayanamsha, exactly as a chart does, and
  classifies the Moon with the FROZEN ``classify``.
* ``panchanga_from_chart(chart)`` -- for a chart the engine has already built.
  It **reads** the Sun's and the Moon's sidereal longitudes, the Moon's
  ``DivisionalPlacement``, the instant, the Julian Day, the ayanamsha and the
  location off the chart, and makes **no planetary ephemeris call at all**. The
  nakshatra is the chart's own placement object, carried by identity rather
  than reclassified, so the panchanga cannot disagree with the chart it came
  from -- not "agrees to many decimals", the same object.

Both paths make the same sunrise calls, because a sunrise is not something a
chart carries.

Nothing is rounded and nothing is recalculated that a layer below already
produced. The two Julian Days -- the one Layer 4 gives for the instant and the
one Layer 6 reports alongside its positions -- are cross-checked rather than
assumed equal, in the same spirit as ``assemble_chart``'s ayanamsha check: they
come from the same function on the same instant, so a difference would be an
internal contradiction, not a caller's mistake.

Ephemeris lifecycle is the caller's, as for ``assemble_chart``: wrap calls in
``ephemeris_session(path)``. This module opens and closes nothing, because a
caller computing many panchangas should not pay to reopen the ephemeris each
time.

Two interpretations, recorded rather than left implicit:

* Specification section 3's table leaves the standard-library column for this
  module empty. It is read as an omission, not as a prohibition: the frozen
  dataclasses and enums section 5 requires cannot be written without
  ``dataclasses`` and ``enum``, and an annotated instant needs ``datetime``.
  Those three are used and nothing else -- in particular not ``zoneinfo``,
  which stays the sunrise module's privilege; the local datetime is produced
  from the zone object that module resolves.
* ``vara is None`` iff the sunrise is unavailable is checked in
  ``__post_init__`` and raises ``ValueError``, following ``BirthChart``, which
  validates its own invariants there rather than trusting its constructor's
  callers.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from vedic_chart.astronomy.positions import Body
from vedic_chart.chart.model import BirthChart
from vedic_chart.sidereal.positions import calculate_sidereal_positions
from vedic_chart.vedic.grahas import Graha

from .elements import (
    CALCULATION_CONVENTION,
    Karana,
    Nakshatra,
    NityaYoga,
    Tithi,
    elongation,
    karana_from_elongation,
    longitude_sum,
    nakshatra_from_longitude,
    nakshatra_from_placement,
    tithi_from_elongation,
    yoga_from_sum,
)
from .sunrise import (
    SUNRISE_CONVENTION,
    SunriseUnavailable,
    SunriseWindow,
    Vara,
    find_sunrise_window,
    resolve_zone,
    utc_instant,
    validate_coordinates,
    vara_from_sunrise,
)


class LongitudeSource(Enum):
    """Where the two sidereal longitudes in a panchanga came from."""

    BIRTH_CHART = "birth_chart"
    COMPUTED = "computed"


class LocationProvenance(Enum):
    """Where the place in a panchanga came from."""

    BIRTH_CHART = "birth_chart"
    EXPLICIT = "explicit"


@dataclass(frozen=True)
class PanchangaLocation:
    """The place a panchanga was computed for, and how it was supplied.

    A deliberately smaller thing than Layer 2's ``ResolvedLocation``: a
    panchanga needs coordinates and a zone, not a canonical place name or a
    resolver's opinion, and this package is forbidden the location layer
    precisely so that the calculation cannot start depending on how a place was
    looked up. ``provenance`` records which entry point supplied the three
    values, so a stored result still says whether a chart stood behind it.
    """

    latitude: float
    longitude: float
    timezone_id: str
    provenance: LocationProvenance


@dataclass(frozen=True)
class Panchanga:
    """The five elements at one instant and one place, with their inputs.

    Everything the result depends on is carried alongside it: the instant, the
    Julian Day, the longitudes, the ayanamsha they were rotated by, the place,
    and the two convention strings. A stored panchanga is therefore
    self-describing -- nothing has to be looked up in this package to know what
    it means.

    ``vara`` is None exactly when ``sunrise`` is a ``SunriseUnavailable``. The
    four angular elements are always present: they are functions of two
    longitudes and are as well defined inside a polar day as anywhere else.
    """

    instant_utc: datetime
    julian_day_ut: float
    local_datetime: datetime
    location: PanchangaLocation
    sun_sidereal_longitude: float
    moon_sidereal_longitude: float
    ayanamsa: float
    longitudes_source: LongitudeSource
    tithi: Tithi
    nakshatra: Nakshatra
    yoga: NityaYoga
    karana: Karana
    vara: Vara | None
    sunrise: SunriseWindow | SunriseUnavailable
    calculation_convention: str
    sunrise_convention: str

    def __post_init__(self) -> None:
        if self.instant_utc.tzinfo is not timezone.utc:
            raise ValueError(
                "instant_utc must carry timezone.utc itself, not merely an "
                "equivalent zero offset (specification 2.4); got "
                f"{self.instant_utc.tzinfo!r}. Two spellings of one instant "
                "must not produce two different panchangas."
            )

        available = isinstance(self.sunrise, SunriseWindow)
        if available != (self.vara is not None):
            raise ValueError(
                "vara must be present exactly when the sunrise window is: got "
                f"sunrise {type(self.sunrise).__name__} with vara "
                f"{self.vara!r}."
            )
        if self.vara is not None and self.vara.sunrise is not self.sunrise:
            raise ValueError(
                "the vara must have been read from this panchanga's own "
                "sunrise window; it carries a different one."
            )
        if self.karana.tithi_index != self.tithi.index:
            raise ValueError(
                "the karana halves a different tithi than the one recorded: "
                f"karana.tithi_index {self.karana.tithi_index}, tithi.index "
                f"{self.tithi.index}."
            )

    @property
    def sunrise_available(self) -> bool:
        """Whether a sunrise pair was found, and therefore whether there is a vara."""
        return isinstance(self.sunrise, SunriseWindow)


def _assemble(
    moment_utc: datetime,
    julian_day: float,
    sun_longitude: float,
    moon_longitude: float,
    nakshatra: Nakshatra,
    ayanamsa: float,
    location: PanchangaLocation,
    longitudes_source: LongitudeSource,
) -> Panchanga:
    """The one assembly both entry points funnel through.

    It exists so that the from-chart and explicit paths cannot drift apart:
    everything after "where did the two longitudes and the place come from" is
    the same code, and the only difference between the two results is the
    provenance each records.
    """
    arc = elongation(sun_longitude, moon_longitude)
    total = longitude_sum(sun_longitude, moon_longitude)

    window = find_sunrise_window(
        moment_utc, location.latitude, location.longitude, location.timezone_id
    )
    vara = vara_from_sunrise(window) if isinstance(window, SunriseWindow) else None

    zone = resolve_zone(location.timezone_id)

    return Panchanga(
        instant_utc=moment_utc,
        julian_day_ut=julian_day,
        local_datetime=moment_utc.astimezone(zone),
        location=location,
        sun_sidereal_longitude=sun_longitude,
        moon_sidereal_longitude=moon_longitude,
        ayanamsa=ayanamsa,
        longitudes_source=longitudes_source,
        tithi=tithi_from_elongation(arc),
        nakshatra=nakshatra,
        yoga=yoga_from_sum(total),
        karana=karana_from_elongation(arc),
        vara=vara,
        sunrise=window,
        calculation_convention=CALCULATION_CONVENTION,
        sunrise_convention=SUNRISE_CONVENTION,
    )


def calculate_panchanga(
    moment_utc: datetime,
    latitude: float,
    longitude: float,
    timezone_id: str,
) -> Panchanga:
    """Compute the panchanga for an exact instant at a place.

    All four inputs are checked **before** the sky is asked, so an unusable
    call costs no ephemeris work at all -- the fail-fast, typed-error rule
    Layer 3 and ``calculate_lagna`` already follow. ``moment_utc`` must be
    timezone-aware, and Layer 4 rejects a naive datetime with a ValueError.
    ``latitude`` is north-positive and ``longitude`` east-positive, in degrees,
    validated as ``calculate_lagna`` validates them. ``timezone_id`` is an IANA
    identifier and nothing is inferred from a place name, so a bad one is an
    ``InvalidTimezoneError``. ``find_sunrise_window`` validates the same three
    again later; the repetition is deliberate and harmless, because it is also
    a public entry point and the checks are idempotent.

    The ephemeris must already be open: wrap the call in ``ephemeris_session``.
    """
    moment, julian_day = utc_instant(moment_utc)
    validate_coordinates(latitude, longitude)
    resolve_zone(timezone_id)

    location = PanchangaLocation(
        latitude=latitude,
        longitude=longitude,
        timezone_id=timezone_id,
        provenance=LocationProvenance.EXPLICIT,
    )

    sidereal = calculate_sidereal_positions(moment)

    # Both Julian Days came from ``julian_day_ut`` at the same instant. A
    # difference would mean the positions belong to a different moment than the
    # one this result claims, which is worth failing over rather than shipping.
    if sidereal.julian_day_ut != julian_day:
        raise RuntimeError(
            "Internal inconsistency: the instant converts to Julian Day "
            f"{julian_day!r} but Layer 6 computed its positions at "
            f"{sidereal.julian_day_ut!r}."
        )

    moon_longitude = sidereal.bodies[Body.MOON].sidereal_longitude

    return _assemble(
        moment_utc=moment,
        julian_day=sidereal.julian_day_ut,
        sun_longitude=sidereal.bodies[Body.SUN].sidereal_longitude,
        moon_longitude=moon_longitude,
        nakshatra=nakshatra_from_longitude(moon_longitude),
        ayanamsa=sidereal.ayanamsa,
        location=location,
        longitudes_source=LongitudeSource.COMPUTED,
    )


def panchanga_from_chart(chart: BirthChart) -> Panchanga:
    """Compute the panchanga of an already assembled birth chart.

    The instant is normalised to UTC like any other (specification 2.4); a
    chart's instant is already UTC, so that is a no-op for every chart
    ``assemble_chart`` produced and the object is passed straight through.

    No planetary ephemeris call is made: the longitudes, the instant, the
    Julian Day and the ayanamsha are all read off the chart, and the Moon's
    nakshatra is the chart's own ``DivisionalPlacement`` object rather than a
    fresh classification of the same double. The only calls into the astronomy
    boundary are the sunrise ones, which a chart does not carry.

    The ephemeris must still be open for those, so this stays inside an
    ``ephemeris_session`` like everything else in the engine.
    """
    moment, julian_day = utc_instant(chart.moment_utc)

    # The chart computed its own Julian Day from its own instant with the same
    # FROZEN function. If the two disagree the chart is not internally
    # consistent, and a panchanga built on it would quietly inherit that.
    if julian_day != chart.julian_day_ut:
        raise RuntimeError(
            "Internal inconsistency: the chart's instant converts to Julian "
            f"Day {julian_day!r} but the chart records "
            f"{chart.julian_day_ut!r} for the same moment."
        )

    sun = chart.grahas[Graha.SUN]
    moon = chart.grahas[Graha.MOON]

    location = PanchangaLocation(
        latitude=chart.location.latitude,
        longitude=chart.location.longitude,
        timezone_id=chart.location.timezone_id,
        provenance=LocationProvenance.BIRTH_CHART,
    )

    return _assemble(
        moment_utc=moment,
        julian_day=chart.julian_day_ut,
        sun_longitude=sun.sidereal_longitude,
        moon_longitude=moon.sidereal_longitude,
        nakshatra=nakshatra_from_placement(
            moon.placement, moon.sidereal_longitude
        ),
        ayanamsa=chart.ayanamsa,
        location=location,
        longitudes_source=LongitudeSource.BIRTH_CHART,
    )
