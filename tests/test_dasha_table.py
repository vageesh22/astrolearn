"""Layer 13's table: rows and text (specification section 7).

Self-contained in the same sense as the Layer 11 and Layer 12 tests: the
birthplace comes from the committed fixture geodata database or from an
explicit ``ResolvedLocation``, the positions from the committed ``ephe/``
directory, and nothing here needs the production database, a network or a
clock.

Three kinds of input appear, and they are kept apart on purpose.

* **Real births.** Jalandhar 1995-03-21 06:45 IST and Jammu 2001-02-04 10:45
  IST, the two reference charts of Layer 12, assembled here exactly as that
  layer's adapter tests assemble them.
* **Divergence longitudes.** ``nextafter(40.0, 0)`` and ``3.666666666666666``,
  the two hand-computed inputs of Layer 12 section 7 for which the nominal
  birth chain and the quantized birth chain differ. They are the reason the
  table has two birth columns rather than one, so they are asserted column by
  column.
* **Synthetic presentation fixtures.** ``VimshottariTimeline`` objects built by
  hand, never by the core, and used only where a real cycle cannot reach: the
  two ``datetime`` limits, where converting a boundary into a zone overflows.
  They are labelled as fakes everywhere they appear and prove nothing about
  daśā arithmetic -- only about what this module does when a conversion cannot
  be done.

The two committed goldens are the *only* text files this milestone adds, and
both live in the new ``tests/fixtures/dasha/`` directory; every existing
fixture and SVG golden is untouched.
"""

import dataclasses
import math
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from render_helpers import EPHE_DIR, FIXTURE_DB, REPO_ROOT, FixedResolver
from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.chart.assemble import assemble_chart
from vedic_chart.dasha import (
    DashaPeriod,
    DashaRangeError,
    DashaRow,
    VimshottariTimeline,
    YearConvention,
    build_vimshottari,
    dasha_rows,
    render_dasha_text,
    resolve_zone,
    vimshottari_from_chart,
)
from vedic_chart.dasha.table import DAY_WARNING
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.model import ResolvedLocation
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.vedic.grahas import Graha

GOLDEN_DIR = REPO_ROOT / "tests" / "fixtures" / "dasha"

CONVENTIONS = tuple(YearConvention)
DEPTHS = (1, 2, 3)
PRECISIONS = ("second", "day")
ROW_COUNTS = {1: 9, 2: 90, 3: 819}

KOLKATA = "Asia/Kolkata"
UTC = timezone.utc

#: A birth instant for the synthetic longitude cases. Any aware instant does;
#: this one is Jalandhar's, so the cases sit in the same era as the real ones.
SYNTHETIC_BIRTH = datetime(1995, 3, 21, 1, 15, tzinfo=UTC)

#: Layer 12 section 7's two hand-computed divergence longitudes.
NEXT_AFTER_FORTY = math.nextafter(40.0, 0)
THREE_TWO_THIRDS = 3.666666666666666

JAMMU_LOCATION = ResolvedLocation(
    canonical_name="Jammu, Jammu and Kashmir, India",
    latitude=32.73528,
    longitude=74.86167,
    timezone_id="Asia/Kolkata",
)


def jalandhar_chart():
    request = BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query="Jalandhar"
    )
    with ephemeris_session(EPHE_DIR):
        with OfflineLocationResolver(FIXTURE_DB) as resolver:
            return assemble_chart(request, resolver)


def jammu_chart():
    request = BirthChartRequest.from_components(
        2001, 2, 4, 10, 45, place_query="Jammu, Jammu and Kashmir, India"
    )
    with ephemeris_session(EPHE_DIR):
        return assemble_chart(request, FixedResolver(JAMMU_LOCATION))


def victorian_jalandhar_chart():
    """The same place in 1890, inside the ephemeris files' 1800-2399 coverage.

    Asia/Kolkata was ``+05:21:10`` before 1906 -- an offset that is not a whole
    number of minutes -- which is the case the offset rule of section 3(a)
    exists for.
    """
    request = BirthChartRequest.from_components(
        1890, 3, 21, 6, 45, place_query="Jalandhar"
    )
    with ephemeris_session(EPHE_DIR):
        with OfflineLocationResolver(FIXTURE_DB) as resolver:
            return assemble_chart(request, resolver)


