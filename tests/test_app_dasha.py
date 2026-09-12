"""Layer 13's public exposure: the pipeline calls and the command.

Self-contained in the Layer 11 sense: the committed fixture geodata database,
the committed ``ephe/`` directory, no production database, no network and no
clock. Every filesystem failure is *injected* on the exact call rather than
produced with ``chmod``, so no case depends on the test user's privileges.

The claims under test are the ones the specification makes, and most of them
are about things **not** happening: ``render_birth_chart`` still produces the
Layer 10 goldens byte for byte and still refuses bad renderer options before
any resource is opened; a combined call assembles **one** chart, so the drawing
and the table cannot describe two different births; the two writes happen in a
fixed order and a failure of the second never destroys the first; and a daśā
option that arrived without ``--dasha`` is a usage error rather than a silently
ignored word on the command line.
"""

import os
import subprocess
import sys
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import pytest

from render_helpers import EPHE_DIR, FIXTURE_DB, GOLDEN_DIR, REPO_ROOT
from vedic_chart.app import cli
from vedic_chart.app import pipeline as pipeline_module
from vedic_chart.app.pipeline import (
    EPHEMERIS_FILE_SIZES,
    ChartAndDashaResult,
    ChartConfig,
    DashaResult,
    compute_dasha,
    render_birth_chart,
    render_chart_and_dasha,
)
from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.chart.assemble import assemble_chart
from vedic_chart.dasha import (
    DashaRangeError,
    YearConvention,
    render_dasha_text,
    vimshottari_from_chart,
)
from vedic_chart.dasha.table import DAY_WARNING
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.location.offline.search import RankingConfig
from vedic_chart.render import NorthIndianOptions
from vedic_chart.representation.d1 import build_d1_chart

EPHE_PATH = Path(EPHE_DIR)
GOLDEN = (GOLDEN_DIR / "jalandhar_nocaption_degrees.svg").read_bytes()

OK = 0
UNEXPECTED = 1
INPUT = 2
PLACE = 3
OUTPUT = 5

SIDEREAL_YEAR = "365.256363"
JULIAN_YEAR = "365.25"
KOLKATA = "Asia/Kolkata"


# --- shared fixtures -------------------------------------------------------


@pytest.fixture
def config():
    return ChartConfig(geodata_path=FIXTURE_DB, ephemeris_path=EPHE_PATH)


@pytest.fixture
def jalandhar_request():
    return BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query="Jalandhar"
    )


_CHART_CACHE = {}


def reference_chart():
    """The Jalandhar chart, assembled without the code under test."""
    if "chart" not in _CHART_CACHE:
        request = BirthChartRequest.from_components(
            1995, 3, 21, 6, 45, place_query="Jalandhar"
        )
        with ephemeris_session(EPHE_DIR):
            with OfflineLocationResolver(FIXTURE_DB) as resolver:
                _CHART_CACHE["chart"] = assemble_chart(request, resolver)
    return _CHART_CACHE["chart"]


def expected_table(
    *,
    year=SIDEREAL_YEAR,
    depth=2,
    precision="second",
    zone=KOLKATA,
):
    """The table the command must produce, rendered independently here."""
    convention = {
        JULIAN_YEAR: YearConvention.FIXED_365_25,
        SIDEREAL_YEAR: YearConvention.FIXED_365_256363,
    }[year]
    timeline = vimshottari_from_chart(reference_chart(), convention)
    return render_dasha_text(
        timeline, zone=zone, depth=depth, precision=precision
    ).encode("utf-8")


def argv_for(
    out=None,
    *,
    dasha=None,
    dasha_year=None,
    dasha_out=None,
    place="Jalandhar",
    date="1995-03-21",
    time="06:45",
    geodata=FIXTURE_DB,
    ephemeris=EPHE_PATH,
    extra=(),
):
    """A command line; every daśā option is opt-in, as the CLI's are."""
    args = [
        "--date", date,
        "--time", time,
        "--place", place,
        "--geodata", str(geodata),
        "--ephemeris", str(ephemeris),
    ]
    if out is not None:
        args += ["--out", str(out)]
    if dasha is not None:
        args += ["--dasha"] if dasha == "" else ["--dasha", dasha]
    if dasha_year is not None:
        args += ["--dasha-year", dasha_year]
    if dasha_out is not None:
        args += ["--dasha-out", str(dasha_out)]
    return args + list(extra)


def invoke(capfdbinary, argv):
    """Run the CLI in process and return (code, stdout_broken, stdout, stderr)."""
    code, broken = cli.run(argv)
    captured = capfdbinary.readouterr()
    return code, broken, captured.out, captured.err.decode("utf-8")


