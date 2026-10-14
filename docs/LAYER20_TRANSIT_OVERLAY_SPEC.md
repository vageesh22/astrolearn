# Layer 20 — Natal–transit overlay toggle in the viewer

**Status:** SPECIFICATION v1.0 (promoted 2026-10-11 on the owner's instruction, documentation
only). The implementation of 2026-10-09 (with the corrections of §14) and the closing pass of
2026-10-10 (§16.7, including the corrected house-label width model and the synthetic browser
evidence) are the implementation this specification describes; its history is the draft
series v0.1 2026-10-08, v0.2 2026-10-09, v0.3 2026-10-09. The design sections §1–§15 are the
v0.3 text the implementation was built from (their "Proposed" markings are historical); §16
is the implementation record, whose limitations (§11, §16.4, §16.6) and verification
boundaries (§16.2: no native browser acceptance and no native full-suite run) remain part of
this specification and are not superseded by the promotion. Promotion changed documentation
only: no executable code, test, golden or fixture changed after the closing pass. Baseline:
commit `1905e86` (`master`, "Add Layer 19: South
Indian D1 renderer and viewer chart-style switching"), verified on the owner's machine before
v0.1: clean working tree, empty index, 159 tracked files; the cloud copy this draft was
written against is byte-identical to those files; the Layer 20 files were delivered on top
of it without staging.

This is a **viewer presentation** milestone. A transit chart is an ordinary chart generated
for another instant through the unchanged `POST /api/chart` endpoint, with the unchanged
four-key request; the page keeps the natal result and lays the second chart's nine graha
placements over the natal frame. Nothing in this layer changes the FROZEN v1.0 calculation
specification, Layer 9's `D1Chart`, the Layer 10 and Layer 19 renderers and their goldens,
the Layer 11 pipeline, the CLI, the daśā arithmetic, `planetary_positions`, the
dependencies, or Panchanga Layers 16–18. No transit calculation function, transit model,
dedicated endpoint, planetary property, cache, storage or clock is introduced. **One additive
response key, `overlay`, produced by a presentation-only helper, is the only API addition**
(§6.2); it formats what the renderers already compute for one chart and is disclosed as such.

Throughout, **"Verified"** marks behaviour read from the source at `1905e86` (with file and
line), **"Proposed"** marks this design, and **"Probed"** marks numbers produced by the
scratch probes of §15 (run against the frozen geometry modules and the fixture data, outside
the repository; not repository tests). v0.3 corrects the four findings of the owner's review
of v0.2 (sha256 `4de898509342ee32…`): visibility and request ownership (§6.3–6.4),
transactional replacement (§6.5), marker geometry and its evidence (§5.4, §6.2, §15), and
stacked rungs with validation by layout (§6.2, §6.7).

Decisions taken by the owner for v0.2 (binding): natal black, transit orange with an
explicit textual marker; explicit Update after edits; presentation-only helper with its API
addition disclosed; marker plus complete panel for cells with no room; retrograde underline,
subject to browser clearance tests; IANA zone plus the returned offset; optional seconds;
natal regeneration waits for an explicit transit Update; no automatic clock or extra
calculation path.

---

## 1. Scope

### 1.1 In scope (v1)

* One "Show transits" On/Off toggle, off by default, with a transit date and time beside it
  and an Update button; the natal place and its IANA zone shown as the fixed transit
  location, with the returned UTC offset after a successful response.
* One ordinary chart request for the selected transit instant, made only by the explicit
  rule of §3.3; the completed result retained in page memory and reused by every later
  toggle and chart-style switch.
* The nine transit grahas drawn **by sign into the natal cells** of the North Indian and the
  South Indian documents (and both in "Both"), with degrees and retrograde marks, prefixed
  `T:` and in a second colour, with every natal node untouched.
* An HTML "Transits" panel under the charts naming the transit instant, the identification
  rule, and the complete placement list with per-style omissions.
* Invalidation, late-response, abort, failure, loading and fallback rules; keyboard and
  mobile behaviour; the validation plan of §10.

### 1.2 Out of scope (v1)

Aspect lines, conjunction or any interpretation, predictions, the transit Ascendant or
houses, relocated houses, a transit daśā display, additional chart systems, animation or
"now", saved records, storage of any kind, and any change to the natal form's defaults.

### 1.3 Reuse rules (binding on the implementation)

1. The transit chart is requested with the **same four-key body**, headers, fetch options and
   token as the natal chart (§2.1), answered by the same handler, the same
   `render_chart_and_dasha_at` call under `ENGINE_LOCK`, the same `serialize`. No new
   endpoint, no new request key, no server-side notion of "transit".
2. The page reads the transit instant's placements from the response's existing
   `planetary_positions` block (§2.3); the `overlay` block (§6.2) adds only presentation
   facts (degree text, underline flag, row coordinates) and is tested for consistency with
   `planetary_positions`.
3. The helper performs no astronomy, sees one chart at a time, and lives in the render
   package next to the geometry it reads; nothing enters or leaves the engine lock.

---

## 2. Verified source behaviour this design relies on

All references are to `1905e86`.

### 2.1 Request and sequencing (viewer.js)

* The body is exactly `{date, time, place_text, place_id}`, raw `.value` strings, built by
  `currentValues()` (587–594) and sent by `fetch("/api/chart", …)` with `method: "POST"`,
  `mode: "same-origin"`, `credentials: "omit"`, `cache: "no-store"`, `redirect: "error"`,
  `referrerPolicy: "no-referrer"`, headers `Content-Type: application/json; charset=utf-8`
  and `X-Viewer-Token` (711–724); the token comes from `<meta name="viewer-token">` (136–140).
* Sequencing uses `sequence`, `inFlight`, `cancelledSequence` (186–188): a new submit aborts
  any in-flight request (701–707); a response is applied only if `mine === sequence`
  (737–739); `echoMatches` (798–810) requires `request.submitted` to equal the four captured
  strings. `#cancel` aborts the in-flight natal request (1754–1759). `enterLoading` (657–668)
  sets `aria-busy`, `data-busy` and `inert` on `#results` and shows Cancel; `leaveLoading`
  (670–675) reverses it; a failed or cancelled natal request leaves `shown` as it was.
* `refreshStale()` (1718–1741) compares `currentValues()` with
  `shown.document.request.submitted`; a difference sets `data-stale="true"` on `#results`
  and shows the stale banner; it is called from the date/time `input` events (1761–1763),
  `onPlaceInput`, `selectSuggestion` and `applyDocument`.
* A chosen birthplace is stored as `placeField.value = suggestion.label` and
  `placeIdField.value = String(suggestion.geoname_id)` (381–396); editing the text clears
  the id. `String(…)` is therefore an accepted construct in `viewer.js`.
* `DATE_SYNTAX = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/`, `TIME_SYNTAX =
  /^[0-9]{2}:[0-9]{2}(:[0-9]{2})?$/` (118–119); a blank time is accepted and the server
  assumes noon (`transport.parse_request`, `ASSUMED_TIME = time(12, 0, 0)`).
* `applyDocument` (864–894) clones `#results-template`, **replaces the whole
  `#results-body` subtree**, sets `shown = {document, view}`, then `applyStyle(view)` and
  `refreshStale()`. Daśā expansion state lives only in the DOM; `applyStyle` only toggles
  `hidden` on the two chart blocks (1097–1138).
* `insertSvg` (1172–1219) parses with `DOMParser` as `image/svg+xml`, rejects
  `parsererror`, a non-SVG root, `script`, `foreignObject` and any `on*` attribute, adopts
  the root and sets inline `display/width/height/maxWidth/minWidth` on it.
* The page never reads `planetary_positions`, never mentions transits, and contains no
  `Date`, `Number(`, `parseFloat`, `innerHTML`, storage or `history` (forbidden by
  `tests/test_viewer_boundaries.py` `FORBIDDEN_JS_TEXT` 221–234 and `FORBIDDEN_STATE_TEXT`
  247–252); its header (7–14) states it "converts no transported value into a numeric
  type". `setTimeout` is used for the 150 ms suggestion debounce; `setInterval` is not.
* The only fetch targets are `/api/chart` and `/api/places`; `source.count("fetch(") == 2`
  is asserted (test_viewer_boundaries.py 1051).
* DOM order of the top-level page (viewer.html): the form section (`#birth-form` with
  `#generate`, `#cancel`), `#status`, `#alert`, then `fieldset#chart-style` (74–82), then
  `section#results` (84). Tab order therefore reaches the chart-style radios **before**
  anything placed between them and the results.

### 2.2 Server (server.py)

* `POST /api/chart`: Host, Origin/`Sec-Fetch-Site`, token, `Transfer-Encoding`,
  `Content-Length` (≤ `MAX_BODY_BYTES = 4096`), `Content-Type` and read-timeout gates
  (`_read_api_body`, 772–894); `transport.parse_request` requires exactly the four string
  keys (`PARSED_KEYS`, transport.py 177) and rejects `STALE_KEYS`; `_effective_input`
  (897–960) maps `place_id` + matching `place_text` to the GeoNames record through
  `OfflineLocationResolver.record(place_id)` and raises `TransportError` when the submitted
  text differs from the record's label.
* Under `ENGINE_LOCK` and nothing else: `render_chart_and_dasha_at(effective.request,
  effective.location, chart_config, transport.RENDERER_OPTIONS, transport.YEAR)` and
  `dasha_rows(...)` (648–656). After the lock, inside the same `try`:
  `render_south_indian_svg(result.d1, transport.SOUTH_INDIAN_RENDERER_OPTIONS)` and
  `transport.serialize(result, parsed, effective=effective, rows=rows, south_indian_svg=south)`
  (660–669).
* Error kinds (670–706): `place_selection_required` 400; `dasha_range` 400; `input` 400 for
  `TransportError`, `InvalidBirthDateError`, `InvalidBirthTimeError`,
  `InvalidPlaceQueryError`, `InvalidTimezoneError`, `NonexistentLocalTimeError` (DST gap),
  `AmbiguousLocalTimeError` (DST overlap); `place_not_found` 404; `resource` 500; anything
  else `unexpected` 500 — including, deliberately, the engine's bare `RuntimeError` for an
  instant outside ephemeris coverage (comment 643–645). Error documents are
  `{"schema", "error": {"kind", "message"}}` (transport.py 1182–1190).

### 2.3 Response document (transport.py)

* `SCHEMA = "vedic_chart.viewer/2"`; key order `schema, request, engine, location,
  effective, assumptions, birth, svg, timeline, birth_chain, rows, planetary_positions,
  south_indian_svg` — the last present only when the keyword is given (`serialize`,
  1099–1106, 1168–1175); the no-keyword document is pinned by the Layer 11/15 golden and
  the 13-key order by `tests/test_viewer_south_indian.py` `EXTENDED_KEYS` (57–71).
* `effective.place` carries `geoname_id` (int), `label`, `timezone_id`, …;
  `effective.time_assumed`, `effective.place_assumed`, `effective.source`
  (`"selected"`/`"default"`) (990–1027); `location.timezone_id` (974–987);
  `assumptions.any/time/place/labels` (1030–1051); `birth.offset` is the UTC offset string
  (`"+05:30"` in the Jalandhar golden) and `birth.zone` the IANA id (849–855).
  `normalized.place_label` equals `effective.label`, the record's `candidate_label`, which
  is the string the server requires as `place_text` for that `place_id`.
* `planetary_positions` (947–971): `schema "vedic_chart.planetary_positions/1"`, nine
  `planets` in `Graha` order, each with `key`, `name`, `kind` (`"planet"`/`"lunar_node"`),
  `sidereal_longitude` (repr string), `sign {index, number, name, english_name}`,
  `degrees_in_sign` (repr string), `house` (Whole Sign house **of that chart**),
  `is_retrograde` (bool), `speed_longitude`, `nakshatra`; and `ascendant`. There is **no
  D°MM′ text** in this block; the renderers produce it from `dms(0)`.

### 2.4 Renderers and geometry (what the overlay must fit around)

* Coordinates: both renderers map the unit chart to user units with `to_x(u) = margin +
  u·side`, `to_y(u) = chart_top + u·side`, `margin = 40`, `side = 1000`, `chart_top = 40`
  without a caption (north_indian.py 560–569; the viewer's options have `caption=False`).
  The viewBox is `0 0 1080 H`.
* North (`north_indian.py`, `north_indian_geometry.py`): one
  `g.house[data-house][data-rashi][data-layout]` per house in `REGIONS` order, `data-rashi`
  the 1-based rashi number; `text.numeral` at `region.numeral` shows the **rashi number**
  (sign), font `0.026`; entries are bare `text.abbr`, `text.deg`, `line.retro` with
  `data-graha`, start-anchored at `row_start_x(box.x0) = box.x0 + LEFT_INSET (0.01)`, rows
  at `row_baseline(top, i, f) = top + 0.75 f + i·1.45 f` (geometry 304–306); font from
  `SIZE_LADDER = (0.032, 0.030, 0.028, 0.026, 0.024, 0.022, 0.021)` by `select_size`
  (289–301: width gate `LEFT_INSET + 6.12 f ≤ width`, then the largest size with
  `capacity = ⌊height / 1.45 f⌋ ≥ count`, else the floor with `capacity − 1` shown and `+n`
  in the next row); kite boxes 0.23 × 0.22, triangle boxes 0.21 × 0.10 (`REGIONS`,
  124–137); side houses `SIDE_HOUSES = (3, 5, 9, 11)` are **stacked** (abbreviation row,
  degree row, inter-entry gap `0.40 f`, pitch `3.30 f`) in a box **centred on the numeral's
  y** against the outer edge (`side_box`, 407–424) whose admissibility is the corner test
  `width ≤ SIDE_EDGE_INTERCEPT − height/2` with `SIDE_EDGE_INTERCEPT = 0.25 − 0.015√2 −
  0.015`, `width ≤ 0.15`, `height ≤ 0.40` (428–438); the underline is `line.retro` at
  `baseline + 0.22 f`, stroke `0.08 f`; ink `#000000`, paper `#ffffff`.
* South (`south_indian.py`, `south_indian_geometry.py`): twelve
  `g.sign[data-rashi][data-house][data-lagna]` with `rect.cell`, `text.sign-label` (left),
  `text.house-label` (`H<n>`, end-anchored, right) on the label row (font 0.020, row 0.032),
  then `g.entry[data-graha]` groups; cells fixed by `CELL_BY_RASHI_INDEX`, cell side 0.25,
  entry box 0.230 × 0.198 below the label row; same ladder, pitch, `select_size` and
  overflow rule; `+n` at `row_baseline(box.y0, shown, f)` (651–657).
* `render/__init__.py` exports exactly four names (`test_only_four_names_are_public`);
  `PACKAGE_FILES` pins the module list; render modules may import only `dataclasses, math,
  re, xml.sax.saxutils, itertools` and `vedic_chart.representation.d1`,
  `…representation.dms`, `…vedic.grahas`; the viewer package may not import any render
  module except the two option classes (`transport.py`) and `render_south_indian_svg`
  (`server.py`).

---

## 3. User flow and controls (Proposed)

### 3.1 Controls

One native `fieldset#transit`, placed **after `#chart-style` and before `#results`**
(outside the form and the template), disabled until the first natal document arrives and
its `overlay` block validates (§6.7):

```
┌ Transits ───────────────────────────────────────────────────────────────────────┐
│ [ ] Show transits   Date [2026-10-08]  Time [14:30:00]  [Update]                 │
│ Local time at Jalandhar, Punjab, India — Asia/Kolkata (the natal birthplace)    │
│ Transits for 2026-10-08 14:30:00 Asia/Kolkata (UTC+05:30) shown.                │
└─────────────────────────────────────────────────────────────────────────────────┘
```

| element | id | notes |
|---|---|---|
| `fieldset.v-transit` | `transit` | `disabled` initially; `legend` "Transits" |
| `input type="checkbox"` | `transit-toggle` | label "Show transits"; **no `checked` attribute** (the script sets `checked = false` at start, as it sets the North radio) |
| `input type="date"` | `transit-date` | label "Transit date"; `autocomplete="off"` |
| `input type="time" step="1"` | `transit-time` | label "Transit time"; `autocomplete="off"`; seconds optional (`TIME_SYNTAX`) |
| `button type="button"` | `transit-update` | "Update"; **always visible and enabled while the fieldset is enabled** (§3.4); never hidden, never disabled by state |
| `p` | `transit-place` | "Local time at `<effective.place.label>` — `<location.timezone_id>` (the natal birthplace)" |
| `p role="status" tabindex="-1"` | `transit-status` | the status line (§6.6); mirrored to the existing `#status` live region by `announce()` |

No `name` attributes; the fieldset is outside `#birth-form`, so Generate never submits
transit values and Enter in a transit field does not submit the natal form (Enter in a
transit field activates Update through a `keydown` handler on the fieldset).

### 3.2 Keyboard order (corrected to the DOM)

Tab order: natal date → natal time → birthplace → Generate → (Cancel, when shown) →
**North Indian / South Indian / Both** radios (one tab stop, arrows move) → **Show
transits** → Transit date → Transit time → Update → results heading → … Space toggles the
checkbox; Enter on Update activates it. Every control has a `<label for>` or button text as
its accessible name.

### 3.3 Request rule (explicit Update; unchanged from v0.1 in principle)

Let *inputs* be `{date: transit-date.value, time: transit-time.value}`, *complete* mean both
match `DATE_SYNTAX`/`TIME_SYNTAX`, and *key* be `{natal: shown, date, time}` (the natal
`{document, view}` object identity plus the two strings; one record shape everywhere,
§6.4). A transit request is made in exactly two situations:

* **(a)** the toggle transitions off → on, inputs complete, `natalUsable()` (§6.4) true,
  the retained completed result does not match this key, and no request with this key is
  pending;
* **(b)** Update is activated while the toggle is on, inputs complete, `natalUsable()`
  true, and either the retained completed result does not match this key or the last
  attempt with this key **failed** (retry), and no request with this key is pending.

Showing is a separate matter from requesting: every show or re-show, from any event, goes
through the single predicate `overlayVisible()` of §6.4; nothing else ever reveals the
overlay. Restoring inputs that match the retained completed result while the toggle is on
re-shows it through that predicate with no request; restoring them while the toggle is off
shows nothing.

Everything else makes no request: keystrokes, segment edits, `change` events, chart-style
switches, repeated toggles, natal regeneration, Update with a retained matching result
(which re-shows it and announces "Transits for … already shown."), Update while the same key
is pending (announces "Calculating transits…"; no second request).

### 3.4 Focus

Update is never hidden or disabled while the fieldset is enabled, so focus can stay on it:
after a successful Update, focus stays on Update and the status line is announced; after a
failure, focus stays where it was and the status line is announced. Turning the toggle on
or off never moves focus. When the fieldset becomes disabled (§6.7 fallback, or a new natal
document replacing the results while the control held focus), focus moves to the
chart-style checked radio, as Layer 19 does when a focused block is hidden.

### 3.5 Flow

1. Generate a natal chart. The fieldset becomes enabled; `#transit-place` shows the natal
   place and zone; the toggle is off; no overlay.
2. Enter a transit date and time. Nothing is requested.
3. Turn Show transits on. With complete inputs, rule (a) makes one request; the natal
   results stay exactly as they are (no dimming, no `inert`); on success the overlay appears
   in every visible chart and the panel fills. With incomplete inputs: no request, status
   "Enter a transit date and time.", toggle stays on.
4. Turn it off: overlay and panel hidden at once; the result is retained. On again: shown
   again, no request.
5. Switch North / South / Both: no request, no rebuild (§6.5).
6. Edit a transit field while on: the overlay and panel are hidden **immediately**
   (`overlayVisible()` is false because the inputs no longer match the retained key), any
   pending request is aborted and its ownership invalidated, and the status says "Transit
   inputs changed — press Update to show transits for `<date> <time>`." Press Update: rule
   (b). Revert the edit to the retained result's inputs: `overlayVisible()` is true again and
   the overlay reappears with no request. With the toggle off, editing or reverting shows
   nothing.
7. Edit the **natal** form: the results go stale (verified banner); `overlayVisible()` is
   false, the overlay and panel are hidden immediately and the status says "Natal inputs
   changed — generate the natal chart first." Revert the natal form: the overlay reappears
   only if the toggle is on **and** the transit inputs still equal the retained key; if the
   transit inputs were changed in between, it stays hidden until Update.
8. Press Generate: on `enterLoading` any pending transit request is aborted; the overlay
   stays hidden. If the natal request fails or is cancelled, `shown` is unchanged and the
   stale rule decides (the overlay returns only when the form again equals the shown
   submission). If it succeeds, the results body is replaced; the retained transit result
   is discarded (it belonged to the previous natal object); the toggle keeps its state; if
   on, the status says "Press Update to show transits for the new natal chart." No
   automatic request (owner's decision).

---

## 4. Overlay semantics (Proposed)

* **Frame:** the natal document is the frame. Its Lagna, its `data-house`/`data-rashi`
  mapping and every natal node stay exactly as rendered; nothing from the second chart's
  `ascendant`, `house` numbers, `svg`, `south_indian_svg`, `rows`, `timeline` or
  `assumptions` is displayed.
* **Alignment by sign:** transit graha *g* with `planetary_positions.planets[g].sign.number
  = n` is drawn in the natal cell of sign *n*: in North, the `g.house` whose `data-rashi` is
  *n* (its `data-house` is the natal house of that sign); in South, the fixed cell of sign
  *n*. The cell coordinates come from the natal response's slot table (§6.2), keyed by
  rashi number, which the helper derived from the natal `D1Chart` by lookup
  (`houses[i].rashi_index`, as Layer 19's `_house_by_rashi`); the page never uses the
  transit response's `house` and never computes a house.
* **Nine grahas only**, in `Graha` order; the transit Ascendant is neither drawn nor listed.
* **Degrees:** the renderer's own `D°MM′` from `dms(0)` for the transit chart, delivered by
  the `overlay.entries` of the transit response; never computed in the page.
* **Retrograde:** underlined when `is_retrograde` and `kind !== "lunar_node"` (the rule the
  viewer's `mark_node_retrograde=False` gives natal entries), delivered as
  `entries[i].underline`.

---

## 5. Visual presentation (Proposed)

### 5.1 Identification: text first, colour second

| dataset | text | fill | identified in words |
|---|---|---|---|
| natal | unchanged, e.g. `Su 6°09′` | the renderer's ink `#000000` | panel: "Natal — black, no prefix" |
| transit | **`T:` prefix**, e.g. `T:Sa 16°45′` | `#c2410c` (orange; 5.18 : 1 on white, 4.06 : 1 against the natal black — computed WCAG ratios) | panel: "Transit — orange, prefixed T:" |

The prefix is part of the text content of every transit row (and of the `+n` marker:
`T:+2`), so the distinction survives grayscale, high-contrast modes and screen readers.
Italic is **not** used in v1: it adds nothing the prefix does not, and oblique glyphs would
need their own width allowance; with upright text the transit rows use the renderer's own
character advance (0.68 em) and the width accounting of §6.2 is exact to the renderer's
model. (D9 closed.)

### 5.2 Rows

A transit row is one `<text class="transit" x y font-size font-family fill="#c2410c"
text-anchor="start">` per entry, with the content `T:<abbr>` and, when degrees are shown,
a second `<text class="transit-deg">` at `deg_x` on the same baseline (inline cells), or a
second row (stacked cells) — mirroring the natal `abbr`/`deg` element pair; **every
coordinate is a string copied from the slot table** (§6.2). The retrograde mark is
`text-decoration="underline"` on the abbreviation `<text>` (D5, owner's decision), whose
rendered position is browser-determined (typically about 0.1 em below the baseline); the
browser clearance test (§10.7) verifies it stays inside the row's pitch and clear of the next
row and of natal elements.

### 5.3 Capacity rule in the page

Given *k* transit entries for a cell and the slot's `rungs` (largest font first; the floor
rung always last):

1. the first rung with `rows.length ≥ k` (inline) or `entries.length ≥ k` (stacked) shows
   all *k* at that font;
2. otherwise the floor rung with *r* = its row count: if *r* ≥ 2, show *r − 1* entries and
   the marker `T:+n` (n = k − (r − 1)) in row *r*; if *r* = 1, show no entry and `T:+k` in
   the one row; if *r* = 0, show nothing in the rows and draw the **cell marker** (§5.4)
   when the slot provides one, otherwise nothing in the cell at all ("panel only").

In every case the panel lists all *k* for that cell and says what each style omitted.
`rows.length`, `entries.length` and *k* are integers from JSON and DOM counts — the kind of
integer bookkeeping `viewer.js` already does (`sequence + 1`, row levels); no transported
value is converted.

### 5.4 Cell marker (no free row) — text marker, verified placement

The v0.2 ellipses are withdrawn. The owner's independent calculation, confirmed by the §15
probe (part A), gives 12.82 units of clearance after stroke for the North triangles and 13
for the South `H<n>` ellipse, both short of the 15-unit minimum. The probe establishes that
**the specified v0.2 ellipses fail**; it does not establish that every enclosing outline
would (the numeral centre is 35.36 units from a North triangle's slanted edges and the
two-digit numeral's glyph box reaches about 19.2 units along that direction, which leaves
little room, but no exhaustive search of shapes was made). The text marker below was chosen
because it needs no enclosure at all. v0.2's "none in the probe" was not evidence: that
probe checked no clearance.

The v0.3 marker is a **text** `T:+n` (the same marker as the in-row one; *n* = all transit
entries of that cell), **font 20 units** (D13, resolved by the owner: the auxiliary marker
uses the 20-unit label-font size; **planet-entry text keeps the 21-unit minimum**), transit
colour, **no stroke** — so its clearance is
measured on its glyph box (width `4 × 0.68 em` = 54.4, height `1 em` = 20) — placed by
the helper and accepted only when all of these hold:

* North: ≥ 15 units (`MIN_BOX_CLEARANCE`) from every edge of the cell polygon; ≥ 15 units
  from the **numeral's glyph box** (the enclosed label: the marker never touches or crosses
  the numeral, which it sits beside, not around); ≥ 15 units from every **natal text box**
  (unrelated natal text), the boxes being the renderer's own plan — inline cells: text
  from `x0 + 0.01` to `x0 + 0.01 + 6.12 f`, `natal_rows × 1.45 f` tall from the box top;
  stacked cells: the natal side box.
* South: inside the label row's inner box, right-aligned 9 units (`0.45 em` at the label
  font — the renderer's abbreviation–degree gap) before the house label's glyph box and
  ≥ 9 units after the sign label's glyph box. The label row is the South renderer's own
  padded band (10 units of cell padding), so this is its own spacing rule, not a relaxation
  of the North edge rule; the marker never enters the entry area.

Placement (North): kites 1, 7 and triangles 2, 6, 8, 12 — centred on the numeral's x, in
the middle of the gap between the natal text and the numeral glyph box (on the box side of
the numeral); kites 4, 10 — 45 units above the numeral and 45 units toward the box side,
where the kite is wider; side houses 3, 5, 9, 11 — 15 units below the natal side box,
left-aligned at the box's own x (`0.015 + 0.01` from the outer edge), or at the numeral's
y when the side house is empty.

Probed (§15 B): every North region with natal fills 0, 1, 2, 3 and 7 — 60 cases — accepts
the marker; the smallest clearances are 16.1 units to an edge (kites 4 and 10), 25.3 to the
numeral, 15.0 to natal text (side houses, by construction). South: 120 of the 144 sign ×
house-label combinations accept it; the 24 that do not are every cell of **Vrishabha**
(9 characters) and **Vrishchika** (10), whose label rows cannot hold the marker at the
required gaps — they get `marker: null`.

When a cell has no free row and `marker: null`, the page draws nothing in that cell and
the panel row says **"panel only — no room for marker"** (never "cell marked"); the status
line adds "Some transit entries appear in the panel only."

### 5.5 Transits panel (per style)

`section#transit-panel` under `.v-charts`, hidden with the overlay:

```
Transits — 2026-10-08 14:30:00 Asia/Kolkata (UTC+05:30) at Jalandhar, Punjab, India
Natal — black, no prefix.  Transit — orange, prefixed T:.  Underline = retrograde (not Ra/Ke).

 House  Sign (natal)  Transit planets                 North Indian        South Indian
   1    Meena         T:Sa 16°45′ ℞                   shown               shown
   5    Karka         T:Ma 11°41′, T:Ju 26°38′        T:+2 in row (0 shown)    shown
   6    Simha         T:Mo 22°49′, T:Ke 3°05′         shown                    shown
   7    Kanya         T:Su 20°52′                     shown                    shown
   8    Tula          T:Me 15°34′, T:Ve 13°45′ ℞      T:+2 marker (0 shown)    shown
  12    Kumbha        T:Ra 3°05′                      T:+1 marker (0 shown)    shown
```

(Probed data: Jalandhar natal, transit 2026-10-08 14:30:00 Asia/Kolkata; §5.7.) The table
lists every occupied natal house with its sign, the complete transit list in `Graha` order
with degree text and "℞" for underlined entries, and one column per style saying "shown",
"T:+n in row (k shown)", "T:+n marker (0 shown)" or "panel only — no room for marker"; in
North-only or South-only mode the other column is
still present (it describes the document the page holds), so switching styles never changes
the table. A line "Natal chart uses assumed birth details." follows the heading when
`assumptions.any`. The panel is plain HTML outside `#chart`, so the CSS rules stay as they
are.

### 5.6 Accessibility of the overlay

* Each natal `<svg>` root has `aria-labelledby="<prefix>-title"` and
  `aria-describedby="<prefix>-desc"` (verified). The overlay group carries one
  `<desc id="<prefix>-transit-desc">` ("Transit placements for 2026-10-08 14:30:00
  Asia/Kolkata: Sa 16°45′ retrograde in Meena (house 1); …"), and while the overlay is
  **shown** the page sets the root's `aria-describedby` to `"<prefix>-desc
  <prefix>-transit-desc"`; while **hidden** it restores `"<prefix>-desc"` and the group has
  `display="none"`, which removes it from the accessibility tree. These are the only two
  attributes of a natal node the page ever changes, and both are restored on hide and
  verified in §10.11. Ids are `d1-transit-desc` and `d1-south-transit-desc`; uniqueness is
  tested.
* `#chart-heading` and `#chart-south-heading` get `aria-describedby="transit-summary"`
  while shown (`#transit-summary` is the panel's first paragraph) and lose it when hidden.
* The panel is a `<table>` with `<caption>` and `<th scope>`; the status line is
  `role="status"`.

### 5.7 Worked example (Probed)

Natal: Jalandhar, 1995-03-21 06:45:00, Lagna Meena 9°47′ (the Layer 10 reference chart).
Natal placements: Su 6°09′ Meena (H1); Ke 13°47′ Mesha (H2); Ma 19°27′ ℞ Karka (H5); Mo
29°12′ and Ra 13°47′ Tula (H8); Ju 21°23′ Vrishchika (H9); Ve 27°39′ Makara (H11); Me
15°23′ and Sa 23°02′ Kumbha (H12). Transit instant 2026-10-08 14:30:00 Asia/Kolkata at the
same record (09:00 UTC), whose own Ascendant is Makara — a different frame, which the
overlay ignores: Su 20°52′ Kanya; Mo 22°49′ Simha; Me 15°34′ Tula; Ve 13°45′ ℞ Tula; Ma
11°41′ Karka; Ju 26°38′ Karka; Sa 16°45′ ℞ Meena; Ra 3°05′ Kumbha; Ke 3°05′ Simha.

Slot outcome per natal cell (North / South; §6.2 rules; probe values):

| sign | natal house | natal rows | North rungs (font : rows) | result North | South rungs | result South |
|---|---|---|---|---|---|---|
| Meena 12 | 1 (kite) | 2 (As, Su) | 28 : 3; 21 : 4 | T:Sa at 28 | 28 : 2; 24 : 3; 21 : 3 | T:Sa at 28 |
| Karka 4 | 5 (side) | 1 (Ma ℞) | 21 : 1 | `T:+2` in the one row | 28 : 3; 26 : 4; 21 : 4 | T:Ma, T:Ju at 28 |
| Simha 5 | 6 (triangle) | 0 | 26 : 2; 22 : 3; 21 : 3 | T:Mo, T:Ke at 26 | 28 : 4; … | both at 28 |
| Kanya 6 | 7 (kite) | 0 | 28 : 5; 24 : 6; 21 : 7 | T:Su at 28 | 28 : 4; … | T:Su at 28 |
| Tula 7 | 8 (triangle) | 2 (Mo, Ra) | 21 : 0 (floor, no rows) | `T:+2` text marker at (790.00, 889.74), 25.3 from the numeral | 28 : 2; 24 : 3; 21 : 3 | T:Me, T:Ve at 28 |
| Kumbha 11 | 12 (triangle) | 2 (Me, Sa) | 21 : 0 (floor, no rows) | `T:+1` text marker at (790.00, 196.66), 28.9 from the numeral | 28 : 2; 24 : 3; 21 : 3 | T:Ra at 28 |

The two styles differ exactly where the panel of §5.5 says so. North kites never exceed 28
for transit rows because `0.01 + 7.48 × 0.030 = 0.234 > 0.23` (the width gate with the
prefix); South cells likewise.

### 5.8 Mockups (from the worked example; `T:` rows are orange in the real document)

**North Indian** — natal Lagna Meena, so house 1 (top kite) holds sign 12. The diamond is
the Layer 10 geometry; only the cells that matter are lettered, rows are vertical in the
real document.

```
                          ┌───────── 12  (house 1) ──────────┐
                          │ As 9°47′                          │
                          │ Su 6°09′                          │
                          │ T:Sa 16°45′  (underlined)         │
        ┌── 1 (H2) ──┐    └───────────────────────────────────┘    ┌── 11 (H12) ──┐
        │ Ke 13°47′  │                                             │ Me 15°23′    │
        └────────────┘                                             │ Sa 23°02′      │
                                                                   │   T:+1   (11)  │ ← text marker
   ┌──  2 (H3) ──┐                                            ┌──  10 (H11) ──┐
   │ (empty)     │                                            │ Ve            │
   └─────────────┘                                            │ 27°39′        │
   ┌──  3 (H4) ──────┐                                        └───────────────┘
   │ (empty)         │              ─── natal frame ───         ┌──  9 (H10) ───┐
   └─────────────────┘                                          │ (empty)       │
   ┌──  4 (H5) ──┐                                              └───────────────┘
   │ Ma          │  (underlined)                             ┌──  8 (H9) ──┐
   │ 19°27′      │                                           │ Ju          │
   │ T:+2        │  ← one floor row: both transits in panel  │ 21°23′      │
   └─────────────┘                                           └─────────────┘
        ┌── 5 (H6) ──────┐   ┌──────── 6  (house 7) ─────────┐   ┌── 7 (H8) ─────┐
        │ T:Mo 22°49′    │   │ T:Su 20°52′                    │   │ Mo 29°12′      │
        │ T:Ke 3°05′     │   │                                │   │ Ra 13°47′      │
        │                │   │                                │   │   T:+2   (7)   │ ← text marker
        └────────────────┘   └────────────────────────────────┘   └────────────────┘
```

**South Indian** — cells fixed by sign; the Meena cell (top-left) carries the thick Lagna
border and `As`.

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ Meena   H1 ▌ │ Mesha    H2  │ Vrishabha H3 │ Mithuna   H4 │
│ As 9°47′     │ Ke 13°47′    │              │              │
│ Su 6°09′     │              │              │              │
│ T:Sa 16°45′  │              │              │              │
├──────────────┼──────────────┴──────────────┼──────────────┤
│ Kumbha  H12  │                             │ Karka     H5 │
│ Me 15°23′    │                             │ Ma 19°27′    │
│ Sa 23°02′    │                             │ T:Ma 11°41′  │
│ T:Ra 3°05′   │          D1 / Rashi         │ T:Ju 26°38′  │
├──────────────┤                             ├──────────────┤
│ Makara  H11  │                             │ Simha     H6 │
│ Ve 27°39′    │                             │ T:Mo 22°49′  │
│              │                             │ T:Ke 3°05′   │
├──────────────┼──────────────┬──────────────┼──────────────┤
│ Dhanu   H10  │ Vrishchika H9│ Tula      H8 │ Kanya     H7 │
│              │ Ju 21°23′    │ Mo 29°12′    │ T:Su 20°52′  │
│              │              │ Ra 13°47′    │              │
│              │              │ T:Me 15°34′  │              │
│              │              │ T:Ve 13°45′  │              │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

Both mockups, the §5.5 panel and the §5.7 table carry the same nine transit entries and the
same natal entries; the only per-style differences are the North omissions in Karka (`T:+2`
in its one floor row), Tula and Kumbha (text markers beside the numerals). No cell of this
example is "panel only".

### 5.9 Layout, mobile

The control is a flex row wrapping at narrow widths; at 375 px nothing overflows the page
(checked as Layer 19 checks the style control). The overlay lives inside the existing chart
wrappers, so the Layer 19 scroll hints and the 600–1080 px sizing apply unchanged; the panel
table sits in its own scrolling wrapper with a hint on narrow screens.

---

## 6. Architecture (Proposed)

### 6.1 Overview

```
natal Generate ──► POST /api/chart ──► document N (13 existing keys + overlay)
                                         page keeps shown = {document: N, view}
transit (a)/(b) ─► POST /api/chart ──► document T (same contract)
                                         page keeps transit = {key, planets, entries, …}
compose (page) ──► one <g class="transit"> per natal document, built in a detached
                   fragment from N.overlay.slots + T.overlay.entries + T.planetary_positions,
                   then appended atomically; HTML panel filled.
toggle / style ──► visibility only: display attribute on the groups, hidden on the panel.
```

### 6.2 The presentation helper and the `overlay` key (the one API addition)

**Why.** The page may not convert transported values to numbers or compute boundaries and
holds no geometry (§2.1, §2.4); empty natal cells have no element to copy from, side-house
boxes depend on the natal plan, and `D°MM′` text exists only through `dms(0)`. The helper
formats these presentation facts for **one** chart, deterministically and unit-testably, in
Python next to the geometry. It is not a transit API: it does not know whether a chart is
natal or transit, performs no astronomy, and the engine lock is untouched.

**Module** `src/vedic_chart/render/overlay.py` (new), fifth export of `vedic_chart.render`:

```python
def overlay_block(chart: D1Chart, *, show_degrees: bool = True,
                  mark_node_retrograde: bool = False) -> dict
```

Supported option profile: the viewer's — `show_degrees=True`, `mark_node_retrograde=False`,
`caption=False` (coordinates assume `chart_top = 40`), the default style numbers — is the
profile the server uses and the only one the viewer exercises. `show_degrees=False` is
**accepted and tested** (D12): inline rows carry `T:Su` only (width budget `4 × 0.68 =
2.72 em`, so every ladder font passes the gate — probed, §15 D), rungs omit `deg_x`, stacked
entries have `abbr_y` only and one line each (`side_rows_per_entry(False)`). `caption=True`
is **not** supported (the block would need `chart_top`); the helper has no caption parameter
and its coordinates are documented as "no-caption documents only". `ValueError` for a
non-`D1Chart` or non-bool flags.

**Schema** (coordinates are strings formatted by the renderers' `_number` rule — two
decimals — in absolute SVG user units including the 40-unit margin; counts are integers;
values below are **probed** for the Jalandhar natal chart, §5.7):

```json
"overlay": {
  "schema": "vedic_chart.overlay/1",
  "prefix": "T:",
  "font_family": "\"DejaVu Sans\", Arial, Helvetica, sans-serif",
  "marker_font_size": "20.00",
  "entries": [
    {"key": "sun", "abbr": "Su", "degree_text": "6°09′", "underline": false, "rashi_number": 12},
    … nine, in Graha order …
  ],
  "slots": {
    "north": {
      "12": {"house": 1, "layout": "inline", "natal_rows": 2,
             "rungs": [
               {"font_size": "28.00", "x": "435.00", "deg_x": "523.76",
                "rows": ["293.80", "334.40", "375.00"]},
               {"font_size": "21.00", "x": "435.00", "deg_x": "501.57",
                "rows": ["288.55", "319.00", "349.45", "379.90"]}],
             "marker": {"x": "540.00", "y": "376.66", "anchor": "middle"}},
      "4":  {"house": 5, "layout": "stacked", "natal_rows": 1,
             "rungs": [
               {"font_size": "21.00", "x": "65.00",
                "entries": [{"abbr_y": "860.55", "deg_y": "891.00"}],
                "overflow_y": "860.55"}],
             "marker": {"x": "65.00", "y": "866.40", "anchor": "start"}},
      "7":  {"house": 8, "layout": "inline", "natal_rows": 2,
             "rungs": [{"font_size": "21.00", "x": "695.00", "deg_x": "761.57", "rows": []}],
             "marker": {"x": "790.00", "y": "889.74", "anchor": "middle"}},
      "2":  {"house": 3, "layout": "stacked", "natal_rows": 0,
             "rungs": [
               {"font_size": "32.00", "x": "65.00", "entries": [{"abbr_y": "…", "deg_y": "…"}], "overflow_y": "…"},
               {"font_size": "28.00", "x": "65.00", "entries": [… 2 …], "overflow_y": "…"},
               {"font_size": "22.00", "x": "65.00", "entries": [… 3 …], "overflow_y": "…"},
               {"font_size": "21.00", "x": "65.00", "entries": [… 3 …], "overflow_y": "…"}],
             "marker": {"x": "65.00", "y": "…", "anchor": "start"}},
      … "1" … "12" …
    },
    "south": {
      "7":  {"house": 8, "layout": "inline", "natal_rows": 2,
             "rungs": [
               {"font_size": "28.00", "x": "560.00", "deg_x": "648.76", "rows": ["945.80", "986.40"]},
               {"font_size": "24.00", "x": "560.00", "deg_x": "636.08", "rows": ["942.80", "977.60", "1012.40"]},
               {"font_size": "21.00", "x": "560.00", "deg_x": "626.57", "rows": ["940.55", "971.00", "1001.45"]}],
             "marker": {"x": "…", "y": "…", "anchor": "end"}},
      "2":  {"house": 3, "layout": "inline", "natal_rows": 0, "rungs": [ … ],
             "marker": null},
      … "1" … "12" …
    }
  }
}
```

A stacked rung with no capacity is `{"font_size": "21.00", "x": "…", "entries": [],
"overflow_y": null}` (`overflow_y` is null exactly when `entries` is empty: there is no row
for a `T:+n`); an inline rung with no capacity is `{"font_size": "21.00", "x": "…",
"deg_x": "…", "rows": []}`. Both are the mandatory floor rung of a cell that holds nothing.

* `font_family` is the renderers' `font_family` string and `marker_font_size` the D13
  marker size, so the page copies them instead of holding presentation constants.
* `entries[i]` mirrors `planetary_positions.planets[i]`: same `key` order, `rashi_number ==
  planets[i].sign.number`, `underline == planets[i].is_retrograde and kind != "lunar_node"`
  (for `mark_node_retrograde=False`), `degree_text` equal to the string the North and South
  renderers put in that graha's `text.deg`/`text.degrees` for the same chart and options
  (pinned by parsing the SVGs in tests). `prefix` is the textual marker the page prepends.
* `slots.<style>` has **exactly** the keys `"1"`…`"12"`; `house` is the natal house of that
  sign from `D1Chart.houses` and is **identical between the two styles for every sign**
  (tested); `natal_rows` is the number of rows the natal renderer used in that cell
  (shown entries plus one when it overflowed; stacked cells count entries).
* **Geometry rules** (all with the renderers' own functions and constants):
  * *Transit width budgets.* Inline rows carry `T:` + the 9-character worst case
    `Me 29°59′` = 11 characters: `TRANSIT_WIDTH_EMS = 11 × 0.68 = 7.48`, gate
    `0.01 + 7.48 f ≤ box width`; the degree element sits at `deg_x = x + 3.17 f`
    (`T:Su` = 4 × 0.68 = 2.72 em slot + the 0.45 em gap). Stacked rows: the abbreviation
    row `T:Su` is 2.72 em and the degree row `29°59′` is the renderer's 4.08 em, so the side
    width budget is the renderer's own `side_width_budget` (4.08 em governs).
  * *Inline cells (kites, triangles, every South cell).* The natal rows occupy
    `[box.y0, box.y0 + natal_rows × 1.45 × f_natal)`; the natal underline
    (`baseline + 0.22 f + 0.04 f`) and the natal `+n` row lie inside that span, so the
    **remainder box** is `Box(box.x0, box.y0 + natal_rows × 1.45 f_natal, box.x1, box.y1)`
    so the first transit baseline is `0.70 f_natal + 0.75 f_t` below the last natal
    baseline and the transit glyph top is `0.70 f_natal` below it — `0.45 f_natal` clear of
    the natal descent (`0.25 f`) and `0.44 f_natal` clear of the natal underline bottom
    (`0.22 f + 0.04 f`): about 14 units in the probed house 1. For each ladder font passing the transit width
    gate, a rung lists `⌊remainder height / 1.45 f⌋` baselines `row_baseline(rem.y0, i, f)`;
    a rung whose row count equals the previous rung's is dropped **except the floor rung,
    which is always present** (D10; possibly with `rows: []`). An **empty natal cell** has
    the remainder equal to the box, i.e. the natal algorithm itself.
  * *Stacked cells (North side houses).* With `natal_rows = 0` the rungs follow the natal
    algorithm: for each ladder font, the largest *k* whose centred `side_box` is admissible,
    placed by `side_box`. Otherwise the transit box starts at `natal_box.y1 + 0.40 f` (the
    renderer's inter-entry gap) against the outer edge, and *k* grows while the **bottom
    inner corner** passes the renderer's corner rule generalised to an off-centre box:
    `width ≤ SIDE_EDGE_INTERCEPT − (bottom − numeral_y)` and `bottom ≤ numeral_y + 0.25 −
    OUTER_CLEARANCE`; `natal_box` is the natal plan's side box, which already includes the
    natal `+n` row when the natal cell overflowed. Each entry has `abbr_y`/`deg_y` from
    `side_abbr_baseline`/`side_deg_baseline`; `overflow_y` is the last entry's abbreviation
    baseline (the `T:+n` row replaces that entry) and null when `entries` is empty. Rungs
    with a repeated *k* are dropped except the floor, which is always present. Probed
    (§15 C, house 5): empty → 32 : 1, 28 : 2, 22 : 3, 21 : 3; one natal entry → 21 : 1;
    two, three, or four (natal overflow, `+2` shown) → the floor with no entry
    (`entries: []`, `overflow_y: null`) and the text marker fitting below the natal box in
    every case.
  * *Marker.* The text marker of §5.4: `{x, y, anchor}` is the baseline position and
    `text-anchor` of a `T:+n` text at font 20, or `null` when the §5.4 clearances cannot all
    be met. The helper evaluates the clearances with the geometry (edge distances through
    `distance_to_segment`, box gaps against the numeral glyph box and the natal plan boxes;
    South label-glyph gaps) for the cell's actual natal plan, so the result depends on the
    natal chart, as the rungs do.
* **Size.** The v0.2 probe measured 10.4 KB for both styles' slots of the Jalandhar chart
  plus about 0.8 KB of entries, before the floor-always-present rule and the text markers
  (a few hundred bytes more) — **an estimate until measured on the real server**.
  `south_indian_svg` is about the same size.

**Server:** after the South render, inside the same `try`:
`overlay = overlay_block(result.d1, show_degrees=transport.RENDERER_OPTIONS.show_degrees,
mark_node_retrograde=transport.RENDERER_OPTIONS.mark_node_retrograde)`;
`transport.serialize(..., south_indian_svg=south, overlay=overlay)`. A failure is a 500
`unexpected`, as a South render failure is.

**Transport:** `serialize(..., south_indian_svg=None, overlay=None)` appends `overlay`
**after** `south_indian_svg` when given (a `dict`; otherwise `TypeError`). The no-keyword
document is unchanged; the Layer 11/15 golden and its legacy projection are unchanged; the
HTTP document gains one key, so the exact-order tests move from 13 to 14 keys (§9).

### 6.3 The transit request (page)

```js
var transitCaptured = {
  date: transitDateField.value,                       // complete by DATE_SYNTAX
  time: transitTimeField.value,                       // complete by TIME_SYNTAX
  place_text: shown.document.effective.place.label,   // the record's label (== normalized.place_label)
  place_id: String(shown.document.effective.place.geoname_id)
};
```

Identical fetch options and headers to the natal request (a third `fetch(`; the boundary
count becomes 3, §9), its own `AbortController` and `transitSequence`; the natal
`sequence`, `inFlight`, `cancelledSequence`, `enterLoading` and `#cancel` are not touched.
The server resolves `place_id` through the existing contract; because the natal place may
be the configured default (sent by the natal form as a blank `place_id`), the transit
request always sends the effective record id explicitly.

**Acceptance of a transit response — all of, in order, evaluated in the `then` handler
before anything else; the `catch` and `finally` handlers apply the same ownership test
first:**

1. **ownership:** `transitPending !== null && transitPending.sequence === mine` (the
   request is still the one pending; an aborted, superseded or invalidated request fails
   here and its handlers return without touching state, status or busy state);
2. `transitPending.key.natal === shown` (the natal object has not been replaced);
3. **current-input equality:** `transitDateField.value === transitPending.key.date &&
   transitTimeField.value === transitPending.key.time` (belt and braces: edits already
   invalidate ownership in §6.4);
4. `natalUsable()` (§6.4);
5. `transitOn` — a response arriving with the toggle off is **discarded** (OFF during
   loading already aborted and disowned it; this catches a body that still arrives) and the
   toggle is never changed;
6. `echoMatches(document, transitPending.captured)`; `effective.time_assumed === false`;
   `effective.source === "selected"`;
7. the metadata validation of §6.7 on `document.overlay.entries` and
   `document.planetary_positions`;
8. composition succeeds (§6.5).

Failing 1–5 means "ignore silently" (no state change at all); failing 6–8 means "failure"
(§6.6) for the owned request. On acceptance the result becomes the one retained completed
result (§6.5) and `overlayVisible()` decides whether it is shown.

### 6.4 State, ownership and the single visibility predicate

```js
var transitOn = false;        // mirrors #transit-toggle.checked; a response never sets it
var transitSequence = 0;      // bumped by every request AND every invalidation
var transitPending = null;    // the ONE owned request, or null:
                              // {key: {natal, date, time}, captured: {date, time, place_text, place_id},
                              //  sequence, controller}
var transitResult = null;     // the ONE retained completed result, or null:
                              // {key: {natal, date, time}, planets, entries, offset,
                              //  groups: {north: <g>|null, south: <g>|null}, panelRows}
var transitFailure = null;    // {key, kind, message} of the last failed owned attempt
var overlayMeta = META_NONE;  // META_OK | META_MISSING | META_MALFORMED, from the natal document

function sameKey(a, b) { return a.natal === b.natal && a.date === b.date && a.time === b.time; }
function currentKey()  { return {natal: shown, date: transitDateField.value, time: transitTimeField.value}; }
function natalUsable() {
  return shown !== null && overlayMeta === META_OK && !natalLoading
      && !resultsRegion.hasAttribute("data-stale");
}
function overlayVisible() {             // THE predicate: every show/re-show path uses it
  return transitOn && natalUsable() && transitResult !== null
      && sameKey(transitResult.key, currentKey());
}
function syncOverlay() {                // called at the end of EVERY event handler below
  if (overlayVisible()) { showOverlay(transitResult); } else { hideOverlay(); }
}
function invalidatePending() {          // ownership first, then the fetch
  if (transitPending) { var p = transitPending; transitPending = null;
                        transitSequence = transitSequence + 1; p.controller.abort(); }
  leaveTransitBusy();
}
```

`showOverlay` and `hideOverlay` are idempotent visibility operations on
`transitResult.groups` and the panel (§6.5); they never build or request anything.

| event | effect, then `syncOverlay()` |
|---|---|
| toggle → on | `transitOn = true`; if `sameKey(transitResult.key, currentKey())` and `natalUsable()`: nothing more (the predicate shows it); else rule (a) may start a request. |
| toggle → off | `transitOn = false`; `invalidatePending()`; `transitResult` kept. |
| Update | rule (b); if `transitPending && sameKey(transitPending.key, currentKey())`: announce "Calculating transits…", nothing else. |
| transit field `input` | `invalidatePending()`; status per §6.6 (the predicate hides or re-shows by key equality alone). |
| natal form `input` (stale) | `invalidatePending()`; `transitResult` kept. |
| natal `enterLoading` | `natalLoading = true`; `invalidatePending()`. |
| natal failure or cancel | `natalLoading = false`; `shown` unchanged. |
| natal `applyDocument` | `natalLoading = false`; `invalidatePending()`; `transitResult = null`, `transitFailure = null` (they belonged to the previous natal object; their groups left with the replaced subtree); `overlayMeta` from the new document (§6.7); `#transit-place` refreshed; fieldset enabled iff `overlayMeta === META_OK`; if on: status "Press Update to show transits for the new natal chart." |
| chart-style change | nothing. |
| request start | `transitSequence = transitSequence + 1; transitPending = {key, captured, sequence: transitSequence, controller}`; `enterTransitBusy()`. |
| `then` (owned, accepted) | `transitPending = null`; commit (§6.5): `transitResult` replaced, `transitFailure = null`; `leaveTransitBusy()`. |
| `then` (owned, rejected 6–8) / `catch` (owned) | `transitPending = null`; `transitFailure = {key, …}`; `transitResult` **unchanged**; `leaveTransitBusy()`; status failure row. |
| `then`/`catch`/`finally` (not owned) | return; no state, status or busy change. |

`enterTransitBusy`/`leaveTransitBusy` set and clear `aria-busy` on `#transit` and the
"Calculating transits…" line; because only the owned request's handlers call
`leaveTransitBusy()`, an older request can neither clear a newer pending request nor remove
its busy state, and because every status write is guarded by ownership, an older request
cannot overwrite a newer one's status.

Duplicate prevention: a pending request whose key equals the requested key blocks a second
request. Retry: after a failure, Update with the same inputs is allowed by rule (b).

**Exactly one completed result is retained** — the most recently accepted one. There is no
cache of earlier instants: A → B keeps B only, and returning to A's inputs makes a new
request.

Required tests (§10.10): completed A → toggle off → edit or revert the transit inputs:
stays hidden (`transitOn` false); completed A → natal edit → change the transit inputs →
revert the natal form: A stays hidden (key mismatch), and reverting the transit inputs too
re-shows A without a request; completed A, on, edit then restore: re-shown with no request.

### 6.5 Composition and transactional replacement

On acceptance the page builds, in a **detached** `DocumentFragment`, one
`<g class="transit" data-transit-date data-transit-time data-transit-zone>` for the North
document and one for the South document when `southState === "present"`, each with its
`<desc id="<prefix>-transit-desc">` and the rows and marker of §5.2–5.4 placed from
`shown.document.overlay.slots.<style>`, plus the panel rows (§5.5). Only when every element
of both groups and every panel row has been created without error does the **commit**
happen, as one synchronous sequence:

1. if `transitResult` exists: remove its `groups.north` and `groups.south` from their roots
   (they are the only `g.transit` elements and carry the only `<prefix>-transit-desc` ids),
   restoring each root's `aria-describedby` to `"<prefix>-desc"`;
2. append the new groups as the last child of their `<svg>` roots (hidden,
   `display="none"`) and replace the panel's table body;
3. `transitResult = {key, planets, entries, offset, groups, panelRows}`.

Invariants (tested): at most one `g.transit` per `<svg>` root; `d1-transit-desc` and
`d1-south-transit-desc` each occur at most once in the page; every natal node is untouched
(DOM equality of the root's children minus the group, before and after A → B → C
replacements); the headings' and roots' `aria-describedby` reference only ids that exist.

A composition failure (any exception while building the fragment) **publishes nothing**:
the fragment is discarded, `transitResult` keeps the previous completed result and its
groups (still attached, shown or hidden by `overlayVisible()` — hidden, because its key
differs from the request that failed), `transitFailure` records the failure, and the status
says "Transit overlay could not be composed: `<reason>`". Reverting the inputs to the
previous result's key then re-shows it coherently.

Showing and hiding (`showOverlay`/`hideOverlay`) set `display="none"` on the groups and
`hidden` on the panel and swap the `aria-describedby` values of §5.6; nothing is rebuilt.
`applyStyle` keeps its Layer 19 body.

### 6.6 Status line and failure behaviour

| situation | overlay | toggle | `#transit-status` | panel |
|---|---|---|---|---|
| request in flight | hidden | on | "Calculating transits…" ; `aria-busy="true"` on `#transit` only | hidden |
| success | shown in every visible chart | on | "Transits for `<date> <time> <zone>` (UTC`<birth.offset>`) shown." | shown |
| Update with retained matching result | shown | on | "Transits for … already shown." | shown |
| toggle off | hidden | off | "Transits off." | hidden |
| late / superseded / discarded response | unchanged | unchanged | unchanged | unchanged |
| 400 `input` (bad date/time, DST gap or overlap) | none | on | "Transit time not accepted: `<message>`" | hidden |
| 400 `dasha_range` | none | on | "The server could not calculate a chart for this transit date: `<message>`" (the unchanged pipeline builds the daśā timeline, §11) | hidden |
| 500 `unexpected` (e.g. ephemeris range) / `resource` / network / non-JSON / echo mismatch / validation failure / composition failure | none | on | "Transits could not be calculated: `<message>`" (stale schema: the existing reload sentence) | hidden |
| inputs edited while on | hidden | on | "Transit inputs changed — press Update to show transits for `<date> <time>`." | hidden |
| natal form edited (stale) | hidden | unchanged | "Natal inputs changed — generate the natal chart first." | hidden |
| natal regenerated | removed | unchanged | if on: "Press Update to show transits for the new natal chart." | hidden |
| incomplete inputs at toggle-on or Update | none | on | "Enter a transit date and time." | hidden |
| metadata unavailable (§6.7) | none | off, fieldset disabled | "Transit overlay not available: `<reason>`" | hidden |
| success with a "panel only" cell | shown | on | the success line plus "Some transit entries appear in the panel only." | shown |

Failures never touch `#alert`, `#results`, the natal document or the daśā state; an old
overlay is never shown under a new selection; the status line always names the instant of
what is shown.

### 6.7 Response validation and graceful fallback

**Natal response (at `applyDocument`):** `document.overlay` must be an object with
`schema === "vedic_chart.overlay/1"`, `prefix` a non-empty string, `slots.north` and
`slots.south` objects whose key sets are exactly `"1"`…`"12"`, each slot with integer
`house` in 1…12, `layout` in `{"inline","stacked"}`, `natal_rows` an integer ≥ 0, `rungs` a
**non-empty** array whose last element has `font_size === "21.00"` (the floor) and whose
elements are validated **by layout**: an inline rung has `font_size`, `x`, `deg_x` (absent
only when the natal document was rendered without degrees — not the viewer's profile, so the
page requires it) and `rows` (an array, possibly empty, of coordinate strings); a stacked
rung has `font_size`, `x`, `entries` (an array, possibly empty, of `{abbr_y, deg_y}`
objects) and `overflow_y` (a coordinate string when `entries` is non-empty, `null` when it
is empty); every coordinate string matches `/^[0-9]+\.[0-9]{2}$/`; `marker` is `null` or
`{x, y, anchor}` with two coordinate strings and `anchor` in `{"start","middle","end"}`;
**`house` for each sign identical in `north` and `south`**, and the twelve houses a
permutation of 1…12. A valid crowded chart — full cells, empty rungs, null markers — is
**usable** and reaches the marker/panel-only fallback; only a malformed block disables the
control. On any failure the natal display is applied exactly as today, the transit fieldset
stays **disabled**, the toggle is set off, and `#transit-status` says "Transit overlay not
available: the server did not provide usable placement data (`<reason>`). Reload the page
or restart the viewer." The natal chart, daśā and everything else remain usable.

**Transit response (at acceptance):** `overlay.schema`, `prefix` equal to the natal's,
`entries` an array of nine objects with unique `key`s equal, in order, to
`planetary_positions.planets[i].key`, `abbr` a 2-character string, `degree_text` a string
matching `/^[0-9]{1,2}°[0-9]{2}′$/` when degrees are shown, `underline` a boolean, and
`rashi_number === planets[i].sign.number` for every *i*; `planetary_positions.schema ===
"vedic_chart.planetary_positions/1"`, `planets[i].sign.number` an integer in 1…12 and
`kind` a string. Any failure is reported as "Transits could not be calculated: the server's
placement data was not usable (`<reason>`)" and nothing is drawn or retained.

**Zone and offset:** `#transit-place` shows `location.timezone_id` from the natal document
from the start; the success line adds the transit response's `birth.offset` verbatim
("UTC+05:30"), which is the offset at the **transit** instant (DST-aware, from the
unchanged Layer 3 path); the page never derives an offset.

### 6.8 No storage, no clock

No `localStorage`, `sessionStorage`, cookies, `history`, `Date`, `setInterval`, server
cache or file; the transit date and time default to blank; there is no "now".

---

## 7. Data integrity rules (Proposed, tested in §10)

1. `shown.document` is never mutated; natal SVG nodes are never moved, re-styled or removed;
   the only natal-node attribute the page changes is each root's `aria-describedby`
   (restored on hide); one group is appended per document root.
2. The daśā table, birth details, assumption badges and labels, `#submitted-line`, the
   stale banner and expanded rows are not re-rendered by any transit activity.
3. A transit result is bound to `{natal identity, date, time}`; the overlay is visible only
   through `overlayVisible()` (§6.4), which requires the toggle on, usable metadata, the
   natal neither loading nor stale, and all three key members equal to the current
   selection.
4. A response whose request is no longer the owned pending request (aborted, superseded,
   invalidated, or the toggle went off) is dropped by its own handlers without touching
   state, status or busy state, and never changes the toggle.
5. The natal form's optional-time and default-place behaviour is untouched; the overlay view
   repeats "Natal chart uses assumed birth details." when `assumptions.any`.
6. All existing security gates apply unchanged to the transit request, which is
   indistinguishable from a natal request at the server.
7. Composition is atomic and replacement transactional: both groups and the panel are built
   before the previous result's groups are removed; a failure publishes nothing and keeps
   the previous completed result; exactly one completed result is retained.

---

## 8. Changed-file manifest (Proposed; nothing exists yet) — 19 paths

| # | path | change |
|---|---|---|
| 1 | `src/vedic_chart/render/overlay.py` | **new** presentation helper `overlay_block` (§6.2) |
| 2 | `src/vedic_chart/render/__init__.py` | export `overlay_block`; `__all__` five sorted names |
| 3 | `src/vedic_chart/viewer/transport.py` | `serialize(..., overlay=None)` appending `overlay` after `south_indian_svg` |
| 4 | `src/vedic_chart/viewer/server.py` | one import; one call after the South render; the keyword argument |
| 5 | `src/vedic_chart/viewer/static/viewer.html` | `fieldset#transit` (§3.1) after `#chart-style`; `section#transit-panel` in the results template after `#charts` |
| 6 | `src/vedic_chart/viewer/static/viewer.js` | transit state, request, validation, composition, visibility, messages (§6); hooks in `enterLoading`, `leaveLoading`, `applyDocument`, `refreshStale` |
| 7 | `src/vedic_chart/viewer/static/viewer.css` | `.v-transit*`, `.v-transit-panel*` rules (all `v-` classes; nothing inside `#chart`) |
| 8 | `tests/test_render_overlay.py` | **new**: block schema, entry/degree/underline parity with the renderers, slot geometry invariants, option profile, determinism, validation, goldens |
| 9 | `tests/fixtures/overlay/jalandhar.json` | **new** golden of the block (written with `RENDER_GOLDEN_UPDATE=1`) |
| 10 | `tests/fixtures/overlay/bharatpur.json` | **new** golden |
| 11 | `tests/test_viewer_transit_overlay.py` | **new**: server/transport integration, static-file rules for the control and panel, the JS state rules checkable statically |
| 12 | `tests/test_render_north_indian.py` | `PACKAGE_FILES`, five public names, import rules for `overlay.py` |
| 13 | `tests/test_viewer_boundaries.py` | amendments of §9 |
| 14 | `tests/test_viewer_transport.py` | extended-response test: 14 keys, `overlay` last |
| 15 | `tests/test_viewer_south_indian.py` | `EXTENDED_KEYS` 14; the after-lock sequence test |
| 16 | `tests/render_helpers.py` | overlay cases (full kite, full triangle, one- and two-entry side houses, a transit instant with a different Lagna) |
| 17 | `tools/viewer/acceptance.py` | the checks of §10.9–10.12; `year_implicit` amended for the second fieldset and the checkbox |
| 18 | `docs/LAYER20_TRANSIT_OVERLAY_SPEC.md` | this document |
| 19 | `README.md` | one subsection under "Interactive viewer" (added at promotion, §16.8) |

**Not touched:** `north_indian.py`, `north_indian_geometry.py`, `south_indian.py`,
`south_indian_geometry.py`, all sixteen SVG goldens, `tests/fixtures/viewer/*.json`,
`app/*`, `cli.py`, `representation/*`, the calculation packages, `dasha/*`, `panchanga/*`,
`pyproject.toml`, deployment files.

---

## 9. Boundary-test amendments (Proposed, each narrow)

* `test_viewer_boundaries.py`: `source.count("fetch(") == 2` → `== 3`, target set
  unchanged; "style control immediately before `#results`" → the sequence `#chart-style`,
  `#transit`, `#results`; `LAYER19_TEMPLATE_IDS` extended by the panel ids;
  `"checked" not in source` kept; new rules `"setInterval" not in source` and the exact
  strings `'var transitOn = false;'` and `'transitToggle.checked = false;'` present; CSS
  checks extended with the `v-transit` selectors, the no-selector-inside-`#chart` rule
  unchanged; the server allow-list gains `overlay_block`; the "exactly one `with
  ENGINE_LOCK` whose body calls exactly two names" rule unchanged.
* `test_viewer_transport.py` / `test_viewer_south_indian.py`: 13 → 14 keys; "South render
  immediately after the lock, inside the try" → "South render, then `overlay_block`,
  inside the try"; one pipeline call per request unchanged.
* `test_render_north_indian.py`: `PACKAGE_FILES` + `overlay.py`; five public names; the
  relative-import rule for `overlay.py` = `["north_indian_geometry",
  "south_indian_geometry"]` and no import of `north_indian`/`south_indian`.
* `tools/viewer/acceptance.py` `year_implicit`: `other_fieldsets` 0 → 1 (`#transit`); the
  checkbox counted and named.

---

## 10. Validation plan (Proposed; none of it has been run)

1. **Ordinary path reuse.** AST tests: `server.py` has no route, key, branch or string
   containing "transit"; the parser accepts exactly `PARSED_KEYS`; `pipeline.py` unchanged
   by hash; a request with the transit body shape is handled by `_api_chart` with one
   `render_chart_and_dasha_at` call (counting wrapper, as Layer 19).
2. **Transit = ordinary.** For Jalandhar's record and `{2026-10-08, 14:30:00}`, the
   document returned for the transit-shaped request is byte-equal to the document for the
   same four strings submitted as a natal request.
3. **Natal instant.** Requesting the natal instant as the transit instant gives
   `planetary_positions.planets` and `overlay.entries` equal between the two responses.
4. **Sign placement into the natal frame.** `test_render_overlay.py`: for twelve synthetic
   Lagnas, the slot of sign *n* has `house` equal to the `number` of the `D1House` whose
   `rashi_number` is *n*, identical in both styles; every rung row's text box (from the
   transit width budget and the font) lies inside the cell polygon/rect with
   `MIN_BOX_CLEARANCE` and intersects no natal text box or underline box of the natal
   document at the same options (boxes computed with the geometry; the natal boxes
   cross-checked against the parsed SVG attributes); every non-null marker satisfies the
   §5.4 clearances (edges, numeral glyph box, natal boxes; South label gaps), measured on
   the marker's glyph box; `marker` is null for every Vrishabha and Vrishchika South cell
   and non-null for every North cell of the §15 B fills. Acceptance: with the §5.7 transit
   (Ascendant Makara vs natal Meena), every transit `<text>` for sign *n* lies inside the
   natal cell of `data-rashi="n"` by `getScreenCTM` bounds, never in the transit chart's
   own house cell.
5. **Boundaries, retrograde, nodes.** Entries at 0°00′ and 29°59′ of a sign land in the
   right cell; `underline` true for a retrograde planet, false for Rahu/Ketu, matching the
   renderer's `line.retro` presence in the same chart's SVG; `degree_text` equal to the
   SVG's `text.deg` content for all nine grahas of both reference charts.
6. **Errors, no fallback.** Server tests: DST-gap and ambiguous transit times → 400
   `input`; a bad calendar date → 400 `input`; an instant outside coverage → 500
   `unexpected` (existing); the page's static rule that a blank transit time is never sent;
   acceptance: `time_assumed` false on every transit response and each error in
   `#transit-status` with nothing drawn.
7. **Crowded cells and clearance.** Synthetic natal charts (labelled synthetic) with 0, 1,
   2 entries in a triangle, **0, 1, 2, 3 and 4 (overflowing)** in a side house, 0, 2, 7 in
   a kite and 0, 2, 4, 6 in a South cell, combined with transit sets of 1, 2, 4 and 9 in
   that sign: rung rows equal the geometry's capacities (the §5.7 table and the §15 C
   figures are the expected outputs); the floor rung is present in every cell, empty where
   nothing fits, with `overflow_y` null exactly then; the page shows exactly the §5.3 rule,
   reaching the marker and the "panel only" fallback; the panel lists all; browser check at
   600 px: no transit text box overlaps a natal box, the `text-decoration` underline of a
   transit row stays within its row pitch (bounding boxes via `getScreenCTM`), **no
   planet-entry text below 21 units (11.67 px at 600 px) — the auxiliary `T:+n` cell marker
   is 20 units (11.11 px) by D13 and is the only transit text below the entry floor**, the
   `T:` prefix rows fit their cell at every rung used, and every drawn text marker's bounding
   box keeps the §5.4 distances. Geometry is verified on the **final** coordinates after
   string formatting: polygon containment of every transit text box and marker box (point-in-
   polygon on the formatted values, not only edge distance) in the Python tests, and actual
   browser text bounds (`getBBox`/`getScreenCTM`) at the 600 px minimum chart width in the
   acceptance checks; the scratch probe's glyph boxes are model evidence, not proof of browser
   rendering.
8. **Unchanged natal-only output and transactional replacement.** The sixteen SVG goldens
   and `tests/fixtures/viewer/*.json` byte-identical; the no-keyword `serialize` document
   unchanged; `svg` and `south_indian_svg` strings unchanged in the extended document;
   overlay hidden → the natal `<svg>` root's children minus the appended group equal the
   standalone document (DOM equality), `aria-describedby` restored, and pixels equal
   natal-only (environment qualification as Layer 19 §13.4). Acceptance A → B → C: after
   each accepted replacement exactly one `g.transit` per root, one `d1-transit-desc` and one
   `d1-south-transit-desc` in the page, every `aria-describedby` reference resolvable, the
   natal children unchanged. A malformed `entries` payload is rejected by metadata
   validation (§6.7) and therefore cannot demonstrate a composition failure; instead the
   acceptance check injects an exception **after validation**, while the second detached
   group or the panel is being built (through the page's `#acceptance` seam, a hook
   `window.__transitComposeFault = "south" | "panel"` consulted only by the composition
   function), for request B after a completed A: A's groups remain attached and hidden, no
   partial group is attached to any root, the failure is reported in the status line, the
   busy state clears, and restoring A's inputs shows A's overlay — and A's success status
   text — with no request. Request ownership is kept until the throwable preparation has
   been handled: the ownership guard runs first and the composition `try/catch` runs inside
   the owned branch, so the current request's own composition error is reported, never
   swallowed.
9. **Request counts.** Acceptance: natal Generate 1; toggle on with inputs → 2; off/on ×5
   → 2; North/South/Both ×6 → 2; Update unchanged → 2; edit then Update → 3; revert to the
   shown pair → 3 and the overlay reappears; Update while pending → no extra request.
10. **Races and transitions** (route interception with held responses; after every step
    the overlay's visibility equals `overlayVisible()` evaluated by the test from the DOM
    state):
    * edit during loading: request A held; edit the date; A released → **not applied**
      (ownership lost), overlay absent, status says inputs changed, `aria-busy` cleared by
      the edit, not by A; Update → request B; B applied;
    * off → on race: A held; toggle off (A disowned and aborted); toggle on → request B
      starts; A's body released → ignored: B remains pending with its busy state and status
      intact; B released → applied;
    * edit → restore race: A held for inputs X; edit to Y (A disowned); restore X → no
      request and nothing shown (no completed result); A's body released → ignored; Update
      → request C; C applied;
    * toggle off during loading: A aborted, a copy of A's body released → nothing drawn,
      toggle still off;
    * natal edit during loading: A aborted; natal reverted → no overlay (A was discarded);
      Update → one request;
    * natal Generate during loading: A aborted; natal success → fieldset refreshed,
      `transitResult` null, status "Press Update …"; natal failure (injected 500) and
      cancel → `shown` unchanged, overlay hidden while stale, re-shown when the form is
      reverted only if the transit inputs still match;
    * completed A → off → edit and revert the transit inputs → stays hidden; completed A →
      natal edit → change transit inputs → revert natal → A hidden; revert transit inputs →
      A shown, no request;
    * rapid edits: twenty `input` events → zero requests;
    * duplicate: Update twice quickly → one request;
    * retry: injected 500 then Update with the same inputs → a second request.
11. **Preserved natal state and accessibility.** Expand three daśā rows and the birth chain,
    then toggle and switch styles: `aria-expanded`, roving row, badges, `#assumption-labels`,
    `#submitted-line`, `data-stale` identical; the accessibility tree shows the root's
    description including the transit desc while shown and excluding it while hidden; the
    hidden group is absent from the tree.
12. **Browser matrix.** Jammu (full database) and Jalandhar (fixture): North, South, Both at
    1280 and 375 px with the overlay on; the keyboard path of §3.2; the accessibility tree
    holds the checkbox "Show transits", the two fields and the button; with
    `filter: grayscale(1)` injected, transit entries remain identifiable by the `T:` prefix
    and the panel; screenshots `transit_{place}_{style}_{width}.png`.

Environment labelling as in Layer 19 §13: cloud sandbox, session VM and native results
reported separately; nothing claimed for an environment not run.

---

## 11. Limitations (v1)

* The unchanged pipeline computes the transit instant's daśā timeline and two SVG documents
  that the page discards; a transit date whose cycle is outside the daśā range fails with
  `dasha_range` although no daśā is shown.
* The transit location is the natal effective place.
* An instant outside ephemeris coverage is a 500 `unexpected` (existing behaviour).
* North side houses (3, 5, 9, 11) have little room: with one natal entry one floor row,
  with two or more none; transits there often appear as a `T:+n` row or text marker and are
  read from the panel. Triangles with two natal rows hold no transit row. South cells with
  four or more natal rows hold none, and the Vrishabha and Vrishchika cells cannot carry the
  text marker ("panel only — no room for marker").
* Transit rows use `text-decoration` for retrograde (browser-rendered) rather than the
  renderer's drawn line.
* The auxiliary `T:+n` cell marker is 20-unit text (D13), below the 21-unit floor that
  planet-entry text keeps.
* Both mode holds two overlay groups built once per result.
* The response grows by the `overlay` block — about 11 KB per the probe, an estimate until
  measured.
* `overlay` coordinates are valid for no-caption documents only (the viewer's profile).

---

## 12. Decisions

Resolved by the owner (v0.2): D1 natal black / transit orange with `T:`; D2 explicit
Update; D3 degree text through the disclosed `overlay` block; D4 marker plus panel; D5
underline subject to clearance tests; D6 IANA zone plus returned offset; D7 optional
seconds; D8 natal regeneration waits for Update; D9 closed as "prefix, no italic" (§5.1).

Adopted in v0.3 on the owner's recommendation: **D10** capacity-distinct rungs with the
floor always retained; **D11** the South marker anchored beside the `H<n>` label only where
the corrected geometry verifies it fits (120 of 144 combinations; null otherwise); **D12**
`show_degrees=False` accepted and tested in the helper with the `T:`-prefixed budgets, the
viewer's profile unchanged. The ellipse markers of v0.2 are withdrawn in favour of the
verified text marker (§5.4).

Resolved by the owner at implementation: **D13** — the auxiliary `T:+n` cell marker uses
20-unit text; planet-entry text retains the 21-unit minimum; every statement of the floor
distinguishes the two (§5.4, §10.7, §11).

---

## 13. Alternatives considered (unchanged from v0.1)

Server-side combined document (the server never holds both charts; a natal instant in the
transit request would change the request structure); overlay-ready natal variant (doubles
payload and render work, swaps the natal document); page-only composition from SVG scraping
(fails for empty cells and side houses, moves geometry into JS). All excluded.

---

## 14. Change log

### v1.0 (2026-10-11; promotion, documentation only)

Status promoted to SPECIFICATION v1.0. §16.2 gains the owner's second native targeted
result (902 `test_render_overlay.py` cases after the helper correction), kept separate from
the 1,440-test run, with both labelled as targeted verification; §16.6 rewritten as "not run,
and not claimed"; §16.8 added; the README subsection added (manifest 19 paths). The draft
history, the corrected house-label width model (§16.4, §16.7), the synthetic browser evidence
(§16.7), the overflow behaviour (§5.3–5.5) and the limitations (§11) are preserved unchanged.

### Implementation corrections (2026-10-09; applied to v0.3 before building)

D13 resolved: 20-unit text for the auxiliary `T:+n` cell marker, 21-unit minimum retained
for planet-entry text, every floor statement distinguishing the two (§5.4, §10.7, §11). The
withdrawn-ellipse explanation qualified: the probe shows the specified v0.2 ellipses fail,
not that every outline must (§5.4). The composition-failure test now injects an exception
after validation while building the second group or the panel, and checks the previous
result, busy state, ownership and status restoration (§10.8). Geometry verification uses the
final formatted coordinates with polygon containment, and browser text bounds at the minimum
width; the probe's glyph boxes are model evidence only (§10.7). The block gains
`font_family` and `marker_font_size` (§6.2).

### v0.3 (2026-10-09) — corrections after the owner's review of v0.2 (`4de89850…`)

1. *Visibility and request ownership.* One predicate, `overlayVisible()` (toggle on, usable
   metadata, natal neither loading nor stale, retained result's natal identity, date and
   time all equal to the current selection), used by every show/re-show path; one pending
   record shape `{key: {natal, date, time}, captured, sequence, controller}` read
   consistently; `invalidatePending()` disowns before it aborts; `then`/`catch`/`finally`
   guarded by ownership so an older request cannot clear, overwrite or un-busy a newer one;
   the transit-input and natal-revert rows corrected; off → on and edit → restore races and
   the three required visibility tests added (§3.3, §6.3, §6.4, §10.10).
2. *Transactional replacement.* Build both groups and the panel first, then remove the
   previous owned groups and replace the panel; one `g.transit` per root and one of each
   description id; composition failure publishes nothing and keeps the previous completed
   result; exactly one completed result retained, no cache; A → B → C, failed B, unique ids,
   accessibility references and natal-content tests added (§6.5, §7, §10.8).
3. *Marker geometry and evidence.* v0.2's ellipses withdrawn (12.82 / 13 units after
   stroke, confirmed); "none in the probe" withdrawn as evidence; a text `T:+n` marker with
   glyph-box clearances (15 units in North from edges, numeral and natal text; the label-row
   gaps in South) verified for all 60 North fills and 120 of 144 South combinations;
   `marker: null` with "panel only — no room for marker" for the rest; the worked example,
   panel, mockups and acceptance expectations reconciled (§5.4, §5.5, §5.7, §5.8, §6.2,
   §10.4, §10.7, §15).
4. *Stacked rungs and validation.* Separate inline and stacked rung shapes; the floor rung
   always present, with the explicit zero-capacity forms (`rows: []`; `entries: []` with
   `overflow_y: null`); validation by layout; empty, one-, two-, three-entry and
   overflowing side cells probed and required in tests; crowded charts remain usable
   (§6.2, §6.7, §10.7).
5. Decisions D10–D12 adopted as recommended; D13 opened.

### v0.2 (2026-10-09) — corrections after the owner's review of v0.1

1. *Input edits and stale responses.* Acceptance now requires current-input equality
   (§6.3 item 3) in addition to sequence and natal identity; edits abort and invalidate a
   pending request immediately (§6.4); natal form edits (stale), natal `enterLoading`,
   natal failure and cancel are handled explicitly with the `overlayAllowed` predicate;
   tests §10.10 added for each case.
2. *Toggle-off and cancellation.* One rule: OFF with a completed result retains and hides;
   OFF during loading aborts, invalidates and discards any late response; ON reuses a
   matching completed result or makes one request. Retry after failure and duplicate
   prevention specified (§3.3, §6.4). The v0.1 "retained but not shown" rule for responses
   arriving while off is withdrawn.
3. *Placement made implementable.* Server-supplied per-row baseline strings (inline
   `rows[]`, stacked `entries[{abbr_y, deg_y}]`, `overflow_y`), absolute coordinates with
   the 40-unit margin, exact remainder-box and side-house rules, empty-cell rule, zero- and
   one-row behaviour, the width budgets with the prefix, the supported option profile; the
   `dy="1.45em"` construction is withdrawn.
4. *Identification and panel.* `T:` prefix as the primary marker; italic dropped; overflow
   per style with per-style panel columns; North marker described as the **sign** numeral;
   accessible association through the roots' `aria-describedby` and the headings, with the
   hidden state tested.
5. *Controls and focus.* Keyboard order corrected to the DOM (chart-style radios precede
   the transit fieldset); Update always visible and enabled, so focus never rests on a
   hidden element.
6. *Validation and fallback.* §6.7 defines the natal- and transit-side checks (unique keys,
   consistency with `planetary_positions`, complete `"1"`…`"12"` slot maps, identical house
   mapping across styles), the disabled-control fallback and atomic composition; IANA zone
   plus `birth.offset` on success; optional seconds; DST errors unchanged.
7. *Examples and inventory.* The worked example and both mockups now come from the probed
   Jalandhar chart and a real transit instant with a different Ascendant; the slot tables
   agree on every house; the panel, occurrences and per-style omissions are consistent; the
   manifest lists 19 paths; the size figure is marked an estimate.

### v0.1 (2026-10-08)

First draft, for review.

---

## 15. Drafting probes (scratch; outside the repository)

Two scratch scripts, kept under `Claude outputs/l20/` on the owner's machine and not
repository files, were run in the cloud sandbox against the frozen geometry modules, the
renderers' private planning functions, the fixture geodata and the bundled ephemeris. They
are the source of every number marked "Probed"; they are not tests, were not run on the
owner's machine, and will be superseded by `test_render_overlay.py` at implementation.

* `probe_slots.py` (v0.2): the Jalandhar natal chart and an ordinary chart for 2026-10-08
  14:30:00 at the same record through the unchanged `assemble_chart`/`build_d1_chart` path;
  the §5.7 placements, the inline rung values of §6.2 and the size figure. Its marker
  formulas were the v0.2 ellipses and it performed **no** clearance check; those outputs are
  withdrawn.
* `probe_v03.py` (v0.3), four parts, exercised exactly as follows:
  * **A** — the v0.2 ellipse against a 15-unit painted-outline clearance (720 outline
    samples per ellipse against the region edges, stroke 2): North kites 19.89 units after
    stroke (pass), all eight triangles 12.82 (fail), matching the owner's 12.816885; the
    South `H<n>` ellipse 14 units to the right cell edge before stroke, 13 after (fail) for
    every cell.
  * **B** — the v0.3 text marker rule of §5.4: every North region × natal fills {0, 1, 2,
    3, 7} entries in that house (60 cases; the empty fill from a nine-in-one-house chart,
    the others from `count_in_house_d1`), checking edge distance (`distance_to_segment` on
    the glyph box's corners and side midpoints), the gap to the numeral glyph box (two-digit
    worst case) and to the natal plan boxes: 60 of 60 accepted; minimum clearances 16.1
    (edge, kites 4/10), 25.3 (numeral), 15.0 (natal, side houses). South: all 12 sign names
    × 12 house labels with the 9-unit label gaps: 120 of 144 accepted; every Vrishabha and
    Vrishchika combination rejected.
  * **C** — stacked rungs for house 5 with natal 0, 1, 2, 3 and 4 entries (the last
    overflowing, `+2` shown): empty → rungs 32 : 1, 28 : 2, 22 : 3, 21 : 3 (floor kept
    although equal to 22's capacity); one → 21 : 1; two, three, four → the floor alone with
    `entries: []`, `overflow_y: null`; the text marker accepted below the natal box in all
    five.
  * **D** — width gates with the `T:` prefix: with degrees (7.48 em) kites and South cells
    admit 28, 26, 24, 22, 21 and triangles 26, 24, 22, 21; without degrees (2.72 em) every
    ladder font passes everywhere.
  * **E** — the §5.7 example's North markers: Tula/house 8 at (790.00, 889.74), Kumbha/
    house 12 at (790.00, 196.66), both ≥ 25 units from numeral and natal text; Karka/house
    5 at (65.00, 866.40), 15.0 from the natal side box.

No race probe was run: §6.4 is specified from the verified page code and is to be tested by
§10.10. No repository test was run in this pass.

---

## 16. Implementation record (2026-10-09; reviewed and closed 2026-10-10; promoted 2026-10-11; nothing staged or committed at the time of writing)

Built by two Opus subagents (server side: helper, transport, server, render tests and
goldens; page side: control, state machine, composition, static tests, acceptance checks)
from this document with the §14 implementation corrections applied, reviewed by Fable.
Working copy: the 159 tracked files of `1905e86` (byte-equal to the owner's tree) in the
cloud sandbox (Linux x86_64, Python 3.13.16, pyswisseph 2.10.3.2, PyPI tzdata, Playwright
1.63.0 with Chromium 141.0.7390.37), plus the full `data/geodata.sqlite` (sha256
`8afad22bfa50fb2a…`, equal to the owner's copy, transferred in five parts for this pass).

### 16.1 Changed files (19 paths with `README.md`; SHA-256 prefixes of the delivered state)

| path | change | lines | sha256 |
|---|---|---|---|
| `src/vedic_chart/render/overlay.py` | new presentation helper `overlay_block` (§6.2); house-label width model corrected in the closing pass (§16.7) | 697 | `d13f84d99cc3ae7d` (first delivery `3b3cd249472edf3d`) |
| `src/vedic_chart/render/__init__.py` | fifth export; `__all__` five sorted names | 23 → 27 | `177cbb1ffa2ac7fd` (was `bb229132099cccdc`) |
| `src/vedic_chart/viewer/transport.py` | `serialize(..., overlay=None)` appending `overlay` after `south_indian_svg`; `TypeError` otherwise; no arithmetic | 1206 → 1219 | `332f79254a52bc97` (was `4b2c0937f6a38cb5`) |
| `src/vedic_chart/viewer/server.py` | one import; `overlay_block(result.d1, show_degrees=…, mark_node_retrograde=…)` after the South render inside the `try`; the keyword | 1209 → 1218 | `1e6ed0a96944a630` (was `5499a4569a872439`) |
| `src/vedic_chart/viewer/static/viewer.html` | `fieldset#transit` between `#chart-style` and `#results`; `section#transit-panel` after `#charts` in the template | 174 → 220 | `a3599ce7f59bdc31` (was `c0a6d537522fd652`) |
| `src/vedic_chart/viewer/static/viewer.js` | the transit state, request, validation, composition, visibility and messages of §6; hooks in `enterLoading`, `leaveLoading`, `applyDocument`, `refreshStale`; the `#acceptance`-gated fault seam | 1780 → 2910 | `19b1ae7ffcd9bba5` (was `e84e4431e8deda26`) |
| `src/vedic_chart/viewer/static/viewer.css` | `.v-transit*` and `.v-transit-panel*` only | 566 → 693 | `4fad7716559f7991` (was `02ac72137a89e779`) |
| `tests/test_render_overlay.py` | new, 32 test functions (902 cases); `house_label_box` added in the closing pass | 1086 | `a3d197113d3d68f4` (first delivery `6b15f75155b3aeb3`) |
| `tests/fixtures/overlay/jalandhar.json` | new golden of the block; regenerated once in the closing pass (§16.7) | 1137 | `304159b7000c5166` (first delivery `47ca430c023605e2`) |
| `tests/fixtures/overlay/bharatpur.json` | new golden; regenerated once in the closing pass | 1134 | `667e4b0622329d30` (first delivery `4ad19eda956c2fba`) |
| `tests/test_viewer_transit_overlay.py` | new, 20 test functions (59 cases) | 797 | `a645ce96087431ec` |
| `tests/test_render_north_indian.py` | `overlay` in the internal module list; five public names; import rules for `overlay.py` | 1110 → 1167 | `a69fbaaae56b30f0` (was `8db2f773f0479930`) |
| `tests/test_viewer_boundaries.py` | §9 amendments: `fetch(` count 3; `#chart-style`, `#transit`, `#results` order; template and panel ids; `setInterval` forbidden; the exact transit strings; `autocomplete="off"` count 5; `v-transit` CSS rules; server allow-list `overlay_block` | 1057 → 1143 | `8c1edbb3a1b6c242` (was `5b7701f1b1e5ca0e`) |
| `tests/test_viewer_transport.py` | extended response 14 keys, `overlay` last; `TypeError` and no-keyword-unchanged tests | 1463 → 1520 | `9c37ef692865c059` (was `ed5c0da2413bd928`) |
| `tests/test_viewer_south_indian.py` | `EXTENDED_KEYS` 14; after-lock sequence (South render, then `overlay_block`); the one-call test counts `overlay_block`; block equality and 500-on-failure tests | 523 → 616 | `01437ce3fe8f6f18` (was `46d577f03615f80c`) |
| `tests/render_helpers.py` | `overlay.py` in `PACKAGE_FILES`; `house_fill_d1`, `transit_jalandhar_d1`, `overlay_chart`, `OVERLAY_FILLS`, `OVERLAY_GOLDEN_DIR`; existing cases untouched | 450 → 510 | `3f19b32dbb78f673` (was `938dd491860136d6`) |
| `tools/viewer/acceptance.py` | eleven `transit_*` checks (the eleventh, `transit_synthetic_crowded_600`, from the closing pass); `year_implicit` counts `#transit` and its checkbox; `south_svg_bytes_equal_renderer` expects the last two keys `south_indian_svg, overlay`; `StylePage` gained optional `hash_fragment`/`init_script` | 6067 → 8366 | `ba7a5ba3b3dcc13d` (was `32794b609df0fc50`; first delivery `4224e45537834d30`) |
| `docs/LAYER20_TRANSIT_OVERLAY_SPEC.md` | this document (promoted 2026-10-11) | | (its own hash is in the promotion report) |
| `README.md` | one subsection "Transit overlay (Layer 20)" under "Interactive viewer", added at promotion | 1225 → 1284 | `70e13b0ab6712ca4` (was `8fac8c2ba10041c2`) |

`README.md` gained its subsection at promotion (§16.8). Not changed (verified by hash against
`1905e86`, 110 protected paths hashed before and after each build): `north_indian.py`
`0c4922462205…`, `north_indian_geometry.py` `d7b553261501…`, `south_indian.py`
`c8d7d3ceb619…`, `south_indian_geometry.py` `8fc0e50fbd5d…`, every file of `app`,
`astronomy`, `chart`, `dasha`, `ephemeris`, `inputs`, `lagna`, `location`, `panchanga`,
`representation`, `sidereal`, `time`, `vedic`, `pyproject.toml`, all sixteen SVG goldens,
`tests/fixtures/viewer/*.json`, `tests/fixtures/dasha/*`, `test_app_boundaries.py`,
`test_render_golden.py`, `test_render_south_golden.py`, `test_render_geometry.py`,
`test_render_south_geometry.py`. No existing golden regenerated; no existing assertion
relaxed; no dependency, clock, storage or transit calculation path.

### 16.2 Test results by environment

* **Cloud sandbox** (Linux x86_64, Python 3.13.16): full-suite **baseline at `1905e86`,
  measured before any change: 4541 passed, 12 failed**; **updated: 5515 passed, 12
  failed**; the twelve failure identities are identical (8 `test_dasha_from_chart`, 2
  `test_dasha_table` goldens, 2 `test_viewer_transport` goldens — the platform-pinned set).
  Targeted: `test_render_overlay.py` 902 passed; `test_viewer_transit_overlay.py` 59 passed;
  the ten render/viewer modules together 2333 passed (the two transport goldens excluded by
  their known failure in the full run only).
* **Session VM** (Linux aarch64, Python 3.10.12, the repository's `.venv`, run on the
  owner's tree after delivery): every one of the 42 test modules run in nine calls (the
  bridge shell's 45-second limit prevents one full-suite process; a background run is killed
  with the shell), **5527 passed, 0 failed** — the same 5527 tests the cloud collects
  (`--co` agrees on both), with `test_app_boundaries.py` counted once; this VM reproduces
  the twelve platform-pinned goldens that fail in the cloud. No VM **baseline** run was made
  at `1905e86` (the owner's tree already held the Layer 20 files), so the VM figure is an
  updated-tree result without a same-environment baseline; the Layer 19 VM targeted runs
  are the nearest prior reference.
* **Native macOS** (owner's independent run, Darwin arm64, Python 3.11.16, reported
  2026-10-10): **1,440 targeted tests passed** across `test_render_overlay`,
  `test_viewer_transit_overlay`, `test_viewer_boundaries`, `test_render_north_indian` and
  `test_viewer_south_indian`. **This is targeted verification only** — not a full-suite run
  and not a browser run; it predates the closing-pass change to `overlay.py` and its goldens
  (§16.7), whose 902 overlay cases were re-run in the cloud and the session VM after that
  change.
* **Native macOS, after the helper correction** (owner's independent run, Darwin arm64,
  Python 3.11.16, reported 2026-10-11): **all 902 tests of `test_render_overlay.py` passed**
  against the corrected `overlay.py` and the regenerated Layer 20 goldens. This is a separate
  result from the 1,440-test run above and, like it, **targeted verification only**: neither
  is a native browser acceptance run and neither is a native full-suite run.
* **Cloud sandbox, after the closing pass:** full suite again 5515 passed, 12 failed, the
  same twelve identities.

### 16.3 Browser acceptance (cloud sandbox, headless Chromium 141 through Playwright)

Two runs of `tools/viewer/acceptance.py` (`--chromium` as Layer 19): against the fixture
database with `--default-place-id 1268782` — **61 passed, 0 failed, 1 skipped**
(`reference_jammu_365256363`, no Jammu record; the pre-change baseline of this run was
51 / 0 / 1, the ten new `transit_*` checks being the difference) — and against the **full
database** with the Jammu default — **62 passed, 0 failed, 0 skipped**, the first run of
the **Layer 20 version** of this script against the full database (earlier layers already had
production-database acceptance runs: the Layer 14/15 runs recorded in their specifications
and the Layer 19 native review of 2026-10-08). Evidence under
`Claude outputs/l20_acceptance/{fixture,full}/` (`report.json`, screenshots, responses).
Transit instant for every check: 2026-10-08 14:30:00 at the natal place.

* `transit_control_default`: toggle unchecked, fieldset disabled before the first
  document, enabled after; `#transit-place` shows the natal label and `Asia/Kolkata`.
* `transit_metadata_fallback`: a response with `overlay` deleted / malformed (route
  interception) leaves the natal display usable, the fieldset disabled and the status
  explaining; a valid document re-enables it.
* `transit_sign_placement`: every transit `<text>` lies inside the natal cell of its own
  sign by `getScreenCTM` bounds in both styles; both transit charts have Lagna Makara against
  natal Meena (Jalandhar) and Mesha (Jammu), so house-based placement would have differed.
* `transit_text_bounds_600` (600 px chart, CTM scale 0.5555): smallest planet-entry font
  21 units = 11.6665 px (North); the `T:+n` markers 20 units = 11.1109 px (D13); no transit
  text box overlaps natal text or underline boxes and none leaves its cell; the smallest
  gap between a transit text box and natal text in the same cell is 11.0 units (North
  Jalandhar), 11.3 (North Jammu) and 1.4 (South, both) — the South figure is the distance
  from a transit row's browser text box to the **label-row** text box above it, the same
  distance the renderer's own first natal row keeps from that label (the browser's text box
  is taller than the geometry's em box); the North markers for Jalandhar measure 40.18 /
  17.34 / 20.06 units (Tula: edge / numeral / natal text) and 44.56 / 23.54 / 41.06
  (Kumbha), all ≥ 15; Jammu needs no marker and neither chart has a South marker, so the
  South label-gap rule was not exercised in the browser (it is in the Python tests);
  `text-decoration` underlines sit 1.56–2.22 px below the baseline and 6.05–7.66 px inside
  the row pitch, touching no natal element.
* `transit_replacement`: A → B → C replacements keep one `g.transit` per root, one
  `d1-transit-desc` and one `d1-south-transit-desc`, resolvable `aria-describedby`
  references and unchanged natal children; the injected composition fault
  (`window.__transitComposeFault = "south"` and `"panel"`, after validation) leaves A's
  groups attached and hidden, no partial group, the failure reported, busy cleared, and
  restoring A's inputs shows A with its success status and no request.
* `transit_request_counts`: §10.9 exactly (1; 2; off/on ×5 → 2; styles ×6 → 2; Update
  unchanged → 2; edit then Update → 3; revert → 3 with the overlay reappearing; Update while
  pending → no extra request).
* `transit_races`: the §10.10 list with held responses, including edit-during-loading,
  off → on, edit → restore, toggle-off-during-loading, natal edit / Generate / injected
  natal 500 / cancel during loading, twenty rapid edits → 0 requests, duplicate Update → 1,
  retry after an injected 500 → a second request; and the three §6.4 visibility cases.
* `transit_errors`: DST gap (`Europe/London` 2026-03-29 01:30) and overlap (2026-10-25
  01:30) → 400 `input` shown in the status line; an injected 500 and a network abort → the
  §6.6 rows; `time_assumed` false and `source` `"selected"` on every transit response;
  offsets `UTC+01:00` / `UTC+00:00` shown for the London instants.
* `transit_preserved_state`: expanded daśā rows, roving row, badges, assumption labels,
  `#submitted-line` and `data-stale` identical across toggles and style switches; the
  accessibility tree includes the transit description while shown and not while hidden.
* `transit_previews`: `transit_{jalandhar,jammu}_{north,south,both}_{1280,375}.png`,
  grayscale identification screenshots, the keyboard path of §3.2.
* `transit_synthetic_crowded_600` (closing pass, §16.7): the labelled synthetic crowded-cell
  cases of §10.7, driven through the page's own composition code.

### 16.4 Deviations and interpretations (reported explicitly)

* **`aria-hidden="true"` on hidden transit groups** (never on a natal node): in this
  Chromium `display="none"` on an SVG group did not remove its texts from the accessibility
  tree, so the page sets both; the check asserts it. §5.6's "removes it from the
  accessibility tree" is to be read with this addition: the group is hidden by
  `display="none"` **and** `aria-hidden="true"`.
* The underline acceptance criterion is the spec's "within the row pitch, clear of the next
  row and of natal elements"; a stricter first draft ("inside the browser text box") was
  exceeded by 1.06 px for Jammu's North `T:Sa` and was not adopted. The text-box figure is
  still recorded.
* Status messages caused by the natal flow (new natal document, natal form stale) are
  written to `#transit-status` only, not mirrored to `#status`, so that the natal flow's own
  announcements are not overwritten; transit-initiated messages are mirrored.
* Three messages the draft did not define: "Transit request cancelled: the natal chart is
  being recalculated.", "Turn on Show transits to see transits." (Update while off), and
  "Transits wait for the natal chart to finish calculating."
* §6.3 items 2–5 failing while the request is still owned (not normally reachable, since
  every such event disowns first) release the pending record and clear the busy state but
  change nothing else, rather than "no state change at all", which would leave the busy
  state stuck.
* Inline rungs with zero rows are dropped unless they are the floor (the §5.7 example
  already showed only the floor for house 8); the side-house marker baseline is rounded
  **up** to the next hundredth (`math.ceil`, no `round()`) so that the formatted value keeps
  the 15-unit limit; kites 4 and 10 try a second position below the numeral if the one above
  fails; right-hand side houses mirror the left rule (marker x 960.60); every marker corner
  is checked for polygon containment on the formatted coordinates; the numeral glyph box
  uses the cell's actual digits.
* `south_svg_bytes_equal_renderer` (an existing acceptance check) failed on the server-side
  build alone because it expected `south_indian_svg` to be the last key; it now expects the
  last two keys `south_indian_svg, overlay` — the only pre-existing acceptance assertion
  changed.
* The fault seam `window.__transitComposeFault` is read only when the page was opened with
  `#acceptance`, as `__loadFixture`.
* **Closing-pass correction to the helper (§16.7):** the South `H<n>` label had been modelled
  at the renderers' uniform 0.68 em per character; the browser measured `H1` at 27.76 units
  against the modelled 27.2, leaving 8.44 units to the marker instead of the required 9.
  `overlay.py` now models the label as 0.80 em for the `H` plus 0.66 em per digit (DejaVu
  Sans advances are 0.752 and 0.636; the Arial/Helvetica fallbacks are narrower), the test
  mirrors it, and the two Layer 20 overlay goldens — new in this layer, not pre-existing —
  were regenerated once (`RENDER_GOLDEN_UPDATE=1`, `-k golden_blocks_match_exactly` only);
  one-digit markers moved 2.0 units left, two-digit 1.6. No pre-existing golden changed.
* **Closing-pass correction to a check criterion:** the first draft of
  `transit_synthetic_crowded_600` asserted a 15-unit gap between transit rows and natal
  text, which §6.2/§10.7 never required (rows must be inside the cell with 15 units to the
  **edges** and must not overlap natal boxes; consecutive rows keep the renderer's own pitch).
  The check now asserts exactly that and records the measured gap; the 15-unit marker rules
  and the 9-unit South label gaps are unchanged and were not loosened.

### 16.5 Protected behaviour verified

One pipeline call per request (counting wrapper); the lock body unchanged (AST rule);
`overlay_block` after the South render inside the `try`, outside the lock; the no-keyword
`serialize` document unchanged (golden assertions untouched); the extended document's
thirteen existing keys unchanged with `overlay` fourteenth; the request parser accepts
exactly the four keys; `svg` and `south_indian_svg` byte-equal to the renderers; sixteen
SVG goldens and the viewer JSON fixtures byte-identical; CSP, token, Host/Origin and payload
limits unchanged (existing tests); no dependency change; `viewer.js` holds no `Date`,
`Number(`, `parseFloat`, `innerHTML`, storage, `history` or `setInterval` (boundary scans).
Mutation check by the server-side builder: six deliberate geometry faults planted in a
scratch copy were each caught by `test_render_overlay.py` (40–349 failures); loosening the
side-house bottom guard alone was not, because the corner rule always binds first.

### 16.6 Not run, and not claimed

A native browser acceptance run of the Layer 20 version of `tools/viewer/acceptance.py`
(its Python Playwright dependency is not installed natively; the Layer 19 native review used
an independent Node script, and no Layer 20 equivalent has been made); a native full-suite
run; a session-VM full-suite baseline at `1905e86` (the owner's tree already held the Layer
20 files). The native results on record are the two targeted runs of §16.2.

### 16.7 Closing pass (2026-10-10)

**Synthetic crowded cells in the browser.** `transit_synthetic_crowded_600` builds synthetic
natal and transit charts with `tests/render_helpers.py` (every case labelled "synthetic"),
renders them with the unchanged renderers and `overlay_block`, splices the four keys (`svg`,
`south_indian_svg`, `overlay`, `planetary_positions` — the last from the synthetic chart's own
`BirthChart` through transport's `_planetary_positions`) into a real document, loads the
natal document through `window.__loadFixture`, serves the transit document through route
interception echoing the posted body, and lets the page's own validation and `composeTransit`
run unchanged at a 600 px chart (viewport 1280, style Both). Ten natal charts × transit
counts k ∈ {1, 2, 4, 9} = 40 cases, 80 style-cases; the outcome the check predicts from the
overlay block (rung font, shown count, `T:+n` in row, text marker, panel only) equalled what
the page drew in every one:

| natal case (synthetic) | North | South |
|---|---|---|
| kite 1, seven entries | text marker (edge 51.5, numeral 23.4, natal 35.0 units) | label-row marker (sign label 58.9, house label 10.44) |
| kite 1, two entries | k ≤ 2 at 28; k = 4 at 21; k = 9 `T:+6` in row (3 shown) | k ≤ 2 shown; k = 4 `T:+2` in row; k = 9 `T:+7` |
| triangle 2, two entries | text marker (44.6 / 23.5 / 41.1) | k ≤ 2 shown; k ≥ 4 in row |
| triangle 2, one entry | k = 1 at 26; k ≥ 2 `T:+k` in the one row | k ≤ 2 at 28; k = 4 at 26; k = 9 `T:+6` |
| side 3, one entry | k = 1 at 21; k ≥ 2 `T:+k` in the one row | as triangle 2, one entry |
| side 3, two entries | text marker below the side box (23.2 / 147.1 / 24.4) | as kite 1, two entries |
| side 11, four entries (natal overflow) | text marker, right-hand side (33.2 / 137.7 / 21.3) | label-row marker, `H11` (45.7 / 10.90) |
| Mesha four entries (kite 4) | k = 1 at 28; k ≥ 2 in row | label-row marker (58.9 / 10.44) |
| **Vrishabha** four entries (triangle 2) | text marker (45.1 / 24.3 / 53.1) | `marker: null` → no text in the cell; panel "panel only — no room for marker" |
| **Vrishchika** four entries (side 3) | text marker (23.2 / 145.8 / 21.3) | `marker: null` → panel only |

Verified on browser bounds in every case: every transit text inside its natal cell with
≥ 15 units to the North cell edges (minimum 16.1) and no overlap with natal text or
underlines; underlines inside the row pitch and clear of natal elements; no planet-entry text
below 21 units, every marker exactly 20; every North marker ≥ 15 units from edges, numeral
and natal text; every South marker ≥ 9 units from both labels (one-digit labels 10.44,
`H11` 10.90, after the helper correction of §16.4); the panel complete — every transit graha
once with its degree text, each style column consistent with the drawn cell, and exactly
"panel only — no room for marker" for the two null-marker cells; natal nodes equal to the
standalone document before and after; off/on × 3 with no request, one `g.transit` and one
description id per root, hidden groups `display="none"` + `aria-hidden="true"`. Recorded,
not asserted: the smallest browser-box gap between a transit row and a natal element is
9.88–11.15 units in North (the renderer's own pitch), 1.4 units between a South transit row
and the label-row text above it, and 0.8 units between a South label-row marker and the first
natal entry box below it — the same relationships the South renderer's own labels and first
row keep, with no overlap. Evidence: `Claude outputs/l20_acceptance/{fixture3,full3}/`
(`transit_synthetic_*` screenshots, per-case bounds JSON, `report.json`).

**Runs after the closing pass (cloud):** fixture database 62 pass / 0 fail / 1 skipped
(`reference_jammu_365256363`); full database 63 / 0 / 0; `test_render_overlay.py` 902
passed with the regenerated goldens; full suite 5515 / 12, identities unchanged. **Session
VM** (Python 3.10.12, the owner's tree after this delivery): `test_render_overlay`,
`test_viewer_transit_overlay` and `test_viewer_boundaries` together **1046 passed**. All 18
delivered paths verified by hash on the owner's machine; every protected path byte-identical
to `1905e86`; index empty. The overlay block for Jalandhar measures 10,572 bytes compact (slots 9,612,
entries 803); one `overlay_block` call takes about 1.3 ms (median of 200).

### 16.8 Promotion (2026-10-11; documentation only)

Promoted to SPECIFICATION v1.0 on the owner's instruction. Changes at promotion: the status
line; §14's v1.0 entry; §16.1's README row and heading (19 paths); §16.2's second native
result; §16.4's `aria-hidden` note made final; §16.6 rewritten; this section; and one
`README.md` subsection ("Transit overlay (Layer 20)") under "Interactive viewer" after the
Layer 19 chart-styles subsection, describing the toggle and its inputs, the fixed natal
place and zone with the returned offset, the explicit Update rule, the ordinary second
request and the additive `overlay` key, placement by sign in the natal frame, the `T:`
identification, overflow (`T:+n`, text markers, "panel only") and the panel, what is
retained and what is never requested, and the unchanged calculations. Verified at promotion:
every executable path, test module, golden and fixture of §16.1 keeps the hash recorded
there (closing-pass state), every protected path remains byte-identical to `1905e86`, and the
index is empty. No fixture regenerated, no test rerun needed for a documentation change.
Nothing staged, committed, pushed or deployed.
