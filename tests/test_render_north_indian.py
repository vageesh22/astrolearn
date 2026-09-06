"""Tests for Layer 10: the North Indian D1 SVG renderer.

Everything asserted here is asserted against the ``D1Chart`` that was handed to
the renderer, never against independently computed astrology: the renderer's
job is to draw the representation faithfully, and a test that recomputed a
longitude would be testing the engine again through a keyhole.

The safety tests are deliberately **structural**. They parse the document and
walk elements and attributes rather than grepping for scary substrings, because
a place name may legitimately contain ``<script>`` or ``url(`` and must survive
as escaped, inert character data. The same test renders exactly such a name and
insists that it round-trips.
"""

import ast
import xml.etree.ElementTree as ET

import pytest

import render_helpers as helpers
from render_helpers import (
    CASE_NAMES,
    ESCAPING_NAME,
    INJECTION_NAME,
    LONG_NAME_NO_SPACES,
    LONG_NAME_WITH_SPACES,
    LONG_TIMEZONE,
    PACKAGE_FILES,
    RENDER_PACKAGE,
    case_chart,
    case_options,
    with_meta,
)
from vedic_chart.render import NorthIndianOptions, render_north_indian_svg
from vedic_chart.render.north_indian import (
    COMPACT_AYANAMSHA_LABELS,
    HOUSE_SYSTEM_LABELS,
    MARKER_LAGNA_LINE,
    MARKER_RETRO_DEFAULT,
    MARKER_RETRO_NODES,
    NODE_LABELS,
    TITLE_PLAIN,
)
from vedic_chart.render.north_indian_geometry import character_budget
from vedic_chart.vedic.grahas import Graha

NODES = (Graha.RAHU, Graha.KETU)
FULL_NAMES = {
    Graha.SUN: "Sun",
    Graha.MOON: "Moon",
    Graha.MERCURY: "Mercury",
    Graha.VENUS: "Venus",
    Graha.MARS: "Mars",
    Graha.JUPITER: "Jupiter",
    Graha.SATURN: "Saturn",
    Graha.RAHU: "Rahu",
    Graha.KETU: "Ketu",
}
CAPTION_BUDGET = character_budget(24.0)
LEGEND_BUDGET = character_budget(22.0)


# --- small parsing helpers -------------------------------------------------


def local_name(name: str) -> str:
    return name.split("}")[-1]


def parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def children_of_class(group, css_class):
    return [child for child in group if child.get("class") == css_class]


def groups_of_class(root, css_class):
    return [el for el in root.iter() if el.get("class") == css_class]


def house_groups(root):
    return {
        int(group.get("data-house")): group
        for group in groups_of_class(root, "house")
    }


def legend_blocks(root):
    return {
        int(group.get("data-house")): group
        for group in groups_of_class(root, "legend-house")
    }


def degree_text(dms) -> str:
    return f"{dms.degrees}°{dms.minutes:02d}′"


def expects_underline(chart, graha, options) -> bool:
    placement = chart.grahas[graha]
    if not placement.is_retrograde:
        return False
    if graha in NODES and not options.mark_node_retrograde:
        return False
    return True


def rendered(name: str) -> str:
    return render_north_indian_svg(case_chart(name), case_options(name))


# --- A. semantic correctness ----------------------------------------------


def check_entry_elements(chart, options, group, keys):
    """Every entry in a group has the right degree text and marker."""
    degrees = children_of_class(group, "deg")
    if options.show_degrees:
        assert [element.get("data-graha") for element in degrees] == keys
        for element in degrees:
            key = element.get("data-graha")
            if key == "lagna":
                expected = degree_text(chart.lagna.dms(0))
            else:
                expected = degree_text(chart.grahas[Graha(key)].dms(0))
            assert element.text == expected
    else:
        assert degrees == []

    marked = {
        element.get("data-graha")
        for element in children_of_class(group, "retro")
    }
    expected_marked = {
        key
        for key in keys
        if key != "lagna" and expects_underline(chart, Graha(key), options)
    }
    assert marked == expected_marked


