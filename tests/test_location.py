"""Tests for the Layer 2 location boundary.

Pure tests: no ephemeris files and no ephemeris fixture are needed.
"""

import ast
import dataclasses
from datetime import date, datetime, time, timezone
from pathlib import Path

import pytest

from vedic_chart.location.model import (
    InvalidCoordinateError,
    LocationResolver,
    PlaceNotFoundError,
    ResolvedLocation,
)
from vedic_chart.location.static_resolver import StaticLocationResolver
from vedic_chart.time.julian_day import julian_day_ut
from vedic_chart.time.local_time import InvalidTimezoneError, normalize_birth_time

LOCATION_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "vedic_chart" / "location"


def build(**overrides) -> ResolvedLocation:
    fields = {
        "canonical_name": "Somewhere",
        "latitude": 0.0,
        "longitude": 0.0,
        "timezone_id": "Asia/Kolkata",
    }
    fields.update(overrides)
    return ResolvedLocation(**fields)


# --- coordinate validation -------------------------------------------------


@pytest.mark.parametrize("latitude", [90.0, -90.0, 0.0, 28.6139])
def test_latitudes_in_range_are_accepted(latitude):
    assert build(latitude=latitude).latitude == latitude


@pytest.mark.parametrize("latitude", [90.000001, -91.0, 180.0])
def test_latitudes_out_of_range_are_rejected(latitude):
    with pytest.raises(InvalidCoordinateError):
        build(latitude=latitude)


@pytest.mark.parametrize("longitude", [180.0, -180.0, 0.0, -74.0060])
def test_longitudes_in_range_are_accepted(longitude):
    assert build(longitude=longitude).longitude == longitude


@pytest.mark.parametrize("longitude", [180.5, -181.0])
def test_longitudes_out_of_range_are_rejected(longitude):
    with pytest.raises(InvalidCoordinateError):
        build(longitude=longitude)


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), float("-inf")]
)
def test_non_finite_coordinates_are_rejected(value):
    with pytest.raises(InvalidCoordinateError):
        build(latitude=value)
    with pytest.raises(InvalidCoordinateError):
        build(longitude=value)


def test_coordinate_error_names_the_value():
    with pytest.raises(InvalidCoordinateError, match="91"):
        build(latitude=91.0)


# --- timezone and name validation ------------------------------------------


def test_valid_timezone_is_accepted():
    assert build(timezone_id="Asia/Kolkata").timezone_id == "Asia/Kolkata"


@pytest.mark.parametrize("timezone_id", ["Asia/Kolkatta", "", "Not/AZone"])
def test_invalid_timezone_is_rejected(timezone_id):
    with pytest.raises(InvalidTimezoneError):
        build(timezone_id=timezone_id)


def test_timezone_error_is_the_shared_type():
    # The same exception Layer 3 raises, not a near-duplicate.
    assert issubclass(InvalidTimezoneError, ValueError)
    with pytest.raises(ValueError):
        build(timezone_id="Asia/Kolkatta")


@pytest.mark.parametrize("canonical_name", ["", "   ", "\t\n"])
def test_blank_canonical_name_is_rejected(canonical_name):
    with pytest.raises(ValueError):
        build(canonical_name=canonical_name)


def test_resolved_location_is_immutable():
    location = build()
    with pytest.raises(dataclasses.FrozenInstanceError):
        location.latitude = 10.0


# --- static resolver -------------------------------------------------------


EXPECTED_PLACES = {
    "New Delhi, India": (28.6139, 77.2090, "Asia/Kolkata"),
    "Jalandhar, India": (31.3260, 75.5762, "Asia/Kolkata"),
    "New York, USA": (40.7128, -74.0060, "America/New_York"),
    "London, UK": (51.5074, -0.1278, "Europe/London"),
    "Tokyo, Japan": (35.6764, 139.6500, "Asia/Tokyo"),
}


@pytest.fixture
def resolver():
    return StaticLocationResolver()


