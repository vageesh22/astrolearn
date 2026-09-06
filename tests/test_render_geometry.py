"""Tests for Layer 10's geometry and layout arithmetic (section 10.B).

Two halves. The first proves the *diagram*: the twelve regions partition the
unit square, their edges are shared exactly as the specification's edge table
says, and every label box and numeral anchor sits where it claims to. The
200 x 200 grid sweep is the numerical companion to the structural argument of
section 3, not a substitute for it.

The second proves the *layout* of real renders: for every case the semantic
suite exercises, each row's bounding box and each retrograde underline lands
inside its label box, the ``+n`` indicator takes the last row, the chosen size
comes from the ladder and degrees are never dropped to make something fit.
Those are read back out of the rendered document, so they test what a viewer
would actually be shown rather than an internal intention.
"""

import xml.etree.ElementTree as ET

import pytest

from render_helpers import CASE_NAMES, case_chart, case_options
from vedic_chart.render import render_north_indian_svg
from vedic_chart.render.north_indian_geometry import (
    ASCENT,
    BAND_PADDING,
    DEG_OFFSET,
    DESCENT,
    DRAWN_SEGMENTS,
    EXPECTED_AREA,
    FLOOR_SIZE,
    KITE,
    KITE_AREA,
    LEFT_INSET,
    LINE_HEIGHT,
    MIN_BOX_CLEARANCE,
    OUTER_SEGMENTS,
    REGIONS,
    REGION_BY_HOUSE,
    RETRO_DROP,
    RETRO_STROKE,
    SIZE_LADDER,
    TRIANGLE,
    TRIANGLE_AREA,
    ABBR_SLOT,
    band_baseline,
    band_height,
    capacity,
    character_budget,
    clearance_from_drawn_segments,
    entry_width_budget,
    is_sub_segment,
    legend_entries_per_line,
    legend_gap,
    legend_indent,
    legend_slot_width,
    legend_slot_x,
    point_in_polygon,
    polygon_area,
    ray_cast_inside,
    row_baseline,
    row_start_x,
    same_segment,
    select_size,
    width_gated_size,
    wrap_text,
)

SVG = "{http://www.w3.org/2000/svg}"
CHART_SIDE = 1000.0
CHART_LEFT = 40.0
CANVAS_WIDTH = 1080.0
MARGIN = 40.0
CHART_GAP = 30.0
LEGEND_FONT = 22.0
LEGEND_PITCH = 30
CAPTION_FONT = 24.0
CAPTION_PITCH = 32
TOLERANCE = 0.01


# --- the diagram -----------------------------------------------------------


def test_there_are_twelve_regions_numbered_one_to_twelve():
    assert [region.house for region in REGIONS] == list(range(1, 13))
    assert sorted(REGION_BY_HOUSE) == list(range(1, 13))


def test_region_areas_are_an_eighth_or_a_sixteenth_and_sum_to_one():
    for region in REGIONS:
        assert polygon_area(region.polygon) == pytest.approx(
            EXPECTED_AREA[region.kind], abs=1e-12
        )
    total = sum(polygon_area(region.polygon) for region in REGIONS)
    assert total == pytest.approx(1.0, abs=1e-12)
    kites = [r for r in REGIONS if r.kind == KITE]
    triangles = [r for r in REGIONS if r.kind == TRIANGLE]
    assert len(kites) == 4 and len(triangles) == 8
    assert 4 * KITE_AREA + 8 * TRIANGLE_AREA == pytest.approx(1.0)


def test_every_region_edge_is_a_sub_segment_of_a_drawn_segment():
    for region in REGIONS:
        for edge in region.edges:
            containers = [
                segment
                for segment in DRAWN_SEGMENTS
                if is_sub_segment(edge, segment)
            ]
            assert containers, f"house {region.house} edge {edge} is not drawn"


def test_every_edge_is_shared_with_exactly_one_neighbour_or_lies_outside():
    for region in REGIONS:
        for edge in region.edges:
            on_outer = any(
                is_sub_segment(edge, segment) for segment in OUTER_SEGMENTS
            )
            neighbours = [
                other.house
                for other in REGIONS
                if other.house != region.house
                and any(same_segment(edge, candidate) for candidate in other.edges)
            ]
            if on_outer:
                assert neighbours == [], (
                    f"outer edge {edge} of house {region.house} has neighbours "
                    f"{neighbours}"
                )
            else:
                assert len(neighbours) == 1, (
                    f"interior edge {edge} of house {region.house} is shared "
                    f"with {neighbours}"
                )


