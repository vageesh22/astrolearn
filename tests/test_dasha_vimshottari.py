"""Layer 12's Vimshottari core (specification section 10).

Self-contained: standard library, the two frozen Layer 7 constants modules and
the layer under test. No ephemeris, no database, no network, no clock -- every
case here is a longitude and an explicit instant, so nothing in this file can
pass or fail because of the day it runs on.

Three things are checked that are easy to get wrong and easy to hide:

* the conversion from a double longitude to an exact rational, at all 27
  nakshatra boundaries and at the 0/360 seam, against the frozen classifier as
  oracle and against exact rational arithmetic as a second opinion. The four
  doubles where the frozen float classification and exact rational arithmetic
  disagree are named, their distances below the rational boundaries asserted,
  and the decision to follow the frozen index made visible rather than
  implied;
* that the nominal arithmetic is genuinely exact -- nine children summing to
  their parent as ``Fraction``s, not to within a tolerance -- and that the one
  quantization step is the only place precision is lost;
* that the two queries differ exactly where the specification says they do.
  ``periods_at_birth`` and ``active_periods_at(birth_utc)`` are compared on two
  real inputs whose post-birth remainder is shorter than a microsecond, one at
  all three levels and one at levels 2 and 3 only.

The 3,483-double boundary sweep goes through the core's own classification
helper rather than through ``build_vimshottari``: one build lays out 819
periods of exact rationals, and 3,483 of them would dominate the suite for no
extra coverage. A sample of the same longitudes is built in full, and every
other case in this file builds.
"""

import dataclasses
import math
from datetime import date, datetime, timedelta, timezone, tzinfo
from fractions import Fraction

import pytest

from vedic_chart.dasha import (
    CYCLE_YEARS,
    LORD_SEQUENCE,
    LORD_YEARS,
    MICROSECONDS_PER_DAY,
    NAKSHATRA_COUNT,
    DashaRangeError,
    YearConvention,
    build_vimshottari,
)
from vedic_chart.dasha.vimshottari import _classify_moon
from vedic_chart.vedic.divisions import NAKSHATRA_NAMES, classify
from vedic_chart.vedic.grahas import Graha

CONVENTIONS = tuple(YearConvention)
IST = timezone(timedelta(hours=5, minutes=30))
MICROSECOND = timedelta(microseconds=1)

#: A neutral anchor for the synthetic cases: far from either datetime limit,
#: on a round instant, so a failure reads as a duration and not as an offset.
ANCHOR = datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)

# --- the two internal reference births (specification section 9) -----------

JALANDHAR_MOON = 209.20440791222882
JALANDHAR_BIRTH = datetime(1995, 3, 21, 1, 15, tzinfo=timezone.utc)
JALANDHAR_BALANCE = Fraction(87164189005907, 17592186044416)

JAMMU_MOON = 54.892295957053236
JAMMU_BIRTH = datetime(2001, 2, 4, 5, 15, tzinfo=timezone.utc)
JAMMU_BALANCE = Fraction(6959800514669247, 1125899906842624)

# --- the two collapse cases ------------------------------------------------

#: 39.99999999999999 -- the largest double below Krittika's exact end, so the
#: Sun Mahadasha has 6/2**51 nominal years left at birth: under a twentieth of
#: a microsecond. Every level of the birth chain therefore ends at the birth
#: instant itself.
TINY_BALANCE_MOON = math.nextafter(40.0, 0)

#: 3.666666666666666 -- an input whose Mahadasha has years to run but whose
#: birth *antardasha* does not. Found by scanning, for every nakshatra and
#: every one of the 729 pratyantar boundaries lying in the middle half of the
#: Mahadasha, the doubles within six ULPs of the longitude that would put that
#: boundary exactly at the birth, and keeping one whose boundary lands a
#: strictly positive but sub-microsecond distance after it. This one sits
#: 21/90071992547409920 nominal years -- 0.00736 microseconds under
#: FIXED_365_25 -- past the end of Ketu-Sun and of its last pratyantar
#: Ketu-Sun-Venus, while the Ketu Mahadasha still has 5.075 nominal years to
#: run. One ULP of longitude here is worth about 29 microseconds of boundary,
#: which is why such a double has to be searched for rather than constructed.
TINY_SUBPERIOD_MOON = 3.666666666666666
TINY_SUBPERIOD_OFFSET = Fraction(21, 90071992547409920)

#: Nakshatra to lord, name by name (section 4). Written out rather than
#: generated, so that a change to ``LORD_SEQUENCE`` or to its rotation has to
#: disagree with a table a reader can check against BPHS.
NAKSHATRA_LORDS = (
    ("Ashwini", Graha.KETU),
    ("Bharani", Graha.VENUS),
    ("Krittika", Graha.SUN),
    ("Rohini", Graha.MOON),
    ("Mrigashira", Graha.MARS),
    ("Ardra", Graha.RAHU),
    ("Punarvasu", Graha.JUPITER),
    ("Pushya", Graha.SATURN),
    ("Ashlesha", Graha.MERCURY),
    ("Magha", Graha.KETU),
    ("Purva Phalguni", Graha.VENUS),
    ("Uttara Phalguni", Graha.SUN),
    ("Hasta", Graha.MOON),
    ("Chitra", Graha.MARS),
    ("Swati", Graha.RAHU),
    ("Vishakha", Graha.JUPITER),
    ("Anuradha", Graha.SATURN),
    ("Jyeshtha", Graha.MERCURY),
    ("Mula", Graha.KETU),
    ("Purva Ashadha", Graha.VENUS),
    ("Uttara Ashadha", Graha.SUN),
    ("Shravana", Graha.MOON),
    ("Dhanishta", Graha.MARS),
    ("Shatabhisha", Graha.RAHU),
    ("Purva Bhadrapada", Graha.JUPITER),
    ("Uttara Bhadrapada", Graha.SATURN),
    ("Revati", Graha.MERCURY),
)

#: The four doubles where the frozen float classification returns ``k`` and
#: exact rational arithmetic returns ``k - 1``, with their exact distances
#: *below* the rational boundary ``k * 40/3`` (section 5).
CONFLICTING_DOUBLES = (
    (7, 93.33333333333333, Fraction(1, 211106232532992)),
    (14, 186.66666666666666, Fraction(1, 105553116266496)),
    (17, 226.66666666666666, Fraction(1, 105553116266496)),
    (25, 333.3333333333333, Fraction(1, 52776558133248)),
)

