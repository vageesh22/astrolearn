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


# --- Layer 15 C1: suggest() ------------------------------------------------
#
# The fixture database holds Jalandhar (1268782), London, two Hyderabads and
# five Springfields, and deliberately does **not** hold Jammu: the production
# default record belongs to the acceptance run, not to this suite.

JALANDHAR_ID = 1268782


def labels(candidates) -> list[str]:
    return [OfflineLocationResolver.candidate_label(c) for c in candidates]


def test_suggest_lists_jalandhar_for_its_prefix(resolver):
    candidates = resolver.suggest("jal", limit=10)

    assert len(candidates) <= 10
    assert all(isinstance(c, PlaceCandidate) for c in candidates)
    assert candidates[0].geoname_id == JALANDHAR_ID
    assert labels(candidates)[0] == "Jalandhar, Punjab, India"


def test_suggest_deduplicates_a_place_with_many_names(resolver):
    """Jalandhar carries a dozen names; it is one suggestion, not a dozen."""
    candidates = resolver.suggest("jal", limit=50)
    ids = [candidate.geoname_id for candidate in candidates]

    assert len(ids) == len(set(ids))


def test_suggest_normalises_the_prefix_like_a_query(resolver):
    """``jāl`` and ``jal`` are the same prefix: one normalisation, Layer 2's."""
    assert resolver.suggest("jāl", limit=10) == resolver.suggest("jal", limit=10)
    assert resolver.suggest("JAL", limit=10) == resolver.suggest("jal", limit=10)
    assert resolver.suggest("  jal  ", limit=10) == resolver.suggest(
        "jal", limit=10
    )


def test_suggest_obeys_the_limit(resolver):
    assert len(resolver.suggest("ja", limit=3)) == 3
    assert len(resolver.suggest("ja", limit=1)) == 1


def test_a_one_character_prefix_lists_nothing_and_does_not_raise(resolver):
    assert resolver.suggest("j", limit=10) == []
    assert resolver.suggest("", limit=10) == []
    assert resolver.suggest("   ", limit=10) == []
    # Two code points *after* normalisation is the rule: the marks are dropped
    # before the length is measured, and edge punctuation with them.
    assert resolver.suggest("j.", limit=10) == []


def test_an_unmatched_prefix_lists_nothing(resolver):
    assert resolver.suggest("xyzzyvill", limit=10) == []


def test_suggest_never_resolves_a_timezone(resolver):
    """Section 5.1: a suggestion is not a resolved place."""
    for candidate in resolver.suggest("ja", limit=10):
        assert candidate.timezone_id is None


def test_a_comma_qualifier_filters_by_country(resolver):
    """Decision E4, on the fixture's two Hyderabads."""
    indian = resolver.suggest("hyderabad, india", limit=10)
    pakistani = resolver.suggest("hyderabad, pakistan", limit=10)
    both = resolver.suggest("hyderabad", limit=10)

    assert [c.country_name for c in indian] == ["India"]
    assert [c.country_name for c in pakistani] == ["Pakistan"]
    assert {c.country_name for c in both} == {"India", "Pakistan"}


def test_a_comma_qualifier_works_through_a_country_alias(resolver):
    """``Delhi, IN`` matches through ``country_aliases``, as resolution does."""
    by_alias = resolver.suggest("delhi, in", limit=10)
    by_name = resolver.suggest("delhi, india", limit=10)

    assert by_alias == by_name
    assert by_alias
    assert all(c.country_name == "India" for c in by_alias)


def test_a_comma_qualifier_matches_an_admin1_name(resolver):
    qualified = resolver.suggest("springfield, illinois", limit=10)

    assert [c.admin1_name for c in qualified] == ["Illinois"]


def test_an_unmatched_qualifier_lists_nothing_rather_than_raising(resolver):
    assert resolver.suggest("hyderabad, france", limit=10) == []


def test_the_qualifier_filter_applies_before_the_limit(resolver):
    """Five Springfields, one of which is in Illinois: a limit of 1 finds it."""
    assert len(resolver.suggest("springfield", limit=5)) == 5
    one = resolver.suggest("springfield, illinois", limit=1)

    assert [c.admin1_name for c in one] == ["Illinois"]


