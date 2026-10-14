"""Chart builders shared by the Layer 10 renderer tests.

Two kinds of chart live here. **Synthetic** charts are assembled straight from
the frozen dataclasses, exactly as ``tests/test_d1_representation.py`` does, so
crowding, boundary degrees, retrograde marking and caption text can be exercised
on plain numbers with no ephemeris in the loop. ``BirthChart`` validates that
every graha is present and placed in a house in 1..12, and nothing more, so a
deliberately impossible sky -- all nine grahas in one rashi, Ketu not opposite
Rahu -- is a legitimate input for a *renderer* test: the renderer must draw what
the representation says, not what the sky allows.

**Real** charts run the ordinary pipeline. Jalandhar 1995-03-21 06:45 IST is the
frozen reference birth, resolved through the offline fixture geocoder. Bharatpur
2003-12-09 04:00 IST is the audit's external-comparison case and is pinned to
its recorded coordinates 27.21 / 77.29 through a fixed resolver: the fixture
database does contain a "Bharatpur", but it is a different settlement in Punjab
at 30.66 / 76.66, and the case is defined by its coordinates.

Charts are built once and cached, because an ephemeris run per parametrised case
would dominate the suite's runtime.
"""

from dataclasses import replace
from datetime import date, datetime, time, timezone
from pathlib import Path

from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.chart.assemble import assemble_chart
from vedic_chart.chart.model import BirthChart
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.lagna.ascendant import Lagna
from vedic_chart.location.model import ResolvedLocation
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.render import NorthIndianOptions, SouthIndianOptions
from vedic_chart.representation.d1 import D1Chart, build_d1_chart
from vedic_chart.vedic.divisions import classify
from vedic_chart.vedic.grahas import Graha, GrahaPosition

REPO_ROOT = Path(__file__).resolve().parent.parent
EPHE_DIR = str(REPO_ROOT / "ephe")
FIXTURE_DB = REPO_ROOT / "tests" / "fixtures" / "geodata_fixture.sqlite"
GOLDEN_DIR = REPO_ROOT / "tests" / "fixtures" / "render"
SOUTH_GOLDEN_DIR = REPO_ROOT / "tests" / "fixtures" / "render_south"
RENDER_PACKAGE = REPO_ROOT / "src" / "vedic_chart" / "render"
PACKAGE_FILES = (
    "__init__.py",
    "north_indian.py",
    "north_indian_geometry.py",
    "overlay.py",
    "south_indian.py",
    "south_indian_geometry.py",
)

RASHI_COUNT = 12
TEST_AYANAMSA = 23.5

#: The audit's external-comparison birth, pinned to its recorded coordinates.
BHARATPUR = ResolvedLocation(
    "Bharatpur, Rajasthan, India", 27.21, 77.29, "Asia/Kolkata"
)

LONG_NAME_NO_SPACES = (
    "Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch"
    "superiorupperlowermiddlesettlementdistrictprovinceregionsubward"
)
LONG_NAME_WITH_SPACES = (
    "Saint Mary Church in the Hollow of the White Hazel near the Rapid "
    "Whirlpool of the Church of Saint Tysilio of the Red Cave, Upper "
    "Settlement District, Anglesey"
)
ESCAPING_NAME = 'Ampersand & Angle < Quote " Place'
INJECTION_NAME = 'url(x) href <script>alert(1)</script> onload=1 &'
LONG_TIMEZONE = "America/Argentina/ComodRivadavia"


class FixedResolver:
    """Protocol-conformant resolver over one explicit location."""

    def __init__(self, location: ResolvedLocation) -> None:
        self._location = location

    def resolve(self, place_query: str) -> ResolvedLocation:
        return self._location


# --- synthetic charts ------------------------------------------------------

