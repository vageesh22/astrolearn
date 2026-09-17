"""Layer 16's angular elements (specification sections 2.2, 4.1 and 4.2).

Pure tests: no ephemeris, no zone, no I/O, just the arithmetic on two
longitudes. The three divisions this layer adds -- 12 deg for the tithi, 6 deg
for the karana, 360/27 deg for the yoga -- are exercised the way
``tests/test_divisions.py`` exercises the frozen ones: every boundary at its
start, one ULP below and one ULP above, every name in its cycle sampled at the
middle of its interval, and the 0/360 seam and negative inputs stated
explicitly.

The sixty karana slots are pinned **individually**, as a literal table, rather
than re-derived from ``(index - 1) mod 7``. The implementation builds the table
from that rule on purpose, so a test that applied the same rule would only be
checking the rule against itself; the point of the table below is that somebody
wrote the answer down.

Yoga boundaries are at 40k/3 degrees and inherit the FROZEN "float fact": only
a k that is a multiple of 3 is exactly representable as a float, and for every
other k no float equals the boundary at all. That is handled exactly as
``test_non_representable_boundaries_are_documented`` handles the nakshatra
boundaries it shares its arithmetic with -- asserted as the specified
behaviour, never nudged.
"""

import dataclasses
import math
from fractions import Fraction

import pytest

from vedic_chart.panchanga import (
    KARANA_FIXED_NAMES,
    KARANA_REPEATING_NAMES,
    TITHI_NAMES,
    VARA_LORDS,
    VARA_NAMES,
    YOGA_NAMES,
    Karana,
    KaranaKind,
    Nakshatra,
    NityaYoga,
    Paksha,
    Tithi,
    TithiHalf,
)
from vedic_chart.panchanga.elements import (
    KARANA_COUNT,
    NAKSHATRA_COUNT,
    KARANA_SPAN,
    TITHI_COUNT,
    TITHI_SPAN,
    VARA_ENGLISH_WEEKDAYS,
    YOGA_COUNT,
    YOGA_SPAN,
    _progress_fraction,
    elongation,
    karana_from_elongation,
    longitude_sum,
    nakshatra_from_longitude,
    nakshatra_from_placement,
    tithi_from_elongation,
    vara_index_from_weekday,
    yoga_from_sum,
)
from vedic_chart.vedic.divisions import (
    NAKSHATRA_NAMES,
    NAKSHATRA_SPAN,
    classify,
    normalize_longitude,
)
from vedic_chart.vedic.grahas import Graha

#: The thirty tithis: (index, paksha, number in paksha, name).
TITHI_TABLE = (
    (0, Paksha.SHUKLA, 1, "Pratipada"),
    (1, Paksha.SHUKLA, 2, "Dwitiya"),
    (2, Paksha.SHUKLA, 3, "Tritiya"),
    (3, Paksha.SHUKLA, 4, "Chaturthi"),
    (4, Paksha.SHUKLA, 5, "Panchami"),
    (5, Paksha.SHUKLA, 6, "Shashthi"),
    (6, Paksha.SHUKLA, 7, "Saptami"),
    (7, Paksha.SHUKLA, 8, "Ashtami"),
    (8, Paksha.SHUKLA, 9, "Navami"),
    (9, Paksha.SHUKLA, 10, "Dashami"),
    (10, Paksha.SHUKLA, 11, "Ekadashi"),
    (11, Paksha.SHUKLA, 12, "Dwadashi"),
    (12, Paksha.SHUKLA, 13, "Trayodashi"),
    (13, Paksha.SHUKLA, 14, "Chaturdashi"),
    (14, Paksha.SHUKLA, 15, "Purnima"),
    (15, Paksha.KRISHNA, 1, "Pratipada"),
    (16, Paksha.KRISHNA, 2, "Dwitiya"),
    (17, Paksha.KRISHNA, 3, "Tritiya"),
    (18, Paksha.KRISHNA, 4, "Chaturthi"),
    (19, Paksha.KRISHNA, 5, "Panchami"),
    (20, Paksha.KRISHNA, 6, "Shashthi"),
    (21, Paksha.KRISHNA, 7, "Saptami"),
    (22, Paksha.KRISHNA, 8, "Ashtami"),
    (23, Paksha.KRISHNA, 9, "Navami"),
    (24, Paksha.KRISHNA, 10, "Dashami"),
    (25, Paksha.KRISHNA, 11, "Ekadashi"),
    (26, Paksha.KRISHNA, 12, "Dwadashi"),
    (27, Paksha.KRISHNA, 13, "Trayodashi"),
    (28, Paksha.KRISHNA, 14, "Chaturdashi"),
    (29, Paksha.KRISHNA, 15, "Amavasya"),
)

