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

from render_helpers import (
    CASE_NAMES,
    case_chart,
    case_options,
    count_in_house_d1,
)
from vedic_chart.render import NorthIndianOptions
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
    OUTER_CLEARANCE,
    OUTER_SEGMENTS,
    REGIONS,
    REGION_BY_HOUSE,
    RETRO_DROP,
    RETRO_STROKE,
    SIDE_EDGE_INTERCEPT,
    SIDE_ENTRY_GAP,
    SIDE_HEIGHT_GUARD,
    SIDE_HOUSES,
    SIDE_NUMERAL_WIDTH_LIMIT,
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
    select_side_size,
    select_size,
    side_abbr_baseline,
    side_box,
    side_box_admissible,
    side_deg_baseline,
    side_entry_pitch,
    side_overflow_baseline,
    side_rows_height,
    side_width_budget,
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

#: The numeral's assumed glyph box (section 3.1): two digits at 0.026 give a
#: half-width of about 0.0155, and half the cap height about 0.0095.
NUMERAL_HALF_WIDTH = 0.0155
NUMERAL_HALF_HEIGHT = 0.0095
#: The clearance section 3.1 claims between a side box and that glyph box.
NUMERAL_CLEARANCE = 0.0195
CHAR_ADVANCE = 0.68
#: Coordinates are serialised to two decimals of a viewBox unit, so a position
#: read back out of the document may sit half a hundredth away from the exact
#: one. Normalised, that is 5e-6; 1e-5 is the safe allowance.
CLEARANCE_TOLERANCE = 1e-5


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
    """The fixed boxes of the section 3 table.

    Houses 3, 5, 9 and 11 are absent on purpose: since U-8 their box is a
    function of the entry count and is asserted by the side-triangle suite
    below, not by a constant table.
    """
    expected = {
        1: (0.23, 0.22), 2: (0.21, 0.10),
        4: (0.22, 0.23), 6: (0.21, 0.10),
        7: (0.23, 0.22), 8: (0.21, 0.10),
        10: (0.22, 0.23), 12: (0.21, 0.10),
    }
    assert sorted(set(range(1, 13)) - set(expected)) == list(SIDE_HOUSES)
    for region in REGIONS:
        if region.house in SIDE_HOUSES:
            continue
        width, height = expected[region.house]
        assert region.box.width == pytest.approx(width, abs=1e-12)
        assert region.box.height == pytest.approx(height, abs=1e-12)


# --- the sizing ladder -----------------------------------------------------


def test_the_size_ladder_is_the_documented_one():
    assert SIZE_LADDER == (0.032, 0.030, 0.028, 0.026, 0.024, 0.022, 0.021)
    assert FLOOR_SIZE == 0.021


def test_the_entry_constants_are_the_documented_ones():
    """Section 4, including the underline raised to 0.08 f after 10.D."""
    assert ABBR_SLOT == 1.45
    assert DEG_OFFSET == pytest.approx(1.90)
    assert RETRO_DROP == 0.22
    assert RETRO_STROKE == 0.08
    assert LINE_HEIGHT == 1.45


#: Section 6's capacity table. The side triangles have no row: their box is
#: occupant-dependent and their capacity is decided by ``select_side_size``.
CAPACITY_TABLE = {
    0.22: {0.032: 4, 0.030: 5, 0.028: 5, 0.026: 5, 0.024: 6, 0.022: 6, 0.021: 7},
    0.23: {0.032: 4, 0.030: 5, 0.028: 5, 0.026: 6, 0.024: 6, 0.022: 7, 0.021: 7},
    0.10: {0.032: 2, 0.030: 2, 0.028: 2, 0.026: 2, 0.024: 2, 0.022: 3, 0.021: 3},
}


@pytest.mark.parametrize("height", sorted(CAPACITY_TABLE))
def test_the_capacity_table_of_section_six(height):
    for size, expected in CAPACITY_TABLE[height].items():
        assert capacity(height, size) == expected, (height, size)


def test_the_capacity_table_covers_every_fixed_label_box():
    for region in REGIONS:
        if region.house in SIDE_HOUSES:
            continue
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
        if region.house in SIDE_HOUSES:
            continue
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
    assert RETRO_STROKE * LEGEND_FONT == pytest.approx(1.76)
    assert ABBR_SLOT * LEGEND_FONT == pytest.approx(31.9)
    assert DEG_OFFSET * LEGEND_FONT == pytest.approx(41.8)
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


