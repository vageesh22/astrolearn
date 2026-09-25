# Layer 17 — Panchanga transition times

**Status:** SPECIFICATION v1.0 (promoted 2026-09-24 by the project owner after an independent
implementation review found no functional blocker and after the native-macOS verification
recorded in §13). History: DRAFT v0.1, v0.2 and v0.3, all 2026-09-24 — eight review findings
resolved in v0.2, five corrections in v0.3 (§11); implementation record in §12. The
conventions fixed at v1.0: absolute-grid cells with nested tolerances and a 100 ms default,
representative-based interval membership, the query classified off-grid and every probe on
the grid, reach measured from the query, separate supported and evaluation ranges, and the
conditional guarantees of §4.9. Nothing in this document changes the FROZEN v1.0 calculation
specification (`docs/CALCULATION_SPEC.md`) or Layer 16 v1.0 (`docs/LAYER16_PANCHANGA_SPEC.md`).
Any change to a convention recorded here requires a new specification version and owner
approval. Baseline: commit `2c5b180` (`master` = `origin/master`,
clean tree). Nothing here changes the FROZEN v1.0 calculation specification
(`docs/CALCULATION_SPEC.md`) or Layer 16 v1.0 (`docs/LAYER16_PANCHANGA_SPEC.md`): no existing
calculation function, convention, test or golden changes; Layer 16's results are never clamped
and no classification epsilon is introduced. Deployment files and the viewer/CLI/HTTP surfaces
are outside this milestone. Decisions D1 and D5 of v0.1 are approved (§10).

## 1. Scope

Backend only. For the four **angular** panchanga elements — tithi, nakshatra, nitya yoga,
karana — Layer 17 answers, from evaluated astronomical positions:

1. *Neighbours:* for a supplied instant and a set of kinds, the previous transition (when the
   current element began) and the next (when it ends).
2. *Listing:* every transition of the requested kinds whose representative instant lies in an
   explicitly bounded UTC interval, in time order.

Every answer is immutable and carries the Layer 16 element **before** and **after** the
transition, a UTC **cell** — two instants that are verified old-side and new-side
classifications — their Julian Days, and the uncertainty record of §5. Local time is a
presentation step applied afterwards through an IANA zone.

Excluded: vara (Layer 16's `find_sunrise_window` is its boundary; no sunrise code and no
second sunrise convention here — D6), UI, HTTP, CLI, festivals, lunar-month naming, muhurta,
sunset, moonrise, sunrise-relative day tables, any change to Layer 16's classification.

## 2. What is fixed by the layers below

* Positions (FROZEN §4–5): Swiss Ephemeris via pyswisseph, the three `.se1` files, apparent
  geocentric longitudes, Lahiri `SIDM_LAHIRI` true equinox of date, one ayanamsha per instant.
  Layer 17 evaluates positions only through the existing Layer 6 entry
  `calculate_sidereal_positions(moment)` at timezone-aware datetimes (D7: no JD-based
  accessor, one code path for longitudes), so every longitude it sees is exactly what Layer 16
  computes at that datetime.
* Time (FROZEN §3.3): `JD_UT = unix/86400 + 2440587.5`; UTC used as UT1. Layer 16 §2.4:
  instants normalised to UTC by `sunrise.utc_instant`.
* Classification (Layer 16 §4): `tithi_from_elongation`, `karana_from_elongation`,
  `yoga_from_sum`, `nakshatra_from_longitude` (→ FROZEN `classify`); half-open `[start, end)`
  on unrounded values; `angular_fraction = scaled − index ∈ [0, 1)` exactly; the raw
  `degrees_in_*` offset can be a few 10⁻¹⁴° negative at inexact 40k/3° boundaries.
* Ephemeris lifecycle: the caller's, via `ephemeris_session`.

### 2.1 Monotonicity and rates — empirical, with margin

The three divided quantities are increasing functions of time in the geocentric apparent frame:
elongation `E = (λ_M − λ_S) mod 360`, the Moon's sidereal longitude `λ_M`, and the sum
`Y = (λ_S + λ_M) mod 360`. This is a physical property (the Moon is never retrograde
geocentrically and always outruns the Sun), and the design treats it as a **checked
assumption**, not a theorem: every result is verified by classification at both endpoints
(§4.1), and a violation surfaces as a typed failure (§4.5), never as a wrong answer.

The rate bounds used for the *initial estimate* are empirical. Drafting survey over
1800–2399 (one 40-day window per 25 years, 6-hour steps, from the engine's own tropical
speeds; the same survey with finite differences of the sidereal longitudes agrees):

| Quantity | Tropical-speed minimum | maximum | Ayanamsha term |
|---|---|---|---|
| E | 10.782°/day | 14.360°/day | cancels exactly (difference of two sidereal longitudes rotated by the same ayanamsha) |
| λ_M | 11.774°/day | 15.356°/day | sidereal rate = tropical rate − dA/dt |
| Y | 12.734°/day | 16.351°/day | sidereal rate = tropical rate − 2·dA/dt |

Layer 6 keeps *tropical* speeds unchanged (FROZEN §5), so a sidereal rate is the tropical
speed minus the ayanamsha derivative. Measured over the same survey, |dA/dt| ≤ 9.45 × 10⁻⁵
°/day (the true-equinox ayanamsha carries nutation, so this exceeds the ~3.8 × 10⁻⁵ secular
rate); it is five orders below the margin. `RATE_MIN` is the measured minimum **minus 10 %**.
The implementation's fuller survey (§12) found lower minima than the drafting one — E 10.741,
λ_M 11.760, Y 12.775 °/day — and pinned `RATE_MIN = {tithi: 9.66, karana: 9.66, nakshatra:
10.58, yoga: 11.46}` and `RATE_MAX = {15.83, 15.83, 16.95, 18.07}` (maxima 14.385, 15.401,
16.419 plus 10 %), all recorded in the module docstring. These constants only size the first probe; correctness never depends on them (§4.3).
When the rate assumption holds, the first probe already lies past the change and no expansion
occurs (probe R4: 30 successive tithi searches, zero expansions).

### 2.2 Ephemeris coverage edges — state-dependent