#: The sixty karana slots of one lunar month, written out.
KARANA_TABLE = (
    (0, "Kimstughna", KaranaKind.FIXED, None),
    (1, "Bava", KaranaKind.REPEATING, 1),
    (2, "Balava", KaranaKind.REPEATING, 2),
    (3, "Kaulava", KaranaKind.REPEATING, 3),
    (4, "Taitila", KaranaKind.REPEATING, 4),
    (5, "Garaja", KaranaKind.REPEATING, 5),
    (6, "Vanija", KaranaKind.REPEATING, 6),
    (7, "Vishti", KaranaKind.REPEATING, 7),
    (8, "Bava", KaranaKind.REPEATING, 1),
    (9, "Balava", KaranaKind.REPEATING, 2),
    (10, "Kaulava", KaranaKind.REPEATING, 3),
    (11, "Taitila", KaranaKind.REPEATING, 4),
    (12, "Garaja", KaranaKind.REPEATING, 5),
    (13, "Vanija", KaranaKind.REPEATING, 6),
    (14, "Vishti", KaranaKind.REPEATING, 7),
    (15, "Bava", KaranaKind.REPEATING, 1),
    (16, "Balava", KaranaKind.REPEATING, 2),
    (17, "Kaulava", KaranaKind.REPEATING, 3),
    (18, "Taitila", KaranaKind.REPEATING, 4),
    (19, "Garaja", KaranaKind.REPEATING, 5),
    (20, "Vanija", KaranaKind.REPEATING, 6),
    (21, "Vishti", KaranaKind.REPEATING, 7),
    (22, "Bava", KaranaKind.REPEATING, 1),
    (23, "Balava", KaranaKind.REPEATING, 2),
    (24, "Kaulava", KaranaKind.REPEATING, 3),
    (25, "Taitila", KaranaKind.REPEATING, 4),
    (26, "Garaja", KaranaKind.REPEATING, 5),
    (27, "Vanija", KaranaKind.REPEATING, 6),
    (28, "Vishti", KaranaKind.REPEATING, 7),
    (29, "Bava", KaranaKind.REPEATING, 1),
    (30, "Balava", KaranaKind.REPEATING, 2),
    (31, "Kaulava", KaranaKind.REPEATING, 3),
    (32, "Taitila", KaranaKind.REPEATING, 4),
    (33, "Garaja", KaranaKind.REPEATING, 5),
    (34, "Vanija", KaranaKind.REPEATING, 6),
    (35, "Vishti", KaranaKind.REPEATING, 7),
    (36, "Bava", KaranaKind.REPEATING, 1),
    (37, "Balava", KaranaKind.REPEATING, 2),
    (38, "Kaulava", KaranaKind.REPEATING, 3),
    (39, "Taitila", KaranaKind.REPEATING, 4),
    (40, "Garaja", KaranaKind.REPEATING, 5),
    (41, "Vanija", KaranaKind.REPEATING, 6),
    (42, "Vishti", KaranaKind.REPEATING, 7),
    (43, "Bava", KaranaKind.REPEATING, 1),
    (44, "Balava", KaranaKind.REPEATING, 2),
    (45, "Kaulava", KaranaKind.REPEATING, 3),
    (46, "Taitila", KaranaKind.REPEATING, 4),
    (47, "Garaja", KaranaKind.REPEATING, 5),
    (48, "Vanija", KaranaKind.REPEATING, 6),
    (49, "Vishti", KaranaKind.REPEATING, 7),
    (50, "Bava", KaranaKind.REPEATING, 1),
    (51, "Balava", KaranaKind.REPEATING, 2),
    (52, "Kaulava", KaranaKind.REPEATING, 3),
    (53, "Taitila", KaranaKind.REPEATING, 4),
    (54, "Garaja", KaranaKind.REPEATING, 5),
    (55, "Vanija", KaranaKind.REPEATING, 6),
    (56, "Vishti", KaranaKind.REPEATING, 7),
    (57, "Shakuni", KaranaKind.FIXED, None),
    (58, "Chatushpada", KaranaKind.FIXED, None),
    (59, "Naga", KaranaKind.FIXED, None),
)

#: How far apart the raw offset and the progress fraction may be where both are
#: well defined. They are computed from different doubles -- ``value - index *
#: span`` and ``scaled - index`` -- and ``scaled`` runs up to 60, so the
#: fraction inherits about half an ULP of a number that size, which is 7.1e-15.
#: Measured worst cases: 3.6e-15 for the tithi, 7.1e-15 for the karana.
ULP_BAND = 1e-14

#: A yoga boundary is 40k/3 degrees, exact as a float only for k divisible by 3.
EXACT_YOGA_K = tuple(k for k in range(1, 27) if k % 3 == 0)
INEXACT_YOGA_K = tuple(k for k in range(1, 27) if k % 3 != 0)


