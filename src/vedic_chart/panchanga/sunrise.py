"""Layer 16, part 2: the sunrise adapter and the vara it decides.

The vara is the only element of the panchanga that is not a function of a
longitude. It is the weekday of the **local civil date of the last sunrise at
or before the instant**, so a birth before sunrise keeps the previous day's
vara even though the civil clock has already rolled over at midnight. That one
sentence is the whole of this module's astronomy; everything else here is
bracketing, conversion and refusal.

**The sunrise convention (specification section 2.3, decision D2).** Sunrise is
Swiss Ephemeris' geometric Hindu rising -- disc centre, no refraction,
geocentric Sun with its ecliptic latitude ignored, at 0 m -- reached through
the single Layer 5 accessor ``calc_sunrise_hindu``. This module never imports
``swisseph`` and never chooses flags; the convention is stated at the astronomy
boundary and only named here. It is a few minutes later than the upper-limb
refracted sunrise almanacs print, so a birth in those few minutes gets a
different vara here than there. No claim is made to match any almanac.

**What a ``None`` means (specification section 3.2).** This is the correction
that shapes the whole algorithm. Below about 65 degrees of latitude the library
uses its fast rise/set method, which never reports "not found". Beyond it the
library searches a **28-hour window** starting two hours before the probe and
reports -2 -- our ``None`` -- when no rising falls inside that window. A
``None`` therefore says "no sunrise within about 28 hours of *this probe*". It
does **not** say "no sunrise in the two-day span", and reading it that way is
wrong at exactly the latitudes where it matters. Tromso (69.65 N, 18.96 E) on
2026-01-19 at 15:00 UTC is the case that proves it: probes two days and
thirty-six hours before the instant both return ``None``, and the probe
twenty-four hours before returns 10:35:38 UTC that morning -- the first
geometric-centre sunrise of the year there -- with the next at 10:15:37 UTC on
the 20th. A single first probe decides nothing.

**Bracketing (specification section 3.2, decision D4).** The span is therefore
probed, not sampled once. Phase A walks from ``t - SEARCH_SPAN_DAYS`` up to the
instant: a ``None`` advances the probe by ``SEARCH_STEP_DAYS`` and keeps
looking; a sunrise at or before the instant becomes the running ``previous``
and the probe restarts just past it; the first sunrise after the instant is the
``following`` and ends the phase. Phase B runs only when phase A found a
previous sunrise but ran off the end of the span before finding the next one:
it probes forward from just past ``previous`` for at most
``MAX_CONSECUTIVE_GAP_DAYS``, and it can still discover a *later* previous that
the span's probe positions happened to miss.

The comparison is ``<=``, which is decision D5: a birth **exactly at** sunrise
-- exact equality of two Julian Day floats, not of two microsecond datetimes --
belongs to the new vara.

**Termination is checked, not argued.** Each loop runs at most ``MAX_PROBES``
times, on its own counter. Every accepted sunrise must lie strictly past the
previous one, and no more than ``MAX_BACKTRACK_DAYS`` before the probe that
asked for it -- the library scans from two hours before its start time
(``swecl.c``: ``t = tjd_ut - twohrs``), so a returned event is not guaranteed
to be at or after the probe, and the advance per iteration is a step minus
those two hours rather than a whole step. A library that returned the same
event twice, an earlier one, or one from well before its probe would otherwise
spin here forever, and an infinite loop is the one failure mode that never
reports itself. All three checks are ``if``/``raise`` and not ``assert``: they
are the difference between a visible error and a hang, so they must survive
``python -O``. They are checks, not clamps -- none moves a value along, all
three refuse to continue with it.

**Refusal (decision D3).** Inside a polar day or night there is no previous
sunrise, or no next one, or the two that are found are not consecutive. Each of
those is a ``SunriseUnavailable`` *result* carrying which of the three
happened. It is deliberately not an exception and deliberately not a 06:00 or
civil-weekday fallback: a fallback would silently hand back a vara that no
sunrise supports, and an exception would deny a polar birth the four angular
elements, which are perfectly well defined there.

**Time.** All arithmetic is in the Julian Day (UT) domain, obtained from the
FROZEN ``julian_day_ut``. The IANA zone is used for exactly one thing: naming
the civil date of the previous sunrise. Datetimes are produced from Julian Days
only for presentation, and the Julian Days are carried unchanged beside them,
so nothing downstream has to trust that conversion.

Two interpretations, recorded rather than left implicit:

* The coordinate validation of ``calculate_lagna`` is **re-stated** here rather
  than imported. ``vedic_chart.lagna`` is forbidden to this package by
  specification section 3, and the validator there is private in any case; the
  location layer re-states the same four bounds for the same reason. The
  message wording and the ``ValueError`` type match ``calculate_lagna``, since
  section 5 says coordinates are validated "like ``calculate_lagna``".
* ``Graha`` is taken from ``elements`` rather than from Layer 7 directly.
  Section 5 requires ``Vara.lord`` to be annotated with the FROZEN ``Graha``,
  and section 3's table does not grant this module ``vedic_chart.vedic.grahas``
  -- it grants it to ``elements``, which is where ``VARA_LORDS`` lives. Reading
  the type from the sibling that already owns the table adds no dependency the
  package has not declared, and the alternative -- an unannotated or
  forward-referenced lord -- would lose the one thing section 5 states about
  that field.
* ``searched_from_utc`` and ``searched_to_utc`` on the unavailable result name
  the two-day window in which the *previous* sunrise -- the vara boundary --
  was sought. The following sunrise is sought forward from the previous one and
  has no separate bound, so it is not represented there. Both are the Julian
  Day round trip of the bounds, not the caller's own datetime.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from vedic_chart.ephemeris.swiss_ephemeris import calc_sunrise_hindu
from vedic_chart.time.julian_day import (
    SECONDS_PER_DAY,
    UNIX_EPOCH_JD,
    julian_day_ut,
)
from vedic_chart.time.local_time import InvalidTimezoneError

from .elements import (
    VARA_ENGLISH_WEEKDAYS,
    VARA_LORDS,
    VARA_NAMES,
    Graha,
    vara_index_from_weekday,
)

#: The exact string every sunrise result carries.
SUNRISE_CONVENTION = (
    "geometric Hindu rising: Swiss Ephemeris rise_trans with rsmi = "
    "CALC_RISE | BIT_HINDU_RISING (897) -- centre of the solar disc on the "
    "geometric horizon, no atmospheric refraction, geocentric Sun with its "
    "ecliptic latitude ignored -- at 0 m altitude, atmospheric pressure 0.0 "
    "and temperature 0.0, ephemeris flag SEFLG_SWIEPH; later than the "
    "upper-limb refracted sunrise of astronomical almanacs"
)

#: How far back the previous sunrise is looked for, in days.
SEARCH_SPAN_DAYS = 2.0

#: How far the probe advances when a probe found nothing, and how far past a
#: found sunrise the next probe starts. Half a day cannot step over a sunrise,
#: because consecutive sunrises are never less than about 23 hours apart, and it
#: is long enough that the library never returns the same sunrise twice.
SEARCH_STEP_DAYS = 0.5

#: The largest gap two sunrises may have and still be called consecutive.
MAX_CONSECUTIVE_GAP_DAYS = 2.0

#: How far before its probe a returned sunrise may lie before this module calls
#: the library broken. The slow search starts its scan two hours *before* the
#: time it was given (``swecl.c``: ``t = tjd_ut - twohrs``), so a returned event
#: earlier than the probe is conceivable in principle; measured against this
#: build it never happens, at either latitude, at any offset around a known
#: sunrise. A quarter of a day is therefore comfortably beyond the two hours
#: and still far short of a day, so it catches a library that hands back an
#: event from the wrong side without ever firing on a legitimate one.
MAX_BACKTRACK_DAYS = 0.25

#: The hard iteration bound on **each** probing loop -- the counter is per
#: phase, not shared.
#:
#: This is an upper bound with margin, not an exact fit, and it deliberately
#: does not rest on "every probe advances a full step". A silent probe advances
#: by exactly ``SEARCH_STEP_DAYS``; a probe that found a sunrise ``r`` restarts
#: at ``r + SEARCH_STEP_DAYS``, and ``r`` is only known to be at or after
#: ``probe - MAX_BACKTRACK_DAYS`` -- the progress check requires ``r`` to be
#: past the *previous sunrise*, not past the probe. The guaranteed advance per
#: iteration is therefore ``SEARCH_STEP_DAYS`` minus the library's two-hour
#: look-back, about 0.417 days. Phase A travels at most ``SEARCH_SPAN_DAYS``
#: and phase B at most ``MAX_CONSECUTIVE_GAP_DAYS - SEARCH_STEP_DAYS`` from its
#: own starting probe (its limit only ever re-anchors upward), so each phase
#: needs at most ``ceil(2.0 / 0.417) = 5`` iterations. Nine leaves room for the
#: bound to be loose rather than wrong; reaching it means the library broke the
#: advance property, which is a RuntimeError rather than a silent infinite loop.
MAX_PROBES = 9

REASON_NO_PREVIOUS_SUNRISE = (
    "the Sun did not rise in the two days up to the instant"
)
REASON_NO_NEXT_SUNRISE = (
    "the Sun did not rise again within two days after the previous sunrise"
)
REASON_SUNRISES_NOT_CONSECUTIVE = (
    "the two sunrises found are more than two days apart and cannot be the "
    "boundaries of one vara"
)

UNAVAILABLE_REASONS: tuple[str, ...] = (
    REASON_NO_PREVIOUS_SUNRISE,
    REASON_NO_NEXT_SUNRISE,
    REASON_SUNRISES_NOT_CONSECUTIVE,
)

MIN_LATITUDE = -90.0
MAX_LATITUDE = 90.0
MIN_LONGITUDE = -180.0
MAX_LONGITUDE = 180.0

#: The instant Julian Day ``UNIX_EPOCH_JD`` names, as a datetime. Julian Days
#: are converted through the Unix epoch because that is the same anchor
#: ``julian_day_ut`` uses in the other direction.
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class SunriseWindow:
    """The two sunrises the vara lies between.

    ``previous`` is at or before the instant and ``next`` strictly after it.
    Both are carried twice: as the Julian Day the library actually returned,
    which is the value every comparison was made on, and as the datetime a
    reader wants. ``previous_local`` is in the place's zone and its **date** is
    what names the vara.
    """

    previous_utc: datetime
    next_utc: datetime
    previous_julian_day_ut: float
    next_julian_day_ut: float
    previous_local: datetime
    next_local: datetime
    convention: str


@dataclass(frozen=True)
class SunriseUnavailable:
    """No pair of consecutive sunrises brackets the instant.

    A result, not an exception (decision D3). ``reason`` is one of
    ``UNAVAILABLE_REASONS``; the coordinates and the searched window are
    carried so the refusal can be explained without repeating the search.
    """

    reason: str
    latitude: float
    longitude: float
    searched_from_utc: datetime
    searched_to_utc: datetime
    convention: str


@dataclass(frozen=True)
class Vara:
    """The weekday of the civil date of the previous sunrise.

    ``lord`` is the FROZEN ``Graha``, not a new planet vocabulary, and
    ``sunrise`` is the window the vara was read from -- the same object the
    panchanga carries, so the two can never disagree.
    """

    index: int
    number: int
    key: str
    name: str
    english_weekday: str
    lord: Graha
    sunrise: SunriseWindow


def resolve_zone(timezone_id: str) -> ZoneInfo:
    """Resolve an IANA identifier, or raise Layer 3's ``InvalidTimezoneError``.

    The error type is Layer 3's rather than a new one for the same reason Layer
    2 reuses it: a bad IANA identifier is one condition and deserves one
    exception across the codebase. The resolution is re-stated here instead of
    calling into Layer 3 because ``normalize_birth_time`` resolves a *wall
    time*, which this module never has -- it only ever has an exact instant.
    """
    if not isinstance(timezone_id, str):
        raise InvalidTimezoneError(
            "timezone_id must be a string IANA identifier such as "
            f"'Asia/Kolkata'; got {type(timezone_id).__name__}."
        )

    try:
        return ZoneInfo(timezone_id)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise InvalidTimezoneError(
            f"Unknown timezone identifier {timezone_id!r}. It must be an IANA "
            "identifier accepted by the system tzdata database, for example "
            "'Asia/Kolkata' or 'America/New_York'. No inference from place or "
            "country names is performed here."
        ) from exc


def _validate_coordinate(
    value: float, name: str, minimum: float, maximum: float
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number in degrees; got {value!r}.")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite; got {value!r}.")
    if not minimum <= value <= maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum} degrees "
            f"inclusive; got {value!r}."
        )


def validate_coordinates(latitude: float, longitude: float) -> None:
    """Reject coordinates that are not on the globe, as ``calculate_lagna``."""
    _validate_coordinate(latitude, "latitude", MIN_LATITUDE, MAX_LATITUDE)
    _validate_coordinate(longitude, "longitude", MIN_LONGITUDE, MAX_LONGITUDE)


def datetime_from_julian_day(julian_day: float) -> datetime:
    """Convert a Julian Day (UT) into an aware UTC datetime.

    The inverse of ``julian_day_ut`` across the same Unix-epoch anchor. It is
    for presentation only: ``timedelta`` holds microseconds, so the round trip
    is not exact at the last bits, and every comparison in this module is made
    on the Julian Day itself rather than on the datetime this produces.
    """
    return UNIX_EPOCH + timedelta(
        seconds=(julian_day - UNIX_EPOCH_JD) * SECONDS_PER_DAY
    )


def default_rise_after(
    julian_day: float, latitude: float, longitude: float
) -> float | None:
    """The first geometric Hindu sunrise at or after a Julian Day, or None.

    A thin named alias of the Layer 5 accessor. It exists so that the default
    value of ``find_sunrise_window``'s ``rise_after`` parameter has this
    module's signature and so that a test can substitute a synthetic one
    without monkeypatching the astronomy boundary.
    """
    return calc_sunrise_hindu(julian_day, latitude, longitude)


RiseAfter = Callable[[float, float, float], float | None]


def utc_instant(moment: datetime) -> tuple[datetime, float]:
    """Normalise an aware instant to UTC and give its Julian Day (UT).

    Specification 2.4: any timezone-aware datetime is accepted and normalised
    to UTC before anything is computed or stored, so that two spellings of the
    same instant -- ``+00:00``, a fixed ``+05:30``, a ``ZoneInfo`` -- produce
    equal results instead of merely equivalent ones.

    The Julian Day is asked for first and from the caller's own value, because
    that is Layer 4's refusal of a naive datetime and it must happen before the
    normalisation: ``astimezone`` on a naive datetime does not raise, it quietly
    assumes the machine's local zone, which would be both a wrong answer and a
    clock read. ``astimezone`` never moves an aware instant, so the Julian Day
    of the normalised value is the same float.
    """
    julian_day = julian_day_ut(moment)
    return moment.astimezone(timezone.utc), julian_day


def _probe_forward(
    rise_after: RiseAfter,
    latitude: float,
    longitude: float,
    *,
    probe: float,
    instant: float,
    previous: float | None,
    gap: float | None,
) -> tuple[float | None, float | None]:
    """Walk probes forward, collecting the last sunrise at or before ``instant``.

    Returns ``(previous, following)``. ``following`` is the first sunrise
    strictly after ``instant`` if one was reached before the probe ran past the
    walk's limit, and None otherwise. ``previous`` is whatever the walk found at
    or before the instant, starting from the value handed in -- phase B
    continues phase A's search rather than restarting it.

    ``gap`` selects the limit and so the phase. None means the walk stops once
    the probe passes ``instant``: that is phase A, sweeping the span up to the
    birth. A number means it stops once the probe passes ``previous + gap``, and
    that limit **moves with** ``previous``: that is phase B, looking for the
    next sunrise within a consecutive-pair's distance of the previous one, and
    re-anchoring if a later previous turns up.

    A ``None`` from ``rise_after`` means only "nothing within the library's
    28-hour window from this probe" and advances the probe one step; it never
    ends the walk. That distinction is the whole correction of specification
    3.2.
    """
    probes = 0
    while probe <= (instant if gap is None else previous + gap):
        if probes >= MAX_PROBES:
            raise RuntimeError(
                f"the sunrise search made {probes} probes without reaching its "
                f"limit (probe {probe!r}, instant {instant!r}, previous "
                f"{previous!r}, gap {gap!r}). Every probe must advance by at "
                f"least {SEARCH_STEP_DAYS} days, so this means the accessor "
                "returned a sunrise before the probe that asked for it."
            )
        probes += 1

        rise = rise_after(probe, latitude, longitude)

        if rise is None:
            probe = probe + SEARCH_STEP_DAYS
            continue

        if previous is not None and not rise > previous:
            raise RuntimeError(
                f"the sunrise search did not advance: the probe at {probe!r} "
                f"returned {rise!r}, which is not after the previous sunrise "
                f"{previous!r}. Consecutive sunrises are about a day apart, so "
                "a non-advancing result would loop forever."
            )

        if rise < probe - MAX_BACKTRACK_DAYS:
            raise RuntimeError(
                f"the sunrise search went backwards: the probe at {probe!r} "
                f"returned {rise!r}, which is more than {MAX_BACKTRACK_DAYS} "
                "days before it. The library scans from two hours before the "
                "time it is given, never a quarter of a day, so an event this "
                "far back means the accessor no longer answers the question "
                "this loop is asking."
            )

        if rise <= instant:
            previous = rise
            probe = rise + SEARCH_STEP_DAYS
            continue

        return previous, rise

    return previous, None


def find_sunrise_window(
    moment_utc: datetime,
    latitude: float,
    longitude: float,
    timezone_id: str,
    *,
    rise_after: RiseAfter = default_rise_after,
) -> SunriseWindow | SunriseUnavailable:
    """Bracket an instant between the previous and the next sunrise.

    ``moment_utc`` must be timezone-aware; Layer 4 rejects a naive datetime
    with a ValueError, and it is asked before anything else so that a naive
    instant costs no ephemeris call. The instant is then normalised to UTC
    (specification 2.4); nothing this function returns is derived from the
    instant's own spelling -- the window is Julian Days and the civil date
    comes from the sunrise, not from the birth -- so the normalisation buys
    consistency with the two entry points rather than a different answer, and
    the unused name below says so. Coordinates are validated as
    ``calculate_lagna`` validates them and the zone as Layer 3 validates it.

    Returns a ``SunriseWindow`` when a consecutive pair brackets the instant
    and a ``SunriseUnavailable`` otherwise. ``rise_after`` is injectable so the
    bracketing can be exercised on exact synthetic Julian Days with no sky in
    the loop; the default is the real sunrise.
    """
    _normalised, instant = utc_instant(moment_utc)
    validate_coordinates(latitude, longitude)
    zone = resolve_zone(timezone_id)

    searched_from = instant - SEARCH_SPAN_DAYS

    # Phase A: probe the whole span up to the instant. A ``None`` is one
    # probe's silence, not the span's.
    previous, following = _probe_forward(
        rise_after,
        latitude,
        longitude,
        probe=searched_from,
        instant=instant,
        previous=None,
        gap=None,
    )

    # Phase B: the span ran out before the next sunrise was reached. Keep
    # probing past the previous one -- and accept a later previous, if the
    # span's probe positions happened to miss it.
    if previous is not None and following is None:
        previous, following = _probe_forward(
            rise_after,
            latitude,
            longitude,
            probe=previous + SEARCH_STEP_DAYS,
            instant=instant,
            previous=previous,
            gap=MAX_CONSECUTIVE_GAP_DAYS,
        )

    if previous is None:
        reason = REASON_NO_PREVIOUS_SUNRISE
    elif following is None:
        reason = REASON_NO_NEXT_SUNRISE
    elif following - previous > MAX_CONSECUTIVE_GAP_DAYS:
        reason = REASON_SUNRISES_NOT_CONSECUTIVE
    else:
        previous_utc = datetime_from_julian_day(previous)
        next_utc = datetime_from_julian_day(following)
        return SunriseWindow(
            previous_utc=previous_utc,
            next_utc=next_utc,
            previous_julian_day_ut=previous,
            next_julian_day_ut=following,
            previous_local=previous_utc.astimezone(zone),
            next_local=next_utc.astimezone(zone),
            convention=SUNRISE_CONVENTION,
        )

    return SunriseUnavailable(
        reason=reason,
        latitude=latitude,
        longitude=longitude,
        searched_from_utc=datetime_from_julian_day(searched_from),
        searched_to_utc=datetime_from_julian_day(instant),
        convention=SUNRISE_CONVENTION,
    )


def vara_from_sunrise(window: SunriseWindow) -> Vara:
    """Name the vara of a sunrise window.

    The civil date is read from ``previous_local`` -- the previous sunrise in
    the place's own zone -- and never from the instant's UTC date nor from the
    birth's own wall clock, which is what makes a pre-dawn birth keep the
    previous day's vara and what makes a date-line zone come out right.
    """
    index = vara_index_from_weekday(window.previous_local.date().weekday())

    return Vara(
        index=index,
        number=index + 1,
        key=VARA_NAMES[index].lower(),
        name=VARA_NAMES[index],
        english_weekday=VARA_ENGLISH_WEEKDAYS[index],
        lord=VARA_LORDS[index],
        sunrise=window,
    )
