"""Tests for Layer 9: the canonical D1 (Rashi) chart representation.

The structural tests build ``BirthChart`` instances synthetically from the
frozen dataclasses, so the whole house/rashi/occupant rearrangement is proved on
plain numbers without touching the ephemeris. The regression tests then run the
real pipeline for the reference birth (1995-03-21 06:45 IST at Jalandhar) and
assert the finished D1 chart.

Every expected value lives here; the implementation hardcodes no chart.
"""

import ast
import dataclasses
from datetime import date, datetime, time, timezone
from pathlib import Path
from types import MappingProxyType

import pytest

from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.chart.assemble import assemble_chart
from vedic_chart.chart.model import BirthChart
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.lagna.ascendant import Lagna
from vedic_chart.location.model import ResolvedLocation
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.representation.d1 import (
    D1Chart,
    D1GrahaPlacement,
    D1House,
    D1Lagna,
    D1Meta,
    build_d1_chart,
)
from vedic_chart.representation.dms import DMS
from vedic_chart.vedic.divisions import RASHI_NAMES, classify
from vedic_chart.vedic.grahas import Graha, GrahaPosition

REPO_ROOT = Path(__file__).resolve().parent.parent
EPHE_DIR = str(REPO_ROOT / "ephe")
FIXTURE_DB = REPO_ROOT / "tests" / "fixtures" / "geodata_fixture.sqlite"
REPRESENTATION_PACKAGE = REPO_ROOT / "src" / "vedic_chart" / "representation"
PACKAGE_FILES = ("__init__.py", "d1.py", "dms.py")

RASHI_COUNT = 12
TEST_AYANAMSA = 23.5

# Sidereal longitudes chosen so that one rashi holds four grahas (Mesha: Sun,
# Moon, Saturn, Ketu), five rashis hold one each, and six are empty. Ketu is
# Rahu + 180 as the frozen engine derives it.
SYNTHETIC_LONGITUDES = {
    Graha.SUN: 5.0,
    Graha.MOON: 5.5,
    Graha.MERCURY: 35.0,
    Graha.VENUS: 65.0,
    Graha.MARS: 95.0,
    Graha.JUPITER: 125.0,
    Graha.SATURN: 5.9,
    Graha.RAHU: 200.0,
    Graha.KETU: 20.0,
}
SYNTHETIC_SPEEDS = {
    Graha.SUN: 0.99,
    Graha.MOON: 13.2,
    Graha.MERCURY: 1.4,
    Graha.VENUS: 1.2,
    Graha.MARS: -0.21,
    Graha.JUPITER: 0.13,
    Graha.SATURN: 0.06,
    Graha.RAHU: -0.053,
    Graha.KETU: -0.053,
}
# Rashi index -> the grahas in it, in Graha enum order.
SYNTHETIC_BY_RASHI = {
    0: (Graha.SUN, Graha.MOON, Graha.SATURN, Graha.KETU),
    1: (Graha.MERCURY,),
    2: (Graha.VENUS,),
    3: (Graha.MARS,),
    4: (Graha.JUPITER,),
    6: (Graha.RAHU,),
}
EMPTY_RASHIS = (5, 7, 8, 9, 10, 11)


def synthetic_chart(lagna_rashi_index: int, *, reversed_order: bool = False):
    """Build a BirthChart directly from frozen dataclasses -- no ephemeris.

    ``reversed_order`` supplies the graha mappings in reverse enum order, which
    ``BirthChart`` preserves; a build from it must still produce enum-ordered
    occupants, which is what proves Layer 9 orders them itself.
    """
    grahas_in_order = list(Graha)
    if reversed_order:
        grahas_in_order = list(reversed(grahas_in_order))

    grahas = {}
    for graha in grahas_in_order:
        longitude = SYNTHETIC_LONGITUDES[graha]
        speed = SYNTHETIC_SPEEDS[graha]
        grahas[graha] = GrahaPosition(
            sidereal_longitude=longitude,
            speed_longitude=speed,
            is_retrograde=speed < 0.0,
            placement=classify(longitude),
        )

    lagna_longitude = lagna_rashi_index * 30.0 + 13.788209
    lagna = Lagna(
        tropical_longitude=(lagna_longitude + TEST_AYANAMSA) % 360.0,
        sidereal_longitude=lagna_longitude,
        ayanamsa=TEST_AYANAMSA,
        placement=classify(lagna_longitude),
    )

    # The Whole Sign formula, spelled out here rather than imported: Layer 9
    # must not depend on lagna.whole_sign, and neither may this test.
    houses = {
        graha: (position.placement.rashi_index - lagna_rashi_index)
        % RASHI_COUNT
        + 1
        for graha, position in grahas.items()
    }

    return BirthChart(
        request=BirthChartRequest(date(2000, 1, 1), time(12, 0), "test"),
        location=ResolvedLocation("Test", 0.0, 0.0, "UTC"),
        moment_utc=datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc),
        julian_day_ut=2451545.0,
        ayanamsa=TEST_AYANAMSA,
        lagna=lagna,
        grahas=grahas,
        houses=houses,
    )


