"""Layer 20: the ``overlay`` presentation block of one chart.

This module is a **presentation helper**, not a calculation. Its one public
function, :func:`overlay_block`, reads one ``D1Chart`` and formats, for that one
chart and nothing else, the facts a page needs to lay the nine graha
placements of *another* chart over the drawing of this one without holding any
geometry of its own:

* ``entries`` -- this chart's nine grahas in ``Graha`` order: the abbreviation,
  the renderers' ``D°MM′`` text from Layer 9's truncating ``dms(0)``, the
  underline flag the renderers would draw, and the rashi number;
* ``slots`` -- for every sign, in the North Indian and the South Indian layout,
  the house that sign occupies in this chart, the number of rows the renderer
  used for this chart's own text there, the ladder of row positions ("rungs")
  that fit beside that text, and the position of an auxiliary ``T:+n`` text
  marker, or ``None`` where the marker cannot keep its clearances.

It performs no astronomy, applies no astrological rule and has no notion of a
"natal" or a "transit" chart: it sees one chart at a time, and the page decides
which chart's ``slots`` and which chart's ``entries`` it combines. The engine is
never touched.

The plan the renderers make for this chart's own text is re-derived here with
the geometry modules' own functions (``select_size``, ``select_side_size``,
``side_box`` ...). Neither renderer is imported: the conventions shared with
them -- the abbreviations, the node set, the degree format, the style numbers
and the two-decimal ``_number`` rule -- are **re-declared** below, and the test
suite pins every one of them equal to its renderer counterpart.

Coordinates are absolute SVG user units of a **no-caption** document, as the
renderers draw it: ``x = 40 + 1000 u`` and ``y = 40 + 1000 u``. A captioned
document moves the chart down by its caption band, which this block does not
know; the helper therefore has no caption parameter and its coordinates are
valid for no-caption documents only (the viewer's profile). Every coordinate
is a string with two decimals; counts are integers.

Truncation, never rounding: ``round()`` appears nowhere in this module. The one
placement that sits *exactly* on a clearance limit -- the side-house marker,
15 units below this chart's side box -- has its baseline rounded **up** to the
next hundredth (``math.ceil``) so that the formatted value keeps the limit.
Every marker is accepted only after its clearances are evaluated on the
formatted coordinates.
"""

import math
from dataclasses import dataclass

from vedic_chart.representation.d1 import D1Chart
from vedic_chart.vedic.grahas import Graha

from . import north_indian_geometry as ng
from . import south_indian_geometry as sg

__all__ = ["overlay_block"]

SCHEMA = "vedic_chart.overlay/1"

#: The textual marker the page prepends to every row it draws from a block's
#: ``entries`` (and to the ``+n`` marker): the distinction survives grayscale.
PREFIX = "T:"

# --- conventions re-declared from the renderers (pinned equal by tests) ----

ABBREVIATIONS = {
    Graha.SUN: "Su",
    Graha.MOON: "Mo",
    Graha.MERCURY: "Me",
    Graha.VENUS: "Ve",
    Graha.MARS: "Ma",
    Graha.JUPITER: "Ju",
    Graha.SATURN: "Sa",
    Graha.RAHU: "Ra",
    Graha.KETU: "Ke",
}

NODES = (Graha.RAHU, Graha.KETU)

DEGREE_SIGN = "°"
PRIME_SIGN = "′"

LAYOUT_INLINE = "inline"
LAYOUT_STACKED = "stacked"

ANCHOR_START = "start"
ANCHOR_MIDDLE = "middle"
ANCHOR_END = "end"


@dataclass(frozen=True)
class OverlayStyle:
    """The style numbers this block shares with the two renderers.

    ``font_family`` is published in the block so that the page copies it
    rather than holding a presentation constant. ``numeral_font`` and
    ``label_font`` size the glyph boxes the marker keeps clear of; ``ink`` is
    the renderers' text colour, recorded for the parity test only (the block
    emits no colour). Fractions are of the chart side.
    """

    font_family: str = '"DejaVu Sans", Arial, Helvetica, sans-serif'
    numeral_font: float = 0.026
    label_font: float = 0.020
    #: Owner decision D13: the auxiliary ``T:+n`` marker is 20-unit text;
    #: planet-entry rows keep the ladder's 21-unit floor.
    marker_font: float = 0.020
    ink: str = "#000000"
    chart_side: int = 1000
    margin: int = 40