BUILDERS = {
    "jalandhar": jalandhar_chart,
    "jammu": jammu_chart,
    "jalandhar1890": victorian_jalandhar_chart,
}
CASE_NAMES = ("jalandhar", "jammu")

_CHART_CACHE = {}
_TIMELINE_CACHE = {}


def chart(name):
    """Built once: an ephemeris run per parametrised case would dominate."""
    if name not in _CHART_CACHE:
        _CHART_CACHE[name] = BUILDERS[name]()
    return _CHART_CACHE[name]


def timeline(name, convention):
    key = (name, convention)
    if key not in _TIMELINE_CACHE:
        _TIMELINE_CACHE[key] = vimshottari_from_chart(chart(name), convention)
    return _TIMELINE_CACHE[key]


def divergence_timeline(longitude, convention=YearConvention.FIXED_365_25):
    return build_vimshottari(longitude, SYNTHETIC_BIRTH, convention)


def marked(rows):
    """``{(level, lords): (N, Q)}`` for every row carrying either flag."""
    return {
        (row.level, row.lords): (
            row.in_nominal_birth_chain,
            row.in_quantized_birth_chain,
        )
        for row in rows
        if row.in_nominal_birth_chain or row.in_quantized_birth_chain
    }


def body_lines(text):
    """The period lines: everything after the column header."""
    lines = text.splitlines()
    header_index = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("Level  Chain")
    )
    return lines[header_index + 1:]


def printed_stamps(line):
    """``(start, end)`` as printed, with the level and chain columns dropped."""
    rest = line[7:]                      # "MD     " / "AD     " / "PD     "
    rest = rest[10:]                     # the chain column and its gap
    return rest


# --- rows ------------------------------------------------------------------


@pytest.mark.parametrize("depth", DEPTHS)
@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_row_count_is_nine_ninety_or_eight_hundred_and_nineteen(
    name, convention, depth
):
    rows = dasha_rows(timeline(name, convention), depth=depth)

    assert len(rows) == ROW_COUNTS[depth]
    assert all(isinstance(row, DashaRow) for row in rows)
    assert {row.level for row in rows} == set(range(1, depth + 1))


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_rows_are_in_pre_order(name):
    """Each parent immediately precedes its own children, at every level."""
    rows = dasha_rows(timeline(name, YearConvention.FIXED_365_25), depth=3)

    assert [row.level for row in rows[:4]] == [1, 2, 3, 3]
    open_chain = {}
    for row in rows:
        open_chain[row.level] = row.lords
        if row.level > 1:
            assert row.lords[:-1] == open_chain[row.level - 1]
        assert len(row.lords) == row.level
    # The nine Mahadashas appear in the core's order, once each.
    assert [row.lords[0] for row in rows if row.level == 1] == [
        period.lord
        for period in timeline(name, YearConvention.FIXED_365_25).mahadashas
    ]


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_rows_carry_the_periods_values_losslessly(name, convention):
    """No zone, no truncation: the row is the period, by value."""
    line = timeline(name, convention)
    rows = dasha_rows(line, depth=3)

    periods = []
    for mahadasha in line.mahadashas:
        periods.append(mahadasha)
        for antardasha in mahadasha.children:
            periods.append(antardasha)
            periods.extend(antardasha.children)

    assert len(rows) == len(periods)
    for row, period in zip(rows, periods):
        assert (row.level, row.lords) == (period.level, period.lords)
        assert row.start_utc == period.start_utc
        assert row.end_utc == period.end_utc
        assert row.start_utc.tzinfo is period.start_utc.tzinfo
        assert row.nominal_start == period.nominal_start
        assert row.nominal_end == period.nominal_end
        assert isinstance(row.nominal_start, Fraction)


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_birth_flags_reproduce_the_two_queries(name, convention):
    line = timeline(name, convention)
    rows = dasha_rows(line, depth=3)

    nominal = {
        (period.level, period.lords) for period in line.periods_at_birth()
    }
    quantized = {
        (period.level, period.lords)
        for period in line.active_periods_at(line.birth_utc)
    }

    assert {
        (row.level, row.lords) for row in rows if row.in_nominal_birth_chain
    } == nominal
    assert {
        (row.level, row.lords) for row in rows if row.in_quantized_birth_chain
    } == quantized
    # Ordinary births: the two chains are the same three rows.
    assert nominal == quantized
    assert len(nominal) == 3


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
def test_the_nextafter_forty_case_splits_the_two_columns(convention):
    """Layer 12 section 7's first divergence, column by column."""
    rows = dasha_rows(
        divergence_timeline(NEXT_AFTER_FORTY, convention), depth=3
    )

    assert marked(rows) == {
        (1, (Graha.SUN,)): (True, False),
        (2, (Graha.SUN, Graha.VENUS)): (True, False),
        (3, (Graha.SUN, Graha.VENUS, Graha.KETU)): (True, False),
        (1, (Graha.MOON,)): (False, True),
        (2, (Graha.MOON, Graha.MOON)): (False, True),
        (3, (Graha.MOON, Graha.MOON, Graha.MOON)): (False, True),
    }


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
def test_the_three_and_two_thirds_case_splits_the_two_columns(convention):
    """The second divergence: the Mahadasha agrees, the children do not."""
    rows = dasha_rows(
        divergence_timeline(THREE_TWO_THIRDS, convention), depth=3
    )

    assert marked(rows) == {
        (1, (Graha.KETU,)): (True, True),
        (2, (Graha.KETU, Graha.SUN)): (True, False),
        (3, (Graha.KETU, Graha.SUN, Graha.VENUS)): (True, False),
        (2, (Graha.KETU, Graha.MOON)): (False, True),
        (3, (Graha.KETU, Graha.MOON, Graha.MOON)): (False, True),
    }


