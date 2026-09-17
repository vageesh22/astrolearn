"""Layer 16's composition, against the real ephemeris (specification 3.3, 6).

Self-contained in the same sense as the Layer 12 and 14 tests: the birthplaces
come from the committed fixture geodata database or from an explicit
``ResolvedLocation``, the positions from the committed ``ephe/`` directory, and
nothing here needs the production database or a network.

Two reference births, both already used by the frozen layers: Jalandhar
1995-03-21 06:45 IST and Jammu 2001-02-04 10:45 IST. Their five elements were
computed with this library and these flags before the code was written and are
pinned here by name and index. The sunrise is pinned only **to the minute** --
the seconds are a property of the Swiss Ephemeris release and of the tzdata the
machine happens to have, and pinning them would turn a convention test into a
golden of somebody else's data.

The only claim this file makes about almanacs is the one specification 2.3
makes: the geometric Hindu sunrise is a few minutes LATER than the plain
upper-limb refracted ``CALC_RISE`` sunrise. That comparison is computed here by
calling ``swisseph`` directly -- tests may touch the library, the package may
not -- so it is a check of the convention against the library rather than of
the engine against itself.

The new-moon and full-moon cases take nothing on trust either: the crossing is
found by bisecting the engine's own elongation, and the assertion is about what
the tithi index does across it, not about a date somebody looked up.
"""

import dataclasses
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import swisseph as swe  # tests may touch the library directly; src may not

from render_helpers import EPHE_DIR, FIXTURE_DB, FixedResolver
from vedic_chart.astronomy.positions import Body, ephemeris_session
from vedic_chart.chart.assemble import assemble_chart
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.model import ResolvedLocation
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.panchanga import (
    CALCULATION_CONVENTION,
    SUNRISE_CONVENTION,
    InvalidTimezoneError,
    KaranaKind,
    LocationProvenance,
    LongitudeSource,
    Panchanga,
    PanchangaLocation,
    Paksha,
    SunriseUnavailable,
    SunriseWindow,
    TithiHalf,
    calculate_panchanga,
    panchanga_from_chart,
)
from vedic_chart.panchanga.elements import (
    elongation,
    nakshatra_from_placement,
    tithi_from_elongation,
)
from vedic_chart.sidereal.positions import calculate_sidereal_positions
from vedic_chart.time.local_time import normalize_birth_time
from vedic_chart.vedic.grahas import Graha

IST = timezone(timedelta(hours=5, minutes=30))

JAMMU_LOCATION = ResolvedLocation(
    canonical_name="Jammu, Jammu and Kashmir, India",
    latitude=32.73528,
    longitude=74.86167,
    timezone_id="Asia/Kolkata",
)

#: The two reference births: the four inputs and the five expected elements.
REFERENCES = {
    "jalandhar": {
        "date": date(1995, 3, 21),
        "time": time(6, 45),
        "latitude": 31.32556,
        "longitude": 75.57917,
        "timezone_id": "Asia/Kolkata",
        "tithi_index": 19,
        "tithi_name": "Panchami",
        "paksha": Paksha.KRISHNA,
        "number_in_paksha": 5,
        "nakshatra_name": "Vishakha",
        "yoga_index": 13,
        "yoga_name": "Harshana",
        "karana_index": 38,
        "karana_name": "Kaulava",
        "vara_name": "Mangalavara",
        "english_weekday": "Tuesday",
        "sunrise_local": datetime(1995, 3, 21, 6, 35, tzinfo=IST),
    },
    "jammu": {
        "date": date(2001, 2, 4),
        "time": time(10, 45),
        "latitude": 32.73528,
        "longitude": 74.86167,
        "timezone_id": "Asia/Kolkata",
        "tithi_index": 10,
        "tithi_name": "Ekadashi",
        "paksha": Paksha.SHUKLA,
        "number_in_paksha": 11,
        "nakshatra_name": "Mrigashira",
        "yoga_index": 25,
        "yoga_name": "Indra",
        "karana_index": 20,
        "karana_name": "Vanija",
        "vara_name": "Ravivara",
        "english_weekday": "Sunday",
        "sunrise_local": datetime(2001, 2, 4, 7, 27, tzinfo=IST),
    },
}
CASE_NAMES = tuple(REFERENCES)