def forbid_the_resolver(monkeypatch) -> None:
    """Prove a refusal happened before any database was opened."""

    def forbidden(self, *args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("the geodata database was opened")

    monkeypatch.setattr(OfflineLocationResolver, "__init__", forbidden)


def resolver_spy(monkeypatch) -> list[str]:
    queries: list[str] = []
    original = OfflineLocationResolver.resolve_with_details

    def counting(self, place_query):
        queries.append(place_query)
        return original(self, place_query)

    monkeypatch.setattr(
        OfflineLocationResolver, "resolve_with_details", counting
    )
    return queries


def session_spy(monkeypatch) -> list[str]:
    events: list[str] = []
    original = pipeline_module.ephemeris_session

    @contextmanager
    def recorder(path):
        events.append(f"enter:{path}")
        with original(path):
            try:
                yield
            finally:
                events.append("exit")

    monkeypatch.setattr(pipeline_module, "ephemeris_session", recorder)
    return events


def write_spy(monkeypatch) -> list[tuple[str, str]]:
    """Record every write the CLI performs, in order, and then perform it."""
    events: list[tuple[str, str]] = []
    direct = cli._write_direct
    replacing = cli._write_replacing
    to_stdout = cli._write_stdout

    def recording_direct(dest, data):
        events.append(("file", str(dest)))
        return direct(dest, data)

    def recording_replacing(dest, data):
        events.append(("file", str(dest)))
        return replacing(dest, data)

    def recording_stdout(data):
        events.append(("stdout", "-"))
        return to_stdout(data)

    monkeypatch.setattr(cli, "_write_direct", recording_direct)
    monkeypatch.setattr(cli, "_write_replacing", recording_replacing)
    monkeypatch.setattr(cli, "_write_stdout", recording_stdout)
    return events


# ===========================================================================
# The pipeline
# ===========================================================================


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
def test_the_split_left_render_birth_chart_byte_identical(
    config, jalandhar_request, options, golden
):
    """Layer 11's contract after the _assemble_once refactoring."""
    result = render_birth_chart(jalandhar_request, config, options)

    assert result.svg.encode("utf-8") == (
        GOLDEN_DIR / f"{golden}.svg"
    ).read_bytes()


def test_render_birth_chart_still_rejects_options_before_any_resource_use(
    monkeypatch, config, jalandhar_request
):
    forbid_the_resolver(monkeypatch)

    with pytest.raises(ValueError, match="NorthIndianOptions"):
        render_birth_chart(jalandhar_request, config, {"caption": True})


def test_the_assembly_step_returns_the_chart_and_its_decision(
    config, jalandhar_request
):
    """The shared step, called directly: it resolves, assembles and asserts."""
    chart, decision = pipeline_module._assemble_once(jalandhar_request, config)

    assert chart.request is jalandhar_request
    assert decision.query == "Jalandhar"
    assert decision.chosen.name == "Jalandhar"
    assert chart.location.canonical_name == "Jalandhar, Punjab, India"
    assert chart == reference_chart()


def test_the_sentinel_is_the_parser_default_for_the_seven_options():
    """Section 6: "explicitly supplied" has to be distinguishable.

    Without this, ``--caption`` absent and ``--caption`` present would both be
    a bool, and the daśā-only orphan rule could not be enforced at all.
    """
    defaults = {
        action.dest: action.default
        for action in cli.build_parser()._actions
    }

    for name in (
        "dasha_precision",
        "dasha_zone",
        "caption",
        "no_degrees",
        "mark_node_retrograde",
        "width",
        "id_prefix",
    ):
        assert defaults[name] is cli._UNSET, name
    assert defaults["out"] is None
    assert defaults["force"] is False


# --- compute_dasha ---------------------------------------------------------


@pytest.mark.parametrize("year", list(YearConvention), ids=lambda y: y.name)
def test_compute_dasha_equals_the_adapter_on_its_own_chart(
    config, jalandhar_request, year
):
    result = compute_dasha(jalandhar_request, config, year)

    assert isinstance(result, DashaResult)
    assert result.timeline == vimshottari_from_chart(result.chart, year)
    assert result.request is jalandhar_request
    assert result.chart.request is jalandhar_request
    assert result.resolution.chosen.name == "Jalandhar"
    assert result.timeline.year is year


def test_compute_dasha_matches_an_independently_assembled_chart(
    config, jalandhar_request
):
    year = YearConvention.FIXED_365_256363

    result = compute_dasha(jalandhar_request, config, year)

    assert result.chart == reference_chart()
    assert result.timeline == vimshottari_from_chart(reference_chart(), year)


def test_compute_dasha_opens_each_resource_once(
    monkeypatch, config, jalandhar_request
):
    queries = resolver_spy(monkeypatch)
    events = session_spy(monkeypatch)

    compute_dasha(jalandhar_request, config, YearConvention.FIXED_365_25)

    assert queries == ["Jalandhar"]
    assert events == [f"enter:{config.ephemeris_path}", "exit"]


@pytest.mark.parametrize("year", ["365.25", 365.25, None, 1, YearConvention])
def test_a_bad_year_is_refused_before_the_database_opens(
    monkeypatch, config, jalandhar_request, year
):
    forbid_the_resolver(monkeypatch)

    with pytest.raises(TypeError, match="YearConvention"):
        compute_dasha(jalandhar_request, config, year)


def test_the_year_is_required(config, jalandhar_request):
    with pytest.raises(TypeError):
        compute_dasha(jalandhar_request, config)


@pytest.mark.parametrize(
    "request_value, config_value, message",
    [
        ("1995-03-21", None, "BirthChartRequest"),
        (None, "data/geodata.sqlite", "ChartConfig"),
    ],
)
def test_compute_dasha_validates_request_and_config_first(
    monkeypatch,
    config,
    jalandhar_request,
    request_value,
    config_value,
    message,
):
    forbid_the_resolver(monkeypatch)
    given_request = jalandhar_request if request_value is None else request_value
    given_config = config if config_value is None else config_value

    with pytest.raises(ValueError, match=message):
        compute_dasha(
            given_request, given_config, YearConvention.FIXED_365_25
        )


def test_compute_dasha_renders_nothing_and_writes_nothing(
    monkeypatch, tmp_path, config
):
    monkeypatch.chdir(tmp_path)
    request = BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query="Jalandhar"
    )

    result = compute_dasha(request, config, YearConvention.FIXED_365_25)

    assert not hasattr(result, "svg")
    assert not hasattr(result, "d1")
    assert list(tmp_path.iterdir()) == []


# --- render_chart_and_dasha ------------------------------------------------


