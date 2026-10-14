"""Tests for Layer 20: the ``overlay`` presentation block (``overlay_block``).

Specification ``docs/LAYER20_TRANSIT_OVERLAY_SPEC.md`` sections 5.3-5.4, 6.2,
10.4-10.7 and 15. The block is checked against the two renderers' own output
for the same chart, never against a second copy of its own arithmetic:

* ``entries`` against the ``text.deg`` / ``text.degrees`` content and the
  ``line.retro`` presence of the parsed North and South documents;
* ``slots`` against the parsed documents' cells: the house of each sign, the
  number of rows each renderer used, and the boxes of every natal element;
* every transit row and every marker as a glyph box built from the block's
  **formatted** strings, with polygon containment, edge clearance, the
  numeral and label glyph boxes and the natal text boxes.

The glyph-box model (0.68 em per character, 1 em tall, ascent 0.75 em) is the
renderers' own layout model; browser text bounds are the acceptance tool's job
(section 10.7) and are not claimed here.
"""

import ast
import inspect
import json
import math
import os
import re
import xml.etree.ElementTree as ET

import pytest

import render_helpers as helpers
from render_helpers import (
    OVERLAY_FILLS,
    OVERLAY_GOLDEN_DIR,
    SOUTH_CROWD_LAYOUTS,
    case_chart,
    count_in_house_d1,
    house_fill_d1,
    overlay_chart,
)
from vedic_chart.render import (
    NorthIndianOptions,
    SouthIndianOptions,
    overlay_block,
    render_north_indian_svg,
    render_south_indian_svg,
)
from vedic_chart.render import north_indian as ni
from vedic_chart.render import north_indian_geometry as ng
from vedic_chart.render import overlay as ov
from vedic_chart.render import south_indian as si
from vedic_chart.render import south_indian_geometry as sg
from vedic_chart.vedic.grahas import Graha

UPDATE_ENVIRONMENT_VARIABLE = "RENDER_GOLDEN_UPDATE"

# --- the numbers of the specification, spelled out --------------------------

SIDE = 1000.0
MARGIN = 40.0
CLEARANCE = 0.015
TOLERANCE = 1e-9
CHAR = 0.68
ASCENT = 0.75
MARKER_FONT = 0.020
NUMERAL_FONT = 0.026
DIGIT_HEIGHT = 0.729
LABEL_GAP = 0.45 * 0.020
MARKER_WIDTH = 4 * CHAR * MARKER_FONT
INLINE_EMS = {True: 11 * CHAR, False: 4 * CHAR}
STACKED_EMS = {True: 4.08, False: 4 * CHAR}
FLOOR = "21.00"
LADDER = ("32.00", "30.00", "28.00", "26.00", "24.00", "22.00", "21.00")
SIDE_HOUSES = (3, 5, 9, 11)

COORDINATE = re.compile(r"^[0-9]+\.[0-9]{2}$")
BLOCK_KEYS = [
    "schema", "prefix", "font_family", "marker_font_size", "entries", "slots",
]
ENTRY_KEYS = ["key", "abbr", "degree_text", "underline", "rashi_number"]
SLOT_KEYS = ["house", "layout", "natal_rows", "rungs", "marker"]
RASHI_KEYS = [str(number) for number in range(1, 13)]
GRAHA_KEYS = [graha.value for graha in Graha]

REFERENCE_CHARTS = ("jalandhar", "bharatpur")
LAGNA_CHARTS = tuple(f"lagna_{index:02d}" for index in range(12))
FILL_CHARTS = tuple(
    f"fill_{house}_{count}" for house in range(1, 13) for count in OVERLAY_FILLS
)
GEOMETRY_CHARTS = (
    REFERENCE_CHARTS
    + LAGNA_CHARTS
    + FILL_CHARTS
    + tuple(SOUTH_CROWD_LAYOUTS)
    + (
        "two_overflow",
        "boundary_degrees",
        "all_retrograde",
        "nine_house1",
        "nine_house2",
        "nine_house3",
        "transit_jalandhar",
    )
)
GEOMETRY_CASES = tuple(
    (name, degrees) for name in GEOMETRY_CHARTS for degrees in (True, False)
)


# --- cached blocks and documents ----------------------------------------------

_BLOCKS: dict = {}
_DOCUMENTS: dict = {}


def block_for(name: str, degrees: bool = True, nodes: bool = False) -> dict:
    key = (name, degrees, nodes)
    if key not in _BLOCKS:
        _BLOCKS[key] = overlay_block(
            overlay_chart(name), show_degrees=degrees, mark_node_retrograde=nodes
        )
    return _BLOCKS[key]


def documents_for(name: str, degrees: bool = True, nodes: bool = False):
    key = (name, degrees, nodes)
    if key not in _DOCUMENTS:
        chart = overlay_chart(name)
        north = render_north_indian_svg(
            chart,
            NorthIndianOptions(show_degrees=degrees, mark_node_retrograde=nodes),
        )
        south = render_south_indian_svg(
            chart,
            SouthIndianOptions(show_degrees=degrees, mark_node_retrograde=nodes),
        )
        _DOCUMENTS[key] = (ET.fromstring(north), ET.fromstring(south))
    return _DOCUMENTS[key]


# --- parsing helpers -------------------------------------------------------------