ONE_MINUTE = timedelta(minutes=1)

_CACHE = {}


def jalandhar_chart():
    request = BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query="Jalandhar"
    )
    with OfflineLocationResolver(FIXTURE_DB) as resolver:
        return assemble_chart(request, resolver)


def jammu_chart():
    """Jammu is not in the fixture database, so its coordinates are explicit."""
    request = BirthChartRequest.from_components(
        2001, 2, 4, 10, 45, place_query="Jammu, Jammu and Kashmir, India"
    )
    return assemble_chart(request, FixedResolver(JAMMU_LOCATION))


BUILDERS = {"jalandhar": jalandhar_chart, "jammu": jammu_chart}


@pytest.fixture(scope="module", autouse=True)
def ephemeris():
    with ephemeris_session(EPHE_DIR):
        yield


def chart(name):
    """Built once: an ephemeris run per parametrised case would dominate."""
    if name not in _CACHE:
        _CACHE[name] = BUILDERS[name]()
    return _CACHE[name]


def moment_of(name):
    reference = REFERENCES[name]
    return normalize_birth_time(
        reference["date"], reference["time"], reference["timezone_id"]
    )


def explicit(name):
    reference = REFERENCES[name]
    return calculate_panchanga(
        moment_of(name),
        reference["latitude"],
        reference["longitude"],
        reference["timezone_id"],
    )


# --- the two reference births ----------------------------------------------


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_reference_elements_are_the_recorded_ones(name):
    reference = REFERENCES[name]
    panchanga = explicit(name)

    assert panchanga.tithi.index == reference["tithi_index"]
    assert panchanga.tithi.name == reference["tithi_name"]
    assert panchanga.tithi.paksha is reference["paksha"]
    assert panchanga.tithi.number_in_paksha == reference["number_in_paksha"]

    assert panchanga.nakshatra.name == reference["nakshatra_name"]

    assert panchanga.yoga.index == reference["yoga_index"]
    assert panchanga.yoga.name == reference["yoga_name"]

    assert panchanga.karana.index == reference["karana_index"]
    assert panchanga.karana.name == reference["karana_name"]
    assert panchanga.karana.kind is KaranaKind.REPEATING

    assert panchanga.vara.name == reference["vara_name"]
    assert panchanga.vara.english_weekday == reference["english_weekday"]


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_reference_sunrise_is_the_recorded_minute(name):
    """Pinned to the minute: the seconds belong to the library and to tzdata."""
    reference = REFERENCES[name]
    panchanga = explicit(name)

    local = panchanga.sunrise.previous_local

    assert local.tzinfo is not None
    assert local.utcoffset() == timedelta(hours=5, minutes=30)
    assert abs(local - reference["sunrise_local"]) < ONE_MINUTE


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_karana_halves_the_tithi_it_names(name):
    panchanga = explicit(name)
    half = 0 if panchanga.karana.half is TithiHalf.FIRST else 1

    assert panchanga.karana.tithi_index == panchanga.tithi.index
    assert panchanga.karana.index == 2 * panchanga.tithi.index + half


