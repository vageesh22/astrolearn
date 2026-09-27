"""Layer 18: the daily panchanga, sunrise to sunrise (specification section 11).

Against the real ephemeris where the point is the sky -- the reference days,
parity with Layer 16, the consecutive-day partition, civil-date anomalies and
polar stretches -- and against injected ``rise_after`` and ``evaluate``
callables where the point is the selection and placement logic: sunrises put
exactly on the 100 ms tolerance grid, a tithi forced to change exactly at, one
microsecond before or one microsecond after a sunrise, a second locating of one
sunrise made to differ by 10 ms, sunrise sequences out of order, skipped, or
with a gap. Both injection points are the ones Layers 16 and 17 already define
and are passed straight through.

**Reference values are engine values.** Every datetime asserted below is what
this engine produced on Linux x86_64 in the cloud venv, and every expectation
of the specification that concerns a real place was run before it was written
down here. All matched but one: at Ushuaia, Layer 16 asked at ``closing.utc -
1 s`` returns a ``previous`` float that differs from the canonical opening
(see ``PARITY_BY_EVENT_ONLY``); that cell is pinned by event identity and its
difference recorded, not asserted away.
Transition cells are subject to the platform note of Layer 17 section 4.9.

**Neighbour information is bounded by the walk.** Wherever a polar test
asserts ``preceding_sunrise`` or ``following_sunrise`` it first asserts the
walk's range, written out, so that ``None`` reads as "not found within that
range" and never as "does not exist".
"""

import ast
import dataclasses
import functools
import math
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from types import MappingProxyType
from zoneinfo import ZoneInfo

import pytest

from render_helpers import EPHE_DIR, REPO_ROOT
from vedic_chart.astronomy.positions import ephemeris_session
import vedic_chart.panchanga as package
import vedic_chart.panchanga.daily as daily_module
import vedic_chart.panchanga.sunrise as sunrise_module
import vedic_chart.panchanga.transitions as transitions_module
from vedic_chart.panchanga import (
    ALL_KINDS,
    ALLOWED_TOLERANCES,
    ANCHOR_EPOCH,
    ANCHOR_STEP,
    CALCULATION_CONVENTION,
    CONTAINING_WALK_AFTER,
    CONTAINING_WALK_BEFORE,
    DEFAULT_TOLERANCE,
    MAX_OFFSET_HOURS,
    SAME_SUNRISE_MAX_SEPARATION,
    SEARCH_CONVENTION,
    SUNRISE_CONVENTION,
    SUPPORTED_DATE_END,
    SUPPORTED_DATE_START,
    SUPPORTED_INSTANT_END,
    SUPPORTED_INSTANT_START,
    WALK_AFTER,
    WALK_BEFORE,
    DayPlacement,
    DayRequestError,
    DaySearchError,
    DaySunrise,
    DayUnavailableReason,
    InstantElements,
    InvalidTimezoneError,
    LocationProvenance,
    PanchangaDay,
    PanchangaDayAmbiguous,
    PanchangaDayUnavailable,
    PanchangaLocation,
    PlacedTransition,
    SunriseLocating,
    SunriseUnavailable,
    SunriseWindow,
    TransitionKind,
    TransitionRequestError,
    UnsupportedDateError,
    UnsupportedInstantError,
    calculate_panchanga,
    find_transitions,
    list_transitions,
    next_transition,
    panchanga_day,
    panchanga_day_containing,
    same_event,
)
from vedic_chart.panchanga.elements import NAKSHATRA_SPAN
from vedic_chart.panchanga.sunrise import (
    REASON_NO_NEXT_SUNRISE,
    REASON_NO_PREVIOUS_SUNRISE,
    REASON_SUNRISES_NOT_CONSECUTIVE,
    SEARCH_SPAN_DAYS,
    UNAVAILABLE_REASONS,
    datetime_from_julian_day,
)
from vedic_chart.time.julian_day import julian_day_ut

TITHI = TransitionKind.TITHI
KARANA = TransitionKind.KARANA
NAKSHATRA = TransitionKind.NAKSHATRA
YOGA = TransitionKind.YOGA

CANONICAL = SunriseLocating.CANONICAL_ANCHOR
WINDOW_NEXT = SunriseLocating.WINDOW_NEXT
FIRST_ANCHOR = SunriseLocating.FIRST_ANCHOR

WITHIN = DayPlacement.WITHIN
REFLECTED = DayPlacement.STRADDLES_OPENING_REFLECTED
AFTER = DayPlacement.STRADDLES_OPENING_AFTER
AT_OR_BEFORE_CLOSING = DayPlacement.AT_OR_BEFORE_CLOSING

UTC = timezone.utc
US = timedelta(microseconds=1)
MS = timedelta(milliseconds=1)
SECOND = timedelta(seconds=1)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)

IST = ZoneInfo("Asia/Kolkata")

# The project's coordinates (tests/test_panchanga_compute.py) and the places of
# specification section 11.
JALANDHAR = (31.32556, 75.57917, "Asia/Kolkata")
JAMMU = (32.73528, 74.86167, "Asia/Kolkata")
USHUAIA = (-54.8019, -68.3030, "America/Argentina/Ushuaia")
ANCHORAGE = (61.2181, -149.9003, "America/Anchorage")
TROMSO = (69.6496, 18.9560, "Europe/Oslo")
ARCTIC = (66.57, 25.0, "Europe/Helsinki")
CHATHAM = (-43.95, -176.55, "Pacific/Chatham")
LONDON = (51.5074, -0.1278, "Europe/London")
APIA = (-13.8333, -171.7667, "Pacific/Apia")
KIRITIMATI = (1.87, -157.4, "Pacific/Kiritimati")
SAO_PAULO = (-23.55, -46.63, "America/Sao_Paulo")
#: A place for injected skies, which ignore it; the zone is the one thing used.
SYNTHETIC_UTC = (31.32556, 75.57917, "UTC")

ALL_PLACES = (
    JALANDHAR, JAMMU, USHUAIA, ANCHORAGE, TROMSO, ARCTIC, CHATHAM, LONDON,
    APIA, KIRITIMATI, SAO_PAULO, SYNTHETIC_UTC,
)

REFERENCE_DATE = date(1995, 3, 21)


@pytest.fixture(scope="module", autouse=True)
def ephemeris():
    with ephemeris_session(EPHE_DIR):
        yield


def at(year, month, day, hour=0, minute=0, second=0, microsecond=0, tz=UTC):
    return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=tz)


def jd(moment):
    return julian_day_ut(moment)


@functools.lru_cache(maxsize=None)
def day_of(civil_date, place, ordinal=None):
    """The date form at a real place, computed once per module run."""
    return panchanga_day(civil_date, *place, sunrise_ordinal=ordinal)


def complete(result):
    assert isinstance(result, PanchangaDay), result
    return result


def in_day_by_julian_day(day, moment):
    """Layer 16's membership predicate, on the two Julian Day floats."""
    return day.opening.julian_day_ut <= jd(moment) < day.closing.julian_day_ut


def in_listing_by_datetime(day, moment):
    """Layer 17's membership predicate for a representative, on datetimes."""
    return day.listing.start_utc <= moment < day.listing.end_utc


def cell_of(transition):
    return (
        transition.kind,
        transition.before.name,
        transition.after.name,
        transition.before_utc,
        transition.after_utc,
    )


def placed_containing(day, kind, moment):
    """The placed transition of ``kind`` whose cell ``(before, after]`` holds ``moment``."""
    found = [
        entry
        for entry in day.placed
        if entry.transition.kind is kind
        and entry.transition.before_utc < moment <= entry.transition.after_utc
    ]
    assert len(found) <= 1
    return found[0] if found else None


# --- injected skies and longitudes -----------------------------------------------


def sky(*sunrises):
    """A ``rise_after`` over fixed sunrise Julian Days (Layer 16's test shape)."""
    ordered = sorted(sunrises)

    def rise_after(julian_day, latitude, longitude):
        for sunrise in ordered:
            if sunrise >= julian_day:
                return sunrise
        return None

    return rise_after


def grid_aligned(start):
    """The first 100 ms grid point from ``start`` whose float maps back to it.

    A microsecond datetime does not survive datetime -> Julian Day -> datetime
    (the float grid is ~40 us), so a synthetic sunrise meant to sit exactly on
    the tolerance grid must be chosen among the grid points that do (probe E).
    """
    moment = start
    for _step in range(1000):
        julian_day = jd(moment)
        if datetime_from_julian_day(julian_day) == moment:
            return moment
        moment += DEFAULT_TOLERANCE
    raise AssertionError(f"no grid-aligned instant near {start}")


def grid_sky(first, days):
    """Grid-aligned synthetic sunrises one day apart; returns (moments, rise_after)."""
    moments = [grid_aligned(first + n * DAY) for n in days]
    return moments, sky(*[jd(moment) for moment in moments])


def linear_longitudes(x, *, rate=12.0, at_x=60.0):
    """An ``evaluate``: the Sun at 0 deg, the Moon at ``at_x`` deg at ``x``.

    With the defaults the tithi steps from index 4 to 5 exactly at ``x`` (60
    deg of elongation), the karana with it, and nothing else changes within
    hours of it (probes D2, E, F3).
    """

    def evaluate(moment):
        return 0.0, (at_x + rate * ((moment - x) / DAY)) % 360.0

    return evaluate


class AnchoredSky:
    """A ``rise_after`` whose sunrises depend on the walk anchor being asked.

    Layer 16 begins every search with the probe ``julian_day_ut(anchor) -
    SEARCH_SPAN_DAYS``; this sky recognises that first probe and answers the
    rest of the search from ``sunrises_for(anchor)``. That makes "a later
    locating of the same sunrise differs by 10 ms" and "one anchor sees a
    different sequence" deterministic, with Layer 16 unchanged. The synthetic
    sunrises must not lie on the 12-hour anchor grid: a later probe of one
    search (a sunrise plus half a day) would otherwise coincide with another
    anchor's first probe.
    """

    def __init__(self, sunrises_for, first, last):
        self.sunrises_for = sunrises_for
        self.starts = {}
        index = (first - ANCHOR_EPOCH) // ANCHOR_STEP
        anchor = ANCHOR_EPOCH + index * ANCHOR_STEP
        while anchor <= last:
            self.starts[jd(anchor) - SEARCH_SPAN_DAYS] = anchor
            anchor += ANCHOR_STEP
        self.anchor = None
        self.asked = []

    def __call__(self, julian_day, latitude, longitude):
        if julian_day in self.starts:
            self.anchor = self.starts[julian_day]
            self.asked.append(self.anchor)
        if self.anchor is None:
            raise AssertionError("the sky was asked before any anchor")
        for sunrise in self.sunrises_for(self.anchor):
            if sunrise >= julian_day:
                return sunrise
        return None


def anchor_index(anchor):
    return (anchor - ANCHOR_EPOCH) // ANCHOR_STEP


class Refused(Exception):
    """Raised by an injected callable that must never be reached."""


class Recorder:
    """``rise_after`` and ``evaluate`` that record and refuse every call."""

    def __init__(self):
        self.calls = []

    def rise_after(self, julian_day, latitude, longitude):
        self.calls.append(("rise_after", julian_day))
        raise Refused(julian_day)

    def evaluate(self, moment):
        self.calls.append(("evaluate", moment))
        raise Refused(moment)


# --- constants, vocabulary, surface ----------------------------------------------


def test_the_constants_are_the_specified_ones():
    assert ANCHOR_EPOCH == datetime(1970, 1, 1, tzinfo=UTC)
    assert ANCHOR_EPOCH.tzinfo is UTC
    assert ANCHOR_STEP == timedelta(hours=12)
    assert WALK_BEFORE == timedelta(hours=48)
    assert WALK_AFTER == timedelta(hours=108)
    assert CONTAINING_WALK_BEFORE == timedelta(hours=72)
    assert CONTAINING_WALK_AFTER == timedelta(hours=60)
    assert SAME_SUNRISE_MAX_SEPARATION == 0.5
    assert isinstance(SAME_SUNRISE_MAX_SEPARATION, float)
    assert SUPPORTED_DATE_START == date(1800, 1, 7)
    assert SUPPORTED_DATE_END == date(2399, 12, 21)
    assert SUPPORTED_INSTANT_START == datetime(1800, 1, 10, tzinfo=UTC)
    assert SUPPORTED_INSTANT_END == datetime(2399, 12, 21, tzinfo=UTC)
    assert MAX_OFFSET_HOURS == 16
    assert daily_module.DEFAULT_TOLERANCE is transitions_module.DEFAULT_TOLERANCE
    assert DEFAULT_TOLERANCE == timedelta(milliseconds=100)


