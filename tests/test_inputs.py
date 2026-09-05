"""Tests for the Layer 1 birth-chart request model.

Pure tests apart from the single end-to-end integration test at the bottom.
"""

import ast
import dataclasses
from datetime import date, datetime, time, timezone
from pathlib import Path

import pytest

from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.sidereal.positions import calculate_sidereal_positions
from vedic_chart.inputs.model import (
    BirthChartRequest,
    InvalidBirthDateError,
    InvalidBirthTimeError,
    InvalidPlaceQueryError,
)
from vedic_chart.location.static_resolver import StaticLocationResolver
from vedic_chart.time.julian_day import julian_day_ut
from vedic_chart.time.local_time import normalize_birth_time
from vedic_chart.vedic.grahas import Graha, derive_grahas

INPUTS_MODEL = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "vedic_chart"
    / "inputs"
    / "model.py"
)


# --- valid construction ----------------------------------------------------


def test_fields_are_preserved_exactly():
    request = BirthChartRequest(
        birth_date=date(1995, 3, 21),
        birth_time=time(6, 45),
        place_query="Jalandhar",
    )

    assert request.birth_date == date(1995, 3, 21)
    assert request.birth_time == time(6, 45)
    assert request.place_query == "Jalandhar"


def test_seconds_and_microseconds_are_preserved():
    request = BirthChartRequest(
        birth_date=date(2000, 1, 1),
        birth_time=time(23, 59, 59, 999999),
        place_query="Tokyo",
    )

    assert request.birth_time == time(23, 59, 59, 999999)
    assert request.birth_time.second == 59
    assert request.birth_time.microsecond == 999999


def test_place_query_is_stored_verbatim():
    # Surrounding whitespace is accepted and kept: normalizing queries is the
    # resolver's job, not this layer's.
    request = BirthChartRequest(
        birth_date=date(2000, 1, 1),
        birth_time=time(12, 0),
        place_query="  Jalandhar  ",
    )

    assert request.place_query == "  Jalandhar  "


# --- from_components -------------------------------------------------------


def test_from_components_accepts_a_leap_day():
    request = BirthChartRequest.from_components(
        2000, 2, 29, 12, 0, place_query="London"
    )

    assert request.birth_date == date(2000, 2, 29)
    assert request.birth_time == time(12, 0)
    assert request.place_query == "London"


def test_from_components_preserves_every_component():
    request = BirthChartRequest.from_components(
        1990, 5, 15, 14, 30, 45, 123456, place_query="Tokyo"
    )

    assert request.birth_date == date(1990, 5, 15)
    assert request.birth_time == time(14, 30, 45, 123456)


@pytest.mark.parametrize(
    "components",
    [
        (1900, 2, 29),  # 1900 was not a leap year
        (2023, 2, 30),
        (2023, 13, 1),
        (2023, 0, 1),
        (2023, 1, 0),
        (2023, 4, 31),
    ],
)
def test_from_components_rejects_impossible_dates(components):
    year, month, day = components
    with pytest.raises(InvalidBirthDateError):
        BirthChartRequest.from_components(
            year, month, day, 12, 0, place_query="London"
        )


@pytest.mark.parametrize(
    "clock",
    [
        (24, 0, 0, 0),
        (12, 60, 0, 0),
        (12, 0, 60, 0),
        (12, 0, 0, 1000000),
        (-1, 0, 0, 0),
    ],
)
def test_from_components_rejects_impossible_times(clock):
    hour, minute, second, microsecond = clock
    with pytest.raises(InvalidBirthTimeError):
        BirthChartRequest.from_components(
            2000, 1, 1, hour, minute, second, microsecond, place_query="London"
        )


def test_date_error_names_the_offending_components():
    with pytest.raises(InvalidBirthDateError, match="30"):
        BirthChartRequest.from_components(
            2023, 2, 30, 12, 0, place_query="London"
        )


# --- rejected kinds of value -----------------------------------------------


def test_naive_datetime_is_rejected_as_birth_date():
    with pytest.raises(InvalidBirthDateError):
        BirthChartRequest(
            birth_date=datetime(2000, 1, 1, 12, 0),
            birth_time=time(12, 0),
            place_query="London",
        )