# --- the from-chart path ---------------------------------------------------


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_from_chart_and_explicit_paths_agree(name):
    built = chart(name)
    from_chart = panchanga_from_chart(built)
    direct = calculate_panchanga(
        built.moment_utc,
        built.location.latitude,
        built.location.longitude,
        built.location.timezone_id,
    )

    assert from_chart.tithi == direct.tithi
    assert from_chart.yoga == direct.yoga
    assert from_chart.karana == direct.karana
    assert from_chart.nakshatra == direct.nakshatra
    assert from_chart.vara == direct.vara
    assert from_chart.sunrise == direct.sunrise
    assert from_chart.sun_sidereal_longitude == direct.sun_sidereal_longitude
    assert from_chart.moon_sidereal_longitude == direct.moon_sidereal_longitude
    assert from_chart.ayanamsa == direct.ayanamsa
    assert from_chart.julian_day_ut == direct.julian_day_ut


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_nakshatra_is_the_charts_own_placement_object(name):
    """Specification 3.3: agreement by identity, not by many decimals."""
    built = chart(name)
    panchanga = panchanga_from_chart(built)

    assert panchanga.nakshatra.placement is built.grahas[Graha.MOON].placement


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_from_chart_path_makes_no_planetary_ephemeris_call(
    monkeypatch, name
):
    """The only calls into the sky are the sunrise ones.

    ``calculate_sidereal_positions`` is the single door this package has to the
    planets; making it raise turns any planetary call into a failure, and the
    adapter still has to produce a complete panchanga.
    """
    import vedic_chart.panchanga.compute as compute_module

    built = chart(name)

    def refuse(moment):
        raise AssertionError(
            "panchanga_from_chart called the planetary ephemeris"
        )

    monkeypatch.setattr(
        compute_module, "calculate_sidereal_positions", refuse
    )

    panchanga = panchanga_from_chart(built)

    assert panchanga.tithi.index == REFERENCES[name]["tithi_index"]
    assert panchanga.vara.name == REFERENCES[name]["vara_name"]
    assert panchanga.sunrise_available


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_from_chart_path_reads_the_charts_values_not_new_ones(name):
    built = chart(name)
    panchanga = panchanga_from_chart(built)

    assert panchanga.instant_utc is built.moment_utc
    assert panchanga.julian_day_ut == built.julian_day_ut
    assert panchanga.ayanamsa == built.ayanamsa
    assert panchanga.sun_sidereal_longitude == (
        built.grahas[Graha.SUN].sidereal_longitude
    )
    assert panchanga.moon_sidereal_longitude == (
        built.grahas[Graha.MOON].sidereal_longitude
    )
    assert panchanga.longitudes_source is LongitudeSource.BIRTH_CHART
    assert panchanga.location.provenance is LocationProvenance.BIRTH_CHART
    assert panchanga.location.latitude == built.location.latitude
    assert panchanga.location.longitude == built.location.longitude
    assert panchanga.location.timezone_id == built.location.timezone_id


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_explicit_path_records_its_own_provenance(name):
    panchanga = explicit(name)

    assert panchanga.longitudes_source is LongitudeSource.COMPUTED
    assert panchanga.location.provenance is LocationProvenance.EXPLICIT


# --- the conventions travel with the result --------------------------------


@pytest.mark.parametrize("name", CASE_NAMES)
def test_every_result_carries_both_convention_strings(name):
    panchanga = explicit(name)

    assert panchanga.calculation_convention == CALCULATION_CONVENTION
    assert panchanga.sunrise_convention == SUNRISE_CONVENTION
    assert panchanga.sunrise.convention == SUNRISE_CONVENTION
    assert "Lahiri" in CALCULATION_CONVENTION
    assert "897" in SUNRISE_CONVENTION


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_local_datetime_is_the_instant_in_the_places_zone(name):
    reference = REFERENCES[name]
    panchanga = explicit(name)

    assert panchanga.local_datetime == panchanga.instant_utc
    assert panchanga.local_datetime.utcoffset() == timedelta(
        hours=5, minutes=30
    )
    assert panchanga.local_datetime.date() == reference["date"]
    assert panchanga.local_datetime.timetz().replace(tzinfo=None) == (
        reference["time"]
    )