def test_the_date_walk_visits_fourteen_anchors_and_the_containing_walk_eleven_or_twelve():
    """Spec 4.3 says "12 anchors" for the containing walk; the closed range
    ``[t - 72 h, t + 60 h]`` holds twelve when ``t`` is on the anchor grid and
    eleven otherwise (probes F1 and F2 walked eleven)."""
    origin = at(1995, 3, 21)
    assert len(daily_module._anchors(origin - WALK_BEFORE, origin + WALK_AFTER)) == 14

    on_grid = at(2024, 6, 21, 12)
    off_grid = at(2024, 6, 19, 3)
    assert len(daily_module._anchors(
        on_grid - CONTAINING_WALK_BEFORE, on_grid + CONTAINING_WALK_AFTER
    )) == 12
    anchors = daily_module._anchors(
        off_grid - CONTAINING_WALK_BEFORE, off_grid + CONTAINING_WALK_AFTER
    )
    assert len(anchors) == 11
    assert (anchors[0], anchors[-1]) == (at(2024, 6, 16, 12), at(2024, 6, 21, 12))


def test_the_error_types_are_the_specified_ones():
    assert issubclass(DayRequestError, ValueError)
    assert issubclass(UnsupportedDateError, ValueError)
    assert issubclass(DaySearchError, RuntimeError)
    assert not issubclass(DaySearchError, ValueError)
    assert daily_module.UnsupportedInstantError is UnsupportedInstantError
    assert daily_module.TransitionRequestError is TransitionRequestError


def test_the_enums_have_exactly_the_specified_members():
    assert [m.name for m in SunriseLocating] == [
        "CANONICAL_ANCHOR", "WINDOW_NEXT", "FIRST_ANCHOR",
    ]
    assert [m.name for m in DayPlacement] == [
        "WITHIN", "STRADDLES_OPENING_REFLECTED", "STRADDLES_OPENING_AFTER",
        "AT_OR_BEFORE_CLOSING",
    ]
    assert [m.name for m in DayUnavailableReason] == [
        "NO_SUNRISE_WITH_DATE", "SUNRISE_UNAVAILABLE", "NO_VARA_DAY_AT_SUNRISE",
    ]


LAYER_18_NAMES = (
    "panchanga_day", "panchanga_day_containing", "PanchangaDay",
    "PanchangaDayUnavailable", "PanchangaDayAmbiguous", "DaySunrise",
    "InstantElements", "PlacedTransition", "SunriseLocating", "DayPlacement",
    "DayUnavailableReason", "DayRequestError", "UnsupportedDateError",
    "DaySearchError", "ANCHOR_EPOCH", "ANCHOR_STEP", "WALK_BEFORE", "WALK_AFTER",
    "CONTAINING_WALK_BEFORE", "CONTAINING_WALK_AFTER",
    "SAME_SUNRISE_MAX_SEPARATION", "SUPPORTED_DATE_START", "SUPPORTED_DATE_END",
    "SUPPORTED_INSTANT_START", "SUPPORTED_INSTANT_END", "MAX_OFFSET_HOURS",
)


def test_the_package_re_exports_the_twenty_six_names_by_identity():
    assert len(LAYER_18_NAMES) == 26 == len(set(LAYER_18_NAMES))
    for name in LAYER_18_NAMES:
        assert name in package.__all__, name
        assert getattr(package, name) is getattr(daily_module, name), name
    assert package.__all__ == sorted(package.__all__)


def test_the_signatures_are_the_specified_ones():
    import inspect

    date_form = inspect.signature(panchanga_day)
    assert list(date_form.parameters) == [
        "civil_date", "latitude", "longitude", "timezone_id", "sunrise_ordinal",
        "tolerance", "rise_after", "evaluate",
    ]
    for name in ("sunrise_ordinal", "tolerance", "rise_after", "evaluate"):
        assert date_form.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert date_form.parameters["sunrise_ordinal"].default is None
    assert date_form.parameters["tolerance"].default is DEFAULT_TOLERANCE
    assert date_form.parameters["rise_after"].default is sunrise_module.default_rise_after
    assert date_form.parameters["evaluate"].default is transitions_module.default_evaluate

    containing = inspect.signature(panchanga_day_containing)
    assert list(containing.parameters) == [
        "moment_utc", "latitude", "longitude", "timezone_id", "tolerance",
        "rise_after", "evaluate",
    ]
    for name in ("tolerance", "rise_after", "evaluate"):
        assert containing.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert containing.parameters["tolerance"].default is DEFAULT_TOLERANCE
    assert containing.parameters["rise_after"].default is sunrise_module.default_rise_after
    assert containing.parameters["evaluate"].default is transitions_module.default_evaluate


def test_every_result_type_is_frozen():
    day = complete(day_of(REFERENCE_DATE, JALANDHAR))
    with pytest.raises(dataclasses.FrozenInstanceError):
        day.opening = day.closing
    with pytest.raises(dataclasses.FrozenInstanceError):
        day.opening.utc = day.closing.utc
    with pytest.raises(dataclasses.FrozenInstanceError):
        day.at_opening.tithi = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        day.placed[0].placement = AFTER
    for cls in (PanchangaDay, PanchangaDayUnavailable, PanchangaDayAmbiguous,
                DaySunrise, InstantElements, PlacedTransition):
        assert dataclasses.is_dataclass(cls) and cls.__dataclass_params__.frozen


def test_cells_at_closing_is_a_read_only_mapping():
    day = complete(day_of(REFERENCE_DATE, JALANDHAR))
    assert isinstance(day.cells_at_closing, MappingProxyType)
    with pytest.raises(TypeError):
        day.cells_at_closing[TITHI] = day.placed[0]


