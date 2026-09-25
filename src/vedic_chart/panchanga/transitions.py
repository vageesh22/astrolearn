"""Layer 17: when the angular panchanga elements change.

For the four **angular** elements -- tithi, karana, nakshatra, nitya yoga --
this module answers two questions from evaluated positions: when did the
element current at an instant begin and when does it end (``find_transitions``,
``previous_transition``, ``next_transition``), and which transitions fall in a
bounded UTC interval (``list_transitions``). The vara is excluded: its boundary
is a sunrise, which ``sunrise.find_sunrise_window`` already answers (decision
D6). Specification: ``docs/LAYER17_PANCHANGA_TRANSITIONS_SPEC.md`` (v0.3).

**The predicate is the classifier (specification 4.1).** A transition of a kind
is *defined* as a change of the Layer 16 index of that kind. Nothing here
solves ``angle(t) = boundary`` and then classifies the answer: the search
evaluates ``classifier(quantity(positions(t)))`` at instants and looks for the
change, so every endpoint it returns carries a classification that was actually
computed there. At an inexact 40k/3 deg yoga or nakshatra boundary the frozen
float fact moves the flip by ~3e-14 deg, about nine orders of magnitude below
the default cell; the endpoint is still on the side Layer 16 says it is on,
because Layer 16 is what said so.

**Two kinds of evaluation (specification 4.2, 4.4).** The *query* is one
evaluation at the caller's exact instant, normalised to UTC by
``sunrise.utc_instant`` and never snapped, so ``Neighbours.current`` is exactly
Layer 16's answer there. Every other evaluation is a *probe*, and every probe is
a point of the absolute tolerance grid ``1970-01-01T00:00Z + n * tolerance``.
Before each probe -- never the query -- four things are checked, all as
``if``/``raise`` of ``TransitionSearchError``: the instant is a grid point, it
lies within ``MAX_REACH`` of the caller's instant (the actual distance, snap
offset and every expansion included), it lies inside ``[SAFE_EVAL_START,
SAFE_EVAL_END]``, and, during bisection, the Julian Days strictly increase
across ``a < mid < b``. The module contains no ``assert`` statement, so
``python -O`` changes nothing.

**The cell.** The result of a search is the unique grid cell ``(a, a + tol]``
with the old index at ``a`` and the new index at ``a + tol``. Because the grid
is absolute and an evaluation at a grid point is a deterministic function of
that point, the cell depends only on the event and the tolerance -- not on the
query instant, the initial estimate or the expansion path. The tolerances nest
(each divides the next), so the cell at a finer tolerance lies inside the cell
at a coarser one, which is what makes ``same_event`` meaningful. Under the
monotonicity and separation assumptions (specification 4.9) the true change
``tau`` satisfies ``before_utc < tau <= after_utc``; ``after_utc`` is a verified
new-side endpoint, the representative, and nothing more.

**Bracketing (specification 4.3).** The first probe is sized by an estimate
``(1 - angular_fraction) * span / RATE_MIN`` (or ``angular_fraction * span /
RATE_MIN`` backwards) rounded up to whole cells, at least one. The progress
fraction is Layer 16's ``angular_fraction``, which lies in ``[0, 1)`` exactly;
the raw ``degrees_in_*`` offset, which can be a few 1e-14 deg negative at an
inexact boundary, is used nowhere. While the probe still shows the departing
index the step doubles; the reach guard ends a runaway search. The bracket end
must show the successor (or predecessor) index, the cell's two endpoints must
not both differ from the query's index, and every bisection midpoint must show
one of the two indices the bracket holds: each of those is an observable
violation of the assumptions and raises rather than being widened or retried.

**Rates -- survey re-run for the implementation (specification 2.1).** Over
1800-01-05 .. 2399-12-28, one 40-day window per 10 years (starting 1800-01-05,
1810-01-05, ..., 2390-01-05, plus one window ending 2399-12-28), 4-hour steps,
14 701 samples:

====================================  ===============  ===============
quantity (deg/day)                    minimum          maximum
====================================  ===============  ===============
E, tropical speeds (dA/dt cancels)    10.742742        14.374816
E, finite differences (sidereal)      10.742739        14.375287
lambda_M, tropical speed              11.761451        15.392934
lambda_M, tropical speed - dA/dt      11.761396        15.392846
lambda_M, finite differences          11.761387        15.393311
Y, tropical speeds                    12.780161        16.411057
Y, tropical speeds - 2 dA/dt          12.780051        16.410881
Y, finite differences                 12.780034        16.411335
dA/dt (central difference, +-1 h)     0.000004         0.000104
====================================  ===============  ===============

A denser supplementary run (one 40-day window per year, 1-hour steps, 577 561
samples) found E 10.740818 .. 14.384510, lambda_M 11.760259 .. 15.400764 and
Y 12.775195 .. 16.419326 (for each quantity, the extremes over its three
measurements: tropical speeds, speeds corrected by dA/dt, and finite
differences).

The drafting survey's minima (E 10.782, lambda_M 11.774, Y 12.734; one window
per 25 years at 6-hour steps) were not the true minima: 0.9 times the measured
E and lambda_M minima is 9.667 and 10.584, *below* the drafted 9.70 and 10.59.
Following the specification's rule (constants <= 0.9 x measured minima) those
two are **lowered** to 9.66 and 10.58; the yoga's 11.46 is <= 0.9 x 12.775 =
11.498 and stays. ``RATE_MAX`` -- which only bounds a listing's iteration count
-- is the largest measured maximum plus 10 %, rounded up to two decimals:
15.83, 16.95 and 18.07. None of these constants decides a result: a rate below
``RATE_MIN`` costs expansion probes, and the cell is the same either way.

**Ranges (specification 4.6).** Inputs -- the query instant and both interval
endpoints -- must lie in ``[SUPPORTED_START, SUPPORTED_END]``, checked before
the first ephemeris call. Probes must lie in ``[SAFE_EVAL_START,
SAFE_EVAL_END]``, checked before each one. The two differ by exactly
``MAX_REACH``, so an input inside the supported range can never trip the
evaluation guard.

Interpretations, recorded rather than left implicit:

* Every public search function takes a keyword-only ``evaluate`` callable,
  ``(moment_utc) -> (sun_sidereal_longitude, moon_sidereal_longitude)``,
  defaulting to ``default_evaluate`` (Layer 6 ``calculate_sidereal_positions``
  read for ``Body.SUN`` and ``Body.MOON``), in the way ``find_sunrise_window``
  takes ``rise_after``. The specification's signatures do not show it; section
  7 requires the search to take one.
* Two checks beyond the text of 4.3 are made because a ``Transition`` could not
  be constructed without them: in the "change inside the query's own cell" path
  the far endpoint must show the successor (predecessor) index, and every
  bisection midpoint must show the old or the new index.
* A listing's walk requires each found cell to end strictly after its cursor, a
  progress check in the spirit of the sunrise walk; with canonical cells it
  cannot fire.
* ``unordered_pairs`` (refined at review): an adjacent pair ``(i, i + 1)`` is
  listed **iff the two transitions divide different quantities and have
  identical cells**. All cells of one listing have one width on one grid, so
  two cells either coincide or are disjoint, and "overlap" is exactly "identical
  cell". Pairs dividing the *same* quantity are excluded: the only such
  cross-kind pair is tithi/karana (both ``ELONGATION``), whose shared cell is a
  simultaneous change by construction (specification 4.8,
  ``int(E*60/360) == int(2*(E*30/360))``), so no order question is open. The
  rule is about adjacent entries only. When a nakshatra or yoga change shares a
  cell with a coincident tithi/karana pair, the sorted order is tithi, karana,
  nakshatra/yoga, so only ``(karana, nakshatra/yoga)`` is listed; the tithi's
  relation to it follows because its cell is identical to the karana's.
* ``Transition`` additionally checks that ``before``/``after`` are the element
  type of its kind, that ``tolerance`` is one of ``ALLOWED_TOLERANCES``, that the
  two Julian Days are ``julian_day_ut`` of the two instants, and that
  ``uncertainty.cell_width == tolerance``.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from types import MappingProxyType
from typing import Callable, Iterable, Mapping

from vedic_chart.astronomy.positions import Body
from vedic_chart.sidereal.positions import calculate_sidereal_positions
from vedic_chart.time.julian_day import julian_day_ut

from .elements import (
    CALCULATION_CONVENTION,
    KARANA_COUNT,
    KARANA_SPAN,
    NAKSHATRA_COUNT,
    NAKSHATRA_SPAN,
    TITHI_COUNT,
    TITHI_SPAN,
    YOGA_COUNT,
    YOGA_SPAN,
    Karana,
    Nakshatra,
    NityaYoga,
    Tithi,
    elongation,
    karana_from_elongation,
    longitude_sum,
    nakshatra_from_longitude,
    tithi_from_elongation,
    yoga_from_sum,
)
from .sunrise import resolve_zone, utc_instant

__all__ = [
    "ALLOWED_TOLERANCES",
    "ALL_KINDS",
    "DEFAULT_TOLERANCE",
    "EventId",
    "GRID_EPOCH",
    "IntervalError",
    "LocalTransition",
    "MAX_INTERVAL",
    "MAX_REACH",
    "MODEL_NOTE",
    "Neighbours",
    "PanchangaTransitions",
    "Quantity",
    "RATE_MAX",
    "RATE_MIN",
    "SAFE_EVAL_END",
    "SAFE_EVAL_START",
    "SEARCH_CONVENTION",
    "SUPPORTED_END",
    "SUPPORTED_START",
    "Transition",
    "TransitionKind",
    "TransitionList",
    "TransitionRequestError",
    "TransitionSearchError",
    "TransitionUncertainty",
    "UT1_NOTE",
    "UnsupportedInstantError",
    "default_evaluate",
    "find_transitions",
    "list_transitions",
    "local_transition",
    "next_transition",
    "previous_transition",
    "same_event",
]


# --- vocabulary --------------------------------------------------------------


class TransitionKind(Enum):
    """The four angular elements, in canonical order."""

    TITHI = "tithi"
    KARANA = "karana"
    NAKSHATRA = "nakshatra"
    YOGA = "yoga"


class Quantity(Enum):
    """The angle each kind divides."""

    ELONGATION = "elongation"
    MOON_LONGITUDE = "moon_longitude"
    LONGITUDE_SUM = "longitude_sum"


#: A Layer 16 element of one of the four angular kinds.
Element = Tithi | Karana | Nakshatra | NityaYoga

#: ``(moment_utc) -> (sun_sidereal_longitude, moon_sidereal_longitude)``.
Evaluate = Callable[[datetime], tuple[float, float]]


class UnsupportedInstantError(ValueError):
    """An input instant lies outside ``[SUPPORTED_START, SUPPORTED_END]``."""


class IntervalError(ValueError):
    """A listing interval is empty, reversed or longer than ``MAX_INTERVAL``."""


class TransitionRequestError(ValueError):
    """``kinds`` or ``tolerance`` is not a valid request."""


class TransitionSearchError(RuntimeError):
    """A search assumption failed observably; nothing was widened or retried."""


# --- constants ---------------------------------------------------------------

#: Canonical order of the kinds, and the default request.
ALL_KINDS: tuple[TransitionKind, ...] = tuple(TransitionKind)

#: The origin of every tolerance grid.
GRID_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

#: Each divides the next, so the grids nest (specification 4.2). The 1 ms
#: floor keeps a grid step >= 25 Julian Day ULPs near JD 2.46e6.
ALLOWED_TOLERANCES: tuple[timedelta, ...] = (
    timedelta(milliseconds=1),
    timedelta(milliseconds=10),
    timedelta(milliseconds=100),
    timedelta(seconds=1),
    timedelta(seconds=10),
    timedelta(minutes=1),
    timedelta(minutes=10),
    timedelta(hours=1),
)

DEFAULT_TOLERANCE = timedelta(milliseconds=100)

MAX_INTERVAL = timedelta(days=366)

#: No probe may lie further than this from the caller's instant.
MAX_REACH = timedelta(days=3)

#: Every probe is checked against these immediately before it is evaluated;
#: one day inside the observed cold-session edges (specification 2.2).
SAFE_EVAL_START = datetime(1800, 1, 2, tzinfo=timezone.utc)
SAFE_EVAL_END = datetime(2399, 12, 31, tzinfo=timezone.utc)

#: Every input is checked against these before the first evaluation. Being
#: ``MAX_REACH`` inside the evaluation range, they make the two agree.
SUPPORTED_START = SAFE_EVAL_START + MAX_REACH
SUPPORTED_END = SAFE_EVAL_END - MAX_REACH

#: Deg/day, <= 0.9 x the surveyed minima (module docstring). Sizes the first
#: probe only; no result depends on it.
RATE_MIN: Mapping[TransitionKind, float] = MappingProxyType(
    {
        TransitionKind.TITHI: 9.66,
        TransitionKind.KARANA: 9.66,
        TransitionKind.NAKSHATRA: 10.58,
        TransitionKind.YOGA: 11.46,
    }
)

#: Deg/day, >= 1.1 x the surveyed maxima (module docstring). Bounds the number
#: of iterations a listing's walk may take; no result depends on it.
RATE_MAX: Mapping[TransitionKind, float] = MappingProxyType(
    {
        TransitionKind.TITHI: 15.83,
        TransitionKind.KARANA: 15.83,
        TransitionKind.NAKSHATRA: 16.95,
        TransitionKind.YOGA: 18.07,
    }
)

UT1_NOTE = (
    "|UT1 − UTC| ≤ 0.9 s under the leap-second regime in force since 1972; "
    "not asserted for instants before 1972 (when civil time was not UTC) or "
    "for future instants should that regime change; the frozen convention is "
    "applied throughout regardless."
)

MODEL_NOTE = (
    "Positions are this engine's: Swiss Ephemeris with its DE431-derived .se1 "
    "files, apparent geocentric longitudes, Lahiri true-equinox ayanamsha "
    "(SIDM_LAHIRI). Layer 17 claims only the instant at which this engine's "
    "classification changes, not the instant at which the sky does; "
    "microsecond fields are resolution, not accuracy."
)

#: The exact string every result carries.
SEARCH_CONVENTION = (
    "predicate: a transition of a kind is a change of the Layer 16 index of "
    "that kind (the classifier itself is evaluated; no angle equation is "
    "solved); query: the caller's instant, normalised to UTC, is classified "
    "exactly as given and never snapped; grid: every search probe and both "
    "returned endpoints lie on 1970-01-01T00:00:00Z + n * tolerance, "
    "tolerance one of 1 ms, 10 ms, 100 ms, 1 s, 10 s, 1 min, 10 min, 1 h; "
    "cell: the unique grid cell (before_utc, after_utc] of width tolerance "
    "whose endpoints are verified old-side and new-side classifications, so "
    "the change lies in (before_utc, after_utc] under the monotonicity and "
    "separation assumptions; after_utc is the representative and decides "
    "interval membership start <= after_utc < end; UT1: UTC is used as UT1 "
    "(FROZEN 3.3), |UT1 - UTC| <= 0.9 s asserted only under the leap-second "
    "regime since 1972"
)


# --- the four kinds ----------------------------------------------------------


@dataclass(frozen=True)
class _KindRule:
    quantity: Quantity
    span: float
    count: int
    element_type: type
    classify: Callable[[float, float], Element]


def _tithi(sun: float, moon: float) -> Tithi:
    return tithi_from_elongation(elongation(sun, moon))


def _karana(sun: float, moon: float) -> Karana:
    return karana_from_elongation(elongation(sun, moon))


def _nakshatra(sun: float, moon: float) -> Nakshatra:
    return nakshatra_from_longitude(moon)


def _yoga(sun: float, moon: float) -> NityaYoga:
    return yoga_from_sum(longitude_sum(sun, moon))


_RULES: Mapping[TransitionKind, _KindRule] = MappingProxyType(
    {
        TransitionKind.TITHI: _KindRule(
            Quantity.ELONGATION, TITHI_SPAN, TITHI_COUNT, Tithi, _tithi
        ),
        TransitionKind.KARANA: _KindRule(
            Quantity.ELONGATION, KARANA_SPAN, KARANA_COUNT, Karana, _karana
        ),
        TransitionKind.NAKSHATRA: _KindRule(
            Quantity.MOON_LONGITUDE,
            NAKSHATRA_SPAN,
            NAKSHATRA_COUNT,
            Nakshatra,
            _nakshatra,
        ),
        TransitionKind.YOGA: _KindRule(
            Quantity.LONGITUDE_SUM, YOGA_SPAN, YOGA_COUNT, NityaYoga, _yoga
        ),
    }
)


def _on_grid(moment: datetime, tolerance: timedelta) -> bool:
    return (moment - GRID_EPOCH) % tolerance == timedelta(0)


def _require_utc(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is not timezone.utc:
        raise ValueError(
            f"{name} must be a datetime carrying timezone.utc itself; got "
            f"{value!r}."
        )


def _require_tolerance(tolerance: timedelta, name: str = "tolerance") -> None:
    if not isinstance(tolerance, timedelta) or tolerance not in ALLOWED_TOLERANCES:
        raise ValueError(
            f"{name} must be one of ALLOWED_TOLERANCES; got {tolerance!r}."
        )


# --- result types ------------------------------------------------------------


@dataclass(frozen=True)
class TransitionUncertainty:
    """Specification 5: the cell width and the two inherited qualifications."""

    cell_width: timedelta
    ut1_note: str
    model_note: str

    def __post_init__(self) -> None:
        if not isinstance(self.cell_width, timedelta) or not (
            self.cell_width > timedelta(0)
        ):
            raise ValueError(
                f"cell_width must be a positive timedelta; got {self.cell_width!r}."
            )
        if not isinstance(self.ut1_note, str) or not isinstance(
            self.model_note, str
        ):
            raise ValueError("ut1_note and model_note must be strings.")


@dataclass(frozen=True)
class EventId:
    """A transition's identity at one tolerance: ``cell_end_utc == after_utc``."""

    kind: TransitionKind
    after_index: int
    cell_end_utc: datetime


