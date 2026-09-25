"""Layer 17: panchanga transition times (specification section 7).

Against the real ephemeris where the point is the sky, and against injected
``evaluate`` callables where the point is the search logic: the search takes
``evaluate`` exactly as Layer 16's ``find_sunrise_window`` takes
``rise_after``, so probes can be recorded, a stuck or non-monotonic sky can be
injected, and "no ephemeris call" can be asserted for every refused input.

**Membership, everywhere.** Every transition any test obtains is passed through
``verified``, which re-classifies both endpoints through Layer 6 and the Layer
16 classifiers -- not through anything in ``transitions.py`` -- and checks the
cell width and the grid.

**Reference values are engine values.** The Jalandhar and Jammu cells, and the
new-moon cells compared with NASA, are what this engine produced on Linux
x86_64 in the cloud venv. Specification 4.9 claims no cross-platform equality
at this resolution: a different platform may legitimately give an identical or
an adjacent cell, and such a difference is environment-sensitive, like the
last-digit longitude differences of the frozen record.
"""

import ast
import dataclasses
import math
import os
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from types import MappingProxyType

import pytest
import swisseph as swe  # tests may touch the library directly; src may not

from render_helpers import EPHE_DIR, REPO_ROOT
from vedic_chart.astronomy.positions import Body, ephemeris_session
import vedic_chart.panchanga as package
import vedic_chart.panchanga.transitions as transitions_module
from vedic_chart.panchanga import (
    ALL_KINDS,
    ALLOWED_TOLERANCES,
    CALCULATION_CONVENTION,
    DEFAULT_TOLERANCE,
    MAX_INTERVAL,
    MAX_REACH,
    RATE_MAX,
    RATE_MIN,
    SAFE_EVAL_END,
    SAFE_EVAL_START,
    SEARCH_CONVENTION,
    SUPPORTED_END,
    SUPPORTED_START,
    EventId,
    IntervalError,
    InvalidTimezoneError,
    LocalTransition,
    Neighbours,
    PanchangaTransitions,
    Quantity,
    Transition,
    TransitionKind,
    TransitionList,
    TransitionRequestError,
    TransitionSearchError,
    TransitionUncertainty,
    UnsupportedInstantError,
    calculate_panchanga,
    find_transitions,
    list_transitions,
    local_transition,
    next_transition,
    previous_transition,
    same_event,
)
from vedic_chart.panchanga.elements import (
    KARANA_SLOTS,
    KARANA_SPAN,
    NAKSHATRA_SPAN,
    TITHI_SPAN,
    YOGA_SPAN,
    elongation,
    karana_from_elongation,
    longitude_sum,
    nakshatra_from_longitude,
    tithi_from_elongation,
    yoga_from_sum,
)
from vedic_chart.panchanga.transitions import (
    MODEL_NOTE,
    UT1_NOTE,
    default_evaluate,
)
from vedic_chart.sidereal.positions import calculate_sidereal_positions
from vedic_chart.time.julian_day import julian_day_ut
from vedic_chart.time.local_time import normalize_birth_time

TITHI = TransitionKind.TITHI
KARANA = TransitionKind.KARANA
NAKSHATRA = TransitionKind.NAKSHATRA
YOGA = TransitionKind.YOGA

UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
US = timedelta(microseconds=1)
MS = timedelta(milliseconds=1)
SECOND = timedelta(seconds=1)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)

SPAN = {TITHI: TITHI_SPAN, KARANA: KARANA_SPAN, NAKSHATRA: NAKSHATRA_SPAN,
        YOGA: YOGA_SPAN}
COUNT = {TITHI: 30, KARANA: 60, NAKSHATRA: 27, YOGA: 27}

JALANDHAR = normalize_birth_time(date(1995, 3, 21), time(6, 45), "Asia/Kolkata")
JAMMU = normalize_birth_time(date(2001, 2, 4), time(10, 45), "Asia/Kolkata")
JALANDHAR_PLACE = (31.32556, 75.57917, "Asia/Kolkata")


@pytest.fixture(scope="module", autouse=True)
def ephemeris():
    with ephemeris_session(EPHE_DIR):
        yield


def at(year, month, day, hour=0, minute=0, second=0, microsecond=0):
    return datetime(year, month, day, hour, minute, second, microsecond,
                    tzinfo=UTC)


# --- independent classification and the membership check -------------------


def classify(kind, moment):
    """Layer 6 + the Layer 16 classifiers, nothing from ``transitions.py``."""
    sidereal = calculate_sidereal_positions(moment)
    sun = sidereal.bodies[Body.SUN].sidereal_longitude
    moon = sidereal.bodies[Body.MOON].sidereal_longitude
    if kind is TITHI:
        return tithi_from_elongation(elongation(sun, moon))
    if kind is KARANA:
        return karana_from_elongation(elongation(sun, moon))
    if kind is YOGA:
        return yoga_from_sum(longitude_sum(sun, moon))
    return nakshatra_from_longitude(moon)


def on_grid(moment, tolerance):
    return (moment - EPOCH) % tolerance == timedelta(0)


def verified(transition):
    """Specification 7's membership check, applied to every result."""
    kind = transition.kind
    tolerance = transition.tolerance
    assert classify(kind, transition.before_utc) == transition.before
    assert classify(kind, transition.after_utc) == transition.after
    assert classify(kind, transition.before_utc).index == transition.before.index
    assert classify(kind, transition.after_utc).index == transition.after.index
    assert transition.after_utc - transition.before_utc == tolerance
    assert on_grid(transition.before_utc, tolerance)
    assert on_grid(transition.after_utc, tolerance)
    assert transition.after.index == (transition.before.index + 1) % COUNT[kind]
    assert transition.boundary_degrees == transition.after.index * SPAN[kind]
    assert transition.before_julian_day_ut == julian_day_ut(transition.before_utc)
    assert transition.after_julian_day_ut == julian_day_ut(transition.after_utc)
    return transition


def verified_all(items):
    for item in items:
        verified(item)
    return items


def cell(transition):
    return transition.before_utc, transition.after_utc


class Recorder:
    """An ``evaluate`` that records every instant it is asked about."""

    def __init__(self, inner=default_evaluate):
        self.inner = inner
        self.calls = []

    def __call__(self, moment):
        self.calls.append(moment)
        return self.inner(moment)


def refuse(moment):
    raise AssertionError(f"the ephemeris was evaluated at {moment!r}")


@pytest.fixture
def no_ephemeris(monkeypatch):
    """Make the Layer 6 door fail if anything walks through it."""
    monkeypatch.setattr(transitions_module, "calculate_sidereal_positions", refuse)


# --- the Jalandhar event the adversarial tests revolve around ---------------

#: Engine values on Linux x86_64, cloud venv; environment-sensitive per spec
#: section 4.9. Krishna Panchami -> Shashthi for the Jalandhar birth.
JAL_A = at(1995, 3, 21, 13, 45, 8, 200000)
JAL_B = at(1995, 3, 21, 13, 45, 8, 300000)


def jalandhar_tithi_end():
    transition = next_transition(JALANDHAR, TITHI)
    assert cell(transition) == (JAL_A, JAL_B)
    return verified(transition)


# --- constants and vocabulary -----------------------------------------------


