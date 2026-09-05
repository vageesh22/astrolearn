"""Tests for the offline geocoder (Layer 2).

Every test runs against the committed fixture database, never the production
one: the fixture is small, versioned with the code, and cannot drift under the
tests. Building it is documented in README.md.
"""

import ast
import socket
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.model import (
    AmbiguousPlaceError,
    LocationResolver,
    PlaceCandidate,
    PlaceNotFoundError,
    ResolvedLocation,
)
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.location.offline.search import RankingConfig
from vedic_chart.location.offline.tz_lookup import TimezoneLookupError
from vedic_chart.location.static_resolver import StaticLocationResolver
from vedic_chart.sidereal.positions import calculate_sidereal_positions
from vedic_chart.time.julian_day import julian_day_ut
from vedic_chart.time.local_time import normalize_birth_time
from vedic_chart.vedic.grahas import Graha, derive_grahas

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DB = REPO_ROOT / "tests" / "fixtures" / "geodata_fixture.sqlite"
OFFLINE_PACKAGE = REPO_ROOT / "src" / "vedic_chart" / "location" / "offline"


@pytest.fixture(scope="module")
def resolver():
    with OfflineLocationResolver(FIXTURE_DB) as offline:
        yield offline


# --- India -----------------------------------------------------------------


def test_jalandhar_resolves(resolver):
    location = resolver.resolve("Jalandhar")

    assert location.canonical_name == "Jalandhar, Punjab, India"
    assert location.timezone_id == "Asia/Kolkata"
    assert location.latitude == pytest.approx(31.33, abs=0.05)
    assert location.longitude == pytest.approx(75.58, abs=0.05)


def test_jalandhar_beats_its_population_zero_namesakes(resolver):
    """The city outranks two same-named villages with unknown population."""
    _location, decision = resolver.resolve_with_details("Jalandhar")

    assert decision.dominance_applied is True
    assert decision.materially_different_count >= 2
    assert "868929" in decision.dominance_reason


def test_jalandhar_with_state_qualifier(resolver):
    qualified = resolver.resolve("jalandhar, punjab")
    plain = resolver.resolve("Jalandhar")

    assert qualified.canonical_name == plain.canonical_name
    assert qualified.latitude == plain.latitude


@pytest.mark.parametrize("village", ["Ghanaula", "Kotla Nihang"])
def test_punjab_villages_resolve(resolver, village):
    """Village-level coverage is the point of the full India pack."""
    location = resolver.resolve(village)

    assert location.timezone_id == "Asia/Kolkata"
    assert "Punjab" in location.canonical_name


@pytest.mark.parametrize("town", ["Phagwara", "Kapurthala"])
def test_punjab_towns_resolve(resolver, town):
    location = resolver.resolve(town)

    assert location.timezone_id == "Asia/Kolkata"
    assert "Punjab" in location.canonical_name


def test_new_delhi_and_delhi_resolve(resolver):
    new_delhi = resolver.resolve("New Delhi, India")
    delhi = resolver.resolve("Delhi")

    assert new_delhi.timezone_id == "Asia/Kolkata"
    assert delhi.timezone_id == "Asia/Kolkata"
    assert new_delhi.canonical_name.startswith("New Delhi")
    assert delhi.canonical_name.startswith("Delhi")


def test_historic_name_still_resolves(resolver):
    """GeoNames alternate names carry the colonial-era spelling."""
    assert resolver.resolve("Jullundur").canonical_name == "Jalandhar, Punjab, India"


# --- international ---------------------------------------------------------


def test_london_dominates_by_capital_rule(resolver):
    location, decision = resolver.resolve_with_details("London")

    assert location.canonical_name == "London, England, United Kingdom"
    assert location.timezone_id == "Europe/London"
    assert decision.dominance_applied is True
    assert "capital feature code" in decision.dominance_reason


def test_paris_dominates_and_records_the_decision(resolver):
    location, decision = resolver.resolve_with_details("Paris")

    assert location.canonical_name == "Paris, Île-de-France, France"
    assert location.timezone_id == "Europe/Paris"
    assert decision.dominance_applied is True
    assert decision.dominance_reason


def test_tokyo_and_new_york(resolver):
    assert resolver.resolve("Tokyo").timezone_id == "Asia/Tokyo"
    assert resolver.resolve("New York City").timezone_id == "America/New_York"


def test_country_alias_qualifier(resolver):
    """Our project alias map lets "UK" and "USA" work as qualifiers."""
    assert resolver.resolve("London, UK").canonical_name.endswith("United Kingdom")
    assert resolver.resolve("Springfield, Illinois, USA").timezone_id


# --- ambiguity -------------------------------------------------------------


def test_springfield_is_ambiguous(resolver):
    with pytest.raises(AmbiguousPlaceError) as excinfo:
        resolver.resolve("Springfield")

    candidates = excinfo.value.candidates
    assert len(candidates) >= 2
    assert all(isinstance(c, PlaceCandidate) for c in candidates)
    admin1_names = {c.admin1_name for c in candidates}
    assert len(admin1_names) >= 2


def test_hyderabad_is_ambiguous_across_countries(resolver):
    with pytest.raises(AmbiguousPlaceError) as excinfo:
        resolver.resolve("Hyderabad")

    countries = {c.country_name for c in excinfo.value.candidates}
    assert "India" in countries
    assert "Pakistan" in countries


def test_hyderabad_disambiguated_by_country(resolver):
    location = resolver.resolve("Hyderabad, India")

    assert location.canonical_name == "Hyderabad, Telangana, India"
    assert location.timezone_id == "Asia/Kolkata"


