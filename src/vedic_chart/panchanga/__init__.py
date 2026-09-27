"""Layer 16: the panchanga of an instant and a place.

Three modules. ``elements`` is pure arithmetic on two sidereal longitudes --
tithi, nitya yoga, karana, and the nakshatra by way of the FROZEN Layer 7
classifier. ``sunrise`` is the adapter that brackets an instant between two
geometric Hindu sunrises and names the vara from the local civil date of the
earlier one; it is the only module here that knows what a time zone is.
``compute`` composes the five elements into one immutable ``Panchanga``, either
for an explicit instant and place or for a chart the engine has already built.

The scope is the five classical elements and nothing else. Festivals, the
lunar month and year (masa, adhika, samvatsara), muhurta, Rahu Kalam and the
other kalas, hora, the transition times of a tithi or a nakshatra, sunset,
moonrise, and any CLI, HTTP or viewer surface are out of scope by decision;
see ``docs/LAYER16_PANCHANGA_SPEC.md`` section 1.

Layer 17 adds a fourth module, ``transitions``, without changing the three
above: when the tithi, karana, nakshatra and nitya yoga current at an instant
began and end, and every such change in a bounded interval, found by
evaluating Layer 16's own classifiers on an absolute tolerance grid (see
``docs/LAYER17_PANCHANGA_TRANSITIONS_SPEC.md``). Its names are re-exported
here beside Layer 16's.

Layer 18 adds a fifth module, ``daily``, again without changing the four
above: the Panchanga day of a local civil date (``panchanga_day``) or of an
instant (``panchanga_day_containing``), from the geometric Hindu sunrise that
carries the date to the next one. It composes Layer 16's sunrise windows and
Layer 17's transitions and adds only the choice of the two sunrises -- each
located from a fixed global anchor grid, so consecutive days share one sunrise
bit for bit -- and the placement of each transition relative to them (see
``docs/LAYER18_DAILY_PANCHANGA_SPEC.md``). A date that carries no sunrise, or
several, is a typed result rather than an exception or a guess.

Nothing in Layers 1 to 15 imports this package: it is a consumer of the engine,
never a part of it, and the frozen calculation specification is untouched. The
one change it required below itself is additive -- Layer 5 gained the single
accessor ``calc_sunrise_hindu``, which is still the only way ``swisseph`` is
reached from anywhere.

Ephemeris lifecycle is the caller's, as for ``assemble_chart``::

    from vedic_chart.astronomy.positions import ephemeris_session
    from vedic_chart.panchanga import calculate_panchanga

    with ephemeris_session("ephe"):
        p = calculate_panchanga(moment, 31.32556, 75.57917, "Asia/Kolkata")
"""

from .compute import (
    LocationProvenance,
    LongitudeSource,
    Panchanga,
    PanchangaLocation,
    calculate_panchanga,
    panchanga_from_chart,
)
from .daily import (
    ANCHOR_EPOCH,
    ANCHOR_STEP,
    CONTAINING_WALK_AFTER,
    CONTAINING_WALK_BEFORE,
    MAX_OFFSET_HOURS,
    SAME_SUNRISE_MAX_SEPARATION,
    SUPPORTED_DATE_END,
    SUPPORTED_DATE_START,
    SUPPORTED_INSTANT_END,
    SUPPORTED_INSTANT_START,
    WALK_AFTER,
    WALK_BEFORE,
    DayPlacement,
    DayRequestError,
    DaySearchError,
    DaySunrise,
    DayUnavailableReason,
    InstantElements,
    PanchangaDay,
    PanchangaDayAmbiguous,
    PanchangaDayUnavailable,
    PlacedTransition,
    SunriseLocating,
    UnsupportedDateError,
    panchanga_day,
    panchanga_day_containing,
)
from .elements import (
    CALCULATION_CONVENTION,
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
from .sunrise import (
    SUNRISE_CONVENTION,
    InvalidTimezoneError,
    SunriseUnavailable,
    SunriseWindow,
    Vara,
    find_sunrise_window,
)
from .transitions import (
    ALLOWED_TOLERANCES,
    ALL_KINDS,
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
    find_transitions,
    list_transitions,
    local_transition,
    next_transition,
    previous_transition,
    same_event,
)

__all__ = [
    "ALLOWED_TOLERANCES",
    "ALL_KINDS",
    "ANCHOR_EPOCH",
    "ANCHOR_STEP",
    "CALCULATION_CONVENTION",
    "CONTAINING_WALK_AFTER",
    "CONTAINING_WALK_BEFORE",
    "DEFAULT_TOLERANCE",
    "DayPlacement",
    "DayRequestError",
    "DaySearchError",
    "DaySunrise",
    "DayUnavailableReason",
    "EventId",
    "InstantElements",
    "IntervalError",
    "InvalidTimezoneError",
    "KARANA_FIXED_NAMES",
    "KARANA_REPEATING_NAMES",
    "Karana",
    "KaranaKind",
    "LocalTransition",
    "LocationProvenance",
    "LongitudeSource",
    "MAX_INTERVAL",
    "MAX_OFFSET_HOURS",
    "MAX_REACH",
    "Nakshatra",
    "Neighbours",
    "NityaYoga",
    "Paksha",
    "Panchanga",
    "PanchangaDay",
    "PanchangaDayAmbiguous",
    "PanchangaDayUnavailable",
    "PanchangaLocation",
    "PanchangaTransitions",
    "PlacedTransition",
    "Quantity",
    "RATE_MAX",
    "RATE_MIN",
    "SAFE_EVAL_END",
    "SAFE_EVAL_START",
    "SAME_SUNRISE_MAX_SEPARATION",
    "SEARCH_CONVENTION",
    "SUNRISE_CONVENTION",
    "SUPPORTED_DATE_END",
    "SUPPORTED_DATE_START",
    "SUPPORTED_END",
    "SUPPORTED_INSTANT_END",
    "SUPPORTED_INSTANT_START",
    "SUPPORTED_START",
    "SunriseLocating",
    "SunriseUnavailable",
    "SunriseWindow",
    "TITHI_NAMES",
    "Tithi",
    "TithiHalf",
    "Transition",
    "TransitionKind",
    "TransitionList",
    "TransitionRequestError",
    "TransitionSearchError",
    "TransitionUncertainty",
    "UnsupportedDateError",
    "UnsupportedInstantError",
    "VARA_LORDS",
    "VARA_NAMES",
    "Vara",
    "WALK_AFTER",
    "WALK_BEFORE",
    "YOGA_NAMES",
    "calculate_panchanga",
    "find_sunrise_window",
    "find_transitions",
    "list_transitions",
    "local_transition",
    "next_transition",
    "panchanga_day",
    "panchanga_day_containing",
    "panchanga_from_chart",
    "previous_transition",
    "same_event",
]