Nominal coverage is 1800-01-01 … 2400-01-01 UT, but the outermost hours answered differently
depending on call order during inspection (a cold session evaluates 1800-01-01 12:00 but not
00:00; 2400-01-01 succeeded after in-range calls and failed after an out-of-range one). Margins
are therefore fixed conservatively (§4.6) and tested cold (§7).

### 2.3 Datetime resolution versus Julian Day resolution

At JD ≈ 2.46 × 10⁶ one double ULP is 4.66 × 10⁻¹⁰ day = **40 µs**. A 1 µs datetime step
therefore usually maps to the same JD float and the same ephemeris evaluation (measured: 975 of
1000 consecutive 1 µs steps left the JD unchanged); a 1 ms step always advances it (0 of 1000
unchanged; 25 ULP). Every **search probe and returned endpoint** lies on a grid of whole
milliseconds or coarser, and the bisection checks JD progress explicitly (§4.4). The supplied
query instant is the one evaluation that is *not* on the grid (§4.2).

## 3. Public surface (`vedic_chart.panchanga.transitions`, re-exported by `vedic_chart.panchanga`)

Types, all `@dataclass(frozen=True)`, fully annotated, invariants enforced in `__post_init__`
with `ValueError`:

* `TransitionKind(Enum)`: `TITHI`, `KARANA`, `NAKSHATRA`, `YOGA` (this is also the canonical
  order). `Quantity(Enum)`: `ELONGATION`, `MOON_LONGITUDE`, `LONGITUDE_SUM`.
* `TransitionUncertainty(cell_width: timedelta, ut1_note: str, model_note: str)` — §5.
* `Transition(kind, quantity, boundary_degrees: float, before: Element, after: Element,
  before_utc: datetime, after_utc: datetime, before_julian_day_ut: float,
  after_julian_day_ut: float, tolerance: timedelta, uncertainty: TransitionUncertainty)`.
  `Element` is the Layer 16 `Tithi | Nakshatra | NityaYoga | Karana` of the kind, computed at
  `before_utc` and `after_utc` respectively. Invariants: both instants `tzinfo is
  timezone.utc`; `after_utc − before_utc == tolerance`; both lie on the tolerance grid (§4.2);
  `after.index == (before.index + 1) % count`; `boundary_degrees == after.index · span`.
  Property `event_id -> EventId`.
* `EventId(kind: TransitionKind, after_index: int, cell_end_utc: datetime)` — identity of
  a transition at a given tolerance: `cell_end_utc == after_utc`. Function
  `same_event(a: Transition, b: Transition) -> bool`: same kind and `after_index`, and the two
  cells nest (one contains the other; §4.2 guarantees nesting across tolerances).
* `Neighbours(kind, current: Element, previous: Transition, next: Transition)` with
  `previous.after.index == current.index == next.before.index`.
* `PanchangaTransitions(instant_utc, julian_day_ut, tolerance, kinds: tuple[TransitionKind, ...],
  neighbours: Mapping[TransitionKind, Neighbours], calculation_convention: str,
  search_convention: str)` — `neighbours` is a `MappingProxyType` whose keys are exactly
  `kinds`, in canonical order (Layer 8 precedent for read-only mappings). There are no
  per-kind attributes: a subset request has a subset result, and `result.neighbours[kind]`
  is the one access path.
* `TransitionList(start_utc, end_utc, tolerance, kinds, transitions: tuple[Transition, ...],
  unordered_pairs: tuple[tuple[int, int], ...], calculation_convention, search_convention)` —
  §4.7 for ordering and `unordered_pairs`.
* `LocalTransition(transition, timezone_id, before_local, after_local)` — presentation.

Functions:

* `next_transition(moment_utc, kind, *, tolerance=DEFAULT_TOLERANCE, evaluate=default_evaluate) -> Transition`
* `previous_transition(moment_utc, kind, *, tolerance=DEFAULT_TOLERANCE, evaluate=…) -> Transition`
* `find_transitions(moment_utc, *, kinds=ALL_KINDS, tolerance=DEFAULT_TOLERANCE, evaluate=…) -> PanchangaTransitions`
* `list_transitions(start_utc, end_utc, *, kinds=ALL_KINDS, tolerance=DEFAULT_TOLERANCE, evaluate=…) -> TransitionList`

`evaluate` — keyword-only on all four search functions — is the injectable position source:

```python
Evaluate = Callable[[datetime], tuple[float, float]]      # (sun_sidereal, moon_sidereal), degrees in [0, 360)

def default_evaluate(moment_utc: datetime) -> tuple[float, float]:
    sidereal = calculate_sidereal_positions(moment_utc)   # the one Layer 6 path (D7)
    return (sidereal.bodies[Body.SUN].sidereal_longitude,
            sidereal.bodies[Body.MOON].sidereal_longitude)
```

