"""Layer 10, part 1: the pure geometry and layout arithmetic of the chart.

This module is deliberately ignorant of astrology. It knows the unit square,
the thirteen named points of the North Indian diagram, the twelve regions cut
out of it by the drawn segments, and the bookkeeping rules that decide how many
text rows fit in a box and where each of them sits. Nothing here reads a
``D1Chart``; nothing here emits SVG. Consequently it imports nothing from
``vedic_chart`` at all -- that absence is what keeps the geometry testable on
plain numbers and unable to drift towards the data.

All coordinates are normalized to the unit square with the origin at the
**top-left**, x rightward and y downward, which is the SVG convention. The
renderer maps them onto the output canvas by a single affine scale; because
that map is linear, every clearance and containment argument proved here holds
in output units too.

Truncation, never rounding: ``math.floor`` decides capacities and budgets, so a
row that does not entirely fit is never counted as fitting. ``round()`` appears
nowhere in this package and the test suite parses the AST to prove it.
"""

import math
from dataclasses import dataclass

# --- the thirteen named points (section 3) ---------------------------------

A = (0.0, 0.0)
T = (0.5, 0.0)
B = (1.0, 0.0)
L = (0.0, 0.5)
O = (0.5, 0.5)
R = (1.0, 0.5)
D = (0.0, 1.0)
M = (0.5, 1.0)
C = (1.0, 1.0)
E1 = (0.75, 0.25)
E2 = (0.75, 0.75)
E3 = (0.25, 0.75)
E4 = (0.25, 0.25)

POINTS = {
    "A": A, "T": T, "B": B,
    "L": L, "O": O, "R": R,
    "D": D, "M": M, "C": C,
    "E1": E1, "E2": E2, "E3": E3, "E4": E4,
}

#: The square, the two diagonals and the rhombus -- and nothing else. Every
#: region edge is a sub-segment of one of these ten.
DRAWN_SEGMENTS = (
    (A, B), (B, C), (C, D), (D, A),
    (A, C), (B, D),
    (T, R), (R, M), (M, L), (L, T),
)

#: The four outer edges, kept apart because a region edge lying on one of them
#: has no neighbour on the far side.
OUTER_SEGMENTS = ((A, B), (B, C), (C, D), (D, A))

KITE = "kite"
TRIANGLE = "tri"

KITE_AREA = 0.125
TRIANGLE_AREA = 0.0625

#: Minimum clearance a label box keeps from every drawn segment.
MIN_BOX_CLEARANCE = 0.015


@dataclass(frozen=True)
class Box:
    """An axis-aligned label box inside a region, in normalized units."""

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

    @property
    def corners(self) -> tuple[tuple[float, float], ...]:
        return (
            (self.x0, self.y0),
            (self.x1, self.y0),
            (self.x1, self.y1),
            (self.x0, self.y1),
        )

    def contains(self, point: tuple[float, float], tol: float = 1e-9) -> bool:
        x, y = point
        return (
            self.x0 - tol <= x <= self.x1 + tol
            and self.y0 - tol <= y <= self.y1 + tol
        )


@dataclass(frozen=True)
class Region:
    """One of the twelve houses as a drawn face of the diagram."""

    house: int
    kind: str
    polygon: tuple[tuple[float, float], ...]
    numeral: tuple[float, float]
    box: Box

    @property
    def edges(self) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
        count = len(self.polygon)
        return tuple(
            (self.polygon[i], self.polygon[(i + 1) % count])
            for i in range(count)
        )


#: House 1 is the top-centre kite; numbering runs anticlockwise.
REGIONS: tuple[Region, ...] = (
    Region(1, KITE, (T, E1, O, E4), (0.50, 0.44), Box(0.385, 0.14, 0.615, 0.36)),
    Region(2, TRIANGLE, (A, T, E4), (0.25, 0.20), Box(0.145, 0.02, 0.355, 0.12)),
    Region(3, TRIANGLE, (A, E4, L), (0.20, 0.25), Box(0.02, 0.19, 0.165, 0.31)),
    Region(4, KITE, (L, E4, O, E3), (0.44, 0.50), Box(0.14, 0.385, 0.36, 0.615)),
    Region(5, TRIANGLE, (L, E3, D), (0.20, 0.75), Box(0.02, 0.69, 0.165, 0.81)),
    Region(6, TRIANGLE, (D, M, E3), (0.25, 0.80), Box(0.145, 0.88, 0.355, 0.98)),
    Region(7, KITE, (M, E3, O, E2), (0.50, 0.56), Box(0.385, 0.64, 0.615, 0.86)),
    Region(8, TRIANGLE, (M, C, E2), (0.75, 0.80), Box(0.645, 0.88, 0.855, 0.98)),
    Region(9, TRIANGLE, (C, E2, R), (0.80, 0.75), Box(0.835, 0.69, 0.98, 0.81)),
    Region(10, KITE, (R, E2, O, E1), (0.56, 0.50), Box(0.64, 0.385, 0.86, 0.615)),
    Region(11, TRIANGLE, (B, R, E1), (0.80, 0.25), Box(0.835, 0.19, 0.98, 0.31)),
    Region(12, TRIANGLE, (T, B, E1), (0.75, 0.20), Box(0.645, 0.02, 0.855, 0.12)),
)

REGION_BY_HOUSE = {region.house: region for region in REGIONS}

EXPECTED_AREA = {KITE: KITE_AREA, TRIANGLE: TRIANGLE_AREA}


