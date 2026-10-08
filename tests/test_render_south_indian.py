"""Tests for Layer 19: the South Indian D1 SVG renderer (spec section 9.1).

As with Layer 10, every assertion is made against the ``D1Chart`` handed to the
renderer, never against recomputed astrology. Occurrence checks count logical
entry **groups** (``g.entry``, ``g.legend-entry``), never their inner text or
underline elements (owner correction b).
"""

import dataclasses
import itertools
from collections import Counter
from datetime import date, time

import xml.etree.ElementTree as ET

import pytest

from render_helpers import (
    CASES,
    ESCAPING_NAME,
    GOLDEN_DIR,
    INJECTION_NAME,
    SOUTH_CASE_NAMES,
    case_chart,
    named_d1,
    south_case_chart,
    south_case_options,
    synthetic_d1,
    with_meta,
)
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.model import ResolvedLocation
from vedic_chart.render import (
    NorthIndianOptions,
    SouthIndianOptions,
    render_north_indian_svg,
    render_south_indian_svg,
)
from vedic_chart.render import north_indian as north
from vedic_chart.render import north_indian_geometry as north_geo
from vedic_chart.render import south_indian as south
from vedic_chart.render import south_indian_geometry as geo
from vedic_chart.vedic.grahas import Graha

SVG = "{http://www.w3.org/2000/svg}"
CHART_SIDE = 1000.0
CHART_LEFT = 40.0
TOLERANCE = 0.01
NORMAL_STROKE = 2.5
FLOOR_FONT = 21.0
REFERENCE_CHARTS = ("jalandhar", "bharatpur")

SOUTH_COMBINATIONS = {
    "caption_degrees": SouthIndianOptions(caption=True, show_degrees=True),
    "caption_nodegrees": SouthIndianOptions(caption=True, show_degrees=False),
    "nocaption_degrees": SouthIndianOptions(caption=False, show_degrees=True),
    "nocaption_nodegrees": SouthIndianOptions(caption=False, show_degrees=False),
}
NORTH_COMBINATIONS = {
    "caption_degrees": NorthIndianOptions(caption=True, show_degrees=True),
    "caption_nodegrees": NorthIndianOptions(caption=True, show_degrees=False),
    "nocaption_degrees": NorthIndianOptions(caption=False, show_degrees=True),
    "nocaption_nodegrees": NorthIndianOptions(caption=False, show_degrees=False),
}


# --- parsing helpers -------------------------------------------------------


def parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def local_name(name: str) -> str:
    return name.split("}")[-1]


def classes(element) -> list[str]:
    return (element.get("class") or "").split()


def of_class(root, css_class):
    """Every descendant whose class list contains ``css_class``."""
    return [el for el in root.iter() if css_class in classes(el)]


def children_of_class(group, css_class):
    return [child for child in group if css_class in classes(child)]


def sign_groups(root):
    return {int(g.get("data-rashi")): g for g in of_class(root, "sign")}


def legend_sign_groups(root):
    return {int(g.get("data-rashi")): g for g in of_class(root, "legend-sign")}


def degree_text(dms) -> str:
    return f"{dms.degrees}°{dms.minutes:02d}′"


def expects_underline(chart, graha, options) -> bool:
    placement = chart.grahas[graha]
    if not placement.is_retrograde:
        return False
    if graha in (Graha.RAHU, Graha.KETU) and not options.mark_node_retrograde:
        return False
    return True


def rendered(name: str) -> str:
    return render_south_indian_svg(south_case_chart(name), south_case_options(name))


def entry_tuple(group):
    """``(key, abbreviation, degree text, underlined)`` of one entry group."""
    abbrs = children_of_class(group, "abbr")
    degrees = children_of_class(group, "degrees")
    retros = children_of_class(group, "retro")
    assert len(abbrs) == 1
    assert len(degrees) <= 1
    assert len(retros) <= 1
    return (
        group.get("data-graha"),
        abbrs[0].text,
        degrees[0].text if degrees else "",
        bool(retros),
    )


def chart_top(root) -> float:
    """The chart's top edge, read from Meena's cell (row 0)."""
    meena = sign_groups(root)[12]
    return float(children_of_class(meena, "cell")[0].get("y"))


# --- grid and strokes ------------------------------------------------------


def edge_lines(root):
    return of_class(root, "cell-edge")


@pytest.mark.parametrize("name", SOUTH_CASE_NAMES)
def test_the_grid_is_the_thirty_six_canonical_edges_each_once(name):
    chart = south_case_chart(name)
    root = parse(rendered(name))
    top = chart_top(root)

    lines = edge_lines(root)
    assert len(lines) == 36
    assert all(local_name(line.tag) == "line" for line in lines)
    drawn = []
    for line in lines:
        x1, y1, x2, y2 = (float(line.get(a)) for a in ("x1", "y1", "x2", "y2"))
        drawn.append(
            (
                ((x1 - CHART_LEFT) / CHART_SIDE / 0.25, (y1 - top) / CHART_SIDE / 0.25),
                ((x2 - CHART_LEFT) / CHART_SIDE / 0.25, (y2 - top) / CHART_SIDE / 0.25),
            )
        )
    expected = [
        ((float(a[0]), float(a[1])), (float(b[0]), float(b[1])))
        for a, b in geo.GRID_EDGES
    ]
    assert len(drawn) == len(expected)
    for (d0, d1), (e0, e1) in zip(drawn, expected):
        assert d0 == pytest.approx(e0, abs=1e-6)
        assert d1 == pytest.approx(e1, abs=1e-6)
    assert len(set(drawn)) == 36

    thick = [line for line in lines if "lagna" in classes(line)]
    assert len(thick) == 4
    lagna_edges = set(geo.rashi_cell_edges(chart.lagna.rashi_index))
    for line, edge in zip(lines, geo.GRID_EDGES):
        is_thick = "lagna" in classes(line)
        assert is_thick is (edge in lagna_edges)
        assert line.get("class") == ("cell-edge lagna" if is_thick else "cell-edge")
        assert float(line.get("stroke-width")) == pytest.approx(
            2 * NORMAL_STROKE if is_thick else NORMAL_STROKE
        )