ALL_LAGNA_INDICES = tuple(range(RASHI_COUNT))


# --- fixtures for the real reference chart ---------------------------------


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
        1995, 3, 21, 6, 45, place_query="Jalandhar"
    )


@pytest.fixture
def chart(ephemeris, resolver, request_):
    return assemble_chart(request_, resolver)


@pytest.fixture
def reference_d1(chart):
    return build_d1_chart(chart)


# --- (1) structure: twelve houses, in order, one rashi each ----------------


@pytest.mark.parametrize("lagna_index", ALL_LAGNA_INDICES)
def test_twelve_houses_numbered_one_to_twelve_in_order(lagna_index):
    d1 = build_d1_chart(synthetic_chart(lagna_index))

    assert len(d1.houses) == 12
    assert [house.number for house in d1.houses] == list(range(1, 13))


@pytest.mark.parametrize("lagna_index", ALL_LAGNA_INDICES)
def test_house_rashi_follows_the_lagna(lagna_index):
    d1 = build_d1_chart(synthetic_chart(lagna_index))

    for index, house in enumerate(d1.houses):
        assert house.rashi_index == (lagna_index + index) % RASHI_COUNT
        assert house.rashi_number == house.rashi_index + 1


@pytest.mark.parametrize("lagna_index", ALL_LAGNA_INDICES)
def test_the_twelve_rashis_appear_exactly_once_each(lagna_index):
    d1 = build_d1_chart(synthetic_chart(lagna_index))

    indices = [house.rashi_index for house in d1.houses]

    assert sorted(indices) == list(range(RASHI_COUNT))


@pytest.mark.parametrize("lagna_index", ALL_LAGNA_INDICES)
def test_house_rashi_names_come_from_the_frozen_table(lagna_index):
    d1 = build_d1_chart(synthetic_chart(lagna_index))

    for house in d1.houses:
        assert house.rashi_name == RASHI_NAMES[house.rashi_index]


def test_rashi_names_are_the_twelve_in_zodiacal_order():
    d1 = build_d1_chart(synthetic_chart(0))

    assert [house.rashi_name for house in d1.houses] == list(RASHI_NAMES)


def test_first_house_holds_the_lagna_rashi():
    for lagna_index in ALL_LAGNA_INDICES:
        d1 = build_d1_chart(synthetic_chart(lagna_index))

        assert d1.houses[0].rashi_index == d1.lagna.rashi_index
        assert d1.houses[0].rashi_index == lagna_index


# --- (2) occupants ---------------------------------------------------------


@pytest.mark.parametrize("lagna_index", ALL_LAGNA_INDICES)
def test_occupants_match_the_source_houses(lagna_index):
    source = synthetic_chart(lagna_index)
    d1 = build_d1_chart(source)

    for house in d1.houses:
        expected = tuple(
            g for g in Graha if source.houses[g] == house.number
        )
        assert house.occupants == expected


@pytest.mark.parametrize("lagna_index", ALL_LAGNA_INDICES)
def test_empty_houses_are_present_with_an_empty_tuple(lagna_index):
    d1 = build_d1_chart(synthetic_chart(lagna_index))

    empty = [h for h in d1.houses if h.rashi_index in EMPTY_RASHIS]

    assert len(empty) == len(EMPTY_RASHIS)
    for house in empty:
        assert house.occupants == ()
        assert house.occupants is not None


@pytest.mark.parametrize("lagna_index", ALL_LAGNA_INDICES)
def test_a_crowded_house_lists_its_grahas_in_enum_order(lagna_index):
    d1 = build_d1_chart(synthetic_chart(lagna_index))

    by_rashi = {h.rashi_index: h.occupants for h in d1.houses}

    for rashi_index, expected in SYNTHETIC_BY_RASHI.items():
        assert by_rashi[rashi_index] == expected


@pytest.mark.parametrize("lagna_index", ALL_LAGNA_INDICES)
def test_every_graha_occupies_exactly_one_house(lagna_index):
    d1 = build_d1_chart(synthetic_chart(lagna_index))

    occupants = [g for house in d1.houses for g in house.occupants]

    assert len(occupants) == 9
    assert sorted(occupants, key=list(Graha).index) == list(Graha)