def unit(text: str) -> float:
    """A formatted coordinate on the unit square (no caption)."""
    return (float(text) - MARGIN) / SIDE


def font_of(text: str) -> float:
    return float(text) / SIDE


def of_class(root, css_class):
    return [element for element in root.iter() if element.get("class") == css_class]


def text_box(element):
    """The renderers' glyph-box model of a parsed ``<text>``."""
    x = unit(element.get("x"))
    y = unit(element.get("y"))
    font = font_of(element.get("font-size"))
    width = len(element.text) * CHAR * font
    anchor = element.get("text-anchor")
    x0 = {"start": x, "middle": x - width / 2.0, "end": x - width}[anchor]
    return ng.Box(x0, y - ASCENT * font, x0 + width, y - ASCENT * font + font)


def house_label_box(element):
    """The ``H<n>`` label with the helper's own width allowances (one ``H``
    at 0.80 em plus 0.66 em per digit), end-anchored like the renderer's."""
    x = unit(element.get("x"))
    y = unit(element.get("y"))
    font = font_of(element.get("font-size"))
    text = element.text
    assert text.startswith("H") and text[1:].isdigit(), text
    width = (0.80 + 0.66 * len(text[1:])) * font
    assert abs(width - ov.house_label_width(int(text[1:]), font)) < 1e-12
    assert width > len(text) * CHAR * font  # wider than the uniform model
    return ng.Box(x - width, y - ASCENT * font, x, y - ASCENT * font + font)


def line_box(element):
    x1 = unit(element.get("x1"))
    x2 = unit(element.get("x2"))
    y = unit(element.get("y1"))
    half = float(element.get("stroke-width")) / SIDE / 2.0
    return ng.Box(min(x1, x2), y - half, max(x1, x2), y + half)


def north_cells(root):
    cells = {}
    for group in of_class(root, "house"):
        texts = [
            child for child in group
            if child.get("class") in ("abbr", "deg", "overflow")
        ]
        cells[group.get("data-rashi")] = {
            "house": int(group.get("data-house")),
            "layout": group.get("data-layout"),
            "region": ng.REGION_BY_HOUSE[int(group.get("data-house"))],
            "numeral": next(c for c in group if c.get("class") == "numeral"),
            "texts": texts,
            "lines": [child for child in group if child.get("class") == "retro"],
            "rows": sum(
                1 for child in group if child.get("class") in ("abbr", "overflow")
            ),
            "abbr": [child for child in group if child.get("class") == "abbr"],
            "overflow": [c for c in group if c.get("class") == "overflow"],
        }
    return cells


def south_cells(root):
    cells = {}
    for group in of_class(root, "sign"):
        entries = [child for child in group if child.get("class") == "entry"]
        overflow = [child for child in group if child.get("class") == "overflow"]
        texts = [
            element
            for entry in entries
            for element in entry
            if element.get("class") in ("abbr", "degrees")
        ] + overflow
        rect = next(child for child in group if child.get("class") == "cell")
        x0 = unit(rect.get("x"))
        y0 = unit(rect.get("y"))
        cells[group.get("data-rashi")] = {
            "house": int(group.get("data-house")),
            "rect": ng.Box(
                x0,
                y0,
                x0 + float(rect.get("width")) / SIDE,
                y0 + float(rect.get("height")) / SIDE,
            ),
            "sign_label": next(c for c in group if c.get("class") == "sign-label"),
            "house_label": next(c for c in group if c.get("class") == "house-label"),
            "texts": texts,
            "lines": [
                element
                for entry in entries
                for element in entry
                if element.get("class") == "retro"
            ],
            "rows": len(entries) + len(overflow),
            "abbr": [
                element for entry in entries for element in entry
                if element.get("class") == "abbr"
            ],
        }
    return cells


# --- geometry checks -------------------------------------------------------------


def overlaps(first, second, tol: float = TOLERANCE) -> bool:
    return (
        first.x0 < second.x1 - tol
        and second.x0 < first.x1 - tol
        and first.y0 < second.y1 - tol
        and second.y0 < first.y1 - tol
    )


def gap(first, second) -> float:
    dx = max(second.x0 - first.x1, first.x0 - second.x1, 0.0)
    dy = max(second.y0 - first.y1, first.y0 - second.y1, 0.0)
    return math.hypot(dx, dy)


#: Half a formatting quantum (0.005 units) plus float noise: a renderer's own
#: two-decimal output may sit this far from the exact plan.
FORMAT_SLACK = 0.0051 / SIDE


def inside(outer, box, tol: float = FORMAT_SLACK) -> bool:
    return (
        outer.x0 - tol <= box.x0
        and box.x1 <= outer.x1 + tol
        and outer.y0 - tol <= box.y0
        and box.y1 <= outer.y1 + tol
    )


def edge_distance(box, polygon) -> float:
    points = list(box.corners)
    for index in range(4):
        (x0, y0), (x1, y1) = box.corners[index], box.corners[(index + 1) % 4]
        points.append(((x0 + x1) / 2.0, (y0 + y1) / 2.0))
    count = len(polygon)
    return min(
        ng.distance_to_segment(point, polygon[i], polygon[(i + 1) % count])
        for point in points
        for i in range(count)
    )


def assert_in_polygon(box, polygon, what):
    for corner in box.corners:
        assert ng.point_in_polygon(corner, polygon), f"{what}: corner {corner} outside"
    distance = edge_distance(box, polygon)
    assert distance >= CLEARANCE - TOLERANCE, f"{what}: edge clearance {distance}"


