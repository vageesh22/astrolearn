"""Tests for Layer 11's Python entry point (specification section 10.A).

Self-contained: every case runs against the committed fixture geodata database
and the committed ``ephe/`` directory, so nothing here needs the 150 MB
production database and nothing is skipped for its absence. Where a real
permission change would be unreliable -- root, CI sandboxes, Windows -- the
failure is *injected* on the exact call rather than produced with ``chmod``.

The claims under test are the ones the specification makes: the reference chart
reproduces the Layer 10 golden byte for byte, the birthplace is resolved exactly
once and the chart provably carries that resolution, every existing typed error
still reaches the caller with its own type, and both resources are closed on
every path -- including the failure paths.
"""

import builtins
import dataclasses
import os
import pathlib
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from render_helpers import EPHE_DIR, FIXTURE_DB, GOLDEN_DIR
from vedic_chart.app import pipeline as pipeline_module
from vedic_chart.app.pipeline import (
    EPHEMERIS_FILE_SIZES,
    ChartAndDashaResult,
    ChartConfig,
    ChartResult,
    ConfigurationError,
    LocatedChartAndDashaResult,
    _PreresolvedResolver,
    render_birth_chart,
    render_chart_and_dasha,
    render_chart_and_dasha_at,
)
from vedic_chart.dasha import YearConvention
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.model import (
    AmbiguousPlaceError,
    PlaceNotFoundError,
    ResolvedLocation,
)
from vedic_chart.location.offline.db import GeodataError
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.location.offline.search import RankingConfig, ResolutionDecision
from vedic_chart.render import NorthIndianOptions
from vedic_chart.representation.d1 import build_d1_chart

EPHE_PATH = Path(EPHE_DIR)


# --- shared fixtures -------------------------------------------------------


@pytest.fixture
def config():
    return ChartConfig(geodata_path=FIXTURE_DB, ephemeris_path=EPHE_PATH)


@pytest.fixture
def jalandhar_request():
    return BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query="Jalandhar"
    )


def golden_bytes(name: str) -> bytes:
    return (GOLDEN_DIR / f"{name}.svg").read_bytes()


def linked_ephemeris(directory: Path) -> Path:
    """A directory of symlinks to the real ``.se1`` files.

    Symlinks keep the fixture cheap while still presenting three regular files
    of exactly the recorded sizes to ``stat``.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name, _size in EPHEMERIS_FILE_SIZES:
        os.symlink(EPHE_PATH / name, directory / name)
    return directory


@contextmanager
def _null_session(_path):
    yield


def session_spy(monkeypatch, *, real: bool = True) -> list[str]:
    """Record every entry and exit of the pipeline's ephemeris session."""
    events: list[str] = []
    original = pipeline_module.ephemeris_session

    @contextmanager
    def recorder(path):
        events.append(f"enter:{path}")
        inner = original(path) if real else _null_session(path)
        with inner:
            try:
                yield
            finally:
                events.append("exit")

    monkeypatch.setattr(pipeline_module, "ephemeris_session", recorder)
    return events


def close_spy(monkeypatch) -> list[int]:
    closes: list[int] = []
    original = OfflineLocationResolver.close

    def recorder(self):
        closes.append(id(self))
        original(self)

    monkeypatch.setattr(OfflineLocationResolver, "close", recorder)
    return closes


# --- the reference round trip ---------------------------------------------


def test_the_jalandhar_reference_renders_the_golden_document(
    config, jalandhar_request
):
    result = render_birth_chart(jalandhar_request, config)

    assert isinstance(result, ChartResult)
    assert result.svg.encode("utf-8") == golden_bytes(
        "jalandhar_nocaption_degrees"
    )