def test_the_constants_are_the_specified_ones():
    assert DEFAULT_TOLERANCE == timedelta(milliseconds=100)
    assert ALLOWED_TOLERANCES == (
        MS, 10 * MS, 100 * MS, SECOND, 10 * SECOND, timedelta(minutes=1),
        timedelta(minutes=10), HOUR,
    )
    assert MAX_INTERVAL == timedelta(days=366)
    assert MAX_REACH == timedelta(days=3)
    assert SAFE_EVAL_START == at(1800, 1, 2)
    assert SAFE_EVAL_END == at(2399, 12, 31)
    assert SUPPORTED_START == at(1800, 1, 5) == SAFE_EVAL_START + MAX_REACH
    assert SUPPORTED_END == at(2399, 12, 28) == SAFE_EVAL_END - MAX_REACH
    assert transitions_module.GRID_EPOCH == EPOCH


def test_each_tolerance_divides_the_next_so_the_grids_nest():
    for finer, coarser in zip(ALLOWED_TOLERANCES, ALLOWED_TOLERANCES[1:]):
        assert coarser % finer == timedelta(0)
    # The 1 ms floor is >= 25 Julian Day ULPs near JD 2.46e6 (spec 2.3).
    jd = julian_day_ut(JALANDHAR)
    assert julian_day_ut(JALANDHAR + MS) - jd >= 20 * math.ulp(jd)


#: The implementation's re-run survey (module docstring): the lowest minimum
#: and the highest maximum of each quantity over the two runs, deg/day.
SURVEYED_MINIMUM = {TITHI: 10.740818, KARANA: 10.740818, NAKSHATRA: 11.760259,
                    YOGA: 12.775195}
SURVEYED_MAXIMUM = {TITHI: 14.384510, KARANA: 14.384510, NAKSHATRA: 15.400764,
                    YOGA: 16.419326}


def test_the_rate_constants_keep_their_ten_percent_margins():
    assert dict(RATE_MIN) == {TITHI: 9.66, KARANA: 9.66, NAKSHATRA: 10.58,
                              YOGA: 11.46}
    assert dict(RATE_MAX) == {TITHI: 15.83, KARANA: 15.83, NAKSHATRA: 16.95,
                              YOGA: 18.07}
    for kind in ALL_KINDS:
        assert RATE_MIN[kind] <= 0.9 * SURVEYED_MINIMUM[kind]
        assert RATE_MAX[kind] >= 1.1 * SURVEYED_MAXIMUM[kind]
    assert isinstance(RATE_MIN, MappingProxyType)
    assert isinstance(RATE_MAX, MappingProxyType)


def test_the_kinds_are_in_canonical_order():
    assert list(TransitionKind) == [TITHI, KARANA, NAKSHATRA, YOGA]
    assert ALL_KINDS == (TITHI, KARANA, NAKSHATRA, YOGA)
    assert set(Quantity) == {Quantity.ELONGATION, Quantity.MOON_LONGITUDE,
                             Quantity.LONGITUDE_SUM}


def test_the_error_types_are_the_specified_ones():
    for error in (UnsupportedInstantError, IntervalError, TransitionRequestError):
        assert issubclass(error, ValueError)
    assert issubclass(TransitionSearchError, RuntimeError)
    assert not issubclass(TransitionSearchError, ValueError)


def test_the_search_convention_names_predicate_grid_cell_and_ut1():
    for fragment in ("predicate", "classifier", "never snapped", "grid",
                     "1970-01-01T00:00:00Z", "(before_utc, after_utc]",
                     "start <= after_utc < end", "UT1", "1972"):
        assert fragment in SEARCH_CONVENTION, fragment


def test_the_uncertainty_notes_are_the_specified_text():
    assert UT1_NOTE == (
        "|UT1 − UTC| ≤ 0.9 s under the leap-second regime in force since 1972; "
        "not asserted for instants before 1972 (when civil time was not UTC) "
        "or for future instants should that regime change; the frozen "
        "convention is applied throughout regardless."
    )
    for fragment in ("DE431", "apparent", "Lahiri", "true-equinox",
                     "this engine's", "resolution, not accuracy"):
        assert fragment in MODEL_NOTE, fragment


def test_the_module_contains_no_assert_statement():
    """Every guard is ``if``/``raise``; ``python -O`` strips asserts."""
    source = (REPO_ROOT / "src" / "vedic_chart" / "panchanga" /
              "transitions.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert [node for node in ast.walk(tree) if isinstance(node, ast.Assert)] == []
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "round"
        for node in ast.walk(tree)
    )
    assert transitions_module.__all__ == sorted(transitions_module.__all__)


#: Specification 3's surface plus ``RATE_MAX``; the module additionally
#: exports ``GRID_EPOCH``, ``UT1_NOTE``, ``MODEL_NOTE`` and ``default_evaluate``,
#: which the package does not re-export.
MODULE_ONLY = {"GRID_EPOCH", "MODEL_NOTE", "UT1_NOTE", "default_evaluate"}


def test_the_package_re_exports_the_layer_17_surface():
    for name in transitions_module.__all__:
        if name in MODULE_ONLY:
            assert name not in package.__all__, name
            continue
        assert getattr(package, name) is getattr(transitions_module, name), name
        assert name in package.__all__, name
    assert package.__all__ == sorted(package.__all__)


# --- the reference births ----------------------------------------------------

#: Engine values on Linux x86_64, cloud venv; environment-sensitive per spec
#: section 4.9. kind -> (previous cell, previous names, next cell, next names)
#: at the default 100 ms tolerance.
REFERENCE_CELLS = {
    "jalandhar": {
        TITHI: ((at(1995, 3, 20, 16, 12, 55, 0), at(1995, 3, 20, 16, 12, 55, 100000)),
                ("Chaturthi", "Panchami"),
                (at(1995, 3, 21, 13, 45, 8, 200000), at(1995, 3, 21, 13, 45, 8, 300000)),
                ("Panchami", "Shashthi")),
        KARANA: ((at(1995, 3, 20, 16, 12, 55, 0), at(1995, 3, 20, 16, 12, 55, 100000)),
                 ("Balava", "Kaulava"),
                 (at(1995, 3, 21, 2, 58, 29, 900000), at(1995, 3, 21, 2, 58, 30, 0)),
                 ("Kaulava", "Taitila")),
        NAKSHATRA: ((at(1995, 3, 20, 9, 53, 21, 700000), at(1995, 3, 20, 9, 53, 21, 800000)),
                    ("Swati", "Vishakha"),
                    (at(1995, 3, 21, 8, 8, 56, 600000), at(1995, 3, 21, 8, 8, 56, 700000)),
                    ("Vishakha", "Anuradha")),
        YOGA: ((at(1995, 3, 20, 6, 27, 42, 300000), at(1995, 3, 20, 6, 27, 42, 400000)),
               ("Vyaghata", "Harshana"),
               (at(1995, 3, 21, 3, 16, 31, 700000), at(1995, 3, 21, 3, 16, 31, 800000)),
               ("Harshana", "Vajra")),
    },
    "jammu": {
        TITHI: ((at(2001, 2, 3, 23, 13, 6, 400000), at(2001, 2, 3, 23, 13, 6, 500000)),
                ("Dashami", "Ekadashi"),
                (at(2001, 2, 4, 20, 53, 13, 800000), at(2001, 2, 4, 20, 53, 13, 900000)),
                ("Ekadashi", "Dwadashi")),
        KARANA: ((at(2001, 2, 3, 23, 13, 6, 400000), at(2001, 2, 3, 23, 13, 6, 500000)),
                 ("Garaja", "Vanija"),
                 (at(2001, 2, 4, 10, 7, 50, 800000), at(2001, 2, 4, 10, 7, 50, 900000)),
                 ("Vanija", "Vishti")),
        NAKSHATRA: ((at(2001, 2, 4, 2, 36, 52, 200000), at(2001, 2, 4, 2, 36, 52, 300000)),
                    ("Rohini", "Mrigashira"),
                    (at(2001, 2, 5, 0, 53, 2, 800000), at(2001, 2, 5, 0, 53, 2, 900000)),
                    ("Mrigashira", "Ardra")),
        YOGA: ((at(2001, 2, 3, 8, 16, 47, 800000), at(2001, 2, 3, 8, 16, 47, 900000)),
               ("Brahma", "Indra"),
               (at(2001, 2, 4, 5, 32, 43, 0), at(2001, 2, 4, 5, 32, 43, 100000)),
               ("Indra", "Vaidhriti")),
    },
}
REFERENCE_MOMENTS = {"jalandhar": JALANDHAR, "jammu": JAMMU}


