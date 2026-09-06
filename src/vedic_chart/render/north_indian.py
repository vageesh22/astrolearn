"""Layer 10, part 2: the North Indian D1 chart as a self-contained SVG string.

The renderer performs no astronomy and no astrology. Every house, rashi,
occupant, degree and retrograde flag is read from the ``D1Chart`` it is handed;
its only arithmetic is the coordinate geometry of
:mod:`vedic_chart.render.north_indian_geometry` and the text-layout bookkeeping
below. Degrees are never recomputed and never rounded: the displayed value
comes from Layer 9's truncating ``dms(0)`` and nowhere else, so ``round()``
appears nowhere in this package.

The output is deterministic. Attribute order is fixed, every coordinate is
written with two decimals, no identifier is generated and no timestamp, path or
environment value reaches the document. Two renders of the same chart with the
same options are byte-identical.

Privacy is structural rather than advisory: with ``caption`` off, the birth
date, time, place, timezone identifier, Julian Day and ayanamsha value are not
assembled at all, so they cannot appear in the title, the description, an
attribute or a comment.
"""

import math
from dataclasses import dataclass
from xml.sax.saxutils import escape

from vedic_chart.representation.d1 import D1Chart
from vedic_chart.vedic.grahas import Graha

from . import north_indian_geometry as geo

__all__ = ["NorthIndianOptions", "render_north_indian_svg"]

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

DEGREE_SIGN = "°"
PRIME_SIGN = "′"
EM_DASH = "—"
MIDDLE_DOT = "·"

TITLE_PLAIN = "D1 chart (North Indian)"
MARKER_LAGNA_LINE = "As = Lagna (ascendant), first in house 1"
MARKER_RETRO_DEFAULT = "Underline = retrograde; not shown for Ra and Ke"
MARKER_RETRO_NODES = "Underline = retrograde; shown for Ra and Ke too"


@dataclass(frozen=True)
class RenderStyle:
    """Private v1 style constants. Not a parameter and not public API.

    Sizes given as fractions are fractions of the chart side; the band fonts
    and pitches are viewBox units, and the pitches are fixed integers rather
    than a multiplier applied to a font size.
    """

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


_STYLE = RenderStyle()
_CAPTION_BUDGET = geo.character_budget(_STYLE.caption_font)
_LEGEND_BUDGET = geo.character_budget(_STYLE.legend_font)


@dataclass(frozen=True)
class NorthIndianOptions:
    """The complete public option set for the North Indian renderer."""

    show_degrees: bool = True
    mark_node_retrograde: bool = False
    caption: bool = False
    width: int | None = None

    def __post_init__(self) -> None:
        for name in ("show_degrees", "mark_node_retrograde", "caption"):
            value = getattr(self, name)
            if type(value) is not bool:
                raise ValueError(
                    f"{name} must be exactly True or False; got {value!r}."
                )
        width = self.width
        if width is None:
            return
        if isinstance(width, bool) or not isinstance(width, int):
            raise ValueError(
                f"width must be None or an int of at least 1 CSS pixel; got "
                f"{width!r}."
            )
        if width < 1:
            raise ValueError(
                f"width must be None or an int of at least 1 CSS pixel; got "
                f"{width!r}."
            )


# --- internal plan objects -------------------------------------------------


@dataclass(frozen=True)
class _Entry:
    """One row of a cell or one slot of a legend line."""

    key: str
    abbr: str
    degree_text: str
    underline: bool


@dataclass(frozen=True)
class _HousePlan:
    house: int
    rashi_number: int
    size: float
    shown: tuple[_Entry, ...]
    overflow_count: int
    all_entries: tuple[_Entry, ...]

    @property
    def overflows(self) -> bool:
        return self.overflow_count > 0


# --- formatting primitives -------------------------------------------------


def _number(value: float) -> str:
    return f"{value:.2f}"


def _chars(value: str) -> str:
    """Escape dynamic text for use as character data."""
    return escape(str(value))


def _attribute(value: str) -> str:
    """Escape a value for use inside a double-quoted attribute."""
    return escape(str(value), {'"': "&quot;", "'": "&#39;"})


def _degree_text(dms) -> str:
    """``D<deg>MM<prime>`` from a Layer 9 DMS; seconds are simply not shown."""
    return f"{dms.degrees}{DEGREE_SIGN}{dms.minutes:02d}{PRIME_SIGN}"