The default is `default_evaluate`, exported by the module (not by the package surface). The
ephemeris lifecycle is the **caller's**: `default_evaluate` assumes an open `ephemeris_session`
exactly as `assemble_chart` and Layer 16 do, and opens or closes nothing itself — a caller
computing many transitions should not pay to reopen the ephemeris per call. A supplied
`evaluate` is called only at the query instant and at grid probes, receives aware UTC
datetimes, and must return the two Lahiri sidereal longitudes in `[0, 360)`; tests use it to
record probes, inject a stuck classifier and prove that validation failures make no
ephemeris call (the same pattern as Layer 16's `rise_after`).
* `local_transition(transition, timezone_id) -> LocalTransition` (zone via Layer 16
  `resolve_zone`; `InvalidTimezoneError` on a bad id).
* Constants: `ALL_KINDS` (canonical order), `DEFAULT_TOLERANCE = timedelta(milliseconds=100)`,
  `ALLOWED_TOLERANCES` (§4.2), `MAX_INTERVAL = timedelta(days=366)`, `MAX_REACH =
  timedelta(days=3)`, `SAFE_EVAL_START/END`, `SUPPORTED_START/END` (§4.6), `RATE_MIN`,
  `SEARCH_CONVENTION` (the exact string every result carries: predicate, grid rule, cell
  semantics, UT1 note).

Argument validation (all `ValueError` subclasses, raised before any ephemeris call):

| Condition | Error |
|---|---|
| naive datetime | `ValueError` from Layer 4 (unchanged) |
| instant, or any interval endpoint, outside `[SUPPORTED_START, SUPPORTED_END]` | `UnsupportedInstantError` |
| `end_utc <= start_utc`; `end_utc − start_utc > MAX_INTERVAL` | `IntervalError` |
| `kinds` not an iterable of `TransitionKind`; empty; containing a duplicate | `TransitionRequestError` (an invalid member is named; order of the input is irrelevant — the result uses canonical order) |
| `tolerance` not a `timedelta`, or not in `ALLOWED_TOLERANCES` | `TransitionRequestError` |

Run-time failures: `TransitionSearchError(RuntimeError)` for every "should be unreachable"
condition in §4 (bracket not verified within `MAX_REACH`, two changes of one kind inside one
cell, no JD progress, an evaluation instant outside `[SAFE_EVAL_START, SAFE_EVAL_END]`). The
engine's bare `RuntimeError` out of coverage is neither caught nor reclassified by message.

## 4. Algorithm

### 4.1 The predicate is the classifier

A transition of kind *K* is *defined* as a change of the Layer 16 index for *K*. The search
never solves `angle(t) = boundary` and then classifies; it evaluates
`index_K(t) = classifier_K(quantity_K(positions(t)))` and looks for the change. Consequently
every endpoint it reports carries a **verified** classification, and the float fact at
inexact boundaries cannot put an endpoint on the wrong side of what Layer 16 says at that
same instant.

### 4.2 The tolerance grid and the canonical cell

Let `tol` be the tolerance and `G(tol) = { EPOCH + n·tol : n ∈ ℤ }` with `EPOCH =
1970-01-01T00:00:00Z`. Two categories of evaluation:

* the **query classification** — one evaluation at the caller's exact instant `t0`, off the
  grid if the caller's instant is, so that `Neighbours.current` (and `k0`, the index the
  search departs from) is precisely Layer 16's answer at that instant. The query is **never
  snapped**; it is checked against the supported input range (§4.6) and nothing else;
* **search probes** — every other evaluation, each a grid point, each checked for reach and
  safe range before the call (§4.4).

The result of a search is the unique **cell** `(a, a + tol]`, `a ∈ G(tol)`, with `index(a) =
old` and `index(a + tol) = new`, both endpoints being probes. Because the grid is fixed in
absolute time and the evaluation at a grid point is a deterministic function of that point,
the cell depends only on the event and the tolerance — **not on the query origin, the initial
estimate or the expansion path** (probe P3/R2, §8: origins from −3 h to +9 h, an off-grid
origin, and both the tithi and the karana search returned the identical cell for Jalandhar's
Krishna Panchami end).

`ALLOWED_TOLERANCES = (1 ms, 10 ms, 100 ms, 1 s, 10 s, 1 min, 10 min, 1 h)`: each divides the
next, so the grids nest and the cell at a finer tolerance lies inside the cell at a coarser one
(probe P5). That nesting is what makes `same_event` well defined across tolerances. A `1 ms`
floor keeps every grid step ≥ 25 JD ULP (§2.3); the ceiling keeps a cell far below the
minimum gap between two changes of one kind (≈ 10 h for karana).

Interval semantics of the true change: under the monotonicity of §2.1, the instant τ at which
the frozen classification changes satisfies **τ ∈ (before_utc, after_utc]**. `before_utc` is
the last grid point verified on the old side and `after_utc` the first verified on the new
side; `after_utc` is a *verified new-side endpoint*, not the first representable instant of
the new element and not "the transition instant". Callers who need one number use
`after_utc` and read `tolerance` beside it.

### 4.3 Bracketing (time domain, verified, bounded)

For `next_transition(t0, K, tol)`:

1. Evaluate `e0 = element_K(t0)`, `k0 = e0.index`, `k1 = (k0 + 1) mod count`.
2. `g0 = snap_down(t0)`, `g1 = g0 + tol`. If `index(g1) ≠ k0` the change is inside `t0`'s own
   cell: require `index(g0) = k0` (else two changes in one cell → `TransitionSearchError`) and
   return `(g0, g1]`.
3. Initial estimate, **classifier-consistent and used only to size the first probe**:
   `est = (1 − e0.angular_fraction) · span / RATE_MIN[K]` days, rounded up to whole cells,
   at least one cell. `angular_fraction ∈ [0, 1)` by Layer 16 §4.2, so `est ∈ (0, span/RATE_MIN]`
   — the raw-offset arithmetic of v0.1 (`e0 − k0·span`, which is −1.4 × 10⁻¹⁴ at yoga index 7
   and becomes 360 under `mod 360`) is not used anywhere (finding 2; probe P1).
4. `lo = g1` (grid, verified old side), `hi = lo + step`. While `index(hi) = k0`: double `step`,
   `lo, hi = hi, hi + step`. **Reach is measured as the actual distance `|probe − t0|` from the
   caller's instant** — snapping and every accumulated expansion included — and checked before
   each probe against `MAX_REACH = 3 days` (§4.4); the counter of v0.2, which started at the
   step size and ignored the snap offset, is gone. With `RATE_MIN` 10 % under the measured
   minima the first probe lies at most `span/RATE_MIN + tol ≤ 1.26 d + 1 h` from `t0`, so a
   search that reaches the bound has had at least one expansion, i.e. the rate assumption has
   already failed observably. On exit `index(hi) = k1` is required (a `raise`, never an
   `assert`); any other index is a `TransitionSearchError`.
5. Bisection on the grid: `mid = a + ⌊cells/2⌋·tol`; `index(mid) = k0 → a = mid` else `b = mid`;
   until `b − a = tol`.

`previous_transition` mirrors it: `g0 = snap_down(t0)`; if `index(g0) ≠ k0` the change is
inside `t0`'s own cell and `(g0, g0 + tol]` is returned after verifying `index(g0 + tol) = k0`;
otherwise `hi = g0` (grid, verified new side), `est = e0.angular_fraction · span / RATE_MIN`,
`lo = hi − step` expanding backwards until `index(lo) = (k0 − 1) mod count`, then grid
bisection. There is no "1 µs shortcut" anywhere (finding 3): an instant exactly on a boundary
in Layer 16's sense is handled by the same grid logic as any other, and which side it is on is
established by evaluation, never assumed. Every guard in this section is a run-time `raise` of
a typed exception; the production module contains no `assert` statement, so nothing changes
under `python -O`.

