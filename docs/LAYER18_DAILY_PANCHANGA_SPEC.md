# Layer 18 — Daily Panchanga (sunrise to sunrise)

**Status:** SPECIFICATION v1.0 (promoted 2026-09-27 by the project owner after the
implementation review passed and the native-macOS targeted verification recorded in §17.4).
History: DRAFT v0.1 and v0.2 (2026-09-25), DRAFT v0.3 (2026-09-26, with the §4.7 correction
of the owner's review), implemented 2026-09-27 against v0.3; the review findings of each
round and their resolutions are in §16, the implementation record, actual test results, final
ranges and file manifest in §17, and the limitations retained at v1.0 in §15. The conventions
fixed at v1.0: the canonical anchor grid (§4.1) with closing = the next sunrise's own canonical
locating (§4.3), the two membership predicates kept distinct (§2, §7.1), the image check
(§7.2), placement by index on datetime cells (§4.6), bounded neighbour information (§6), the
explicit-ordinal contract (§4.3, §9, §10), the separate date and instant ranges (§4.7), and the
result-not-exception treatment of unavailable, ambiguous and lone-sunrise dates (§6). Any
change to a convention recorded here requires a new specification version and owner
approval. Baseline: commit `d90ebb0` (`master`, clean tree and index, 141 tracked files, no deployment
files tracked). Nothing in this document changes the FROZEN v1.0 calculation specification
(`docs/CALCULATION_SPEC.md`), Layer 16 v1.0 (`docs/LAYER16_PANCHANGA_SPEC.md`) or Layer 17 v1.0
(`docs/LAYER17_PANCHANGA_TRANSITIONS_SPEC.md`): no formula is recalculated, no second sunrise
convention is introduced, no classification epsilon is added, no lower-layer value is adjusted,
no existing test, golden or fixture changes. The deployment kit under `Claude outputs/` and the
viewer/CLI/HTTP surfaces are outside this milestone.

Accepted at the v0.1 review: the canonical-anchor direction (§4.1), no lower-layer accessor
(§3.1), the containing-instant entry point (§10), closing-side information (§4.6) and the
opening-element cross-check (§4.5). Decided at the v0.2 review: D7 (the Layer 16 limitation
paragraph, text in §13), D9(a) (tolerance validation restated from the public
`ALLOWED_TOLERANCES`, with parity tests), D10 (`FIRST_ANCHOR` supplies informational
`preceding_sunrise` data only, never a canonical boundary); D8 (the range constants) accepted
provisionally, subject to the fresh-interpreter edge checks and to the revised containing-form
algorithm of §4.3. The review findings and their resolutions are in §16.

## 1. Scope

Backend only. Given a **local civil date**, coordinates and an IANA zone — or an instant and the
same place — Layer 18 returns the **Panchanga day** that opens at the geometric Hindu sunrise
carrying that civil date (or containing that instant) and closes at the next sunrise, composed
from:

* Layer 16 (`find_sunrise_window`, `vara_from_sunrise`, the element classifiers) for the two
  sunrises, the vara and the four angular elements at the opening sunrise;
* Layer 17 (`find_transitions`, `list_transitions`) for the transitions of the interval, with
  Layer 17's cells, tolerances, event identities, ordering and `unordered_pairs` carried as they
  are.

Layer 18 adds exactly three things: the mapping *civil date (or instant) → sunrise pair* (§4), a
rule that makes consecutive days share one sunrise **bit for bit** (§4.3), and the placement of
each listed transition relative to the two sunrises (§4.6). Everything else is a field copied
from a lower layer's result.

Excluded: UI, HTTP, CLI, festivals, lunar months and their naming, muhurta, Rahu Kalam, sunset,
moonrise, place-name resolution, assumed birth-time defaults, any change to Layers 16 and 17.

## 2. Definitions

**Civil date.** A `datetime.date` read in the supplied IANA zone. Layer 18 never assumes that a
civil date is 24 hours long, that it begins at a unique midnight, that it exists (a zone can
skip a date: `Pacific/Apia` 2011-12-30, `Pacific/Kiritimati` 1994-12-31) or that it occurs once
(`America/Anchorage` repeats 1867-10-19 when its LMT offset moves from +14:00:24 to −09:59:36).
The zone is used for exactly one thing, as in Layer 16: naming the civil date of a sunrise.

**Sunrise.** Layer 16's geometric Hindu rising (`SUNRISE_CONVENTION`), obtained only through
`find_sunrise_window`. Layer 18 never calls the astronomy boundary and never re-implements
Layer 16's bracketing: it does not call `default_rise_after` or `calc_sunrise_hindu` itself.

**Panchanga day.** The half-open interval `[opening, closing)` between two consecutive sunrises,
in the Julian Day (UT) domain, with Layer 16's membership rule: an instant whose Julian Day is
`>= opening` and `< closing` belongs to the day (Layer 16 D5: equality at a sunrise is the new
day). Its vara is the weekday of the civil date of `opening` — `vara_from_sunrise` applied to
the opening window, so the vara of the day for date *D* is the weekday of *D* by construction.

**The day of a civil date.** The Panchanga day whose opening sunrise has civil date *D* in the
zone. This is the same reading Layer 16 uses to name a vara, so "the day of *D*" and "the day
whose vara is *D*'s weekday" coincide. Zero or two sunrises may carry *D* (§6); the result then
says so instead of choosing.

**Two membership predicates.** Layer 16 decides whether an instant belongs to a day on Julian
Day floats (`opening_jd <= jd(t) < closing_jd`). Layer 17 decides whether a transition belongs
to an interval on microsecond datetimes (`start_utc <= after_utc < end_utc`). Layer 18 keeps
both, unchanged, and never pretends they are the same predicate: §7.1 says exactly where they
differ.

**Event identity of a sunrise.** Two Julian Day floats returned by Layer 16 denote the same
sunrise when they differ by less than `SAME_SUNRISE_MAX_SEPARATION = 0.5` day. This is not an
epsilon: consecutive sunrises are never less than about 22 hours apart (Layer 16 §3), while the
largest difference measured between two locatings of one sunrise is ~14 ms (§12, probe A — a
measurement at sampled latitudes, not a bound). The rule is only ever used to tell "same
sunrise, located again" from "the next sunrise"; it is never used to compare an instant with a
sunrise.

## 3. What is fixed by the layers below, and what this draft measured

### 3.1 The datetime image of a sunrise float

Layer 16 decides membership on Julian Day floats; `SunriseWindow.previous_utc` is
`datetime_from_julian_day(previous_julian_day_ut)`, rounded to the microsecond. Layer 18 needs
`julian_day_ut(previous_utc) == previous_julian_day_ut` — the datetime image must name the same
float — and this holds for every float in the supported range, by the following bound (probe D5
measured every term):

* Every Julian Day in [1800, 2400] lies in the binade [2²¹, 2²²), where one ULP is 2⁻³¹ day
  = 40.233 µs; a float is recovered by the final rounding whenever the accumulated error before
  it is below half an ULP, 20.117 µs.
* Forward (`datetime_from_julian_day`): `jd − 2440587.5` is exact (both operands in one binade);
  `× 86400` produces a value below 2³⁴ s, whose ULP is 2⁻¹⁹ s = 1.907 µs, so the product's
  rounding error is at most 0.954 µs; `timedelta` then rounds to the microsecond, at most
  0.5 µs. Total at most **1.454 µs**. The largest error found in 200,000 random floats over
  1800–2399 was 1.4534 µs (near 2389); a native sample near 2399 gave ≈ 1.447 µs. v0.1's
  "well under 1 µs" was wrong and is withdrawn.
* Reverse (`julian_day_ut`): `timestamp()` is CPython's correctly rounded integer division, at
  most 0.954 µs (half an ULP of the seconds value); `/ 86400` is correctly rounded, at most half
  an ULP of the day offset (2.515 µs at 2399, so 1.257 µs); total before the final `+ 2440587.5`
  at most **2.211 µs**.
* Forward plus reverse: at most 3.67 µs, below 20.117 µs, so the final rounding returns the
  original float. Round trip mismatches in 200,000 random floats: 0; in 1,011 real sunrises: 0.

Layer 18 relies on this **and checks it** at every sunrise it reports (`DaySearchError`
otherwise, §7.2); it never adjusts a datetime or a float to make it true. The other direction —
a microsecond datetime through `julian_day_ut` and back — is **not** exact (the float grid is
40 µs; probe E measured a 12 µs shift) and Layer 18 never uses it for anything it stores.

Because the datetime grid is finer than the float grid, about 40 microsecond datetimes map to
each sunrise float (probe D4: 19 below and 20 above the image at both Jalandhar sunrises). This
is why the two membership predicates of §2 differ at the endpoints (§7.1). No accessor is
needed: Layer 16's public `find_sunrise_window` with microsecond-exact anchors suffices (D2 of
v0.1, accepted).

### 3.2 A sunrise float depends on the probe it was asked from

Asked from different instants of the same day, Layer 16 returned the identical float for one
sunrise in every sample at Jalandhar, Jammu, Apia, Ushuaia (−54.8°), Anchorage (61.2°) and
Reykjavik (64.1°) **from instants 0.5 h to 22.5 h after it**, and floats differing by up to
13.6 ms at 65.5°, 66.5° and 69.6° (Tromsø) from every instant — the library's 28-hour search
converges to a slightly different value from each start (§12, probe A). The implementation's
parity test then found the lower-latitude reproducibility to be a property of the probe
positions, not of the latitude (§12, probe G; §17): Layer 16's first probe is `instant − 2 d`,
and when the two days before the closing together exceed 48 hours, an instant in the last
minutes before the closing puts that probe just after the previous sunrise; the library, asked
from about a day before the opening, then returns a float for it 141 ms away at Ushuaia (March
2024, 40 of 40 dates at `closing.utc − 1 s`), 84 ms at Jalandhar (August), 88 ms at Anchorage
and 36 ms at London (September), and the direct library call shows the float moving by about
0.1 ms per hour of probe offset even in the ordinary positions. Layer 16 §3 records the
library's method change at about 65°; all of these are **measurements at the sampled places
and dates, not universal bounds**, and every statement in this document that rests on them is
phrased as such. Consequence, measured: at Tromsø, `calculate_panchanga(window.previous_utc, …)` — Layer
16 asked at the exact datetime of a sunrise it had just returned — bracketed that instant into
the **previous** day on 26 of 60 dates (Feb–Mar 2024), because its fresh search located the
same sunrise a few milliseconds later than the instant. This is within Layer 16's contract (it
promises comparisons on the floats it returns and says nothing about a second search), but it
means Layer 18 cannot obtain the vara or the membership of the opening instant by calling
`calculate_panchanga` at it. §4.3 and §7.3 are the consequences.

### 3.3 Layer 17 facts used

Layer 17 lists a transition in `[start, end)` by its representative `after_utc` and guarantees
that adjacent intervals partition exactly **when they share the same endpoint datetime**; Layer
18's job is therefore to hand consecutive days the same endpoint. `previous_transition(t)`
returns the transition into the element current at `t`: its `after.index` is that element's
index, and its cell may contain `t` or end exactly at `t`. Element records (`Tithi`, `Karana`,
`Nakshatra`, `NityaYoga`) carry the instantaneous longitude and progress fields, so two records
of the same classification taken at different instants are **not equal** (probe D1: inside the
Jalandhar tithi cell, at 13:45:08.225 UTC, `current.index == before.index == 19` while
`current != before` and `current != after`). Placement therefore compares indices (§4.6);
whole-record equality is used only between two evaluations of the same instant (§4.5).

## 4. Algorithm

### 4.1 Anchor grid