def assert_in_rect(box, rect, what):
    for value in (
        box.x0 - rect.x0, rect.x1 - box.x1, box.y0 - rect.y0, rect.y1 - box.y1
    ):
        assert value >= CLEARANCE - TOLERANCE, f"{what}: clearance {value}"


def numeral_box(element):
    """The numeral's glyph box: chars x 0.68 em by the digit height, centred
    on the parsed (central-baseline) position."""
    x = unit(element.get("x"))
    y = unit(element.get("y"))
    font = font_of(element.get("font-size"))
    assert font == NUMERAL_FONT
    half_width = len(element.text) * CHAR * font / 2.0
    half_height = DIGIT_HEIGHT * font / 2.0
    return ng.Box(x - half_width, y - half_height, x + half_width, y + half_height)


def natal_font(cell) -> float:
    fonts = {element.get("font-size") for element in cell["abbr"]}
    fonts |= {element.get("font-size") for element in cell.get("overflow", [])}
    assert len(fonts) == 1
    return font_of(fonts.pop())


def north_natal_box(cell, degrees: bool):
    """The renderer's text plan box, rebuilt from the parsed cell."""
    if cell["rows"] == 0:
        return None
    font = natal_font(cell)
    region = cell["region"]
    if cell["layout"] == "stacked":
        return ng.side_box(
            region,
            ng.side_rows_height(len(cell["abbr"]), font, degrees, bool(cell["overflow"])),
            ng.side_width_budget(font, degrees),
        )
    box = region.box
    return ng.Box(
        box.x0 + 0.01,
        box.y0,
        box.x0 + 0.01 + 6.12 * font,
        box.y0 + cell["rows"] * 1.45 * font,
    )


def south_natal_box(cell, rect):
    if cell["rows"] == 0:
        return None
    font = natal_font(cell)
    top = rect.y0 + 0.010 + 0.032
    return ng.Box(
        rect.x0 + 0.020,
        top,
        rect.x0 + 0.020 + 6.12 * font,
        top + cell["rows"] * 1.45 * font,
    )


def marker_glyph_box(marker):
    x = unit(marker["x"])
    y = unit(marker["y"])
    x0 = {
        "start": x, "middle": x - MARKER_WIDTH / 2.0, "end": x - MARKER_WIDTH,
    }[marker["anchor"]]
    top = y - ASCENT * MARKER_FONT
    return ng.Box(x0, top, x0 + MARKER_WIDTH, top + MARKER_FONT)


def row_boxes(slot, degrees: bool):
    """Every transit text box the slot offers: ``(rung, box)`` pairs."""
    out = []
    for rung in slot["rungs"]:
        font = font_of(rung["font_size"])
        x = unit(rung["x"])
        if slot["layout"] == "inline":
            width = INLINE_EMS[degrees] * font
            for y in rung["rows"]:
                baseline = unit(y)
                out.append(
                    (rung, ng.Box(x, baseline - ASCENT * font, x + width,
                                  baseline - ASCENT * font + font))
                )
        else:
            width = STACKED_EMS[degrees] * font
            for entry in rung["entries"]:
                for key in ("abbr_y", "deg_y"):
                    if key not in entry:
                        continue
                    baseline = unit(entry[key])
                    out.append(
                        (rung, ng.Box(x, baseline - ASCENT * font, x + width,
                                      baseline - ASCENT * font + font))
                    )
    return out


def rung_count(rung) -> int:
    return len(rung["rows"]) if "rows" in rung else len(rung["entries"])


# --- A. the block's shape ----------------------------------------------------------


@pytest.mark.parametrize("name", REFERENCE_CHARTS + ("transit_jalandhar",))
def test_the_block_has_the_schema_and_the_key_order(name):
    block = block_for(name)

    assert list(block) == BLOCK_KEYS
    assert block["schema"] == "vedic_chart.overlay/1"
    assert block["prefix"] == "T:"
    assert block["font_family"] == '"DejaVu Sans", Arial, Helvetica, sans-serif'
    assert block["marker_font_size"] == "20.00"
    assert list(block["slots"]) == ["north", "south"]
    for style in ("north", "south"):
        assert list(block["slots"][style]) == RASHI_KEYS
        for slot in block["slots"][style].values():
            assert list(slot) == SLOT_KEYS
            assert type(slot["house"]) is int
            assert type(slot["natal_rows"]) is int
    for entry in block["entries"]:
        assert list(entry) == ENTRY_KEYS


def test_the_block_holds_only_json_values_and_no_float():
    def walk(value):
        if isinstance(value, dict):
            assert all(type(key) is str for key in value)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        else:
            assert value is None or type(value) in (str, int, bool), repr(value)

    for name in REFERENCE_CHARTS:
        for degrees in (True, False):
            block = block_for(name, degrees)
            walk(block)
            text = json.dumps(block, ensure_ascii=False, allow_nan=False)
            assert json.loads(text) == block


