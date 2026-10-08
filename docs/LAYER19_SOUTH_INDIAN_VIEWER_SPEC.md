# Layer 19 — South Indian D1 chart style in the viewer

**Status:** SPECIFICATION v1.0 (promoted 2026-10-08 on the owner's instruction after the
independent native review; drafts v0.1 2026-09-27 and v0.2 2026-10-07, the owner's four
implementation corrections of 2026-10-07, and the closing revision of 2026-10-08 — §12). The
implementation record is §13; its validation limitations (§13.6) and the qualified pixel
results (§13.4, §13.7) are part of this specification and are not superseded by the promotion.
Promotion changed documentation only: no executable code, test, golden or fixture changed
between the closing revision and v1.0.
Baseline: commit `c67f46c` (`master`, "Add Layer 18: daily Panchanga with canonical sunrise
boundaries"), clean tree and empty index, 144 tracked files; the only untracked file is this
document. This is a **rendering and viewer** milestone. Nothing in it changes the FROZEN v1.0
calculation specification, Layer 9's `D1Chart`, the Layer 10 North Indian renderer and its
geometry (byte-unchanged, goldens byte-identical), the Layer 11 pipeline entry points or their
signatures, the CLI, the daśā arithmetic, the `planetary_positions` data, the dependencies,
or Panchanga Layers 16–18. Deployment files are outside this milestone.

Decided at the v0.1 review: **D1** sign labels are Layer 9's `rashi_name`; **D2** the Lagna
cell's boundary is drawn at twice the normal stroke width and `As` is its first entry;
**D3** the headings are "D1 chart — North Indian" and "D1 chart — South Indian". The v0.1
review's seven findings and their resolutions are in §12.

## 1. Scope

Add a **South Indian** D1 chart beside the existing North Indian one:

* a new pure renderer, `render_south_indian_svg(chart, options)`, consuming the same
  `D1Chart` (§3, §4);
* one additive response field, `south_indian_svg`, rendered from `result.d1` of the single
  existing pipeline call (§5);
* a "Chart style" display control in the viewer — North Indian (default), South Indian, Both
  — that switches between SVGs the page already holds (§6).

Excluded: divisional charts, Panchanga UI, interpretation, prediction, exports, deployment
changes, any change to the request payload, any change to `svg`'s meaning.

## 2. What is fixed by the layers below, and what this layer reads

* **`D1Chart`** (`vedic_chart.representation.d1`, Layer 9 v1.0): `lagna` (`D1Lagna`:
  `rashi_index`, `rashi_number`, `rashi_name`, `house == 1`, `dms(0)`), `houses` (twelve
  `D1House`: `number`, `rashi_index`, `rashi_number`, `rashi_name`, `occupants` in the
  canonical graha order), `grahas` (`D1GrahaPlacement`: `rashi_index`, `house`,
  `is_retrograde`, `dms(0)`), `meta` (`D1Meta`: request, location, ayanamsha/house-system/node
  descriptors), `house(n)`, `house_of(graha)`. Layer 19 reads these and computes nothing
  astrological or astronomical: a planet's cell is its `rashi_index`, a cell's house label is
  the `number` of the `D1House` whose `rashi_index` is that sign, the Lagna's cell is
  `lagna.rashi_index`. No house formula is introduced; a test asserts every cell's house label
  equals the house record's number for all twelve Lagna signs.
* **Layer 10 conventions carried over unchanged** (re-declared in the new module, never
  imported from the frozen one, with equality pinned by tests — §4.4): the abbreviations
  `Su Mo Me Ve Ma Ju Sa Ra Ke` and `As`; the full names used in the accessible description;
  occupant order = `D1House.occupants` order; degree text `D°MM′` from Layer 9's truncating
  `dms(0)` (seconds never shown, `round()` never called); retrograde shown as an underline,
  suppressed for Rahu and Ketu unless `mark_node_retrograde`; the option concepts
  `show_degrees`, `mark_node_retrograde`, `caption`, `width`, `id_prefix` with the same
  validation; the caption content (three lines: date, time and zone; canonical place name;
  the convention line) and the privacy rule that with `caption=False` no birth detail is
  assembled at all; the `RenderStyle` numbers (canvas 1080 wide, chart side 1000, margin 40,
  chart gap 30, caption font 24 / pitch 32, legend font 22 / pitch 30, font family, stroke
  0.0025 of the side, black ink on white paper); two-decimal coordinates, fixed attribute
  order, no generated identifiers, no timestamps.
* **Pipeline** (`vedic_chart.app.pipeline`): the viewer server calls
  `render_chart_and_dasha_at(request, location, config, options, year)` once under
  `ENGINE_LOCK` and receives `LocatedChartAndDashaResult(request, location, chart, d1, svg,
  timeline)`; `svg` is the North Indian document rendered with `transport.RENDERER_OPTIONS`
  (`id_prefix="d1"`). The Vimshottari timeline and the `365.256363`-day convention, Lahiri,
  Whole Sign and Mean Node all live in that one call and are untouched. Layer 19 renders its
  document from `result.d1` **after** the lock, in the server (§5.2).
* **Transport** (`vedic_chart.viewer.transport`, schema `vedic_chart.viewer/2`): the response
  keys in order are `schema, request, engine, location, effective, assumptions, birth, svg,
  timeline, birth_chain, rows, planetary_positions`; `planetary_positions` was added
  additively without a schema bump (`docs/API_PLANETARY_POSITIONS.md`) and is the precedent
  Layer 19 follows.
* **Viewer** (`vedic_chart.viewer.static`): `insertSvg` parses the SVG with `DOMParser`,
  refuses `<script>`/`<foreignObject>`/`on*` attributes, adopts the root into `#chart` with
  inline `min-width: 600px; max-width: 1080px` (600 px is the supported minimum chart width,
  Layer 14); `.v-chart-wrapper` (`padding: 4px; border: 1px`) scrolls horizontally and
  `#chart-scroll-hint` appears when `scrollWidth > clientWidth`; the page is `body.v-page`
  (`padding: 0 16px`) → `main.v-main` (`max-width: 1120px; margin: 0 auto`) →
  `section.v-results#results` (no padding or border) → `.v-results-body` → the cloned
  `.v-results-inner`; stale-input state is `refreshStale()` comparing the four submitted
  birth fields; the results subtree is cloned from `#results-template` on every applied
  document; the last applied document is `shown`.

## 3. South Indian geometry (`vedic_chart.render.south_indian_geometry`)

### 3.1 The grid and its canonical strokes

The chart is a square of side 1 (chart units; multiplied by `chart_side = 1000` at
rendering) divided into a 4 × 4 grid of cells of side 0.25. The twelve perimeter cells are
the sign cells; the four inner cells form one merged **centre** square of side 0.5 with no
planetary content. Sign positions are **fixed** and never rotate with the ascendant:

```
row 0:  Meena (12)   Mesha (1)      Vrishabha (2)   Mithuna (3)
row 1:  Kumbha (11)  [           centre           ]  Karka (4)
row 2:  Makara (10)  [           centre           ]  Simha (5)
row 3:  Dhanu (9)    Vrishchika (8) Tula (7)        Kanya (6)
```

`CELL_BY_RASHI_INDEX: tuple[tuple[int, int], ...]` maps `rashi_index` 0…11 (Mesha…Meena) to
`(row, column)`: `0→(0,1) 1→(0,2) 2→(0,3) 3→(1,3) 4→(2,3) 5→(3,3) 6→(3,2) 7→(3,1) 8→(3,0)
9→(2,0) 10→(1,0) 11→(0,0)` — clockwise from Mesha at the top, second from the left, the
standard South Indian arrangement. A test asserts the map is a bijection onto the twelve
perimeter cells and that the four centre cells are never assigned.

**Strokes are one canonical set of unit edges, each drawn once.** `GRID_EDGES` is the tuple
of the **36** unit-cell edges that bound the twelve ring cells — 16 on the outer perimeter, 8
on the centre square's boundary, and 12 shared edges between neighbouring ring cells (the ring
is a cycle of twelve cells, so it has twelve adjacencies; v0.2 wrote 8 and 32 and was
corrected by the owner) — each as a `(start, end)` pair of grid points with `start < end`
lexicographically, in a fixed order (outer perimeter clockwise from the top-left, then the
centre boundary, then the shared edges clockwise from Meena|Mesha). The set is **derived**
from the twelve cell boundaries: the union of the four edges of each of the twelve cells,
each distinct edge kept once; a test re-derives it that way and asserts equality, that no two
edges overlap or coincide, that no edge lies inside the centre, and that the count is 36 —
the count is never adjusted to fit. Each edge is one `<line class="cell-edge">`; the **four edges of the Lagna
cell** are emitted as `<line class="cell-edge lagna">` with `stroke-width` twice the normal
stroke (D2) — the same canonical edges, drawn once, at the doubled width; nothing redraws
them. Every sign group keeps a `<rect class="cell" fill="none" stroke="none">` for structure
and data attributes; it draws nothing. Normal stroke width `0.0025` of the side, as Layer 10; every `cell-edge` line carries
`stroke-linecap="square"` so that the four doubled Lagna edges meet at their corners without
notches (an implementation addition recorded in §13).

### 3.2 Anatomy of a sign cell

Each sign cell (side 0.25, inset by a padding of `0.010`) holds, top to bottom:

1. a **label row** of height `LABEL_ROW = 0.032`: the sign label at the left, the house
   label at the right, both in the label font `LABEL_FONT = 0.020` of the side. The sign
   label is the Layer 9 `rashi_name` (`Mesha` … `Meena`; D1). The house label is `H`
   followed by the house number (`H1`…`H12`), never a bare numeral, so a sign number and a
   house number can never be confused; the cell's `rashi_number` appears only in the
   `data-rashi` attribute, not as visible text. The longest sign label, `Vrishchika`, is
   10 characters ≈ `0.68 × 10 × 0.020 = 0.136` of the side wide and `H12` ≈ `0.041`; their
   sum is below the inner width `0.230`, so the two labels never meet (asserted by the
   browser measurement of §9.3 for all twelve cells).
2. the **entry rows**: the occupants of the sign, one per row, each `abbr` then (when
   `show_degrees`) the degree text at a fixed offset, exactly as a Layer 10 inline cell:
   left inset `0.01`, abbreviation slot `1.45 f`, gap `0.45 f`, line pitch `1.45 f`, ascent
   `0.75 f`, retrograde underline `0.08 f` thick dropped `0.22 f` below the baseline. In the
   Lagna's cell the first row is `As` with the Lagna's degree text, before the occupants (D2).

The entry area is the cell minus padding and label row: width `0.230`, height
`0.25 − 0.020 − 0.032 = 0.198`.

### 3.3 Sizing, crowding and overflow (deterministic)

The entry font `f` is chosen from the ladder `SIZE_LADDER = (0.032, 0.030, 0.028, 0.026,
0.024, 0.022, 0.021)` — the same numbers as Layer 10, declared here independently — by the
same rule: the largest size whose width budget `0.01 + 6.12 f` fits the entry width and whose
row capacity `floor(0.198 / (1.45 f))` holds every entry; if none does, the floor size with
one row surrendered to an overflow indicator. Capacities: 4 rows at 0.032…0.028, 5 at 0.026
and 0.024, 6 at 0.022 and 0.021. Consequences, all deterministic and depending only on the
entry count and `show_degrees`:

* up to 6 entries (the `As` row included) always fit in one column at ≥ 0.021;
* 7 or more entries — at most 10 are possible (`As` + nine grahas) — show the first 5 rows at
  the floor size and a sixth row `+n`, and the sign's **complete occupant list** is printed in
  the **legend band** below the chart under the heading `<rashi_name> (H<house>) — complete
  list:`, exactly as Layer 10 lists an overflowing house;