def test_a_shallower_depth_keeps_the_flags_it_can_show():
    """A depth-1 table still marks the Mahadasha, and marks it correctly."""
    rows = dasha_rows(divergence_timeline(NEXT_AFTER_FORTY), depth=1)

    assert marked(rows) == {
        (1, (Graha.SUN,)): (True, False),
        (1, (Graha.MOON,)): (False, True),
    }


def test_a_row_is_frozen():
    row = dasha_rows(timeline("jalandhar", YearConvention.FIXED_365_25), depth=1)[0]

    with pytest.raises(dataclasses.FrozenInstanceError):
        row.level = 2
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.in_nominal_birth_chain = False


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("value", [True, False, 1.0, 2.0, "2", None, Fraction(2)])
def test_a_depth_of_the_wrong_type_is_refused(value):
    """``type(depth) is int``: ``True`` and ``1.0`` equal a legal depth."""
    line = timeline("jalandhar", YearConvention.FIXED_365_25)

    with pytest.raises(TypeError, match="depth"):
        dasha_rows(line, depth=value)
    with pytest.raises(TypeError, match="depth"):
        render_dasha_text(line, zone=KOLKATA, depth=value)


@pytest.mark.parametrize("value", [0, 4, -1, 27])
def test_a_depth_outside_one_to_three_is_refused(value):
    line = timeline("jalandhar", YearConvention.FIXED_365_25)

    with pytest.raises(ValueError, match="1, 2 or 3"):
        dasha_rows(line, depth=value)
    with pytest.raises(ValueError, match="1, 2 or 3"):
        render_dasha_text(line, zone=KOLKATA, depth=value)


def test_the_depth_is_keyword_only():
    line = timeline("jalandhar", YearConvention.FIXED_365_25)

    with pytest.raises(TypeError):
        dasha_rows(line, 2)


@pytest.mark.parametrize("value", [1, None, b"day", ("second",)])
def test_a_precision_of_the_wrong_type_is_refused(value):
    line = timeline("jalandhar", YearConvention.FIXED_365_25)

    with pytest.raises(TypeError, match="precision"):
        render_dasha_text(line, zone=KOLKATA, precision=value)