def middle_of_tithi(index):
    return (index + 0.5) * TITHI_SPAN


def middle_of_karana(index):
    return (index + 0.5) * KARANA_SPAN


def middle_of_yoga(index):
    return (index + 0.5) * YOGA_SPAN


# --- the name tables -------------------------------------------------------


def test_the_name_tables_have_the_specified_lengths():
    assert len(TITHI_NAMES) == 30
    assert len(YOGA_NAMES) == 27
    assert len(KARANA_REPEATING_NAMES) == 7
    assert len(KARANA_FIXED_NAMES) == 4
    assert len(VARA_NAMES) == 7
    assert len(VARA_LORDS) == 7
    assert len(VARA_ENGLISH_WEEKDAYS) == 7


def test_the_name_tables_are_immutable_tuples():
    for table in (
        TITHI_NAMES,
        YOGA_NAMES,
        KARANA_REPEATING_NAMES,
        KARANA_FIXED_NAMES,
        VARA_NAMES,
        VARA_LORDS,
    ):
        assert isinstance(table, tuple)


def test_the_tithi_names_repeat_once_with_two_singular_names():
    """Fourteen shared names twice over, plus Purnima at 15 and Amavasya at 30."""
    assert TITHI_NAMES[:14] == TITHI_NAMES[15:29]
    assert TITHI_NAMES[14] == "Purnima"
    assert TITHI_NAMES[29] == "Amavasya"
    assert TITHI_NAMES.count("Purnima") == 1
    assert TITHI_NAMES.count("Amavasya") == 1


def test_the_karana_name_tables_are_disjoint_and_complete():
    assert set(KARANA_REPEATING_NAMES) & set(KARANA_FIXED_NAMES) == set()
    assert len(set(KARANA_REPEATING_NAMES) | set(KARANA_FIXED_NAMES)) == 11
    assert KARANA_FIXED_NAMES == (
        "Kimstughna", "Shakuni", "Chatushpada", "Naga",
    )


def test_the_yoga_names_are_the_twenty_seven_of_the_specification():
    assert YOGA_NAMES[0] == "Vishkambha"
    assert YOGA_NAMES[13] == "Harshana"
    assert YOGA_NAMES[25] == "Indra"
    assert YOGA_NAMES[26] == "Vaidhriti"
    assert len(set(YOGA_NAMES)) == 27


# --- elongation and sum ----------------------------------------------------


def test_the_elongation_is_the_moon_minus_the_sun_wrapped():
    assert elongation(0.0, 0.0) == 0.0
    assert elongation(10.0, 20.0) == 10.0
    assert elongation(350.0, 10.0) == 20.0
    assert elongation(10.0, 350.0) == 340.0


def test_the_sum_is_the_two_longitudes_wrapped():
    assert longitude_sum(0.0, 0.0) == 0.0
    assert longitude_sum(200.0, 200.0) == 40.0
    assert longitude_sum(359.5, 0.25) == 359.75


def test_negative_inputs_are_normalised_and_never_rejected():
    """Rule 13's wrap is the layer's only answer to a negative value."""
    assert elongation(0.0, -0.5) == 359.5
    assert longitude_sum(-0.5, 0.0) == 359.5

    assert tithi_from_elongation(elongation(0.0, -0.5)).index == 29
    assert karana_from_elongation(elongation(0.0, -0.5)).index == 59
    assert yoga_from_sum(longitude_sum(-0.5, 0.0)).index == 26
    assert nakshatra_from_longitude(-0.5).index == 26


# --- all thirty tithis -----------------------------------------------------


@pytest.mark.parametrize(
    "index,paksha,number_in_paksha,name",
    TITHI_TABLE,
    ids=[f"{row[0]:02d}" for row in TITHI_TABLE],
)
def test_every_tithi_is_named_numbered_and_placed(
    index, paksha, number_in_paksha, name
):
    tithi = tithi_from_elongation(middle_of_tithi(index))

    assert tithi.index == index
    assert tithi.number == index + 1
    assert tithi.name == name
    assert tithi.paksha is paksha
    assert tithi.number_in_paksha == number_in_paksha
    assert tithi.key == f"{paksha.value}_{name.lower()}"
    assert tithi.name == TITHI_NAMES[index]


def test_the_two_pakshas_split_the_month_in_half():
    shukla = [row for row in TITHI_TABLE if row[1] is Paksha.SHUKLA]
    krishna = [row for row in TITHI_TABLE if row[1] is Paksha.KRISHNA]

    assert len(shukla) == len(krishna) == 15
    assert {row[2] for row in shukla} == set(range(1, 16))
    assert {row[2] for row in krishna} == set(range(1, 16))


