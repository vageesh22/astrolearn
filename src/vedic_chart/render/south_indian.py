"""Layer 19, part 2: the South Indian D1 chart as a self-contained SVG string.

The renderer performs no astronomy and no astrology. A graha's cell is its
``rashi_index``, a cell's house label is the ``number`` of the ``D1House``
whose ``rashi_index`` is that sign, and the Lagna's cell is
``lagna.rashi_index``; nothing else is read and no house formula exists here.
Degrees come from Layer 9's truncating ``dms(0)`` and are never rounded.

The conventions shared with Layer 10 (abbreviations, full names, option
validation, caption content, style numbers, typography) are **re-declared**
here rather than imported from the frozen Layer 10 renderer; the test suite
pins every one of them equal to its Layer 10 counterpart.

The output is deterministic: fixed attribute order, two-decimal coordinates,
no generated identifier, no timestamp. With ``caption`` off, the birth date,
time, zone, place, Julian Day and ayanamsha value are never assembled, so they
cannot reach the title, the description, an attribute or a comment.
"""

import math
import re
from dataclasses import dataclass
from xml.sax.saxutils import escape

from vedic_chart.representation.d1 import D1Chart
from vedic_chart.vedic.grahas import Graha

from . import south_indian_geometry as geo

__all__ = ["SouthIndianOptions", "render_south_indian_svg"]

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

NODES = (Graha.RAHU, Graha.KETU)

LAGNA_KEY = "lagna"
LAGNA_ABBR = "As"

#: Every South Indian cell uses the one-line layout.
LAYOUT_INLINE = "inline"

DEGREE_SIGN = "°"
PRIME_SIGN = "′"
EM_DASH = "—"
MIDDLE_DOT = "·"

#: Compact caption forms of the Layer 9 ayanamsha descriptor, matched on the
#: whole string; an unknown descriptor is shown verbatim.
COMPACT_AYANAMSHA_LABELS = {
    "Lahiri (Chitrapaksha), true equinox": "Lahiri (true equinox)",
}

#: A value outside these mappings raises rather than being guessed at.
HOUSE_SYSTEM_LABELS = {"whole_sign": "Whole Sign"}
NODE_LABELS = {"mean": "Mean Node"}

#: A letter then up to 31 letters, digits, hyphens or underscores.
ID_PREFIX_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}")

TITLE_PLAIN = "D1 chart (South Indian)"
CENTRE_TEXT = "D1 / Rashi"
MARKER_LAGNA_LINE = (
    "As = Lagna (ascendant), first in its cell; thicker border"
)
MARKER_RETRO_DEFAULT = "Underline = retrograde; not shown for Ra and Ke"
MARKER_RETRO_NODES = "Underline = retrograde; shown for Ra and Ke too"
LEGEND_HEADING_FORMAT = "{rashi_name} (H{house}) {dash} complete list:"


@dataclass(frozen=True)
class SouthIndianStyle:
    """Private style constants; the shared numbers mirror Layer 10's
    ``RenderStyle``. Fractions are of the chart side; band fonts and pitches
    are viewBox units."""

    font_family: str = '"DejaVu Sans", Arial, Helvetica, sans-serif'
    numeral_font: float = 0.026
    stroke: float = 0.0025
    ink: str = "#000000"
    paper: str = "#ffffff"

    canvas_width: int = 1080
    chart_side: int = 1000
    margin: int = 40
    chart_gap: int = 30

    caption_font: float = 24.0
    caption_pitch: int = 32
    legend_font: float = 22.0
    legend_pitch: int = 30

    label_font: float = 0.020
    label_row: float = 0.032
    centre_font: float = 0.032
    lagna_stroke_factor: float = 2.0


_STYLE = SouthIndianStyle()
LABEL_FONT = _STYLE.label_font
LABEL_ROW = _STYLE.label_row
CENTRE_FONT = _STYLE.centre_font
_CAPTION_BUDGET = geo.character_budget(_STYLE.caption_font)
_LEGEND_BUDGET = geo.character_budget(_STYLE.legend_font)