@pytest.mark.parametrize("value", ["days", "SECOND", "", "minute"])
def test_an_unknown_precision_is_refused(value):
    line = timeline("jalandhar", YearConvention.FIXED_365_25)

    with pytest.raises(ValueError, match="precision"):
        render_dasha_text(line, zone=KOLKATA, precision=value)


@pytest.mark.parametrize("value", ["a timeline", None, 1, object()])
def test_a_non_timeline_is_refused(value):
    with pytest.raises(TypeError, match="VimshottariTimeline"):
        dasha_rows(value, depth=1)
    with pytest.raises(TypeError, match="VimshottariTimeline"):
        render_dasha_text(value, zone=KOLKATA)


# --- the single zone validator ---------------------------------------------


def test_resolve_zone_returns_the_zone():
    resolved = resolve_zone(KOLKATA)

    assert isinstance(resolved, ZoneInfo)
    assert str(resolved) == KOLKATA


@pytest.mark.parametrize("key", ["Not/AZone", "Etc/GMT+99", "Mars/Olympus"])
def test_an_unknown_zone_is_a_value_error_chained_from_the_lookup(key):
    with pytest.raises(ValueError) as caught:
        resolve_zone(key)

    assert key in str(caught.value)
    assert isinstance(caught.value.__cause__, ZoneInfoNotFoundError)
    assert not isinstance(caught.value, KeyError)


@pytest.mark.parametrize("key", ["", "../etc/passwd", "Asia/Kolkata/", "/UTC"])
def test_a_malformed_zone_is_a_value_error_chained_from_the_value_error(key):
    with pytest.raises(ValueError) as caught:
        resolve_zone(key)

    assert key in str(caught.value)
    cause = caught.value.__cause__
    assert isinstance(cause, ValueError)
    assert not isinstance(cause, LookupError)


@pytest.mark.parametrize("value", [None, 1, b"UTC", ZoneInfo("UTC")])
def test_a_non_string_zone_is_a_type_error(value):
    with pytest.raises(TypeError, match="zone"):
        resolve_zone(value)

    line = timeline("jalandhar", YearConvention.FIXED_365_25)
    with pytest.raises(TypeError, match="zone"):
        render_dasha_text(line, zone=value)


@pytest.mark.parametrize("key", ["Not/AZone", "../etc/passwd"])
def test_the_text_refuses_the_same_keys_the_validator_refuses(key):
    line = timeline("jalandhar", YearConvention.FIXED_365_25)

    with pytest.raises(ValueError) as caught:
        render_dasha_text(line, zone=key)

    assert key in str(caught.value)
    assert caught.value.__cause__ is not None


# --- the two committed goldens ---------------------------------------------

GOLDEN_CASES = {
    "jalandhar_md_ad_365256363_second_kolkata.txt": (
        "jalandhar", YearConvention.FIXED_365_256363, 2, "second", KOLKATA,
    ),
    "jammu_md_36525_day_kolkata.txt": (
        "jammu", YearConvention.FIXED_365_25, 1, "day", KOLKATA,
    ),
}


def golden_text(filename):
    """The text a golden records, rendered from the committed fixtures."""
    name, convention, depth, precision, zone = GOLDEN_CASES[filename]
    return render_dasha_text(
        timeline(name, convention),
        zone=zone,
        depth=depth,
        precision=precision,
    )


@pytest.mark.parametrize("filename", sorted(GOLDEN_CASES))
def test_the_golden_is_reproduced_byte_for_byte(filename):
    expected = (GOLDEN_DIR / filename).read_bytes()

    assert golden_text(filename).encode("utf-8") == expected


