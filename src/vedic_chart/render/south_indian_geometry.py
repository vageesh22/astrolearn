"""Layer 19, part 1: the pure geometry and layout arithmetic of the South
Indian chart.

This module knows the 4 x 4 grid, the fixed map from a rashi to its perimeter
cell, the canonical set of unit edges that bound the twelve sign cells, the
anatomy of one cell and the text-layout bookkeeping that decides how many rows
fit in a cell and where each of them sits. It reads no ``D1Chart`` and emits no
SVG, and it imports nothing from ``vedic_chart`` at all.

Coordinates are normalised to the unit square with the origin at the
**top-left**, x rightward and y downward (the SVG convention). Grid points are
integer lattice points ``(x, y)`` with ``0 <= x, y <= 4``; a grid point maps to
the unit square by multiplying by :data:`CELL_SIDE`.

The typography numbers below are the Layer 10 numbers, **declared here
independently** (never imported from the Layer 10 module); the test suite pins
the two declarations equal so that a divergence fails loudly.

Truncation, never rounding: ``math.floor`` decides capacities and budgets, and
no rounding function is called anywhere in this module.
"""

import math
from dataclasses import dataclass

# --- the grid and the fixed sign map (section 3.1) -------------------------

GRID_SIZE = 4
CELL_SIDE = 0.25

#: ``rashi_index`` 0..11 (Mesha..Meena) -> ``(row, column)``: clockwise from
#: Mesha at the top, second from the left. Positions never rotate.
CELL_BY_RASHI_INDEX: tuple[tuple[int, int], ...] = (
    (0, 1),  # Mesha
    (0, 2),  # Vrishabha
    (0, 3),  # Mithuna
    (1, 3),  # Karka
    (2, 3),  # Simha
    (3, 3),  # Kanya
    (3, 2),  # Tula
    (3, 1),  # Vrishchika
    (3, 0),  # Dhanu
    (2, 0),  # Makara
    (1, 0),  # Kumbha
    (0, 0),  # Meena
)

#: The four inner cells, merged into the centre square; never a sign cell.
CENTRE_CELLS: tuple[tuple[int, int], ...] = ((1, 1), (1, 2), (2, 1), (2, 2))

#: The centre square in unit coordinates and the anchor of its one label.
CENTRE_BOX_GRID = ((1, 1), (3, 3))
CENTRE_POINT = (0.5, 0.5)

OUTER = "outer"
CENTRE_BOUNDARY = "centre"
SHARED = "shared"