#: Every case that gets the full structural treatment. Two real charts, the
#: two collapse cases and two plain hand-worked longitudes.
STRUCTURAL_CASES = (
    ("jalandhar", JALANDHAR_MOON, JALANDHAR_BIRTH),
    ("jammu", JAMMU_MOON, JAMMU_BIRTH),
    ("tiny_balance", TINY_BALANCE_MOON, ANCHOR),
    ("tiny_subperiod", TINY_SUBPERIOD_MOON, ANCHOR),
    ("ashwini_start", 0.0, ANCHOR),
    ("mid_uttara_phalguni", 153.3333333333333, ANCHOR),
)
STRUCTURAL_IDS = tuple(case[0] for case in STRUCTURAL_CASES)

_TIMELINE_CACHE = {}


def timeline(longitude, year, birth=ANCHOR):
    """One built timeline, cached: 819 periods of Fractions per build."""
    key = (longitude, year, birth)
    if key not in _TIMELINE_CACHE:
        _TIMELINE_CACHE[key] = build_vimshottari(longitude, birth, year)
    return _TIMELINE_CACHE[key]


def structural(name, convention):
    for case_name, longitude, birth in STRUCTURAL_CASES:
        if case_name == name:
            return timeline(longitude, convention, birth)
    raise KeyError(name)


def every_period(line):
    for mahadasha in line.mahadashas:
        yield mahadasha
        for antardasha in mahadasha.children:
            yield antardasha
            yield from antardasha.children


def every_parent(line):
    for mahadasha in line.mahadashas:
        yield mahadasha
        yield from mahadasha.children


def doubles_around(value, count=64):
    """``value`` and its ``count`` nearest doubles on each side."""
    lower = []
    step = value
    for _ in range(count):
        step = math.nextafter(step, -math.inf)
        lower.append(step)
    lower.reverse()
    upper = []
    step = value
    for _ in range(count):
        step = math.nextafter(step, math.inf)
        upper.append(step)
    return tuple(lower) + (value,) + tuple(upper)


def normalises_to_three_sixty(longitude):
    return longitude % 360.0 == 360.0


def exact_rational_index(longitude):
    """Classify by exact rational arithmetic -- the test's own second opinion.

    Deliberately *not* how the layer does it. The normalisation is the same
    float ``%`` (there is no other definition of "normalised" to compare
    against), but the multiplication and the floor are exact, so this returns
    what the frozen float classification would return if doubles were reals.
    """
    return math.floor(Fraction(longitude % 360.0) * 27 / 360)


def quantized(offset, convention):
    """The specification's quantization rule, spelled out in the test."""
    return math.floor(offset * convention.value * MICROSECONDS_PER_DAY)


def chain_lords(periods):
    return tuple(period.lord for period in periods)


# --- constants and the nakshatra mapping -----------------------------------


def test_the_nine_lord_years_sum_to_the_cycle():
    assert sum(LORD_YEARS.values()) == CYCLE_YEARS == 120


def test_the_lord_sequence_is_the_nine_grahas_once_each():
    assert isinstance(LORD_SEQUENCE, tuple)
    assert len(LORD_SEQUENCE) == 9
    assert set(LORD_SEQUENCE) == set(Graha)
    assert len(set(LORD_SEQUENCE)) == 9
    assert set(LORD_YEARS) == set(Graha)


def test_the_lord_sequence_is_the_bphs_order_rotated_to_ashwini():
    """BPHS counts from Krittika, which is nakshatra index 2."""
    from_krittika = (
        Graha.SUN,
        Graha.MOON,
        Graha.MARS,
        Graha.RAHU,
        Graha.JUPITER,
        Graha.SATURN,
        Graha.MERCURY,
        Graha.KETU,
        Graha.VENUS,
    )
    rotated = tuple(from_krittika[(step - 2) % 9] for step in range(9))

    assert LORD_SEQUENCE == rotated
    assert [LORD_YEARS[lord] for lord in from_krittika] == [
        6, 10, 7, 18, 16, 19, 17, 7, 20
    ]


@pytest.mark.parametrize("index", range(NAKSHATRA_COUNT))
def test_each_nakshatra_has_its_classical_lord(index):
    name, lord = NAKSHATRA_LORDS[index]
    inside = index * 40.0 / 3.0 + 1.0

    assert NAKSHATRA_NAMES[index] == name
    assert LORD_SEQUENCE[index % 9] == lord
    assert classify(inside).nakshatra_index == index

    line = timeline(inside, CONVENTIONS[0])
    assert line.nakshatra_name == name
    assert line.lord == lord
    assert line.mahadashas[0].lord == lord
    assert line.mahadashas[0].nominal_years == LORD_YEARS[lord]


def test_the_nakshatra_count_matches_the_frozen_name_table():
    assert NAKSHATRA_COUNT == len(NAKSHATRA_NAMES) == len(NAKSHATRA_LORDS) == 27


def test_microseconds_per_day_is_the_real_conversion():
    assert MICROSECONDS_PER_DAY == 24 * 60 * 60 * 1_000_000
    assert timedelta(days=1) // MICROSECOND == MICROSECONDS_PER_DAY


def test_the_year_conventions_are_exact_ratios_not_floats():
    assert YearConvention.FIXED_365_25.value == Fraction(1461, 4)
    assert YearConvention.FIXED_365_256363.value == Fraction(365256363, 1000000)
    assert YearConvention.FIXED_365_25.value == Fraction("365.25")
    assert YearConvention.FIXED_365_256363.value == Fraction("365.256363")
    # The trap the specification names: the binary neighbour of the decimal is
    # a different number, and it is what Fraction(float) would have given.
    assert YearConvention.FIXED_365_256363.value != Fraction(365.256363)
    assert len(YearConvention) == 2