# --- (3) invariants over any chart -----------------------------------------


def check_invariants(source: BirthChart, d1: D1Chart) -> None:
    assert d1.source is source
    assert d1.lagna.house == 1
    assert d1.houses[0].rashi_index == d1.lagna.rashi_index
    assert len(d1.grahas) == 9
    assert list(d1.grahas) == list(Graha)

    for graha, placement in d1.grahas.items():
        assert placement.graha is graha
        assert placement.house == source.houses[graha]
        assert placement.position is source.grahas[graha]

        house = d1.houses[placement.house - 1]
        assert house.number == placement.house
        assert graha in house.occupants
        assert placement.rashi_index == house.rashi_index
        assert placement.rashi_number == house.rashi_number
        assert placement.rashi_name == house.rashi_name

        origin = source.grahas[graha].placement
        assert placement.nakshatra_index == origin.nakshatra_index
        assert placement.nakshatra_number == origin.nakshatra_number
        assert placement.nakshatra_name == origin.nakshatra_name
        assert placement.pada == origin.pada
        assert placement.degrees_in_rashi == origin.degrees_in_rashi

        assert placement.is_retrograde is source.grahas[graha].is_retrograde
        assert placement.is_retrograde == (placement.speed_longitude < 0.0)
        assert placement.speed_longitude == (
            source.grahas[graha].speed_longitude
        )

        # A graha occupies one house and no other.
        others = [h for h in d1.houses if h.number != placement.house]
        assert all(graha not in h.occupants for h in others)

    rahu = d1.grahas[Graha.RAHU]
    ketu = d1.grahas[Graha.KETU]
    assert (rahu.house - ketu.house) % RASHI_COUNT == 6
    assert rahu.is_retrograde is True
    assert ketu.is_retrograde is True


@pytest.mark.parametrize("lagna_index", ALL_LAGNA_INDICES)
def test_invariants_hold_for_every_lagna(lagna_index):
    source = synthetic_chart(lagna_index)

    check_invariants(source, build_d1_chart(source))


def test_invariants_hold_for_the_reference_chart(chart, reference_d1):
    check_invariants(chart, reference_d1)


def test_lagna_is_never_an_occupant(reference_d1):
    """The Lagna is exposed once, as D1Chart.lagna, and never in a house."""
    for house in reference_d1.houses:
        for occupant in house.occupants:
            assert isinstance(occupant, Graha)
    assert not isinstance(reference_d1.lagna, D1GrahaPlacement)
    assert reference_d1.lagna.position is reference_d1.source.lagna


# --- (4) identity: nothing authoritative is copied -------------------------


def test_graha_positions_are_the_source_objects(chart, reference_d1):
    for graha, placement in reference_d1.grahas.items():
        assert placement.position is chart.grahas[graha]


def test_longitudes_are_the_source_floats(chart, reference_d1):
    for graha, placement in reference_d1.grahas.items():
        assert (
            placement.sidereal_longitude
            is chart.grahas[graha].sidereal_longitude
        )
        assert (
            placement.degrees_in_rashi
            is chart.grahas[graha].placement.degrees_in_rashi
        )


def test_lagna_is_the_source_object(chart, reference_d1):
    assert reference_d1.lagna.position is chart.lagna
    assert reference_d1.lagna.sidereal_longitude == chart.lagna.sidereal_longitude
    assert reference_d1.lagna.tropical_longitude == chart.lagna.tropical_longitude
    assert reference_d1.lagna.ayanamsa == chart.lagna.ayanamsa
    assert (
        reference_d1.lagna.degrees_in_rashi
        == chart.lagna.placement.degrees_in_rashi
    )


def test_meta_references_the_source_fields(chart, reference_d1):
    meta = reference_d1.meta

    assert meta.request is chart.request
    assert meta.location is chart.location
    assert meta.moment_utc is chart.moment_utc
    assert meta.julian_day_ut == chart.julian_day_ut
    assert meta.ayanamsa == chart.ayanamsa


def test_meta_carries_the_convention_descriptors(reference_d1):
    meta = reference_d1.meta

    assert meta.zodiac == "sidereal"
    assert meta.ayanamsha == "Lahiri (Chitrapaksha), true equinox"
    assert meta.house_system == "whole_sign"
    assert meta.node == "mean"
    assert meta.engine_spec == "AstroLearn Calculation Specification FROZEN v1.0"