@pytest.mark.parametrize("name", REFERENCE_CHARTS + LAGNA_CHARTS + ("transit_jalandhar",))
@pytest.mark.parametrize("degrees", (True, False))
def test_entries_are_the_nine_grahas_in_graha_order(name, degrees):
    chart = overlay_chart(name)
    entries = block_for(name, degrees)["entries"]

    assert [entry["key"] for entry in entries] == GRAHA_KEYS
    assert len({entry["key"] for entry in entries}) == 9
    for entry, graha in zip(entries, Graha):
        assert entry["abbr"] == ni.ABBREVIATIONS[graha]
        assert len(entry["abbr"]) == 2
        assert entry["rashi_number"] == chart.grahas[graha].rashi_number
        assert type(entry["underline"]) is bool
        if degrees:
            assert re.fullmatch(r"[0-9]{1,2}°[0-9]{2}′", entry["degree_text"])
        else:
            assert entry["degree_text"] == ""


@pytest.mark.parametrize("name", REFERENCE_CHARTS)
@pytest.mark.parametrize("degrees", (True, False))
def test_degree_text_is_the_renderers_own_text(name, degrees):
    north, south = documents_for(name, degrees)
    entries = {entry["key"]: entry for entry in block_for(name, degrees)["entries"]}

    north_degrees = {}
    for element in of_class(north, "deg"):
        key = element.get("data-graha")
        if key != "lagna":
            north_degrees.setdefault(key, set()).add(element.text)
    south_degrees = {}
    for group in of_class(south, "entry"):
        key = group.get("data-graha")
        for element in group:
            if element.get("class") == "degrees" and key != "lagna":
                south_degrees.setdefault(key, set()).add(element.text)

    if not degrees:
        assert north_degrees == {} and south_degrees == {}
        assert {entry["degree_text"] for entry in entries.values()} == {""}
        return
    assert sorted(north_degrees) == sorted(GRAHA_KEYS)
    assert sorted(south_degrees) == sorted(GRAHA_KEYS)
    for key, entry in entries.items():
        assert north_degrees[key] == {entry["degree_text"]}, key
        assert south_degrees[key] == {entry["degree_text"]}, key


@pytest.mark.parametrize(
    "name", REFERENCE_CHARTS + ("all_retrograde", "nodes_unmarked", "transit_jalandhar")
)
@pytest.mark.parametrize("nodes", (False, True))
def test_underline_is_the_presence_of_the_renderers_retrograde_line(name, nodes):
    north, south = documents_for(name, True, nodes)
    marked_north = {element.get("data-graha") for element in of_class(north, "retro")}
    marked_south = {
        group.get("data-graha")
        for group in of_class(south, "entry")
        if any(child.get("class") == "retro" for child in group)
    }
    chart = overlay_chart(name)
    shown = {
        element.get("data-graha") for element in of_class(north, "abbr")
    }

    for entry in block_for(name, True, nodes)["entries"]:
        graha = Graha(entry["key"])
        placement = chart.grahas[graha]
        expected = placement.is_retrograde and (
            graha not in (Graha.RAHU, Graha.KETU) or nodes
        )
        assert entry["underline"] is expected
        if entry["key"] in shown:
            assert (entry["key"] in marked_north) is expected, entry["key"]
            assert (entry["key"] in marked_south) is expected, entry["key"]


def test_node_marking_changes_entries_only():
    plain = block_for("jalandhar", True, False)
    marked = block_for("jalandhar", True, True)

    assert plain["slots"] == marked["slots"]
    nodes = {"rahu", "ketu"}
    for first, second in zip(plain["entries"], marked["entries"]):
        if first["key"] in nodes:
            assert first["underline"] is False
            assert second["underline"] is True  # the Mean Node always moves back
        else:
            assert first == second


# --- B. the slots: houses, natal rows, layouts --------------------------------------


@pytest.mark.parametrize("name", LAGNA_CHARTS + REFERENCE_CHARTS + ("transit_jalandhar",))
def test_every_sign_has_its_house_identically_in_both_styles(name):
    chart = overlay_chart(name)
    slots = block_for(name)["slots"]
    house_of_sign = {house.rashi_number: house.number for house in chart.houses}

    for style in ("north", "south"):
        assert list(slots[style]) == RASHI_KEYS
        assert sorted(slot["house"] for slot in slots[style].values()) == list(
            range(1, 13)
        )
    for key in RASHI_KEYS:
        assert slots["north"][key]["house"] == slots["south"][key]["house"]
        assert slots["north"][key]["house"] == house_of_sign[int(key)]


@pytest.mark.parametrize("lagna", range(12))
def test_twelve_lagnas_rotate_the_houses_through_the_signs(lagna):
    slots = block_for(f"lagna_{lagna:02d}")["slots"]

    for number in range(1, 13):
        assert slots["north"][str(number)]["house"] == (number - 1 - lagna) % 12 + 1


@pytest.mark.parametrize(("name", "degrees"), GEOMETRY_CASES)
def test_natal_rows_and_layout_are_what_the_renderers_drew(name, degrees):
    north, south = documents_for(name, degrees)
    slots = block_for(name, degrees)["slots"]
    north_parsed = north_cells(north)
    south_parsed = south_cells(south)

    assert sorted(north_parsed, key=int) == RASHI_KEYS
    assert sorted(south_parsed, key=int) == RASHI_KEYS
    for key in RASHI_KEYS:
        slot = slots["north"][key]
        cell = north_parsed[key]
        assert slot["house"] == cell["house"]
        assert slot["layout"] == cell["layout"]
        assert slot["layout"] == ("stacked" if cell["house"] in SIDE_HOUSES else "inline")
        assert slot["natal_rows"] == cell["rows"]

        slot = slots["south"][key]
        cell = south_parsed[key]
        assert slot["house"] == cell["house"]
        assert slot["layout"] == "inline"
        assert slot["natal_rows"] == cell["rows"]