def test_the_public_duration_constants_cannot_be_mutated():
    with pytest.raises(TypeError):
        LORD_YEARS[Graha.SUN] = 7
    with pytest.raises(TypeError):
        del LORD_YEARS[Graha.SUN]
    with pytest.raises(AttributeError):
        LORD_YEARS.clear()
    with pytest.raises(TypeError):
        LORD_SEQUENCE[0] = Graha.SUN

    assert LORD_YEARS[Graha.SUN] == 6
    assert LORD_SEQUENCE[0] is Graha.KETU


def test_the_result_objects_are_frozen():
    line = timeline(JALANDHAR_MOON, CONVENTIONS[0], JALANDHAR_BIRTH)
    period = line.mahadashas[0]

    with pytest.raises(dataclasses.FrozenInstanceError):
        line.lord = Graha.SUN
    with pytest.raises(dataclasses.FrozenInstanceError):
        period.nominal_years = Fraction(1)

    assert isinstance(line.mahadashas, tuple)
    assert isinstance(period.children, tuple)
    assert isinstance(period.lords, tuple)


# --- the 27 boundary neighbourhoods ----------------------------------------


@pytest.mark.parametrize("k", range(NAKSHATRA_COUNT))
def test_the_boundary_neighbourhood_classifies_as_the_frozen_layer_does(k):
    """``float(B_k)`` and its 64 nearest doubles on each side (section 10).

    Two classes. Negative doubles that Python's float ``%`` wraps all the way
    to ``360.0`` -- the 64 lower neighbours of zero, subnormals down to
    ``-5e-324`` -- are rejected inputs and are asserted to raise. Everything
    else must classify exactly as the frozen ``classify`` does and yield an
    elapsed fraction in ``[0, 1)``.
    """
    exact_boundary = Fraction(k * 40, 3)
    inputs = doubles_around(float(exact_boundary))
    assert len(inputs) == 129

    rejected = []
    for longitude in inputs:
        if normalises_to_three_sixty(longitude):
            assert longitude < 0.0
            rejected.append(longitude)
            with pytest.raises(ValueError):
                _classify_moon(longitude)
            with pytest.raises(ValueError):
                build_vimshottari(longitude, ANCHOR, CONVENTIONS[0])
            continue

        normalized, index, elapsed = _classify_moon(longitude)
        assert index == classify(longitude).nakshatra_index
        assert normalized == longitude % 360.0
        assert Fraction(0) <= elapsed < 1

    assert len(rejected) == (64 if k == 0 else 0)


@pytest.mark.parametrize("k", range(NAKSHATRA_COUNT))
def test_the_built_timeline_agrees_with_the_helper_at_each_boundary(k):
    """The sampled full builds behind the sweep above."""
    exact_boundary = float(Fraction(k * 40, 3))
    samples = [exact_boundary, math.nextafter(exact_boundary, math.inf)]
    below = math.nextafter(exact_boundary, -math.inf)
    if not normalises_to_three_sixty(below):
        samples.append(below)

    for longitude in samples:
        normalized, index, elapsed = _classify_moon(longitude)
        line = timeline(longitude, CONVENTIONS[0])

        assert line.moon_sidereal_longitude == longitude
        assert line.normalized_longitude == normalized
        assert line.nakshatra_index == index
        assert line.nakshatra_number == index + 1
        assert line.nakshatra_name == NAKSHATRA_NAMES[index]
        assert line.elapsed_fraction == elapsed
        assert line.remaining_fraction == 1 - elapsed
        assert line.lord == LORD_SEQUENCE[index % 9]
        assert line.elapsed_years == elapsed * LORD_YEARS[line.lord]
        assert line.balance_years == (1 - elapsed) * LORD_YEARS[line.lord]


@pytest.mark.parametrize("k", range(NAKSHATRA_COUNT))
def test_float_classification_never_falls_below_the_rational_one(k):
    """Within the examined neighbourhood, float never classifies *lower*.

    The asymmetry is the point. A double one ULP below a boundary can round
    *up* past it once multiplied, which is how the four conflicts of section 5
    arise; nothing rounds the other way, so following the frozen index can
    never produce a negative elapsed fraction.
    """
    disagreements = []
    for longitude in doubles_around(float(Fraction(k * 40, 3))):
        if normalises_to_three_sixty(longitude):
            continue
        frozen = classify(longitude).nakshatra_index
        rational = exact_rational_index(longitude)
        assert frozen >= rational, (longitude, frozen, rational)
        if frozen != rational:
            disagreements.append((longitude, frozen, rational))

    assert disagreements == [
        (value, index, index - 1)
        for index, value, _distance in CONFLICTING_DOUBLES
        if index == k
    ]


@pytest.mark.parametrize("k,longitude,distance", CONFLICTING_DOUBLES)
def test_the_four_conflicting_doubles_are_handled_as_decided(
    k, longitude, distance
):
    """D1 made visible: the frozen index, and an elapsed fraction of exactly 0.

    The rational fraction into nakshatra ``k`` at these longitudes is
    *negative*; a layer that took the frozen index and the rational fraction
    would report a balance longer than the lord's full years. Taking the
    fraction from the same double the frozen layer floors gives exactly zero
    instead, with no clamp and no nudge.
    """
    exact_boundary = Fraction(k * 40, 3)

    assert float(exact_boundary) == longitude
    assert Fraction(longitude) < exact_boundary
    assert exact_boundary - Fraction(longitude) == distance
    assert exact_rational_index(longitude) == k - 1
    # What the rejected alternative would have produced.
    assert Fraction(longitude) * 27 / 360 - k < 0

    line = timeline(longitude, CONVENTIONS[0])
    assert line.nakshatra_index == k == classify(longitude).nakshatra_index
    assert line.elapsed_fraction == Fraction(0)
    assert line.elapsed_years == Fraction(0)
    assert line.balance_years == LORD_YEARS[line.lord]
    assert line.cycle_start_utc == ANCHOR


def test_the_conflicting_distances_have_the_recorded_denominators():
    assert [
        distance.denominator for _k, _x, distance in CONFLICTING_DOUBLES
    ] == [
        211106232532992,
        105553116266496,
        105553116266496,
        52776558133248,
    ]
    assert CONFLICTING_DOUBLES[0][2] == Fraction(1, 3 * 2**46)
    assert CONFLICTING_DOUBLES[1][2] == Fraction(1, 3 * 2**45)
    assert CONFLICTING_DOUBLES[2][2] == Fraction(1, 3 * 2**45)
    assert CONFLICTING_DOUBLES[3][2] == Fraction(1, 3 * 2**44)


