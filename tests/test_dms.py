"""Tests for Layer 9 display derivation (degrees/minutes/seconds).

A DMS value is display data and nothing else. The policy under test is
truncation toward zero at every stage: no stage rounds, so no stage can carry a
displayed value across a division boundary the authoritative value never
crossed.
"""

import dataclasses

import pytest

from vedic_chart.representation.dms import DMS, to_dms


# --- truncation ------------------------------------------------------------


def test_zero_degrees():
    assert to_dms(0.0) == DMS(0, 0, 0.0)


def test_truncates_seconds_to_two_decimals():
    result = to_dms(13.788209, 2)

    assert (result.degrees, result.minutes, result.seconds) == (13, 47, 17.55)


def test_truncates_seconds_to_whole_seconds_by_default():
    result = to_dms(13.788209)

    assert (result.degrees, result.minutes, result.seconds) == (13, 47, 17.0)


def test_never_carries_into_the_next_degree():
    """29.999999 deg must display as 29 deg 59' 59", never as 30 deg."""
    result = to_dms(29.999999)

    assert (result.degrees, result.minutes, result.seconds) == (29, 59, 59.0)
    assert result.degrees != 30


def test_more_decimals_only_reveal_more_of_the_same_value():
    coarse = to_dms(13.788209, 0)
    fine = to_dms(13.788209, 4)

    assert (coarse.degrees, coarse.minutes) == (fine.degrees, fine.minutes)
    assert fine.seconds == 17.5524
    assert coarse.seconds <= fine.seconds


@pytest.mark.parametrize("decimals", [0, 1, 2, 3, 6])
def test_seconds_and_minutes_never_reach_sixty(decimals):
    """A 60-carry is impossible by construction; sweep near every boundary."""
    values = [
        0.0,
        1e-12,
        29.999999,
        29.9999999999,
        13.788209,
        0.999999,
        59.999999,
        123.4567891,
    ]

    for value in values:
        result = to_dms(value, decimals)
        assert 0 <= result.minutes < 60, (value, result)
        assert 0.0 <= result.seconds < 60.0, (value, result)
        assert result.degrees == int(value), (value, result)


def test_integer_input_is_accepted():
    assert to_dms(7) == DMS(7, 0, 0.0)


# --- rejection -------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        -1.0,
        -0.000001,
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        False,
        "x",
        None,
        [1.0],
    ],
)
def test_rejects_invalid_degree_values(value):
    with pytest.raises(ValueError):
        to_dms(value)


@pytest.mark.parametrize("decimals", [-1, 1.5, True, "2", None])
def test_rejects_invalid_seconds_decimals(decimals):
    with pytest.raises(ValueError):
        to_dms(13.788209, decimals)


# --- the type --------------------------------------------------------------


def test_dms_is_frozen():
    result = to_dms(13.788209, 2)

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.degrees = 0


def test_str_formats_whole_seconds_without_a_decimal_point():
    assert str(DMS(13, 47, 17.0)) == "13°47'17\""


def test_str_formats_fractional_seconds():
    assert str(DMS(13, 47, 17.55)) == "13°47'17.55\""


def test_str_of_a_converted_value():
    assert str(to_dms(13.788209)) == "13°47'17\""
    assert str(to_dms(13.788209, 2)) == "13°47'17.55\""
    assert str(to_dms(29.999999)) == "29°59'59\""


def test_equal_inputs_give_equal_output():
    assert to_dms(13.788209, 2) == to_dms(13.788209, 2)