* no two text elements overlap (rows are on a fixed pitch inside a fixed box; a test
  measures every text's box); the ladder never yields more than one column.

**Occurrence rules (the intentional repetition, stated and tested):**

* each planet belongs to exactly one sign — the cell of its `rashi_index`;
* each planet appears **at most once among cell entries** (once when its sign does not
  overflow or it is among the rows shown; zero times when it is omitted by the overflow rule);
* each planet of an overflowing sign appears **exactly once in that sign's complete legend
  list**, in `D1House.occupants` order, whether or not it was shown in the cell; planets of
  non-overflowing signs appear in no legend list;
* therefore every planet is represented in the document — in its cell, or in its cell and the
  legend, or in the legend alone — and never under another sign;
* `As` appears exactly once, in the Lagna cell, and is never listed in a complete-list
  legend; when the Lagna cell overflows, `As` is the first shown row and the omitted entries
  are occupants;
* `+n` counts exactly the occupants omitted from the cell (`len(occupants) − occupants shown`).

**Typography, actual rendered sizes.** The floor applies to **entry text**: `0.021 × 1000 =
21` viewBox units, which renders at `21 × 600/1080 ≈ 11.67 px` at the supported minimum
chart width of 600 px and at 21 px at the 1080 px maximum. The sign and house labels are
fixed at `LABEL_FONT = 20` units (`≈ 11.11 px` at 600 px, 20 px at 1080 px); the centre
label at 32 units (`≈ 17.8 px` / 32 px); caption 24 and legend 22 units (`≈ 13.3` / `12.2 px`
at 600 px). These are the smallest text in the document and are measured in the browser
acceptance (§9.3); no "no text smaller than the floor" claim is made for labels.

Without `show_degrees` the width budget shrinks to the abbreviation slot and the rule is
unchanged.

### 3.4 The Lagna cell

The cell of `lagna.rashi_index` carries `data-lagna="true"`; its four boundary edges are the
`cell-edge lagna` lines of §3.1 at twice the normal stroke width; its `As` row is its first
entry. The accessible description names the Lagna's sign, house 1 and degree text. Nothing
else marks the ascendant; sign positions do not move.

### 3.5 The centre

The merged centre square holds one text element, `D1 / Rashi`, at font `0.032` of the side,
centred, class `centre-label`, and nothing else. With `caption=True` the caption band lies
**above** the chart (as Layer 10), never in the centre.

### 3.6 Bands and document height

`document_height = margin + caption_height + chart_side + chart_gap + legend_height + margin`
with the Layer 10 band rules (caption band: wrapped caption lines at pitch 32 when `caption`;
legend band: the two marker lines — `As = Lagna (ascendant), first in its cell; thicker border`
(57 characters, inside the 60-character legend budget, so it never wraps) and the retrograde line, `Underline = retrograde; not shown for Ra and Ke` or `…;
shown for Ra and Ke too` — then one block per overflowing sign). The `viewBox` is
`0 0 1080 H`; with `width` set, `width="<w>" height="floor(w·H/1080)"` are added as Layer 10
does.

### 3.7 Identifiers, classes and data attributes

Root: `<svg xmlns=… role="img" aria-labelledby="<prefix>-title" aria-describedby="<prefix>-desc"
viewBox="0 0 1080 H" preserveAspectRatio="xMidYMin meet">`; `<title id="<prefix>-title">`,
`<desc id="<prefix>-desc">`; these two are the **only** ids in the document. Groups:
`g.caption` (when captioned), `g.chart` containing `g.grid` (the 36 `line.cell-edge`, the
Lagna's four with class `cell-edge lagna`; 36 lines in all), `g.centre` with `text.centre-label`, and twelve
`g.sign` each with `data-rashi="<1..12>"`, `data-house="<1..12>"`, `data-lagna="true|false"`,
`data-layout="inline"`, containing `rect.cell` (no stroke, no fill), `text.sign-label`,
`text.house-label`, then **one logical entry group per displayed row**: `g.entry` with
`data-graha="<key>"` (`lagna` for `As`) containing `text.abbr`, `text.degrees` (only when
`show_degrees`; at the fixed offset of §3.2) and `line.retro` (only when underlined), and
`text.overflow` for the `+n` row; `g.legend` with `text.legend-marker` and one
`g.legend-sign[data-rashi][data-house]` per overflowing sign containing `text.legend-heading`
and one `g.legend-entry[data-graha]` per occupant with the same inner structure as
`g.entry`. Occurrence checks count **groups** (`g.entry`, `g.legend-entry`), never their
inner text or underline elements. Class names are the Layer 10 vocabulary where the concept is the
same (`paper`, `cell`, `entry`, `retro`, `overflow`, `legend`, `legend-marker`) and new names
only for new concepts (`grid`, `cell-edge`, `sign`, `sign-label`, `house-label`, `centre`,
`centre-label`, `abbr`, `degrees`, `legend-sign`, `legend-heading`, `legend-entry`).

Title: `D1 chart (South Indian)`, with ` — <canonical place name>` appended only when
`caption=True`. Description: the caption lines (captioned only), then `Lagna in rashi <n>
(<name>), house 1, at <degrees>.`, then one sentence per non-empty sign in fixed-map order:
`<rashi_name> (house <h>): <Full name> <degrees>, <retrograde|direct>; …` — the whole
description is derived from the `D1Chart` and never from the request when `caption=False`.

## 4. Renderer API (`vedic_chart.render.south_indian`)

### 4.1 Public surface

```python
@dataclass(frozen=True)
class SouthIndianOptions:
    show_degrees: bool = True
    mark_node_retrograde: bool = False
    caption: bool = False
    width: int | None = None
    id_prefix: str = "d1-south"
    # __post_init__: exactly the Layer 10 validation — bools must be exactly bool,
    # width None or int >= 1 (bool rejected), id_prefix matches [A-Za-z][A-Za-z0-9_-]{0,31}.

def render_south_indian_svg(
    chart: D1Chart, options: SouthIndianOptions = SouthIndianOptions()
) -> str
```

`render_south_indian_svg` raises `ValueError` for a non-`D1Chart` chart and for a non-
`SouthIndianOptions` options object. A `meta.house_system`/`meta.node` outside the supported
labels (`whole_sign`, `mean`) raises `ValueError` **only when `caption=True`**, because the
labels are read solely to build the caption; the rejection then happens before a character
of output exists. With `caption=False` the labels are not read and the document is rendered
regardless (and is byte-equal to the document for the same chart with supported labels).
This is exactly Layer 10's behaviour, and the two cases are tested (§8.1).
The default `id_prefix` differs from Layer 10's (`d1` vs `d1-south`) so that the two
documents coexist on one page without duplicate ids (§5.4); the viewer passes the prefix
explicitly anyway.

`vedic_chart.render.__init__` gains `from .south_indian import SouthIndianOptions,
render_south_indian_svg` and `__all__ = ["NorthIndianOptions", "SouthIndianOptions",
"render_north_indian_svg", "render_south_indian_svg"]` (sorted); the docstring's "only two
names are public" sentence is updated. `north_indian.py` and `north_indian_geometry.py` are
not edited.

### 4.2 Modules and imports

* `south_indian_geometry.py`: pure geometry and layout arithmetic; imports `math` and
  `dataclasses` only, nothing from the project (mirrors the Layer 10 rule
  `test_the_geometry_module_imports_nothing_from_the_project`, extended to it).
* `south_indian.py`: imports `math`, `re`, `dataclasses`, `xml.sax.saxutils.escape`,
  `vedic_chart.representation.d1.D1Chart`, `vedic_chart.vedic.grahas.Graha`, and relatively
  `south_indian_geometry`. It does **not** import `north_indian` or `north_indian_geometry`
  (public or private names): the shared conventions are re-declared (§2) and pinned equal by
  tests, so the frozen renderer is neither imported nor refactored.
* Forbidden exactly as Layer 10: `swisseph`, ephemeris/astronomy/sidereal/time/lagna/
  location/inputs/chart/divisions modules, network, `os`, `pathlib`, `io`, `random`,
  `datetime`. No clock, no environment value, no external font, script or image; the font
  family string is the Layer 10 generic stack.

### 4.3 Purity, determinism, escaping, privacy

Two renders of one chart with equal options are byte-identical (test: repeated renders, and
renders from two independently built but equal `D1Chart`s). Every dynamic string passes
through `escape` (character data) or attribute escaping (`"` and `'`); a synthetic
`D1Chart` whose place name contains `<`, `&`, `"` and a non-ASCII letter renders to
well-formed XML with the characters preserved. With `caption=False` the birth date, time,
zone, place name, Julian Day and ayanamsha value are **not assembled** (no variable holds
them), so they appear in no title, description, attribute or comment — asserted by scanning
the whole document for each of the request's strings and the `str()` of the numbers.

### 4.4 Convention-equality tests (instead of shared code)

`tests/test_render_south_indian.py` asserts, importing both modules: `south.ABBREVIATIONS ==
north.ABBREVIATIONS`, `south.FULL_NAMES == north.FULL_NAMES`, `south.NODES == north.NODES`,
`south.LAGNA_ABBR == north.LAGNA_ABBR`, `south.ID_PREFIX_PATTERN.pattern ==
north.ID_PREFIX_PATTERN.pattern`, `south.COMPACT_AYANAMSHA_LABELS`, `HOUSE_SYSTEM_LABELS`,
`NODE_LABELS` equal, `south_geometry.SIZE_LADDER == north_geometry.SIZE_LADDER` and the
five typography constants equal, and the `SouthIndianStyle` numbers equal to the
`RenderStyle` numbers they mirror. For both reference charts and all four option
combinations, the caption text nodes of the two renderers are equal and every entry's
`(data-graha, abbreviation, degree text, underlined)` set — read from Layer 19's `g.entry`
groups and from Layer 10's `text` entries — is equal between the two documents. A future divergence therefore fails loudly instead of drifting.

## 5. Transport and server

### 5.1 Response extension

`POST /api/chart` keeps its request payload, schema string `vedic_chart.viewer/2`, every
existing key in its existing order and meaning, and its error semantics. One key is appended
after `planetary_positions`:

```
"south_indian_svg": "<svg …>…</svg>"     # str, the South Indian document
```

`svg` remains the North Indian document, always, whatever the page's style selection; the
selection is a display preference that never reaches the request or the response.
`transport.serialize(result, parsed, *, effective, rows=None, south_indian_svg=None)` gains
the keyword parameter; when it is `None` (the default) the key is **absent** and the document
is byte-identical to today's — which is what the existing transport fixture, which calls
`serialize` without the keyword, continues to exercise; the server always passes a string.
`transport.SOUTH_INDIAN_RENDERER_OPTIONS = SouthIndianOptions(show_degrees=True,
mark_node_retrograde=False, caption=False, width=None, id_prefix="d1-south")` sits beside
`RENDERER_OPTIONS`; nothing in a request can vary either.

### 5.2 Where and when the document is rendered

In `server._api_chart`, immediately after the `with ENGINE_LOCK:` block that calls
`render_chart_and_dasha_at` and `dasha_rows`, and inside the same `try` that routes failures
to `_fail`: `south = render_south_indian_svg(result.d1, transport.SOUTH_INDIAN_RENDERER_OPTIONS)`.
Rendering is pure and reads only `result.d1`, so the ephemeris lock is not extended (the
boundary test that pins the calls inside the lock to exactly `{"render_chart_and_dasha_at",
"dasha_rows"}` stays as it is). The pipeline is called once per submission, as before; no
second `BirthChart`, resolution or timeline.

### 5.3 Failure handling

A `ValueError` or any other exception from `render_south_indian_svg` reaches the existing
`except Exception` arm of `_api_chart` and produces the existing `500 unexpected` error
document; no partially successful document (a response with `svg` but without
`south_indian_svg`) is ever sent by this server. The test injects a failing renderer and
asserts the error document, the status and the absence of a 200 response.

### 5.4 Coexistence and identifiers

North Indian ids: `d1-title`, `d1-desc`; South Indian ids: `d1-south-title`, `d1-south-desc`.
Both prefixes match the id-prefix pattern; a test renders both for the reference charts,
concatenates the documents and asserts every `id` is unique. `data-*` attributes and class
names may repeat across the two documents (they are not identifiers).

### 5.5 Security properties preserved

CSP (`default-src 'none'; script-src 'self'; …`), `X-Viewer-Token`, Host and Origin /
`Sec-Fetch-Site` checks, `MAX_BODY_BYTES = 4096` and the places limit are untouched; the
request is not extended, so nothing new is parsed. The page's `insertSvg` acceptance
(DOMParser, namespace, no `<script>`/`<foreignObject>`, no `on*` attribute) is applied to
`south_indian_svg` exactly as to `svg`. The renderer emits no `url(`, `javascript:` or
`data:` value and no element outside the Layer 10 allow-list (`svg, title, desc, rect, g,
polygon, line, text`), pinned by the same forbidden-element test extended to the new
renderer.

### 5.6 Compatibility and the South-unavailable fallback (precise)

* Older clients ignore the extra key.
* CLI: unchanged; it renders the North Indian document only, as before.
* **The page's rule for a missing or rejected South Indian document.** Let `northOk` be
  whether `insertSvg` accepted `document_.svg`, and `southState` one of `present`
  (`south_indian_svg` is a string that `insertSvg` accepted), `missing` (key absent or not a
  string — an older server), `rejected` (present but refused by `insertSvg`). Then, for the
  selected preference:

  | preference | `southState = present` | `missing` | `rejected` |
  |---|---|---|---|
  | North | North shown | North shown | North shown |
  | South | South shown, North hidden | **North shown** + notice `The South Indian chart is not available from this server's response; the North Indian chart is shown instead.` in `#chart-south-message` (the South block shows the notice only) | **North shown** + notice `The South Indian chart could not be shown: the server's document was not one this page accepts; the North Indian chart is shown instead.` |
  | Both | both shown | North shown + the "not available" notice in the South block | North shown + the "could not be shown" notice in the South block |

  The North chart is never hidden unless a valid South chart is displayed in its place; a
  North chart is never relabelled — its heading stays "D1 chart — North Indian" and the
  South block's heading stays "D1 chart — South Indian" above its notice. The preference is
  **preserved** (the radio stays checked) so that a later valid response shows South
  without the user re-selecting it. When `northOk` is false the existing "could not be
  shown" message appears in `#chart-message` as today, independently of the South state.

## 6. Viewer behaviour

### 6.1 The control

A `<fieldset class="v-style" id="chart-style">` with `<legend class="v-style-legend">Chart
style</legend>` and three radio inputs in one `name="chart-style"` group — `north`
(**checked initially: set by `viewer.js` when the script starts**, because the existing
boundary rule `"checked" not in viewer.html` keeps the markup free of a `checked` attribute;
the script also overrides any radio state a browser restores on reload, so a reload returns
to North Indian), `south`, `both` — each `<input class="v-style-input">` followed by
its visible `<label class="v-style-label">`; placed in the static page **outside**
`#birth-form` and outside `#results-template`, immediately above the results region, so it
is neither submitted nor re-created per document and its state survives every Generate. No
`autocomplete` attribute (the html test's count of three stays), no `aria-controls` (the
combobox rule stays). Keyboard: **native** radio-group behaviour (arrow keys move and select, Tab enters/leaves
the group), nothing scripted; the selected state is the browser's checked state, made
visible by `.v-style-input:checked + .v-style-label` (a border and background using the
existing `--v-*` colour tokens) — class-qualified selectors only, so the bare-element-selector
test stays satisfied. No `role` attribute is added: the markup is a native `fieldset` with a
`legend`, and tests look for a group named "Chart style" containing the three labelled radios
and their checked states — they do not require a `radiogroup` role the markup does not
supply. The fieldset is disabled until the first document is shown.

### 6.2 State

`chartStyle` is a module variable in `viewer.js` (`"north"` initially), updated on the
group's `change` event; **no `localStorage`, `sessionStorage`, cookie, `history` or URL
state** (a boundary test forbids those tokens in the static files). It is read by
`applyStyle(view)`, which is called by `applyDocument` after the results subtree is built and
by the `change` handler with the current `shown.view`.

### 6.3 Layout and the wide mode for Both

The results template gains a second chart block after the first:

```html
<div class="v-charts" id="charts">
  <section class="v-chart-block" id="chart-block-north" data-style="north">
    <h3 class="v-subheading" id="chart-heading">D1 chart — North Indian<span class="v-badge" id="chart-badge" role="status" hidden></span></h3>
    <div class="v-chart-wrapper" id="chart-wrapper"><div id="chart"></div></div>
    <p class="v-scroll-hint" id="chart-scroll-hint" hidden>Scroll horizontally to see the full chart.</p>
    <p class="v-note" id="chart-message" hidden></p>
  </section>
  <section class="v-chart-block" id="chart-block-south" data-style="south" hidden>
    <h3 class="v-subheading" id="chart-south-heading">D1 chart — South Indian<span class="v-badge" id="chart-south-badge" role="status" hidden></span></h3>
    <div class="v-chart-wrapper" id="chart-south-wrapper"><div id="chart-south"></div></div>
    <p class="v-scroll-hint" id="chart-south-scroll-hint" hidden>Scroll horizontally to see the full chart.</p>
    <p class="v-note" id="chart-south-message" hidden></p>
  </section>
</div>
```

The existing ids `#chart`, `#chart-wrapper`, `#chart-scroll-hint`, `#chart-message`,
`#chart-badge`, `#chart-heading` keep their names and roles (D3 changes the heading text).

**Block width.** A chart block's minimum width is the chart's supported minimum plus its
wrapper's chrome: `600 + 2 × 4 (padding) + 2 × 1 (border) = 610 px`. `.v-charts` is
`display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-start`; each `.v-chart-block` is
`flex: 1 1 610px; min-width: 0`; `#chart-south { min-width: 600px; max-width: 1080px }`
mirrors `#chart` (and `insertSvg` applies the same inline sizes to the adopted root). Two
blocks therefore sit side by side exactly when the **actual width of `.v-charts`** is at
least `2 × 610 + 8 = 1228 px`, which the browser decides from the real container, and stack
otherwise.

**Wide mode.** `.v-main` is `max-width: 1120px`, inside which two 610 px blocks can never
fit. When the selected style is **Both and a document is shown**, `applyStyle` adds the class
`v-main-wide` to `main.v-main`; `.v-main-wide { max-width: 1228px }`. With the page's 16 px
side paddings, side-by-side display is reached at a viewport width of `1228 + 32 = 1260 px`
plus the width of a vertical scrollbar when the platform draws one (0 px in headless
Chromium; up to about 17 px with classic scrollbars). In North or South mode, and before
any document is shown, the class is absent and the existing `1120 px` single-chart layout
is untouched; a single chart never widens beyond `1080 + 10 px`, since `#chart`/`#chart-south`
keep `max-width: 1080px`.

**Scrolling.** Each block keeps its own horizontal-scroll wrapper and hint;
`refreshScrollHints` measures both wrappers (on apply, resize and style change). The page
itself must not overflow horizontally at any tested width: wrappers scroll, the document
does not (`document.documentElement.scrollWidth <= window.innerWidth`, measured in §9.3).

No CSS selector reaches inside `#chart` or `#chart-south`; every new class carries the `v-`
prefix; no bare element selector is added.

### 6.4 Filling

`fillChart` inserts `document_.svg` into `#chart` as today. A new `fillSouthChart(fragment,
document_)` inserts `document_.south_indian_svg` into `#chart-south` through the same
`insertSvg`, recording `southState` (§5.6) on the view. Both fills run on every applied
document regardless of the selected style, so a later switch needs **no** network request,
no re-parse and no recalculation: `applyStyle` only toggles `hidden` on the blocks per the
§5.6 table, toggles `v-main-wide`, shows or hides the South notice, and refreshes the scroll
hints. A test counts `fetch` calls across style switches (zero) and asserts the submitted
birth data and `shown.document` are unchanged by a switch.

### 6.5 What a style switch preserves

Daśā expansion state (rows are not rebuilt), the assumptions list and badges, the birth
details, the stale-input state (`refreshStale` reads only the four birth fields; a style
change never calls it and never marks inputs stale), scroll position and focus where the
browser keeps them (the hidden/visible toggle does not move focus; if focus was inside a
block being hidden, focus moves to the group's checked radio). The `ASSUMED_BADGE` and the
assumption labels apply to every displayed chart: `#chart-south-badge` mirrors
`#chart-badge` (both set by `fillBadges`).

### 6.6 Loading, failure, cancellation and stale states

* During a request (`#results` `aria-busy`/`inert`), the control remains enabled and a switch
  re-applies to the currently shown document; when the response arrives, `applyDocument`
  builds the new subtree and `applyStyle` applies the persisted selection.
* After a failed request (error document, network failure) or a cancelled one (`#cancel`,
  or superseded by a newer submit), `shown` is unchanged, so a switch shows the previous
  document's charts under the existing alert/stale semantics; nothing is re-fetched.
* With stale inputs (`data-stale` on `#results`, the stale banner visible), a switch changes
  neither the banner nor `data-stale`.
* With assumed time or default place, both charts carry the badge and the notice list is
  unchanged.

## 7. File manifest (individual paths; nothing created yet)

| path | change |
|---|---|
| `src/vedic_chart/render/south_indian_geometry.py` | new: grid, sign map, `GRID_EDGES`, cell boxes, ladder and capacity, band arithmetic, text wrapping (re-declared) |
| `src/vedic_chart/render/south_indian.py` | new: `SouthIndianOptions`, `render_south_indian_svg`, re-declared convention tables and style |
| `src/vedic_chart/render/__init__.py` | additive: two exports, `__all__` of four names, docstring sentence |
| `src/vedic_chart/viewer/transport.py` | additive: `SOUTH_INDIAN_RENDERER_OPTIONS`; `serialize(..., south_indian_svg=None)`; key appended when given; import `SouthIndianOptions` from `vedic_chart.render` |
| `src/vedic_chart/viewer/server.py` | additive: import `render_south_indian_svg`; the render call after the lock; the argument to `serialize` |
| `src/vedic_chart/viewer/static/viewer.html` | the control (§6.1); the second chart block (§6.3); D3 heading text |
| `src/vedic_chart/viewer/static/viewer.js` | `chartStyle`, `applyStyle`, `fillSouthChart`, `southState`, second wrapper in `refreshScrollHints`, badge mirroring, the `change` handler, `v-main-wide`, disabled-until-shown |
| `src/vedic_chart/viewer/static/viewer.css` | `.v-charts`, `.v-chart-block`, `.v-style`, `.v-style-legend`, `.v-style-input`, `.v-style-label` and its checked rule, `.v-main-wide`, `#chart-south` sizing |
| `tests/test_render_south_indian.py` | new: §9.1 |
| `tests/test_render_south_geometry.py` | new: §9.1 geometry items |
| `tests/test_render_south_golden.py` | new: the South Indian golden suite |
| `tests/fixtures/render_south/jalandhar_caption_degrees.svg` | new golden |
| `tests/fixtures/render_south/jalandhar_caption_nodegrees.svg` | new golden |
| `tests/fixtures/render_south/jalandhar_nocaption_degrees.svg` | new golden |
| `tests/fixtures/render_south/jalandhar_nocaption_nodegrees.svg` | new golden |
| `tests/fixtures/render_south/bharatpur_caption_degrees.svg` | new golden |
| `tests/fixtures/render_south/bharatpur_caption_nodegrees.svg` | new golden |
| `tests/fixtures/render_south/bharatpur_nocaption_degrees.svg` | new golden |
| `tests/fixtures/render_south/bharatpur_nocaption_nodegrees.svg` | new golden |
| `tests/test_viewer_south_indian.py` | new: §9.2 transport/server items |
| `tests/test_viewer_transport.py` | the extended-response case of §8.5 only; existing fixture and assertions untouched |
| `tests/test_render_north_indian.py` | §8.2 |
| `tests/render_helpers.py` | §8.1 |
| `tests/test_viewer_boundaries.py` | §8.4 |
| `tools/viewer/acceptance.py` | the new named checks of §9.3, a `--chromium PATH` option (an explicit Chromium executable for environments whose bundled headless shell is absent), and one narrow amendment of the existing `year_implicit` check (§13.3) |
| `docs/LAYER19_SOUTH_INDIAN_VIEWER_SPEC.md` | this document |
| `README.md` | one subsection under "Interactive viewer" (added at promotion, §13.9) |

Not touched: `north_indian.py`, `north_indian_geometry.py`, `tests/fixtures/render/*.svg`
(the eight North Indian goldens, byte-identical), `tests/fixtures/viewer/*.json`,
`tests/test_app_boundaries.py` (no change needed, §8.3), `vedic_chart/app/*`,
`vedic_chart/representation/*`, `vedic_chart/dasha/*`, the panchanga package,
`pyproject.toml`.

## 8. Boundary-test amendments (each additive; no existing restriction loosened)

1. `tests/render_helpers.py`: `PACKAGE_FILES` gains `"south_indian.py"`,
   `"south_indian_geometry.py"`; a `SOUTH_CASES` registry parallel to `CASES` with
   `SouthIndianOptions`.
2. `tests/test_render_north_indian.py`: `INTERNAL_MODULES` gains the two new modules;
   `test_render_imports_only_what_the_contract_allows` also allows the relative names
   `SouthIndianOptions`, `render_south_indian_svg` in `__init__.py`;
   `test_only_two_names_are_public` becomes `test_only_four_names_are_public` with the sorted
   four-name list; `test_the_package_has_exactly_the_expected_modules` needs no edit (it
   reads `PACKAGE_FILES`); `test_the_geometry_module_imports_nothing_from_the_project` is
   parametrised over both geometry modules; the parametrised forbidden-import,
   allowed-import and never-`round` tests cover the new files automatically. A new test
   asserts that `south_indian.py` imports nothing from `north_indian` or
   `north_indian_geometry`.
3. `tests/test_app_boundaries.py`: **no change** — `pipeline.py` does not import the South
   Indian names; `PIPELINE_PROJECT_IMPORTS["vedic_chart.render"]` stays the two names and the
   file is not in the manifest. `tests/test_viewer_south_indian.py` asserts `pipeline.py`'s
   project imports are unchanged.
4. `tests/test_viewer_boundaries.py`: `FORBIDDEN_IMPORTS` gains
   `vedic_chart.render.south_indian` and `vedic_chart.render.south_indian_geometry` (the
   viewer reaches the render package only through its public surface);
   `PROJECT_IMPORTS["transport.py"]["vedic_chart.render"]` becomes `{"NorthIndianOptions",
   "SouthIndianOptions"}`; `PROJECT_IMPORTS["server.py"]` gains `"vedic_chart.render":
   {"render_south_indian_svg"}`; `test_the_server_holds_the_engine_lock_around_the_pipeline_call_only`
   unchanged (the render call is outside the lock); the html test that counts
   `autocomplete="off"` unchanged (the radios carry none); `_CHART_DESCENDANT` extended to
   `#chart-south` with the same rule; the class-prefix and no-bare-element CSS tests apply to
   the new rules automatically (all new selectors are class- or id-qualified); a new test
   forbids `localStorage`, `sessionStorage`, `document.cookie` and `history.` in `viewer.js`;
   `test_viewer_js_fetches_only_the_two_relative_endpoints` unchanged.
5. `tests/test_viewer_transport.py`: the **existing fixture, its golden comparison
   (`_legacy_document`) and its key-set assertion are untouched** — that fixture calls
   `serialize` without `south_indian_svg`, so its document has no such key and must keep
   none. One **extended-response case** is added: `serialize(result, parsed,
   effective=effective, rows=rows, south_indian_svg=render_south_indian_svg(result.d1,
   SOUTH_INDIAN_RENDERER_OPTIONS))` → the exact key set and order
   `schema, request, engine, location, effective, assumptions, birth, svg, timeline,
   birth_chain, rows, planetary_positions, south_indian_svg`; every pre-existing field,
   **`planetary_positions` included**, equal (`==` and `transport.encode` bytes) to the
   no-keyword document's; `south_indian_svg` verbatim. No golden file is touched or
   regenerated.
6. `tests/test_render_golden.py`: unchanged; the South Indian suite has its own module and
   directory (`test_the_golden_set_is_exactly_the_eight_documented_files` globs
   `tests/fixtures/render/*.svg`).

## 9. Test plan

### 9.1 Renderer (`tests/test_render_south_indian.py`, `tests/test_render_south_geometry.py`)

* The fixed map (§3.1): bijection, clockwise order, centre never used, each cell box inside
  the square, cells non-overlapping; `GRID_EDGES`: exactly 36 edges, equal to the set
  derived from the twelve cell boundaries, no overlaps or duplicates, none inside the centre
  (16 outer, 8 centre-boundary, 12 shared — counted by classification); the rendered document
  has exactly 36 `line.cell-edge`, exactly four with class `lagna` (the Lagna cell's own four
  edges) at twice the stroke width, and no stroked `rect`/`polygon`.
* All twelve Lagna signs: synthetic `D1Chart`s with the Lagna in each sign (built with Layer
  9's public builder from synthetic `BirthChart`s, as Layer 10's tests build theirs) — the
  `As` row is in the cell of `lagna.rashi_index`, that cell has `data-lagna="true"` and
  `data-house="1"`, its four edges are the thick ones, and every cell's `data-house` equals
  the number of the `D1House` with that `rashi_index`; sign positions identical across the
  twelve.
* Every planet in the cell of its `rashi_index`, with its house record's number on the
  cell; occupant order within a cell equals `D1House.occupants` order.
* Degrees on/off, retrograde underline with and without `mark_node_retrograde` (Rahu/Ketu
  retrograde in the reference charts), node display, caption on/off, the title suffix rule,
  the privacy scan (§4.3).
* Crowding and the occurrence rules (§3.3), with labelled synthetic cases: `one_sign_all_nine`
  (nine grahas in one sign, Lagna elsewhere), `lagna_sign_all_nine` (ten entries), `six_exact`
  (six entries, no overflow), `seven_first_overflow`, `two_signs_crowded`, each with and
  without degrees. Asserted per case: the size, the rows shown, `+n` equal to the omitted
  occupant count, the legend block present exactly for overflowing signs with the complete
  occupant list in order, each planet at most once among `g.entry[data-graha]` groups in cells,
  exactly once in its sign's legend when that sign overflows and in no legend otherwise, every
  planet represented, `As` once and never in a legend; no overlapping text boxes; entry font
  never below the floor.
* Determinism and escaping (§4.3); invalid options (each of the five, as Layer 10's tests);
  a non-`D1Chart`; unsupported convention labels refused with `caption=True` and ignored
  without a caption (§4.1).
* Convention equality with Layer 10 (§4.4).
* Goldens: the eight documents of §7 in `tests/fixtures/render_south/`, compared by string
  equality, written only with `RENDER_GOLDEN_UPDATE=1`, well-formed XML, ending in a newline.
* **North Indian byte equality**: the existing golden test module is unchanged and must
  pass; additionally the new module renders the eight North Indian cases and compares them
  to the stored goldens again.
* Both charts together: concatenated documents have unique ids (§5.4).

### 9.2 Transport and server (`tests/test_viewer_south_indian.py`, additive cases in `tests/test_viewer_server.py`, the §8.5 case in `tests/test_viewer_transport.py`)

* `serialize` without the keyword omits the key (existing fixture unchanged); with it, the
  key is last and verbatim and every other field is unchanged (§8.5).
* Through the live server (the existing fixture harness): the document carries
  `south_indian_svg` equal to `render_south_indian_svg(result.d1,
  SOUTH_INDIAN_RENDERER_OPTIONS)`; `svg` is byte-identical to a fresh
  `render_north_indian_svg(result.d1, RENDERER_OPTIONS)` and, where the environment
  reproduces the platform-pinned golden, to the golden's `svg`; `planetary_positions`,
  `timeline`, `rows` and `birth_chain` are unchanged.
* One calculation per Generate: a monkeypatched `render_chart_and_dasha_at` counts exactly
  one call per `/api/chart` request; an AST test asserts the South Indian render call lies
  outside the `with ENGINE_LOCK` block and inside the `try`.
* Failure injection: a raising `render_south_indian_svg` → `500 unexpected` error document,
  no 200.
* Security: CSP header unchanged; token/Host/Origin refusals unchanged; both SVGs pass the
  Python re-implementation of the `insertSvg` checks used by the server tests.

### 9.3 Static files and browser acceptance (`tools/viewer/acceptance.py`, extended)

The existing check `year_implicit` asserted "no radio and no fieldset anywhere on the page"
as its proof that the year-convention control is gone; the Chart style control is a fieldset
of three radios, so the check now asserts there are **no radios and no fieldsets other than
the `#chart-style` control**, that `year_convention` controls are zero, and that the control's
radios are exactly three — the same intent, stated against the new control.

Static checks (pytest): the control markup and classes, the second block, the ids of §6.3,
the CSS rules, no storage tokens, no new endpoint, class prefix, no bare element selectors,
no descendant selectors into either chart container.

Browser acceptance: the existing script `tools/viewer/acceptance.py` (Playwright Chromium,
not a dependency, not collected by pytest, writes only under `--out`) keeps every existing
named check and gains the following named checks, run at the desktop viewport 1280 × 800 and
the mobile viewport 375 × 812 as stated, for both reference births (Jalandhar; Jammu when the
record is available, skipped with an explicit entry otherwise):

* `style_default_north` — the control exists, is disabled before the first document, enabled
  after it, `north` checked; only the North block visible.
* `style_switch_no_requests` — after one Generate, switching North → South → Both → North
  issues **zero** network requests (Playwright request log), leaves `shown.document` and the
  four birth fields unchanged, and never marks inputs stale.
* `style_one_calculation_per_generate` — exactly one `/api/chart` request per Generate
  across style changes (request log); the server-side single-call property is the unit test
  of §9.2.
* `style_both_side_by_side_1280` — at 1280 × 800 the two blocks share one top edge, each
  chart's rendered width is ≥ 600 px, `.v-main` has `v-main-wide`, no wrapper overflows, no
  page-level horizontal overflow (`scrollWidth <= innerWidth`).
* `style_both_stacked_375` — at 375 × 812 the blocks stack, each wrapper overflows and shows
  its own hint, the page does not overflow horizontally.
* `style_both_threshold` — the script computes the threshold from computed styles
  (`2 × (600 + 2·padding + 2·border) + gap` of `.v-charts`, plus the body's side paddings
  and the measured scrollbar width) and sets the viewport to that width and to one pixel
  less: side by side at the threshold, stacked one pixel below; no page overflow at either.
* `style_single_layout_unchanged` — in North and in South mode `.v-main` keeps its 1120 px
  maximum and the single chart's width equals the pre-Layer-19 measurement.
* `style_fallback_missing`, `style_fallback_malformed`, `style_fallback_valid` — the server
  is fronted by the script's interception to deliver a document without the key, with a
  malformed South document (`<svg><script/></svg>`), and the real one; for each of the three
  preferences the §5.6 table holds: the North chart stays visible and labelled North, the
  South block carries the right notice or the chart, the radio keeps its state, and after the
  valid document arrives the South chart appears under the preserved preference.
* `style_during_loading`, `style_after_failure`, `style_after_cancel`, `style_stale_preserved`
  — switching while a delayed response is pending, after an injected 500, after `#cancel`,
  and with stale inputs: the previous document's charts, the banner and `data-stale` are as
  §6.6 states; no request is issued by the switch.
* `style_keyboard` — Tab reaches the group, arrow keys move the selection (native behaviour)
  and the page updates, the checked label carries the visible selected style (computed
  border/background differs from the unchecked ones), and the accessibility tree contains a
  group named "Chart style" with three radios labelled "North Indian", "South Indian", "Both"
  whose checked states follow the selection.
* `style_assumptions_and_dasha_preserved` — with assumed time and default place, both chart
  badges and the assumption list are present in every mode; a daśā tree expanded two levels
  before a switch is unchanged after it (row count, `aria-expanded`, focused row).
* `style_unique_ids` — in Both mode every `id` in the results subtree is unique and the two
  SVG roots carry `d1-title`/`d1-desc` and `d1-south-title`/`d1-south-desc`.
* `south_svg_bytes_equal_renderer` and `south_svg_pixels_equal_standalone` — the captured
  `south_indian_svg` equals the renderer's output for the same `D1Chart` (via the CLI-less
  Python comparison the script already uses for the North document) and the inserted chart
  rasterises identically to the standalone document, as `svg_pixels_equal_standalone` does
  for the North chart.
* `south_text_bounds_600` — at the 600 px minimum chart width, for the reference births and
  for the synthetic stress cases `one_sign_all_nine` and `lagna_sign_all_nine` (served through
  the interception from documents rendered by the test's own synthetic `D1Chart`s): every
  `text.sign-label` (all twelve names, including `Vrishchika`), every `text.house-label`
  (`H1`…`H12`, `H10`–`H12` checked by name), every `text.entry`, every `text.overflow` and
  every legend text has a bounding rectangle inside its cell or band and not intersecting any
  other text's rectangle, **all in one coordinate system**: every `getBBox()` rectangle (SVG
  user units) is mapped through the element's `getScreenCTM()` into CSS pixels before any
  comparison, and the cell/band rectangles are mapped the same way; the **effective** font
  size is the `font-size` attribute (user units) multiplied by the screen transform's scale
  (`a` of `getScreenCTM()`), which at a 600 px chart is `600/1080`, and must equal §3.3's
  pixel figures within 0.1 px — a raw `font-size="21"` property is never read as 21 on-screen
  pixels.

Screenshots are kept under the run's `--out` directory and copied to `Claude outputs/`.

### 9.4 Environments

Run per environment and reported separately: cloud sandbox (Python 3.11.x) full suite
against its measured baseline at `c67f46c` (last measured 3833 passed / 12 failed, the known
environment-dependent goldens: 8 `test_dasha_from_chart`, 2 `test_dasha_table`, 2
`test_viewer_transport`); session VM (3.10.12 aarch64) against its measured baseline
(3845 / 0); native macOS targeted run of the new and amended test files by the owner. Every
failure is identified against a baseline measured in that environment at implementation
time; none is assumed pre-existing.

## 10. Decisions

D1, D2 and D3 are closed (see the status paragraph). No decision is open at v0.2.

## 11. Limitations

* The South Indian chart shows rāśi placements only (D1); no divisional charts.
* Two documents are rendered per submission; the second is pure and adds no ephemeris work,
  but the response grows by one SVG (about the size of `svg`); the 4 KiB request limit is
  unaffected.
* "Both" side by side needs a viewport of about 1260 px (plus any scrollbar); below that the
  charts stack by design, each scrolling in its own wrapper.
* The style preference lives in the page only; reloading the page returns to North Indian
  (no storage in this milestone).
* The smallest text in the South Indian document is the 20-unit label text (≈ 11.1 px at
  the 600 px minimum width); the entry floor is 21 units (≈ 11.67 px).

## 12. Change log

### v1.0 from the closing revision (2026-10-08; promotion)

Documentation only. Status promoted to SPECIFICATION v1.0; §13.2 and §13.6 corrected to
distinguish the **completed** session-VM targeted run (three South render modules, 662 passed,
after the comment edit) from the **unperformed** session-VM baseline/updated full-suite
comparison; the README subsection on chart styles added (§13.9). The draft history below, the
limitations of §11 and §13.6 and the qualified pixel results of §13.4/§13.7 are preserved
unchanged.

### Closing revision (2026-10-08; DRAFT retained at the time)

After the owner's independent native review: §4.1 and §8.1 reconciled to the implemented
caption-only rejection of unsupported convention labels (as Layer 10); one comment in
`south_indian.py` corrected; §13.2, §13.4, §13.6–§13.8 record the native test run, the
native browser evidence and the qualified pixel comparison. No behaviour changed; not promoted.

### v0.2 from v0.1 (the review's seven findings)

1. *Side by side made achievable.* `.v-main` is 1120 px wide; two 610 px blocks (600 px chart
   + 10 px wrapper chrome) cannot fit. Both mode adds `v-main-wide` (`max-width: 1228px`),
   the gap is 8 px, the block basis is 610 px, wrapping follows the real `.v-charts` width,
   and the threshold (≈ 1260 px viewport plus scrollbar) is computed and tested at 1280, 375,
   the threshold and one pixel below, with page-level overflow checked (§6.3, §9.3).
2. *Strokes reconciled.* One canonical set of non-overlapping unit edges drawn once (36 after
   the owner's correction; v0.2 wrote 32); the
   Lagna cell's four edges at twice the width; structural `rect.cell` elements stroke nothing;
   legend wording "thicker border" (§3.1, §3.4, §3.6, §9.1).
3. *Occurrence rules stated.* The complete-list legend is kept and the intentional repetition
   is specified and tested per condition instead of document-wide uniqueness (§3.3, §9.1).
4. *Fallback defined.* The §5.6 table: a missing or rejected South document keeps a valid
   North chart visible with an explicit notice even under the South preference; the
   preference is preserved; nothing is relabelled; tested across missing/malformed/valid ×
   three modes (§5.6, §6.4, §9.3).
5. *Typography and CSS corrected.* Actual rendered sizes stated (entry floor 21 units ≈
   11.67 px at 600 px; labels 20 units ≈ 11.11 px); the floor scoped to entry text; the
   selector made class-qualified (`.v-style-input:checked + .v-style-label`); browser checks
   measure text bounds for all labels, `H10`–`H12`, crowded cells, legends and synthetic
   stress cases at 600 px (§3.3, §6.1, §9.3, §11).
6. *Transport tests kept consistent.* The existing no-keyword fixture, its golden comparison
   and key set are untouched; an extended-response case checks the exact extended key set and
   order and every pre-existing field, `planetary_positions` included (§5.1, §8.5).
**Owner's implementation corrections (2026-10-07, applied before implementation):**
(a) `GRID_EDGES` is 36 edges derived from the twelve cell boundaries (§3.1, §3.7, §9.1);
(b) one logical entry group per displayed row — `g.entry[data-graha]` / `g.legend-entry` with
`text.abbr`, optional `text.degrees` and `line.retro` — and occurrence tests count groups
(§3.7, §9.1, §4.4); (c) the control stays a native `fieldset`/`legend` with radio inputs and
native keyboard behaviour; tests look for the named group and labelled radios, not a
`radiogroup` role (§6.1, §9.3); (d) browser typography checks map SVG user units to CSS
pixels through `getScreenCTM()` and compare bounds and effective font sizes in one coordinate
system (§9.3).

7. *Acceptance manifest completed.* `tools/viewer/acceptance.py` named and extended with the
   checks of §9.3; every changed path listed individually with the eight golden filenames;
   `tests/test_app_boundaries.py` removed from the manifest; the §3.2 cross-reference fixed
   (D1, not D2).

### v0.1 (2026-09-27)

First draft.

## 13. Implementation record (2026-10-07; reviewed 2026-10-08; nothing staged or committed at the time of writing)

Built by two Opus subagents (renderer; transport/viewer/acceptance) from this draft with the
owner's four corrections applied, reviewed against it by Fable. Working copy: a `git archive`
of `c67f46c` (144 tracked files, tar sha256 `11ea4c0181513d14`) extracted in the cloud
sandbox; the sandbox interpreter is Python 3.13.16 with `pyswisseph 2.10.3.2`,
`timezonefinder 8.2.0`, `pytest 9.1.1`, `playwright 1.63.0` and the PyPI `tzdata 2026.5`
package (the sandbox's system zoneinfo lacks the backward link
`America/Argentina/ComodRivadavia` that `tests/render_helpers.py` uses; without the package
28 Layer 10 tests fail on that zone alone — recorded in §13.4, nothing in the project
changed for it).

### 13.1 Changed files (individual paths; SHA-256 prefixes of the delivered state)

| path | change | lines | sha256 |
|---|---|---|---|
| `src/vedic_chart/render/south_indian_geometry.py` | new | 417 | `8fc0e50fbd5d8e3f` |
| `src/vedic_chart/render/south_indian.py` | new (one comment reworded 2026-10-08, §13.8) | 717 | `c8d7d3ceb61924ad` (was `92668a69d7205ae2`) |
| `src/vedic_chart/render/__init__.py` | additive exports, four-name `__all__` | 15 → 23 | `bb229132099cccdc` |
| `src/vedic_chart/viewer/transport.py` | `SOUTH_INDIAN_RENDERER_OPTIONS`, `serialize(..., south_indian_svg=None)` | 1170 → 1206 | `4b2c0937f6a38cb5` |
| `src/vedic_chart/viewer/server.py` | one import; the render call after the lock inside the `try`; the argument | 1198 → 1209 | `5499a4569a872439` |
| `src/vedic_chart/viewer/static/viewer.html` | the control; the two chart blocks; D3 headings | 151 → 174 | `c0a6d537522fd652` |
| `src/vedic_chart/viewer/static/viewer.js` | `chartStyle`, `fillSouthChart`, `applyStyle`, `wireStyleControl`, second hint, mirrored badge | 1623 → 1780 | `e84e4431e8deda26` |
| `src/vedic_chart/viewer/static/viewer.css` | `.v-charts`, `.v-chart-block`, `.v-style*`, `.v-main-wide`, `#chart-south` | 489 → 566 | `02ac72137a89e779` |
| `tests/render_helpers.py` | `PACKAGE_FILES`, `SOUTH_CASES` and helpers | 360 → 450 | `938dd491860136d6` |
| `tests/test_render_north_indian.py` | §8.2 amendments only | 1079 → 1110 | `8db2f773f0479930` |
| `tests/test_viewer_boundaries.py` | §8.4 amendments and the new static tests | 809 → 1057 | `5b7701f1b1e5ca0e` |
| `tests/test_viewer_transport.py` | the §8.5 extended-response test only | 1411 → 1463 | `ed5c0da2413bd928` |
| `tests/test_render_south_geometry.py` | new, 28 test functions | 331 | `0c31f93a79ed7967` |
| `tests/test_render_south_indian.py` | new, 44 test functions | 1092 | `199fd224ad0599e1` |
| `tests/test_render_south_golden.py` | new | 84 | `a96962ff002fa92b` |
| `tests/fixtures/render_south/bharatpur_caption_degrees.svg` | new golden | | `a9a9cd7e7fd39360` |
| `tests/fixtures/render_south/bharatpur_caption_nodegrees.svg` | new golden | | `eab051ddbc2223b8` |
| `tests/fixtures/render_south/bharatpur_nocaption_degrees.svg` | new golden | | `4cfcd1ac3b55dbbb` |
| `tests/fixtures/render_south/bharatpur_nocaption_nodegrees.svg` | new golden | | `0fd4e0242a197377` |
| `tests/fixtures/render_south/jalandhar_caption_degrees.svg` | new golden | | `b6671e1abaa978e0` |
| `tests/fixtures/render_south/jalandhar_caption_nodegrees.svg` | new golden | | `f0788434e575b1be` |
| `tests/fixtures/render_south/jalandhar_nocaption_degrees.svg` | new golden | | `9f4a2b8fe998a010` |
| `tests/fixtures/render_south/jalandhar_nocaption_nodegrees.svg` | new golden | | `350f5678e328ef13` |
| `tests/test_viewer_south_indian.py` | new, 15 test functions | 523 | `46d577f03615f80c` |
| `tools/viewer/acceptance.py` | `--chromium`, 20 new checks + `style_previews`, the `year_implicit` amendment | 4115 → 6067 | `32794b609df0fc50` |
| `docs/LAYER19_SOUTH_INDIAN_VIEWER_SPEC.md` | this document (closing revision 2026-10-08) | | (its own hash is in the closing report) |

Not changed (verified by hash against `c67f46c`): `north_indian.py` `0c492246220529e1`,
`north_indian_geometry.py` `d7b553261501e3d7`, `app/pipeline.py` `9cb4a0619f3d563a`,
`app/cli.py` `6269a74e7c6a8003`, `app/__init__.py` `71413f1072864040`,
`representation/d1.py` `c37278f20e697a6c`, `dasha/__init__.py` `36385599315f633c`,
`pyproject.toml` `2d77dfbef5dc4c49`, `tests/test_app_boundaries.py` `ba48e9809cfe5959`,
`tests/test_render_golden.py` `f4f66175bd50883f`, `tests/test_render_geometry.py`
`26993955b12bab1f`, all eight `tests/fixtures/render/*.svg`, all three
`tests/fixtures/viewer/*.json`, every `tests/fixtures/dasha/*`, the panchanga package and
its tests. `tests/test_viewer_server.py` needed no change and is not in the manifest.
`README.md` gained one subsection at promotion (§13.9).

### 13.2 Test results by environment

* **Cloud sandbox** (Linux x86_64, Python 3.13.16, pyswisseph 2.10.03): full-suite
  **baseline measured at `c67f46c` before any change: 3833 passed, 12 failed** (8
  `test_dasha_from_chart`, 2 `test_dasha_table`, 2 `test_viewer_transport` — the
  platform-pinned goldens; the first measurement without the PyPI `tzdata` package was
  3805 / 40, the extra 28 being the `long_name_*` Layer 10 cases that need the
  `ComodRivadavia` link). **Updated: 4541 passed, 12 failed**, the failure set identical to
  the baseline's. The seven Layer 19 and Layer 10 renderer/viewer test modules together:
  **1240 passed** (`test_render_south_geometry`, `test_render_south_indian`,
  `test_render_south_golden`, `test_viewer_south_indian`, `test_viewer_boundaries`,
  `test_render_north_indian`, `test_render_golden`).
* **Native macOS** (Darwin arm64, Python 3.11.16, native pyswisseph 2.10.3.2; the owner's
  independent run of 2026-10-08, recorded from its `local-review.json` and logs):
  **baseline at `c67f46c`: 3832 passed, 12 failed, 1 deselected; Layer 19: 4540 passed,
  12 failed, 1 deselected.** The twelve failure identities are unchanged between the two runs
  (eight `test_dasha_from_chart`, two `test_dasha_table` goldens, two `test_viewer_transport`
  goldens — the platform-pinned set). The one deselected test is pre-existing,
  `tests/test_app_cli.py::test_a_cleanup_failure_is_reported_after_the_original_error`,
  excluded identically from both runs because its mocked `os.unlink` interferes with pytest's
  temporary-file teardown on macOS and poisons later setup; its body passes when run alone.
  No repository test was modified for the exclusion. **This is therefore not an unqualified
  all-green full-suite run**: it is the full suite less one deselected pre-existing test, with
  the known twelve platform-pinned failures. Net: 708 additional passing cases; the review
  notes that two pre-existing boundary-test identities were renamed/parameterised by the §8.4
  amendments and that no previously passing test regressed.
* **Session VM** (Python 3.10.12, aarch64, the repository's `.venv`): **one targeted run
  only** — the three South render modules (`test_render_south_geometry`,
  `test_render_south_indian`, `test_render_south_golden`), **662 passed**, made after the
  comment edit of §13.8, with the South goldens byte-identical. **No** full-suite baseline or
  updated run was made in the VM, so no VM baseline/updated comparison exists (§13.6).

### 13.3 Deviations and interpretations (reported explicitly)

* `stroke-linecap="square"` on every `cell-edge` line, so the doubled Lagna edges meet at
  their corners without notches (§3.1 updated).
* The first legend marker line was shortened to `As = Lagna (ascendant), first in its cell;
  thicker border` (57 characters) because the v0.2 wording (62) wrapped under the 60-character
  legend budget (§3.6 updated); the document height without caption is therefore 1202 units.
* The North Indian radio is checked by `viewer.js` at start-up rather than by a `checked`
  attribute (the existing boundary rule forbids the attribute in the markup); a reload returns
  to North Indian (§6.1 updated).
* The existing acceptance check `year_implicit` asserted "no radios and no fieldsets on the
  page"; it now asserts none **other than** the `#chart-style` control (§9.3 updated). It is
  the only pre-existing check whose assertion changed.
* `transport.serialize` raises `TypeError` for a `south_indian_svg` that is neither `None` nor
  a string (the same discipline as its other arguments).
* Unsupported convention labels raise only when `caption=True`, exactly as Layer 10, because
  the labels are read only to build the caption.
* `select_size` takes an optional fourth argument (`show_degrees`) so the width budget shrinks
  to the abbreviation slot without degrees; with three arguments it is Layer 10's rule, tested
  equal on four box sizes.
* The Python re-implementation of the page's `insertSvg` acceptance did not exist in
  `test_viewer_server.py` as assumed; it was written in `tests/test_viewer_south_indian.py`
  with a negative test.
* A pre-existing cosmetic defect was observed and **not** fixed (outside this milestone): the
  `.v-badge` pill shows as an empty yellow outline beside the headings when nothing is
  assumed, because its `display: inline-block` overrides the `hidden` attribute; the mirrored
  `#chart-south-badge` behaves identically.

### 13.4 Browser acceptance (cloud sandbox, headless Chromium 141.0.7390.37 through Playwright)

Command: `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers PYTHONPATH=src python tools/viewer/acceptance.py
--python <venv> --geodata tests/fixtures/geodata_fixture.sqlite --ephemeris ephe --out <dir>
--default-place-id 1268782 --chromium /opt/pw-browsers/chromium-1194/chrome-linux/chrome`.
Baseline run before the change: 30 passed, 0 failed, 1 skipped. After: **51 passed, 0
failed, 1 skipped** (`reference_jammu_365256363`, the fixture database has no Jammu record;
every per-birth Layer 19 check records an explicit `jammu: skipped` entry — see §13.6 for the
full-database run). Evidence (`report.json` and `screenshots/` delivered under
`Claude outputs/l19_acceptance/`):

* `style_switch_no_requests`: North → South → Both → North issued **0** requests; the results
  subtree and both SVG roots are the same DOM nodes before and after; form values unchanged;
  `data-stale` absent and the stale banner hidden throughout.
* `style_one_calculation_per_generate`: `/api/chart` requests 1 after the first Generate, 2
  after the second, still 2 after five switches; the server log holds exactly two
  `api_chart 200` lines.
* `style_both_side_by_side_1280`: at 1280 × 800 both blocks at `offsetTop` 1056, lefts 26 and
  644, each block 610 px wide with a 600 px chart, no wrapper overflow, page
  `scrollWidth 1280 ≤ innerWidth 1280`, `v-main-wide` present.
* `style_both_stacked_375`: at 375 × 812 blocks at `offsetTop` 1770 and 2538, each wrapper
  scrolling (608 px content in 341 px) with its hint shown, page `375 ≤ 375`.
* `style_both_threshold`: computed from the live styles `2 × (600 + 8 + 2) + 8 + 32 + 0
  (scrollbar) = 1260`; at 1260 px `.v-charts` is 1228 wide and the blocks share one top edge
  (lefts 16 and 634); at 1259 px it is 1227 wide and the blocks stack (south `offsetTop`
  2334); no page overflow at either width.
* `style_single_layout_unchanged`: in North and South mode the chart is 1080 px at 1280 and
  600 px at 375, `.v-main` keeps 1120 px — equal to the pre-change run's measurements.
* `style_fallback_missing` / `_malformed` / `_valid` (route interception: key deleted;
  `<svg><script/></svg>`; the real document) × North / South / Both: the §5.6 table holds in
  every cell; e.g. missing + South: North visible, South block visible with the
  "not available" notice and no South `svg` element, radio `south` still checked, no
  `v-main-wide`; after the valid document the South chart appears under the preserved
  South preference.
* `style_during_loading`, `style_after_failure` (injected 500 and a network abort),
  `style_after_cancel` (`#cancel` and a superseded submit), `style_stale_preserved`: the
  previous document's nodes are kept, no request is issued by a switch, alert, stale banner
  and `data-stale` unchanged; `aria-busy="true"` while loading with the control enabled.
* `style_keyboard`: Tab from Generate reaches the checked radio; ArrowRight/Left/Up/Down move
  the selection natively and the page follows at each step; Tab leaves to `#expand-all`,
  Shift+Tab returns; the checked label has border `rgb(28,79,156)` and background
  `rgb(244,245,248)` against transparent unchecked labels; the accessibility tree holds a
  group named "Chart style" with three labelled radios; focus inside a block being hidden
  moved to the checked radio.
* `style_assumptions_and_dasha_preserved`: with assumed time and default place all four
  badges and both assumption labels are present in every mode; the daśā tree (rows,
  `aria-expanded`, roving row, focus) is unchanged across switches.
* `style_unique_ids`: no duplicate id in Both mode; roots carry `d1-title`/`d1-desc` and
  `d1-south-title`/`d1-south-desc`.
* `south_svg_bytes_equal_renderer`: the captured `south_indian_svg` is the renderer's output
  (sha256 `9f4a2b8f…`, equal to `jalandhar_nocaption_degrees.svg`); the inserted DOM has 126
  elements and 201 text nodes, equal to the parsed document.
* `south_svg_pixels_equal_standalone`: 0 differing pixels at 600 and 1080 px — **a result
  specific to this browser and environment** (headless Chromium 141 on Linux); the native
  comparison in §13.7 did not reproduce pixel equality.
* `south_text_bounds_600`: at a 600 px chart the root CTM scale is 0.55555; effective font
  sizes labels 11.1109 px, centre 17.7775 px, legend 12.222 px, entries 17.7775 px (base) and
  11.6665 px (floor, in the stress cases); every text's screen rectangle inside its cell or
  band, no two overlapping — for Jalandhar (47 texts) and the synthetic `one_sign_all_nine`
  (59 texts, `+4`) and `lagna_sign_all_nine` (57 texts, `+5`, `As` occupying a row), each with
  its complete-list legend.
* `style_previews`: `preview_jalandhar_{north,south,both}_{1280,375}.png` written. Jammu
  previews from this script do not exist: the script has **not** been run against the full
  database in any environment, and its `reference_jammu_365256363` skip stands as recorded
  above. Native Jammu previews come from the independent script of §13.7.

### 13.5 Protected behaviour verified

One pipeline call per request (unit test with a counting wrapper; acceptance request counts);
the South render outside the lock (AST test); the no-keyword `serialize` document unchanged
(the existing fixture and golden assertions untouched and passing where the platform
reproduces them; the extended-response test shows every pre-existing field, including
`planetary_positions`, byte-equal); the request payload unchanged; CSP, token, Host/Origin
checks and payload limits unchanged (existing tests); the North Indian goldens byte-identical
from both the existing and the new golden modules; the CLI untouched; no dependency change.

### 13.6 Not run, and not claimed

* **Session VM full-suite comparison** (Python 3.10.12, aarch64): no baseline run at
  `c67f46c` and no updated full-suite run were made in the VM — the link to the owner's
  machine was down when the cloud record was written and the owner's review did not make one
  either. The VM's only run is the targeted 662-test run of the three South render modules
  recorded in §13.2; it is not a full-suite result and supports no regression comparison.
* **`tools/viewer/acceptance.py` against the full `data/geodata.sqlite`**: not run in any
  environment (the cloud sandbox holds only `tests/fixtures/geodata_fixture.sqlite`, which has
  no Jammu record, and the script's Python Playwright dependency is not installed natively).
  Its `reference_jammu_365256363` skip in the cloud run is the recorded state. The owner's
  command, should it be wanted later, from the repository root:

```
PYTHONPATH=src python tools/viewer/acceptance.py --python "$(which python)" \
  --geodata data/geodata.sqlite --ephemeris ephe --out "Claude outputs/l19_acceptance/full_db"
```

### 13.7 Native browser evidence (owner's independent review, 2026-10-08; supplementary)

Recorded from the review folder `l19-review-20261008/` (`LOCAL_REVIEW.txt`,
`local-review.json`, `native-browser/report.json`, `independent-parity.json`,
`pixel-comparison.json`, screenshots, server log). These checks were made by an independent
targeted Node/Playwright script (`native_browser.cjs`, installed Google Chrome 154.0.8037.98)
against the **real native server and the production geodata database** on macOS. They
**supplement** the cloud acceptance run of §13.4; they are **not** a native execution of
`tools/viewer/acceptance.py`, and they do not lift that script's Jammu skip.

* **19 targeted checks passed, 0 failed**, for both Jammu (place 1269321) and Jalandhar:
  initial North preference with the control disabled until the first document; production
  autocomplete choosing the correct record and exactly one `/api/chart` request per Generate,
  819 timeline rows each; North/South/Both switches preserving the SVG node identity and the
  expanded daśā state with no new request; native radio keyboard behaviour; unique document
  ids in Both mode; side by side at 1260 px and stacked at 1259 px, mobile wrappers scrolling
  without page overflow; native previews (`{jammu,jalandhar}_{south,both}_{1280,375}.png`);
  only the five own-origin routes (`/`, `/api/chart`, `/api/places`, `/viewer.css`,
  `/viewer.js`), no page error, no CSP violation; a reload resets the preference to North.
* **Parity with fresh renders**: for both births the response's `svg` and `south_indian_svg`
  are byte-equal to fresh renders through the pipeline; the North document is byte-equal to
  the CLI's stdout; all 819 rows per birth (UTC endpoints, nominal offsets, N/Q flags) equal
  the independently computed timeline values. South sha256 prefixes: Jammu `8f76159bc2457e5a`,
  Jalandhar `9f4a2b8fe998a010` (the latter equal to the `jalandhar_nocaption_degrees.svg`
  golden and to the cloud capture).
* **Pixel comparison — qualified, not equality.** After matching the CSS width and the
  fractional origin (phase y 0.484375), the inserted and standalone screenshots differ by
  **82 pixels at 600 px and 48 (Jammu) / 47 (Jalandhar) pixels at 1080 px**, each differing
  pixel by one intensity level in its RGB channels; the PNG bytes are not identical. The cause
  is **unestablished** (the review calls them tiny edge-rasterisation differences without
  attributing them). No native pixel equality is claimed, the renderer was not altered to
  force a match, and the cloud result of §13.4 stands only with its own environment
  qualification. The native screenshots, difference images and the exact pixel report are in
  `native-browser/`.

### 13.8 Closing revision (2026-10-08; documentation and one comment; DRAFT at the time)

Made after the owner's review, without changing calculation or rendering behaviour:

* §4.1 reconciled with the implementation and §13.3: unsupported `house_system`/`node` labels
  are refused only with `caption=True` (the labels are read solely for the caption), exactly
  as Layer 10; without a caption the document renders regardless. §8.1's test line now says
  the same. This retains the implemented and tested behaviour.
* The one comment in `src/vedic_chart/render/south_indian.py` that read as unconditional
  ("read — and an unsupported one rejected — before a single character…") now states the
  caption-only reading. Comment-only; the module's code is unchanged, and the Layer 19 render
  modules and goldens were re-run after the edit: cloud sandbox, the seven render/viewer
  modules 1240 passed; session VM (Python 3.10.12, aarch64), the three South render modules
  662 passed, goldens byte-identical.
* §13.2 records the native macOS run as the owner reported it, with the deselected
  pre-existing cleanup test and the unchanged twelve failures stated, not as an all-green run.
* §13.4's pixel-equality bullet carries its environment qualification; §13.7 added for the
  native browser evidence; §13.6 rewritten to list what was not run.
* Hashes of the two edited files are in §13.1 (updated in place). No other file changed.

### 13.9 Promotion (2026-10-08; documentation only)

Promoted to SPECIFICATION v1.0 on the owner's instruction. Changes at promotion: the status
line; §11's heading; §12's v1.0 entry; §13.2 and §13.6 reworded so that the session VM's
completed targeted run (662 tests, three modules) is not mistaken for the unperformed VM
full-suite baseline/updated comparison; this section; and one `README.md` subsection ("Chart
styles: North Indian, South Indian, Both") under "Interactive viewer", describing the three
modes, the North Indian default, client-only switching with no request and no recalculation,
and the unchanged calculations. Verified at promotion: every executable path, test module,
golden and fixture of §13.1 keeps the hash recorded there (`south_indian.py`
`c8d7d3ceb61924ad` from §13.8), and every protected file remains byte-identical to `c67f46c`.
No full-suite rerun was made for the promotion, none being needed for documentation.
Nothing installed, staged, committed, pushed or deployed.