@dataclass(frozen=True)
class Transition:
    """One change of one kind, as a verified grid cell.

    ``before`` is the Layer 16 element computed at ``before_utc`` and ``after``
    the one computed at ``after_utc``; the change lies in ``(before_utc,
    after_utc]`` under the assumptions of specification 4.9. ``after_utc`` is a
    verified new-side endpoint, not "the transition instant".
    """

    kind: TransitionKind
    quantity: Quantity
    boundary_degrees: float
    before: Element
    after: Element
    before_utc: datetime
    after_utc: datetime
    before_julian_day_ut: float
    after_julian_day_ut: float
    tolerance: timedelta
    uncertainty: TransitionUncertainty

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TransitionKind):
            raise ValueError(f"kind must be a TransitionKind; got {self.kind!r}.")
        rule = _RULES[self.kind]
        if self.quantity is not rule.quantity:
            raise ValueError(
                f"a {self.kind.value} transition divides {rule.quantity}; got "
                f"{self.quantity!r}."
            )
        for name in ("before", "after"):
            element = getattr(self, name)
            if not isinstance(element, rule.element_type):
                raise ValueError(
                    f"{name} must be a {rule.element_type.__name__} for a "
                    f"{self.kind.value} transition; got {type(element).__name__}."
                )
        _require_utc(self.before_utc, "before_utc")
        _require_utc(self.after_utc, "after_utc")
        _require_tolerance(self.tolerance)
        if self.after_utc - self.before_utc != self.tolerance:
            raise ValueError(
                f"after_utc - before_utc must equal the tolerance {self.tolerance}; "
                f"got {self.after_utc - self.before_utc}."
            )
        if not (
            _on_grid(self.before_utc, self.tolerance)
            and _on_grid(self.after_utc, self.tolerance)
        ):
            raise ValueError(
                f"both endpoints must lie on the {self.tolerance} grid; got "
                f"{self.before_utc.isoformat()} and {self.after_utc.isoformat()}."
            )
        if self.after.index != (self.before.index + 1) % rule.count:
            raise ValueError(
                f"after.index must follow before.index modulo {rule.count}; got "
                f"{self.before.index} -> {self.after.index}."
            )
        if self.boundary_degrees != self.after.index * rule.span:
            raise ValueError(
                f"boundary_degrees must be after.index * span = "
                f"{self.after.index * rule.span!r}; got {self.boundary_degrees!r}."
            )
        if self.before_julian_day_ut != julian_day_ut(self.before_utc) or (
            self.after_julian_day_ut != julian_day_ut(self.after_utc)
        ):
            raise ValueError(
                "the Julian Days must be julian_day_ut of the two endpoints."
            )
        if not isinstance(self.uncertainty, TransitionUncertainty) or (
            self.uncertainty.cell_width != self.tolerance
        ):
            raise ValueError(
                "uncertainty must be a TransitionUncertainty whose cell_width "
                "is the tolerance."
            )

    @property
    def event_id(self) -> EventId:
        return EventId(self.kind, self.after.index, self.after_utc)