def test_every_tithi_key_is_unique():
    keys = {
        tithi_from_elongation(middle_of_tithi(index)).key for index in range(30)
    }

    assert len(keys) == 30


# --- all twenty-seven yogas ------------------------------------------------


@pytest.mark.parametrize("index", range(27))
def test_every_yoga_is_named_and_numbered(index):
    yoga = yoga_from_sum(middle_of_yoga(index))

    assert yoga.index == index
    assert yoga.number == index + 1
    assert yoga.name == YOGA_NAMES[index]
    assert yoga.key == YOGA_NAMES[index].lower()
    assert yoga.sum_longitude == middle_of_yoga(index)


def test_the_yoga_shares_the_frozen_nakshatra_arithmetic():
    """Same division, same formula shape, therefore the same float behaviour.

    Specification 4.1 says the indices "mirror the FROZEN nakshatra formula
    shape so the float behaviour is the same". This is that claim, tested
    rather than asserted in prose: on every value the two must agree.
    """
    for k in range(0, 3600):
        value = k * 0.1
        assert yoga_from_sum(value).index == classify(value).nakshatra_index


# --- all sixty karana slots ------------------------------------------------


@pytest.mark.parametrize(
    "index,name,kind,cycle_position",
    KARANA_TABLE,
    ids=[f"{row[0]:02d}" for row in KARANA_TABLE],
)
def test_every_karana_slot_is_pinned(index, name, kind, cycle_position):
    karana = karana_from_elongation(middle_of_karana(index))

    assert karana.index == index
    assert karana.number == index + 1
    assert karana.name == name
    assert karana.key == name.lower()
    assert karana.kind is kind
    assert karana.cycle_position == cycle_position


@pytest.mark.parametrize(
    "index,name,kind,cycle_position",
    KARANA_TABLE,
    ids=[f"{row[0]:02d}" for row in KARANA_TABLE],
)
def test_every_karana_halves_the_tithi_it_should(
    index, name, kind, cycle_position
):
    """``karana_index == 2 * tithi_index + half`` (specification 4.1)."""
    arc = middle_of_karana(index)
    karana = karana_from_elongation(arc)
    tithi = tithi_from_elongation(arc)

    half = 0 if karana.half is TithiHalf.FIRST else 1

    assert karana.tithi_index == tithi.index
    assert karana.index == 2 * tithi.index + half
    assert karana.tithi_index == index // 2
    assert half == index % 2


def test_the_karana_table_is_four_fixed_and_fifty_six_repeating():
    kinds = [row[2] for row in KARANA_TABLE]

    assert kinds.count(KaranaKind.FIXED) == 4
    assert kinds.count(KaranaKind.REPEATING) == 56
    assert len(KARANA_TABLE) == 60


def test_the_fixed_karanas_sit_in_the_four_specified_slots():
    fixed = {row[0]: row[1] for row in KARANA_TABLE if row[2] is KaranaKind.FIXED}

    assert fixed == {
        0: "Kimstughna", 57: "Shakuni", 58: "Chatushpada", 59: "Naga",
    }
    for index in fixed:
        assert karana_from_elongation(middle_of_karana(index)).cycle_position is None


def test_the_repeating_karanas_cycle_eight_times():
    repeating = [
        karana_from_elongation(middle_of_karana(index)).name
        for index in range(1, 57)
    ]

    assert repeating == list(KARANA_REPEATING_NAMES) * 8
    assert len(repeating) == 56


def test_the_specifications_two_spot_checks():
    assert karana_from_elongation(middle_of_karana(1)).name == "Bava"
    assert karana_from_elongation(middle_of_karana(56)).name == "Vishti"


# --- the boundaries --------------------------------------------------------


@pytest.mark.parametrize("k", range(1, 30))
def test_tithi_boundaries_are_half_open(k):
    boundary = k * TITHI_SPAN

    assert Fraction(boundary) == Fraction(12 * k), boundary

    assert tithi_from_elongation(boundary).index == k
    assert tithi_from_elongation(boundary).degrees_in_tithi == 0.0
    assert tithi_from_elongation(math.nextafter(boundary, -math.inf)).index == k - 1
    assert tithi_from_elongation(math.nextafter(boundary, math.inf)).index == k


@pytest.mark.parametrize("k", range(1, 60))
def test_karana_boundaries_are_half_open(k):
    boundary = k * KARANA_SPAN

    assert Fraction(boundary) == Fraction(6 * k), boundary

    assert karana_from_elongation(boundary).index == k
    assert karana_from_elongation(boundary).degrees_in_karana == 0.0
    assert karana_from_elongation(math.nextafter(boundary, -math.inf)).index == k - 1
    assert karana_from_elongation(math.nextafter(boundary, math.inf)).index == k