# --- the 0/360 seam --------------------------------------------------------


def test_three_hundred_and_sixty_is_the_start_of_ashwini():
    line = timeline(360.0, CONVENTIONS[0])

    assert line.moon_sidereal_longitude == 360.0
    assert line.normalized_longitude == 0.0
    assert line.nakshatra_index == 0 == classify(360.0).nakshatra_index
    assert line.lord is Graha.KETU
    assert line.elapsed_fraction == Fraction(0)
    assert line.balance_years == 7


def test_a_small_negative_longitude_wraps_into_revati():
    line = timeline(-1e-9, CONVENTIONS[0])

    assert line.moon_sidereal_longitude == -1e-9
    assert line.normalized_longitude == 359.999999999
    assert line.nakshatra_index == 26
    assert line.nakshatra_name == "Revati"
    assert line.lord is Graha.MERCURY


def test_the_largest_double_below_three_sixty_keeps_one_part_in_two_to_48():
    line = timeline(math.nextafter(360.0, 0), CONVENTIONS[0])

    assert line.normalized_longitude == 359.99999999999994
    assert line.nakshatra_index == 26
    assert line.remaining_fraction == Fraction(1, 2**48)
    assert line.balance_years == Fraction(17, 2**48)


@pytest.mark.parametrize("longitude", [-(2.0**-45), -5e-324, -1e-320])
def test_longitudes_that_normalise_to_three_sixty_are_rejected(longitude):
    """The input class the frozen classifier's own assertion would fail on."""
    assert normalises_to_three_sixty(longitude)

    with pytest.raises(ValueError, match="360"):
        build_vimshottari(longitude, ANCHOR, CONVENTIONS[0])


def test_the_rejection_is_not_a_blanket_ban_on_negative_longitudes():
    assert timeline(-40.0, CONVENTIONS[0]).nakshatra_index == 24
    assert timeline(-1e-6, CONVENTIONS[0]).nakshatra_index == 26


# --- hand-worked conversions -----------------------------------------------


def test_zero_is_the_first_instant_of_ashwini():
    line = timeline(0.0, CONVENTIONS[0])

    assert (line.nakshatra_index, line.nakshatra_number) == (0, 1)
    assert line.nakshatra_name == "Ashwini"
    assert line.lord is Graha.KETU
    assert line.elapsed_fraction == Fraction(0)
    assert line.elapsed_years == Fraction(0)
    assert line.balance_years == Fraction(7)
    assert line.cycle_start_utc == ANCHOR


def test_forty_degrees_is_the_exactly_representable_start_of_rohini():
    line = timeline(40.0, CONVENTIONS[0])

    assert Fraction(40) == Fraction(3 * 40, 3)
    assert line.nakshatra_index == 3
    assert line.nakshatra_name == "Rohini"
    assert line.lord is Graha.MOON
    assert line.elapsed_fraction == Fraction(0)
    assert line.balance_years == Fraction(10)


def test_mid_uttara_phalguni_keeps_the_double_exactly():
    line = timeline(153.3333333333333, CONVENTIONS[0])

    assert line.nakshatra_index == 11
    assert line.nakshatra_name == "Uttara Phalguni"
    assert line.lord is Graha.SUN
    assert line.elapsed_fraction == Fraction(281474976710655, 562949953421312)
    assert line.elapsed_years == line.elapsed_fraction * 6


def test_the_tiny_balance_case_is_the_hand_computed_one():
    line = timeline(TINY_BALANCE_MOON, CONVENTIONS[0])

    assert TINY_BALANCE_MOON == 39.99999999999999
    assert line.nakshatra_index == 2
    assert line.nakshatra_name == "Krittika"
    assert line.lord is Graha.SUN
    assert line.elapsed_fraction == Fraction(2**51 - 1, 2**51)
    assert line.remaining_fraction == Fraction(1, 2**51)
    assert line.balance_years == Fraction(6, 2**51)

    # Under a tenth of a microsecond, so the floor takes it to nothing.
    for convention in CONVENTIONS:
        micros = line.balance_years * convention.value * MICROSECONDS_PER_DAY
        assert 0 < micros < Fraction(1, 10)
        assert math.floor(micros) == 0


# --- the shape of one cycle ------------------------------------------------


def identity(period):
    """A period's value fingerprint, cheap enough to assert in a loop.

    Full ``==`` on a Mahadasha walks its 90 descendants; the six fields below
    already determine a period uniquely within a timeline, and comparing them
    is still comparing by value.
    """
    return (
        period.level,
        period.lords,
        period.nominal_start,
        period.nominal_end,
        period.start_utc,
        period.end_utc,
    )