@pytest.mark.parametrize("name", SOUTH_CASE_NAMES)
def test_nothing_else_strokes_a_cell(name):
    root = parse(rendered(name))

    assert [el for el in root.iter() if local_name(el.tag) == "polygon"] == []
    for rect in (el for el in root.iter() if local_name(el.tag) == "rect"):
        assert rect.get("stroke") in (None, "none")
    cells = of_class(root, "cell")
    assert len(cells) == 12
    for rect in cells:
        assert rect.get("fill") == "none"
        assert rect.get("stroke") == "none"
    # Lines are only grid edges and retrograde underlines.
    for line in (el for el in root.iter() if local_name(el.tag) == "line"):
        assert classes(line) in (["cell-edge"], ["cell-edge", "lagna"], ["retro"])


# --- the twelve Lagna signs -------------------------------------------------


@pytest.mark.parametrize("lagna_index", range(12))
def test_every_lagna_sign_marks_its_own_fixed_cell(lagna_index):
    name = f"lagna_{lagna_index:02d}"
    chart = south_case_chart(name)
    assert chart.lagna.rashi_index == lagna_index
    root = parse(rendered(name))
    signs = sign_groups(root)

    assert sorted(signs) == list(range(1, 13))
    lagna_group = signs[lagna_index + 1]
    assert lagna_group.get("data-lagna") == "true"
    assert lagna_group.get("data-house") == "1"
    assert [s for s, g in signs.items() if g.get("data-lagna") == "true"] == [
        lagna_index + 1
    ]
    entries = children_of_class(lagna_group, "entry")
    assert entries[0].get("data-graha") == "lagna"
    assert entry_tuple(entries[0])[1] == "As"

    for house in chart.houses:
        group = signs[house.rashi_number]
        assert int(group.get("data-house")) == house.number
        assert children_of_class(group, "house-label")[0].text == f"H{house.number}"
        assert children_of_class(group, "sign-label")[0].text == house.rashi_name

    thick = [
        tuple(float(line.get(a)) for a in ("x1", "y1", "x2", "y2"))
        for line in edge_lines(root)
        if "lagna" in classes(line)
    ]
    cell = children_of_class(lagna_group, "cell")[0]
    x0, y0 = float(cell.get("x")), float(cell.get("y"))
    x1, y1 = x0 + float(cell.get("width")), y0 + float(cell.get("height"))
    assert sorted(thick) == sorted(
        [(x0, y0, x1, y0), (x1, y0, x1, y1), (x0, y1, x1, y1), (x0, y0, x0, y1)]
    )


def test_sign_positions_never_move_with_the_lagna():
    positions = []
    for lagna_index in range(12):
        root = parse(rendered(f"lagna_{lagna_index:02d}"))
        positions.append(
            {
                rashi: (
                    children_of_class(group, "cell")[0].get("x"),
                    children_of_class(group, "cell")[0].get("y"),
                )
                for rashi, group in sign_groups(root).items()
            }
        )
    assert all(position == positions[0] for position in positions)
    for rashi_index, (row, column) in enumerate(geo.CELL_BY_RASHI_INDEX):
        x, y = positions[0][rashi_index + 1]
        assert float(x) == pytest.approx(CHART_LEFT + column * 250.0)
        assert float(y) == pytest.approx(CHART_LEFT + row * 250.0)


# --- semantics and the occurrence rules ------------------------------------


def check_occurrence_rules(chart, options, root):
    signs = sign_groups(root)
    legends = legend_sign_groups(root)
    houses = {house.rashi_index: house for house in chart.houses}
    lagna_index = chart.lagna.rashi_index

    cell_counts = Counter()
    legend_counts = Counter()
    overflowing = set()

    # Entry groups live only in sign groups; legend entries only in legend signs.
    for group in of_class(root, "entry"):
        assert group.get("class") == "entry"
    assert sum(len(children_of_class(g, "entry")) for g in signs.values()) == len(
        of_class(root, "entry")
    )
    assert sum(
        len(children_of_class(g, "legend-entry")) for g in legends.values()
    ) == len(of_class(root, "legend-entry"))

    for rashi_number, group in signs.items():
        house = houses[rashi_number - 1]
        is_lagna = rashi_number - 1 == lagna_index
        assert group.get("data-lagna") == ("true" if is_lagna else "false")
        assert int(group.get("data-house")) == house.number
        assert group.get("data-layout") == "inline"

        entries = children_of_class(group, "entry")
        keys = [entry.get("data-graha") for entry in entries]
        expected = [graha.value for graha in house.occupants]
        if is_lagna:
            assert keys[:1] == ["lagna"]
            shown = keys[1:]
        else:
            shown = keys
        assert "lagna" not in shown
        assert shown == expected[: len(shown)]

        overflow = children_of_class(group, "overflow")
        if overflow:
            overflowing.add(rashi_number)
            assert len(overflow) == 1
            omitted = len(expected) - len(shown)
            assert omitted > 0
            assert overflow[0].text == f"+{omitted}"
            block = legends[rashi_number]
            assert int(block.get("data-house")) == house.number
            legend_entries = children_of_class(block, "legend-entry")
            assert [e.get("data-graha") for e in legend_entries] == expected
            for entry in legend_entries:
                check_entry(chart, options, entry)
            heading = " ".join(
                e.text for e in children_of_class(block, "legend-heading")
            )
            assert heading == f"{house.rashi_name} (H{house.number}) — complete list:"
        else:
            assert shown == expected
            assert rashi_number not in legends

        for entry in entries:
            check_entry(chart, options, entry)
        cell_counts.update(keys)

    for block in legends.values():
        legend_counts.update(
            e.get("data-graha") for e in children_of_class(block, "legend-entry")
        )

    assert set(legends) == overflowing
    assert all(count <= 1 for count in cell_counts.values())
    assert cell_counts["lagna"] == 1
    assert legend_counts["lagna"] == 0
    for graha in Graha:
        sign = chart.grahas[graha].rashi_index + 1
        assert legend_counts[graha.value] == (1 if sign in overflowing else 0)
        assert cell_counts[graha.value] + legend_counts[graha.value] >= 1