def test_the_named_edge_pairs_of_section_three():
    """Spot checks quoted in the specification: T-E1 and E1-O."""
    house1 = REGION_BY_HOUSE[1]
    edge_t_e1 = ((0.5, 0.0), (0.75, 0.25))
    edge_e1_o = ((0.75, 0.25), (0.5, 0.5))
    assert any(same_segment(edge_t_e1, edge) for edge in house1.edges)
    assert any(same_segment(edge_e1_o, edge) for edge in house1.edges)
    assert any(
        same_segment(edge_t_e1, edge) for edge in REGION_BY_HOUSE[12].edges
    )
    assert any(
        same_segment(edge_e1_o, edge) for edge in REGION_BY_HOUSE[10].edges
    )


def test_a_two_hundred_square_grid_lands_in_exactly_one_region():
    """The numerical companion to the planar-subdivision argument."""
    steps = 200
    interior_points = 0
    boundary_points = 0
    for i in range(steps):
        x = (i + 0.5) / steps
        for j in range(steps):
            y = (j + 0.5) / steps
            point = (x, y)
            if clearance_from_drawn_segments(point) > 1e-6:
                hits = [
                    region.house
                    for region in REGIONS
                    if ray_cast_inside(point, region.polygon)
                ]
                assert len(hits) == 1, f"{point} lies in regions {hits}"
                interior_points += 1
            else:
                hits = [
                    region.house
                    for region in REGIONS
                    if point_in_polygon(
                        point, region.polygon, include_boundary=True
                    )
                ]
                assert hits, f"{point} lies on a segment but in no region"
                boundary_points += 1
    assert interior_points + boundary_points == steps * steps
    assert boundary_points > 0, "the grid never touched a drawn segment"


def test_label_box_corners_are_inside_their_region_with_clearance():
    worst = 1.0
    for region in REGIONS:
        for corner in region.box.corners:
            assert point_in_polygon(corner, region.polygon), (
                f"house {region.house} corner {corner} is outside its region"
            )
            clearance = clearance_from_drawn_segments(corner)
            worst = min(worst, clearance)
            assert clearance >= MIN_BOX_CLEARANCE, (
                f"house {region.house} corner {corner} clears only {clearance}"
            )
    # The specification records 0.0177 as the tightest corner in the table.
    assert worst == pytest.approx(0.0177, abs=5e-5)


def test_numeral_anchors_are_inside_the_region_and_outside_the_box():
    for region in REGIONS:
        assert point_in_polygon(region.numeral, region.polygon)
        assert not region.box.contains(region.numeral)


def test_box_dimensions_match_the_specification_table():
    expected = {
        1: (0.23, 0.22), 2: (0.21, 0.10), 3: (0.145, 0.12),
        4: (0.22, 0.23), 5: (0.145, 0.12), 6: (0.21, 0.10),
        7: (0.23, 0.22), 8: (0.21, 0.10), 9: (0.145, 0.12),
        10: (0.22, 0.23), 11: (0.145, 0.12), 12: (0.21, 0.10),
    }
    for region in REGIONS:
        width, height = expected[region.house]
        assert region.box.width == pytest.approx(width, abs=1e-12)
        assert region.box.height == pytest.approx(height, abs=1e-12)


# --- the sizing ladder -----------------------------------------------------


def test_the_size_ladder_is_the_documented_one():
    assert SIZE_LADDER == (0.032, 0.030, 0.028, 0.026, 0.024, 0.022, 0.021)
    assert FLOOR_SIZE == 0.021


CAPACITY_TABLE = {
    0.22: {0.032: 4, 0.030: 5, 0.028: 5, 0.026: 5, 0.024: 6, 0.022: 6, 0.021: 7},
    0.23: {0.032: 4, 0.030: 5, 0.028: 5, 0.026: 6, 0.024: 6, 0.022: 7, 0.021: 7},
    0.12: {0.022: 3, 0.021: 3},
    0.10: {0.032: 2, 0.030: 2, 0.028: 2, 0.026: 2, 0.024: 2, 0.022: 3, 0.021: 3},
}


