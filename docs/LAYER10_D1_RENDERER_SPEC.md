# Layer 10 — North Indian D1 Kundli SVG Renderer — SPECIFICATION DRAFT v0.3

**Status:** DRAFT v0.3 — design approved for implementation by the owner subject to six
corrections, all applied in this revision (§2 package filename and internal imports; §5/§6 width
budget including the left inset; §7 exact line pitches and legend width budgets; §2 option
validation and width semantics; §10.A structural SVG safety tests; §10.D expanded rendered
inspection). **Implemented** (`src/vedic_chart/render/`, tests `tests/test_render_*.py`) and
**visually validated** — the record is §13 and `docs/render_inspection/INSPECTION.md`; the
supported minimum width was raised from the provisional 450 px to **600 px** by that inspection.
The document stays DRAFT until the owner reviews the implementation and the validation record and
promotes it. Inputs are the frozen calculation contract
(`docs/CALCULATION_SPEC.md`, FROZEN v1.0, commit `2b3a5a9`) and the Layer 9 representation
contract (`docs/LAYER9_D1_REPRESENTATION_SPEC.md` v1.0, commit `5f076fd`). This layer changes
neither.

Owner-fixed behaviour carried into v0.2: North Indian layout; SVG via the Python standard library
with no new runtime dependency; English abbreviations Su Mo Me Ve Ma Ju Sa Ra Ke; retrograde shown
as a short underline beneath the abbreviation only (never the degrees), suppressed for Rahu/Ketu by
default, explained in a legend and stated in accessible text; degrees ON by default as truncated
D°MM′; rashi numerals only; `house.occupants` order preserved; captions off by default, printing
the IANA timezone id verbatim when on; no birth metadata anywhere when captions are off.

Owner decisions U-1…U-6 (v0.1) resolved as: U-1 the overflow legend lists the complete house,
labelled "House N — complete list", and `+n` counts only occupants omitted from the cell; U-2
`As` is the Lagna entry, always first in house 1, with degrees by default, never moved to the
legend; U-3 450 px is a *provisional* minimum total SVG width pending rendered inspection, with
effective sizes calculated in §7 and readability explicitly *not* claimed; U-4 a compact marker
legend is always present; U-5 the numeral anchors are provisional pending rendered inspection;
U-6 `RenderStyle` is internal in v1 and only the minimal `NorthIndianOptions` is public.

```
D1Chart (Layer 9)  ──►  render_north_indian_svg(chart, options)  ──►  str (SVG document)
```

## 1. Scope and non-goals

The renderer draws one D1 chart in the North Indian style as a self-contained SVG string. It
performs no astronomy and no astrology: every house, rashi, occupant, degree and retrograde flag is
read from `D1Chart`; its only arithmetic is coordinate geometry and text-layout bookkeeping.
Non-goals for v1: South/East Indian styles, sign names, Sanskrit labels, degree re-sorting,
PNG/PDF rasterisation, interactivity, embedded fonts, public theming, and any divisional, dasha,
aspect or interpretation content.

## 2. Public API and allowed imports

Package `src/vedic_chart/render/` (Layer 10):

The package consists of exactly three files; the first is the package initialiser and is named
with the usual double underscores, `render/__init__.py`:

```
render/__init__.py                  package docstring; re-exports the two public names
render/north_indian.py              render_north_indian_svg, NorthIndianOptions  (public)
render/north_indian_geometry.py     REGIONS table, sizing/packing/wrapping helpers (internal)
```

```python
@dataclass(frozen=True)
class NorthIndianOptions:
    show_degrees: bool = True            # D°MM′ after every entry, from Layer 9 dms(0)
    mark_node_retrograde: bool = False   # underline Ra/Ke when is_retrograde (always True by data)
    caption: bool = False                # §8; when False no birth metadata is emitted anywhere
    width: int | None = None             # CSS px; None omits width/height (scales to container)

def render_north_indian_svg(chart: D1Chart, options: NorthIndianOptions = NorthIndianOptions()) -> str
```

