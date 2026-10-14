# Layer 21 — Panchanga in the existing viewer

Status: DRAFT v0.1, implemented for local preview on 2026-10-14.
Baseline: `2afbc20` (Layer 20), initially clean. No staging, commit or deployment.

## Scope

Show the existing Layers 16–18 in the chart viewer, using the effective chart
instant and location. No calendar form, implicit current time, new endpoint,
calculation convention, dependency or chart renderer is introduced.

The panel contains the five elements at the chart time, previous and next
transition cells for the four angular elements, the Layer 16 sunrise window,
and the Layer 18 sunrise-to-sunrise day containing the instant. The latter's
civil date may precede the entered date. It is not a daily civil-midnight
calendar and does not select a different date or sunrise ordinal itself.

## Backend composition

`viewer.panchanga.panchanga_document(chart, ephemeris_path)` is the only new
composition adapter. The existing pipeline still assembles one BirthChart.
Under the same `ENGINE_LOCK`, after the pipeline session closes, this adapter
opens one `ephemeris_session` for `find_transitions`, `panchanga_from_chart`
and `panchanga_day_containing`. No engine calls can overlap other requests.
The instant classifications come from the chart path, including its Moon
placement. Transition current indices are checked against these values.

Layer 17 validates its supported range before evaluation. Its range failure
produces an unavailable panel while leaving the successful chart usable. A
Layer 18 range failure leaves the instant elements and transition information
available with an unavailable day. Polar cases preserve the four angular
elements and use the core's unavailable vara/day results. There is no fallback
weekday, timestamp, location, or rounded boundary. Internal search failures
follow the existing HTTP 500 `unexpected` path, with no partial document.

The adapter formats values without astronomy or boundary arithmetic. Core
datetime values travel losslessly as offset-bearing microsecond ISO strings.
Table display strings truncate to seconds and are labelled approximate.
Exact transition windows retain `(before, after]`: the new-side endpoint is
not claimed to be the true event instant. The core's UT1/model uncertainty
notes are carried verbatim. The frozen geometric Hindu sunrise convention
and high-latitude limitations remain explicit.

## Additive response

`transport.serialize(..., panchanga=None)` preserves the former result when
omitted; a provided dictionary is appended as key 15, after `overlay`. The
server supplies it on every ordinary `/api/chart` response, including transit
requests. The four-key request and parent schema `/2` remain unchanged. The
nested schema is `vedic_chart.panchanga/1`.

The block contains `status`, `instant` (UTC, local, display), `timezone_id`,
display notes and, when available:

- `elements`: tithi, nakshatra, yoga and karana in UI order, each with core
  name/index/number, contextual detail and previous/next transition windows.
- `vara`: name and English weekday, or null when the sunrise window is unavailable.
- `sunrise`: available previous/next instants, or an unavailable reason.
- `day`: canonical opening/closing, their `located_by`, civil date, ordinal,
  vara, opening elements, ordered `transitions` with placement labels,
  separate `cells_at_closing`, and the core's `unordered_pairs`. Unavailable
  days carry reasons and the bounded-neighbour qualification.
- The core's calculation and sunrise convention strings.

Membership and placement are never recomputed by this layer. Day listings
retain core order and `after`-endpoint interval membership. Closing cells
remain separate; opening-reflected changes are labelled, not applied twice.
Coincident cross-kind windows carry the core's unproven-order qualification.

## Viewer behaviour

The panel is built from the natal response inside the existing detached result
fragment. A successful Generate replaces it together with the chart. Existing
stale/loading/error/cancel semantics apply to the whole result. Transit
responses and style switches cannot replace the natal panel. No new fetch,
clock, JavaScript date conversion or numerical calculation is added.

Birth-input assumptions are shown on the Panchanga heading. Missing old-server
blocks and malformed panel data produce an explanatory section without
breaking the chart. Native details/summary controls expose daily information
and exact windows. Tables scroll within labelled, keyboard-focusable wrappers
at narrow widths; scoped CSS does not target chart SVG contents.

## Boundary amendments

The viewer gains a fifth Python module. Only `viewer/panchanga.py` may import
the public Panchanga package and `astronomy.positions.ephemeris_session`;
all other astronomy access remains forbidden. Its project import names are
enumerated in the viewer boundary test. It has no arithmetic or clock exemption.
The Panchanga boundary test admits this one public-surface consumer and still
forbids every calculation package from depending on it.

The exact server lock-body set gains `panchanga_document`. The HTTP extended
key-list test and acceptance tail check gain `panchanga`. Existing default
serializer goldens and every calculation/renderer fixture are preserved.

## Verification

Native baseline (Darwin arm64, Python 3.11.16, native pyswisseph): 5514 passed,
12 failed, 1 deselected. The failures are the previously documented eight
daśā-from-chart and four daśā/viewer golden cases. The one deselected test is
`test_app_cli.py::test_a_cleanup_failure_is_reported_after_the_original_error`:
its global os.write/os.unlink monkeypatch stalls the native pytest runner;
this is the existing macOS qualification, not a production-code exception.
Pure-Python pytest was reused from the existing session environment; nothing
was installed.

Updated native run: **5554 passed, 12 failed, 1 deselected**. The twelve
failure identities match the measured baseline exactly; the same cleanup test
was excluded from both runs. The four focused modules (viewer Panchanga,
viewer boundaries, Panchanga boundaries and viewer South Indian integration)
passed **222 tests**. No assertion or golden was relaxed to fit this environment.

Local browser verification used the real native server with the production
geodata database in the Codex in-app browser. Verified:

- Date-only 2001-02-04 defaults to noon at Jammu with the assumption badge.
- Selecting Jammu and supplying 10:45 replaces the panel with Ravivara,
  Shukla Ekadashi, Mrigashira pada 1, Indra and Vanija, with no assumption badge.
- Editing inputs leaves the old panel intact and shows the existing stale
  banner until Generate succeeds.
- Both disclosure controls open by keyboard. The daily section displays six
  transitions and the canonical sunrise interval; the exact section displays
  offset-bearing microsecond cells and the core uncertainty notes.
- A real transit request for 2026-10-08 14:30 and a switch to Both leave the
  complete natal Panchanga text unchanged.
- At a 375 px viewport the document scroll width remains 375 px and the
  560 px tables scroll inside 309 px focusable wrappers. The viewport override
  was reset afterwards. No browser console error was observed.

This was a focused UI verification, not a run of the full Playwright acceptance
script, a pixel-equivalence claim, or a new external almanac comparison.
The script's additive response-key expectation was updated; the original
calculation and renderer fixtures remain unchanged.

`test_viewer_panchanga.py` compares same-environment core values for Jalandhar,
Jammu, a pre-sunrise birth, historical Kolkata seconds offsets and London DST;
checks polar and range-edge results; exercises all boundary-placement labels;
and verifies one chart, locking, effective defaults, failure atomicity and no
extra browser request. Frozen calculation files are checked against the baseline.