# --- (5) determinism -------------------------------------------------------


def test_two_builds_from_one_chart_are_equal(chart):
    assert build_d1_chart(chart) == build_d1_chart(chart)


def test_two_builds_from_a_synthetic_chart_are_equal():
    source = synthetic_chart(3)

    assert build_d1_chart(source) == build_d1_chart(source)


def test_occupant_order_is_independent_of_the_source_dict_order():
    forward = synthetic_chart(5)
    backward = synthetic_chart(5, reversed_order=True)

    assert list(backward.grahas) == list(reversed(list(Graha)))

    built_forward = build_d1_chart(forward)
    built_backward = build_d1_chart(backward)

    assert [h.occupants for h in built_forward.houses] == [
        h.occupants for h in built_backward.houses
    ]
    assert list(built_backward.grahas) == list(Graha)


# --- (6) convenience lookups ----------------------------------------------


def test_house_lookup_by_number(reference_d1):
    for number in range(1, 13):
        assert reference_d1.house(number) is reference_d1.houses[number - 1]


@pytest.mark.parametrize("number", [0, 13, -1, 1.0, True, "1"])
def test_house_lookup_rejects_bad_numbers(reference_d1, number):
    with pytest.raises(ValueError):
        reference_d1.house(number)


def test_house_of_graha(reference_d1):
    for graha, placement in reference_d1.grahas.items():
        house = reference_d1.house_of(graha)

        assert house.number == placement.house
        assert graha in house.occupants


# --- (7) DMS pass-through --------------------------------------------------


def test_placement_dms_is_derived_from_degrees_in_rashi(reference_d1):
    rahu = reference_d1.grahas[Graha.RAHU]

    assert isinstance(rahu.dms(), DMS)
    assert rahu.dms() == DMS(13, 47, 17.0)
    assert rahu.dms(2) == DMS(13, 47, 17.55)


def test_lagna_dms(reference_d1):
    assert reference_d1.lagna.dms() == DMS(9, 47, 45.0)
    assert str(reference_d1.lagna.dms()) == "9°47'45\""


# --- (8) reference chart regression ---------------------------------------

EXPECTED_HOUSES = {
    1: ("Meena", (Graha.SUN,)),
    2: ("Mesha", (Graha.KETU,)),
    3: ("Vrishabha", ()),
    4: ("Mithuna", ()),
    5: ("Karka", (Graha.MARS,)),
    6: ("Simha", ()),
    7: ("Kanya", ()),
    8: ("Tula", (Graha.MOON, Graha.RAHU)),
    9: ("Vrishchika", (Graha.JUPITER,)),
    10: ("Dhanu", ()),
    11: ("Makara", (Graha.VENUS,)),
    12: ("Kumbha", (Graha.MERCURY, Graha.SATURN)),
}


@pytest.mark.parametrize("number", sorted(EXPECTED_HOUSES))
def test_reference_house(reference_d1, number):
    rashi_name, occupants = EXPECTED_HOUSES[number]
    house = reference_d1.house(number)

    assert house.rashi_name == rashi_name
    assert house.occupants == occupants


def test_reference_rashi_sequence(reference_d1):
    assert [h.rashi_name for h in reference_d1.houses] == [
        EXPECTED_HOUSES[n][0] for n in range(1, 13)
    ]


def test_reference_lagna(reference_d1):
    lagna = reference_d1.lagna

    assert lagna.house == 1
    assert lagna.rashi_name == "Meena"
    assert lagna.rashi_index == 11
    assert lagna.rashi_number == 12
    assert lagna.nakshatra_name == "Uttara Bhadrapada"
    assert lagna.pada == 2


def test_reference_retrograde_set(reference_d1):
    retrograde = {
        g for g, p in reference_d1.grahas.items() if p.is_retrograde
    }

    assert retrograde == {Graha.MARS, Graha.RAHU, Graha.KETU}
    assert reference_d1.grahas[Graha.MARS].house == 5


# --- (9) immutability ------------------------------------------------------


def test_chart_attributes_cannot_be_rebound(reference_d1):
    with pytest.raises(dataclasses.FrozenInstanceError):
        reference_d1.lagna = None


def test_house_attributes_cannot_be_rebound(reference_d1):
    with pytest.raises(dataclasses.FrozenInstanceError):
        reference_d1.houses[0].rashi_name = "Mesha"


def test_graha_placement_attributes_cannot_be_rebound(reference_d1):
    with pytest.raises(dataclasses.FrozenInstanceError):
        reference_d1.grahas[Graha.SUN].house = 7