def side_plan(chart, number, options):
    """``(box, size, shown, overflow)`` for one side triangle of a chart."""
    count = len(chart.house(number).occupants)
    size, shown, overflow = select_side_size(count, options.show_degrees)
    box = side_box(
        REGION_BY_HOUSE[number],
        side_rows_height(shown, size, options.show_degrees, overflow),
        side_width_budget(size, options.show_degrees),
    )
    return box, size, shown, overflow


def house_plan(chart, number, options):
    """The box and size plan of any house, stacked or inline."""
    if number in SIDE_HOUSES:
        return side_plan(chart, number, options)
    box = REGION_BY_HOUSE[number].box
    count = len(chart.house(number).occupants) + (1 if number == 1 else 0)
    size, shown, overflow = select_size(count, box.width, box.height)
    return box, size, shown, overflow


@pytest.mark.parametrize("name", CASE_NAMES)
def test_every_row_and_underline_stays_inside_its_label_box(name):
    chart = case_chart(name)
    options = case_options(name)
    root = ET.fromstring(render_north_indian_svg(chart, options))
    groups, chart_top = house_layout(root)

    for number, group in groups.items():
        stacked = number in SIDE_HOUSES
        box, size, shown, overflow = house_plan(chart, number, options)
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
        assert size in SIZE_LADDER
        assert len(abbrs) == (shown if overflow else entry_count)
        assert bool(overflows) is (overflow and entry_count > 0)
        assert group.get("data-layout") == ("stacked" if stacked else "inline")

        font = size * CHART_SIDE
        expected_x = CHART_LEFT + row_start_x(box.x0) * CHART_SIDE

        def expected_baseline(index, kind):
            if not stacked:
                return chart_top + row_baseline(box.y0, index, size) * CHART_SIDE
            if kind == "deg":
                place = side_deg_baseline
            elif kind == "overflow":
                place = side_overflow_baseline
            else:
                place = side_abbr_baseline
            return chart_top + place(
                box.y0, index, size, options.show_degrees
            ) * CHART_SIDE

        rows = [(element, index, "abbr") for index, element in enumerate(abbrs)]
        if stacked:
            rows += [
                (element, index, "deg") for index, element in enumerate(degrees)
            ]
        rows += [(element, len(abbrs), "overflow") for element in overflows]

        for element, index, kind in rows:
            assert float(element.get("font-size")) == pytest.approx(
                font, abs=TOLERANCE
            )
            expected_row_x = expected_x
            if kind == "deg" and not stacked:
                expected_row_x = expected_x + DEG_OFFSET * font
            assert float(element.get("x")) == pytest.approx(
                expected_row_x, abs=TOLERANCE
            )
            baseline = float(element.get("y"))
            assert baseline == pytest.approx(
                expected_baseline(index, kind), abs=TOLERANCE
            )
            assert baseline - ASCENT * font >= top - TOLERANCE
            assert baseline + DESCENT * font <= bottom + TOLERANCE

        # The +n indicator, when present, owns the last row and nothing follows.
        if overflows:
            last = max(float(element.get("y")) for element, _, _ in rows)
            assert float(overflows[0].get("y")) == pytest.approx(
                last, abs=TOLERANCE
            )
            if not stacked:
                assert len(abbrs) + 1 == capacity(box.height, size)

        # Degrees are never dropped to make something fit.
        if options.show_degrees:
            assert len(degrees) == len(abbrs)
            for abbr, degree in zip(abbrs, degrees):
                assert abbr.get("data-graha") == degree.get("data-graha")
                if stacked:
                    # Same x, one 1.45 f row lower: the stacked construction.
                    assert float(degree.get("x")) == pytest.approx(
                        float(abbr.get("x")), abs=TOLERANCE
                    )
                    assert float(degree.get("y")) - float(
                        abbr.get("y")
                    ) == pytest.approx(LINE_HEIGHT * font, abs=TOLERANCE)
                else:
                    assert float(degree.get("x")) == pytest.approx(
                        expected_x + DEG_OFFSET * font, abs=TOLERANCE
                    )
        else:
            assert degrees == []

        # The fixed worst-case budget fits the box, so no row can overrun it.
        budget = (
            side_width_budget(size, options.show_degrees)
            if stacked
            else entry_width_budget(size)
        )
        assert left + budget * CHART_SIDE <= right + 1e-9

        for line in retros:
            x1 = float(line.get("x1"))
            x2 = float(line.get("x2"))
            y = float(line.get("y1"))
            assert x1 == pytest.approx(expected_x, abs=TOLERANCE)
            assert x2 == pytest.approx(x1 + ABBR_SLOT * font, abs=TOLERANCE)
            assert float(line.get("y2")) == pytest.approx(y, abs=TOLERANCE)
            assert left <= x1
            assert x2 <= right + TOLERANCE
            assert top <= y <= bottom
            assert float(line.get("stroke-width")) == pytest.approx(
                RETRO_STROKE * font, abs=TOLERANCE
            )
            if not stacked:
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
            if stacked:
                # A stacked underline is a whole row above its own degrees, so
                # it can never share their baseline.
                assert matching == []
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