@pytest.mark.parametrize("name", CASE_NAMES)
def test_semantics_match_the_representation(name):
    chart = case_chart(name)
    options = case_options(name)
    root = parse(render_north_indian_svg(chart, options))

    houses = house_groups(root)
    blocks = legend_blocks(root)
    assert sorted(houses) == list(range(1, 13))

    for house in chart.houses:
        group = houses[house.number]
        assert int(group.get("data-rashi")) == house.rashi_number

        numerals = children_of_class(group, "numeral")
        assert len(numerals) == 1
        assert numerals[0].text == str(house.rashi_number)

        keys = [
            element.get("data-graha")
            for element in children_of_class(group, "abbr")
        ]
        expected = [graha.value for graha in house.occupants]

        if house.number == 1:
            assert keys[:1] == ["lagna"]
            shown = keys[1:]
        else:
            shown = keys
        assert "lagna" not in shown

        overflow = children_of_class(group, "overflow")
        assert shown == expected[: len(shown)]
        if overflow:
            assert len(overflow) == 1
            assert overflow[0].text == f"+{len(expected) - len(shown)}"
            block = blocks[house.number]
            assert [
                element.get("data-graha")
                for element in children_of_class(block, "abbr")
            ] == expected
            check_entry_elements(chart, options, block, expected)
        else:
            assert shown == expected
            assert house.number not in blocks

        check_entry_elements(chart, options, group, keys)

    # No house other than 1 -- and no legend block -- carries a Lagna entry.
    lagna_entries = [
        element
        for element in root.iter()
        if element.get("data-graha") == "lagna"
    ]
    assert {element.get("class") for element in lagna_entries} <= {"abbr", "deg"}
    assert len(children_of_class(houses[1], "abbr")) >= 1
    for number, group in houses.items():
        keys = [e.get("data-graha") for e in children_of_class(group, "abbr")]
        assert keys.count("lagna") == (1 if number == 1 else 0)
    for block in blocks.values():
        keys = [e.get("data-graha") for e in children_of_class(block, "abbr")]
        assert "lagna" not in keys

    # Only overflowed houses get a legend block.
    assert set(blocks) <= set(houses)


@pytest.mark.parametrize("name", CASE_NAMES)
def test_no_graha_is_drawn_in_two_house_cells(name):
    root = parse(rendered(name))

    seen = {}
    for number, group in house_groups(root).items():
        keys = [e.get("data-graha") for e in children_of_class(group, "abbr")]
        assert len(keys) == len(set(keys)), f"house {number} repeats an entry"
        for key in keys:
            assert key not in seen, f"{key} appears in houses {seen[key]}, {number}"
            seen[key] = number


@pytest.mark.parametrize("name", CASE_NAMES)
def test_description_reads_the_whole_chart(name):
    chart = case_chart(name)
    root = parse(rendered(name))

    description = root.find("{http://www.w3.org/2000/svg}desc").text
    assert (
        f"Lagna in rashi {chart.lagna.rashi_number} "
        f"({chart.lagna.rashi_name}) at {degree_text(chart.lagna.dms(0))}."
        in description
    )
    for house in chart.houses:
        heading = (
            f"House {house.number}, rashi {house.rashi_number} "
            f"({house.rashi_name}): "
        )
        assert heading in description
        if not house.occupants:
            assert heading + "empty." in description
    for graha, placement in chart.grahas.items():
        word = "retrograde" if placement.is_retrograde else "direct"
        assert (
            f"{FULL_NAMES[graha]} {degree_text(placement.dms(0))}, {word}"
            in description
        )


@pytest.mark.parametrize("name", CASE_NAMES)
def test_marker_legend_is_always_present(name):
    options = case_options(name)
    root = parse(rendered(name))

    lines = [
        element.text for element in groups_of_class(root, "legend-marker")
    ]
    expected_second = (
        MARKER_RETRO_NODES
        if options.mark_node_retrograde
        else MARKER_RETRO_DEFAULT
    )
    assert lines == [MARKER_LAGNA_LINE, expected_second]
    assert all(len(line) <= LEGEND_BUDGET for line in lines)


@pytest.mark.parametrize(
    "name,house,expected_cell,expected_overflow",
    [
        ("nine_house1", 1, ["As", "Su", "Mo", "Me", "Ve", "Ma"], "+4"),
        ("nine_house2", 2, ["Su", "Mo"], "+7"),
        ("nine_house3", 3, ["Su", "Mo"], "+7"),
    ],
)
def test_nine_graha_cells_match_the_worked_examples(
    name, house, expected_cell, expected_overflow
):
    """Section 6's worked examples, character for character."""
    root = parse(rendered(name))
    group = house_groups(root)[house]

    assert [e.text for e in children_of_class(group, "abbr")] == expected_cell
    assert [
        e.text for e in children_of_class(group, "overflow")
    ] == [expected_overflow]
    block = legend_blocks(root)[house]
    assert [e.text for e in children_of_class(block, "abbr")] == [
        "Su", "Mo", "Me", "Ve", "Ma", "Ju", "Sa", "Ra", "Ke",
    ]