@pytest.mark.parametrize("k", EXACT_YOGA_K)
def test_exactly_representable_yoga_boundaries_are_half_open(k):
    boundary = k * YOGA_SPAN

    assert Fraction(boundary) == Fraction(360 * k, 27), boundary

    assert yoga_from_sum(boundary).index == k
    assert yoga_from_sum(math.nextafter(boundary, -math.inf)).index == k - 1
    assert yoga_from_sum(math.nextafter(boundary, math.inf)).index == k


@pytest.mark.parametrize("k", INEXACT_YOGA_K)
def test_non_representable_yoga_boundaries_are_documented(k):
    """40k/3 is irrational in binary unless 3 divides k (the FROZEN float fact).

    No float equals the boundary, so "the value exactly on it" does not exist
    to be tested. What is tested instead is that the nearest float on each side
    classifies as the division it actually belongs to. Rule 12 forbids nudging
    one across, so this is asserted as the specified behaviour, exactly as
    ``tests/test_divisions.py`` does for the nakshatra boundaries this division
    shares its arithmetic with.
    """
    true_boundary = Fraction(360 * k, 27)
    approximation = k * YOGA_SPAN

    assert Fraction(approximation) != true_boundary

    # Walk down one float at a time until the index drops. The division stays
    # half-open in the float domain -- there is a last value of yoga k-1 and a
    # first value of yoga k, adjacent floats -- but the flip does not
    # necessarily land on the side of ``true_boundary`` that exact arithmetic
    # would put it on, because ``value * 27.0 / 360.0`` rounds a second time
    # after the boundary itself has already been rounded.
    value = approximation
    while yoga_from_sum(value).index == k:
        value = math.nextafter(value, -math.inf)

    last_of_previous = value
    first_of_k = math.nextafter(value, math.inf)

    assert yoga_from_sum(last_of_previous).index == k - 1, k
    assert yoga_from_sum(first_of_k).index == k, k
    assert Fraction(last_of_previous) < Fraction(first_of_k)

    # The disagreement with exact arithmetic is confined to a couple of ULP:
    # the flip is within a nanodegree of the boundary no float can express.
    assert abs(Fraction(first_of_k) - true_boundary) < Fraction(1, 10**9), k


def test_the_specifications_worked_boundary_examples():
    """Specification 4.1's own three cases, at 0, at 180 and just below 180."""
    start = tithi_from_elongation(0.0)
    assert start.index == 0
    assert start.paksha is Paksha.SHUKLA
    assert start.name == "Pratipada"
    assert karana_from_elongation(0.0).name == "Kimstughna"

    at_180 = tithi_from_elongation(180.0)
    assert at_180.index == 15
    assert at_180.paksha is Paksha.KRISHNA
    assert at_180.name == "Pratipada"
    karana_180 = karana_from_elongation(180.0)
    assert karana_180.index == 30
    assert karana_180.name == "Balava"

    just_below = math.nextafter(180.0, 0.0)
    assert tithi_from_elongation(just_below).index == 14
    assert tithi_from_elongation(just_below).name == "Purnima"
    assert karana_from_elongation(just_below).index == 29
    assert karana_from_elongation(just_below).name == "Bava"
    assert karana_from_elongation(just_below).half is TithiHalf.SECOND


def test_the_zero_three_hundred_and_sixty_seam():
    """E = 0 starts the month; the last float below 360 ends it."""
    assert tithi_from_elongation(0.0).index == 0
    assert karana_from_elongation(0.0).index == 0
    assert yoga_from_sum(0.0).index == 0

    last = math.nextafter(360.0, 0.0)
    assert tithi_from_elongation(last).index == 29
    assert tithi_from_elongation(last).name == "Amavasya"
    assert karana_from_elongation(last).index == 59
    assert karana_from_elongation(last).name == "Naga"
    assert karana_from_elongation(last).half is TithiHalf.SECOND
    assert yoga_from_sum(last).index == 26

    # 360 itself is not in the domain: the wrap turns it into 0.
    assert elongation(0.0, 360.0) == 0.0
    assert longitude_sum(0.0, 360.0) == 0.0


# --- angular fractions -----------------------------------------------------


@pytest.mark.parametrize("index", range(30))
def test_the_tithi_fraction_is_a_fraction_of_arc_in_the_unit_interval(index):
    for offset in (0.0, 0.25, 6.0, 11.999999):
        tithi = tithi_from_elongation(index * TITHI_SPAN + offset)
        assert 0.0 <= tithi.angular_fraction < 1.0
        assert tithi.degrees_in_tithi == pytest.approx(offset, abs=1e-12)
        # The tithi's boundaries are exact, so the raw offset and the progress
        # fraction agree to rounding everywhere (specification 4.2).
        assert tithi.angular_fraction == pytest.approx(
            tithi.degrees_in_tithi / TITHI_SPAN, abs=ULP_BAND
        )
        assert tithi.degrees_in_tithi >= 0.0

    # The offset is exact where the arc is a whole number of spans: the tithi
    # boundaries are multiples of 12 and every one of them is a float.
    assert tithi_from_elongation(index * TITHI_SPAN).degrees_in_tithi == 0.0