### 4.4 Progress and evaluation guards

Before **each probe** (never the query classification): the instant is a grid point;
`|probe − t0| <= MAX_REACH`; the probe lies inside `[SAFE_EVAL_START, SAFE_EVAL_END]` (§4.6);
and, in bisection, `jd(a) < jd(mid) < jd(b)`. Any violation is a `TransitionSearchError`. The
query classification is guarded only by the input check (§4.6). Cost: `⌈log₂(bracket/tol)⌉ + 3`
evaluations; 21–24 for tithi at 100 ms (measured), ≈ 2 ms.

### 4.5 Typed failure, not silent widening

The rate constants, `MAX_REACH`, the one-change-per-cell property and monotonicity are all
assumptions the code *checks*. If any fails the call raises `TransitionSearchError` naming the
kind, the instants evaluated and which check failed. Nothing is widened, clamped or retried
with a different rule.

### 4.6 Coverage margins — inputs versus evaluations

Two ranges, checked at two different times:

* `SAFE_EVAL_START = 1800-01-02T00:00Z`, `SAFE_EVAL_END = 2399-12-31T00:00Z`: every evaluation
  instant is checked against these **immediately before the ephemeris call** (§4.4). They sit
  a day inside the observed cold-session edges (§2.2).
* `SUPPORTED_START = SAFE_EVAL_START + MAX_REACH = 1800-01-05T00:00Z`,
  `SUPPORTED_END = SAFE_EVAL_END − MAX_REACH = 2399-12-28T00:00Z`: inputs (the instant, both
  interval endpoints) are checked against these **before the first ephemeris call**. Since
  every probe is checked to lie within `MAX_REACH` of the caller's instant (§4.4), an input
  inside the supported range can never trigger the safe-range guard — the two ranges agree by
  construction (finding 6; probe R3: queries at `SUPPORTED_START` and `SUPPORTED_END` probed
  only inside `[SAFE_EVAL_START, SAFE_EVAL_END]`). The initial angle is not needed for this
  check. A listing walks from `cursor = after_utc` of each found cell, and each such walk is a
  fresh query whose own input check applies, so a listing near `SUPPORTED_END` fails typed at
  the first cursor outside the range rather than probing past it.

### 4.7 Listing

`list_transitions(start, end, kinds, tol)` for each kind, independently:

1. `p = previous_transition(start, K)`; include `p` iff **`start <= p.after_utc < end`** —
   both bounds (v0.2 tested only the lower one and would have listed an event at `end`;
   `list(b − 1 µs, b)` for a cell `(a, b]` must be, and now is, empty — probe R1). This covers
   a change whose cell straddles `start` while `start` is already on the new side, the case a
   `next_transition(start)`-only walk skips (finding 4).
2. `cursor = start`; repeat `n = next_transition(cursor, K)`: if `n.after_utc >= end` stop;
   else include `n` if `n.after_utc >= start`, set `cursor = n.after_utc`.
3. A hard bound of `⌈interval_days · RATE_MAX / span⌉ + 3` iterations per kind.

Membership rule: a transition is in `[start, end)` **iff `start <= after_utc < end`**, where
`after_utc` is the canonical cell end. Because the cell is origin-independent (§4.2), two
consecutive intervals `[s, m)` and `[m, e)` list exactly the transitions of `[s, e)`, with no
duplicate and no omission, **for any `m`** — inside a cell, at either cell endpoint, one
microsecond either side of them, or on no grid point at all (probes P4, R1) — including
intervals entirely inside a cell's new-side portion or entirely inside its old-side portion,
which are empty. What this contract does *not* claim: that the true change τ lies
inside the interval. When a split falls inside a cell, τ may be up to `tol` before
`after_utc`; the representative decides membership, and `tolerance` says how far the truth
may be from it.

Ordering: `transitions` is sorted by `(after_utc, canonical kind order)`. This is an order of
**representatives**. All cells of one listing lie on one grid, so two cells either coincide or
do not touch; for two adjacent entries with **identical cells and different quantities**
(§3 `Quantity`), the true order of the two changes is **not proven** by the data, and their
index pair is listed in `unordered_pairs`; consumers that need a proven order lower the
tolerance (nesting guarantees the finer cells lie inside the coarser ones). A tithi/karana pair
is never listed: both divide the elongation and their identical cell is one change at one
instant (§4.8), so there is no order to prove. When a nakshatra or yoga change shares a cell
with a coincident tithi/karana pair, the entries sort tithi, karana, then the other kind, and
only the adjacent (karana, other) pair is listed — the tithi's coincidence is implied by its
identical cell. Same-kind entries never share a cell.

### 4.8 Coincident changes (tithi and karana)

Every tithi boundary is a karana boundary, and `int(E·60/360) = int(2·(E·30/360))` exactly
(scaling a double by 2 is exact), so the two classifiers flip at the same instant. Because
cells are canonical, the tithi transition and the karana transition at that boundary have
**identical** `(before_utc, after_utc)` (probe P3: tithi 20→21 and karana 40→41 for
Jalandhar, from different origins, gave the same cell). The contract and the tests assert cell
equality, not "each contains the other's endpoint" (finding 5). New moon = tithi 30→1 with
karana 60→1 (Naga → Kimstughna); full moon = tithi 15→16 with karana 30→31 (Bava → Balava).

### 4.9 What the finite search does and does not establish

A yoga/nakshatra boundary at an inexact 40k/3° flips, in Layer 16, up to ~3 × 10⁻¹⁴° from the
mathematical boundary, i.e. ≈ 2 × 10⁻¹⁰ s of Moon motion — about **nine orders of magnitude**
below the 100 ms default cell. Layer 17 reports the flip Layer 16 sees.