def own_lord_first(lord):
    start = LORD_SEQUENCE.index(lord)
    return tuple(LORD_SEQUENCE[(start + step) % 9] for step in range(9))


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", STRUCTURAL_IDS)
def test_the_cycle_is_nine_mahadashas_from_the_true_pre_birth_start(
    name, convention
):
    line = structural(name, convention)

    assert len(line.mahadashas) == 9
    assert tuple(md.lord for md in line.mahadashas) == own_lord_first(line.lord)
    assert sum(md.nominal_years for md in line.mahadashas) == CYCLE_YEARS
    assert line.mahadashas[0].nominal_start == -line.elapsed_years
    assert line.mahadashas[-1].nominal_end == CYCLE_YEARS - line.elapsed_years
    assert line.cycle_start_utc == line.mahadashas[0].start_utc
    assert line.cycle_end_utc == line.mahadashas[-1].end_utc
    assert line.cycle_start_utc <= line.birth_utc < line.cycle_end_utc
    assert line.year is convention
    assert all(md.level == 1 and len(md.lords) == 1 for md in line.mahadashas)


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", STRUCTURAL_IDS)
def test_every_parent_is_partitioned_exactly_by_its_nine_children(
    name, convention
):
    """Exact, not approximate: these are ``Fraction``s and they must be equal."""
    line = structural(name, convention)
    parents = list(every_parent(line))
    assert len(parents) == 9 + 81

    for parent in parents:
        children = parent.children
        assert len(children) == 9
        assert tuple(child.lord for child in children) == own_lord_first(
            parent.lord
        )
        assert sum(child.nominal_years for child in children) == (
            parent.nominal_years
        )
        assert children[0].nominal_start == parent.nominal_start
        assert children[-1].nominal_end == parent.nominal_end
        for index, child in enumerate(children):
            assert child.level == parent.level + 1
            assert child.lords == parent.lords + (child.lord,)
            assert child.nominal_end == child.nominal_start + child.nominal_years
            if index:
                assert child.nominal_start == children[index - 1].nominal_end

    for pratyantar in (
        pd for md in line.mahadashas for ad in md.children for pd in ad.children
    ):
        assert pratyantar.children == ()
        assert pratyantar.level == 3


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", STRUCTURAL_IDS)
def test_the_child_durations_are_the_classical_proportions(name, convention):
    line = structural(name, convention)

    for mahadasha in line.mahadashas:
        assert mahadasha.nominal_years == LORD_YEARS[mahadasha.lord]
        for antardasha in mahadasha.children:
            assert antardasha.nominal_years == Fraction(
                LORD_YEARS[mahadasha.lord] * LORD_YEARS[antardasha.lord],
                CYCLE_YEARS,
            )
            for pratyantar in antardasha.children:
                assert pratyantar.nominal_years == Fraction(
                    LORD_YEARS[mahadasha.lord]
                    * LORD_YEARS[antardasha.lord]
                    * LORD_YEARS[pratyantar.lord],
                    CYCLE_YEARS**2,
                )


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", STRUCTURAL_IDS)
def test_shared_quantized_endpoints_are_identical(name, convention):
    line = structural(name, convention)

    for parent in every_parent(line):
        children = parent.children
        assert children[0].start_utc == parent.start_utc
        assert children[-1].end_utc == parent.end_utc
        for index in range(8):
            assert children[index + 1].start_utc == children[index].end_utc


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", STRUCTURAL_IDS)
def test_all_boundaries_are_monotone_and_no_period_is_empty(name, convention):
    line = structural(name, convention)
    periods = list(every_period(line))
    assert len(periods) == 9 + 81 + 729

    for period in periods:
        # The shortest possible pratyantar is 343/14400 nominal years, about
        # nine days, so nothing here can quantize to an empty interval.
        assert period.start_utc < period.end_utc
        assert period.nominal_start < period.nominal_end

    for level in (1, 2, 3):
        at_level = [p for p in periods if p.level == level]
        starts = [p.start_utc for p in at_level]
        assert starts == sorted(starts)
        assert all(
            at_level[i].end_utc <= at_level[i + 1].start_utc
            for i in range(len(at_level) - 1)
        )


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", STRUCTURAL_IDS)
def test_every_instant_is_the_floor_of_the_exact_product(name, convention):
    """The quantization rule, recomputed in the test from the Fractions."""
    line = structural(name, convention)

    for period in every_period(line):
        assert period.start_utc == line.birth_utc + timedelta(
            microseconds=quantized(period.nominal_start, convention)
        )
        assert period.end_utc == line.birth_utc + timedelta(
            microseconds=quantized(period.nominal_end, convention)
        )
        span = (period.end_utc - period.start_utc) // MICROSECOND
        nominal = quantized(period.nominal_years, convention)
        assert span - nominal in (0, 1)


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", STRUCTURAL_IDS)
def test_the_pre_birth_start_floors_toward_minus_infinity(name, convention):
    """A negative offset must land no *later* than its exact instant."""
    line = structural(name, convention)
    offset = line.mahadashas[0].nominal_start
    exact = offset * convention.value * MICROSECONDS_PER_DAY
    micros = (line.cycle_start_utc - line.birth_utc) // MICROSECOND

    assert offset <= 0
    assert micros == math.floor(exact)
    assert micros <= exact
    assert exact - micros < 1
    if offset != 0:
        assert micros < 0


# --- the two year conventions ----------------------------------------------

CONVENTION_OFFSETS = (
    Fraction(-1, 7),
    Fraction(1, 3),
    Fraction(7, 2),
    JALANDHAR_BALANCE,
    JAMMU_BALANCE,
    -Fraction(87164189005907, 17592186044416) - 11,
    Fraction(0),
    Fraction(120),
)


@pytest.mark.parametrize("offset", CONVENTION_OFFSETS, ids=str)
def test_the_two_conventions_are_compared_by_exact_floors(offset):
    """Each floor computed independently; the difference is then *bounded*.

    The specification is explicit that the gap between the conventions is not
    in general ``floor(o * dY * C)`` -- it is that or one microsecond more --
    so the two anchored floors are the primary assertion and the difference is
    only checked to lie in the two-element set.
    """
    first = YearConvention.FIXED_365_25.value
    second = YearConvention.FIXED_365_256363.value

    low = math.floor(offset * first * MICROSECONDS_PER_DAY)
    high = math.floor(offset * second * MICROSECONDS_PER_DAY)
    assert low == quantized(offset, YearConvention.FIXED_365_25)
    assert high == quantized(offset, YearConvention.FIXED_365_256363)

    gap = math.floor(offset * (second - first) * MICROSECONDS_PER_DAY)
    assert high - low in (gap, gap + 1)


def test_the_convention_gap_is_sometimes_the_floor_plus_one():
    """The two-element set is not a formality: both values really occur.

    Both signs of offset are swept, because the specification makes the claim
    for negative offsets -- the pre-birth Mahadasha start -- as well.
    """
    first = YearConvention.FIXED_365_25.value
    second = YearConvention.FIXED_365_256363.value
    seen = set()

    for denominator in (3, 7, 11, 13, 97):
        for numerator in range(-500, 500):
            offset = Fraction(numerator, denominator)
            low = math.floor(offset * first * MICROSECONDS_PER_DAY)
            high = math.floor(offset * second * MICROSECONDS_PER_DAY)
            gap = math.floor(
                offset * (second - first) * MICROSECONDS_PER_DAY
            )
            seen.add(high - low - gap)

    assert seen == {0, 1}