@pytest.mark.parametrize("name", sorted(REFERENCE_CELLS))
def test_the_reference_neighbours_are_the_recorded_engine_cells(name):
    result = find_transitions(REFERENCE_MOMENTS[name])

    assert result.kinds == ALL_KINDS
    assert tuple(result.neighbours) == ALL_KINDS
    for kind, (prev_cell, prev_names, next_cell, next_names) in (
        REFERENCE_CELLS[name].items()
    ):
        entry = result.neighbours[kind]
        verified(entry.previous)
        verified(entry.next)
        assert cell(entry.previous) == prev_cell, kind
        assert (entry.previous.before.name, entry.previous.after.name) == prev_names
        assert cell(entry.next) == next_cell, kind
        assert (entry.next.before.name, entry.next.after.name) == next_names
        assert entry.previous.after_utc <= result.instant_utc < entry.next.before_utc


@pytest.mark.parametrize("name", sorted(REFERENCE_CELLS))
def test_current_is_exactly_layer_16s_answer_at_the_instant(name):
    moment = REFERENCE_MOMENTS[name]
    result = find_transitions(moment)
    panchanga = calculate_panchanga(moment, *JALANDHAR_PLACE)

    assert result.neighbours[TITHI].current == panchanga.tithi
    assert result.neighbours[KARANA].current == panchanga.karana
    assert result.neighbours[NAKSHATRA].current == panchanga.nakshatra
    assert result.neighbours[YOGA].current == panchanga.yoga
    assert result.julian_day_ut == panchanga.julian_day_ut
    assert result.calculation_convention == CALCULATION_CONVENTION
    assert result.search_convention == SEARCH_CONVENTION


def test_single_searches_agree_with_find_transitions():
    result = find_transitions(JAMMU)
    for kind in ALL_KINDS:
        assert next_transition(JAMMU, kind) == result.neighbours[kind].next
        assert previous_transition(JAMMU, kind) == result.neighbours[kind].previous


def test_any_spelling_of_the_instant_gives_the_same_result():
    ist = JALANDHAR.astimezone(timezone(timedelta(hours=5, minutes=30)))
    a = find_transitions(JALANDHAR, kinds=(TITHI,))
    b = find_transitions(ist, kinds=(TITHI,))

    assert b.instant_utc.tzinfo is UTC
    assert a == b


# --- the result types ------------------------------------------------------


def test_neighbours_is_a_read_only_mapping_over_exactly_the_requested_kinds():
    result = find_transitions(JALANDHAR, kinds=[YOGA, TITHI])

    assert result.kinds == (TITHI, YOGA)
    assert isinstance(result.neighbours, MappingProxyType)
    assert tuple(result.neighbours) == (TITHI, YOGA)
    assert KARANA not in result.neighbours
    with pytest.raises(TypeError):
        result.neighbours[KARANA] = result.neighbours[TITHI]
    for entry in result.neighbours.values():
        assert entry.previous.after.index == entry.current.index
        assert entry.next.before.index == entry.current.index
    assert not hasattr(result, "tithi")


def test_the_mapping_is_a_copy_not_a_window_onto_the_callers_dict():
    result = find_transitions(JALANDHAR, kinds=(TITHI,))
    source = dict(result.neighbours)
    rebuilt = dataclasses.replace(result, neighbours=source)
    source.clear()

    assert tuple(rebuilt.neighbours) == (TITHI,)


def test_every_type_is_frozen():
    transition = jalandhar_tithi_end()
    result = find_transitions(JALANDHAR, kinds=(TITHI,))
    listing = list_transitions(JAL_A - HOUR, JAL_B + HOUR, kinds=(TITHI,))
    local = local_transition(transition, "Asia/Kolkata")
    objects = [
        (transition, "after_utc"),
        (transition.uncertainty, "cell_width"),
        (transition.event_id, "after_index"),
        (result.neighbours[TITHI], "next"),
        (result, "tolerance"),
        (listing, "transitions"),
        (local, "after_local"),
    ]
    for value, field in objects:
        assert dataclasses.is_dataclass(value)
        assert type(value).__dataclass_params__.frozen
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, field, None)


@pytest.mark.parametrize(
    "changes",
    [
        {"after_utc": JAL_B + MS},
        # an equivalent zero offset is not timezone.utc itself
        {"before_utc": JAL_A.replace(tzinfo=timezone(timedelta(0), "Z"))},
        {"before_utc": JAL_A + 50 * MS, "after_utc": JAL_B + 50 * MS},
        {"tolerance": timedelta(milliseconds=50)},
        {"boundary_degrees": 250.0},
        {"quantity": Quantity.LONGITUDE_SUM},
        {"kind": KARANA},
        {"before_julian_day_ut": 0.0},
        {"uncertainty": TransitionUncertainty(SECOND, UT1_NOTE, MODEL_NOTE)},
    ],
)
def test_transition_invariants_raise_value_error(changes):
    transition = jalandhar_tithi_end()

    with pytest.raises(ValueError):
        dataclasses.replace(transition, **changes)


def test_transition_requires_consecutive_indices():
    transition = jalandhar_tithi_end()
    following = next_transition(JAL_B, TITHI)

    with pytest.raises(ValueError):
        dataclasses.replace(transition, after=following.after)


def test_neighbours_invariants_raise_value_error():
    entry = find_transitions(JALANDHAR, kinds=(TITHI,)).neighbours[TITHI]
    following = next_transition(entry.next.after_utc, TITHI)

    with pytest.raises(ValueError):
        dataclasses.replace(entry, next=following)
    with pytest.raises(ValueError):
        dataclasses.replace(entry, kind=KARANA)


def test_the_event_id_is_the_cell_end():
    transition = jalandhar_tithi_end()

    assert transition.event_id == EventId(TITHI, 20, JAL_B)
    assert transition.event_id.cell_end_utc == transition.after_utc


# --- cycles, wraps and coincidences ---------------------------------------


def consecutive(transitions, count):
    for earlier, later in zip(transitions, transitions[1:]):
        assert later.before.index == earlier.after.index
        assert later.after_utc > earlier.after_utc
    return [t.after.index for t in transitions]