**Conditional guarantees.** Verifying the classification at two grid points establishes that
the index differs between them. It does not, by itself, prove that the index changed exactly
once between them, nor that it is monotonic elsewhere. The numerical guarantees of §5 are
therefore **conditional on two documented assumptions**: (i) monotonicity of the three
quantities (§2.1) and (ii) separation — no two changes of one kind closer than the coarsest
tolerance (1 h; the physical minimum is ≈ 10 h for karana). The run-time checks detect every
*observable* violation — a bracket end that is not the successor element, a cell whose both
endpoints changed, a search that reaches `MAX_REACH` — and raise `TransitionSearchError`; a
violation invisible to the probes (a change and its reversal between two adjacent probes)
would not be detected, and the assumptions are what exclude it.

**Cross-platform.** The engine's longitudes were observed to differ between platforms by
~10⁻¹²° at the reference instants (FROZEN record); that is a measurement on a handful of
cases, not a bound over six centuries. Where the displacement of a change between two
platforms is smaller than one grid step, the two platforms' cells for that event are
**identical or adjacent** (they can differ only if the change straddles a grid point on one
platform and not the other, and then the cells share that point). No unconditional
cross-platform equality is claimed, and **no golden pinned to the second is claimed
reproducible everywhere**: reference values in tests are recorded as engine values on the
platform that produced them, and a cross-platform difference in a cell is reported as
environment-sensitive, exactly as the existing last-digit longitude differences are.

## 5. Accuracy contract

* **Numerical (conditional on §4.9's monotonicity and separation assumptions; every observable
  violation raises):** τ ∈ `(before_utc, after_utc]`, `after_utc − before_utc = tol`, both
  endpoints verified classifications on the tolerance grid.
* **Time-scale (inherited, qualified):** the engine uses UTC as UT1 (FROZEN §3.3). The
  `ut1_note` says: "|UT1 − UTC| ≤ 0.9 s under the leap-second regime in force since 1972; not
  asserted for instants before 1972 (when civil time was not UTC) or for future instants
  should that regime change; the frozen convention is applied throughout regardless."
  Presentation is to the second because nothing finer is astronomically meaningful in this
  engine.
* **Model (inherited, unquantified):** `model_note` states that the positions are the engine's
  (DE431-derived files, apparent longitudes, Lahiri true-equinox ayanamsha) and that Layer 17
  claims only "the instant at which *this engine's* classification changes". Microsecond
  fields are resolution, not accuracy.

## 6. File scope

* `src/vedic_chart/panchanga/transitions.py` — new. Imports: stdlib `dataclasses`, `datetime`,
  `enum`, `types` (`MappingProxyType`), `typing`; project `vedic_chart.astronomy.positions`
  (`Body`), `vedic_chart.sidereal.positions` (`calculate_sidereal_positions`),
  `vedic_chart.time.julian_day` (`julian_day_ut`), `.elements` (the four classifiers, spans,
  counts, `CALCULATION_CONVENTION`, `elongation`, `longitude_sum`), `.sunrise` (`utc_instant`,
  `resolve_zone`). No `swisseph`, no clock, no `round()`, no `zoneinfo` (through `.sunrise`).
* `src/vedic_chart/panchanga/__init__.py` — additive re-exports; `__all__` sorted.
* `tests/test_panchanga_transitions.py` — new.
* `tests/test_panchanga_boundaries.py` — narrowly amended (D1): the module table gains
  `transitions.py` with its allowed and actual import sets; the "exactly four modules" pin
  becomes five; nothing else in that file changes.
* `docs/LAYER17_PANCHANGA_TRANSITIONS_SPEC.md` — this file. `README.md` at promotion only.
* No lower-layer change (D7).

## 7. Test plan

**Membership, everywhere:** for every returned transition in every test,
`classifier(quantity(before_utc)).index == before.index`,
`classifier(quantity(after_utc)).index == after.index`, `after_utc − before_utc == tolerance`,
both endpoints on the grid.