def check_entry(chart, options, group):
    key, abbr, degrees, underlined = entry_tuple(group)
    if key == "lagna":
        assert abbr == "As"
        expected_degrees = degree_text(chart.lagna.dms(0))
        assert underlined is False
    else:
        graha = Graha(key)
        assert abbr == south.ABBREVIATIONS[graha]
        expected_degrees = degree_text(chart.grahas[graha].dms(0))
        assert underlined is expects_underline(chart, graha, options)
    assert degrees == (expected_degrees if options.show_degrees else "")
    # Inner elements carry no identity of their own: the group does.
    for child in group:
        assert child.get("data-graha") is None


@pytest.mark.parametrize("name", SOUTH_CASE_NAMES)
def test_semantics_and_occurrence_rules(name):
    chart = south_case_chart(name)
    options = south_case_options(name)
    check_occurrence_rules(chart, options, parse(rendered(name)))


@pytest.mark.parametrize("name", SOUTH_CASE_NAMES)
def test_every_planet_sits_in_the_cell_of_its_rashi_index(name):
    chart = south_case_chart(name)
    root = parse(rendered(name))
    signs = sign_groups(root)

    for graha, placement in chart.grahas.items():
        holders = [
            rashi
            for rashi, group in signs.items()
            if graha.value
            in [e.get("data-graha") for e in children_of_class(group, "entry")]
        ]
        house = chart.house(placement.house)
        assert house.rashi_index == placement.rashi_index
        assert holders in ([placement.rashi_index + 1], [])
        if not holders:
            # Omitted by the overflow rule: its own sign overflows.
            assert children_of_class(signs[placement.rashi_index + 1], "overflow")


# --- crowding (labelled cases) ---------------------------------------------

#: ``case -> {rashi_index: (size, shown keys, +n or None)}``.
CROWD_EXPECTATIONS = {
    "one_sign_all_nine": {
        7: (0.021, ["sun", "moon", "mercury", "venus", "mars"], 4),
    },
    "lagna_sign_all_nine": {
        0: (0.021, ["lagna", "sun", "moon", "mercury", "venus"], 5),
    },
    "six_exact": {
        3: (0.022, ["lagna", "sun", "moon", "mercury", "venus", "mars"], None),
    },
    "seven_first_overflow": {
        3: (0.021, ["lagna", "sun", "moon", "mercury", "venus"], 2),
    },
    "two_signs_crowded": {
        9: (0.021, ["lagna", "sun", "moon", "mercury", "venus"], 2),
        1: (0.032, ["saturn", "rahu", "ketu"], None),
    },
}
SIZE_BY_COUNT = {0: 0.032, 1: 0.032, 2: 0.032, 3: 0.032, 4: 0.032, 5: 0.026, 6: 0.022}
CROWD_CASES = [
    (case, suffix)
    for case in sorted(CROWD_EXPECTATIONS)
    for suffix in ("", "_no_degrees")
]


@pytest.mark.parametrize("case,suffix", CROWD_CASES)
def test_crowded_cells_follow_section_three_three(case, suffix):
    name = case + suffix
    chart = south_case_chart(name)
    options = south_case_options(name)
    assert options.show_degrees is (suffix == "")
    root = parse(rendered(name))
    signs = sign_groups(root)
    top = chart_top(root)
    expectations = CROWD_EXPECTATIONS[case]

    for rashi_number, group in signs.items():
        rashi_index = rashi_number - 1
        house = chart.house(int(group.get("data-house")))
        count = len(house.occupants) + (
            1 if rashi_index == chart.lagna.rashi_index else 0
        )
        entries = children_of_class(group, "entry")
        overflow = children_of_class(group, "overflow")
        if rashi_index in expectations:
            size, keys, plus = expectations[rashi_index]
            assert [e.get("data-graha") for e in entries] == keys
            if plus is None:
                assert overflow == []
            else:
                assert [e.text for e in overflow] == [f"+{plus}"]
        else:
            assert count <= 6
            size = SIZE_BY_COUNT[count]
            assert overflow == []

        font = size * CHART_SIDE
        box = geo.entry_box(rashi_index)
        expected_x = CHART_LEFT + geo.row_start_x(box.x0) * CHART_SIDE
        rows = [children_of_class(e, "abbr")[0] for e in entries] + overflow
        assert len(rows) <= geo.capacity(geo.ENTRY_HEIGHT, size)
        if overflow:
            assert len(rows) == geo.capacity(geo.ENTRY_HEIGHT, size) == 6
        for index, element in enumerate(rows):
            assert float(element.get("font-size")) == pytest.approx(font)
            assert float(element.get("x")) == pytest.approx(expected_x, abs=TOLERANCE)
            assert float(element.get("y")) == pytest.approx(
                top + geo.row_baseline(box.y0, index, size) * CHART_SIDE,
                abs=TOLERANCE,
            )
        for entry in entries:
            degrees = children_of_class(entry, "degrees")
            assert bool(degrees) is options.show_degrees
            for element in degrees:
                assert float(element.get("x")) == pytest.approx(
                    expected_x + geo.DEG_OFFSET * font, abs=TOLERANCE
                )

    overflowing = sorted(
        rashi_index + 1
        for rashi_index, (_, _, plus) in expectations.items()
        if plus is not None
    )
    assert sorted(legend_sign_groups(root)) == overflowing
    check_occurrence_rules(chart, options, root)


