"""Layer 16, part 1: the four angular elements of the panchanga.

Pure arithmetic on longitudes. Nothing here opens an ephemeris, reads a clock
or knows what a time zone is: given two sidereal longitudes it produces the
tithi, the nitya yoga, the karana and -- by handing the Moon straight to the
FROZEN Layer 7 classifier -- the nakshatra. The fifth element, the vara, is not
here, because it is not a function of a longitude at all; it is decided by a
sunrise and lives in :mod:`vedic_chart.panchanga.sunrise`.

The definitions are the standard nirayana ones (specification section 2.1):

* tithi   -- the elongation ``E = (moon - sun) mod 360`` in 12 deg steps, 30 of them;
* karana  -- the same elongation in 6 deg steps, 60 half-tithis per lunar month;
* yoga    -- the sum ``Y = (sun + moon) mod 360`` in 360/27 deg steps, 27 of them;
* nakshatra -- the Moon's own sidereal longitude, classified by Layer 7.

Both inputs are Lahiri sidereal longitudes (FROZEN sections 4.3 and 5). The
ayanamsha is neither changed nor introduced here: tithi and karana depend only
on the *difference* of the two longitudes and would be the same in the tropical
frame, but the yoga depends on their *sum* and is meaningful only sidereally,
so the whole module is stated in the sidereal frame and the two agree.

Every index is taken as a plain floor of the unrounded value, in exactly the
shape FROZEN rule 8 uses for the nakshatra, so the float behaviour is the same
one the engine has already frozen: intervals are half-open ``[start, end)``
(rule 10), nothing is rounded (rule 11) and nothing is nudged across a boundary
(rule 12). The index assertions are guards, not clamps -- a clamp would move a
value across a boundary, which rule 12 forbids.

Boundaries at multiples of 12 deg and 6 deg are exactly representable as
floats and classify exactly. The yoga boundaries are at 40k/3 deg and share the
FROZEN "float fact": only a k that is a multiple of 3 is exactly representable,
and for the rest no float equals the boundary, so the value simply falls where
it falls. That is asserted in the tests rather than worked around.

**Two different quantities, not one (specification section 4.2).** Each element
carries a raw offset and a progress fraction, and they are deliberately
computed differently.

``degrees_in_<element>`` is the **raw offset** ``value - index * span``: the
FROZEN Layer 7 shape, inherited unchanged. Within one or two units in the last
place of a non-representable yoga or nakshatra boundary the index -- floored
from ``value * N / 360.0``, which rounds -- and this offset -- which does
not -- can disagree, and the offset is then a few 1e-14 degrees *negative*.
That is the frozen engine's documented float fact; ``classify`` does exactly
the same at exactly the same values, and rule 12 forbids nudging or clamping it
back, so it is carried as computed and pinned by a test.

``angular_fraction`` is the **progress fraction** ``scaled - index``, where
``scaled = value * N / 360.0`` is the very double the index was floored from.
Being the fractional part of that same double it lies in ``[0, 1)`` *exactly*,
at every input, with no epsilon and no clamping: subtracting an integer from a
non-negative double of larger magnitude is exact in IEEE arithmetic. It is
consistent with the index by construction, which is the point -- inside the ULP
band it is 0.0 while the raw offset is the negative one, and the two disagree
only there. The runtime check on it is a **check, not a clamp**: it raises
rather than moving the value, and it should be unreachable.

Ambiguities in the specification, decided here and recorded rather than left
implicit:

* ``TITHI_NAMES`` is a 30-tuple in slot order, not a 15-tuple plus two special
  cases. Specification section 2.2 gives the fourteen repeated names once and
  then "Purnima (15) / Amavasya (30)"; storing the resolved 30 makes ``name``
  a lookup instead of a branch, and the two full-moon/new-moon names sit at the
  indices they actually occupy.
* ``KARANA_FIXED_NAMES`` is in **slot** order -- Kimstughna (0), Shakuni (57),
  Chatushpada (58), Naga (59) -- not in the order section 2.2's prose lists
  them, for the same reason.
* A ``key`` is the element's name lower-cased with spaces replaced by
  underscores. A tithi name repeats between the two pakshas, so a tithi key is
  prefixed with its paksha (``shukla_pratipada``, ``krishna_amavasya``): keys
  are meant to be stable identifiers, and two different tithis sharing one
  would defeat that.
"""

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