@pytest.mark.parametrize(
    "options, golden",
    [
        (NorthIndianOptions(), "jalandhar_nocaption_degrees"),
        (NorthIndianOptions(caption=True), "jalandhar_caption_degrees"),
        (
            NorthIndianOptions(show_degrees=False),
            "jalandhar_nocaption_nodegrees",
        ),
        (
            NorthIndianOptions(caption=True, show_degrees=False),
            "jalandhar_caption_nodegrees",
        ),
    ],
)
def test_every_option_combination_matches_its_golden(
    config, jalandhar_request, options, golden
):
    result = render_birth_chart(jalandhar_request, config, options)

    assert result.svg.encode("utf-8") == golden_bytes(golden)


def test_the_chart_equals_the_one_layer_8_builds(config, jalandhar_request):
    from render_helpers import jalandhar_d1

    result = render_birth_chart(jalandhar_request, config)

    assert result.chart == jalandhar_d1().source


def test_the_result_carries_its_parts_by_identity(config, jalandhar_request):
    result = render_birth_chart(jalandhar_request, config)

    assert result.request is jalandhar_request
    assert result.d1.source is result.chart
    assert result.chart.request is jalandhar_request
    assert result.resolution.chosen.name == "Jalandhar"
    assert result.chart.location.canonical_name == "Jalandhar, Punjab, India"


def test_the_d1_is_the_one_the_svg_was_drawn_from(config, jalandhar_request):
    from vedic_chart.render import render_north_indian_svg

    result = render_birth_chart(jalandhar_request, config)

    assert render_north_indian_svg(result.d1, NorthIndianOptions()) == result.svg
    assert build_d1_chart(result.chart) == result.d1


# --- exactly one resolution ------------------------------------------------


def test_the_place_is_resolved_exactly_once(
    monkeypatch, config, jalandhar_request
):
    queries = []
    returned = {}
    original = OfflineLocationResolver.resolve_with_details

    def counting(self, place_query):
        queries.append(place_query)
        location, decision = original(self, place_query)
        returned["location"] = location
        return location, decision

    def forbidden(self, place_query):  # pragma: no cover - must never run
        raise AssertionError(
            "resolve() was called; the pipeline must resolve once, with details"
        )

    monkeypatch.setattr(
        OfflineLocationResolver, "resolve_with_details", counting
    )
    monkeypatch.setattr(OfflineLocationResolver, "resolve", forbidden)

    result = render_birth_chart(jalandhar_request, config)

    assert queries == ["Jalandhar"]
    assert result.chart.location is returned["location"]
    assert result.resolution.query == "Jalandhar"


def test_the_adapter_refuses_a_different_query():
    location = ResolvedLocation("Somewhere, Testland", 0.0, 0.0, "UTC")
    adapter = _PreresolvedResolver("Jalandhar", location)

    assert adapter.resolve("Jalandhar") is location
    with pytest.raises(RuntimeError, match="different place query"):
        adapter.resolve("London")


def test_a_chart_carrying_another_location_is_refused(
    monkeypatch, config, jalandhar_request
):
    """The identity assertion, forced by a chart built somewhere else."""
    original = pipeline_module.assemble_chart

    def swapping(request, resolver):
        chart = original(request, resolver)
        return replace(chart, location=replace(chart.location))

    monkeypatch.setattr(pipeline_module, "assemble_chart", swapping)

    with pytest.raises(RuntimeError, match="single-resolution guarantee"):
        render_birth_chart(jalandhar_request, config)


# --- places ----------------------------------------------------------------


@pytest.mark.parametrize("place", ["Springfield", "Hyderabad"])
def test_an_ambiguous_place_is_refused_before_the_ephemeris_opens(
    monkeypatch, config, place
):
    events = session_spy(monkeypatch)
    request = BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query=place
    )

    with pytest.raises(AmbiguousPlaceError) as caught:
        render_birth_chart(request, config)

    assert len(caught.value.candidates) >= 2
    assert events == []


