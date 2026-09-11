"""Layer 12's chart adapter (specification section 10, "Adapter").

Self-contained in the same sense as the Layer 11 tests: the birthplace comes
from the committed fixture geodata database or from an explicit
``ResolvedLocation``, the positions from the committed ``ephe/`` directory, and
nothing here needs the 150 MB production database or a network.

Two real births are used, and both are pinned by their *engine* Moon
longitude rather than by a rounded degree, because the whole point of the
adapter is that the dasha is a function of that double and the birth instant
and of nothing else. Jammu is not in the fixture database, so it is built from
its recorded coordinates through a fixed resolver -- the case is defined by
those coordinates, not by a name lookup.
"""

import dataclasses
from datetime import datetime, timedelta, timezone
from fractions import Fraction

import pytest

from render_helpers import EPHE_DIR, FIXTURE_DB, FixedResolver
from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.chart.assemble import assemble_chart
from vedic_chart.dasha import YearConvention, build_vimshottari
from vedic_chart.dasha.from_chart import vimshottari_from_chart
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.model import ResolvedLocation
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.vedic.grahas import Graha

CONVENTIONS = tuple(YearConvention)
IST = timezone(timedelta(hours=5, minutes=30))

#: The frozen engine's Moon longitudes for the two reference births
#: (specification section 9). Asserted, not assumed: if an upstream layer ever
#: moved, every reference number in this milestone would move with it.
JALANDHAR_MOON = 209.20440791222882
JAMMU_MOON = 54.892295957053236

JAMMU_LOCATION = ResolvedLocation(
    canonical_name="Jammu, Jammu and Kashmir, India",
    latitude=32.73528,
    longitude=74.86167,
    timezone_id="Asia/Kolkata",
)

_CHART_CACHE = {}


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


BUILDERS = {"jalandhar": jalandhar_chart, "jammu": jammu_chart}
EXPECTED_MOON = {"jalandhar": JALANDHAR_MOON, "jammu": JAMMU_MOON}
EXPECTED_UTC = {
    "jalandhar": datetime(1995, 3, 21, 1, 15, tzinfo=timezone.utc),
    "jammu": datetime(2001, 2, 4, 5, 15, tzinfo=timezone.utc),
}
CASE_NAMES = tuple(BUILDERS)


def chart(name):
    """Built once: an ephemeris run per parametrised case would dominate."""
    if name not in _CHART_CACHE:
        _CHART_CACHE[name] = BUILDERS[name]()
    return _CHART_CACHE[name]


def with_moon_nakshatra(base, index):
    """A test double: the same chart with the Moon's stored index changed.

    Only ``nakshatra_index`` moves. The longitude is left alone, so the chart
    now contradicts itself in exactly the way decision D1 says cannot happen,
    which is what the adapter's cross-check exists to catch.
    """
    moon = base.grahas[Graha.MOON]
    placement = dataclasses.replace(moon.placement, nakshatra_index=index)
    grahas = dict(base.grahas)
    grahas[Graha.MOON] = dataclasses.replace(moon, placement=placement)
    return dataclasses.replace(base, grahas=grahas)


# --- the two inputs the adapter is allowed to read -------------------------


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_reference_charts_carry_the_recorded_moon(name):
    built = chart(name)
    moon = built.grahas[Graha.MOON]

    assert moon.sidereal_longitude == EXPECTED_MOON[name]
    assert built.moment_utc == EXPECTED_UTC[name]
    assert built.moment_utc.utcoffset() == timedelta(0)


def test_the_jammu_chart_uses_the_recorded_coordinates():
    built = chart("jammu")

    assert built.location == JAMMU_LOCATION
    assert built.request.place_query == "Jammu, Jammu and Kashmir, India"
    assert built.moment_utc.astimezone(IST) == datetime(
        2001, 2, 4, 10, 45, tzinfo=IST
    )