#: One graha per rashi except Ketu, which shares Moon's rashi. Mars, Rahu and
#: Ketu move backwards, so the default chart exercises the marker as well.
DEFAULT_LONGITUDES = {
    Graha.SUN: 5.0,
    Graha.MOON: 35.5,
    Graha.MERCURY: 65.25,
    Graha.VENUS: 95.75,
    Graha.MARS: 125.5,
    Graha.JUPITER: 155.25,
    Graha.SATURN: 185.5,
    Graha.RAHU: 215.25,
    Graha.KETU: 35.25,
}
DEFAULT_SPEEDS = {
    Graha.SUN: 0.99,
    Graha.MOON: 13.2,
    Graha.MERCURY: 1.4,
    Graha.VENUS: 1.2,
    Graha.MARS: -0.21,
    Graha.JUPITER: 0.13,
    Graha.SATURN: 0.06,
    Graha.RAHU: -0.053,
    Graha.KETU: -0.053,
}

DEFAULT_LOCATION = ResolvedLocation("Test Place, Testland", 0.0, 0.0, "UTC")


def synthetic_birth_chart(
    lagna_rashi_index: int = 0,
    *,
    longitudes=None,
    speeds=None,
    location: ResolvedLocation = DEFAULT_LOCATION,
    request: BirthChartRequest = None,
) -> BirthChart:
    """Build a ``BirthChart`` from frozen dataclasses -- no ephemeris."""
    longitudes = dict(DEFAULT_LONGITUDES if longitudes is None else longitudes)
    speeds = dict(DEFAULT_SPEEDS if speeds is None else speeds)

    grahas = {}
    for graha in Graha:
        longitude = longitudes[graha]
        speed = speeds[graha]
        grahas[graha] = GrahaPosition(
            sidereal_longitude=longitude,
            speed_longitude=speed,
            is_retrograde=speed < 0.0,
            placement=classify(longitude),
        )

    lagna_longitude = lagna_rashi_index * 30.0 + 13.788209
    lagna = Lagna(
        tropical_longitude=(lagna_longitude + TEST_AYANAMSA) % 360.0,
        sidereal_longitude=lagna_longitude,
        ayanamsa=TEST_AYANAMSA,
        placement=classify(lagna_longitude),
    )

    houses = {
        graha: (position.placement.rashi_index - lagna_rashi_index)
        % RASHI_COUNT
        + 1
        for graha, position in grahas.items()
    }

    if request is None:
        request = BirthChartRequest(date(2000, 1, 1), time(12, 0), "test")

    return BirthChart(
        request=request,
        location=location,
        moment_utc=datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc),
        julian_day_ut=2451545.0,
        ayanamsa=TEST_AYANAMSA,
        lagna=lagna,
        grahas=grahas,
        houses=houses,
    )


def synthetic_d1(lagna_rashi_index: int = 0, **kwargs) -> D1Chart:
    return build_d1_chart(synthetic_birth_chart(lagna_rashi_index, **kwargs))


def all_in_rashi_longitudes(rashi_index: int) -> dict:
    """Every graha inside one rashi, two degrees apart."""
    base = rashi_index * 30.0
    return {
        graha: base + 1.0 + 2.0 * index
        for index, graha in enumerate(Graha)
    }


def nine_in_house_d1(house_number: int) -> D1Chart:
    """All nine grahas crowded into one house, the Lagna chosen to suit."""
    rashi_index = 0
    lagna_rashi_index = (rashi_index - (house_number - 1)) % RASHI_COUNT
    return synthetic_d1(
        lagna_rashi_index,
        longitudes=all_in_rashi_longitudes(rashi_index),
    )


def count_in_house_d1(house_number: int, count: int) -> D1Chart:
    """Exactly ``count`` grahas in one house, the rest one per other rashi.

    The side-triangle suite of section 10.B2 needs a house holding a chosen
    number of occupants and nothing accidental anywhere else, so the leftover
    grahas are dealt out to consecutive *other* rashis -- never the target
    one -- and no second house is ever crowded.
    """
    if not 0 <= count <= 9:
        raise ValueError(f"count must be 0..9; got {count!r}.")
    rashi_index = 0
    lagna_rashi_index = (rashi_index - (house_number - 1)) % RASHI_COUNT
    order = list(Graha)
    longitudes = {}
    for index, graha in enumerate(order[:count]):
        longitudes[graha] = rashi_index * 30.0 + 1.0 + 2.0 * index
    for offset, graha in enumerate(order[count:]):
        other = (rashi_index + 1 + offset) % RASHI_COUNT
        longitudes[graha] = other * 30.0 + 1.0
    return synthetic_d1(lagna_rashi_index, longitudes=longitudes)