def test_lagna_attributes_cannot_be_rebound(reference_d1):
    with pytest.raises(dataclasses.FrozenInstanceError):
        reference_d1.lagna.house = 2


def test_meta_attributes_cannot_be_rebound(reference_d1):
    with pytest.raises(dataclasses.FrozenInstanceError):
        reference_d1.meta.house_system = "placidus"


def test_graha_mapping_is_read_only(reference_d1):
    assert isinstance(reference_d1.grahas, MappingProxyType)

    with pytest.raises(TypeError):
        reference_d1.grahas[Graha.SUN] = None
    with pytest.raises(TypeError):
        del reference_d1.grahas[Graha.SUN]


def test_houses_and_occupants_are_tuples(reference_d1):
    assert isinstance(reference_d1.houses, tuple)
    for house in reference_d1.houses:
        assert isinstance(house.occupants, tuple)


def test_the_mapping_is_copied_before_it_is_proxied(chart):
    """Mutating the dict handed to D1Chart must not touch the built chart."""
    d1 = build_d1_chart(chart)
    grahas = dict(d1.grahas)
    houses = tuple(d1.houses)

    rebuilt = D1Chart(
        source=chart, meta=d1.meta, lagna=d1.lagna, houses=houses,
        grahas=grahas,
    )
    grahas.pop(Graha.MOON)

    assert len(rebuilt.grahas) == 9


# --- (10) construction guards ---------------------------------------------


def test_rejects_a_graha_placed_in_a_house_that_does_not_list_it(chart):
    d1 = build_d1_chart(chart)
    grahas = dict(d1.grahas)
    sun = grahas[Graha.SUN]
    grahas[Graha.SUN] = D1GrahaPlacement(
        graha=Graha.SUN, position=sun.position, house=7
    )

    with pytest.raises(ValueError):
        D1Chart(
            source=chart, meta=d1.meta, lagna=d1.lagna, houses=d1.houses,
            grahas=grahas,
        )


def test_rejects_the_wrong_number_of_houses(chart):
    d1 = build_d1_chart(chart)

    with pytest.raises(ValueError):
        D1Chart(
            source=chart, meta=d1.meta, lagna=d1.lagna,
            houses=d1.houses[:11], grahas=dict(d1.grahas),
        )


# --- (11) layer boundary ---------------------------------------------------

FORBIDDEN_IMPORTS = (
    "swisseph",
    "vedic_chart.ephemeris",
    "vedic_chart.astronomy",
    "vedic_chart.sidereal",
    "vedic_chart.time",
    "vedic_chart.lagna.whole_sign",
    "vedic_chart.location.offline",
    "http",
    "urllib",
    "requests",
    "socket",
    "ssl",
    "ftplib",
    "aiohttp",
)

ALLOWED_PROJECT_IMPORTS = (
    "vedic_chart.chart.model",
    "vedic_chart.vedic.grahas",
    "vedic_chart.vedic.divisions",
    "vedic_chart.lagna.ascendant",
    "vedic_chart.inputs.model",
    "vedic_chart.location.model",
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


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_representation_imports_nothing_forbidden(filename):
    for name in imported_module_names(REPRESENTATION_PACKAGE / filename):
        lowered = name.lower()
        for forbidden in FORBIDDEN_IMPORTS:
            assert not lowered.startswith(forbidden), f"{filename} imports {name}"


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_representation_imports_only_the_allowed_project_modules(filename):
    for name in imported_module_names(REPRESENTATION_PACKAGE / filename):
        if not name.startswith("vedic_chart"):
            continue
        assert any(
            name == allowed or name.startswith(allowed + ".")
            for allowed in ALLOWED_PROJECT_IMPORTS
        ), f"{filename} imports {name}"


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_representation_never_calls_round(filename):
    """Display truncates; a round() anywhere here would be a policy breach."""
    tree = ast.parse((REPRESENTATION_PACKAGE / filename).read_text())

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            assert not (
                isinstance(func, ast.Name) and func.id == "round"
            ), f"{filename} calls round()"
            assert not (
                isinstance(func, ast.Attribute) and func.attr == "round"
            ), f"{filename} calls a round method"


def test_the_package_has_exactly_the_expected_modules():
    modules = sorted(p.name for p in REPRESENTATION_PACKAGE.glob("*.py"))

    assert modules == sorted(PACKAGE_FILES)


# --- (12) types ------------------------------------------------------------


def test_the_representation_types_are_frozen_dataclasses():
    for cls in (D1Chart, D1Meta, D1Lagna, D1House, D1GrahaPlacement):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True