# --- the sunrise pair, against the sky -------------------------------------


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_sunrise_pair_brackets_the_instant(name):
    panchanga = explicit(name)
    window = panchanga.sunrise

    assert isinstance(window, SunriseWindow)
    assert (
        window.previous_julian_day_ut
        <= panchanga.julian_day_ut
        < window.next_julian_day_ut
    )
    assert window.previous_utc <= panchanga.instant_utc < window.next_utc


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_two_sunrises_are_about_a_day_apart(name):
    window = explicit(name).sunrise
    gap = window.next_julian_day_ut - window.previous_julian_day_ut

    assert 0.99 < gap < 1.01
    assert abs((window.next_utc - window.previous_utc) - timedelta(days=1)) < (
        timedelta(minutes=10)
    )


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_vara_is_the_weekday_of_the_previous_sunrises_local_date(name):
    panchanga = explicit(name)
    civil_date = panchanga.sunrise.previous_local.date()

    assert panchanga.vara.index == (civil_date.weekday() + 1) % 7
    assert panchanga.vara.sunrise is panchanga.sunrise
    assert isinstance(panchanga.vara.lord, Graha)


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_hindu_sunrise_is_a_few_minutes_after_the_astronomical_one(name):
    """Specification 2.3, checked against the library rather than against us.

    The plain ``CALC_RISE`` sunrise is the upper limb with refraction, which is
    what almanacs and newspapers print. The geometric Hindu rising waits for
    the disc *centre* on the *geometric* horizon, so it must be later -- by
    minutes, not by seconds and not by an hour.
    """
    reference = REFERENCES[name]
    panchanga = explicit(name)
    window = panchanga.sunrise

    return_code, tret = swe.rise_trans(
        window.previous_julian_day_ut - 0.5,
        swe.SUN,
        swe.CALC_RISE,
        (reference["longitude"], reference["latitude"], 0.0),
        0.0,
        0.0,
        swe.FLG_SWIEPH,
    )

    assert return_code == 0
    astronomical = tret[0]
    difference_minutes = (
        window.previous_julian_day_ut - astronomical
    ) * 24.0 * 60.0

    assert 2.0 < difference_minutes < 10.0, difference_minutes


# --- new moon and full moon, found with the engine's own longitudes --------


def sidereal_pair(moment):
    positions = calculate_sidereal_positions(moment)
    return (
        positions.bodies[Body.SUN].sidereal_longitude,
        positions.bodies[Body.MOON].sidereal_longitude,
    )


def arc_at(moment):
    return elongation(*sidereal_pair(moment))


def bisect_crossing(before, after, target):
    """The instant the elongation crosses ``target``, to the microsecond.

    ``before`` is an instant whose elongation is still below ``target`` in the
    cyclic sense and ``after`` one where it has passed. Nothing is looked up:
    the bracket is narrowed with the engine's own longitudes until the two ends
    are one microsecond apart.
    """
    assert after > before

    def passed(moment):
        return (arc_at(moment) - target) % 360.0 < 180.0

    assert not passed(before), before
    assert passed(after), after

    while after - before > timedelta(microseconds=1):
        middle = before + (after - before) / 2
        if passed(middle):
            after = middle
        else:
            before = middle

    return before, after


@pytest.mark.parametrize(
    "bracket_start,bracket_end,target,before_index,after_index",
    (
        (
            datetime(2024, 1, 11, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 11, 23, 0, tzinfo=timezone.utc),
            0.0,
            29,
            0,
        ),
        (
            datetime(2024, 1, 25, 12, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 25, 23, 0, tzinfo=timezone.utc),
            180.0,
            14,
            15,
        ),
    ),
    ids=("new_moon", "full_moon"),
)
def test_the_tithi_index_steps_across_a_syzygy(
    bracket_start, bracket_end, target, before_index, after_index
):
    """New moon starts the month; full moon starts the dark fortnight."""
    before, after = bisect_crossing(bracket_start, bracket_end, target)

    assert tithi_from_elongation(arc_at(before)).index == before_index
    assert tithi_from_elongation(arc_at(after)).index == after_index
    assert after - before <= timedelta(microseconds=1)