@pytest.mark.parametrize(("name", "degrees"), GEOMETRY_CASES)
def test_rungs_have_the_shape_of_their_layout(name, degrees):
    slots = block_for(name, degrees)["slots"]

    for style in ("north", "south"):
        for key, slot in slots[style].items():
            rungs = slot["rungs"]
            assert rungs, (style, key)
            assert rungs[-1]["font_size"] == FLOOR
            fonts = [rung["font_size"] for rung in rungs]
            assert all(font in LADDER for font in fonts)
            assert [LADDER.index(font) for font in fonts] == sorted(
                LADDER.index(font) for font in set(fonts)
            )
            counts = [rung_count(rung) for rung in rungs]
            # Capacity-distinct, empty rungs dropped, the floor always kept.
            for position, count in enumerate(counts[:-1]):
                assert count > 0
                if position:
                    assert count > counts[position - 1]
            if len(counts) > 1:
                assert counts[-1] >= counts[-2]
            for rung in rungs:
                assert COORDINATE.match(rung["x"])
                if slot["layout"] == "inline":
                    expected = ["font_size", "x", "deg_x", "rows"] if degrees else [
                        "font_size", "x", "rows"
                    ]
                    assert list(rung) == expected
                    for y in rung["rows"]:
                        assert COORDINATE.match(y)
                    if degrees:
                        font = float(rung["font_size"])
                        assert rung["deg_x"] == f"{float(rung['x']) + 3.17 * font:.2f}"
                else:
                    assert list(rung) == ["font_size", "x", "entries", "overflow_y"]
                    for entry in rung["entries"]:
                        assert list(entry) == (["abbr_y", "deg_y"] if degrees else ["abbr_y"])
                        for value in entry.values():
                            assert COORDINATE.match(value)
                    if rung["entries"]:
                        assert rung["overflow_y"] == rung["entries"][-1]["abbr_y"]
                    else:
                        assert rung["overflow_y"] is None
            marker = slot["marker"]
            if marker is not None:
                assert list(marker) == ["x", "y", "anchor"]
                assert COORDINATE.match(marker["x"]) and COORDINATE.match(marker["y"])
                expected_anchor = (
                    "end" if style == "south"
                    else "start" if slot["layout"] == "stacked" else "middle"
                )
                assert marker["anchor"] == expected_anchor


# --- C. geometry on the formatted coordinates ----------------------------------------


@pytest.mark.parametrize(("name", "degrees"), GEOMETRY_CASES)
def test_north_rows_and_markers_keep_every_clearance(name, degrees):
    north, _south = documents_for(name, degrees)
    slots = block_for(name, degrees)["slots"]["north"]

    for key, cell in north_cells(north).items():
        slot = slots[key]
        region = cell["region"]
        polygon = region.polygon
        numeral = numeral_box(cell["numeral"])
        assert cell["numeral"].text == key
        natal_elements = [text_box(e) for e in cell["texts"]] + [
            line_box(e) for e in cell["lines"]
        ]
        natal = north_natal_box(cell, degrees)
        # The plan box rebuilt from the parsed attributes holds every natal
        # element the renderer drew in that cell.
        for element in natal_elements:
            assert natal is not None and inside(natal, element), (key, element)

        for rung, box in row_boxes(slot, degrees):
            what = f"{name} north sign {key} rung {rung['font_size']}"
            assert_in_polygon(box, polygon, what)
            assert not overlaps(box, numeral), what
            if natal is not None:
                assert not overlaps(box, natal), what
            for element in natal_elements:
                assert not overlaps(box, element), what

        marker = slot["marker"]
        if marker is None:
            continue
        box = marker_glyph_box(marker)
        what = f"{name} north sign {key} marker"
        assert_in_polygon(box, polygon, what)
        assert gap(box, numeral) >= CLEARANCE - TOLERANCE, what
        if natal is not None:
            assert gap(box, natal) >= CLEARANCE - TOLERANCE, what
        for element in natal_elements:
            assert gap(box, element) >= CLEARANCE - TOLERANCE, what


