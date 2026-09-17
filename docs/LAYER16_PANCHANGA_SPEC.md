# Layer 16 — Panchanga for an instant and a place

**Status:** SPECIFICATION v1.0 (promoted 2026-09-16 by the project owner after the
independent native-macOS verification recorded in §9). History: DRAFT v0.1 (2026-09-16),
DRAFT v0.2 (same day — sunrise bracketing, UTC normalisation, progress fractions, IMD
evidence). Nothing in this document changes the FROZEN v1.0 calculation specification
(`docs/CALCULATION_SPEC.md`); every existing calculation function, constant and golden is left
as it is. The conventions fixed at v1.0 and retained explicitly: the geometric Hindu sunrise
(§2.3, D2), the high-latitude limitations (§2.3, §3.2, §10), the Julian-Day boundary
semantics — `<=` on JD floats, JD equality is the new vara (§3.2, D5) — and the still-pending
external date-specific validation (§8, §10). Any change to a convention recorded here
requires a new specification version and owner approval.

## 1. Scope

Input: an exact instant (aware UTC `datetime`), a place (latitude north-positive,
longitude east-positive, IANA timezone identifier) — or an already assembled `BirthChart`,
which carries all four. Output: an immutable `Panchanga` holding the five classical
elements at that instant: **tithi**, **nakshatra**, **nitya yoga**, **karana** and **vara**,
plus the sunrise boundaries the vara was decided by and the conventions used.

Out of scope (not implemented, by decision): festivals, lunar-month or year naming
(masa, adhika, samvatsara), muhurta, Rahu Kalam and the other kalas, hora, transition
schedules (tithi/nakshatra end times), sunset/moonrise, UI, HTTP, viewer or CLI changes.

## 2. Sources and conventions

2.1 **Element definitions.** The four angular elements are the nirayana (sidereal)
definitions of the Rashtriya Panchang, as stated in the Positional Astronomy Centre's
published *Explanation* (retrieved 2026-09-16, §8): "Tithi is the time period during which
the moon gains 12 degrees or its integral multiples in longitude on the sun"; "Nakshatra is
the time taken by the moon to traverse a segment of 13° 20' or its integral multiples of
nirayana zodiac"; "Yoga is calculated from the sum of the nirayana longitudes of the sun and
moon. When this sum amounts to 13° 20' the first yoga ends"; "Karana is the time period
during which the moon gains 6 degrees in longitude on the sun … There are 7 karanas which
repeat in a cyclic order starting from 2nd half of sukla pratipada and ending at 1st half of
Krishna chaturdasi. There are 4 sthira or non-recurring karanas which cover the period from
2nd half of Krishna chaturdasi to 1st half of sukla pratipada"; and "the sunrise system of
reckoning the day has been followed in pursuance of the Indian convention":

| Element | Quantity | Division | Count |
|---|---|---|---|
| Tithi | elongation `E = (λ_Moon − λ_Sun) mod 360` | 12° | 30 |
| Nakshatra | Moon's sidereal longitude `λ_Moon` | 13°20′ (360/27) | 27 |
| Nitya yoga | `Y = (λ_Sun + λ_Moon) mod 360` | 13°20′ (360/27) | 27 |
| Karana | elongation `E` | 6° (half a tithi) | 60 per month, 11 names |
| Vara | weekday of the local civil date of the last sunrise at or before the instant | — | 7 |

`λ_Sun`, `λ_Moon` are the engine's **Lahiri sidereal** longitudes (FROZEN §4.3, §5). Tithi and
karana depend only on the difference of the two longitudes and are therefore the same in
the tropical and sidereal frames (up to floating-point rounding of the two normalisations);
the nitya yoga depends on the sum and is meaningful only in the sidereal frame — the
ayanamsha is not changed, and none is introduced.