@pytest.mark.parametrize("canonical_name", sorted(EXPECTED_PLACES))
def test_known_places_resolve_exactly(resolver, canonical_name):
    latitude, longitude, timezone_id = EXPECTED_PLACES[canonical_name]

    resolved = resolver.resolve(canonical_name)

    assert resolved.canonical_name == canonical_name
    assert resolved.latitude == latitude
    assert resolved.longitude == longitude
    assert resolved.timezone_id == timezone_id


@pytest.mark.parametrize(
    ("query", "canonical_name"),
    [
        ("  NEW   delhi  ", "New Delhi, India"),
        ("delhi", "New Delhi, India"),
        ("NYC", "New York, USA"),
        ("new york city", "New York, USA"),
        ("Tokyo, JAPAN", "Tokyo, Japan"),
        ("JALANDHAR", "Jalandhar, India"),
        ("london,   uk", "London, UK"),
    ],
)
def test_lookup_ignores_case_and_spacing(resolver, query, canonical_name):
    assert resolver.resolve(query).canonical_name == canonical_name


def test_both_indian_cities_share_a_timezone(resolver):
    assert resolver.resolve("delhi").timezone_id == "Asia/Kolkata"
    assert resolver.resolve("jalandhar").timezone_id == "Asia/Kolkata"


def test_new_york_carries_an_identifier_not_an_offset(resolver):
    timezone_id = resolver.resolve("nyc").timezone_id
    assert timezone_id == "America/New_York"
    # Nothing that looks like a stored offset.
    assert "+" not in timezone_id and not timezone_id.startswith("-")
    assert not hasattr(resolver.resolve("nyc"), "utc_offset")


def test_repeated_keys_share_one_instance(resolver):
    assert resolver.resolve("delhi") is resolver.resolve("new delhi, india")


@pytest.mark.parametrize("query", ["Atlantis", "Paris", "", "New Del"])
def test_unknown_places_are_rejected(resolver, query):
    with pytest.raises(PlaceNotFoundError):
        resolver.resolve(query)


def test_not_found_message_names_the_query(resolver):
    with pytest.raises(PlaceNotFoundError, match="Atlantis"):
        resolver.resolve("Atlantis")


def test_known_places_lists_five(resolver):
    names = resolver.known_places()
    assert len(names) == 5
    assert set(names) == set(EXPECTED_PLACES)


def test_static_resolver_satisfies_the_protocol(resolver):
    assert isinstance(resolver, LocationResolver)


# --- layer separation ------------------------------------------------------


FORBIDDEN_IMPORT_FRAGMENTS = (
    "swisseph",
    "ephemeris",
    "astronomy",
    "sidereal",
    "julian",
)


def imported_module_names(path: Path) -> list[str]:
    """Every module named by an import statement, parsed rather than grepped."""
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


@pytest.mark.parametrize("filename", ["model.py", "static_resolver.py"])
def test_location_layer_imports_no_calculation_layers(filename):
    names = imported_module_names(LOCATION_PACKAGE / filename)
    assert names, filename

    for name in names:
        lowered = name.lower()
        for fragment in FORBIDDEN_IMPORT_FRAGMENTS:
            assert fragment not in lowered, f"{filename} imports {name}"


def test_model_imports_exactly_one_project_name():
    names = imported_module_names(LOCATION_PACKAGE / "model.py")
    project = [n for n in names if n.startswith("vedic_chart")]
    assert project == [
        "vedic_chart.time.local_time",
        "vedic_chart.time.local_time.InvalidTimezoneError",
    ]


# --- integration with Layer 3 ----------------------------------------------


def test_resolved_timezone_feeds_layer_three(resolver):
    resolved = resolver.resolve("Jalandhar")

    moment = normalize_birth_time(
        date(2000, 1, 1), time(17, 30), resolved.timezone_id
    )

    assert moment == datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert julian_day_ut(moment) == 2451545.0