def test_six_entries_never_overflow_and_seven_always_do():
    six = parse(rendered("six_exact"))
    seven = parse(rendered("seven_first_overflow"))
    assert of_class(six, "overflow") == []
    assert of_class(six, "legend-sign") == []
    assert len(of_class(seven, "overflow")) == 1
    assert len(of_class(seven, "legend-sign")) == 1


# --- text boxes ------------------------------------------------------------


def text_box(element):
    """``(x0, y0, x1, y1)`` from x/y/font/anchor at 0.68 em per character."""
    x = float(element.get("x"))
    y = float(element.get("y"))
    font = float(element.get("font-size"))
    width = len(element.text or "") * geo.CHAR_ADVANCE * font
    anchor = element.get("text-anchor")
    if anchor == "end":
        x0, x1 = x - width, x
    elif anchor == "middle":
        x0, x1 = x - width / 2, x + width / 2
    else:
        x0, x1 = x, x + width
    if element.get("dominant-baseline") == "central":
        return (x0, y - font / 2, x1, y + font / 2)
    return (x0, y - geo.ASCENT * font, x1, y + geo.DESCENT * font)


def line_box(element):
    x1, x2 = float(element.get("x1")), float(element.get("x2"))
    y1, y2 = float(element.get("y1")), float(element.get("y2"))
    half = float(element.get("stroke-width")) / 2
    return (min(x1, x2), min(y1, y2) - half, max(x1, x2), max(y1, y2) + half)


def boxes_overlap(a, b) -> bool:
    return (
        a[0] < b[2] - 1e-6 and b[0] < a[2] - 1e-6
        and a[1] < b[3] - 1e-6 and b[1] < a[3] - 1e-6
    )


def inside(box, container) -> bool:
    return (
        container[0] - TOLERANCE <= box[0] and box[2] <= container[2] + TOLERANCE
        and container[1] - TOLERANCE <= box[1] and box[3] <= container[3] + TOLERANCE
    )


@pytest.mark.parametrize("name", SOUTH_CASE_NAMES)
def test_no_text_boxes_overlap_and_every_text_stays_in_its_cell(name):
    root = parse(rendered(name))
    top = chart_top(root)
    texts = [el for el in root.iter() if local_name(el.tag) == "text"]
    boxes = [(el, text_box(el)) for el in texts]

    for (a, box_a), (b, box_b) in itertools.combinations(boxes, 2):
        assert not boxes_overlap(box_a, box_b), (a.text, b.text)

    for rashi_number, group in sign_groups(root).items():
        inner = geo.inner_box(rashi_number - 1)
        container = (
            CHART_LEFT + inner.x0 * CHART_SIDE, top + inner.y0 * CHART_SIDE,
            CHART_LEFT + inner.x1 * CHART_SIDE, top + inner.y1 * CHART_SIDE,
        )
        for element in group.iter():
            if local_name(element.tag) == "text":
                assert inside(text_box(element), container), element.text
            elif local_name(element.tag) == "line":
                assert inside(line_box(element), container)
        # An underline touches no text but its own abbreviation.
        for entry in children_of_class(group, "entry"):
            own = children_of_class(entry, "abbr")[0]
            for line in children_of_class(entry, "retro"):
                for element, box in boxes:
                    if element is not own:
                        assert not boxes_overlap(line_box(line), box)

    centre = of_class(root, "centre-label")
    assert len(centre) == 1 and centre[0].text == "D1 / Rashi"
    assert float(centre[0].get("font-size")) == pytest.approx(32.0)
    assert inside(
        text_box(centre[0]),
        (CHART_LEFT + 250, top + 250, CHART_LEFT + 750, top + 750),
    )


@pytest.mark.parametrize("name", SOUTH_CASE_NAMES)
def test_entry_text_is_never_below_the_floor(name):
    root = parse(rendered(name))
    for css_class in ("abbr", "degrees", "overflow"):
        for element in of_class(root, css_class):
            assert float(element.get("font-size")) >= FLOOR_FONT - 1e-9
    for element in of_class(root, "sign-label") + of_class(root, "house-label"):
        assert float(element.get("font-size")) == pytest.approx(20.0)


@pytest.mark.parametrize("name", SOUTH_CASE_NAMES)
def test_the_bands_and_document_height(name):
    options = south_case_options(name)
    root = parse(rendered(name))
    view_box = root.get("viewBox").split()
    assert view_box[:3] == ["0", "0", "1080"]
    height = int(view_box[3])

    captions = of_class(root, "caption-line")
    assert bool(captions) is options.caption
    caption_height = geo.band_height(len(captions), 32) if options.caption else 0
    assert chart_top(root) == pytest.approx(40 + caption_height)
    legend_lines = of_class(root, "legend-marker") + of_class(root, "legend-heading")
    entry_baselines = {
        float(children_of_class(e, "abbr")[0].get("y"))
        for e in of_class(root, "legend-entry")
    }
    line_count = len(legend_lines) + len(entry_baselines)
    assert height == 40 + caption_height + 1000 + 30 + geo.band_height(line_count, 30) + 40
    for element in of_class(root, "legend-entry"):
        for child in element:
            if local_name(child.tag) == "text":
                assert text_box(child)[2] <= CHART_LEFT + CHART_SIDE + TOLERANCE