def split_overflow_d1() -> D1Chart:
    """Five grahas in house 2 and four in house 3: two overflowed houses."""
    longitudes = {}
    for index, graha in enumerate(
        (Graha.SUN, Graha.MOON, Graha.MERCURY, Graha.VENUS, Graha.MARS)
    ):
        longitudes[graha] = 31.0 + 2.0 * index
    for index, graha in enumerate(
        (Graha.JUPITER, Graha.SATURN, Graha.RAHU, Graha.KETU)
    ):
        longitudes[graha] = 61.0 + 2.0 * index
    return synthetic_d1(0, longitudes=longitudes)


def boundary_degrees_d1() -> D1Chart:
    """Occupants pinned to the display boundaries of section 10.A."""
    longitudes = dict(DEFAULT_LONGITUDES)
    longitudes[Graha.SUN] = 29.999999          # -> 29 deg 59'
    longitudes[Graha.MOON] = 30.000001         # ->  0 deg 00'
    longitudes[Graha.MERCURY] = 60.0 + 12.5    # -> 12 deg 30'
    return synthetic_d1(0, longitudes=longitudes)


def all_retrograde_d1() -> D1Chart:
    speeds = {graha: -1.0 for graha in Graha}
    return synthetic_d1(0, speeds=speeds)


def long_name_d1(name: str) -> D1Chart:
    location = ResolvedLocation(name, 12.5, 77.5, LONG_TIMEZONE)
    request = BirthChartRequest(date(1980, 7, 4), time(23, 5, 7, 250000), name)
    return synthetic_d1(4, location=location, request=request)


def nine_in_house_long_caption_d1(house_number: int, name: str) -> D1Chart:
    """Nine grahas in one house *and* a long caption, in one drawing.

    The two crowding pressures of section 10.D meet here: the cell overflows to
    its floor size and gains a legend block, while the caption band wraps a long
    place name and a long timezone id above it.
    """
    rashi_index = 0
    lagna_rashi_index = (rashi_index - (house_number - 1)) % RASHI_COUNT
    location = ResolvedLocation(name, 12.5, 77.5, LONG_TIMEZONE)
    request = BirthChartRequest(date(1980, 7, 4), time(23, 5, 7, 250000), name)
    return synthetic_d1(
        lagna_rashi_index,
        longitudes=all_in_rashi_longitudes(rashi_index),
        location=location,
        request=request,
    )


def with_meta(chart: D1Chart, **changes) -> D1Chart:
    """The same chart with edited ``D1Meta`` descriptors.

    Used to hand the renderer a convention it does not have a label for, which
    the engine itself can never produce; ``D1Chart.__post_init__`` re-runs and
    still validates the rearrangement, so the copy is a legitimate chart.
    """
    return replace(chart, meta=replace(chart.meta, **changes))


def named_d1(name: str) -> D1Chart:
    location = ResolvedLocation(name, 12.5, 77.5, "Asia/Kolkata")
    request = BirthChartRequest(date(1980, 7, 4), time(23, 5, 7), name)
    return synthetic_d1(2, location=location, request=request)


# --- real charts -----------------------------------------------------------


def jalandhar_d1() -> D1Chart:
    request = BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query="Jalandhar"
    )
    with ephemeris_session(EPHE_DIR):
        with OfflineLocationResolver(FIXTURE_DB) as resolver:
            return build_d1_chart(assemble_chart(request, resolver))


def bharatpur_d1() -> D1Chart:
    request = BirthChartRequest.from_components(
        2003, 12, 9, 4, 0, place_query="Bharatpur"
    )
    with ephemeris_session(EPHE_DIR):
        return build_d1_chart(assemble_chart(request, FixedResolver(BHARATPUR)))


# --- the shared case registry ---------------------------------------------

DEFAULT_OPTIONS = NorthIndianOptions()

