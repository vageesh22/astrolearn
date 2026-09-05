"""Tests for the Layer 5 Swiss Ephemeris boundary."""

import tempfile
from pathlib import Path

import pytest

from vedic_chart.ephemeris.swiss_ephemeris import (
    SUN,
    calc_planet_position,
    close_ephemeris,
    get_version,
    init_ephemeris,
)

EPHE_DIR = str(Path(__file__).resolve().parent.parent / "ephe")

# 2000-01-01 12:00 TT, the J2000.0 epoch.
J2000 = 2451545.0


@pytest.fixture(autouse=True)
def ephemeris():
    init_ephemeris(EPHE_DIR)
    yield
    close_ephemeris()


def test_version():
    version = get_version()
    assert isinstance(version, str)
    assert version != ""


def test_sun_position_j2000():
    position = calc_planet_position(J2000, SUN)

    assert 0.0 <= position.longitude < 360.0
    assert 279.0 <= position.longitude <= 282.0
    assert abs(position.speed_longitude - 1.0) <= 0.1
    assert 0.98 < position.distance_au < 1.0


def test_uses_swiss_ephemeris_files_not_moshier():
    # With the real .se1 files present the guard must not fire.
    calc_planet_position(J2000, SUN)

    # With an empty ephemeris directory the library would silently fall back
    # to Moshier; the guard must turn that into a RuntimeError.
    with tempfile.TemporaryDirectory() as empty_dir:
        close_ephemeris()
        init_ephemeris(empty_dir)
        try:
            with pytest.raises(RuntimeError):
                calc_planet_position(J2000, SUN)
        finally:
            close_ephemeris()
            init_ephemeris(EPHE_DIR)

    # The good path is restored and calculations work again.
    calc_planet_position(J2000, SUN)


# --- Lahiri ayanamsha reference frame (Core Engine Audit OPEN-1, 2026-09-05) ---

import swisseph as swe  # tests may touch the library directly; src may not

from vedic_chart.ephemeris.swiss_ephemeris import get_ayanamsa_lahiri

REPRESENTATIVE_JDS = (
    2415020.5,          # 1900-01-01 00:00 UT
    2433282.5,          # 1950-01-01
    2451545.0,          # J2000
    2449797.5520833335, # the Jalandhar reference chart instant
    2460311.0416666665, # 2024-01-01 13:00 UT
)


def test_lahiri_accessor_is_the_true_equinox_value():
    """Our accessor must equal swe.get_ayanamsa_ex_ut(jd, 0) exactly."""
    for jd in REPRESENTATIVE_JDS:
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        _flags, expected = swe.get_ayanamsa_ex_ut(jd, 0)
        assert get_ayanamsa_lahiri(jd) == expected, jd


def test_lahiri_accessor_is_not_the_legacy_mean_equinox_value():
    """The legacy get_ayanamsa_ut (mean equinox) is intentionally NOT used.

    The two differ by the nutation in longitude, which is never exactly zero
    at these instants and stays below ~17 arcseconds.
    """
    for jd in REPRESENTATIVE_JDS:
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        legacy = swe.get_ayanamsa_ut(jd)
        ours = get_ayanamsa_lahiri(jd)
        assert ours != legacy, jd
        assert abs(ours - legacy) * 3600 < 18.0, jd
        assert legacy == swe.get_ayanamsa_ex_ut(jd, swe.FLG_NONUT)[1], jd


def test_engine_sidereal_matches_swiss_ephemeris_native_sidereal():
    """tropical(true equinox) - ayanamsha(true equinox) == SEFLG_SIDEREAL output."""
    from vedic_chart.ephemeris.swiss_ephemeris import MOON, SUN, calc_planet_position
    for jd in REPRESENTATIVE_JDS:
        ayanamsa = get_ayanamsa_lahiri(jd)
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        for body in (SUN, MOON):
            ours = (calc_planet_position(jd, body).longitude - ayanamsa) % 360.0
            native = swe.calc_ut(jd, body, swe.FLG_SWIEPH | swe.FLG_SPEED | swe.FLG_SIDEREAL)[0][0]
            assert abs(((ours - native) + 180.0) % 360.0 - 180.0) * 3600 < 0.01, (jd, body)