def test_the_combined_call_shares_one_chart(
    monkeypatch, config, jalandhar_request
):
    queries = resolver_spy(monkeypatch)
    events = session_spy(monkeypatch)
    year = YearConvention.FIXED_365_256363

    result = render_chart_and_dasha(
        jalandhar_request, config, NorthIndianOptions(), year
    )

    assert isinstance(result, ChartAndDashaResult)
    assert result.d1.source is result.chart
    assert result.timeline == vimshottari_from_chart(result.chart, year)
    assert build_d1_chart(result.chart) == result.d1
    assert queries == ["Jalandhar"]
    assert events == [f"enter:{config.ephemeris_path}", "exit"]


def test_the_combined_svg_equals_the_single_call(config, jalandhar_request):
    for options in (
        NorthIndianOptions(),
        NorthIndianOptions(caption=True),
        NorthIndianOptions(width=800, id_prefix="chart-7"),
    ):
        combined = render_chart_and_dasha(
            jalandhar_request, config, options, YearConvention.FIXED_365_25
        )
        alone = render_birth_chart(jalandhar_request, config, options)

        assert combined.svg == alone.svg


def test_the_combined_timeline_equals_compute_dasha(config, jalandhar_request):
    year = YearConvention.FIXED_365_25

    combined = render_chart_and_dasha(
        jalandhar_request, config, NorthIndianOptions(), year
    )
    alone = compute_dasha(jalandhar_request, config, year)

    assert combined.timeline == alone.timeline
    assert combined.chart == alone.chart


def test_the_combined_call_requires_options_and_year(
    config, jalandhar_request
):
    with pytest.raises(TypeError):
        render_chart_and_dasha(jalandhar_request, config)
    with pytest.raises(TypeError):
        render_chart_and_dasha(
            jalandhar_request, config, NorthIndianOptions()
        )


@pytest.mark.parametrize(
    "options, year, error, message",
    [
        ({"caption": True}, YearConvention.FIXED_365_25, ValueError, "NorthIndianOptions"),
        (NorthIndianOptions(), "365.25", TypeError, "YearConvention"),
    ],
)
def test_the_combined_call_validates_before_any_resource_use(
    monkeypatch, config, jalandhar_request, options, year, error, message
):
    forbid_the_resolver(monkeypatch)

    with pytest.raises(error, match=message):
        render_chart_and_dasha(jalandhar_request, config, options, year)


def test_a_ranking_config_still_reaches_the_resolver(
    monkeypatch, jalandhar_request
):
    seen = []
    original = OfflineLocationResolver.__init__

    def recorder(self, db_path, ranking_config=None):
        seen.append(ranking_config)
        original(self, db_path, ranking_config)

    monkeypatch.setattr(OfflineLocationResolver, "__init__", recorder)
    ranking = RankingConfig(dominance_population_ratio=2.0)
    config = ChartConfig(
        geodata_path=FIXTURE_DB,
        ephemeris_path=EPHE_PATH,
        ranking_config=ranking,
    )

    compute_dasha(jalandhar_request, config, YearConvention.FIXED_365_25)

    assert seen == [ranking]


# ===========================================================================
# The command: the seven output combinations
# ===========================================================================


def test_svg_to_a_file_is_unchanged(monkeypatch, capfdbinary, tmp_path):
    destination = tmp_path / "chart.svg"
    events = write_spy(monkeypatch)

    code, broken, out, err = invoke(capfdbinary, argv_for(destination))

    assert (code, broken) == (OK, False)
    assert destination.read_bytes() == GOLDEN
    assert (out, err) == (b"", "")
    assert events == [("file", str(destination))]


def test_the_dasha_goes_to_a_file(monkeypatch, capfdbinary, tmp_path):
    table = tmp_path / "dasha.txt"
    events = write_spy(monkeypatch)

    code, broken, out, err = invoke(
        capfdbinary,
        argv_for(dasha="", dasha_year=SIDEREAL_YEAR, dasha_out=table),
    )

    assert (code, broken) == (OK, False)
    assert table.read_bytes() == expected_table()
    assert (out, err) == (b"", "")
    assert events == [("file", str(table))]


def test_both_files_are_written_svg_first(monkeypatch, capfdbinary, tmp_path):
    chart = tmp_path / "chart.svg"
    table = tmp_path / "dasha.txt"
    events = write_spy(monkeypatch)

    code, broken, out, err = invoke(
        capfdbinary,
        argv_for(
            chart, dasha="", dasha_year=SIDEREAL_YEAR, dasha_out=table
        ),
    )

    assert (code, broken) == (OK, False)
    assert chart.read_bytes() == GOLDEN
    assert table.read_bytes() == expected_table()
    assert out == b""
    assert events == [("file", str(chart)), ("file", str(table))]


def test_an_svg_file_and_a_dasha_on_stdout(monkeypatch, capfdbinary, tmp_path):
    chart = tmp_path / "chart.svg"
    events = write_spy(monkeypatch)

    code, broken, out, err = invoke(
        capfdbinary,
        argv_for(chart, dasha="", dasha_year=SIDEREAL_YEAR, dasha_out="-"),
    )

    assert (code, broken) == (OK, False)
    assert chart.read_bytes() == GOLDEN
    assert out == expected_table()
    assert err == ""
    assert events == [("file", str(chart)), ("stdout", "-")]


def test_a_dasha_file_is_written_before_an_svg_on_stdout(
    monkeypatch, capfdbinary, tmp_path
):
    """Section 6's one counter-intuitive order: the file first, stdout last."""
    table = tmp_path / "dasha.txt"
    events = write_spy(monkeypatch)

    code, broken, out, err = invoke(
        capfdbinary,
        argv_for("-", dasha="md", dasha_year=JULIAN_YEAR, dasha_out=table),
    )

    assert (code, broken) == (OK, False)
    assert out == GOLDEN
    assert table.read_bytes() == expected_table(year=JULIAN_YEAR, depth=1)
    assert events == [("file", str(table)), ("stdout", "-")]