`ANCHOR_EPOCH = 1970-01-01T00:00Z`, `ANCHOR_STEP = 12 h`. Anchor *k* is
`ANCHOR_EPOCH + k × ANCHOR_STEP`, a microsecond-exact UTC datetime independent of the request.
Every sunrise Layer 18 reports as an opening or a canonical closing is the `previous_*` of
`find_sunrise_window(anchor_k, …)` for the **first anchor inside that sunrise's window** — a
deterministic function of `(k, latitude, longitude, timezone_id)`. Because the grid is global,
two requests that need the same sunrise ask Layer 16 the same question and get the same float.
That is the whole of the consecutive-day rule.

### 4.2 The walk and its entries

A walk visits every anchor in a closed range in increasing *k*, calling `find_sunrise_window`
once per anchor, and produces a tuple of **entries** in anchor order:

* `Located(anchor, window, canonical)` — the result was a `SunriseWindow` whose
  `previous_julian_day_ut` is a new event (no `Located` entry within
  `SAME_SUNRISE_MAX_SEPARATION` before it). `canonical` is True unless this is the walk's very
  first anchor: a sunrise first seen at the first anchor may have been locatable from an earlier
  anchor the walk did not visit, so its float is not guaranteed canonical and it is never a
  candidate, an opening or a closing — it may only supply `preceding_sunrise` information,
  reported with `located_by = FIRST_ANCHOR` (D10, approved).
* nothing — the result was a window whose previous is the sunrise already located (a later
  locating of the same event; its float may differ by milliseconds and is discarded), **or** a
  `SunriseUnavailable` repeating the reason of the entry before it;
* `Unavailable(anchor, result)` — a `SunriseUnavailable` with a reason different from the entry
  before it (a stretch of anchors with one reason is one entry). Layer 16's three reasons occur
  in sequence across a polar stretch — `REASON_NO_NEXT_SUNRISE` while the last sunrise is still
  within two days behind the anchor, then `REASON_NO_PREVIOUS_SUNRISE` once it is not (probe D3:
  Tromsø, May 2024, four anchors of the first then five of the second) — so no rule may assume a
  stretch carries one reason.

Every `Located` window's `next_*` is also information: a **next-only sunrise** is a window's
`next` whose event is not the `previous` of any `Located` entry — the sunrise that closes a day
but opens none (Layer 16 finds no consecutive pair from it: the last sunrise before a polar
day, probe D3 at 66.57 N: the 06-18 window's next, 06-19 01:26, is followed by unavailability
until a canonical sunrise on 06-23). Next-only sunrises are located once, by their own window,
and are reported with `located_by = WINDOW_NEXT`.

Guards, all `if`/`raise` (`DaySearchError`, a `RuntimeError`), never `assert`: a `Located`
sunrise not later than the one before it; a `Located` sunrise earlier than the `next` of the
window before it by more than `SAME_SUNRISE_MAX_SEPARATION` (a sunrise Layer 16 skipped over);
a walk that produces no entry at all. A `Located` sunrise **later** than the previous window's
`next` by more than that separation is not an error: it is the first sunrise after a gap.

### 4.3 Selecting a day

**Date form.** For civil date *D*, let `D0 = D at 00:00 UTC` (built from the date's fields; a
bookkeeping origin, never a boundary of the day). The walk range is
`[D0 − WALK_BEFORE, D0 + WALK_AFTER]`, `WALK_BEFORE = 48 h`, `WALK_AFTER = 108 h` (14 anchors).
The **candidates** are the canonical `Located` sunrises whose `previous_local.date() == D`, in
time order.

* one candidate, or `sunrise_ordinal` naming one → it is the opening;
* zero → `PanchangaDayUnavailable` (§6), **whatever `sunrise_ordinal` says** — a valid positive
  ordinal never turns a date without a candidate into an error, and the result is the same
  as an ordinal-free request's; the next-only sunrise dated *D* is reported as the lone
  sunrise if there is one;
* two or more and no ordinal → `PanchangaDayAmbiguous` (§6); an ordinal larger than a
  **nonzero** count → `DayRequestError` after the walk (§9, post-discovery).

**Containing form.** For an instant *t* (normalised through `utc_instant`, Julian Day `jd(t)`),
the walk range is `[t − 72 h, t + 60 h]` (eleven anchors when *t* is off the anchor grid,
twelve when it is on it; v0.3 said twelve). The opening is the last canonical
`Located` sunrise with `previous_julian_day_ut <= jd(t)`; the closing is selected as below; the
result is a complete day **only if `opening_jd <= jd(t) < closing_jd`**. Otherwise *t* lies
after a next-only sunrise or inside an unavailable stretch and the result is
`PanchangaDayUnavailable` with `SUNRISE_UNAVAILABLE` (probe D3: Tromsø, 2024-05-22 12:00 UTC —
the last located sunrise at or before the query opens 05-19 23:22:57 UTC and its window's next
is 05-20 23:06:14 UTC; the query is a day and a half later; v0.1's "largest located sunrise at
or before the query" would have returned that day and is withdrawn). Layer 16's own answer at
*t*, `find_sunrise_window(t)`, is carried as `layer16_at_instant` for comparison and never used
for control flow: within the ~14 ms measured at high latitude the two may disagree about which
side of a sunrise *t* is on (§7.3), and Layer 18 answers by its canonical floats.

**The containing form's civil date and ordinal come from the date form's enumeration.** Once
the opening is found, `civil_date = opening.local.date()` and the ordinal is obtained by running
the **same** date-selection helper the date form uses — the 14-anchor walk of
`[D0 − 48 h, D0 + 108 h]` for that date and its canonical candidates — and finding the
opening's float among the candidates (exact identity: both walks locate it at the same anchor,
§4.1). Counting candidates inside the containing walk itself is wrong and is withdrawn: that
walk can locate the containing day while an earlier canonical sunrise carrying the same civil
date is seen only at the walk's first anchor (`FIRST_ANCHOR`, not a candidate). Probe F1
reproduces it with Layer 16 unchanged and an injected sunrise sequence — UTC 1867-10-18 10:00
plus *n* × 47 h in `America/Anchorage`, whose real 1867 date repetition puts two of those
sunrises on civil date 1867-10-19; each 47-hour gap is inside Layer 16's two-day limit, so this
is **synthetic coverage of the allowed-gap contract, not an observed astronomical sequence**.
Query 1867-10-22 07:00 UTC: the date form for 1867-10-19 finds two canonical candidates; the
containing walk (anchors from 1867-10-19 12:00 UTC) sees the first only as `FIRST_ANCHOR` and
the second as canonical, so counting inside it gives ordinal 1, and the date form with ordinal
1 selects the wrong day (opening 10-18 09:59 UTC instead of 10-20 09:00 UTC). The shared
enumeration gives ordinal 2, and the round trip reproduces the same opening, closing (both
`CANONICAL_ANCHOR`) and an identical 12-transition listing. One helper, one rule.

**Closing.** Let *W* be the opening's window and *S* the next canonical `Located` sunrise after
the opening, if any.

* *S* exists and is the same event as `W.next` → the closing is *S*'s own canonical
  `previous_*` (`located_by = CANONICAL_ANCHOR`), and `closing_window` is *S*'s window. Below the
  sampled ~65° the two floats were identical in every sample; above it they differed by up to
  ~7 ms in the sample of §12, and only the canonical one is what the next civil date's request
  reports as *its* opening.
* otherwise (*S* absent, or *S* later than `W.next` by more than the separation: a gap) → the
  closing is `W.next_*` (`located_by = WINDOW_NEXT`), `closing_window = None`, and the day is
  still a complete interval by Layer 16's own bracketing. No later day exists to disagree with
  it. This is the last complete day before a polar day (probe D3: 66.57 N, 2024-06-18, closing
  06-19 01:26 EEST as `WINDOW_NEXT`; the next canonical sunrise is 06-23).

The v0.1 condition "every anchor after the opening reports `REASON_NO_NEXT_SUNRISE`" is
withdrawn (reasons change along the stretch, §4.2), and so is v0.1's guard that every adjacent
pair of located sunrises be the earlier window's `next` (a gap is not an error).

### 4.4 Interval datetimes

`opening.utc = W.previous_utc`; `closing.utc = closing_window.previous_utc` or `W.next_utc`;
Julian Days and local datetimes are copied from the same windows. §7.2's check guarantees each
datetime names its float.

### 4.5 Elements at the opening sunrise

`transitions_at_opening = find_transitions(opening.utc, kinds=ALL_KINDS, tolerance=…,
evaluate=…)`. Its `neighbours[kind].current` is the element of each kind at the opening
instant — Layer 17 classifies the caller's exact instant off-grid with Layer 16's classifiers
on Layer 6's longitudes, which is what `calculate_panchanga` classifies at the same datetime
(Layer 17 D7). The two sidereal longitudes are obtained once more through the same `evaluate`
for the record, and the four elements are re-derived from them with Layer 16's
`tithi_from_elongation`, `karana_from_elongation`, `nakshatra_from_longitude`, `yoga_from_sum`.
Whole-record equality with the four `current` elements is the internal-consistency check
(`DaySearchError`): same instant, same longitudes, same classifiers, so the records must be
equal, field for field — this is the one place whole-record equality is appropriate. The vara is
`vara_from_sunrise(W)`. The same is done at `closing.utc` for `at_closing` and
`transitions_at_closing` (accepted closing-side information; one extra Layer 17 query).

### 4.6 The interval's transitions and their placement

`listing = list_transitions(opening.utc, closing.utc, kinds=ALL_KINDS, tolerance=…,
evaluate=…)`, carried whole. Each listed transition *T* receives a `DayPlacement`, decided from
the cell datetimes and the **index** of the opening element of its kind, `k_open`:

| condition | placement | what may be claimed |
|---|---|---|
| `T.before_utc >= opening.utc` | `WITHIN` | the change lies in `(before_utc, after_utc]`, with `after_utc < closing.utc` by membership |
| `T.before_utc < opening.utc <= T.after_utc` and `T.after.index == k_open` | `STRADDLES_OPENING_REFLECTED` | the change lies in `(before_utc, opening.utc]`; the day **opened** in `T.after`; listing it here is Layer 17's representative rule, not a claim that it happened after sunrise — nothing is applied twice |
| `T.before_utc < opening.utc < T.after_utc` and `T.before.index == k_open` | `STRADDLES_OPENING_AFTER` | the change lies in `(opening.utc, after_utc]`, after the opening instant and within one cell of it |

Any other combination is a `DaySearchError`. By Layer 17's contract the reflected case is
exactly `same_event(T, transitions_at_opening.neighbours[kind].previous)` and the after case
exactly `same_event(T, …neighbours[kind].next)`; the implementation decides by the cell and the
index and checks the identity. Transition identity is always `same_event`; element identity in
placement is always the index (v0.1 compared whole records and would have found no match, §3.3).

**Cells at the closing sunrise.** For each kind, `transitions_at_closing.neighbours[kind].previous`
— the transition into the element current at `closing.utc` — is reported in
`cells_at_closing` when its cell **spans or ends at** the closing datetime:
`before_utc < closing.utc <= after_utc`. Such a transition is never a member of this day's
listing (`after_utc >= closing.utc`). **When an adjacent complete day exists** — the closing is
`CANONICAL_ANCHOR`, so the next day opens at the same datetime — Layer 17 lists it in that day,
where it is `STRADDLES_OPENING_REFLECTED`; when the closing is `WINDOW_NEXT` the day leads into
unavailability, no day lists it, and `cells_at_closing` is the only place it is reported. What
may be claimed about it: the element of that kind at the
closing instant is already `after`, so the change lies in `(before_utc, closing.utc]` in
datetime terms. **Nothing more**: the closing instant is excluded from `[opening, closing)`, a
change exactly at `closing.utc` belongs to the next day, and a change a microsecond before
`closing.utc` maps to the closing float and is outside this day by Layer 16's membership (probe
E, "1 µs before closing": JD membership False). The two cases are indistinguishable inside one
cell, and the result says so through the placement name `AT_OR_BEFORE_CLOSING` rather than
"inside this day". v0.1's `before_utc < closing.utc < after_utc` missed the cell that ends
exactly at the closing datetime — possible whenever the closing datetime lies on the tolerance
grid — which an adjacent day lists as reflected; probe E reproduces it with a grid-aligned
synthetic sunrise (cell 01:03:58.400–.500, `after_utc == closing.utc`, listed by the next day,
missed by the v0.1 rule, caught by `<=`).