@pytest.mark.parametrize(("name", "degrees"), GEOMETRY_CASES)
def test_south_rows_and_markers_keep_every_clearance(name, degrees):
    _north, south = documents_for(name, degrees)
    slots = block_for(name, degrees)["slots"]["south"]

    for key, cell in south_cells(south).items():
        slot = slots[key]
        rect = cell["rect"]
        sign = text_box(cell["sign_label"])
        house = house_label_box(cell["house_label"])
        label_bottom = rect.y0 + 0.010 + 0.032
        natal_elements = [text_box(e) for e in cell["texts"]] + [
            line_box(e) for e in cell["lines"]
        ]
        natal = south_natal_box(cell, rect)
        for element in natal_elements:
            assert natal is not None and inside(natal, element), (key, element)

        for rung, box in row_boxes(slot, degrees):
            what = f"{name} south sign {key} rung {rung['font_size']}"
            assert_in_rect(box, rect, what)
            assert box.y0 >= label_bottom - TOLERANCE, what
            assert not overlaps(box, sign) and not overlaps(box, house), what
            if natal is not None:
                assert not overlaps(box, natal), what
            for element in natal_elements:
                assert not overlaps(box, element), what

        marker = slot["marker"]
        inner = ng.Box(rect.x0 + 0.010, rect.y0 + 0.010, rect.x1 - 0.010, rect.y1 - 0.010)
        candidate_x0 = house.x0 - LABEL_GAP - MARKER_WIDTH
        if marker is None:
            # Null only where the label row truly has no room.
            assert candidate_x0 - sign.x1 < LABEL_GAP - TOLERANCE, (name, key)
            continue
        box = marker_glyph_box(marker)
        what = f"{name} south sign {key} marker"
        assert marker["y"] == cell["house_label"].get("y")
        assert box.x0 - sign.x1 >= LABEL_GAP - TOLERANCE, what
        assert house.x0 - box.x1 >= LABEL_GAP - TOLERANCE, what
        assert abs(house.x0 - box.x1 - LABEL_GAP) < 1e-6, what
        assert inside(inner, box, TOLERANCE), what
        assert box.y1 <= label_bottom + TOLERANCE, what
        for element in natal_elements:
            assert not overlaps(box, element), what


@pytest.mark.parametrize("lagna", range(12))
def test_the_south_marker_is_null_exactly_for_vrishabha_and_vrishchika(lagna):
    slots = block_for(f"lagna_{lagna:02d}")["slots"]["south"]

    for key, slot in slots.items():
        if key in ("2", "8"):
            assert slot["marker"] is None, key
        else:
            assert slot["marker"] is not None, key


@pytest.mark.parametrize("house", range(1, 13))
@pytest.mark.parametrize("count", OVERLAY_FILLS)
def test_every_north_cell_of_the_probed_fills_gets_a_marker(house, count):
    """Section 15 B: every North region with 0, 1, 2, 3 and 7 grahas."""
    chart = house_fill_d1(house, count)
    block = overlay_block(chart)
    slot = next(
        slot for slot in block["slots"]["north"].values() if slot["house"] == house
    )
    occupants = len(chart.house(house).occupants)

    assert occupants == count
    assert slot["marker"] is not None, (house, count)


@pytest.mark.parametrize("name", REFERENCE_CHARTS + ("transit_jalandhar",))
def test_every_north_cell_of_the_reference_charts_gets_a_marker(name):
    for key, slot in block_for(name)["slots"]["north"].items():
        assert slot["marker"] is not None, key


# --- D. the side houses (section 15 C) ------------------------------------------------

SIDE_EXPECTED = {
    0: [("32.00", 1), ("28.00", 2), ("22.00", 3), ("21.00", 3)],
    1: [("21.00", 1)],
    2: [("21.00", 0)],
    3: [("21.00", 0)],
    4: [("21.00", 0)],
}
SIDE_NATAL_ROWS = {0: 0, 1: 1, 2: 2, 3: 3, 4: 3}


@pytest.mark.parametrize("house", SIDE_HOUSES)
@pytest.mark.parametrize("count", sorted(SIDE_EXPECTED))
def test_side_house_rungs_follow_the_probed_capacities(house, count):
    chart = house_fill_d1(house, count) if count == 0 else count_in_house_d1(house, count)
    slot = next(
        slot
        for slot in overlay_block(chart)["slots"]["north"].values()
        if slot["house"] == house
    )

    assert slot["layout"] == "stacked"
    assert slot["natal_rows"] == SIDE_NATAL_ROWS[count]
    assert [(rung["font_size"], len(rung["entries"])) for rung in slot["rungs"]] == (
        SIDE_EXPECTED[count]
    )
    for rung in slot["rungs"]:
        assert (rung["overflow_y"] is None) is (rung["entries"] == [])
    assert slot["marker"] is not None
    assert slot["marker"]["anchor"] == "start"


def test_the_overflowing_side_house_marker_sits_below_the_natal_box():
    chart = count_in_house_d1(5, 4)
    north = ET.fromstring(render_north_indian_svg(chart))
    cell = north_cells(north)["1"]
    slot = overlay_block(chart)["slots"]["north"]["1"]

    assert cell["house"] == 5 and cell["overflow"]
    natal = north_natal_box(cell, True)
    box = marker_glyph_box(slot["marker"])
    assert box.y0 >= natal.y1 + CLEARANCE - TOLERANCE
    assert box.y0 - natal.y1 < CLEARANCE + 0.0001


# --- E. options -----------------------------------------------------------------------


@pytest.mark.parametrize("name", REFERENCE_CHARTS + LAGNA_CHARTS)
def test_the_width_gates_with_the_prefix(name):
    """Section 15 D: with degrees kites and South cells admit 28 and below,
    triangles 26 and below; without degrees every ladder font passes."""
    with_degrees = block_for(name, True)["slots"]
    without = block_for(name, False)["slots"]

    for key in RASHI_KEYS:
        for style in ("north", "south"):
            slot = with_degrees[style][key]
            if slot["layout"] != "inline":
                continue
            house = slot["house"]
            limit = "26.00" if style == "north" and house in (2, 6, 8, 12) else "28.00"
            fonts = [rung["font_size"] for rung in slot["rungs"]]
            assert all(LADDER.index(font) >= LADDER.index(limit) for font in fonts)
            if slot["natal_rows"] == 0:
                assert fonts[0] == limit
            plain = without[style][key]
            if plain["natal_rows"] == 0:
                assert plain["rungs"][0]["font_size"] == "32.00"
            for rung in plain["rungs"]:
                assert "deg_x" not in rung