def test_the_jalandhar_golden_carries_the_expected_header():
    lines = (
        GOLDEN_DIR / "jalandhar_md_ad_365256363_second_kolkata.txt"
    ).read_text(encoding="utf-8").splitlines()

    assert lines[0] == (
        "Vimshottari dasha  |  Moon 209.20440791222882 (Vishakha #16)  |  "
        "lord Jupiter"
    )
    assert lines[1] == (
        "Birth 1995-03-21 06:45:00+05:30 (Asia/Kolkata)  |  "
        "year 365.256363 days  |  depth md-ad"
    )
    assert lines[2] == (
        "Nominal balance of the first Mahadasha at birth: "
        "87164189005907/17592186044416 = 4.954710505 years "
        "(nominal; decimal truncated to 9 places)"
    )
    assert lines[3].endswith(
        "shown in Asia/Kolkata with the UTC offset."
    )
    assert lines[6] == ""
    assert lines[7] == (
        "Level  Chain     Start                      "
        "End                        N  Q"
    )
    assert lines[8].startswith("MD     Ju        1984-03-03 ")
    assert lines[8].endswith("  N  Q")
    assert len(lines) == 98        # six header lines, a blank, a rule, 90 rows


def test_the_jammu_golden_carries_the_day_warning_and_dates_only():
    text = (GOLDEN_DIR / "jammu_md_36525_day_kolkata.txt").read_text(
        encoding="utf-8"
    )
    lines = text.splitlines()

    assert DAY_WARNING in lines
    assert lines[0].startswith(
        "Vimshottari dasha  |  Moon 54.892295957053236 (Mrigashira #5)"
    )
    assert lines[1] == (
        "Birth 2001-02-04 10:45:00+05:30 (Asia/Kolkata)  |  "
        "year 365.25 days  |  depth md"
    )
    assert len(body_lines(text)) == 9
    for line in body_lines(text):
        assert ":" not in line
        assert line.startswith("MD     ")


@pytest.mark.parametrize("filename", sorted(GOLDEN_CASES))
def test_the_golden_files_live_in_the_new_directory_only(filename):
    assert (GOLDEN_DIR / filename).is_file()
    assert GOLDEN_DIR.name == "dasha"
    assert sorted(path.name for path in GOLDEN_DIR.iterdir()) == sorted(
        GOLDEN_CASES
    )


# --- text semantics, parameterised -----------------------------------------


def rendered(name, convention, depth, precision, zone=KOLKATA):
    return render_dasha_text(
        timeline(name, convention), zone=zone, depth=depth, precision=precision
    )


@pytest.mark.parametrize("depth", DEPTHS)
@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", CASE_NAMES)
def test_second_precision_never_prints_an_instant_after_the_boundary(
    name, convention, depth
):
    """Truncation, not rounding: printed <= true, and within one second."""
    zone = resolve_zone(KOLKATA)
    rows = dasha_rows(timeline(name, convention), depth=depth)
    lines = body_lines(rendered(name, convention, depth, "second"))

    assert len(lines) == len(rows)
    for row, line in zip(rows, lines):
        printed = printed_stamps(line)
        start_text, end_text = printed[:25].strip(), printed[27:].strip()
        for text, boundary in (
            (start_text, row.start_utc),
            (end_text.split("  ")[0], row.end_utc),
        ):
            parsed = datetime.fromisoformat(text)
            true_local = boundary.astimezone(zone)
            assert parsed <= true_local
            assert true_local - parsed < timedelta(seconds=1)
            assert parsed.utcoffset() == true_local.utcoffset()


@pytest.mark.parametrize("depth", DEPTHS)
@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", CASE_NAMES)
def test_day_precision_prints_the_local_calendar_date(name, convention, depth):
    zone = resolve_zone(KOLKATA)
    rows = dasha_rows(timeline(name, convention), depth=depth)
    lines = body_lines(rendered(name, convention, depth, "day"))

    assert len(lines) == len(rows)
    for row, line in zip(rows, lines):
        printed = printed_stamps(line)
        start_text, end_text = printed[:10], printed[12:22]
        assert start_text == row.start_utc.astimezone(zone).date().isoformat()
        assert end_text == row.end_utc.astimezone(zone).date().isoformat()


@pytest.mark.parametrize("precision", PRECISIONS)
@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_day_warning_appears_exactly_when_day_precision_is_asked_for(
    name, precision
):
    text = rendered(name, YearConvention.FIXED_365_25, 1, precision)

    assert (DAY_WARNING in text) is (precision == "day")
    assert ("truncated to the second" in text) is (precision == "second")