def same_event(a: Transition, b: Transition) -> bool:
    """Same kind, same new index, and one cell contains the other.

    The tolerance grids nest (specification 4.2), so the cells of one event at
    two tolerances nest; cells of two different events of one kind are hours
    apart and cannot.
    """
    if a.kind is not b.kind or a.after.index != b.after.index:
        return False
    a_in_b = b.before_utc <= a.before_utc and a.after_utc <= b.after_utc
    b_in_a = a.before_utc <= b.before_utc and b.after_utc <= a.after_utc
    return a_in_b or b_in_a


@dataclass(frozen=True)
class Neighbours:
    """The element current at an instant and the transitions around it."""

    kind: TransitionKind
    current: Element
    previous: Transition
    next: Transition

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TransitionKind):
            raise ValueError(f"kind must be a TransitionKind; got {self.kind!r}.")
        if not isinstance(self.current, _RULES[self.kind].element_type):
            raise ValueError(
                f"current must be the {self.kind.value} element; got "
                f"{type(self.current).__name__}."
            )
        if not (
            isinstance(self.previous, Transition)
            and isinstance(self.next, Transition)
            and self.previous.kind is self.kind
            and self.next.kind is self.kind
        ):
            raise ValueError("previous and next must be Transitions of this kind.")
        if not (
            self.previous.after.index == self.current.index == self.next.before.index
        ):
            raise ValueError(
                "previous.after.index == current.index == next.before.index is "
                f"required; got {self.previous.after.index}, "
                f"{self.current.index}, {self.next.before.index}."
            )
        if self.previous.tolerance != self.next.tolerance:
            raise ValueError("previous and next must share one tolerance.")