# --- B2. side triangles (U-8) ---------------------------------------------
#
# One synthetic chart per (house, occupant count) pair, rendered with degrees
# on and off, is enough to pin the whole of section 3.1 and the side-triangle
# half of section 6: the size chosen, the box built around it, that box's
# clearance from the diagram and from the numeral, and the position of every
# element the cell emits.

SIDE_COUNTS = (0, 1, 2, 3, 4, 9)

#: Section 6's stated results, as ``(size, shown, overflow)``.
EXPECTED_SIDE_PLAN_WITH_DEGREES = {
    0: (0.032, 0, False),
    1: (0.032, 1, False),
    2: (0.028, 2, False),
    3: (0.022, 3, False),
    4: (FLOOR_SIZE, 2, True),
    9: (FLOOR_SIZE, 2, True),
}
EXPECTED_SIDE_PLAN_WITHOUT_DEGREES = {
    0: (0.032, 0, False),
    1: (0.032, 1, False),
    2: (0.032, 2, False),
    3: (0.032, 3, False),
    4: (0.032, 4, False),
    9: (0.024, 9, False),
}

SIDE_CASES = [
    (house, count, show_degrees)
    for house in SIDE_HOUSES
    for count in SIDE_COUNTS
    for show_degrees in (True, False)
]


def expected_side_plan(count: int, show_degrees: bool):
    table = (
        EXPECTED_SIDE_PLAN_WITH_DEGREES
        if show_degrees
        else EXPECTED_SIDE_PLAN_WITHOUT_DEGREES
    )
    return table[count]


def side_case(house: int, count: int, show_degrees: bool):
    """``(chart, options, root, group)`` for one side-triangle case."""
    chart = count_in_house_d1(house, count)
    options = NorthIndianOptions(show_degrees=show_degrees)
    root = ET.fromstring(render_north_indian_svg(chart, options))
    groups, chart_top = house_layout(root)
    return chart, options, root, groups, chart_top


def rectangle_distance(box, x0, y0, x1, y1) -> float:
    """Distance between an axis-aligned ``Box`` and another rectangle."""
    dx = max(x0 - box.x1, box.x0 - x1, 0.0)
    dy = max(y0 - box.y1, box.y0 - y1, 0.0)
    return (dx * dx + dy * dy) ** 0.5


@pytest.mark.parametrize("house,count,show_degrees", SIDE_CASES)
def test_side_triangle_size_is_the_section_six_result(house, count, show_degrees):
    assert select_side_size(count, show_degrees) == expected_side_plan(
        count, show_degrees
    )
    chart = count_in_house_d1(house, count)
    assert len(chart.house(house).occupants) == count


@pytest.mark.parametrize("house,count,show_degrees", SIDE_CASES)
def test_the_side_box_is_admissible_and_clears_the_diagram(
    house, count, show_degrees
):
    """Section 3.1's three conditions, corner by corner."""
    region = REGION_BY_HOUSE[house]
    size, shown, overflow = expected_side_plan(count, show_degrees)
    height = side_rows_height(shown, size, show_degrees, overflow)
    width = side_width_budget(size, show_degrees)
    box = side_box(region, height, width)

    assert side_box_admissible(box)
    assert box.width <= SIDE_EDGE_INTERCEPT - box.height / 2.0
    assert box.width <= SIDE_NUMERAL_WIDTH_LIMIT
    assert box.height <= SIDE_HEIGHT_GUARD

    for corner in box.corners:
        assert point_in_polygon(corner, region.polygon, include_boundary=True)
        assert clearance_from_drawn_segments(corner) >= MIN_BOX_CLEARANCE - 1e-12


@pytest.mark.parametrize("house,count,show_degrees", SIDE_CASES)
def test_the_side_box_clears_the_numeral_glyph_box(house, count, show_degrees):
    region = REGION_BY_HOUSE[house]
    size, shown, overflow = expected_side_plan(count, show_degrees)
    box = side_box(
        region,
        side_rows_height(shown, size, show_degrees, overflow),
        side_width_budget(size, show_degrees),
    )
    anchor_x, anchor_y = region.numeral

    gap = rectangle_distance(
        box,
        anchor_x - NUMERAL_HALF_WIDTH,
        anchor_y - NUMERAL_HALF_HEIGHT,
        anchor_x + NUMERAL_HALF_WIDTH,
        anchor_y + NUMERAL_HALF_HEIGHT,
    )
    assert gap >= NUMERAL_CLEARANCE, (house, count, show_degrees, gap)