CASES = {
    "jalandhar": (jalandhar_d1, DEFAULT_OPTIONS),
    "jalandhar_caption": (jalandhar_d1, NorthIndianOptions(caption=True)),
    "jalandhar_no_degrees": (
        jalandhar_d1, NorthIndianOptions(show_degrees=False),
    ),
    "bharatpur": (bharatpur_d1, DEFAULT_OPTIONS),
    "bharatpur_caption": (bharatpur_d1, NorthIndianOptions(caption=True)),
    "boundary_degrees": (boundary_degrees_d1, DEFAULT_OPTIONS),
    "nodes_unmarked": (lambda: synthetic_d1(0), DEFAULT_OPTIONS),
    "nodes_marked": (
        lambda: synthetic_d1(0), NorthIndianOptions(mark_node_retrograde=True),
    ),
    "nine_house1": (lambda: nine_in_house_d1(1), DEFAULT_OPTIONS),
    "nine_house2": (lambda: nine_in_house_d1(2), DEFAULT_OPTIONS),
    "nine_house3": (lambda: nine_in_house_d1(3), DEFAULT_OPTIONS),
    "nine_house1_no_degrees": (
        lambda: nine_in_house_d1(1), NorthIndianOptions(show_degrees=False),
    ),
    "two_overflow": (split_overflow_d1, DEFAULT_OPTIONS),
    "all_retrograde": (all_retrograde_d1, DEFAULT_OPTIONS),
    "all_retrograde_nodes_marked": (
        all_retrograde_d1, NorthIndianOptions(mark_node_retrograde=True),
    ),
    "long_name_no_spaces": (
        lambda: long_name_d1(LONG_NAME_NO_SPACES),
        NorthIndianOptions(caption=True),
    ),
    "long_name_with_spaces": (
        lambda: long_name_d1(LONG_NAME_WITH_SPACES),
        NorthIndianOptions(caption=True),
    ),
    "escaping_name": (
        lambda: named_d1(ESCAPING_NAME), NorthIndianOptions(caption=True),
    ),
    "injection_name": (
        lambda: named_d1(INJECTION_NAME), NorthIndianOptions(caption=True),
    ),
}
CASES.update(
    {
        f"lagna_{index:02d}": (
            (lambda captured=index: synthetic_d1(captured)), DEFAULT_OPTIONS,
        )
        for index in range(RASHI_COUNT)
    }
)

CASE_NAMES = tuple(sorted(CASES))

_CHART_CACHE: dict[str, D1Chart] = {}


def case_chart(name: str) -> D1Chart:
    """The ``D1Chart`` for a registered case, built once and cached."""
    if name not in _CHART_CACHE:
        _CHART_CACHE[name] = CASES[name][0]()
    return _CHART_CACHE[name]


def case_options(name: str) -> NorthIndianOptions:
    return CASES[name][1]


# --- Layer 19: the South Indian registry ------------------------------------


def signs_d1(lagna_rashi_index: int, counts: dict) -> D1Chart:
    """Grahas dealt into chosen signs, the Lagna in a chosen sign.

    ``counts`` maps a rashi index to how many grahas it holds; grahas are
    dealt in enum order to the signs in the order given, two degrees apart.
    Any leftover graha goes, one per sign, to consecutive signs that are
    neither listed nor the Lagna's, so no other cell is crowded by accident.
    """
    order = list(Graha)
    if sum(counts.values()) > len(order):
        raise ValueError(f"more than nine grahas requested: {counts!r}.")
    longitudes = {}
    position = 0
    for rashi_index, count in counts.items():
        for slot in range(count):
            longitudes[order[position]] = rashi_index * 30.0 + 1.0 + 2.0 * slot
            position += 1
    spare = [
        index
        for index in range(RASHI_COUNT)
        if index not in counts and index != lagna_rashi_index
    ]
    for graha, rashi_index in zip(order[position:], spare):
        longitudes[graha] = rashi_index * 30.0 + 1.0
    return synthetic_d1(lagna_rashi_index, longitudes=longitudes)


#: The crowding cases of section 9.1: ``(lagna_rashi_index, counts)``.
SOUTH_CROWD_LAYOUTS = {
    "one_sign_all_nine": (2, {7: 9}),
    "lagna_sign_all_nine": (0, {0: 9}),
    "six_exact": (3, {3: 5}),
    "seven_first_overflow": (3, {3: 6}),
    "two_signs_crowded": (9, {9: 6, 1: 3}),
}