def test_stacked_side_entries_share_an_x_and_underline_the_abbreviation_only():
    """Section 4's stacked construction, read back out of the document.

    ``all_retrograde`` puts one retrograde graha in each of houses 3 and 5, so
    the two-row entry and its marker are both exercised in a side triangle.
    """
    root = parse(rendered("all_retrograde"))
    houses = house_groups(root)

    assert [n for n, g in houses.items() if g.get("data-layout") == "stacked"] == [
        3, 5, 9, 11,
    ]
    assert [n for n, g in houses.items() if g.get("data-layout") == "inline"] == [
        1, 2, 4, 6, 7, 8, 10, 12,
    ]

    stacked_entries = 0
    underlines = 0
    for number in (3, 5, 9, 11):
        group = houses[number]
        abbrs = children_of_class(group, "abbr")
        degrees = children_of_class(group, "deg")
        retros = children_of_class(group, "retro")
        assert len(degrees) == len(abbrs)

        by_key = {}
        for abbr, degree in zip(abbrs, degrees):
            key = abbr.get("data-graha")
            assert degree.get("data-graha") == key
            font = float(abbr.get("font-size"))
            # Same x, one 1.45 f row lower -- not side by side.
            assert abbr.get("x") == degree.get("x")
            assert float(degree.get("y")) - float(abbr.get("y")) == pytest.approx(
                1.45 * font, abs=0.01
            )
            by_key[key] = (abbr, degree, font)
            stacked_entries += 1

        for line in retros:
            abbr, degree, font = by_key[line.get("data-graha")]
            y = float(line.get("y1"))
            # The marker sits 0.22 f under the abbreviation baseline, and its
            # lower edge stays clear of the degree row's cap height 0.70 f
            # below that baseline.
            assert y == pytest.approx(
                float(abbr.get("y")) + 0.22 * font, abs=0.01
            )
            assert y + 0.04 * font < float(degree.get("y")) - 0.75 * font
            assert line.get("x1") == abbr.get("x")
            assert float(line.get("x2")) == pytest.approx(
                float(abbr.get("x")) + 1.45 * font, abs=0.01
            )
            underlines += 1

    assert stacked_entries == 2
    assert underlines == 2


def test_two_overflowed_houses_get_two_legend_headings():
    root = parse(rendered("two_overflow"))

    headings = [e.text for e in groups_of_class(root, "legend-heading")]
    assert headings == [
        "House 2 — complete list:",
        "House 3 — complete list:",
    ]
    assert sorted(legend_blocks(root)) == [2, 3]


@pytest.mark.parametrize(
    "graha,expected",
    [
        (Graha.SUN, "29°59′"),
        (Graha.MOON, "0°00′"),
        (Graha.MERCURY, "12°30′"),
    ],
)
def test_boundary_degrees_are_truncated_not_rounded(graha, expected):
    chart = case_chart("boundary_degrees")
    root = parse(rendered("boundary_degrees"))

    texts = [
        element.text
        for element in root.iter()
        if element.get("class") == "deg"
        and element.get("data-graha") == graha.value
    ]
    assert texts == [expected]
    assert degree_text(chart.grahas[graha].dms(0)) == expected


@pytest.mark.parametrize("lagna_index", range(12))
def test_every_lagna_rashi_rotates_the_numerals(lagna_index):
    name = f"lagna_{lagna_index:02d}"
    chart = case_chart(name)
    root = parse(rendered(name))

    numerals = {
        int(group.get("data-house")): children_of_class(group, "numeral")[0].text
        for group in groups_of_class(root, "house")
    }
    assert numerals == {
        house.number: str(house.rashi_number) for house in chart.houses
    }
    assert numerals[1] == str(chart.lagna.rashi_number)


def test_nodes_are_marked_only_when_asked():
    plain = parse(rendered("nodes_unmarked"))
    marked = parse(rendered("nodes_marked"))

    def marked_keys(root):
        return {
            element.get("data-graha")
            for element in groups_of_class(root, "retro")
        }

    assert marked_keys(plain) == {"mars"}
    assert marked_keys(marked) == {"mars", "rahu", "ketu"}


def test_every_graha_retrograde_underlines_all_seven_planets():
    plain = parse(rendered("all_retrograde"))
    marked = parse(rendered("all_retrograde_nodes_marked"))

    planets = {
        graha.value for graha in Graha if graha not in NODES
    }
    assert {
        e.get("data-graha") for e in groups_of_class(plain, "retro")
    } == planets
    assert {
        e.get("data-graha") for e in groups_of_class(marked, "retro")
    } == planets | {"rahu", "ketu"}


# --- A. captions -----------------------------------------------------------


def caption_lines(root):
    return [
        element.text for element in groups_of_class(root, "caption-line")
    ]


