"""Tests for the astronomical position API."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from vedic_chart.astronomy.positions import (
    Body,
    calculate_positions,
    ephemeris_session,
)

EPHE_DIR = str(Path(__file__).resolve().parent.parent / "ephe")

J2000_UTC = datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def positions():
    with ephemeris_session(EPHE_DIR):
        yield calculate_positions(J2000_UTC)


def test_all_bodies_present(positions):
    assert set(positions) == set(Body)
    assert len(positions) == 9


def test_longitudes_in_range(positions):
    for body, position in positions.items():
        assert 0.0 <= position.longitude < 360.0, body


def test_sun_longitude(positions):
    assert 279.0 <= positions[Body.SUN].longitude <= 282.0


def test_moon_speed(positions):
    assert 11.0 < positions[Body.MOON].speed_longitude < 15.0


def test_mean_node_moves_backwards(positions):
    assert positions[Body.MEAN_NODE].speed_longitude < 0.0


def test_nodes_agree(positions):
    mean = positions[Body.MEAN_NODE].longitude
    true = positions[Body.TRUE_NODE].longitude
    separation = abs((mean - true + 180.0) % 360.0 - 180.0)
    assert separation < 2.0


def test_naive_datetime_rejected():
    with ephemeris_session(EPHE_DIR):
        with pytest.raises(ValueError):
            calculate_positions(datetime(2000, 1, 1, 12, 0))