The mirror fact at the opening, from probe F3: when the opening datetime lies on the tolerance
grid, a change 1 µs after it falls in the cell `(opening.utc, opening.utc + tolerance]`, whose
`before_utc == opening.utc`, and the rule above places it `WITHIN` — correctly, since the cell
starts at the opening. `STRADDLES_OPENING_AFTER` arises only when the opening lies strictly
inside a cell (the ordinary case: Jalandhar's opening 01:05:11.853857 in the cell
01:05:11.800–.900); v0.2's test expectation for the grid-aligned case was wrong and is
corrected in §11.

Ordering is Layer 17's (`after_utc`, then canonical kind order); Layer 18 adds no sort.

### 4.7 Supported inputs — derived separately for the two forms

Inputs and evaluations are separated as in Layer 17 §4.6. Layer 16 evaluates from
`SEARCH_SPAN_DAYS = 2 d` before an anchor (the library scans a further two hours back) to
about `2.5 d` after it (phase B), and the library's own forward scan from a probe covers about
one day at low latitude and 28 hours at high latitude; Layer 17 needs both interval endpoints
inside `[SUPPORTED_START, SUPPORTED_END]` = `[1800-01-05, 2399-12-28]` and evaluates within
`[SAFE_EVAL_START, SAFE_EVAL_END]` = `[1800-01-02, 2399-12-31]`.

*Date form*, walk `[D0 − 48 h, D0 + 108 h]`: earliest evaluation ≈ `D0 − 4 d 2 h`, latest ≈
`D0 + 4.5 d + 2.5 d + 1.2 d ≈ D0 + 8.2 d`; the opening lies in `[D0 − 16 h, D0 + 40 h)` and the
closing before `D0 + 88 h`. Proposed `SUPPORTED_DATE_START = 1800-01-07`,
`SUPPORTED_DATE_END = 2399-12-21`.

