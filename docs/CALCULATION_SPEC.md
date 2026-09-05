# AstroLearn Calculation Specification — FROZEN v1.0

**Status:** FROZEN v1.0, approved by the project owner on 2026-09-05. Produced by the Core Engine
Audit against the engine at 275 passing tests. This document states what the engine *implements*,
convention by convention, at the precision the code actually uses. Any change to a convention
recorded here requires a new specification version and owner approval.

**External validation recorded at freeze (see `docs/CORE_ENGINE_AUDIT.md` for detail):**
Jagannatha Hora's published Lahiri ayanamsha table agrees with the engine's accessor within
0.5″ at the eleven tested dates (1 January of 1900, 1943, 1950, 1988, 1990, 1995, 2000, 2003,
2010, 2024, 2026); Swiss Ephemeris' native `SEFLG_SIDEREAL` sidereal longitudes agree with the
engine within 0.01″ at the five regression instants (Sun and Moon); the deva.guru True-Citrā
comparison (Bharatpur, 2003-12-09 04:00 IST, 27.21/77.29) supports the separately tested
tropical-position, ascendant and reference-frame chain with per-body residuals of Sun 0.8″,
Moon 0.5″, Mercury 0.4″, Venus 0.1″, Mars 0.4″, Jupiter 0.5″, Saturn 0.8″, Rahu 0.3″, Ketu 0.3″
and Lagna 2.4″ against the engine's `SIDM_TRUE_CITRA` variant. A direct Lahiri comparison with
deva.guru was unavailable because its ayanamsha and node controls are authentication-gated; it
was not performed and no bound is claimed for it. Lahiri correctness is independently validated
against the published Lahiri reference and the Swiss Ephemeris native sidereal implementation.

Nothing in this document is a proposal; every statement was verified against the source and
by execution during the audit.

## 1. Scope

Input: a birth date, a naive local wall-clock time, and a free-text place query.
Output: an immutable `BirthChart` containing the resolved place, the exact UTC instant, the
Julian Day, the Lahiri ayanamsha, the sidereal Lagna, nine graha placements (sidereal
longitude, rashi, nakshatra, pada, degrees within each, longitudinal speed, retrograde flag)
and Whole Sign house numbers. Nothing else is computed (§10).

## 2. Software and data versions (as audited)

| Component | Version / identity |
|---|---|
| Python | 3.10.12 |
| pyswisseph | 2.10.3.2 (pinned in `pyproject.toml`, 2026-09-05) |
| Swiss Ephemeris C library | 2.10.03 |
| Ephemeris data files | `sepl_18.se1` (484,061 B), `semo_18.se1` (1,304,771 B), `seas_18.se1` (223,004 B); coverage 1800-01-01 … 2399-12-31 |
| timezonefinder | 8.2.0 (pinned); bundled boundary data "as bundled with timezonefinder 8.2.0 (444 timezone names)", ODbL |
| OS tzdata (Layer 3 rules) | 2026c (`tzdata 2026c-0ubuntu0.22.04.1`) |
| GeoNames dump | 2026-09-04 daily dump; six official files, SHA-256 recorded in `dataset_metadata` and `data/DATA_SOURCES.md` |
| Geodata DB | `data/geodata.sqlite`, 786,552 places (cities500 global + all P-class India) |

2.1 **Explicit assumptions.** (a) All astronomy is Swiss Ephemeris 2.10.03 via pyswisseph 2.10.3.2;
positions come from the three `.se1` files above (JPL-DE431-derived), never the Moshier fallback,
and the engine refuses dates outside 1800–2399 rather than degrading. (b) The Lahiri ayanamsha is
`SIDM_LAHIRI` evaluated with `swe.get_ayanamsa_ex_ut(jd, 0)`: **true equinox of date, nutation
included** (§4.3). (c) Time-zone rules are the OS tzdata (2026c at freeze); historical results
depend on that database. (d) Timezone geometry is timezonefinder 8.2.0's bundled boundary data.
(e) Place data is the GeoNames dump of 2026-09-04. Rebuilding any of these inputs may change
outputs at the arcsecond level and must be recorded in `data/DATA_SOURCES.md`.

## 3. Time

3.1 **Input validation (Layer 1).** `birth_date` must be a `datetime.date` and not a `datetime`;
`birth_time` a naive `datetime.time` (tzinfo forbidden); `place_query` a non-blank string stored
verbatim. Raw components go through `BirthChartRequest.from_components`, which converts
impossible dates/times into `InvalidBirthDateError` / `InvalidBirthTimeError`.