def test_the_order_is_population_then_exact_then_name_then_id(resolver):
    """Ordering as revised in v0.3, asserted on a constructed tie.

    Two places share the population 0 and the prefix; the exact-name match
    comes first, and among rows that tie on all three the ``geoname_id``
    decides. The assertion is made against the fixture's own rows rather than
    against a literal list, so it states the rule and not a snapshot.
    """
    candidates = resolver.suggest("lo", limit=50)

    keys = [
        (
            -candidate.population,
            0 if candidate.matched_name.casefold() == "lo" else 1,
            candidate.name,
            candidate.geoname_id,
        )
        for candidate in candidates
    ]
    assert keys == sorted(keys)
    assert candidates[0].name == "London"
    assert candidates[0].population == 8961989


def test_population_outranks_an_exact_name_match(resolver):
    """The v0.3 evidence: a population-0 hamlet named ``London`` sorts last."""
    candidates = resolver.suggest("lo", limit=50)
    exact = [c for c in candidates if c.matched_name == "London"]

    assert len(exact) >= 2
    assert exact[0].geoname_id == 2643743
    assert candidates.index(exact[0]) == 0
    assert candidates.index(exact[-1]) > 0
    assert exact[-1].population == 0


def test_the_matched_name_is_the_exact_match_when_a_place_has_one(resolver):
    hamlet = next(
        candidate
        for candidate in resolver.suggest("london", limit=50)
        if candidate.geoname_id == 10304286
    )

    assert hamlet.name == "Ban Sarkāri"
    assert hamlet.matched_name == "London"


def test_the_matched_name_is_otherwise_the_smallest_matching_name(resolver):
    """``MIN(pn.original)`` over the group: deterministic, never arbitrary."""
    import sqlite3

    candidate = next(
        one
        for one in resolver.suggest("jal", limit=50)
        if one.geoname_id == 1436599
    )
    connection = sqlite3.connect(f"file:{FIXTURE_DB}?mode=ro", uri=True)
    try:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT original FROM place_names WHERE geoname_id = ? "
                "AND norm_name >= 'jal' AND norm_name < 'jam'",
                (candidate.geoname_id,),
            )
        ]
    finally:
        connection.close()

    assert candidate.matched_name == min(names)
    assert candidate.matched_name != candidate.name


@pytest.mark.parametrize("text", [None, 17, b"jal", ["jal"]])
def test_suggest_refuses_a_non_string_text(resolver, text):
    with pytest.raises(TypeError):
        resolver.suggest(text, limit=10)


@pytest.mark.parametrize("limit", [True, False, 1.0, "10", None])
def test_suggest_refuses_a_bool_or_non_int_limit(resolver, limit):
    """A bool is an int in Python; ``limit=True`` must not mean one."""
    with pytest.raises(TypeError):
        resolver.suggest("jal", limit=limit)


@pytest.mark.parametrize("limit", [0, -1, 51, 1000])
def test_suggest_refuses_a_limit_outside_one_to_fifty(resolver, limit):
    with pytest.raises(ValueError):
        resolver.suggest("jal", limit=limit)


def test_suggest_requires_the_limit_by_keyword(resolver):
    with pytest.raises(TypeError):
        resolver.suggest("jal", 10)


# --- Layer 15 C1: the safe upper bound -------------------------------------


@pytest.mark.parametrize(
    "prefix, expected",
    [
        ("jal", "jam"),
        ("ab", "ac"),
        # U+D7FF increments into the surrogate block, which cannot be encoded
        # for SQLite, so it becomes U+E000.
        ("ab\ud7ff", "ab\ue000"),
        # Trailing U+10FFFF cannot be incremented and is dropped first.
        ("ab\U0010ffff", "ac"),
        ("ab\U0010ffff\U0010ffff", "ac"),
        # Nothing remains: the scan has no upper bound, which is still correct.
        ("\U0010ffff", None),
        ("\U0010ffff\U0010ffff", None),
    ],
)
def test_the_range_upper_bound_is_safe_for_every_code_point(prefix, expected):
    from vedic_chart.location.offline.search import prefix_upper_bound

    assert prefix_upper_bound(prefix) == expected