The IMD page also states its ayanamsha basis: a "variable ayanamsa (also called increasing
ayanamsa)" whose initial point "coincides with that of vernal equinoctial point of vernal
equinox day of 285 A.D.", fixed by "the tropical longitude of this initial point … 23° 15'
00" for 0h on 21st March, 1956" — the Lahiri/Chitrapaksha definition the engine's FROZEN
`SIDM_LAHIRI` accessor implements (no equality of numerical values is claimed here; the
engine's own Lahiri validation is in `docs/CALCULATION_SPEC.md`). The sunrise flag set was
cross-checked against the Swiss Ephemeris source (`swecl.c`, `swephexp.h`, pyswisseph
2.10.3.2 sdist); the name tables against public references (§8).

2.2 **Numbering and names.** Every element carries a 0-based `index`, a 1-based `number`
and a stable lowercase ASCII `key`, plus the transliterated `name` used in this repository.

*Tithi* (`index` 0–29, `number` 1–30): 1–15 Shukla Pratipada … Purnima, 16–30 Krishna
Pratipada … Chaturdashi, Amavasya. `paksha` is `SHUKLA` for index 0–14 and `KRISHNA` for
15–29; `number_in_paksha` is `index % 15 + 1` (1–15 in each paksha; 15 = Purnima in Shukla,
Amavasya in Krishna). Names in order: Pratipada, Dwitiya, Tritiya, Chaturthi, Panchami,
Shashthi, Saptami, Ashtami, Navami, Dashami, Ekadashi, Dwadashi, Trayodashi, Chaturdashi,
then Purnima (15) / Amavasya (30).

*Nakshatra*: the FROZEN 27-name table `NAKSHATRA_NAMES` and the FROZEN pada rule, reused,
never restated.

*Nitya yoga* (`index` 0–26, `number` 1–27): Vishkambha, Priti, Ayushman, Saubhagya, Shobhana,
Atiganda, Sukarma, Dhriti, Shula, Ganda, Vriddhi, Dhruva, Vyaghata, Harshana, Vajra, Siddhi,
Vyatipata, Variyan, Parigha, Shiva, Siddha, Sadhya, Shubha, Shukla, Brahma, Indra, Vaidhriti.

*Karana* (`index` 0–59 within the lunar month, `number` 1–60, `half` FIRST/SECOND of its
tithi): four **fixed** (sthira) karanas occupy fixed slots and seven **repeating** (chara)
karanas cycle eight times through the remaining 56 half-tithis:

| slot `index` | tithi | karana | kind |
|---|---|---|---|
| 0 | Shukla Pratipada, first half | Kimstughna | fixed |
| 1 … 56 | Shukla Pratipada second half … Krishna Chaturdashi first half | Bava, Balava, Kaulava, Taitila, Garaja, Vanija, Vishti, repeating: `REPEATING[(index − 1) mod 7]` | repeating |
| 57 | Krishna Chaturdashi, second half | Shakuni | fixed |
| 58 | Amavasya, first half | Chatushpada | fixed |
| 59 | Amavasya, second half | Naga | fixed |

Check: 1 + 56 + 3 = 60; index 1 → Bava, index 56 → (55 mod 7 = 6) → Vishti. Each karana
record states `kind` (`FIXED` / `REPEATING`), its `cycle_position` (1–7 for repeating,
`None` for fixed) and the tithi it halves.

*Vara* (`index` 0–6 with **Sunday = 0**, `number` 1–7): Ravivara, Somavara, Mangalavara,
Budhavara, Guruvara, Shukravara, Shanivara; `english_weekday` Sunday … Saturday; `lord` is
the FROZEN `Graha` (Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn). Python's
`date.weekday()` is Monday = 0; the conversion is `(weekday + 1) % 7` and is tested.

2.3 **Sunrise convention (v1, "geometric Hindu rising").** Sunrise is the instant at which
the **centre of the solar disc** crosses the geometric horizon of the place, **without
atmospheric refraction**, using the **geocentric** position of the Sun with its ecliptic
latitude ignored, at **0 m** altitude. This is exactly Swiss Ephemeris' documented Hindu
rising:

```
rsmi   = SE_CALC_RISE | SE_BIT_HINDU_RISING
       = 1 | (SE_BIT_DISC_CENTER 256 | SE_BIT_NO_REFRACTION 512 | SE_BIT_GEOCTR_NO_ECL_LAT 128) = 897
geopos = (longitude_east, latitude_north, 0.0)     # order is the library's: lon, lat, alt
atpress = 0.0, attemp = 0.0                        # irrelevant: refraction is disabled
epheflag = SEFLG_SWIEPH
```

(`swephexp.h`: `#define SE_BIT_HINDU_RISING (SE_BIT_DISC_CENTER|SE_BIT_NO_REFRACTION|
SE_BIT_GEOCTR_NO_ECL_LAT)`; `swecl.c` comment: "risings according to Hindu astrology".
pyswisseph exposes `swe.BIT_HINDU_RISING == 896`; it does not expose the name
`BIT_GEOCTR_NO_ECL_LAT`, whose value 128 is confirmed from the header.)

**This deliberately differs from the Rashtriya Panchang.** The IMD *Explanation* states:
"In the calculation of sunrise and sunset, atmospheric refraction is included and the times
relate to the appearance and disappearance of the upper limb of the sun on the horizon …
The amount of horizontal refraction taken for the purpose is 31' and that of the sun's
semi-diameter is 16' so that at the moment when the upper limb of the sun is visible on the
horizon, the centre of the sun is actually 47' below the horizon, the time equivalent of
which is about 3.5 minutes." The geometric convention chosen here is therefore **later**
than the IMD sunrise (and than newspapers' astronomical sunrise) — by about 4 minutes at
Jalandhar and Jammu (measured against Swiss Ephemeris' own upper-limb refracted rising:
06:35:11 vs 06:31:05 IST on 1995-03-21; 07:27:37 vs 07:23:12 IST on 2001-02-04; Swiss
Ephemeris' refraction model differs slightly from IMD's fixed 31′). A birth in those
minutes gets a different vara here than in the Rashtriya Panchang. This is the owner's v1
choice, recorded as decision D2; no claim is made to match the Rashtriya Panchang's sunrise
column or any other almanac. Swiss Ephemeris uses its fast rise/set algorithm for the Sun at
|latitude| ≤ 65° and its slow search (28-hour window) beyond; the library notes that beyond
those limits "some risings or settings may be missed". Deliberately **not** used:
`SE_BIT_DISC_BOTTOM`, twilight bits, `SE_BIT_FIXED_DISC_SIZE`, `SE_BIT_FORCE_SLOW_METHOD`
(an Astrodienst in-house test flag), non-zero altitude, pressure or temperature.

2.4 **Time.** Any timezone-aware `datetime` is accepted; it is **normalised to UTC**
(`astimezone(timezone.utc)`) before anything is computed or stored, so `Panchanga.instant_utc`
always carries `tzinfo == timezone.utc` and two inputs naming the same instant in different
zones give equal results. All arithmetic is in UT (Julian Day from `julian_day_ut`, FROZEN
§3.3, UTC taken as UT1). The IANA zone is used for exactly one thing: the local civil date of the
previous sunrise, which names the vara. DST, historical offsets and date-line zones are
whatever the OS tzdata says for that zone at that sunrise instant (same rule as FROZEN
§3.2). A birth before local sunrise therefore takes the vara of the previous civil date's
sunrise even though its own civil date has already changed at midnight; a birth whose UTC
date differs from its local date is unaffected, because the civil date is read from the
sunrise instant in the place's zone, never from the UTC date and never from the birth's
own wall clock.

## 3. Architecture

New package `src/vedic_chart/panchanga/`:

| module | role | may import |
|---|---|---|
| `__init__.py` | the public surface (§5) | its own submodules only |
| `elements.py` | pure arithmetic on longitudes: tithi, yoga, karana; name tables; `normalize_longitude`/`classify` reused for nakshatra | stdlib `dataclasses`, `enum`, `math`, `typing`; `vedic_chart.vedic.divisions` (`classify`, `DivisionalPlacement`, `normalize_longitude`, `NAKSHATRA_SPAN`), `vedic_chart.vedic.grahas` (`Graha`) |
| `sunrise.py` | the sunrise **adapter**: bracket the instant between the previous and next geometric sunrise, convert to datetimes, decide the vara; typed unavailable result | stdlib `dataclasses`, `datetime`, `enum`, `math`, `typing`, `zoneinfo`; `vedic_chart.time.julian_day` (`julian_day_ut`, `UNIX_EPOCH_JD`, `SECONDS_PER_DAY`), `vedic_chart.time.local_time` (`InvalidTimezoneError`), `vedic_chart.ephemeris.swiss_ephemeris` (`calc_sunrise_hindu` only) |
| `compute.py` | composition: `calculate_panchanga` and `panchanga_from_chart` | the two modules above; `vedic_chart.chart.model` (`BirthChart`), `vedic_chart.vedic.grahas` (`Graha`), `vedic_chart.sidereal.positions` (`calculate_sidereal_positions`), `vedic_chart.astronomy.positions` (`Body`), `vedic_chart.time.julian_day` (`julian_day_ut`) |

Forbidden everywhere in the package (AST-tested, mirroring the dasha/viewer boundary
tests): `swisseph`, `vedic_chart.lagna`, `vedic_chart.location`, `vedic_chart.inputs`,
`vedic_chart.representation`, `vedic_chart.render`, `vedic_chart.dasha`, `vedic_chart.app`,
`vedic_chart.viewer`, `sqlite3`, `random`, `time`, `os`, `http`, `urllib`, `requests`,
`socket`; no `round()`; no clock (`now`, `utcnow`, `today`, `fromtimestamp`, `monotonic`).
Nothing under `vedic_chart` outside this package imports it (Layers 1–15 unchanged).

3.1 **The astronomy boundary gains one accessor.** `vedic_chart.ephemeris.swiss_ephemeris`
remains the only module importing `swisseph`. It gains

```python
RISE_HINDU_FLAGS = swe.CALC_RISE | swe.BIT_HINDU_RISING   # == 897

def calc_sunrise_hindu(julian_day_ut: float, latitude: float, longitude: float) -> float | None:
    """First geometric Hindu sunrise at or after ``julian_day_ut`` (JD UT), or None if the
    library reports that the Sun does not rise (return code -2)."""
```

It calls `calc_planet_position(julian_day_ut, SUN)` first, so the existing Moshier guard
(FROZEN §4.1) still refuses a missing/unsupported ephemeris before `swe.rise_trans` runs
(`rise_trans` does not report which ephemeris it used). Return code `0` → `tret[0]`;
`-2` → `None`; a library `swisseph.Error` propagates. No existing function in the module
is touched. This is an addition to the audited astronomy boundary and is flagged as such
for approval.

3.2 **Sunrise adapter algorithm** (`panchanga/sunrise.py`, `find_sunrise_window`).

What a `None` from the accessor means: for |latitude| ≤ 65° the library's fast method never
returns −2; beyond it the slow method searches a **28-hour window** from two hours before
the probe and returns −2 when that window holds no rising. A `None` therefore says "no
sunrise within ~28 h of this probe", **never** "no sunrise anywhere in the two-day span".
v0.1 treated the first probe's `None` as the latter and wrongly reported Tromsø
(69.65 N, 18.96 E) on 2026-01-19 15:00 UTC as unavailable although the Sun rose at
10:35:38 UTC that day (the first geometric-centre sunrise of the year there) and again at
10:15:37 UTC on the 20th. v0.2 probes the whole span:

```
t = JD UT of the instant; SPAN = 2.0; STEP = 0.5; MAX_GAP = 2.0
# phase A: the last sunrise at or before t
probe = t − SPAN; previous = None; following = None
repeat at most MAX_PROBES times while probe <= t:
    r = rise_after(probe)
    if r is None:          probe += STEP; continue          # nothing within the library window
    if r <= t:             require r > previous (progress); previous = r; probe = r + STEP; continue
    following = r; break                                    # first sunrise after t
# phase B: the next sunrise, when phase A ran off the end of the span before finding one
if previous is not None and following is None:
    probe = previous + STEP
    repeat at most MAX_PROBES times while probe <= previous + MAX_GAP:
        r = rise_after(probe)
        if r is None:      probe += STEP; continue
        require r > previous (progress)
        if r <= t:         previous = r; probe = r + STEP; continue   # a later previous the span missed
        following = r; break
```

`previous` is the vara boundary (**`r == t` counts as the new vara**: `<=` on JD floats);
`following` is the next sunrise. Each phase's loop is **bounded by a constant**
(`MAX_PROBES = 9`, an upper bound with margin: the library's slow search starts two hours
before its start time, so a found sunrise may precede its probe by up to 2 h and the
guaranteed advance per iteration is STEP − 2 h ≈ 0.417 d, at most 5 probes per phase).
Three run-time checks raise `RuntimeError`: a result not strictly past the previous
sunrise (progress), a result earlier than `probe − 0.25` d (backtrack), and bound
exhaustion. They are `if`/`raise` statements, not `assert`, so they survive `python -O`.
A half-day probe step cannot skip a sunrise, because consecutive sunrises are never less
than ~23 h apart.

The window is **unavailable** — a typed `SunriseUnavailable` result, never a 06:00 or
civil-weekday fallback — when `previous is None` (no sunrise in the two days up to the
instant, e.g. polar night, or Tromsø on 2026-01-18), when `following is None` (no sunrise
within two days after the previous one, e.g. the last sunrise before a polar night), or
when `following − previous > MAX_GAP` (the pair cannot be consecutive daily sunrises).
`rise_after` is injectable (default: the Layer 5 accessor) so the bracketing is testable
with exact synthetic JDs; the instant→JD conversion is the FROZEN `julian_day_ut`, and
equality "at exact sunrise" is defined on JD floats, not on microsecond datetimes. JD → `datetime` conversion
(`UNIX_EPOCH + timedelta(seconds=(jd − UNIX_EPOCH_JD) · 86400)`) is for presentation of the
boundaries and for the civil date only; the JDs are carried unchanged alongside.

3.3 **Where the longitudes come from.** `panchanga_from_chart(chart)` reads
`chart.grahas[Graha.SUN].sidereal_longitude`, `chart.grahas[Graha.MOON].sidereal_longitude`,
`chart.grahas[Graha.MOON].placement` (the nakshatra/pada object itself — reused, not
recomputed, so agreement with the frozen classification is by identity), `chart.moment_utc`,
`chart.julian_day_ut`, `chart.ayanamsa` and `chart.location`. It performs no planetary
ephemeris call. `calculate_panchanga(moment_utc, latitude, longitude, timezone_id)` obtains
the two longitudes through the existing Layer 6 `calculate_sidereal_positions` (one call,
same JD, same ayanamsha accessor as a chart) and classifies the Moon with the FROZEN
`classify`. Both paths make the same sunrise calls. Nothing parses SVG or rounded output;
nothing is recalculated that a chart already holds.

Ephemeris lifecycle is the caller's, as for `assemble_chart`: wrap calls in
`ephemeris_session(path)`.

## 4. Boundary arithmetic

4.1 Indices mirror the FROZEN nakshatra formula shape so the float behaviour is the same:

```
E = (moon − sun) % 360.0 ; Y = (sun + moon) % 360.0        # inputs already in [0, 360)
tithi_index  = int(E * 30.0 / 360.0)     # 0..29, guard-asserted (not clamped)
karana_index = int(E * 60.0 / 360.0)     # 0..59
yoga_index   = int(Y * 27.0 / 360.0)     # 0..26
nakshatra    = classify(moon)            # FROZEN rule 8/9
```

Intervals are half-open `[start, end)`; the unrounded value is classified; no epsilon
(FROZEN §6.3). Tithi and karana boundaries (multiples of 12° and 6°) are exactly
representable and classify exactly; yoga boundaries at 40k/3° share the FROZEN "float fact"
(exactly representable only when k is a multiple of 3, otherwise ambiguous by ~1 ULP).
`E == 0.0` is Shukla Pratipada / Kimstughna (new moon is the *start* of the month);
`E` just below 360 is Amavasya / Naga; `E == 180.0` is the start of Krishna Pratipada
(tithi index 15, karana index 30 → (29 mod 7 = 1) → Balava), and `nextafter(180, 0)` is
Purnima's second half (tithi index 14, karana index 29 → (28 mod 7 = 0) → Bava); the table
decides and the tests pin every slot. `karana_index == 2 * tithi_index + half` where
`half ∈ {0, 1}` — asserted.

4.2 **Raw offsets and progress fractions — two different quantities.** Each element
carries both, and they are defined differently on purpose:

* `degrees_in_<element>` is the **raw offset** `value − index · span`, the FROZEN Layer 7
  shape (`degrees_in_nakshatra` is copied from the chart's placement, never recomputed).
  At a non-representable boundary (40k/3°, k not a multiple of 3) the index — floored from
  `value · N / 360`, which rounds — and this offset — which does not — can disagree by one
  or two ULP, and the offset is then a few 10⁻¹⁴° *negative*. That is the frozen engine's
  documented float fact; it is inherited unchanged, not clamped, not nudged.
* `angular_fraction` is the **progress fraction** `scaled − index` where
  `scaled = value · N / 360.0` is the very quantity the index was floored from
  (`index = int(scaled)`). Because it is the fractional part of the same double, it lies in
  `[0, 1)` **exactly**, at every input, with no epsilon and no clamping — the subtraction of
  an integer from a non-negative double of larger magnitude is exact in IEEE arithmetic —
  and it is consistent with the index by construction. For the tithi and the karana, whose
  boundaries are exact, `angular_fraction == degrees_in / span` to rounding; for the yoga
  and the nakshatra the two differ only inside the ULP band above, where the raw offset is
  the negative one and the progress fraction is 0.0.
* The nakshatra's progress is computed from the Moon's longitude the chart carries:
  `scaled = normalize(λ_Moon) · 27 / 360.0`; `int(scaled)` is **required** to equal the
  placement's `nakshatra_index` (same FROZEN formula on the same double; a mismatch raises
  `RuntimeError`), and the placement object is still carried by identity.

All of these are **fractions of arc, not of time**: the tithi is not 12° of uniform
duration, and the fraction says nothing about when the element began or will end.

4.3 **Consistency.** `karana.tithi_index == tithi.index`; `nakshatra` equals
`chart.grahas[Graha.MOON].placement` for the from-chart path and `classify(moon)` for the
explicit path; `vara.sunrise is panchanga.sunrise`.

## 5. Public surface (`vedic_chart.panchanga`)

Types (all `@dataclass(frozen=True)`, all fully annotated):

* `Paksha(Enum)`: `SHUKLA`, `KRISHNA`. `KaranaKind(Enum)`: `FIXED`, `REPEATING`.
  `TithiHalf(Enum)`: `FIRST`, `SECOND`.
* `Tithi(index, number, key, name, paksha, number_in_paksha, elongation, degrees_in_tithi,
  angular_fraction)`.
* `Nakshatra(index, number, key, name, pada, degrees_in_nakshatra, degrees_in_pada,
  angular_fraction, placement: DivisionalPlacement)` — `placement` is the FROZEN object.
* `NityaYoga(index, number, key, name, sum_longitude, degrees_in_yoga, angular_fraction)`.
* `Karana(index, number, key, name, kind, cycle_position, tithi_index, half,
  degrees_in_karana, angular_fraction)`.
* `Vara(index, number, key, name, english_weekday, lord: Graha, sunrise: SunriseWindow)`.
* `SunriseWindow(previous_utc, next_utc, previous_julian_day_ut, next_julian_day_ut,
  previous_local, next_local, convention: str)`; `SunriseUnavailable(reason: str,
  latitude, longitude, searched_from_utc, searched_to_utc, convention: str)`.
* `PanchangaLocation(latitude, longitude, timezone_id, provenance: LocationProvenance)` with
  `LocationProvenance(Enum)`: `BIRTH_CHART`, `EXPLICIT`.
* `Panchanga(instant_utc, julian_day_ut, local_datetime, location, sun_sidereal_longitude,
  moon_sidereal_longitude, ayanamsa, longitudes_source: LongitudeSource, tithi, nakshatra,
  yoga, karana, vara: Vara | None, sunrise: SunriseWindow | SunriseUnavailable,
  calculation_convention: str, sunrise_convention: str)` with `LongitudeSource(Enum)`:
  `BIRTH_CHART`, `COMPUTED`. `instant_utc.tzinfo` is always `timezone.utc`. `vara is None`
  **iff** `sunrise` is a `SunriseUnavailable`.
  `Panchanga.sunrise_available -> bool` property.

Functions:

* `calculate_panchanga(moment_utc: datetime, latitude: float, longitude: float,
  timezone_id: str) -> Panchanga` — any aware datetime accepted and normalised to UTC
  (§2.4; naive → `ValueError` from Layer 4); coordinates validated like `calculate_lagna`
  (`ValueError`) and the zone (`InvalidTimezoneError`) before any ephemeris call.
* `panchanga_from_chart(chart: BirthChart) -> Panchanga`.
* `find_sunrise_window(moment_utc, latitude, longitude, timezone_id, *, rise_after=...)
  -> SunriseWindow | SunriseUnavailable` — the adapter, exposed for callers who need only
  the boundaries.
* Name tables (tuples): `TITHI_NAMES`, `YOGA_NAMES`, `KARANA_REPEATING_NAMES`,
  `KARANA_FIXED_NAMES`, `VARA_NAMES`, `VARA_LORDS`; constants `CALCULATION_CONVENTION`
  and `SUNRISE_CONVENTION` (the exact strings carried in every result, naming Lahiri
  sidereal longitudes, the divisions, and the 897 flag set).
* Errors: `InvalidTimezoneError` (re-exported from Layer 3), `ValueError` for coordinates
  and naive instants. Sunrise unavailability is a **result**, not an exception.

Usage:

```python
from datetime import date, time
from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.time.local_time import normalize_birth_time
from vedic_chart.panchanga import calculate_panchanga, panchanga_from_chart

moment = normalize_birth_time(date(1995, 3, 21), time(6, 45), "Asia/Kolkata")
with ephemeris_session("ephe"):
    p = calculate_panchanga(moment, 31.32556, 75.57917, "Asia/Kolkata")
p.tithi.name, p.tithi.paksha, p.tithi.number_in_paksha     # 'Panchami', Paksha.KRISHNA, 5
p.nakshatra.name, p.nakshatra.pada                          # 'Vishakha', ...
p.yoga.name, p.karana.name, p.karana.kind                   # 'Harshana', 'Kaulava', KaranaKind.REPEATING
p.vara.name if p.vara else p.sunrise.reason                 # 'Mangalavara'
p.sunrise.previous_local                                    # 1995-03-21 06:35:11+05:30

# From a chart the engine already built (no planetary ephemeris call):
with ephemeris_session("ephe"):
    chart = assemble_chart(request, resolver)
    p2 = panchanga_from_chart(chart)
assert p2.nakshatra.placement is chart.grahas[Graha.MOON].placement
```

## 6. Tests (`tests/test_panchanga_elements.py`, `tests/test_panchanga_sunrise.py`,
`tests/test_panchanga_compute.py`, `tests/test_panchanga_boundaries.py`)

Pure arithmetic: every tithi/yoga/karana index at the start of its interval, at
`nextafter(start, −∞)` (previous division) and at `nextafter(start, +∞)`; the 0°/360° seam
(`E = 0.0`, `nextafter(360, 0)`, negative inputs normalised); complete name cycles and the
karana table (all 60 slots, fixed vs repeating, cycle positions, `2·tithi + half`); paksha
and number-in-paksha for all 30; angular fractions in `[0, 1)`; the vara table and the
Monday-0 → Sunday-0 conversion for all seven days.

Sunrise adapter with an injected `rise_after`: instant before / exactly at / just after a
sunrise (`<=` semantics with exact floats and `nextafter`); the two-day bracketing; a
`None` at the first probe with a sunrise later in the span (synthetic) and the real Tromsø
regression (2026-01-19 15:00 UTC, 69.65 N 18.96 E, Europe/Oslo: previous 10:35:38 UTC,
next 2026-01-20 10:15:37 UTC, vara Somavara); genuine unavailability, real (Tromsø
2026-01-18 and 2026-12-01, 80 N in June and December) and synthetic; the progress and
bound checks raising `RuntimeError` on a stuck or backward fake; the three unavailable
reasons; local-date naming across a UTC/local date difference
(Asia/Kolkata early morning = previous UTC date), a DST zone (Europe/London or
America/New_York on a transition day) and a date-line zone (Pacific/Kiritimati); invalid
zone, naive instant, out-of-range coordinates.

Live ephemeris (Jalandhar 1995-03-21 06:45 IST, Jammu 2001-02-04 10:45 IST): the
from-chart and explicit paths produce equal elements; the nakshatra object is the chart's;
the sunrise pair brackets the instant, is ~1 day apart and lies within a few minutes of
the astronomical sunrise computed with the plain `CALC_RISE` flags (sanity, not a golden);
new-moon and full-moon dates from the ephemeris itself (elongation crossing 0°/180°) give
tithi index 0 / 15 immediately after and 29 / 14 immediately before; a polar case
(latitude 80°, June and December) yields `SunriseUnavailable` and `vara is None` with the
four angular elements still present.

Invariants: immutability of every result type; the import boundary (AST); `swisseph` is
still imported only by `swiss_ephemeris.py`; packaging unchanged; the existing chart/app/
viewer outputs unchanged (the whole existing suite, run before and after in the same
environment, with pre-existing environment-dependent failures listed separately).

## 7. Decisions (D1–D5, approved with v1.0)

D1 — the astronomy boundary gains `calc_sunrise_hindu` (§3.1): additive, but it is a change
to the audited Layer 5 module. D2 — sunrise convention: geometric Hindu rising, flags 897,
0 m, geocentric, no refraction (§2.3); differs from upper-limb almanacs by minutes.
D3 — unavailable sunrise is a typed result inside `Panchanga` (`vara = None`), not an
exception, so polar births still get the four angular elements. D4 — the two-day bracketing
rule and the "consecutive sunrises ≤ 2 days apart" check (§3.2). D5 — a birth exactly at
sunrise (JD equality) belongs to the new vara. None of these touches an existing
convention; none adds a dependency. All five were accepted by the owner at promotion.

## 8. Evidence record

| Claim | Source | Status |
|---|---|---|
| Tithi 12°, nakshatra 13°20′ nirayana, yoga = sum of nirayana longitudes in 13°20′ steps, karana 6° with the 7 + 4 slot rule, day reckoned from sunrise | Positional Astronomy Centre, IMD, *Rashtriya Panchanga — Explanation*, https://packolkata.imd.gov.in/panchang/en/explanation | **Retrieved and quoted** 2026-09-16 (§2.1) |
| IMD sunrise = upper limb, refraction included (31′ + 16′ = 47′, ≈ 3.5 min) | same page | **Retrieved and quoted** (§2.3); our convention deliberately differs |
| IMD ayanamsha = variable, initial point 23°15′00″ tropical at 0h 21 March 1956 (285 A.D. equinox) | same page | Retrieved; identified as the Lahiri definition, numerical agreement not claimed here |
| `SE_BIT_HINDU_RISING = DISC_CENTER 256 \| NO_REFRACTION 512 \| GEOCTR_NO_ECL_LAT 128`; fast method ≤ 65° (Sun), slow method 28 h window, −2 = not found | Swiss Ephemeris 2.10.03 source in the pyswisseph 2.10.3.2 sdist: `libswe/swephexp.h` 336–361, `libswe/swecl.c` (`swe_rise_trans`, `rise_set_fast`, `swe_rise_trans_true_hor`) | **Retrieved** (PyPI sdist) |
| Hindu sunrise at Jalandhar/Jammu vs an independent geometric-centre altitude bisection (apparent geocentric longitude, true obliquity, sidereal time) | computed in this work | agrees to < 1 ms (same ephemeris, different rise algorithm; not an external almanac) |
| 60-slot karana table (Kimstughna slot 0; Shakuni, Chatushpada, Naga slots 57–59) | IMD page (the 7 + 4 rule) and Wikipedia "Karaṇa (pañcāṅga)" | consistent |
| 27 nitya-yoga names in order | vedictime.com nitya-yoga list; secondary | name table only |
| Hindu (disc-centre, no refraction) vs astronomical sunrise as a general practice | drikpanchang FAQ "Hindu Sunrise and Hindu Sunset"; secondary | background only |
| New moon 2024-01-11 ≈ 11:57 UTC and full moon 2024-01-25 ≈ 17:54 UTC as published values | not retrieved | **UNVERIFIED** — recollected only; the engine's own crossings (11:57:24 and 17:54:00 UTC) are recorded, but no external source was fetched, so no agreement is claimed |
| Rashtriya Panchang's printed tithi/nakshatra/yoga/karana for any specific date | not retrieved | not compared |

## 9. Validation record at v1.0

Three environments, recorded separately; none is a substitute for another.

| Environment | What was run | Result |
|---|---|---|
| **Native macOS** (owner's machine, Python 3.11.16 Darwin arm64 environment; run and reported by the owner) | Targeted: the four Panchanga test files (`tests/test_panchanga_*.py`), normally and under `python -O`; the three regressions of the v0.2 correction pass checked directly — Tromsø 2026-01-19 15:00 UTC bracketing, UTC normalisation of non-UTC aware instants, progress fractions at inexact yoga boundaries | 813 passed normally; 813 passed under `-O`; all three regressions confirmed. **Targeted testing only — not a full-suite native run, and not claimed as one.** |
| **Session VM** (Linux aarch64, project `.venv` Python 3.10.12) | Full suite, baseline before Layer 16 and updated after it, same environment, uncommitted planetary-API work present in both | baseline 2681 passed / 0 failed; updated 3494 passed / 0 failed; the four Panchanga files 813 passed under `python -O` |
| **Cloud sandbox** (Linux x86_64, Python 3.11.15) | Full suite, baseline and updated, same environment | baseline 2669 passed / 12 failed; updated 3482 passed / 12 failed — the identical 12 pre-existing environment-dependent golden failures (8 `test_dasha_from_chart`, 2 `test_dasha_table`, 2 `test_viewer_transport`), no new failures; 813 passed under `-O` |

Reference outputs reproduced in all three environments: Jalandhar 1995-03-21 06:45 IST →
Krishna Panchami (20), Vishakha pada 3, Harshana (14), Kaulava (39), Mangalavara, sunrise
06:35:11 IST; Jammu 2001-02-04 10:45 IST → Shukla Ekadashi (11), Mrigashira pada 1,
Indra (26), Vanija (21), Ravivara, sunrise 07:27:37 IST; Tromsø 2026-01-19 15:00 UTC →
Somavara, previous sunrise 10:35:38 UTC, next 2026-01-20 10:15:37 UTC.

## 10. Limitations retained at v1.0

* **Sunrise convention.** Geometric Hindu rising (disc centre, no refraction, geocentric,
  0 m; flags 897). Deliberately different from the Rashtriya Panchang (upper limb,
  refraction; §2.3) and from newspapers' astronomical sunrise, by minutes. **No universal
  almanac compatibility is claimed**; a birth within those minutes of sunrise may receive a
  different vara here than in a given almanac.
* **High latitudes.** Beyond |65°| Swiss Ephemeris uses its slow search, which it documents
  as possibly missing some risings; the two-day probing (§3.2) mitigates but cannot prove
  completeness. Polar day and night, and the days around the first/last sunrise of a polar
  season, yield the typed `SunriseUnavailable` result with `vara = None`. The two-day span,
  the two-day consecutive-gap rule and the quarter-day backtrack tolerance are v1
  conventions (D4).
* **Boundary semantics.** Vara boundaries are decided on Julian-Day floats (UT, UTC taken as
  UT1): a birth whose JD equals the sunrise JD begins the new vara; the datetime forms are
  presentation only. Yoga and nakshatra boundaries at 40k/3° (k not a multiple of 3) carry
  the FROZEN float fact: the raw `degrees_in_*` offset can be a few 10⁻¹⁴° negative there
  while the progress `angular_fraction` is exactly 0.0 (§4.2).
* **External validation is incomplete.** The IMD definitions were retrieved and quoted
  (§2.1, §2.3). The Rashtriya Panchang's printed elements for specific dates have **not**
  been compared; the 2024 lunar-phase times remain **unverified** recollections; the only
  sunrise cross-checks are Swiss Ephemeris' own upper-limb mode and an independent
  altitude bisection on the same ephemeris (§8). Date-specific external validation is
  **pending** and is not claimed.
* **Environment sensitivity.** Sun/Moon longitudes differ between platforms at ~10⁻¹²°
  (the engine's documented property); sunrise seconds and historical-date local dates
  depend on the Swiss Ephemeris build and the installed tzdata. No golden was regenerated
  or relaxed for Layer 16.
* **Out of scope** remains as §1: festivals, masa/adhika/samvatsara naming, muhurta, Rahu
  Kalam, hora, transition times, sunset, moonrise, and any viewer, CLI or HTTP surface.