# --- options: degrees, retrograde, caption, title, privacy ------------------


def test_degrees_off_removes_only_the_degree_texts():
    chart = case_chart("jalandhar")
    with_degrees = parse(render_south_indian_svg(chart, SouthIndianOptions()))
    without = parse(
        render_south_indian_svg(chart, SouthIndianOptions(show_degrees=False))
    )
    assert len(of_class(with_degrees, "degrees")) == len(of_class(with_degrees, "entry"))
    assert of_class(without, "degrees") == []
    assert [e.get("data-graha") for e in of_class(with_degrees, "entry")] == [
        e.get("data-graha") for e in of_class(without, "entry")
    ]


@pytest.mark.parametrize("chart_name", REFERENCE_CHARTS)
def test_nodes_are_underlined_only_when_asked(chart_name):
    chart = case_chart(chart_name)
    assert chart.grahas[Graha.RAHU].is_retrograde
    assert chart.grahas[Graha.KETU].is_retrograde

    def underlined(options):
        root = parse(render_south_indian_svg(chart, options))
        return {
            e.get("data-graha")
            for e in of_class(root, "entry")
            if children_of_class(e, "retro")
        }

    plain = underlined(SouthIndianOptions())
    marked = underlined(SouthIndianOptions(mark_node_retrograde=True))
    planets = {
        g.value for g, p in chart.grahas.items()
        if p.is_retrograde and g not in (Graha.RAHU, Graha.KETU)
    }
    assert plain == planets
    assert marked == planets | {"rahu", "ketu"}


def test_marker_lines_follow_the_node_option():
    plain = parse(render_south_indian_svg(synthetic_d1(0)))
    marked = parse(
        render_south_indian_svg(
            synthetic_d1(0), SouthIndianOptions(mark_node_retrograde=True)
        )
    )
    budget = geo.character_budget(22.0)

    def lines(root):
        return [e.text for e in of_class(root, "legend-marker")]

    assert lines(plain) == geo.wrap_text(south.MARKER_LAGNA_LINE, budget) + [
        "Underline = retrograde; not shown for Ra and Ke"
    ]
    assert lines(marked)[-1] == "Underline = retrograde; shown for Ra and Ke too"
    assert " ".join(lines(plain)[:-1]) == (
        "As = Lagna (ascendant), first in its cell; thicker border"
    )
    assert all(len(line) <= budget for line in lines(plain) + lines(marked))


def test_caption_on_shows_three_lines_and_the_place_in_the_title():
    chart = case_chart("jalandhar")
    root = parse(render_south_indian_svg(chart, SouthIndianOptions(caption=True)))
    meta = chart.meta

    lines = [e.text for e in of_class(root, "caption-line")]
    assert lines == [
        f"{meta.request.birth_date.isoformat()} 06:45 {meta.location.timezone_id}",
        meta.location.canonical_name,
        "Lahiri (true equinox) · Whole Sign · Mean Node",
    ]
    assert root.find(f"{SVG}title").text == (
        f"D1 chart (South Indian) — {meta.location.canonical_name}"
    )
    description = root.find(f"{SVG}desc").text
    assert description.startswith(
        f"{meta.request.birth_date.isoformat()} 06:45 {meta.location.timezone_id}. "
        f"{meta.location.canonical_name}. "
        "Lahiri (Chitrapaksha), true equinox · Whole Sign houses · Mean Node. "
    )


@pytest.mark.parametrize("chart_name", REFERENCE_CHARTS)
def test_the_description_reads_the_chart_in_fixed_map_order(chart_name):
    chart = case_chart(chart_name)
    description = parse(render_south_indian_svg(chart)).find(f"{SVG}desc").text
    lagna = chart.lagna

    expected = [
        f"Lagna in rashi {lagna.rashi_number} ({lagna.rashi_name}), house 1, "
        f"at {degree_text(lagna.dms(0))}."
    ]
    for house in sorted(chart.houses, key=lambda h: h.rashi_index):
        if not house.occupants:
            continue
        body = "; ".join(
            f"{south.FULL_NAMES[g]} {degree_text(chart.grahas[g].dms(0))}, "
            f"{'retrograde' if chart.grahas[g].is_retrograde else 'direct'}"
            for g in house.occupants
        )
        expected.append(f"{house.rashi_name} (house {house.number}): {body}.")
    assert description == " ".join(expected)


@pytest.mark.parametrize("chart_name", REFERENCE_CHARTS)
@pytest.mark.parametrize("show_degrees", [True, False])
def test_caption_off_assembles_no_birth_detail(chart_name, show_degrees):
    chart = case_chart(chart_name)
    svg = render_south_indian_svg(
        chart, SouthIndianOptions(caption=False, show_degrees=show_degrees)
    )
    root = parse(svg)
    meta = chart.meta
    request = meta.request

    assert of_class(root, "caption") == []
    assert root.find(f"{SVG}title").text == "D1 chart (South Indian)"
    forbidden = (
        request.birth_date.isoformat(),
        str(request.birth_date),
        request.birth_time.strftime("%H:%M"),
        str(request.birth_time),
        request.place_query,
        meta.location.canonical_name,
        meta.location.timezone_id,
        str(meta.julian_day_ut),
        repr(meta.julian_day_ut),
        str(int(meta.julian_day_ut)),
        str(meta.ayanamsa),
        repr(meta.ayanamsa),
        f"{meta.ayanamsa:.4f}",
        meta.ayanamsha,
        "Lahiri",
        str(meta.location.latitude),
        str(meta.location.longitude),
        str(meta.moment_utc),
        meta.moment_utc.isoformat(),
    )
    for needle in forbidden:
        assert needle not in svg, f"caption-off output leaks {needle!r}"