def test_without_degrees_no_rung_carries_a_degree_coordinate():
    for name in REFERENCE_CHARTS + FILL_CHARTS[:20]:
        for style in ("north", "south"):
            for slot in block_for(name, False)["slots"][style].values():
                for rung in slot["rungs"]:
                    assert "deg_x" not in rung
                    for entry in rung.get("entries", []):
                        assert list(entry) == ["abbr_y"]


def test_the_block_is_deterministic():
    chart = case_chart("jalandhar")
    first = overlay_block(chart)
    second = overlay_block(chart)

    assert first == second
    assert first is not second
    assert json.dumps(first, ensure_ascii=False) == json.dumps(second, ensure_ascii=False)
    # A chart rebuilt from scratch gives the same block.
    assert overlay_block(helpers.jalandhar_d1()) == first
    # The result is a fresh structure each time.
    first["slots"]["north"]["1"]["rungs"].clear()
    assert overlay_block(chart) == second


@pytest.mark.parametrize(
    "chart", [None, "jalandhar", 42, {"houses": ()}, object()]
)
def test_a_value_that_is_not_a_d1chart_is_refused(chart):
    with pytest.raises(ValueError):
        overlay_block(chart)


def test_a_birth_chart_is_refused():
    with pytest.raises(ValueError):
        overlay_block(case_chart("jalandhar").source)


@pytest.mark.parametrize("field", ["show_degrees", "mark_node_retrograde"])
@pytest.mark.parametrize("value", [1, 0, None, "True", 1.0])
def test_flags_must_be_exactly_bool(field, value):
    with pytest.raises(ValueError):
        overlay_block(case_chart("jalandhar"), **{field: value})


def test_the_flags_are_keyword_only():
    with pytest.raises(TypeError):
        overlay_block(case_chart("jalandhar"), True)  # noqa: FBT003


# --- F. constants pinned to the renderers -------------------------------------------


def test_the_shared_conventions_equal_the_renderers():
    assert ov.ABBREVIATIONS == ni.ABBREVIATIONS == si.ABBREVIATIONS
    assert ov.NODES == ni.NODES == si.NODES
    assert ov.DEGREE_SIGN == ni.DEGREE_SIGN == si.DEGREE_SIGN
    assert ov.PRIME_SIGN == ni.PRIME_SIGN == si.PRIME_SIGN
    assert ov.LAYOUT_INLINE == ni.LAYOUT_INLINE == si.LAYOUT_INLINE
    assert ov.LAYOUT_STACKED == ni.LAYOUT_STACKED

    style = ov._STYLE
    assert style.font_family == ni._STYLE.font_family == si._STYLE.font_family
    assert style.numeral_font == ni._STYLE.numeral_font == si._STYLE.numeral_font
    assert style.label_font == si._STYLE.label_font == sg.LABEL_FONT
    assert style.ink == ni._STYLE.ink == si._STYLE.ink
    assert style.chart_side == ni._STYLE.chart_side == si._STYLE.chart_side
    assert style.margin == ni._STYLE.margin == si._STYLE.margin
    assert style.marker_font == 0.020

    for value in (0.0, 1.005, 12.345, 523.76, 999.999, 1080.0, 40.0 + 0.2538 * 1000):
        assert ov._number(value) == ni._number(value) == si._number(value)
    chart = case_chart("jalandhar")
    for graha in Graha:
        dms = chart.grahas[graha].dms(0)
        assert ov._degree_text(dms) == ni._degree_text(dms) == si._degree_text(dms)


def test_the_transit_budgets_are_the_specified_numbers():
    assert ov.PREFIX == "T:"
    assert math.isclose(ov.TRANSIT_WIDTH_EMS, 7.48)
    assert math.isclose(ov.TRANSIT_ABBR_EMS, 2.72)
    assert math.isclose(ov.TRANSIT_DEG_OFFSET, 3.17)
    assert ov.MARKER_CHARS == 4
    assert ov.MARKER_CLEARANCE == ng.MIN_BOX_CLEARANCE == CLEARANCE
    assert math.isclose(ov.MARKER_LABEL_GAP_EMS * ov._STYLE.label_font * SIDE, 9.0)
    assert ng.CHAR_ADVANCE == sg.CHAR_ADVANCE == CHAR
    assert ng.SIZE_LADDER == sg.SIZE_LADDER


