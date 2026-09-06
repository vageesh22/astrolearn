# Layer 9 — Canonical D1 (Rashi) Chart Representation — SPECIFICATION v1.0 — APPROVED 2026-09-06, implemented

**Status:** SPECIFICATION v1.0, approved by the project owner on 2026-09-06 and implemented as
`src/vedic_chart/representation/` with `tests/test_d1_representation.py` and `tests/test_dms.py`.
All eight owner decisions in section N were approved as recommended. The calculation
baseline is commit `2b3a5a9` (Vedic Chart Engine v1.0, `docs/CALCULATION_SPEC.md` FROZEN v1.0)
and is not modified by anything in this document.

```
BirthChart (frozen, Layer 8)  →  D1Chart (Layer 9, derived, immutable)  →  Renderer(s)  →  North / South / East Indian, table, JSON, web …
```

Layer 9 describes the *astrological structure* of a D1 chart — which rashi sits in which house,
which grahas occupy it, where the Lagna is — in a form no visual layout can bias. It computes no
astronomy and applies no astrological rule. It is not an interpretation layer.

## A. Audit of the frozen `BirthChart` (as implemented at 2b3a5a9)

`chart/model.py::BirthChart` (frozen dataclass; `grahas`/`houses` are `MappingProxyType` over private copies):

| Existing field | Type / content | Sufficient for D1? | Missing |
|---|---|---|---|
| `request` | `BirthChartRequest{birth_date: date, birth_time: time (naive), place_query: str}` | yes — chart metadata | — |
| `location` | `ResolvedLocation{canonical_name, latitude, longitude, timezone_id}` | yes — metadata | — |
| `moment_utc` | aware UTC `datetime` | yes — metadata | — |
| `julian_day_ut` | `float` | yes — metadata | — |
| `ayanamsa` | `float` (Lahiri, true equinox) | yes — metadata (value) | the ayanamsha *name* is a constant of the frozen spec, not a field; Layer 9 supplies it as a descriptor |
| `lagna` | `Lagna{tropical_longitude, sidereal_longitude, ayanamsa, placement: DivisionalPlacement}` | yes | — |
| `lagna.placement` | `DivisionalPlacement{rashi_index 0–11, rashi_number 1–12, rashi_name, degrees_in_rashi, nakshatra_index, nakshatra_number, nakshatra_name, degrees_in_nakshatra, pada 1–4, degrees_in_pada}` | yes — Lagna rashi, degree-in-sign, nakshatra, pada all present | — |
| `grahas[Graha]` | `GrahaPosition{sidereal_longitude, speed_longitude, is_retrograde, placement: DivisionalPlacement}` for the 9 `Graha` members (SUN, MOON, MERCURY, VENUS, MARS, JUPITER, SATURN, RAHU, KETU), dict in enum order | yes — longitude, rashi, degree, nakshatra, pada, retrograde | — |
| `houses[Graha]` | `int` 1–12 (Whole Sign house of each graha) | yes — graha → house | the **inverse** view (house → rashi, house → occupants) is not stored; it is a pure rearrangement of `lagna.placement.rashi_index` and `houses`, which Layer 9 derives |

Facts established by inspection: no display/DMS helper exists anywhere in `src/`; no rulership
("lord") table exists anywhere in `src/`; Lagna's house is not stored (it is house 1 by
definition of Whole Sign, `lagna/whole_sign.py`); `Graha` enum order is the deterministic
iteration order of `BirthChart.grahas`; tropical longitudes of grahas are *not* on `BirthChart`
(only on the intermediate `SiderealPositions`) — not needed for D1.

**Conclusion:** every value a D1 chart needs already exists on `BirthChart`. Nothing is missing
from the frozen model; Layer 9 needs only rearrangement plus display derivation.

## B. Canonical representation (proposed)

Package `src/vedic_chart/representation/` (Layer 9). Two modules: `d1.py` (model + builder) and
`dms.py` (display derivation). All dataclasses `frozen=True`.

```
D1Chart
  source:   BirthChart                     # the authority; never copied, only referenced
  meta:     D1Meta                         # descriptors + references to request/location/instant
  lagna:    D1Lagna                        # distinguished from grahas; not an "occupant"
  houses:   tuple[D1House, ...]            # exactly 12, index 0 → house 1 … index 11 → house 12
  grahas:   Mapping[Graha, D1GrahaPlacement]   # exactly 9, MappingProxyType, Graha enum order
```

Construction: `build_d1_chart(chart: BirthChart) -> D1Chart`, a pure function; equal inputs give
equal outputs (deterministic, tested).