@pytest.mark.parametrize("name", STRUCTURAL_IDS)
def test_the_conventions_differ_but_share_the_nominal_arithmetic(name):
    slow = structural(name, YearConvention.FIXED_365_25)
    fast = structural(name, YearConvention.FIXED_365_256363)

    assert slow.elapsed_fraction == fast.elapsed_fraction
    assert slow.balance_years == fast.balance_years
    assert [md.lord for md in slow.mahadashas] == [
        md.lord for md in fast.mahadashas
    ]
    assert [md.nominal_end for md in slow.mahadashas] == [
        md.nominal_end for md in fast.mahadashas
    ]
    # 365.256363 days is the longer year, so every post-birth boundary moves
    # later and every pre-birth boundary moves earlier.
    assert fast.cycle_end_utc > slow.cycle_end_utc
    if slow.cycle_start_utc != slow.birth_utc:
        assert fast.cycle_start_utc <= slow.cycle_start_utc


# --- the two internal reference births (section 9) -------------------------


def test_jalandhar_reproduces_the_reference_row():
    line = timeline(JALANDHAR_MOON, CONVENTIONS[0], JALANDHAR_BIRTH)
    mahadasha, antardasha, pratyantar = line.periods_at_birth()

    assert line.nakshatra_index == 15
    assert line.nakshatra_number == 16
    assert line.nakshatra_name == "Vishakha"
    assert line.lord is Graha.JUPITER
    assert LORD_YEARS[line.lord] == 16
    assert abs(float(line.elapsed_fraction) - 0.690330593417162) < 1e-15
    assert abs(float(line.remaining_fraction) - 0.30966940658283804) < 1e-15
    assert abs(float(line.elapsed_years) - 11.045289494674591) < 1e-13
    assert line.balance_years == JALANDHAR_BALANCE
    assert line.balance_years == line.remaining_fraction * 16

    assert chain_lords((mahadasha, antardasha, pratyantar)) == (
        Graha.JUPITER,
        Graha.SUN,
        Graha.MERCURY,
    )
    assert mahadasha.children.index(antardasha) == 5      # 6th of 9
    assert antardasha.nominal_years == Fraction(4, 5)
    assert pratyantar.nominal_years == Fraction(17, 150)
    assert abs(float(antardasha.nominal_end) - 0.288044) < 5e-7
    assert abs(float(pratyantar.nominal_end) - 0.108044) < 5e-7
    assert [md.lord.name for md in line.mahadashas[1:]] == [
        "SATURN", "MERCURY", "KETU", "VENUS", "SUN", "MOON", "MARS", "RAHU"
    ]


def test_jammu_reproduces_the_reference_row():
    line = timeline(JAMMU_MOON, CONVENTIONS[0], JAMMU_BIRTH)
    mahadasha, antardasha, pratyantar = line.periods_at_birth()

    assert line.nakshatra_index == 4
    assert line.nakshatra_number == 5
    assert line.nakshatra_name == "Mrigashira"
    assert line.lord is Graha.MARS
    assert LORD_YEARS[line.lord] == 7
    assert abs(float(line.elapsed_fraction) - 0.11692219677899285) < 1e-15
    assert abs(float(line.remaining_fraction) - 0.8830778032210072) < 1e-15
    assert abs(float(line.elapsed_years) - 0.8184553774529499) < 1e-14
    assert line.balance_years == JAMMU_BALANCE
    assert line.balance_years == line.remaining_fraction * 7

    assert chain_lords((mahadasha, antardasha, pratyantar)) == (
        Graha.MARS,
        Graha.RAHU,
        Graha.SATURN,
    )
    assert mahadasha.children.index(antardasha) == 1      # 2nd of 9
    assert antardasha.nominal_years == Fraction(21, 20)
    assert pratyantar.nominal_years == Fraction(133, 800)
    assert abs(float(antardasha.nominal_end) - 0.639878) < 5e-7
    assert abs(float(pratyantar.nominal_end) - 0.053628) < 5e-7
    assert [md.lord.name for md in line.mahadashas[1:]] == [
        "RAHU", "JUPITER", "SATURN", "MERCURY", "KETU", "VENUS", "SUN", "MOON"
    ]


@pytest.mark.parametrize(
    "longitude,birth,slow_end,fast_end",
    [
        (
            JALANDHAR_MOON,
            JALANDHAR_BIRTH,
            datetime(2000, 3, 3, 23, 44, tzinfo=IST),
            datetime(2000, 3, 4, 0, 29, tzinfo=IST),
        ),
        (
            JAMMU_MOON,
            JAMMU_BIRTH,
            datetime(2007, 4, 12, 6, 10, tzinfo=IST),
            datetime(2007, 4, 12, 7, 6, tzinfo=IST),
        ),
    ],
    ids=["jalandhar", "jammu"],
)
def test_the_birth_mahadasha_end_matches_the_sensitivity_table(
    longitude, birth, slow_end, fast_end
):
    """Section 9's table, which is printed in IST and only to the minute."""
    for convention, expected in (
        (YearConvention.FIXED_365_25, slow_end),
        (YearConvention.FIXED_365_256363, fast_end),
    ):
        line = timeline(longitude, convention, birth)
        end = line.periods_at_birth()[0].end_utc.astimezone(IST)
        assert end.replace(second=0, microsecond=0) == expected


# --- the birth chain, and the rules that would get it wrong ----------------


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", STRUCTURAL_IDS)
def test_the_birth_chain_is_the_only_one_containing_offset_zero(
    name, convention
):
    """Brute force over all 9 + 81 + 729 nominal intervals."""
    line = structural(name, convention)
    zero = Fraction(0)

    for level in (1, 2, 3):
        matches = [
            period
            for period in every_period(line)
            if period.level == level
            and period.nominal_start <= zero < period.nominal_end
        ]
        assert len(matches) == 1
        assert identity(matches[0]) == identity(line.periods_at_birth()[level - 1])

    assert len([p for p in every_period(line) if p.level == 3]) == 729
    assert line.periods_at_birth()[0] == line.mahadashas[0]