def test_the_new_moon_starts_shukla_pratipada():
    before, after = bisect_crossing(
        datetime(2024, 1, 11, 0, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 11, 23, 0, tzinfo=timezone.utc),
        0.0,
    )
    ending = calculate_panchanga(before, 31.32556, 75.57917, "Asia/Kolkata")
    starting = calculate_panchanga(after, 31.32556, 75.57917, "Asia/Kolkata")

    assert ending.tithi.name == "Amavasya"
    assert ending.tithi.paksha is Paksha.KRISHNA
    assert ending.karana.name == "Naga"

    assert starting.tithi.name == "Pratipada"
    assert starting.tithi.paksha is Paksha.SHUKLA
    assert starting.tithi.number_in_paksha == 1
    assert starting.karana.name == "Kimstughna"
    assert starting.karana.kind is KaranaKind.FIXED


def test_the_full_moon_starts_krishna_pratipada():
    before, after = bisect_crossing(
        datetime(2024, 1, 25, 12, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 25, 23, 0, tzinfo=timezone.utc),
        180.0,
    )
    ending = calculate_panchanga(before, 31.32556, 75.57917, "Asia/Kolkata")
    starting = calculate_panchanga(after, 31.32556, 75.57917, "Asia/Kolkata")

    assert ending.tithi.name == "Purnima"
    assert ending.tithi.paksha is Paksha.SHUKLA
    assert ending.karana.name == "Bava"

    assert starting.tithi.name == "Pratipada"
    assert starting.tithi.paksha is Paksha.KRISHNA
    assert starting.karana.name == "Balava"


# --- the polar case (decision D3) ------------------------------------------


@pytest.mark.parametrize(
    "moment",
    (
        datetime(2024, 6, 21, 12, 0, tzinfo=timezone.utc),
        datetime(2024, 12, 21, 12, 0, tzinfo=timezone.utc),
    ),
    ids=("june", "december"),
)
@pytest.mark.parametrize("longitude", (0.0, 90.0, -120.0))
def test_a_polar_instant_still_has_four_angular_elements(moment, longitude):
    panchanga = calculate_panchanga(moment, 80.0, longitude, "UTC")

    assert isinstance(panchanga.sunrise, SunriseUnavailable)
    assert panchanga.vara is None
    assert panchanga.sunrise_available is False
    assert panchanga.sunrise.latitude == 80.0
    assert panchanga.sunrise.longitude == longitude

    assert panchanga.tithi is not None
    assert panchanga.nakshatra is not None
    assert panchanga.yoga is not None
    assert panchanga.karana is not None
    assert 0 <= panchanga.tithi.index <= 29
    assert 0 <= panchanga.karana.index <= 59
    assert 0 <= panchanga.yoga.index <= 26
    assert 0 <= panchanga.nakshatra.index <= 26


def test_a_polar_instant_agrees_with_a_temperate_one_on_the_angular_elements():
    """The four longitude elements do not depend on the place at all."""
    moment = datetime(2024, 6, 21, 12, 0, tzinfo=timezone.utc)
    polar = calculate_panchanga(moment, 80.0, 0.0, "UTC")
    temperate = calculate_panchanga(moment, 31.32556, 75.57917, "Asia/Kolkata")

    assert polar.tithi == temperate.tithi
    assert polar.nakshatra == temperate.nakshatra
    assert polar.yoga == temperate.yoga
    assert polar.karana == temperate.karana
    assert polar.vara is None
    assert temperate.vara is not None


# --- input validation ------------------------------------------------------


def test_a_naive_instant_is_refused():
    with pytest.raises(ValueError):
        calculate_panchanga(
            datetime(1995, 3, 21, 1, 15), 31.32556, 75.57917, "Asia/Kolkata"
        )


def test_an_unknown_timezone_is_refused():
    moment = moment_of("jalandhar")

    with pytest.raises(InvalidTimezoneError):
        calculate_panchanga(moment, 31.32556, 75.57917, "Mars/Olympus_Mons")


@pytest.mark.parametrize(
    "latitude,longitude",
    ((90.5, 0.0), (0.0, 180.5), (float("nan"), 0.0), ("31.3", 0.0)),
)
def test_coordinates_off_the_globe_are_refused(latitude, longitude):
    moment = moment_of("jalandhar")

    with pytest.raises(ValueError):
        calculate_panchanga(moment, latitude, longitude, "Asia/Kolkata")