@dataclass(frozen=True)
class SouthIndianOptions:
    """The complete public option set for the South Indian renderer."""

    show_degrees: bool = True
    mark_node_retrograde: bool = False
    caption: bool = False
    width: int | None = None
    id_prefix: str = "d1-south"

    def __post_init__(self) -> None:
        for name in ("show_degrees", "mark_node_retrograde", "caption"):
            value = getattr(self, name)
            if type(value) is not bool:
                raise ValueError(
                    f"{name} must be exactly True or False; got {value!r}."
                )
        width = self.width
        if width is not None:
            if isinstance(width, bool) or not isinstance(width, int):
                raise ValueError(
                    f"width must be None or an int of at least 1 CSS pixel; "
                    f"got {width!r}."
                )
            if width < 1:
                raise ValueError(
                    f"width must be None or an int of at least 1 CSS pixel; "
                    f"got {width!r}."
                )
        prefix = self.id_prefix
        if type(prefix) is not str or ID_PREFIX_PATTERN.fullmatch(prefix) is None:
            raise ValueError(
                f"id_prefix must be a str of 1 to 32 ASCII characters matching "
                f"[A-Za-z][A-Za-z0-9_-]{{0,31}}; got {prefix!r}."
            )


# --- internal plan objects -------------------------------------------------


@dataclass(frozen=True)
class _Entry:
    """One displayed row of a cell or one slot of a legend line."""

    key: str
    abbr: str
    degree_text: str
    underline: bool


@dataclass(frozen=True)
class _SignPlan:
    rashi_index: int
    rashi_number: int
    rashi_name: str
    house: int
    is_lagna: bool
    size: float
    shown: tuple[_Entry, ...]
    overflow_count: int
    overflows: bool
    occupants: tuple[_Entry, ...]


# --- formatting primitives -------------------------------------------------


def _number(value: float) -> str:
    return f"{value:.2f}"


def _chars(value) -> str:
    """Escape dynamic text for use as character data."""
    return escape(str(value))


def _attribute(value) -> str:
    """Escape a value for use inside a double-quoted attribute."""
    return escape(str(value), {'"': "&quot;", "'": "&#39;"})


def _degree_text(dms) -> str:
    """``D<deg>MM<prime>`` from a Layer 9 DMS; seconds are not shown."""
    return f"{dms.degrees}{DEGREE_SIGN}{dms.minutes:02d}{PRIME_SIGN}"


def _time_text(birth_time) -> str:
    if birth_time.microsecond != 0:
        return birth_time.strftime("%H:%M:%S.%f")
    if birth_time.second != 0:
        return birth_time.strftime("%H:%M:%S")
    return birth_time.strftime("%H:%M")


# --- chart reading ---------------------------------------------------------


def _underlined(placement, options: SouthIndianOptions) -> bool:
    if not placement.is_retrograde:
        return False
    if placement.graha in NODES and not options.mark_node_retrograde:
        return False
    return True


def _entry_for(chart: D1Chart, graha: Graha, options: SouthIndianOptions) -> _Entry:
    placement = chart.grahas[graha]
    return _Entry(
        key=graha.value,
        abbr=ABBREVIATIONS[graha],
        degree_text=(
            _degree_text(placement.dms(0)) if options.show_degrees else ""
        ),
        underline=_underlined(placement, options),
    )


def _lagna_entry(chart: D1Chart, options: SouthIndianOptions) -> _Entry:
    return _Entry(
        key=LAGNA_KEY,
        abbr=LAGNA_ABBR,
        degree_text=(
            _degree_text(chart.lagna.dms(0)) if options.show_degrees else ""
        ),
        underline=False,
    )


def _house_by_rashi(chart: D1Chart) -> dict:
    """``rashi_index -> D1House``, read from the representation."""
    return {house.rashi_index: house for house in chart.houses}


def _plan_sign(chart: D1Chart, house, options: SouthIndianOptions) -> _SignPlan:
    is_lagna = house.rashi_index == chart.lagna.rashi_index
    occupants = tuple(
        _entry_for(chart, graha, options) for graha in house.occupants
    )
    entries: list[_Entry] = []
    if is_lagna:
        entries.append(_lagna_entry(chart, options))
    entries.extend(occupants)

    size, shown_count, overflow = geo.select_size(
        len(entries), geo.ENTRY_WIDTH, geo.ENTRY_HEIGHT, options.show_degrees
    )
    shown = tuple(entries[:shown_count])
    if overflow:
        shown_occupants = sum(1 for entry in shown if entry.key != LAGNA_KEY)
        overflow_count = len(occupants) - shown_occupants
    else:
        overflow_count = 0

    return _SignPlan(
        rashi_index=house.rashi_index,
        rashi_number=house.rashi_number,
        rashi_name=house.rashi_name,
        house=house.number,
        is_lagna=is_lagna,
        size=size,
        shown=shown,
        overflow_count=overflow_count,
        overflows=overflow,
        occupants=occupants,
    )


# --- caption and description ----------------------------------------------