## C. Exact fields and their source

Values are exposed by **reference** to the frozen objects wherever they already exist (option B —
derived, not copied). The only *new* data is structural (house → rashi, house → occupants), the
constant convention descriptors, and on-demand DMS display values.

| Layer 9 field | Source | Kind |
|---|---|---|
| `D1Chart.source` | the `BirthChart` itself | reference |
| `D1Meta.request`, `.location`, `.moment_utc`, `.julian_day_ut`, `.ayanamsa` | `BirthChart` fields | reference / same float |
| `D1Meta.zodiac = "sidereal"`, `.ayanamsha = "Lahiri (Chitrapaksha), true equinox"`, `.house_system = "whole_sign"`, `.node = "mean"`, `.engine_spec = "AstroLearn Calculation Specification FROZEN v1.0"` | constants of the frozen spec | descriptor strings (labels only; they assert nothing new) |
| `D1Lagna.position` | `BirthChart.lagna` (`Lagna`) | reference |
| `D1Lagna.house = 1` | Whole Sign definition | constant |
| `D1House.number` (1–12) | position in the 12-tuple | structural |
| `D1House.rashi_index` (0–11) | `(lagna.placement.rashi_index + number − 1) mod 12` | structural (inverse of the frozen `house_number` formula; tested against `BirthChart.houses`) |
| `D1House.rashi_number` (1–12), `.rashi_name` | `rashi_index + 1`; `vedic.divisions.RASHI_NAMES[rashi_index]` | structural, from the frozen name table |
| `D1House.occupants` | `tuple[Graha, ...]` of grahas whose `BirthChart.houses[g] == number`, in `Graha` enum order | structural |
| `D1GrahaPlacement.graha` | `Graha` | reference |
| `D1GrahaPlacement.position` | `BirthChart.grahas[graha]` (`GrahaPosition`) | reference |
| `D1GrahaPlacement.house` | `BirthChart.houses[graha]` | same int |
| convenience read-only properties (`sidereal_longitude`, `rashi_index/number/name`, `degrees_in_rashi`, `nakshatra_index/number/name`, `pada`, `is_retrograde`, `speed_longitude`) | pass-throughs to `position` / `position.placement` | no storage |
| `D1GrahaPlacement.dms()` / `D1Lagna.dms()` | `dms.to_dms(degrees_in_rashi, …)` | derived display, computed on call, never stored |

No authoritative number is copied; every float reachable from `D1Chart` *is* the float on
`BirthChart` (identity, not equality — tested).

## D. House representation

`D1House(number, rashi_index, rashi_number, rashi_name, occupants)`, frozen.

- House numbers are always 1–12; `D1Chart.houses[i].number == i + 1`; there is no house 0.
- Rashi indexing stays 0-based internally (`rashi_index`) with the 1-based `rashi_number` beside
  it, mirroring `DivisionalPlacement` exactly; renderers and APIs are expected to publish the
  1-based number and the name.
- `rashi_index` of house *n* is `(lagna_rashi_index + n − 1) mod 12`; the 12 houses therefore
  carry the 12 rashis each exactly once, in zodiacal order starting from the Lagna's rashi.
- **Rashi lord: excluded.** No rulership table exists in the frozen engine; lordship is an
  astrological rule (it feeds yoga/dasha/strength logic), not a structural fact of the D1
  geometry, and no renderer needs it to draw a Kundli. It belongs to a future reference-data
  layer if wanted (owner decision L-1).
- Empty house: present, with `occupants == ()`. Never omitted, never `None`.
- Multiple grahas: `occupants` is a tuple in **`Graha` enum order** (Sun, Moon, Mercury, Venus,
  Mars, Jupiter, Saturn, Rahu, Ketu) — the same deterministic order the frozen `BirthChart`
  already iterates in (owner decision L-2; degree-ordering remains available to any renderer via
  `degrees_in_rashi`).
- The Lagna is **not** an occupant (owner decision L-6); it is exposed once, as `D1Chart.lagna`.

## E. Graha representation

`D1GrahaPlacement(graha, position, house)` for each of the nine grahas, exposing by
pass-through: identity (`Graha`), `sidereal_longitude` (full precision), rashi
index/number/name, `degrees_in_rashi`, nakshatra index/number/name, `pada`, `is_retrograde`,
`speed_longitude` (raw, °/day, kept because it is the datum `is_retrograde` was derived from
and is useful for stationary-graha display; decision L-8), and `house`.
Excluded on purpose: dignity, exaltation/debilitation, combustion, planetary war, strength,
shadbala, aspects/drishti, yogas, interpretation, lordship.