from vedic_chart.vedic.divisions import (
    NAKSHATRA_SPAN,
    DivisionalPlacement,
    classify,
    normalize_longitude,
)
from vedic_chart.vedic.grahas import Graha

#: The exact string every result carries, so a stored panchanga says what it
#: was computed under without the reader having to find this module.
CALCULATION_CONVENTION = (
    "Lahiri sidereal longitudes (Swiss Ephemeris SIDM_LAHIRI, true equinox of "
    "date); tithi = floor(E/12 deg) and karana = floor(E/6 deg) of the "
    "elongation E = (moon - sun) mod 360; nitya yoga = floor(Y/(360/27) deg) "
    "of Y = (sun + moon) mod 360; nakshatra = the frozen Layer 7 "
    "classification of the Moon's sidereal longitude; half-open intervals, no "
    "rounding, no epsilon"
)

TITHI_COUNT = 30
KARANA_COUNT = 60
YOGA_COUNT = 27
NAKSHATRA_COUNT = 27
VARA_COUNT = 7

TITHI_SPAN = 360.0 / 30.0
KARANA_SPAN = 360.0 / 60.0

#: The yoga divides its circle into 27 exactly as the nakshatra divides the
#: zodiac, so the FROZEN span is reused rather than restated. Writing
#: ``360.0 / 27.0`` again here would be a second definition of the same double,
#: and the two could only ever drift apart, never usefully differ.
YOGA_SPAN = NAKSHATRA_SPAN

#: The fourteen names shared by both pakshas, in order.
_COMMON_TITHI_NAMES: tuple[str, ...] = (
    "Pratipada",
    "Dwitiya",
    "Tritiya",
    "Chaturthi",
    "Panchami",
    "Shashthi",
    "Saptami",
    "Ashtami",
    "Navami",
    "Dashami",
    "Ekadashi",
    "Dwadashi",
    "Trayodashi",
    "Chaturdashi",
)

#: All thirty tithis in slot order. The fifteenth of the bright fortnight is
#: Purnima and the fifteenth of the dark one is Amavasya; the other twenty-eight
#: repeat the common names.
TITHI_NAMES: tuple[str, ...] = (
    _COMMON_TITHI_NAMES + ("Purnima",) + _COMMON_TITHI_NAMES + ("Amavasya",)
)

YOGA_NAMES: tuple[str, ...] = (
    "Vishkambha",
    "Priti",
    "Ayushman",
    "Saubhagya",
    "Shobhana",
    "Atiganda",
    "Sukarma",
    "Dhriti",
    "Shula",
    "Ganda",
    "Vriddhi",
    "Dhruva",
    "Vyaghata",
    "Harshana",
    "Vajra",
    "Siddhi",
    "Vyatipata",
    "Variyan",
    "Parigha",
    "Shiva",
    "Siddha",
    "Sadhya",
    "Shubha",
    "Shukla",
    "Brahma",
    "Indra",
    "Vaidhriti",
)

#: The seven chara (movable) karanas, which cycle eight times through the 56
#: half-tithis between the fixed slots.
KARANA_REPEATING_NAMES: tuple[str, ...] = (
    "Bava",
    "Balava",
    "Kaulava",
    "Taitila",
    "Garaja",
    "Vanija",
    "Vishti",
)

#: The four sthira (fixed) karanas, in the order of the slots they occupy:
#: 0, 57, 58, 59.
KARANA_FIXED_NAMES: tuple[str, ...] = (
    "Kimstughna",
    "Shakuni",
    "Chatushpada",
    "Naga",
)