def test_svg_to_stdout_is_unchanged(monkeypatch, capfdbinary):
    events = write_spy(monkeypatch)

    code, broken, out, err = invoke(capfdbinary, argv_for("-"))

    assert (code, broken) == (OK, False)
    assert out == GOLDEN
    assert events == [("stdout", "-")]


def test_the_dasha_goes_to_stdout(monkeypatch, capfdbinary):
    events = write_spy(monkeypatch)

    code, broken, out, err = invoke(
        capfdbinary,
        argv_for(dasha="md-ad-pd", dasha_year=SIDEREAL_YEAR, dasha_out="-"),
    )

    assert (code, broken) == (OK, False)
    assert out == expected_table(depth=3)
    assert err == ""
    assert events == [("stdout", "-")]


@pytest.mark.parametrize(
    "word, depth", [("", 2), ("md", 1), ("md-ad", 2), ("md-ad-pd", 3)]
)
def test_every_depth_word_reaches_the_table(capfdbinary, tmp_path, word, depth):
    table = tmp_path / "dasha.txt"

    code, _broken, _out, _err = invoke(
        capfdbinary,
        argv_for(dasha=word, dasha_year=SIDEREAL_YEAR, dasha_out=table),
    )

    assert code == OK
    assert table.read_bytes() == expected_table(depth=depth)


@pytest.mark.parametrize("year", [JULIAN_YEAR, SIDEREAL_YEAR])
def test_both_year_conventions_reach_the_table(capfdbinary, tmp_path, year):
    table = tmp_path / "dasha.txt"

    code, _broken, _out, _err = invoke(
        capfdbinary, argv_for(dasha="", dasha_year=year, dasha_out=table)
    )

    assert code == OK
    assert table.read_bytes() == expected_table(year=year)


# --- usage errors ----------------------------------------------------------


def test_neither_output_is_a_usage_error(monkeypatch, capfdbinary):
    forbid_the_resolver(monkeypatch)

    code, broken, out, err = invoke(capfdbinary, argv_for())

    assert (code, broken) == (INPUT, False)
    assert out == b""
    assert "at least one of --out or --dasha" in err


@pytest.mark.parametrize(
    "extra",
    [
        ("--dasha-year", JULIAN_YEAR),
        ("--dasha-out", "d.txt"),
        ("--dasha-precision", "day"),
        ("--dasha-zone", "UTC"),
        ("--dasha-precision", "second"),
    ],
)
def test_a_dasha_option_without_dasha_is_a_usage_error(
    monkeypatch, capfdbinary, tmp_path, extra
):
    forbid_the_resolver(monkeypatch)

    code, _broken, out, err = invoke(
        capfdbinary, argv_for(tmp_path / "c.svg", extra=extra)
    )

    assert code == INPUT
    assert out == b""
    assert extra[0] in err
    assert "--dasha" in err


def test_the_defaulted_dasha_options_never_trigger_the_orphan_error(
    capfdbinary, tmp_path
):
    """``--dasha-precision`` and ``--dasha-zone`` default to a sentinel.

    Their effective defaults exist, but argparse never fills them in, so an
    SVG-only run carries no trace of them and is not an orphan.
    """
    destination = tmp_path / "chart.svg"

    code, _broken, _out, err = invoke(capfdbinary, argv_for(destination))

    assert code == OK
    assert err == ""
    assert destination.read_bytes() == GOLDEN


@pytest.mark.parametrize(
    "dasha_year, dasha_out, missing",
    [
        (None, "d.txt", "--dasha-year"),
        (SIDEREAL_YEAR, None, "--dasha-out"),
        (None, None, "--dasha-year"),
    ],
)
def test_dasha_without_its_required_options_is_a_usage_error(
    monkeypatch, capfdbinary, tmp_path, dasha_year, dasha_out, missing
):
    forbid_the_resolver(monkeypatch)
    target = None if dasha_out is None else tmp_path / dasha_out

    code, _broken, out, err = invoke(
        capfdbinary,
        argv_for(dasha="", dasha_year=dasha_year, dasha_out=target),
    )

    assert code == INPUT
    assert out == b""
    assert missing in err


def test_two_stdout_destinations_are_a_usage_error(monkeypatch, capfdbinary):
    forbid_the_resolver(monkeypatch)

    code, _broken, out, err = invoke(
        capfdbinary,
        argv_for("-", dasha="", dasha_year=JULIAN_YEAR, dasha_out="-"),
    )

    assert code == INPUT
    assert out == b""
    assert "at most one output may go to stdout" in err


@pytest.mark.parametrize(
    "flag",
    [
        ("--caption",),
        ("--no-degrees",),
        ("--mark-node-retrograde",),
        ("--width", "800"),
        ("--id-prefix", "chart-7"),
    ],
)
def test_a_renderer_flag_without_out_is_a_usage_error(
    monkeypatch, capfdbinary, tmp_path, flag
):
    forbid_the_resolver(monkeypatch)

    code, _broken, out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="",
            dasha_year=JULIAN_YEAR,
            dasha_out=tmp_path / "d.txt",
            extra=flag,
        ),
    )

    assert code == INPUT
    assert out == b""
    assert "renderer options require --out" in err
    assert flag[0] in err
    assert not (tmp_path / "d.txt").exists()


def test_renderer_flags_are_accepted_in_the_combined_mode(
    capfdbinary, tmp_path
):
    chart = tmp_path / "chart.svg"
    table = tmp_path / "dasha.txt"

    code, _broken, _out, _err = invoke(
        capfdbinary,
        argv_for(
            chart,
            dasha="",
            dasha_year=SIDEREAL_YEAR,
            dasha_out=table,
            extra=("--caption",),
        ),
    )

    assert code == OK
    assert chart.read_bytes() == (
        GOLDEN_DIR / "jalandhar_caption_degrees.svg"
    ).read_bytes()
    assert table.read_bytes() == expected_table()