def test_caption_off_emits_no_birth_metadata_anywhere():
    chart = case_chart("jalandhar")
    svg = rendered("jalandhar")
    root = parse(svg)

    assert groups_of_class(root, "caption") == []
    meta = chart.meta
    forbidden = (
        meta.request.birth_date.isoformat(),
        "06:45",
        meta.location.canonical_name,
        "Jalandhar",
        meta.location.timezone_id,
        repr(meta.julian_day_ut),
        str(int(meta.julian_day_ut)),
        repr(meta.ayanamsa),
        f"{meta.ayanamsa:.4f}",
        meta.ayanamsha,
        "Lahiri",
        str(meta.location.latitude),
        str(meta.location.longitude),
    )
    for needle in forbidden:
        assert needle not in svg, f"caption-off output leaks {needle!r}"
    assert root.find("{http://www.w3.org/2000/svg}title").text == TITLE_PLAIN


def test_caption_on_shows_the_three_lines_and_the_place_in_the_title():
    chart = case_chart("jalandhar_caption")
    root = parse(rendered("jalandhar_caption"))
    meta = chart.meta

    lines = caption_lines(root)
    assert lines
    assert all(len(line) <= CAPTION_BUDGET for line in lines)
    joined = " ".join(lines)
    assert joined.startswith(
        f"{meta.request.birth_date.isoformat()} 06:45 "
        f"{meta.location.timezone_id}"
    )
    assert meta.location.canonical_name in joined
    assert lines[-1] == "Lahiri (true equinox) · Whole Sign · Mean Node"
    assert "Mean Node" in joined
    assert (
        root.find("{http://www.w3.org/2000/svg}title").text
        == f"{TITLE_PLAIN} — {meta.location.canonical_name}"
    )


def test_caption_line_three_is_derived_from_the_layer_nine_descriptors():
    """The visible line is compact; nothing about it is hardcoded."""
    chart = case_chart("jalandhar_caption")
    meta = chart.meta
    root = parse(rendered("jalandhar_caption"))

    expected = (
        f"{COMPACT_AYANAMSHA_LABELS[meta.ayanamsha]} · "
        f"{HOUSE_SYSTEM_LABELS[meta.house_system]} · {NODE_LABELS[meta.node]}"
    )
    assert expected == "Lahiri (true equinox) · Whole Sign · Mean Node"
    assert caption_lines(root)[-1] == expected
    assert len(expected) <= CAPTION_BUDGET
    # The compact form drops the synonym alone: ayanamsha and equinox survive.
    assert "Chitrapaksha" not in expected
    assert meta.ayanamsha not in " ".join(caption_lines(root))


def test_the_description_carries_the_full_ayanamsha_descriptor():
    """The accessible caption is the unabbreviated one."""
    chart = case_chart("jalandhar_caption")
    root = parse(rendered("jalandhar_caption"))

    description = root.find("{http://www.w3.org/2000/svg}desc").text
    assert (
        "Lahiri (Chitrapaksha), true equinox · Whole Sign houses · Mean Node"
        in description
    )
    assert chart.meta.ayanamsha in description
    assert description.startswith(
        f"{chart.meta.request.birth_date.isoformat()} 06:45 "
    )


@pytest.mark.parametrize(
    "field,value",
    [("house_system", "equal"), ("node", "true")],
)
def test_an_unsupported_convention_is_refused_before_any_output(field, value):
    """A label is never guessed; and the refusal precedes the document."""
    chart = with_meta(case_chart("jalandhar"), **{field: value})

    with pytest.raises(ValueError) as error:
        render_north_indian_svg(chart, NorthIndianOptions(caption=True))
    message = str(error.value)
    assert field in message
    assert repr(value) in message


@pytest.mark.parametrize(
    "field,value",
    [("house_system", "equal"), ("node", "true")],
)
def test_an_unsupported_convention_is_irrelevant_without_a_caption(field, value):
    """With no caption the descriptors are never read, so nothing raises."""
    chart = with_meta(case_chart("jalandhar"), **{field: value})

    svg = render_north_indian_svg(chart, NorthIndianOptions(caption=False))
    check_structural_safety(svg)
    assert value not in svg
    assert parse(svg).find("{http://www.w3.org/2000/svg}title").text == (
        TITLE_PLAIN
    )


def test_an_unknown_ayanamsha_descriptor_is_shown_verbatim():
    """Not in the compact table means shown as it is, never relabelled."""
    chart = with_meta(case_chart("jalandhar"), ayanamsha="Raman")
    root = parse(
        render_north_indian_svg(chart, NorthIndianOptions(caption=True))
    )

    assert caption_lines(root)[-1] == "Raman · Whole Sign · Mean Node"
    assert (
        "Raman · Whole Sign houses · Mean Node"
        in root.find("{http://www.w3.org/2000/svg}desc").text
    )