_STYLE = OverlayStyle()

# --- the transit width budgets (section 6.2) --------------------------------

#: ``T:Me 29°59′`` -- the prefix plus the renderers' nine-character worst case.
TRANSIT_WIDTH_CHARS = 11
#: ``T:Su`` -- the prefix plus an abbreviation.
TRANSIT_ABBR_CHARS = 4
#: ``T:+n`` -- the auxiliary marker.
MARKER_CHARS = 4

TRANSIT_WIDTH_EMS = TRANSIT_WIDTH_CHARS * ng.CHAR_ADVANCE  # 7.48
TRANSIT_ABBR_EMS = TRANSIT_ABBR_CHARS * ng.CHAR_ADVANCE  # 2.72
#: The degree element of an inline row: the ``T:Su`` slot plus the
#: renderers' abbreviation-to-degree gap.
TRANSIT_DEG_OFFSET = TRANSIT_ABBR_EMS + ng.ABBR_DEG_GAP  # 3.17

# --- the marker placement rules (section 5.4) -------------------------------

#: Cap height of a DejaVu Sans digit, in ems: the numeral glyph box is this
#: tall and centred on the numeral (the renderer centres it vertically).
DIGIT_HEIGHT = 0.729

#: Every North clearance of the marker's glyph box: polygon edges, the
#: numeral glyph box and this chart's text boxes.
MARKER_CLEARANCE = ng.MIN_BOX_CLEARANCE

#: Kites 1 and 7 and triangles 2, 6, 8 and 12: the marker is centred on the
#: numeral's x in the gap between this chart's text and the numeral.
CENTRED_MARKER_HOUSES = (1, 2, 6, 7, 8, 12)

#: Kites 4 and 10: the marker sits this far above (failing that, below) the
#: numeral and this far toward the box side, where the kite is wider.
KITE_MARKER_OFFSET = 0.045

#: South: the marker keeps the renderers' abbreviation-to-degree gap, 0.45 em
#: at the label font (9 units), from both labels of the label row.
MARKER_LABEL_GAP_EMS = ng.ABBR_DEG_GAP

#: The glyph-box model of the South ``H<n>`` label, which the marker is
#: right-aligned against. The renderers' 0.68 em per character is a worst
#: case for digits and two-letter abbreviations, but the capital ``H`` is
#: wider in the renderers' first font (DejaVu Sans: ``H`` 0.752 em, digits
#: 0.636 em; the Arial/Helvetica fallbacks are narrower). The closing
#: browser check measured ``H1`` at 27.76 units against the 27.2 of the
#: uniform model, leaving 8.44 units instead of the required 9; these
#: allowances keep the modelled label at least as wide as the drawn one.
HOUSE_LABEL_H_EMS = 0.80
HOUSE_LABEL_DIGIT_EMS = 0.66


def house_label_width(house_number: int, font: float) -> float:
    """The modelled width of ``H<n>``: one ``H`` plus its digits."""
    digits = len(str(house_number))
    return (HOUSE_LABEL_H_EMS + digits * HOUSE_LABEL_DIGIT_EMS) * font

#: Floating-point slack of every clearance comparison, in unit-square units.
TOLERANCE = 1e-9


# --- formatting --------------------------------------------------------------


def _number(value: float) -> str:
    """The renderers' coordinate format: two decimals."""
    return f"{value:.2f}"


def _number_up(value: float) -> str:
    """Two decimals, rounded up to the next hundredth.

    Used for the one placement that sits exactly on a clearance limit, so
    that formatting can only move it away from the box it keeps clear of. The
    ``1e-6`` hundredths absorb the float noise of a value that already is a
    whole hundredth.
    """
    return _number(math.ceil(value * 100.0 - 1e-6) / 100.0)


def _to_x(value: float) -> float:
    return _STYLE.margin + value * _STYLE.chart_side


def _to_y(value: float) -> float:
    # No caption: the chart's top is the margin, as on the x axis.
    return _STYLE.margin + value * _STYLE.chart_side


def _units(size: float) -> str:
    return _number(size * _STYLE.chart_side)


def _from_units(text: str) -> float:
    """A formatted coordinate back on the unit square (for the checks)."""
    return (float(text) - _STYLE.margin) / _STYLE.chart_side