3.2 **Timezone normalization (Layer 3).** The IANA identifier comes only from place resolution.
Rules come from the OS tzdata via `zoneinfo`; historical offsets (e.g. India +06:30 in
1942–45, Britain +02:00 BDST in 1943, London LMT −00:01:15 before 1847-12-01) are whatever
tzdata says. A wall time in a DST gap raises `NonexistentLocalTimeError`; a wall time in a
fall-back overlap raises `AmbiguousLocalTimeError`. Nothing is ever silently disambiguated.
Seconds and microseconds are preserved exactly.

3.3 **Julian Day (Layer 4).** `JD_UT = unix_timestamp / 86400 + 2440587.5` on the UTC instant.
Verified identical to `swe.julday` (Gregorian) to 0.000000 s across 1850–2399. Two documented
approximations: UTC is used as UT1 (|ΔUT1| ≤ 0.9 s, ≤ 0.00015° even for the Moon); the calendar
is proleptic Gregorian.

## 4. Astronomy (Layer 5 — the only module importing `swisseph`)

4.1 **Planetary positions.** `swe.calc_ut(jd_ut, body, SEFLG_SWIEPH | SEFLG_SPEED)`. This yields
**geocentric apparent** ecliptic longitude/latitude/distance and their rates, referred to the
**true equinox and ecliptic of date** (light-time, annual aberration and gravitational
deflection applied; nutation included). Measured at J2000 for Mars: removing light-time
changes longitude by 29.8″, aberration 14.1″, nutation 13.9″, deflection 0.005″. If the
`.se1` files are not used (date outside 1800–2399, or files missing) the engine raises
`RuntimeError` rather than accepting the Moshier fallback.

4.2 **Bodies.** Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Mean Node, True Node are
computed. The standard chart uses the **Mean Node**; the True Node is computed and exposed but
not consumed by any chart.

4.3 **Ayanamsha (audit item OPEN-1, CLOSED 2026-09-05).** `get_ayanamsa_lahiri(jd)` calls
`swe.set_sid_mode(SIDM_LAHIRI, 0, 0)` on every call (global library state is never trusted), then
returns `swe.get_ayanamsa_ex_ut(jd, 0)[1]`: the Lahiri/Chitrapaksha ayanamsha referred to the
**true equinox of date, nutation included** — the same frame as the apparent tropical
longitudes (4.1) and apparent ascendant (4.4). Consequently engine sidereal longitudes equal
Swiss Ephemeris' native `SEFLG_SIDEREAL` Lahiri output (regression-tested to < 0.01″ for Sun and
Moon at five instants) and the accessor matches Jagannatha Hora's published Lahiri table at
00:00 UT on 1 January of 1900, 1943, 1950, 1988, 1990, 1995, 2000, 2003, 2010, 2024 and 2026
to within the table's whole-second rounding (worst |Δ| = 0.5″). J2000 value: 23.853222°
(23°51′11.5″). The legacy `swe.get_ayanamsa_ut` (mean-equinox value, = `get_ayanamsa_ex_ut(jd,
SEFLG_NONUT)`, 23.857092° at J2000) is deliberately not used; a regression test asserts the
engine value differs from it by the nutation in longitude (< 18″) at every representative date.
Note: this is *Lahiri* (SE `SIDM_LAHIRI`), not *True Chitrapaksha* (`SIDM_TRUE_CITRA`), which
fixes Spica at 180° and currently differs by about 1′23″; some software (e.g. deva.guru's
default) uses the latter.

4.4 **Ascendant.** `swe.houses_ex(jd_ut, latitude, longitude, b"W")`, taking `ascmc[0]` —
the apparent tropical ascendant (true obliquity). The twelve returned cusps are discarded and
never used. Argument order (latitude before longitude) verified against an independent
textbook formula to ≤ 0.004° at five sites.

## 5. Sidereal conversion (Layer 6)

`sidereal_longitude = (tropical_longitude − ayanamsha) mod 360`, one implementation, used for
planets and the Lagna. The ayanamsha is obtained once per instant at the same JD as the
positions; assembly raises `RuntimeError` if the Lagna's and the planets' ayanamsha ever
differ. Latitude, distance and speeds are carried in the tropical frame unchanged (the
ayanamsha rate, ~0.000038°/day, is deliberately not applied to speeds). 

## 6. Vedic classification (Layer 7) — the locked 15-rule AstroLearn spec

6.1 Rahu = Mean Node sidereal longitude; **Ketu = (Rahu + 180) mod 360**, inheriting Rahu's
speed. Retrograde for every graha is `speed_longitude < 0.0`; with the Mean Node this yields
the classical always-retrograde nodes as a consequence, not a rule. Speeds are kept in the data.