def test_every_bad_input_is_refused_before_the_ephemeris_is_asked(monkeypatch):
    """Fail fast and typed: an unusable call costs no ephemeris work.

    ``calculate_sidereal_positions`` is this package's single door to the
    planets. Making it raise turns "the sky was asked" into a distinguishable
    failure, so each refusal below is shown to happen strictly before it.
    """
    import vedic_chart.panchanga.compute as compute_module

    reached = []

    def refuse(moment):
        reached.append(moment)
        raise AssertionError("the ephemeris was asked before validation")

    monkeypatch.setattr(
        compute_module, "calculate_sidereal_positions", refuse
    )

    good = moment_of("jalandhar")

    with pytest.raises(ValueError):                       # naive instant
        calculate_panchanga(
            datetime(1995, 3, 21, 1, 15), 31.32556, 75.57917, "Asia/Kolkata"
        )
    with pytest.raises(ValueError):                       # latitude off globe
        calculate_panchanga(good, 90.5, 75.57917, "Asia/Kolkata")
    with pytest.raises(ValueError):                       # longitude off globe
        calculate_panchanga(good, 31.32556, 180.5, "Asia/Kolkata")
    with pytest.raises(ValueError):                       # not a number
        calculate_panchanga(good, "31.3", 75.57917, "Asia/Kolkata")
    with pytest.raises(ValueError):                       # not finite
        calculate_panchanga(
            good, float("inf"), 75.57917, "Asia/Kolkata"
        )
    with pytest.raises(InvalidTimezoneError):             # unknown zone
        calculate_panchanga(good, 31.32556, 75.57917, "Mars/Olympus_Mons")
    with pytest.raises(InvalidTimezoneError):             # an offset, not a zone
        calculate_panchanga(good, 31.32556, 75.57917, "+05:30")
    with pytest.raises(InvalidTimezoneError):             # not a string
        calculate_panchanga(good, 31.32556, 75.57917, None)

    assert reached == []


def test_a_good_call_does_reach_the_ephemeris(monkeypatch):
    """The counterpart: the guard above is not passing for the wrong reason."""
    import vedic_chart.panchanga.compute as compute_module

    reached = []
    real = compute_module.calculate_sidereal_positions

    def spy(moment):
        reached.append(moment)
        return real(moment)

    monkeypatch.setattr(compute_module, "calculate_sidereal_positions", spy)

    panchanga = explicit("jalandhar")

    assert reached == [moment_of("jalandhar")]
    assert panchanga.tithi.index == REFERENCES["jalandhar"]["tithi_index"]


# --- invariants of the assembled result ------------------------------------


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_result_types_are_frozen(name):
    panchanga = explicit(name)

    assert isinstance(panchanga, Panchanga)
    assert isinstance(panchanga.location, PanchangaLocation)

    with pytest.raises(dataclasses.FrozenInstanceError):
        panchanga.tithi = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        panchanga.vara = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        panchanga.location.latitude = 0.0


def test_a_vara_without_a_sunrise_is_refused_at_construction():
    """``vara is None`` iff the sunrise is unavailable, checked, not assumed."""
    polar = calculate_panchanga(
        datetime(2024, 6, 21, 12, 0, tzinfo=timezone.utc), 80.0, 0.0, "UTC"
    )
    ordinary = explicit("jalandhar")

    with pytest.raises(ValueError, match="vara must be present"):
        dataclasses.replace(polar, vara=ordinary.vara)
    with pytest.raises(ValueError, match="vara must be present"):
        dataclasses.replace(ordinary, vara=None)


def test_a_vara_from_a_different_window_is_refused():
    jalandhar = explicit("jalandhar")
    jammu = explicit("jammu")

    with pytest.raises(ValueError, match="own"):
        dataclasses.replace(jalandhar, vara=jammu.vara)