def _degree_text(dms) -> str:
    """``D<deg>MM<prime>`` from a Layer 9 DMS; seconds are not shown."""
    return f"{dms.degrees}{DEGREE_SIGN}{dms.minutes:02d}{PRIME_SIGN}"


# --- entries -------------------------------------------------------------------


def _entries(chart: D1Chart, show_degrees: bool, mark_node_retrograde: bool):
    entries = []
    for graha in Graha:
        placement = chart.grahas[graha]
        underline = bool(placement.is_retrograde) and (
            graha not in NODES or mark_node_retrograde
        )
        entries.append(
            {
                "key": graha.value,
                "abbr": ABBREVIATIONS[graha],
                "degree_text": (
                    _degree_text(placement.dms(0)) if show_degrees else ""
                ),
                "underline": underline,
                "rashi_number": placement.rashi_number,
            }
        )
    return entries


# --- the renderers' own plan for this chart's text ---------------------------


@dataclass(frozen=True)
class _Plan:
    """What a renderer draws for this chart's own text in one cell.

    ``rows`` is the number of rows it uses: the shown entries plus one when
    the cell overflows (a stacked cell counts entries). ``box`` is the inline
    cell's box, or the side house's occupant-dependent box, which already
    includes the ``+n`` row of an overflowing cell.
    """

    size: float
    rows: int
    box: object


def _north_plan(chart: D1Chart, region, show_degrees: bool) -> _Plan:
    house = chart.house(region.house)
    count = len(house.occupants) + (1 if region.house == 1 else 0)
    if region.house in ng.SIDE_HOUSES:
        size, shown, overflow = ng.select_side_size(count, show_degrees)
        box = ng.side_box(
            region,
            ng.side_rows_height(shown, size, show_degrees, overflow),
            ng.side_width_budget(size, show_degrees),
        )
    else:
        box = region.box
        size, shown, overflow = ng.select_size(count, box.width, box.height)
    return _Plan(size=size, rows=shown + (1 if overflow else 0), box=box)


def _south_plan(chart: D1Chart, house, show_degrees: bool) -> _Plan:
    is_lagna = house.rashi_index == chart.lagna.rashi_index
    count = len(house.occupants) + (1 if is_lagna else 0)
    size, shown, overflow = sg.select_size(
        count, sg.ENTRY_WIDTH, sg.ENTRY_HEIGHT, show_degrees
    )
    return _Plan(
        size=size,
        rows=shown + (1 if overflow else 0),
        box=sg.entry_box(house.rashi_index),
    )


# --- rungs ---------------------------------------------------------------------


def _inline_width(size: float, show_degrees: bool) -> float:
    """The inline transit row's width budget, inset included."""
    ems = TRANSIT_WIDTH_EMS if show_degrees else TRANSIT_ABBR_EMS
    return ng.LEFT_INSET + ems * size


def _inline_rungs(geo, box, plan: _Plan, show_degrees: bool) -> list:
    """Rows below this chart's text in an inline cell (kites, triangles and
    every South cell).

    The remainder box starts where this chart's rows end. For each ladder
    font passing the transit width gate, a rung lists every baseline that
    fits; a rung with no row, or with as many rows as the rung before it, is
    dropped -- except the floor rung, which is always present (possibly with
    no row at all).
    """
    top = box.y0 + plan.rows * geo.LINE_HEIGHT * plan.size
    height = box.y1 - top
    width = box.x1 - box.x0
    row_x = geo.row_start_x(box.x0)
    rungs = []
    last = None
    for size in geo.SIZE_LADDER:
        floor = size == geo.FLOOR_SIZE
        count = 0
        if _inline_width(size, show_degrees) <= width:
            count = max(geo.capacity(height, size), 0)
        if not floor and (count == 0 or count == last):
            continue
        last = count
        rung = {"font_size": _units(size), "x": _number(_to_x(row_x))}
        if show_degrees:
            rung["deg_x"] = _number(
                _to_x(row_x) + TRANSIT_DEG_OFFSET * size * _STYLE.chart_side
            )
        rung["rows"] = [
            _number(_to_y(geo.row_baseline(top, index, size)))
            for index in range(count)
        ]
        rungs.append(rung)
    return rungs


def _side_width(size: float, show_degrees: bool) -> float:
    """The stacked transit width: the renderers' side budget or the ``T:Su``
    abbreviation row, whichever is wider (4.08 em governs with degrees)."""
    return max(
        ng.side_width_budget(size, show_degrees),
        ng.LEFT_INSET + TRANSIT_ABBR_EMS * size,
    )