@pytest.mark.parametrize("value", ["365", "365.2563", "sidereal"])
def test_an_unknown_year_is_a_usage_error(
    monkeypatch, capfdbinary, tmp_path, value
):
    forbid_the_resolver(monkeypatch)

    code, _broken, out, err = invoke(
        capfdbinary,
        argv_for(dasha="", dasha_year=value, dasha_out=tmp_path / "d.txt"),
    )

    assert code == INPUT
    assert out == b""
    assert "--dasha-year" in err


def test_an_unknown_depth_word_is_a_usage_error(
    monkeypatch, capfdbinary, tmp_path
):
    forbid_the_resolver(monkeypatch)

    code, _broken, out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="md-ad-pd-sd",
            dasha_year=JULIAN_YEAR,
            dasha_out=tmp_path / "d.txt",
        ),
    )

    assert code == INPUT
    assert out == b""
    assert "--dasha" in err


# --- destinations ----------------------------------------------------------


def test_two_equal_destinations_are_refused_before_any_calculation(
    monkeypatch, capfdbinary, tmp_path
):
    forbid_the_resolver(monkeypatch)
    both = tmp_path / "one.out"

    code, _broken, out, err = invoke(
        capfdbinary,
        argv_for(both, dasha="", dasha_year=JULIAN_YEAR, dasha_out=both),
    )

    assert code == OUTPUT
    assert out == b""
    assert "refer to the same file" in err
    assert not both.exists()


def test_two_spellings_of_one_path_are_refused(
    monkeypatch, capfdbinary, tmp_path
):
    forbid_the_resolver(monkeypatch)
    (tmp_path / "sub").mkdir()
    spelled = tmp_path / "sub" / ".." / "one.out"

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            tmp_path / "one.out",
            dasha="",
            dasha_year=JULIAN_YEAR,
            dasha_out=spelled,
        ),
    )

    assert code == OUTPUT
    assert "refer to the same file" in err


def test_a_hard_link_between_the_two_destinations_is_refused(
    monkeypatch, capfdbinary, tmp_path
):
    """Different paths, one file: only ``samefile`` can tell."""
    forbid_the_resolver(monkeypatch)
    first = tmp_path / "chart.svg"
    first.write_bytes(b"existing\n")
    second = tmp_path / "dasha.txt"
    os.link(first, second)

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            first,
            dasha="",
            dasha_year=JULIAN_YEAR,
            dasha_out=second,
            extra=("--force",),
        ),
    )

    assert code == OUTPUT
    assert "refer to the same file" in err
    assert first.read_bytes() == b"existing\n"


def test_an_unverifiable_pair_of_destinations_is_refused(
    monkeypatch, capfdbinary, tmp_path
):
    first = tmp_path / "chart.svg"
    first.write_bytes(b"a\n")
    second = tmp_path / "dasha.txt"
    second.write_bytes(b"b\n")
    real_samefile = os.path.samefile

    def refusing(one, other):
        if str(one) == str(first) and str(other) == str(second):
            raise PermissionError(13, "Permission denied")
        return real_samefile(one, other)

    monkeypatch.setattr(os.path, "samefile", refusing)

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            first,
            dasha="",
            dasha_year=JULIAN_YEAR,
            dasha_out=second,
            extra=("--force",),
        ),
    )

    assert code == OUTPUT
    assert "unverifiable pair" in err


def test_force_replaces_both_files(capfdbinary, tmp_path):
    chart = tmp_path / "chart.svg"
    chart.write_bytes(b"old svg\n")
    table = tmp_path / "dasha.txt"
    table.write_bytes(b"old table\n")

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            chart,
            dasha="",
            dasha_year=SIDEREAL_YEAR,
            dasha_out=table,
            extra=("--force",),
        ),
    )

    assert code == OK
    assert chart.read_bytes() == GOLDEN
    assert table.read_bytes() == expected_table()
    assert [path for path in tmp_path.iterdir() if path.suffix == ".tmp"] == []
    assert err == ""


def test_an_existing_dasha_destination_is_not_overwritten_without_force(
    monkeypatch, capfdbinary, tmp_path
):
    table = tmp_path / "dasha.txt"
    table.write_bytes(b"mine\n")
    forbid_the_resolver(monkeypatch)

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(dasha="", dasha_year=JULIAN_YEAR, dasha_out=table),
    )

    assert code == OUTPUT
    assert table.read_bytes() == b"mine\n"
    assert "--force" in err


def test_the_geodata_file_is_never_the_dasha_destination(
    capfdbinary, tmp_path
):
    before = FIXTURE_DB.stat()

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="",
            dasha_year=JULIAN_YEAR,
            dasha_out=FIXTURE_DB,
            extra=("--force",),
        ),
    )

    assert code == OUTPUT
    assert "input resource" in err
    assert FIXTURE_DB.stat().st_mtime_ns == before.st_mtime_ns


def test_an_ephemeris_file_is_never_the_dasha_destination(
    capfdbinary, tmp_path
):
    target = EPHE_PATH / EPHEMERIS_FILE_SIZES[0][0]
    before = target.stat()

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="",
            dasha_year=JULIAN_YEAR,
            dasha_out=target,
            extra=("--force",),
        ),
    )

    assert code == OUTPUT
    assert "input resource" in err
    assert target.stat().st_mtime_ns == before.st_mtime_ns


def test_a_symlink_dasha_destination_is_refused_even_with_force(
    capfdbinary, tmp_path
):
    target = tmp_path / "target.txt"
    target.write_bytes(b"target bytes\n")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="", dasha_year=JULIAN_YEAR, dasha_out=link, extra=("--force",)
        ),
    )

    assert code == OUTPUT
    assert "symbolic link" in err
    assert target.read_bytes() == b"target bytes\n"