@pytest.mark.parametrize("height", sorted(CAPACITY_TABLE))
def test_the_capacity_table_of_section_six(height):
    for size, expected in CAPACITY_TABLE[height].items():
        assert capacity(height, size) == expected, (height, size)


def test_the_capacity_table_covers_every_label_box():
    for region in REGIONS:
        height = round(region.box.height, 3)
        assert height in CAPACITY_TABLE
        gate = width_gated_size(region.box.width)
        for size in SIZE_LADDER:
            if size > gate:
                continue
            assert capacity(region.box.height, size) == CAPACITY_TABLE[height][size]


def test_the_width_gate_admits_what_section_six_says():
    assert entry_width_budget(0.032) == pytest.approx(0.20584, abs=1e-12)
    assert width_gated_size(0.23) == 0.032
    assert width_gated_size(0.22) == 0.032
    assert width_gated_size(0.21) == 0.032
    assert width_gated_size(0.145) == 0.022
    assert entry_width_budget(0.022) == pytest.approx(0.14464, abs=1e-12)
    assert 0.145 - entry_width_budget(0.022) == pytest.approx(0.00036, abs=1e-9)
    assert entry_width_budget(0.024) > 0.145


@pytest.mark.parametrize(
    "house,count,expected",
    [
        (1, 10, (0.021, 6, True)),    # nine grahas plus the Lagna entry
        (2, 9, (0.021, 2, True)),
        (3, 9, (0.021, 2, True)),
        (3, 2, (0.022, 2, False)),
        (3, 3, (0.022, 3, False)),
        (3, 4, (0.021, 2, True)),
        (1, 7, (0.021, 7, False)),    # house 1 with six occupants
        (1, 2, (0.032, 2, False)),
        (12, 2, (0.032, 2, False)),
        (1, 0, (0.032, 0, False)),
    ],
)
def test_select_size_reproduces_the_worked_examples(house, count, expected):
    box = REGION_BY_HOUSE[house].box

    assert select_size(count, box.width, box.height) == expected


def test_a_size_depends_only_on_the_box_and_the_count():
    box = REGION_BY_HOUSE[1].box
    first = select_size(5, box.width, box.height)

    assert select_size(5, box.width, box.height) == first


def test_overflow_always_leaves_room_for_at_least_two_entries():
    for region in REGIONS:
        size, shown, overflow = select_size(
            99, region.box.width, region.box.height
        )
        assert overflow is True
        assert size == FLOOR_SIZE
        assert shown >= 2
        assert shown + 1 == capacity(region.box.height, FLOOR_SIZE)


# --- wrapping and bands ----------------------------------------------------


def test_character_budgets_are_fifty_five_and_sixty():
    assert character_budget(CAPTION_FONT) == 55
    assert character_budget(LEGEND_FONT) == 60


@pytest.mark.parametrize("budget", [5, 12, 55, 60])
def test_wrapping_never_exceeds_the_budget_and_never_drops_text(budget):
    samples = [
        "a b c",
        "x" * 300,
        "short " + "y" * (budget * 3) + " tail",
        "  spaced   out   words  ",
        "",
    ]
    for text in samples:
        lines = wrap_text(text, budget)
        assert lines
        assert all(len(line) <= budget for line in lines)
        assert "".join(lines).replace(" ", "") == text.replace(" ", "")


def test_wrapping_hard_splits_at_exactly_the_budget():
    text = "z" * 120

    lines = wrap_text(text, 55)

    assert lines == ["z" * 55, "z" * 55, "z" * 10]


def test_wrapping_is_greedy_at_whitespace():
    assert wrap_text("aaa bbb ccc", 7) == ["aaa bbb", "ccc"]


def test_band_geometry_matches_the_specification():
    assert band_height(5, LEGEND_PITCH) == 182
    assert band_height(3, CAPTION_PITCH) == 128
    assert band_baseline(0.0, 0, CAPTION_FONT, CAPTION_PITCH) == 40.0
    assert band_baseline(0.0, 2, LEGEND_FONT, LEGEND_PITCH) == 98.0
    # The last descender stays inside the band by the documented margin.
    assert BAND_PADDING + CAPTION_PITCH - 1.25 * CAPTION_FONT == 18.0
    assert BAND_PADDING + LEGEND_PITCH - 1.25 * LEGEND_FONT == 18.5


