"""Independent verification suite (Core Engine Audit, 2026-09-05).

Runs the diverse birth cases defined in tools/audit/verification_cases.py and
asserts INTERNAL-CONSISTENCY invariants on every produced chart, plus the few
externally anchored facts that were already verified in earlier milestones
(historical tzdata offsets, the Jalandhar reference Lagna). It hardcodes no
other external truths.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "audit"))

import verification_cases as vc  # noqa: E402
from vedic_chart.astronomy.positions import Body, ephemeris_session  # noqa: E402
from vedic_chart.chart.model import BirthChart  # noqa: E402
from vedic_chart.location.offline.resolver import OfflineLocationResolver  # noqa: E402
from vedic_chart.time.local_time import NonexistentLocalTimeError  # noqa: E402
from vedic_chart.vedic.divisions import classify  # noqa: E402
from vedic_chart.vedic.grahas import Graha  # noqa: E402


@pytest.fixture(scope="module")
def results():
    with ephemeris_session(vc.EPHE_DIR), OfflineLocationResolver(vc.FIXTURE_DB) as fixture:
        cases = vc.build_cases()
        return {case.key: (case, vc.run_case(case, fixture)) for case in cases}


CHART_KEYS = ["V01", "V02", "V04", "V05", "V06a", "V06b", "V07", "V08a", "V08b", "V09a", "V09b", "V10"]


def _chart(results, key) -> BirthChart:
    case, result = results[key]
    assert not isinstance(result, Exception), f"{key} unexpectedly failed: {result!r}"
    return result


@pytest.mark.parametrize("key", CHART_KEYS)
def test_invariants_hold_for_every_chart(results, key):
    chart = _chart(results, key)

    assert chart.moment_utc.tzinfo is timezone.utc
    ZoneInfo(chart.location.timezone_id)  # valid IANA id
    assert not chart.location.timezone_id.startswith("Etc/")

    rahu, ketu = chart.grahas[Graha.RAHU], chart.grahas[Graha.KETU]
    assert ketu.sidereal_longitude == (rahu.sidereal_longitude + 180.0) % 360.0
    assert ketu.speed_longitude == rahu.speed_longitude
    assert rahu.is_retrograde and ketu.is_retrograde  # mean node: uniformly negative

    lagna_idx = chart.lagna.placement.rashi_index
    assert chart.lagna.placement == classify(chart.lagna.sidereal_longitude)
    for graha, position in chart.grahas.items():
        assert 0.0 <= position.sidereal_longitude < 360.0
        assert position.placement == classify(position.sidereal_longitude)
        assert chart.houses[graha] == (position.placement.rashi_index - lagna_idx) % 12 + 1
        assert position.is_retrograde == (position.speed_longitude < 0.0)
    assert chart.lagna.sidereal_longitude == (chart.lagna.tropical_longitude - chart.ayanamsa) % 360.0
    assert chart.lagna.ayanamsa == chart.ayanamsa


def test_v01_reference_lagna_is_unchanged(results):
    chart = _chart(results, "V01")
    assert chart.lagna.sidereal_longitude == pytest.approx(339.795911, abs=1e-4)  # true-equinox Lahiri (OPEN-1 resolved 2026-09-05)
    assert chart.lagna.placement.rashi_name == "Meena"
    assert chart.houses[Graha.SUN] == 1 and chart.houses[Graha.MOON] == 8


def test_v03_dst_gap_is_rejected(results):
    case, result = results["V03"]
    assert case.expect_error is NonexistentLocalTimeError
    assert isinstance(result, NonexistentLocalTimeError)


def test_v04_v05_v10_historical_offsets_from_tzdata(results):
    # Anchored in the Layer 3 milestone against the installed tzdata.
    assert _chart(results, "V04").moment_utc == datetime(1943, 7, 15, 10, 0, tzinfo=timezone.utc)   # BDST +02:00
    assert _chart(results, "V05").moment_utc == datetime(1943, 1, 1, 5, 30, tzinfo=timezone.utc)    # +06:30
    assert _chart(results, "V10").moment_utc == datetime(1840, 5, 10, 8, 1, 15, tzinfo=timezone.utc)  # LMT -00:01:15


def test_v06_date_line_pair_shares_one_instant(results):
    a, b = _chart(results, "V06a"), _chart(results, "V06b")
    assert a.request.birth_date != b.request.birth_date
    assert a.moment_utc == b.moment_utc and a.julian_day_ut == b.julian_day_ut
    assert a.ayanamsa == b.ayanamsa
    for graha in Graha:
        assert a.grahas[graha] == b.grahas[graha]
    assert a.lagna.sidereal_longitude != b.lagna.sidereal_longitude  # different longitude on Earth


def test_v07_high_latitude_lagna_is_classifiable(results):
    chart = _chart(results, "V07")
    assert chart.location.latitude > 66.5
    assert 0 <= chart.lagna.placement.rashi_index <= 11


def test_v08_boundary_hugging_sun_classifies_by_unrounded_value(results):
    before, after = _chart(results, "V08a"), _chart(results, "V08b")
    sb, sa = before.grahas[Graha.SUN], after.grahas[Graha.SUN]
    assert sb.sidereal_longitude > 359.99 and sb.placement.rashi_name == "Meena"
    assert sa.sidereal_longitude < 0.01 and sa.placement.rashi_name == "Mesha"
    assert sb.placement.nakshatra_name == "Revati" and sa.placement.nakshatra_name == "Ashwini"
    # Same sign for everything else; only the Sun's house changes, by exactly one.
    assert after.houses[Graha.SUN] == before.houses[Graha.SUN] + 1


def test_v09_station_flips_retrograde_on_speed_sign(results):
    before, after = _chart(results, "V09a"), _chart(results, "V09b")
    mb, ma = before.grahas[Graha.MERCURY], after.grahas[Graha.MERCURY]
    assert abs(mb.speed_longitude) < 1e-3 and abs(ma.speed_longitude) < 1e-3
    assert mb.speed_longitude > 0 > ma.speed_longitude
    assert mb.is_retrograde is False and ma.is_retrograde is True


def test_case_document_is_in_sync(results):
    doc = (ROOT / "docs" / "verification_cases.md").read_text(encoding="utf-8")
    for key in results:
        assert f"## {key} —" in doc, f"docs/verification_cases.md lacks {key}; regenerate it"