# --- determinism, escaping, validation --------------------------------------


@pytest.mark.parametrize("name", SOUTH_CASE_NAMES)
def test_two_renders_are_byte_identical(name):
    assert rendered(name) == rendered(name)


def test_equal_but_independently_built_charts_render_identically():
    assert render_south_indian_svg(synthetic_d1(5)) == render_south_indian_svg(
        synthetic_d1(5)
    )


@pytest.mark.parametrize("name", SOUTH_CASE_NAMES)
def test_ids_coordinates_and_environment(name):
    svg = rendered(name)
    root = parse(svg)
    prefix = south_case_options(name).id_prefix
    assert prefix == "d1-south"
    assert [el.get("id") for el in root.iter() if el.get("id")] == [
        f"{prefix}-title", f"{prefix}-desc",
    ]
    assert root.get("aria-labelledby") == f"{prefix}-title"
    assert root.get("aria-describedby") == f"{prefix}-desc"
    assert root.get("role") == "img"
    assert root.get("preserveAspectRatio") == "xMidYMin meet"
    assert "<!--" not in svg
    for forbidden in ("/home/", "/Users/", "C:\\", "file://", ".venv"):
        assert forbidden not in svg
    for element in root.iter():
        if local_name(element.tag) == "svg":
            continue
        for attribute in ("x", "y", "x1", "y1", "x2", "y2", "width", "height",
                          "font-size", "stroke-width"):
            value = element.get(attribute)
            if value is not None:
                assert len(value.split(".")[1]) == 2, (attribute, value)


ALLOWED_ELEMENTS = {"svg", "title", "desc", "rect", "g", "polygon", "line", "text"}


@pytest.mark.parametrize("name", SOUTH_CASE_NAMES)
def test_only_the_layer_ten_element_vocabulary_and_no_active_values(name):
    svg = rendered(name)
    root = parse(svg)
    assert "<style" not in svg and "<?" not in svg
    for element in root.iter():
        assert local_name(element.tag) in ALLOWED_ELEMENTS
        for attribute, value in element.attrib.items():
            assert not local_name(attribute).lower().startswith("on")
            assert local_name(attribute) not in ("href", "style")
            for prefix in ("url(", "javascript:", "data:"):
                assert not value.strip().startswith(prefix)
            assert "url(" not in value


def test_document_structure_order():
    root = parse(rendered("jalandhar_caption"))
    children = [(local_name(c.tag), c.get("class")) for c in root]
    assert children == [
        ("title", None), ("desc", None), ("rect", "paper"),
        ("g", "caption"), ("g", "chart"), ("g", "legend"),
    ]
    chart = of_class(root, "chart")[0]
    kinds = [c.get("class") for c in chart]
    assert kinds == ["grid", "centre"] + ["sign"] * 12
    assert [int(c.get("data-rashi")) for c in chart if c.get("class") == "sign"] == list(
        range(1, 13)
    )
    for group in children_of_class(chart, "sign"):
        names = [c.get("class") for c in group]
        assert names[:3] == ["cell", "sign-label", "house-label"]
        assert set(names[3:]) <= {"entry", "overflow"}
        assert group.find(f"{SVG}text[@class='house-label']").get("text-anchor") == "end"
    no_caption = parse(rendered("jalandhar"))
    assert [local_name(c.tag) for c in no_caption][:3] == ["title", "desc", "rect"]
    assert of_class(no_caption, "caption") == []


SPECIAL_NAME = 'Pläce <Ñame> & "Quoted" Śhāstri'


@pytest.mark.parametrize("name", [SPECIAL_NAME, ESCAPING_NAME, INJECTION_NAME])
def test_special_characters_are_escaped_and_round_trip(name):
    svg = render_south_indian_svg(named_d1(name), SouthIndianOptions(caption=True))
    root = parse(svg)

    assert name in [e.text for e in of_class(root, "caption-line")] or name in " ".join(
        e.text for e in of_class(root, "caption-line")
    )
    assert root.find(f"{SVG}title").text.endswith(name)
    assert name in root.find(f"{SVG}desc").text
    assert "&amp;" in svg and "&lt;" in svg
    assert "<script" not in svg


@pytest.mark.parametrize("field", ["show_degrees", "mark_node_retrograde", "caption"])
@pytest.mark.parametrize("value", [0, 1, None, "true", "", 1.0, []])
def test_flags_must_be_exactly_bool(field, value):
    with pytest.raises(ValueError) as error:
        SouthIndianOptions(**{field: value})
    assert field in str(error.value) and repr(value) in str(error.value)


@pytest.mark.parametrize("value", [True, False, 0, -1, 450.0, "450", [], 0.5])
def test_width_rejects_everything_that_is_not_a_positive_int(value):
    with pytest.raises(ValueError) as error:
        SouthIndianOptions(width=value)
    assert "width" in str(error.value) and repr(value) in str(error.value)