def _below_fits(bottom: float, width: float, numeral_y: float) -> bool:
    """The side-box corner rule generalised to a box below the numeral.

    The inner bottom corner of a box laid against the outer edge keeps the
    minimum clearance from the slanted edge exactly when ``width <=
    SIDE_EDGE_INTERCEPT - (bottom - numeral_y)``; the bottom itself stays
    within the triangle's half-height less the outer clearance.
    """
    return (
        width <= ng.SIDE_EDGE_INTERCEPT - (bottom - numeral_y)
        and bottom <= numeral_y + 0.25 - ng.OUTER_CLEARANCE
    )


def _stacked_rungs(region, plan: _Plan, show_degrees: bool) -> list:
    """Stacked entries in a North side house (3, 5, 9, 11).

    With no text of this chart in the cell, the renderer's own algorithm: for
    each ladder font, the largest count whose centred ``side_box`` is
    admissible. Otherwise the box starts one inter-entry gap below this
    chart's side box and grows while its inner bottom corner passes
    :func:`_below_fits`. Repeated or empty counts are dropped except at the
    floor, which is always present.
    """
    left = region.numeral[0] < 0.5
    numeral_y = region.numeral[1]
    rungs = []
    last = None
    for size in ng.SIZE_LADDER:
        floor = size == ng.FLOOR_SIZE
        width = _side_width(size, show_degrees)
        count = 0
        top = None
        if width <= ng.SIDE_NUMERAL_WIDTH_LIMIT:
            if plan.rows == 0:
                while ng.side_box_admissible(
                    ng.Box(
                        0.0,
                        0.0,
                        width,
                        ng.side_rows_height(count + 1, size, show_degrees),
                    )
                ):
                    count += 1
                if count:
                    top = ng.side_box(
                        region,
                        ng.side_rows_height(count, size, show_degrees),
                        width,
                    ).y0
            else:
                top = plan.box.y1 + ng.side_entry_gap(size, show_degrees)
                while _below_fits(
                    top + ng.side_rows_height(count + 1, size, show_degrees),
                    width,
                    numeral_y,
                ):
                    count += 1
        if not floor and (count == 0 or count == last):
            continue
        last = count
        x0 = (
            ng.OUTER_CLEARANCE
            if left
            else 1.0 - ng.OUTER_CLEARANCE - width
        )
        entries = []
        for index in range(count):
            entry = {
                "abbr_y": _number(
                    _to_y(ng.side_abbr_baseline(top, index, size, show_degrees))
                )
            }
            if show_degrees:
                entry["deg_y"] = _number(
                    _to_y(ng.side_deg_baseline(top, index, size, show_degrees))
                )
            entries.append(entry)
        rungs.append(
            {
                "font_size": _units(size),
                "x": _number(_to_x(ng.row_start_x(x0))),
                "entries": entries,
                "overflow_y": (
                    _number(
                        _to_y(
                            ng.side_abbr_baseline(
                                top, count - 1, size, show_degrees
                            )
                        )
                    )
                    if count
                    else None
                ),
            }
        )
    return rungs


# --- the auxiliary marker (section 5.4) --------------------------------------


def _marker_width() -> float:
    return MARKER_CHARS * ng.CHAR_ADVANCE * _STYLE.marker_font


def _marker_box(x_text: str, y_text: str, anchor: str):
    """The glyph box of a ``T:+n`` marker from its formatted position.

    ``4 x 0.68 em`` wide and ``1 em`` tall at the marker font, its top
    ``0.75 em`` above the baseline -- evaluated on the formatted strings, so
    every check below sees the coordinates the page will draw.
    """
    font = _STYLE.marker_font
    x = _from_units(x_text)
    y = _from_units(y_text)
    width = _marker_width()
    if anchor == ANCHOR_START:
        x0 = x
    elif anchor == ANCHOR_MIDDLE:
        x0 = x - width / 2.0
    else:
        x0 = x - width
    top = y - ng.ASCENT * font
    return ng.Box(x0, top, x0 + width, top + font)


def _numeral_glyph_box(region, rashi_number: int):
    """The North numeral's glyph box: ``chars x 0.68 em`` by the digit
    height, centred on the numeral point (central baseline)."""
    font = _STYLE.numeral_font
    half_width = len(str(rashi_number)) * ng.CHAR_ADVANCE * font / 2.0
    half_height = DIGIT_HEIGHT * font / 2.0
    x, y = region.numeral
    return ng.Box(x - half_width, y - half_height, x + half_width, y + half_height)