def test_aware_datetime_is_rejected_as_birth_date():
    with pytest.raises(InvalidBirthDateError):
        BirthChartRequest(
            birth_date=datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc),
            birth_time=time(12, 0),
            place_query="London",
        )


def test_aware_birth_time_is_rejected():
    with pytest.raises(InvalidBirthTimeError) as excinfo:
        BirthChartRequest(
            birth_date=date(2000, 1, 1),
            birth_time=time(12, 0, tzinfo=timezone.utc),
            place_query="London",
        )

    message = str(excinfo.value)
    assert "Layer 2" in message and "Layer 3" in message


def test_string_birth_date_is_rejected():
    with pytest.raises(InvalidBirthDateError):
        BirthChartRequest(
            birth_date="2000-01-01",
            birth_time=time(12, 0),
            place_query="London",
        )


def test_string_birth_time_is_rejected():
    with pytest.raises(InvalidBirthTimeError):
        BirthChartRequest(
            birth_date=date(2000, 1, 1),
            birth_time="12:00",
            place_query="London",
        )


@pytest.mark.parametrize("place_query", [None, 123, 4.5, ["London"]])
def test_non_string_place_query_is_rejected(place_query):
    with pytest.raises(InvalidPlaceQueryError):
        BirthChartRequest(
            birth_date=date(2000, 1, 1),
            birth_time=time(12, 0),
            place_query=place_query,
        )


@pytest.mark.parametrize("place_query", ["", "   ", "\t\n"])
def test_blank_place_query_is_rejected(place_query):
    with pytest.raises(InvalidPlaceQueryError):
        BirthChartRequest(
            birth_date=date(2000, 1, 1),
            birth_time=time(12, 0),
            place_query=place_query,
        )


# --- model shape -----------------------------------------------------------


def test_all_errors_are_value_errors():
    for error_type in (
        InvalidBirthDateError,
        InvalidBirthTimeError,
        InvalidPlaceQueryError,
    ):
        assert issubclass(error_type, ValueError)


def test_request_is_immutable():
    request = BirthChartRequest(
        birth_date=date(2000, 1, 1),
        birth_time=time(12, 0),
        place_query="London",
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        request.place_query = "Tokyo"


def test_model_carries_no_location_or_timezone_fields():
    names = {field.name for field in dataclasses.fields(BirthChartRequest)}
    assert names == {"birth_date", "birth_time", "place_query"}


# --- layer separation ------------------------------------------------------


FORBIDDEN_IMPORT_FRAGMENTS = (
    "swisseph",
    "ephemeris",
    "astronomy",
    "sidereal",
    "julian",
    "location",
    "zoneinfo",
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


def test_input_layer_imports_nothing_from_the_project():
    names = imported_module_names(INPUTS_MODEL)
    assert names

    assert not [name for name in names if name.startswith("vedic_chart")]


def test_input_layer_knows_nothing_of_timezones_or_astronomy():
    for name in imported_module_names(INPUTS_MODEL):
        lowered = name.lower()
        for fragment in FORBIDDEN_IMPORT_FRAGMENTS:
            assert fragment not in lowered, f"model.py imports {name}"


# --- integration through Layers 2, 3 and 4 ---------------------------------


def test_request_feeds_the_pipeline():
    request = BirthChartRequest.from_components(
        2000, 1, 1, 17, 30, place_query="Jalandhar"
    )

    resolved = StaticLocationResolver().resolve(request.place_query)
    moment = normalize_birth_time(
        request.birth_date, request.birth_time, resolved.timezone_id
    )

    assert resolved.canonical_name == "Jalandhar, India"
    assert moment == datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert julian_day_ut(moment) == 2451545.0

    # And the instant drives the calculation layers all the way to a graha.
    with ephemeris_session(
        str(Path(__file__).resolve().parent.parent / "ephe")
    ):
        grahas = derive_grahas(calculate_sidereal_positions(moment))

    assert len(grahas) == 9
    sun = grahas[Graha.SUN]
    assert sun.sidereal_longitude == pytest.approx(256.5157, abs=1e-3)  # true-equinox Lahiri (OPEN-1 resolved 2026-09-05)
    assert sun.placement.rashi_name == "Dhanu"