def test_a_qualified_place_resolves(config):
    request = BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query="Hyderabad, India"
    )

    result = render_birth_chart(request, config)

    assert result.resolution.chosen.name == "Hyderabad"
    assert "India" in result.chart.location.canonical_name


def test_an_unknown_place_is_not_found(monkeypatch, config):
    events = session_spy(monkeypatch)
    request = BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query="Xyzzyville"
    )

    with pytest.raises(PlaceNotFoundError):
        render_birth_chart(request, config)

    assert events == []


# --- daylight saving -------------------------------------------------------


def test_a_nonexistent_london_wall_time_is_refused(config):
    from vedic_chart.time.local_time import NonexistentLocalTimeError

    request = BirthChartRequest.from_components(
        2023, 3, 26, 1, 30, place_query="London"
    )

    with pytest.raises(NonexistentLocalTimeError):
        render_birth_chart(request, config)


def test_an_ambiguous_london_wall_time_is_refused(config):
    from vedic_chart.time.local_time import AmbiguousLocalTimeError

    request = BirthChartRequest.from_components(
        2023, 10, 29, 1, 30, place_query="London"
    )

    with pytest.raises(AmbiguousLocalTimeError):
        render_birth_chart(request, config)


def test_british_summer_time_becomes_the_right_instant(config):
    request = BirthChartRequest.from_components(
        2023, 7, 1, 12, 0, place_query="London"
    )

    result = render_birth_chart(request, config)

    assert result.chart.moment_utc.utcoffset().total_seconds() == 0
    assert result.chart.moment_utc.hour == 11
    assert result.chart.location.timezone_id == "Europe/London"


# --- the engine's coverage boundary, not this layer's ----------------------


@pytest.mark.parametrize(
    "year, month, day", [(1800, 1, 1), (2399, 12, 31)]
)
def test_births_inside_the_files_coverage_render(config, year, month, day):
    request = BirthChartRequest.from_components(
        year, month, day, 12, 0, place_query="Jalandhar"
    )

    result = render_birth_chart(request, config)

    assert result.svg.startswith("<svg")


@pytest.mark.parametrize("year", [1750, 2450])
def test_a_birth_outside_coverage_raises_the_engines_own_runtime_error(
    monkeypatch, config, year
):
    """No guard is added here: the engine's bare RuntimeError is the contract."""
    events = session_spy(monkeypatch)
    closes = close_spy(monkeypatch)
    request = BirthChartRequest.from_components(
        year, 6, 1, 12, 0, place_query="Jalandhar"
    )

    with pytest.raises(RuntimeError) as caught:
        render_birth_chart(request, config)

    assert type(caught.value) is RuntimeError
    assert not isinstance(caught.value, (ValueError, LookupError, OSError))
    assert len(closes) == 1
    assert events[0].startswith("enter:") and events[-1] == "exit"


# --- ChartConfig -----------------------------------------------------------