@pytest.mark.parametrize("index", range(60))
def test_the_karana_fraction_stays_in_the_unit_interval(index):
    for offset in (0.0, 0.5, 5.999999):
        karana = karana_from_elongation(index * KARANA_SPAN + offset)
        assert 0.0 <= karana.angular_fraction < 1.0
        assert karana.degrees_in_karana == pytest.approx(offset, abs=1e-12)

    assert karana_from_elongation(index * KARANA_SPAN).degrees_in_karana == 0.0


@pytest.mark.parametrize("index", range(27))
def test_the_yoga_fraction_stays_in_the_unit_interval(index):
    for offset in (0.0, 1.0, 13.0):
        yoga = yoga_from_sum(index * YOGA_SPAN + offset)
        assert 0.0 <= yoga.angular_fraction < 1.0


def test_the_nakshatra_fraction_stays_in_the_unit_interval():
    for k in range(0, 3600):
        nakshatra = nakshatra_from_longitude(k * 0.1)
        assert 0.0 <= nakshatra.angular_fraction < 1.0


def test_the_raw_offset_carries_the_ulp_band_and_the_fraction_does_not():
    """Specification 4.2, the whole point of having two quantities.

    ``int(value * 27 / 360)`` rounds a second time and can call a value the
    start of yoga k while ``value - k * span`` -- which does not round -- is
    still a few times 1e-14 negative. The FROZEN ``classify`` does exactly the
    same at exactly the same values and rule 12 forbids nudging either, so the
    raw offset keeps that negative number. The progress fraction is the
    fractional part of the very double the index came from, so at the same
    value it is exactly 0.0 -- not nearly zero, and never negative.
    """
    value = math.nextafter(7 * YOGA_SPAN, -math.inf)
    yoga = yoga_from_sum(value)
    placement = classify(value)

    assert yoga.index == 7
    assert placement.nakshatra_index == 7

    # The raw offset is the frozen engine's, negative and unchanged.
    assert -1e-13 < yoga.degrees_in_yoga < 0.0
    assert yoga.degrees_in_yoga == placement.degrees_in_nakshatra

    # The progress fraction is exactly zero.
    assert yoga.angular_fraction == 0.0
    assert not yoga.angular_fraction < 0.0

    # One float up, the raw offset is a clean zero and the fraction is the
    # sub-ULP positive the second rounding leaves; both are in the interval.
    at_boundary = yoga_from_sum(7 * YOGA_SPAN)
    assert at_boundary.index == 7
    assert at_boundary.degrees_in_yoga == 0.0
    assert 0.0 <= at_boundary.angular_fraction < 1e-15


@pytest.mark.parametrize("k", INEXACT_YOGA_K)
def test_at_every_inexact_yoga_boundary_the_fraction_is_zero(k):
    """For each such k there is a float where offset < 0 and fraction == 0.0.

    Found rather than assumed: walk down from the boundary's nearest float
    until the index drops, and look at the first value of the new division.
    Where the index and the raw offset disagree, the offset is negative and the
    progress fraction is exactly zero.
    """
    value = k * YOGA_SPAN
    while yoga_from_sum(value).index == k:
        value = math.nextafter(value, -math.inf)
    first_of_k = math.nextafter(value, math.inf)

    yoga = yoga_from_sum(first_of_k)

    assert yoga.index == k
    assert 0.0 <= yoga.angular_fraction < 1.0
    if yoga.degrees_in_yoga < 0.0:
        assert yoga.degrees_in_yoga > -1e-12, (k, yoga.degrees_in_yoga)
        assert yoga.angular_fraction == 0.0, k
    else:
        assert yoga.angular_fraction == pytest.approx(
            yoga.degrees_in_yoga / YOGA_SPAN, abs=ULP_BAND
        )


@pytest.mark.parametrize("k", range(1, 27))
def test_at_every_nakshatra_boundary_the_fraction_stays_in_the_interval(k):
    """The same, through the wrapper that reads the FROZEN placement."""
    value = k * NAKSHATRA_SPAN
    while nakshatra_from_longitude(value).index == k:
        value = math.nextafter(value, -math.inf)
    first_of_k = math.nextafter(value, math.inf)

    nakshatra = nakshatra_from_longitude(first_of_k)

    assert nakshatra.index == k
    assert 0.0 <= nakshatra.angular_fraction < 1.0
    if nakshatra.degrees_in_nakshatra < 0.0:
        assert nakshatra.angular_fraction == 0.0, k


