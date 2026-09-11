# Layer 12 — Vimshottari daśā core — SPECIFICATION v1.0

**Status:** v1.0 — **APPROVED.** Implemented against DRAFT v0.2 and promoted after the
implementation review recorded in §13; v1.0 differs from v0.2 only in the adapter wording of §5
and §8 (the cross-check reads the returned timeline), the documented guards of §7, and the new
§13. Layers 1–11 (frozen calculation
contract `docs/CALCULATION_SPEC.md` v1.0 at `2b3a5a9`; Layer 9 `5f076fd`; Layer 10 `e6c60b5`;
Layer 11 `11e8881`) are unchanged by this milestone and must remain so; in particular **Layer 7
(`vedic_chart.vedic.divisions`) is not modified** even where §5 reports an arithmetic tension
with it.

**Owner decisions carried into this draft.** Scope (approved 2026-09-11): standard Moon-based
Vimshottari; Mahādaśā, Antardaśā and Pratyantardaśā (three levels); own-lord-first subdivision of
the **full** parent period including its pre-birth portion; two explicit year conventions,
`FIXED_365_25` and `FIXED_365_256363`, the convention a **required argument with no implicit
default**; `fractions.Fraction` for nominal durations and offsets, with the conversion from the
input longitude defined exactly (§5–§6); no renderer, CLI integration, alternate starting bodies,
compressed cycles, Tribhāgi or other variations. Decisions closed in v0.2: **D1** the elapsed
fraction is derived from the same normalised float product frozen Layer 7 floors; **D2** every
offset is floored to integer microseconds from the birth anchor, negative offsets included;
**D3** out-of-cycle queries raise `DashaRangeError`; **D4** no `remaining_at` convenience for now;
**D5** independent absolute-date validation stays pending — duration agreement alone is
insufficient (§2, §10).

## 1. Scope and non-goals

In scope: a pure package `vedic_chart.dasha` computing, from one Moon sidereal longitude and one
birth instant, the Vimshottari timeline of one cycle at three levels, with exact nominal
arithmetic and one documented quantization to `datetime`; a thin adapter that reads those two
inputs from a Layer 8 `BirthChart`; tests.

Out of scope (recorded, not open): sūkṣma and prāṇa levels; starting bodies other than the Moon
(Kṣema/Utpanna/Ādhāna tārās, Lagna, other grahas); compressed ("1–6 year") cycles; reversed or
"previous lord" sub-orders; Tribhāgi; savana (360), tropical, anomalistic or synodic years;
event/transit overlays; any rendering (the D1 SVG renderer of Layer 10 is not touched and gains
no daśā output); any `vedic_chart.app` change (no `--dasha` flag); interpretation of periods.

## 2. Evidence base: classical rule, observed behaviour, inference

Three kinds of statement are kept apart throughout this document.