**Cycles and wraps:** walk one lunation of tithi (0…29→0) and karana (0…59→0, names and
fixed/repeating from Layer 16's table) and one sidereal month of nakshatra (0…26→0) and yoga
(0…26→0) via `list_transitions`; explicit 0°/360° wrap cases; new and full Moon: tithi 29→0
with karana 59→0, tithi 14→15 with karana 29→30, asserting **identical cells** (§4.8).

**Adversarial origin/tolerance cases (findings 3–5):** the same event queried from −3 h, −1 s,
inside its own cell (old side and new side), at both cell endpoints, and +8 h: identical cell;
at tolerances 1 ms/10 ms/100 ms/1 s/1 min: nested cells and `same_event` true across all
pairs; the `after_utc` of a 1 ms cell — a verified new-side endpoint at most 1 ms after the
change, **not** an exact-boundary instant — queried as `previous_transition` (returns that
cell) and `next_transition` (returns the following event); an off-grid query (`t0 + 7 ms`)
returns the same cell as the on-grid one and is itself never probed or snapped; a value where
Layer 16's raw offset is negative (probe P1 style) driving `previous_transition` — the estimate
is zero and expansion must still find the change within one cell (no near-full-cycle search).

**Listing contract (finding 4, R1):** for a cell `(a, b]`: `list(b − 1 µs, b)` empty;
`[b − 2 ms, b)` split at `b − 1 ms` — whole, left and right all empty; `list(a + 1 µs, b)` empty;
`list(b, b + 1 µs)` is exactly the cell (`after_utc == start` included); `list(b + 1 µs, b + 1 s)`
empty; `list(a − 1 s, a + 1 µs)` empty; partition tests splitting a 4-day window inside a
cell, at `a`, at `b`, at `b ± 1 µs` and at non-grid points: left + right == whole, no
duplicates, no omissions; `unordered_pairs` populated exactly for overlapping adjacent cells of
different kinds (construct with a coarse tolerance around a near-coincident nakshatra/yoga
pair, then show it empties at a finer tolerance); sorting is by representative and the test
says so.

**Validation and ranges:** each row of the §3 table; `SUPPORTED_START − 1 ms` and
`SUPPORTED_END + 1 ms` → `UnsupportedInstantError` with `calculate_sidereal_positions`
monkeypatched to fail if called; `SUPPORTED_START` and `SUPPORTED_END` succeed live and every
probe they make lies inside `[SAFE_EVAL_START, SAFE_EVAL_END]` (recorded through the
injectable evaluator); the reach rule: with a 1 h tolerance and a query 59 min 59 s past a
grid point, every probe is within `MAX_REACH` of the query, and an injected classifier that
never changes raises `TransitionSearchError` at the reach bound (R3); a
**cold-session** test runs a subprocess whose first ephemeris call is at `SAFE_EVAL_START`
and another at `SAFE_EVAL_END`, then after a deliberate out-of-range failure (probe P7:
both edges evaluate cold and after a failure); `MAX_REACH` exhaustion and the
two-changes-in-one-cell guard exercised with an injected classifier (the search takes an
`evaluate` callable, defaulting to the Layer 6 path, exactly as Layer 16's `rise_after`).

**Presentation:** Asia/Kolkata, a DST day in Europe/London and America/New_York,
Pacific/Kiritimati; UTC fields unchanged by presentation; invalid zone.

**Reference births:** Jalandhar 1995-03-21 06:45 IST (drafting probe: Krishna Panchami began
1995-03-20 16:12:55 UTC-cell, ends 1995-03-21 13:45:08.2–13:45:08.3 UTC = 19:15:08 IST;
karana Kaulava → Taitila at 02:58:29.9–02:58:30.0 UTC) and Jammu 2001-02-04 10:45 IST; all
four kinds, pinned to the cell after the implementation's first run, labelled engine values.

**Independent numerical cross-check (tests only; not external validation):** a solver sharing
no code with `transitions.py`: `swe.calc_ut(jd, body, FLG_SWIEPH | FLG_SPEED)` for the tropical
Sun and Moon, `swe.set_sid_mode(SIDM_LAHIRI, 0, 0)` then `swe.get_ayanamsa_ex_ut(jd, 0)` for the
ayanamsha (the frozen accessor's exact calls), inside the same `ephemeris_session` the test
opened, JD from the FROZEN `julian_day_ut` on the same datetimes; angles unwrapped in time
explicitly; the crossing of `k·span` located by the secant method on the continuous angle to a
convergence of |Δt| < 1 ms. **Acceptance:** the secant root lies in
`(before_utc − 1 ms, after_utc + 1 ms]` — the cell plus the second solver's own convergence
tolerance and nothing else; both solvers use the same time argument, so no allowance for the
UT1 convention is added. It checks the bracketing/bisection logic, not the sky.

**External comparison with a minute-resolution published reference (separate, labelled,
retrieved):** NASA GSFC "Moon Phases: 2001 to 2025"
(`https://eclipse.gsfc.nasa.gov/phase/phase2001gmt.html`, Fred Espenak, Meeus algorithms,
Universal Time to the minute) was retrieved 2026-09-24 and is reproduced in §8.2 for the
fourteen phases compared. The test pins those fourteen published minutes with the URL and
retrieval date beside each, and asserts the engine's cell end within ±60 s. This is
**agreement with a minute-resolution reference computed by a different method**, not a proof
of astronomical accuracy: the table's rounding is ±30 s and its ephemeris is not DE431. USNO's API
(`https://aa.usno.navy.mil/api/moon/phases/date?date=…&nump=…`, documented at
`https://aa.usno.navy.mil/data/api`, Universal Time) could not be fetched from this session —
the fetch tool refused the endpoint as outside its provenance set twice — and is left as an
optional second source. IMD's daily panchang (tithi/nakshatra/yoga/karana ending moments, IST)
was attempted through the browser pane on the owner's Mac, which was unreachable at the time;
it remains a planned comparison. No recalled times are used anywhere.

**Suites:** Layer 17's file, then the full suite baseline and updated in the same environment;
environment-dependent failures reported separately (cloud: the known 12; session VM: 0). No
golden regenerated, no assertion relaxed, no calculation changed.

## 8. Probes run for this draft (scratch, not production; `Claude outputs/l17_probe.py`)

8.1 Engine at `2c5b180`, cloud sandbox, Python 3.11:

| Probe | Result |
|---|---|
| P1 raw-offset arithmetic at yoga index 7 | raw offset −1.42 × 10⁻¹⁴, `% 360` → 360.0; Layer 16 `angular_fraction` 0.0 → estimate 0.0° (no cycle-long search) |
| P2 datetime vs JD progress | 1 µs steps: 975/1000 leave the JD unchanged; 1 ms steps: 0/1000; ULP 40.2 µs |
| P3 canonical cell, four origins (−3 h … +9 h) | identical cell `(13:45:08.200, 13:45:08.300]` UTC, 21–24 evaluations each |
| P3 coincident tithi 20→21 / karana 40→41, two origins | identical cell |
| P3 repeat queries from `a`, `b`, `a + 1 µs`, `a + tol/2` | same cell each time |
| P4 partition of a 4-day window at a split inside the cell / at `a` / at `b` / at `b + 1 µs` | left + right == whole in all four cases |
| P5 tolerances 1 s / 100 ms / 10 ms / 1 ms | nested cells `(…08.000, …09.000] ⊃ (…08.200, …08.300] ⊃ (…08.280, …08.290] ⊃ (…08.289, …08.290]` |
| P6 rate survey 1800–2399 | E ≥ 10.782, λ_M ≥ 11.774, Y ≥ 12.734 °/day; \|dA/dt\| ≤ 9.45 × 10⁻⁵ °/day |
| P7 cold sessions | first call at 1800-01-02 and 2399-12-31 succeed; still succeed after a deliberate out-of-range failure; 1800-01-01 00:00 fails cold |

8.1a Regression probes for v0.3 (`Claude outputs/l17_probe_v3.py`, 29 checks, 0 failures):

| Probe | Result |
|---|---|
| R1 `list(b − 1 µs, b)`; `[b − 2 ms, b)` split at `b − 1 ms`; `list(a + 1 µs, b)`; `list(b + 1 µs, b + 1 s)`; `list(a − 1 s, a + 1 µs)` | all empty |
| R1 `list(b, b + 1 µs)`; `list(b − 50 ms, b + 50 ms)`; `list(a, b + 1 µs)` | exactly the cell |
| R1 partitions of a 4-day window at inside-cell / `a` / `b` / `b ± 1 µs` / off-grid −7 ms | left + right == whole, no duplicates, in all six |
| R2 off-grid query `t0 + 7 ms` | query classified at the exact instant and equal to Layer 16's direct classification; never probed, never snapped; every probe and both endpoints on the grid; same cell as the on-grid query |
| R3 reach | max `|probe − t0|` = 17 h 13 m for the Jalandhar search; 1 h tolerance with a 59 m 59 s snap offset stays within reach; stuck classifier → `TransitionSearchError` at the bound; queries at `SUPPORTED_START`/`SUPPORTED_END` probe only inside the safe range; `SUPPORTED_END + 1 µs` refused before any evaluation |
| R4 rates | `RATE_MIN` ≤ 0.9 × measured minima; 30 successive tithi searches needed no expansion |
| Coincident | tithi 20→21 and karana 40→41 share the identical cell |

8.2 External comparison, engine tithi cells (1 s tolerance) versus NASA GSFC published minutes:

| Phase | NASA GSFC (UT) | Engine cell end (UTC) | Δ |
|---|---|---|---|
| New | 2024-01-11 11:57 | 11:57:25 | +25 s |
| Full | 2024-01-25 17:54 | 17:54:01 | +1 s |
| New | 2024-02-09 22:59 | 22:59:11 | +11 s |
| Full | 2024-02-24 12:30 | 12:30:27 | +27 s |
| New | 2024-03-10 09:00 | 09:00:27 | +27 s |
| Full | 2024-03-25 07:00 | 07:00:20 | +20 s |
| New | 2024-06-06 12:38 | 12:37:45 | −15 s |
| Full | 2024-06-22 01:08 | 01:07:54 | −6 s |
| Full | 2024-12-15 09:02 | 09:01:42 | −18 s |
| New | 2024-12-30 22:27 | 22:26:49 | −11 s |
| Full | 2025-03-14 06:55 | 06:54:40 | −20 s |
| New | 2025-03-29 10:58 | 10:57:51 | −9 s |
| Full | 2025-09-07 18:09 | 18:08:55 | −5 s |
| New | 2025-09-21 19:54 | 19:54:09 | +9 s |

All fourteen within ±30 s, the published table's rounding. This is agreement with a
minute-resolution published reference computed by a different method; it is neither a proof
of astronomical accuracy nor a statement about Layer 17's own precision.

## 9. Usage

```python
from datetime import datetime, timezone, timedelta
from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.panchanga import (TransitionKind, find_transitions, list_transitions,
                                   local_transition)

with ephemeris_session("ephe"):
    t = find_transitions(moment, kinds=(TransitionKind.TITHI, TransitionKind.KARANA))
    n = t.neighbours[TransitionKind.TITHI].next
    n.before.name, n.after.name        # 'Panchami', 'Shashthi'
    n.after_utc, n.tolerance           # verified new-side endpoint, 100 ms
    local_transition(n, "Asia/Kolkata").after_local

    week = list_transitions(datetime(2026, 1, 19, tzinfo=timezone.utc),
                            datetime(2026, 1, 26, tzinfo=timezone.utc),
                            tolerance=timedelta(seconds=1))
    week.unordered_pairs               # adjacent cross-kind cells whose order is not proven
```

## 10. Decisions (all closed at v1.0)

**D1** `transitions.py` inside `vedic_chart.panchanga` with the narrow boundary-test amendment
— approved (v0.2). **D2′** cells on an absolute grid, `ALLOWED_TOLERANCES` as listed, default
100 ms, presentation to the second — approved (v0.3). **D3′** `SAFE_EVAL` one day inside the
nominal edges, `MAX_REACH` 3 d, `SUPPORTED` = `SAFE_EVAL` ± 3 d, reach measured from the query
— approved (v0.3). **D4′** membership by representative `after_utc` on `[start, end)`,
`MAX_INTERVAL` 366 d, `unordered_pairs` for different-quantity pairs sharing a cell — approved
(v0.3). **D5** external retrieval — approved (v0.2); NASA GSFC retrieved, USNO API and IMD
outstanding (§7, §13). **D6** vara excluded — carried. **D7** Layer 6 path only, no lower-layer
addition — carried. **D8′** rate minima pinned from the full-range survey at −10 %, correctness
independent of them — approved (v0.3; constants in §12).

## 11. Change log

### v0.3 (five corrections, all demonstrated by `l17_probe_v3.py`)

1. Listing: the initial `previous_transition(start)` candidate must satisfy both bounds
   `start <= after_utc < end` (§4.7; R1).
2. Grid: the query classification is evaluated off-grid at the caller's instant and never
   snapped; probes and endpoints are grid points; guards apply per category (§4.2, §4.4; R2).
3. Reach: `MAX_REACH` is enforced on the actual `|probe − t0|` including snapping and
   accumulated expansion, before every probe; typed exceptions, no `assert` (§4.3, §4.4; R3).
4. Guarantees qualified: conditional on monotonicity and separation, run-time checks detect
   observable violations only; cross-platform "identical or adjacent" conditional on the
   displacement being under one grid step; no unconditional second-precision golden claim
   (§4.9, §5).
5. Wording: `RATE_MIN` = measured minima − 10 % (§2.1; R4); a 1 ms cell's `after_utc` is a
   verified new-side endpoint (§7); NASA comparison labelled as agreement with a
   minute-resolution reference (§7, §8.2).

### v0.2 from v0.1 (the eight findings)

1. τ ∈ `(before_utc, after_utc]`; `after_utc` is a verified new-side endpoint (§4.2, §5).
2. Angular estimate from Layer 16's `angular_fraction` only; verified time-domain bracketing
   with bounded doubling; no raw-offset `mod 360` (§4.3, probe P1).
3. No 1 µs shortcut; grid of ≥ 1 ms; JD progress checked before each evaluation (§2.3, §4.4).
4. Canonical absolute-grid cells give origin-independent results, `EventId`/`same_event`,
   start-inclusive listing via `previous_transition(start)`, partition proved for any split
   (§4.2, §4.7, probes P3–P5); sorting of representatives distinguished from proven order
   (`unordered_pairs`).
5. Coincident tithi/karana: identical cells by construction; the impossible mutual-containment
   requirement removed (§4.8).
6. `SAFE_EVAL` vs `SUPPORTED` reconciled through `MAX_REACH`; input validation before the first
   call, evaluation guard before every call; rates empirical with the ayanamsha derivative
   accounted; cold-session tests (§2.1, §2.2, §4.6, §7).
7. UT1 note qualified to the leap-second era; "nine orders"; cross-platform guarantee stated as
   identical-or-adjacent cells; cross-check frame/flags/lifecycle pinned and its acceptance
   band reduced to the cell plus the second solver's convergence (§4.9, §5, §7).
8. `neighbours` mapping keyed by the requested kinds; `kinds`/`tolerance` validation table;
   canonical ordering; typed errors (§3).

## 12. Implementation record (2026-09-24, cloud sandbox, Linux x86_64, Python 3.11)

Files: new `src/vedic_chart/panchanga/transitions.py` (1159 lines, no `assert`, no `round()`,
no clock, no `swisseph`) and `tests/test_panchanga_transitions.py` (136 tests); additive
re-exports in `src/vedic_chart/panchanga/__init__.py`; the narrow D1 amendment of
`tests/test_panchanga_boundaries.py` (five modules, the new module's allowed and exact imports,
the extended `__all__`; every other assertion unchanged). No other file touched.

Equivalence with the reference probe: 256 next/previous cells (both births, all eight
tolerances, four origins, four kinds) and a 30-day all-kinds listing — identical.

Survey (1800-01-05 … 2399-12-28, one 40-day window per 10 years at 4-hour steps, 14 701
samples; dense check one window per year at 1-hour steps, 577 561 samples): E 10.7427–14.3753
(dense 10.7408–14.3845), λ_M 11.7614–15.3933 (11.7603–15.4008), Y 12.7800–16.4113
(12.7752–16.4193) °/day; |dA/dt| ≤ 1.04 × 10⁻⁴ °/day; tropical speeds, dA/dt-corrected speeds
and finite differences agree to ~10⁻⁴ °/day. Pinned `RATE_MIN` 9.66/9.66/10.58/11.46 (two of the
draft's values were lowered because 0.9 × the surveyed minima fell below them), `RATE_MAX`
15.83/15.83/16.95/18.07.

Reference cells (100 ms, UTC; engine values, environment-sensitive per §4.9; every row
re-read from `find_transitions` at promotion — three Jalandhar dates in the v0.3 draft of this
table were wrong in the prose, the tests and implementation were not):

| Birth / kind | Previous (began) | Next (ends) |
|---|---|---|
| Jalandhar tithi | 1995-03-20 16:12:55.0–.1 Chaturthi→Panchami | 1995-03-21 13:45:08.2–.3 Panchami→Shashthi |
| Jalandhar karana | 1995-03-20 16:12:55.0–.1 Balava→Kaulava | 1995-03-21 02:58:29.9–30.0 Kaulava→Taitila |
| Jalandhar nakshatra | 1995-03-20 09:53:21.7–.8 Swati→Vishakha | 1995-03-21 08:08:56.6–.7 Vishakha→Anuradha |
| Jalandhar yoga | 1995-03-20 06:27:42.3–.4 Vyaghata→Harshana | 1995-03-21 03:16:31.7–.8 Harshana→Vajra |
| Jammu tithi | 2001-02-03 23:13:06.4–.5 Dashami→Ekadashi | 2001-02-04 20:53:13.8–.9 Ekadashi→Dwadashi |
| Jammu karana | 2001-02-03 23:13:06.4–.5 Garaja→Vanija | 2001-02-04 10:07:50.8–.9 Vanija→Vishti |
| Jammu nakshatra | 2001-02-04 02:36:52.2–.3 Rohini→Mrigashira | 2001-02-05 00:53:02.8–.9 Mrigashira→Ardra |
| Jammu yoga | 2001-02-03 08:16:47.8–.9 Brahma→Indra | 2001-02-04 05:32:43.0–.1 Indra→Vaidhriti |

NASA GSFC comparison inside the test file: all fourteen phases within ±60 s (observed −20.6 s
to +26.4 s). Cross-check solver (direct `swisseph`, secant, 1 ms): every cell accepted over
≥ 12 transitions per kind. A defect the tests caught before delivery: `LocalTransition`'s
consistency check compared local datetimes with `!=`, which Python never satisfies across a
fall-back hour; it now compares by subtraction.

Suites: new file 136 passed, normally and under `python -O`; full suite in the sandbox 3626
passed / 12 failed, the failures being exactly the 12 pre-existing environment-dependent golden
failures of this environment (baseline 3482 / 12). Session-VM results are in §13.

## 13. Validation record at v1.0

Three environments, recorded separately; none stands in for another.

| Environment | What was run | Result |
|---|---|---|
| **Native macOS** (owner's machine: Darwin arm64, Python 3.11.16, native pyswisseph; the existing pure-Python pytest installation reused, no dependency installed) | Targeted: `tests/test_panchanga_transitions.py` + `tests/test_panchanga_boundaries.py`, normally and under `python -O` | 194 passed normally; 194 passed under `-O`. **Targeted verification only — not a native full-suite run, and not claimed as one.** |
| **Session VM** (Linux aarch64, project `.venv` Python 3.10.12) | Full suite, baseline at `2c5b180` and updated, same environment | baseline 3494 passed / 0 failed; updated 3638 passed / 0 failed; the new file 136 passed normally and under `-O`; Jalandhar's Panchami→Shashthi cell identical to the sandbox's (13:45:08.200–.300 UTC) |
| **Cloud sandbox** (Linux x86_64, Python 3.11.15) | Full suite, baseline and updated, same environment | baseline 3482 / 12; updated 3626 / 12 — the identical 12 pre-existing environment-dependent golden failures, none new; 136 passed under `-O` |

Independent implementation review (owner-commissioned): no functional blocker; three
Jalandhar dates in §12's prose table corrected at promotion (implementation and tests were
already right).

Outstanding external comparisons, retained as limitations: the NASA GSFC phase table is
**agreement with a minute-resolution reference computed by a different method**, not a proof
of astronomical accuracy (§7, §8.2); the USNO Phases API and the IMD daily panchang ending
moments have **not** been retrieved or compared. Cross-platform stability of the pinned cells
is established for the two Linux builds and the native-macOS targeted run only (§4.9).