@pytest.mark.parametrize(
    "value", ["", "1st", "-x", "_x", "a b", "a.b", "chart:1", "a" * 33, "chärt", None, True, 1]
)
def test_id_prefix_rejects_anything_outside_the_conservative_format(value):
    with pytest.raises(ValueError) as error:
        SouthIndianOptions(id_prefix=value)
    assert "id_prefix" in str(error.value) and repr(value) in str(error.value)


@pytest.mark.parametrize(
    "field,value",
    [("show_degrees", 1), ("mark_node_retrograde", 0), ("caption", "yes"),
     ("width", 0), ("id_prefix", "9")],
)
def test_each_of_the_five_options_is_validated_like_layer_ten(field, value):
    with pytest.raises(ValueError) as south_error:
        SouthIndianOptions(**{field: value})
    with pytest.raises(ValueError) as north_error:
        NorthIndianOptions(**{field: value})
    assert str(south_error.value) == str(north_error.value)


def test_options_defaults_and_frozen():
    options = SouthIndianOptions()
    assert (
        options.show_degrees, options.mark_node_retrograde, options.caption,
        options.width, options.id_prefix,
    ) == (True, False, False, None, "d1-south")
    assert [f.name for f in dataclasses.fields(SouthIndianOptions)] == [
        f.name for f in dataclasses.fields(NorthIndianOptions)
    ]
    with pytest.raises(Exception):
        options.caption = True