def test_a_lunation_of_tithis_and_karanas_walks_every_slot_and_wraps():
    listing = list_transitions(at(2024, 1, 11, 11), at(2024, 2, 10),
                               kinds=(TITHI, KARANA))
    verified_all(listing.transitions)
    tithis = [t for t in listing.transitions if t.kind is TITHI]
    karanas = [t for t in listing.transitions if t.kind is KARANA]

    # Tithi and karana divide the same quantity: coincident cells are one
    # simultaneous change, never an unordered pair.
    assert listing.unordered_pairs == ()

    tithi_indices = consecutive(tithis, 30)
    karana_indices = consecutive(karanas, 60)
    assert len(tithis) == 31 and set(tithi_indices) == set(range(30))
    assert tithi_indices[0] == 0 and tithi_indices[-1] == 0
    assert len(karanas) == 61 and set(karana_indices) == set(range(60))
    for karana in karanas:
        for element in (karana.before, karana.after):
            slot = KARANA_SLOTS[element.index]
            assert element.name == slot.name
            assert element.kind is slot.kind
            assert element.cycle_position == slot.cycle_position


def test_a_sidereal_month_of_nakshatras_and_yogas_walks_every_slot_and_wraps():
    listing = list_transitions(at(2024, 1, 1), at(2024, 1, 29),
                               kinds=(NAKSHATRA, YOGA))
    verified_all(listing.transitions)
    for kind in (NAKSHATRA, YOGA):
        found = [t for t in listing.transitions if t.kind is kind]
        indices = consecutive(found, 27)
        assert set(indices) == set(range(27)), kind
        assert 0 in indices


def wrap(kind, start, days=30):
    listing = list_transitions(start, start + timedelta(days=days), kinds=(kind,))
    found = [t for t in listing.transitions if t.after.index == 0]
    assert found
    return verified(found[0])


@pytest.mark.parametrize(
    "kind, names",
    [
        (TITHI, ("Amavasya", "Pratipada")),
        (KARANA, ("Naga", "Kimstughna")),
        (NAKSHATRA, ("Revati", "Ashwini")),
        (YOGA, ("Vaidhriti", "Vishkambha")),
    ],
)
def test_the_zero_degree_wrap_of_each_kind(kind, names):
    found = wrap(kind, at(2024, 1, 1), days=29)

    assert found.before.index == COUNT[kind] - 1
    assert found.after.index == 0
    assert found.boundary_degrees == 0.0
    assert (found.before.name, found.after.name) == names


def coincident(tithi_before, karana_before, start):
    listing = list_transitions(start, start + timedelta(days=30),
                               kinds=(TITHI, KARANA))
    (tithi,) = [t for t in listing.transitions
                if t.kind is TITHI and t.before.index == tithi_before]
    (karana,) = [t for t in listing.transitions
                 if t.kind is KARANA and t.before.index == karana_before]
    return verified(tithi), verified(karana), listing


def test_new_moon_tithi_and_karana_share_an_identical_cell():
    tithi, karana, listing = coincident(29, 59, at(2024, 1, 1))

    assert cell(tithi) == cell(karana)
    assert (tithi.before.index, tithi.after.index) == (29, 0)
    assert (karana.before.index, karana.after.index) == (59, 0)
    assert (tithi.before.name, tithi.after.name) == ("Amavasya", "Pratipada")
    assert (karana.before.name, karana.after.name) == ("Naga", "Kimstughna")
    assert tithi.after.paksha.value == "shukla"


def test_full_moon_tithi_and_karana_share_an_identical_cell():
    tithi, karana, listing = coincident(14, 29, at(2024, 1, 1))

    assert cell(tithi) == cell(karana)
    assert (tithi.before.index, tithi.after.index) == (14, 15)
    assert (karana.before.index, karana.after.index) == (29, 30)
    assert (tithi.before.name, tithi.after.name) == ("Purnima", "Pratipada")
    assert tithi.after.paksha.value == "krishna"
    # Karana index 30 is slot 30 of Layer 16's table: (30 - 1) mod 7 = 1.
    assert karana.after.name == KARANA_SLOTS[30].name == "Balava"
    assert karana.before.name == KARANA_SLOTS[29].name == "Bava"


def test_every_tithi_change_is_a_karana_change_in_the_same_cell():
    """Identical cells, one quantity: simultaneous, so never unordered."""
    listing = list_transitions(at(2024, 5, 1), at(2024, 5, 20),
                               kinds=(TITHI, KARANA))
    karana_cells = {cell(t) for t in listing.transitions if t.kind is KARANA}
    tithis = [i for i, t in enumerate(listing.transitions) if t.kind is TITHI]

    assert tithis
    for index in tithis:
        assert cell(listing.transitions[index]) in karana_cells
        # Canonical order puts the karana right after its tithi.
        assert listing.transitions[index + 1].kind is KARANA
        assert cell(listing.transitions[index + 1]) == cell(listing.transitions[index])
        assert (index, index + 1) not in listing.unordered_pairs
    assert listing.unordered_pairs == ()


@pytest.mark.parametrize("tolerance", [DEFAULT_TOLERANCE, HOUR])
def test_an_all_kinds_listing_never_lists_a_tithi_karana_pair(tolerance):
    """The rule, checked pair by pair over a lunation of all four kinds."""
    listing = list_transitions(at(2024, 1, 1), at(2024, 1, 31),
                               tolerance=tolerance)
    entries = listing.transitions
    expected = tuple(
        (i, i + 1)
        for i in range(len(entries) - 1)
        if entries[i].quantity is not entries[i + 1].quantity
        and cell(entries[i]) == cell(entries[i + 1])
    )

    assert listing.unordered_pairs == expected
    for i, j in listing.unordered_pairs:
        assert {entries[i].kind, entries[j].kind} != {TITHI, KARANA}
        assert entries[i].quantity is not entries[j].quantity
    # Coincident tithi/karana cells are present and adjacent, and not listed.
    coincident = [i for i in range(len(entries) - 1)
                  if (entries[i].kind, entries[i + 1].kind) == (TITHI, KARANA)
                  and cell(entries[i]) == cell(entries[i + 1])]
    assert len(coincident) >= 29
    assert not set(coincident) & {i for i, _ in listing.unordered_pairs}
    if tolerance == DEFAULT_TOLERANCE:
        assert listing.unordered_pairs == ()


# --- adversarial origins and tolerances ----------------------------------


def test_the_same_event_from_every_origin_is_the_identical_cell():
    event = jalandhar_tithi_end()
    fine = next_transition(JALANDHAR, TITHI, tolerance=MS)
    old_inside, new_inside = fine.before_utc, fine.after_utc
    assert JAL_A < old_inside < new_inside < JAL_B

    forward_origins = [JAL_B - 3 * HOUR, JAL_A - SECOND, old_inside, JAL_A,
                       JAL_A + US]
    for origin in forward_origins:
        assert classify(TITHI, origin).index == 19
        found = next_transition(origin, TITHI)
        assert cell(found) == (JAL_A, JAL_B), origin
        assert found == event

    backward_origins = [new_inside, JAL_B, JAL_B + US, JAL_B + 8 * HOUR]
    for origin in backward_origins:
        assert classify(TITHI, origin).index == 20
        found = previous_transition(origin, TITHI)
        assert cell(found) == (JAL_A, JAL_B), origin
        assert found == event