# --- elementary geometry ---------------------------------------------------


def polygon_area(polygon) -> float:
    """The shoelace area of a simple polygon, orientation-independent."""
    total = 0.0
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def distance_to_segment(point, start, end) -> float:
    """Euclidean distance from ``point`` to the closed segment start--end."""
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    length_squared = dx * dx + dy * dy
    if length_squared == 0.0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / length_squared
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def clearance_from_drawn_segments(point) -> float:
    """Distance from ``point`` to the nearest drawn segment of the diagram."""
    return min(
        distance_to_segment(point, start, end)
        for start, end in DRAWN_SEGMENTS
    )


def ray_cast_inside(point, polygon) -> bool:
    """Strict interior test by ray casting; undefined exactly on an edge.

    Callers that may sit on an edge use :func:`point_in_polygon`, which tests
    the boundary first. This bare form exists because the 200x200 grid check
    excludes boundary points up front and would otherwise pay for the edge test
    forty thousand times over.
    """
    x, y = point
    inside = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing:
                inside = not inside
    return inside


def point_on_polygon_boundary(point, polygon, tol: float = 1e-9) -> bool:
    count = len(polygon)
    for index in range(count):
        start = polygon[index]
        end = polygon[(index + 1) % count]
        if distance_to_segment(point, start, end) <= tol:
            return True
    return False


def point_in_polygon(
    point, polygon, *, include_boundary: bool = False, tol: float = 1e-9
) -> bool:
    """Point-in-polygon with an explicit decision about the boundary."""
    if point_on_polygon_boundary(point, polygon, tol):
        return include_boundary
    return ray_cast_inside(point, polygon)


def is_sub_segment(segment, container, tol: float = 1e-9) -> bool:
    """True when ``segment`` lies wholly inside the segment ``container``."""
    start, end = segment
    outer_start, outer_end = container
    return (
        distance_to_segment(start, outer_start, outer_end) <= tol
        and distance_to_segment(end, outer_start, outer_end) <= tol
    )


def same_segment(first, second, tol: float = 1e-9) -> bool:
    """Segment equality, ignoring direction."""
    (a1, a2), (b1, b2) = first, second
    forward = (
        math.dist(a1, b1) <= tol and math.dist(a2, b2) <= tol
    )
    backward = (
        math.dist(a1, b2) <= tol and math.dist(a2, b1) <= tol
    )
    return forward or backward


# --- the size ladder and the one sizing algorithm (section 6) --------------

#: Entry sizes as fractions of the chart side: base first, floor last.
SIZE_LADDER: tuple[float, ...] = (
    0.032, 0.030, 0.028, 0.026, 0.024, 0.022, 0.021,
)
FLOOR_SIZE = SIZE_LADDER[-1]
BASE_SIZE = SIZE_LADDER[0]

LINE_HEIGHT = 1.45
CHAR_ADVANCE = 0.68
LEFT_INSET = 0.01
#: 9-character worst case ``Me 29 deg 59'`` at 0.68 em, as a multiple of f.
WIDTH_BUDGET_EMS = 6.12
ABBR_SLOT = 1.45
ABBR_DEG_GAP = 0.45
DEG_OFFSET = ABBR_SLOT + ABBR_DEG_GAP  # 1.90 f
RETRO_DROP = 0.22
RETRO_STROKE = 0.06
ASCENT = 0.75
DESCENT = 0.25


def entry_width_budget(size: float) -> float:
    """W(f) = left inset + the fixed nine-character worst case."""
    return LEFT_INSET + WIDTH_BUDGET_EMS * size


def capacity(height: float, size: float) -> int:
    """How many whole rows of pitch 1.45 f fit in a box of this height."""
    return math.floor(height / (LINE_HEIGHT * size))


def width_gated_size(width: float) -> float:
    """The largest ladder size whose width budget fits the box width."""
    for size in SIZE_LADDER:
        if entry_width_budget(size) <= width:
            return size
    return FLOOR_SIZE


def select_size(count: int, width: float, height: float):
    """Return ``(size, shown, overflow)`` for ``count`` entries in a box.

    The width gate first, then the largest size that fits every entry; failing
    both, the floor, with one row surrendered to the ``+n`` indicator. The
    result depends only on the box and the entry count -- never on which
    grahas are involved -- because the width budget is a fixed worst case.
    """
    gate = width_gated_size(width)
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


# --- free-text wrapping (section 7) ----------------------------------------


def wrap_text(text: str, budget: int) -> list[str]:
    """Greedy whitespace wrapping with a hard split, dropping nothing.

    Tokens are packed greedily into lines of at most ``budget`` characters. A
    single token longer than the budget -- a place name written without
    spaces -- is cut at exactly ``budget`` characters as many times as needed,
    so no text is ever discarded and no line ever exceeds the budget.
    """
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


# --- bands and the legend's slot layout (section 7) ------------------------

BAND_PADDING = 16
BAND_WIDTH = 1000.0
FREE_TEXT_ADVANCE = 0.75
LEGEND_INDENT_CHARS = 4
LEGEND_SLOT_CHARS_WITH_DEGREES = 6
LEGEND_GAP_EMS = 1.00


def character_budget(font: float) -> int:
    """B = floor(1000 / (0.75 F)): 0.68 em plus a ten per cent margin."""
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
    """A slot reproduces section 4's abbreviation/degree spacing at F_l."""
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