def test_a_fifo_dasha_destination_is_refused_even_with_force(
    capfdbinary, tmp_path
):
    fifo = tmp_path / "dasha.txt"
    os.mkfifo(fifo)

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="", dasha_year=JULIAN_YEAR, dasha_out=fifo, extra=("--force",)
        ),
    )

    assert code == OUTPUT
    assert "not a regular file" in err


def test_a_missing_dasha_parent_directory_is_an_output_error(
    capfdbinary, tmp_path
):
    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="",
            dasha_year=JULIAN_YEAR,
            dasha_out=tmp_path / "absent" / "d.txt",
        ),
    )

    assert code == OUTPUT
    assert "never creates directories" in err


# --- partial failures ------------------------------------------------------


def test_a_failed_second_file_write_keeps_the_first_file(
    monkeypatch, capfdbinary, tmp_path
):
    chart = tmp_path / "chart.svg"
    table = tmp_path / "dasha.txt"
    real_open = os.open

    def refusing(path, flags, mode=0o777, **kwargs):
        if str(path) == str(table):
            raise PermissionError(13, "Permission denied")
        return real_open(path, flags, mode, **kwargs)

    monkeypatch.setattr(os, "open", refusing)

    code, broken, out, err = invoke(
        capfdbinary,
        argv_for(chart, dasha="", dasha_year=SIDEREAL_YEAR, dasha_out=table),
    )

    assert (code, broken) == (OUTPUT, False)
    assert out == b""
    assert chart.read_bytes() == GOLDEN
    assert not table.exists()
    assert "could not create" in err
    assert f"note: svg output was written to {chart} and is kept" in err
    assert err.index("could not create") < err.index("note: svg output")


def test_a_failed_second_file_write_after_the_dasha_keeps_the_table(
    monkeypatch, capfdbinary, tmp_path
):
    """The same, with the daśā file first: ``--out -`` puts the SVG last."""
    table = tmp_path / "dasha.txt"

    def failing(data):
        cli._stderr("error: could not write to stdout: injected")
        return OUTPUT, False

    monkeypatch.setattr(cli, "_write_stdout", failing)

    code, broken, _out, err = invoke(
        capfdbinary,
        argv_for("-", dasha="", dasha_year=SIDEREAL_YEAR, dasha_out=table),
    )

    assert (code, broken) == (OUTPUT, False)
    assert table.read_bytes() == expected_table()
    assert f"note: dasha output was written to {table} and is kept" in err


class _BrokenBuffer:
    def __init__(self, error):
        self._error = error
        self.written = BytesIO()

    def write(self, data):
        raise self._error

    def flush(self):  # pragma: no cover - never reached in these tests
        raise AssertionError("flush must not follow a failed write")


class _FakeStdout:
    def __init__(self, buffer):
        self.buffer = buffer


def test_a_broken_svg_pipe_after_the_dasha_file_keeps_the_file(
    monkeypatch, capfdbinary, tmp_path
):
    table = tmp_path / "dasha.txt"
    monkeypatch.setattr(
        sys,
        "stdout",
        _FakeStdout(_BrokenBuffer(BrokenPipeError(32, "Broken pipe"))),
    )
    try:
        code, broken = cli.run(
            argv_for(
                "-", dasha="", dasha_year=SIDEREAL_YEAR, dasha_out=table
            )
        )
    finally:
        monkeypatch.undo()
    err = capfdbinary.readouterr().err.decode("utf-8")

    assert (code, broken) == (OUTPUT, True)
    assert table.read_bytes() == expected_table()
    assert err.count("stdout closed by reader") == 1
    assert f"note: dasha output was written to {table} and is kept" in err


def test_a_broken_dasha_pipe_after_the_svg_file_keeps_the_file(
    monkeypatch, capfdbinary, tmp_path
):
    chart = tmp_path / "chart.svg"
    monkeypatch.setattr(
        sys,
        "stdout",
        _FakeStdout(_BrokenBuffer(BrokenPipeError(32, "Broken pipe"))),
    )
    try:
        code, broken = cli.run(
            argv_for(
                chart, dasha="", dasha_year=SIDEREAL_YEAR, dasha_out="-"
            )
        )
    finally:
        monkeypatch.undo()
    err = capfdbinary.readouterr().err.decode("utf-8")

    assert (code, broken) == (OUTPUT, True)
    assert chart.read_bytes() == GOLDEN
    assert err.count("stdout closed by reader") == 1
    assert f"note: svg output was written to {chart} and is kept" in err


def test_a_failed_first_write_reports_no_note(
    monkeypatch, capfdbinary, tmp_path
):
    """Nothing was kept, so nothing is claimed to be kept."""
    chart = tmp_path / "chart.svg"
    table = tmp_path / "dasha.txt"
    real_open = os.open

    def refusing(path, flags, mode=0o777, **kwargs):
        if str(path) == str(chart):
            raise PermissionError(13, "Permission denied")
        return real_open(path, flags, mode, **kwargs)

    monkeypatch.setattr(os, "open", refusing)

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(chart, dasha="", dasha_year=SIDEREAL_YEAR, dasha_out=table),
    )

    assert code == OUTPUT
    assert "and is kept" not in err
    assert not table.exists()


# --- presentation options through the command ------------------------------


def test_day_precision_prints_dates_and_the_warning(capfdbinary, tmp_path):
    table = tmp_path / "dasha.txt"

    code, _broken, _out, _err = invoke(
        capfdbinary,
        argv_for(
            dasha="md",
            dasha_year=JULIAN_YEAR,
            dasha_out=table,
            extra=("--dasha-precision", "day"),
        ),
    )
    text = table.read_text(encoding="utf-8")

    assert code == OK
    assert table.read_bytes() == expected_table(
        year=JULIAN_YEAR, depth=1, precision="day"
    )
    assert DAY_WARNING in text
    # The Birth line keeps its seconds and offset; only the period rows are dates.
    body = text.split("\n\n", 1)[1].splitlines()[1:]
    assert body and all("+05:30" not in line and ":" not in line for line in body)
    assert text.splitlines()[1].startswith("Birth 1995-03-21 06:45:00+05:30 ")


