# Layer 10 rendered inspection record (§10.D / §10.A4 of `docs/LAYER10_D1_RENDERER_SPEC.md`)

Inspector: Claude (Fable 5.1), judging the rasterised images directly. **Owner visual approval:
granted 2026-09-06** for the v0.5 design — numeral anchors, stacked side-triangle entries,
retrograde underlines and the 600 px supported minimum — and the specification was promoted to
**v1.0** with no change to renderer behaviour; the v0.5 evidence in section 1 is therefore the
v1.0 evidence. From v1.0 the generated assets under `svg/`, `png/` and `typography/` are ignored
by Git and kept locally (reproducible via section 3); this record, the goldens and the tooling
stay tracked. Earlier draft states are kept below as history.

## 1. Current evidence (v0.5 = v1.0 — stacked side-triangle layout U-8 on top of v0.4)

Renderer state: the working tree on top of the committed DRAFT v0.3 baseline `a38e424`
(v0.4 + v0.5 changes, now approved as v1.0, awaiting the owner's staged review and commit). Every file in this section was produced from the v0.5
renderer; each PNG was rasterised from the SVG of the same name in `svg/` (or `typography/`).

**SVG cases** (`svg/`, written by `tools/render/render_inspection_set.py`; degrees on unless
stated): `jalandhar_nocaption`, `jalandhar_caption`, `bharatpur_caption`, `nine_house1`,
`nine_house2`, `nine_house3`, `side_three` (three occupants in house 3), `side_nodegrees` (nine
occupants in house 3, `show_degrees=False`), `all_retrograde`, `all_retrograde_nodes_marked`,
`long_caption_spaces`, `long_caption_nospaces`, `two_overflow_houses`, `long_caption_overflow`,
plus the embedding documents `embed_two_different.html` / `embed_two_identical.html`.

**Typography-only image** (`typography/typography_side_widest.svg`, built by
`tools/render/rasterise_inspection.py --worst`): the nine-in-house-3 render with every entry
replaced by the widest glyphs `Mo` / `29°59′`. It is a width stress test of the side-triangle
box, **not a chart and not a fixture**; real planet identities are never altered in any semantic
case. (`svg/nine_house3_worst.svg` is the superseded v0.4 one-line version of the same idea; it
is tracked in `a38e424` and cannot be removed without a Git write, so it remains in `svg/` but is
no longer produced or used.)

**PNG evidence** (`png/`, `typography/`): for each semantic case `<case>_600.png` /
`<case>_1000.png` in DejaVu Sans and `<case>_arial_600.png` / `<case>_arial_1000.png` in
Liberation Sans (Chromium's resolution of `Arial`) — 56 images — plus the four typography renders
and the zooms `zoom_house1_600`, `zoom_house1_arial_600` (crowded kite, floor size, underline),
`zoom_house11_1000` (single-occupant side triangle after the outer-edge refinement),
`zoom_bharatpur_house3_600` (two stacked occupants with the 0.40 f grouping gap) and
`typography/zoom_typography_side_widest_1000`.

**Verdicts, per case × size × font** (items: no text touching or crossing a chart line;
underline under the abbreviation row only, never near the degrees; side-triangle and floor-size
text legible with `°` and `′` distinct; `+n` legible on its own row; each abbreviation grouped
with its own degrees and successive planets distinguishable; legend headings and slot entries
legible and within the band; caption lines within the band; numeral placement acceptable —
provisional, owner review pending; widest row clear of the slanted edges and the numeral):

| # | Case | DejaVu 600 | DejaVu 1000 | Liberation 600 | Liberation 1000 |
|---|---|---|---|---|---|
| 1 | `jalandhar_nocaption` (Ve, Ma, Ju now stacked at the base size 0.032) | pass | pass | pass | pass |
| 2 | `jalandhar_caption` | pass | pass | pass | pass |
| 3 | `bharatpur_caption` (house 3 = Me, Ve stacked at 0.028; Sa underlined in house 9; Ju in 11) | pass | pass | pass | pass |
| 4 | `nine_house1` (kite; floor; `+4`) — unchanged by U-8 | pass | pass | pass | pass |
| 5 | `nine_house2` (top triangle; `+7`) — unchanged by U-8 | pass | pass | pass | pass |
| 6 | `nine_house3` (side triangle: `Su`/`1°00′`, `Mo`/`3°00′`, `+7` at the floor) | pass | pass | pass | pass |
| 7 | `side_three` (three stacked occupants at 0.022) | pass | pass | pass | pass |
| 8 | `side_nodegrees` (nine abbreviations at 0.024, single rows, no overflow) | pass | pass | pass | pass |
| 9 | `all_retrograde` | pass | pass | pass | pass |
| 10 | `all_retrograde_nodes_marked` | pass | pass | pass | pass |
| 11 | `long_caption_spaces` | pass | pass | pass | pass |
| 12 | `long_caption_nospaces` | pass | pass | pass | pass |
| 13 | `two_overflow_houses` (house 3 = `Ju`/`1°00′`, `Sa`/`3°00′`, `+2`) | pass | pass | pass | pass |
| 14 | `long_caption_overflow` | pass | pass | pass | pass |
| T | `typography_side_widest` (typography-only) | pass | pass | pass | pass |

Findings: single-occupant side triangles now carry labels at the same size as every other
one- or two-entry house (`Ve` / `27°39′` in house 11 is 0.032 like `As 9°47′` in house 1); the
text block sits against the outer edge with the slack toward the numeral, mirrored between the
left and right triangles, and the numeral keeps ≥ 0.0195 clearance. Two occupants (Bharatpur
house 3) read as two clearly separate blocks thanks to the 0.40 f gap. Crowding behaviour is
unchanged in outcome: nine occupants still show two entries and `+7`, four show two and `+2`,
and the overflow row has its own space. In Liberation Sans everything is narrower and the same
verdicts hold; the fixed-length underline still overhangs short abbreviations slightly but stays
on the abbreviation row. Kites and top/bottom triangles are byte-identical to v0.4 apart from the
`data-layout` attribute.

**Embedding check (§10.A4, Chromium half):** re-run on the v0.5 documents — no duplicate ids,
each SVG's accessible name and description equal its own `<title>`/`<desc>`.

**Decision.** Supported minimum total width remains **600 px**.

## 2. Historical images — STALE, not current validation

**v0.4 leftovers** (one-line side-triangle labels at 0.022, superseded by U-8): the semantic
PNGs of v0.4 were overwritten by the v0.5 renders of the same names; the only v0.4 images that
remain are `png/nine_house3_worst_600.png`, `png/nine_house3_worst_1000.png`,
`png/nine_house3_worst_arial_600.png`, `png/nine_house3_worst_arial_1000.png` and
`svg/nine_house3_worst.svg` — the v0.4 typography-only stress image, replaced by
`typography/typography_side_widest*`. They are not v0.5 evidence.

**v0.3 images** (underline 0.06 f, ids `title`/`desc`, two-line descriptor caption):

The files below were produced from the v0.3 renderer as committed in `a38e424` (underline 0.06 f,
ids `title`/`desc`, two-line descriptor caption) and were **not** regenerated for v0.4. They are
kept only as the evidence behind the 450 px → 600 px decision and must not be read as current
validation:

- `png/jalandhar_nocaption_450.png`, `png/nine_house1_450.png`, `png/nine_house3_450.png`,
  `png/zoom_house3_450.png` — the 450 px renders and pixel crop that failed the floor-size
  legibility item (8.75 px / 9.2 px text, `′` a one-pixel tick, 0.06 f underline 0.5 px).
- `png/zoom_house3_600.png` — the v0.3 600 px crop used for the escalation decision (the current
  crowded-cell crop is `zoom_house1_600.png`).
- `png/zoom_worst_1000.png` — v0.3 crop of the one-line worst-case side triangle; superseded by
  `typography/`.

Everything else in `svg/` and `png/` is v0.5. The v0.3 versions of the SVGs and of the 600/1000 px
PNGs are what the repository holds at `a38e424`; on disk they have been overwritten.

**v0.3 decision record.** Eleven cases at 450/600/1000 px in DejaVu Sans: 1000 px and 600 px
passed every item; 450 px failed the floor-size/side-triangle legibility item; per the §10.D
escalation rule the set was re-inspected at 600 px and passed, fixing the minimum at 600 px.

## 3. Exact procedure (reproducibility)

1. **Generate the SVG set** (committed generator, stdlib + project only):
   `python tools/render/render_inspection_set.py docs/render_inspection/svg` — writes the 14
   case SVGs and the 2 embedding HTML documents from the test suite's chart builders
   (`tests/render_helpers.py`), so an inspected drawing and an asserted drawing cannot drift.
2. **Rasterise** (validation tooling, not a dependency): headless Chromium 1194 via Playwright
   1.56 on Linux, device scale factor 1, each SVG inline in an empty white HTML page sized to the
   requested total width with height from the viewBox aspect, full-page screenshot:
   `python tools/render/rasterise_inspection.py docs/render_inspection/svg docs/render_inspection/png --widths 600 1000 --worst --a11y`
   (DejaVu Sans set; `--worst` builds the typography-only `typography/typography_side_widest.svg`
   and rasterises it into `typography/`; `--a11y` runs the embedding check), then
   `python tools/render/rasterise_inspection.py docs/render_inspection/svg docs/render_inspection/png --widths 600 1000 --font-family Arial --suffix _arial`
   (second-font set; the script prints the platform font Chromium actually used — Liberation Sans
   here — via CDP `CSS.getPlatformFontsForNode`). Fonts present in the validation environment:
   DejaVu Sans (fontconfig default and first in the declared stack); `Arial` and `Helvetica` both
   mapped by Chromium to Liberation Sans. Real Arial/Helvetica on macOS were not rendered.
3. **Pixel zooms**: Pillow `Image.open(png).crop(box).resize(size, resample)`;
   `zoom_house1_600.png` / `zoom_house1_arial_600.png` = box (200, 80, 420, 220) of the
   `nine_house1_600` renders ×4 NEAREST; `zoom_house11_1000.png` = box (700, 150, 1000, 330) of
   `jalandhar_nocaption_1000` ×3 LANCZOS; `zoom_bharatpur_house3_600.png` = box (15, 90, 190,
   260) of `bharatpur_caption_600` ×4 NEAREST; `typography/zoom_typography_side_widest_1000.png`
   = box (30, 120, 330, 360) of `typography_side_widest_1000` ×3 LANCZOS.
4. **Judgement**: a person (here the inspector) views the images; nothing in `pytest` counts as a
   visual pass (§10.D).

**Steps not reproduced by the committed set generator:** rasterisation (step 2), the font
substitution for the `_arial_` images, the typography-only image construction, the embedding
accessibility check, and the zoom crops (step 3). All of them are reproduced by
`tools/render/rasterise_inspection.py` (steps 2 and the a11y check; the zoom parameters are
documented above) given Playwright + Chromium and Pillow, which are validation-only and not
project dependencies. The regenerated PNGs were byte-compared with the delivered ones in the
validation environment and are identical; on another machine or Chromium build the pixels may
differ slightly, which is expected and does not affect the SVG evidence.