*Containing form*, walk `[t − 72 h, t + 60 h]` followed by the date walk for the opening's
civil date *D* (§4.3): the opening lies in `[t − 2 d, t]` and the closing in `(t, t + 2 d]`; the
opening's local date lies within `(t − 2 d − 16 h, t + 16 h)`, so `D0` lies in
`(t − 2 d − 16 h − 24 h, t + 16 h]`. Earliest evaluation is the date walk's, ≈ `D0 − 4 d 2 h` ≥
`(t − 2 d − 16 h − 24 h) − 4 d 2 h = t − 7 d 18 h` (v0.3 wrote 6 d 18 h; corrected at the
owner's review); latest is also the date walk's, ≈ `D0 + 8.2 d` ≤ `t + 8 d 21 h` (the
containing walk's own reach, `t − 5 d 2 h` to `t + 6.2 d`, lies inside these). The range is
chosen so that *D* is always inside the date range, which makes the date-form round trip of
§10 total. Proposed `SUPPORTED_INSTANT_START = 1800-01-10T00:00Z`, at which the earliest
evaluation reaches 1800-01-02 06:00 UTC — six hours inside `SAFE_EVAL_START` and the tighter
of the two start bounds; `SUPPORTED_INSTANT_END = 2399-12-21T00:00Z`, at which the latest
evaluation is ≈ 2399-12-29 21:00, the tighter of the two end bounds. Both are confirmed, or
moved inward, by the fresh-interpreter edge probe (D8, provisional; result in §17).

Outside either range → `UnsupportedDateError` / `UnsupportedInstantError` before any
evaluation. Probe C showed 1800-01-05 failing inside the engine (the cold-start edge Layer 17
§2.2 records), 1800-01-06 succeeding, 2399-12-26 succeeding and 2399-12-28 failing typed in the
listing. The final constants are fixed at implementation by probing every date (instant) in
`[proposed − 4, proposed + 4]` at both ends, at longitudes −180, 0 and +180 and latitudes 0 and
±66, **each probe in a fresh interpreter** (the edge failures are state-dependent), confirming
typed behaviour on both sides; the constants may only move inward.

### 4.8 Cost

Layer 16 allows `MAX_PROBES = 9` probes **per phase**, two phases, so at most 18 sunrise calls
per window (v0.1 said nine per window; withdrawn). The date walk makes 14 window calls (at most
252 sunrise calls). The containing form makes 12 window calls for its own walk, one Layer 16
call at the instant, and — for a complete day — the 14 calls of the date walk for the opening's
civil date (§4.3): at most 27 window calls, 486 sunrise calls. Each complete day then costs two
`find_transitions` (opening and closing) and one `list_transitions`. Measured for the date form
with the closing-side query included (probe D6): 27 ms per day at Jalandhar, 47 ms at Tromsø;
the containing form adds roughly the cost of one more walk. The v0.1 prototype figures omitted
the closing query.

### 4.9 Constants

`ANCHOR_EPOCH`, `ANCHOR_STEP`, `WALK_BEFORE`, `WALK_AFTER`, `CONTAINING_WALK_BEFORE = 72 h`,
`CONTAINING_WALK_AFTER = 60 h`, `SAME_SUNRISE_MAX_SEPARATION`, `SUPPORTED_DATE_START/END`,
`SUPPORTED_INSTANT_START/END`, `DEFAULT_TOLERANCE` (re-exported from Layer 17, 100 ms),
`MAX_OFFSET_HOURS = 16` (the coverage assumption of §4.10, tested against the installed tz
database rather than believed).

### 4.10 Coverage of the walks

Every IANA offset in the installed database lies within ±16 h (extremes found:
`America/Metlakatla` LMT +15:13:42, `Asia/Manila` LMT −15:56:00), so every sunrise with civil
date *D* lies in `[D0 − 16 h, D0 + 40 h)`, its window's first anchor is preceded by at least
two walked anchors, and its successor (at most 2 days later, Layer 16
`MAX_CONSECUTIVE_GAP_DAYS`) has its first anchor before `D0 + 100 h`. For the containing form
the opening is at most 2 days before *t* (its first anchor is preceded by at least one walked
anchor from `t − 72 h`) and the closing's first anchor is before `t + 2 d + 12 h`. Both walks
are fixed ranges rather than early-stopping loops so that cost is bounded and no monotonicity of
civil dates along the walk is assumed.

## 5. Result types (all frozen dataclasses; mappings as `MappingProxyType`)

```
SunriseLocating(Enum): CANONICAL_ANCHOR, WINDOW_NEXT, FIRST_ANCHOR
DaySunrise(utc, julian_day_ut, local, timezone_id, located_by: SunriseLocating)
DayPlacement(Enum): WITHIN, STRADDLES_OPENING_REFLECTED, STRADDLES_OPENING_AFTER,
                    AT_OR_BEFORE_CLOSING          # cells_at_closing only, never in `placed`
PlacedTransition(transition: Transition, placement: DayPlacement)
InstantElements(tithi, karana, nakshatra, yoga,
                sun_sidereal_longitude, moon_sidereal_longitude)

PanchangaDay:
    civil_date: date                       # as requested, or opening.local.date() (containing form)
    sunrise_ordinal: int                   # 1 unless the date carries several sunrises
    location: PanchangaLocation            # Layer 16's, provenance EXPLICIT
    timezone_id: str
    opening: DaySunrise                    # located_by CANONICAL_ANCHOR always
    closing: DaySunrise                    # CANONICAL_ANCHOR or WINDOW_NEXT
    opening_window: SunriseWindow          # Layer 16 objects, unchanged
    closing_window: SunriseWindow | None   # None iff closing.located_by is WINDOW_NEXT
    vara: Vara                             # vara_from_sunrise(opening_window)
    at_opening: InstantElements
    at_closing: InstantElements
    transitions_at_opening: PanchangaTransitions   # Layer 17 neighbours at opening.utc
    transitions_at_closing: PanchangaTransitions   # Layer 17 neighbours at closing.utc
    listing: TransitionList                # Layer 17; start == opening.utc, end == closing.utc
    placed: tuple[PlacedTransition, ...]   # same order and length as listing.transitions
    cells_at_closing: Mapping[TransitionKind, PlacedTransition]   # placement AT_OR_BEFORE_CLOSING
    layer16_at_instant: SunriseWindow | SunriseUnavailable | None  # containing form only
    query_utc: datetime | None             # containing form only, normalised
    tolerance: timedelta
    calculation_convention, sunrise_convention, search_convention: str

    __post_init__ (ValueError): opening.jd < closing.jd; vara.sunrise is opening_window;
    listing.start_utc == opening.utc and listing.end_utc == closing.utc; len(placed) ==
    len(listing.transitions) and placed[i].transition is listing.transitions[i]; no placed
    entry is AT_OR_BEFORE_CLOSING and every cells_at_closing entry is; each cells_at_closing
    cell satisfies before_utc < closing.utc <= after_utc; at_opening's four records equal
    transitions_at_opening's currents and likewise at closing; closing_window is None iff
    closing.located_by is WINDOW_NEXT; query_utc is None iff layer16_at_instant is None;
    when query_utc is set, opening.jd <= jd(query_utc) < closing.jd.
```

Nothing is rounded; every Layer 16 and Layer 17 object is carried by identity.

## 6. Unavailability, ambiguity, partial information (results, not exceptions — Layer 16 D3)

```
DayUnavailableReason(Enum):
    NO_SUNRISE_WITH_DATE      # date form: every anchor gave a window, none carries D (zone skips D)
    SUNRISE_UNAVAILABLE       # date form: no sunrise carries D and the walk met unavailability;
                              # containing form: no canonical day contains the instant
    NO_VARA_DAY_AT_SUNRISE    # date form: only a next-only sunrise carries D

PanchangaDayUnavailable(civil_date | None, query_utc | None, location, timezone_id, reason,
                        layer16_reasons: tuple[str, ...],          # distinct, in walk order
                        layer16_at_instant: ... | None,            # containing form only
                        preceding_sunrise: DaySunrise | None,      # last sunrise located WITHIN THE WALK
                                                                   # before the date's span / the instant
                                                                   # (any locating, FIRST_ANCHOR included)
                        following_sunrise: DaySunrise | None,      # first canonical sunrise located
                                                                   # WITHIN THE WALK after it
                        lone_sunrise: DaySunrise | None,           # NO_VARA_DAY_AT_SUNRISE only
                        at_lone_sunrise: InstantElements | None,
                        sunrise_convention)

PanchangaDayAmbiguous(civil_date, location, timezone_id,
                      candidates: tuple[DaySunrise, ...],          # time order; ordinal = index + 1
                      sunrise_convention)
```

Rules: a date with no qualifying sunrise never becomes another date — `preceding_sunrise` and
`following_sunrise` are information about neighbours, each carrying its own civil date and its
own `located_by`, never a substitute. No 06:00, noon, midnight or civil-weekday fallback exists
anywhere. `NO_VARA_DAY_AT_SUNRISE` is the only case where partial information is
astronomically defined without a day: the next-only sunrise's instant (`located_by =
WINDOW_NEXT`) and the four angular elements at it; it has no vara, because Layer 16 gives none
to any instant after that sunrise, and Layer 18 does not contradict Layer 16. In the containing
form an instant after a next-only sunrise, or inside an unavailable stretch, is
`SUNRISE_UNAVAILABLE` with the next-only sunrise as `preceding_sunrise` (when its window was
walked) and, as `following_sunrise`, the first canonical sunrise after the stretch **if the
walk reached it**.

**Neighbour information is bounded by the walk.** `preceding_sunrise` and `following_sunrise`
are what the walk of §4.3 found and nothing more; `None` means "not found within the search
range", never "no such sunrise exists". The search is not widened. Probe F2: 66.57 N 25 E
`Europe/Helsinki`, query 2024-06-19 06:00 local (03:00 UTC): the containing walk covers
`[06-16 03:00, 06-21 15:00]` UTC (last anchor 06-21 12:00), locates the 06-17 and 06-18
windows, finds no day containing the query (the 06-18 day closes `WINDOW_NEXT` at 06-19 01:26)
and returns `following_sunrise = None`, although the resumed sunrise exists on 06-23 01:27:51
local; the date form for 06-19, whose walk reaches 06-23 12:00 UTC, reports it. A caller who
needs the next sunrise after a gap asks for a later date or instant.

`PanchangaDayAmbiguous` is real: `America/Anchorage` 1867-10-19 carries two sunrises (probe C).
A near-polar spring in a zone whose clock is close to solar time could produce the same (a
sunrise minutes after local midnight followed by one minutes before the next); no real
instance was found in the scan of §12 and the case is also tested synthetically.

## 7. Boundary rules

### 7.1 Julian Day membership versus datetime membership

The two predicates of §2 agree everywhere except within the ~40 µs of datetimes that share a
sunrise's float. Probe D4 at Jalandhar 1995-03-21 (opening 01:05:11.853857 UTC, closing 03-22
01:03:56.321939 UTC):

| instant | Layer 16 JD membership in the day | Layer 17 datetime membership of a representative there |
|---|---|---|
| `opening.utc − 1 µs` | **in** (same float as the opening) | **out** (`< start`) |
| `opening.utc` | in | in |
| `closing.utc − 1 µs` | **out** (same float as the closing) | **in** (`< end`) |
| `closing.utc` | out | out |

Layer 18 keeps both predicates as they are, states which one each field uses — every `jd`
comparison is Layer 16's, every listing membership is Layer 17's — and tests the four rows at
both endpoints of the reference days. No epsilon is added and no lower-layer value is adjusted:
the two rules disagree on at most ~40 µs a day, and a result that hid that would be less
honest than one that reports it.

### 7.2 The image check

Layer 18 requires `julian_day_ut(sunrise.utc) == sunrise.julian_day_ut` for every `DaySunrise`
it reports and raises `DaySearchError` otherwise. §3.1 shows this cannot fail in the supported
range; the check exists so that if a future interpreter or a changed `datetime_from_julian_day`
ever broke the property, the failure would be visible rather than a day that begins one float
before its own sunrise. No microsecond is ever added or removed to make the equality hold.

### 7.3 Membership near a sunrise at high latitude

Layer 18's membership is on the canonical floats. Layer 16's `calculate_panchanga(t)` runs its
own search from *t* and locates the same sunrise at a float that depends on *t*'s probe
positions: up to ~14 ms away at the sampled latitudes above ~65° from every instant, and up to
~141 ms away at any sampled latitude from an instant in the last minutes of a day longer than
24 hours (§3.2). The two layers can therefore disagree about which day an instant within that
distance of a sunrise belongs to, and `calculate_panchanga(opening.utc)` itself named the
previous vara at Tromsø on 26 of 60 sampled dates (16 of 40 in the committed test's window).
Layer 18 does not correct Layer 16 and does not hide this: the containing form carries
`layer16_at_instant`, the test plan measures the disagreement (§11, §17), and §15 records it.
From the ordinary instants of a day at the sampled lower latitudes the two agreed bit for bit.

### 7.4 Transitions at a sunrise

Layer 17's cells are absolute-grid cells; a sunrise falls inside a transition's cell with
probability about `cell width / 1 day` per kind per day — 100 ms / 86,400 s ≈ 1.16 × 10⁻⁶ per
kind, about 4.6 × 10⁻⁶ per day for the four kinds together. None occurred in the 480 kind-days
probed (expected ≈ 0.00056); the placements of §4.6 are therefore exercised with synthetic
`evaluate` functions (probes D2, E and F3: the tithi index steps exactly at, 1 µs before and
1 µs after each sunrise) and with a synthetic `rise_after` that puts a sunrise on the
tolerance grid so that a cell ends or starts exactly at it.

## 8. What a `PanchangaDay` claims

* `opening`/`closing` are Layer 16's floats for the geometric Hindu sunrise, by the convention
  string carried; their datetimes are the exact microsecond images of those floats (§3.1).
* `vara` is the weekday of `civil_date`; `at_opening` is the classification at `opening.utc`.
* `listing.transitions` are the Layer 17 transitions whose representatives lie in
  `[opening.utc, closing.utc)`, with Layer 17's uncertainty record on each. `placed` states a
  relation between the transition's **datetime cell** and the two sunrise datetimes, nothing
  else: `WITHIN` means `opening.utc <= before_utc` and `after_utc < closing.utc`, so the change
  lies in a cell that starts at or after the opening datetime and ends before the closing
  datetime; `STRADDLES_OPENING_REFLECTED` and `STRADDLES_OPENING_AFTER` mean the cell contains
  the opening datetime and say on which side of it the change lies. Whether an instant inside
  such a cell belongs to the day under Layer 16's Julian Day membership is a different
  predicate (§7.1) and is not what `placed` asserts. `cells_at_closing` are changes at or before
  the closing datetime, listed by the adjacent day when one exists; nothing claims that every
  listed change happened inside the day, nor that a change at or before the closing instant did.
* Consecutive days for consecutive sunrises share `closing`/`opening` bit for bit whenever the
  closing is `CANONICAL_ANCHOR`, so their listings partition Layer 17's listing of the union
  interval exactly (tested, §11).
* `preceding_sunrise` and `following_sunrise` on an unavailable result are bounded by the walk
  (§6); `None` is "not found within the search", not "does not exist".

## 9. Errors and where they are raised

Before any evaluation (pre-evaluation validation, in this order):

| condition | error |
|---|---|
| `civil_date` not a `datetime.date`, or a `datetime` (a subclass of `date`; rejected explicitly) | `DayRequestError` (`ValueError`) |
| `sunrise_ordinal` not `None` or a positive `int` (`bool` rejected) | `DayRequestError` |
| `civil_date` outside `[SUPPORTED_DATE_START, SUPPORTED_DATE_END]` | `UnsupportedDateError` (`ValueError`) |
| `moment_utc` naive | `ValueError` from Layer 4 (through `utc_instant`) |
| `moment_utc` outside `[SUPPORTED_INSTANT_START, SUPPORTED_INSTANT_END]` | `UnsupportedInstantError` (Layer 17's class, re-raised with Layer 18's range in the message) |
| coordinates | `ValueError` from Layer 16 `validate_coordinates` |
| zone | `InvalidTimezoneError` from Layer 16 `resolve_zone` |
| `tolerance` not a `timedelta`, or not a member of Layer 17's public `ALLOWED_TOLERANCES` | `TransitionRequestError` (Layer 17's class), raised by Layer 18's own two-line restatement of the rule (D9(a), approved); a parity test asserts that Layer 18 and Layer 17 accept and reject exactly the same values — every allowed tolerance, and rejected: `0`, `1 µs`, `2 ms`, `−1 ms`, `1.5 h`, an `int`, a `float`, `None` |

After the walk (post-discovery):

| condition | error / result |
|---|---|
| `sunrise_ordinal` larger than the number of candidates, when that number is at least one | `DayRequestError` (the message carries the count and the candidates' instants) |
| any `sunrise_ordinal` with zero candidates | not an error: `PanchangaDayUnavailable`, identical to the ordinal-free result (§4.3) |
| walk guards, the image check, the consistency checks of §4.5–4.6 | `DaySearchError` (`RuntimeError`) |
| Layer 16 search failures, Layer 17 `TransitionSearchError` | propagated unchanged |

The ephemeris lifecycle is the caller's (`ephemeris_session`), as in Layers 16 and 17; Layer
18 opens and closes nothing. No `assert` anywhere in the module (verified under `python -O`).

## 10. Public surface (`vedic_chart.panchanga.daily`, re-exported by `vedic_chart.panchanga`)

```
panchanga_day(civil_date: date, latitude: float, longitude: float, timezone_id: str, *,
              sunrise_ordinal: int | None = None,
              tolerance: timedelta = DEFAULT_TOLERANCE,
              rise_after: RiseAfter = default_rise_after,
              evaluate: Evaluate = default_evaluate,
) -> PanchangaDay | PanchangaDayUnavailable | PanchangaDayAmbiguous

panchanga_day_containing(moment_utc: datetime, latitude, longitude, timezone_id, *,
              tolerance=..., rise_after=..., evaluate=...,
) -> PanchangaDay | PanchangaDayUnavailable
```

`sunrise_ordinal=None` requires the date to carry exactly one sunrise; `n` selects the *n*-th
candidate in time order when the date carries at least *n*, is a `DayRequestError` when it
carries fewer but at least one, and is ignored when it carries none (the unavailable result
is returned as for `None`). The containing form returns `civil_date = opening.local.date()` and
the ordinal of the opening among that date's canonical sunrises, so that
`panchanga_day(day.civil_date, …, sunrise_ordinal=day.sunrise_ordinal)` reproduces the same
`opening` and `closing` floats and the same listing (the date walk locates the same anchors,
§4.1; the instant range of §4.7 keeps `civil_date` inside the date range). `rise_after` and
`evaluate` are the injection points Layers 16 and 17 already define, passed straight through;
production callers leave them alone.

Re-exports added to `vedic_chart.panchanga.__init__` (sorted into `__all__`): `panchanga_day`,
`panchanga_day_containing`, `PanchangaDay`, `PanchangaDayUnavailable`, `PanchangaDayAmbiguous`,
`DaySunrise`, `InstantElements`, `PlacedTransition`, `SunriseLocating`, `DayPlacement`,
`DayUnavailableReason`, `DayRequestError`, `UnsupportedDateError`, `DaySearchError`,
`ANCHOR_EPOCH`, `ANCHOR_STEP`, `WALK_BEFORE`, `WALK_AFTER`, `CONTAINING_WALK_BEFORE`,
`CONTAINING_WALK_AFTER`, `SAME_SUNRISE_MAX_SEPARATION`, `SUPPORTED_DATE_START`,
`SUPPORTED_DATE_END`, `SUPPORTED_INSTANT_START`, `SUPPORTED_INSTANT_END`, `MAX_OFFSET_HOURS`
(26 names). Nothing existing is renamed or removed.

## 11. Validation plan (`tests/test_panchanga_daily.py`, plus the boundary-test amendments of §14)

*Reference days* (the project's coordinates, `tests/test_panchanga_compute.py`). Jalandhar
(31.32556 N, 75.57917 E, Asia/Kolkata) 1995-03-21: opening 06:35:11.853857 IST (01:05:11.853857
Z), closing 03-22 06:33:56.321939 IST — Layer 16 §9's 06:35:11 and 06:33:56. Jammu (32.73528 N,
74.86167 E) 2001-02-04: 07:27:37.981834 → 02-05 07:26:52.040783 IST — Layer 16 §9's 07:27:37
and 07:26:52. Vara (Mangalavara; Ravivara) and the four opening records equal
`calculate_panchanga(opening.utc)`'s (whole-record equality: same instant). The listings,
reproduced by probe B with these coordinates, are exactly (UTC cells, 100 ms): Jalandhar —
karana Kaulava→Taitila 03-21 02:58:29.9–30.0, yoga Harshana→Vajra 03:16:31.7–.8, nakshatra
Vishakha→Anuradha 08:08:56.6–.7, tithi Panchami→Shashthi 13:45:08.2–.3 with karana
Taitila→Garaja in the same cell, yoga Vajra→Siddhi 03-22 00:08:51.7–.8, karana Garaja→Vanija
00:33:20.0–.1 (seven); Jammu — nakshatra Rohini→Mrigashira 02-04 02:36:52.2–.3, yoga
Indra→Vaidhriti 05:32:43.0–.1, karana Vanija→Vishti 10:07:50.8–.9, tithi Ekadashi→Dwadashi
20:53:13.8–.9 with karana Vishti→Bava in the same cell, nakshatra Mrigashira→Ardra 02-05
00:53:02.8–.9 (six). The Layer 17 §12 reference cells before the opening (Jalandhar tithi
03-20 16:12:55, nakshatra 03-20 09:53:21, yoga 03-20 06:27:42; Jammu tithi 02-03 23:13:06,
yoga 02-03 08:16:47) are absent from the listings and present as
`transitions_at_opening.neighbours[kind].previous`. `placement == WITHIN` for every listed
transition; `cells_at_closing` empty; `unordered_pairs == ()`.

*Both membership predicates at both endpoints* (§7.1): the four rows of the table at each
reference day, plus the count of microsecond datetimes sharing each sunrise float (recorded,
not asserted beyond "at least 1 on each side").

*Parity with Layer 16.* For 40 consecutive days at each of Jalandhar, Ushuaia (−54.8°) and
Anchorage (61.2°): `calculate_panchanga(t)` at `opening.utc`, `opening.utc + 1 s`, mid-day and
`closing.utc − 1 s` reports the same vara and the same window floats as the day. At Tromsø the
same test asserts equality of vara and *event identity* of the floats at `± 1 s`, and records
(not asserts) the disagreement rate at `opening.utc` itself and the largest float difference
seen (§7.3), stated in the record as sampled values.

*Consecutive days and partitioning.* For runs of 12 consecutive dates at Jalandhar, Ushuaia,
Chatham (+12:45/+13:45), London across both DST changes and Tromsø in February: `closing` of
day *n* equals `opening` of day *n + 1* in all three spellings (`==` on the float, the datetime
and the local datetime); the concatenation of the 12 listings equals
`list_transitions(opening₁, closing₁₂)` element for element (Layer 17 `Transition` equality),
and no `event_id` appears twice or is missing. Every `cells_at_closing` entry of day *n* is
`same_event` with a `STRADDLES_OPENING_REFLECTED` entry of day *n + 1*, and vice versa —
including the cell that ends exactly at the boundary, which the synthetic grid-aligned sunrise
of probe E supplies.

*Actual changes at the closing boundary, separately from representative membership.* With the
synthetic longitudes of probe E and a grid-aligned synthetic sunrise: a change exactly at
`closing.utc`, 1 µs before and 1 µs after. Asserted: which day's listing carries the cell (next,
next, next), that `cells_at_closing` of this day carries it in the first two cases and not the
third, `placement == AT_OR_BEFORE_CLOSING`, `after_utc == closing.utc` in the first two, and the
JD membership of the change instant (out, out, out) — the row that shows why "at or before
closing" is not "inside this day". The same three cases against a `WINDOW_NEXT` closing
(synthetic sequence ending in `None`s): `cells_at_closing` carries the first two and no day
lists them.

*Placement at the opening, two openings.* (a) A grid-aligned synthetic opening (probe F3): a
change exactly at `opening.utc` and 1 µs before it fall in the cell ending at the opening and
are `STRADDLES_OPENING_REFLECTED`, listed by this day; a change 1 µs after it falls in the cell
`(opening.utc, opening.utc + tolerance]` and is **`WITHIN`** (its `before_utc == opening.utc`).
(b) The real Jalandhar opening, strictly inside the cell 01:05:11.800–.900: exactly at and 1 µs
before → `STRADDLES_OPENING_REFLECTED`; 1 µs after → `STRADDLES_OPENING_AFTER`. v0.2 expected
`STRADDLES_OPENING_AFTER` in case (a); that contradicted §4.6 and is corrected.

*Placement by index.* With a synthetic evaluate whose records differ in longitude but not in
index across the opening (the natural case), the reflected/after decision is by index; a test
that pins whole-record inequality between `current` and `T.before`/`T.after` at a real cell
(probe D1) documents why.

*Synthetic sunrises and transitions.* With injected `rise_after` (exact Julian Days, as Layer
16's tests do) and injected `evaluate` (Layer 17's synthetic longitude functions): a kind that
changes three times in one day (karana, naturally; nakshatra synthetically); tithi and karana
changing in the same cell (ordered, never an unordered pair) and a synthetic nakshatra/yoga
same-cell pair (`unordered_pairs` carried through unchanged); a date carrying two synthetic
sunrises (ordinal selection, ambiguity result, containing-form round trip); a synthetic
sequence whose second locating of one sunrise differs by 10 ms (the high-latitude behaviour,
made deterministic) proving the canonical rule and the same-event identity; a sequence that
returns a sunrise out of order (guard raises); a sequence with a gap (last window's next
followed by `None`s, then a resumed sunrise) proving the gap is not an error.

*Containing-form ordinal regression (finding 1 of v0.2).* The synthetic sequence of §4.3 —
UTC 1867-10-18 10:00 + *n* × 47 h through the unchanged `julian_day_ut`, `America/Anchorage`,
Layer 16 unchanged with the injected `rise_after` — labelled in the test as synthetic coverage
of the allowed-gap contract, not an observed sequence. Asserted: the date form for 1867-10-19
returns `PanchangaDayAmbiguous` with two candidates; `panchanga_day_containing(1867-10-22
07:00 UTC)` returns `civil_date == 1867-10-19` and `sunrise_ordinal == 2`; the date form with
ordinal 2 reproduces the same `opening` and `closing` floats and datetimes and an identical
listing; and the date form with ordinal 1 is a different day (opening 10-18) — the day the
withdrawn counting rule would have named.

*Explicit ordinals on unavailable dates (v1.0).* `Pacific/Apia` 2011-12-30 with
`sunrise_ordinal` 1 and 2, and Tromsø 2024-06-21 (`SUNRISE_UNAVAILABLE`), 2024-05-21
(`NO_VARA_DAY_AT_SUNRISE`) and 2025-11-27 with `sunrise_ordinal=1`: each returns the same
`PanchangaDayUnavailable` as the ordinal-free request (`==`), never `DayRequestError`; the
nonzero out-of-range case (two candidates, ordinal 3 → `DayRequestError`) is retained.

*Civil-date cases (real tz data).* `Pacific/Apia` 2011-12-29/30/31 and `Pacific/Kiritimati`
1994-12-30/31/1995-01-01 (skipped date → `NO_SUNRISE_WITH_DATE`, neighbours reported, the day of
12-29 closing on 12-31 with `closing.local.date()` two days later); `America/Anchorage`
1867-10-18/19/20 (ambiguity on the 19th, both ordinals, each a complete day, the second one's
closing = the 20th's opening); `America/Sao_Paulo` 2018-11-03/04/05 and 2019-02-16/17 (DST at
midnight, both directions); `Europe/London` 2024-03-30/31 and 10-26/27; `Pacific/Chatham`
2024-04-06/07 and 09-28/29; a request with a `datetime` instead of a `date` (rejected);
`MAX_OFFSET_HOURS` checked against the installed tz database for the zones used.

*Polar, through both entry points.* Tromsø: 2025-11-26…29 (`SUNRISE_UNAVAILABLE`, Layer 16
reasons carried in sequence), 2026-01-16 (unavailable, `following_sunrise` = 01-19 11:35 CET),
2026-01-19 (first day of the year: opening 11:35:35 CET, closing 01-20 11:15:37 CET, 23.667 h),
2024-05-18/19 (days of 23.8 h), 2024-05-20 (the final complete day, `closing.located_by ==
WINDOW_NEXT`, `closing_window is None`), 2024-05-21 (`NO_VARA_DAY_AT_SUNRISE` with
`lone_sunrise` and `at_lone_sunrise`, no vara), 2024-06-21 (`SUNRISE_UNAVAILABLE`),
2024-07-22/23/24 (first days after, 24.27 h and 24.20 h). 66.57 N 25 E Europe/Helsinki, date
form: 2024-06-17 (complete, canonical closing), 06-18 (final complete day, `WINDOW_NEXT`), 06-19
(lone sunrise; `following_sunrise` = 06-23 01:27:51 local, which that walk reaches), 06-20…22
(gap; each date's walk `[D0 − 48 h, D0 + 108 h]` reaches the 06-23 sunrise — its first anchor
is 06-23 00:00 UTC — so `following_sunrise` = 06-23 for all three, and `preceding_sunrise` =
the lone 06-19 01:26 sunrise as `WINDOW_NEXT` for 06-20, whose walk starts 06-18 00:00 UTC
inside the 06-18 window (seen as `FIRST_ANCHOR`), and `None` for 06-21 and 06-22, whose walks
start after that window ended at 06-18 22:26 UTC; each asserted from the written-out range,
not assumed), 06-23
(first resumed day). Containing form: mid-day of 06-18 (that day), 06-19 06:00 local = 03:00
UTC (unavailable; `preceding_sunrise` = the lone 06-19 01:26 sunrise as `WINDOW_NEXT`;
**`following_sunrise is None`**, the resumed sunrise lying outside the walk `[06-16 03:00,
06-21 15:00]` UTC, probe F2), 06-21 12:00 UTC (unavailable; walk `[06-18 12:00, 06-24 00:00]`
UTC: the 06-18 window is seen at the first anchor as `FIRST_ANCHOR`, so `preceding_sunrise` is
its next, the lone 06-19 sunrise, and `following_sunrise` = 06-23, found at anchor 06-23
00:00 UTC), 06-23 12:00 UTC (the resumed day), and Tromsø 2024-05-22 12:00 UTC (unavailable —
probe D3's case). Each expectation for `preceding_sunrise`/`following_sunrise` is stated as
"found within the walk `[…]`" with the range written out, and `None` is asserted where the
neighbour lies outside it. Every polar result carries the exact Layer 16 reason strings and no
invented weekday.

*Containing-form round trip.* For every complete day found through the containing form,
`panchanga_day(day.civil_date, …, sunrise_ordinal=day.sunrise_ordinal)` reproduces the
`opening`/`closing` floats and datetimes and the listing exactly. For every complete day found
through the date form **whose `opening.utc` and `opening.utc + 1 h` lie inside
`[SUPPORTED_INSTANT_START, SUPPORTED_INSTANT_END]`** — the containing form's narrower range —
`panchanga_day_containing(opening.utc + 1 h, …)` reproduces it, and
`panchanga_day_containing(opening.utc, …)` too (the opening instant belongs to its own day by
JD membership); date-form days near the date range's edges are excluded from this test, and a
containing-form query just outside the instant range is asserted to raise
`UnsupportedInstantError` before any evaluation.

*Ranges and guards.* Both proposed edges of both ranges and their neighbours (§4.7, fresh
interpreter per probe at implementation; the committed tests assert the typed refusals just
outside and the successes just inside); `python -O` run of the module's tests; every walk guard
and consistency check raised with synthetic inputs; pre-evaluation validation shown to make no
ephemeris call (a `rise_after`/`evaluate` that raises if called).

*Whole suite.* Reported per environment with exact counts, environment-dependent golden
failures listed separately (currently 12 in the cloud sandbox, 0 on the session VM), and the
native-macOS targeted run recorded as such — never called a full native run.

*External comparison (approved; to be executed at implementation and recorded honestly).*
(a) IMD Rashtriya Panchang daily pages (`packolkata.imd.gov.in`, public, read-only, through
the browser pane) for the two reference dates: tithi, nakshatra and yoga at sunrise and their
ending times, printed to the minute. IMD's sunrise is the refracted upper-limb rising, about
3.5–4 minutes earlier than Layer 16's geometric rising, so agreement on "the element at
sunrise" can be claimed only when no transition falls in that gap, and ending times can agree
only to the minute; a page that cannot be retrieved, or whose ayanamsha/convention is not
stated, is recorded as *not compared*, never as agreement. (b) The NASA GSFC phase table
(already used by Layer 17) applies only to phase instants: it can check the tithi 30→1 and
15→16 transitions in the listings of the days containing the new and full moons nearest the
reference dates, at minute resolution, and **cannot validate the complete Panchanga of either
ordinary reference birth date**; the record will say which days it was used for. No other
almanac is used unless its sunrise convention and ayanamsha are stated.

## 12. Probes run for this draft (scratch, not production; `Claude outputs/l18_probe_{a,b,c,d,e,f,g}.py`)

Cloud sandbox, Linux x86_64, Python 3.11.15, pyswisseph 2.10.03, repository files at `d90ebb0`
(hashes matched against the Mac copy). All figures are sample results at the places and dates
named; none is a bound.

**A — reproducibility and round trip** (six places, every 7th day over three years, 891
windows; then six places every 3rd day of 2024 with five re-asks per window):
`julian_day_ut(previous_utc) == previous_julian_day_ut` in 891/891. Re-asking Layer 16 for the
same sunrise from other instants of the same day: identical float in all 610 pairs at each of
Reykjavik (64.1°), Anchorage (61.2°) and Ushuaia (−54.8°), and in every pair at Jalandhar, Jammu
and Apia; different in 610/610 at 65.5° (largest 13.438 ms), 608/610 at 66.5° (13.559 ms),
404/405 at Tromsø (10.259 ms). `calculate_panchanga(previous_utc)` at Tromsø, 60 dates Feb–Mar
2024: same event with an earlier float 34 times, previous day's window (vara one day early)
26 times.

**B — canonical walk, parity, partition** (prototype of §4.1–4.3 with a 48 h/96 h range and
no closing-side query): `closing(D−1) == opening(D)` exact in 117/117 consecutive pairs at
Jalandhar, Tromsø, Ushuaia; `opening_window.next` equal to the canonical closing in 80/80 at
the two lower-latitude places and different in 40/40 at Tromsø (−6.84 … +7.00 ms). Four-element
parity of `find_transitions(opening_utc).current` with `calculate_panchanga(opening_utc)` in
120/120 (whole records, same instant). Union of 12 daily listings equal to the single listing
of the run at Jalandhar (56 transitions) and Ushuaia (58); Tromsø in June correctly yields no
day. No cell straddled a sunrise in 480 kind-days (expected ≈ 0.0006).

**C — civil dates, polar, ranges, timing:** the cases of §11 behaved as listed there (Anchorage
1867-10-19 two sunrises; Apia and Kiritimati skipped dates; São Paulo, Chatham and London DST
days of 23.96–24.03 h; Tromsø sequences; 1800-01-05 engine failure, 1800-01-06 success,
2399-12-26 success, 2399-12-28 typed listing failure). Cost per complete day without the
closing-side query: 27 ms (Jalandhar), 24 ms (Ushuaia), 47 ms (Tromsø).

**D — the v0.1 review findings** (`l18_probe_d.py`): D1 record inequality with equal index
inside the Jalandhar tithi cell (fields differing: `elongation`, `degrees_in_tithi`,
`angular_fraction`); D4 the four membership rows of §7.1 and 19/20 microsecond datetimes
sharing each sunrise float; D3 the Tromsø 2024-05-22 12:00 UTC containing query (entries:
window 05-18→05-19, window 05-19 23:22:57→05-20 23:06:14, then `NO_NEXT` × 4, `NO_PREVIOUS`
× 5; largest located sunrise at or before the query does not contain it; Layer 16 at the query:
unavailable) and the 66.57 N walk entries (06-18 window, next-only 06-19 01:26, unavailable
stretch, canonical 06-23); D5 the conversion bound of §3.1 (max 1.4534 µs in 200,000 floats, 0
round-trip mismatches, ULP figures); D6 the cost figures of §4.8 with the closing-side query.

**E — the cell that ends at the closing sunrise** (`l18_probe_e.py`): a synthetic `rise_after`
with sunrises whose float images lie exactly on the 100 ms grid (found by scanning 22 grid
points from 01:03:56.300) and synthetic longitudes stepping the tithi index at, 1 µs before and
1 µs after the closing: the cell 01:03:58.400–.500 has `after_utc == closing.utc`, is listed by
the next day and not this one, is `previous_transition(closing)` in the first two cases, is
missed by v0.1's `<` rule and caught by `<=`; the JD membership of the change instant in this
day is False in all three cases. Also observed: `datetime_from_julian_day(julian_day_ut(dt))`
shifted a microsecond datetime by 12 µs (the direction Layer 18 never uses).

**F — the v0.2 review findings** (`l18_probe_f.py`): F1 the synthetic 47-hour sequence in
`America/Anchorage` (§4.3): date form for 1867-10-19 → two canonical candidates (10-18
09:59 UTC → local 10-19 00:00 LMT +14:00:24; 10-20 09:00 UTC → local 10-19 23:00 LMT
−09:59:36); containing walk from anchor 1867-10-19 12:00 UTC sees the first as
`canonical=False`; query 10-22 07:00 UTC → opening 10-20 09:00 UTC; ordinal by counting inside
the containing walk 1, by the shared enumeration 2; date form with ordinal 1 gives a different
day, with ordinal 2 the identical opening and closing and an identical 12-transition listing.
(The 09:59 spelling of the 10:00 sunrise is the datetime→float→datetime shift of §3.1, up to
~20 µs.) F2 66.57 N: containing walk `[06-16 03:00, 06-21 15:00]` UTC, last anchor 06-21
12:00; located 06-16 (`FIRST_ANCHOR`), 06-17, 06-18; last canonical opening 06-18 01:31 with
`WINDOW_NEXT` closing 06-19 01:26, query not contained; following canonical sunrise within the
walk: none; date form 06-19 finds 06-23 01:27:51 within `[06-17 00:00, 06-23 12:00]` UTC. F3
placements as recorded in §4.6 and §11 (grid-aligned opening 01:05:12.700: after → `WITHIN`,
at/before → reflected; real opening 01:05:11.853857: after → `STRADDLES_OPENING_AFTER`).

**G — the probe-position dependence** (`l18_probe_g.py`, run at implementation): per place and
date, the difference between the `previous` float Layer 16 returns when asked N minutes before
the closing and the canonical opening float: Ushuaia 2024-03-01 (day 24.0339 h) +140.9 ms for
N ≤ 4, 0 for N ≥ 5; Anchorage 2024-09-10 (24.0411 h) +88.3 ms for N ≤ 4; London 2024-09-10
(24.0264 h) +35.9 ms for N ≤ 3; Jalandhar 2024-08-10 (24.0105 h) +83.7 ms for N ≤ 1; zero at
every N for Ushuaia in September, Anchorage, Jalandhar and Reykjavik in March (days shorter
than 24 h). The direct library call from probes 0.5 h to 23 h before the Ushuaia opening moves
from +1.207 ms to −0.925 ms, passing through 0 at 12 h — the anchor position.

## 13. Decisions

* **D7 — Layer 16 documentation note: approved.** The paragraph to be added to Layer 16 §10
  (documentation-only, additive; the Layer 16 v1.0 conventions and code are untouched), with
  the manifest entry of §14: *"Reproducibility of a sunrise float. Asked from different instants
  of one day, the library returned bit-identical Julian Days for a sunrise at every sampled
  place below about 65° of latitude (Jalandhar, Jammu, Apia, Ushuaia −54.8°, Anchorage 61.2°,
  Reykjavik 64.1°; 2023–2024), and Julian Days differing by up to about 14 ms at the sampled
  places above it (65.5° N, 66.5° N and Tromsø 69.6° N; 2024), where its slow search method is
  used. …"* **Applied 2026-09-27** with the implementation, in the wording reproduced in
  §17.6 — revised from the v0.3 text after probe G showed that the lower-latitude
  reproducibility holds only from ordinary instants of a day (§3.2); the paragraph now states
  both observations, each as a measurement, and a one-line history note was added to the
  Layer 16 header. No Layer 16 convention, code, test or golden changed.
* **D8 — the range constants: accepted provisionally.** The derivation of §4.7, revised for
  the containing form's second walk, stands subject to the fresh-interpreter edge checks at
  implementation; the constants may only move inward.
* **D9 — tolerance validation: (a) approved.** Layer 18 restates the rule from the public
  `ALLOWED_TOLERANCES` (`isinstance(tolerance, timedelta) and tolerance in ALLOWED_TOLERANCES`,
  else `TransitionRequestError`), before any evaluation, with the parity test of §9. The v0.2
  reference to validating through `list_transitions` is removed.
* **D10 — `FIRST_ANCHOR`: approved.** A sunrise located only at a walk's first anchor may supply
  `preceding_sunrise` information with `located_by = FIRST_ANCHOR`; it is never a candidate, an
  opening or a closing.
* **D6 (v0.1) — executed at implementation.** IMD public read-only retrieval and NASA reuse are
  approved with the limits of §11; nothing has been retrieved yet.

All decisions are closed at v1.0.

## 14. File manifest (seven repository paths at v1.0; see §17.1 for hashes)

| path | change |
|---|---|
| `src/vedic_chart/panchanga/daily.py` | new: the walks, selection, placement, result types, two entry points; relative imports only (§14.1) and the standard library `dataclasses`, `datetime`, `enum`, `types`, `typing` |
| `src/vedic_chart/panchanga/__init__.py` | additive re-exports (§10), `__all__` kept sorted, docstring paragraph for Layer 18 |
| `tests/test_panchanga_daily.py` | new: §11 |
| `tests/test_panchanga_boundaries.py` | the narrow amendments of §14.1; every existing restriction preserved |
| `docs/LAYER18_DAILY_PANCHANGA_SPEC.md` | this document, v1.0 |
| `README.md` | one section "Daily Panchanga, sunrise to sunrise (Layer 18)" whose example was executed against the implementation before it was written down (§17.1) |
| `docs/LAYER16_PANCHANGA_SPEC.md` | D7 (approved): the one paragraph of §17.6 appended to §10, with a one-line history note; documentation only |

Not touched: `swiss_ephemeris.py`, `sunrise.py`, `compute.py`, `elements.py`, `transitions.py`,
every existing test other than the amendments below, every golden and fixture,
`docs/CALCULATION_SPEC.md`, deployment files.

### 14.1 Amendments to `tests/test_panchanga_boundaries.py` (each additive; no existing pin loosened)

The file pins exactly five modules, per-module standard-library and project import tables, the
relative imports of `transitions.py`, and the public surface; v0.1's "one appended test" could
not have passed. The amendments:

1. `PACKAGE_FILES` gains `"daily.py"`; `test_the_package_modules_are_exactly_the_five_specified`
   becomes `…_six_specified` with `len(PACKAGE_FILES) == 6`. Every parametrised test
   (forbidden imports, allowed and expected standard library, allowed and pinned project
   imports, no rounding, no clock) then runs for `daily.py` automatically.
2. `ALLOWED_STDLIB_BY_FILE["daily.py"] = EXPECTED_STDLIB_BY_FILE["daily.py"] =
   {"dataclasses", "datetime", "enum", "types", "typing"}` — no `zoneinfo`, no `math`.
3. `PROJECT_IMPORTS["daily.py"] = ACTUAL_PROJECT_IMPORTS["daily.py"] = {}`: `daily.py` makes
   **no absolute project import**. The Julian Day of a datetime comes from `sunrise.utc_instant`
   (the one UTC rule, which already returns it), longitudes from Layer 17's `default_evaluate`,
   classifiers from `elements`, the location type from `compute`.
4. A new pinned table `DAILY_RELATIVE_IMPORTS` and a test
   `test_the_daily_module_imports_exactly_its_pinned_sibling_names` (level-1 only), mirroring
   the `transitions.py` one: `elements` → `CALCULATION_CONVENTION`, `Karana`, `Nakshatra`,
   `NityaYoga`, `Tithi`, `elongation`, `karana_from_elongation`, `longitude_sum`,
   `nakshatra_from_longitude`, `tithi_from_elongation`, `yoga_from_sum`; `sunrise` →
   `RiseAfter`, `SUNRISE_CONVENTION`, `SunriseUnavailable`, `SunriseWindow`, `Vara`,
   `default_rise_after`, `find_sunrise_window`, `resolve_zone`, `utc_instant`,
   `validate_coordinates`, `vara_from_sunrise`; `compute` → `LocationProvenance`,
   `PanchangaLocation`; `transitions` → `ALLOWED_TOLERANCES`, `ALL_KINDS`, `DEFAULT_TOLERANCE`,
   `Evaluate`, `PanchangaTransitions`, `SEARCH_CONVENTION`, `SUPPORTED_END`, `SUPPORTED_START`,
   `Transition`, `TransitionKind`, `TransitionList`, `TransitionRequestError`,
   `UnsupportedInstantError`, `default_evaluate`, `find_transitions`, `list_transitions`,
   `same_event` (final list fixed at implementation; D9 may add or remove one name).
5. `"daily.py"` is added to the explicit exclusion tuples of
   `test_only_the_sunrise_module_knows_about_time_zones`,
   `test_only_the_sunrise_module_reaches_the_astronomy_boundary`,
   `test_only_the_composition_module_knows_about_the_chart_model` and
   `test_only_the_elements_module_knows_about_the_frozen_divisions` (each currently lists
   `__init__.py`, `elements.py` and one of `compute.py`/`sunrise.py`; `transitions.py` is
   covered by its own pin, and `daily.py` joins the tuples so the same four divisions of labour
   are asserted for it).
6. `test_the_utc_normalisation_rule_lives_in_exactly_one_place` is unchanged and must still
   pass: `daily.py` contains no `astimezone(timezone.utc)`.
7. `test_the_package_re_exports_through_relative_imports_only`: `"daily"` joins the modules
   asserted present in the relative imports of `__init__.py`.
8. `PUBLIC_SURFACE` gains the 26 names of §10, kept sorted; the invariant
   `package.__all__ == sorted(package.__all__)` is unchanged.
9. `test_every_public_type_is_a_frozen_dataclass_or_an_enum`: `dataclass_names` gains
   `PanchangaDay`, `PanchangaDayUnavailable`, `PanchangaDayAmbiguous`, `DaySunrise`,
   `InstantElements`, `PlacedTransition`; `enum_names` gains `SunriseLocating`, `DayPlacement`,
   `DayUnavailableReason`.
10. A new test, parallel to `test_the_progress_and_bound_checks_survive_optimised_python`, pins
    that every guard of `daily.py` is a `Raise` of `DaySearchError` and that the module contains
    no `Assert`.
11. `test_this_layer_added_no_dependency`, `test_no_module_outside_the_package_imports_it`,
    `test_swisseph_is_imported_by_exactly_one_module_in_the_whole_source`,
    `test_the_layer_five_accessor_is_imported_by_the_sunrise_module_alone` and
    `test_the_frozen_modules_this_layer_reads_were_not_changed_to_suit_it` are unchanged and
    must still pass.

## 15. Limitations (to be carried into v1.0)

* The sunrise is Layer 16's geometric Hindu rising; almanacs printing refracted upper-limb
  sunrise differ by minutes, and a transition in that gap moves between days.
* Layer 16's search does not reproduce a sunrise float exactly from every instant:
  differences up to ~14 ms were observed from every instant at the sampled latitudes above
  ~65°, and up to ~141 ms from instants in the last minutes of days longer than 24 hours at
  the sampled lower latitudes (§3.2). Layer 18's days are consistent among themselves by the
  canonical rule, but Layer 16 asked directly at an instant within that distance of a sunrise
  may bracket it into the other day (§7.3). No bound is claimed for other latitudes, dates or
  library builds.
* The Julian Day and datetime membership predicates differ within the ~40 µs of datetimes that
  share a sunrise float (§7.1); both are kept as their layers define them.
* Civil dates that a zone skips or repeats produce typed results, never a neighbouring date.
* The coverage bound of §4.10 is an assumption about the tz database (|offset| ≤ 16 h), tested,
  not an astronomical one.
* UT1 and model notes of Layer 17 apply to every transition; the UTC-as-UT1 approximation of
  Layer 4 applies to every sunrise.

## 16. Change log

### v1.0 from v0.3 (closing revision, 2026-09-27)

1. Native targeted verification recorded (§17.4).
2. Explicit-ordinal contract made normative: zero candidates → `PanchangaDayUnavailable`
   whatever the ordinal; an ordinal above a nonzero count → `DayRequestError` (§4.3, §9,
   §10); five regressions added, the out-of-range test retained (§11).
3. External-validation wording tightened: IMD is numerical agreement with the captured table
   at New Delhi, not evidence of matched day assignment; the 29 September karana difference
   is explained conditionally and left unattributed; NASA limited to six phase boundaries
   (§17.7).
4. Scratch scripts made runnable from the repository root without hard-coded paths (§17.8).
5. README section added with an executed example; manifest of seven repository paths (§14).

### v0.3 from v0.2 (decisions D7–D10 and four findings)

1. *Containing-form ordinal.* `civil_date` and `sunrise_ordinal` come from the date form's own
   enumeration for the opening's civil date, through one shared helper; counting inside the
   containing walk is withdrawn; cost and range reasoning updated for the second walk (§4.3,
   §4.7, §4.8; probe F1; regression in §11, labelled synthetic coverage of the allowed-gap
   contract).
2. *Bounded neighbour information.* `preceding_sunrise`/`following_sunrise` are what the walk
   found; `None` means "not found within the search"; polar expectations restated per written
   walk range, including `following_sunrise is None` for the 66.57 N containing query (§6, §8,
   §11; probe F2).
3. *Grid-aligned opening.* A change 1 µs after a grid-aligned opening is `WITHIN` by §4.6;
   `STRADDLES_OPENING_AFTER` is tested with an opening strictly inside a cell (§4.6, §11;
   probe F3).
4. *Wording.* `WITHIN` and the other placements state a datetime-cell relation, not Julian Day
   membership (§8); "listed by the next day" is conditional on an adjacent complete day (§4.6,
   §8); date-to-containing round-trip tests restricted to the containing form's instant range
   (§11); the per-kind probability corrected to ≈ 1.16 × 10⁻⁶ (§7.4).
5. *Decisions.* D7 approved (text and manifest entry), D9(a) approved (§9 restated, the
   `list_transitions` reference removed), D10 approved (§4.2), D8 provisional (§13).

### v0.2 from v0.1 (the six findings)

1. *Indices, not records.* Placement compares `T.before.index`/`T.after.index` with the index of
   the opening element; `same_event` remains the transition identity; whole-record equality is
   kept only for the same-instant cross-check (§3.3, §4.5, §4.6; probe D1).
2. *Closing boundary.* `closing_straddles` → `cells_at_closing` with `before_utc < closing.utc
   <= after_utc`, placement `AT_OR_BEFORE_CLOSING`, and the claim reduced to "the change lies in
   `(before_utc, closing.utc]`"; the reciprocal test now includes the cell ending at the
   boundary; actual changes before/at/after closing are tested separately from representative
   membership (§4.6, §11; probes D2, E).
3. *Polar gaps and the containing form.* Complete windows, next-only sunrises and unavailable
   stretches are represented as walk entries; the containing form requires
   `opening_jd <= jd(t) < closing_jd`; the `NO_NEXT`-only fallback condition and the adjacency
   guard are withdrawn; the final complete day, lone sunrise, gap and resumed day are tested
   through both entry points (§4.2, §4.3, §6, §11; probe D3).
4. *Two membership predicates.* Kept distinct, documented with the four-row table and tested at
   both endpoints; the round-trip bound corrected (forward ≤ 1.454 µs, reverse ≤ 2.211 µs,
   total below the 20.117 µs half-ULP; measured 1.4534 µs); the image check retained (§2, §3.1,
   §7.1, §7.2; probes D4, D5).
5. *Boundary tests and manifest.* The eleven amendments of §14.1 enumerated; `daily.py` makes
   no absolute project import; the conditional Layer 16 note is in the manifest (§14).
6. *Evidence and ranges.* Every reproducibility figure qualified as a sample; ranges derived
   for both entry points with the date-form round trip made total; pre-evaluation validation
   separated from post-discovery checks; the cost bound corrected to nine probes per phase and
   the final algorithm's cost measured with the closing-side query; IMD and NASA usage limited
   to what each can validate (§3.2, §4.7, §4.8, §9, §11).

## 17. Implementation record (2026-09-27, DRAFT v0.3 implemented; nothing staged or committed)

Built by an Opus subagent from this draft, reviewed against it by Fable; the cloud sandbox copy
(Linux x86_64, Python 3.11.15, pyswisseph 2.10.03) was verified file-for-file equal to
`d90ebb0` (all 141 tracked blobs) before any change.

### 17.1 Files (cloud copy == Mac working tree, SHA-256 prefixes; seven repository paths)

| path | change | lines | sha256 |
|---|---|---|---|
| `src/vedic_chart/panchanga/daily.py` | new | 1250 | `64e275d9b0f0dc5a` |
| `src/vedic_chart/panchanga/__init__.py` | 26 re-exports, sorted `__all__`, Layer 18 docstring paragraph | 163 → 227 | `efe43b37d973d472` |
| `tests/test_panchanga_daily.py` | new, 70 test functions (198 tests at v1.0; 193 at review) | 2057 | `79e8309d4a7f8dad` (review state `db34002c854adc20`) |
| `tests/test_panchanga_boundaries.py` | the eleven amendments of §14.1 only (the removed lines are exactly the comment, the five→six rename and count, the four exclusion tuples, the relative-modules tuple and the `enum_names` line they replace) | 788 → 970 | `f821dfbe06507cca` |
| `docs/LAYER16_PANCHANGA_SPEC.md` | D7: the §10 paragraph of §17.6 and a header history line; documentation only | 486 → 504 | `8b62cb87a9a94286` |
| `docs/LAYER18_DAILY_PANCHANGA_SPEC.md` | this document, v1.0 | | (see the Mac/cloud hash in the delivery report) |
| `README.md` | one section "Daily Panchanga, sunrise to sunrise (Layer 18)", example executed before it was written down | 1121 → 1199 | `0fecdf92c552d8ef` |
| `Claude outputs/l18_probe_g.py`, `l18_range_check.py`, `l18_range_check_cloud.log`, `l18_imd_compare.py`, `l18_nasa_compare.py`, `imd_daily_2026-09-21_28.txt`, `l18_imd_compare.log`, `l18_nasa_compare.log`, `l18_vm_baseline_full.log`, `l18_vm_updated_full.log` | scratch and records, outside the package | | |

Protected files verified unchanged against their `d90ebb0` blobs after the work:
`sunrise.py` `d08d4a785e871ba6`, `compute.py` `b76dfae25a9dd535`, `elements.py`
`045220715054e648`, `transitions.py` `f2aface907eb341c`, `swiss_ephemeris.py`
`548caa10033b5bd1`, `docs/CALCULATION_SPEC.md` `07d5cc2ceb43a737`,
`docs/LAYER17_PANCHANGA_TRANSITIONS_SPEC.md` `8b42cdd14c727201`; every golden and fixture; the
blob comparison of all 141 tracked files lists exactly `docs/LAYER16_PANCHANGA_SPEC.md`,
`src/vedic_chart/panchanga/__init__.py` and `tests/test_panchanga_boundaries.py` as changed.
README not touched (its Layer 18 section is a promotion item, §14). No dependency change
(`test_this_layer_added_no_dependency` passes). `daily.py` contains no `assert`, no `round(`,
no `astimezone(timezone.utc)`, no clock attribute; relative imports only; standard library
exactly `dataclasses`, `datetime`, `enum`, `types`, `typing`.

### 17.2 Interpretations recorded by the implementation (none weakens a rule)

* The containing walk visits the anchors inside the closed range: eleven when *t* is off the
  grid, twelve when on it (§4.3 corrected; a test pins both counts).
* A date form request with zero candidates returns the unavailable result whatever
  `sunrise_ordinal` says; `DayRequestError` is raised only when candidates exist and the
  ordinal exceeds their count.
* "Before/after the date's span" is read on the sunrise's local date; in the containing form
  on Julian Day ≤ / > `jd(t)`.
* Were several next-only sunrises to carry one date, the first would be the lone sunrise.
* Three guards beyond §4.2/§5, each tested: the opening must be `CANONICAL_ANCHOR`
  (`__post_init__`); a Layer 16 result of another type than `SunriseWindow`/
  `SunriseUnavailable` is a `DaySearchError`; the containing form raises `DaySearchError` if
  the opening's civil date falls outside the date range (which the instant range makes
  impossible).
* `daily.py` imports a subset of §14.1 item 4: `SUPPORTED_START`/`SUPPORTED_END` of
  `transitions` are not needed and not imported; the boundary test pins the actual set.
* The new boundary test requires `DaySearchError` in the five guard helpers (`_walk`,
  `_day_sunrise`, `_ordinal_of`, `_elements_at`, `_placement`), `ValueError` only in
  `PanchangaDay.__post_init__`, and one of the five named error classes anywhere else.

### 17.3 Discrepancies between this draft's expectations and observed values

* **Ushuaia parity at `closing.utc − 1 s`** (§11 expected bit-for-bit window floats at the
  three lower places): on 40 of 40 dates (2024-03-01 … 04-09) Layer 16's `previous` float
  differed from the canonical opening by up to 140.937 ms, with the vara and the `next` float
  identical. Probe G traced it to the probe-position dependence of §3.2. The test pins that one
  cell by event identity and records the difference; code and rules unchanged.
* **Tromsø**, recorded not pinned: Layer 16 at `opening.utc` named the previous window on 16
  of 40 dates (2024-02-01 … 03-11); largest same-event difference 11.507 ms; vara and event
  identity held on all 40 days at `± 1 s` and mid-day.
* Everything else in §11 matched: the reference days and their seven/six cells, the four
  membership rows, all polar cases through both entry points, the civil-date cases, F1, E, F3.

### 17.4 Test results (exact)

* Cloud sandbox (Python 3.11.15), implementation as delivered for review:
  `tests/test_panchanga_daily.py` + `tests/test_panchanga_boundaries.py` → **260 passed**
  (193 + 67) in 17.5 s; under `python -O` → **260 passed, 1 warning** (pytest's notice that
  asserts outside test modules are ignored under `-O`). All `tests/test_panchanga_*.py` →
  **1159 passed**. Full suite: baseline at `d90ebb0` **3626 passed, 12 failed**; updated
  **3828 passed, 12 failed**. At v1.0 (five regressions added): the two files → **265 passed**
  (198 + 67) and **265 passed, 1 warning** under `-O`; full suite **3833 passed, 12 failed**.
  In every run the failure set is identical (8 `test_dasha_from_chart`, 2 `test_dasha_table`, 2 `test_viewer_transport` —
  the environment-dependent goldens recorded since Layer 14; none regenerated or relaxed).
* Session VM (Linux aarch64, project `.venv` Python 3.10.12, pyswisseph 2.10.03): baseline run
  on a `git archive d90ebb0` extraction with `data/geodata.sqlite` linked in →
  **3638 passed, 0 failed**; updated working tree at review → **3840 passed, 0 failed**, the
  two files **260 passed** normally and **260 passed, 1 warning** under `-O`; at v1.0 →
  **3845 passed, 0 failed**, the two files **265 passed** and **265 passed, 1 warning**.
* Native macOS (Darwin arm64, Python 3.11.16, native pyswisseph), run by the owner from
  Terminal on the implementation as delivered (the 260-test state): `tests/test_panchanga_daily.py`
  + `tests/test_panchanga_boundaries.py` → **260 passed** normally and **260 passed** under
  `python -O` with the expected pytest warning. The pure-Python pytest already present in the
  session environment was reused; nothing was installed into the native environment. This is
  the **targeted native verification** of the two Layer 18 test files, not a native full-suite
  run; no native full-suite figure is claimed.
* Closing revision (2026-09-27, after the review): five regression tests for explicit ordinals
  on unavailable results were added (§11, §16); the two files then give **265 passed** normally
  and **265 passed, 1 warning** under `python -O` in the cloud sandbox and likewise on the
  session VM; the full suites were re-run in both environments (cloud **3833 passed, 12
  failed**, the same 12; VM **3845 passed, 0 failed**). The native targeted figures above
  are for the review state (260 tests); the five added tests were not run natively.
* Cost (cloud, after warm-up): `panchanga_day` 33.6/34.7 ms per day at Jalandhar, 57.3/58.4 ms
  at Tromsø; `panchanga_day_containing` 36.9/36.7 ms at Jalandhar.

### 17.5 Final ranges (D8) — fresh-interpreter check

`l18_range_check.py`: for each of the four edges, every date/instant from edge − 4 to edge + 4
days, at latitudes 0, +66, −66 and longitudes −180, 0, +180, one fresh interpreter each
(324 runs). Every run outside a range was refused typed before any evaluation (a `rise_after`
that raises was never called); every run inside produced a complete `PanchangaDay`; no engine
error anywhere. The constants therefore stand as proposed and nothing moved inward:
`SUPPORTED_DATE_START = 1800-01-07`, `SUPPORTED_DATE_END = 2399-12-21`,
`SUPPORTED_INSTANT_START = 1800-01-10T00:00Z`, `SUPPORTED_INSTANT_END = 2399-12-21T00:00Z`.
The committed tests assert both edges of both ranges in-process and in fresh interpreters
(`test_each_edge_answers_in_a_fresh_interpreter`).

### 17.6 The Layer 16 paragraph applied (D7)

Appended to Layer 16 §10 as its last bullet, with the header line *"Documentation addition
2026-09-27 (Layer 18 D7, approved by the project owner): one limitation paragraph appended
to §10, 'Reproducibility of a sunrise float'; no convention, code, test or golden changes."*:

> **Reproducibility of a sunrise float** (documentation addition 2026-09-27, Layer 18 D7). The
> Julian Day the library returns for one sunrise depends on the probe it was asked from, and
> this module's probe positions depend on the instant. Asked from different instants of one
> day, `find_sunrise_window` returned bit-identical Julian Days for a sunrise at every sampled
> place below about 65° of latitude (Jalandhar, Jammu, Apia, Ushuaia −54.8°, Anchorage 61.2°,
> Reykjavik 64.1°; 2023–2024) from instants 0.5 h to 22.5 h after it, but from an instant in
> the last minutes of a day longer than 24 hours — when the two-day span behind the instant
> starts after the previous sunrise — it returned a float up to about 141 ms away (Ushuaia,
> March 2024; 84 ms at Jalandhar in August, 88 ms at Anchorage and 36 ms at London in
> September). At the sampled places above 65° (65.5° N, 66.5° N and Tromsø 69.6° N; 2024),
> where the slow search is used, the floats differed by up to about 14 ms from every instant.
> These are measurements at the sampled places, dates and library build, not bounds. A caller
> that re-asks this module at the exact datetime of a sunrise it returned can therefore be
> bracketed into the previous day (observed on 26 of 60 sampled dates at Tromsø); comparisons
> across separate searches must use the floats of one search or an event-identity rule of
> their own, as Layer 18 does with its anchor grid (`docs/LAYER18_DAILY_PANCHANGA_SPEC.md`
> §3.2, §4.1). Nothing in this module changes.

### 17.7 External comparisons (D6; retrieved 2026-09-27 through the desktop browser pane)

**IMD Positional Astronomy Centre, "Daily Astronomical Information"**
(`packolkata.imd.gov.in/page.php?q=65`, public, read-only). The page shows only the current
week — 21 to 28 September 2026 — so the two reference birth dates could not be compared there;
the eight days shown were compared instead (`l18_imd_compare.py`, `imd_daily_2026-09-21_28.txt`,
`l18_imd_compare.log`). IMD prints the element current at sunrise and its ending time in IST to
the minute; ending times are geocentric, so Layer 18 was asked at New Delhi (28.6139 N,
77.2090 E). Result: all 8 varas agree; all 8 tithi, 7 nakshatra (the eighth is "ahoratra" and
Layer 18 lists no nakshatra change in that day), 8 yoga and 16 karana names agree after
transliteration; all 39 printed ending times agree with Layer 18's cell ends within ±30 s
(largest +29.4 s, −28.2 s), i.e. to IMD's rounded minute. This is **numerical agreement with
the captured table, using Layer 18's New Delhi calculation**: the page states neither the
location nor the sunrise convention behind its day boundaries, so it does not establish that
Layer 18's sunrise-based assignment of elements to days matches IMD's. One difference
illustrates that: for 28 September Layer 18's day (geometric sunrise 06:16:14 IST, closing
06:16:45 the next morning) lists a third karana change, Vanija→Vishti, at 06:14:16 IST on the
29th, which IMD does not print under the 28th. A sunrise earlier than Layer 16's geometric one
— for instance a refracted upper-limb sunrise, which precedes it by a few minutes — could
explain the difference by placing that change in the 29th; whether that is IMD's reason is
unverified, and the attribution is recorded as open. The page's Moon-sign entry times are
outside Layer 18's scope and were not compared.

**NASA GSFC phase table** (`eclipse.gsfc.nasa.gov/phase/phases2001.html`, UT, minute). Used
only for the tithi 30→1 (new moon) and 15→16 (full moon) boundaries, which is all it can check
(`l18_nasa_compare.py`, `l18_nasa_compare.log`): the day containing each phase instant, asked
through `panchanga_day_containing` at Jammu for 2001 and New Delhi for 2026, carries exactly
one such tithi cell, ending 2001-01-24 13:06:49.9 (NASA 13:07), 2001-02-08 07:11:39.5 (07:12),
2001-02-23 08:21:05.7 (08:21), 2026-09-11 03:27:00.3 (03:27), 2026-09-26 16:49:02.8 (16:49)
and 2026-10-10 15:50:05.5 (15:50) UT — all within the printed minute (−20.5 s … +5.7 s). NASA
validates nothing about the complete Panchanga of either ordinary reference birth date.

Nothing was fetched from any other almanac.

### 17.8 Promotion record

The implementation review passed on 2026-09-27; the native targeted verification (§17.4) was
recorded; the explicit-ordinal contract was reconciled into §4.3, §9 and §10 with regressions
(§11, §16); the external-validation wording was tightened (§17.7); the comparison and probe
scripts in the ignored `Claude outputs/` folder were made runnable from the repository root
without hard-coded paths (`PYTHONPATH=src python "Claude outputs/<script>"`; they locate the
repository and their data relative to themselves and use the running interpreter); the README
section was added with an executed example; and this document was promoted to v1.0. The seven
repository paths of §14 are the milestone; nothing is staged, committed, pushed or deployed,
and no viewer, CLI or HTTP surface touches Layer 18.