@pytest.mark.parametrize("value", [None, 123, b"x", True, 1.5, object()])
def test_a_non_path_is_refused_before_any_filesystem_access(
    monkeypatch, value
):
    def forbidden(self, *args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("Path.resolve was called for a non-path value")

    monkeypatch.setattr(pathlib.Path, "resolve", forbidden)

    with pytest.raises(ConfigurationError, match="geodata_path"):
        ChartConfig(geodata_path=value, ephemeris_path=EPHE_PATH)
    with pytest.raises(ConfigurationError, match="ephemeris_path"):
        ChartConfig(geodata_path=FIXTURE_DB, ephemeris_path=value)


def test_relative_paths_are_stored_absolute_and_survive_a_chdir(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(FIXTURE_DB.parent.parent.parent)

    config = ChartConfig(
        geodata_path="tests/fixtures/geodata_fixture.sqlite",
        ephemeris_path="ephe",
    )
    before = (config.geodata_path, config.ephemeris_path, config.ephemeris_files)

    monkeypatch.chdir(tmp_path)

    assert config.geodata_path.is_absolute()
    assert config.ephemeris_path.is_absolute()
    assert (
        config.geodata_path,
        config.ephemeris_path,
        config.ephemeris_files,
    ) == before
    assert config.geodata_path == FIXTURE_DB.resolve()


def test_a_tilde_is_expanded(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    os.symlink(FIXTURE_DB, home / "geo.sqlite")
    linked_ephemeris(home / "ephe")

    config = ChartConfig(
        geodata_path="~/geo.sqlite", ephemeris_path="~/ephe"
    )

    assert config.geodata_path == (home / "geo.sqlite").resolve()
    assert config.ephemeris_path == (home / "ephe").resolve()


def test_the_derived_file_list_cannot_be_passed_in():
    with pytest.raises(TypeError):
        ChartConfig(
            geodata_path=FIXTURE_DB,
            ephemeris_path=EPHE_PATH,
            ephemeris_files=(),
        )


def test_the_derived_file_list_names_the_three_frozen_files():
    config = ChartConfig(geodata_path=FIXTURE_DB, ephemeris_path=EPHE_PATH)

    assert [path.name for path in config.ephemeris_files] == [
        name for name, _size in EPHEMERIS_FILE_SIZES
    ]
    assert all(path.is_absolute() for path in config.ephemeris_files)


def test_a_missing_geodata_file_is_a_configuration_error(tmp_path):
    with pytest.raises(ConfigurationError, match="geodata_path"):
        ChartConfig(
            geodata_path=tmp_path / "absent.sqlite", ephemeris_path=EPHE_PATH
        )


def test_a_geodata_path_that_is_a_directory_is_refused(tmp_path):
    with pytest.raises(ConfigurationError, match="regular file"):
        ChartConfig(geodata_path=tmp_path, ephemeris_path=EPHE_PATH)


def test_a_database_without_the_required_tables_fails_in_the_resolver(
    tmp_path, jalandhar_request
):
    """The schema check belongs to db.connect, not to ChartConfig."""
    broken = tmp_path / "broken.sqlite"
    connection = sqlite3.connect(broken)
    connection.execute("CREATE TABLE places (geoname_id INTEGER)")
    connection.commit()
    connection.close()

    config = ChartConfig(geodata_path=broken, ephemeris_path=EPHE_PATH)

    with pytest.raises(GeodataError, match="missing tables"):
        render_birth_chart(jalandhar_request, config)


def test_a_missing_ephemeris_directory_is_a_configuration_error(tmp_path):
    with pytest.raises(ConfigurationError, match="ephemeris_path"):
        ChartConfig(
            geodata_path=FIXTURE_DB, ephemeris_path=tmp_path / "absent"
        )


def test_an_ephemeris_path_that_is_a_file_is_refused():
    with pytest.raises(ConfigurationError, match="must be a directory"):
        ChartConfig(geodata_path=FIXTURE_DB, ephemeris_path=FIXTURE_DB)


def test_a_missing_ephemeris_file_is_named_with_its_expected_size(tmp_path):
    directory = linked_ephemeris(tmp_path / "ephe")
    (directory / "semo_18.se1").unlink()

    with pytest.raises(ConfigurationError, match="semo_18.se1"):
        ChartConfig(geodata_path=FIXTURE_DB, ephemeris_path=directory)


def test_an_ephemeris_file_of_the_wrong_size_is_refused(tmp_path):
    directory = linked_ephemeris(tmp_path / "ephe")
    (directory / "seas_18.se1").unlink()
    (directory / "seas_18.se1").write_bytes(b"not the frozen file")

    with pytest.raises(ConfigurationError) as caught:
        ChartConfig(geodata_path=FIXTURE_DB, ephemeris_path=directory)

    assert "223004" in str(caught.value)


def test_an_ephemeris_entry_that_is_a_directory_is_refused(tmp_path):
    directory = tmp_path / "ephe"
    directory.mkdir()
    (directory / "sepl_18.se1").mkdir()
    for name, _size in EPHEMERIS_FILE_SIZES[1:]:
        os.symlink(EPHE_PATH / name, directory / name)

    with pytest.raises(ConfigurationError, match="not a regular file"):
        ChartConfig(geodata_path=FIXTURE_DB, ephemeris_path=directory)


def test_extra_files_in_the_ephemeris_directory_are_ignored(tmp_path):
    directory = linked_ephemeris(tmp_path / "ephe")
    (directory / "LICENSE.txt").write_text("notice")
    (directory / "sepl_24.se1").write_bytes(b"another range")

    config = ChartConfig(geodata_path=FIXTURE_DB, ephemeris_path=directory)

    assert len(config.ephemeris_files) == 3


@pytest.mark.parametrize("target", ["geodata_fixture.sqlite", "semo_18.se1"])
def test_an_unreadable_resource_is_a_configuration_error(monkeypatch, target):
    """Injected, never chmod: the suite must not depend on its privileges."""
    real_open = builtins.open

    def refusing(file, *args, **kwargs):
        if str(file).endswith(target):
            raise PermissionError(13, "Permission denied")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", refusing)

    with pytest.raises(ConfigurationError) as caught:
        ChartConfig(geodata_path=FIXTURE_DB, ephemeris_path=EPHE_PATH)

    assert "Permission denied" in str(caught.value)


def test_an_os_error_from_resolve_becomes_a_configuration_error(monkeypatch):
    real_resolve = pathlib.Path.resolve

    def refusing(self, *args, **kwargs):
        if self.name == "ephe":
            raise PermissionError(13, "Permission denied")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "resolve", refusing)

    with pytest.raises(ConfigurationError) as caught:
        ChartConfig(geodata_path=FIXTURE_DB, ephemeris_path=EPHE_PATH)

    assert "Permission denied" in str(caught.value)
    assert not isinstance(caught.value, OSError)


@pytest.mark.parametrize("value", ["strict", 3, object()])
def test_a_bad_ranking_config_is_refused(value):
    with pytest.raises(ConfigurationError, match="ranking_config"):
        ChartConfig(
            geodata_path=FIXTURE_DB,
            ephemeris_path=EPHE_PATH,
            ranking_config=value,
        )


def test_a_ranking_config_is_forwarded_to_the_resolver(
    monkeypatch, jalandhar_request
):
    ranking = RankingConfig(dominance_population_ratio=2.0)
    seen = []
    original = OfflineLocationResolver.__init__

    def recorder(self, db_path, ranking_config=None):
        seen.append(ranking_config)
        original(self, db_path, ranking_config)

    monkeypatch.setattr(OfflineLocationResolver, "__init__", recorder)
    config = ChartConfig(
        geodata_path=FIXTURE_DB,
        ephemeris_path=EPHE_PATH,
        ranking_config=ranking,
    )

    render_birth_chart(jalandhar_request, config)

    assert seen == [ranking]


# --- argument kinds and option pass-through --------------------------------


def test_a_non_request_is_refused(config):
    with pytest.raises(ValueError, match="BirthChartRequest"):
        render_birth_chart("1995-03-21", config)


def test_a_non_config_is_refused(jalandhar_request):
    with pytest.raises(ValueError, match="ChartConfig"):
        render_birth_chart(jalandhar_request, "data/geodata.sqlite")


def test_non_renderer_options_are_refused(config, jalandhar_request):
    with pytest.raises(ValueError, match="NorthIndianOptions"):
        render_birth_chart(jalandhar_request, config, {"caption": True})


def test_the_id_prefix_reaches_the_document(config, jalandhar_request):
    result = render_birth_chart(
        jalandhar_request, config, NorthIndianOptions(id_prefix="chart-7")
    )

    assert "chart-7-title" in result.svg


def test_the_width_reaches_the_document(config, jalandhar_request):
    result = render_birth_chart(
        jalandhar_request, config, NorthIndianOptions(width=800)
    )

    assert 'width="800"' in result.svg


# --- lifecycle -------------------------------------------------------------


def test_both_resources_are_opened_once_and_closed(
    monkeypatch, config, jalandhar_request
):
    events = session_spy(monkeypatch)
    closes = close_spy(monkeypatch)

    render_birth_chart(jalandhar_request, config)

    assert closes and len(closes) == 1
    assert events == [f"enter:{config.ephemeris_path}", "exit"]


def test_the_geodata_connection_is_closed_before_the_ephemeris_opens(
    monkeypatch, config, jalandhar_request
):
    order = []
    original_close = OfflineLocationResolver.close
    original_session = pipeline_module.ephemeris_session

    def recording_close(self):
        order.append("close")
        original_close(self)

    @contextmanager
    def recording_session(path):
        order.append("open ephemeris")
        with original_session(path):
            yield

    monkeypatch.setattr(OfflineLocationResolver, "close", recording_close)
    monkeypatch.setattr(pipeline_module, "ephemeris_session", recording_session)

    render_birth_chart(jalandhar_request, config)

    assert order == ["close", "open ephemeris"]


def test_the_pipeline_writes_nothing(tmp_path, monkeypatch, config):
    """A successful run leaves no file behind in the working directory."""
    monkeypatch.chdir(tmp_path)
    request = BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query="Jalandhar"
    )

    render_birth_chart(request, config)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "place, year, expected",
    [
        ("Springfield", 1995, AmbiguousPlaceError),
        ("Xyzzyville", 1995, PlaceNotFoundError),
    ],
)
def test_a_failure_before_assembly_still_closes_the_geodata(
    monkeypatch, config, place, year, expected
):
    events = session_spy(monkeypatch)
    closes = close_spy(monkeypatch)
    request = BirthChartRequest.from_components(
        year, 3, 21, 6, 45, place_query=place
    )

    with pytest.raises(expected):
        render_birth_chart(request, config)

    assert len(closes) == 1
    assert events == []