def test_a_pre_1906_kolkata_boundary_prints_its_offset_seconds():
    """``+05:21:10``: the offset is the zone's, never forced to whole minutes."""
    line = vimshottari_from_chart(
        chart("jalandhar1890"), YearConvention.FIXED_365_256363
    )
    text = render_dasha_text(line, zone=KOLKATA, depth=1)

    assert "+05:21:10" in text
    first = body_lines(text)[0]
    parsed = datetime.fromisoformat(printed_stamps(first)[:28].strip())
    assert parsed.utcoffset() == timedelta(hours=5, minutes=21, seconds=10)
    assert parsed.utcoffset() == line.mahadashas[0].start_utc.astimezone(
        resolve_zone(KOLKATA)
    ).utcoffset()


@pytest.mark.parametrize(
    "birth_utc, expected_offset",
    [
        (datetime(2023, 10, 29, 0, 30, tzinfo=UTC), "+01:00"),
        (datetime(2023, 10, 29, 1, 30, tzinfo=UTC), "+00:00"),
    ],
)
def test_a_repeated_london_hour_is_distinguished_by_the_offset(
    birth_utc, expected_offset
):
    """The 2023-10-29 fall-back hour, printed twice from two real instants.

    A synthetic *core* timeline, not a synthetic presentation fixture: the
    longitude 0.0 is legal and gives an elapsed fraction of exactly zero, so
    the first Mahadasha starts at the birth instant itself and the table's
    first boundary is that instant. The two births are one hour apart in UTC
    and share the local wall time ``01:30:00`` -- only the offset tells them
    apart, which is what section 3(a) says it is for.
    """
    line = build_vimshottari(0.0, birth_utc, YearConvention.FIXED_365_25)
    text = render_dasha_text(line, zone="Europe/London", depth=1)
    first = body_lines(text)[0]

    assert line.cycle_start_utc == birth_utc
    assert f"2023-10-29 01:30:00{expected_offset}" in first
    parsed = datetime.fromisoformat(printed_stamps(first)[:25].strip())
    assert parsed.astimezone(UTC) == birth_utc


def test_the_two_london_renderings_differ_only_in_the_offset():
    texts = [
        body_lines(
            render_dasha_text(
                build_vimshottari(0.0, moment, YearConvention.FIXED_365_25),
                zone="Europe/London",
                depth=1,
            )
        )[0]
        for moment in (
            datetime(2023, 10, 29, 0, 30, tzinfo=UTC),
            datetime(2023, 10, 29, 1, 30, tzinfo=UTC),
        )
    ]

    assert texts[0] != texts[1]
    assert all("2023-10-29 01:30:00" in text for text in texts)


# --- the balance line ------------------------------------------------------


def balance_line(text):
    return next(
        line for line in text.splitlines() if line.startswith("Nominal balance")
    )


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_balance_line_is_the_integer_truncation_rule(name, convention):
    line = timeline(name, convention)
    balance = line.balance_years
    scaled = balance.numerator * 10**9 // balance.denominator

    text = balance_line(render_dasha_text(line, zone=KOLKATA, depth=1))

    assert text == (
        "Nominal balance of the first Mahadasha at birth: "
        f"{balance.numerator}/{balance.denominator} = "
        f"{scaled // 10**9}.{scaled % 10**9:09d} years "
        "(nominal; decimal truncated to 9 places)"
    )
    # Truncation toward zero, never rounding: the printed decimal is never
    # larger than the exact value.
    assert Fraction(scaled, 10**9) <= balance


def test_a_sub_microsecond_balance_prints_nine_zeros():
    """``nextafter(40.0, 0)``: a balance of 6/2**51 years is not rounded up."""
    line = divergence_timeline(NEXT_AFTER_FORTY)

    text = balance_line(render_dasha_text(line, zone=KOLKATA, depth=1))

    assert line.balance_years == Fraction(6, 2**51)
    assert text.endswith(
        "3/1125899906842624 = 0.000000000 years "
        "(nominal; decimal truncated to 9 places)"
    )