def _canonical_kinds_check(kinds: tuple, name: str = "kinds") -> None:
    if not isinstance(kinds, tuple) or not kinds:
        raise ValueError(f"{name} must be a non-empty tuple; got {kinds!r}.")
    if kinds != tuple(k for k in ALL_KINDS if k in kinds) or len(set(kinds)) != len(
        kinds
    ):
        raise ValueError(
            f"{name} must be distinct TransitionKinds in canonical order; got "
            f"{kinds!r}."
        )


@dataclass(frozen=True)
class PanchangaTransitions:
    """Neighbours for each requested kind at one instant.

    ``neighbours`` is a read-only ``MappingProxyType`` over a private copy
    whose keys are exactly ``kinds`` in canonical order; there are no per-kind
    attributes, so a subset request has a subset result.
    """

    instant_utc: datetime
    julian_day_ut: float
    tolerance: timedelta
    kinds: tuple[TransitionKind, ...]
    neighbours: Mapping[TransitionKind, Neighbours]
    calculation_convention: str
    search_convention: str

    def __post_init__(self) -> None:
        _require_utc(self.instant_utc, "instant_utc")
        _require_tolerance(self.tolerance)
        _canonical_kinds_check(self.kinds)
        if tuple(self.neighbours) != self.kinds:
            raise ValueError(
                f"neighbours must be keyed by exactly {self.kinds!r} in that "
                f"order; got {tuple(self.neighbours)!r}."
            )
        for kind, entry in self.neighbours.items():
            if not isinstance(entry, Neighbours) or entry.kind is not kind:
                raise ValueError(f"neighbours[{kind}] must be that kind's Neighbours.")
            if entry.previous.tolerance != self.tolerance:
                raise ValueError(f"neighbours[{kind}] has a different tolerance.")
        object.__setattr__(
            self, "neighbours", MappingProxyType(dict(self.neighbours))
        )