def test_a_failure_during_assembly_exits_the_session(monkeypatch, config):
    from vedic_chart.time.local_time import NonexistentLocalTimeError

    events = session_spy(monkeypatch)
    closes = close_spy(monkeypatch)
    request = BirthChartRequest.from_components(
        2023, 3, 26, 1, 30, place_query="London"
    )

    with pytest.raises(NonexistentLocalTimeError):
        render_birth_chart(request, config)

    assert len(closes) == 1
    assert events == [f"enter:{config.ephemeris_path}", "exit"]


def test_a_failure_in_the_renderer_leaves_nothing_open(
    monkeypatch, config, jalandhar_request
):
    events = session_spy(monkeypatch)
    closes = close_spy(monkeypatch)

    def exploding(d1, options):
        raise ValueError("injected renderer failure")

    monkeypatch.setattr(pipeline_module, "render_north_indian_svg", exploding)

    with pytest.raises(ValueError, match="injected renderer failure"):
        render_birth_chart(jalandhar_request, config)

    assert len(closes) == 1
    assert events == [f"enter:{config.ephemeris_path}", "exit"]


# --- Layer 15 C2: the exact-location entry point ---------------------------
#
# Additive: every claim above still holds, and the two assertions at the end of
# this section are what keep ``ChartAndDashaResult`` exactly as it was.