**(C) Classical rule** — Bṛhat Parāśara Horā Śāstra, R. Santhanam's translation (vol. 2), as
available at
<https://archive.org/stream/BPHSEnglish/BPHS%20-%202%20RSanthanam_djvu.txt>: Ch. 46 "Dasas
(Periods) of Planets", vv. 12–14 ("Beginning from Krittika the lords of Dasas (periods) are the
Sun, the Moon, Mars, Rahu, Jupiter, Saturn, Mercury, Ketu and Venus in that order", with the years
6, 10, 7, 18, 16, 19, 17, 7, 20), v. 15 (120 years as the Kali-yuga life span, hence Vimshottari
"the most appropriate"), v. 16 (balance at birth: the lord's years × the expired part of the
nakṣatra ÷ the nakṣatra span, subtracted from the full years); the antardaśā computation chapter
(Ch. 51 in that numbering; Ch. 52 "The Chapter on Computing the Antardaśā" in the VedicSpace
numbering at <https://vedicspace.com/bphs/52>) and the pratyantar/sūkṣma chapters (61–63) give
the proportional rule and own-lord-first order. Secondary restatements used for cross-checking:
Wikipedia "Dasha (astrology)" <https://en.wikipedia.org/wiki/Dasha_(astrology)> (table of lords,
years and nakṣatras; "calculated on pro-rata basis in proportion of the years allotted to them in
the 120 years cycle"; its cited claim that the year is "the astronomical solar year of 365.25
days"); astrosutras <https://astrosutras.in/index.php/2025/03/04/vimshottari-dasha-system-in-brihat-parashara-hora-shastra-bphs/>
(balance formula); Saptarishis Astrology, "Observations on the Vimshottari Dasha System, Part I"
<https://saptarishisastrology.com/observations-on-the-vimshottari-dasha-system-part-i-by-s-s-kakatkar/>
(notes that a 360-day year changes periods only slightly). The classical text fixes the lords, the
years, the nakṣatra cycle, the proportional subdivision and its order; it does **not** fix the
length of a "year" in days, and secondary sources disagree (365.25 vs 360).

**(O) Observed behaviour of deva.guru** (public, login-free chart auto-generated for
2026-09-11 04:33:15 PDT, Fremont; inspected 2026-09-11 with the built-in browser; every setting
control was disabled without login, so nothing was changed): <https://deva.guru/> settings form —
`Daśā: Viṁśottarī`; `Starting from: Mo` selected among Kṣema(4)/Utpanna(5)/Ādhāna(8)/Lagna/
Su/Mo/Ma/Me/Jp/Ve/Sa/Ra/Ke; `Daśā length: Normal` (1–6 years offered); `Subdaśā order: Default`
(Direct/Reverse/Previous lord reverse offered); `Tribhāgi variation` off; `Year definition: Mean
Sidereal` selected among Mean Tropical/Anomalistic/Savana (360)/Synodic (354); `Ayanāṃśa: True
Citrā` selected among Lahiri/True Revatī/True Puṣya/Raman/Usha-Shashi; `Mean or True Nodes:
Mean`. FAQ <https://deva.guru/faq>: "Lahiri-chitrapaksa (true chitrapaksa)"; apparent geocentric
positions; Julian calendar before 1582-10-04, Gregorian after 1582-10-15. Table: header "Starting
Tārā Mo (Uttaraphālgunī)"; rows `Su −1.0 2025-09-19 to 2031-09-19`, … where the number is the
age at the period's start in years to one decimal (negative before birth) and the range is
labelled start "to" end; levels 1–3 show dates only, level 4 shows date and time to the second;
the birth Mahādaśā's antardaśās are listed from the Mahādaśā's pre-birth start (Su–Su 2025-09-19,
Su–Mo 2026-01-06, Su–Ma 2026-07-08 to 2026-11-13 containing the birth), i.e. no restart at birth.
Their displayed ayanāṃśa at that instant is 24°12′33″ (Swiss `SIDM_TRUE_CITRA` gives 24°12′42.7″;
Swiss `SIDM_LAHIRI`, our frozen accessor, gives 24°13′57.2″).

**Observed duration evidence.** The displayed start/end times below are the original browser
observations recorded on 2026-09-11 (level 4, chart-displayed times read to the second; chain
`Su > Ma > …`). The observed seconds, the nominal years (6·7·y₃·y₄/120³) and the residuals
`nominal_years × Y × 86 400 s − observed` are our independently checked arithmetic on those
observations:

| Chain | Displayed start → end | Observed | Nominal years | 365.256363 | 365.25 | 360 |
|---|---|---|---:|---:|---:|---:|
| Su–Ma–Ra–Ra | 2026-07-15 23:13:19 → 2026-07-18 20:15:19 | 248 520 s | 63/8000 = 0.007875 | +0.4 s | −3.9 s | −3576 s |
| Su–Ma–Ra–Jp | 2026-07-18 20:15:19 → 2026-07-21 09:37:06 | 220 907 s | 7/1000 = 0.007 | +0.0 s | −3.8 s | −3179 s |
| Su–Ma–Ra–Sa | 2026-07-21 09:37:06 → 2026-07-24 10:29:13 | 262 327 s | 133/16000 = 0.0083125 | +0.1 s | −4.5 s | −3775 s |
| Su–Ma–Ra–Me | 2026-07-24 10:29:13 → 2026-07-27 03:41:07 | 234 714 s | 119/16000 = 0.0074375 | −0.3 s | −4.4 s | −3378 s |
| Su–Ma–Me–Ve | 2026-09-14 01:15:15 → 2026-09-17 01:41:48 | 260 793 s | 119/14400 ≈ 0.0082639 | +0.0 s | −4.5 s | −3753 s |
| Su–Ma–Me–Sa | 2026-09-25 16:09:29 → 2026-09-28 12:58:42 | 247 753 s | 2261/288000 ≈ 0.0078507 | +0.4 s | −3.9 s | −3565 s |

These six differences of displayed times are evidence about **durations only**. The largest
residual under 365.256363 is about 0.429 s, so the observations agree with that year length
**within 0.43 s** (at one-second display resolution) and are inconsistent with 365.25 and 360;
they say nothing about where any boundary lies in absolute time.

**(I) Inference and our own contract** — to be read as ours, not as facts about deva.guru:
- `FIXED_365_256363` is **our chosen fixed approximation**, consistent with the observed durations
  above; it is *not* a verified implementation constant of deva.guru (they may derive the mean
  sidereal year from a formula or epoch; agreement within 0.43 s over ≈3-day intervals bounds the
  relative difference to about 2×10⁻⁶ and fixes no further digits).
- Adjacent displayed dates (each row's start printed equal to the previous row's end) do **not**
  prove half-open intervals on their side; **`[start, end)` is our explicit contract** (§7).
- Duration agreement does **not** establish matching absolute boundaries or a matching birth
  chain. Both depend on the Moon longitude fed in (ayanāṃśa, precision), the anchor instant, the
  timezone interpretation of displayed times, the ordering rule and the display rounding. A
  level-4 boundary predicted from their displayed, arcsecond-rounded Moon fell 42 min from the
  displayed 2026-09-10 10:19:23 when that display is read as chart-local time — within the
  ±66 min that 1″ of Moon implies for a 6-year lord — and about 7 h off when read as UTC; so
  "times displayed in the chart's zone" is an inference, not a documented fact.
- Whether their "Lahiri" option equals Swiss `SIDM_LAHIRI`, whether the daśā uses the
  full-precision or the displayed Moon, and whether level-1–3 dates are truncated or rounded,
  are **unresolved** and need a compatible logged-in session (owner's own account; none was
  created for this research).

## 3. Package layout and imports

```
src/vedic_chart/dasha/__init__.py     docstring; re-exports the public names of §8
src/vedic_chart/dasha/vimshottari.py  the pure core: constants, types, build function, queries
src/vedic_chart/dasha/from_chart.py   adapter: BirthChart -> core inputs (reads, never computes)
```

Allowed imports (AST-enforced like every other layer): stdlib (`dataclasses`, `datetime`,
`enum`, `fractions`, `math`, `types`, `typing`); from the project **only**
`vedic_chart.vedic.divisions` (`NAKSHATRA_NAMES`; `classify` is *not* called by the core — it is
the test oracle), `vedic_chart.vedic.grahas` (`Graha`) and, in `from_chart.py` only,
`vedic_chart.chart.model` (`BirthChart`, for typing). Forbidden: `swisseph`,
`vedic_chart.ephemeris`, `.astronomy`, `.sidereal`, `.lagna`, `.time`, `.location`,
`.representation`, `.render`, `.app`, `zoneinfo`. The core never opens the ephemeris, never
touches a session, never writes.

`Graha` is reused as the lord type: its nine members are exactly the nine Vimshottari lords, so no
second enum is introduced.

## 4. Constants (exact and immutable)

```python
LORD_SEQUENCE: tuple[Graha, ...] = (Graha.KETU, Graha.VENUS, Graha.SUN, Graha.MOON, Graha.MARS,
                                    Graha.RAHU, Graha.JUPITER, Graha.SATURN, Graha.MERCURY)
LORD_YEARS: Mapping[Graha, int] = MappingProxyType({KETU: 7, VENUS: 20, SUN: 6, MOON: 10,
                                    MARS: 7, RAHU: 18, JUPITER: 16, SATURN: 19, MERCURY: 17})
CYCLE_YEARS: int = 120                                   # == sum(LORD_YEARS.values())
NAKSHATRA_COUNT: int = 27                                # index i -> lord LORD_SEQUENCE[i % 9]
MICROSECONDS_PER_DAY: int = 86_400_000_000
```

Public duration constants are **immutable**: the sequence is a tuple, `LORD_YEARS` is a
`MappingProxyType` over a private dict (no item assignment), `YearConvention` members hold
`Fraction`s (immutable). A caller cannot alter one and silently change later calculations; a test
asserts that assignment raises.

`LORD_SEQUENCE` is the cyclic order for Mahādaśās and for every sub-level; it is the BPHS order
rotated to begin at Aśvinī (index 0) = Ketu, so that `lord_of(index) = LORD_SEQUENCE[index % 9]`
gives Aśvinī/Maghā/Mūla → Ketu, Bharaṇī/Pūrva Phalgunī/Pūrva Āṣāḍhā → Venus, Kṛttikā/Uttara
Phalgunī/Uttara Āṣāḍhā → Sun, Rohiṇī/Hasta/Śravaṇa → Moon, Mṛgaśira/Citrā/Dhaniṣṭhā → Mars,
Ārdrā/Svātī/Śatabhiṣā → Rahu, Punarvasu/Viśākhā/Pūrva Bhādrapadā → Jupiter, Puṣya/Anurādhā/
Uttara Bhādrapadā → Saturn, Āśleṣā/Jyeṣṭhā/Revatī → Mercury. A test asserts this table against
`NAKSHATRA_NAMES` name by name.

```python
class YearConvention(Enum):
    FIXED_365_25     = Fraction(1461, 4)              # == Fraction("365.25")
    FIXED_365_256363 = Fraction(365256363, 1000000)   # == Fraction("365.256363")
```

Both values are defined from integer ratios (equivalently exact decimal strings) — **never**
`Fraction(365.256363)` of a float, which would be the binary neighbour of the decimal, not the
decimal. The member value is the length of one nominal daśā-year in days, exact.

## 5. Nakṣatra indexing and the conversion from the input longitude

**Indexing.** `nakshatra_index` is **zero-based** (Aśvinī = 0 … Revatī = 26), the same field
Layer 7 stores in `DivisionalPlacement.nakshatra_index`; the human **number** is `index + 1`,
Layer 7's `nakshatra_number`. So Viśākhā is index 15 = nakṣatra 16; Mṛgaśira is index 4 =
nakṣatra 5. The result type carries both, and names come from `NAKSHATRA_NAMES[index]`.

**Frozen classification convention (rules 8, 10–13 of the calculation contract).** Layer 7
normalises with `longitude % 360.0` and computes, in IEEE-754 double arithmetic,
`nakshatra_index = int(longitude * 27.0 / 360.0)`.

**Normalisation and the 0/360 seam.** The core applies the identical `% 360.0` once, on the
double it receives. Consequences it documents and tests: `360.0` normalises to `0.0` (Aśvinī,
elapsed 0), exactly as Layer 7 classifies it; `-1e-9` normalises to `359.999999999` (Revatī);
the largest double below 360, `359.99999999999994`, gives `p = 26.999999999999996` (Revatī,
remaining `1/2⁴⁸` of a nakṣatra). Negative inputs of magnitude at most `2⁻⁴⁵` (half an ULP of 360)
normalise, under Python's float `%`, to **`360.0`** — for which Layer 7's own assertion fails
(index 27). The core treats the same input class as invalid: if the normalised value is not
`< 360.0` it raises `ValueError("longitude normalises to 360.0")` rather than indexing 27.
Layer 6 produces its sidereal longitudes through the same `% 360`, so a chart can carry `360.0`
(which both layers read as `0.0`) but never a value that normalises to `360.0` again. The result
stores **both** `moon_sidereal_longitude` (the float as given) and `normalized_longitude` (the
value after `% 360.0`, the one actually classified).

**Analysis of the 27 boundaries in double precision (scoped).** The exact boundaries are
`B_k = k·40/3` degrees, k = 0…26. For k a multiple of 3 they are exactly representable; the other
18 are not, and the nearest double `float(B_k)` lies *below* the exact value for
k ∈ {7, 11, 14, 17, 22, 25} and *above* it for the remaining twelve. The examined neighbourhood is
`float(B_k)` and its 64 nearest doubles on each side, for every k (3,483 inputs). Around k = 0
the 64 lower neighbours are negative doubles of magnitude far below 2⁻⁴⁵ (subnormals down to
`-5e-324`); these normalise to `360.0` and belong to the **rejected** input class above, so they
are recorded as rejection cases, not compared. For the remaining **accepted** inputs the frozen
float classification is compared with the exact rational classification
`floor(Fraction(x)·27/360)`. **Within that neighbourhood** the two agree everywhere except at
four inputs — the doubles
`93.33333333333333` (k = 7), `186.66666666666666` (k = 14), `226.66666666666666` (k = 17) and
`333.3333333333333` (k = 25). Their exact distances **below** the rational boundaries, recomputed
for this draft, are `1/(3·2⁴⁶)` ≈ 4.74×10⁻¹⁵°, `1/(3·2⁴⁵)` ≈ 9.47×10⁻¹⁵°, `1/(3·2⁴⁵)` and
`1/(3·2⁴⁴)` ≈ 1.89×10⁻¹⁴° respectively (denominators 211 106 232 532 992, 105 553 116 266 496,
105 553 116 266 496 and 52 776 558 133 248). At each, the float product `x·27.0/360.0` rounds
**up to exactly k**, so Layer 7 returns index **k** while exact rational arithmetic returns
**k−1**. For k = 11 and 22 the nearest double is also below its boundary but both methods agree
on k−1. No input in the examined neighbourhood classifies *lower* in float than in rational
arithmetic. The scan is not exhaustive over all doubles; the implementation's tests re-run it,
and the general lesson holds regardless: a double one ULP below a boundary need not stay below it
after the multiplication.

**Reported conflict.** For those four longitudes the frozen chart says "first instant of nakṣatra
k" while the exact rational fraction into nakṣatra k is negative (by 27/360 of the distances
above). A daśā layer that reused the frozen index but computed the elapsed fraction rationally
from the longitude would produce a negative elapsed fraction and a balance greater than the lord's
full years. Layer 7 is not to be changed.