## F. Lagna representation

`D1Lagna(position: Lagna, house: int = 1)`, exposing by pass-through `sidereal_longitude`,
`tropical_longitude`, `ayanamsa`, rashi index/number/name, `degrees_in_rashi`, nakshatra
index/number/name, `pada`, and `dms()`. It is a distinct type, never a `Graha`, never listed in
`occupants`; renderers draw the ascendant marker from `D1Chart.lagna` alone. House is the
constant 1 (Whole Sign). All fields already exist on the frozen `Lagna`; nothing new is needed.

## G. Precision and display policy

Three precisions, kept apart:

1. **Calculation precision** — IEEE-754 double from Swiss Ephemeris, per the frozen spec.
2. **Canonical stored precision** — identical: Layer 9 stores no numbers of its own; it holds
   references to the frozen floats. No rounding occurs anywhere in Layer 9's data.
3. **Display precision** — `dms.to_dms(value_degrees, seconds_decimals=0) -> DMS(degrees: int,
   minutes: int, seconds: float)`: a pure, on-demand conversion that is **non-authoritative
   display data**. Policy: **truncation toward zero** at the requested precision, never rounding
   (owner decision L-3). Rationale: truncation guarantees the displayed value can never appear to
   cross a rashi/nakshatra/pada boundary that the authoritative value did not cross (29.999999°
   displays as 29°59′59″, not 30°00′00″). Renderers may request more decimals of seconds; they
   may not obtain a value inconsistent with the classification.

The longitude on `BirthChart` remains the single authority; a DMS value is never stored, compared,
or fed back into any calculation.

## H. Retrograde

`is_retrograde` and `speed_longitude` are exposed exactly as the frozen `GrahaPosition` holds
them; Layer 9 neither recomputes nor overrides them. Rahu and Ketu therefore appear with
`is_retrograde == True` at every instant (Mean Node: uniformly negative speed, per the frozen
spec), through the same field as the planets — no special node flag. Sun and Moon carry
`is_retrograde == False` by data. Renderers decide the glyph (e.g. "(R)"); Layer 9 decides nothing.

## I. Immutability and source of truth

`BirthChart` stays the authority. `D1Chart` is a **derived, immutable view**: frozen dataclasses,
`houses` a tuple of frozen `D1House` with tuple `occupants`, `grahas` a `MappingProxyType` over
a private dict, and a `source` reference so nothing needs copying. Because every number is a
reference to a frozen object, the representation *cannot* diverge from its `BirthChart`; it can
be rebuilt at any time and will compare equal. A derived view is preferred over a serialized copy
precisely to avoid duplicated authoritative state.

## J. Renderer boundary

```
D1Chart  ──►  Renderer.render(d1: D1Chart) -> Output
```

- A renderer consumes only `D1Chart` (and may use `dms.to_dms`). It performs no astronomy and no
  astrology: it imports nothing from `ephemeris`, `astronomy`, `sidereal`, `time`, `lagna` or
  `vedic.grahas` calculation paths (AST-enforced, as for every other layer).
- All layout knowledge — North Indian fixed-house diamond (house 1 top-centre, anticlockwise),
  South Indian fixed-rashi grid (Mesha second cell of the top row, clockwise), East Indian/Bengali
  grid, tabular columns, JSON field names, web components — lives inside the renderer.
- Conceptual protocol: `class ChartRenderer(Protocol): def render(self, chart: D1Chart) -> T`.
  Candidate first renderers (not now): `TabularRenderer` (rows), `DictRenderer` (JSON-ready
  primitives; the natural API shape), then `NorthIndianSVGRenderer` etc.
- Renderers may read `D1Chart.meta` descriptors to label the chart (ayanamsha, house system).

## K. Test matrix (to implement with the layer)

Structural (pure, no ephemeris; `BirthChart` instances built synthetically from frozen
dataclasses via `classify()`): for each Lagna rashi 0–11 → 12 houses present, numbers 1–12 in
order, `houses[i].rashi_index == (lagna_idx + i) mod 12`, the 12 rashi indices are a permutation
of 0–11, the 12 names match `RASHI_NAMES`; empty houses have `occupants == ()`; a house holding
several grahas lists them in `Graha` enum order; every graha appears in exactly one house;
`len(sum(occupants)) == 9`.

