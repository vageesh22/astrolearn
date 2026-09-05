# Core Engine Audit — 2026-09-05

Engine state audited: 252 passing tests, all eight layers built. Rule of the audit: **report,
never fix**. No file under `src/`, `tools/geodata/` or any pre-existing test was modified.
Added: this report, `docs/CALCULATION_SPEC.md` (draft), `docs/verification_cases.md`,
`tools/audit/verification_cases.py`, `tests/test_verification_cases.py`.

Evidence classes: **(A)** internal implementation consistency, **(B)** astronomical
correctness, **(C)** conformity with the chosen Vedic conventions.

## STOP item — OPEN-1 CLOSED 2026-09-05 (owner approved option (a); freeze gate accepted)

**OPEN-1 — ayanamsha reference frame (B, C).** `ephemeris/swiss_ephemeris.py::get_ayanamsa_lahiri`
uses `swe.get_ayanamsa_ut`, which returns the Lahiri ayanamsha relative to the *mean* equinox
(measured identical to `get_ayanamsa_ex_ut(jd, SEFLG_NONUT)`: 23.85709235° at J2000), while
`calc_planet_position` and `calc_ascendant_tropical` return *true-equinox* (apparent)
longitudes. `sidereal/positions.py::sidereal_longitude` subtracts the one from the other, so
every sidereal longitude carries the nutation in longitude (≤ ~17″, 0.005°) relative to Swiss
Ephemeris' native `SEFLG_SIDEREAL` Lahiri longitudes. Measured: Sun J2000 engine 256.511826° vs
native 256.515696° (Δ = −13.93″ = nutation); reference chart Sun 336.168758° vs native
336.165799° (Δ = +10.65″). All existing tests pass because their tolerances (≥ 0.02°) exceed
the effect; they did not detect it. Internal consistency (A) is intact. Decision needed:
(a) use `swe.get_ayanamsa_ex_ut(jd, 0)` (true-equinox ayanamsha) — engine then matches Swiss
Ephemeris / Jagannatha-Hora-class software exactly; test reference values and the two docs
shift by ≤ 17″ (e.g. `test_chart` Lagna 339.798870 → 339.795911); or (b) keep and document.
Recommendation: (a). **Not applied.**

## Findings (no change made)

- **F-1 (A/C, low) — RESOLVED BY SPECIFICATION 2026-09-05 (spec §8 now states the rival is the highest-ranked, not most-populous, candidate; no code change):** `offline/search.py::evaluate`: the population ratio is measured against the
  *highest-scored* materially different rival (`rivals[0]`), not the *most populous* one. Because
  score = feature weight + 1.5·log10(pop) + bonuses, a rival can be ordered below a
  less-populous one, so dominance could in principle be granted against a smaller rival than
  exists. Rare in practice; recommend ratio against `max(rival.population)` when the policy is
  next revised.
- **F-2 (A, low)** `evaluate` treats two candidates with `admin1_name` = `None` in the same
  country as *not* materially different (tuple equality on `(country, None)`).
- **F-3 (A, info)** `PlanetPosition`, `SiderealBodyPosition`, `SiderealPositions` are mutable
  dataclasses (all chart-reachable models are frozen). Intermediate only.
- **F-4 (A, info)** `calculate_sidereal_positions` computes `julian_day_ut(moment)` and
  `calculate_positions(moment)` recomputes it internally — same deterministic value, no drift,
  but two calls. Also `location/model.py` and `lagna/ascendant.py` each carry a private
  `_validate_coordinate`; kept separate on purpose (engine must not import Layer 2).
- **F-5 (provenance, low) — RESOLVED 2026-09-05: `pyswisseph==2.10.3.2` pinned in `pyproject.toml`.** `pyproject.toml` declares `pyswisseph` without a version pin
  (installed 2.10.3.2, SE 2.10.03). Recommend pinning when the spec is finalized.
- **F-6 (A, info)** `offline/normalize.py` drops all Unicode combining marks, which in Indic
  scripts includes virama and nukta. Both the importer and the query path apply the same
  function, so lookups stay consistent; distinct names differing only in those marks would
  collide. Observed no failure.
- **F-7 (A, info)** `offline/db.py` builds a SQLite URI from the raw path; a path containing
  `?` or `#` would need percent-encoding (the project path with a space works).
- **F-8 (A, info)** `search.py:225` rounds the ranking *score* to 6 places — the only `round()`
  in `src/`; no astronomical value is rounded anywhere.
