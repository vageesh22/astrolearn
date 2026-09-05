"""Tests for the Lagna layer: sidereal ascendant and Whole Sign houses."""

import ast
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from vedic_chart.astronomy.positions import (
    Body,
    calculate_positions,
    ephemeris_session,
)
from vedic_chart.ephemeris.swiss_ephemeris import (
    calc_ascendant_tropical,
    get_ayanamsa_lahiri,
)
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.lagna.ascendant import Lagna, calculate_lagna
from vedic_chart.lagna.whole_sign import assign_houses, house_number
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.time.julian_day import julian_day_ut
from vedic_chart.time.local_time import normalize_birth_time
from vedic_chart.vedic.divisions import classify
from vedic_chart.vedic.grahas import Graha, derive_grahas

REPO_ROOT = Path(__file__).resolve().parent.parent
EPHE_DIR = str(REPO_ROOT / "ephe")
FIXTURE_DB = REPO_ROOT / "tests" / "fixtures" / "geodata_fixture.sqlite"
LAGNA_PACKAGE = REPO_ROOT / "src" / "vedic_chart" / "lagna"

JALANDHAR = (31.3260, 75.5762)
J2000 = datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def ephemeris():
    with ephemeris_session(EPHE_DIR):
        yield


def shortest_arc(a: float, b: float) -> float:
    """Signed difference a - b, wrapped into (-180, 180]."""
    return (a - b + 180.0) % 360.0 - 180.0


# --- Whole Sign houses: pure ----------------------------------------------


def test_lagna_in_mesha():
    assert house_number(0, 0) == 1
    assert house_number(11, 0) == 12
    assert house_number(6, 0) == 7


def test_lagna_in_tula():
    # Lagna in Tula (index 6): Tula is house 1, Mesha becomes house 7.
    assert house_number(6, 6) == 1
    assert house_number(0, 6) == 7
    assert house_number(5, 6) == 12
    assert house_number(7, 6) == 2


def test_every_lagna_gives_a_permutation_of_the_twelve_houses():
    for lagna_index in range(12):
        houses = [house_number(rashi, lagna_index) for rashi in range(12)]
        assert sorted(houses) == list(range(1, 13)), lagna_index


@pytest.mark.parametrize("bad", [-1, 12, 100])
def test_invalid_indices_rejected(bad):
    with pytest.raises(ValueError):
        house_number(bad, 0)
    with pytest.raises(ValueError):
        house_number(0, bad)


def test_assign_houses_is_generic_over_keys():
    houses = assign_houses(6, {"sun": 6, "moon": 0, "mars": 5})

    assert houses == {"sun": 1, "moon": 7, "mars": 12}


def test_assign_houses_validates_the_lagna():
    with pytest.raises(ValueError):
        assign_houses(12, {"sun": 0})


# --- independent-formula cross-check ---------------------------------------


def independent_ascendant(julian_day: float, latitude: float, longitude: float) -> float:
    """A textbook tropical ascendant, written from scratch for this test.

    Deliberately shares no code with the implementation: GMST from the IAU 1982
    polynomial, mean obliquity (no nutation), and the standard ascendant
    formula. Swiss Ephemeris computes the *apparent* ascendant with true
    obliquity, so a small disagreement is expected and is the point of the
    tolerance.
    """
    days = julian_day - 2451545.0
    centuries = days / 36525.0

    gmst = (
        280.46061837
        + 360.98564736629 * days
        + 0.000387933 * centuries**2
        - centuries**3 / 38710000.0
    ) % 360.0
    local_sidereal = math.radians((gmst + longitude) % 360.0)

    obliquity = math.radians(
        23.439291111
        - 0.0130041667 * centuries
        - 1.638889e-7 * centuries**2
        + 5.036111e-7 * centuries**3
    )
    latitude_rad = math.radians(latitude)

    ascendant = math.degrees(
        math.atan2(
            math.cos(local_sidereal),
            -(
                math.sin(local_sidereal) * math.cos(obliquity)
                + math.tan(latitude_rad) * math.sin(obliquity)
            ),
        )
    )
    return ascendant % 360.0