def _unordered_pairs(
    transitions: tuple[Transition, ...]
) -> tuple[tuple[int, int], ...]:
    """Adjacent pairs of different quantities whose cells are identical.

    On one grid at one width, cells either coincide or are disjoint, so the
    identity test is the overlap test. Same-quantity pairs (tithi/karana) are
    simultaneous by construction and are not an open order question.
    """
    pairs = []
    for index in range(len(transitions) - 1):
        earlier, later = transitions[index], transitions[index + 1]
        if (
            earlier.quantity is not later.quantity
            and earlier.before_utc == later.before_utc
            and earlier.after_utc == later.after_utc
        ):
            pairs.append((index, index + 1))
    return tuple(pairs)


def _order_key(transition: Transition) -> tuple[datetime, int]:
    return transition.after_utc, ALL_KINDS.index(transition.kind)


@dataclass(frozen=True)
class TransitionList:
    """Every transition whose ``after_utc`` lies in ``[start_utc, end_utc)``.

    Sorted by ``(after_utc, canonical kind order)`` -- an order of
    representatives.

    ``unordered_pairs``: an adjacent pair ``(i, i + 1)`` is listed iff the two
    transitions divide **different quantities** and have **identical cells**
    (one grid, one width: overlapping means identical). For such a pair the data
    do not prove which change came first; lower the tolerance to separate them
    (the finer cells nest inside these). A tithi/karana pair is never listed:
    both divide the elongation, and their shared cell is one simultaneous change
    by construction (specification 4.8), not an unproven order.
    """

    start_utc: datetime
    end_utc: datetime
    tolerance: timedelta
    kinds: tuple[TransitionKind, ...]
    transitions: tuple[Transition, ...]
    unordered_pairs: tuple[tuple[int, int], ...]
    calculation_convention: str
    search_convention: str

    def __post_init__(self) -> None:
        _require_utc(self.start_utc, "start_utc")
        _require_utc(self.end_utc, "end_utc")
        _require_tolerance(self.tolerance)
        _canonical_kinds_check(self.kinds)
        if not isinstance(self.transitions, tuple):
            raise ValueError("transitions must be a tuple.")
        for transition in self.transitions:
            if not isinstance(transition, Transition):
                raise ValueError(f"not a Transition: {transition!r}.")
            if transition.kind not in self.kinds:
                raise ValueError(f"{transition.kind} was not requested.")
            if transition.tolerance != self.tolerance:
                raise ValueError("every transition must carry the list's tolerance.")
            if not self.start_utc <= transition.after_utc < self.end_utc:
                raise ValueError(
                    f"{transition.after_utc.isoformat()} is not in "
                    "[start_utc, end_utc)."
                )
        if list(self.transitions) != sorted(self.transitions, key=_order_key):
            raise ValueError(
                "transitions must be sorted by (after_utc, canonical kind order)."
            )
        if self.unordered_pairs != _unordered_pairs(self.transitions):
            raise ValueError(
                "unordered_pairs must be exactly the adjacent pairs of "
                "different quantities whose cells are identical."
            )