def test_second_precision_is_the_default(capfdbinary, tmp_path):
    table = tmp_path / "dasha.txt"

    invoke(
        capfdbinary,
        argv_for(
            dasha="md",
            dasha_year=JULIAN_YEAR,
            dasha_out=table,
            extra=("--dasha-precision", "second"),
        ),
    )

    assert table.read_bytes() == expected_table(year=JULIAN_YEAR, depth=1)


def test_the_zone_defaults_to_the_birthplace(capfdbinary, tmp_path):
    table = tmp_path / "dasha.txt"

    invoke(
        capfdbinary,
        argv_for(dasha="md", dasha_year=JULIAN_YEAR, dasha_out=table),
    )

    assert table.read_bytes() == expected_table(
        year=JULIAN_YEAR, depth=1, zone=KOLKATA
    )
    assert reference_chart().location.timezone_id == KOLKATA


def test_an_explicit_zone_is_used(capfdbinary, tmp_path):
    table = tmp_path / "dasha.txt"

    code, _broken, _out, _err = invoke(
        capfdbinary,
        argv_for(
            dasha="md",
            dasha_year=JULIAN_YEAR,
            dasha_out=table,
            extra=("--dasha-zone", "UTC"),
        ),
    )

    assert code == OK
    assert table.read_bytes() == expected_table(
        year=JULIAN_YEAR, depth=1, zone="UTC"
    )
    assert b"+00:00" in table.read_bytes()


@pytest.mark.parametrize("key", ["Not/AZone", "../etc/passwd", ""])
def test_an_invalid_zone_is_an_input_error_before_anything_opens(
    monkeypatch, capfdbinary, tmp_path, key
):
    forbid_the_resolver(monkeypatch)
    table = tmp_path / "dasha.txt"

    code, _broken, out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="md",
            dasha_year=JULIAN_YEAR,
            dasha_out=table,
            extra=("--dasha-zone", key),
        ),
    )

    assert code == INPUT
    assert out == b""
    assert "error:" in err
    assert not table.exists()


def test_verbose_reports_the_dasha_destination_zone_year_and_depth(
    capfdbinary, tmp_path
):
    table = tmp_path / "dasha.txt"

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="md-ad-pd",
            dasha_year=SIDEREAL_YEAR,
            dasha_out=table,
            extra=("--verbose",),
        ),
    )

    assert code == OK
    assert f"dasha output: {table}" in err
    assert f"dasha zone: {KOLKATA}" in err
    assert f"dasha year: {SIDEREAL_YEAR} days" in err
    assert "dasha depth: md-ad-pd" in err
    assert "dasha precision: second" in err


def test_verbose_names_a_stdout_dasha_destination(capfdbinary):
    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="md",
            dasha_year=JULIAN_YEAR,
            dasha_out="-",
            extra=("--verbose",),
        ),
    )

    assert code == OK
    assert "dasha output: -" in err


# --- error scopes ----------------------------------------------------------


def test_a_dasha_range_error_from_the_pipeline_is_an_input_error(
    monkeypatch, capfdbinary, tmp_path
):
    def exploding(request, config, year):
        raise DashaRangeError("injected cycle out of range")

    monkeypatch.setattr(cli, "compute_dasha", exploding)

    code, _broken, out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="md", dasha_year=JULIAN_YEAR, dasha_out=tmp_path / "d.txt"
        ),
    )

    assert code == INPUT
    assert out == b""
    assert "injected cycle out of range" in err
    assert not (tmp_path / "d.txt").exists()


def test_a_dasha_range_error_from_the_table_is_an_input_error(
    monkeypatch, capfdbinary, tmp_path
):
    def exploding(timeline, *, zone, depth, precision):
        raise DashaRangeError("injected conversion overflow")

    monkeypatch.setattr(cli, "render_dasha_text", exploding)

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="md", dasha_year=JULIAN_YEAR, dasha_out=tmp_path / "d.txt"
        ),
    )

    assert code == INPUT
    assert "injected conversion overflow" in err
    assert not (tmp_path / "d.txt").exists()


def test_an_unrelated_value_error_in_the_pipeline_is_still_the_generic_exit(
    monkeypatch, capfdbinary, tmp_path
):
    """DashaRangeError is caught by type, not for being a ValueError."""

    def exploding(request, config, year):
        raise ValueError("injected pipeline failure")

    monkeypatch.setattr(cli, "compute_dasha", exploding)

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="md", dasha_year=JULIAN_YEAR, dasha_out=tmp_path / "d.txt"
        ),
    )

    assert code == UNEXPECTED
    assert "injected pipeline failure" in err


def test_an_unrelated_overflow_error_in_the_pipeline_is_the_generic_exit(
    monkeypatch, capfdbinary, tmp_path
):
    def exploding(request, config, options, year):
        raise OverflowError("injected overflow")

    monkeypatch.setattr(cli, "render_chart_and_dasha", exploding)

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            tmp_path / "c.svg",
            dasha="md",
            dasha_year=JULIAN_YEAR,
            dasha_out=tmp_path / "d.txt",
        ),
    )

    assert code == UNEXPECTED
    assert "injected overflow" in err


def test_an_unknown_place_is_still_a_place_error_in_dasha_mode(
    capfdbinary, tmp_path
):
    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="md",
            dasha_year=JULIAN_YEAR,
            dasha_out=tmp_path / "d.txt",
            place="Xyzzyville",
        ),
    )

    assert code == PLACE
    assert "Xyzzyville" in err


