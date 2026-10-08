"""Tests for Layer 19's South Indian geometry (spec section 3, section 9.1).

The fixed sign map, the canonical edge set re-derived independently from the
twelve cell boundaries, the anatomy of a cell and the sizing ladder. Nothing
here renders a document; the document-level checks live in
``test_render_south_indian.py``.
"""

import itertools

import pytest

from vedic_chart.render import south_indian_geometry as geo

PERIMETER_CELLS = {
    (row, column)
    for row in range(4)
    for column in range(4)
    if row in (0, 3) or column in (0, 3)
}
CENTRE = {(1, 1), (1, 2), (2, 1), (2, 2)}


# --- the fixed map ---------------------------------------------------------


def test_the_map_is_the_documented_table():
    assert geo.CELL_BY_RASHI_INDEX == (
        (0, 1), (0, 2), (0, 3), (1, 3), (2, 3), (3, 3),
        (3, 2), (3, 1), (3, 0), (2, 0), (1, 0), (0, 0),
    )


def test_the_map_is_a_bijection_onto_the_twelve_perimeter_cells():
    cells = geo.CELL_BY_RASHI_INDEX
    assert len(cells) == 12
    assert len(set(cells)) == 12
    assert set(cells) == PERIMETER_CELLS


def test_the_centre_cells_are_never_assigned():
    assert set(geo.CENTRE_CELLS) == CENTRE
    assert CENTRE.isdisjoint(geo.CELL_BY_RASHI_INDEX)


def test_the_map_runs_clockwise_from_mesha_one_step_at_a_time():
    """Consecutive rashis are grid neighbours, and the walk turns clockwise."""
    cells = geo.CELL_BY_RASHI_INDEX
    assert cells[0] == (0, 1)
    for index in range(12):
        row, column = cells[index]
        next_row, next_column = cells[(index + 1) % 12]
        assert abs(row - next_row) + abs(column - next_column) == 1
    # Signed area of the cell-centre loop in (x right, y down) coordinates is
    # positive exactly when the loop is clockwise on screen.
    points = [(column + 0.5, row + 0.5) for row, column in cells]
    area = sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1])
    )
    assert area > 0


def test_each_cell_box_is_inside_the_square_and_cells_do_not_overlap():
    boxes = [geo.cell_box(index) for index in range(12)]
    for box in boxes:
        assert 0.0 <= box.x0 < box.x1 <= 1.0
        assert 0.0 <= box.y0 < box.y1 <= 1.0
        assert box.width == pytest.approx(0.25)
        assert box.height == pytest.approx(0.25)
    for first, second in itertools.combinations(boxes, 2):
        assert not first.overlaps(second)
    centre = geo.Box(0.25, 0.25, 0.75, 0.75)
    for box in boxes:
        assert not box.overlaps(centre)


# --- the canonical edge set ------------------------------------------------


def independent_cell_edges(row, column):
    """The four edges of a cell, written out by hand -- not via the module."""
    corners = [
        (column, row), (column + 1, row), (column + 1, row + 1), (column, row + 1),
    ]
    edges = set()
    for index in range(4):
        a, b = corners[index], corners[(index + 1) % 4]
        edges.add((min(a, b), max(a, b)))
    return edges


def derived_edge_set():
    union = set()
    for row, column in geo.CELL_BY_RASHI_INDEX:
        union |= independent_cell_edges(row, column)
    return union


def test_grid_edges_equal_the_set_derived_from_the_twelve_cells():
    assert set(geo.GRID_EDGES) == derived_edge_set()


def test_there_are_exactly_thirty_six_edges_and_no_duplicates():
    assert len(geo.GRID_EDGES) == 36
    assert len(set(geo.GRID_EDGES)) == 36
    assert len(derived_edge_set()) == 36


def test_every_edge_is_a_normalised_unit_edge():
    for start, end in geo.GRID_EDGES:
        assert start < end
        (x0, y0), (x1, y1) = start, end
        assert abs(x1 - x0) + abs(y1 - y0) == 1
        assert all(0 <= value <= 4 for value in (x0, y0, x1, y1))


def classify_independently(edge):
    (x0, y0), (x1, y1) = edge
    if (x0 == x1 and x0 in (0, 4)) or (y0 == y1 and y0 in (0, 4)):
        return "outer"
    owners = [
        cell
        for cell in geo.CELL_BY_RASHI_INDEX
        if edge in independent_cell_edges(*cell)
    ]
    return "shared" if len(owners) == 2 else "centre"


def test_the_edges_classify_sixteen_eight_twelve():
    kinds = [classify_independently(edge) for edge in geo.GRID_EDGES]
    assert kinds.count("outer") == 16
    assert kinds.count("centre") == 8
    assert kinds.count("shared") == 12
    assert [geo.classify_edge(edge) for edge in geo.GRID_EDGES] == kinds