CROSS_CHECK_CASES = [
    ("Jalandhar", datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc), 31.3260, 75.5762),
    ("London", datetime(1985, 6, 15, 9, 20, tzinfo=timezone.utc), 51.5074, -0.1278),
    ("Tokyo", datetime(2010, 11, 3, 21, 5, tzinfo=timezone.utc), 35.6764, 139.6500),
    ("Sydney", datetime(1972, 2, 29, 3, 33, tzinfo=timezone.utc), -33.8688, 151.2093),
    ("Quito", datetime(2024, 6, 21, 18, 0, tzinfo=timezone.utc), -0.1807, -78.4678),
]

CROSS_CHECK_TOLERANCE = 0.5


@pytest.mark.parametrize(
    ("label", "moment", "latitude", "longitude"), CROSS_CHECK_CASES
)
def test_ascendant_matches_an_independent_formula(
    ephemeris, label, moment, latitude, longitude
):
    julian_day = julian_day_ut(moment)
    from_library = calc_ascendant_tropical(julian_day, latitude, longitude)
    from_formula = independent_ascendant(julian_day, latitude, longitude)

    delta = abs(shortest_arc(from_library, from_formula))
    assert delta < CROSS_CHECK_TOLERANCE, (
        f"{label}: swisseph {from_library:.6f} vs formula "
        f"{from_formula:.6f}, delta {delta:.6f} deg"
    )


# --- physical behaviour ----------------------------------------------------


def test_ascendant_meets_the_sun_at_sunrise(ephemeris):
    """At sunrise the ascendant is, by definition, the Sun's longitude."""
    latitude, longitude = JALANDHAR
    midnight = datetime(2000, 1, 1, tzinfo=timezone.utc)

    def difference(minutes: float) -> float:
        moment = midnight + timedelta(minutes=minutes)
        julian_day = julian_day_ut(moment)
        ascendant = calc_ascendant_tropical(julian_day, latitude, longitude)
        sun = calculate_positions(moment)[Body.SUN].longitude
        return shortest_arc(ascendant, sun)

    # The Sun rises somewhere in this window: the ascendant is behind it at
    # 01:00 UTC and ahead of it by 03:00 UTC.
    assert difference(60) < 0
    assert difference(180) > 0

    low, high = 60.0, 180.0
    for _ in range(60):
        middle = (low + high) / 2.0
        if difference(middle) < 0:
            low = middle
        else:
            high = middle
    crossing = (low + high) / 2.0

    assert abs(difference(crossing)) < 0.01
    # Geometric sunrise at Jalandhar on this date, a few minutes after the
    # refracted apparent sunrise.
    assert 60.0 < crossing < 180.0


def test_ascendant_rotates_through_every_sign_in_a_day(ephemeris):
    latitude, longitude = JALANDHAR
    start = datetime(2000, 1, 1, tzinfo=timezone.utc)

    seen = set()
    previous = None
    for step in range(24 * 6):
        moment = start + timedelta(minutes=10 * step)
        lagna = calculate_lagna(moment, latitude, longitude)
        seen.add(lagna.placement.rashi_index)

        if previous is not None:
            advance = (lagna.tropical_longitude - previous) % 360.0
            # Always forward, and never more than a sign in ten minutes.
            assert 0.0 < advance < 30.0
        previous = lagna.tropical_longitude

    assert seen == set(range(12))


def test_ascendant_closes_over_a_sidereal_day(ephemeris):
    latitude, longitude = JALANDHAR
    start = datetime(2000, 1, 1, tzinfo=timezone.utc)
    sidereal_day = timedelta(hours=23, minutes=56, seconds=4)

    first = calc_ascendant_tropical(julian_day_ut(start), latitude, longitude)
    second = calc_ascendant_tropical(
        julian_day_ut(start + sidereal_day), latitude, longitude
    )

    assert abs(shortest_arc(first, second)) < 1.5


# --- sidereal consistency --------------------------------------------------


def test_lagna_sidereal_matches_the_shared_rotation(ephemeris):
    lagna = calculate_lagna(J2000, *JALANDHAR)

    expected = (lagna.tropical_longitude - lagna.ayanamsa) % 360.0
    assert lagna.sidereal_longitude == pytest.approx(expected, abs=1e-12)
    assert 0.0 <= lagna.sidereal_longitude < 360.0