@pytest.mark.parametrize("house,count,show_degrees", SIDE_CASES)
def test_the_side_box_sits_against_the_outer_edge(house, count, show_degrees):
    region = REGION_BY_HOUSE[house]
    size, shown, overflow = expected_side_plan(count, show_degrees)
    height = side_rows_height(shown, size, show_degrees, overflow)
    width = side_width_budget(size, show_degrees)
    box = side_box(region, height, width)

    if house in (3, 5):
        assert box.x0 == pytest.approx(OUTER_CLEARANCE, abs=1e-12)
        assert box.x1 == pytest.approx(OUTER_CLEARANCE + width, abs=1e-12)
    else:
        assert box.x1 == pytest.approx(1.0 - OUTER_CLEARANCE, abs=1e-12)
        assert box.x0 == pytest.approx(1.0 - OUTER_CLEARANCE - width, abs=1e-12)
    # Centred on the numeral's y, so the four triangles mirror one another.
    assert (box.y0 + box.y1) / 2.0 == pytest.approx(region.numeral[1], abs=1e-12)
    assert box.height == pytest.approx(height, abs=1e-12)


@pytest.mark.parametrize("house,count,show_degrees", SIDE_CASES)
def test_every_side_element_lies_inside_the_occupant_dependent_box(
    house, count, show_degrees
):
    """Bounding boxes: ascent 0.75 f, descent 0.25 f, budgeted width."""
    chart, options, root, groups, chart_top = side_case(house, count, show_degrees)
    group = groups[house]
    size, shown, overflow = expected_side_plan(count, show_degrees)
    box = side_box(
        REGION_BY_HOUSE[house],
        side_rows_height(shown, size, show_degrees, overflow),
        side_width_budget(size, show_degrees),
    )
    font = size * CHART_SIDE
    left = CHART_LEFT + box.x0 * CHART_SIDE
    right = CHART_LEFT + box.x1 * CHART_SIDE
    top = chart_top + box.y0 * CHART_SIDE
    bottom = chart_top + box.y1 * CHART_SIDE

    def inside_the_box(x0, y0, x1, y1, what):
        """Every corner of a drawn extent is in the box and off the diagram.

        The two claims are separate on purpose: the box is where the layout
        promises to keep its ink, and the 0.015 clearance is what that promise
        is *for*. Asserting only the first would pass a box that had itself
        drifted onto a chart line.
        """
        assert x0 >= left - TOLERANCE, what
        assert x1 <= right + TOLERANCE, what
        assert y0 >= top - TOLERANCE, what
        assert y1 <= bottom + TOLERANCE, what
        for point in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            normalised = (
                (point[0] - CHART_LEFT) / CHART_SIDE,
                (point[1] - chart_top) / CHART_SIDE,
            )
            assert (
                clearance_from_drawn_segments(normalised)
                >= MIN_BOX_CLEARANCE - CLEARANCE_TOLERANCE
            ), (what, point)

    for element in group:
        css = element.get("class")
        if css in ("abbr", "deg", "overflow"):
            x = float(element.get("x"))
            baseline = float(element.get("y"))
            width = len(element.text) * CHAR_ADVANCE * font
            inside_the_box(
                x,
                baseline - ASCENT * font,
                x + width,
                baseline + DESCENT * font,
                (css, element.text),
            )
        elif css == "retro":
            # The marker is a fixed 1.45 f, which is exactly what section 5
            # budgets a degrees-off side box, so it ends on the box's edge and
            # never past it.
            x1 = float(element.get("x1"))
            x2 = float(element.get("x2"))
            y = float(element.get("y1"))
            half = float(element.get("stroke-width")) / 2.0
            assert float(element.get("y2")) == pytest.approx(y, abs=TOLERANCE)
            inside_the_box(x1, y - half, x2, y + half, ("retro", x1, x2))