def test_the_order_is_outer_then_centre_then_shared():
    kinds = [classify_independently(edge) for edge in geo.GRID_EDGES]
    assert kinds == ["outer"] * 16 + ["centre"] * 8 + ["shared"] * 12


def test_the_outer_perimeter_runs_clockwise_from_the_top_left():
    outer = geo.GRID_EDGES[:16]
    assert outer[0] == ((0, 0), (1, 0))
    assert outer[3] == ((3, 0), (4, 0))
    assert outer[4] == ((4, 0), (4, 1))
    assert outer[15] == ((0, 0), (0, 1))
    # Consecutive outer edges share a point (a closed walk).
    for first, second in zip(outer, outer[1:] + outer[:1]):
        assert set(first) & set(second)


def test_the_centre_boundary_is_a_closed_clockwise_loop():
    centre = geo.GRID_EDGES[16:24]
    assert centre[0] == ((1, 1), (2, 1))
    for first, second in zip(centre, centre[1:] + centre[:1]):
        assert set(first) & set(second)


def test_shared_edges_run_clockwise_from_meena_mesha():
    shared = geo.GRID_EDGES[24:]
    for rank, edge in enumerate(shared):
        later = geo.CELL_BY_RASHI_INDEX[rank]
        earlier = geo.CELL_BY_RASHI_INDEX[(rank - 1) % 12]
        assert edge in independent_cell_edges(*later)
        assert edge in independent_cell_edges(*earlier)
    assert shared[0] == ((1, 0), (1, 1))  # Meena | Mesha


def segments_overlap(first, second):
    """Collinear unit edges overlapping in more than a point, or coinciding."""
    (a0, a1), (b0, b1) = first, second
    if a0[0] == a1[0] == b0[0] == b1[0]:
        low = max(min(a0[1], a1[1]), min(b0[1], b1[1]))
        high = min(max(a0[1], a1[1]), max(b0[1], b1[1]))
        return high > low
    if a0[1] == a1[1] == b0[1] == b1[1]:
        low = max(min(a0[0], a1[0]), min(b0[0], b1[0]))
        high = min(max(a0[0], a1[0]), max(b0[0], b1[0]))
        return high > low
    return False


def test_no_two_edges_overlap_or_coincide():
    for first, second in itertools.combinations(geo.GRID_EDGES, 2):
        assert not segments_overlap(first, second), (first, second)


def test_no_edge_lies_inside_the_centre():
    for (x0, y0), (x1, y1) in geo.GRID_EDGES:
        mid_x = (x0 + x1) / 2
        mid_y = (y0 + y1) / 2
        assert not (1 < mid_x < 3 and 1 < mid_y < 3), ((x0, y0), (x1, y1))


@pytest.mark.parametrize("rashi_index", range(12))
def test_a_cells_four_edges_are_canonical_edges(rashi_index):
    edges = geo.rashi_cell_edges(rashi_index)
    assert len(set(edges)) == 4
    assert set(edges) <= set(geo.GRID_EDGES)
    assert set(edges) == independent_cell_edges(
        *geo.CELL_BY_RASHI_INDEX[rashi_index]
    )


def test_edges_map_to_the_unit_square_at_the_cell_side():
    assert geo.edge_to_unit(((1, 0), (2, 0))) == ((0.25, 0.0), (0.5, 0.0))


# --- cell anatomy ----------------------------------------------------------


def test_the_cell_anatomy_numbers():
    assert geo.CELL_SIDE == 0.25
    assert geo.CELL_PADDING == 0.010
    assert geo.LABEL_ROW == 0.032
    assert geo.LABEL_FONT == 0.020
    assert geo.ENTRY_WIDTH == pytest.approx(0.230)
    assert geo.ENTRY_HEIGHT == pytest.approx(0.198)


@pytest.mark.parametrize("rashi_index", range(12))
def test_the_entry_box_sits_below_the_label_row_inside_the_padded_cell(rashi_index):
    cell = geo.cell_box(rashi_index)
    inner = geo.inner_box(rashi_index)
    label = geo.label_row_box(rashi_index)
    entry = geo.entry_box(rashi_index)

    assert cell.contains_box(inner)
    assert inner.contains_box(label) and inner.contains_box(entry)
    assert entry.width == pytest.approx(0.230)
    assert entry.height == pytest.approx(0.198)
    assert label.y1 == pytest.approx(entry.y0)
    assert inner.x0 - cell.x0 == pytest.approx(0.010)
    assert cell.y1 - entry.y1 == pytest.approx(0.010)
    baseline = geo.label_baseline(rashi_index)
    assert baseline - geo.ASCENT * geo.LABEL_FONT >= label.y0 - 1e-12
    assert baseline + geo.DESCENT * geo.LABEL_FONT <= label.y1 + 1e-12