def test_a_birth_outside_coverage_is_still_the_generic_failure(
    capfdbinary, tmp_path
):
    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            dasha="md",
            dasha_year=JULIAN_YEAR,
            dasha_out=tmp_path / "d.txt",
            date="1750-06-01",
        ),
    )

    assert code == UNEXPECTED
    assert "RuntimeError" in err


# --- the executable boundary -----------------------------------------------


def child_environment():
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    return environment


def test_the_module_runs_a_combined_invocation_as_a_command(tmp_path):
    chart = tmp_path / "chart.svg"
    table = tmp_path / "dasha.txt"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "vedic_chart.app",
            *argv_for(
                chart, dasha="", dasha_year=SIDEREAL_YEAR, dasha_out=table
            ),
        ],
        cwd=REPO_ROOT,
        env=child_environment(),
        capture_output=True,
    )

    assert completed.returncode == OK
    assert completed.stdout == b""
    assert chart.read_bytes() == GOLDEN
    assert table.read_bytes() == expected_table()


# --- unexpected failures while generating content ---------------------------
#
# Content is generated after the pipeline and before any write. A failure
# there that is not a DashaRangeError is the documented generic case: exit 1,
# a one-line diagnostic, a traceback only with --verbose, nothing on stdout,
# and -- because nothing has been written yet -- no output file created or
# modified. It is never reinterpreted as an input error.


def _content_failure_cases():
    def value_error(timeline, *, zone, depth, precision):
        raise ValueError("injected presentation failure")

    def overflow_error(timeline, *, zone, depth, precision):
        raise OverflowError("injected presentation overflow")

    def unencodable(timeline, *, zone, depth, precision):
        # A lone surrogate cannot be encoded as UTF-8: the encode step fails,
        # not the renderer.
        return "Vimshottari dasha \udcff\n"

    return [
        pytest.param(value_error, "ValueError: injected presentation failure", id="ValueError"),
        pytest.param(overflow_error, "OverflowError: injected presentation overflow", id="OverflowError"),
        pytest.param(unencodable, "UnicodeEncodeError", id="encoding"),
    ]


@pytest.mark.parametrize("stub,diagnostic", _content_failure_cases())
def test_an_unexpected_content_failure_is_the_generic_exit_without_traceback(
    monkeypatch, capfdbinary, tmp_path, stub, diagnostic
):
    monkeypatch.setattr(cli, "render_dasha_text", stub)
    svg_dest = tmp_path / "c.svg"
    dasha_dest = tmp_path / "d.txt"

    code, broken, out, err = invoke(
        capfdbinary,
        argv_for(
            svg_dest, dasha="md", dasha_year=JULIAN_YEAR, dasha_out=dasha_dest
        ),
    )

    assert (code, broken) == (UNEXPECTED, False)
    assert out == b""
    assert diagnostic in err
    assert "Traceback" not in err
    assert not svg_dest.exists()
    assert not dasha_dest.exists()


@pytest.mark.parametrize("stub,diagnostic", _content_failure_cases())
def test_an_unexpected_content_failure_shows_a_traceback_only_when_verbose(
    monkeypatch, capfdbinary, tmp_path, stub, diagnostic
):
    monkeypatch.setattr(cli, "render_dasha_text", stub)
    svg_dest = tmp_path / "c.svg"
    dasha_dest = tmp_path / "d.txt"

    code, _broken, out, err = invoke(
        capfdbinary,
        argv_for(
            svg_dest,
            dasha="md",
            dasha_year=JULIAN_YEAR,
            dasha_out=dasha_dest,
            extra=("--verbose",),
        ),
    )

    assert code == UNEXPECTED
    assert out == b""
    assert diagnostic in err
    assert "Traceback" in err
    assert not svg_dest.exists()
    assert not dasha_dest.exists()


@pytest.mark.parametrize("stub,diagnostic", _content_failure_cases())
def test_an_unexpected_content_failure_leaves_existing_outputs_untouched(
    monkeypatch, capfdbinary, tmp_path, stub, diagnostic
):
    """With --force both destinations exist; neither may change."""
    monkeypatch.setattr(cli, "render_dasha_text", stub)
    svg_dest = tmp_path / "c.svg"
    dasha_dest = tmp_path / "d.txt"
    svg_dest.write_bytes(b"old svg\n")
    dasha_dest.write_bytes(b"old table\n")

    code, _broken, out, err = invoke(
        capfdbinary,
        argv_for(
            svg_dest,
            dasha="md",
            dasha_year=JULIAN_YEAR,
            dasha_out=dasha_dest,
            extra=("--force",),
        ),
    )

    assert code == UNEXPECTED
    assert out == b""
    assert diagnostic in err
    assert svg_dest.read_bytes() == b"old svg\n"
    assert dasha_dest.read_bytes() == b"old table\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["c.svg", "d.txt"]


def test_a_dasha_range_error_from_the_table_is_still_an_input_error_not_generic(
    monkeypatch, capfdbinary, tmp_path
):
    """The scoped handler keeps its type distinction after the generic one was added."""

    def exploding(timeline, *, zone, depth, precision):
        raise DashaRangeError("injected conversion overflow")

    monkeypatch.setattr(cli, "render_dasha_text", exploding)

    code, _broken, out, err = invoke(
        capfdbinary,
        argv_for(
            tmp_path / "c.svg",
            dasha="md",
            dasha_year=JULIAN_YEAR,
            dasha_out=tmp_path / "d.txt",
        ),
    )

    assert code == INPUT
    assert out == b""
    assert "injected conversion overflow" in err
    assert "Traceback" not in err
    assert not (tmp_path / "c.svg").exists()