@pytest.fixture
def jalandhar_record():
    """The Jalandhar record of the fixture database, by primary key."""
    with OfflineLocationResolver(FIXTURE_DB) as offline:
        return offline.record(JALANDHAR_GEONAME_ID)


JALANDHAR_GEONAME_ID = 1268782


def located_request(location) -> BirthChartRequest:
    """The reference birth, with the record's own label as its place query."""
    return BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query=location.canonical_name
    )


def test_the_exact_location_path_equals_the_query_path(
    config, jalandhar_request, jalandhar_record
):
    """The same SVG, byte for byte, and the same daśā rows.

    The caption is off, as it is for every viewer render, so the two
    documents are comparable even though the two requests carry different
    (and equally informational) place queries.
    """
    from vedic_chart.dasha import dasha_rows

    location, _candidate = jalandhar_record
    options = NorthIndianOptions(caption=False)
    year = YearConvention.FIXED_365_256363

    by_query = render_chart_and_dasha(
        jalandhar_request, config, options, year
    )
    by_record = render_chart_and_dasha_at(
        located_request(location), location, config, options, year
    )

    assert by_record.svg.encode("utf-8") == by_query.svg.encode("utf-8")
    assert dasha_rows(by_record.timeline, depth=3) == dasha_rows(
        by_query.timeline, depth=3
    )
    assert by_record.chart.moment_utc == by_query.chart.moment_utc
    assert by_record.timeline.balance_years == by_query.timeline.balance_years