@pytest.mark.parametrize(
    "prefix",
    ["ab\U0010ffff", "\U0010ffff\U0010ffff", "ab\ud7ff", "\ud7ff\ud7ff"],
)
def test_an_extreme_prefix_queries_without_raising(resolver, prefix):
    """No exception, and no match: the fixture holds no such name."""
    assert resolver.suggest(prefix, limit=10) == []


def test_the_upper_bound_still_bounds_the_scan(resolver):
    """Every listed name really does start with the normalised prefix."""
    for candidate in resolver.suggest("jal", limit=50):
        names = {
            candidate.name.casefold(),
            candidate.matched_name.casefold(),
        }
        assert any(name.startswith("jal") for name in names) or any(
            name.startswith("jāl") for name in names
        )


# --- Layer 15 C1: record() -------------------------------------------------


def test_record_returns_the_same_place_resolution_returns(resolver):
    by_name, _decision = resolver.resolve_with_details("Jalandhar")
    by_id, candidate = resolver.record(JALANDHAR_ID)

    assert by_id == by_name
    assert by_id.canonical_name == "Jalandhar, Punjab, India"
    assert by_id.latitude == by_name.latitude
    assert by_id.longitude == by_name.longitude
    assert by_id.timezone_id == by_name.timezone_id == "Asia/Kolkata"
    assert candidate.geoname_id == JALANDHAR_ID


def test_record_returns_a_validated_location_and_its_candidate(resolver):
    location, candidate = resolver.record(JALANDHAR_ID)

    assert isinstance(location, ResolvedLocation)
    assert isinstance(candidate, PlaceCandidate)
    assert candidate.name == "Jalandhar"
    assert candidate.admin1_name == "Punjab"
    assert candidate.country_name == "India"
    assert candidate.population == 868929
    assert candidate.feature_code == "PPL"
    assert candidate.matched_name == "Jalandhar"
    # The zone *is* resolved for the record actually used (section 5.3).
    assert candidate.timezone_id == "Asia/Kolkata"
    assert OfflineLocationResolver.candidate_label(candidate) == (
        location.canonical_name
    )


def test_record_raises_place_not_found_for_an_absent_id(resolver):
    with pytest.raises(PlaceNotFoundError):
        resolver.record(999999999)


@pytest.mark.parametrize("geoname_id", [True, False, 1.0, "1268782", None])
def test_record_refuses_a_bool_or_non_int_id(resolver, geoname_id):
    with pytest.raises(TypeError):
        resolver.record(geoname_id)


@pytest.mark.parametrize("geoname_id", [0, -1])
def test_record_refuses_an_id_below_one(resolver, geoname_id):
    with pytest.raises(ValueError):
        resolver.record(geoname_id)


def test_the_label_helper_is_the_canonical_name_rule(resolver):
    """The viewer builds labels with this, never with a private name."""
    location, candidate = resolver.record(JALANDHAR_ID)

    assert OfflineLocationResolver.candidate_label(candidate) == (
        "Jalandhar, Punjab, India"
    )
    assert (
        OfflineLocationResolver.candidate_label(candidate)
        == location.canonical_name
    )
    partial = PlaceCandidate(
        geoname_id=1,
        name="Somewhere",
        admin1_name=None,
        country_name="Testland",
        latitude=0.0,
        longitude=0.0,
        timezone_id=None,
        population=0,
        feature_code="PPL",
        score=0.0,
        matched_name="Somewhere",
    )
    assert OfflineLocationResolver.candidate_label(partial) == (
        "Somewhere, Testland"
    )


def test_the_existing_api_is_untouched_by_the_additions(resolver):
    """C1 is additive: ranking, dominance and the ambiguity policy stand."""
    assert resolver.resolve("Jalandhar").canonical_name == (
        "Jalandhar, Punjab, India"
    )
    with pytest.raises(AmbiguousPlaceError):
        resolver.resolve("Hyderabad")
    assert len(resolver.search("Springfield")) == 5