def test_a_karana_that_halves_another_tithi_is_refused():
    jalandhar = explicit("jalandhar")
    jammu = explicit("jammu")

    with pytest.raises(ValueError, match="karana"):
        dataclasses.replace(jalandhar, karana=jammu.karana)


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_panchanga_is_self_describing(name):
    """Everything the result depends on travels with it."""
    panchanga = explicit(name)
    reference = REFERENCES[name]

    assert panchanga.instant_utc == moment_of(name)
    assert panchanga.location.latitude == reference["latitude"]
    assert panchanga.location.longitude == reference["longitude"]
    assert panchanga.location.timezone_id == reference["timezone_id"]
    assert panchanga.ayanamsa > 0.0
    assert 0.0 <= panchanga.sun_sidereal_longitude < 360.0
    assert 0.0 <= panchanga.moon_sidereal_longitude < 360.0
    assert panchanga.julian_day_ut > 0.0


# --- one instant, however it is spelled (specification 2.4) ----------------


def test_every_aware_spelling_of_one_instant_gives_one_panchanga():
    """+00:00, a fixed +05:30 and a ZoneInfo name the same moment.

    The whole dataclass is compared, not a field at a time: the location and
    the provenance are identical too, because the only thing that differed
    between the calls was how the caller wrote the instant down.
    """
    utc = datetime(1995, 3, 21, 1, 15, tzinfo=timezone.utc)
    spellings = (
        utc,
        utc.astimezone(IST),
        utc.astimezone(ZoneInfo("Asia/Kolkata")),
        utc.astimezone(ZoneInfo("America/New_York")),
    )

    results = [
        calculate_panchanga(spelling, 31.32556, 75.57917, "Asia/Kolkata")
        for spelling in spellings
    ]

    for result in results:
        assert result == results[0]


@pytest.mark.parametrize(
    "spelling",
    (
        datetime(1995, 3, 21, 1, 15, tzinfo=timezone.utc),
        datetime(1995, 3, 21, 6, 45, tzinfo=IST),
        datetime(1995, 3, 21, 6, 45, tzinfo=ZoneInfo("Asia/Kolkata")),
    ),
    ids=("utc", "fixed_offset", "zoneinfo"),
)
def test_the_stored_instant_is_always_utc_and_the_local_one_is_always_local(
    spelling,
):
    panchanga = calculate_panchanga(
        spelling, 31.32556, 75.57917, "Asia/Kolkata"
    )

    assert panchanga.instant_utc.tzinfo is timezone.utc
    assert panchanga.instant_utc == datetime(
        1995, 3, 21, 1, 15, tzinfo=timezone.utc
    )
    assert panchanga.local_datetime == datetime(
        1995, 3, 21, 6, 45, tzinfo=IST
    )
    assert panchanga.local_datetime.utcoffset() == timedelta(
        hours=5, minutes=30
    )
    assert panchanga.tithi.index == REFERENCES["jalandhar"]["tithi_index"]


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_from_chart_path_inherits_an_already_utc_instant(name):
    """A chart's instant is UTC already, so it is passed through untouched."""
    built = chart(name)
    panchanga = panchanga_from_chart(built)

    assert built.moment_utc.tzinfo is timezone.utc
    assert panchanga.instant_utc is built.moment_utc
    assert panchanga.instant_utc.tzinfo is timezone.utc


# --- the nakshatra's progress (specification 4.2) --------------------------


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_nakshatra_progress_is_the_charts_own_longitude(name):
    built = chart(name)
    panchanga = panchanga_from_chart(built)
    placement = built.grahas[Graha.MOON].placement
    longitude = built.grahas[Graha.MOON].sidereal_longitude

    scaled = longitude * 27.0 / 360.0

    assert panchanga.nakshatra.placement is placement
    assert panchanga.nakshatra.index == placement.nakshatra_index
    assert panchanga.nakshatra.angular_fraction == scaled - int(scaled)
    assert 0.0 <= panchanga.nakshatra.angular_fraction < 1.0

    # The pada arithmetic is the frozen layer's and is untouched by any of it.
    assert panchanga.nakshatra.pada == placement.pada
    assert panchanga.nakshatra.degrees_in_nakshatra == (
        placement.degrees_in_nakshatra
    )
    assert panchanga.nakshatra.degrees_in_pada == placement.degrees_in_pada


