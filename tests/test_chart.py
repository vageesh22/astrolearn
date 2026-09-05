"""Tests for Layer 8: chart assembly.

Reference birth throughout: 1995-03-21 06:45 IST at Jalandhar. Every expected
value lives here in the tests; the implementation hardcodes nothing.
"""

import ast
import dataclasses
import socket
from datetime import date, datetime, time, timezone
from pathlib import Path
from types import MappingProxyType

import pytest

from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.chart.assemble import assemble_chart
from vedic_chart.chart.model import BirthChart
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.lagna.ascendant import calculate_lagna
from vedic_chart.lagna.whole_sign import assign_houses
from vedic_chart.location.model import AmbiguousPlaceError, PlaceNotFoundError
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.location.static_resolver import StaticLocationResolver
from vedic_chart.sidereal.positions import calculate_sidereal_positions
from vedic_chart.time.local_time import normalize_birth_time
from vedic_chart.vedic.grahas import Graha, derive_grahas

REPO_ROOT = Path(__file__).resolve().parent.parent
EPHE_DIR = str(REPO_ROOT / "ephe")
FIXTURE_DB = REPO_ROOT / "tests" / "fixtures" / "geodata_fixture.sqlite"
CHART_PACKAGE = REPO_ROOT / "src" / "vedic_chart" / "chart"

REFERENCE = dict(year=1995, month=3, day=21, hour=6, minute=45)
EXPECTED_MOMENT = datetime(1995, 3, 21, 1, 15, tzinfo=timezone.utc)


@pytest.fixture
def ephemeris():
    with ephemeris_session(EPHE_DIR):
        yield


@pytest.fixture
def resolver():
    with OfflineLocationResolver(FIXTURE_DB) as offline:
        yield offline


@pytest.fixture
def request_():
    return BirthChartRequest.from_components(
        REFERENCE["year"], REFERENCE["month"], REFERENCE["day"],
        REFERENCE["hour"], REFERENCE["minute"], place_query="Jalandhar",
    )


@pytest.fixture
def chart(ephemeris, resolver, request_):
    return assemble_chart(request_, resolver)


# --- (1) end to end --------------------------------------------------------


def test_assembles_a_complete_chart(chart, request_):
    assert isinstance(chart, BirthChart)
    assert chart.request is request_
    assert chart.location is not None
    assert chart.moment_utc is not None
    assert chart.julian_day_ut > 0
    assert chart.ayanamsa > 0
    assert chart.lagna is not None
    assert len(chart.grahas) == 9
    assert len(chart.houses) == 9


# --- (2) reference Lagna ---------------------------------------------------


def test_reference_lagna(chart):
    assert chart.lagna.sidereal_longitude == pytest.approx(339.795911, abs=1e-4)  # true-equinox Lahiri (OPEN-1 resolved 2026-09-05)
    assert chart.lagna.placement.rashi_name == "Meena"
    assert chart.lagna.placement.nakshatra_name == "Uttara Bhadrapada"
    assert chart.lagna.placement.pada == 2


# --- (3-5) reference grahas, rashis and houses -----------------------------

EXPECTED_PLACEMENTS = {
    Graha.SUN: ("Meena", 1),
    Graha.MOON: ("Tula", 8),
    Graha.MERCURY: ("Kumbha", 12),
    Graha.VENUS: ("Makara", 11),
    Graha.MARS: ("Karka", 5),
    Graha.JUPITER: ("Vrishchika", 9),
    Graha.SATURN: ("Kumbha", 12),
    Graha.RAHU: ("Tula", 8),
    Graha.KETU: ("Mesha", 2),
}


@pytest.mark.parametrize(
    ("graha", "expected"), [(g, e) for g, e in EXPECTED_PLACEMENTS.items()]
)
def test_reference_graha_rashi_and_house(chart, graha, expected):
    rashi_name, house = expected

    assert chart.grahas[graha].placement.rashi_name == rashi_name, graha
    assert chart.houses[graha] == house, graha


def test_every_house_is_in_range(chart):
    assert all(1 <= house <= 12 for house in chart.houses.values())
    assert set(chart.houses) == set(Graha)