@pytest.mark.parametrize("house,count,show_degrees", SIDE_CASES)
def test_side_rows_are_pitched_at_one_point_four_five_and_three_point_three(
    house, count, show_degrees
):
    chart, options, root, groups, chart_top = side_case(house, count, show_degrees)
    group = groups[house]
    size, shown, overflow = expected_side_plan(count, show_degrees)
    font = size * CHART_SIDE

    abbrs = [c for c in group if c.get("class") == "abbr"]
    degrees = [c for c in group if c.get("class") == "deg"]
    overflows = [c for c in group if c.get("class") == "overflow"]
    assert len(abbrs) == shown
    assert len(degrees) == (shown if show_degrees else 0)
    assert len(overflows) == (1 if overflow else 0)

    xs = {element.get("x") for element in abbrs + degrees + overflows}
    assert len(xs) <= 1, "every side row starts at the same x"

    pitch = side_entry_pitch(size, show_degrees) * CHART_SIDE
    assert pitch == pytest.approx(
        (3.30 if show_degrees else 1.45) * font, abs=TOLERANCE
    )
    baselines = [float(element.get("y")) for element in abbrs]
    for previous, following in zip(baselines, baselines[1:]):
        assert following - previous == pytest.approx(pitch, abs=TOLERANCE)

    if show_degrees:
        for abbr, degree in zip(abbrs, degrees):
            assert abbr.get("data-graha") == degree.get("data-graha")
            assert float(degree.get("y")) - float(abbr.get("y")) == pytest.approx(
                LINE_HEIGHT * font, abs=TOLERANCE
            )

    if overflow:
        # The +n row is a further whole pitch below the last abbreviation row:
        # its own row after its own gap.
        assert float(overflows[0].get("y")) - baselines[-1] == pytest.approx(
            pitch, abs=TOLERANCE
        )
        assert SIDE_ENTRY_GAP == 0.40


@pytest.mark.parametrize("house", SIDE_HOUSES)
def test_the_side_overflow_transition_is_exactly_between_three_and_four(house):
    options = NorthIndianOptions(show_degrees=True)

    three = ET.fromstring(
        render_north_indian_svg(count_in_house_d1(house, 3), options)
    )
    groups, _ = house_layout(three)
    group = groups[house]
    assert [e.text for e in group if e.get("class") == "abbr"] == [
        "Su", "Mo", "Me",
    ]
    assert [e for e in group if e.get("class") == "overflow"] == []
    assert [
        int(g.get("data-house"))
        for g in three.iter()
        if g.get("class") == "legend-house"
    ] == []
    assert select_side_size(3, True)[0] == 0.022

    four = ET.fromstring(
        render_north_indian_svg(count_in_house_d1(house, 4), options)
    )
    groups, _ = house_layout(four)
    group = groups[house]
    assert [e.text for e in group if e.get("class") == "abbr"] == ["Su", "Mo"]
    assert [e.text for e in group if e.get("class") == "overflow"] == ["+2"]
    blocks = {
        int(g.get("data-house")): g
        for g in four.iter()
        if g.get("class") == "legend-house"
    }
    assert sorted(blocks) == [house]
    assert [e.text for e in blocks[house] if e.get("class") == "abbr"] == [
        "Su", "Mo", "Me", "Ve",
    ]


@pytest.mark.parametrize("house", SIDE_HOUSES)
def test_nine_occupants_in_a_side_triangle_show_two_entries_and_plus_seven(house):
    options = NorthIndianOptions(show_degrees=True)
    root = ET.fromstring(
        render_north_indian_svg(count_in_house_d1(house, 9), options)
    )
    groups, _ = house_layout(root)
    group = groups[house]

    assert [e.text for e in group if e.get("class") == "abbr"] == ["Su", "Mo"]
    assert [e.text for e in group if e.get("class") == "overflow"] == ["+7"]


@pytest.mark.parametrize("house,count,show_degrees", SIDE_CASES)
def test_the_house_group_declares_its_layout(house, count, show_degrees):
    chart, options, root, groups, chart_top = side_case(house, count, show_degrees)

    for number, group in groups.items():
        expected = "stacked" if number in SIDE_HOUSES else "inline"
        assert group.get("data-layout") == expected, number


@pytest.mark.parametrize("house", SIDE_HOUSES)
@pytest.mark.parametrize("show_degrees", [True, False])
def test_an_empty_side_triangle_emits_no_entry_elements(house, show_degrees):
    options = NorthIndianOptions(show_degrees=show_degrees)
    root = ET.fromstring(
        render_north_indian_svg(count_in_house_d1(house, 0), options)
    )
    groups, _ = house_layout(root)
    group = groups[house]

    assert [
        child.get("class")
        for child in group
        if child.get("class") in ("abbr", "deg", "retro", "overflow")
    ] == []
    assert [child.get("class") for child in group] == ["cell", "numeral"]