def test_lagna_uses_the_existing_ayanamsa(ephemeris):
    lagna = calculate_lagna(J2000, *JALANDHAR)

    assert lagna.ayanamsa == get_ayanamsa_lahiri(julian_day_ut(J2000))


def test_lagna_placement_uses_the_existing_classifier(ephemeris):
    lagna = calculate_lagna(J2000, *JALANDHAR)

    assert lagna.placement == classify(lagna.sidereal_longitude)
    assert isinstance(lagna, Lagna)


def test_lagna_tropical_matches_the_boundary(ephemeris):
    lagna = calculate_lagna(J2000, *JALANDHAR)

    assert lagna.tropical_longitude == calc_ascendant_tropical(
        julian_day_ut(J2000), *JALANDHAR
    )


# --- edges -----------------------------------------------------------------


def test_extreme_latitude_returns_a_value(ephemeris):
    """The polar caveat: defined, badly behaved, returned as computed."""
    lagna = calculate_lagna(J2000, 89.0, 0.0)

    assert 0.0 <= lagna.sidereal_longitude < 360.0
    assert 0 <= lagna.placement.rashi_index <= 11


@pytest.mark.parametrize("latitude", [91.0, -91.0, float("nan"), float("inf")])
def test_invalid_latitude_rejected(ephemeris, latitude):
    with pytest.raises(ValueError):
        calculate_lagna(J2000, latitude, 0.0)


@pytest.mark.parametrize("longitude", [181.0, -181.0, float("nan")])
def test_invalid_longitude_rejected(ephemeris, longitude):
    with pytest.raises(ValueError):
        calculate_lagna(J2000, 0.0, longitude)


def test_naive_datetime_rejected(ephemeris):
    with pytest.raises(ValueError):
        calculate_lagna(datetime(2000, 1, 1, 12, 0), *JALANDHAR)


# --- layer separation ------------------------------------------------------


FORBIDDEN_TOP_LEVEL = (
    "swisseph",
    "http",
    "urllib",
    "requests",
    "socket",
    "ssl",
    "ftplib",
    "aiohttp",
)
FORBIDDEN_FRAGMENTS = ("swisseph", "location", "inputs")


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


@pytest.mark.parametrize(
    "filename", ["__init__.py", "ascendant.py", "whole_sign.py"]
)
def test_lagna_package_stays_within_its_layer(filename):
    for name in imported_module_names(LAGNA_PACKAGE / filename):
        head = name.split(".")[0].lower()
        assert head not in FORBIDDEN_TOP_LEVEL, f"{filename} imports {name}"
        for fragment in FORBIDDEN_FRAGMENTS:
            assert fragment not in name.lower(), f"{filename} imports {name}"


def test_whole_sign_is_pure_stdlib():
    assert imported_module_names(LAGNA_PACKAGE / "whole_sign.py") == []


# --- full pipeline ---------------------------------------------------------


def test_full_pipeline_with_lagna_and_houses(ephemeris):
    request = BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query="Jalandhar"
    )

    with OfflineLocationResolver(FIXTURE_DB) as resolver:
        place = resolver.resolve(request.place_query)

    moment = normalize_birth_time(
        request.birth_date, request.birth_time, place.timezone_id
    )
    lagna = calculate_lagna(moment, place.latitude, place.longitude)
    grahas = derive_grahas_for(moment)

    houses = assign_houses(
        lagna.placement.rashi_index,
        {graha: position.placement.rashi_index for graha, position in grahas.items()},
    )

    assert len(houses) == 9
    assert all(1 <= house <= 12 for house in houses.values())

    assert lagna.placement.rashi_name
    assert lagna.placement.nakshatra_name
    assert 1 <= lagna.placement.pada <= 4

    sun_rashi = grahas[Graha.SUN].placement.rashi_index
    assert houses[Graha.SUN] == (sun_rashi - lagna.placement.rashi_index) % 12 + 1


def derive_grahas_for(moment):
    from vedic_chart.sidereal.positions import calculate_sidereal_positions

    return derive_grahas(calculate_sidereal_positions(moment))