6.2 Rashi: 12 × 30° from 0° sidereal Mesha; `rashi_index = int(lon // 30.0)` (0-based),
number = index + 1, Sanskrit names Mesha … Meena.
Nakshatra: 27 × 13°20′ from Ashwini; `nakshatra_index = int(lon * 27.0 / 360.0)`.
Pada: `pada = int(lon * 108.0 / 360.0) % 4 + 1`.
Degrees within each division are full-precision remainders. The 28-nakshatra/Abhijit scheme is
not implemented.

6.3 Boundary semantics: longitudes are normalized with `% 360.0` before classification; every
interval is half-open `[start, end)`; classification uses the unrounded value; no epsilon or
clamping is applied. Float fact: nakshatra/pada boundaries at 40k/3° are exactly representable
only when k is a multiple of 3; for the others the nearest float lies below the true boundary
and classifies into the earlier division — an ambiguity of ~1 ULP (~6 × 10⁻¹⁴°) that no
ephemeris precision can reach. Verified live: the Sun at 359.999660° classifies Meena/Revati
and 60 s later at 0.000340° classifies Mesha/Ashwini (verification case V08).

6.4 Retrograde station: the flag flips at speed exactly 0. Measured at the Mercury station of
2024-04-01 22:14:30 UTC: speed +8.2 × 10⁻⁵ °/day one minute before (direct), −8.2 × 10⁻⁵ one
minute after (retrograde). A birth within ~1 minute of a station is classified by the sign of a
speed below 10⁻⁴ °/day; this is documented, not smoothed.

## 7. Lagna and houses

7.1 Sidereal Lagna = (apparent tropical ascendant − ayanamsha) mod 360, classified with §6.2.
7.2 Whole Sign: `house = (graha_rashi_index − lagna_rashi_index) mod 12 + 1`; the Lagna's sign
is house 1 regardless of its degree. House cusps are never used.
7.3 Polar caveat: above ~66.5° latitude the ascendant is defined but moves highly non-uniformly
and some ecliptic degrees never rise; values are returned as computed (verified at ±89° and 90°
without error). No special handling.

## 8. Place resolution (Layer 2, offline)

Zero runtime network (enforced by AST tests and a socket-disabled runtime test). Query
normalization: casefold, NFKD with combining marks removed, whitespace collapsed, edge
punctuation stripped; identical function at import and query time. Comma-split: place token +
qualifiers matched against country (incl. ISO codes and a documented alias map), admin1, admin2.
Ranking (all in `RankingConfig`): feature-code weight + 1.5·log10(population + 1) + name-kind
bonuses (+1.0 official, +0.8 ASCII, +0.6 preferred, +0.2 short, −0.5 colloquial, −2.0 historic)
+ 5.0 per matched qualifier. **Dominance policy:** candidates are *materially different* when
(country, admin1) differ. With no materially different rival the top candidate is chosen. Else
auto-pick requires the top candidate's feature code to be a live settlement code (PPLC, PPLA–
PPLA5, PPLG, PPL, PPLS, PPLL, PPLX, PPLR — never PPLW/PPLQ/PPLH), and then either (i) it is the
only candidate with a capital code (PPLC), or (ii) its population ≥ 1000 and
(pop_top + 1)/(pop_rival + 1) ≥ 50, where *rival* is the highest-**ranked** (by score) materially
different candidate — not necessarily the most populous one, since score also carries feature-code
and name-match terms (audit finding F-1; documented behaviour, not redesigned). Otherwise
`AmbiguousPlaceError` with ranked candidates.
Every automatic dominance decision is recorded in `ResolutionDecision`. Coordinates are
north-/east-positive degrees. Timezone: `timezonefinder.timezone_at(lng=, lat=)`; `None` or
`Etc/*` results raise `TimezoneLookupError`; the id is validated with `zoneinfo`. UTC offsets are
never stored.

## 9. Precision and immutability policy

No value in the calculation path is rounded; the only `round()` in `src/` is on a geocoder
ranking score. DMS/degree rounding is a display concern and no display layer exists.
`BirthChartRequest`, `ResolvedLocation`, `PlaceCandidate`, `DivisionalPlacement`,
`GrahaPosition`, `Lagna`, `RankingConfig`, `ResolutionDecision` and `BirthChart` are frozen;
`BirthChart.grahas`/`.houses` are `MappingProxyType` views over private copies. The
intermediate `PlanetPosition`, `SiderealBodyPosition`, `SiderealPositions` are plain
(mutable) dataclasses; none of them is reachable from a `BirthChart`.

## 10. Out of scope (not implemented, by decision)

Aspects, dashas, yogas, divisional charts beyond D1 placement data, house cusps and any
non-Whole-Sign system, interpretation, display/DMS formatting, HTTP/API endpoints, persistence,
True-Node charts, outer planets, the Abhijit scheme, and any online geocoding. Global-tier
alternate names (non-India) are not loaded; exonyms for non-Indian places may not resolve.
