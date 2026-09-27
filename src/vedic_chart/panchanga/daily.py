"""Layer 18: the daily panchanga, from one sunrise to the next.

Given a **local civil date** (or an instant), coordinates and an IANA zone, this
module returns the Panchanga day that opens at the geometric Hindu sunrise
carrying that civil date (or containing that instant) and closes at the next
sunrise, composed from Layer 16 (``find_sunrise_window``, ``vara_from_sunrise``
and the element classifiers) and Layer 17 (``find_transitions``,
``list_transitions``). Specification: ``docs/LAYER18_DAILY_PANCHANGA_SPEC.md``
(DRAFT v0.3).

It adds exactly three things to the layers below: the mapping *civil date (or
instant) -> sunrise pair*, a rule that makes consecutive days share one sunrise
bit for bit, and the placement of each listed transition relative to the two
sunrises. Every other field is a lower layer's object, carried by identity.

**The canonical anchor rule (specification 4.1).** Sunrises are only ever
obtained through Layer 16's public ``find_sunrise_window``, asked at the
anchors ``ANCHOR_EPOCH + k * ANCHOR_STEP`` (1970-01-01T00:00Z plus a whole
number of 12-hour steps) -- microsecond-exact UTC datetimes that do not depend
on the request. A walk visits every anchor of a closed range in increasing
order and keeps one entry per sunrise: the window of the **first** anchor that
falls inside that sunrise's window. The ``previous_*`` fields of that window are
the sunrise's canonical Julian Day and datetime. Because the grid is global,
two requests that need the same sunrise ask Layer 16 the same question at the
same anchor and receive the same float, so the closing of one day is the
opening of the next, compared with ``==``. That matters because the float the
library returns for one sunrise depends on the probe it was asked from: Layer
16 asked from two different instants has been measured to locate one sunrise
up to ~14 ms apart at every instant above about 65 degrees of latitude, and up
to ~141 ms apart at any latitude when the instant lies in the last minutes of
a day longer than 24 hours (specification 3.2, probes A and G); from most
instants of most days the sampled floats were identical. None of these
observations is used as a bound; the anchor rule does not need one.

A walk's entries are: a *located* sunrise (its window, and whether it is
canonical -- it is not when it was first seen at the walk's very first anchor,
since an earlier anchor the walk did not visit might have seen it first); a
stretch of unavailability (consecutive ``SunriseUnavailable`` results with one
reason make one entry, and the reasons are expected to change along a polar
stretch); and, derived from them, the *next-only* sunrises -- a located
window's ``next`` that no located entry has as its ``previous``: the sunrise
that closes a day but opens none, before a polar day or night. Three guards
make the walk refuse rather than guess, all ``DaySearchError``: a located
sunrise not later than the one before it, a located sunrise earlier than the
previous window's ``next`` by more than ``SAME_SUNRISE_MAX_SEPARATION`` (Layer
16 skipped one), and a walk that produced nothing. A located sunrise *later*
than the previous window's ``next`` is the first sunrise after a gap and is
not an error.

Two sunrise floats denote the same sunrise when they differ by less than
``SAME_SUNRISE_MAX_SEPARATION`` (half a day). That is an event-identity rule,
not an epsilon: consecutive sunrises are about a day apart, and the rule is
never used to compare an instant with a sunrise.

**Selecting a day (specification 4.3).** The date form walks
``[D0 - WALK_BEFORE, D0 + WALK_AFTER]`` around ``D0 = D at 00:00 UTC`` (a
bookkeeping origin, never a boundary of anything) and takes as candidates the
canonical located sunrises whose local date is *D*: one candidate is the
opening, none is a ``PanchangaDayUnavailable``, several without an ordinal are
a ``PanchangaDayAmbiguous``. The containing form walks ``[t -
CONTAINING_WALK_BEFORE, t + CONTAINING_WALK_AFTER]``, takes the last canonical
located sunrise at or before ``t`` as the opening, and reports a day only if
``opening <= jd(t) < closing``; its civil date and ordinal are then obtained by
running the **same** date-selection helper for the opening's local date and
finding the opening's float among its candidates, so that the date form with
that ordinal reproduces the day exactly. Layer 16's own answer at ``t`` is
carried as ``layer16_at_instant`` for comparison and never steers anything.

The closing: if the next canonical located sunrise after the opening is the
same event as the opening window's ``next``, the closing is that sunrise's own
canonical float (``CANONICAL_ANCHOR``) -- the value the next date reports as
its opening; otherwise (none, or only one after a gap) the closing is the
opening window's ``next`` (``WINDOW_NEXT``), the last complete day before a
polar stretch, which no later day can disagree with.

**The two membership predicates (specification 2, 7.1).** Layer 16 decides
whether an instant belongs to a day on Julian Day floats, ``opening_jd <=
jd(t) < closing_jd``; Layer 17 decides whether a transition belongs to an
interval on microsecond datetimes, ``start_utc <= after_utc < end_utc``. About
forty microsecond datetimes share each sunrise float, so the two disagree at
the endpoints: ``opening.utc - 1 us`` is in the day by Julian Day and out of it
by datetime; ``closing.utc - 1 us`` the reverse. Both are kept exactly as their
layers define them; nothing is nudged to make them agree. Every datetime this
module reports as a sunrise must name its float --
``utc_instant(sunrise.utc)[1] == sunrise.julian_day_ut`` -- which specification
3.1 shows holds throughout the supported range, and which is checked at every
sunrise constructed here (``DaySearchError`` otherwise); no microsecond is ever
added or removed to make it true.

**Elements and placement (specification 4.5, 4.6).** The elements at the
opening are Layer 17's ``find_transitions(opening.utc).neighbours[kind]
.current``; the two longitudes are evaluated once more through the same
``evaluate`` and classified with Layer 16's classifiers, and the two sets of
records must be equal field for field -- the one place whole-record equality
is right, because it is the same instant. The same is done at the closing.
The listing is ``list_transitions(opening.utc, closing.utc)``, carried whole;
each listed transition is placed by its cell datetimes and by the **index**
(never the whole record) of the opening element of its kind: ``WITHIN`` when
the cell starts at or after the opening datetime, ``STRADDLES_OPENING_REFLECTED``
when the cell contains the opening datetime and the day opened in its new
element (then it is Layer 17's ``previous`` at the opening), and
``STRADDLES_OPENING_AFTER`` when the cell strictly contains the opening
datetime and the day opened in its old element (then it is Layer 17's
``next``). Any other combination is a ``DaySearchError``. The cell of the
transition into the element current at the closing, when it spans or ends at
the closing datetime (``before_utc < closing.utc <= after_utc``), is reported
in ``cells_at_closing`` as ``AT_OR_BEFORE_CLOSING``: the change lies in
``(before_utc, closing.utc]`` and nothing more is claimed -- in particular not
that it happened inside this day.

**Bounded neighbours (specification 6).** On an unavailable result,
``preceding_sunrise`` and ``following_sunrise`` are what the walk found and
nothing more. ``None`` means "not found within the walked range", never "no
such sunrise exists"; the search is not widened.

**What is not claimed.** The sunrise is Layer 16's geometric rising, not an
almanac's refracted upper-limb one. A placement is a relation between a
datetime cell and two datetimes, not Julian Day membership. At high latitude
Layer 16 asked directly near a sunrise may bracket an instant into the other
day (specification 7.3); this module answers by its canonical floats, reports
Layer 16's answer beside them in the containing form, and corrects nothing.

**Refusals.** Everything checkable before evaluation is checked first, in the
order of specification 9, so a refused request costs no ``rise_after`` and no
``evaluate`` call: the civil date's type (``DayRequestError``), the ordinal
(``DayRequestError``), the date range (``UnsupportedDateError``) or the
instant's awareness (Layer 4's ``ValueError``) and range (Layer 17's
``UnsupportedInstantError``), the coordinates and the zone (Layer 16's
``ValueError`` and ``InvalidTimezoneError``), and the tolerance (Layer 17's
``TransitionRequestError``, restated here from the public
``ALLOWED_TOLERANCES``). Every internal check is an ``if`` followed by a
``raise`` of ``DaySearchError`` -- none is a statement that ``python -O`` would
strip -- so optimised Python changes nothing. The ephemeris lifecycle is the caller's
(``ephemeris_session``), as for Layers 16 and 17.

Interpretations, recorded rather than left implicit:

* The containing walk visits the anchors *inside* the closed range
  ``[t - 72 h, t + 60 h]``: eleven of them when ``t`` is off the anchor grid
  and twelve when it is on it. Specification 4.3 says "12 anchors"; its own
  probes (F1, F2) walked eleven for off-grid instants, and the coverage
  argument of specification 4.10 holds for both.
* A date form request that finds no candidate returns the unavailable result
  whatever ``sunrise_ordinal`` says; ``DayRequestError`` is raised only when
  there are candidates and the ordinal exceeds their number.
* For the date form, "before the date's span" and "after it" are read on the
  sunrise's local date: ``preceding_sunrise`` is the last sunrise the walk saw
  whose local date is earlier than the requested one, ``following_sunrise`` the
  first canonical one whose local date is later. For the containing form they
  are the last sunrise at or before ``jd(t)`` and the first canonical one after
  it.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from .compute import LocationProvenance, PanchangaLocation
from .elements import (
    CALCULATION_CONVENTION,
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
from .sunrise import (
    SUNRISE_CONVENTION,
    RiseAfter,
    SunriseUnavailable,
    SunriseWindow,
    Vara,
    default_rise_after,
    find_sunrise_window,
    resolve_zone,
    utc_instant,
    validate_coordinates,
    vara_from_sunrise,
)
from .transitions import (
    ALL_KINDS,
    ALLOWED_TOLERANCES,
    DEFAULT_TOLERANCE,
    SEARCH_CONVENTION,
    Evaluate,
    PanchangaTransitions,
    Transition,
    TransitionKind,
    TransitionList,
    TransitionRequestError,
    UnsupportedInstantError,
    default_evaluate,
    find_transitions,
    list_transitions,
    same_event,
)

__all__ = [
    "ANCHOR_EPOCH",
    "ANCHOR_STEP",
    "CONTAINING_WALK_AFTER",
    "CONTAINING_WALK_BEFORE",
    "DEFAULT_TOLERANCE",
    "DayPlacement",
    "DayRequestError",
    "DaySearchError",
    "DaySunrise",
    "DayUnavailableReason",
    "InstantElements",
    "MAX_OFFSET_HOURS",
    "PanchangaDay",
    "PanchangaDayAmbiguous",
    "PanchangaDayUnavailable",
    "PlacedTransition",
    "SAME_SUNRISE_MAX_SEPARATION",
    "SUPPORTED_DATE_END",
    "SUPPORTED_DATE_START",
    "SUPPORTED_INSTANT_END",
    "SUPPORTED_INSTANT_START",
    "SunriseLocating",
    "UnsupportedDateError",
    "WALK_AFTER",
    "WALK_BEFORE",
    "panchanga_day",
    "panchanga_day_containing",
]


# --- constants (specification 4.9) --------------------------------------------

#: Anchor *k* is ``ANCHOR_EPOCH + k * ANCHOR_STEP``: independent of the request.
ANCHOR_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
ANCHOR_STEP = timedelta(hours=12)

#: The date form walks ``[D0 - WALK_BEFORE, D0 + WALK_AFTER]`` (14 anchors).
WALK_BEFORE = timedelta(hours=48)
WALK_AFTER = timedelta(hours=108)

#: The containing form walks ``[t - CONTAINING_WALK_BEFORE, t +
#: CONTAINING_WALK_AFTER]``.
CONTAINING_WALK_BEFORE = timedelta(hours=72)
CONTAINING_WALK_AFTER = timedelta(hours=60)

#: Days. Two Layer 16 sunrise floats closer than this are one sunrise located
#: twice; consecutive sunrises are about a day apart. An identity rule, not an
#: epsilon.
SAME_SUNRISE_MAX_SEPARATION = 0.5

#: The date form's inputs (specification 4.7, D8 provisional).
SUPPORTED_DATE_START = date(1800, 1, 7)
SUPPORTED_DATE_END = date(2399, 12, 21)

#: The containing form's inputs, chosen so that the opening's civil date always
#: lies inside the date range (specification 4.7, D8 provisional).
SUPPORTED_INSTANT_START = datetime(1800, 1, 10, tzinfo=timezone.utc)
SUPPORTED_INSTANT_END = datetime(2399, 12, 21, tzinfo=timezone.utc)

#: The coverage assumption of specification 4.10: every UTC offset in the tz
#: database lies within this many hours. Tested against the installed database.
MAX_OFFSET_HOURS = 16


# --- vocabulary ---------------------------------------------------------------


class SunriseLocating(Enum):
    """How a reported sunrise was obtained."""

    #: The ``previous`` of the first walked anchor inside its own window.
    CANONICAL_ANCHOR = "canonical_anchor"
    #: The ``next`` of the window before it; it opens no located window.
    WINDOW_NEXT = "window_next"
    #: Seen only at the walk's very first anchor; information, never a boundary.
    FIRST_ANCHOR = "first_anchor"


class DayPlacement(Enum):
    """Where a transition's datetime cell lies relative to the two sunrises."""

    WITHIN = "within"
    STRADDLES_OPENING_REFLECTED = "straddles_opening_reflected"
    STRADDLES_OPENING_AFTER = "straddles_opening_after"
    #: ``cells_at_closing`` only, never in ``placed``.
    AT_OR_BEFORE_CLOSING = "at_or_before_closing"


