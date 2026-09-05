"""Tests for the Layer 7 graha derivation."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from vedic_chart.astronomy.positions import Body, ephemeris_session
from vedic_chart.sidereal.positions import calculate_sidereal_positions
from vedic_chart.vedic.divisions import classify
from vedic_chart.vedic.grahas import Graha, derive_grahas

EPHE_DIR = str(Path(__file__).resolve().parent.parent / "ephe")

J2000_UTC = datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)
Y2024_UTC = datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc)


@pytest.fixture
def ephemeris():
    with ephemeris_session(EPHE_DIR):
        yield


@pytest.fixture
def j2000(ephemeris):
    return calculate_sidereal_positions(J2000_UTC)


def test_all_nine_grahas_present(j2000):
    grahas = derive_grahas(j2000)

    assert set(grahas) == set(Graha)
    assert len(grahas) == 9
    assert list(grahas) == list(Graha)


def test_rahu_is_the_mean_node(j2000):
    grahas = derive_grahas(j2000)

    mean_node = j2000.bodies[Body.MEAN_NODE]
    assert grahas[Graha.RAHU].sidereal_longitude == mean_node.sidereal_longitude
    assert (
        grahas[Graha.RAHU].speed_longitude
        == mean_node.tropical.speed_longitude
    )


def test_true_node_is_not_used(j2000):
    grahas = derive_grahas(j2000)

    true_node = j2000.bodies[Body.TRUE_NODE].sidereal_longitude
    # The two nodes differ by about a degree at this epoch, so this would catch
    # the true node being wired in by mistake.
    assert grahas[Graha.RAHU].sidereal_longitude != true_node
    assert abs(grahas[Graha.RAHU].sidereal_longitude - true_node) > 0.5


def test_ketu_is_opposite_rahu(j2000):
    grahas = derive_grahas(j2000)

    rahu = grahas[Graha.RAHU]
    ketu = grahas[Graha.KETU]

    assert ketu.sidereal_longitude == (rahu.sidereal_longitude + 180.0) % 360.0
    assert ketu.speed_longitude == rahu.speed_longitude
    assert 0.0 <= ketu.sidereal_longitude < 360.0


def test_nodes_are_retrograde_and_luminaries_are_not(j2000):
    grahas = derive_grahas(j2000)

    assert grahas[Graha.RAHU].is_retrograde is True
    assert grahas[Graha.KETU].is_retrograde is True
    assert grahas[Graha.SUN].is_retrograde is False
    assert grahas[Graha.MOON].is_retrograde is False


def test_retrograde_flag_follows_the_raw_speed(j2000):
    grahas = derive_grahas(j2000)

    for graha, position in grahas.items():
        assert position.is_retrograde == (position.speed_longitude < 0.0), graha


def test_known_placements_at_j2000(j2000):
    grahas = derive_grahas(j2000)

    sun = grahas[Graha.SUN]
    assert sun.sidereal_longitude == pytest.approx(256.5157, abs=1e-3)  # true-equinox Lahiri (OPEN-1 resolved 2026-09-05)
    assert sun.placement.rashi_name == "Dhanu"
    assert sun.placement.nakshatra_name == "Purva Ashadha"

    moon = grahas[Graha.MOON]
    assert moon.sidereal_longitude == pytest.approx(199.4705, abs=1e-3)  # true-equinox Lahiri (OPEN-1 resolved 2026-09-05)
    assert moon.placement.rashi_name == "Tula"
    assert moon.placement.nakshatra_name == "Swati"


def test_placement_matches_direct_classification(j2000):
    grahas = derive_grahas(j2000)

    for graha, position in grahas.items():
        assert position.placement == classify(position.sidereal_longitude), graha


def test_direct_motion_on_a_second_date(ephemeris):
    grahas = derive_grahas(calculate_sidereal_positions(Y2024_UTC))

    # Saturn is in direct motion at this instant, so the flag must not be
    # keyed to the planet's identity.
    assert grahas[Graha.SATURN].speed_longitude > 0.0
    assert grahas[Graha.SATURN].is_retrograde is False

    for graha in (Graha.SUN, Graha.MOON, Graha.MARS):
        assert grahas[graha].is_retrograde is False, graha

    # Rahu stays retrograde because it is the Mean Node, whose motion is
    # uniformly negative -- a consequence of rule 1, not a hardcoded flag.
    assert grahas[Graha.RAHU].is_retrograde is True
    assert grahas[Graha.KETU].is_retrograde is True