def test_the_located_result_carries_its_parts_by_identity(
    config, jalandhar_record
):
    location, _candidate = jalandhar_record
    request = located_request(location)

    result = render_chart_and_dasha_at(
        location=location,
        request=request,
        config=config,
        options=NorthIndianOptions(),
        year=YearConvention.FIXED_365_256363,
    )

    assert isinstance(result, LocatedChartAndDashaResult)
    assert result.request is request
    assert result.location is location
    assert result.location is result.chart.location
    assert result.d1.source is result.chart
    assert result.chart.request is request


def test_the_located_result_has_no_resolution_field():
    """Section 5.4: no decision exists on this path, so none is invented."""
    names = [field.name for field in dataclasses.fields(
        LocatedChartAndDashaResult
    )]

    assert "resolution" not in names
    assert names == [
        "request",
        "location",
        "chart",
        "d1",
        "svg",
        "timeline",
    ]
    assert not hasattr(LocatedChartAndDashaResult, "resolution")


def test_the_existing_result_keeps_its_non_optional_resolution():
    """C2 is additive: ``ChartAndDashaResult`` is exactly what it was."""
    field = ChartAndDashaResult.__dataclass_fields__["resolution"]

    assert field.type is ResolutionDecision
    assert field.default is dataclasses.MISSING
    assert field.default_factory is dataclasses.MISSING
    assert [one.name for one in dataclasses.fields(ChartAndDashaResult)] == [
        "request",
        "chart",
        "resolution",
        "d1",
        "svg",
        "timeline",
    ]


def test_the_query_path_still_returns_a_resolution_decision(
    config, jalandhar_request
):
    result = render_chart_and_dasha(
        jalandhar_request,
        config,
        NorthIndianOptions(),
        YearConvention.FIXED_365_256363,
    )

    assert isinstance(result.resolution, ResolutionDecision)
    assert result.resolution.chosen.geoname_id == JALANDHAR_GEONAME_ID


def test_the_geodata_database_is_never_opened_on_this_path(
    monkeypatch, config, jalandhar_record
):
    """Not "closed again": never constructed at all."""
    location, _candidate = jalandhar_record

    def forbidden(self, *args, **kwargs):
        raise AssertionError(
            "the exact-location path constructed an OfflineLocationResolver"
        )

    monkeypatch.setattr(OfflineLocationResolver, "__init__", forbidden)

    result = render_chart_and_dasha_at(
        located_request(location),
        location,
        config,
        NorthIndianOptions(),
        YearConvention.FIXED_365_256363,
    )

    assert result.svg.startswith("<svg")


def test_only_the_ephemeris_session_is_opened_once(
    monkeypatch, config, jalandhar_record
):
    location, _candidate = jalandhar_record
    events = session_spy(monkeypatch)
    closes = close_spy(monkeypatch)

    render_chart_and_dasha_at(
        located_request(location),
        location,
        config,
        NorthIndianOptions(),
        YearConvention.FIXED_365_256363,
    )

    assert events == [f"enter:{config.ephemeris_path}", "exit"]
    assert closes == []