def test_an_exact_balance_prints_its_whole_years():
    """Longitude 0.0: Ketu's full seven years, with nothing elapsed."""
    line = build_vimshottari(0.0, SYNTHETIC_BIRTH, YearConvention.FIXED_365_25)

    text = balance_line(render_dasha_text(line, zone="UTC", depth=1))

    assert line.balance_years == Fraction(7)
    assert "7/1 = 7.000000000 years" in text


# --- header and shape ------------------------------------------------------


@pytest.mark.parametrize("depth", DEPTHS)
@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_header_carries_no_pada(name, depth):
    """The timeline has no pada field, so the table invents none."""
    text = rendered(name, YearConvention.FIXED_365_25, depth, "second")

    assert "pada" not in text.lower()


@pytest.mark.parametrize(
    "convention, days",
    [
        (YearConvention.FIXED_365_25, "365.25"),
        (YearConvention.FIXED_365_256363, "365.256363"),
    ],
)
@pytest.mark.parametrize("depth, word", [(1, "md"), (2, "md-ad"), (3, "md-ad-pd")])
def test_the_header_states_the_year_the_zone_and_the_depth(
    convention, days, depth, word
):
    text = rendered("jammu", convention, depth, "second")
    second = text.splitlines()[1]

    assert f"year {days} days" in second
    assert second.endswith(f"depth {word}")
    assert f"({KOLKATA})" in second


@pytest.mark.parametrize("precision", PRECISIONS)
@pytest.mark.parametrize("depth", DEPTHS)
@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_text_ends_with_exactly_one_newline(name, depth, precision):
    text = rendered(name, YearConvention.FIXED_365_25, depth, precision)

    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert len(body_lines(text)) == ROW_COUNTS[depth]


def test_the_birth_row_is_the_only_one_carrying_both_marks():
    text = rendered("jalandhar", YearConvention.FIXED_365_25, 3, "second")
    marks = [line for line in body_lines(text) if line.endswith("N  Q")]

    assert len(marks) == 3
    assert [line[:2] for line in marks] == ["MD", "AD", "PD"]


def test_a_zone_other_than_the_birthplace_changes_only_the_presentation():
    line = timeline("jalandhar", YearConvention.FIXED_365_25)

    in_kolkata = render_dasha_text(line, zone=KOLKATA, depth=1)
    in_utc = render_dasha_text(line, zone="UTC", depth=1)

    assert in_kolkata != in_utc
    assert "+05:30" in in_kolkata and "+00:00" in in_utc
    assert dasha_rows(line, depth=1) == dasha_rows(line, depth=1)
    assert in_utc.count("\n") == in_kolkata.count("\n")


# --- conversion overflow ---------------------------------------------------
#
# Synthetic *presentation* fixtures: these timelines are built by the test, not
# by the core, and exist only to place a boundary where a zone conversion
# cannot be done. They say nothing about dasha arithmetic.


def synthetic_timeline(start_utc, end_utc, birth_utc):
    """A one-period-per-level fake timeline spanning the birth.

    ``periods_at_birth`` and ``active_periods_at`` stop at the first period
    containing the birth at each level, so one child per level is enough for
    both queries to answer.
    """
    def period(level, lords, children):
        return DashaPeriod(
            level=level,
            lords=lords,
            nominal_years=Fraction(2),
            nominal_start=Fraction(-1),
            nominal_end=Fraction(1),
            start_utc=start_utc,
            end_utc=end_utc,
            children=children,
        )

    pratyantar = period(3, (Graha.KETU, Graha.KETU, Graha.KETU), ())
    antardasha = period(2, (Graha.KETU, Graha.KETU), (pratyantar,))
    mahadasha = period(1, (Graha.KETU,), (antardasha,))
    return VimshottariTimeline(
        birth_utc=birth_utc,
        year=YearConvention.FIXED_365_25,
        moon_sidereal_longitude=0.0,
        normalized_longitude=0.0,
        nakshatra_index=0,
        nakshatra_number=1,
        nakshatra_name="Ashwini",
        lord=Graha.KETU,
        elapsed_fraction=Fraction(0),
        remaining_fraction=Fraction(1),
        elapsed_years=Fraction(0),
        balance_years=Fraction(7),
        cycle_start_utc=start_utc,
        cycle_end_utc=end_utc,
        mahadashas=(mahadasha,),
    )