# --- the adapter forwards, and computes nothing ----------------------------


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_adapter_equals_the_core_on_the_extracted_values(name, convention):
    built = chart(name)

    from_adapter = vimshottari_from_chart(built, convention)
    from_core = build_vimshottari(
        built.grahas[Graha.MOON].sidereal_longitude,
        built.moment_utc,
        convention,
    )

    assert from_adapter == from_core
    assert from_adapter.moon_sidereal_longitude == EXPECTED_MOON[name]
    assert from_adapter.birth_utc == EXPECTED_UTC[name]
    assert from_adapter.nakshatra_index == (
        built.grahas[Graha.MOON].placement.nakshatra_index
    )
    assert from_adapter.nakshatra_name == (
        built.grahas[Graha.MOON].placement.nakshatra_name
    )


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_adapter_reproduces_the_reference_balances(name):
    expected = {
        "jalandhar": (
            Graha.JUPITER,
            Fraction(87164189005907, 17592186044416),
            (Graha.JUPITER, Graha.SUN, Graha.MERCURY),
        ),
        "jammu": (
            Graha.MARS,
            Fraction(6959800514669247, 1125899906842624),
            (Graha.MARS, Graha.RAHU, Graha.SATURN),
        ),
    }[name]
    line = vimshottari_from_chart(chart(name), YearConvention.FIXED_365_25)

    assert line.lord is expected[0]
    assert line.balance_years == expected[1]
    assert tuple(p.lord for p in line.periods_at_birth()) == expected[2]


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_adapter_ignores_everything_but_the_moon_and_the_instant(name):
    """Rewriting the parts of the chart it may not read changes nothing."""
    built = chart(name)
    elsewhere = dataclasses.replace(
        built,
        location=ResolvedLocation("Nowhere, Testland", -45.0, 170.0, "UTC"),
        julian_day_ut=0.0,
        ayanamsa=0.0,
    )

    assert vimshottari_from_chart(
        elsewhere, YearConvention.FIXED_365_25
    ) == vimshottari_from_chart(built, YearConvention.FIXED_365_25)


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_adapter_requires_a_year_convention(name):
    with pytest.raises(TypeError):
        vimshottari_from_chart(chart(name))
    with pytest.raises(TypeError):
        vimshottari_from_chart(chart(name), "FIXED_365_25")


# --- the cross-check -------------------------------------------------------


@pytest.mark.parametrize("name", CASE_NAMES)
def test_a_tampered_moon_placement_is_an_internal_error(name):
    built = chart(name)
    recorded = built.grahas[Graha.MOON].placement.nakshatra_index

    for wrong in ((recorded + 1) % 27, (recorded + 13) % 27, 0 if recorded else 26):
        if wrong == recorded:
            continue
        with pytest.raises(RuntimeError, match="nakshatra index"):
            vimshottari_from_chart(
                with_moon_nakshatra(built, wrong), YearConvention.FIXED_365_25
            )


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_cross_check_passes_for_the_untampered_chart(name):
    """The double really is a double: restoring the index restores the pass."""
    built = chart(name)
    recorded = built.grahas[Graha.MOON].placement.nakshatra_index
    restored = with_moon_nakshatra(built, recorded)

    assert vimshottari_from_chart(
        restored, YearConvention.FIXED_365_25
    ) == vimshottari_from_chart(built, YearConvention.FIXED_365_25)


# --- the cross-check reads the timeline the core returned ------------------


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_adapter_calls_the_core_once_and_returns_its_timeline(
    monkeypatch, name
):
    """One build, and the object handed back is the one the core produced."""
    import vedic_chart.dasha.from_chart as adapter_module

    built = chart(name)
    calls = []
    real_build = adapter_module.build_vimshottari

    def spy(longitude, birth_utc, year):
        calls.append((longitude, birth_utc, year))
        return real_build(longitude, birth_utc, year)

    monkeypatch.setattr(adapter_module, "build_vimshottari", spy)

    line = vimshottari_from_chart(built, YearConvention.FIXED_365_256363)

    assert calls == [
        (
            built.grahas[Graha.MOON].sidereal_longitude,
            built.moment_utc,
            YearConvention.FIXED_365_256363,
        )
    ]
    assert line == real_build(*calls[0])


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_cross_check_uses_the_returned_timelines_index(monkeypatch, name):
    """Tampering with the *timeline* the core returns trips the same check.

    The chart is untouched here. If the adapter re-derived the index itself
    instead of reading ``timeline.nakshatra_index``, this would pass silently.
    """
    import vedic_chart.dasha.from_chart as adapter_module

    built = chart(name)
    recorded = built.grahas[Graha.MOON].placement.nakshatra_index
    real_build = adapter_module.build_vimshottari

    def tampered_build(longitude, birth_utc, year):
        line = real_build(longitude, birth_utc, year)
        return dataclasses.replace(line, nakshatra_index=(recorded + 1) % 27)

    monkeypatch.setattr(adapter_module, "build_vimshottari", tampered_build)

    with pytest.raises(RuntimeError, match="nakshatra index"):
        vimshottari_from_chart(built, YearConvention.FIXED_365_25)


def test_the_adapter_does_not_classify_on_its_own():
    """No private classifier is imported or referenced by the adapter."""
    import ast
    import inspect

    import vedic_chart.dasha.from_chart as adapter_module

    tree = ast.parse(inspect.getsource(adapter_module))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    referenced = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }

    assert "_classify_moon" not in imported
    assert "_classify_moon" not in referenced
    assert "build_vimshottari" in imported
