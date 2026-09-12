# Layer 13 — Daśā table and public exposure — SPECIFICATION v1.0

**Status:** v1.0 — **APPROVED.** Implemented against DRAFT v0.2 (with the two approved
corrections and the closing revision of §3/§6/§7) and promoted after the implementation review
recorded in §11; the promotion changed no behaviour. This layer presents and
exposes the Layer 12 Vimshottari results (`docs/LAYER12_VIMSHOTTARI_SPEC.md` v1.0, `ca73515`)
through a plain-text table, public functions and the existing CLI. It changes **no daśā
arithmetic**, **no D1 SVG renderer** behaviour, and none of the Layers 1–12 calculation contracts,
existing fixtures or SVG goldens. The Layer 11 specification stays frozen and untouched; where this
document widens Layer 11's import rules, **this document supersedes** (R5).

**Owner decisions carried into this draft (2026-09-12).** Scope: a pure plain-text table plus
immutable structured rows; public `compute_dasha`; CLI integration with a separate `--dasha-out`
destination (file or stdout, never interleaved with diagnostics on stderr); bare `--dasha` =
`md-ad`, `md` and `md-ad-pd` explicit; no ages in v1; CLI year choices `365.25` / `365.256363`,
required whenever daśā output is requested, no implicit default; second precision by default,
`day` allowed with a warning. Closed in v0.2: **R1** `--dasha-zone` included, defaulting to the
birthplace zone; **R2** two separate birth-marker columns `N` and `Q`; **R3**
`render_chart_and_dasha` is public and exported; **R4** file outputs first — SVG before daśā when
both are files — and stdout last; **R5** Layer 11 specification untouched, superseding import
rules recorded here (§2).

## 1. Scope and non-goals

In scope: `vedic_chart.dasha.table` (rows and text); `vedic_chart.app.compute_dasha` and
`vedic_chart.app.render_chart_and_dasha` over one shared assembly step; new CLI options; tests
and two small text goldens; a README subsection; a factual validation record (§9).

Out of scope: any change to `render_north_indian_svg` or the SVG document; drawing daśās on the
chart; HTML/JSON/CSV export; sūkṣma/prāṇa levels; other year conventions, starting bodies or
orders; any lookup that reads the clock (a future `--at INSTANT` is deferred); interpretation.

## 2. Modules, counts and import rules

```
src/vedic_chart/dasha/table.py      NEW   pure presentation: DashaRow, dasha_rows, render_dasha_text, resolve_zone
src/vedic_chart/dasha/__init__.py   MOD   re-exports the four table names
src/vedic_chart/app/pipeline.py     MOD   _assemble_once; compute_dasha; render_chart_and_dasha; two result types
src/vedic_chart/app/cli.py          MOD   daśā options, output modes, second destination (§6)
src/vedic_chart/app/__init__.py     MOD   re-exports compute_dasha, DashaResult, render_chart_and_dasha, ChartAndDashaResult
```

**Module counts.** The `app` package keeps exactly its four modules (`__init__`, `pipeline`,
`cli`, `__main__`) — this milestone adds **no** app module. The `dasha` package grows from three
modules to **four** (`__init__`, `vimshottari`, `from_chart`, `table`). The AST tests that assert
these counts (`tests/test_app_boundaries.py`, `tests/test_dasha_boundaries.py`) are updated to
4 and 4 and to the public-name sets below.

**Import rules (AST-enforced; these supersede Layer 11 §9 for the app package).**
- `dasha/table.py`: stdlib `dataclasses`, `datetime`, `fractions`, `typing`, **`zoneinfo`**
  (allowed for this presentation module only; the Layer 12 core modules keep their list, which
  excludes `zoneinfo`); project names `vedic_chart.dasha.vimshottari` (`VimshottariTimeline`,
  `DashaPeriod`, `YearConvention`, `DashaRangeError`) and `vedic_chart.vedic.grahas` (`Graha`).
  Forbidden: `render`, `representation`, `app`, `chart`, `location`, `time`, `inputs`, anything
  astronomical, `round()`, any clock.
- `app/pipeline.py`: Layer 11's list plus `vedic_chart.dasha` (`vimshottari_from_chart`,
  `VimshottariTimeline`, `YearConvention`).