**Resolution (D1, approved).** The elapsed fraction is derived from the **same normalised float
product Layer 7 floors**, then continued exactly:

```python
normalized = longitude % 360.0                    # Layer 7's normalisation (rule 13)
p = normalized * 27.0 / 360.0                     # the very double Layer 7 floors (rule 8)
nakshatra_index = int(p)                          # == Layer 7's nakshatra_index for every double
elapsed_fraction = Fraction(p) - nakshatra_index  # exact rational of that double; 0 <= f < 1
remaining_fraction = 1 - elapsed_fraction
```

`Fraction(p)` converts the double *exactly* (every finite double is a dyadic rational). By
construction the index equals Layer 7's for every double **in the accepted input domain** (finite,
not normalising to `360.0`), the fraction is never negative, and at the four conflicting doubles
it is exactly 0.

**Precision actually preserved.** The quantity carried forward is the double `p ∈ [0, 27)`, so
the resolution of `elapsed_fraction` is the spacing of doubles at `p`: for **nonzero normal**
values, `2⁻⁵²·2^⌊log₂ p⌋` of a nakṣatra — `2⁻⁵²` for p in [1, 2), `2⁻⁴⁸` for p in [16, 32), i.e.
for indices 16–26 (the formula does not apply at p = 0 or to subnormal p, where the spacing is the
fixed 2⁻¹⁰⁷⁴; those inputs lie within 10⁻³⁰⁰° of Aśvinī's start and are irrelevant in practice). Scaled to a
20-year lord under `FIXED_365_25`, one spacing step is 0.140 µs at p ∈ [1, 2) and **≈ 2.2423 µs
at p ∈ [16, 32)** — above the microsecond quantum of §7, so two adjacent doubles of longitude can
differ by a few microseconds in every derived boundary. That is the input resolution of this
layer; nothing here claims anything about the astronomical accuracy of the Moon longitude
itself, which is the frozen engine's business and is not restated in this document. For the two
reference charts the difference between the product-based fraction and the exact rational of the
longitude is 7.1×10⁻¹⁶ (Jalandhar) and 1.8×10⁻¹⁶ (Jammu) of a nakṣatra.

Rejected alternatives: (a) exact rational classification `floor(Fraction(x)·27/360)` — disagrees
with the frozen chart at the four doubles; (b) frozen index with rational fraction and a clamp to
0 — a hidden nudge (rule 12); (c) raising on the four values — makes four legal longitudes fail.

**Adapter cross-check.** `from_chart` reads `chart.grahas[Graha.MOON].sidereal_longitude` and
`chart.moment_utc`, calls `build_vimshottari` **once**, and checks that the returned
`timeline.nakshatra_index` **equals** `chart.grahas[Graha.MOON].placement.nakshatra_index` by
value; a mismatch is an internal `RuntimeError`, since under D1 it cannot happen. The adapter
performs no classification of its own and imports no private helper.

## 6. Exact nominal arithmetic

- **Inputs are approximate, ratios are exact.** The Moon longitude is an approximation of the
  sky; once converted per §5 every further nominal quantity is an exact `Fraction`.
- Full-period durations in nominal years, exact:
  `MD(L) = LORD_YEARS[L]`;
  `AD(M, A) = LORD_YEARS[M]·LORD_YEARS[A] / 120`;
  `PD(M, A, P) = LORD_YEARS[M]·LORD_YEARS[A]·LORD_YEARS[P] / 120²`.
  The nine children of any period sum to the parent exactly (Σ LORD_YEARS = 120).
- Order within any period: the period's own lord first, then `LORD_SEQUENCE` cyclically —
  e.g. Jupiter's antardaśās Ju, Sa, Me, Ke, Ve, Su, Mo, Ma, Ra; Ju–Sa's pratyantars Sa, Me, Ke,
  Ve, Su, Mo, Ma, Ra, Ju. (Owner-approved standard order; deva.guru's "Default" was observed to
  list the same order.)
- Birth balance: `elapsed_years = elapsed_fraction · LORD_YEARS[lord]`,
  `balance_years = remaining_fraction · LORD_YEARS[lord]`, both exact Fractions. The full birth
  Mahādaśā is `LORD_YEARS[lord]` long; `balance_years` is only its post-birth **remaining
  segment**.
- Nominal offsets: every period has `nominal_start` and `nominal_end`, exact Fractions of years
  measured from the **birth instant** (negative before birth). The birth Mahādaśā starts at
  `−elapsed_years`; each later period starts where its predecessor ends; children partition the
  parent exactly.
- No "years/months/days" breakdown is part of the result. A 12×30 split of nominal years is not
  elapsed calendar time and, if ever shown by a presentation layer, must be labelled "nominal".

## 7. Time boundaries: input, anchor, quantization, range

**Input validation and normalisation.**
- `birth_utc` must be a `datetime` instance (not a `date`, not a string — `TypeError` otherwise)
  that is timezone-aware: `tzinfo` not `None` **and** `utcoffset()` not `None`; a naive value, or
  a `tzinfo` whose `utcoffset()` returns `None`, is a `ValueError` (the Layer 4 convention). It is
  converted with `astimezone(timezone.utc)`; if that conversion itself raises `OverflowError`
  (an aware non-UTC instant within a few hours of `datetime`'s limits), the core raises
  `DashaRangeError`. The normalised UTC value, with its native microsecond precision, is stored
  as `birth_utc`; the Layer 8 `moment_utc` already meets this.
- `moon_sidereal_longitude` must be a `float` or `int` (`bool` rejected, `TypeError` for other
  types); non-finite is a `ValueError`; §5 governs normalisation. Two further guards, both
  `ValueError`: an `int` too large to convert to `float` (the `OverflowError` from `float()` is
  translated so that it never escapes the layer), and a computed nakṣatra index outside `0..26`
  (mirrors the frozen `classify` assertion as a real exception that `python -O` cannot strip;
  unreachable from any accepted input once the `360.0` rejection of §5 is in place).
- `year` must be a `YearConvention` member (`TypeError` otherwise) — no default.

**Anchor.** All instants are derived from one anchor, `T0 = birth_utc`, so that the birth instant
is exactly representable and every boundary is a function of `(T0, nominal offset)` alone.

**Quantization rule (D2, approved — one rule for every boundary).** For a nominal offset `o`
(Fraction, years) and year length `Y` (Fraction, days):

```python
micros = math.floor(o * Y * MICROSECONDS_PER_DAY)   # exact integer floor of the exact product
instant = T0 + timedelta(microseconds=micros)        # floor toward −∞, also for negative offsets
```

Consequences: (i) monotone — a larger nominal offset never yields an earlier instant; (ii)
**shared boundaries are the same arithmetic**: a last child's `nominal_end` equals its parent's
`nominal_end` as a Fraction, so the floors are equal and the last child ends exactly at the
parent's `end_utc`; consecutive children are contiguous because each child's `nominal_start` *is*
its predecessor's `nominal_end`; (iii) a period's quantized duration `end_utc − start_utc` equals
`floor(o_end·Y·C) − floor(o_start·Y·C)`, which differs from `floor(nominal_years·Y·C)` by 0 or 1
µs, and is never used for arithmetic — nominal Fractions are the exact quantities, datetimes are
their presentation. The true Mahādaśā start before birth is
`T0 + floor(−elapsed_years·Y·C) µs`, floored like everything else.

**Difference between the two conventions.** For one nominal offset `o`, the two independently
anchored floors satisfy `|(floor(o·Y₂·C) − floor(o·Y₁·C)) − o·(Y₂−Y₁)·C| < 1`, i.e. the
datetime difference between conventions is `floor(o·ΔY·C)` **or that plus one microsecond**, for
positive and negative `o` alike; it is *not* in general `floor(o·ΔY·C)`. Tests compare the two
floors exactly, not through the difference (§10).

**Collapsed post-birth segments.** A **full** period never collapses: the birth Mahādaśā began
`elapsed_years` before birth and its quantized interval is years long. What can collapse is the
**remaining post-birth segment** of a period that contains the birth: if the nominal remainder
scales to less than one microsecond, the period's `end_utc` floors to exactly `T0`, so that period
is `[start_utc, T0)` — non-empty, but containing no instant at or after birth. This can happen at
any level: the birth Mahādaśā's remainder, or an antardaśā's or pratyantar's remainder within a
Mahādaśā that still has years to run, since AD/PD boundaries lying less than one microsecond after
birth quantize to `T0` too. Hence the two queries of §8 differ by design: `periods_at_birth()`
uses **exact nominal membership** (offset 0 in `[nominal_start, nominal_end)`) and always returns
the chain the Moon longitude defines; `active_periods_at(T0)` uses the **quantized** intervals and
then selects the *next* period at every level whose boundary quantized to `T0`. No special case is
added to make them agree.

Concrete case (hand-computed): longitude `nextafter(40.0, 0)` = `39.99999999999999` → Kṛttikā,
Sun; `remaining_fraction = 1/2⁵¹`; `balance_years = 6/2⁵¹`, which under `FIXED_365_25` is
≈ 0.084086 µs (under `FIXED_365_256363` ≈ 0.084088 µs). `floor` gives 0, so the Sun Mahādaśā ends
at exactly `T0`; nominally birth falls in its last antardaśā Su–Ve and that antardaśā's last
pratyantar Su–Ve–Ke, both of which also end at `T0` after flooring. `periods_at_birth()` returns
(Su, Su–Ve, Su–Ve–Ke); `active_periods_at(T0)` returns (Mo, Mo–Mo, Mo–Mo–Mo).

**Datetime range.** Two failure directions exist and both are checked before any `datetime`
arithmetic: the pre-birth Mahādaśā start (up to 20 nominal years before birth) can **underflow**
below `datetime.min` (year 1) for births in the first approximately twenty calendar years of
`datetime`'s supported range, and the cycle end
(up to 120 nominal years after birth) can **overflow** past `datetime.max` (year 9999) for births
later than roughly the year 9879. In either case the core raises `DashaRangeError(ValueError)`
naming the birth instant and the offending offset, instead of letting `OverflowError` escape.
Within the ephemeris coverage 1800–2399 neither can occur; the check is a guard.

**Intervals are half-open**: `[start_utc, end_utc)`. An instant equal to a period's `start_utc`
belongs to that period; equal to its `end_utc`, to the next. This is our contract (§2, I).

## 8. API (module `vedic_chart.dasha.vimshottari`)

```python
class DashaRangeError(ValueError): ...

@dataclass(frozen=True)
class DashaPeriod:
    level: int                        # 1 Mahādaśā, 2 Antardaśā, 3 Pratyantardaśā
    lords: tuple[Graha, ...]          # chain, len == level; lords[-1] is this period's lord
    nominal_years: Fraction           # exact full length (§6), regardless of birth
    nominal_start: Fraction           # exact offset from birth, years (negative before birth)
    nominal_end: Fraction             # == nominal_start + nominal_years
    start_utc: datetime               # quantized per §7
    end_utc: datetime                 # quantized per §7; == parent's end_utc for the last child
    children: tuple["DashaPeriod", ...]   # nine, or () at level 3
    @property
    def lord(self) -> Graha: ...

@dataclass(frozen=True)
class VimshottariTimeline:
    birth_utc: datetime               # normalised UTC (§7)
    year: YearConvention
    moon_sidereal_longitude: float    # as given
    normalized_longitude: float       # after % 360.0; the value classified (§5)
    nakshatra_index: int              # 0-based
    nakshatra_number: int             # 1-based
    nakshatra_name: str
    lord: Graha                       # birth Mahādaśā lord
    elapsed_fraction: Fraction        # §5, in [0, 1)
    remaining_fraction: Fraction
    elapsed_years: Fraction
    balance_years: Fraction           # remaining post-birth segment of the first Mahādaśā
    cycle_start_utc: datetime         # == mahadashas[0].start_utc (before or at birth)
    cycle_end_utc: datetime           # == mahadashas[-1].end_utc
    mahadashas: tuple[DashaPeriod, ...]   # exactly nine, level 1, each with 9×9 descendants
    def periods_at_birth(self) -> tuple[DashaPeriod, DashaPeriod, DashaPeriod]: ...
    def active_periods_at(self, instant: datetime) -> tuple[DashaPeriod, DashaPeriod, DashaPeriod]: ...

def build_vimshottari(moon_sidereal_longitude: float, birth_utc: datetime,
                      year: YearConvention) -> VimshottariTimeline: ...
```

And in `vedic_chart.dasha.from_chart`:

```python
def vimshottari_from_chart(chart: BirthChart, year: YearConvention) -> VimshottariTimeline
```

which only reads `chart.grahas[Graha.MOON].sidereal_longitude` and `chart.moment_utc`, calls
`build_vimshottari` once, performs the §5 cross-check on the returned timeline, and returns that
timeline. It computes nothing else and does not touch `chart.location`, the ephemeris or any
session.

**Timeline scope.** Exactly **nine** Mahādaśās are returned: one full cycle of 120 nominal years
that begins at the **true start of the birth Mahādaśā**, `elapsed_years` before birth, and ends
`120 − elapsed_years` nominal years **after** birth. It is not "120 years after birth" and it is
not a requested interval; there is no continuation into a second cycle.

**Queries.** `periods_at_birth()` locates, by exact nominal offsets, the level-1/2/3 periods whose
`[nominal_start, nominal_end)` contain offset 0 — the birth lord's Mahādaśā, then the antardaśā
and pratyantar of the full parent laid out from its pre-birth start (never restarted at birth,
never a pro-rata split of the balance). `active_periods_at(instant)` validates and normalises
`instant` exactly like `birth_utc` (§7), then searches the quantized half-open intervals: an
instant equal to a `start_utc` belongs to that period; an instant `< cycle_start_utc` or
`>= cycle_end_utc` raises `DashaRangeError` (D3). Both return the chain `(MD, AD, PD)`; no
`remaining_at` helper is provided (D4) — callers compute remaining time from the Fractions or the
datetimes as their purpose requires.

**Comparison.** Numeric fields are compared by **value** (`==` on Fractions, ints, datetimes);
object identity is not part of any contract or test of this layer — it proves nothing about
arithmetic.

## 9. Worked reference values (internal, from the frozen engine at full precision)

Both charts come from Layer 11 with the production database (acceptance record of 2026-09-11);
the Moon longitudes are the frozen engine's floats, not SVG labels.

| | Jalandhar 1995-03-21 06:45 IST (`moment_utc` 1995-03-21 01:15 UTC) | Jammu 2001-02-04 10:45 IST (`moment_utc` 2001-02-04 05:15 UTC) |
|---|---|---|
| Moon sidereal longitude (repr) | `209.20440791222882` | `54.892295957053236` |
| Nakṣatra | Viśākhā — index 15, number 16, pada 3 | Mṛgaśira — index 4, number 5, pada 1 |
| Lord, full years | Jupiter, 16 | Mars, 7 |
| Elapsed fraction (§5, float value of the Fraction) | 0.690330593417162 | 0.11692219677899285 |
| Remaining fraction | 0.30966940658283804 | 0.8830778032210072 |
| Elapsed years | 11.045289494674591 | 0.8184553774529499 |
| Balance, nominal years (exact Fraction; float shown) | `87164189005907/17592186044416` ≈ 4.954710505325409 | `6959800514669247/1125899906842624` ≈ 6.18154462254705 |
| Antardaśā at birth (from the true MD start) | Ju–Su, 6th of 9, length 4/5 y, 0.288044… y remaining | Ma–Ra, 2nd of 9, length 21/20 y, 0.639878… y remaining |
| Pratyantar at birth | Ju–Su–Me, length 17/150 y, 0.108044… y remaining | Ma–Ra–Sa, length 133/800 y, 0.053628… y remaining |
| Mahādaśā order after Jupiter / Mars | Sa 19, Me 17, Ke 7, Ve 20, Su 6, Mo 10, Ma 7, Ra 18 | Ra 18, Ju 16, Sa 19, Me 17, Ke 7, Ve 20, Su 6, Mo 10 |

Year-convention sensitivity of the birth Mahādaśā end, computed per §7 (display in IST for
reading only): Jalandhar 2000-03-03 23:44 (`FIXED_365_25`) vs 2000-03-04 00:29
(`FIXED_365_256363`); Jammu 2007-04-12 06:10 vs 07:06. The exact microsecond values are fixed by
the implementation's tests, not by this table (which is rounded to the minute). There is **no
external reference** for either birth's daśā; V01 (`docs/verification_cases.md`) covers positions
only.

## 10. Tests (self-contained, stdlib + the two frozen constants modules)

- **Constants and mapping:** `LORD_YEARS` sums to 120; `LORD_SEQUENCE` is the nine `Graha`s
  with no repeat; the 27 nakṣatra → lord assignments of §4 hold name by name against
  `NAKSHATRA_NAMES`; `LORD_YEARS[...] = ...` raises `TypeError` and `LORD_SEQUENCE` is a tuple;
  `YearConvention` values are `Fraction(1461, 4)` and `Fraction(365256363, 1000000)` exactly.
- **Boundary analysis, all 27:** for every k, `float(B_k)` and its 64 nearest doubles on each side
  are split into the rejected class (negative doubles normalising to `360.0`, asserted to raise
  `ValueError`) and accepted inputs, which give the same `nakshatra_index` from the core as from
  `vedic_chart.vedic.divisions.classify` (the frozen oracle), an elapsed fraction in `[0, 1)`, and
  for the four doubles of §5 yield
  exactly `Fraction(0)`; an exact-rational classifier used *only inside the test* documents the
  k−1 disagreement at those four values and asserts their recorded distances below the rational
  boundaries, so the decision is visible in the suite.
- **Normalisation seam:** `360.0` → index 0 with elapsed 0; `-1e-9` → index 26; `nextafter(360.0,
  0)` → index 26 with remaining `1/2⁴⁸`; `-2.0**-45` and `-5e-324` raise `ValueError`;
  `normalized_longitude` holds the `% 360.0` value and `moon_sidereal_longitude` the input.
- **Hand-worked cases (values computed for this draft with the §5 rule):** `0.0` → Aśvinī, Ketu,
  elapsed 0, balance 7; `40.0` (an exactly representable boundary, k = 3) → Rohiṇī, Moon, elapsed
  0, balance 10; `153.3333333333333` (mid Uttara Phalgunī, index 11) → Sun, elapsed
  `281474976710655/562949953421312`; and the tiny-balance input `nextafter(40.0, 0)` →
  Kṛttikā, Sun, elapsed `2251799813685247/2251799813685248`, remaining `1/2⁵¹`, balance `6/2⁵¹`
  years ≈ 0.084086 µs, so the Sun Mahādaśā, Su–Ve and Su–Ve–Ke all end at `T0` after flooring
  (§7).
- **Exact parent sums:** for both reference charts and for the hand-worked cases, at every level
  the nine children's `nominal_years` sum to the parent's, their `nominal_start`/`nominal_end`
  chain without gaps, and `children[-1].nominal_end == parent.nominal_end` as Fractions.
- **Shared quantized endpoints:** `children[-1].end_utc == parent.end_utc` and
  `children[i+1].start_utc == children[i].end_utc` for every period, both conventions;
  monotonicity of all 9 + 81 + 729 boundaries; each period's quantized duration differs from
  `floor(nominal_years·Y·C)` by 0 or 1 µs.
- **Birth chain and its divergence:** `periods_at_birth()` for Jalandhar is (Ju, Ju–Su, Ju–Su–Me)
  and for Jammu (Ma, Ma–Ra, Ma–Ra–Sa) with the remaining Fractions of §9, found in the test by a
  brute-force scan over all 729 pratyantars; restarting the sub-sequence at birth (Ju–Ju / Ma–Ma)
  or subdividing only the balance is shown to give a *different* chain. With the real input
  `nextafter(40.0, 0)`: `periods_at_birth()` is (Su, Su–Ve, Su–Ve–Ke), every one of those three
  has `end_utc == birth_utc`, and `active_periods_at(birth_utc)` is (Mo, Mo–Mo, Mo–Mo–Mo). A
  second synthetic input whose birth Mahādaśā has years to run but whose birth pratyantar ends
  less than 1 µs after birth exercises the same divergence at levels 2–3 only.
- **Year conventions:** every datetime test runs under both members; for a set of nominal
  offsets including negative ones (the pre-birth start, `−1/7`) and positive ones (`1/3`, `7/2`,
  both reference balances), the two floors are computed independently and compared exactly to
  `math.floor(o·Y·C)` for each convention, and the bound
  `floor(o·Y₂·C) − floor(o·Y₁·C) ∈ {floor(o·ΔY·C), floor(o·ΔY·C) + 1}` is asserted.
- **Quantization rule:** the floor is applied to negative offsets toward −∞ (the pre-birth
  Mahādaśā start is never later than its exact instant), checked against `math.floor` on the
  exact product.
- **Queries and input validation:** `active_periods_at` at each Mahādaśā `start_utc` returns that
  Mahādaśā; at `cycle_end_utc` and at `cycle_start_utc − 1 µs` raises `DashaRangeError`; naive
  datetimes and a `tzinfo` whose `utcoffset()` returns `None` raise `ValueError`; a `date`, a
  string, a `bool` longitude, a non-`YearConvention` year raise `TypeError`; NaN/inf raise
  `ValueError`.
- **Range:** a birth at `0001-01-05 00:00 UTC` with a Venus-lord Moon (pre-birth start up to
  20 years earlier) raises `DashaRangeError` (underflow); a birth at `9990-01-01 00:00 UTC` raises
  `DashaRangeError` (overflow); an aware non-UTC birth such as `0001-01-01 02:00 +05:30` raises
  `DashaRangeError` from the normalisation step; none of them lets `OverflowError` escape.
- **Adapter:** `vimshottari_from_chart` on the Jalandhar and Jammu `BirthChart`s equals
  `build_vimshottari` on the extracted values (by value); a chart whose Moon placement was
  tampered to another index (a test double, not a real chart) raises `RuntimeError`; a spy on
  the core shows it is called exactly once with the two extracted inputs and that the object
  returned is the core's; a core stub returning a timeline with a tampered `nakshatra_index`
  trips the same `RuntimeError` (so the check reads the returned timeline, not a private
  re-derivation); an AST check shows the adapter imports and references no private classifier.
- **Boundaries of the package:** AST test for §3; `pyproject.toml` unchanged; no dependency added;
  no `round()`; nothing from `render`, `app`, `representation` imported.
- **Independent absolute-date validation** against deva.guru is recorded as **pending** (D5) and is
  **not a prerequisite** for implementing the internally specified core. Matching absolute dates
  would require sufficiently compatible inputs (the same Moon longitude, hence the same
  ayanāṃśa and precision), the same year convention, the same ordering rule, a known timezone
  interpretation of their displayed times, and display precision fine enough at the compared
  level. Duration agreement alone does not suffice, and a birth chain cannot stand in for it
  either, because the chain depends on the Moon input just as the dates do. No special case will
  be added to make any reference date match.

## 11. Acceptance criteria

1. The nine-lord cycle, years and nakṣatra mapping are the classical ones (§4), immutable, and
   tested.
2. The nakṣatra index equals Layer 7's for every double in the accepted input domain (§5, D1),
   Layer 7 untouched; the 0/360 seam and the rejected class behave as §5 states.
3. All nominal quantities are exact Fractions, children partition parents exactly, and the two
   year constants are exact ratios.
4. One quantization rule (§7, D2) produces contiguous, monotone half-open intervals whose shared
   endpoints are identical; the cycle is nine Mahādaśās from the true pre-birth start; the two
   queries of §8 behave as §7 specifies where a remainder collapses.
5. The Jalandhar and Jammu internal reference values of §9 are reproduced by value.
6. Frozen layers, Layer 9–11 files, fixtures and goldens unchanged; full suite green.

## 12. Decisions closed and remaining

Closed in v0.2: D1 (float-product fraction), D2 (floor to microseconds, negative offsets
included), D3 (`DashaRangeError` outside the cycle), D4 (no `remaining_at`), D5 (external
absolute-date validation pending; durations alone insufficient). Closed at implementation review
(v1.0): the adapter calls the core once and cross-checks the returned timeline (§5, §8).

Open only as future work, not blocking v1.0: which deva.guru settings and precision would count as
compatible for D5 (a logged-in session with "Lahiri" and a chosen year definition, boundaries
readable to the minute or better), and whether Layer 6/7's handling of inputs that normalise to
`360.0` deserves a separate note in the frozen contract's documentation (no code change proposed).

## 13. Validation record (v1.0)

**Files.** `src/vedic_chart/dasha/__init__.py` (42 lines), `vimshottari.py` (563),
`from_chart.py` (60); `tests/test_dasha_vimshottari.py` (1254), `tests/test_dasha_from_chart.py`
(296), `tests/test_dasha_boundaries.py` (265). No tracked file changed: Layers 1–11, fixtures,
goldens, `pyproject.toml` (byte-identical to `11e8881`) and the installed dependencies
(pyswisseph 2.10.3.2, timezonefinder 8.2.0) are as at Layer 11 v1.0. No renderer or CLI change.

**Test suite (final, after the adapter cleanup).** Full suite on the owner's machine (project
`.venv`, committed fixture database and `ephe/`; the new tests use no production database and no
network): **1914 passed, 0 failed, 0 skipped** — 1543 at Layer 11 v1.0 plus 371 Layer 12 tests
(the three files above: 371 alone). Before the cleanup the count was 1909 + the same result; the
cleanup added five adapter tests and changed no behaviour.

**Reference births (fixture database for Jalandhar; explicit `ResolvedLocation` 32.73528 N,
74.86167 E, Asia/Kolkata for Jammu), engine Moon longitudes `209.20440791222882` and
`54.892295957053236`, identical results from the adapter and the core, under both conventions:**

| | Jalandhar 1995-03-21 06:45 IST | Jammu 2001-02-04 10:45 IST |
|---|---|---|
| Birth nakṣatra / lord | Viśākhā (index 15, #16) / Jupiter | Mṛgaśira (index 4, #5) / Mars |
| Exact nominal balance | `87164189005907/17592186044416` ≈ 4.9547105 y | `6959800514669247/1125899906842624` ≈ 6.1815446 y |
| Birth chain (`periods_at_birth`) | Ju › Ju–Su › Ju–Su–Me | Ma › Ma–Ra › Ma–Ra–Sa |
| `active_periods_at(birth_utc)` | same chain, both conventions | same chain, both conventions |
| First MD, `FIXED_365_25` (UTC) | 1984-03-03 18:14:32.242857 → 2000-03-03 18:14:32.242857 | 2000-04-11 06:40:12.580490 → 2007-04-12 00:40:12.580490 |
| First MD, `FIXED_365_256363` (UTC) | 1984-03-03 16:33:19.949159 → 2000-03-03 18:59:56.160359 | 2000-04-11 06:32:42.623843 → 2007-04-12 01:36:50.966243 |

The balances and chains are convention-independent by construction; only the datetimes move.

**Quantization-divergence cases (both conventions, tested).** (1) The real input
`nextafter(40.0, 0)` = `39.99999999999999`: Kṛttikā, Sun, balance `6/2⁵¹` nominal years ≈ 0.084
µs; `periods_at_birth()` = (Su, Su–Ve, Su–Ve–Ke), all three with `end_utc == birth_utc`;
`active_periods_at(birth_utc)` = (Mo, Mo–Mo, Mo–Mo–Mo). (2) The searched double
`3.666666666666666` (Aśvinī, Ketu): Ke–Su and Ke–Su–Ve end `21/90071992547409920` nominal years ≈
0.0074 µs after birth; `periods_at_birth()` = (Ke, Ke–Su, Ke–Su–Ve), `active_periods_at(birth_utc)`
= (Ke, Ke–Mo, Ke–Mo–Mo) — level 1 agrees and the Ketu Mahādaśā has ≈ 5.075 nominal years left, so
only levels 2–3 diverge. Where nothing collapses (Jalandhar, Jammu, mid-Uttara Phalgunī) the two
queries agree.

**External validation.** Independent absolute-date validation against deva.guru (or any other
implementation) remains **pending** (D5). This layer makes **no claim of exact deva.guru
compatibility**: the only external evidence used is the duration table of §2, which constrains the
year length and nothing else, and `FIXED_365_256363` is our fixed approximation, not their
constant. Matching absolute dates would require compatible inputs (same Moon longitude, hence
ayanāṃśa and precision), year convention, ordering, timezone interpretation and display precision.