@dataclass(frozen=True)
class Box:
    """An axis-aligned box in normalised units."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def contains_box(self, other: "Box", tol: float = 1e-9) -> bool:
        return (
            self.x0 - tol <= other.x0
            and other.x1 <= self.x1 + tol
            and self.y0 - tol <= other.y0
            and other.y1 <= self.y1 + tol
        )

    def overlaps(self, other: "Box", tol: float = 1e-9) -> bool:
        """True when the interiors intersect; touching edges do not count."""
        return (
            self.x0 < other.x1 - tol
            and other.x0 < self.x1 - tol
            and self.y0 < other.y1 - tol
            and other.y0 < self.y1 - tol
        )


def _normalised(first, second):
    """An edge as ``(start, end)`` with ``start < end`` lexicographically."""
    return (first, second) if first < second else (second, first)


def grid_cell_edges(row: int, column: int):
    """The four unit edges of grid cell ``(row, column)``: top, right,
    bottom, left; each a normalised pair of ``(x, y)`` grid points."""
    top_left = (column, row)
    top_right = (column + 1, row)
    bottom_right = (column + 1, row + 1)
    bottom_left = (column, row + 1)
    return (
        _normalised(top_left, top_right),
        _normalised(top_right, bottom_right),
        _normalised(bottom_left, bottom_right),
        _normalised(top_left, bottom_left),
    )


def rashi_cell_edges(rashi_index: int):
    """The four edges of the cell of ``rashi_index`` (the Lagna's thick ones)."""
    row, column = CELL_BY_RASHI_INDEX[rashi_index]
    return grid_cell_edges(row, column)


def _square_loop(low: int, high: int):
    """Grid points around a square, clockwise from its top-left corner."""
    points = [(x, low) for x in range(low, high)]
    points += [(high, y) for y in range(low, high)]
    points += [(x, high) for x in range(high, low, -1)]
    points += [(low, y) for y in range(high, low, -1)]
    return points


def _loop_rank(edge, loop) -> int:
    count = len(loop)
    for index in range(count):
        if _normalised(loop[index], loop[(index + 1) % count]) == edge:
            return index
    raise ValueError(f"edge {edge!r} is not on the loop.")


def _cells_of_edge(edge):
    """The rashi indices of the sign cells that have ``edge`` on their boundary."""
    return tuple(
        rashi_index
        for rashi_index in range(len(CELL_BY_RASHI_INDEX))
        if edge in rashi_cell_edges(rashi_index)
    )


def classify_edge(edge) -> str:
    """``outer``, ``centre`` or ``shared``, from the edge's own position."""
    (x0, y0), (x1, y1) = edge
    if (x0 == x1 and x0 in (0, GRID_SIZE)) or (y0 == y1 and y0 in (0, GRID_SIZE)):
        return OUTER
    if len(_cells_of_edge(edge)) == 2:
        return SHARED
    return CENTRE_BOUNDARY


def _shared_rank(edge) -> int:
    """Clockwise from Meena|Mesha: the rashi index of the later cell."""
    first, second = sorted(_cells_of_edge(edge))
    count = len(CELL_BY_RASHI_INDEX)
    if (first + 1) % count == second:
        return second
    return first  # the Meena|Mesha pair: (0, 11) -> Mesha, rank 0


def _edge_order(edge):
    kind = classify_edge(edge)
    if kind == OUTER:
        return (0, _loop_rank(edge, _square_loop(0, GRID_SIZE)))
    if kind == CENTRE_BOUNDARY:
        (low, _), (high, _) = CENTRE_BOX_GRID
        return (1, _loop_rank(edge, _square_loop(low, high)))
    return (2, _shared_rank(edge))


def derive_grid_edges():
    """The union of the four edges of each of the twelve sign cells, each
    distinct edge once, ordered outer (clockwise from the top-left), centre
    boundary (clockwise from its top-left), shared (clockwise from
    Meena|Mesha)."""
    distinct = []
    for row, column in CELL_BY_RASHI_INDEX:
        for edge in grid_cell_edges(row, column):
            if edge not in distinct:
                distinct.append(edge)
    return tuple(sorted(distinct, key=_edge_order))


#: The 36 canonical unit edges: 16 outer, 8 centre-boundary, 12 shared.
GRID_EDGES = derive_grid_edges()


def edge_to_unit(edge):
    """An edge of grid points as a pair of unit-square points."""
    (x0, y0), (x1, y1) = edge
    return (
        (x0 * CELL_SIDE, y0 * CELL_SIDE),
        (x1 * CELL_SIDE, y1 * CELL_SIDE),
    )


# --- cell anatomy (section 3.2) --------------------------------------------

CELL_PADDING = 0.010
LABEL_ROW = 0.032
LABEL_FONT = 0.020
ENTRY_WIDTH = CELL_SIDE - 2 * CELL_PADDING  # 0.230
ENTRY_HEIGHT = CELL_SIDE - 2 * CELL_PADDING - LABEL_ROW  # 0.198


def cell_box(rashi_index: int) -> Box:
    """The whole 0.25 x 0.25 cell of a rashi."""
    row, column = CELL_BY_RASHI_INDEX[rashi_index]
    x0 = column * CELL_SIDE
    y0 = row * CELL_SIDE
    return Box(x0, y0, x0 + CELL_SIDE, y0 + CELL_SIDE)


def inner_box(rashi_index: int) -> Box:
    """The cell minus its padding: label row plus entry area."""
    cell = cell_box(rashi_index)
    return Box(
        cell.x0 + CELL_PADDING,
        cell.y0 + CELL_PADDING,
        cell.x0 + CELL_PADDING + ENTRY_WIDTH,
        cell.y1 - CELL_PADDING,
    )


def label_row_box(rashi_index: int) -> Box:
    inner = inner_box(rashi_index)
    return Box(inner.x0, inner.y0, inner.x1, inner.y0 + LABEL_ROW)


def entry_box(rashi_index: int) -> Box:
    """The entry area: 0.230 wide, 0.198 high, below the label row."""
    inner = inner_box(rashi_index)
    top = inner.y0 + LABEL_ROW
    return Box(inner.x0, top, inner.x0 + ENTRY_WIDTH, top + ENTRY_HEIGHT)


def label_baseline(rashi_index: int) -> float:
    """The label font's em box centred in the label row."""
    row = label_row_box(rashi_index)
    return row.y0 + (LABEL_ROW - LABEL_FONT) / 2.0 + ASCENT * LABEL_FONT


def sign_label_x(rashi_index: int) -> float:
    """Left anchor of the sign label: the rows' own left edge."""
    return row_start_x(inner_box(rashi_index).x0)


def house_label_x(rashi_index: int) -> float:
    """Right anchor (text-anchor end) of the house label, inset as the left."""
    return inner_box(rashi_index).x1 - LEFT_INSET


# --- the size ladder and the sizing rule (section 3.3) ---------------------

#: Entry sizes as fractions of the chart side: base first, floor last.
SIZE_LADDER: tuple[float, ...] = (
    0.032, 0.030, 0.028, 0.026, 0.024, 0.022, 0.021,
)
FLOOR_SIZE = SIZE_LADDER[-1]
BASE_SIZE = SIZE_LADDER[0]

LINE_HEIGHT = 1.45
CHAR_ADVANCE = 0.68
LEFT_INSET = 0.01
WIDTH_BUDGET_EMS = 6.12
ABBR_SLOT = 1.45
ABBR_DEG_GAP = 0.45
DEG_OFFSET = ABBR_SLOT + ABBR_DEG_GAP  # 1.90 f
RETRO_DROP = 0.22
RETRO_STROKE = 0.08
ASCENT = 0.75
DESCENT = 0.25


def entry_width_budget(size: float, show_degrees: bool = True) -> float:
    """W(f): the inset plus the nine-character worst case ``Me 29°59′``, or
    plus the abbreviation slot when degrees are off."""
    ems = WIDTH_BUDGET_EMS if show_degrees else ABBR_SLOT
    return LEFT_INSET + ems * size


def capacity(height: float, size: float) -> int:
    """How many whole rows of pitch 1.45 f fit in a box of this height."""
    return math.floor(height / (LINE_HEIGHT * size))


def width_gated_size(width: float, show_degrees: bool = True) -> float:
    """The largest ladder size whose width budget fits the box width."""
    for size in SIZE_LADDER:
        if entry_width_budget(size, show_degrees) <= width:
            return size
    return FLOOR_SIZE


def select_size(count: int, width: float, height: float, show_degrees: bool = True):
    """Return ``(size, shown, overflow)`` for ``count`` entries in a box.

    The Layer 10 rule: the width gate first, then the largest size that fits
    every entry; failing both, the floor with one row surrendered to ``+n``.
    """
    gate = width_gated_size(width, show_degrees)
    for size in SIZE_LADDER:
        if size <= gate and capacity(height, size) >= count:
            return size, count, False
    return FLOOR_SIZE, capacity(height, FLOOR_SIZE) - 1, True


def row_baseline(box_top: float, index: int, size: float) -> float:
    """Baseline of row ``index`` (0-based) inside a box."""
    return box_top + ASCENT * size + index * LINE_HEIGHT * size


def row_start_x(box_left: float) -> float:
    """Left edge of every row: the box's left edge plus the inset."""
    return box_left + LEFT_INSET


# --- free-text wrapping and bands (re-declared Layer 10 values) -------------


def wrap_text(text: str, budget: int) -> list[str]:
    """Greedy whitespace wrapping with a hard split, dropping nothing."""
    if budget < 1:
        raise ValueError(f"budget must be a positive int; got {budget!r}.")

    lines: list[str] = []
    current = ""
    for token in text.split():
        while len(token) > budget:
            if current:
                lines.append(current)
                current = ""
            lines.append(token[:budget])
            token = token[budget:]
        if not token:
            continue
        if not current:
            current = token
        elif len(current) + 1 + len(token) <= budget:
            current = current + " " + token
        else:
            lines.append(current)
            current = token
    if current:
        lines.append(current)
    if not lines:
        lines.append("")
    return lines


BAND_PADDING = 16
BAND_WIDTH = 1000.0
FREE_TEXT_ADVANCE = 0.75
LEGEND_INDENT_CHARS = 4
LEGEND_SLOT_CHARS_WITH_DEGREES = 6
LEGEND_GAP_EMS = 1.00


def character_budget(font: float) -> int:
    """B = floor(1000 / (0.75 F))."""
    return math.floor(BAND_WIDTH / (FREE_TEXT_ADVANCE * font))


def band_height(line_count: int, pitch: int) -> int:
    """A band is padding, its lines at a fixed pitch, then padding."""
    return BAND_PADDING + line_count * pitch + BAND_PADDING


def band_baseline(band_top: float, index: int, font: float, pitch: int) -> float:
    """Baseline of line ``index`` (0-based) in a band."""
    return band_top + BAND_PADDING + font + index * pitch


def legend_indent(font: float) -> float:
    """I = 4 x 0.75 F: four characters of hanging indent."""
    return LEGEND_INDENT_CHARS * FREE_TEXT_ADVANCE * font


def legend_gap(font: float) -> float:
    return LEGEND_GAP_EMS * font


def legend_slot_width(font: float, show_degrees: bool) -> float:
    """A slot reproduces the abbreviation/degree spacing at the legend font."""
    if show_degrees:
        return (
            DEG_OFFSET + LEGEND_SLOT_CHARS_WITH_DEGREES * FREE_TEXT_ADVANCE
        ) * font
    return 2 * FREE_TEXT_ADVANCE * font


def legend_entries_per_line(font: float, show_degrees: bool) -> int:
    """E = floor((1000 - I + G) / (slot + G))."""
    slot = legend_slot_width(font, show_degrees)
    gap = legend_gap(font)
    return math.floor((BAND_WIDTH - legend_indent(font) + gap) / (slot + gap))


def legend_slot_x(index: int, font: float, show_degrees: bool) -> float:
    """Left edge of slot ``index`` (0-based), relative to the band's left."""
    slot = legend_slot_width(font, show_degrees)
    return legend_indent(font) + index * (slot + legend_gap(font))


def legend_entry_line_count(
    entry_count: int, font: float, show_degrees: bool
) -> int:
    """How many entry lines a complete list of that length needs."""
    if entry_count <= 0:
        return 0
    per_line = legend_entries_per_line(font, show_degrees)
    return -(-entry_count // per_line)