- `app/cli.py`: Layer 11's list plus `vedic_chart.dasha` (`YearConvention`, `DashaRangeError`,
  `render_dasha_text`, `resolve_zone`). The Layer 11 rule "exception classes only from the three
  modules" is retained for those three modules; `vedic_chart.dasha` is the one additional source
  and may contribute exactly the four names above.
- Public names: `vedic_chart.dasha` adds `DashaRow`, `dasha_rows`, `render_dasha_text`,
  `resolve_zone`; `vedic_chart.app` adds `compute_dasha`, `DashaResult`,
  `render_chart_and_dasha`, `ChartAndDashaResult`.

## 3. `vedic_chart.dasha.table`

```python
@dataclass(frozen=True)
class DashaRow:
    level: int                          # 1, 2, 3
    lords: tuple[Graha, ...]            # chain, len == level
    start_utc: datetime                 # the DashaPeriod's quantized instants, unchanged (lossless, UTC, µs)
    end_utc: datetime
    nominal_start: Fraction             # exact offsets from birth, years (Layer 12 §6)
    nominal_end: Fraction
    in_nominal_birth_chain: bool        # N: this period is one of timeline.periods_at_birth()
    in_quantized_birth_chain: bool      # Q: this period is one of timeline.active_periods_at(birth_utc)

def resolve_zone(key: str) -> ZoneInfo
def dasha_rows(timeline: VimshottariTimeline, *, depth: int) -> tuple[DashaRow, ...]
def render_dasha_text(timeline: VimshottariTimeline, *, zone: str, depth: int = 2,
                      precision: str = "second") -> str
```

**Validation (all functions).** `timeline` must be a `VimshottariTimeline` (`TypeError`).
`depth` must satisfy `type(depth) is int` — `bool` and floats such as `1.0` are rejected with
`TypeError` even though they compare equal to a member of `{1, 2, 3}` — and be 1, 2 or 3
(`ValueError`). `precision` must be a `str` equal to `"second"` or `"day"` (`TypeError` /
`ValueError`). `zone` must be a `str` (`TypeError`); `resolve_zone` is the **single** zone
validator for this layer: it calls `zoneinfo.ZoneInfo(key)` and converts both failure kinds —
`zoneinfo.ZoneInfoNotFoundError` (a `KeyError` subclass, unknown key) and the `ValueError` raised
for malformed keys — into one `ValueError` naming the key, chained from the original. No zone is
ever inferred from coordinates or country.

**Rows.** Pre-order traversal: each Mahādaśā, then (depth ≥ 2) its nine antardaśās, each followed
(depth ≥ 3) by its nine pratyantars: 9 / 90 / 819 rows. Timestamps are the `DashaPeriod`
datetimes **unchanged** — rows are lossless and carry no zone. The two birth flags are separate
because Layer 12 §7 documents cases in which a remainder shorter than one microsecond makes the
nominal chain and the quantized chain differ (`nextafter(40.0, 0)`, `3.666666666666666`); a single
"contains birth" flag would erase that. Flags are set by value comparison of `(level, lords)`
with the two chains, never by proximity.

**Text layout** (illustrative values; `...` elided):

```
Vimshottari dasha  |  Moon 209.20440791222882 (Vishakha #16)  |  lord Jupiter
Birth 1995-03-21 06:45:00+05:30 (Asia/Kolkata)  |  year 365.256363 days  |  depth md-ad
Nominal balance of the first Mahadasha at birth: 87164189005907/17592186044416 = 4.954710505 years (nominal; decimal truncated to 9 places)
Intervals are half-open [start, end). Timestamps are truncated to the second and shown in Asia/Kolkata with the UTC offset.
The first Mahadasha begins at or before birth (before birth unless the core's elapsed nakshatra fraction is zero); its pre-birth part is listed.
Columns: N = period contains the birth instant by exact nominal offset; Q = period contains the birth timestamp after microsecond quantization.

Level  Chain     Start                      End                        N  Q
MD     Ju        1984-03-03 22:03:19+05:30  2000-03-04 00:29:56+05:30  N  Q
AD     Ju-Ju     1984-03-03 22:03:19+05:30  1986-04-21 ...
AD     Ju-Su     1994-09-14 ...             1995-07-03 ...             N  Q
...
```