def antardasha_lord_at(line, offset, rule):
    """The antardasha lord at ``offset`` under one of three layout rules.

    ``"full"`` is the implemented rule: the nine antardashas tile the *whole*
    Mahadasha from its pre-birth start. ``"restart"`` restarts the sequence at
    the birth with full-length children. ``"balance"`` subdivides only the
    post-birth balance. The last two are the rejected readings of the
    classical text, written out here so the difference is demonstrated rather
    than asserted.
    """
    if rule == "full":
        cursor = line.mahadashas[0].nominal_start
        total = Fraction(LORD_YEARS[line.lord])
    elif rule == "restart":
        cursor = Fraction(0)
        total = Fraction(LORD_YEARS[line.lord])
    else:
        cursor = Fraction(0)
        total = line.balance_years

    for lord in own_lord_first(line.lord):
        length = total * LORD_YEARS[lord] / CYCLE_YEARS
        if cursor <= offset < cursor + length:
            return lord
        cursor += length
    return None


@pytest.mark.parametrize(
    "longitude,birth",
    [(JALANDHAR_MOON, JALANDHAR_BIRTH), (JAMMU_MOON, JAMMU_BIRTH)],
    ids=["jalandhar", "jammu"],
)
@pytest.mark.parametrize("offset", [Fraction(0), Fraction(1)], ids=["birth", "one_year"])
def test_the_rejected_subdivision_rules_give_a_different_chain(
    longitude, birth, offset
):
    line = timeline(longitude, CONVENTIONS[0], birth)

    implemented = antardasha_lord_at(line, offset, "full")
    restarted = antardasha_lord_at(line, offset, "restart")
    balance_only = antardasha_lord_at(line, offset, "balance")

    assert implemented is not None
    if offset == 0:
        assert implemented == line.periods_at_birth()[1].lord
        assert restarted is line.lord and balance_only is line.lord
    assert implemented != restarted
    assert implemented != balance_only


# --- where the two queries part company ------------------------------------


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
def test_a_sub_microsecond_balance_collapses_all_three_levels(convention):
    """The hand-computed ``nextafter(40.0, 0)`` case of section 7."""
    line = timeline(TINY_BALANCE_MOON, convention)
    at_birth = line.periods_at_birth()

    assert chain_lords(at_birth) == (Graha.SUN, Graha.VENUS, Graha.KETU)
    assert all(period.end_utc == line.birth_utc for period in at_birth)
    assert all(period.start_utc < line.birth_utc for period in at_birth)

    active = line.active_periods_at(line.birth_utc)
    assert chain_lords(active) == (Graha.MOON, Graha.MOON, Graha.MOON)
    assert all(period.start_utc == line.birth_utc for period in active)
    assert line.cycle_start_utc < line.birth_utc


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
def test_a_sub_microsecond_antardasha_collapses_only_levels_two_and_three(
    convention
):
    """The searched double 3.666666666666666 (see its definition above)."""
    line = timeline(TINY_SUBPERIOD_MOON, convention)
    at_birth = line.periods_at_birth()
    active = line.active_periods_at(line.birth_utc)

    assert line.lord is Graha.KETU
    assert chain_lords(at_birth) == (Graha.KETU, Graha.SUN, Graha.VENUS)
    assert chain_lords(active) == (Graha.KETU, Graha.MOON, Graha.MOON)

    # Level 1 agrees, and has years left to run: this is not the whole
    # Mahadasha collapsing, only its antardasha and pratyantar.
    assert identity(at_birth[0]) == identity(active[0])
    assert at_birth[0].nominal_end == 7 - line.elapsed_years
    assert abs(float(at_birth[0].nominal_end) - 5.075) < 1e-12
    assert at_birth[0].end_utc > line.birth_utc + timedelta(days=1800)

    assert at_birth[1].nominal_end == at_birth[2].nominal_end
    assert at_birth[1].nominal_end == TINY_SUBPERIOD_OFFSET
    assert TINY_SUBPERIOD_OFFSET > 0
    assert (
        TINY_SUBPERIOD_OFFSET * convention.value * MICROSECONDS_PER_DAY < 1
    )
    assert at_birth[1].end_utc == line.birth_utc
    assert at_birth[2].end_utc == line.birth_utc
    assert active[1].start_utc == line.birth_utc


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", ["jalandhar", "jammu", "mid_uttara_phalguni"])
def test_the_two_queries_agree_when_nothing_collapses(name, convention):
    line = structural(name, convention)

    assert [identity(p) for p in line.periods_at_birth()] == [
        identity(p) for p in line.active_periods_at(line.birth_utc)
    ]


# --- half-open intervals, queried at their own boundaries ------------------


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", STRUCTURAL_IDS)
def test_a_period_start_belongs_to_that_period(name, convention):
    line = structural(name, convention)

    for period in every_period(line):
        found = line.active_periods_at(period.start_utc)[period.level - 1]
        assert identity(found) == identity(period)

    # One full value comparison, to show the fingerprint is not hiding a
    # difference the dataclass would have caught.
    first = line.mahadashas[0]
    assert line.active_periods_at(first.start_utc)[0] == first


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", STRUCTURAL_IDS)
def test_a_period_end_belongs_to_the_next_period(name, convention):
    line = structural(name, convention)

    for index in range(8):
        this, following = line.mahadashas[index], line.mahadashas[index + 1]
        assert identity(line.active_periods_at(this.end_utc)[0]) == identity(
            following
        )

    for parent in every_parent(line):
        for index in range(8):
            this = parent.children[index]
            following = parent.children[index + 1]
            found = line.active_periods_at(this.end_utc)[this.level - 1]
            assert identity(found) == identity(following)


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
@pytest.mark.parametrize("name", STRUCTURAL_IDS)
def test_queries_outside_the_cycle_raise(name, convention):
    line = structural(name, convention)

    with pytest.raises(DashaRangeError):
        line.active_periods_at(line.cycle_end_utc)
    with pytest.raises(DashaRangeError):
        line.active_periods_at(line.cycle_start_utc - MICROSECOND)

    # The two instants just inside are answered normally.
    assert line.active_periods_at(line.cycle_start_utc)[0] == line.mahadashas[0]
    assert (
        line.active_periods_at(line.cycle_end_utc - MICROSECOND)[0]
        == line.mahadashas[-1]
    )