@pytest.mark.parametrize("name", CASE_NAMES)
def test_a_chart_whose_moon_placement_was_tampered_with_is_refused(name):
    """The same contradiction the dasha adapter refuses, refused here too."""
    built = chart(name)
    moon = built.grahas[Graha.MOON]
    recorded = moon.placement.nakshatra_index

    tampered = dataclasses.replace(
        moon.placement, nakshatra_index=(recorded + 1) % 27
    )

    with pytest.raises(RuntimeError, match="internal contradiction"):
        nakshatra_from_placement(tampered, moon.sidereal_longitude)


# --- the chart's instant, and the tzinfo guarantee -------------------------


def chart_with_instant(base, moment):
    """The Jalandhar chart with its instant respelled, nothing else changed."""
    return dataclasses.replace(base, moment_utc=moment)


@pytest.mark.parametrize(
    "tz",
    (timezone.utc, timezone(timedelta(0)), ZoneInfo("UTC")),
    ids=("timezone_utc", "fixed_zero_offset", "zoneinfo_utc"),
)
def test_a_chart_instant_spelled_any_utc_way_still_stores_timezone_utc(tz):
    """``ZoneInfo("UTC")`` is a zero offset but not ``timezone.utc`` itself.

    Section 5 promises the stored instant carries ``timezone.utc``, so the
    from-chart path normalises like every other. The rest of the panchanga must
    be untouched by how the chart happened to spell the same moment.
    """
    base = chart("jalandhar")
    respelled = chart_with_instant(
        base, base.moment_utc.astimezone(tz)
    )

    panchanga = panchanga_from_chart(respelled)
    reference = panchanga_from_chart(base)

    assert panchanga.instant_utc.tzinfo is timezone.utc
    assert panchanga.instant_utc == base.moment_utc
    assert panchanga == reference


def test_the_from_chart_path_leaves_an_already_utc_instant_identical():
    """Normalising a ``timezone.utc`` datetime returns the same object."""
    base = chart("jalandhar")
    panchanga = panchanga_from_chart(base)

    assert base.moment_utc.tzinfo is timezone.utc
    assert panchanga.instant_utc is base.moment_utc


def test_a_panchanga_whose_instant_is_not_timezone_utc_is_refused():
    """The guard, exercised on a hand-built copy of a real result."""
    good = explicit("jalandhar")

    for tz in (ZoneInfo("UTC"), IST, timezone(timedelta(hours=-5))):
        with pytest.raises(ValueError, match="timezone.utc"):
            dataclasses.replace(
                good, instant_utc=good.instant_utc.astimezone(tz)
            )

    # And the untampered spelling is accepted, so the guard is not vacuous.
    assert dataclasses.replace(
        good, instant_utc=good.instant_utc.astimezone(timezone.utc)
    ) == good


def test_a_chart_whose_julian_day_contradicts_its_instant_is_refused():
    """The assemble-style cross-check: one FROZEN function, one instant.

    ``assemble_chart`` takes the Julian Day from the positions it computed, so
    no chart the engine produced can fail this. A chart that does is an
    internal contradiction, not a caller's mistake.
    """
    base = chart("jalandhar")

    for wrong in (0.0, base.julian_day_ut + 1.0, base.julian_day_ut - 1e-9):
        broken = dataclasses.replace(base, julian_day_ut=wrong)
        with pytest.raises(RuntimeError, match="Internal inconsistency"):
            panchanga_from_chart(broken)

    # Restoring it restores the pass.
    restored = dataclasses.replace(base, julian_day_ut=base.julian_day_ut)
    assert panchanga_from_chart(restored) == panchanga_from_chart(base)