class DayUnavailableReason(Enum):
    """Why no Panchanga day is returned (a result, not an exception)."""

    #: Date form: every anchor gave a window and none carries the date.
    NO_SUNRISE_WITH_DATE = "no_sunrise_with_date"
    #: Date form: no sunrise carries the date and the walk met unavailability;
    #: containing form: no canonical day contains the instant.
    SUNRISE_UNAVAILABLE = "sunrise_unavailable"
    #: Date form: only a next-only sunrise carries the date.
    NO_VARA_DAY_AT_SUNRISE = "no_vara_day_at_sunrise"


class DayRequestError(ValueError):
    """``civil_date`` or ``sunrise_ordinal`` is not a valid request."""


class UnsupportedDateError(ValueError):
    """``civil_date`` lies outside ``[SUPPORTED_DATE_START, SUPPORTED_DATE_END]``."""


class DaySearchError(RuntimeError):
    """A walk guard, the image check or a consistency check failed."""


# --- result types (specification 5, 6) -------------------------------------------


@dataclass(frozen=True)
class DaySunrise:
    """One sunrise as Layer 16 returned it: the float and its datetime images.

    ``julian_day_ut`` is the value every membership comparison is made on;
    ``utc`` is its exact microsecond image and ``local`` the same instant in
    the place's zone, whose date is the sunrise's civil date.
    """

    utc: datetime
    julian_day_ut: float
    local: datetime
    timezone_id: str
    located_by: SunriseLocating