@dataclass(frozen=True)
class LocalTransition:
    """A transition presented in an IANA zone; the UTC fields are unchanged."""

    transition: Transition
    timezone_id: str
    before_local: datetime
    after_local: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.transition, Transition):
            raise ValueError("transition must be a Transition.")
        # Subtraction, not ``!=``: under PEP 495 an aware datetime in a
        # repeated (fold) hour never compares equal to one in another zone,
        # while the difference is computed through ``utcoffset`` and is exact.
        if (
            not isinstance(self.before_local, datetime)
            or not isinstance(self.after_local, datetime)
            or self.before_local.tzinfo is None
            or self.after_local.tzinfo is None
            or self.before_local - self.transition.before_utc != timedelta(0)
            or self.after_local - self.transition.after_utc != timedelta(0)
        ):
            raise ValueError(
                "before_local and after_local must be the transition's own "
                "instants, zone-aware."
            )


# --- the search --------------------------------------------------------------


def default_evaluate(moment_utc: datetime) -> tuple[float, float]:
    """The Sun's and the Moon's sidereal longitudes through Layer 6 (D7).

    The one path to longitudes, identical to Layer 16's: every value the search
    classifies is exactly what ``calculate_panchanga`` would classify at the
    same datetime.
    """
    sidereal = calculate_sidereal_positions(moment_utc)
    return (
        sidereal.bodies[Body.SUN].sidereal_longitude,
        sidereal.bodies[Body.MOON].sidereal_longitude,
    )