Invariants over any chart: for every graha, `placement.house == the house whose occupants contain
it`; `placement.rashi_index == houses[house−1].rashi_index`; `house == source.houses[graha]`;
`placement.position is source.grahas[graha]`; `lagna.position is source.lagna`; `lagna.house == 1`;
`houses[0].rashi_index == lagna.rashi_index`; Rahu and Ketu are 6 houses apart and
`is_retrograde` is True for both; `is_retrograde == (speed_longitude < 0)` pass-through; nakshatra
and pada equal the source placement's.

Longitude preservation: `placement.sidereal_longitude is source.grahas[g].sidereal_longitude`
(object identity) and `==` for Lagna; no `round()` in the package (AST scan).

DMS (`dms.py`): 0.0 → 0°0′0″; 13.788209 → 13°47′17.55″ (truncated at 2 decimals) and 13°47′17″
at 0 decimals; 29.999999 → 29°59′59″ (never 30°0′0″); negative input rejected (`ValueError`, since
degrees-in-division are non-negative); output type frozen; 60-carry impossible by construction.

Determinism: two builds from the same `BirthChart` are `==`; occupant order equals enum order
regardless of input dict order (build from a `BirthChart` whose grahas were supplied in reversed
order — `BirthChart` re-proxies but preserves insertion order, so this test proves Layer 9 sorts).

Regression: the frozen Jalandhar reference chart (1995-03-21 06:45 IST, fixture geocoder):
Lagna Meena house 1; house 1 occupants (Sun,); house 12 (Mercury, Saturn) in that order; house 8
(Moon, Rahu); house 2 (Ketu,); house 5 (Mars,) retrograde; house 9 (Jupiter,); house 11 (Venus,);
houses 3, 4, 6, 7, 10 empty; twelve rashis Meena, Mesha, … , Kumbha in order.

Immutability: `FrozenInstanceError` on attribute set for `D1Chart`, `D1House`, `D1GrahaPlacement`,
`D1Lagna`; `TypeError` on `grahas[...] = …`; `houses` is a tuple; `occupants` is a tuple.

Boundary: AST test — `representation/*.py` import only `chart.model`, `vedic.grahas` (Graha,
GrahaPosition types), `vedic.divisions` (names/placement type), `lagna.ascendant` (Lagna type),
`inputs.model`/`location.model` (types), stdlib; never `swisseph`, `ephemeris`, `astronomy`,
`sidereal`, `time`, `lagna.whole_sign` (the inverse formula is Layer 9's own two lines).

## L. Architectural impact

Layer 9 is implementable **entirely as a derived layer with zero changes to Layers 1–8**. Every
required value exists on `BirthChart`; the house→rashi/house→occupant views are pure
rearrangements of `lagna.placement.rashi_index` and `houses`; the descriptors are constants of the
frozen spec; DMS is display derivation. No change to the frozen model is proposed or needed.

## M. Explicitly excluded from Layer 9

Graha Drishti (no placeholder either), dashas, yogas, divisional charts (D9 etc.), Bhava Chalit,
bhava cusps, degree-based aspects, dignity/exaltation/debilitation, combustion, planetary war,
shadbala/strength, transits, retrograde *calculation*, rashi/house lordship, interpretation of any
kind, and every visual/geometric/format concern (those are renderers).

## N. Owner decisions — all approved as recommended (2026-09-06)

- **L-1** Rashi lord: exclude (recommended) / include as static reference data. **Approved as recommended.**
- **L-2** Occupant order within a house: `Graha` enum order (recommended) / ascending degree. **Approved as recommended.**
- **L-3** DMS display: truncation toward zero (recommended) / rounding with carry. **Approved as recommended.**
- **L-4** `D1Chart.source` reference to the full `BirthChart`: include (recommended) / omit. **Approved as recommended.**
- **L-5** Package name `vedic_chart.representation` (recommended) / alternative. **Approved as recommended.**
- **L-6** Lagna is not a house occupant (recommended) / also listed in house 1. **Approved as recommended.**
- **L-7** Convention descriptor strings in `D1Meta` (recommended) / omit. **Approved as recommended.**
- **L-8** Expose raw `speed_longitude` on graha placements (recommended) / hide. **Approved as recommended.**

## O. Files created/changed at implementation (created)

Create: `src/vedic_chart/representation/__init__.py`, `representation/d1.py`,
`representation/dms.py`, `tests/test_d1_representation.py`, `tests/test_dms.py`.
Change: `README.md` (Layer 9 section), this document (promote from draft), and
`docs/CALCULATION_SPEC.md` gains **no** change (Layer 9 alters no calculation).
Untouched: everything under `src/` that exists at `2b3a5a9`, all existing tests, `pyproject.toml`
(no new dependency).
