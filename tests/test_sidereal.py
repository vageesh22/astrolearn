"""Tests for the Layer 6 sidereal conversion."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from vedic_chart.astronomy.positions import Body, calculate_positions, ephemeris_session
from vedic_chart.ephemeris.swiss_ephemeris import get_ayanamsa_lahiri
from vedic_chart.time.julian_day import julian_day_ut
from vedic_chart.sidereal.positions import (
    calculate_sidereal_positions,
    sidereal_longitude,
)

EPHE_DIR = str(Path(__file__).resolve().parent.parent / "ephe")

J2000_UTC = datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)
Y1900_UTC = datetime(1900, 1, 1, 0, 0, tzinfo=timezone.utc)
Y2024_UTC = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def ephemeris():
    with ephemeris_session(EPHE_DIR):
        yield


def ayanamsa_at(moment):
    return get_ayanamsa_lahiri(julian_day_ut(moment))


def test_sidereal_longitude_wraps():
    assert sidereal_longitude(10.0, 24.0) == pytest.approx(346.0)


def test_ayanamsa_j2000_matches_published_value(ephemeris):
    # Published (true-equinox, nutation-included) Lahiri ayanamsha at
    # 2000-01-01 is 23 deg 51' 12" (Jagannatha Hora tables) = 23.85333.
    assert abs(ayanamsa_at(J2000_UTC) - 23.85333) < 0.002


def test_ayanamsa_1900_matches_published_value(ephemeris):
    # Published (true-equinox) Lahiri ayanamsha at 1900-01-01 is
    # 22 deg 27' 55" (Jagannatha Hora tables) = 22.46528.
    assert abs(ayanamsa_at(Y1900_UTC) - 22.46528) < 0.002


def test_ayanamsa_increases_with_precession(ephemeris):
    ayanamsa_1900 = ayanamsa_at(Y1900_UTC)
    ayanamsa_2000 = ayanamsa_at(J2000_UTC)
    ayanamsa_2024 = ayanamsa_at(Y2024_UTC)

    assert ayanamsa_1900 < ayanamsa_2000 < ayanamsa_2024

    # 24 years of precession at about 50.3 arcsec/yr is about 0.335 deg.
    assert 0.30 < ayanamsa_2024 - ayanamsa_2000 < 0.37


def test_all_bodies_present(ephemeris):
    result = calculate_sidereal_positions(J2000_UTC)

    assert set(result.bodies) == set(Body)
    assert len(result.bodies) == 9
    assert Body.MEAN_NODE in result.bodies
    assert Body.TRUE_NODE in result.bodies


def test_sidereal_longitudes_are_consistent(ephemeris):
    result = calculate_sidereal_positions(J2000_UTC)

    for body, entry in result.bodies.items():
        expected = (entry.tropical.longitude - result.ayanamsa) % 360.0
        assert entry.sidereal_longitude == pytest.approx(expected, abs=1e-9), body
        assert 0.0 <= entry.sidereal_longitude < 360.0, body


def test_tropical_data_is_preserved(ephemeris):
    result = calculate_sidereal_positions(J2000_UTC)
    tropical = calculate_positions(J2000_UTC)

    for body, entry in result.bodies.items():
        assert entry.tropical == tropical[body], body


def test_sun_sidereal_longitude(ephemeris):
    result = calculate_sidereal_positions(J2000_UTC)

    # Tropical Sun 280.369 deg minus the J2000 ayanamsha; equals Swiss
    # Ephemeris' native SEFLG_SIDEREAL Lahiri value 256.515696.
    assert abs(result.bodies[Body.SUN].sidereal_longitude - 256.515696) < 0.0005