def test_the_longest_labels_fit_side_by_side_in_the_label_row():
    width = geo.house_label_x(7) - geo.sign_label_x(7)
    vrishchika = len("Vrishchika") * geo.CHAR_ADVANCE * geo.LABEL_FONT
    h12 = len("H12") * geo.CHAR_ADVANCE * geo.LABEL_FONT
    assert vrishchika == pytest.approx(0.136)
    assert vrishchika + h12 < width


# --- ladder and sizing -----------------------------------------------------


def test_the_ladder_and_typography_constants():
    assert geo.SIZE_LADDER == (0.032, 0.030, 0.028, 0.026, 0.024, 0.022, 0.021)
    assert geo.FLOOR_SIZE == 0.021
    assert (
        geo.LINE_HEIGHT, geo.CHAR_ADVANCE, geo.LEFT_INSET, geo.WIDTH_BUDGET_EMS,
        geo.ABBR_SLOT, geo.ABBR_DEG_GAP, geo.RETRO_DROP, geo.RETRO_STROKE,
        geo.ASCENT, geo.DESCENT,
    ) == (1.45, 0.68, 0.01, 6.12, 1.45, 0.45, 0.22, 0.08, 0.75, 0.25)
    assert geo.DEG_OFFSET == pytest.approx(1.90)


def test_the_capacities_are_four_four_four_five_five_six_six():
    assert [
        geo.capacity(geo.ENTRY_HEIGHT, size) for size in geo.SIZE_LADDER
    ] == [4, 4, 4, 5, 5, 6, 6]


@pytest.mark.parametrize("show_degrees", [True, False])
def test_every_ladder_size_passes_the_width_gate(show_degrees):
    for size in geo.SIZE_LADDER:
        assert geo.entry_width_budget(size, show_degrees) <= geo.ENTRY_WIDTH
    assert geo.width_gated_size(geo.ENTRY_WIDTH, show_degrees) == 0.032


EXPECTED_PLANS = {
    0: (0.032, 0, False),
    1: (0.032, 1, False),
    2: (0.032, 2, False),
    3: (0.032, 3, False),
    4: (0.032, 4, False),
    5: (0.026, 5, False),
    6: (0.022, 6, False),
    7: (0.021, 5, True),
    8: (0.021, 5, True),
    9: (0.021, 5, True),
    10: (0.021, 5, True),
}


@pytest.mark.parametrize("count", sorted(EXPECTED_PLANS))
@pytest.mark.parametrize("show_degrees", [True, False])
def test_select_size_gives_the_section_three_three_plans(count, show_degrees):
    assert geo.select_size(
        count, geo.ENTRY_WIDTH, geo.ENTRY_HEIGHT, show_degrees
    ) == EXPECTED_PLANS[count]


def test_select_size_takes_the_layer_ten_positional_arguments():
    assert geo.select_size(6, geo.ENTRY_WIDTH, geo.ENTRY_HEIGHT) == (0.022, 6, False)


@pytest.mark.parametrize("count", sorted(EXPECTED_PLANS))
def test_rows_and_the_plus_n_row_fit_the_entry_height(count):
    size, shown, overflow = EXPECTED_PLANS[count]
    rows = shown + (1 if overflow else 0)
    if rows == 0:
        return
    last = geo.row_baseline(0.0, rows - 1, size)
    assert last + geo.DESCENT * size <= geo.ENTRY_HEIGHT
    # The underline of the last row stays inside the box too.
    assert last + (geo.RETRO_DROP + geo.RETRO_STROKE / 2) * size <= geo.ENTRY_HEIGHT


def test_band_arithmetic_has_the_layer_ten_values():
    assert geo.character_budget(24.0) == 55
    assert geo.character_budget(22.0) == 60
    assert geo.band_height(3, 32) == 16 + 96 + 16
    assert geo.band_baseline(100.0, 2, 22.0, 30) == 100.0 + 16 + 22.0 + 60
    assert geo.legend_indent(22.0) == pytest.approx(4 * 0.75 * 22.0)
    assert geo.legend_slot_x(0, 22.0, True) == pytest.approx(geo.legend_indent(22.0))


@pytest.mark.parametrize("budget", [1, 5, 55, 60])
def test_wrapping_never_exceeds_the_budget_and_drops_nothing(budget):
    text = "As = Lagna (ascendant), first in its cell; thicker border"
    lines = geo.wrap_text(text, budget)
    assert all(len(line) <= budget for line in lines)
    assert "".join(text.split()) == "".join("".join(lines).split())