@pytest.mark.parametrize("width", [1, 449, 600, 1080, 2000])
def test_width_writes_a_proportional_floor_height(width):
    root = parse(render_south_indian_svg(case_chart("jalandhar"), SouthIndianOptions(width=width)))
    height = int(root.get("viewBox").split()[3])
    assert root.get("width") == str(width)
    assert root.get("height") == str(width * height // 1080)


def test_width_none_writes_no_size():
    root = parse(render_south_indian_svg(case_chart("jalandhar")))
    assert root.get("width") is None and root.get("height") is None
    assert root.get("viewBox") == "0 0 1080 1202"


@pytest.mark.parametrize("chart", [None, 42, "chart", object()])
def test_render_rejects_a_chart_that_is_not_a_d1chart(chart):
    with pytest.raises(ValueError) as error:
        render_south_indian_svg(chart)
    assert "D1Chart" in str(error.value)


@pytest.mark.parametrize(
    "options", [None, 0, {"caption": True}, object(), NorthIndianOptions()]
)
def test_render_rejects_options_that_are_not_south_indian_options(options):
    with pytest.raises(ValueError) as error:
        render_south_indian_svg(case_chart("jalandhar"), options)
    assert "SouthIndianOptions" in str(error.value)


@pytest.mark.parametrize("field,value", [("house_system", "equal"), ("node", "true")])
def test_an_unsupported_convention_is_refused_before_any_output(field, value):
    chart = with_meta(case_chart("jalandhar"), **{field: value})
    with pytest.raises(ValueError) as error:
        render_south_indian_svg(chart, SouthIndianOptions(caption=True))
    assert field in str(error.value) and repr(value) in str(error.value)


@pytest.mark.parametrize(
    "field,value", [("house_system", "equal_zz"), ("node", "true_zz")]
)
def test_an_unsupported_convention_is_irrelevant_without_a_caption(field, value):
    """As Layer 10: the labels are read only to build the caption."""
    chart = with_meta(case_chart("jalandhar"), **{field: value})
    svg = render_south_indian_svg(chart, SouthIndianOptions(caption=False))
    assert value not in svg
    assert svg == render_south_indian_svg(case_chart("jalandhar"))


def test_an_unknown_ayanamsha_descriptor_is_shown_verbatim():
    chart = with_meta(case_chart("jalandhar"), ayanamsha="Raman & Co")
    svg = render_south_indian_svg(chart, SouthIndianOptions(caption=True))
    root = parse(svg)
    assert of_class(root, "caption-line")[-1].text == "Raman & Co · Whole Sign · Mean Node"
    assert "&amp;" in svg


def test_a_long_place_name_wraps_within_the_caption_budget_and_loses_nothing():
    name = "Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch" * 2
    location = ResolvedLocation(name, 12.5, 77.5, "Asia/Kolkata")
    request = BirthChartRequest(date(1980, 7, 4), time(23, 5), name)
    chart = synthetic_d1(4, location=location, request=request)
    root = parse(render_south_indian_svg(chart, SouthIndianOptions(caption=True)))
    lines = [e.text for e in of_class(root, "caption-line")]
    assert all(len(line) <= geo.character_budget(24.0) for line in lines)
    assert name in "".join(lines)


# --- convention equality with Layer 10 (section 4.4) -----------------------


def test_the_convention_tables_equal_layer_ten():
    assert south.ABBREVIATIONS == north.ABBREVIATIONS
    assert south.FULL_NAMES == north.FULL_NAMES
    assert south.NODES == north.NODES
    assert south.LAGNA_KEY == north.LAGNA_KEY
    assert south.LAGNA_ABBR == north.LAGNA_ABBR
    assert south.ID_PREFIX_PATTERN.pattern == north.ID_PREFIX_PATTERN.pattern
    assert south.COMPACT_AYANAMSHA_LABELS == north.COMPACT_AYANAMSHA_LABELS
    assert south.HOUSE_SYSTEM_LABELS == north.HOUSE_SYSTEM_LABELS
    assert south.NODE_LABELS == north.NODE_LABELS
    assert south.MARKER_RETRO_DEFAULT == north.MARKER_RETRO_DEFAULT
    assert south.MARKER_RETRO_NODES == north.MARKER_RETRO_NODES
    assert (south.DEGREE_SIGN, south.PRIME_SIGN, south.EM_DASH, south.MIDDLE_DOT) == (
        north.DEGREE_SIGN, north.PRIME_SIGN, north.EM_DASH, north.MIDDLE_DOT,
    )


TYPOGRAPHY = (
    "SIZE_LADDER", "FLOOR_SIZE", "BASE_SIZE", "LINE_HEIGHT", "CHAR_ADVANCE",
    "LEFT_INSET", "WIDTH_BUDGET_EMS", "ABBR_SLOT", "ABBR_DEG_GAP", "DEG_OFFSET",
    "RETRO_DROP", "RETRO_STROKE", "ASCENT", "DESCENT", "BAND_PADDING",
    "BAND_WIDTH", "FREE_TEXT_ADVANCE", "LEGEND_INDENT_CHARS",
    "LEGEND_SLOT_CHARS_WITH_DEGREES", "LEGEND_GAP_EMS",
)


@pytest.mark.parametrize("constant", TYPOGRAPHY)
def test_the_typography_constants_equal_layer_ten(constant):
    assert getattr(geo, constant) == getattr(north_geo, constant)


def test_the_layout_functions_agree_with_layer_ten():
    for font in (22.0, 24.0):
        assert geo.character_budget(font) == north_geo.character_budget(font)
        for show in (True, False):
            assert geo.legend_entries_per_line(font, show) == (
                north_geo.legend_entries_per_line(font, show)
            )
            for index in range(10):
                assert geo.legend_slot_x(index, font, show) == (
                    north_geo.legend_slot_x(index, font, show)
                )
    for lines in range(6):
        assert geo.band_height(lines, 30) == north_geo.band_height(lines, 30)
    for text in (south.MARKER_LAGNA_LINE, ESCAPING_NAME, "x" * 130):
        for budget in (5, 55, 60):
            assert geo.wrap_text(text, budget) == north_geo.wrap_text(text, budget)
    for width, height in ((0.23, 0.198), (0.22, 0.22), (0.21, 0.10), (0.145, 0.12)):
        for count in range(11):
            assert geo.select_size(count, width, height) == north_geo.select_size(
                count, width, height
            )
    for size in geo.SIZE_LADDER:
        assert geo.entry_width_budget(size) == north_geo.entry_width_budget(size)
        assert geo.row_baseline(0.1, 3, size) == north_geo.row_baseline(0.1, 3, size)


def test_the_style_numbers_equal_render_style():
    north_style = north.RenderStyle()
    south_style = south.SouthIndianStyle()
    for field in dataclasses.fields(north.RenderStyle):
        assert getattr(south_style, field.name) == getattr(north_style, field.name), (
            field.name
        )
    assert (south.LABEL_FONT, south.LABEL_ROW, south.CENTRE_FONT) == (0.020, 0.032, 0.032)
    assert south_style.label_row == geo.LABEL_ROW
    assert south_style.label_font == geo.LABEL_FONT


def north_entry_set(root):
    found = set()
    for group in (el for el in root.iter() if el.get("class") == "house"):
        retros = {c.get("data-graha") for c in group if c.get("class") == "retro"}
        degrees = {
            c.get("data-graha"): c.text for c in group if c.get("class") == "deg"
        }
        for abbr in (c for c in group if c.get("class") == "abbr"):
            key = abbr.get("data-graha")
            found.add((key, abbr.text, degrees.get(key, ""), key in retros))
    return found


@pytest.mark.parametrize("chart_name", REFERENCE_CHARTS)
@pytest.mark.parametrize("combination", sorted(SOUTH_COMBINATIONS))
def test_captions_and_entries_equal_layer_ten(chart_name, combination):
    chart = case_chart(chart_name)
    north_root = parse(render_north_indian_svg(chart, NORTH_COMBINATIONS[combination]))
    south_root = parse(render_south_indian_svg(chart, SOUTH_COMBINATIONS[combination]))

    def caption_texts(root):
        return [e.text for e in root.iter() if e.get("class") == "caption-line"]

    assert caption_texts(south_root) == caption_texts(north_root)
    assert bool(caption_texts(south_root)) is SOUTH_COMBINATIONS[combination].caption
    south_entries = {entry_tuple(group) for group in of_class(south_root, "entry")}
    assert south_entries == north_entry_set(north_root)
    assert len(south_entries) == 10


@pytest.mark.parametrize("chart_name", REFERENCE_CHARTS)
def test_both_documents_together_have_unique_ids(chart_name):
    chart = case_chart(chart_name)
    for caption in (False, True):
        documents = render_north_indian_svg(
            chart, NorthIndianOptions(caption=caption)
        ) + render_south_indian_svg(chart, SouthIndianOptions(caption=caption))
        wrapped = parse(f"<page>{documents}</page>")
        ids = [el.get("id") for el in wrapped.iter() if el.get("id")]
        assert ids == ["d1-title", "d1-desc", "d1-south-title", "d1-south-desc"]
        assert len(ids) == len(set(ids))


# --- North Indian byte equality, re-checked from this module ---------------


@pytest.mark.parametrize("chart_name", REFERENCE_CHARTS)
@pytest.mark.parametrize("combination", sorted(NORTH_COMBINATIONS))
def test_the_north_indian_goldens_are_still_byte_identical(chart_name, combination):
    """Read-only: this module never writes a North Indian golden."""
    path = GOLDEN_DIR / f"{chart_name}_{combination}.svg"
    svg = render_north_indian_svg(case_chart(chart_name), NORTH_COMBINATIONS[combination])
    assert path.read_text(encoding="utf-8") == svg


def test_the_south_registry_mirrors_every_layer_ten_case():
    assert set(CASES) <= set(SOUTH_CASE_NAMES)