@dataclass(frozen=True)
class InstantElements:
    """The four angular elements at one instant, with the two longitudes."""

    tithi: Tithi
    karana: Karana
    nakshatra: Nakshatra
    yoga: NityaYoga
    sun_sidereal_longitude: float
    moon_sidereal_longitude: float


@dataclass(frozen=True)
class PlacedTransition:
    """A Layer 17 transition and its placement relative to the day."""

    transition: Transition
    placement: DayPlacement


@dataclass(frozen=True)
class PanchangaDay:
    """The interval ``[opening, closing)`` between two consecutive sunrises.

    Membership of an instant is Layer 16's, on the two Julian Day floats;
    membership of a listed transition is Layer 17's, on ``after_utc``. The two
    differ within the few tens of microseconds that share a sunrise float, and
    neither is adjusted.
    """

    civil_date: date
    sunrise_ordinal: int
    location: PanchangaLocation
    timezone_id: str
    opening: DaySunrise
    closing: DaySunrise
    opening_window: SunriseWindow
    closing_window: SunriseWindow | None
    vara: Vara
    at_opening: InstantElements
    at_closing: InstantElements
    transitions_at_opening: PanchangaTransitions
    transitions_at_closing: PanchangaTransitions
    listing: TransitionList
    placed: tuple[PlacedTransition, ...]
    cells_at_closing: Mapping[TransitionKind, PlacedTransition]
    layer16_at_instant: SunriseWindow | SunriseUnavailable | None
    query_utc: datetime | None
    tolerance: timedelta
    calculation_convention: str
    sunrise_convention: str
    search_convention: str

    def __post_init__(self) -> None:
        if self.opening.located_by is not SunriseLocating.CANONICAL_ANCHOR:
            raise ValueError(
                "the opening must be a canonical anchor sunrise; got "
                f"{self.opening.located_by!r}."
            )
        if not self.opening.julian_day_ut < self.closing.julian_day_ut:
            raise ValueError(
                f"the opening {self.opening.julian_day_ut!r} must be before the "
                f"closing {self.closing.julian_day_ut!r}."
            )
        if self.vara.sunrise is not self.opening_window:
            raise ValueError("the vara must have been read from the opening window.")
        if not (
            self.listing.start_utc == self.opening.utc
            and self.listing.end_utc == self.closing.utc
        ):
            raise ValueError(
                "the listing must run from opening.utc to closing.utc exactly."
            )
        if len(self.placed) != len(self.listing.transitions) or any(
            entry.transition is not transition
            for entry, transition in zip(self.placed, self.listing.transitions)
        ):
            raise ValueError(
                "placed must carry the listing's transitions, in its order, by "
                "identity."
            )
        if any(
            entry.placement is DayPlacement.AT_OR_BEFORE_CLOSING
            for entry in self.placed
        ):
            raise ValueError("no listed transition may be AT_OR_BEFORE_CLOSING.")
        for kind, entry in self.cells_at_closing.items():
            if entry.placement is not DayPlacement.AT_OR_BEFORE_CLOSING:
                raise ValueError(
                    f"cells_at_closing[{kind}] must be AT_OR_BEFORE_CLOSING."
                )
            cell = entry.transition
            if not cell.before_utc < self.closing.utc <= cell.after_utc:
                raise ValueError(
                    f"cells_at_closing[{kind}] must span or end at the closing: "
                    "before_utc < closing.utc <= after_utc."
                )
        for name, elements, transitions in (
            ("opening", self.at_opening, self.transitions_at_opening),
            ("closing", self.at_closing, self.transitions_at_closing),
        ):
            if not _elements_match(elements, transitions):
                raise ValueError(
                    f"at_{name} must equal the four current elements of "
                    f"transitions_at_{name}."
                )
        if (self.closing_window is None) != (
            self.closing.located_by is SunriseLocating.WINDOW_NEXT
        ):
            raise ValueError(
                "closing_window must be None exactly when the closing is "
                "WINDOW_NEXT."
            )
        if (self.query_utc is None) != (self.layer16_at_instant is None):
            raise ValueError(
                "query_utc and layer16_at_instant are both set (containing "
                "form) or both None (date form)."
            )
        if self.query_utc is not None:
            _query, query_jd = utc_instant(self.query_utc)
            if not (
                self.opening.julian_day_ut <= query_jd < self.closing.julian_day_ut
            ):
                raise ValueError(
                    "the query instant must lie in [opening, closing) by Julian Day."
                )
        object.__setattr__(
            self, "cells_at_closing", MappingProxyType(dict(self.cells_at_closing))
        )