def test_the_endpoints_themselves_as_queries():
    event = jalandhar_tithi_end()

    assert previous_transition(JAL_B, TITHI) == event
    following = verified(next_transition(JAL_B, TITHI))
    assert following.before.index == 20 and following.after_utc > JAL_B + HOUR
    assert next_transition(JAL_A, TITHI) == event
    before = verified(previous_transition(JAL_A, TITHI))
    assert before.after.index == 19 and before.after_utc < JAL_A - HOUR


def test_the_cells_nest_across_tolerances_and_are_one_event():
    tolerances = (MS, 10 * MS, 100 * MS, SECOND, timedelta(minutes=1))
    found = [verified(next_transition(JALANDHAR, TITHI, tolerance=tol))
             for tol in tolerances]

    for finer, coarser in zip(found, found[1:]):
        assert coarser.before_utc <= finer.before_utc
        assert finer.after_utc <= coarser.after_utc
    for a in found:
        for b in found:
            assert same_event(a, b)
    assert cell(found[2]) == (JAL_A, JAL_B)
    assert cell(found[3]) == (at(1995, 3, 21, 13, 45, 8), at(1995, 3, 21, 13, 45, 9))


def test_same_event_is_false_for_other_events_and_other_kinds():
    event = jalandhar_tithi_end()
    following = next_transition(JAL_B, TITHI)
    karana = next_transition(JAL_A, KARANA)

    assert cell(karana) == cell(event)
    assert not same_event(event, following)
    assert not same_event(event, karana)


def test_the_end_of_a_one_millisecond_cell_is_a_verified_new_side_endpoint():
    fine = verified(next_transition(JALANDHAR, TITHI, tolerance=MS))
    end = fine.after_utc

    assert classify(TITHI, end).index == 20
    assert previous_transition(end, TITHI, tolerance=MS) == fine
    following = verified(next_transition(end, TITHI, tolerance=MS))
    assert following.before.index == 20 and following.after.index == 21


def test_an_off_grid_query_is_classified_where_it_is_and_never_probed():
    off = JALANDHAR + 7 * MS
    assert not on_grid(off, DEFAULT_TOLERANCE)
    recorder = Recorder()

    found = verified(next_transition(off, TITHI, evaluate=recorder))

    assert cell(found) == (JAL_A, JAL_B)
    assert found == next_transition(JALANDHAR, TITHI)
    assert recorder.calls[0] == off
    assert off not in recorder.calls[1:]
    assert all(on_grid(p, DEFAULT_TOLERANCE) for p in recorder.calls[1:])

    # The query classification is Layer 16's own answer at that instant.
    recorder = Recorder()
    result = find_transitions(off, kinds=(TITHI,), evaluate=recorder)
    assert result.neighbours[TITHI].current == classify(TITHI, off)
    assert result.instant_utc == off
    assert recorder.calls.count(off) == 1


def test_a_negative_raw_offset_estimates_zero_and_finds_the_change_in_one_cell():
    """Probe P1: yoga index 7 entered at a double whose raw offset is < 0."""
    boundary = 93.33333333333333   # one ULP below 7 * YOGA_SPAN
    element = yoga_from_sum(boundary)
    assert element.index == 7
    assert element.degrees_in_yoga < 0.0
    assert element.angular_fraction == 0.0

    query = at(2024, 1, 1, 12)
    rate = 13.0   # deg/day, a plausible linear sum

    def sky(moment):
        return 0.0, boundary + rate * ((moment - query) / DAY)

    recorder = Recorder(sky)
    found = previous_transition(query, YOGA, evaluate=recorder)

    assert cell(found) == (query - DEFAULT_TOLERANCE, query)
    assert (found.before.index, found.after.index) == (6, 7)
    # query, the grid point equal to it, and one cell back: no cycle-long search.
    assert recorder.calls == [query, query, query - DEFAULT_TOLERANCE]


def test_successive_tithi_searches_need_no_expansion():
    """R4: with RATE_MIN under the true minimum, the first probe overshoots."""
    cursor = JALANDHAR
    for _ in range(30):
        recorder = Recorder()
        found = next_transition(cursor, TITHI, evaluate=recorder)
        k0 = classify(TITHI, cursor).index
        # calls: query, g1, first bracket probe, then bisection only
        assert classify(TITHI, recorder.calls[2]).index != k0
        assert len(recorder.calls) <= 30
        cursor = found.after_utc


# --- the listing contract (R1) -------------------------------------------


def tithi_list(start, end):
    return list(verified_all(list_transitions(start, end, kinds=(TITHI,)).transitions))


def test_the_r1_empty_listings():
    event = jalandhar_tithi_end()
    a, b = cell(event)

    assert tithi_list(b - US, b) == []
    assert tithi_list(b - 2 * MS, b) == []
    assert tithi_list(b - 2 * MS, b - MS) == []
    assert tithi_list(b - MS, b) == []
    assert tithi_list(a + US, b) == []
    assert tithi_list(b + US, b + SECOND) == []
    assert tithi_list(a - SECOND, a + US) == []


def test_the_r1_listings_that_contain_exactly_the_cell():
    event = jalandhar_tithi_end()
    a, b = cell(event)

    assert tithi_list(b, b + US) == [event]
    assert tithi_list(b - 50 * MS, b + 50 * MS) == [event]
    assert tithi_list(a, b + US) == [event]


@pytest.mark.parametrize(
    "split",
    ["inside", "a", "b", "b+1us", "b-1us", "a-7ms", "a+13us"],
)
def test_two_adjacent_intervals_partition_the_whole(split):
    """All four kinds; the representative decides, wherever the split falls."""
    a, b = JAL_A, JAL_B
    point = {
        "inside": a + DEFAULT_TOLERANCE / 3,
        "a": a,
        "b": b,
        "b+1us": b + US,
        "b-1us": b - US,
        "a-7ms": a - 7 * MS,
        "a+13us": a + 13 * US,
    }[split]
    start, end = JALANDHAR - DAY, JALANDHAR + 3 * DAY

    whole = list_transitions(start, end).transitions
    left = list_transitions(start, point).transitions
    right = list_transitions(point, end).transitions

    verified_all(whole)
    assert left + right == whole
    assert len({t.event_id for t in whole}) == len(whole)
    assert all(t.after_utc < point for t in left)
    assert all(t.after_utc >= point for t in right)


def test_a_straddling_cell_is_listed_from_its_new_side():
    """Finding 4: a start already past the change but inside its cell."""
    fine = next_transition(JALANDHAR, TITHI, tolerance=MS)
    start = fine.after_utc   # new side, strictly inside (JAL_A, JAL_B)
    assert classify(TITHI, start).index == 20

    assert start + 10 * MS == JAL_B
    assert tithi_list(start, start + 10 * MS) == []   # end is exclusive
    assert tithi_list(start, start + 20 * MS) == [jalandhar_tithi_end()]