def test_the_module_source_has_no_assert_statement_and_no_forbidden_spelling():
    source = (REPO_ROOT / "src" / "vedic_chart" / "panchanga" / "daily.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Assert)]
    assert "assert" not in source
    assert "round(" not in source
    assert "astimezone(timezone.utc)" not in source


# --- the reference days (specification 11) -----------------------------------------

#: UTC cells, 100 ms, engine values (probe B, re-run for the implementation).
REFERENCE_DAYS = {
    "jalandhar": dict(
        place=JALANDHAR,
        civil_date=date(1995, 3, 21),
        opening=at(1995, 3, 21, 6, 35, 11, 853857, tz=IST),
        closing=at(1995, 3, 22, 6, 33, 56, 321939, tz=IST),
        vara="Mangalavara",
        cells=[
            (KARANA, "Kaulava", "Taitila",
             at(1995, 3, 21, 2, 58, 29, 900000), at(1995, 3, 21, 2, 58, 30)),
            (YOGA, "Harshana", "Vajra",
             at(1995, 3, 21, 3, 16, 31, 700000), at(1995, 3, 21, 3, 16, 31, 800000)),
            (NAKSHATRA, "Vishakha", "Anuradha",
             at(1995, 3, 21, 8, 8, 56, 600000), at(1995, 3, 21, 8, 8, 56, 700000)),
            (TITHI, "Panchami", "Shashthi",
             at(1995, 3, 21, 13, 45, 8, 200000), at(1995, 3, 21, 13, 45, 8, 300000)),
            (KARANA, "Taitila", "Garaja",
             at(1995, 3, 21, 13, 45, 8, 200000), at(1995, 3, 21, 13, 45, 8, 300000)),
            (YOGA, "Vajra", "Siddhi",
             at(1995, 3, 22, 0, 8, 51, 700000), at(1995, 3, 22, 0, 8, 51, 800000)),
            (KARANA, "Garaja", "Vanija",
             at(1995, 3, 22, 0, 33, 20), at(1995, 3, 22, 0, 33, 20, 100000)),
        ],
        # Layer 17 section 12's cells before the opening (their after_utc).
        before_opening={
            TITHI: at(1995, 3, 20, 16, 12, 55, 100000),
            NAKSHATRA: at(1995, 3, 20, 9, 53, 21, 800000),
            YOGA: at(1995, 3, 20, 6, 27, 42, 400000),
        },
    ),
    "jammu": dict(
        place=JAMMU,
        civil_date=date(2001, 2, 4),
        opening=at(2001, 2, 4, 7, 27, 37, 981834, tz=IST),
        closing=at(2001, 2, 5, 7, 26, 52, 40783, tz=IST),
        vara="Ravivara",
        cells=[
            (NAKSHATRA, "Rohini", "Mrigashira",
             at(2001, 2, 4, 2, 36, 52, 200000), at(2001, 2, 4, 2, 36, 52, 300000)),
            (YOGA, "Indra", "Vaidhriti",
             at(2001, 2, 4, 5, 32, 43), at(2001, 2, 4, 5, 32, 43, 100000)),
            (KARANA, "Vanija", "Vishti",
             at(2001, 2, 4, 10, 7, 50, 800000), at(2001, 2, 4, 10, 7, 50, 900000)),
            (TITHI, "Ekadashi", "Dwadashi",
             at(2001, 2, 4, 20, 53, 13, 800000), at(2001, 2, 4, 20, 53, 13, 900000)),
            (KARANA, "Vishti", "Bava",
             at(2001, 2, 4, 20, 53, 13, 800000), at(2001, 2, 4, 20, 53, 13, 900000)),
            (NAKSHATRA, "Mrigashira", "Ardra",
             at(2001, 2, 5, 0, 53, 2, 800000), at(2001, 2, 5, 0, 53, 2, 900000)),
        ],
        before_opening={
            TITHI: at(2001, 2, 3, 23, 13, 6, 500000),
            YOGA: at(2001, 2, 3, 8, 16, 47, 900000),
        },
    ),
}


@pytest.mark.parametrize("name", sorted(REFERENCE_DAYS))
def test_the_reference_day_is_the_recorded_sunrise_pair(name):
    case = REFERENCE_DAYS[name]
    day = complete(day_of(case["civil_date"], case["place"]))

    assert day.civil_date == case["civil_date"]
    assert day.sunrise_ordinal == 1
    assert day.opening.local == case["opening"]
    assert day.opening.utc == case["opening"]
    assert day.opening.local.utcoffset() == timedelta(hours=5, minutes=30)
    assert day.closing.local == case["closing"]
    assert day.opening.utc.tzinfo is UTC and day.closing.utc.tzinfo is UTC
    assert day.opening.located_by is CANONICAL
    assert day.closing.located_by is CANONICAL
    assert day.opening_window.previous_julian_day_ut == day.opening.julian_day_ut
    assert day.closing_window.previous_julian_day_ut == day.closing.julian_day_ut
    assert day.vara.name == case["vara"]
    assert day.vara.sunrise is day.opening_window
    assert day.location == PanchangaLocation(
        *case["place"], provenance=LocationProvenance.EXPLICIT
    )
    assert day.timezone_id == case["place"][2]
    assert day.layer16_at_instant is None and day.query_utc is None
    assert day.tolerance == DEFAULT_TOLERANCE
    assert day.calculation_convention == CALCULATION_CONVENTION
    assert day.sunrise_convention == SUNRISE_CONVENTION
    assert day.search_convention == SEARCH_CONVENTION


@pytest.mark.parametrize("name", sorted(REFERENCE_DAYS))
def test_the_reference_listing_is_exactly_the_recorded_cells_all_within(name):
    case = REFERENCE_DAYS[name]
    day = complete(day_of(case["civil_date"], case["place"]))

    assert [cell_of(t) for t in day.listing.transitions] == case["cells"]
    assert [entry.placement for entry in day.placed] == [WITHIN] * len(case["cells"])
    assert dict(day.cells_at_closing) == {}
    assert day.listing.unordered_pairs == ()
    assert day.listing.start_utc == day.opening.utc
    assert day.listing.end_utc == day.closing.utc
    # Carried whole, not rebuilt.
    assert day.listing == list_transitions(day.opening.utc, day.closing.utc)


@pytest.mark.parametrize("name", sorted(REFERENCE_DAYS))
def test_the_cells_before_the_opening_are_neighbours_not_listed(name):
    case = REFERENCE_DAYS[name]
    day = complete(day_of(case["civil_date"], case["place"]))

    listed = {t.after_utc for t in day.listing.transitions}
    for kind, after_utc in case["before_opening"].items():
        assert after_utc not in listed
        previous = day.transitions_at_opening.neighbours[kind].previous
        assert previous.after_utc == after_utc
        assert previous.after_utc < day.opening.utc


@pytest.mark.parametrize("name", sorted(REFERENCE_DAYS))
def test_the_opening_records_are_layer_16s_at_the_same_instant(name):
    """Whole-record equality is right here: same instant, same longitudes."""
    case = REFERENCE_DAYS[name]
    day = complete(day_of(case["civil_date"], case["place"]))
    layer16 = calculate_panchanga(day.opening.utc, *case["place"])

    assert day.at_opening.tithi == layer16.tithi
    assert day.at_opening.karana == layer16.karana
    assert day.at_opening.nakshatra == layer16.nakshatra
    assert day.at_opening.yoga == layer16.yoga
    assert day.at_opening.sun_sidereal_longitude == layer16.sun_sidereal_longitude
    assert day.at_opening.moon_sidereal_longitude == layer16.moon_sidereal_longitude
    assert layer16.vara.name == day.vara.name
    for kind, record in ((TITHI, day.at_opening.tithi), (KARANA, day.at_opening.karana),
                         (NAKSHATRA, day.at_opening.nakshatra), (YOGA, day.at_opening.yoga)):
        assert day.transitions_at_opening.neighbours[kind].current == record
    layer16_closing = calculate_panchanga(day.closing.utc, *case["place"])
    assert day.at_closing.tithi == layer16_closing.tithi
    assert day.at_closing.yoga == layer16_closing.yoga
    assert day.transitions_at_closing.instant_utc == day.closing.utc


def test_tithi_and_karana_changing_in_one_cell_are_ordered_never_unordered():
    day = complete(day_of(REFERENCE_DATE, JALANDHAR))
    kinds = [t.kind for t in day.listing.transitions]
    index = kinds.index(TITHI)

    assert kinds[index + 1] is KARANA
    tithi, karana = day.listing.transitions[index], day.listing.transitions[index + 1]
    assert (tithi.before_utc, tithi.after_utc) == (karana.before_utc, karana.after_utc)
    assert day.listing.unordered_pairs == ()


def test_placement_compares_indices_because_records_inside_a_cell_differ():
    """Probe D1: inside the Jalandhar tithi cell the current record has the
    departing index yet equals neither endpoint record."""
    day = complete(day_of(REFERENCE_DATE, JALANDHAR))
    tithi = next(t for t in day.listing.transitions if t.kind is TITHI)
    moment = at(1995, 3, 21, 13, 45, 8, 225000)
    assert tithi.before_utc < moment < tithi.after_utc

    current = find_transitions(moment, kinds=(TITHI,)).neighbours[TITHI].current

    assert current.index == tithi.before.index == 19
    assert current != tithi.before and current != tithi.after
    differing = [f.name for f in dataclasses.fields(current)
                 if getattr(current, f.name) != getattr(tithi.before, f.name)]
    assert differing == ["elongation", "degrees_in_tithi", "angular_fraction"]


# --- the two membership predicates (specification 7.1) --------------------------------


@pytest.mark.parametrize("name", sorted(REFERENCE_DAYS))
def test_the_four_membership_rows_at_both_endpoints(name):
    case = REFERENCE_DAYS[name]
    day = complete(day_of(case["civil_date"], case["place"]))
    opening, closing = day.opening.utc, day.closing.utc

    # (instant, Layer 16 Julian Day membership, Layer 17 datetime membership)
    rows = [
        (opening - US, True, False),
        (opening, True, True),
        (closing - US, False, True),
        (closing, False, False),
    ]
    for moment, by_julian_day, by_datetime in rows:
        assert in_day_by_julian_day(day, moment) is by_julian_day, moment
        assert in_listing_by_datetime(day, moment) is by_datetime, moment

    # The image check of spec 7.2, from the caller's side.
    assert jd(opening) == day.opening.julian_day_ut
    assert jd(closing) == day.closing.julian_day_ut


def datetimes_sharing_the_float(moment, julian_day):
    below = 0
    while jd(moment - (below + 1) * US) == julian_day:
        below += 1
    above = 0
    while jd(moment + (above + 1) * US) == julian_day:
        above += 1
    return below, above


@pytest.mark.parametrize("name", sorted(REFERENCE_DAYS))
def test_several_microsecond_datetimes_share_each_sunrise_float(name, record_property):
    """Recorded, not pinned beyond "at least one on each side" (probe D4
    measured 19 below and 20 above at both Jalandhar sunrises)."""
    case = REFERENCE_DAYS[name]
    day = complete(day_of(case["civil_date"], case["place"]))

    for label, sunrise in (("opening", day.opening), ("closing", day.closing)):
        below, above = datetimes_sharing_the_float(sunrise.utc, sunrise.julian_day_ut)
        record_property(f"{name}_{label}_sharing_below_above", (below, above))
        assert below >= 1 and above >= 1


# --- parity with Layer 16 (specification 11) ------------------------------------------


def consecutive_days(place, first, count):
    return [complete(day_of(first + n * DAY, place)) for n in range(count)]


#: The one observed exception to bit-for-bit parity at the three lower places
#: (a discrepancy with specification 11, reported at implementation): at
#: Ushuaia, Layer 16 asked at ``closing.utc - 1 s`` returned the same window
#: -- same vara, the identical ``next`` float -- but a ``previous`` float that
#: differs from the canonical opening, on 40 of 40 dates (2024-03-01 ..
#: 04-09), by up to 140.937 ms. Probe G traced the mechanism: when two
#: consecutive days together exceed 48 hours, an instant in the last minutes
#: before the closing puts Layer 16's first probe (instant - 2 d) just after
#: the previous sunrise, and the library, asked from about a day before the
#: opening, returns a float for it that differs from the one it returns from
#: the canonical anchor. Days at Ushuaia lengthen in March; at Jalandhar
#: (August, 83.7 ms), Anchorage (September, 88.3 ms) and London (September,
#: 35.9 ms) the same thing was measured in their lengthening seasons, which the
#: March dates of this test do not visit. The canonical rule of spec 4.1 is
#: what keeps Layer 18 consistent there; the difference is recorded, not pinned.
PARITY_BY_EVENT_ONLY = {("ushuaia", "closing-1s")}


@pytest.mark.parametrize(
    "name, place",
    [("jalandhar", JALANDHAR), ("ushuaia", USHUAIA), ("anchorage", ANCHORAGE)],
)
def test_layer_16_agrees_across_forty_days(name, place, record_property):
    largest_ms = 0.0
    for day in consecutive_days(place, date(2024, 3, 1), 40):
        middle = day.opening.utc + (day.closing.utc - day.opening.utc) / 2
        for label, moment in (("opening", day.opening.utc),
                              ("opening+1s", day.opening.utc + SECOND),
                              ("mid-day", middle),
                              ("closing-1s", day.closing.utc - SECOND)):
            layer16 = calculate_panchanga(moment, *place)
            window = layer16.sunrise
            assert isinstance(window, SunriseWindow)
            assert layer16.vara.index == day.vara.index, moment
            assert window.next_julian_day_ut == day.closing.julian_day_ut, moment
            if (name, label) in PARITY_BY_EVENT_ONLY:
                gap = window.previous_julian_day_ut - day.opening.julian_day_ut
                assert abs(gap) < SAME_SUNRISE_MAX_SEPARATION
                largest_ms = max(largest_ms, abs(gap) * 86400e3)
            else:
                assert window.previous_julian_day_ut == day.opening.julian_day_ut, (
                    label, moment
                )
    record_property(f"{name}_largest_previous_difference_ms", largest_ms)


#: Recorded at implementation (cloud venv, 2024-02-01 .. 2024-03-11, 40 days):
#: Layer 16 at ``opening.utc`` itself named another (the previous) window on 16
#: of 40 dates; the largest same-event float difference seen at the sampled
#: instants was 11.507 ms (at ``opening.utc + 1 s``). Sampled values, not
#: bounds; not pinned.
TROMSO_RECORD: dict = {}


def test_layer_16_agrees_at_tromso_by_event_identity_and_the_rest_is_recorded(
    record_property,
):
    disagreements = 0
    largest_ms = 0.0
    days = consecutive_days(TROMSO, date(2024, 2, 1), 40)
    for day in days:
        middle = day.opening.utc + (day.closing.utc - day.opening.utc) / 2
        for moment in (day.opening.utc + SECOND, middle, day.closing.utc - SECOND):
            layer16 = calculate_panchanga(moment, *TROMSO)
            window = layer16.sunrise
            assert isinstance(window, SunriseWindow)
            assert layer16.vara.index == day.vara.index, moment
            previous_gap = window.previous_julian_day_ut - day.opening.julian_day_ut
            next_gap = window.next_julian_day_ut - day.closing.julian_day_ut
            assert abs(previous_gap) < SAME_SUNRISE_MAX_SEPARATION
            assert abs(next_gap) < SAME_SUNRISE_MAX_SEPARATION
            largest_ms = max(largest_ms, abs(previous_gap) * 86400e3,
                             abs(next_gap) * 86400e3)

        layer16 = calculate_panchanga(day.opening.utc, *TROMSO)
        window = layer16.sunrise
        if not (isinstance(window, SunriseWindow) and abs(
            window.previous_julian_day_ut - day.opening.julian_day_ut
        ) < SAME_SUNRISE_MAX_SEPARATION):
            disagreements += 1
        elif isinstance(window, SunriseWindow):
            largest_ms = max(largest_ms, abs(
                window.previous_julian_day_ut - day.opening.julian_day_ut
            ) * 86400e3)

    TROMSO_RECORD.update(
        dates=len(days), disagreements_at_opening=disagreements, largest_ms=largest_ms
    )
    record_property("tromso_layer16_disagreements_at_opening", disagreements)
    record_property("tromso_largest_same_event_difference_ms", largest_ms)
    print(f"\nTromso, {len(days)} dates: Layer 16 at opening.utc named another "
          f"window on {disagreements}; largest same-event difference "
          f"{largest_ms:.3f} ms (sampled values)")
    assert 0 <= disagreements <= len(days)


# --- consecutive days and partitioning (specification 11) ------------------------------

PARTITION_RUNS = {
    "jalandhar": (JALANDHAR, date(2024, 3, 1)),
    "ushuaia": (USHUAIA, date(2024, 3, 1)),
    "chatham": (CHATHAM, date(2024, 4, 1)),
    "london-spring": (LONDON, date(2024, 3, 25)),
    "london-autumn": (LONDON, date(2024, 10, 21)),
    "tromso-february": (TROMSO, date(2024, 2, 1)),
}


def assert_reciprocal(earlier, later):
    """cells_at_closing of one day <-> STRADDLES_OPENING_REFLECTED of the next."""
    reflected = [e.transition for e in later.placed if e.placement is REFLECTED]
    cells = [e.transition for e in earlier.cells_at_closing.values()]
    for cell in cells:
        assert any(same_event(cell, t) for t in reflected), cell
    for transition in reflected:
        assert any(same_event(transition, c) for c in cells), transition


@pytest.mark.parametrize("name", sorted(PARTITION_RUNS))
def test_twelve_consecutive_days_share_their_sunrises_and_partition_the_run(name):
    place, first = PARTITION_RUNS[name]
    days = consecutive_days(place, first, 12)

    for earlier, later in zip(days, days[1:]):
        assert earlier.closing.julian_day_ut == later.opening.julian_day_ut
        assert earlier.closing.utc == later.opening.utc
        assert earlier.closing.local == later.opening.local
        assert earlier.closing.local.utcoffset() == later.opening.local.utcoffset()
        assert earlier.closing.located_by is CANONICAL
        assert earlier.closing_window is later.opening_window or (
            earlier.closing_window == later.opening_window
        )
        assert_reciprocal(earlier, later)

    union = [t for day in days for t in day.listing.transitions]
    whole = list_transitions(days[0].opening.utc, days[-1].closing.utc)
    assert tuple(union) == whole.transitions
    ids = [t.event_id for t in union]
    assert len(ids) == len(set(ids))
    assert set(ids) == {t.event_id for t in whole.transitions}


# --- the closing boundary, with actual changes (probe E) --------------------------------

#: Grid-aligned synthetic sunrises one day apart around the Jalandhar reference
#: closing (probe E scanned from 01:03:56.300); the day of 1995-03-21 closes at
#: ``GRID_CLOSING``.
GRID_MOMENTS, GRID_SKY = grid_sky(at(1995, 3, 21, 1, 3, 56, 300000), range(-5, 6))
GRID_OPENING, GRID_CLOSING = GRID_MOMENTS[5], GRID_MOMENTS[6]
#: The same sequence ending at the closing: Layer 16 then finds no next sunrise.
ENDING_MOMENTS, ENDING_SKY = GRID_MOMENTS[:7], sky(*[jd(m) for m in GRID_MOMENTS[:7]])

CLOSING_CASES = {
    # label: (offset of the change from the closing, cell carried at the closing)
    "exactly-at-closing": (timedelta(0), True),
    "one-us-before-closing": (-US, True),
    "one-us-after-closing": (US, False),
}


def test_the_grid_aligned_synthetic_sunrises_are_on_the_grid():
    for moment in GRID_MOMENTS:
        assert (moment - ANCHOR_EPOCH) % DEFAULT_TOLERANCE == timedelta(0)
        assert datetime_from_julian_day(jd(moment)) == moment
    assert GRID_OPENING.date() == date(1995, 3, 21)


@pytest.mark.parametrize("label", sorted(CLOSING_CASES))
def test_a_change_at_or_just_before_the_closing_is_reported_at_or_before_closing(label):
    offset, carried = CLOSING_CASES[label]
    change = GRID_CLOSING + offset
    evaluate = linear_longitudes(change)

    this = complete(panchanga_day(REFERENCE_DATE, *JALANDHAR, rise_after=GRID_SKY,
                                  evaluate=evaluate))
    following = complete(panchanga_day(REFERENCE_DATE + DAY, *JALANDHAR,
                                       rise_after=GRID_SKY, evaluate=evaluate))
    assert this.closing.utc == GRID_CLOSING == following.opening.utc
    assert this.closing.located_by is CANONICAL

    # Which day's listing carries the cell: the next one, in all three cases.
    assert placed_containing(this, TITHI, change) is None
    listed = placed_containing(following, TITHI, change)
    assert listed is not None

    # JD membership of the actual change instant in this day: out, out, out.
    assert not in_day_by_julian_day(this, change)

    if carried:
        cell = this.cells_at_closing[TITHI]
        assert cell.placement is AT_OR_BEFORE_CLOSING
        assert cell.transition.after_utc == this.closing.utc
        assert cell.transition.before_utc < this.closing.utc <= cell.transition.after_utc
        assert same_event(cell.transition, listed.transition)
        assert listed.placement is REFLECTED
        assert set(this.cells_at_closing) == {TITHI, KARANA}
    else:
        assert TITHI not in this.cells_at_closing
        assert listed.transition.before_utc == following.opening.utc
        assert listed.placement is WITHIN
    assert_reciprocal(this, following)


@pytest.mark.parametrize("label", sorted(CLOSING_CASES))
def test_the_same_three_changes_against_a_window_next_closing(label):
    offset, carried = CLOSING_CASES[label]
    change = GRID_CLOSING + offset
    evaluate = linear_longitudes(change)

    this = complete(panchanga_day(REFERENCE_DATE, *JALANDHAR, rise_after=ENDING_SKY,
                                  evaluate=evaluate))
    assert this.closing.located_by is WINDOW_NEXT
    assert this.closing_window is None
    assert this.closing.utc == GRID_CLOSING
    assert placed_containing(this, TITHI, change) is None
    assert not in_day_by_julian_day(this, change)

    # No day lists it: the closing's own date carries only a next-only sunrise.
    after = panchanga_day(REFERENCE_DATE + DAY, *JALANDHAR, rise_after=ENDING_SKY,
                          evaluate=evaluate)
    assert isinstance(after, PanchangaDayUnavailable)
    assert after.reason is DayUnavailableReason.NO_VARA_DAY_AT_SUNRISE
    assert after.lone_sunrise.utc == GRID_CLOSING

    if carried:
        cell = this.cells_at_closing[TITHI]
        assert cell.placement is AT_OR_BEFORE_CLOSING
        assert cell.transition.after_utc == this.closing.utc
    else:
        assert TITHI not in this.cells_at_closing


# --- placement at the opening (probe F3) ---------------------------------------------

GRID_OPENING_MOMENTS, GRID_OPENING_SKY = grid_sky(
    at(1995, 3, 21, 1, 5, 11, 900000), range(-5, 6)
)
GRID_ALIGNED_OPENING = GRID_OPENING_MOMENTS[5]

OPENING_CASES = {
    "one-us-before": -US,
    "exactly-at": timedelta(0),
    "one-us-after": US,
}


@pytest.mark.parametrize("label", sorted(OPENING_CASES))
def test_placement_at_a_grid_aligned_opening(label):
    """(a) A change 1 us after a grid-aligned opening lies in the cell that
    starts at the opening and is WITHIN; at and 1 us before are reflected."""
    change = GRID_ALIGNED_OPENING + OPENING_CASES[label]
    day = complete(panchanga_day(REFERENCE_DATE, *JALANDHAR,
                                 rise_after=GRID_OPENING_SKY,
                                 evaluate=linear_longitudes(change)))
    assert day.opening.utc == GRID_ALIGNED_OPENING
    entry = placed_containing(day, TITHI, change)
    assert entry is not None, "listed by this day"

    if label == "one-us-after":
        assert entry.transition.before_utc == day.opening.utc
        assert entry.placement is WITHIN
    else:
        assert entry.transition.after_utc == day.opening.utc
        assert entry.placement is REFLECTED
        assert entry.transition.after.index == day.at_opening.tithi.index
        assert same_event(entry.transition,
                          day.transitions_at_opening.neighbours[TITHI].previous)


@pytest.mark.parametrize("label", sorted(OPENING_CASES))
def test_placement_at_the_real_jalandhar_opening(label):
    """(b) The real opening 01:05:11.853857 lies strictly inside the cell
    01:05:11.800-.900: 1 us after is STRADDLES_OPENING_AFTER."""
    opening = complete(day_of(REFERENCE_DATE, JALANDHAR)).opening.utc
    assert opening == at(1995, 3, 21, 1, 5, 11, 853857)
    change = opening + OPENING_CASES[label]
    day = complete(panchanga_day(REFERENCE_DATE, *JALANDHAR,
                                 evaluate=linear_longitudes(change)))
    entry = placed_containing(day, TITHI, change)
    assert entry is not None
    assert (entry.transition.before_utc, entry.transition.after_utc) == (
        at(1995, 3, 21, 1, 5, 11, 800000), at(1995, 3, 21, 1, 5, 11, 900000)
    )
    neighbours = day.transitions_at_opening.neighbours[TITHI]

    if label == "one-us-after":
        assert entry.placement is AFTER
        assert same_event(entry.transition, neighbours.next)
        # By index: the departing record is not the opening's record.
        assert entry.transition.before.index == day.at_opening.tithi.index
        assert entry.transition.before != day.at_opening.tithi
    else:
        assert entry.placement is REFLECTED
        assert same_event(entry.transition, neighbours.previous)
        assert entry.transition.after.index == day.at_opening.tithi.index
        assert entry.transition.after != day.at_opening.tithi


# --- the containing-form ordinal regression (specification 4.3, probe F1) ----------------

F1_BASE = at(1867, 10, 18, 10)
F1_SKY = sky(*[jd(F1_BASE + n * timedelta(hours=47)) for n in range(-6, 10)])
F1_DATE = date(1867, 10, 19)


def test_the_containing_form_takes_its_ordinal_from_the_date_forms_enumeration():
    """Synthetic coverage of Layer 16's allowed-gap contract, not an observed
    astronomical sequence: sunrises at UTC 1867-10-18 10:00 + n x 47 h through
    the unchanged ``julian_day_ut``, in America/Anchorage, whose real 1867 date
    repetition puts two of them on civil date 1867-10-19."""
    ambiguous = panchanga_day(F1_DATE, *ANCHORAGE, rise_after=F1_SKY)
    assert isinstance(ambiguous, PanchangaDayAmbiguous)
    assert len(ambiguous.candidates) == 2
    assert [c.local.date() for c in ambiguous.candidates] == [F1_DATE, F1_DATE]
    assert all(c.located_by is CANONICAL for c in ambiguous.candidates)

    query = at(1867, 10, 22, 7)
    containing = complete(panchanga_day_containing(query, *ANCHORAGE, rise_after=F1_SKY))
    assert containing.civil_date == F1_DATE
    assert containing.sunrise_ordinal == 2
    assert containing.opening.julian_day_ut == ambiguous.candidates[1].julian_day_ut

    # The containing walk sees the first 10-19 sunrise only at its first anchor.
    walk = daily_module._walk(query - CONTAINING_WALK_BEFORE,
                              query + CONTAINING_WALK_AFTER, *ANCHORAGE, F1_SKY)
    assert walk.located[0].anchor == at(1867, 10, 19, 12)
    assert walk.located[0].canonical is False
    assert (walk.located[0].window.previous_julian_day_ut
            == ambiguous.candidates[0].julian_day_ut)

    second = complete(panchanga_day(F1_DATE, *ANCHORAGE, sunrise_ordinal=2,
                                    rise_after=F1_SKY))
    assert second.opening == containing.opening
    assert second.closing == containing.closing
    assert second.opening.julian_day_ut == containing.opening.julian_day_ut
    assert second.closing.julian_day_ut == containing.closing.julian_day_ut
    assert second.closing.located_by is CANONICAL is containing.closing.located_by
    assert second.listing.transitions == containing.listing.transitions
    assert len(second.listing.transitions) == 12

    first = complete(panchanga_day(F1_DATE, *ANCHORAGE, sunrise_ordinal=1,
                                   rise_after=F1_SKY))
    assert first.opening.julian_day_ut != containing.opening.julian_day_ut
    assert first.opening.utc.date() == date(1867, 10, 18)

    with pytest.raises(DayRequestError, match=r"larger than the 2 canonical"):
        panchanga_day(F1_DATE, *ANCHORAGE, sunrise_ordinal=3, rise_after=F1_SKY)


# --- civil-date cases, real tz data (specification 11) -----------------------------------


def test_apia_skips_a_date_and_the_day_before_it_closes_two_dates_later():
    before = complete(day_of(date(2011, 12, 29), APIA))
    skipped = day_of(date(2011, 12, 30), APIA)
    after = complete(day_of(date(2011, 12, 31), APIA))

    assert isinstance(skipped, PanchangaDayUnavailable)
    assert skipped.reason is DayUnavailableReason.NO_SUNRISE_WITH_DATE
    assert skipped.layer16_reasons == ()
    assert skipped.preceding_sunrise == before.opening
    assert skipped.following_sunrise == after.opening
    assert skipped.lone_sunrise is None and skipped.at_lone_sunrise is None
    assert (before.closing.local.date() - before.opening.local.date()).days == 2
    assert before.closing == after.opening


@pytest.mark.parametrize("ordinal", [1, 2])
def test_an_explicit_ordinal_on_a_skipped_date_is_the_unavailable_result(ordinal):
    """Specification 4.3 and 9 (v1.0): zero candidates is a result, whatever the ordinal.

    A valid positive ordinal does not turn a date the zone skips into a
    ``DayRequestError``; the ordinal is checked against the candidates only when
    there are candidates. The result equals the one an ordinal-free request gives.
    """
    plain = day_of(date(2011, 12, 30), APIA)
    explicit = day_of(date(2011, 12, 30), APIA, ordinal)

    assert isinstance(explicit, PanchangaDayUnavailable)
    assert explicit.reason is DayUnavailableReason.NO_SUNRISE_WITH_DATE
    assert explicit == plain


@pytest.mark.parametrize("civil_date, reason", [
    (date(2024, 6, 21), DayUnavailableReason.SUNRISE_UNAVAILABLE),
    (date(2024, 5, 21), DayUnavailableReason.NO_VARA_DAY_AT_SUNRISE),
    (date(2025, 11, 27), DayUnavailableReason.SUNRISE_UNAVAILABLE),
])
def test_an_explicit_ordinal_on_a_polar_unavailable_date_is_the_unavailable_result(
    civil_date, reason
):
    """Specification 4.3 and 9 (v1.0): the polar results are results with an ordinal too."""
    plain = unavailable(day_of(civil_date, TROMSO), reason)
    explicit = day_of(civil_date, TROMSO, 1)

    assert isinstance(explicit, PanchangaDayUnavailable)
    assert explicit.reason is reason
    assert explicit == plain


def test_kiritimati_skips_a_date():
    before = complete(day_of(date(1994, 12, 30), KIRITIMATI))
    skipped = day_of(date(1994, 12, 31), KIRITIMATI)
    after = complete(day_of(date(1995, 1, 1), KIRITIMATI))

    assert isinstance(skipped, PanchangaDayUnavailable)
    assert skipped.reason is DayUnavailableReason.NO_SUNRISE_WITH_DATE
    assert skipped.preceding_sunrise == before.opening
    assert skipped.following_sunrise == after.opening
    assert before.closing == after.opening
    assert before.closing.local.date() == date(1995, 1, 1)


def test_anchorage_repeats_a_date_and_both_of_its_days_are_complete():
    eighteenth = complete(day_of(date(1867, 10, 18), ANCHORAGE))
    ambiguous = day_of(date(1867, 10, 19), ANCHORAGE)
    twentieth = complete(day_of(date(1867, 10, 20), ANCHORAGE))

    assert isinstance(ambiguous, PanchangaDayAmbiguous)
    assert len(ambiguous.candidates) == 2
    first = complete(day_of(date(1867, 10, 19), ANCHORAGE, 1))
    second = complete(day_of(date(1867, 10, 19), ANCHORAGE, 2))
    assert [first.opening, second.opening] == list(ambiguous.candidates)
    assert first.opening.local.utcoffset() == timedelta(hours=14, seconds=24)
    assert second.opening.local.utcoffset() == -timedelta(hours=9, minutes=59,
                                                          seconds=36)
    assert eighteenth.closing == first.opening
    assert first.closing == second.opening
    assert second.closing == twentieth.opening
    assert first.vara.name == second.vara.name == "Shanivara"
    with pytest.raises(DayRequestError):
        panchanga_day(date(1867, 10, 19), *ANCHORAGE, sunrise_ordinal=3)


@pytest.mark.parametrize(
    "place, dates",
    [
        (SAO_PAULO, [date(2018, 11, 3), date(2018, 11, 4), date(2018, 11, 5)]),
        (SAO_PAULO, [date(2019, 2, 16), date(2019, 2, 17)]),
        (LONDON, [date(2024, 3, 30), date(2024, 3, 31)]),
        (LONDON, [date(2024, 10, 26), date(2024, 10, 27)]),
        (CHATHAM, [date(2024, 4, 6), date(2024, 4, 7)]),
        (CHATHAM, [date(2024, 9, 28), date(2024, 9, 29)]),
    ],
    ids=["sao-paulo-spring", "sao-paulo-autumn", "london-spring", "london-autumn",
         "chatham-autumn", "chatham-spring"],
)
def test_daylight_saving_dates_are_ordinary_days(place, dates):
    days = [complete(day_of(d, place)) for d in dates]
    for civil_date, day in zip(dates, days):
        assert day.civil_date == civil_date == day.opening.local.date()
        assert day.vara.english_weekday == civil_date.strftime("%A")
        hours = (day.closing.julian_day_ut - day.opening.julian_day_ut) * 24
        assert 23.9 < hours < 24.1
    for earlier, later in zip(days, days[1:]):
        assert earlier.closing == later.opening
    offsets = {d.opening.local.utcoffset() for d in days} | {
        d.closing.local.utcoffset() for d in days
    }
    assert len(offsets) == 2, "the run crosses the clock change"


def test_a_datetime_is_not_a_civil_date():
    recorder = Recorder()
    for value in (at(1995, 3, 21), datetime(1995, 3, 21), at(1995, 3, 21, tz=IST)):
        with pytest.raises(DayRequestError, match="not a datetime"):
            panchanga_day(value, *JALANDHAR, rise_after=recorder.rise_after,
                          evaluate=recorder.evaluate)
    assert recorder.calls == []


ZONES_USED = sorted({place[2] for place in ALL_PLACES} | {
    # The extremes spec 4.10 found in the installed database.
    "America/Metlakatla", "Asia/Manila",
})


@pytest.mark.parametrize("zone", ZONES_USED)
def test_max_offset_hours_covers_the_zones_used(zone):
    """Spec 4.10's coverage assumption, checked against the installed tz data."""
    tz = ZoneInfo(zone)
    bound = timedelta(hours=MAX_OFFSET_HOURS)
    for year in (1800, 1867, 1900, 1950, 2000, 2024):
        for month in range(1, 13):
            offset = at(year, month, 1, 12).astimezone(tz).utcoffset()
            assert -bound <= offset <= bound, (zone, year, month, offset)


# --- polar, through both entry points (specification 11) ---------------------------------


def date_walk_range(civil_date):
    origin = at(civil_date.year, civil_date.month, civil_date.day)
    return origin - WALK_BEFORE, origin + WALK_AFTER


def containing_walk_range(moment):
    return moment - CONTAINING_WALK_BEFORE, moment + CONTAINING_WALK_AFTER


def unavailable(result, reason):
    assert isinstance(result, PanchangaDayUnavailable), result
    assert result.reason is reason
    assert not hasattr(result, "vara"), "no invented weekday"
    assert set(result.layer16_reasons) <= set(UNAVAILABLE_REASONS)
    return result


BOTH_REASONS = (REASON_NO_NEXT_SUNRISE, REASON_NO_PREVIOUS_SUNRISE)


@pytest.mark.parametrize(
    "civil_date, reasons",
    [
        (date(2025, 11, 26), BOTH_REASONS),
        (date(2025, 11, 27), (REASON_NO_PREVIOUS_SUNRISE,)),
        (date(2025, 11, 28), (REASON_NO_PREVIOUS_SUNRISE,)),
        (date(2025, 11, 29), (REASON_NO_PREVIOUS_SUNRISE,)),
    ],
)
def test_tromso_polar_night_dates_are_unavailable_with_layer_16s_reasons(
    civil_date, reasons
):
    result = unavailable(day_of(civil_date, TROMSO),
                         DayUnavailableReason.SUNRISE_UNAVAILABLE)
    assert result.layer16_reasons == reasons
    assert result.civil_date == civil_date and result.query_utc is None


def test_tromso_2026_01_16_reports_the_first_sunrise_its_walk_reaches():
    assert date_walk_range(date(2026, 1, 16)) == (at(2026, 1, 14), at(2026, 1, 20, 12))
    result = unavailable(day_of(date(2026, 1, 16), TROMSO),
                         DayUnavailableReason.SUNRISE_UNAVAILABLE)
    assert result.layer16_reasons == (REASON_NO_PREVIOUS_SUNRISE,)
    assert result.preceding_sunrise is None
    following = result.following_sunrise
    assert following.local == at(2026, 1, 19, 11, 35, 35, 795885,
                                 tz=ZoneInfo("Europe/Oslo"))
    assert following.located_by is CANONICAL


def test_tromso_2026_01_19_is_the_first_day_of_the_year():
    day = complete(day_of(date(2026, 1, 19), TROMSO))
    oslo = ZoneInfo("Europe/Oslo")
    assert day.opening.local == at(2026, 1, 19, 11, 35, 35, 795885, tz=oslo)
    assert day.closing.local == at(2026, 1, 20, 11, 15, 37, 125742, tz=oslo)
    hours = (day.closing.julian_day_ut - day.opening.julian_day_ut) * 24
    assert f"{hours:.3f}" == "23.667"
    assert day.closing.located_by is CANONICAL


def test_tromso_may_2024_ends_with_a_window_next_closing_and_a_lone_sunrise():
    eighteenth = complete(day_of(date(2024, 5, 18), TROMSO))
    nineteenth = complete(day_of(date(2024, 5, 19), TROMSO))
    for day in (eighteenth, nineteenth):
        hours = (day.closing.julian_day_ut - day.opening.julian_day_ut) * 24
        assert 23.75 < hours < 23.85
        assert day.closing.located_by is CANONICAL

    final = complete(day_of(date(2024, 5, 20), TROMSO))
    assert final.opening == nineteenth.closing
    assert final.closing.located_by is WINDOW_NEXT
    assert final.closing_window is None
    assert final.closing.julian_day_ut == final.opening_window.next_julian_day_ut

    lone = unavailable(day_of(date(2024, 5, 21), TROMSO),
                       DayUnavailableReason.NO_VARA_DAY_AT_SUNRISE)
    assert lone.lone_sunrise == final.closing
    assert lone.lone_sunrise.located_by is WINDOW_NEXT
    assert isinstance(lone.at_lone_sunrise, InstantElements)
    layer17 = find_transitions(lone.lone_sunrise.utc)
    assert lone.at_lone_sunrise.tithi == layer17.neighbours[TITHI].current
    assert lone.layer16_reasons == BOTH_REASONS
    assert lone.preceding_sunrise == final.opening
    assert date_walk_range(date(2024, 5, 21))[1] == at(2024, 5, 25, 12)
    assert lone.following_sunrise is None


def test_tromso_midsummer_is_unavailable():
    result = unavailable(day_of(date(2024, 6, 21), TROMSO),
                         DayUnavailableReason.SUNRISE_UNAVAILABLE)
    assert result.layer16_reasons == (REASON_NO_PREVIOUS_SUNRISE,)
    assert result.preceding_sunrise is None and result.following_sunrise is None


def test_tromso_july_2024_resumes_with_days_longer_than_24_hours():
    days = [complete(day_of(date(2024, 7, d), TROMSO)) for d in (22, 23, 24)]
    hours = [(d.closing.julian_day_ut - d.opening.julian_day_ut) * 24 for d in days]
    assert f"{hours[0]:.2f}" == "24.27"
    assert f"{hours[1]:.2f}" == "24.20"
    assert days[0].closing == days[1].opening and days[1].closing == days[2].opening


def test_the_arctic_circle_in_june_through_the_date_form():
    place = ARCTIC
    helsinki = ZoneInfo("Europe/Helsinki")
    resumed = at(2024, 6, 23, 1, 27, 51, 921314, tz=helsinki)
    lone_local = at(2024, 6, 19, 1, 26, 6, 212815, tz=helsinki)

    seventeenth = complete(day_of(date(2024, 6, 17), place))
    assert seventeenth.closing.located_by is CANONICAL

    final = complete(day_of(date(2024, 6, 18), place))
    assert final.opening == seventeenth.closing
    assert final.closing.located_by is WINDOW_NEXT and final.closing_window is None
    assert final.closing.local == lone_local

    # 06-19: the lone sunrise; its walk [06-17 00:00, 06-23 12:00] UTC reaches
    # the resumed sunrise's first anchor, 06-23 00:00 UTC.
    assert date_walk_range(date(2024, 6, 19)) == (at(2024, 6, 17), at(2024, 6, 23, 12))
    lone = unavailable(day_of(date(2024, 6, 19), place),
                       DayUnavailableReason.NO_VARA_DAY_AT_SUNRISE)
    assert lone.lone_sunrise == final.closing
    assert lone.at_lone_sunrise is not None
    assert lone.following_sunrise.local == resumed
    assert lone.following_sunrise.located_by is CANONICAL
    assert lone.preceding_sunrise == final.opening

    # 06-20: walk [06-18 00:00, 06-24 12:00] UTC starts inside the 06-18 window
    # (06-17 22:31 .. 06-18 22:26 UTC), seen at its first anchor as FIRST_ANCHOR,
    # so the lone sunrise is its window's next.
    assert date_walk_range(date(2024, 6, 20)) == (at(2024, 6, 18), at(2024, 6, 24, 12))
    walk = daily_module._select_date(date(2024, 6, 20), *place,
                                     sunrise_module.default_rise_after).walk
    assert walk.located[0].anchor == at(2024, 6, 18)
    assert walk.located[0].canonical is False
    assert walk.located[0].window.previous_julian_day_ut == final.opening.julian_day_ut
    gap = unavailable(day_of(date(2024, 6, 20), place),
                      DayUnavailableReason.SUNRISE_UNAVAILABLE)
    assert gap.preceding_sunrise == final.closing
    assert gap.preceding_sunrise.located_by is WINDOW_NEXT
    assert gap.following_sunrise.local == resumed
    assert gap.layer16_reasons == BOTH_REASONS

    # 06-21 and 06-22: walks start at 06-19 00:00 and 06-20 00:00 UTC, after the
    # 06-18 window ended at 06-18 22:26 UTC: no preceding sunrise within them.
    for civil_date, start in ((date(2024, 6, 21), at(2024, 6, 19)),
                              (date(2024, 6, 22), at(2024, 6, 20))):
        assert date_walk_range(civil_date)[0] == start > final.closing.utc
        gap = unavailable(day_of(civil_date, place),
                          DayUnavailableReason.SUNRISE_UNAVAILABLE)
        assert gap.preceding_sunrise is None
        assert gap.following_sunrise.local == resumed
        assert gap.layer16_reasons == BOTH_REASONS

    first = complete(day_of(date(2024, 6, 23), place))
    assert first.opening.local == resumed
    assert first.closing.located_by is CANONICAL


def test_the_arctic_circle_in_june_through_the_containing_form():
    place = ARCTIC
    final = complete(day_of(date(2024, 6, 18), place))
    resumed = complete(day_of(date(2024, 6, 23), place))

    midday = complete(panchanga_day_containing(at(2024, 6, 18, 10), *place))
    assert midday.opening == final.opening and midday.closing == final.closing
    assert midday.closing.located_by is WINDOW_NEXT

    # 06-19 06:00 local = 03:00 UTC: walk [06-16 03:00, 06-21 15:00] UTC, last
    # anchor 06-21 12:00; the resumed sunrise (first anchor 06-23 00:00) is
    # outside it, so following_sunrise is None (probe F2).
    query = at(2024, 6, 19, 3)
    assert at(2024, 6, 19, 6, tz=ZoneInfo("Europe/Helsinki")) == query
    assert containing_walk_range(query) == (at(2024, 6, 16, 3), at(2024, 6, 21, 15))
    result = unavailable(panchanga_day_containing(query, *place),
                         DayUnavailableReason.SUNRISE_UNAVAILABLE)
    assert result.query_utc == query and result.civil_date is None
    assert result.preceding_sunrise == final.closing
    assert result.preceding_sunrise.located_by is WINDOW_NEXT
    assert result.following_sunrise is None
    assert isinstance(result.layer16_at_instant, SunriseUnavailable)
    assert result.layer16_reasons == BOTH_REASONS

    # 06-21 12:00 UTC: walk [06-18 12:00, 06-24 00:00] UTC; the 06-18 window is
    # seen at the first anchor (FIRST_ANCHOR), its next is the lone sunrise, and
    # the resumed sunrise is found at anchor 06-23 00:00 UTC.
    query = at(2024, 6, 21, 12)
    assert containing_walk_range(query) == (at(2024, 6, 18, 12), at(2024, 6, 24))
    walk = daily_module._walk(*containing_walk_range(query), *place,
                              sunrise_module.default_rise_after)
    assert walk.located[0].anchor == at(2024, 6, 18, 12)
    assert walk.located[0].canonical is False
    found = [e for e in walk.located
             if e.window.previous_julian_day_ut == resumed.opening.julian_day_ut]
    assert [e.anchor for e in found] == [at(2024, 6, 23)]
    assert found[0].canonical is True
    result = unavailable(panchanga_day_containing(query, *place),
                         DayUnavailableReason.SUNRISE_UNAVAILABLE)
    assert result.preceding_sunrise == final.closing
    assert result.following_sunrise == resumed.opening

    day = complete(panchanga_day_containing(at(2024, 6, 23, 12), *place))
    assert day.opening == resumed.opening and day.closing == resumed.closing


TROMSO_CONTAINING = {
    # label: (query, the civil date of the containing day, or None)
    "2025-11-27": (at(2025, 11, 27, 11), None),
    "2026-01-16": (at(2026, 1, 16, 11), None),
    "2026-01-19": (at(2026, 1, 19, 11), date(2026, 1, 19)),
    "2024-05-20": (at(2024, 5, 20, 11), date(2024, 5, 20)),
    "2024-05-21": (at(2024, 5, 21, 11), None),
    "2024-06-21": (at(2024, 6, 21, 11), None),
    "2024-07-22": (at(2024, 7, 22, 11), date(2024, 7, 22)),
}


@pytest.mark.parametrize("label", sorted(TROMSO_CONTAINING))
def test_tromso_through_the_containing_form(label):
    query, civil_date = TROMSO_CONTAINING[label]
    result = panchanga_day_containing(query, *TROMSO)
    if civil_date is not None:
        day = complete(result)
        expected = complete(day_of(civil_date, TROMSO))
        assert (day.civil_date, day.sunrise_ordinal) == (civil_date, 1)
        assert day.opening == expected.opening and day.closing == expected.closing
        return

    result = unavailable(result, DayUnavailableReason.SUNRISE_UNAVAILABLE)
    assert isinstance(result.layer16_at_instant, SunriseUnavailable)
    start, end = containing_walk_range(query)
    if label == "2026-01-16":
        # Walk [01-13 11:00, 01-18 23:00] UTC: the first sunrise of the year
        # (01-19 10:35 UTC) lies outside it, although the date form reports it.
        assert (start, end) == (at(2026, 1, 13, 11), at(2026, 1, 18, 23))
        assert result.following_sunrise is None
        assert day_of(date(2026, 1, 16), TROMSO).following_sunrise is not None
    if label == "2024-05-21":
        # Walk [05-18 11:00, 05-23 23:00] UTC: after the lone sunrise.
        assert (start, end) == (at(2024, 5, 18, 11), at(2024, 5, 23, 23))
        lone = day_of(date(2024, 5, 21), TROMSO).lone_sunrise
        assert result.preceding_sunrise == lone
        assert result.preceding_sunrise.located_by is WINDOW_NEXT
        assert result.following_sunrise is None
    if label in ("2025-11-27", "2024-06-21"):
        assert result.preceding_sunrise is None
        assert result.following_sunrise is None
        assert result.layer16_reasons == (REASON_NO_PREVIOUS_SUNRISE,)


def test_tromso_after_the_last_sunrise_of_may_is_unavailable_by_the_containing_form():
    """Probe D3: the last located sunrise at or before the query opens a day
    that closed a day and a half before the query."""
    query = at(2024, 5, 22, 12)
    final = complete(day_of(date(2024, 5, 20), TROMSO))
    assert containing_walk_range(query) == (at(2024, 5, 19, 12), at(2024, 5, 25))

    result = unavailable(panchanga_day_containing(query, *TROMSO),
                         DayUnavailableReason.SUNRISE_UNAVAILABLE)
    assert final.opening.utc == at(2024, 5, 19, 23, 22, 57, 783689)
    assert final.closing.utc == at(2024, 5, 20, 23, 6, 14, 858853)
    assert result.preceding_sunrise == final.closing
    assert result.following_sunrise is None
    assert isinstance(result.layer16_at_instant, SunriseUnavailable)
    assert result.layer16_reasons == BOTH_REASONS


# --- round trips (specification 10, 11) ----------------------------------------------

CONTAINING_QUERIES = [
    (JALANDHAR, at(1995, 3, 21, 12)),
    (JAMMU, at(2001, 2, 4, 12)),
    (TROMSO, at(2026, 1, 19, 11)),
    (TROMSO, at(2024, 5, 20, 11)),
    (ARCTIC, at(2024, 6, 18, 10)),
    (ARCTIC, at(2024, 6, 23, 12)),
    (ANCHORAGE, at(1867, 10, 19, 6)),
    (ANCHORAGE, at(1867, 10, 19, 20)),
    (APIA, at(2011, 12, 30, 20)),
    (SAO_PAULO, at(2019, 2, 17, 3)),
    (CHATHAM, at(2024, 4, 6, 12)),
]


@pytest.mark.parametrize("place, query", CONTAINING_QUERIES)
def test_the_date_form_reproduces_every_containing_day(place, query):
    containing = complete(panchanga_day_containing(query, *place))
    assert containing.query_utc == query
    assert containing.layer16_at_instant is not None
    assert in_day_by_julian_day(containing, query)
    assert containing.opening.local.date() == containing.civil_date

    again = complete(panchanga_day(containing.civil_date, *place,
                                   sunrise_ordinal=containing.sunrise_ordinal))
    assert again.opening == containing.opening
    assert again.closing == containing.closing
    assert again.opening.julian_day_ut == containing.opening.julian_day_ut
    assert again.closing.julian_day_ut == containing.closing.julian_day_ut
    assert again.listing.transitions == containing.listing.transitions


def test_the_anchorage_containing_ordinals_are_one_and_two():
    first = complete(panchanga_day_containing(at(1867, 10, 19, 6), *ANCHORAGE))
    second = complete(panchanga_day_containing(at(1867, 10, 19, 20), *ANCHORAGE))
    assert (first.civil_date, first.sunrise_ordinal) == (date(1867, 10, 19), 1)
    assert (second.civil_date, second.sunrise_ordinal) == (date(1867, 10, 19), 2)


DATE_FORM_DAYS = [
    (JALANDHAR, date(1995, 3, 21), None),
    (JAMMU, date(2001, 2, 4), None),
    (TROMSO, date(2024, 5, 18), None),
    (TROMSO, date(2024, 5, 20), None),
    (TROMSO, date(2026, 1, 19), None),
    (TROMSO, date(2024, 7, 22), None),
    (ARCTIC, date(2024, 6, 17), None),
    (ARCTIC, date(2024, 6, 18), None),
    (ARCTIC, date(2024, 6, 23), None),
    (ANCHORAGE, date(1867, 10, 19), 1),
    (ANCHORAGE, date(1867, 10, 19), 2),
    (APIA, date(2011, 12, 29), None),
    (APIA, date(2011, 12, 31), None),
    (KIRITIMATI, date(1994, 12, 30), None),
    (SAO_PAULO, date(2018, 11, 4), None),
    (LONDON, date(2024, 3, 31), None),
    (CHATHAM, date(2024, 4, 7), None),
]


@pytest.mark.parametrize("place, civil_date, ordinal", DATE_FORM_DAYS)
def test_the_containing_form_reproduces_every_date_day_in_its_range(
    place, civil_date, ordinal
):
    day = complete(day_of(civil_date, place, ordinal))
    assert SUPPORTED_INSTANT_START <= day.opening.utc
    assert day.opening.utc + HOUR <= SUPPORTED_INSTANT_END

    for moment in (day.opening.utc + HOUR, day.opening.utc):
        again = complete(panchanga_day_containing(moment, *place))
        assert again.opening == day.opening
        assert again.closing == day.closing
        assert again.listing.transitions == day.listing.transitions
        assert again.civil_date == day.civil_date
        assert again.sunrise_ordinal == day.sunrise_ordinal


# --- ranges (specification 4.7) --------------------------------------------------------


def test_the_date_range_edges():
    recorder = Recorder()
    for civil_date in (SUPPORTED_DATE_START - DAY, SUPPORTED_DATE_END + DAY):
        with pytest.raises(UnsupportedDateError):
            panchanga_day(civil_date, *JALANDHAR, rise_after=recorder.rise_after,
                          evaluate=recorder.evaluate)
    assert recorder.calls == []
    for civil_date in (SUPPORTED_DATE_START, SUPPORTED_DATE_END):
        day = complete(panchanga_day(civil_date, *JALANDHAR))
        assert day.civil_date == civil_date


def test_the_instant_range_edges():
    recorder = Recorder()
    for moment in (SUPPORTED_INSTANT_START - US, SUPPORTED_INSTANT_END + US,
                   at(2399, 12, 21, 5, 30, 0, 1, tz=IST)):
        with pytest.raises(UnsupportedInstantError, match="Layer 18"):
            panchanga_day_containing(moment, *JALANDHAR,
                                     rise_after=recorder.rise_after,
                                     evaluate=recorder.evaluate)
    assert recorder.calls == []
    for moment in (SUPPORTED_INSTANT_START, SUPPORTED_INSTANT_END):
        day = complete(panchanga_day_containing(moment, *JALANDHAR))
        assert in_day_by_julian_day(day, moment)
        assert SUPPORTED_DATE_START <= day.civil_date <= SUPPORTED_DATE_END


def test_an_equivalent_spelling_of_the_last_instant_is_accepted():
    with pytest.raises(Refused):
        panchanga_day_containing(at(2399, 12, 21, 5, 30, tz=IST), *JALANDHAR,
                                 rise_after=Recorder().rise_after)


EDGE_SCRIPT = """
import sys
from datetime import date, datetime, timezone
from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.panchanga import (
    PanchangaDay, SUPPORTED_DATE_END, SUPPORTED_DATE_START,
    SUPPORTED_INSTANT_END, SUPPORTED_INSTANT_START, panchanga_day,
    panchanga_day_containing)

edge = sys.argv[1]
with ephemeris_session(sys.argv[2]):
    if edge == "date-start":
        result = panchanga_day(SUPPORTED_DATE_START, 0.0, 180.0, "UTC")
    elif edge == "date-end":
        result = panchanga_day(SUPPORTED_DATE_END, 0.0, -180.0, "UTC")
    elif edge == "instant-start":
        result = panchanga_day_containing(SUPPORTED_INSTANT_START, 66.0, 180.0, "UTC")
    else:
        result = panchanga_day_containing(SUPPORTED_INSTANT_END, -66.0, -180.0, "UTC")
    print(type(result).__name__)
"""


@pytest.mark.parametrize("edge", ["date-start", "date-end", "instant-start",
                                  "instant-end"])
def test_each_edge_answers_in_a_fresh_interpreter(edge):
    """The edge failures of Layer 17 section 2.2 are state-dependent, so each
    supported edge is also computed as the first thing a cold session does."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-c", EDGE_SCRIPT, edge, EPHE_DIR],
        cwd=REPO_ROOT, env=environment, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.split()[-1] in ("PanchangaDay", "PanchangaDayUnavailable")


# --- pre-evaluation validation (specification 9) ----------------------------------------

DATE_DEFAULTS = dict(civil_date=REFERENCE_DATE, latitude=JALANDHAR[0],
                     longitude=JALANDHAR[1], timezone_id=JALANDHAR[2])
NAIVE = datetime(1995, 3, 21, 12)

DATE_REFUSED = [
    (DayRequestError, dict(civil_date=at(1995, 3, 21))),
    (DayRequestError, dict(civil_date=NAIVE)),
    (DayRequestError, dict(civil_date="1995-03-21")),
    (DayRequestError, dict(civil_date=None)),
    (DayRequestError, dict(sunrise_ordinal=0)),
    (DayRequestError, dict(sunrise_ordinal=-1)),
    (DayRequestError, dict(sunrise_ordinal=True)),
    (DayRequestError, dict(sunrise_ordinal=False)),
    (DayRequestError, dict(sunrise_ordinal=1.0)),
    (DayRequestError, dict(sunrise_ordinal="1")),
    (UnsupportedDateError, dict(civil_date=SUPPORTED_DATE_START - DAY)),
    (UnsupportedDateError, dict(civil_date=SUPPORTED_DATE_END + DAY)),
    (UnsupportedDateError, dict(civil_date=date(1700, 1, 1))),
    (ValueError, dict(latitude=91.0)),
    (ValueError, dict(longitude=180.5)),
    (ValueError, dict(latitude=math.nan)),
    (ValueError, dict(latitude=True)),
    (InvalidTimezoneError, dict(timezone_id="Mars/Olympus_Mons")),
    (InvalidTimezoneError, dict(timezone_id=None)),
    (TransitionRequestError, dict(tolerance=timedelta(milliseconds=50))),
    (TransitionRequestError, dict(tolerance=0.1)),
    (TransitionRequestError, dict(tolerance=None)),
    # The order of specification 9's table: the first failing row decides.
    (DayRequestError, dict(civil_date=NAIVE, sunrise_ordinal=0, latitude=91.0,
                           timezone_id="x", tolerance=None)),
    (DayRequestError, dict(sunrise_ordinal=0, civil_date=date(1700, 1, 1))),
    (UnsupportedDateError, dict(civil_date=date(1700, 1, 1), latitude=91.0)),
    (ValueError, dict(latitude=91.0, timezone_id="Mars/Olympus_Mons")),
    (InvalidTimezoneError, dict(timezone_id="Mars/Olympus_Mons", tolerance=None)),
]

CONTAINING_DEFAULTS = dict(moment_utc=at(1995, 3, 21, 12), latitude=JALANDHAR[0],
                           longitude=JALANDHAR[1], timezone_id=JALANDHAR[2])

CONTAINING_REFUSED = [
    (ValueError, dict(moment_utc=NAIVE)),
    (UnsupportedInstantError, dict(moment_utc=SUPPORTED_INSTANT_START - US)),
    (UnsupportedInstantError, dict(moment_utc=SUPPORTED_INSTANT_END + US)),
    (ValueError, dict(latitude=-91.0)),
    (InvalidTimezoneError, dict(timezone_id="Not/A_Zone")),
    (TransitionRequestError, dict(tolerance=timedelta(hours=2))),
    (ValueError, dict(moment_utc=datetime(1700, 1, 1), latitude=91.0)),
    (UnsupportedInstantError, dict(moment_utc=at(1700, 1, 1), latitude=91.0)),
    (ValueError, dict(latitude=91.0, timezone_id="Not/A_Zone")),
    (InvalidTimezoneError, dict(timezone_id="Not/A_Zone", tolerance=None)),
]


@pytest.mark.parametrize("error, changes", DATE_REFUSED)
def test_every_refused_date_request_costs_no_evaluation(error, changes):
    recorder = Recorder()
    arguments = {**DATE_DEFAULTS, **changes}
    with pytest.raises(error) as raised:
        panchanga_day(rise_after=recorder.rise_after, evaluate=recorder.evaluate,
                      **arguments)
    assert raised.type is error
    assert recorder.calls == []


@pytest.mark.parametrize("error, changes", CONTAINING_REFUSED)
def test_every_refused_containing_request_costs_no_evaluation(error, changes):
    recorder = Recorder()
    arguments = {**CONTAINING_DEFAULTS, **changes}
    with pytest.raises(error) as raised:
        panchanga_day_containing(rise_after=recorder.rise_after,
                                 evaluate=recorder.evaluate, **arguments)
    assert raised.type is error
    assert recorder.calls == []


def refuse(*args):
    raise AssertionError(f"the ephemeris was reached with {args!r}")


def test_the_default_path_is_not_reached_by_a_refused_request(monkeypatch):
    monkeypatch.setattr(sunrise_module, "calc_sunrise_hindu", refuse)
    monkeypatch.setattr(transitions_module, "calculate_sidereal_positions", refuse)
    with pytest.raises(UnsupportedDateError):
        panchanga_day(SUPPORTED_DATE_START - DAY, *JALANDHAR)
    with pytest.raises(DayRequestError):
        panchanga_day(REFERENCE_DATE, *JALANDHAR, sunrise_ordinal=0)
    with pytest.raises(UnsupportedInstantError):
        panchanga_day_containing(SUPPORTED_INSTANT_END + US, *JALANDHAR)
    with pytest.raises(TransitionRequestError):
        panchanga_day_containing(at(1995, 3, 21), *JALANDHAR, tolerance=None)


# --- tolerance parity with Layer 17 (decision D9(a)) -------------------------------------

REJECTED_TOLERANCES = [
    timedelta(0), timedelta(microseconds=1), timedelta(milliseconds=2),
    timedelta(milliseconds=-1), timedelta(hours=1.5), 100, 0.1, None,
]
PARITY_START = at(1995, 3, 21, 12)


@pytest.mark.parametrize("tolerance", ALLOWED_TOLERANCES)
def test_every_allowed_tolerance_is_accepted_by_both_layers(tolerance):
    recorder = Recorder()
    with pytest.raises(Refused):
        panchanga_day(REFERENCE_DATE, *JALANDHAR, tolerance=tolerance,
                      rise_after=recorder.rise_after, evaluate=recorder.evaluate)
    with pytest.raises(Refused):
        panchanga_day_containing(PARITY_START, *JALANDHAR, tolerance=tolerance,
                                 rise_after=recorder.rise_after,
                                 evaluate=recorder.evaluate)
    with pytest.raises(Refused):
        list_transitions(PARITY_START, PARITY_START + DAY, tolerance=tolerance,
                         evaluate=recorder.evaluate)
    with pytest.raises(Refused):
        next_transition(PARITY_START, TITHI, tolerance=tolerance,
                        evaluate=recorder.evaluate)


@pytest.mark.parametrize("tolerance", REJECTED_TOLERANCES,
                         ids=[repr(t) for t in REJECTED_TOLERANCES])
def test_every_rejected_tolerance_is_rejected_by_both_layers(tolerance):
    recorder = Recorder()
    calls = [
        lambda: panchanga_day(REFERENCE_DATE, *JALANDHAR, tolerance=tolerance,
                              rise_after=recorder.rise_after,
                              evaluate=recorder.evaluate),
        lambda: panchanga_day_containing(PARITY_START, *JALANDHAR,
                                         tolerance=tolerance,
                                         rise_after=recorder.rise_after,
                                         evaluate=recorder.evaluate),
        lambda: list_transitions(PARITY_START, PARITY_START + DAY,
                                 tolerance=tolerance, evaluate=recorder.evaluate),
        lambda: next_transition(PARITY_START, TITHI, tolerance=tolerance,
                                evaluate=recorder.evaluate),
    ]
    for call in calls:
        with pytest.raises(TransitionRequestError) as raised:
            call()
        assert raised.type is TransitionRequestError
    assert recorder.calls == []


# --- synthetic sunrise sequences (specification 11) ---------------------------------------

#: Daily synthetic sunrises at 01:03:56 UTC around the reference date.
DAILY_BASE = [jd(at(1995, 3, 1, 1, 3, 56) + n * DAY) for n in range(60)]
TEN_MS_DAYS = 0.010 / 86400.0


def alternating_ten_ms(anchor):
    """Sunrises seen 10 ms later from every other pair of anchors."""
    shift = TEN_MS_DAYS if (anchor_index(anchor) // 2) % 2 else 0.0
    return [sunrise + shift for sunrise in DAILY_BASE]


def test_a_second_locating_that_differs_by_ten_ms_is_one_sunrise_and_the_canonical_float_closes():
    """The high-latitude behaviour, made deterministic: the canonical closing of
    each day is the next day's opening bit for bit, and not its own window's
    ``next``, which differs by 10 ms."""
    rise_after = AnchoredSky(alternating_ten_ms, at(1995, 3, 1), at(1995, 4, 20))
    days = [complete(panchanga_day(REFERENCE_DATE + n * DAY, *JALANDHAR,
                                   rise_after=rise_after))
            for n in range(4)]
    assert rise_after.asked[:14] == list(daily_module._anchors(
        *date_walk_range(REFERENCE_DATE)
    ))

    for earlier, later in zip(days, days[1:]):
        assert earlier.closing == later.opening
        assert earlier.closing.julian_day_ut == later.opening.julian_day_ut
        assert earlier.closing.located_by is CANONICAL
        difference = (earlier.closing.julian_day_ut
                      - earlier.opening_window.next_julian_day_ut)
        assert difference != 0.0
        # 10 ms, to within the ~40 us spacing of Julian Day floats.
        assert abs(abs(difference) * 86400.0 - 0.010) < 1e-4
        assert abs(difference) < SAME_SUNRISE_MAX_SEPARATION

    # Every sunrise is located once; the 10 ms re-locatings were discarded.
    walk = daily_module._select_date(REFERENCE_DATE, *JALANDHAR, rise_after).walk
    gaps = [b.window.previous_julian_day_ut - a.window.previous_julian_day_ut
            for a, b in zip(walk.located, walk.located[1:])]
    assert all(0.99 < gap < 1.01 for gap in gaps)
    assert walk.next_only == (walk.located[-1].window,)


#: 23.5 hours apart from 1995-03-21 11:17 UTC (never on the anchor grid), so a
#: sequence with one sunrise removed still has consecutive sunrises within
#: Layer 16's two days.
SPACED = [jd(at(1995, 3, 21, 11, 17) + n * timedelta(hours=23.5))
          for n in range(-10, 11)]
X0, X1 = SPACED[10], SPACED[11]


def test_a_sunrise_located_out_of_order_is_a_search_error():
    """Anchor 1995-03-22 00:00 UTC is shown a sky without the 03-21 sunrise, so
    it locates the 03-20 sunrise after the walk has already located 03-21."""
    odd_anchor = at(1995, 3, 22)

    def sunrises_for(anchor):
        return [s for s in SPACED if s != X0] if anchor == odd_anchor else SPACED

    rise_after = AnchoredSky(sunrises_for, at(1995, 3, 10), at(1995, 4, 1))
    with pytest.raises(DaySearchError, match="not later than"):
        panchanga_day(REFERENCE_DATE, *SYNTHETIC_UTC, rise_after=rise_after)
    assert rise_after.asked[-1] == odd_anchor


def test_a_sunrise_that_layer_16_skipped_over_is_a_search_error():
    """Anchor 1995-03-21 12:00 UTC is shown a sky without the 03-22 sunrise, so
    its window's next is two sunrises later; the walk then locates the skipped
    one more than half a day before that next."""
    odd_anchor = at(1995, 3, 21, 12)

    def sunrises_for(anchor):
        return [s for s in SPACED if s != X1] if anchor == odd_anchor else SPACED

    rise_after = AnchoredSky(sunrises_for, at(1995, 3, 10), at(1995, 4, 1))
    with pytest.raises(DaySearchError, match="skipped a sunrise"):
        panchanga_day(REFERENCE_DATE, *SYNTHETIC_UTC, rise_after=rise_after)
    # 03-22 00:00 re-locates 03-21; 03-22 12:00 locates the skipped sunrise.
    assert odd_anchor in rise_after.asked
    assert rise_after.asked[-1] == odd_anchor + 2 * ANCHOR_STEP


def test_a_walk_with_no_anchor_is_a_search_error():
    with pytest.raises(DaySearchError, match="no entry"):
        daily_module._walk(at(1995, 3, 21), at(1995, 3, 21) - HOUR, *JALANDHAR,
                           sunrise_module.default_rise_after)


def test_a_result_of_another_type_from_layer_16_is_a_search_error(monkeypatch):
    monkeypatch.setattr(daily_module, "find_sunrise_window", lambda *a, **k: None)
    with pytest.raises(DaySearchError, match="NoneType"):
        panchanga_day(REFERENCE_DATE, *JALANDHAR)


#: Daily at 06:00 UTC with a hole: 03-23 and 03-24 have no sunrise.
GAP_MOMENTS = [at(1995, 3, 21, 6) + n * DAY for n in list(range(-6, 2)) + list(range(4, 13))]
GAP_SKY = sky(*[jd(m) for m in GAP_MOMENTS])


def test_a_gap_is_not_an_error_and_is_reported_on_both_sides():
    last = complete(panchanga_day(date(1995, 3, 21), *SYNTHETIC_UTC, rise_after=GAP_SKY))
    assert last.closing.located_by is WINDOW_NEXT
    assert last.closing_window is None
    assert last.closing.utc.date() == date(1995, 3, 22)
    # The next canonical sunrise is in the walk, but after a gap: not an error,
    # and not the closing.
    walk = daily_module._select_date(date(1995, 3, 21), *SYNTHETIC_UTC, GAP_SKY).walk
    resumed = [e for e in walk.located if e.canonical][-1]
    assert datetime_from_julian_day(resumed.window.previous_julian_day_ut).date() == (
        date(1995, 3, 25)
    )
    assert any(isinstance(e, daily_module._Unavailable) for e in walk.entries)

    lone = unavailable(panchanga_day(date(1995, 3, 22), *SYNTHETIC_UTC,
                                     rise_after=GAP_SKY),
                       DayUnavailableReason.NO_VARA_DAY_AT_SUNRISE)
    assert lone.lone_sunrise == last.closing
    assert lone.preceding_sunrise == last.opening
    assert lone.following_sunrise.utc.date() == date(1995, 3, 25)
    assert lone.at_lone_sunrise is not None

    inside = unavailable(panchanga_day(date(1995, 3, 23), *SYNTHETIC_UTC,
                                       rise_after=GAP_SKY),
                         DayUnavailableReason.SUNRISE_UNAVAILABLE)
    assert inside.preceding_sunrise == last.closing
    assert inside.following_sunrise.utc.date() == date(1995, 3, 25)
    assert REASON_SUNRISES_NOT_CONSECUTIVE in inside.layer16_reasons

    first = complete(panchanga_day(date(1995, 3, 25), *SYNTHETIC_UTC, rise_after=GAP_SKY))
    assert first.opening.utc.date() == date(1995, 3, 25)
    assert first.closing.located_by is CANONICAL

    containing = unavailable(panchanga_day_containing(at(1995, 3, 23, 12), *SYNTHETIC_UTC,
                                                      rise_after=GAP_SKY),
                             DayUnavailableReason.SUNRISE_UNAVAILABLE)
    assert containing.preceding_sunrise == last.closing
    assert containing.following_sunrise == first.opening


# --- synthetic transitions (specification 11) ---------------------------------------------


def test_the_karana_changes_three_times_in_one_real_day():
    day = complete(day_of(date(1995, 3, 17), JALANDHAR))
    karanas = [t for t in day.listing.transitions if t.kind is KARANA]
    assert [(t.before.name, t.after.name) for t in karanas] == [
        ("Bava", "Balava"), ("Balava", "Kaulava"), ("Kaulava", "Taitila"),
    ]
    assert all(e.placement is WITHIN for e in day.placed)


FORTY_SEVEN = [jd(at(2024, 1, 1, 6) + n * timedelta(hours=47)) for n in range(-4, 7)]


def test_three_nakshatra_changes_in_one_synthetic_day_with_unordered_pairs_carried():
    """A 47-hour synthetic day and a Moon at 18 deg/day starting half a degree
    before a boundary: three nakshatra changes, each sharing its cell with a
    yoga change (Sun at 0, so the sum is the Moon), listed by Layer 17 as
    unordered pairs and carried through unchanged."""
    opening_datetime = datetime_from_julian_day(FORTY_SEVEN[4])
    evaluate = linear_longitudes(opening_datetime, rate=18.0,
                                 at_x=2 * NAKSHATRA_SPAN - 0.5)
    day = complete(panchanga_day(date(2024, 1, 1), *SYNTHETIC_UTC,
                                 rise_after=sky(*FORTY_SEVEN), evaluate=evaluate))
    nakshatras = [t for t in day.listing.transitions if t.kind is NAKSHATRA]
    yogas = [t for t in day.listing.transitions if t.kind is YOGA]
    assert len(nakshatras) == 3 and len(yogas) == 3
    assert [(t.before_utc, t.after_utc) for t in nakshatras] == [
        (t.before_utc, t.after_utc) for t in yogas
    ]
    assert len(day.listing.unordered_pairs) == 3
    for i, j in day.listing.unordered_pairs:
        assert (day.listing.transitions[i].kind, day.listing.transitions[j].kind) == (
            NAKSHATRA, YOGA
        )
    independent = list_transitions(day.opening.utc, day.closing.utc, evaluate=evaluate)
    assert day.listing == independent
    assert day.listing.unordered_pairs == independent.unordered_pairs
    assert all(e.placement is WITHIN for e in day.placed)


# --- consistency guards (specification 4.5, 4.6, 7.2) --------------------------------------


def test_the_opening_cross_check_is_whole_record_equality():
    """A second evaluation of the very same instant that moves the Moon by
    1e-9 deg changes no index but fails the whole-record check."""
    opening = complete(day_of(REFERENCE_DATE, JALANDHAR)).opening.utc
    inner = linear_longitudes(opening + 10 * HOUR)
    seen = []

    def evaluate(moment):
        sun, moon = inner(moment)
        if moment == opening:
            seen.append(moment)
            if len(seen) == 2:
                return sun, moon + 1e-9
        return sun, moon

    with pytest.raises(DaySearchError, match="differ from Layer 17"):
        panchanga_day(REFERENCE_DATE, *JALANDHAR, evaluate=evaluate)


def straddling(change):
    """A tithi transition straddling the real Jalandhar opening, and the day."""
    day = complete(panchanga_day(REFERENCE_DATE, *JALANDHAR,
                                 evaluate=linear_longitudes(change)))
    entry = placed_containing(day, TITHI, change)
    return day, entry.transition, linear_longitudes(change)


def test_a_straddling_cell_that_matches_neither_index_is_a_search_error():
    opening = complete(day_of(REFERENCE_DATE, JALANDHAR)).opening.utc
    day, transition, evaluate = straddling(opening + US)
    elsewhere = find_transitions(opening + 5 * DAY, evaluate=evaluate)
    assert elsewhere.neighbours[TITHI].current.index not in (
        transition.before.index, transition.after.index
    )
    with pytest.raises(DaySearchError, match="cannot be placed"):
        daily_module._placement(transition, day.opening.utc, elsewhere)


def test_a_straddling_cell_that_is_not_layer_17s_neighbour_is_a_search_error():
    """Thirty synthetic days later the Moon is back at the same elongation: the
    index matches, the event does not."""
    opening = complete(day_of(REFERENCE_DATE, JALANDHAR)).opening.utc

    day, after_case, evaluate = straddling(opening + US)
    later = find_transitions(opening + 30 * DAY, evaluate=evaluate)
    assert later.neighbours[TITHI].current.index == after_case.before.index
    with pytest.raises(DaySearchError, match="not Layer 17's next"):
        daily_module._placement(after_case, day.opening.utc, later)

    day, reflected_case, evaluate = straddling(opening)
    later = find_transitions(opening + 30 * DAY, evaluate=evaluate)
    assert later.neighbours[TITHI].current.index == reflected_case.after.index
    with pytest.raises(DaySearchError, match="not Layer 17's previous"):
        daily_module._placement(reflected_case, day.opening.utc, later)


def test_the_image_check_refuses_a_datetime_that_names_another_float(monkeypatch):
    real = daily_module.find_sunrise_window

    def shifted(*args, **kwargs):
        result = real(*args, **kwargs)
        if isinstance(result, SunriseWindow):
            return dataclasses.replace(result, previous_utc=result.previous_utc + MS)
        return result

    monkeypatch.setattr(daily_module, "find_sunrise_window", shifted)
    with pytest.raises(DaySearchError, match="image check"):
        panchanga_day(REFERENCE_DATE, *JALANDHAR)


def test_an_opening_missing_from_the_date_enumeration_is_a_search_error():
    rise_after = sunrise_module.default_rise_after
    this = daily_module._select_date(REFERENCE_DATE, *JALANDHAR, rise_after)
    other = daily_module._select_date(REFERENCE_DATE + DAY, *JALANDHAR, rise_after)
    assert daily_module._ordinal_of(this.candidates[0], this) == 1
    with pytest.raises(DaySearchError, match="not among the canonical candidates"):
        daily_module._ordinal_of(this.candidates[0], other)


# --- PanchangaDay invariants (specification 5) -------------------------------------------


def tampered_copies():
    day = complete(day_of(REFERENCE_DATE, JALANDHAR))
    other = complete(day_of(date(2001, 2, 4), JAMMU))
    containing = complete(panchanga_day_containing(at(1995, 3, 21, 12), *JALANDHAR))
    closing_cell = day.transitions_at_closing.neighbours[TITHI].previous
    first = day.placed[0]
    return [
        ("opening FIRST_ANCHOR", "canonical anchor", day,
         dict(opening=dataclasses.replace(day.opening, located_by=FIRST_ANCHOR))),
        ("closing not after opening", "before the closing", day,
         dict(closing=dataclasses.replace(day.opening))),
        ("vara of another window", "vara", day, dict(vara=other.vara)),
        ("listing of another day", "listing must run", day, dict(listing=other.listing)),
        ("placed shortened", "placed must carry", day, dict(placed=day.placed[:-1])),
        ("placed by equality not identity", "placed must carry", day,
         dict(placed=(dataclasses.replace(first, transition=dataclasses.replace(
             first.transition)),) + day.placed[1:])),
        ("placed AT_OR_BEFORE_CLOSING", "no listed transition", day,
         dict(placed=(dataclasses.replace(first, placement=AT_OR_BEFORE_CLOSING),)
              + day.placed[1:])),
        ("closing cell WITHIN", "must be AT_OR_BEFORE_CLOSING", day,
         dict(cells_at_closing={TITHI: PlacedTransition(closing_cell, WITHIN)})),
        ("closing cell not spanning", "span or end", day,
         dict(cells_at_closing={TITHI: PlacedTransition(closing_cell,
                                                        AT_OR_BEFORE_CLOSING)})),
        ("at_opening of another day", "at_opening", day,
         dict(at_opening=other.at_opening)),
        ("at_closing of the opening", "at_closing", day,
         dict(at_closing=day.at_opening)),
        ("canonical closing without window", "closing_window", day,
         dict(closing_window=None)),
        ("window-next closing with window", "closing_window", day,
         dict(closing=dataclasses.replace(day.closing, located_by=WINDOW_NEXT))),
        ("query without layer 16", "both set", day, dict(query_utc=day.opening.utc)),
        ("layer 16 without query", "both set", containing, dict(query_utc=None)),
        ("query at the closing", "query instant", containing,
         dict(query_utc=containing.closing.utc)),
        ("query before the opening float", "query instant", containing,
         dict(query_utc=containing.opening.utc - MS)),
    ]


def test_every_invariant_of_panchanga_day_raises_value_error():
    for label, message, day, changes in tampered_copies():
        with pytest.raises(ValueError, match=message):
            dataclasses.replace(day, **changes)
        # An untampered copy passes.
        assert dataclasses.replace(day) == day, label