@dataclass(frozen=True)
class PanchangaDayUnavailable:
    """No Panchanga day for the date or the instant; neighbours are information.

    ``preceding_sunrise`` and ``following_sunrise`` are bounded by the walk:
    ``None`` means "not found within the walked range", not "does not exist".
    ``lone_sunrise`` and ``at_lone_sunrise`` are set for
    ``NO_VARA_DAY_AT_SUNRISE`` only; there is no vara, because Layer 16 gives
    none after a sunrise that no later sunrise follows.
    """

    civil_date: date | None
    query_utc: datetime | None
    location: PanchangaLocation
    timezone_id: str
    reason: DayUnavailableReason
    layer16_reasons: tuple[str, ...]
    layer16_at_instant: SunriseWindow | SunriseUnavailable | None
    preceding_sunrise: DaySunrise | None
    following_sunrise: DaySunrise | None
    lone_sunrise: DaySunrise | None
    at_lone_sunrise: InstantElements | None
    sunrise_convention: str


@dataclass(frozen=True)
class PanchangaDayAmbiguous:
    """The date carries several canonical sunrises; ``sunrise_ordinal`` chooses."""

    civil_date: date
    location: PanchangaLocation
    timezone_id: str
    candidates: tuple[DaySunrise, ...]
    sunrise_convention: str


# --- the walk (specification 4.1, 4.2) --------------------------------------------


@dataclass(frozen=True)
class _Located:
    """A new sunrise event: the window of the first walked anchor inside it."""

    anchor: datetime
    window: SunriseWindow
    canonical: bool


@dataclass(frozen=True)
class _Unavailable:
    """A stretch of anchors whose Layer 16 results share one reason."""

    anchor: datetime
    result: SunriseUnavailable


@dataclass(frozen=True)
class _Walk:
    """The entries of one walk, in anchor order, and what follows from them."""

    start: datetime
    end: datetime
    entries: tuple[_Located | _Unavailable, ...]
    located: tuple[_Located, ...]
    next_only: tuple[SunriseWindow, ...]


def _same_sunrise(first: float, second: float) -> bool:
    """Event identity of two Layer 16 sunrise floats (never an instant test)."""
    return abs(first - second) < SAME_SUNRISE_MAX_SEPARATION