def _descriptor_labels(meta) -> tuple[str, str]:
    """The visible and the accessible convention line, from ``D1Meta``."""
    ayanamsha = meta.ayanamsha
    compact = COMPACT_AYANAMSHA_LABELS.get(ayanamsha, ayanamsha)
    if meta.house_system not in HOUSE_SYSTEM_LABELS:
        raise ValueError(
            f"house_system {meta.house_system!r} is not supported by the "
            f"South Indian renderer."
        )
    if meta.node not in NODE_LABELS:
        raise ValueError(
            f"node {meta.node!r} is not supported by the South Indian "
            f"renderer."
        )
    house_label = HOUSE_SYSTEM_LABELS[meta.house_system]
    node_label = NODE_LABELS[meta.node]
    return (
        f"{compact} {MIDDLE_DOT} {house_label} {MIDDLE_DOT} {node_label}",
        f"{ayanamsha} {MIDDLE_DOT} {house_label} houses {MIDDLE_DOT} "
        f"{node_label}",
    )


def _caption_lines(chart: D1Chart) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(visible_lines, accessible_lines)`` -- they differ in line 3 only."""
    meta = chart.meta
    request = meta.request
    visible_descriptors, accessible_descriptors = _descriptor_labels(meta)
    head = (
        f"{request.birth_date.isoformat()} {_time_text(request.birth_time)} "
        f"{meta.location.timezone_id}",
        meta.location.canonical_name,
    )
    return head + (visible_descriptors,), head + (accessible_descriptors,)


def _description(
    chart: D1Chart, plans: list[_SignPlan], caption_lines: tuple[str, ...]
) -> str:
    parts: list[str] = [f"{line}." for line in caption_lines]
    lagna = chart.lagna
    parts.append(
        f"Lagna in rashi {lagna.rashi_number} ({lagna.rashi_name}), house 1, "
        f"at {_degree_text(lagna.dms(0))}."
    )
    houses = _house_by_rashi(chart)
    for plan in plans:
        house = houses[plan.rashi_index]
        if not house.occupants:
            continue
        body = "; ".join(
            f"{FULL_NAMES[graha]} "
            f"{_degree_text(chart.grahas[graha].dms(0))}, "
            f"{'retrograde' if chart.grahas[graha].is_retrograde else 'direct'}"
            for graha in house.occupants
        )
        parts.append(f"{house.rashi_name} (house {house.number}): {body}.")
    return " ".join(parts)


# --- element emitters ------------------------------------------------------


def _text_element(
    css_class: str,
    x: float,
    y: float,
    font: float,
    anchor: str,
    content: str,
    *,
    central_baseline: bool = False,
) -> str:
    parts = [f'<text class="{css_class}"']
    parts.append(f' x="{_number(x)}" y="{_number(y)}"')
    parts.append(f' font-family="{_attribute(_STYLE.font_family)}"')
    parts.append(f' font-size="{_number(font)}"')
    parts.append(f' text-anchor="{anchor}"')
    if central_baseline:
        parts.append(' dominant-baseline="central"')
    parts.append(f' fill="{_STYLE.ink}">')
    parts.append(content)
    parts.append("</text>")
    return "".join(parts)


def _retro_element(x: float, y: float, length: float, stroke: float) -> str:
    return (
        f'<line class="retro"'
        f' x1="{_number(x)}" y1="{_number(y)}"'
        f' x2="{_number(x + length)}" y2="{_number(y)}"'
        f' stroke="{_STYLE.ink}" stroke-width="{_number(stroke)}"/>'
    )


def _entry_group(
    css_class: str, entry: _Entry, x: float, baseline: float, font: float
) -> list[str]:
    """One logical entry: abbreviation, optional degrees, optional underline."""
    lines = [f'<g class="{css_class}" data-graha="{_attribute(entry.key)}">']
    lines.append(
        _text_element("abbr", x, baseline, font, "start", _chars(entry.abbr))
    )
    if entry.degree_text:
        lines.append(
            _text_element(
                "degrees",
                x + geo.DEG_OFFSET * font,
                baseline,
                font,
                "start",
                _chars(entry.degree_text),
            )
        )
    if entry.underline:
        lines.append(
            _retro_element(
                x,
                baseline + geo.RETRO_DROP * font,
                geo.ABBR_SLOT * font,
                geo.RETRO_STROKE * font,
            )
        )
    lines.append("</g>")
    return lines


# --- the renderer ----------------------------------------------------------


def render_south_indian_svg(
    chart: D1Chart, options: SouthIndianOptions = SouthIndianOptions()
) -> str:
    """Render one ``D1Chart`` as a South Indian chart SVG document."""
    if not isinstance(chart, D1Chart):
        raise ValueError(
            f"chart must be a D1Chart; got {type(chart).__name__}."
        )
    if not isinstance(options, SouthIndianOptions):
        raise ValueError(
            f"options must be a SouthIndianOptions; got "
            f"{type(options).__name__}."
        )

    # The convention labels are read only when a caption is requested (they
    # exist to build it, as in Layer 10); an unsupported one is then rejected
    # before a single character of the document exists. Without a caption
    # the labels are not read and the document renders regardless.
    caption_lines: tuple[str, ...] = ()
    description_lines: tuple[str, ...] = ()
    if options.caption:
        caption_lines, description_lines = _caption_lines(chart)

    style = _STYLE
    side = float(style.chart_side)
    houses = _house_by_rashi(chart)
    plans = [
        _plan_sign(chart, houses[rashi_index], options)
        for rashi_index in range(len(geo.CELL_BY_RASHI_INDEX))
    ]

    caption_wrapped: list[str] = []
    for line in caption_lines:
        caption_wrapped.extend(geo.wrap_text(line, _CAPTION_BUDGET))
    caption_height = (
        geo.band_height(len(caption_wrapped), style.caption_pitch)
        if options.caption
        else 0
    )

    marker_wrapped: list[str] = []
    for line in (
        MARKER_LAGNA_LINE,
        MARKER_RETRO_NODES if options.mark_node_retrograde
        else MARKER_RETRO_DEFAULT,
    ):
        marker_wrapped.extend(geo.wrap_text(line, _LEGEND_BUDGET))

    per_line = geo.legend_entries_per_line(style.legend_font, options.show_degrees)
    blocks: list[tuple[_SignPlan, list[str], list[tuple[_Entry, ...]]]] = []
    for plan in plans:
        if not plan.overflows:
            continue
        heading = geo.wrap_text(
            LEGEND_HEADING_FORMAT.format(
                rashi_name=plan.rashi_name, house=plan.house, dash=EM_DASH
            ),
            _LEGEND_BUDGET,
        )
        rows = [
            plan.occupants[start:start + per_line]
            for start in range(0, len(plan.occupants), per_line)
        ]
        blocks.append((plan, heading, rows))

    legend_line_count = len(marker_wrapped) + sum(
        len(heading) + len(rows) for _, heading, rows in blocks
    )
    legend_height = geo.band_height(legend_line_count, style.legend_pitch)

    document_height = (
        style.margin
        + caption_height
        + style.chart_side
        + style.chart_gap
        + legend_height
        + style.margin
    )

    chart_left = float(style.margin)
    chart_top = float(style.margin + caption_height)
    legend_top = float(
        style.margin + caption_height + style.chart_side + style.chart_gap
    )

    def to_x(value: float) -> float:
        return chart_left + value * side

    def to_y(value: float) -> float:
        return chart_top + value * side

    title = TITLE_PLAIN
    if options.caption:
        title = f"{TITLE_PLAIN} {EM_DASH} {chart.meta.location.canonical_name}"

    prefix = options.id_prefix
    out: list[str] = []
    root = [
        '<svg xmlns="http://www.w3.org/2000/svg" role="img"',
        f' aria-labelledby="{prefix}-title"'
        f' aria-describedby="{prefix}-desc"',
        f' viewBox="0 0 {style.canvas_width} {document_height}"',
        ' preserveAspectRatio="xMidYMin meet"',
    ]
    if options.width is not None:
        pixel_height = math.floor(
            options.width * document_height / style.canvas_width
        )
        root.append(f' width="{options.width}" height="{pixel_height}"')
    root.append(">")
    out.append("".join(root))

    out.append(f'<title id="{prefix}-title">{_chars(title)}</title>')
    out.append(
        f'<desc id="{prefix}-desc">'
        f'{_chars(_description(chart, plans, description_lines))}</desc>'
    )
    out.append(
        f'<rect class="paper" x="0.00" y="0.00"'
        f' width="{_number(style.canvas_width)}"'
        f' height="{_number(document_height)}" fill="{style.paper}"/>'
    )

    if options.caption:
        out.append('<g class="caption">')
        for index, line in enumerate(caption_wrapped):
            out.append(
                _text_element(
                    "caption-line",
                    chart_left,
                    geo.band_baseline(
                        float(style.margin),
                        index,
                        style.caption_font,
                        style.caption_pitch,
                    ),
                    style.caption_font,
                    "start",
                    _chars(line),
                )
            )
        out.append("</g>")

    out.append('<g class="chart">')

    # The grid: each canonical edge exactly once; the Lagna cell's four edges
    # are the same canonical edges at twice the stroke width.
    lagna_edges = set(geo.rashi_cell_edges(chart.lagna.rashi_index))
    normal_stroke = style.stroke * side
    out.append('<g class="grid">')
    for edge in geo.GRID_EDGES:
        (x1, y1), (x2, y2) = geo.edge_to_unit(edge)
        thick = edge in lagna_edges
        css_class = "cell-edge lagna" if thick else "cell-edge"
        width = normal_stroke * (style.lagna_stroke_factor if thick else 1.0)
        out.append(
            f'<line class="{css_class}"'
            f' x1="{_number(to_x(x1))}" y1="{_number(to_y(y1))}"'
            f' x2="{_number(to_x(x2))}" y2="{_number(to_y(y2))}"'
            f' stroke="{style.ink}" stroke-width="{_number(width)}"'
            f' stroke-linecap="square"/>'
        )
    out.append("</g>")

    out.append('<g class="centre">')
    out.append(
        _text_element(
            "centre-label",
            to_x(geo.CENTRE_POINT[0]),
            to_y(geo.CENTRE_POINT[1]),
            style.centre_font * side,
            "middle",
            _chars(CENTRE_TEXT),
            central_baseline=True,
        )
    )
    out.append("</g>")

    label_font = style.label_font * side
    for plan in plans:
        rashi_index = plan.rashi_index
        cell = geo.cell_box(rashi_index)
        out.append(
            f'<g class="sign" data-rashi="{plan.rashi_number}"'
            f' data-house="{plan.house}"'
            f' data-lagna="{"true" if plan.is_lagna else "false"}"'
            f' data-layout="{LAYOUT_INLINE}">'
        )
        out.append(
            f'<rect class="cell" x="{_number(to_x(cell.x0))}"'
            f' y="{_number(to_y(cell.y0))}"'
            f' width="{_number(cell.width * side)}"'
            f' height="{_number(cell.height * side)}"'
            f' fill="none" stroke="none"/>'
        )
        label_y = to_y(geo.label_baseline(rashi_index))
        out.append(
            _text_element(
                "sign-label",
                to_x(geo.sign_label_x(rashi_index)),
                label_y,
                label_font,
                "start",
                _chars(plan.rashi_name),
            )
        )
        out.append(
            _text_element(
                "house-label",
                to_x(geo.house_label_x(rashi_index)),
                label_y,
                label_font,
                "end",
                _chars(f"H{plan.house}"),
            )
        )

        box = geo.entry_box(rashi_index)
        font = plan.size * side
        row_x = to_x(geo.row_start_x(box.x0))
        for index, entry in enumerate(plan.shown):
            baseline = to_y(geo.row_baseline(box.y0, index, plan.size))
            out.extend(_entry_group("entry", entry, row_x, baseline, font))
        if plan.overflows:
            baseline = to_y(geo.row_baseline(box.y0, len(plan.shown), plan.size))
            out.append(
                _text_element(
                    "overflow", row_x, baseline, font, "start",
                    _chars(f"+{plan.overflow_count}"),
                )
            )
        out.append("</g>")
    out.append("</g>")

    out.append('<g class="legend">')
    line_index = 0
    legend_font = style.legend_font
    for line in marker_wrapped:
        out.append(
            _text_element(
                "legend-marker",
                chart_left,
                geo.band_baseline(
                    legend_top, line_index, legend_font, style.legend_pitch
                ),
                legend_font,
                "start",
                _chars(line),
            )
        )
        line_index += 1

    for plan, heading, rows in blocks:
        out.append(
            f'<g class="legend-sign" data-rashi="{plan.rashi_number}"'
            f' data-house="{plan.house}">'
        )
        for line in heading:
            out.append(
                _text_element(
                    "legend-heading",
                    chart_left,
                    geo.band_baseline(
                        legend_top, line_index, legend_font, style.legend_pitch
                    ),
                    legend_font,
                    "start",
                    _chars(line),
                )
            )
            line_index += 1
        for row in rows:
            baseline = geo.band_baseline(
                legend_top, line_index, legend_font, style.legend_pitch
            )
            for slot, entry in enumerate(row):
                slot_x = chart_left + geo.legend_slot_x(
                    slot, legend_font, options.show_degrees
                )
                out.extend(
                    _entry_group(
                        "legend-entry", entry, slot_x, baseline, legend_font
                    )
                )
            line_index += 1
        out.append("</g>")
    out.append("</g>")

    out.append("</svg>")
    return "\n".join(out) + "\n"