def test_the_listing_is_sorted_by_representative_and_carries_its_request():
    listing = list_transitions(JALANDHAR, JALANDHAR + 2 * DAY,
                               kinds=[YOGA, TITHI, NAKSHATRA, KARANA])

    assert listing.kinds == ALL_KINDS
    assert listing.start_utc == JALANDHAR and listing.end_utc == JALANDHAR + 2 * DAY
    assert listing.tolerance == DEFAULT_TOLERANCE
    keys = [(t.after_utc, ALL_KINDS.index(t.kind)) for t in listing.transitions]
    assert keys == sorted(keys)
    assert listing.calculation_convention == CALCULATION_CONVENTION
    assert listing.search_convention == SEARCH_CONVENTION


# --- unordered pairs: a near-coincident nakshatra/yoga pair ---------------

#: Found by listing 2024 at 1 s (engine values on Linux x86_64, cloud venv;
#: environment-sensitive per spec section 4.9): yoga Sadhya -> Shubha ends its
#: 1 s cell at 09:25:48 and nakshatra Ardra -> Punarvasu at 09:25:57 UTC on
#: 2024-11-19 -- nine seconds apart, yoga first.
PAIR_WINDOW = (at(2024, 11, 19, 6), at(2024, 11, 19, 13))


def pair_listing(tolerance):
    listing = list_transitions(*PAIR_WINDOW, kinds=(NAKSHATRA, YOGA),
                               tolerance=tolerance)
    verified_all(listing.transitions)
    assert len(listing.transitions) == 2
    return listing


def test_a_coarse_tolerance_cannot_order_the_pair_and_says_so():
    listing = pair_listing(HOUR)
    first, second = listing.transitions

    assert cell(first) == cell(second) == (at(2024, 11, 19, 9), at(2024, 11, 19, 10))
    # Different quantities (MOON_LONGITUDE, LONGITUDE_SUM), identical cells.
    assert first.quantity is not second.quantity
    assert listing.unordered_pairs == ((0, 1),)
    # Sorted by representative: equal cell ends fall back to canonical kind
    # order, which puts the nakshatra first although the yoga changed first.
    assert (first.kind, second.kind) == (NAKSHATRA, YOGA)
    assert (first.before.name, first.after.name) == ("Ardra", "Punarvasu")
    assert (second.before.name, second.after.name) == ("Sadhya", "Shubha")

    assert pair_listing(timedelta(minutes=1)).unordered_pairs == ((0, 1),)


def test_a_finer_tolerance_separates_the_pair_and_empties_unordered_pairs():
    coarse = pair_listing(HOUR)
    fine = pair_listing(10 * SECOND)

    assert fine.unordered_pairs == ()
    assert [t.kind for t in fine.transitions] == [YOGA, NAKSHATRA]
    assert fine.transitions[0].after_utc <= fine.transitions[1].before_utc
    for kind in (NAKSHATRA, YOGA):
        (c,) = [t for t in coarse.transitions if t.kind is kind]
        (f,) = [t for t in fine.transitions if t.kind is kind]
        assert same_event(c, f)


# --- validation (specification 3's table) before any ephemeris call -------


NAIVE = datetime(1995, 3, 21, 1, 15)


def calls_of(function, *args, **kwargs):
    recorder = Recorder(refuse)
    return recorder, lambda: function(*args, evaluate=recorder, **kwargs)


REFUSED = [
    # naive datetimes: Layer 4's ValueError, unchanged
    (ValueError, next_transition, (NAIVE, TITHI), {}),
    (ValueError, previous_transition, (NAIVE, TITHI), {}),
    (ValueError, find_transitions, (NAIVE,), {}),
    (ValueError, list_transitions, (NAIVE, at(1995, 3, 22)), {}),
    (ValueError, list_transitions, (at(1995, 3, 20), NAIVE), {}),
    # outside the supported range
    (UnsupportedInstantError, next_transition, (SUPPORTED_START - MS, TITHI), {}),
    (UnsupportedInstantError, previous_transition, (SUPPORTED_END + MS, TITHI), {}),
    (UnsupportedInstantError, find_transitions, (SUPPORTED_START - MS,), {}),
    (UnsupportedInstantError, find_transitions, (SUPPORTED_END + MS,), {}),
    (UnsupportedInstantError, find_transitions, (SUPPORTED_END + US,), {}),
    (UnsupportedInstantError, list_transitions,
     (SUPPORTED_START - MS, SUPPORTED_START + DAY), {}),
    (UnsupportedInstantError, list_transitions,
     (SUPPORTED_END - DAY, SUPPORTED_END + MS), {}),
    # intervals
    (IntervalError, list_transitions, (at(1995, 3, 21), at(1995, 3, 21)), {}),
    (IntervalError, list_transitions, (at(1995, 3, 22), at(1995, 3, 21)), {}),
    (IntervalError, list_transitions,
     (at(1995, 1, 1), at(1995, 1, 1) + MAX_INTERVAL + US), {}),
    # kinds
    (TransitionRequestError, find_transitions, (JALANDHAR,), {"kinds": TITHI}),
    (TransitionRequestError, find_transitions, (JALANDHAR,), {"kinds": 5}),
    (TransitionRequestError, find_transitions, (JALANDHAR,), {"kinds": None}),
    (TransitionRequestError, find_transitions, (JALANDHAR,), {"kinds": "tithi"}),
    (TransitionRequestError, find_transitions, (JALANDHAR,), {"kinds": ["tithi"]}),
    (TransitionRequestError, find_transitions, (JALANDHAR,), {"kinds": ()}),
    (TransitionRequestError, find_transitions, (JALANDHAR,), {"kinds": (TITHI, TITHI)}),
    (TransitionRequestError, list_transitions, (JALANDHAR, JALANDHAR + DAY),
     {"kinds": []}),
    (TransitionRequestError, list_transitions, (JALANDHAR, JALANDHAR + DAY),
     {"kinds": (YOGA, KARANA, YOGA)}),
    (TransitionRequestError, next_transition, (JALANDHAR, "tithi"), {}),
    (TransitionRequestError, previous_transition, (JALANDHAR, None), {}),
    # tolerance
    (TransitionRequestError, next_transition, (JALANDHAR, TITHI), {"tolerance": 0.1}),
    (TransitionRequestError, next_transition, (JALANDHAR, TITHI), {"tolerance": 100}),
    (TransitionRequestError, find_transitions, (JALANDHAR,),
     {"tolerance": timedelta(milliseconds=50)}),
    (TransitionRequestError, find_transitions, (JALANDHAR,),
     {"tolerance": timedelta(0)}),
    (TransitionRequestError, previous_transition, (JALANDHAR, TITHI),
     {"tolerance": -DEFAULT_TOLERANCE}),
    (TransitionRequestError, list_transitions, (JALANDHAR, JALANDHAR + DAY),
     {"tolerance": timedelta(hours=2)}),
]


@pytest.mark.parametrize("error, function, args, kwargs", REFUSED)
def test_every_refused_input_costs_no_evaluation(
    no_ephemeris, error, function, args, kwargs
):
    recorder, call = calls_of(function, *args, **kwargs)

    with pytest.raises(error):
        call()
    assert recorder.calls == []


def test_the_default_path_is_not_reached_by_a_refused_input(no_ephemeris):
    """Spec 7: SUPPORTED_START - 1 ms and SUPPORTED_END + 1 ms, default evaluate."""
    for moment in (SUPPORTED_START - MS, SUPPORTED_END + MS):
        with pytest.raises(UnsupportedInstantError):
            find_transitions(moment)
        with pytest.raises(UnsupportedInstantError):
            next_transition(moment, TITHI)