def test_a_descriptor_containing_an_ampersand_is_escaped():
    descriptor = "Lahiri & Raman, true equinox"
    chart = with_meta(case_chart("jalandhar"), ayanamsha=descriptor)
    svg = render_north_indian_svg(chart, NorthIndianOptions(caption=True))
    check_structural_safety(svg)
    root = parse(svg)

    assert "&amp;" in svg
    assert caption_lines(root)[-1] == f"{descriptor} · Whole Sign · Mean Node"
    assert descriptor in root.find("{http://www.w3.org/2000/svg}desc").text


def test_a_long_unspaced_place_name_is_hard_split_and_nothing_is_lost():
    root = parse(rendered("long_name_no_spaces"))

    lines = caption_lines(root)
    assert all(len(line) <= CAPTION_BUDGET for line in lines)
    assert LONG_NAME_NO_SPACES in "".join(lines)
    assert len(LONG_NAME_NO_SPACES) >= 120
    # The hard split cuts at exactly the budget until the tail is short enough.
    name_lines = [
        line for line in lines if line and line in LONG_NAME_NO_SPACES
    ]
    assert "".join(name_lines) == LONG_NAME_NO_SPACES
    assert LONG_TIMEZONE in " ".join(lines)


def test_a_long_spaced_place_name_wraps_greedily_without_loss():
    root = parse(rendered("long_name_with_spaces"))

    lines = caption_lines(root)
    assert all(len(line) <= CAPTION_BUDGET for line in lines)
    assert LONG_NAME_WITH_SPACES.split() == [
        token for line in lines for token in line.split()
    ][3 : 3 + len(LONG_NAME_WITH_SPACES.split())]


def test_special_characters_in_a_place_name_are_escaped_and_round_trip():
    svg = rendered("escaping_name")
    root = parse(svg)

    assert " ".join(caption_lines(root)) .startswith(
        "1980-07-04 23:05:07 Asia/Kolkata"
    )
    assert ESCAPING_NAME in " ".join(caption_lines(root))
    assert "&amp;" in svg and "&lt;" in svg
    assert root.find("{http://www.w3.org/2000/svg}title").text.endswith(
        ESCAPING_NAME
    )


# --- A2. option validation -------------------------------------------------


@pytest.mark.parametrize("field", ["show_degrees", "mark_node_retrograde", "caption"])
@pytest.mark.parametrize("value", [0, 1, None, "true", "", 1.0, []])
def test_flags_must_be_exactly_bool(field, value):
    with pytest.raises(ValueError) as error:
        NorthIndianOptions(**{field: value})
    assert field in str(error.value)
    assert repr(value) in str(error.value)


@pytest.mark.parametrize("field", ["show_degrees", "mark_node_retrograde", "caption"])
@pytest.mark.parametrize("value", [True, False])
def test_flags_accept_real_bools(field, value):
    assert getattr(NorthIndianOptions(**{field: value}), field) is value


@pytest.mark.parametrize("value", [True, False, 0, -1, 450.0, "450", [], 0.5])
def test_width_rejects_everything_that_is_not_a_positive_int(value):
    with pytest.raises(ValueError) as error:
        NorthIndianOptions(width=value)
    assert "width" in str(error.value)
    assert repr(value) in str(error.value)


@pytest.mark.parametrize("value", [None, 1, 449, 450, 1080, 4096])
def test_width_accepts_none_and_positive_ints(value):
    assert NorthIndianOptions(width=value).width == value


def test_width_none_writes_no_width_or_height_but_keeps_the_viewbox():
    root = parse(render_north_indian_svg(case_chart("jalandhar")))

    assert root.get("width") is None
    assert root.get("height") is None
    assert root.get("viewBox") == "0 0 1080 1202"
    assert root.get("preserveAspectRatio") == "xMidYMin meet"