**Option validation** (in `NorthIndianOptions.__post_init__`, raising `ValueError` with the field
name and the offending value, matching the project's validation style): `show_degrees`,
`mark_node_retrograde` and `caption` must each be exactly `bool` (`type(value) is bool`; `0`,
`1`, `"yes"`, `None` are rejected). `width` must be `None` or an `int` that is not a `bool` and
is ≥ 1; `True`, `0`, negative values, floats (`450.0` included) and strings are rejected.
`render_north_indian_svg` rejects a `chart` that is not a `D1Chart` and an `options` that is not
a `NorthIndianOptions` with `ValueError` before rendering anything.

**Width semantics.** SVG scalability and supported viewing size are two different statements.
(a) *Scalability:* the document always carries a `viewBox` and `preserveAspectRatio` (§7), so it
renders at any size without distortion. When `width` is `None` (the default) no `width`/`height`
attributes are written and the SVG takes the size of its container; when `width` is given it is
written verbatim as the `width` attribute and `height` = ⌊width × H / 1080⌋ is written beside it.
(b) *Supported viewing size:* the renderer is validated for legibility only at total widths ≥
W_min, the supported minimum. W_min was provisionally 450 px; §10.D found floor-size and
side-triangle text marginal at 450 px and **W_min is 600 px** (§13). A `width` below W_min is
accepted and rendered exactly like any other
value — it is not an error, the document is still valid and structurally complete — but it is
outside the supported viewing range and no legibility claim applies to it; the same holds for a
container narrower than W_min when `width` is `None`. The renderer does not warn, clamp or
rescale in that case, because the SVG itself is unchanged; the limitation belongs to viewing, not
to the document.

`RenderStyle` (font family, sizes, strokes, colours; §5) is a private frozen dataclass with fixed
v1 values; it is not a parameter.

Allowed imports in `render/` (AST-enforced by tests): the standard library (`dataclasses`,
`math`, `xml.sax.saxutils`, `itertools`); `vedic_chart.representation.d1` (`D1Chart`, `D1House`,
`D1GrahaPlacement`, `D1Lagna`); `vedic_chart.representation.dms` (`DMS`);
`vedic_chart.vedic.grahas` (`Graha`, for identity and the abbreviation/full-name tables); and
**internal imports between the renderer's own modules** — `north_indian` imports
`north_indian_geometry`, and `__init__` imports from `north_indian` — which are explicitly
allowed (`north_indian_geometry` imports nothing from `vedic_chart` outside `render/`, keeping
it a pure-geometry module).
Forbidden: `swisseph`, `vedic_chart.ephemeris`, `.astronomy`, `.sidereal`, `.time`, `.lagna`,
`.location`, `.inputs`, `.chart` (the renderer never sees a `BirthChart`), `.vedic.divisions`,
any network or filesystem I/O, and any call to `round()` on a degree value. Degree text comes only
from `placement.dms(0)` / `lagna.dms(0)`.

## 3. Geometry (exact, normalized)

Coordinates are in the unit square, origin **top-left**, x rightward, y downward (SVG). Named
points:

```
A=(0,0)   T=(0.5,0)   B=(1,0)          E4=(0.25,0.25)   E1=(0.75,0.25)
L=(0,0.5) O=(0.5,0.5) R=(1,0.5)        E3=(0.25,0.75)   E2=(0.75,0.75)
D=(0,1)   M=(0.5,1)   C=(1,1)
```

Drawn segments: the square A–B–C–D, the diagonals A–C and B–D, and the rhombus T–R–M–L.

**Structural justification (not only sampling).** The drawn segments form a planar straight-line
graph whose only vertices are the thirteen named points: the diagonals meet at O; rhombus edge T–R
(y = x − 0.5) meets diagonal B–D (y = 1 − x) at E1 = (0.75, 0.25), and symmetrically L–T meets A–C
at E4, R–M meets A–C at E2, M–L meets B–D at E3; no other pairs of segments cross. The twelve
regions are exactly the bounded faces of this graph: the diagonals cut the square into four
quadrant triangles (A–B–O, B–C–O, C–D–O, D–A–O, area 0.25 each); inside the top quadrant the two
rhombus sub-segments E4–T and T–E1 (with E4 on edge A–O and E1 on edge B–O) cut it into the
triangle A–T–E4, the triangle T–B–E1 and the quadrilateral T–E1–O–E4, whose areas 0.0625 + 0.0625
+ 0.125 = 0.25 equal the quadrant's; the other three quadrants are the same by the square's
fourfold symmetry. Hence: (i) **total coverage** — the twelve faces partition each quadrant and the
quadrants partition the square, 4 × 0.125 + 8 × 0.0625 = 1.000; (ii) **non-intersecting
interiors** — faces of a planar subdivision have pairwise disjoint interiors by construction, since
edges meet only at the graph's vertices; (iii) **shared boundaries** — every region edge is a
sub-segment of a drawn segment and is shared with exactly one neighbouring region or lies on the
outer square (e.g. edge T–E1 is shared by houses 1 and 12; edge E1–O by houses 1 and 10). Each kite
T–E1–O–E4 is a square of side 0.25·√2 with right angles (its diagonals T–O and E4–E1 are
perpendicular and equal, length 0.5). The grid test in §10.B is a numerical sanity check of this
argument, not its proof.

House assignment (North Indian: house 1 top-centre kite, numbering anticlockwise):

| House | Kind | Polygon (draw order) | Numeral anchor (provisional, U-5) | Label box x | Label box y | Box w × h |
|---|---|---|---|---|---|---|
| 1 | kite | T, E1, O, E4 | (0.50, 0.44) | 0.385 – 0.615 | 0.14 – 0.36 | 0.23 × 0.22 |
| 2 | tri | A, T, E4 | (0.25, 0.20) | 0.145 – 0.355 | 0.02 – 0.12 | 0.21 × 0.10 |
| 3 | tri | A, E4, L | (0.20, 0.25) | 0.02 – 0.165 | 0.19 – 0.31 | 0.145 × 0.12 |
| 4 | kite | L, E4, O, E3 | (0.44, 0.50) | 0.14 – 0.36 | 0.385 – 0.615 | 0.22 × 0.23 |
| 5 | tri | L, E3, D | (0.20, 0.75) | 0.02 – 0.165 | 0.69 – 0.81 | 0.145 × 0.12 |
| 6 | tri | D, M, E3 | (0.25, 0.80) | 0.145 – 0.355 | 0.88 – 0.98 | 0.21 × 0.10 |
| 7 | kite | M, E3, O, E2 | (0.50, 0.56) | 0.385 – 0.615 | 0.64 – 0.86 | 0.23 × 0.22 |
| 8 | tri | M, C, E2 | (0.75, 0.80) | 0.645 – 0.855 | 0.88 – 0.98 | 0.21 × 0.10 |
| 9 | tri | C, E2, R | (0.80, 0.75) | 0.835 – 0.98 | 0.69 – 0.81 | 0.145 × 0.12 |
| 10 | kite | R, E2, O, E1 | (0.56, 0.50) | 0.64 – 0.86 | 0.385 – 0.615 | 0.22 × 0.23 |
| 11 | tri | B, R, E1 | (0.80, 0.25) | 0.835 – 0.98 | 0.19 – 0.31 | 0.145 × 0.12 |
| 12 | tri | T, B, E1 | (0.75, 0.20) | 0.645 – 0.855 | 0.02 – 0.12 | 0.21 × 0.10 |

Label boxes are axis-aligned rectangles inside their polygon with ≥ 0.015 clearance from every
drawn segment (a centred rectangle in a kite with half-extents (a, b) has clearance c from the
45° edges iff a + b ≤ 0.25 − c·√2; with c = 0.015 the bound is 0.2288 and the kites use
0.115/0.11; the triangle boxes were checked corner by corner, minimum clearance 0.0177) and
disjoint from the numeral's glyph box. Numeral anchors lie 0.06 from a kite's inner vertex O or
0.05 from a triangle's apex, inside the polygon and outside the label box. Numerals show
`house.rashi_number` at `numeral_font`, never scaled; house 1's numeral is the Lagna's rashi by
construction.

## 4. Entries, the Lagna entry, and the retrograde marker

An **entry** is one row inside a label box. House 1 always begins with the **Lagna entry** `As`
(`As 9°47′` with degrees) — first, never moved to the legend, never counted as an occupant. Then,
in `house.occupants` order, one entry per graha: the abbreviation and, when `show_degrees`, the
degree text `D°MM′` built as `f"{d.degrees}°{d.minutes:02d}′"` from `dms(0)` (seconds simply not
shown; nothing re-rounded). Abbreviations: SUN Su, MOON Mo, MERCURY Me, VENUS Ve, MARS Ma,
JUPITER Ju, SATURN Sa, RAHU Ra, KETU Ke.

**Entry construction (font-independent confinement of the underline).** Every entry is two
separate SVG text elements laid out left-to-right from the entry's start x₀ at font size f
(§5): `<text class="abbr" x="x₀">` holding the two-letter abbreviation, and, when degrees are on,
`<text class="deg" x="x₀ + 1.90 f">` holding the degree text. The retrograde marker is a
`<line class="retro">` from x₀ to x₀ + 1.45 f at y = baseline + 0.22 f, stroke width 0.06 f, drawn
only when the graha's `is_retrograde` is true and (for Ra/Ke) `mark_node_retrograde` is set. By
construction the underline ends 0.45 f before the degree element begins, so it can never underline
the degrees regardless of font. What is *not* guaranteed: that the underline's length matches the
abbreviation's glyph extent exactly. With the assumed advances (§5) a wide abbreviation such as
`Mo` may extend up to ≈ 0.05 f beyond the line and a narrow one such as `Su` may leave ≈ 0.25 f of
line past its last glyph; rendered inspection (§10.D) confirms the marker reads as "under the
abbreviation" in the target viewers. Vertical clearance: rows are pitched at 1.45 f; the underline's
lower edge (≈ 0.25 f below the baseline) sits ≥ 0.45 f above the next row's cap height, and the
row's bounding box (ascent 0.75 f above the baseline to 0.25 f below) lies inside the label box,
whose ≥ 0.015 clearance keeps every underline off the chart lines.

## 5. Text-width assumptions (stated honestly) and the private style

A fallback font stack cannot fix glyph widths; the renderer measures nothing and guarantees no
label width. It uses **budgets** derived from an assumed advance of 0.68 em per character, chosen
to exceed the average advance of the characters used (digits, `°`, `′`, upper/lower Latin, space)
in DejaVu Sans (≈ 0.63) and Arial (≈ 0.59). Nothing below is a guarantee for an arbitrary system
font; §10.D is where reality is checked.

Private `RenderStyle` values (fractions of the chart side unless noted): `font_family`
`"DejaVu Sans", Arial, Helvetica, sans-serif`; **size ladder** for entries S = (0.032, 0.030,
0.028, 0.026, 0.024, 0.022, 0.021) — the first value is the base, the last the floor; `numeral_font`
0.026; `line_height` 1.45 em; `char_advance` 0.68 em; `left_inset` 0.01 (rows start at the box's
left edge + 0.01); entry width budget **W(f) = 0.01 + 6.12 f** — the left inset plus the
9-character worst case `Me 29°59′` = `As 29°59′` at 0.68 em (the two-element layout of §4 needs
1.90 f + 6 × 0.68 f = 5.98 f, within the 6.12 f text budget); abbreviation slot 1.45 f; gap
0.45 f; `stroke` 0.0025; ink black on white. Caption font 24 and legend font 22 viewBox units
(§7).

## 6. Sizing and crowding — one algorithm

For each house: entries = (`As` if house 1) + occupants in order; n = len(entries); box (w, h)
from §3; capacity(f) = ⌊h / (1.45 f)⌋.

1. **Width gate.** f_w = the largest size in S with W(f) = 0.01 + 6.12 f ≤ w. Kites (w ≥ 0.22)
   and top/bottom triangles (w = 0.21) admit the whole ladder (0.01 + 6.12 × 0.032 = 0.2058 ≤
   0.21); side triangles (w = 0.145) admit only 0.022 and 0.021 (0.01 + 6.12 × 0.022 = 0.1446 ≤
   0.145, a margin of 0.0004; 0.01 + 6.12 × 0.024 = 0.1569 > 0.145). Including the inset changes
   no size selection relative to the uninset budget, but the side-triangle margin is now thin and
   is one of the things §10.D looks at. Because the budget is the fixed worst case, a house's
   size depends only on its geometry and entry count, never on which grahas it holds.
2. **Height fit.** f = the largest size in S with f ≤ f_w and capacity(f) ≥ n. If one exists,
   render all n entries at f. Stop.
3. **Overflow at the floor.** Otherwise f = 0.021 (the floor; never smaller) and the house
   overflows: the cell shows the first k = capacity(0.021) − 1 entries (so `As` is always shown,
   being first, and k ≥ 2 for every box) followed by the `+n` indicator on the last row, where the
   number is the count of **occupants** not shown in the cell (`As` is never counted). The house is
   added to the overflow legend (§7) as "House N — complete list" holding **every** occupant in
   order with abbreviation, degrees (when on) and underline where applicable. Degrees are never
   dropped and no text is ever rendered below the floor.

Rows are left-aligned at the box's left edge + 0.01 and stacked from the box's top edge, first
baseline at top + 0.75 f, pitch 1.45 f.

Capacities (rows) by box height along the ladder S:

| box height | 0.032 | 0.030 | 0.028 | 0.026 | 0.024 | 0.022 | 0.021 |
|---|---|---|---|---|---|---|---|
| 0.22 (houses 1, 7) | 4 | 5 | 5 | 5 | 6 | 6 | 7 |
| 0.23 (houses 4, 10) | 4 | 5 | 5 | 6 | 6 | 7 | 7 |
| 0.12 (houses 3, 5, 9, 11 — width-gated to ≤ 0.022) | – | – | – | – | – | 3 | 3 |
| 0.10 (houses 2, 6, 8, 12) | 2 | 2 | 2 | 2 | 2 | 3 | 3 |

Worked examples with this algorithm (degrees on; re-checked against the inset-inclusive budget —
every selection below is unchanged because the width gate admits the same sizes as before):

- **Nine grahas in house 1** (kite, h 0.22): n = 10 (`As` + 9) > 7 = capacity(0.021) → overflow;
  k = 6: cell shows `As`, Su, Mo, Me, Ve, Ma and `+4` (Ju, Sa, Ra, Ke omitted); legend
  "House 1 — complete list: Su …, Mo …, Me …, Ve …, Ma …, Ju …, Sa …, Ra …, Ke …".
- **Nine grahas in house 2** (top triangle, h 0.10): n = 9 > 3 → overflow; k = 2: Su, Mo, `+7`;
  legend lists all nine.
- **Nine grahas in house 3** (side triangle, w 0.145, h 0.12): f_w = 0.022; n = 9 > 3 → overflow;
  k = 2: Su, Mo, `+7`; legend lists all nine.
- **Reference chart, house 12** (top triangle): n = 2 → f = 0.032 (capacity 2). House 1: n = 2
  (`As`, Su) → 0.032. A side triangle with 2 or 3 occupants renders at 0.022 with no overflow;
  with 4 it overflows (k = 2, `+2`).
- **House 1 with 6 occupants**: n = 7 → f = 0.021 (capacity 7), no overflow.

## 7. Document layout, wrapping, sizing and scaling

All output coordinates are viewBox units; the chart square maps to 1000 × 1000 at x ∈ [40, 1040].
Vertical bands, top to bottom: margin 40; caption band (only if `caption`); the chart square; gap
30; legend band; margin 40. viewBox = `0 0 1080 H` with H = 40 + caption_h + 1000 + 30 +
legend_h + 40; `preserveAspectRatio="xMidYMin meet"`. If `width` is None no `width`/`height`
attributes are written and the SVG scales to its container preserving aspect ratio; if given,
`width` is written as-is and `height` = ⌊width × H / 1080⌋. The chart square is never distorted;
bands never overlap.

**Band constants (exact, used everywhere).** Caption band: font F_c = 24, line pitch P_c = 32,
character budget B_c = 55. Legend band: font F_l = 22, line pitch P_l = 30, character budget
B_l = 60. The pitches are fixed integer constants of `RenderStyle`, not derived from a multiplier
(24 × 1.35 would be 32.4; the values used are 32 and 30, full stop). The character budgets are
B = ⌊1000 / (0.75 × F)⌋ — 0.75 em per character, the 0.68 estimate of §5 with a 10 % margin —
which gives ⌊55.6⌋ = 55 and ⌊60.6⌋ = 60. Band padding is 16 above and 16 below.

**Baselines and band height.** A band with n lines has height h_band = 16 + n × P + 16; its first
baseline is at band_top + 16 + F and line i (0-based) sits at band_top + 16 + F + i × P. This keeps
the last line's descender (0.25 F below its baseline) inside the band by 16 + P − 1.25 F = 18
units (caption) or 18.5 units (legend), and its first line's ascent within the top padding plus
0.28 F. caption_h and legend_h are computed from the wrapped line counts before the viewBox is
emitted, so H is always exact.

**Wrapping — free text (caption lines, marker-legend lines, legend headings).** SVG does not
wrap text, so the renderer breaks lines itself with one deterministic rule: text is wrapped
greedily at whitespace into lines of at most B characters; a single token longer than B
characters (a long place name without spaces) is hard-split at B so that **no text is ever
dropped**. Each wrapped line is one `<text>` element at its own baseline.

**Legend house blocks — slot layout with fixed spacing.** An overflowed house is listed as a
heading line `House N — complete list:` (free text, 24 characters, never wrapped in practice)
followed by one or more *entry lines*. Entry lines are indented by I = 4 × 0.75 × F_l = 66 units
and hold entries in fixed-width slots so that the abbreviation/degree spacing of §4 is reproduced
exactly at the legend font: within a slot starting at x, the abbreviation `<text class="abbr">`
sits at x, the degree text `<text class="deg">` at x + 1.90 F_l = x + 41.8, and the retrograde
underline (when applicable) runs from x to x + 1.45 F_l = x + 31.9 at baseline + 0.22 F_l with
stroke 0.06 F_l. Slot width with degrees on: 1.90 F_l + 6 × 0.75 F_l = 6.40 F_l = 140.8 units;
with degrees off: 2 × 0.75 F_l = 1.50 F_l = 33 units. The inter-slot gap is G = 1.00 F_l = 22
units. Entries per line E = ⌊(1000 − I + G) / (slot + G)⌋ = ⌊956 / 162.8⌋ = **5** with degrees on
and ⌊956 / 55⌋ = 17 (i.e. all nine on one line) with degrees off. A complete list of nine
occupants with degrees therefore takes two entry lines (5 + 4); the nine-graha cases of §6 give
a legend of 2 marker lines + 1 heading + 2 entry lines = 5 lines, legend_h = 32 + 5 × 30 = 182.
Entries are never split across lines and never truncated.

**Marker-legend text (exact strings, each ≤ B_l).** Line 1: `As = Lagna (ascendant), first in
house 1` (40 characters). Line 2, default: `Underline = retrograde; not shown for Ra and Ke`
(47); with `mark_node_retrograde`: `Underline = retrograde; shown for Ra and Ke too` (47).

Residual risk stated: a system font wider than 0.75 em average could still push a full free-text
line, or the fifth slot of an entry line, past the 1000-unit band width; SVG does not clip, so
such text would extend into the 40-unit margin rather than vanish, and §10.D checks for it.

**Effective sizes at the provisional 450 px minimum (U-3).** Scale = 450 / 1080 = 0.4167 px per
viewBox unit; chart side 1000 units → 416.7 px. Entry text: base 0.032 × 1000 = 32 units → 13.3 px;
side-triangle size 0.022 → 9.2 px; floor 0.021 → 8.75 px. Numerals 26 units → 10.8 px. Legend 22
units → 9.2 px; caption 24 units → 10.0 px; underline stroke at the floor 0.06 × 21 = 1.26 units →
0.5 px. These are arithmetic consequences of the layout, not readability claims. §10.D found
the floor and side-triangle sizes marginal at 450 px (the prime mark ′ collapses to a one-pixel
tick and the underline to a 0.5 px grey line), so the supported minimum is **600 px** (§13), at
which the same sizes are: base 17.8 px, side-triangle 12.2 px, floor 11.7 px, numerals 14.4 px,
legend 12.2 px, caption 13.3 px, floor underline stroke 0.7 px.

## 8. Caption (optional, off by default)

When `caption` is true the caption band shows, left-aligned and wrapped per §7:
1. `{birth_date} {birth_time} {timezone_id}` — `birth_date.isoformat()`; `birth_time` as `HH:MM`,
   `HH:MM:SS` if seconds ≠ 0, `HH:MM:SS.ffffff` if microseconds ≠ 0; `meta.location.timezone_id`
   verbatim (e.g. `Asia/Kolkata`), never an abbreviation or offset.
2. `meta.location.canonical_name` verbatim (wrapped, never truncated).
3. `{meta.ayanamsha} · Whole Sign houses · Mean Node` from the descriptor strings.
All dynamic strings are XML-escaped (§9). When `caption` is false the document contains **no**
birth date, time, place, coordinates, timezone id, Julian Day or ayanamsha value anywhere — not in
`<title>`, `<desc>`, comments, ids or attributes — and the `<title>` is the constant
"D1 chart (North Indian)". With a caption the `<title>` becomes "D1 chart (North Indian) —
{canonical_name}".

## 9. Legend, safety and accessibility

**Marker legend (always present, U-4):** the two exact lines of §7 at the top of the legend
band: `As = Lagna (ascendant), first in house 1` and `Underline = retrograde; not shown for Ra
and Ke` (default) or `Underline = retrograde; shown for Ra and Ke too` (when
`mark_node_retrograde`). **Overflow legend:** zero or more house blocks — heading
`House N — complete list:` and slot-laid entry lines as defined in §7 — listing every occupant in
order, each entry built as in §4 (separate abbreviation/degree elements, underline where
applicable) so the legend preserves every occupant's abbreviation, degrees and marker.

**Safety.** All dynamic text passes through `xml.sax.saxutils.escape` (with `"` and `'` also
escaped in attributes). No dynamic string is ever placed in an attribute, an id, a comment or the
prolog: user-derived text (place name, timezone id, date/time, ayanamsha descriptor) appears only
as escaped character data of `<title>`, `<desc>` and caption `<text>` elements. The document
contains no `<script>`, no event-handler (`on*`) attributes, no `href`/`xlink:href`, no
`<image>`, `<use>`, `<foreignObject>`, `<style>`, `<a>`, `<animate*>`/`<set>`, no `<!DOCTYPE>`,
no entity declarations, no external references, no `@import` and no `url(` in any attribute; all
styling is presentation attributes. Escaped text content is *not* subject to these rules: a
place name containing the characters `url(` or `href` or `<script>` is legitimate caption text,
is escaped, and renders as inert characters — the safety tests of §10.A are structural for
exactly this reason.

**Accessibility.** Root `<svg xmlns="http://www.w3.org/2000/svg" role="img"
aria-labelledby="title desc" viewBox=…>`, then `<title id="title">` and `<desc id="desc">`. The
`<desc>` is a complete reading independent of any visual marker: "Lagna in rashi 12 (Meena) at
9°47′. House 1, rashi 12 (Meena): Sun 6°09′, direct. House 2, rashi 1 (Mesha): Ketu 13°47′,
retrograde. House 3, rashi 2 (Vrishabha): empty. … House 12, rashi 11 (Kumbha): Mercury 15°23′,
direct; Saturn 23°03′, direct." Every graha's status is the word `retrograde` or `direct` from
`is_retrograde` — Rahu and Ketu included, since their marker suppression is visual only. Full
names are used in `<desc>`. When a caption is enabled the `<desc>` is prefixed with the three
caption lines; otherwise it contains no birth data.

**Structure for testability.** `<g class="house" data-house="n" data-rashi="r">` holds the
polygon, `<text class="numeral">`, entry elements `<text class="abbr" data-graha="sun">` /
`<text class="deg" data-graha="sun">` (Lagna entry `data-graha="lagna"`), `<line class="retro"
data-graha=…>` and `<text class="overflow">` (`+n`). `<g class="legend">` holds `<text
class="legend-marker">` lines and, per overflowed house, `<g class="legend-house" data-house="n">`
with `abbr`/`deg`/`retro` children carrying `data-graha`. `<g class="caption">` exists only when
enabled. Accessibility text lives only in `<title>`/`<desc>`. Semantic tests treat a graha that
appears both in its house cell and in that house's legend block as **expected**, not as a duplicate
placement; a graha appearing in two different house groups, or twice within one cell, is an error.

## 10. Acceptance tests (to be written with the implementation)

**A. Semantic correctness** (parse with `xml.etree`; assert against the `D1Chart`, never against
independently computed astrology): exactly twelve `g.house` groups numbered 1–12 with
`data-rashi` and numeral text equal to `house.rashi_number`; per house, the cell's `abbr` elements
(excluding `lagna`) are a prefix of `house.occupants` in order, and equal it when no `overflow`
element is present; when an `overflow` element is present, its number equals
len(occupants) − (cell entries excluding `lagna`), and the house's `legend-house` block lists
`house.occupants` completely and in order; house 1 contains exactly one `data-graha="lagna"`
entry, first, and no other house or legend block does; each visible `deg` text equals the `D°MM′`
formatting of `placement.dms(0)` (and of `lagna.dms(0)`); a `retro` line exists for a graha iff
`is_retrograde` and (not a node or `mark_node_retrograde`), in both cell and legend; the `<desc>`
names every house, every graha with the correct `retrograde`/`direct` word, and the Lagna; the
two marker-legend lines are present in every render; `caption` false → no date, place name,
timezone id, JD or ayanamsha value anywhere; `caption` true → the three lines present, escaped,
and wrapped within B. Cases: the frozen Jalandhar reference (empty houses 3/4/6/7/10; house 12 =
Mercury, Saturn; Mars underlined in house 5); Bharatpur 2003 (Saturn underlined; house 3 =
Mercury, Venus); all twelve Lagna rashis (synthetic charts: numeral rotation in all twelve
houses); boundary degrees (synthetic occupants at 29.999999° → `29°59′`, 0.000001° → `0°00′`,
12.5° → `12°30′`); nodes with and without `mark_node_retrograde`; nine grahas in house 1, in house
2 and in house 3 with degrees on (expected cell contents exactly as in §6); a location name of
120 characters without spaces (hard-split wrapping, nothing lost); a name with `&`, `<`, `"`
(escaping).

**A2. Option validation:** each of `show_degrees`, `mark_node_retrograde`, `caption` rejects
`0`, `1`, `None`, `"true"` with `ValueError`; `width` rejects `True`, `False`, `0`, `-1`,
`450.0`, `"450"` with `ValueError` and accepts `None`, `1`, `449` (below W_min, still rendered)
and `450`; a `width` of `n` produces `width="n"` and `height="⌊n × H / 1080⌋"`, and `None`
produces neither attribute while the `viewBox` is present in both cases; `render_north_indian_svg`
rejects a non-`D1Chart` chart and a non-`NorthIndianOptions` options with `ValueError`.

**A3. SVG safety — structural, never token-based.** Parse the output with `xml.etree` (which
does not resolve external entities) and walk every element and attribute. Assert: no element whose
local name is in {`script`, `image`, `use`, `foreignObject`, `style`, `a`, `iframe`, `embed`,
`object`, `animate`, `animateMotion`, `animateTransform`, `set`, `handler`, `listener`}; no
attribute whose local name starts with `on`; no attribute whose local name is `href` (in any
namespace, so `xlink:href` is covered) or `style`; no attribute value that, after stripping
whitespace, starts with `url(`, `javascript:` or `data:`; every `id` value belongs to the fixed
set {`title`, `desc`}; and the raw document prolog contains no `<!DOCTYPE`, `<!ENTITY` or
processing instruction other than the optional XML declaration (this one check is on the raw
prolog because DTDs are not elements). These checks apply to **element and attribute structure
only**: the same test renders a caption chart whose `canonical_name` is
`url(x) href <script>alert(1)</script> onload=1 &` and asserts that the render succeeds, the
structural assertions pass, the parsed caption text round-trips to the original string, and the
raw output contains `&lt;script&gt;` — i.e. harmless escaped text containing such substrings is
never rejected.

**B. Geometry and layout** (pure functions in `north_indian_geometry.py`): region areas equal
0.125 / 0.0625 by kind and sum to 1.000; the edge-sharing table of §3 holds (each region edge
equals a sub-segment of a drawn segment and is matched by exactly one neighbour or the outer
square); on a 200 × 200 interior grid every point farther than 1e-6 from any drawn segment lies in
exactly one region and every point on a segment lies on the boundary of at least one
(edge-inclusive test) — the numerical companion to the structural argument; every label-box
corner is inside its polygon with ≥ 0.015 clearance; every numeral anchor is inside its polygon
and outside its box; for every case in A the layout keeps every row's bounding box and every
underline inside the label box, places `+n` on the last row when present, never selects a size
outside S, never omits degrees, and reproduces the capacity table of §6.

**C. Deterministic serialization:** the same `D1Chart` and options render byte-identically;
golden files for the Jalandhar and Bharatpur charts in four option combinations (caption on/off ×
degrees on/off) are compared exactly; numbers are written with fixed precision (2 decimals in
viewBox units); attribute order is fixed; no timestamps, random ids or environment-dependent
content.

**D. Rendered visual inspection** (manual; results recorded in `docs/` before the layer is
declared complete; not part of `pytest`). The rasteriser (a browser or an SVG tool) is
validation tooling only and is not a project dependency. The inspection set is wider than the
golden files and every case is rendered **with degrees enabled** and rasterised at **both 450 px
and 1000 px** total width:

1. the Jalandhar reference chart (caption off, and caption on);
2. the Bharatpur 2003 chart (caption on — a caption with a real place name);
3. nine grahas in house 1 (kite; floor size 0.021 in the cell; `+4`; two-line legend block);
4. nine grahas in house 2 (top triangle; `+7`);
5. nine grahas in house 3 (side triangle at 0.022 with the 0.0004 width margin; `+7`);
6. a chart in which every graha is retrograde (all seven planet underlines, nodes suppressed) and
   the same chart with `mark_node_retrograde`, so the underline is judged at base size, at the
   side-triangle size and at the floor;
7. a long caption: a `canonical_name` of ≥ 120 characters with and without spaces (greedy wrap
   and hard split) plus a long timezone id such as `America/Argentina/ComodRivadavia`;
8. wrapped overflow legends: at least one case with two overflowed houses so the legend holds two
   headings, each with its own entry lines (with nine grahas and five entries per line, two
   overflowed houses yield at most two entry lines in total; the four-line figure in an earlier
   draft was an arithmetic slip), and the nine-in-one-house cases above for the two-line block.

The inspector looks at the actual images (not the SVG source) and records, per case and per size:
no text touching or crossing a chart line; the underline reading as "under the abbreviation"
and never under the degrees; side-triangle text and floor-size text legible; `+n` legible; legend
headings and slot entries legible and within the band; wrapped caption lines within the band and
nothing hard-split mid-glyph; numeral placement acceptable (U-5); and, for case 5, the
right-hand end of `Me 29°59′`-class entries clear of the triangle's slanted edge. **If any
legibility item fails at 450 px, W_min is raised** (to the next value at which the failing item
passes, tried at 600 px, then 750 px) and the whole set is inspected again at the new minimum;
only after a full pass at some width is that width recorded as the supported minimum. Everything
glyph-width-dependent — label fit, underline extent, wrapping tightness — is verified here and
nowhere else, and a passing geometry test (§10.B) never counts as a visual pass.

## 11. Boundaries preserved

The renderer reads `D1Chart` and nothing upstream; it recalculates no longitude, house, rashi,
nakshatra, pada, speed or retrograde flag; it formats degrees only through Layer 9's truncating
`dms()`. Semantic data (`D1Chart`), geometry (`REGIONS` and the fitting/wrapping rules) and style
(`RenderStyle`, private) are separate objects composed by `render_north_indian_svg`.

## 12. Remaining uncertainties

After §13 the open items are: (a) glyph widths were verified in one font only (DejaVu Sans in
headless Chromium); a viewer that falls back to a wider font could tighten the side-triangle fit
(inset-inclusive margin 0.0004) and the fifth legend slot, and has not been inspected; (b) the
retrograde underline at 0.06 f is thin — 0.7 px at 600 px — and reads as a light grey line;
raising it (e.g. to 0.08 f) would be a style change needing owner approval; (c) numeral anchors
(U-5) were judged acceptable but remain an owner-taste item; (d) `wrap_text` normalises runs of
whitespace inside a place name to single spaces when wrapping (`str.split`), so "verbatim" in §8
means every non-whitespace character verbatim. None of these affects semantics, determinism or
the calculation contracts.

## 13. Validation record (implementation and §10.D inspection)

**Implementation notes recorded as spec clarifications** (behaviour the implementation fixed
where the draft was silent): the `<desc>` always includes degrees, even with `show_degrees`
False, because it is the complete reading and degrees are chart content, not birth metadata;
with `caption` on, the `<desc>` is prefixed by the three logical caption lines each followed by
". "; the document contains a `<rect class="paper">` white background and each house polygon
carries the stroke (the union of the twelve polygon outlines is exactly the drawn figure of §3 —
no separate grid elements); `viewBox` height and the `width`/`height` attributes are integers,
every other number has two decimals; no XML declaration is written; Bharatpur 2003 is built
from an explicit `ResolvedLocation` (27.21, 77.29, `Asia/Kolkata`) because the test fixture
database resolves "Bharatpur" to a different settlement.

**Automated results** (recorded 2026-09-06): render tests 553 passed (semantic/validation/
safety 312, geometry/layout 130, golden/determinism 111); full project suite 1025 passed, 0
failed, 0 skipped; `git diff` against the tracked tree empty — no frozen calculation or Layer 9
file changed.

**Rendered inspection** (headless Chromium 1194 via Playwright in a Linux container, DejaVu Sans,
device scale 1; the tool is validation tooling only). Eleven cases of §10.D rasterised at 450,
600 and 1000 px; images and per-case findings in `docs/render_inspection/`. Findings: at 1000 px
and 600 px every item passes for every case — no text touches a chart line; underlines sit under
the abbreviation only and end before the degrees; side-triangle and floor-size text legible
(`°` and `′` distinct at 600 px); `+n`, legend headings and slot entries legible and within the
band; wrapped captions within the band with no mid-glyph split; numerals acceptable; the
worst-case side-triangle entry (`Mo 29°59′` × 2 rows + `+7`, tested by substituting the widest
glyphs into the nine-in-house-3 render) clears the slanted edge with visible margin. At 450 px
the base-size entries, numerals and legend pass, but the floor-size rows (8.75 px) and
side-triangle rows (9.2 px) are marginal — characters resolvable, `′` reduced to a one-pixel
tick, underline 0.5 px — which fails the "floor-size text legible" item. Per the escalation rule
the set was re-inspected at 600 px and passed in full. **Supported minimum width: 600 px.**
The provisional 450 px is withdrawn.