VARA_NAMES: tuple[str, ...] = (
    "Ravivara",
    "Somavara",
    "Mangalavara",
    "Budhavara",
    "Guruvara",
    "Shukravara",
    "Shanivara",
)

#: The English weekday of each vara, Sunday first. Not part of the package
#: surface -- it exists so the sunrise module can name a civil date in the same
#: order the varas are numbered in.
VARA_ENGLISH_WEEKDAYS: tuple[str, ...] = (
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
)

#: The lord of each vara, as the FROZEN Layer 7 ``Graha``. No new planet
#: vocabulary is invented for this layer.
VARA_LORDS: tuple[Graha, ...] = (
    Graha.SUN,
    Graha.MOON,
    Graha.MARS,
    Graha.MERCURY,
    Graha.JUPITER,
    Graha.VENUS,
    Graha.SATURN,
)


class Paksha(Enum):
    """The bright and dark fortnights of the lunar month."""

    SHUKLA = "shukla"
    KRISHNA = "krishna"


class KaranaKind(Enum):
    """Whether a karana occupies a fixed slot or cycles through the month."""

    FIXED = "fixed"
    REPEATING = "repeating"


class TithiHalf(Enum):
    """Which half of its tithi a karana is."""

    FIRST = "first"
    SECOND = "second"


class _KaranaSlot(NamedTuple):
    """One of the sixty half-tithi slots of a lunar month."""

    name: str
    kind: KaranaKind
    cycle_position: int | None


def _build_karana_table() -> tuple[_KaranaSlot, ...]:
    """The sixty slots of specification section 2.2, built from the rule.

    Written out as the rule rather than as a literal list so that the check in
    the specification -- 1 fixed + 56 repeating + 3 fixed = 60, slot 1 is Bava,
    slot 56 is Vishti -- is a property of the code and not of a transcription.
    """
    slots = [
        _KaranaSlot(KARANA_FIXED_NAMES[0], KaranaKind.FIXED, None),
    ]
    for index in range(1, 57):
        position = (index - 1) % len(KARANA_REPEATING_NAMES)
        slots.append(
            _KaranaSlot(
                KARANA_REPEATING_NAMES[position],
                KaranaKind.REPEATING,
                position + 1,
            )
        )
    for name in KARANA_FIXED_NAMES[1:]:
        slots.append(_KaranaSlot(name, KaranaKind.FIXED, None))

    assert len(slots) == KARANA_COUNT, len(slots)
    return tuple(slots)


KARANA_SLOTS: tuple[_KaranaSlot, ...] = _build_karana_table()


def _key(name: str) -> str:
    """A stable lowercase ASCII identifier for a transliterated name."""
    return name.lower().replace(" ", "_")


@dataclass(frozen=True)
class Tithi:
    """One of the thirty lunar days, as an arc rather than as a duration.

    ``angular_fraction`` is how far through its 12 deg of elongation the Moon
    is -- a fraction of *arc*, not of time. A tithi is not of uniform length, so
    this says nothing about when it began or when it will end. Transition times
    are out of scope (specification section 1).
    """

    index: int
    number: int
    key: str
    name: str
    paksha: Paksha
    number_in_paksha: int
    elongation: float
    degrees_in_tithi: float
    angular_fraction: float


@dataclass(frozen=True)
class Nakshatra:
    """The Moon's nakshatra and pada, carrying the FROZEN placement itself.

    ``placement`` is the Layer 7 ``DivisionalPlacement`` object, not a copy of
    its numbers. On the from-chart path it is the very object the chart already
    holds, so agreement with the chart is by identity and cannot drift. The flat
    fields beside it are a convenience for callers that want the panchanga's own
    shape; they are read off that placement and never recomputed.
    """

    index: int
    number: int
    key: str
    name: str
    pada: int
    degrees_in_nakshatra: float
    degrees_in_pada: float
    angular_fraction: float
    placement: DivisionalPlacement