def test_legend_slot_layout_matches_the_specification():
    assert legend_indent(LEGEND_FONT) == 66.0
    assert legend_gap(LEGEND_FONT) == 22.0
    assert legend_slot_width(LEGEND_FONT, True) == pytest.approx(140.8)
    assert legend_slot_width(LEGEND_FONT, False) == pytest.approx(33.0)
    assert legend_entries_per_line(LEGEND_FONT, True) == 5
    assert legend_entries_per_line(LEGEND_FONT, False) == 17
    assert legend_slot_x(0, LEGEND_FONT, True) == pytest.approx(66.0)
    last = legend_slot_x(4, LEGEND_FONT, True) + legend_slot_width(
        LEGEND_FONT, True
    )
    assert last <= 1000.0


# --- layout invariants over every rendered case ---------------------------


def parse_points(polygon_element):
    return [
        tuple(float(value) for value in pair.split(","))
        for pair in polygon_element.get("points").split()
    ]


def house_layout(root):
    """Yield ``(house_number, group, chart_top)`` for each house group."""
    groups = {
        int(group.get("data-house")): group
        for group in root.iter()
        if group.get("class") == "house"
    }
    polygon = [
        child for child in groups[1] if child.get("class") == "cell"
    ][0]
    chart_top = min(point[1] for point in parse_points(polygon))
    return groups, chart_top