def test_ambiguous_error_is_a_lookup_error(resolver):
    assert issubclass(AmbiguousPlaceError, LookupError)
    with pytest.raises(LookupError):
        resolver.resolve("Hyderabad")


# --- not found -------------------------------------------------------------


def test_unknown_place_raises(resolver):
    with pytest.raises(PlaceNotFoundError):
        resolver.resolve("Xyzzyville")


def test_search_returns_ranked_candidates(resolver):
    candidates = resolver.search("Springfield")

    assert len(candidates) >= 2
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)


# --- timezone --------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    ["Jalandhar", "Ghanaula", "New Delhi, India", "London", "Paris", "Tokyo"],
)
def test_resolved_timezones_are_real(resolver, query):
    timezone_id = resolver.resolve(query).timezone_id

    assert not timezone_id.startswith("Etc/")
    assert ZoneInfo(timezone_id) is not None


def test_timezone_boundary_pair(resolver):
    """Two towns ~20 km apart across the Wabash are in different zones.

    Vincennes is also a genuine GeoNames-vs-spatial disagreement: the dump
    records America/Chicago, the boundary polygon says America/Indiana/Vincennes.
    The resolver trusts the polygon.
    """
    vincennes = resolver.resolve("Vincennes, Indiana")
    mount_carmel = resolver.resolve("Mount Carmel, Illinois")

    assert vincennes.timezone_id == "America/Indiana/Vincennes"
    assert mount_carmel.timezone_id == "America/Chicago"
    assert vincennes.timezone_id != mount_carmel.timezone_id


def test_ocean_coordinates_are_rejected():
    from vedic_chart.location.offline.tz_lookup import lookup

    with pytest.raises(TimezoneLookupError):
        lookup(0.0, -30.0)


# --- protocol conformance --------------------------------------------------


def test_offline_resolver_satisfies_the_protocol(resolver):
    assert isinstance(resolver, LocationResolver)


def test_static_resolver_still_satisfies_the_protocol():
    assert isinstance(StaticLocationResolver(), LocationResolver)


def test_resolve_returns_a_validated_location(resolver):
    assert isinstance(resolver.resolve("Jalandhar"), ResolvedLocation)


# --- configuration ---------------------------------------------------------


def test_ranking_config_override_changes_dominance():
    """Every threshold lives in RankingConfig, so behaviour follows it."""
    permissive = RankingConfig(dominance_population_ratio=1.0)

    with OfflineLocationResolver(FIXTURE_DB) as strict_resolver:
        with pytest.raises(AmbiguousPlaceError):
            strict_resolver.resolve("Hyderabad")

    with OfflineLocationResolver(FIXTURE_DB, permissive) as loose_resolver:
        location, decision = loose_resolver.resolve_with_details("Hyderabad")

    assert decision.dominance_applied is True
    assert location.canonical_name == "Hyderabad, Telangana, India"


def test_ranking_config_is_the_only_source_of_thresholds():
    config = RankingConfig()

    assert config.dominance_population_ratio == 50.0
    assert config.dominance_min_population == 1000
    assert config.capital_feature_codes == frozenset({"PPLC"})
    assert "PPLH" not in config.auto_pick_required_feature_codes


# --- no network ------------------------------------------------------------

NETWORK_MODULES = ("http", "urllib", "requests", "socket", "ssl", "ftplib", "aiohttp")


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
    "filename",
    ["__init__.py", "normalize.py", "db.py", "search.py", "tz_lookup.py", "resolver.py"],
)
def test_offline_package_imports_nothing_network_capable(filename):
    for name in imported_module_names(OFFLINE_PACKAGE / filename):
        head = name.split(".")[0].lower()
        assert head not in NETWORK_MODULES, f"{filename} imports {name}"


def test_resolution_works_with_sockets_disabled(monkeypatch):
    """Prove it at runtime, not just by reading imports."""

    def forbidden(*args, **kwargs):
        raise AssertionError("the offline resolver attempted a network call")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

    with OfflineLocationResolver(FIXTURE_DB) as offline:
        assert offline.resolve("Jalandhar").timezone_id == "Asia/Kolkata"
        assert offline.resolve("London").timezone_id == "Europe/London"
        assert offline.resolve("Ghanaula").timezone_id == "Asia/Kolkata"
        with pytest.raises(AmbiguousPlaceError):
            offline.resolve("Hyderabad")


# --- provenance ------------------------------------------------------------


def test_database_records_its_provenance(resolver):
    rows = resolver.dataset_metadata()

    assert len(rows) == 7
    datasets = {row["dataset"] for row in rows}
    assert "cities500.zip" in datasets
    assert any("timezonefinder" in name for name in datasets)
    for row in rows:
        assert row["license"]
        assert row["attribution"]
        assert row["source_release"]


# --- full pipeline ---------------------------------------------------------


def test_full_pipeline_offline(resolver):
    """Layer 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7, with no network at any point."""
    request = BirthChartRequest.from_components(
        2000, 1, 1, 17, 30, place_query="Jalandhar"
    )

    place = resolver.resolve(request.place_query)
    moment = normalize_birth_time(
        request.birth_date, request.birth_time, place.timezone_id
    )

    assert moment == datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert julian_day_ut(moment) == 2451545.0

    with ephemeris_session(str(REPO_ROOT / "ephe")):
        grahas = derive_grahas(calculate_sidereal_positions(moment))

    assert len(grahas) == 9
    sun = grahas[Graha.SUN]
    assert sun.sidereal_longitude == pytest.approx(256.5157, abs=1e-3)  # true-equinox Lahiri (OPEN-1 resolved 2026-09-05)
    assert sun.placement.rashi_name == "Dhanu"