- **F-9 (test coverage, info)** Dedicated AST import-boundary tests exist for `inputs`,
  `location`, `location/offline`, `lagna`, `chart`. `astronomy`, `sidereal`, `vedic`, `time`,
  `ephemeris` were checked manually in this audit (import table below) and are clean; a single
  repository-wide import-graph test would close the gap.

## Verified as correct (evidence)

- Flags: `SEFLG_SWIEPH|SEFLG_SPEED` = geocentric apparent, true equinox of date (B; measured
  deltas: light-time 29.8″, aberration 14.1″, nutation 13.9″, deflection 0.005″ for Mars at J2000).
- Mean Node for Rahu; `TRUE_NODE` referenced nowhere outside Layer 5/astronomy except a comment (C).
- Retrograde = `speed_longitude < 0.0` only; station behaviour measured (A/B).
- JD formula vs `swe.julday`: 0.000000 s difference at six instants 1850–2399 (B).
- Ephemeris range: 1800–2399 OK; 1799 and 2400+ raise `RuntimeError` (Moshier refused) (A).
- Lat/lon conventions: N+/E+ end to end; `timezone_at(lng=, lat=)` keyword-correct (swapping
  yields Etc/GMT-2, i.e. ocean); `houses_ex(jd, lat, lon)` order confirmed by the 0.004°
  independent-formula agreement (B).
- DST gap/overlap rejection; historical offsets (BDST 1943 +02:00, India 1943 +06:30, London
  1840 LMT −00:01:15) from tzdata 2026c (A, external anchor: tzdata).
- Date-line: same instant via Pacific/Kiritimati (+14) and Pacific/Midway (−11) gives
  identical JD and identical planetary positions, different wall dates (A).
- Boundaries: half-open, unrounded, no epsilon; live Sankranti case crosses 359.99966 → 0.00034
  correctly (A/C). Extreme latitudes 66–90° and −89° return classifiable Lagnas (A).
- Provenance: all six GeoNames SHA-256s recomputed and match `dataset_metadata`; licenses
  recorded (CC BY 4.0; timezonefinder MIT / data ODbL); `DATA_SOURCES.md` present.
- Architecture: `import swisseph` only in `ephemeris/swiss_ephemeris.py`; no network modules
  anywhere in `src/`; `assemble_chart` swallows nothing; chart mappings proxied over copies.

## Import table (manual boundary check, 2026-09-05)

`astronomy/positions` → ephemeris, time.julian_day · `sidereal/positions` → astronomy,
ephemeris.get_ayanamsa_lahiri, time.julian_day · `vedic/grahas` → astronomy, sidereal ·
`vedic/divisions` → stdlib · `time/*` → stdlib (+zoneinfo in local_time) · `lagna/ascendant` →
ephemeris, sidereal, time.julian_day, vedic.divisions · `lagna/whole_sign` → stdlib ·
`chart/*` → inputs, location.model, time.local_time, sidereal, vedic.grahas, lagna ·
`location/model` → time.local_time, zoneinfo · `location/offline/tz_lookup` → timezonefinder,
zoneinfo · `inputs/model` → stdlib.

## Needs external reference comparison (cannot be settled offline)

1. Full-chart agreement with an independent Lahiri/Whole-Sign implementation (Jagannatha Hora,
   Drik Panchang) for the verification cases — do this *after* OPEN-1 is decided, or expect
   ≤ 17″ systematic offsets.
2. Published Lahiri ayanamsha tables (Indian Astronomical Ephemeris) to confirm which equinox
   the published values reference — this determines whether OPEN-1(a) is also the IAE convention.
3. Lagna against a reference for a high-latitude case (V07) — no independent anchor beyond the
   textbook formula used in `test_lagna.py`.

## OPEN-1 resolution record (2026-09-05)

Change applied: `get_ayanamsa_lahiri` now returns `swe.get_ayanamsa_ex_ut(jd, 0)[1]`. Nothing
else in `src/` changed (verified by diff: one function body + docstring). J2000 ayanamsha
23.85709235° → 23.85322249° (−13.93″). Reference Jalandhar chart: ayanamsha 23.790262° →
23.793222° (+10.65″); every sidereal longitude −10.65″; Lagna 339.798870° → 339.795911°;
Sun 336.168758° → 336.165799°; Moon 209.207371° → 209.204408°. No rashi, nakshatra, pada, house
or retrograde classification changed in the reference chart or in any of the 13 verification
case records (diffed before/after). Tests: 5 reference assertions updated to the new values, 3
loosened Layer-6 tolerances tightened to published/native values, 3 regression tests added
(accessor == `get_ayanamsa_ex_ut(jd,0)`; accessor != legacy `get_ayanamsa_ut`; engine sidereal ==
`SEFLG_SIDEREAL` native). Suite: 275 passed.

