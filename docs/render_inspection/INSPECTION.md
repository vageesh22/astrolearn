# Layer 10 rendered inspection record (§10.D of `docs/LAYER10_D1_RENDERER_SPEC.md`)

Date: 2026-09-06. Inspector: Claude (Fable 5.1), viewing the rasterised images directly.
Rasteriser: headless Chromium 1194 driven by Playwright 1.56 in a Linux container, DejaVu Sans
(first font in the stack) present, device scale factor 1, one CSS px = one device px. The
rasteriser is validation tooling only and is not a project dependency. Source SVGs are in `svg/`
(written by `tools/render/render_inspection_set.py`, all with degrees enabled); images in `png/`
are named `<case>_<total width px>.png`; `zoom_*.png` are pixel crops used to judge legibility.

## Cases and verdicts

| # | Case | 450 px | 600 px | 1000 px |
|---|---|---|---|---|
| 1 | `jalandhar_nocaption` (reference; Mars underlined in house 5; side-triangle entries Ve, Ju) | base text pass; side-triangle text marginal | pass | pass |
| 2 | `jalandhar_caption` (caption on) | pass except side-triangle text marginal | pass | pass |
| 3 | `bharatpur_caption` (real place name; Saturn underlined in house 9; house 3 = Me, Ve) | as above | pass | pass |
| 4 | `nine_house1` (kite; floor size; `+4`; two-line legend block) | floor text marginal | pass | pass |
| 5 | `nine_house2` (top triangle; `+7`) | floor text marginal | pass | pass |
| 6 | `nine_house3` (side triangle; 0.022 → floor; `+7`) | floor text marginal | pass | pass |
| 7 | `all_retrograde` (seven planet underlines; nodes suppressed) | underline 0.5 px, faint | pass (0.7 px, light grey, readable as underline) | pass |
| 8 | `all_retrograde_nodes_marked` (nine underlines) | as above | pass | pass |
| 9 | `long_caption_spaces` (≥120-char name with spaces; long timezone id) | pass | pass | pass |
| 10 | `long_caption_nospaces` (hard split at 55 chars) | pass | pass | pass |
| 11 | `two_overflow_houses` (houses 2 and 3 overflowed; two headings) | floor text marginal | pass | pass |
| 12 | `nine_house3_worst` (visual-only: every entry replaced by `Mo 29°59′`, the widest glyphs, in the nine-in-house-3 geometry) | — | pass | pass, visible margin to the slanted edge |

Items checked per case and size: no text touching or crossing a chart line; underline under the
abbreviation only and ending before the degrees; side-triangle and floor-size text legible;
`+n` legible; legend headings and slot entries legible and within the band; caption lines within
the band and not split mid-glyph; numeral placement acceptable (U-5); worst-case entry clear of
the triangle's slanted edge.

## Findings

- **Layout and semantics: no failures at any size.** Nothing touches a line; every underline sits
  under its abbreviation and stops well before the degree text (it is visibly longer than `Ju`
  and slightly shorter than `Mo`, as §4 predicts); captions and legends stay inside their bands;
  numerals sit at the inner vertex of each house in the conventional position.
- **Text width is comfortably conservative in DejaVu Sans.** Wrapped caption lines use roughly
  two-thirds of the band width; the worst-case side-triangle entry keeps a clear gap to the
  slanted edge. A wider fallback font has not been inspected.
- **450 px fails the floor/side-triangle legibility item.** At 450 px the floor rows are 8.75 px
  and side-triangle rows 9.2 px: characters can be resolved (see `zoom_house3_450.png`), but the
  prime mark ′ collapses to a one-pixel tick, the degree sign to a blob, and the underline to a
  0.5 px grey line. Base-size entries (13.3 px), numerals and the legend are fine at 450 px.
- **600 px passes in full** (`zoom_house3_600.png`, `zoom_house1_600.png`): ° and ′ are distinct
  at the floor size, `+n` and the legend slots are clear, the underline is thin but unambiguous.
- Cosmetic notes (not failures): the third caption line (`Lahiri (Chitrapaksha), true equinox ·
  Whole Sign houses · Mean Node`, 66 characters) always wraps onto two lines at the 55-character
  budget; the date/time line wraps its timezone id onto a second line when the id is long.

## Decision

Per the escalation rule of §10.D, the provisional 450 px minimum is withdrawn and the
**supported minimum total width is 600 px**; both 600 px and 1000 px passed every item for every
case. The renderer accepts any `width` (§2), but legibility is claimed only from 600 px upward.