@pytest.mark.parametrize("name", CASE_NAMES)
def test_every_row_and_underline_stays_inside_its_label_box(name):
    chart = case_chart(name)
    options = case_options(name)
    root = ET.fromstring(render_north_indian_svg(chart, options))
    groups, chart_top = house_layout(root)

    for number, group in groups.items():
        region = REGION_BY_HOUSE[number]
        box = region.box
        left = CHART_LEFT + box.x0 * CHART_SIDE
        right = CHART_LEFT + box.x1 * CHART_SIDE
        top = chart_top + box.y0 * CHART_SIDE
        bottom = chart_top + box.y1 * CHART_SIDE

        abbrs = [c for c in group if c.get("class") == "abbr"]
        degrees = [c for c in group if c.get("class") == "deg"]
        retros = [c for c in group if c.get("class") == "retro"]
        overflows = [c for c in group if c.get("class") == "overflow"]

        house = chart.house(number)
        entry_count = len(house.occupants) + (1 if number == 1 else 0)
        size, shown, overflow = select_size(entry_count, box.width, box.height)
        assert size in SIZE_LADDER
        assert len(abbrs) == (shown if overflow else entry_count)
        assert bool(overflows) is (overflow and entry_count > 0)

        font = size * CHART_SIDE
        expected_x = CHART_LEFT + row_start_x(box.x0) * CHART_SIDE

        rows = abbrs + overflows
        for index, element in enumerate(rows):
            assert float(element.get("font-size")) == pytest.approx(
                font, abs=TOLERANCE
            )
            assert float(element.get("x")) == pytest.approx(
                expected_x, abs=TOLERANCE
            )
            baseline = float(element.get("y"))
            expected_baseline = (
                chart_top + row_baseline(box.y0, index, size) * CHART_SIDE
            )
            assert baseline == pytest.approx(expected_baseline, abs=TOLERANCE)
            assert baseline - ASCENT * font >= top - TOLERANCE
            assert baseline + DESCENT * font <= bottom + TOLERANCE

        # The +n indicator, when present, owns the last row and nothing follows.
        if overflows:
            assert rows[-1] is overflows[0]
            assert len(rows) == capacity(box.height, size)

        # Degrees are never dropped to make something fit.
        if options.show_degrees:
            assert len(degrees) == len(abbrs)
            for abbr, degree in zip(abbrs, degrees):
                assert abbr.get("data-graha") == degree.get("data-graha")
                assert float(degree.get("x")) == pytest.approx(
                    expected_x + DEG_OFFSET * font, abs=TOLERANCE
                )
        else:
            assert degrees == []

        # The fixed worst-case budget fits the box, so no row can overrun it.
        assert left + entry_width_budget(size) * CHART_SIDE <= right + 1e-9

        for line in retros:
            x1 = float(line.get("x1"))
            x2 = float(line.get("x2"))
            y = float(line.get("y1"))
            assert x1 == pytest.approx(expected_x, abs=TOLERANCE)
            assert x2 == pytest.approx(x1 + ABBR_SLOT * font, abs=TOLERANCE)
            assert float(line.get("y2")) == pytest.approx(y, abs=TOLERANCE)
            assert left <= x1 and x2 <= right
            assert top <= y <= bottom
            assert float(line.get("stroke-width")) == pytest.approx(
                RETRO_STROKE * font, abs=TOLERANCE
            )
            # The underline ends 0.45 f before the degree text can start.
            assert x2 + 0.45 * font <= expected_x + DEG_OFFSET * font + 1e-9

        for degree in degrees:
            baseline = float(degree.get("y"))
            matching = [
                line
                for line in retros
                if line.get("data-graha") == degree.get("data-graha")
                and abs(
                    float(line.get("y1")) - (baseline + RETRO_DROP * font)
                ) < TOLERANCE
            ]
            for line in matching:
                assert float(line.get("x2")) < float(degree.get("x"))


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_bands_partition_the_canvas_without_overlapping(name):
    options = case_options(name)
    root = ET.fromstring(
        render_north_indian_svg(case_chart(name), options)
    )
    groups, chart_top = house_layout(root)

    view_box = root.get("viewBox").split()
    assert view_box[:3] == ["0", "0", "1080"]
    document_height = int(view_box[3])

    caption_lines = [
        el for el in root.iter() if el.get("class") == "caption-line"
    ]
    caption_height = (
        band_height(len(caption_lines), CAPTION_PITCH) if options.caption else 0
    )
    assert bool(caption_lines) is options.caption
    assert chart_top == pytest.approx(MARGIN + caption_height, abs=TOLERANCE)

    legend_lines = [
        el
        for el in root.iter()
        if el.get("class") in ("legend-marker", "legend-heading")
    ]
    legend_top = chart_top + CHART_SIDE + CHART_GAP
    entry_baselines = sorted(
        {
            float(el.get("y"))
            for group in root.iter()
            if group.get("class") == "legend-house"
            for el in group
            if el.get("class") == "abbr"
        }
    )
    line_count = len(legend_lines) + len(entry_baselines)
    assert document_height == pytest.approx(
        legend_top + band_height(line_count, LEGEND_PITCH) + MARGIN,
        abs=TOLERANCE,
    )

    for index in range(line_count):
        expected = band_baseline(legend_top, index, LEGEND_FONT, LEGEND_PITCH)
        assert expected + DESCENT * LEGEND_FONT <= document_height - MARGIN

    for index, element in enumerate(caption_lines):
        expected = band_baseline(MARGIN, index, CAPTION_FONT, CAPTION_PITCH)
        assert float(element.get("y")) == pytest.approx(expected, abs=TOLERANCE)
        assert float(element.get("x")) == pytest.approx(CHART_LEFT)


@pytest.mark.parametrize("name", CASE_NAMES)
def test_legend_entries_sit_in_their_slots_inside_the_band(name):
    options = case_options(name)
    root = ET.fromstring(
        render_north_indian_svg(case_chart(name), options)
    )

    slot = legend_slot_width(LEGEND_FONT, options.show_degrees)
    per_line = legend_entries_per_line(LEGEND_FONT, options.show_degrees)
    for group in root.iter():
        if group.get("class") != "legend-house":
            continue
        abbrs = [child for child in group if child.get("class") == "abbr"]
        by_baseline = {}
        for element in abbrs:
            by_baseline.setdefault(float(element.get("y")), []).append(element)
        for baseline, row in sorted(by_baseline.items()):
            assert len(row) <= per_line
            for index, element in enumerate(row):
                expected = CHART_LEFT + legend_slot_x(
                    index, LEGEND_FONT, options.show_degrees
                )
                assert float(element.get("x")) == pytest.approx(
                    expected, abs=TOLERANCE
                )
                assert expected + slot <= CHART_LEFT + CHART_SIDE + 1e-9