def test_lagna_sign_is_house_one(chart):
    lagna_index = chart.lagna.placement.rashi_index

    for graha, position in chart.grahas.items():
        if position.placement.rashi_index == lagna_index:
            assert chart.houses[graha] == 1, graha


# --- (6) nodes -------------------------------------------------------------


def test_ketu_opposes_rahu(chart):
    rahu = chart.grahas[Graha.RAHU]
    ketu = chart.grahas[Graha.KETU]

    assert ketu.sidereal_longitude == (rahu.sidereal_longitude + 180.0) % 360.0
    assert ketu.speed_longitude == rahu.speed_longitude


# --- (7) retrograde --------------------------------------------------------


def test_retrograde_set_at_this_moment(chart):
    retrograde = {g for g, p in chart.grahas.items() if p.is_retrograde}

    assert retrograde == {Graha.MARS, Graha.RAHU, Graha.KETU}


# --- (8) instant -----------------------------------------------------------


def test_moment_and_julian_day(chart, ephemeris):
    assert chart.moment_utc == EXPECTED_MOMENT
    assert chart.moment_utc.tzinfo is timezone.utc

    sidereal = calculate_sidereal_positions(chart.moment_utc)
    assert chart.julian_day_ut == sidereal.julian_day_ut
    assert chart.ayanamsa == sidereal.ayanamsa


# --- (9) location ----------------------------------------------------------


def test_resolved_location(chart):
    assert chart.location.canonical_name == "Jalandhar, Punjab, India"
    assert chart.location.timezone_id == "Asia/Kolkata"
    assert chart.location.latitude == pytest.approx(31.32556, abs=1e-4)
    assert chart.location.longitude == pytest.approx(75.57917, abs=1e-4)


# --- (10) immutability -----------------------------------------------------


def test_attributes_cannot_be_rebound(chart):
    with pytest.raises(dataclasses.FrozenInstanceError):
        chart.ayanamsa = 0.0


def test_mappings_are_read_only(chart):
    assert isinstance(chart.grahas, MappingProxyType)
    assert isinstance(chart.houses, MappingProxyType)

    with pytest.raises(TypeError):
        chart.grahas[Graha.SUN] = None
    with pytest.raises(TypeError):
        chart.houses[Graha.SUN] = 99
    with pytest.raises(TypeError):
        del chart.houses[Graha.SUN]


def test_chart_copies_the_mappings_it_is_given(ephemeris, resolver, request_):
    """Mutating the caller's dicts afterwards must not touch the chart."""
    location = resolver.resolve(request_.place_query)
    moment = normalize_birth_time(
        request_.birth_date, request_.birth_time, location.timezone_id
    )
    sidereal = calculate_sidereal_positions(moment)
    grahas = derive_grahas(sidereal)
    lagna = calculate_lagna(moment, location.latitude, location.longitude)
    houses = assign_houses(
        lagna.placement.rashi_index,
        {g: p.placement.rashi_index for g, p in grahas.items()},
    )

    chart = BirthChart(
        request=request_, location=location, moment_utc=moment,
        julian_day_ut=sidereal.julian_day_ut, ayanamsa=sidereal.ayanamsa,
        lagna=lagna, grahas=grahas, houses=houses,
    )
    original_house = chart.houses[Graha.SUN]

    houses[Graha.SUN] = 99
    grahas.pop(Graha.MOON)

    assert chart.houses[Graha.SUN] == original_house
    assert len(chart.grahas) == 9


def test_model_rejects_incomplete_mappings(chart):
    partial = dict(chart.grahas)
    partial.pop(Graha.KETU)

    with pytest.raises(ValueError):
        BirthChart(
            request=chart.request, location=chart.location,
            moment_utc=chart.moment_utc, julian_day_ut=chart.julian_day_ut,
            ayanamsa=chart.ayanamsa, lagna=chart.lagna,
            grahas=partial, houses=dict(chart.houses),
        )


def test_model_rejects_out_of_range_houses(chart):
    bad = dict(chart.houses)
    bad[Graha.SUN] = 13

    with pytest.raises(ValueError):
        BirthChart(
            request=chart.request, location=chart.location,
            moment_utc=chart.moment_utc, julian_day_ut=chart.julian_day_ut,
            ayanamsa=chart.ayanamsa, lagna=chart.lagna,
            grahas=dict(chart.grahas), houses=bad,
        )