def test_a_query_instant_is_normalised_to_utc_like_the_birth():
    line = timeline(JALANDHAR_MOON, CONVENTIONS[0], JALANDHAR_BIRTH)
    boundary = line.mahadashas[3].start_utc

    assert identity(
        line.active_periods_at(boundary.astimezone(IST))[0]
    ) == identity(line.active_periods_at(boundary)[0])


# --- input validation ------------------------------------------------------


class _NoOffset(tzinfo):
    """A tzinfo that admits to knowing no offset -- legal, and unusable."""

    def utcoffset(self, value):
        return None

    def dst(self, value):
        return None

    def tzname(self, value):
        return None


@pytest.mark.parametrize(
    "year", ["FIXED_365_25", 365.25, Fraction(1461, 4), None, 0]
)
def test_the_year_convention_must_be_a_member(year):
    with pytest.raises(TypeError):
        build_vimshottari(0.0, ANCHOR, year)


def test_the_year_convention_has_no_default():
    with pytest.raises(TypeError):
        build_vimshottari(0.0, ANCHOR)


@pytest.mark.parametrize("longitude", [True, False, "40.0", None, Fraction(40)])
def test_a_non_numeric_longitude_is_a_type_error(longitude):
    with pytest.raises(TypeError):
        build_vimshottari(longitude, ANCHOR, CONVENTIONS[0])


@pytest.mark.parametrize(
    "longitude", [float("nan"), float("inf"), float("-inf")]
)
def test_a_non_finite_longitude_is_a_value_error(longitude):
    with pytest.raises(ValueError):
        build_vimshottari(longitude, ANCHOR, CONVENTIONS[0])


def test_an_integer_longitude_is_accepted_and_stored_as_a_float():
    line = timeline(40, CONVENTIONS[0])

    assert line.moon_sidereal_longitude == 40.0
    assert isinstance(line.moon_sidereal_longitude, float)
    assert line.nakshatra_index == 3


@pytest.mark.parametrize(
    "birth",
    [date(2000, 1, 1), "2000-01-01T12:00:00+00:00", 946728000.0, None],
)
def test_a_non_datetime_birth_is_a_type_error(birth):
    with pytest.raises(TypeError):
        build_vimshottari(0.0, birth, CONVENTIONS[0])

    line = timeline(0.0, CONVENTIONS[0])
    with pytest.raises(TypeError):
        line.active_periods_at(birth)


def test_a_naive_birth_is_a_value_error():
    with pytest.raises(ValueError):
        build_vimshottari(0.0, datetime(2000, 1, 1, 12, 0), CONVENTIONS[0])

    line = timeline(0.0, CONVENTIONS[0])
    with pytest.raises(ValueError):
        line.active_periods_at(datetime(2000, 1, 1, 12, 0))


def test_a_tzinfo_without_an_offset_is_a_value_error():
    unusable = datetime(2000, 1, 1, 12, 0, tzinfo=_NoOffset())
    assert unusable.tzinfo is not None
    assert unusable.utcoffset() is None

    with pytest.raises(ValueError):
        build_vimshottari(0.0, unusable, CONVENTIONS[0])

    line = timeline(0.0, CONVENTIONS[0])
    with pytest.raises(ValueError):
        line.active_periods_at(unusable)


def test_an_aware_birth_is_normalised_to_utc():
    """The same instant spelled two ways must give the same timeline."""
    in_ist = build_vimshottari(
        JALANDHAR_MOON,
        datetime(1995, 3, 21, 6, 45, tzinfo=IST),
        CONVENTIONS[0],
    )
    in_utc = timeline(JALANDHAR_MOON, CONVENTIONS[0], JALANDHAR_BIRTH)

    assert in_ist.birth_utc == JALANDHAR_BIRTH
    assert in_ist.birth_utc.tzinfo is timezone.utc
    assert in_ist == in_utc


# --- the datetime range guard ----------------------------------------------


def assert_range_error(build):
    """``DashaRangeError`` and nothing else -- in particular no overflow."""
    try:
        build()
    except DashaRangeError:
        return
    except OverflowError as error:  # pragma: no cover - the bug being guarded
        pytest.fail(f"an OverflowError escaped the layer: {error!r}")
    pytest.fail("no DashaRangeError was raised")


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
def test_a_pre_birth_start_below_datetime_min_is_refused(convention):
    """26.0 degrees is late Bharani: Venus, with about 19 years elapsed."""
    birth = datetime(1, 1, 5, 0, 0, tzinfo=timezone.utc)
    line_later = build_vimshottari(26.0, ANCHOR, convention)

    assert line_later.lord is Graha.VENUS
    assert line_later.elapsed_years > 18

    assert_range_error(lambda: build_vimshottari(26.0, birth, convention))

    # The guard is about the offset, not about the year: the same birth with a
    # Moon at the very start of its nakshatra has nothing before it.
    assert build_vimshottari(0.0, birth, convention).cycle_start_utc == birth


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
def test_a_cycle_end_beyond_datetime_max_is_refused(convention):
    birth = datetime(9990, 1, 1, 0, 0, tzinfo=timezone.utc)

    assert_range_error(lambda: build_vimshottari(0.0, birth, convention))
    assert_range_error(lambda: build_vimshottari(JAMMU_MOON, birth, convention))


@pytest.mark.parametrize("convention", CONVENTIONS, ids=lambda c: c.name)
def test_an_unconvertible_aware_birth_is_refused_at_normalisation(convention):
    """``astimezone`` itself overflows here, before any dasha arithmetic."""
    birth = datetime(1, 1, 1, 2, 0, tzinfo=IST)
    with pytest.raises(OverflowError):
        birth.astimezone(timezone.utc)

    assert_range_error(lambda: build_vimshottari(26.0, birth, convention))
    assert_range_error(lambda: build_vimshottari(0.0, birth, convention))


def test_the_range_guard_leaves_ordinary_births_alone():
    early = build_vimshottari(
        0.0, datetime(1800, 1, 1, tzinfo=timezone.utc), CONVENTIONS[0]
    )
    late = build_vimshottari(
        26.0, datetime(2399, 12, 31, tzinfo=timezone.utc), CONVENTIONS[0]
    )

    assert early.cycle_end_utc.year == 1920
    assert late.cycle_start_utc.year == 2380