@dataclass(frozen=True)
class NityaYoga:
    """One of the twenty-seven yogas of the sum of the two longitudes.

    This is the *nitya* yoga of the panchanga -- a division of ``sun + moon`` --
    and has nothing to do with the planetary yogas of chart interpretation,
    which this engine does not compute.
    """

    index: int
    number: int
    key: str
    name: str
    sum_longitude: float
    degrees_in_yoga: float
    angular_fraction: float


@dataclass(frozen=True)
class Karana:
    """One half-tithi, with the tithi it halves and its place in the month."""

    index: int
    number: int
    key: str
    name: str
    kind: KaranaKind
    cycle_position: int | None
    tithi_index: int
    half: TithiHalf
    degrees_in_karana: float
    angular_fraction: float


def elongation(sun_longitude: float, moon_longitude: float) -> float:
    """``(moon - sun) mod 360``: the arc the Moon has gained on the Sun.

    Normalized through the FROZEN ``normalize_longitude`` so that this layer
    wraps in exactly one way, the way the rest of the engine already does.
    """
    return normalize_longitude(moon_longitude - sun_longitude)


def longitude_sum(sun_longitude: float, moon_longitude: float) -> float:
    """``(sun + moon) mod 360``: the quantity the nitya yoga divides."""
    return normalize_longitude(sun_longitude + moon_longitude)


def _progress_fraction(scaled: float, index: int) -> float:
    """The fractional part of the double the index was floored from.

    Specification 4.2. ``scaled`` is ``value * N / 360.0`` and ``index`` is
    ``int(scaled)``, so this is exactly ``scaled - floor(scaled)`` for a
    non-negative ``scaled``: an IEEE-exact subtraction that lands in [0, 1) by
    construction, consistent with the index whatever the raw offset does.

    The check is a check, not a clamp. It should be unreachable -- reaching it
    would mean the index was not floored from this double -- and it raises
    rather than moving the value, because rule 12 forbids nudging a value to
    make a comparison come out a particular way.
    """
    fraction = scaled - index

    if not 0.0 <= fraction < 1.0:
        raise RuntimeError(
            f"progress fraction {fraction!r} is outside [0, 1) for scaled "
            f"value {scaled!r} and index {index!r}: the index cannot have been "
            "floored from this double."
        )

    return fraction


def tithi_from_elongation(elongation_degrees: float) -> Tithi:
    """Classify an elongation already in [0, 360) into its tithi."""
    scaled = elongation_degrees * TITHI_COUNT / 360.0
    index = int(scaled)
    assert 0 <= index <= TITHI_COUNT - 1, (elongation_degrees, index)

    degrees_in = elongation_degrees - index * TITHI_SPAN
    paksha = Paksha.SHUKLA if index < 15 else Paksha.KRISHNA

    return Tithi(
        index=index,
        number=index + 1,
        key=f"{paksha.value}_{_key(TITHI_NAMES[index])}",
        name=TITHI_NAMES[index],
        paksha=paksha,
        number_in_paksha=index % 15 + 1,
        elongation=elongation_degrees,
        degrees_in_tithi=degrees_in,
        angular_fraction=_progress_fraction(scaled, index),
    )


def karana_from_elongation(elongation_degrees: float) -> Karana:
    """Classify an elongation already in [0, 360) into its karana slot.

    The slot's identity comes from ``KARANA_SLOTS``; this function only finds
    the index and asserts the relation the specification states between the two
    divisions of the same arc, ``karana_index == 2 * tithi_index + half``.
    """
    scaled = elongation_degrees * KARANA_COUNT / 360.0
    index = int(scaled)
    assert 0 <= index <= KARANA_COUNT - 1, (elongation_degrees, index)

    tithi_index = int(elongation_degrees * TITHI_COUNT / 360.0)
    half_index = index - 2 * tithi_index
    assert half_index in (0, 1), (elongation_degrees, index, tithi_index)

    slot = KARANA_SLOTS[index]
    degrees_in = elongation_degrees - index * KARANA_SPAN

    return Karana(
        index=index,
        number=index + 1,
        key=_key(slot.name),
        name=slot.name,
        kind=slot.kind,
        cycle_position=slot.cycle_position,
        tithi_index=tithi_index,
        half=TithiHalf.FIRST if half_index == 0 else TithiHalf.SECOND,
        degrees_in_karana=degrees_in,
        angular_fraction=_progress_fraction(scaled, index),
    )