External comparison 1 — Jagannatha Hora published Lahiri table (00:00 UT, 1 Jan): 1900 +0.3″,
1943 +0.3″, 1950 +0.1″, 1988 +0.2″, 1990 −0.5″, 1995 +0.3″, 2000 −0.5″, 2003 0.0″, 2010 −0.1″,
2024 +0.1″, 2026 −0.5″ — all inside the table's whole-second rounding: exact agreement.

External comparison 2 — deva.guru full chart, Bharatpur 2003-12-09 04:00 IST at 27.21/77.29,
with deva.guru set to True Chitrapaksha + Mean Node: all nine grahas agree with the engine's
`SIDM_TRUE_CITRA` variant within 0.8″ (display rounding), Lagna within 2.4″ (place coordinate /
sub-second time difference). This proves the tropical positions, ascendant and true-equinox
frame; the Lahiri-mode full-chart comparison against deva.guru was not performed (authentication-gated
controls — see the freeze-gate record). Drik Panchang could not be fetched (HTTP 403).

Remaining known differences vs other software (conventions, not errors): True Chitrapaksha
zero-point ≈ 1′23″ from Lahiri; True Node vs Mean Node up to ~1.75°; place coordinates from
different geocoders shift the Lagna by seconds to minutes of arc.

## Freeze-gate attempt (2026-09-05, later)

Attempted the Lahiri/Mean-Node full-chart comparison on deva.guru in the browser pane
(Bharatpur 2003-12-09 04:00, coordinates 27.21/77.29 selected from its own autocomplete, IST):
the site computed the chart (True Citrā, Mean, ayanamsha display 23°53′34″), but its
`calc_ayanamsa_option` and `calc_nodes_mean_true_option` controls are rendered `disabled` for
anonymous visitors and the server ignores changes to them, so Lahiri mode requires a signed-in
account. No account was created or used. astro-seek.com ("Access forbidden") and
drikpanchang.com (positions table not rendered) refused automated access. The deva.guru Lahiri comparison was therefore not performed (see the freeze-gate decision below).

Freeze-gate decision (owner, 2026-09-05): the existing validation chain is accepted and the gate
is closed; no further external comparison is pursued. Evidence, stated precisely:

1. Jagannatha Hora's published Lahiri ayanamsha table agrees with the engine's accessor within
   0.5″ at all eleven tested dates (1 January 1900, 1943, 1950, 1988, 1990, 1995, 2000, 2003, 2010,
   2024, 2026; the table is printed to whole seconds).
2. Swiss Ephemeris' native `SEFLG_SIDEREAL` Lahiri longitudes agree with the engine's
   tropical-minus-ayanamsha values within 0.01″ at the five regression instants (Sun and Moon;
   `test_engine_sidereal_matches_swiss_ephemeris_native_sidereal`).
3. The deva.guru True-Citrā/Mean-Node chart (Bharatpur, 2003-12-09 04:00 IST, 27.21/77.29)
   supports the separately tested tropical-position, ascendant and true-equinox-frame chain.
   Per-body residuals against the engine's `SIDM_TRUE_CITRA` variant: Sun 0.8″, Moon 0.5″,
   Mercury 0.4″, Venus 0.1″, Mars 0.4″, Jupiter 0.5″, Saturn 0.8″, Rahu 0.3″, Ketu 0.3″;
   Lagna 2.4″. (deva.guru prints whole seconds; the Lagna residual includes any sub-second or
   sub-metre difference in its inputs.)

Direct Lahiri comparison with deva.guru was unavailable due to authentication-gated controls. It
was not performed, and no measured bound is claimed for it. Lahiri correctness is independently
validated against the published Lahiri reference (item 1) and the Swiss Ephemeris native sidereal
implementation (item 2). The specification is FROZEN v1.0 on this basis.

Independent freeze items completed this pass: `pyswisseph==2.10.3.2` pinned (F-5); F-1 resolved
by specification wording (§8); spec §2.1 records SE version/data assumptions and the Lahiri
true-equinox convention; full suite re-run from a freshly created virtual environment installing
only the pinned dependencies: 275 passed; `src/` changes since the 252-test freeze: exactly one
(`get_ayanamsa_lahiri`, approved OPEN-1) plus the dependency pin.