def _inline_text_box(box, plan: _Plan):
    """This chart's text in an inline North cell, or ``None`` when empty:
    from the row start to the renderers' width budget, ``rows x 1.45 f``
    tall from the box top."""
    if plan.rows == 0:
        return None
    return ng.Box(
        ng.row_start_x(box.x0),
        box.y0,
        box.x0 + ng.entry_width_budget(plan.size),
        box.y0 + plan.rows * ng.LINE_HEIGHT * plan.size,
    )


def _box_gap(first, second) -> float:
    """Euclidean gap between two axis-aligned boxes (0 when they overlap)."""
    dx = max(second.x0 - first.x1, first.x0 - second.x1, 0.0)
    dy = max(second.y0 - first.y1, first.y0 - second.y1, 0.0)
    return math.hypot(dx, dy)


def _box_edge_distance(box, polygon) -> float:
    """The least distance from the box's corners and the quarter, mid and
    three-quarter points of its sides to the polygon's edges."""
    points = list(box.corners)
    corners = list(box.corners)
    for index in range(4):
        (x0, y0), (x1, y1) = corners[index], corners[(index + 1) % 4]
        for t in (0.25, 0.5, 0.75):
            points.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    count = len(polygon)
    return min(
        ng.distance_to_segment(point, polygon[index], polygon[(index + 1) % count])
        for point in points
        for index in range(count)
    )


def _north_marker_clear(box, region, glyph, text_boxes) -> bool:
    polygon = region.polygon
    return (
        all(ng.point_in_polygon(corner, polygon) for corner in box.corners)
        and _box_edge_distance(box, polygon) >= MARKER_CLEARANCE - TOLERANCE
        and _box_gap(box, glyph) >= MARKER_CLEARANCE - TOLERANCE
        and all(
            _box_gap(box, text) >= MARKER_CLEARANCE - TOLERANCE
            for text in text_boxes
        )
    )


def _north_marker(region, plan: _Plan, rashi_number: int):
    font = _STYLE.marker_font
    width = _marker_width()
    glyph = _numeral_glyph_box(region, rashi_number)
    numeral_x, numeral_y = region.numeral
    candidates = []
    if region.house in ng.SIDE_HOUSES:
        # Left-aligned at the box's own x on the left; mirrored on the right.
        text_boxes = [plan.box] if plan.rows else []
        inset = ng.OUTER_CLEARANCE + ng.LEFT_INSET
        x0 = inset if numeral_x < 0.5 else 1.0 - inset - width
        if plan.rows:
            top = plan.box.y1 + MARKER_CLEARANCE
            y_text = _number_up(_to_y(top + ng.ASCENT * font))
        else:
            top = numeral_y - font / 2.0
            y_text = _number(_to_y(top + ng.ASCENT * font))
        candidates.append((_number(_to_x(x0)), y_text, ANCHOR_START))
    else:
        cell = region.box
        text = _inline_text_box(cell, plan)
        text_boxes = [text] if text is not None else []
        if region.house in CENTRED_MARKER_HOUSES:
            if cell.y1 <= numeral_y:
                low = text.y1 if text is not None else cell.y0
                high = glyph.y0
            else:
                low = glyph.y1
                high = cell.y0
            centres = [(numeral_x, (low + high) / 2.0)]
        else:
            centre_x = (
                numeral_x - KITE_MARKER_OFFSET
                if cell.x1 <= numeral_x
                else numeral_x + KITE_MARKER_OFFSET
            )
            centres = [
                (centre_x, numeral_y - KITE_MARKER_OFFSET),
                (centre_x, numeral_y + KITE_MARKER_OFFSET),
            ]
        for centre_x, centre_y in centres:
            baseline = centre_y - font / 2.0 + ng.ASCENT * font
            candidates.append(
                (
                    _number(_to_x(centre_x)),
                    _number(_to_y(baseline)),
                    ANCHOR_MIDDLE,
                )
            )
    for x_text, y_text, anchor in candidates:
        box = _marker_box(x_text, y_text, anchor)
        if _north_marker_clear(box, region, glyph, text_boxes):
            return {"x": x_text, "y": y_text, "anchor": anchor}
    return None