def _time_text(birth_time) -> str:
    if birth_time.microsecond != 0:
        return birth_time.strftime("%H:%M:%S.%f")
    if birth_time.second != 0:
        return birth_time.strftime("%H:%M:%S")
    return birth_time.strftime("%H:%M")


# --- chart reading ---------------------------------------------------------


def _underlined(placement, options: NorthIndianOptions) -> bool:
    if not placement.is_retrograde:
        return False
    if placement.graha in NODES and not options.mark_node_retrograde:
        return False
    return True


def _entry_for(chart: D1Chart, graha: Graha, options: NorthIndianOptions) -> _Entry:
    placement = chart.grahas[graha]
    return _Entry(
        key=graha.value,
        abbr=ABBREVIATIONS[graha],
        degree_text=(
            _degree_text(placement.dms(0)) if options.show_degrees else ""
        ),
        underline=_underlined(placement, options),
    )


def _lagna_entry(chart: D1Chart, options: NorthIndianOptions) -> _Entry:
    return _Entry(
        key=LAGNA_KEY,
        abbr=LAGNA_ABBR,
        degree_text=(
            _degree_text(chart.lagna.dms(0)) if options.show_degrees else ""
        ),
        underline=False,
    )


def _plan_house(chart: D1Chart, region, options: NorthIndianOptions) -> _HousePlan:
    house = chart.house(region.house)
    entries: list[_Entry] = []
    if region.house == 1:
        entries.append(_lagna_entry(chart, options))
    entries.extend(_entry_for(chart, graha, options) for graha in house.occupants)

    size, shown_count, overflow = geo.select_size(
        len(entries), region.box.width, region.box.height
    )
    shown = tuple(entries[:shown_count])
    if overflow:
        shown_occupants = sum(1 for entry in shown if entry.key != LAGNA_KEY)
        overflow_count = len(house.occupants) - shown_occupants
    else:
        overflow_count = 0

    return _HousePlan(
        house=region.house,
        rashi_number=house.rashi_number,
        size=size,
        shown=shown,
        overflow_count=overflow_count,
        all_entries=tuple(
            _entry_for(chart, graha, options) for graha in house.occupants
        ),
    )


# --- caption and description ----------------------------------------------


def _caption_lines(chart: D1Chart) -> tuple[str, ...]:
    meta = chart.meta
    request = meta.request
    return (
        f"{request.birth_date.isoformat()} {_time_text(request.birth_time)} "
        f"{meta.location.timezone_id}",
        meta.location.canonical_name,
        f"{meta.ayanamsha} {MIDDLE_DOT} Whole Sign houses {MIDDLE_DOT} "
        f"Mean Node",
    )


def _description(chart: D1Chart, caption_lines: tuple[str, ...]) -> str:
    parts: list[str] = [f"{line}." for line in caption_lines]
    lagna = chart.lagna
    parts.append(
        f"Lagna in rashi {lagna.rashi_number} ({lagna.rashi_name}) at "
        f"{_degree_text(lagna.dms(0))}."
    )
    for house in chart.houses:
        if house.occupants:
            body = "; ".join(
                f"{FULL_NAMES[graha]} "
                f"{_degree_text(chart.grahas[graha].dms(0))}, "
                f"{'retrograde' if chart.grahas[graha].is_retrograde else 'direct'}"
                for graha in house.occupants
            )
        else:
            body = "empty"
        parts.append(
            f"House {house.number}, rashi {house.rashi_number} "
            f"({house.rashi_name}): {body}."
        )
    return " ".join(parts)


# --- element emitters ------------------------------------------------------


def _text_element(
    css_class: str,
    graha_key: str | None,
    x: float,
    y: float,
    font: float,
    anchor: str,
    content: str,
    *,
    central_baseline: bool = False,
) -> str:
    parts = [f'<text class="{css_class}"']
    if graha_key is not None:
        parts.append(f' data-graha="{graha_key}"')
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


def _retro_element(
    graha_key: str, x: float, y: float, length: float, stroke: float
) -> str:
    return (
        f'<line class="retro" data-graha="{graha_key}"'
        f' x1="{_number(x)}" y1="{_number(y)}"'
        f' x2="{_number(x + length)}" y2="{_number(y)}"'
        f' stroke="{_STYLE.ink}" stroke-width="{_number(stroke)}"/>'
    )