# --- (11) no network -------------------------------------------------------


def test_assembles_with_sockets_disabled(monkeypatch, request_):
    def forbidden(*args, **kwargs):
        raise AssertionError("chart assembly attempted a network call")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

    with ephemeris_session(EPHE_DIR):
        with OfflineLocationResolver(FIXTURE_DB) as offline:
            chart = assemble_chart(request_, offline)

    assert chart.lagna.placement.rashi_name == "Meena"
    assert chart.houses[Graha.SUN] == 1


# --- (12) layer boundary ---------------------------------------------------

FORBIDDEN_IMPORTS = (
    "swisseph",
    "vedic_chart.ephemeris",
    "vedic_chart.astronomy",
    "vedic_chart.time.julian_day",
    "vedic_chart.vedic.divisions",
    "zoneinfo",
    "http",
    "urllib",
    "requests",
    "socket",
    "ssl",
    "aiohttp",
)


def imported_module_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names.append(module)
            names.extend(f"{module}.{alias.name}" for alias in node.names)
    return names


@pytest.mark.parametrize("filename", ["__init__.py", "model.py", "assemble.py"])
def test_chart_package_respects_its_boundary(filename):
    for name in imported_module_names(CHART_PACKAGE / filename):
        lowered = name.lower()
        for forbidden in FORBIDDEN_IMPORTS:
            assert not lowered.startswith(forbidden), f"{filename} imports {name}"


def test_assemble_does_not_recompute_time_or_ayanamsa():
    """Julian Day and ayanamsha must come from SiderealPositions, not afresh."""
    names = imported_module_names(CHART_PACKAGE / "assemble.py")

    assert not any("julian_day" in n for n in names)
    assert not any("get_ayanamsa" in n for n in names)


# --- (13) pure delegation --------------------------------------------------


def test_chart_values_equal_direct_layer_calls(chart, ephemeris):
    """Assembly adds nothing of its own: every value matches a direct call."""
    moment = chart.moment_utc
    sidereal = calculate_sidereal_positions(moment)

    assert chart.grahas == derive_grahas(sidereal)
    assert chart.lagna == calculate_lagna(
        moment, chart.location.latitude, chart.location.longitude
    )
    assert chart.houses == assign_houses(
        chart.lagna.placement.rashi_index,
        {g: p.placement.rashi_index for g, p in chart.grahas.items()},
    )


# --- Lagna degree invariance ----------------------------------------------


def test_houses_are_invariant_within_one_lagna_sign(ephemeris, resolver):
    """Whole Sign houses depend on the Lagna's sign, not its degree."""
    early = assemble_chart(
        BirthChartRequest(date(1995, 3, 21), time(6, 45), "Jalandhar"), resolver
    )
    later = assemble_chart(
        BirthChartRequest(date(1995, 3, 21), time(6, 50), "Jalandhar"), resolver
    )

    assert (
        early.lagna.placement.degrees_in_rashi
        != later.lagna.placement.degrees_in_rashi
    )
    assert early.lagna.placement.rashi_index == later.lagna.placement.rashi_index
    assert dict(early.houses) == dict(later.houses)


# --- error propagation -----------------------------------------------------


def test_ambiguous_place_propagates(ephemeris, resolver):
    request = BirthChartRequest(date(1995, 3, 21), time(6, 45), "Springfield")

    with pytest.raises(AmbiguousPlaceError):
        assemble_chart(request, resolver)


def test_unknown_place_propagates(ephemeris, resolver):
    request = BirthChartRequest(date(1995, 3, 21), time(6, 45), "Xyzzyville")

    with pytest.raises(PlaceNotFoundError):
        assemble_chart(request, resolver)


# --- resolver injection ----------------------------------------------------


def test_any_resolver_satisfying_the_protocol_works(ephemeris, request_, chart):
    """The static resolver is a different provider with different coordinates."""
    static_chart = assemble_chart(request_, StaticLocationResolver())

    assert static_chart.moment_utc == chart.moment_utc
    assert static_chart.location.latitude != chart.location.latitude
    assert (
        static_chart.lagna.placement.rashi_index
        == chart.lagna.placement.rashi_index
    )
    assert dict(static_chart.houses) == dict(chart.houses)