def at_the_upper_limit():
    return synthetic_timeline(
        start_utc=datetime(9999, 1, 1, tzinfo=UTC),
        end_utc=datetime.max.replace(tzinfo=UTC),
        birth_utc=datetime(9999, 6, 1, tzinfo=UTC),
    )


def at_the_lower_limit():
    return synthetic_timeline(
        start_utc=datetime.min.replace(tzinfo=UTC),
        end_utc=datetime(1, 6, 1, tzinfo=UTC),
        birth_utc=datetime(1, 3, 1, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    "builder, zone",
    [
        (at_the_upper_limit, KOLKATA),            # positive offset, overflow
        (at_the_lower_limit, "America/Los_Angeles"),  # negative, underflow
    ],
)
@pytest.mark.parametrize("depth", DEPTHS)
def test_a_conversion_at_the_datetime_limit_is_a_dasha_range_error(
    builder, zone, depth
):
    line = builder()

    with pytest.raises(DashaRangeError) as caught:
        render_dasha_text(line, zone=zone, depth=depth)

    assert zone in str(caught.value)
    assert isinstance(caught.value.__cause__, OverflowError)
    assert isinstance(caught.value, ValueError)


@pytest.mark.parametrize(
    "builder, zone",
    [(at_the_upper_limit, KOLKATA), (at_the_lower_limit, "America/Los_Angeles")],
)
def test_no_overflow_error_escapes_the_table(builder, zone):
    try:
        render_dasha_text(builder(), zone=zone, depth=1)
    except DashaRangeError:
        pass
    except OverflowError:  # pragma: no cover - the failure this test forbids
        pytest.fail("an OverflowError escaped the table")


@pytest.mark.parametrize("builder", [at_the_upper_limit, at_the_lower_limit])
def test_the_rows_at_the_limits_need_no_conversion_and_succeed(builder):
    """Rows carry UTC instants, so the limit only bites at presentation time."""
    rows = dasha_rows(builder(), depth=3)

    assert [row.level for row in rows] == [1, 2, 3]
    assert all(row.in_nominal_birth_chain for row in rows)
    assert all(row.in_quantized_birth_chain for row in rows)


@pytest.mark.parametrize(
    "builder, zone",
    [(at_the_upper_limit, "UTC"), (at_the_lower_limit, "UTC")],
)
def test_the_same_limits_render_in_utc(builder, zone):
    """UTC has a zero offset, so nothing overflows: the refusal is the zone's."""
    text = render_dasha_text(builder(), zone=zone, depth=1)

    assert len(body_lines(text)) == 1
    assert "+00:00" in text


# --- the Birth line is independent of the row precision --------------------


@pytest.mark.parametrize("name", ["jalandhar", "jammu"])
@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("depth", [1, 2, 3])
def test_the_birth_line_keeps_seconds_and_offset_at_day_precision(
    name, convention, depth
):
    """``precision`` governs the period rows only.

    The Birth line is the anchor every row is measured from; printing it as a
    bare date would throw away the one timestamp the reader most needs, and
    the exact UTC offset with it.
    """
    line = timeline(name, convention)
    second_text = render_dasha_text(
        line, zone=KOLKATA, depth=depth, precision="second"
    )
    day_text = render_dasha_text(
        line, zone=KOLKATA, depth=depth, precision="day"
    )
    birth_second = second_text.splitlines()[1]
    birth_day = day_text.splitlines()[1]

    expected = line.birth_utc.astimezone(ZoneInfo(KOLKATA)).replace(
        microsecond=0
    ).isoformat(sep=" ", timespec="seconds")
    assert birth_second.startswith(f"Birth {expected} ({KOLKATA})")
    assert birth_day.startswith(f"Birth {expected} ({KOLKATA})")
    assert DAY_WARNING in day_text.splitlines()
    for body in body_lines(day_text):
        assert ":" not in body