def _entry_elements(
    entry: _Entry, x: float, baseline: float, font: float
) -> list[str]:
    """The two text elements and the optional underline of one entry."""
    lines = [
        _text_element("abbr", entry.key, x, baseline, font, "start", entry.abbr)
    ]
    if entry.degree_text:
        lines.append(
            _text_element(
                "deg",
                entry.key,
                x + geo.DEG_OFFSET * font,
                baseline,
                font,
                "start",
                entry.degree_text,
            )
        )
    if entry.underline:
        lines.append(
            _retro_element(
                entry.key,
                x,
                baseline + geo.RETRO_DROP * font,
                geo.ABBR_SLOT * font,
                geo.RETRO_STROKE * font,
            )
        )
    return lines


# --- the renderer ----------------------------------------------------------


def render_north_indian_svg(
    chart: D1Chart, options: NorthIndianOptions = NorthIndianOptions()
) -> str:
    """Render one ``D1Chart`` as a North Indian kundli SVG document."""
    if not isinstance(chart, D1Chart):
        raise ValueError(
            f"chart must be a D1Chart; got {type(chart).__name__}."
        )
    if not isinstance(options, NorthIndianOptions):
        raise ValueError(
            f"options must be a NorthIndianOptions; got "
            f"{type(options).__name__}."
        )

    style = _STYLE
    side = float(style.chart_side)
    plans = [_plan_house(chart, region, options) for region in geo.REGIONS]

    caption_lines = _caption_lines(chart) if options.caption else ()
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
    blocks: list[tuple[int, list[str], list[tuple[_Entry, ...]]]] = []
    for plan in plans:
        if not plan.overflows:
            continue
        heading = geo.wrap_text(
            f"House {plan.house} {EM_DASH} complete list:", _LEGEND_BUDGET
        )
        rows = [
            plan.all_entries[start:start + per_line]
            for start in range(0, len(plan.all_entries), per_line)
        ]
        blocks.append((plan.house, heading, rows))

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

    out: list[str] = []
    root = [
        '<svg xmlns="http://www.w3.org/2000/svg" role="img"',
        ' aria-labelledby="title desc"',
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

    out.append(f'<title id="title">{_chars(title)}</title>')
    out.append(
        f'<desc id="desc">{_chars(_description(chart, caption_lines))}</desc>'
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
                    None,
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
    for region, plan in zip(geo.REGIONS, plans):
        out.append(
            f'<g class="house" data-house="{plan.house}"'
            f' data-rashi="{plan.rashi_number}">'
        )
        points = " ".join(
            f"{_number(to_x(px))},{_number(to_y(py))}"
            for px, py in region.polygon
        )
        out.append(
            f'<polygon class="cell" points="{points}" fill="none"'
            f' stroke="{style.ink}"'
            f' stroke-width="{_number(style.stroke * side)}"/>'
        )
        out.append(
            _text_element(
                "numeral",
                None,
                to_x(region.numeral[0]),
                to_y(region.numeral[1]),
                style.numeral_font * side,
                "middle",
                _chars(plan.rashi_number),
                central_baseline=True,
            )
        )

        font = plan.size * side
        row_x = to_x(geo.row_start_x(region.box.x0))
        for index, entry in enumerate(plan.shown):
            baseline = to_y(geo.row_baseline(region.box.y0, index, plan.size))
            out.extend(_entry_elements(entry, row_x, baseline, font))
        if plan.overflows:
            baseline = to_y(
                geo.row_baseline(region.box.y0, len(plan.shown), plan.size)
            )
            out.append(
                _text_element(
                    "overflow",
                    None,
                    row_x,
                    baseline,
                    font,
                    "start",
                    f"+{plan.overflow_count}",
                )
            )
        out.append("</g>")
    out.append("</g>")

    out.append('<g class="legend">')
    line_index = 0
    for line in marker_wrapped:
        out.append(
            _text_element(
                "legend-marker",
                None,
                chart_left,
                geo.band_baseline(
                    legend_top, line_index, style.legend_font, style.legend_pitch
                ),
                style.legend_font,
                "start",
                _chars(line),
            )
        )
        line_index += 1

    legend_font = style.legend_font
    for house_number, heading, rows in blocks:
        out.append(f'<g class="legend-house" data-house="{house_number}">')
        for line in heading:
            out.append(
                _text_element(
                    "legend-heading",
                    None,
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
                    _entry_elements(entry, slot_x, baseline, legend_font)
                )
            line_index += 1
        out.append("</g>")
    out.append("</g>")

    out.append("</svg>")
    return "\n".join(out) + "\n"