def _anchors(start: datetime, end: datetime) -> tuple[datetime, ...]:
    """Every anchor in the closed range ``[start, end]``, in increasing order."""
    index = -((ANCHOR_EPOCH - start) // ANCHOR_STEP)
    anchors = []
    anchor = ANCHOR_EPOCH + index * ANCHOR_STEP
    while anchor <= end:
        anchors.append(anchor)
        index += 1
        anchor = ANCHOR_EPOCH + index * ANCHOR_STEP
    return tuple(anchors)


def _walk(
    start: datetime,
    end: datetime,
    latitude: float,
    longitude: float,
    timezone_id: str,
    rise_after: RiseAfter,
) -> _Walk:
    """Ask Layer 16 at every anchor of ``[start, end]`` and keep the entries.

    A window whose ``previous`` is the same event as the last located sunrise
    is a later locating of it and is discarded (its float may differ by
    milliseconds at high latitude); an unavailability repeating the reason of
    the entry before it extends that entry.
    """
    entries: list[_Located | _Unavailable] = []
    last: _Located | None = None
    for position, anchor in enumerate(_anchors(start, end)):
        result = find_sunrise_window(
            anchor, latitude, longitude, timezone_id, rise_after=rise_after
        )
        if isinstance(result, SunriseWindow):
            sunrise = result.previous_julian_day_ut
            if last is not None:
                if _same_sunrise(sunrise, last.window.previous_julian_day_ut):
                    continue
                if not sunrise > last.window.previous_julian_day_ut:
                    raise DaySearchError(
                        f"the walk located the sunrise {sunrise!r} at anchor "
                        f"{anchor.isoformat()}, which is not later than the "
                        f"sunrise {last.window.previous_julian_day_ut!r} located "
                        f"before it at anchor {last.anchor.isoformat()}."
                    )
                if sunrise < (
                    last.window.next_julian_day_ut - SAME_SUNRISE_MAX_SEPARATION
                ):
                    raise DaySearchError(
                        f"the walk located the sunrise {sunrise!r} at anchor "
                        f"{anchor.isoformat()}, more than "
                        f"{SAME_SUNRISE_MAX_SEPARATION} day before the next "
                        f"sunrise {last.window.next_julian_day_ut!r} of the window "
                        f"located at anchor {last.anchor.isoformat()}: Layer 16 "
                        "skipped a sunrise."
                    )
            last = _Located(anchor=anchor, window=result, canonical=position > 0)
            entries.append(last)
        elif isinstance(result, SunriseUnavailable):
            previous_entry = entries[-1] if entries else None
            if (
                isinstance(previous_entry, _Unavailable)
                and previous_entry.result.reason == result.reason
            ):
                continue
            entries.append(_Unavailable(anchor=anchor, result=result))
        else:
            raise DaySearchError(
                f"find_sunrise_window returned {type(result).__name__} at anchor "
                f"{anchor.isoformat()}; a SunriseWindow or a SunriseUnavailable "
                "was expected."
            )

    if not entries:
        raise DaySearchError(
            f"the walk of [{start.isoformat()}, {end.isoformat()}] produced no "
            "entry at all."
        )

    located = tuple(entry for entry in entries if isinstance(entry, _Located))
    next_only = tuple(
        entry.window
        for entry in located
        if not any(
            _same_sunrise(
                entry.window.next_julian_day_ut, other.window.previous_julian_day_ut
            )
            for other in located
        )
    )
    return _Walk(
        start=start,
        end=end,
        entries=tuple(entries),
        located=located,
        next_only=next_only,
    )


def _day_sunrise(
    utc: datetime,
    julian_day: float,
    local: datetime,
    timezone_id: str,
    located_by: SunriseLocating,
) -> DaySunrise:
    """A reported sunrise, after the image check of specification 7.2."""
    _normalised, image = utc_instant(utc)
    if image != julian_day:
        raise DaySearchError(
            f"the datetime {utc.isoformat()} of the sunrise {julian_day!r} names "
            f"the Julian Day {image!r}: the image check of specification 7.2 "
            "failed, and no microsecond is moved to make it hold."
        )
    return DaySunrise(
        utc=utc,
        julian_day_ut=julian_day,
        local=local,
        timezone_id=timezone_id,
        located_by=located_by,
    )


def _previous_of(
    window: SunriseWindow, timezone_id: str, located_by: SunriseLocating
) -> DaySunrise:
    return _day_sunrise(
        window.previous_utc,
        window.previous_julian_day_ut,
        window.previous_local,
        timezone_id,
        located_by,
    )


def _next_of(window: SunriseWindow, timezone_id: str) -> DaySunrise:
    return _day_sunrise(
        window.next_utc,
        window.next_julian_day_ut,
        window.next_local,
        timezone_id,
        SunriseLocating.WINDOW_NEXT,
    )


def _seen_sunrises(walk: _Walk, timezone_id: str) -> tuple[DaySunrise, ...]:
    """Every sunrise the walk saw, in time order, each with its locating."""
    seen = []
    for entry in walk.located:
        located_by = (
            SunriseLocating.CANONICAL_ANCHOR
            if entry.canonical
            else SunriseLocating.FIRST_ANCHOR
        )
        seen.append(_previous_of(entry.window, timezone_id, located_by))
    for window in walk.next_only:
        seen.append(_next_of(window, timezone_id))
    return tuple(sorted(seen, key=_julian_day_of))


def _julian_day_of(sunrise: DaySunrise) -> float:
    return sunrise.julian_day_ut


def _layer16_reasons(walk: _Walk) -> tuple[str, ...]:
    """The distinct Layer 16 reasons the walk met, in walk order."""
    reasons: list[str] = []
    for entry in walk.entries:
        if isinstance(entry, _Unavailable) and entry.result.reason not in reasons:
            reasons.append(entry.result.reason)
    return tuple(reasons)


# --- selection (specification 4.3) -----------------------------------------------


@dataclass(frozen=True)
class _DateSelection:
    """The date walk and its canonical candidates, in time order."""

    civil_date: date
    walk: _Walk
    candidates: tuple[_Located, ...]


def _select_date(
    civil_date: date,
    latitude: float,
    longitude: float,
    timezone_id: str,
    rise_after: RiseAfter,
) -> _DateSelection:
    """The one date-selection helper both entry points use."""
    origin = datetime(
        civil_date.year, civil_date.month, civil_date.day, tzinfo=timezone.utc
    )
    walk = _walk(
        origin - WALK_BEFORE,
        origin + WALK_AFTER,
        latitude,
        longitude,
        timezone_id,
        rise_after,
    )
    candidates = tuple(
        entry
        for entry in walk.located
        if entry.canonical and entry.window.previous_local.date() == civil_date
    )
    return _DateSelection(civil_date=civil_date, walk=walk, candidates=candidates)


def _closing(
    opening: _Located, walk: _Walk, timezone_id: str
) -> tuple[DaySunrise, SunriseWindow | None]:
    """The closing sunrise of the day that ``opening`` opens, and its window."""
    window = opening.window
    later = [
        entry
        for entry in walk.located
        if entry.canonical
        and entry.window.previous_julian_day_ut > window.previous_julian_day_ut
    ]
    if later and _same_sunrise(
        later[0].window.previous_julian_day_ut, window.next_julian_day_ut
    ):
        following = later[0].window
        return (
            _previous_of(following, timezone_id, SunriseLocating.CANONICAL_ANCHOR),
            following,
        )
    return _next_of(window, timezone_id), None


def _ordinal_of(opening: _Located, selection: _DateSelection) -> int:
    """The opening's position among the date's candidates, by exact float."""
    for position, candidate in enumerate(selection.candidates):
        if (
            candidate.window.previous_julian_day_ut
            == opening.window.previous_julian_day_ut
        ):
            return position + 1
    raise DaySearchError(
        f"the opening sunrise {opening.window.previous_julian_day_ut!r} is not "
        f"among the canonical candidates of {selection.civil_date.isoformat()} "
        f"({[c.window.previous_julian_day_ut for c in selection.candidates]!r})."
    )


# --- elements and placement (specification 4.5, 4.6) -------------------------------


def _elements_match(
    elements: InstantElements, transitions: PanchangaTransitions
) -> bool:
    if tuple(transitions.kinds) != ALL_KINDS:
        return False
    neighbours = transitions.neighbours
    return (
        neighbours[TransitionKind.TITHI].current == elements.tithi
        and neighbours[TransitionKind.KARANA].current == elements.karana
        and neighbours[TransitionKind.NAKSHATRA].current == elements.nakshatra
        and neighbours[TransitionKind.YOGA].current == elements.yoga
    )


def _elements_at(
    moment: datetime, tolerance: timedelta, evaluate: Evaluate
) -> tuple[PanchangaTransitions, InstantElements]:
    """Layer 17's neighbours at an instant, and the cross-checked elements."""
    transitions = find_transitions(
        moment, kinds=ALL_KINDS, tolerance=tolerance, evaluate=evaluate
    )
    sun, moon = evaluate(moment)
    arc = elongation(sun, moon)
    elements = InstantElements(
        tithi=tithi_from_elongation(arc),
        karana=karana_from_elongation(arc),
        nakshatra=nakshatra_from_longitude(moon),
        yoga=yoga_from_sum(longitude_sum(sun, moon)),
        sun_sidereal_longitude=sun,
        moon_sidereal_longitude=moon,
    )
    if not _elements_match(elements, transitions):
        raise DaySearchError(
            f"at {moment.isoformat()} the elements classified from the evaluated "
            "longitudes differ from Layer 17's current elements at the same "
            "instant."
        )
    return transitions, elements


def _placement(
    transition: Transition,
    opening_utc: datetime,
    transitions_at_opening: PanchangaTransitions,
) -> DayPlacement:
    """Place a listed transition by its cell and the opening element's index."""
    neighbours = transitions_at_opening.neighbours[transition.kind]
    opening_index = neighbours.current.index

    if transition.before_utc >= opening_utc:
        return DayPlacement.WITHIN

    if (
        transition.before_utc < opening_utc <= transition.after_utc
        and transition.after.index == opening_index
    ):
        if not same_event(transition, neighbours.previous):
            raise DaySearchError(
                f"the {transition.kind.value} cell ({transition.before_utc.isoformat()}, "
                f"{transition.after_utc.isoformat()}] straddles the opening into its "
                "element but is not Layer 17's previous transition there."
            )
        return DayPlacement.STRADDLES_OPENING_REFLECTED

    if (
        transition.before_utc < opening_utc < transition.after_utc
        and transition.before.index == opening_index
    ):
        if not same_event(transition, neighbours.next):
            raise DaySearchError(
                f"the {transition.kind.value} cell ({transition.before_utc.isoformat()}, "
                f"{transition.after_utc.isoformat()}] straddles the opening out of its "
                "element but is not Layer 17's next transition there."
            )
        return DayPlacement.STRADDLES_OPENING_AFTER

    raise DaySearchError(
        f"the {transition.kind.value} cell ({transition.before_utc.isoformat()}, "
        f"{transition.after_utc.isoformat()}] with indices {transition.before.index} "
        f"-> {transition.after.index} cannot be placed against the opening "
        f"{opening_utc.isoformat()} whose element has index {opening_index}."
    )


def _build_day(
    *,
    civil_date: date,
    sunrise_ordinal: int,
    opening: _Located,
    closing: DaySunrise,
    closing_window: SunriseWindow | None,
    location: PanchangaLocation,
    timezone_id: str,
    tolerance: timedelta,
    evaluate: Evaluate,
    query_utc: datetime | None,
    layer16_at_instant: SunriseWindow | SunriseUnavailable | None,
) -> PanchangaDay:
    window = opening.window
    opening_sunrise = _previous_of(
        window, timezone_id, SunriseLocating.CANONICAL_ANCHOR
    )
    transitions_at_opening, at_opening = _elements_at(
        opening_sunrise.utc, tolerance, evaluate
    )
    transitions_at_closing, at_closing = _elements_at(
        closing.utc, tolerance, evaluate
    )
    listing = list_transitions(
        opening_sunrise.utc,
        closing.utc,
        kinds=ALL_KINDS,
        tolerance=tolerance,
        evaluate=evaluate,
    )
    placed = tuple(
        PlacedTransition(
            transition=transition,
            placement=_placement(
                transition, opening_sunrise.utc, transitions_at_opening
            ),
        )
        for transition in listing.transitions
    )
    cells_at_closing = {}
    for kind in ALL_KINDS:
        previous = transitions_at_closing.neighbours[kind].previous
        if previous.before_utc < closing.utc <= previous.after_utc:
            cells_at_closing[kind] = PlacedTransition(
                transition=previous, placement=DayPlacement.AT_OR_BEFORE_CLOSING
            )

    return PanchangaDay(
        civil_date=civil_date,
        sunrise_ordinal=sunrise_ordinal,
        location=location,
        timezone_id=timezone_id,
        opening=opening_sunrise,
        closing=closing,
        opening_window=window,
        closing_window=closing_window,
        vara=vara_from_sunrise(window),
        at_opening=at_opening,
        at_closing=at_closing,
        transitions_at_opening=transitions_at_opening,
        transitions_at_closing=transitions_at_closing,
        listing=listing,
        placed=placed,
        cells_at_closing=MappingProxyType(cells_at_closing),
        layer16_at_instant=layer16_at_instant,
        query_utc=query_utc,
        tolerance=tolerance,
        calculation_convention=CALCULATION_CONVENTION,
        sunrise_convention=SUNRISE_CONVENTION,
        search_convention=SEARCH_CONVENTION,
    )


# --- validation (specification 9; before any evaluation) ---------------------------


def _check_civil_date(civil_date: date) -> None:
    if isinstance(civil_date, datetime) or not isinstance(civil_date, date):
        raise DayRequestError(
            "civil_date must be a datetime.date (not a datetime); got "
            f"{type(civil_date).__name__} {civil_date!r}."
        )


def _check_ordinal(sunrise_ordinal: int | None) -> None:
    if sunrise_ordinal is None:
        return
    if (
        isinstance(sunrise_ordinal, bool)
        or not isinstance(sunrise_ordinal, int)
        or sunrise_ordinal < 1
    ):
        raise DayRequestError(
            f"sunrise_ordinal must be None or a positive int; got {sunrise_ordinal!r}."
        )


def _check_date_range(civil_date: date) -> None:
    if not SUPPORTED_DATE_START <= civil_date <= SUPPORTED_DATE_END:
        raise UnsupportedDateError(
            f"civil_date {civil_date.isoformat()} is outside the supported range "
            f"[{SUPPORTED_DATE_START.isoformat()}, {SUPPORTED_DATE_END.isoformat()}]."
        )


def _check_instant_range(moment: datetime) -> None:
    if not SUPPORTED_INSTANT_START <= moment <= SUPPORTED_INSTANT_END:
        raise UnsupportedInstantError(
            f"moment_utc {moment.isoformat()} is outside Layer 18's supported "
            f"range [{SUPPORTED_INSTANT_START.isoformat()}, "
            f"{SUPPORTED_INSTANT_END.isoformat()}]."
        )


def _check_tolerance(tolerance: timedelta) -> None:
    """Layer 17's rule, restated from its public ``ALLOWED_TOLERANCES`` (D9)."""
    if not (isinstance(tolerance, timedelta) and tolerance in ALLOWED_TOLERANCES):
        raise TransitionRequestError(
            f"tolerance must be a timedelta in ALLOWED_TOLERANCES; got {tolerance!r}."
        )


def _location(
    latitude: float, longitude: float, timezone_id: str
) -> PanchangaLocation:
    return PanchangaLocation(
        latitude=latitude,
        longitude=longitude,
        timezone_id=timezone_id,
        provenance=LocationProvenance.EXPLICIT,
    )


# --- unavailable results (specification 6) --------------------------------------------


def _date_unavailable(
    selection: _DateSelection,
    location: PanchangaLocation,
    timezone_id: str,
    tolerance: timedelta,
    evaluate: Evaluate,
) -> PanchangaDayUnavailable:
    civil_date = selection.civil_date
    walk = selection.walk
    seen = _seen_sunrises(walk, timezone_id)

    lone = [
        sunrise
        for sunrise in seen
        if sunrise.located_by is SunriseLocating.WINDOW_NEXT
        and sunrise.local.date() == civil_date
    ]
    lone_sunrise = lone[0] if lone else None
    at_lone_sunrise = None
    if lone_sunrise is not None:
        reason = DayUnavailableReason.NO_VARA_DAY_AT_SUNRISE
        _transitions, at_lone_sunrise = _elements_at(
            lone_sunrise.utc, tolerance, evaluate
        )
    elif any(isinstance(entry, _Unavailable) for entry in walk.entries):
        reason = DayUnavailableReason.SUNRISE_UNAVAILABLE
    else:
        reason = DayUnavailableReason.NO_SUNRISE_WITH_DATE

    before = [sunrise for sunrise in seen if sunrise.local.date() < civil_date]
    after = [
        sunrise
        for sunrise in seen
        if sunrise.located_by is SunriseLocating.CANONICAL_ANCHOR
        and sunrise.local.date() > civil_date
    ]
    return PanchangaDayUnavailable(
        civil_date=civil_date,
        query_utc=None,
        location=location,
        timezone_id=timezone_id,
        reason=reason,
        layer16_reasons=_layer16_reasons(walk),
        layer16_at_instant=None,
        preceding_sunrise=before[-1] if before else None,
        following_sunrise=after[0] if after else None,
        lone_sunrise=lone_sunrise,
        at_lone_sunrise=at_lone_sunrise,
        sunrise_convention=SUNRISE_CONVENTION,
    )


def _containing_unavailable(
    walk: _Walk,
    moment: datetime,
    instant: float,
    layer16_at_instant: SunriseWindow | SunriseUnavailable,
    location: PanchangaLocation,
    timezone_id: str,
) -> PanchangaDayUnavailable:
    seen = _seen_sunrises(walk, timezone_id)
    before = [sunrise for sunrise in seen if sunrise.julian_day_ut <= instant]
    after = [
        sunrise
        for sunrise in seen
        if sunrise.located_by is SunriseLocating.CANONICAL_ANCHOR
        and sunrise.julian_day_ut > instant
    ]
    return PanchangaDayUnavailable(
        civil_date=None,
        query_utc=moment,
        location=location,
        timezone_id=timezone_id,
        reason=DayUnavailableReason.SUNRISE_UNAVAILABLE,
        layer16_reasons=_layer16_reasons(walk),
        layer16_at_instant=layer16_at_instant,
        preceding_sunrise=before[-1] if before else None,
        following_sunrise=after[0] if after else None,
        lone_sunrise=None,
        at_lone_sunrise=None,
        sunrise_convention=SUNRISE_CONVENTION,
    )


# --- public functions (specification 10) ----------------------------------------------


def panchanga_day(
    civil_date: date,
    latitude: float,
    longitude: float,
    timezone_id: str,
    *,
    sunrise_ordinal: int | None = None,
    tolerance: timedelta = DEFAULT_TOLERANCE,
    rise_after: RiseAfter = default_rise_after,
    evaluate: Evaluate = default_evaluate,
) -> PanchangaDay | PanchangaDayUnavailable | PanchangaDayAmbiguous:
    """The Panchanga day opened by the sunrise carrying ``civil_date``.

    ``sunrise_ordinal=None`` requires the date to carry exactly one canonical
    sunrise; ``n`` selects the *n*-th in time order. A date carrying none is a
    ``PanchangaDayUnavailable`` and several without an ordinal a
    ``PanchangaDayAmbiguous`` -- results, not exceptions. ``rise_after`` and
    ``evaluate`` are Layer 16's and Layer 17's injection points, passed through.
    The ephemeris must already be open.
    """
    _check_civil_date(civil_date)
    _check_ordinal(sunrise_ordinal)
    _check_date_range(civil_date)
    validate_coordinates(latitude, longitude)
    resolve_zone(timezone_id)
    _check_tolerance(tolerance)
    location = _location(latitude, longitude, timezone_id)

    selection = _select_date(civil_date, latitude, longitude, timezone_id, rise_after)
    candidates = selection.candidates

    if not candidates:
        return _date_unavailable(selection, location, timezone_id, tolerance, evaluate)

    if sunrise_ordinal is None:
        if len(candidates) > 1:
            return PanchangaDayAmbiguous(
                civil_date=civil_date,
                location=location,
                timezone_id=timezone_id,
                candidates=tuple(
                    _previous_of(
                        entry.window, timezone_id, SunriseLocating.CANONICAL_ANCHOR
                    )
                    for entry in candidates
                ),
                sunrise_convention=SUNRISE_CONVENTION,
            )
        ordinal = 1
    else:
        if sunrise_ordinal > len(candidates):
            instants = ", ".join(
                entry.window.previous_utc.isoformat() for entry in candidates
            )
            raise DayRequestError(
                f"sunrise_ordinal {sunrise_ordinal} is larger than the "
                f"{len(candidates)} canonical sunrise(s) carrying "
                f"{civil_date.isoformat()} in {timezone_id}: [{instants}]."
            )
        ordinal = sunrise_ordinal

    opening = candidates[ordinal - 1]
    closing, closing_window = _closing(opening, selection.walk, timezone_id)
    return _build_day(
        civil_date=civil_date,
        sunrise_ordinal=ordinal,
        opening=opening,
        closing=closing,
        closing_window=closing_window,
        location=location,
        timezone_id=timezone_id,
        tolerance=tolerance,
        evaluate=evaluate,
        query_utc=None,
        layer16_at_instant=None,
    )


def panchanga_day_containing(
    moment_utc: datetime,
    latitude: float,
    longitude: float,
    timezone_id: str,
    *,
    tolerance: timedelta = DEFAULT_TOLERANCE,
    rise_after: RiseAfter = default_rise_after,
    evaluate: Evaluate = default_evaluate,
) -> PanchangaDay | PanchangaDayUnavailable:
    """The Panchanga day whose ``[opening, closing)`` contains the instant.

    Membership is Layer 16's, on the canonical Julian Day floats. The result's
    ``civil_date`` and ``sunrise_ordinal`` come from the date form's own
    enumeration, so ``panchanga_day(day.civil_date, ...,
    sunrise_ordinal=day.sunrise_ordinal)`` reproduces the same day. An instant
    that no canonical day contains is a ``PanchangaDayUnavailable``.
    """
    moment, instant = utc_instant(moment_utc)
    _check_instant_range(moment)
    validate_coordinates(latitude, longitude)
    resolve_zone(timezone_id)
    _check_tolerance(tolerance)
    location = _location(latitude, longitude, timezone_id)

    walk = _walk(
        moment - CONTAINING_WALK_BEFORE,
        moment + CONTAINING_WALK_AFTER,
        latitude,
        longitude,
        timezone_id,
        rise_after,
    )
    layer16_at_instant = find_sunrise_window(
        moment, latitude, longitude, timezone_id, rise_after=rise_after
    )

    openings = [
        entry
        for entry in walk.located
        if entry.canonical and entry.window.previous_julian_day_ut <= instant
    ]
    if openings:
        opening = openings[-1]
        closing, closing_window = _closing(opening, walk, timezone_id)
        if opening.window.previous_julian_day_ut <= instant < closing.julian_day_ut:
            civil_date = opening.window.previous_local.date()
            if not SUPPORTED_DATE_START <= civil_date <= SUPPORTED_DATE_END:
                raise DaySearchError(
                    f"the opening's civil date {civil_date.isoformat()} lies "
                    "outside the date range; the instant range should have "
                    "made that impossible."
                )
            selection = _select_date(
                civil_date, latitude, longitude, timezone_id, rise_after
            )
            return _build_day(
                civil_date=civil_date,
                sunrise_ordinal=_ordinal_of(opening, selection),
                opening=opening,
                closing=closing,
                closing_window=closing_window,
                location=location,
                timezone_id=timezone_id,
                tolerance=tolerance,
                evaluate=evaluate,
                query_utc=moment,
                layer16_at_instant=layer16_at_instant,
            )

    return _containing_unavailable(
        walk, moment, instant, layer16_at_instant, location, timezone_id
    )
