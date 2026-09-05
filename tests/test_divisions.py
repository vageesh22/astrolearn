"""Tests for the Layer 7 divisional classification.

Pure tests: no ephemeris and no I/O, just the arithmetic of the locked spec.
"""

import math
from fractions import Fraction

import pytest

from vedic_chart.vedic.divisions import (
    NAKSHATRA_NAMES,
    RASHI_NAMES,
    classify,
    normalize_longitude,
)

# A rashi boundary 30k is always exactly representable as a float. A nakshatra
# boundary is 40k/3 and a pada boundary is 10k/3, which are exact only when k
# is a multiple of 3. The remaining boundaries are irrational in binary, so no
# float equals them and "the value exactly on the boundary" does not exist to
# be tested. See test_non_representable_boundaries_are_documented.
EXACT_NAKSHATRA_K = tuple(k for k in range(1, 27) if k % 3 == 0)
EXACT_PADA_K = tuple(k for k in range(1, 108) if k % 3 == 0)


def test_name_lists_have_expected_lengths():
    assert len(RASHI_NAMES) == 12
    assert len(NAKSHATRA_NAMES) == 27


def test_zero_longitude():
    placement = classify(0.0)

    assert placement.rashi_index == 0
    assert placement.rashi_number == 1
    assert placement.rashi_name == "Mesha"
    assert placement.nakshatra_index == 0
    assert placement.nakshatra_number == 1
    assert placement.nakshatra_name == "Ashwini"
    assert placement.pada == 1
    assert placement.degrees_in_rashi == 0.0
    assert placement.degrees_in_nakshatra == 0.0
    assert placement.degrees_in_pada == 0.0


def test_rashi_boundaries_are_half_open():
    # Rule 10: a longitude exactly on a boundary starts the new rashi.
    for k in range(1, 12):
        boundary = k * 30.0

        at_boundary = classify(boundary)
        assert at_boundary.rashi_index == k
        assert at_boundary.degrees_in_rashi == 0.0

        assert classify(boundary - 1e-9).rashi_index == k - 1


def test_nakshatra_boundaries_are_half_open():
    for k in EXACT_NAKSHATRA_K:
        boundary = k * 360.0 / 27.0
        assert Fraction(boundary) == Fraction(360 * k, 27), boundary

        at_boundary = classify(boundary)
        assert at_boundary.nakshatra_index == k, boundary
        assert at_boundary.degrees_in_nakshatra == pytest.approx(0.0, abs=1e-12)

        assert classify(boundary - 1e-9).nakshatra_index == k - 1, boundary


def test_pada_boundaries_are_half_open():
    for k in EXACT_PADA_K:
        boundary = k * 360.0 / 108.0
        assert Fraction(boundary) == Fraction(360 * k, 108), boundary

        assert classify(boundary).pada == k % 4 + 1, boundary
        assert classify(boundary - 1e-9).pada == (k - 1) % 4 + 1, boundary


def test_every_nakshatra_and_pada_is_reachable():
    # Sampling the middle of each division avoids boundary representation
    # entirely and proves the full 27 x 4 grid is covered.
    for k in range(27):
        middle = (k + 0.5) * 360.0 / 27.0
        placement = classify(middle)
        assert placement.nakshatra_index == k
        assert placement.nakshatra_name == NAKSHATRA_NAMES[k]

    seen = set()
    for k in range(108):
        middle = (k + 0.5) * 360.0 / 108.0
        seen.add(classify(middle).pada)
    assert seen == {1, 2, 3, 4}


def test_non_representable_boundaries_are_documented():
    """Most division boundaries cannot be represented as floats.

    ``k * 360.0 / 27.0`` for k = 11 lands on 146.66666666666666, which is
    strictly *below* the true boundary 440/3. Classifying it as nakshatra 10
    is therefore correct for that value, not an off-by-one: the float simply is
    not the boundary. Rule 12 forbids nudging it across, so this is asserted as
    the specified behaviour rather than worked around.
    """
    for k in (11, 22):
        approx_boundary = k * 360.0 / 27.0
        assert Fraction(approx_boundary) < Fraction(360 * k, 27)
        assert classify(approx_boundary).nakshatra_index == k - 1

    # The smallest float at or above the true boundary does start nakshatra k.
    for k in (11, 22):
        true_boundary = Fraction(360 * k, 27)
        value = float(true_boundary)
        if Fraction(value) < true_boundary:
            value = math.nextafter(value, math.inf)
        assert classify(value).nakshatra_index == k


def test_classification_uses_unrounded_longitude():
    # Rule 11: 29.999999 displays as 30d00'00" at arcsecond rounding but is
    # still in the first rashi.
    assert classify(29.999999).rashi_index == 0

    end_of_zodiac = classify(359.999999)
    assert end_of_zodiac.rashi_index == 11
    assert end_of_zodiac.rashi_name == "Meena"
    assert end_of_zodiac.nakshatra_index == 26
    assert end_of_zodiac.nakshatra_name == "Revati"
    assert end_of_zodiac.pada == 4


def test_normalization():
    assert normalize_longitude(360.0) == 0.0
    assert normalize_longitude(725.0) == 5.0
    assert normalize_longitude(-0.5) == 359.5
    assert classify(-0.5).rashi_index == 11


def test_pada_and_nakshatra_stay_consistent_across_the_zodiac():
    # 108 = 27 x 4 by construction, so the pada-of-zodiac index divided by 4
    # must always land back on the nakshatra index.
    for i in range(10000):
        longitude = i * 360.0 / 10000.0
        placement = classify(longitude)
        assert int(longitude * 108.0 / 360.0) // 4 == placement.nakshatra_index


def test_all_longitudes_classify_within_range():
    for i in range(10000):
        placement = classify(i * 360.0 / 10000.0)
        assert 0 <= placement.rashi_index <= 11
        assert 0 <= placement.nakshatra_index <= 26
        assert 1 <= placement.pada <= 4
        assert 0.0 <= placement.degrees_in_rashi < 30.0