def test_the_progress_fraction_is_in_the_unit_interval_everywhere():
    """A sweep: uniform values, plus both neighbours of every boundary.

    ``angular_fraction`` is the fractional part of the double the index was
    floored from, so specification 4.2's "[0, 1) exactly, at every input" is a
    claim about IEEE arithmetic rather than about the sky. It is checked on ten
    thousand uniform values and on the two floats either side of every boundary
    of all four elements -- the only places the claim could plausibly fail.
    """
    values = [k * 360.0 / 10_000 for k in range(10_000)]
    for count in (TITHI_COUNT, KARANA_COUNT, YOGA_COUNT, NAKSHATRA_COUNT):
        for k in range(count + 1):
            boundary = k * 360.0 / count
            values.append(boundary)
            values.append(math.nextafter(boundary, -math.inf))
            values.append(math.nextafter(boundary, math.inf))

    for value in values:
        arc = normalize_longitude(value)
        if arc >= 360.0:
            # The float just below zero normalises to exactly 360.0 -- a
            # FROZEN ``normalize_longitude`` rounding, pinned on its own below.
            # It is outside the half-open domain, so it is not swept here.
            continue
        for element in (
            tithi_from_elongation(arc),
            karana_from_elongation(arc),
            yoga_from_sum(arc),
            nakshatra_from_longitude(arc),
        ):
            assert 0.0 <= element.angular_fraction < 1.0, (value, element)


@pytest.mark.parametrize("index", range(30))
def test_the_tithi_offset_and_fraction_agree_because_its_boundaries_are_exact(
    index,
):
    for offset in (0.0, 0.25, 6.0, 11.999999):
        tithi = tithi_from_elongation(index * TITHI_SPAN + offset)
        assert tithi.degrees_in_tithi >= 0.0
        assert tithi.angular_fraction >= 0.0
        assert tithi.angular_fraction == pytest.approx(
            tithi.degrees_in_tithi / TITHI_SPAN, abs=ULP_BAND
        )


@pytest.mark.parametrize("index", range(60))
def test_the_karana_offset_and_fraction_agree_because_its_boundaries_are_exact(
    index,
):
    for offset in (0.0, 0.5, 5.999999):
        karana = karana_from_elongation(index * KARANA_SPAN + offset)
        assert karana.degrees_in_karana >= 0.0
        assert karana.angular_fraction >= 0.0
        assert karana.angular_fraction == pytest.approx(
            karana.degrees_in_karana / KARANA_SPAN, abs=ULP_BAND
        )


def test_a_placement_that_disagrees_with_the_longitude_is_an_internal_error():
    """Rule 8 on the same double cannot give two answers; if it did, refuse.

    The placement is built by hand with a nakshatra index the longitude does
    not support. No chart the engine produced can look like this, which is why
    it is a RuntimeError rather than a ValueError.
    """
    longitude = 209.20440791222882
    good = classify(longitude)

    assert nakshatra_from_placement(good, longitude).index == good.nakshatra_index

    for wrong in (0, 26, (good.nakshatra_index + 1) % 27):
        if wrong == good.nakshatra_index:
            continue
        tampered = dataclasses.replace(good, nakshatra_index=wrong)
        with pytest.raises(RuntimeError, match="internal contradiction"):
            nakshatra_from_placement(tampered, longitude)


def test_the_progress_check_is_a_check_and_not_a_clamp():
    """It raises on an impossible pair rather than moving the value."""
    with pytest.raises(RuntimeError, match=r"outside \[0, 1\)"):
        _progress_fraction(5.5, 4)
    with pytest.raises(RuntimeError, match=r"outside \[0, 1\)"):
        _progress_fraction(5.5, 6)

    assert _progress_fraction(5.5, 5) == 0.5
    assert _progress_fraction(5.0, 5) == 0.0


# --- the nakshatra is the frozen classification ----------------------------


def test_the_nakshatra_carries_the_frozen_placement_by_identity():
    longitude = 209.20440791222882
    placement = classify(longitude)
    nakshatra = nakshatra_from_placement(placement, longitude)

    assert nakshatra.placement is placement
    assert nakshatra.index == placement.nakshatra_index
    assert nakshatra.number == placement.nakshatra_number
    assert nakshatra.name == placement.nakshatra_name
    assert nakshatra.pada == placement.pada
    assert nakshatra.degrees_in_nakshatra == placement.degrees_in_nakshatra
    assert nakshatra.degrees_in_pada == placement.degrees_in_pada
    # The progress fraction is the fractional part of the scaled longitude --
    # the same double rule 8 floored to get the index -- not the raw offset
    # divided by the span. Away from the ULP band the two agree closely.
    scaled = longitude * 27.0 / 360.0
    assert nakshatra.angular_fraction == scaled - int(scaled)
    assert nakshatra.angular_fraction == pytest.approx(
        placement.degrees_in_nakshatra / NAKSHATRA_SPAN, abs=1e-12
    )