@pytest.mark.parametrize(
    "location",
    ["Jalandhar", None, 3, {"canonical_name": "Jalandhar"}, object()],
)
def test_a_non_resolved_location_is_refused_before_anything_opens(
    monkeypatch, config, jalandhar_request, location
):
    events = session_spy(monkeypatch)

    def forbidden(self, *args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("a resource was opened for an invalid argument")

    monkeypatch.setattr(OfflineLocationResolver, "__init__", forbidden)

    with pytest.raises(ValueError, match="ResolvedLocation"):
        render_chart_and_dasha_at(
            jalandhar_request,
            location,
            config,
            NorthIndianOptions(),
            YearConvention.FIXED_365_256363,
        )

    assert events == []


def test_the_argument_order_is_request_location_config_options_year(
    config, jalandhar_record
):
    """Each kind is refused before any resource is opened, in this order."""
    location, _candidate = jalandhar_record
    request = located_request(location)
    options = NorthIndianOptions()
    year = YearConvention.FIXED_365_256363

    with pytest.raises(ValueError, match="BirthChartRequest"):
        render_chart_and_dasha_at("1995-03-21", location, config, options, year)
    with pytest.raises(ValueError, match="ResolvedLocation"):
        render_chart_and_dasha_at(request, "Jalandhar", config, options, year)
    with pytest.raises(ValueError, match="ChartConfig"):
        render_chart_and_dasha_at(request, location, "data", options, year)
    with pytest.raises(ValueError, match="NorthIndianOptions"):
        render_chart_and_dasha_at(request, location, config, {}, year)
    with pytest.raises(TypeError, match="YearConvention"):
        render_chart_and_dasha_at(request, location, config, options, "365.25")


def test_a_location_the_chart_does_not_carry_is_refused(
    monkeypatch, config, jalandhar_record
):
    """The identity assertion of this path, forced by a swapped location."""
    location, _candidate = jalandhar_record
    original = pipeline_module.assemble_chart

    def swapping(request, resolver):
        chart = original(request, resolver)
        return replace(chart, location=replace(chart.location))

    monkeypatch.setattr(pipeline_module, "assemble_chart", swapping)

    with pytest.raises(RuntimeError, match="exact-location guarantee"):
        render_chart_and_dasha_at(
            located_request(location),
            location,
            config,
            NorthIndianOptions(),
            YearConvention.FIXED_365_256363,
        )


def test_layer_three_still_validates_the_wall_time_on_this_path(config):
    """A DST-nonexistent London time is refused, from an exact record too."""
    from vedic_chart.time.local_time import NonexistentLocalTimeError

    with OfflineLocationResolver(FIXTURE_DB) as offline:
        location, _candidate = offline.record(2643743)

    request = BirthChartRequest.from_components(
        2023, 3, 26, 1, 30, place_query=location.canonical_name
    )

    with pytest.raises(NonexistentLocalTimeError):
        render_chart_and_dasha_at(
            request,
            location,
            config,
            NorthIndianOptions(),
            YearConvention.FIXED_365_256363,
        )


def test_a_location_that_is_not_a_geodata_record_is_accepted(config):
    """The caller chooses the location; a test fixture is a caller too."""
    location = ResolvedLocation(
        canonical_name="Somewhere, Testland",
        latitude=31.32556,
        longitude=75.57917,
        timezone_id="Asia/Kolkata",
    )
    request = BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query="Somewhere, Testland"
    )

    result = render_chart_and_dasha_at(
        request,
        location,
        config,
        NorthIndianOptions(),
        YearConvention.FIXED_365_256363,
    )

    assert result.location is location
    assert result.chart.location.canonical_name == "Somewhere, Testland"