def test_an_invalid_member_is_named():
    with pytest.raises(TransitionRequestError, match="'tithi'"):
        find_transitions(JALANDHAR, kinds=[TITHI, "tithi"], evaluate=refuse)


def test_the_largest_interval_is_accepted():
    start = at(2024, 1, 1)
    listing = list_transitions(start, start + MAX_INTERVAL, kinds=(TITHI,),
                               tolerance=HOUR)

    assert 360 < len(listing.transitions) < 380


# --- reach, evaluation range and the typed run-time failures (R3) ---------


def test_every_probe_stays_within_reach_of_the_query():
    recorder = Recorder()
    next_transition(JALANDHAR, TITHI, evaluate=recorder)

    assert max(abs(p - JALANDHAR) for p in recorder.calls) <= MAX_REACH


def test_the_snap_offset_counts_toward_reach():
    grid_point = EPOCH + ((JALANDHAR - EPOCH) // HOUR) * HOUR
    query = grid_point + timedelta(minutes=59, seconds=59)
    recorder = Recorder()

    found = verified(next_transition(query, TITHI, tolerance=HOUR,
                                     evaluate=recorder))

    assert recorder.calls[0] == query
    assert recorder.calls[1] == grid_point + HOUR   # one second after the query
    assert all(abs(p - query) <= MAX_REACH for p in recorder.calls)
    assert all(on_grid(p, HOUR) for p in recorder.calls[1:])
    assert found.after_utc > query


def stuck(moment):
    return 0.0, 30.0   # tithi index 2, half way through, forever


@pytest.mark.parametrize("search", [next_transition, previous_transition])
def test_a_classifier_that_never_changes_stops_at_the_reach_bound(search):
    recorder = Recorder(stuck)

    with pytest.raises(TransitionSearchError, match="MAX_REACH"):
        search(JALANDHAR, TITHI, evaluate=recorder)

    assert all(abs(p - JALANDHAR) <= MAX_REACH for p in recorder.calls)
    assert max(abs(p - JALANDHAR) for p in recorder.calls) > DAY


@pytest.mark.parametrize("search", [next_transition, previous_transition])
def test_two_changes_inside_one_cell_raise(search):
    query = JALANDHAR + 7 * MS

    def sky(moment):
        if moment == query:
            return 0.0, 30.0      # tithi index 2
        return (0.0, 18.0) if moment < query else (0.0, 42.0)   # 1 before, 3 after

    with pytest.raises(TransitionSearchError, match="two changes"):
        search(query, TITHI, evaluate=sky)


def test_a_bracket_end_that_skips_an_element_raises():
    def sky(moment):
        return (0.0, 30.0) if moment <= JALANDHAR + HOUR else (0.0, 54.0)

    with pytest.raises(TransitionSearchError, match="successor"):
        next_transition(JALANDHAR, TITHI, evaluate=sky)


def test_a_bisection_midpoint_outside_the_bracket_raises():
    def sky(moment):
        elapsed = (moment - JALANDHAR) / DAY
        if elapsed < 0.3:
            return 0.0, 30.0      # index 2 at the query
        if elapsed < 0.5:
            return 0.0, 100.0     # index 8: not monotonic
        return 0.0, 36.0          # index 3 at the bracket end

    with pytest.raises(TransitionSearchError, match="neither"):
        next_transition(JALANDHAR, TITHI, evaluate=sky)


def test_no_julian_day_progress_raises(monkeypatch):
    monkeypatch.setattr(transitions_module, "julian_day_ut", lambda moment: 2449797.5)

    with pytest.raises(TransitionSearchError, match="Julian Day progress"):
        next_transition(JALANDHAR, TITHI)


def test_the_probe_guards_themselves():
    """The grid and safe-range guards, reached through the private search.

    Through the public functions the safe-range guard is unreachable by
    construction (inputs are MAX_REACH inside it), so it is exercised here by
    placing a query where no public input can be.
    """
    search = transitions_module._Search(TITHI, JALANDHAR, DEFAULT_TOLERANCE, refuse)
    with pytest.raises(TransitionSearchError, match="grid"):
        search.probe(JALANDHAR + MS)

    search = transitions_module._Search(TITHI, SAFE_EVAL_END, DEFAULT_TOLERANCE, stuck)
    with pytest.raises(TransitionSearchError, match="safe evaluation range"):
        search.next(tithi_from_elongation(30.0))


@pytest.mark.parametrize("moment", [SUPPORTED_START, SUPPORTED_END])
def test_the_supported_edges_probe_only_inside_the_safe_range(moment):
    recorder = Recorder()
    result = find_transitions(moment, evaluate=recorder)

    for entry in result.neighbours.values():
        verified(entry.previous)
        verified(entry.next)
    assert recorder.calls
    assert all(SAFE_EVAL_START <= p <= SAFE_EVAL_END for p in recorder.calls)


def test_a_listing_up_to_the_supported_end_stays_inside_the_safe_range():
    recorder = Recorder()
    listing = list_transitions(SUPPORTED_END - 2 * DAY, SUPPORTED_END,
                               evaluate=recorder)

    verified_all(listing.transitions)
    assert all(SAFE_EVAL_START <= p <= SAFE_EVAL_END for p in recorder.calls)


COLD_SCRIPT = """
import sys
from datetime import datetime, timezone
from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.panchanga.transitions import (
    SAFE_EVAL_END, SAFE_EVAL_START, default_evaluate)

first = SAFE_EVAL_START if sys.argv[1] == "start" else SAFE_EVAL_END
with ephemeris_session(sys.argv[2]):
    print("first", default_evaluate(first))
    try:
        default_evaluate(datetime(1700, 1, 1, tzinfo=timezone.utc))
    except RuntimeError as error:
        print("refused", type(error).__name__)
    else:
        print("accepted")
    print("start", default_evaluate(SAFE_EVAL_START))
    print("end", default_evaluate(SAFE_EVAL_END))
"""


@pytest.mark.parametrize("edge", ["start", "end"])
def test_both_evaluation_edges_answer_in_a_cold_session_and_after_a_failure(edge):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-c", COLD_SCRIPT, edge, EPHE_DIR],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.splitlines()
    assert [line.split()[0] for line in lines] == ["first", "refused", "start", "end"]
    # The cold first answer is the same as the answer after the failure.
    first = lines[0].split(" ", 1)[1]
    assert first in (lines[2].split(" ", 1)[1], lines[3].split(" ", 1)[1])


# --- presentation ----------------------------------------------------------


def test_presentation_in_asia_kolkata():
    event = jalandhar_tithi_end()
    local = local_transition(event, "Asia/Kolkata")

    assert isinstance(local, LocalTransition)
    assert local.transition is event
    assert local.timezone_id == "Asia/Kolkata"
    assert local.after_local.utcoffset() == timedelta(hours=5, minutes=30)
    assert local.after_local.replace(tzinfo=None) == datetime(1995, 3, 21, 19, 15, 8, 300000)
    assert local.after_local == event.after_utc
    assert local.before_local == event.before_utc
    assert event.after_utc.tzinfo is UTC


@pytest.mark.parametrize(
    "zone, day, switch, before_offset, after_offset",
    [
        ("Europe/London", at(2024, 3, 31), at(2024, 3, 31, 1), 0, 1),
        ("Europe/London", at(2024, 10, 27), at(2024, 10, 27, 1), 1, 0),
        ("America/New_York", at(2024, 3, 10), at(2024, 3, 10, 7), -5, -4),
        ("America/New_York", at(2024, 11, 3), at(2024, 11, 3, 6), -4, -5),
    ],
)
def test_presentation_across_a_daylight_saving_change(
    zone, day, switch, before_offset, after_offset
):
    listing = list_transitions(day - DAY, day + 2 * DAY)
    offsets = set()

    for transition in verified_all(listing.transitions):
        local = local_transition(transition, zone)
        expected = before_offset if transition.after_utc < switch else after_offset
        assert local.after_local.utcoffset() == timedelta(hours=expected)
        assert local.after_local.replace(tzinfo=None) == (
            transition.after_utc.replace(tzinfo=None) + timedelta(hours=expected)
        )
        assert local.transition.after_utc.tzinfo is UTC
        offsets.add(expected)
    assert offsets == {before_offset, after_offset}


def test_presentation_across_the_date_line():
    event = jalandhar_tithi_end()
    local = local_transition(event, "Pacific/Kiritimati")

    assert local.after_local.utcoffset() == timedelta(hours=14)
    assert local.after_local.date() == date(1995, 3, 22)
    assert event.after_utc.date() == date(1995, 3, 21)


def test_an_invalid_zone_is_refused():
    event = jalandhar_tithi_end()

    with pytest.raises(InvalidTimezoneError):
        local_transition(event, "Asia/Jalandhar")
    with pytest.raises(InvalidTimezoneError):
        local_transition(event, 530)
    with pytest.raises(TransitionRequestError):
        local_transition("not a transition", "Asia/Kolkata")


# --- independent numerical cross-check (tests only) -----------------------


def secant_root(kind, boundary, reference_angle, t0, t1):
    """The crossing of ``boundary`` by the unwrapped angle, to |dt| < 1 ms.

    Shares no code with ``transitions.py``: the library directly, with the
    frozen accessor's flags and ayanamsha calls, and the FROZEN
    ``julian_day_ut`` on the same datetimes.
    """
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED

    def angle(moment):
        jd = julian_day_ut(moment)
        sun = swe.calc_ut(jd, swe.SUN, flags)[0][0]
        moon = swe.calc_ut(jd, swe.MOON, flags)[0][0]
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        ayanamsa = swe.get_ayanamsa_ex_ut(jd, 0)[1]
        sun = (sun - ayanamsa) % 360.0
        moon = (moon - ayanamsa) % 360.0
        if kind in (TITHI, KARANA):
            value = (moon - sun) % 360.0
        elif kind is YOGA:
            value = (sun + moon) % 360.0
        else:
            value = moon
        # Unwrap in time: the continuous branch nearest the reference angle.
        while value < reference_angle - 180.0:
            value += 360.0
        while value >= reference_angle + 180.0:
            value -= 360.0
        return value - boundary

    f0, f1 = angle(t0), angle(t1)
    for _ in range(50):
        step = (t1 - t0) * (-f1 / (f1 - f0))
        t0, f0 = t1, f1
        t1 = t1 + step
        f1 = angle(t1)
        if abs(step) < MS:
            return t1
    raise AssertionError("the secant method did not converge")


@pytest.mark.parametrize(
    "start, days",
    [(at(2024, 1, 1), 14), (at(1805, 6, 1), 14), (at(2395, 6, 1), 14)],
)
def test_the_cells_agree_with_an_independent_secant_solver(start, days):
    listing = list_transitions(start, start + timedelta(days=days))
    counts = {kind: 0 for kind in ALL_KINDS}

    for transition in verified_all(listing.transitions):
        kind = transition.kind
        reference = classify(kind, transition.before_utc)
        if kind in (TITHI, KARANA):
            reference_angle = reference.elongation if kind is TITHI else (
                classify(TITHI, transition.before_utc).elongation
            )
        elif kind is YOGA:
            reference_angle = reference.sum_longitude
        else:
            reference_angle = calculate_sidereal_positions(
                transition.before_utc
            ).bodies[Body.MOON].sidereal_longitude
        boundary = transition.boundary_degrees
        if boundary < reference_angle - 180.0:
            boundary += 360.0   # the 0 deg / 360 deg wrap
        root = secant_root(kind, boundary, reference_angle,
                           transition.before_utc - HOUR,
                           transition.after_utc + HOUR)

        assert transition.before_utc - MS < root <= transition.after_utc + MS, (
            kind, transition.after_utc, root)
        counts[kind] += 1

    assert all(count >= 12 for count in counts.values()), counts


# --- external comparison with a minute-resolution published reference -----

#: NASA GSFC, "Moon Phases: 2001 to 2025" (Fred Espenak), Universal Time to the
#: minute, https://eclipse.gsfc.nasa.gov/phase/phase2001gmt.html, retrieved
#: 2026-09-24. Agreement with a reference computed by a different method (Meeus
#: algorithms, not DE431), not a proof of accuracy; the table rounds to +-30 s.
NASA_URL = "https://eclipse.gsfc.nasa.gov/phase/phase2001gmt.html"
NASA_RETRIEVED = date(2026, 9, 24)
NASA_PHASES = [
    ("new", at(2024, 1, 11, 11, 57)),    # NASA_URL, retrieved 2026-09-24
    ("full", at(2024, 1, 25, 17, 54)),   # NASA_URL, retrieved 2026-09-24
    ("new", at(2024, 2, 9, 22, 59)),     # NASA_URL, retrieved 2026-09-24
    ("full", at(2024, 2, 24, 12, 30)),   # NASA_URL, retrieved 2026-09-24
    ("new", at(2024, 3, 10, 9, 0)),      # NASA_URL, retrieved 2026-09-24
    ("full", at(2024, 3, 25, 7, 0)),     # NASA_URL, retrieved 2026-09-24
    ("new", at(2024, 6, 6, 12, 38)),     # NASA_URL, retrieved 2026-09-24
    ("full", at(2024, 6, 22, 1, 8)),     # NASA_URL, retrieved 2026-09-24
    ("full", at(2024, 12, 15, 9, 2)),    # NASA_URL, retrieved 2026-09-24
    ("new", at(2024, 12, 30, 22, 27)),   # NASA_URL, retrieved 2026-09-24
    ("full", at(2025, 3, 14, 6, 55)),    # NASA_URL, retrieved 2026-09-24
    ("new", at(2025, 3, 29, 10, 58)),    # NASA_URL, retrieved 2026-09-24
    ("full", at(2025, 9, 7, 18, 9)),     # NASA_URL, retrieved 2026-09-24
    ("new", at(2025, 9, 21, 19, 54)),    # NASA_URL, retrieved 2026-09-24
]


@pytest.mark.parametrize("phase, published", NASA_PHASES)
def test_new_and_full_moons_agree_with_nasa_to_the_minute(phase, published):
    after_index = 0 if phase == "new" else 15
    listing = list_transitions(published - DAY, published + DAY, kinds=(TITHI,))
    (found,) = [t for t in listing.transitions if t.after.index == after_index]

    verified(found)
    assert abs(found.after_utc - published) <= timedelta(seconds=60), (
        found.after_utc, published, NASA_URL, NASA_RETRIEVED)