@pytest.mark.parametrize("index", range(27))
def test_the_nakshatra_names_are_the_frozen_twenty_seven(index):
    nakshatra = nakshatra_from_longitude((index + 0.5) * NAKSHATRA_SPAN)

    assert nakshatra.index == index
    assert nakshatra.name == NAKSHATRA_NAMES[index]
    assert nakshatra.key == NAKSHATRA_NAMES[index].lower().replace(" ", "_")


def test_the_nakshatra_is_never_reclassified():
    """The wrapper of a placement equals the wrapper of its own longitude."""
    for k in range(0, 360):
        longitude = k + 0.123456789
        assert nakshatra_from_longitude(longitude) == nakshatra_from_placement(
            classify(longitude), longitude
        )


# --- the vara table --------------------------------------------------------


WEEKDAY_TABLE = (
    (0, 0, "Ravivara", "Sunday", Graha.SUN),
    (1, 1, "Somavara", "Monday", Graha.MOON),
    (2, 2, "Mangalavara", "Tuesday", Graha.MARS),
    (3, 3, "Budhavara", "Wednesday", Graha.MERCURY),
    (4, 4, "Guruvara", "Thursday", Graha.JUPITER),
    (5, 5, "Shukravara", "Friday", Graha.VENUS),
    (6, 6, "Shanivara", "Saturday", Graha.SATURN),
)


@pytest.mark.parametrize("index,_a,name,english,lord", WEEKDAY_TABLE)
def test_the_vara_table_names_numbers_and_lords(index, _a, name, english, lord):
    assert VARA_NAMES[index] == name
    assert VARA_ENGLISH_WEEKDAYS[index] == english
    assert VARA_LORDS[index] is lord


@pytest.mark.parametrize(
    "python_weekday,expected_index",
    ((0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 0)),
    ids=("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
)
def test_the_monday_zero_to_sunday_zero_conversion(
    python_weekday, expected_index
):
    """``date.weekday()`` counts from Monday; the varas count from Sunday."""
    assert vara_index_from_weekday(python_weekday) == expected_index


def test_the_conversion_is_a_bijection_on_the_seven_days():
    assert sorted(vara_index_from_weekday(day) for day in range(7)) == list(
        range(7)
    )


def test_the_lords_are_the_frozen_grahas_in_the_classical_order():
    assert VARA_LORDS == (
        Graha.SUN,
        Graha.MOON,
        Graha.MARS,
        Graha.MERCURY,
        Graha.JUPITER,
        Graha.VENUS,
        Graha.SATURN,
    )
    assert all(isinstance(lord, Graha) for lord in VARA_LORDS)


# --- immutability ----------------------------------------------------------


def test_the_element_types_are_frozen():
    arc = 100.0
    values = (
        tithi_from_elongation(arc),
        karana_from_elongation(arc),
        yoga_from_sum(arc),
        nakshatra_from_longitude(arc),
    )

    assert [type(value) for value in values] == [
        Tithi, Karana, NityaYoga, Nakshatra,
    ]
    for value in values:
        with pytest.raises(dataclasses.FrozenInstanceError):
            value.index = 0
        with pytest.raises(dataclasses.FrozenInstanceError):
            value.name = "tampered"


def test_the_float_below_zero_falls_outside_the_domain_in_the_frozen_layer():
    """``normalize_longitude`` rounds the tiniest negative float up to 360.0.

    Not this layer's behaviour and not this layer's to fix: ``-5e-324 % 360.0``
    is 360.0 exactly, which is outside the half-open [0, 360) every division in
    the engine is defined on. The FROZEN ``classify`` trips its own index guard
    on it in exactly the same way, so the two layers agree about where the
    domain ends. It is pinned here so that a future reader meeting it in a
    sweep knows it is a known edge of Layer 7, not a panchanga bug.
    """
    below_zero = math.nextafter(0.0, -math.inf)

    assert normalize_longitude(below_zero) == 360.0
    assert normalize_longitude(0.0) == 0.0

    # The frozen layer's index guards are ``assert`` statements, so they are
    # only there to be tripped when Python is not running optimised. Under
    # ``python -O`` the value simply produces an out-of-range index, which is
    # the same fact stated differently.
    if __debug__:
        with pytest.raises(AssertionError):
            classify(below_zero)
        with pytest.raises(AssertionError):
            tithi_from_elongation(normalize_longitude(below_zero))
    else:
        assert int(normalize_longitude(below_zero) * 30.0 / 360.0) == 30