def _ceil_cells(duration: timedelta, tolerance: timedelta) -> int:
    """Whole cells covering ``duration``, rounded up; integer arithmetic only."""
    return -((-duration) // tolerance)


class _Search:
    """One search of one kind from one query instant at one tolerance."""

    def __init__(
        self,
        kind: TransitionKind,
        t0: datetime,
        tolerance: timedelta,
        evaluate: Evaluate,
    ) -> None:
        self.kind = kind
        self.rule = _RULES[kind]
        self.t0 = t0
        self.tolerance = tolerance
        self.evaluate = evaluate
        self.probes: list[datetime] = []

    def classify(self, moment: datetime) -> Element:
        sun, moon = self.evaluate(moment)
        return self.rule.classify(sun, moon)

    def fail(self, check: str) -> TransitionSearchError:
        evaluated = ", ".join(p.isoformat() for p in self.probes)
        return TransitionSearchError(
            f"{self.kind.value} search from {self.t0.isoformat()} at tolerance "
            f"{self.tolerance}: {check}. Probes evaluated: [{evaluated}]."
        )

    def probe(self, moment: datetime) -> Element:
        if not _on_grid(moment, self.tolerance):
            raise self.fail(f"probe {moment.isoformat()} is not a grid point")
        if abs(moment - self.t0) > MAX_REACH:
            raise self.fail(
                f"probe {moment.isoformat()} is {abs(moment - self.t0)} from the "
                f"query, beyond MAX_REACH {MAX_REACH}; the bracket was not "
                "verified within reach"
            )
        if not SAFE_EVAL_START <= moment <= SAFE_EVAL_END:
            raise self.fail(
                f"probe {moment.isoformat()} is outside the safe evaluation "
                f"range [{SAFE_EVAL_START.isoformat()}, {SAFE_EVAL_END.isoformat()}]"
            )
        self.probes.append(moment)
        return self.classify(moment)

    def snap_down(self, moment: datetime) -> datetime:
        return GRID_EPOCH + ((moment - GRID_EPOCH) // self.tolerance) * self.tolerance

    def first_step(self, fraction_of_span: float) -> timedelta:
        days = fraction_of_span * self.rule.span / RATE_MIN[self.kind]
        cells = _ceil_cells(timedelta(days=days), self.tolerance)
        return max(cells, 1) * self.tolerance

    def bisect(
        self,
        a: datetime,
        element_a: Element,
        b: datetime,
        element_b: Element,
    ) -> tuple[datetime, Element, datetime, Element]:
        old, new = element_a.index, element_b.index
        while b - a > self.tolerance:
            cells = (b - a) // self.tolerance
            mid = a + (cells // 2) * self.tolerance
            if not julian_day_ut(a) < julian_day_ut(mid) < julian_day_ut(b):
                raise self.fail(
                    f"no Julian Day progress between {a.isoformat()}, "
                    f"{mid.isoformat()} and {b.isoformat()}"
                )
            element_mid = self.probe(mid)
            if element_mid.index == old:
                a, element_a = mid, element_mid
            elif element_mid.index == new:
                b, element_b = mid, element_mid
            else:
                raise self.fail(
                    f"bisection midpoint {mid.isoformat()} has index "
                    f"{element_mid.index}, neither {old} nor {new}"
                )
        return a, element_a, b, element_b

    def transition(
        self, a: datetime, element_a: Element, b: datetime, element_b: Element
    ) -> Transition:
        return Transition(
            kind=self.kind,
            quantity=self.rule.quantity,
            boundary_degrees=element_b.index * self.rule.span,
            before=element_a,
            after=element_b,
            before_utc=a,
            after_utc=b,
            before_julian_day_ut=julian_day_ut(a),
            after_julian_day_ut=julian_day_ut(b),
            tolerance=self.tolerance,
            uncertainty=TransitionUncertainty(
                cell_width=self.tolerance, ut1_note=UT1_NOTE, model_note=MODEL_NOTE
            ),
        )

    def next(self, e0: Element) -> Transition:
        count = self.rule.count
        k0, k1 = e0.index, (e0.index + 1) % count
        g0 = self.snap_down(self.t0)
        g1 = g0 + self.tolerance

        e_g1 = self.probe(g1)
        if e_g1.index != k0:
            e_g0 = self.probe(g0)
            if e_g0.index != k0:
                raise self.fail(
                    f"two changes of one kind inside the cell ({g0.isoformat()}, "
                    f"{g1.isoformat()}]"
                )
            if e_g1.index != k1:
                raise self.fail(
                    f"cell end {g1.isoformat()} has index {e_g1.index}, not the "
                    f"successor {k1}"
                )
            return self.transition(g0, e_g0, g1, e_g1)

        step = self.first_step(1.0 - e0.angular_fraction)
        lo, e_lo = g1, e_g1
        hi = lo + step
        e_hi = self.probe(hi)
        while e_hi.index == k0:
            step = step * 2
            lo, e_lo = hi, e_hi
            hi = hi + step
            e_hi = self.probe(hi)
        if e_hi.index != k1:
            raise self.fail(
                f"bracket end {hi.isoformat()} has index {e_hi.index}, not the "
                f"successor {k1}"
            )
        return self.transition(*self.bisect(lo, e_lo, hi, e_hi))

    def previous(self, e0: Element) -> Transition:
        count = self.rule.count
        k0, kp = e0.index, (e0.index - 1) % count
        g0 = self.snap_down(self.t0)

        e_g0 = self.probe(g0)
        if e_g0.index != k0:
            g1 = g0 + self.tolerance
            e_g1 = self.probe(g1)
            if e_g1.index != k0:
                raise self.fail(
                    f"two changes of one kind inside the cell ({g0.isoformat()}, "
                    f"{g1.isoformat()}]"
                )
            if e_g0.index != kp:
                raise self.fail(
                    f"cell start {g0.isoformat()} has index {e_g0.index}, not the "
                    f"predecessor {kp}"
                )
            return self.transition(g0, e_g0, g1, e_g1)

        step = self.first_step(e0.angular_fraction)
        hi, e_hi = g0, e_g0
        lo = hi - step
        e_lo = self.probe(lo)
        while e_lo.index == k0:
            step = step * 2
            hi, e_hi = lo, e_lo
            lo = lo - step
            e_lo = self.probe(lo)
        if e_lo.index != kp:
            raise self.fail(
                f"bracket start {lo.isoformat()} has index {e_lo.index}, not the "
                f"predecessor {kp}"
            )
        return self.transition(*self.bisect(lo, e_lo, hi, e_hi))


# --- validation (specification 3's table; before any evaluation) ----------------


def _check_supported(moment: datetime, name: str) -> None:
    if not SUPPORTED_START <= moment <= SUPPORTED_END:
        raise UnsupportedInstantError(
            f"{name} {moment.isoformat()} is outside the supported range "
            f"[{SUPPORTED_START.isoformat()}, {SUPPORTED_END.isoformat()}]."
        )


def _instant(moment_utc: datetime, name: str) -> tuple[datetime, float]:
    moment, julian_day = utc_instant(moment_utc)
    _check_supported(moment, name)
    return moment, julian_day


def _check_kind(kind: TransitionKind) -> None:
    if not isinstance(kind, TransitionKind):
        raise TransitionRequestError(
            f"kind must be a TransitionKind; got {kind!r}."
        )


def _check_kinds(kinds: Iterable[TransitionKind]) -> tuple[TransitionKind, ...]:
    try:
        members = tuple(kinds)
    except TypeError as exc:
        raise TransitionRequestError(
            f"kinds must be an iterable of TransitionKind; got {kinds!r}."
        ) from exc
    if not members:
        raise TransitionRequestError("kinds must not be empty.")
    for member in members:
        if not isinstance(member, TransitionKind):
            raise TransitionRequestError(
                f"kinds contains {member!r}, which is not a TransitionKind."
            )
    if len(set(members)) != len(members):
        raise TransitionRequestError(f"kinds contains a duplicate: {members!r}.")
    return tuple(kind for kind in ALL_KINDS if kind in members)


def _check_tolerance(tolerance: timedelta) -> None:
    if not isinstance(tolerance, timedelta):
        raise TransitionRequestError(
            f"tolerance must be a timedelta; got {tolerance!r}."
        )
    if tolerance not in ALLOWED_TOLERANCES:
        raise TransitionRequestError(
            f"tolerance must be one of ALLOWED_TOLERANCES; got {tolerance}."
        )


def _query(kind: TransitionKind, moment: datetime, evaluate: Evaluate) -> Element:
    """The one off-grid evaluation: the caller's own instant."""
    sun, moon = evaluate(moment)
    return _RULES[kind].classify(sun, moon)


# --- public functions ----------------------------------------------------------


def next_transition(
    moment_utc: datetime,
    kind: TransitionKind,
    *,
    tolerance: timedelta = DEFAULT_TOLERANCE,
    evaluate: Evaluate = default_evaluate,
) -> Transition:
    """The first transition of ``kind`` after the element current at the instant."""
    moment, _julian_day = _instant(moment_utc, "moment_utc")
    _check_kind(kind)
    _check_tolerance(tolerance)
    e0 = _query(kind, moment, evaluate)
    return _Search(kind, moment, tolerance, evaluate).next(e0)


def previous_transition(
    moment_utc: datetime,
    kind: TransitionKind,
    *,
    tolerance: timedelta = DEFAULT_TOLERANCE,
    evaluate: Evaluate = default_evaluate,
) -> Transition:
    """The transition that began the element of ``kind`` current at the instant."""
    moment, _julian_day = _instant(moment_utc, "moment_utc")
    _check_kind(kind)
    _check_tolerance(tolerance)
    e0 = _query(kind, moment, evaluate)
    return _Search(kind, moment, tolerance, evaluate).previous(e0)


def find_transitions(
    moment_utc: datetime,
    *,
    kinds: Iterable[TransitionKind] = ALL_KINDS,
    tolerance: timedelta = DEFAULT_TOLERANCE,
    evaluate: Evaluate = default_evaluate,
) -> PanchangaTransitions:
    """Previous and next transition of each requested kind around an instant.

    The query is evaluated once and classified for every kind, so each
    ``current`` is Layer 16's answer at the caller's exact instant.
    """
    moment, julian_day = _instant(moment_utc, "moment_utc")
    requested = _check_kinds(kinds)
    _check_tolerance(tolerance)

    sun, moon = evaluate(moment)
    neighbours = {}
    for kind in requested:
        current = _RULES[kind].classify(sun, moon)
        neighbours[kind] = Neighbours(
            kind=kind,
            current=current,
            previous=_Search(kind, moment, tolerance, evaluate).previous(current),
            next=_Search(kind, moment, tolerance, evaluate).next(current),
        )

    return PanchangaTransitions(
        instant_utc=moment,
        julian_day_ut=julian_day,
        tolerance=tolerance,
        kinds=requested,
        neighbours=neighbours,
        calculation_convention=CALCULATION_CONVENTION,
        search_convention=SEARCH_CONVENTION,
    )


def _walk_bound(kind: TransitionKind, interval: timedelta) -> int:
    """``ceil(interval_days * RATE_MAX / span) + 3`` without ``math``."""
    changes = (interval / timedelta(days=1)) * RATE_MAX[kind] / _RULES[kind].span
    whole = int(changes)
    if whole < changes:
        whole += 1
    return whole + 3


def list_transitions(
    start_utc: datetime,
    end_utc: datetime,
    *,
    kinds: Iterable[TransitionKind] = ALL_KINDS,
    tolerance: timedelta = DEFAULT_TOLERANCE,
    evaluate: Evaluate = default_evaluate,
) -> TransitionList:
    """Every transition whose representative lies in ``[start_utc, end_utc)``.

    Membership is ``start <= after_utc < end`` for the candidate
    ``previous_transition(start)`` -- which catches a change whose cell
    straddles ``start`` -- and for every step of the walk from ``start``.
    Because cells are canonical, adjacent intervals partition exactly.
    """
    start, _start_jd = _instant(start_utc, "start_utc")
    end, _end_jd = _instant(end_utc, "end_utc")
    if end <= start:
        raise IntervalError(
            f"end_utc {end.isoformat()} must be after start_utc {start.isoformat()}."
        )
    if end - start > MAX_INTERVAL:
        raise IntervalError(
            f"the interval {end - start} is longer than MAX_INTERVAL {MAX_INTERVAL}."
        )
    requested = _check_kinds(kinds)
    _check_tolerance(tolerance)

    found: list[Transition] = []
    for kind in requested:
        candidate = previous_transition(
            start, kind, tolerance=tolerance, evaluate=evaluate
        )
        if start <= candidate.after_utc < end:
            found.append(candidate)

        cursor = start
        bound = _walk_bound(kind, end - start)
        finished = False
        for _iteration in range(bound):
            step = next_transition(
                cursor, kind, tolerance=tolerance, evaluate=evaluate
            )
            if step.after_utc <= cursor:
                raise TransitionSearchError(
                    f"{kind.value} listing did not advance: the transition after "
                    f"{cursor.isoformat()} ends at {step.after_utc.isoformat()}."
                )
            if step.after_utc >= end:
                finished = True
                break
            if step.after_utc >= start:
                found.append(step)
            cursor = step.after_utc
        if not finished:
            raise TransitionSearchError(
                f"{kind.value} listing of [{start.isoformat()}, {end.isoformat()}) "
                f"did not reach its end within {bound} iterations "
                f"(ceil(days * RATE_MAX / span) + 3)."
            )

    ordered = tuple(sorted(found, key=_order_key))
    return TransitionList(
        start_utc=start,
        end_utc=end,
        tolerance=tolerance,
        kinds=requested,
        transitions=ordered,
        unordered_pairs=_unordered_pairs(ordered),
        calculation_convention=CALCULATION_CONVENTION,
        search_convention=SEARCH_CONVENTION,
    )


def local_transition(transition: Transition, timezone_id: str) -> LocalTransition:
    """Present a transition's two instants in an IANA zone.

    The zone is resolved by Layer 16's ``resolve_zone`` (``InvalidTimezoneError``
    on a bad identifier); the transition itself is carried unchanged.
    """
    if not isinstance(transition, Transition):
        raise TransitionRequestError(
            f"transition must be a Transition; got {type(transition).__name__}."
        )
    zone = resolve_zone(timezone_id)
    return LocalTransition(
        transition=transition,
        timezone_id=timezone_id,
        before_local=transition.before_utc.astimezone(zone),
        after_local=transition.after_utc.astimezone(zone),
    )