def yoga_from_sum(sum_degrees: float) -> NityaYoga:
    """Classify a sum already in [0, 360) into its nitya yoga."""
    scaled = sum_degrees * YOGA_COUNT / 360.0
    index = int(scaled)
    assert 0 <= index <= YOGA_COUNT - 1, (sum_degrees, index)

    degrees_in = sum_degrees - index * YOGA_SPAN

    return NityaYoga(
        index=index,
        number=index + 1,
        key=_key(YOGA_NAMES[index]),
        name=YOGA_NAMES[index],
        sum_longitude=sum_degrees,
        degrees_in_yoga=degrees_in,
        angular_fraction=_progress_fraction(scaled, index),
    )


def nakshatra_from_placement(
    placement: DivisionalPlacement, moon_longitude: float
) -> Nakshatra:
    """Wrap a FROZEN placement as a panchanga nakshatra, classifying nothing.

    Every named field is read off the placement, including the two raw degree
    offsets, and the placement object itself is carried through by identity --
    on the from-chart path it is the very object the chart holds, so agreement
    with the chart is not a comparison but the same object.

    The one thing computed here is the progress fraction, and it needs the
    longitude because specification 4.2 defines it as the fractional part of
    ``scaled = normalize(longitude) * 27 / 360.0`` -- the same double the FROZEN
    rule 8 floors to get the index. Dividing the placement's raw offset by the
    span instead would inherit the offset's ULP-band negativity, which is
    exactly what the progress fraction exists not to have.

    Taking that scaled value is **not** a second classification: ``int(scaled)``
    is required to equal the index the placement already carries, and a mismatch
    is a ``RuntimeError``. It is the same formula on the same double, so it
    cannot differ for any longitude the engine produced; if it ever did, the two
    definitions of the nakshatra would have parted company and that is an
    internal contradiction, not a caller's mistake.
    """
    scaled = normalize_longitude(moon_longitude) * NAKSHATRA_COUNT / 360.0
    index = int(scaled)

    if index != placement.nakshatra_index:
        raise RuntimeError(
            f"the placement records nakshatra index "
            f"{placement.nakshatra_index} but the frozen rule-8 arithmetic on "
            f"longitude {moon_longitude!r} gives {index}. The two are the same "
            "formula on the same double, so this is an internal contradiction."
        )

    return Nakshatra(
        index=placement.nakshatra_index,
        number=placement.nakshatra_number,
        key=_key(placement.nakshatra_name),
        name=placement.nakshatra_name,
        pada=placement.pada,
        degrees_in_nakshatra=placement.degrees_in_nakshatra,
        degrees_in_pada=placement.degrees_in_pada,
        angular_fraction=_progress_fraction(scaled, placement.nakshatra_index),
        placement=placement,
    )


def nakshatra_from_longitude(moon_longitude: float) -> Nakshatra:
    """Classify the Moon with the FROZEN ``classify`` and wrap the result."""
    return nakshatra_from_placement(classify(moon_longitude), moon_longitude)


def vara_index_from_weekday(weekday: int) -> int:
    """Convert Python's Monday-0 weekday into the vara's Sunday-0 index.

    ``date.weekday()`` counts from Monday and the varas count from Ravivara
    (Sunday), so the two differ by one position. This is the whole of the
    conversion and it is given a name because getting it wrong is silent: every
    vara would still be a valid vara, just the wrong one.
    """
    assert 0 <= weekday <= VARA_COUNT - 1, weekday
    return (weekday + 1) % VARA_COUNT