@pytest.mark.parametrize("width", [1, 449, 450, 1080, 2000])
def test_width_writes_a_proportional_floor_height(width):
    chart = case_chart("jalandhar")
    root = parse(
        render_north_indian_svg(chart, NorthIndianOptions(width=width))
    )

    document_height = int(root.get("viewBox").split()[3])
    assert root.get("width") == str(width)
    assert root.get("height") == str(width * document_height // 1080)
    assert root.get("viewBox") == f"0 0 1080 {document_height}"


BAD_PREFIXES = [
    "",                 # empty
    "1st",              # leading digit
    "-x",               # leading hyphen
    "_x",               # leading underscore
    "a b",              # space
    "a.b",              # dot
    "chart:1",          # colon
    "a" * 33,           # one over the 32-character limit
    "chärt",            # non-ASCII
    None,
    True,
    1,
]
GOOD_PREFIXES = ["d1", "chart-1", "Chart_2", "a", "a" * 32]


@pytest.mark.parametrize("value", BAD_PREFIXES)
def test_id_prefix_rejects_anything_outside_the_conservative_format(value):
    with pytest.raises(ValueError) as error:
        NorthIndianOptions(id_prefix=value)
    assert "id_prefix" in str(error.value)
    assert repr(value) in str(error.value)


@pytest.mark.parametrize("value", GOOD_PREFIXES)
def test_id_prefix_accepts_the_documented_forms(value):
    assert NorthIndianOptions(id_prefix=value).id_prefix == value


@pytest.mark.parametrize("value", GOOD_PREFIXES)
def test_the_ids_and_aria_references_are_exactly_the_prefixed_pair(value):
    svg = render_north_indian_svg(
        case_chart("jalandhar"), NorthIndianOptions(id_prefix=value)
    )
    root = parse(svg)

    assert root.get("aria-labelledby") == f"{value}-title"
    assert root.get("aria-describedby") == f"{value}-desc"
    identifiers = [
        element.get("id") for element in root.iter() if element.get("id")
    ]
    assert identifiers == [f"{value}-title", f"{value}-desc"]
    check_structural_safety(svg, value)


def test_the_default_prefix_is_d1():
    root = parse(render_north_indian_svg(case_chart("jalandhar")))

    assert root.get("aria-labelledby") == "d1-title"
    assert root.get("aria-describedby") == "d1-desc"
    assert [e.get("id") for e in root.iter() if e.get("id")] == [
        "d1-title", "d1-desc",
    ]


@pytest.mark.parametrize("chart", [None, 42, "chart", object()])
def test_render_rejects_a_chart_that_is_not_a_d1chart(chart):
    with pytest.raises(ValueError) as error:
        render_north_indian_svg(chart)
    assert "D1Chart" in str(error.value)


@pytest.mark.parametrize("options", [None, 0, {"caption": True}, object()])
def test_render_rejects_options_that_are_not_north_indian_options(options):
    with pytest.raises(ValueError) as error:
        render_north_indian_svg(case_chart("jalandhar"), options)
    assert "NorthIndianOptions" in str(error.value)


def test_options_are_a_frozen_dataclass_with_the_documented_defaults():
    options = NorthIndianOptions()

    assert options.show_degrees is True
    assert options.mark_node_retrograde is False
    assert options.caption is False
    assert options.width is None
    assert options.id_prefix == "d1"
    with pytest.raises(Exception):
        options.caption = True


# --- A3. structural SVG safety --------------------------------------------

FORBIDDEN_ELEMENTS = {
    "script", "image", "use", "foreignObject", "style", "a", "iframe",
    "embed", "object", "animate", "animateMotion", "animateTransform",
    "set", "handler", "listener",
}
FORBIDDEN_VALUE_PREFIXES = ("url(", "javascript:", "data:")


def allowed_ids(prefix: str = "d1") -> set[str]:
    """The complete id set of a document rendered with that prefix."""
    return {f"{prefix}-title", f"{prefix}-desc"}


def check_structural_safety(svg: str, prefix: str = "d1") -> None:
    root = parse(svg)
    permitted = allowed_ids(prefix)

    for element in root.iter():
        name = local_name(element.tag)
        assert name not in FORBIDDEN_ELEMENTS, f"forbidden element <{name}>"
        for attribute, value in element.attrib.items():
            attribute_name = local_name(attribute)
            assert not attribute_name.lower().startswith("on"), attribute
            assert attribute_name not in ("href", "style"), attribute
            stripped = value.strip()
            for prefix in FORBIDDEN_VALUE_PREFIXES:
                assert not stripped.startswith(prefix), (attribute, value)
            if attribute_name == "id":
                assert value in permitted, value

    prolog = svg[: svg.index("<svg")]
    assert "<!DOCTYPE" not in prolog
    assert "<!ENTITY" not in prolog
    assert "<!" not in prolog
    remainder = prolog.strip()
    if remainder:
        assert remainder.startswith("<?xml") and remainder.endswith("?>")
        assert remainder.count("<?") == 1
    assert "<?" not in svg[svg.index("<svg"):]


@pytest.mark.parametrize("name", CASE_NAMES)
def test_output_is_structurally_safe(name):
    check_structural_safety(rendered(name))


def test_a_hostile_looking_place_name_is_inert_escaped_text():
    """The dangerous-looking characters are content, and content is escaped."""
    svg = rendered("injection_name")
    check_structural_safety(svg)
    root = parse(svg)

    lines = caption_lines(root)
    assert INJECTION_NAME in lines, "the name is one caption line, unaltered"
    assert "&lt;script&gt;" in svg
    assert "<script" not in svg
    assert root.find("{http://www.w3.org/2000/svg}title").text.endswith(
        INJECTION_NAME
    )
    assert INJECTION_NAME in root.find("{http://www.w3.org/2000/svg}desc").text


@pytest.mark.parametrize("name", CASE_NAMES)
def test_accessibility_wiring_is_present(name):
    prefix = case_options(name).id_prefix
    root = parse(rendered(name))

    assert root.get("role") == "img"
    assert root.get("aria-labelledby") == f"{prefix}-title"
    assert root.get("aria-describedby") == f"{prefix}-desc"
    children = list(root)
    assert local_name(children[0].tag) == "title"
    assert children[0].get("id") == f"{prefix}-title"
    assert local_name(children[1].tag) == "desc"
    assert children[1].get("id") == f"{prefix}-desc"
    assert children[0].text and children[1].text
    # The name is the title alone and the description the desc alone: the two
    # references are separate attributes and are never concatenated.
    assert " " not in root.get("aria-labelledby")
    assert " " not in root.get("aria-describedby")


@pytest.mark.parametrize("name", CASE_NAMES)
def test_styling_is_presentation_attributes_only(name):
    """No stylesheet of any kind, and no ``url(`` in any attribute value.

    The ``url(`` ban is on attributes alone: a place name may contain the
    characters and stays legitimate escaped content.
    """
    svg = rendered(name)
    root = parse(svg)

    assert "<style" not in svg
    assert "@import" not in svg
    for element in root.iter():
        for attribute, value in element.attrib.items():
            assert local_name(attribute) != "style"
            assert "url(" not in value
            assert "@import" not in value


# --- A4. embedding regression (ids and accessible names) ------------------

EMBED_PAIRS = {
    # Two different charts, and the same chart twice: the second is the case
    # the renderer cannot detect, since identical input must give identical
    # bytes and therefore identical ids unless the caller separates them.
    "different": ("jalandhar_caption", "nine_house1"),
    "identical": ("jalandhar_caption", "jalandhar_caption"),
}


def embedded_pair(first_name, second_name, first_prefix, second_prefix):
    """Render one pair as two SVG strings, as an HTML body would hold them."""
    def render(name, prefix):
        options = case_options(name)
        return render_north_indian_svg(
            case_chart(name),
            NorthIndianOptions(
                show_degrees=options.show_degrees,
                mark_node_retrograde=options.mark_node_retrograde,
                caption=options.caption,
                width=options.width,
                id_prefix=prefix,
            ),
        )

    return render(first_name, first_prefix), render(second_name, second_prefix)


def ids_of(svg: str) -> list[str]:
    return [
        element.get("id") for element in parse(svg).iter() if element.get("id")
    ]


@pytest.mark.parametrize("pair", sorted(EMBED_PAIRS))
def test_distinct_prefixes_keep_two_inline_charts_apart(pair):
    """Section 10.A4: no id collides across the pair, in either direction."""
    first_name, second_name = EMBED_PAIRS[pair]
    first, second = embedded_pair(first_name, second_name, "chart-1", "chart-2")

    first_ids = ids_of(first)
    second_ids = ids_of(second)
    assert first_ids == ["chart-1-title", "chart-1-desc"]
    assert second_ids == ["chart-2-title", "chart-2-desc"]
    assert set(first_ids).isdisjoint(second_ids)
    assert len(first_ids + second_ids) == len(set(first_ids + second_ids))

    # An HTML body holding both is one id namespace; the check is on the union.
    document = f"<!doctype html>\n<html><body>\n{first}\n<hr>\n{second}\n</body></html>\n"
    assert document.count('id="chart-1-title"') == 1
    assert document.count('id="chart-2-title"') == 1


@pytest.mark.parametrize("pair", sorted(EMBED_PAIRS))
def test_each_root_names_ids_that_exist_only_in_its_own_svg(pair):
    first_name, second_name = EMBED_PAIRS[pair]
    rendered_pair = embedded_pair(
        first_name, second_name, "chart-1", "chart-2"
    )

    for index, svg in enumerate(rendered_pair):
        other = rendered_pair[1 - index]
        root = parse(svg)
        own = set(ids_of(svg))
        foreign = set(ids_of(other))
        for reference in ("aria-labelledby", "aria-describedby"):
            target = root.get(reference)
            assert target in own
            assert target not in foreign


@pytest.mark.parametrize("pair", sorted(EMBED_PAIRS))
def test_the_same_prefix_collides_which_is_why_callers_must_differ(pair):
    """The documented failure, asserted so the requirement stays justified."""
    first_name, second_name = EMBED_PAIRS[pair]
    first, second = embedded_pair(first_name, second_name, "d1", "d1")

    combined = ids_of(first) + ids_of(second)
    assert len(combined) != len(set(combined))
    assert combined.count("d1-title") == 2
    assert combined.count("d1-desc") == 2


def test_the_same_chart_and_options_render_byte_identically():
    """No randomness, no counter, no content hash: ids never self-uniquify."""
    chart = case_chart("jalandhar_caption")
    options = NorthIndianOptions(caption=True, id_prefix="chart-1")

    assert render_north_indian_svg(chart, options) == render_north_indian_svg(
        chart, options
    )
    with_other_prefix = render_north_indian_svg(
        chart, NorthIndianOptions(caption=True, id_prefix="chart-2")
    )
    assert with_other_prefix != render_north_indian_svg(chart, options)
    assert with_other_prefix.replace("chart-2", "chart-1") == (
        render_north_indian_svg(chart, options)
    )


# --- layer boundary --------------------------------------------------------

FORBIDDEN_IMPORTS = (
    "swisseph",
    "vedic_chart.ephemeris",
    "vedic_chart.astronomy",
    "vedic_chart.sidereal",
    "vedic_chart.time",
    "vedic_chart.lagna",
    "vedic_chart.location",
    "vedic_chart.inputs",
    "vedic_chart.chart",
    "vedic_chart.vedic.divisions",
    "http",
    "urllib",
    "requests",
    "socket",
    "ssl",
    "ftplib",
    "aiohttp",
    "os",
    "pathlib",
    "io",
    "random",
    "datetime",
)

ALLOWED_STDLIB = (
    "dataclasses", "math", "re", "xml.sax.saxutils", "itertools",
)
ALLOWED_PROJECT_IMPORTS = (
    "vedic_chart.representation.d1",
    "vedic_chart.representation.dms",
    "vedic_chart.vedic.grahas",
)
INTERNAL_MODULES = ("north_indian", "north_indian_geometry")


def imported_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    absolute = []
    relative = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                if module:
                    relative.append(module)
                relative.extend(alias.name for alias in node.names)
            else:
                absolute.append(module)
                absolute.extend(
                    f"{module}.{alias.name}" for alias in node.names
                )
    return absolute, relative


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_render_imports_nothing_forbidden(filename):
    absolute, _ = imported_names(RENDER_PACKAGE / filename)

    for name in absolute:
        lowered = name.lower()
        for forbidden in FORBIDDEN_IMPORTS:
            assert not (
                lowered == forbidden or lowered.startswith(forbidden + ".")
            ), f"{filename} imports {name}"


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_render_imports_only_what_the_contract_allows(filename):
    absolute, relative = imported_names(RENDER_PACKAGE / filename)

    for name in absolute:
        allowed = ALLOWED_STDLIB + ALLOWED_PROJECT_IMPORTS
        assert any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in allowed
        ), f"{filename} imports {name}"
    for name in relative:
        assert name in INTERNAL_MODULES or any(
            name.startswith(module + ".") for module in INTERNAL_MODULES
        ) or name in ("NorthIndianOptions", "render_north_indian_svg"), (
            f"{filename} relatively imports {name}"
        )


def test_the_geometry_module_imports_nothing_from_the_project():
    absolute, relative = imported_names(
        RENDER_PACKAGE / "north_indian_geometry.py"
    )

    assert not [name for name in absolute if name.startswith("vedic_chart")]
    assert relative == []


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_render_never_calls_round(filename):
    """Degrees truncate; a round() here would be a policy breach."""
    tree = ast.parse((RENDER_PACKAGE / filename).read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            assert not (
                isinstance(function, ast.Name) and function.id == "round"
            ), f"{filename} calls round()"
            assert not (
                isinstance(function, ast.Attribute)
                and function.attr == "round"
            ), f"{filename} calls a round method"


def test_the_package_has_exactly_the_expected_modules():
    modules = sorted(path.name for path in RENDER_PACKAGE.glob("*.py"))

    assert modules == sorted(PACKAGE_FILES)


def test_only_two_names_are_public():
    import vedic_chart.render as package

    assert package.__all__ == ["NorthIndianOptions", "render_north_indian_svg"]