The header shows what the timeline holds — the Moon longitude, `nakshatra_name`,
`nakshatra_number` and the lord. It does **not** show the pada: `VimshottariTimeline` carries no
pada field and this layer introduces no classification calculation to obtain one.

Rules: (a) each timestamp is `start_utc`/`end_utc` converted with
`astimezone(resolve_zone(zone))` and printed as `YYYY-MM-DD HH:MM:SS±HH:MM[:SS]` — the local
wall time truncated to the second (a displayed instant is never later than the true boundary),
and the UTC offset printed **exactly as the zone reports it, seconds included when non-zero**
(e.g. `+05:21:10` for Asia/Kolkata's pre-1906 Madras time, `+00:19:32` for early Amsterdam), so
the represented instant is never altered by forcing `±HH:MM`; the offset makes repeated local
times distinguishable (a DST fall-back hour prints `+01:00` then `+00:00` in Europe/London).
(b) With `precision="day"` each **period-row** timestamp is the zone-local **calendar date**
`YYYY-MM-DD` of the boundary; the header's `Birth` line is **always** printed at second precision
with its exact UTC offset, whatever the precision, because it is the anchor every row is measured
from; and the header carries `WARNING: day precision - dates omit boundary times; a period
listed as ending on a date may end at any instant of that date, and half-open boundaries cannot
be expressed at day resolution.` (c) The nominal balance is printed as the exact `Fraction` then a
decimal produced by integer arithmetic only: `q = balance.numerator * 10**9 // balance.denominator`,
rendered `q // 10**9 "." q % 10**9` zero-padded to nine digits — truncation toward zero, so
labelled; the string is never parsed back or used in any computation. (d) Lords use the D1
renderer's two-letter abbreviations (Su Mo Ma Me Ju Ve Sa Ra Ke) joined by `-`. (e) The header
states the year as its day count, the zone key, and the depth word (`md`, `md-ad`, `md-ad-pd`).
(f) The text ends with one newline and contains no diagnostics. (g) **Conversion overflow:** an
instant within a zone offset of `datetime`'s limits cannot be converted — near `datetime.max` a
**positive-offset** zone overflows, near `datetime.min` a **negative-offset** zone underflows —
and `astimezone` raises `OverflowError`; the table catches it at the conversion of that timestamp
and raises `DashaRangeError` (imported from the core) naming the timestamp and zone. Nothing else in the
module catches `OverflowError` or `ValueError`. `render_dasha_text` computes nothing about daśās.

## 4. Public functions (`vedic_chart.app.pipeline`)

```python
def _assemble_once(request: BirthChartRequest, config: ChartConfig) -> tuple[BirthChart, ResolutionDecision]
    # the existing body of render_birth_chart up to assembly: OfflineLocationResolver.resolve_with_details
    # once (closed before the ephemeris opens); ephemeris_session around assemble_chart with
    # _PreresolvedResolver; identity assertion. No argument validation: callers validate first.

def render_birth_chart(request: BirthChartRequest, config: ChartConfig,
                       options: NorthIndianOptions = _DEFAULT_OPTIONS) -> ChartResult
    # UNCHANGED contract and ordering: request, config and options are type-checked (ValueError)
    # before _assemble_once; then build_d1_chart and render_north_indian_svg.

@dataclass(frozen=True)
class DashaResult:
    request: BirthChartRequest
    chart: BirthChart
    timeline: VimshottariTimeline
    resolution: ResolutionDecision

def compute_dasha(request: BirthChartRequest, config: ChartConfig, year: YearConvention) -> DashaResult
    # validation, in order, before any resource use: request (ValueError), config (ValueError),
    # year must be a YearConvention member (TypeError — the core's rule, checked here first so
    # that a bad year never opens the database); then _assemble_once; then vimshottari_from_chart.

@dataclass(frozen=True)
class ChartAndDashaResult:
    request: BirthChartRequest
    chart: BirthChart
    resolution: ResolutionDecision
    d1: D1Chart
    svg: str
    timeline: VimshottariTimeline

def render_chart_and_dasha(request: BirthChartRequest, config: ChartConfig,
                           options: NorthIndianOptions, year: YearConvention) -> ChartAndDashaResult
    # validation in order: request, config, options (ValueError, as render_birth_chart), year
    # (TypeError); then ONE _assemble_once; d1/svg from that chart; timeline from that same chart.
```

`options` has no default in `render_chart_and_dasha` and `year` has none anywhere. Guarantees,
tested: `render_birth_chart` is byte-identical to Layer 11 v1.0 on every existing SVG golden and
still rejects invalid renderer options before any resource use; `compute_dasha(...).timeline ==
vimshottari_from_chart(compute_dasha(...).chart, year)`; in `render_chart_and_dasha`,
`d1.source is chart`, the timeline was built from that `chart` (adapter cross-check), and
`resolve_with_details` and the ephemeris session run exactly once (spies). Errors from the layers
below propagate with their own types; `DashaRangeError` from the core is not caught here.

## 5. Birth membership

Two chains, two columns (§3): **N** — the nominal chain `timeline.periods_at_birth()` (exact
Fraction membership of offset 0); **Q** — the quantized chain
`timeline.active_periods_at(timeline.birth_utc)` (half-open microsecond intervals). For ordinary
births both columns mark the same three rows. In the Layer 12 divergence cases the table shows
the difference: for `nextafter(40.0, 0)`, rows Su / Su–Ve / Su–Ve–Ke carry `N` only and rows Mo /
Mo–Mo / Mo–Mo–Mo carry `Q` only; for `3.666666666666666`, row Ke carries both, Ke–Su / Ke–Su–Ve
carry `N` only and Ke–Mo / Ke–Mo–Mo carry `Q` only.

## 6. CLI (`python -m vedic_chart.app`)

**New options** (all Layer 11 options keep their names and meanings):

```
--dasha [md|md-ad|md-ad-pd]        request the dasha table; bare --dasha = md-ad
--dasha-year {365.25,365.256363}   required with --dasha -> YearConvention.FIXED_365_25 / FIXED_365_256363
--dasha-out PATH|-                 required with --dasha; the table's destination
--dasha-precision {second,day}     default second
--dasha-zone IANA                  default: the resolved birthplace's timezone_id
```

**Sentinels.** `--dasha-precision`, `--dasha-zone`, `--caption`, `--no-degrees`,
`--mark-node-retrograde`, `--width` and `--id-prefix` are declared with a private `_UNSET`
default (not their effective defaults) so that "explicitly supplied" is distinguishable from
"defaulted". Effective defaults are applied after the mode checks below. (`--print-chart` does
not exist in this CLI and is not added.)

**Output modes and usage errors** (checked after parsing, reported with `parser.error`, argparse's
own exit 2, nothing on stdout):
- *SVG-only*: `--out` present, no daśā option. Identical to Layer 11.
- *Daśā-only*: `--dasha`, `--dasha-year`, `--dasha-out` present, no `--out`. Explicitly supplied
  renderer flags (`--caption`, `--no-degrees`, `--mark-node-retrograde`, `--width`,
  `--id-prefix`) are **rejected** as orphans ("renderer options require --out") rather than
  silently accepted.
- *Combined*: `--out` and the three daśā options.
- Errors: no `--out` and no `--dasha` ("at least one of --out or --dasha is required" — a bare
  invocation is still a usage error, as in Layer 11); `--dasha-year`, `--dasha-out`, an explicit
  `--dasha-precision` or `--dasha-zone` without `--dasha`; `--dasha` without `--dasha-year` or
  without `--dasha-out`; `--out -` together with `--dasha-out -` ("at most one output may go to
  stdout").

**Order of operations** (extends Layer 11 §8): parse → mode checks → renderer options
(`NorthIndianOptions`, `ValueError` → 2, only when SVG is requested) → daśā presentation options
(`resolve_zone` on an explicit `--dasha-zone`, `ValueError` → 2; precision; year mapped) →
request → `ChartConfig` → **pre-check every requested file destination** with the unchanged
Layer 11 §8.2 rules (both destinations; `--force` applies to both) plus the collision rule: the
two normalised destinations must not be equal and, when both exist, must not be
`os.path.samefile` (→ 5, "the SVG and dasha destinations refer to the same file") → **one
calculation** (`render_birth_chart`, `compute_dasha` or `render_chart_and_dasha` by mode) →
**all requested content generated in memory** (the table rendered with the birthplace zone unless
`--dasha-zone` was given; SVG and table encoded UTF-8) → writes.

**Write order (R4).** File destinations first — SVG before daśā when both are files — and a
stdout destination, if any, last. All combinations: `svg→file`; `dasha→file`; `svg→file,
dasha→file` (SVG then daśā); `svg→file, dasha→stdout` (file then stdout); **`svg→stdout,
dasha→file` (daśā file first, then SVG on stdout)**; `svg→stdout`; `dasha→stdout`. Each write
uses the unchanged Layer 11 §8.3 machinery (`O_EXCL` direct write, or temporary + fsync +
`os.replace` with `--force`, conservative cleanup with the three stderr wordings, the
`stdout_broken` flag through `run`). **Two writes are not one atomic transaction.** If the second
write fails after the first succeeded — including a broken pipe on an SVG going to stdout after
the daśā file was written — the first output is **kept** (never deleted as rollback), the failure
is reported with the Layer 11 messages, and stderr adds one line: `note: <svg|dasha> output was
written to <path> and is kept`. Exit is 5 (or the stdout-broken pair `(5, True)`). A file left by
the failed second write is subject only to that write's own conservative cleanup.

**Exit codes and error scopes.** Table unchanged; additions by type and by stage: the
`ValueError` from `resolve_zone` is caught only around that call (2); `DashaRangeError` raised by
`compute_dasha`/`render_chart_and_dasha` (cycle outside `datetime`'s range) or by
`render_dasha_text` (zone-conversion overflow) is caught by type around those calls (2). The
content-generation step — `render_dasha_text` and the UTF-8 encoding of both documents — has its
own generic handler with the pipeline's policy: any other exception there (an unexpected
`ValueError`, `OverflowError`, `UnicodeEncodeError`, …) is exit 1 with a one-line diagnostic
`error: <Type>: <message>`, a traceback only with `--verbose`, nothing on stdout, and — since all
content is generated before any write — no output file created or modified. No handler
reinterprets an internal error as an input error, and `run` never lets one escape. The collision
refusal is 5. `--verbose` additionally reports the daśā destination, zone, year and depth on
stderr.

**Examples.**

```bash
# SVG only (Layer 11, unchanged)
python -m vedic_chart.app --date 1995-03-21 --time 06:45 --place "Jalandhar" \
        --geodata data/geodata.sqlite --ephemeris ephe --out jalandhar.svg
# dasha only: Mahadasha + Antardasha, seconds, birthplace zone
python -m vedic_chart.app --date 1995-03-21 --time 06:45 --place "Jalandhar" \
        --geodata data/geodata.sqlite --ephemeris ephe \
        --dasha --dasha-year 365.256363 --dasha-out jalandhar_dasha.txt
# combined: one calculation, two files (SVG written first)
python -m vedic_chart.app --date 2001-02-04 --time 10:45 --place "Jammu, Jammu and Kashmir, India" \
        --geodata data/geodata.sqlite --ephemeris ephe --caption --out jammu.svg \
        --dasha md-ad-pd --dasha-year 365.25 --dasha-precision day --dasha-zone UTC --dasha-out jammu_dasha.txt
# SVG to stdout, table to a file: the file is written first, stdout last
python -m vedic_chart.app ... --out - --dasha md --dasha-year 365.256363 --dasha-out d.txt > chart.svg
# rejected
python -m vedic_chart.app ... --out a.svg --dasha-year 365.25                              # 2: orphan
python -m vedic_chart.app ... --caption --dasha --dasha-year 365.25 --dasha-out d.txt      # 2: renderer flag without --out
python -m vedic_chart.app ... --out a.txt --dasha --dasha-year 365.25 --dasha-out a.txt    # 5: same file
python -m vedic_chart.app ... --out - --dasha --dasha-year 365.25 --dasha-out -            # 2: two stdouts
```

## 7. Tests

Self-contained (fixture database, explicit Jammu `ResolvedLocation`, `ephe/`); no production
database, network or clock.

- **Rows:** counts 9/90/819; pre-order; timestamps and nominal offsets equal the periods' by
  value (lossless); flags reproduce `periods_at_birth()` and `active_periods_at(birth_utc)` for
  Jalandhar, Jammu and both divergence inputs (the N/Q split of §5); `depth` `True`, `1.0`, `0`,
  `4`, `"2"` rejected with the stated types; `precision` `1`, `"days"` rejected; rows frozen.
- **Text, representative goldens only:** `tests/fixtures/dasha/jalandhar_md_ad_365256363_second_kolkata.txt`
  and `tests/fixtures/dasha/jammu_md_36525_day_kolkata.txt` — **two new files in a new
  subdirectory `tests/fixtures/dasha/`**; every existing fixture and SVG golden is untouched.
- **Text, parameterised semantics** over both births × both conventions × three depths × two
  precisions: at second precision every printed timestamp, parsed back with its offset, is ≤ the
  true boundary and > boundary − 1 s; at day precision every printed date equals
  `boundary.astimezone(zone).date()` (no sub-day assertion); every printed offset equals
  `utcoffset()` at that instant, and offsets with seconds are printed with seconds — a birth in
  1890 in Jalandhar (within ephemeris coverage) rendered in Asia/Kolkata prints `+05:21:10` for
  its pre-1906 boundaries; a Europe/London rendering of a synthetic timeline with a boundary inside
  the 2023-10-29 fall-back hour prints the repeated hour with `+01:00` then `+00:00`; the
  day-precision warning appears exactly when requested; the balance line matches the §3(c)
  integer rule for both births and for `nextafter(40.0, 0)` (`0.000000000`); the header carries no
  pada; unknown and malformed zone keys raise `ValueError` chained from `ZoneInfoNotFoundError` /
  `ValueError`; conversion overflow is tested without requiring an impossible core timeline: near
  `datetime.max` with a **positive-offset** zone (e.g. `Asia/Kolkata`) and near `datetime.min`
  with a **negative-offset** zone (e.g. `America/Los_Angeles`), using either a valid core timeline
  whose endpoints approach the limit (a birth in year 9870–9879 or in the first decades of year 1
  that the core still accepts) or a clearly labelled synthetic presentation fixture (a
  `VimshottariTimeline` built by the test with endpoints placed at the limit); in each case
  `DashaRangeError` is raised from the conversion and no `OverflowError` escapes.
- **Pipeline:** `render_birth_chart` byte-identical to every existing SVG golden and rejects
  invalid options before any resource use (spy on the resolver); `compute_dasha` equals the
  adapter on its own chart and validates request/config/year before resource use;
  `render_chart_and_dasha` shares one chart (`d1.source is chart`, adapter cross-check), resolves
  once and opens the ephemeris once, and its SVG equals `render_birth_chart`'s for the same
  options; `year` required; a bad `year` never opens the database.
- **CLI, all seven output combinations** succeed with the expected bytes (SVG = unchanged goldens;
  table = `render_dasha_text` on the same timeline), and the write order is asserted with a spy
  (file(s) before stdout; SVG before daśā when both are files; daśā file before SVG stdout).
  Usage errors of §6 → 2 with empty stdout, including explicitly supplied renderer flags in
  daśā-only mode and explicit `--dasha-precision`/`--dasha-zone` without `--dasha` (while their
  defaults never trigger the error). Equal or `samefile` destinations → 5 before any calculation
  (spy). `--force` replacing both files. The daśā destination refused as an input resource,
  symlink, non-regular file, or existing without `--force`. **Partial failures:** an injected
  failure of the second file write keeps the first file intact and correct, exits 5, and stderr
  carries the original error followed by the "is kept" note; a closed stdout pipe for the SVG
  after the daśā file was written keeps the file, prints "stdout closed by reader" once and the
  note, and `run` returns `(5, True)`; the same for a closed pipe on a stdout table after an SVG
  file. `--dasha-precision day` prints date-only period rows with the warning while the Birth
  line keeps seconds and offset; injected unexpected `ValueError` and `OverflowError` from
  `render_dasha_text` and an unencodable table (lone surrogate) → 1 with empty stdout, the
  diagnostic, a traceback only with `--verbose`, and in combined mode no output file created (and,
  with `--force` on pre-existing files, none modified), while an injected `DashaRangeError` from
  the same call stays 2; `--dasha-zone UTC` and an
  invalid zone; `--verbose` lines; `DashaRangeError` from an injected core error → 2; an injected
  unrelated `ValueError` inside the pipeline → 1, not 2.
- **Boundaries:** updated AST tests (§2: counts 4/4, allow-lists, public names); `pyproject.toml`
  unchanged; no dependency added; frozen layers, existing fixtures and SVG goldens unchanged.

## 8. Changed-file scope (manifest)

New: `src/vedic_chart/dasha/table.py`; `tests/test_dasha_table.py`; `tests/test_app_dasha.py`;
`tests/fixtures/dasha/jalandhar_md_ad_365256363_second_kolkata.txt`;
`tests/fixtures/dasha/jammu_md_36525_day_kolkata.txt`; `docs/LAYER13_DASHA_OUTPUT_SPEC.md`.
Modified: `src/vedic_chart/dasha/__init__.py`; `src/vedic_chart/app/pipeline.py`;
`src/vedic_chart/app/cli.py`; `src/vedic_chart/app/__init__.py`; `tests/test_app_boundaries.py`;
`tests/test_dasha_boundaries.py`; `README.md` (a "Daśā" subsection with production-vs-fixture
wording as in Layer 11). Untouched: every module of Layers 1–10, `vimshottari.py`,
`from_chart.py`, every existing file under `tests/fixtures/`, the SVG goldens, `pyproject.toml`,
dependencies, and the Layer 11 and Layer 12 specifications.

## 9. Record of external validation status (factual)

Layer 12 was compared with deva.guru on 2026-09-11/12 using its login-free page. Settings there:
Viṁśottarī, Starting from Mo, Normal, Default order, Tribhāgi off, Mean Sidereal, **True Citrā**
ayanāṃśa; the Lahiri option could not be selected in the owner's session either, for a reason
not established. Structure and birth chains agreed for Jalandhar and Jammu. Using the Swiss
`SIDM_TRUE_CITRA` Moon as an **independently calculated comparison input** (not the site's
verified exact Moon), boundaries read to the second and interpreted as IST differed from ours as
follows: **committed core** MD/AD/PD boundaries −19.9 … −18.1 s (Jalandhar, 12 boundaries) and
−8.3 … −3.5 s (Jammu, 10); **scratch-derived level-4** boundaries, which the core does not
produce, −20.3 … −17.9 s (48) and −8.0 … −3.4 s (40). The nearly constant offsets are consistent
with a small input/anchor difference and are not attributed to a single cause; measured drift
+0.0012 and −0.024 s/yr (±≈0.01 s/yr) is consistent with a 365.256363-day year to about 3×10⁻⁷ d,
and `FIXED_365_25` (−550 s/yr) is excluded. Displayed-Moon comparisons are limited by 1″
resolution (10 519 s/″ Jalandhar, 4 602 s/″ Jammu; the display rounding rule is unknown). Their
printed ayanāṃśa and Moon differences (+48.6″/+34.0″ vs −37.1″/−48.7″) are unreconciled. This is a
**partial** validation. **Lahiri absolute-date validation remains pending; no exact deva.guru
compatibility is claimed.** This layer changes nothing the pending comparison would test.

## 10. Decisions

Closed in v0.2: R1–R5 (header). Closed at the closing revision: the content-generation error
policy (§6) and the always-second-precision `Birth` header (§3). None remain open.

## 11. Validation record (v1.0)

**Test suite (previous run, recorded after the closing revision; not re-run for this
promotion).** Full suite on the owner's machine (project `.venv`, committed fixture database,
explicit Jammu `ResolvedLocation`, `ephe/`; no production database, network or clock in the
tests): **2189 passed, 0 failed, 0 skipped** — 1914 at Layer 12 v1.0 (`ca73515`) plus 275
Layer 13 tests (`tests/test_dasha_table.py`, `tests/test_app_dasha.py`, and the updated
boundary tests). The two text goldens under `tests/fixtures/dasha/` were generated by the
implementation and are reproduced byte for byte.

**Verified by tests and by the implementation review.**
- *Single assembly:* `_assemble_once` is the only assembly step; `render_birth_chart` is
  byte-identical to Layer 11 v1.0 on every SVG golden and keeps its validation order (invalid
  renderer options rejected before any resource use); `compute_dasha` equals the adapter on its own
  chart and checks `year` before the database opens; `render_chart_and_dasha` resolves once, opens
  the ephemeris once, and its SVG and timeline derive from one `BirthChart` (`d1.source is
  chart`, adapter cross-check).
- *Output modes:* all seven combinations of SVG/daśā to file/stdout succeed with the expected
  bytes, with the write order files first (SVG before daśā), stdout last; every §6 usage error
  exits 2 with empty stdout, including explicitly supplied renderer flags in daśā-only mode and
  explicit `--dasha-precision`/`--dasha-zone` orphans (defaults never trigger it).
- *Output protections:* both destinations pre-checked with the Layer 11 §8.2 rules and
  `--force` for both; equal or `samefile` destinations refused (5) before any calculation; the
  daśā destination refused as an input resource, symlink, non-regular file or existing file
  without `--force`; partial failures keep the first output and report it, including a broken
  stdout pipe for the SVG after a successful daśā file (`(5, True)`).
- *Content-generation failures:* all content is generated before any write; `DashaRangeError`
  from the pipeline or from `render_dasha_text` → 2; any other exception from `render_dasha_text`
  or the UTF-8 encoding (injected `ValueError`, `OverflowError`, `UnicodeEncodeError`) → 1 with a
  one-line diagnostic, a traceback only with `--verbose`, empty stdout, and no output file created
  or modified (checked with and without `--force` on pre-existing files); no internal error is
  reinterpreted as an input error and none escapes `run`.
- *Presentation:* rows are lossless (UTC microsecond timestamps and exact `Fraction` offsets);
  the birth markers are two separate columns — `N` from `periods_at_birth()`, `Q` from
  `active_periods_at(birth_utc)` — and the Layer 12 divergence inputs `nextafter(40.0, 0)` and
  `3.666666666666666` show the documented `N`/`Q` split; timestamps are truncated to the second
  (never later than the true boundary) with the zone's exact UTC offset, seconds included
  (`+05:21:10` for pre-1906 Asia/Kolkata; `+01:00` then `+00:00` across the 2023-10-29
  Europe/London fall-back hour); the `Birth` header line is always at second precision with its
  offset, whatever `--dasha-precision`; day precision prints date-only period rows with the
  warning line; the nominal balance decimal is produced by integer truncation to nine places;
  zone-conversion overflow near `datetime.max` (positive-offset zone) and `datetime.min`
  (negative-offset zone) raises `DashaRangeError` from clearly labelled synthetic presentation
  fixtures.
- *Import boundaries:* the updated AST tests enforce §2 (four `app` modules, four `dasha`
  modules, `zoneinfo` in `table.py` only, the widened allow-lists and public-name sets).

**Protected files unchanged.** `git diff HEAD` over `src/vedic_chart/dasha/vimshottari.py`,
`from_chart.py`, `src/vedic_chart/app/__main__.py`, every Layer 1–10 package, every existing file
under `tests/fixtures/` (all nine tracked fixtures and every SVG golden) and `pyproject.toml` is
empty; the only additions under `tests/fixtures/` are the two new text goldens in the new
`tests/fixtures/dasha/` directory. Dependencies declared by the project are unchanged.

**External validation.** Lahiri absolute-date validation against deva.guru remains **pending**
(§9); **no exact deva.guru compatibility is claimed.** This layer changes nothing the pending
comparison would test.

**Environment deviation (not a repository or dependency change).** During the build, `pyflakes`
3.4.0 was installed into the untracked `.venv` for a one-off lint and could not be removed from the
sandbox. `pyproject.toml` and the boundary tests' dependency pins are unchanged; the virtual
environment is not part of the repository. Cleanup is the owner's (`.venv/bin/pip uninstall
pyflakes`).