def test_the_module_never_calls_round_and_has_no_caption_parameter():
    tree = ast.parse(
        (helpers.RENDER_PACKAGE / "overlay.py").read_text(encoding="utf-8")
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            assert not (isinstance(function, ast.Name) and function.id == "round")
            assert not (
                isinstance(function, ast.Attribute) and function.attr == "round"
            )
    assert list(inspect.signature(overlay_block).parameters) == [
        "chart", "show_degrees", "mark_node_retrograde",
    ]
    assert ov.__all__ == ["overlay_block"]


# --- G. the worked example (section 5.7) ----------------------------------------------


def test_the_worked_example_slots_are_the_specified_values():
    north = block_for("jalandhar")["slots"]["north"]
    south = block_for("jalandhar")["slots"]["south"]

    assert north["12"] == {
        "house": 1, "layout": "inline", "natal_rows": 2,
        "rungs": [
            {"font_size": "28.00", "x": "435.00", "deg_x": "523.76",
             "rows": ["293.80", "334.40", "375.00"]},
            {"font_size": "21.00", "x": "435.00", "deg_x": "501.57",
             "rows": ["288.55", "319.00", "349.45", "379.90"]},
        ],
        "marker": {"x": "540.00", "y": "376.66", "anchor": "middle"},
    }
    assert north["4"] == {
        "house": 5, "layout": "stacked", "natal_rows": 1,
        "rungs": [
            {"font_size": "21.00", "x": "65.00",
             "entries": [{"abbr_y": "860.55", "deg_y": "891.00"}],
             "overflow_y": "860.55"},
        ],
        "marker": {"x": "65.00", "y": "866.40", "anchor": "start"},
    }
    assert north["7"] == {
        "house": 8, "layout": "inline", "natal_rows": 2,
        "rungs": [{"font_size": "21.00", "x": "695.00", "deg_x": "761.57", "rows": []}],
        "marker": {"x": "790.00", "y": "889.74", "anchor": "middle"},
    }
    assert north["11"]["marker"] == {"x": "790.00", "y": "196.66", "anchor": "middle"}
    assert [
        (rung["font_size"], len(rung["entries"])) for rung in north["2"]["rungs"]
    ] == SIDE_EXPECTED[0]
    assert south["7"]["rungs"] == [
        {"font_size": "28.00", "x": "560.00", "deg_x": "648.76", "rows": ["945.80", "986.40"]},
        {"font_size": "24.00", "x": "560.00", "deg_x": "636.08",
         "rows": ["942.80", "977.60", "1012.40"]},
        {"font_size": "21.00", "x": "560.00", "deg_x": "626.57",
         "rows": ["940.55", "971.00", "1001.45"]},
    ]
    assert south["2"]["marker"] is None and south["2"]["natal_rows"] == 0


def test_the_worked_example_transit_entries():
    entries = block_for("transit_jalandhar")["entries"]
    chart = overlay_chart("transit_jalandhar")

    assert chart.lagna.rashi_name == "Makara"
    assert [
        (e["abbr"], e["degree_text"], e["rashi_number"], e["underline"]) for e in entries
    ] == [
        ("Su", "20°52′", 6, False),
        ("Mo", "22°49′", 5, False),
        ("Me", "15°34′", 7, False),
        ("Ve", "13°45′", 7, True),
        ("Ma", "11°41′", 4, False),
        ("Ju", "26°38′", 4, False),
        ("Sa", "16°45′", 12, True),
        ("Ra", "3°05′", 11, False),
        ("Ke", "3°05′", 5, False),
    ]


def page_outcome(slot, count):
    """The page's capacity rule of section 5.3, for the worked example."""
    for rung in slot["rungs"]:
        if rung_count(rung) >= count:
            return ("shown", rung["font_size"])
    rows = rung_count(slot["rungs"][-1])
    if rows >= 2:
        return ("row", rows - 1)
    if rows == 1:
        return ("row", 0)
    return ("marker",) if slot["marker"] is not None else ("panel",)


def test_the_worked_example_outcome_per_style():
    natal = block_for("jalandhar")["slots"]
    counts = {}
    for entry in block_for("transit_jalandhar")["entries"]:
        counts[entry["rashi_number"]] = counts.get(entry["rashi_number"], 0) + 1

    north = {sign: page_outcome(natal["north"][str(sign)], k) for sign, k in counts.items()}
    south = {sign: page_outcome(natal["south"][str(sign)], k) for sign, k in counts.items()}
    assert north == {
        12: ("shown", "28.00"),
        4: ("row", 0),
        5: ("shown", "26.00"),
        6: ("shown", "28.00"),
        7: ("marker",),
        11: ("marker",),
    }
    assert south == {sign: ("shown", "28.00") for sign in (12, 4, 5, 6, 7, 11)}


# --- H. goldens -----------------------------------------------------------------------


def updating() -> bool:
    return os.environ.get(UPDATE_ENVIRONMENT_VARIABLE) == "1"


def golden_text(block: dict) -> str:
    return json.dumps(block, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


@pytest.mark.parametrize("name", REFERENCE_CHARTS)
def test_golden_blocks_match_exactly(name):
    text = golden_text(overlay_block(case_chart(name)))
    path = OVERLAY_GOLDEN_DIR / f"{name}.json"
    if updating():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert path.exists(), (
        f"golden file {path} is missing; regenerate the set with "
        f"{UPDATE_ENVIRONMENT_VARIABLE}=1"
    )
    assert path.read_text(encoding="utf-8") == text, (
        f"the block differs from {path}; if the change is intended, regenerate "
        f"with {UPDATE_ENVIRONMENT_VARIABLE}=1 and review the diff"
    )


def test_the_golden_set_is_exactly_the_two_reference_charts():
    if updating():
        pytest.skip("the set is being regenerated")
    stored = sorted(path.name for path in OVERLAY_GOLDEN_DIR.glob("*"))

    assert stored == ["bharatpur.json", "jalandhar.json"]
    for name in REFERENCE_CHARTS:
        text = (OVERLAY_GOLDEN_DIR / f"{name}.json").read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert json.loads(text) == overlay_block(case_chart(name))