def _south_label_boxes(rashi_index: int, rashi_name: str, house_number: int):
    """The glyph boxes of the sign label and the ``H<n>`` label (x extent
    only matters; both sit on the label row)."""
    font = _STYLE.label_font
    row = sg.label_row_box(rashi_index)
    sign_x0 = sg.sign_label_x(rashi_index)
    sign = sg.Box(
        sign_x0,
        row.y0,
        sign_x0 + len(rashi_name) * sg.CHAR_ADVANCE * font,
        row.y1,
    )
    house_x1 = sg.house_label_x(rashi_index)
    house = sg.Box(
        house_x1 - house_label_width(house_number, font),
        row.y0,
        house_x1,
        row.y1,
    )
    return sign, house


def _south_marker(rashi_index: int, rashi_name: str, house_number: int):
    gap = MARKER_LABEL_GAP_EMS * _STYLE.label_font
    sign, house = _south_label_boxes(rashi_index, rashi_name, house_number)
    x_text = _number(_to_x(house.x0 - gap))
    y_text = _number(_to_y(sg.label_baseline(rashi_index)))
    box = _marker_box(x_text, y_text, ANCHOR_END)
    inner = sg.inner_box(rashi_index)
    fits = (
        box.x0 - sign.x1 >= gap - TOLERANCE
        and house.x0 - box.x1 >= gap - TOLERANCE
        and inner.contains_box(sg.Box(box.x0, box.y0, box.x1, box.y1), TOLERANCE)
    )
    if not fits:
        return None
    return {"x": x_text, "y": y_text, "anchor": ANCHOR_END}


# --- the block -------------------------------------------------------------------


def _north_slot(chart: D1Chart, house, show_degrees: bool) -> dict:
    region = ng.REGION_BY_HOUSE[house.number]
    plan = _north_plan(chart, region, show_degrees)
    stacked = region.house in ng.SIDE_HOUSES
    return {
        "house": house.number,
        "layout": LAYOUT_STACKED if stacked else LAYOUT_INLINE,
        "natal_rows": plan.rows,
        "rungs": (
            _stacked_rungs(region, plan, show_degrees)
            if stacked
            else _inline_rungs(ng, region.box, plan, show_degrees)
        ),
        "marker": _north_marker(region, plan, house.rashi_number),
    }


def _south_slot(chart: D1Chart, house, show_degrees: bool) -> dict:
    plan = _south_plan(chart, house, show_degrees)
    return {
        "house": house.number,
        "layout": LAYOUT_INLINE,
        "natal_rows": plan.rows,
        "rungs": _inline_rungs(
            sg, sg.entry_box(house.rashi_index), plan, show_degrees
        ),
        "marker": _south_marker(
            house.rashi_index, house.rashi_name, house.number
        ),
    }


def overlay_block(
    chart: D1Chart,
    *,
    show_degrees: bool = True,
    mark_node_retrograde: bool = False,
) -> dict:
    """The ``overlay`` block of one chart (Layer 20 section 6.2).

    ``show_degrees`` and ``mark_node_retrograde`` mean what they mean to the
    renderers and must be exactly ``True`` or ``False``. The result is a fresh
    ``dict`` of strings, integers, booleans, ``None``, lists and dicts only,
    deterministic for the same chart and flags. Slots are keyed by rashi
    number, ``"1"`` to ``"12"``, in that order, in both styles.
    """
    if not isinstance(chart, D1Chart):
        raise ValueError(f"chart must be a D1Chart; got {type(chart).__name__}.")
    for name, value in (
        ("show_degrees", show_degrees),
        ("mark_node_retrograde", mark_node_retrograde),
    ):
        if type(value) is not bool:
            raise ValueError(f"{name} must be exactly True or False; got {value!r}.")

    houses = sorted(chart.houses, key=lambda house: house.rashi_number)
    return {
        "schema": SCHEMA,
        "prefix": PREFIX,
        "font_family": _STYLE.font_family,
        "marker_font_size": _units(_STYLE.marker_font),
        "entries": _entries(chart, show_degrees, mark_node_retrograde),
        "slots": {
            "north": {
                str(house.rashi_number): _north_slot(chart, house, show_degrees)
                for house in houses
            },
            "south": {
                str(house.rashi_number): _south_slot(chart, house, show_degrees)
                for house in houses
            },
        },
    }