def south_options(options: NorthIndianOptions) -> SouthIndianOptions:
    """The South Indian option set with the same four display choices."""
    return SouthIndianOptions(
        show_degrees=options.show_degrees,
        mark_node_retrograde=options.mark_node_retrograde,
        caption=options.caption,
        width=options.width,
    )


SOUTH_DEFAULT_OPTIONS = SouthIndianOptions()

SOUTH_CASES = {
    name: (builder, south_options(options))
    for name, (builder, options) in CASES.items()
}
for _crowd_name, (_lagna, _counts) in SOUTH_CROWD_LAYOUTS.items():
    _builder = (
        lambda lagna=_lagna, counts=_counts: signs_d1(lagna, counts)
    )
    SOUTH_CASES[_crowd_name] = (_builder, SOUTH_DEFAULT_OPTIONS)
    SOUTH_CASES[f"{_crowd_name}_no_degrees"] = (
        _builder, SouthIndianOptions(show_degrees=False),
    )

SOUTH_CASE_NAMES = tuple(sorted(SOUTH_CASES))

_SOUTH_CHART_CACHE: dict[str, D1Chart] = {}


def south_case_chart(name: str) -> D1Chart:
    """The ``D1Chart`` of a South Indian case, shared with ``CASES``."""
    if name in CASES:
        return case_chart(name)
    if name not in _SOUTH_CHART_CACHE:
        _SOUTH_CHART_CACHE[name] = SOUTH_CASES[name][0]()
    return _SOUTH_CHART_CACHE[name]


def south_case_options(name: str) -> SouthIndianOptions:
    return SOUTH_CASES[name][1]


# --- Layer 20: the overlay cases -------------------------------------------

#: Section 15 B and 10.7: the numbers of grahas placed in one house.
OVERLAY_FILLS = (0, 1, 2, 3, 7)


def house_fill_d1(house_number: int, count: int) -> D1Chart:
    """A chart with exactly ``count`` grahas in one house (synthetic).

    ``count == 0`` empties the house by crowding all nine grahas into
    another one (house 7 when the target is house 1, house 1 otherwise), as
    the section 15 probe did; house 1 still holds the Lagna's own row.
    """
    if count == 0:
        return nine_in_house_d1(7 if house_number == 1 else 1)
    return count_in_house_d1(house_number, count)


def transit_jalandhar_d1() -> D1Chart:
    """The Layer 20 worked example's second instant (section 5.7).

    An ordinary chart for 2026-10-08 14:30:00 local time at the fixture
    record for Jalandhar (09:00 UTC), through the same pipeline functions as
    :func:`jalandhar_d1`; its own Lagna (Makara) differs from the reference
    chart's (Meena), which is what the overlay must ignore.
    """
    request = BirthChartRequest.from_components(
        2026, 10, 8, 14, 30, 0, place_query="Jalandhar"
    )
    with ephemeris_session(EPHE_DIR):
        with OfflineLocationResolver(FIXTURE_DB) as resolver:
            return build_d1_chart(assemble_chart(request, resolver))


OVERLAY_GOLDEN_DIR = REPO_ROOT / "tests" / "fixtures" / "overlay"

_OVERLAY_CACHE: dict = {}


def overlay_chart(name: str) -> D1Chart:
    """Layer 20 charts by name, built once: ``transit_jalandhar`` and
    ``fill_<house>_<count>``, plus every name of ``CASES`` and
    ``SOUTH_CASES`` (``jalandhar``, ``lagna_00`` ...)."""
    if name in CASES:
        return case_chart(name)
    if name in SOUTH_CASES:
        return south_case_chart(name)
    if name not in _OVERLAY_CACHE:
        if name == "transit_jalandhar":
            chart = transit_jalandhar_d1()
        elif name.startswith("fill_"):
            _, house, count = name.split("_")
            chart = house_fill_d1(int(house), int(count))
        else:
            raise KeyError(name)
        _OVERLAY_CACHE[name] = chart
    return _OVERLAY_CACHE[name]