# --- Layer 15 C1: the displayed suggestion label ---------------------------


def candidate_named(name: str, matched_name: str) -> PlaceCandidate:
    """One candidate, built directly, to state a rule rather than a row."""
    return PlaceCandidate(
        geoname_id=1,
        name=name,
        admin1_name="Punjab",
        country_name="India",
        latitude=31.0,
        longitude=75.0,
        timezone_id=None,
        population=100,
        feature_code="PPL",
        score=0.0,
        matched_name=matched_name,
    )


def test_the_display_label_is_the_plain_label_for_a_primary_name_match(
    resolver
):
    candidate = next(
        one
        for one in resolver.suggest("jal", limit=50)
        if one.geoname_id == JALANDHAR_ID
    )

    assert candidate.matched_name == candidate.name
    assert OfflineLocationResolver.suggestion_label(candidate) == (
        "Jalandhar, Punjab, India"
    )
    assert OfflineLocationResolver.suggestion_label(candidate) == (
        OfflineLocationResolver.candidate_label(candidate)
    )


def test_the_display_label_names_the_alias_that_matched(resolver):
    """The fixture's own alias case: a place found under another name."""
    hamlet = next(
        one
        for one in resolver.suggest("london", limit=50)
        if one.geoname_id == 10304286
    )

    assert hamlet.name == "Ban Sarkāri"
    assert hamlet.matched_name == "London"
    assert OfflineLocationResolver.suggestion_label(hamlet) == (
        "Ban Sarkāri, Punjab, India (matched: London)"
    )
    # The label a selection sends back is the plain one, never this.
    assert OfflineLocationResolver.candidate_label(hamlet) == (
        "Ban Sarkāri, Punjab, India"
    )


def test_every_fixture_suggestion_agrees_with_the_rule(resolver):
    for candidate in resolver.suggest("jal", limit=50):
        label = OfflineLocationResolver.candidate_label(candidate)
        display = OfflineLocationResolver.suggestion_label(candidate)
        if candidate.matched_name == candidate.name:
            assert display == label
        else:
            assert display.startswith(label + " (matched: ")
            assert display.endswith(f"{candidate.matched_name})")


@pytest.mark.parametrize(
    "name, matched_name",
    [
        ("Jalandhar", "Jalandhar"),
        # Layer 2 owns what "the same name" is: marks are dropped, case is
        # folded, whitespace is collapsed, edge punctuation is stripped.
        ("Jalandhar", "Jālandhar"),
        ("Jālandhar", "Jalandhar"),
        ("Jalandhar", "JALANDHAR"),
        ("Jalandhar", "  Jalandhar  "),
        ("Jalandhar", "Jalandhar."),
    ],
)
def test_a_name_that_only_looks_different_adds_nothing(name, matched_name):
    candidate = candidate_named(name, matched_name)

    assert OfflineLocationResolver.suggestion_label(candidate) == (
        OfflineLocationResolver.candidate_label(candidate)
    )
    assert "(matched:" not in OfflineLocationResolver.suggestion_label(
        candidate
    )


@pytest.mark.parametrize(
    "matched_name", ["Jullundur", "जालंधर", "Jalandhar Cantonment"]
)
def test_a_genuinely_different_name_is_named(matched_name):
    candidate = candidate_named("Jalandhar", matched_name)

    assert OfflineLocationResolver.suggestion_label(candidate) == (
        f"Jalandhar, Punjab, India (matched: {matched_name})"
    )


def test_the_display_label_is_built_where_normalisation_lives():
    """The rule is Layer 2's ``normalize_name``, not a second definition."""
    from vedic_chart.location.offline.normalize import normalize_name

    for name, matched_name in (
        ("Jalandhar", "Jālandhar"),
        ("Ban Sarkāri", "London"),
        ("Delhi", "Dilli"),
    ):
        candidate = candidate_named(name, matched_name)
        same = normalize_name(matched_name) == normalize_name(name)
        display = OfflineLocationResolver.suggestion_label(candidate)

        assert ("(matched:" in display) is not same
