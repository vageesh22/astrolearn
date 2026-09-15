# Layer 15 — Viewer input flow: mandatory date, defaults, offline birthplace autocomplete, implicit daśā convention

**Status: SPECIFICATION v1.0 (promoted 2026-09-15). Implemented against v0.3/v0.3a; §15 is the
validation record of the committed snapshot. It supersedes the Layer 14 sections listed in §12;
`docs/LAYER14_INTERACTIVE_VIEWER_SPEC.md` v1.0 remains the historical record of Layer 14.**

Builds on Layers 1–14. Where it conflicts with `docs/LAYER14_INTERACTIVE_VIEWER_SPEC.md`, the
sections named in §12 are **superseded on implementation**; every other Layer 14 rule (server
contract, security, treegrid, transport losslessness, acceptance discipline) stays in force.

**Validation status carried forward.** Independent, automated absolute-date validation of the
frozen Lahiri convention against deva.guru remains pending (Layer 12 §2, §13; Layer 14
preamble). §11 records the owner's manual comparison as **owner-reported agreement** and nothing
more. No exact-compatibility claim is made.

## 1. Goal, scope and non-goals

**Goal.** A simpler input flow: the birth date is the only mandatory field. Time and birthplace
are optional; a blank time means 12:00 noon and a blank birthplace means one configured default
city, each clearly labelled as assumed wherever it influences a result. The birthplace field
offers offline autocomplete suggestions (city, region, country) and the calculation runs from
the **exact selected record**, never from a second name resolution. The daśā year convention
is no longer chosen on the page: the viewer supplies `FIXED_365_256363` itself and states it.

**In scope.** The viewer page and transport (schema `vedic_chart.viewer/2`), one new
suggestions endpoint, two small read-only additions to the Layer 2 offline resolver, one new
public entry point in Layer 11, the default-city configuration, tests, and the acceptance
procedure. Requires two additive existing-contract changes (§9), C1 and C2, approved in
principle by the owner with C2 revised in v0.2.

**Out of scope.** Any "known/unknown" switch or an "unknown" option the user must pick; any
inference of the default city from browser, IP, locale or computer location; any change to the
CLI (`python -m vedic_chart.app` keeps its explicit `--dasha-year`); any change to the Layer 12
core, Layer 13 table, Layer 10 renderer, Layer 1 request model or Layer 3 time handling; online
geocoding; storing births; rectification or any astrology feature.

## 2. Input rules

| Field | Required | Blank means | Supplied value | Invalid value |
|---|---|---|---|---|
| Date | **yes** | — (blocked client-side; 400 `input` server-side) | `YYYY-MM-DD`, ASCII digits, then Layer 1 calendar validation | error |
| Time | no | **12:00:00 assumed** (local wall time at the effective place) | `HH:MM` or `HH:MM:SS`, ASCII digits, then Layer 1 and Layer 3 validation | error, **never** a fallback to noon |
| Birthplace | no | **the default record assumed** — Jammu, Jammu and Kashmir, India (GeoNames 1269321, §4), or the `--default-place-id` override — with its time zone | a suggestion **selected** from the offline list (carries a GeoNames id) | see below |
| Daśā year | — (no control) | `FIXED_365_256363` always | — | — |

Rules that follow from the brief and are binding:

1. A supplied time is interpreted in the time zone of the **effective** place — the selected
   record, or the default city when the birthplace is blank. This is exactly Layer 3's
   existing behaviour (wall time + place zone → instant); nothing new is computed.
2. Both blank → 12:00:00 at the default record, both labelled assumed.
3. A **non-blank birthplace text without a valid selection** is neither resolved nor
   defaulted: the page prompts *"Select a suggestion from the list, or clear the field to use
   the default birthplace."*, Generate is blocked, and the server independently answers 400
   `place_selection_required` if such a request arrives.
4. Editing the birthplace text after a selection **invalidates** the selection (the hidden
   identifier is cleared on every `input` event); only choosing a suggestion again restores one.
5. An invalid supplied value (a malformed or impossible date or time, a DST-nonexistent or
   ambiguous local time reported by Layer 3, an unknown or malformed place identifier) is an
   error with the existing `kind`s; the viewer never substitutes a default for an invalid value.
6. Whitespace-only time or birthplace text counts as blank (`str.strip()` on the server, the
   same rule in the page).

**Inline note** under the form (static text, filled with the configured city at page load from
the `/` document's `<meta name="viewer-default-place">`): *"Date is required. Leave the time
blank to assume 12:00 noon. Leave the birthplace blank to assume Jammu, Jammu and Kashmir,
India; its time zone applies. A supplied time is read in the birthplace's time zone."* (The
city text is filled from the meta tag, so an override is reflected automatically.)

## 3. Assumed values in results

- The response carries an explicit `assumptions` block (§7.3). The page never displays an
  assumed value in the same form as a supplied one:
  - results heading badge **"Uses assumed birth details"** (a `<span class="v-badge"
    role="status">`) whenever `assumptions.any` is true; the D1 chart heading carries the same
    label beside it (*"D1 chart — uses assumed birth details"*), and the daśā heading likewise;
  - the "Birth details" block lists every effective value with its source: *Time:* `12:00:00
    (assumed — no time was supplied)`; *Birthplace:* `Jammu, Jammu and Kashmir, India (assumed —
    the configured default; no birthplace was supplied)`; *Date:* always `supplied`;
  - the results header line reads *"Computed from 1995-03-21, assumed 12:00:00, assumed
    Jammu, Jammu and Kashmir, India"* rather than presenting the values as the birth;
  - the stale-inputs banner (Layer 14 §10.3) compares the four submitted strings, so clearing
    a field after a result marks the result stale exactly as editing does.
- The SVG document itself is **unchanged** (Layer 10 renderer untouched; caption off); the
  label lives on the page around the chart (decision E5, approved: page-level labels only; the
  SVG stays byte-comparable to the CLI).
- Nothing about an assumption is stored anywhere (Layer 14 §4.3, §11.4 unchanged).

## 4. Default birthplace: the verified Jammu record, with an optional override

### 4.1 The verified default record (decision E1, owner's choice)

The default birthplace is **Jammu, Jammu and Kashmir, India**, identified by its GeoNames
record — not by name. Verified by primary key on the production database `data/geodata.sqlite`
(SHA-256 `8afad22b…b7a4`), on the Mac session VM and again on the hash-identical cloud copy:

| Field | Value in `places` where `geoname_id = 1269321` |
|---|---|
| `geoname_id` | **1269321** (exactly one row) |
| `name` / `ascii_name` | Jammu / Jammu |
| `admin1` (`IN.12`) | Jammu and Kashmir |
| `country` (`IN`) | India |
| `latitude`, `longitude` | **32.73528**, **74.86167** (north, east) |
| `feature_class` / `feature_code` | P / PPLA |
| `population` | 576198 |
| `geonames_tz` (informational column) | Asia/Kolkata |
| `timezonefinder` lookup at those coordinates (the contract's zone source) | **Asia/Kolkata** |
| `resolve_with_details("Jammu")` today | chooses this same record (8 candidates, 7 materially different, dominance applied) |

These match the previously accepted values (1269321; 32.73528 N, 74.86167 E; Asia/Kolkata).
The constant is recorded in the viewer as `DEFAULT_PLACE_ID = 1269321` with a comment naming
the verification above; the coordinates and zone are **never** hard-coded — they are read from
the configured database at start-up (§4.2). **The configured database is authoritative**: what
start-up validates is that the effective identifier exists there and yields a valid
`ResolvedLocation` with a land time zone — not that its contents equal the values above. Those
values are kept here as **reference evidence** of the production record at the time of
writing; a database whose row 1269321 carried different coordinates would be used as it is,
which is the intended behaviour for a rebuilt database (v0.3 correction).

### 4.2 Start-up behaviour (decision E2)

- `--default-place-id <integer>` is an **optional** override of `python -m vedic_chart.viewer`;
  when omitted the viewer uses `DEFAULT_PLACE_ID`. Users do not have to supply anything beyond
  `--geodata` and `--ephemeris` to launch. The flag value must match `[0-9]{1,12}` (argparse
  error, exit 2, otherwise).
- At start-up (`ViewerServer.create`, between the metadata read and the token) the **effective**
  identifier — the override or the built-in default — is looked up with the new Layer 2 record
  lookup (C1, §9). A record that is not in the configured database, or whose coordinates yield
  no land time zone (`TimezoneLookupError`), or that fails `ResolvedLocation` validation, is a
  `ConfigurationError`: `error: the default birthplace record <id> is not available in
  <geodata path>: <reason>` → **exit 4 before binding**. There is no fallback to another record.
- The banner prints `default place: 1269321 = Jammu, Jammu and Kashmir, India (Asia/Kolkata)`
  and adds `(override)` when the flag was used; the page's `<meta
  name="viewer-default-place">` carries the same id and label for the inline note.
- The viewer **never** infers a default from the browser, the request, an IP address, the
  operating system locale or the computer's location. The only sources are the constant and
  the flag.
- The record is resolved to a `ResolvedLocation` (with its `PlaceCandidate`) once at start-up
  and reused for every defaulted request; no per-request database read for the default.
- Documentation: the README viewer subsection states the default (record 1269321, Jammu, Jammu
  and Kashmir, India) and the override flag; `--help` states both.

## 5. Birthplace autocomplete

### 5.1 Data and query (offline; Layer 2 addition C1)

Suggestions come from the same geodata database, read-only, through a new resolver method
`OfflineLocationResolver.suggest(text, *, limit) -> list[PlaceCandidate]`:

- **Argument validation (v0.3).** `text` must be a `str` (else `TypeError`); `limit` must be an
  `int` that is not a `bool`, with `1 <= limit <= 50` (else `TypeError`/`ValueError`). The same
  discipline applies to `record(geoname_id)`: an `int` that is not a `bool` and `>= 1`, else
  `TypeError`/`ValueError` — a `bool` is an `int` in Python and is rejected explicitly.
- `text` is split with the existing `split_query`: the part before the first comma is the
  **place prefix**, later parts are qualifiers. The prefix is normalised with the existing
  `normalize_name` (casefold, NFKD, marks stripped, whitespace collapsed), so *Jāl* and *jal*
  behave alike. **Server normalisation is authoritative**: the page does not reimplement it
  and decides only on raw length (§5.2).
- Minimum prefix length **2** code points after normalisation; shorter → `[]` (no error).
- **Upper bound of the range (v0.3, safe for every code point).** The scan is
  `norm_name >= :lo AND norm_name < :hi` with `lo` = the normalised prefix and `hi` computed
  as: take the prefix, drop every trailing U+10FFFF code point (they cannot be incremented),
  then increment the last remaining code point by one — skipping the surrogate block, so
  U+D7FF becomes U+E000 (a lone surrogate cannot be encoded for SQLite). If nothing remains
  (the prefix was entirely U+10FFFF), the upper bound is omitted and the scan is
  `norm_name >= :lo` alone, which is still correct because nothing sorts after it. Both
  values are **bound parameters**; no SQL is built from user text.
- The query does its work **inside SQLite** (v0.3, after measurement): one `SELECT … FROM
  place_names JOIN places LEFT JOIN countries LEFT JOIN admin1 LEFT JOIN admin2 WHERE
  <range> [AND <qualifier> …] GROUP BY p.geoname_id ORDER BY p.population DESC, exact DESC,
  p.name ASC, p.geoname_id ASC LIMIT :limit`, where `exact = MAX(pn.norm_name = :lo)`. The
  index `idx_place_names_norm` drives the range; grouping deduplicates the several names of a
  place; qualifier filtering and deduplication therefore happen **before** the limit, and
  `geoname_id` is the final deterministic tie-breaker. No new index, no schema change, no
  rebuild.
- **Comma qualifiers filter** (decision E4, approved): every part after the first comma is
  normalised and must match one of the row's qualifier targets — its country name, a country
  alias (`country_aliases`), its admin1 or its admin2 name — as a full-name match exactly as
  resolution applies it today, expressed in SQL as one parameterised predicate per qualifier:
  `(:q IN (c.norm_name, a1.norm_name, a2.norm_name) OR p.country_code IN (SELECT country_code
  FROM country_aliases WHERE norm_alias = :q))`. *"Hyderabad, India"* lists only the Indian
  records, *"Hyderabad, Pakistan"* only the Pakistani one, *"Delhi, IN"* works through the
  alias (and so does *"Hyderabad, Pak"*, because `pak` is Pakistan's ISO-3 alias in
  `country_aliases`); an incomplete qualifier that matches nothing, such as *"Hyderabad, Pa"*,
  lists nothing (an empty list, not an error).
- **Ordering (v0.3 revision of E3, with evidence).** Population descending first, then exact
  normalised-name match, then name, then `geoname_id`. The approved "exact-name-first" order
  was measured on the production database and rejected: it puts population-0 hamlets named
  *Jal* and *Lo* above Jalandhar and London, and *Ma* above Madrid. With population first the
  measured top results are Jalandhar for *jal*, London for *lo*, Jammu for *jammu*, Chennai
  (alias *Madras*) / Madrid / Mashhad for *ma*. Approved by the owner as a revision to E3
  (§14).
- **Which `matched_name` is returned (v0.3).** For each place the exact-match name if one of
  its names equals the prefix, otherwise the lexicographically smallest of its names that
  match the prefix (`MIN(pn.original)` over the group) — deterministic. Two labels are
  produced **by Layer 2** (`OfflineLocationResolver.candidate_label` and
  `suggestion_label`, both public static methods): `label` = `name, admin1, country`, and
  `display_label` = `label` plus ` (matched: <matched_name>)` only when
  `normalize_name(matched_name) != normalize_name(name)`. The page shows `display_label` in
  the list and writes `label` into the field on selection; it never compares names itself
  (implementation note, v0.3).
- **Measured on the production database** (150 712 320 B, 786 552 places; cloud x86_64 copy,
  hash-identical; SQLite 3, one connection, cold cache): two-character prefixes *ja* 82 ms,
  *ma* 239 ms, *sa* 188 ms, *ch* 179 ms, *ku* 80 ms, *sh* 57 ms, *lo* 28 ms, *ne* 20 ms;
  three-character *jal* 9 ms, *jam* 17 ms, *ab* 7 ms; qualified *san, united states* 51 ms,
  *hyderabad, india* 0.3 ms, *delhi, in* 0.4 ms. The Python-side variant (fetching up to
  38 696 rows and ranking in Python) measured 225–503 ms for the same prefixes, which is why
  the work is done in SQL. The Mac session VM figures are recorded at acceptance (§13).
- `PlaceCandidate.timezone_id` stays `None` in suggestions (the existing documented meaning:
  "not resolved yet"). The time zone is looked up only for the record actually used (§5.3).

### 5.2 Endpoint and page behaviour

- `POST /api/places` with `{"q": "<text>"}` (≤ 256 bytes body; every Layer 14 §11.3 check —
  Host, Origin/Sec-Fetch-Site, token, Content-Length, Content-Type — applies unchanged; no
  query string, keeping the "the page never sends one" rule). Response:
  `{"schema": "vedic_chart.viewer/2", "q": "<text as received>", "suggestions": [{"geoname_id":
  1268782, "label": "Jalandhar, Punjab, India", "name": "Jalandhar", "admin1_name": "Punjab",
  "country_name": "India", "population": 868929, "matched_name": "Jalandhar"}, …]}`.
  `label` is built server-side by the same rule as `ResolvedLocation.canonical_name`
  (`name, admin1, country`, omitting missing parts). Route label `api_places` is added to the
  log vocabulary (§11.3 item 5).
- The birthplace input becomes an ARIA **combobox**: `role="combobox"`, `aria-autocomplete=
  "list"`, `aria-expanded`, `aria-controls="place-listbox"` (valid here because the listbox
  element is always present, empty when closed — unlike the treegrid rows, D16),
  `aria-activedescendant` for the highlighted option; the list is `<ul role="listbox">` of
  `<li role="option">` showing the label. Keyboard: `ArrowDown`/`ArrowUp` move the highlight
  (wrapping), `Enter` selects the highlighted option, `Escape` closes the list without
  selecting, `Tab` closes without selecting, typing continues to filter. Pointer: click
  selects. A selection writes the label into the field and the `geoname_id` into a hidden
  input; the field shows a small "✓ selected" marker (text, not colour alone).
- Requests are sent after a **150 ms** debounce whenever the raw field text has at least 2
  code points before the first comma (a raw-length check only; the server's normalisation
  decides what matches, and a too-short normalised prefix simply returns `[]`). Each request
  carries a sequence number and its own `AbortController`.
- **Immediate invalidation (v0.3).** Every `input` event, every clear, and every option
  selection bumps the sequence number *at once* and aborts the in-flight controller — not only
  when the next debounced request starts. A response is applied only if its sequence number
  is still current **and** its echoed `q` equals the field's current text (both checks, as
  Layer 14 §10.2 does for charts). A delayed or out-of-order response therefore can never
  reopen an obsolete list: after a selection the list stays closed even if an older
  suggestion request completes afterwards.
- Any `input` event clears the hidden identifier and the marker (rule 4 of §2). On blur, a
  non-blank text without an identifier shows the inline prompt of rule 3 — except when the
  blur is caused by a pointer press on Generate or Cancel, where inserting the prompt would
  reflow the form under the pointer and swallow the press; the submission that follows shows
  the same prompt, blocks and focuses the field (implementation note, v0.3). A keyboard Tab
  shows it immediately.
- No suggestion is ever auto-selected: a single match is still shown as a list, and Enter
  with nothing highlighted does nothing. Nothing is chosen for the user.

### 5.3 Server-side validation of the identifier and the exact-record calculation

- The four `place_text`/`place_id` combinations (v0.3), decided after JSON parsing:

  | `place_text.strip()` | `place_id` | Result |
  |---|---|---|
  | blank | blank | the default record; `place_assumed: true` |
  | non-blank | blank | 400 `place_selection_required` |
  | blank | non-blank | 400 `input` — *inconsistent: an identifier without its label* |
  | non-blank | non-blank | the identifier is used (below); the submitted text must equal the record's server-generated label (§5.4), else 400 `input` — *the selected label does not match the record*; the viewer never substitutes another record |

- `place_id`, when present, must be `re.fullmatch(r"[0-9]{1,12}")`; anything else → 400
  `input`. The label comparison is exact string equality against the label the server builds
  for the record (the page writes exactly that label into the field on selection, §5.2).
- The identifier is looked up with `OfflineLocationResolver.record(geoname_id)` (C1), which
  returns `(ResolvedLocation, PlaceCandidate)` for that primary key or raises
  `PlaceNotFoundError` → 404 `place_not_found` (an id that is not in this database is not a
  place the viewer can use). The time zone is obtained by the existing `tz_lookup` on the
  record's coordinates, exactly as `resolve_with_details` does today, so the zone contract and
  its `TimezoneLookupError`/`InvalidTimezoneError` behaviour are unchanged.
- The calculation then runs from that `ResolvedLocation` **without resolving any name**:
  the new Layer 11 entry point `render_chart_and_dasha_at(request, location, config, options,
  year)` (C2, §9) feeds the location through the pipeline's existing `_PreresolvedResolver`,
  so `assemble_chart` receives the record itself, one chart is assembled, and the identity
  assertion `chart.location is location` still holds. The request's `place_query` is set to
  the record's label (Layer 1 requires a non-blank string; it is informational only and is
  never resolved on this path).

### 5.4 How provenance reaches the response (no invented resolution decision)

Nothing on this path produces a `ResolutionDecision`, and none is fabricated. Provenance is
carried by three things the viewer already holds, each with a single origin:

1. **Which record and why** — the server knows whether the record came from the request's
   `place_id` (`source: "selected"`) or from the configured default (`source: "default"`, the
   start-up record). That is a fact about the request, decided in the effective-input step
   (§7.2), not a resolver judgement.
2. **What the record is** — the `PlaceCandidate` returned by `record(geoname_id)` (C1): id,
   name, admin1, country, feature code, population, coordinates. Serialised into
   `effective.place` exactly as Layer 14 serialises candidates today.
3. **What the chart was built from** — `LocatedChartAndDashaResult.location` (C2), which the
   pipeline asserts **is** `chart.location`. The response's `location` block is built from it,
   so the coordinates and zone shown are the ones the engine used.

The Layer 14 `resolution` block is therefore absent from schema `/2`, not emptied: there is no
dominance, no rival count and no candidate list to report, because no name was resolved.

## 6. Daśā convention on the page

- The year selector is removed. The server passes `YearConvention.FIXED_365_256363` to the
  pipeline for every request; `parse_request` no longer accepts a `year_convention` key (its
  presence is an unknown key → 400).
- Result details show **"Mean Sidereal year — 365.256363 days"** (the caption line and the
  daśā heading), and the transport's `timeline.year_convention` block gains
  `"display": "Mean Sidereal year — 365.256363 days"` next to the existing `label` and `days`.
- The Python APIs (`compute_dasha`, `render_chart_and_dasha`, `build_vimshottari`,
  `vimshottari_from_chart`) keep their explicit `year` parameter, and the CLI keeps
  `--dasha-year` as a required choice: those contracts are unchanged. The implicit choice is
  a viewer presentation decision only, recorded here.

## 7. Transport (schema `vedic_chart.viewer/2`)

### 7.1 Principles

Unchanged from Layer 14 §9.1: one calculation per request, lossless strings, no arithmetic or
dates in the browser, Python formats presentation once.

### 7.2 Request (`POST /api/chart`)

```json
{"date": "1995-03-21", "time": "", "place_text": "", "place_id": ""}
```

Exactly these four keys, all strings. **Schema `/2` is a viewer-only replacement of `/1`** (the
page is the only client; there is no dual-schema support, decision E10). A stale `/1`
request — one carrying `place_query` or `year_convention`, which a browser tab still running
the old `viewer.js` would send — is rejected with 400 and the dedicated kind `stale_schema`:
*"This page is out of date: reload it to continue."* Other unknown or missing keys → 400
`input`. `parse_request` (transport) does, in order (v0.3): strict UTF-8 decoding (BOM
rejected); JSON parsing with duplicate-key and NaN/Infinity rejection; **then** the
stale-schema check on the parsed object's keys (an undecodable or duplicate-keyed body is a
plain 400 `input` before any key is inspected); then the exact-four-keys and all-strings
checks; `date` regex then Layer 1; `time` — blank after strip
→ assumed `12:00:00`, else regex then Layer 1; `place_id` — blank → `None`, else the id regex;
`place_text` kept verbatim. The **effective-input construction** then happens in one server
function before the engine is called:

```
effective.time                 = supplied time     or  time(12, 0, 0)                        [time_assumed]
effective.location, .record    = record(place_id)  or  server.default_location, .default_record  [place_assumed]
                                 (place_id None and place_text.strip() != ""  →  400 place_selection_required)
request  = BirthChartRequest(birth_date, effective.time, place_query=effective.record label)
result   = render_chart_and_dasha_at(request, effective.location, config, RENDERER_OPTIONS, FIXED_365_256363)
           # -> LocatedChartAndDashaResult; result.location is result.chart.location
```

Layer 1's date/time validation, Layer 3's zone/DST validation and every engine behaviour are
preserved because the engine is called with a complete, ordinary request plus a
`ResolvedLocation` it already knows how to consume.

### 7.3 Response additions and replacements

- `request.submitted` = the four submitted strings verbatim; `request.normalized` = `date`,
  the **effective** `time` (`12:00:00` when assumed), `place_id` (the effective record's id as
  a string, including the default's), `place_label`.
- New `effective` block: `{"date": "…", "time": "12:00:00", "time_assumed": true,
  "place": {"geoname_id": 1269321, "label": "Jammu, Jammu and Kashmir, India", "name": "Jammu",
  "admin1_name": "Jammu and Kashmir", "country_name": "India", "feature_code": "PPLA",
  "population": 576198, "latitude": "32.73528", "longitude": "74.86167", "timezone_id":
  "Asia/Kolkata", "matched_name": null}, "place_assumed": true, "source": "default"}` (the
  example shows the built-in default; a selected record has `"source": "selected"`;
  `matched_name` is **always null** here — a matching alias is a suggestion-list fact, and a
  selection arrives as id + label — implementation note, v0.3).
- New `assumptions` block: `{"any": true, "time": true, "place": true, "labels": ["Time
  12:00:00 assumed: no time was supplied", "Birthplace Jammu, Jammu and Kashmir, India assumed:
  the configured default"]}` (labels are English sentences produced in Python so the page shows
  one wording everywhere).
- The Layer 14 `resolution` block (dominance, candidates, `ResolutionDecision`) is **removed**:
  no resolution happens on this path. `location` stays (it is the `ResolvedLocation` the
  chart carries).
- `timeline.year_convention.display` added (§6). `engine`, `birth`, `svg`, `timeline`,
  `birth_chain`, `rows` are unchanged in shape.
- Errors: new `kind`s `place_selection_required` (400) and `stale_schema` (400);
  `place_not_found` (404) now means "the identifier is not in this database".
  `ambiguous_place` can no longer occur on `/api/chart` and is removed from the viewer's
  vocabulary.

## 8. Page changes (Layer 14 §5, §6, §10 amended)

- Form: Date (required), Local wall time (optional, `placeholder="12:00 assumed if blank"`),
  Birthplace combobox (optional, `placeholder="<Default City> assumed if blank"`), the inline
  note of §2, Generate, Cancel. No radio group. `autocomplete="off"` kept. Neither optional
  field is pre-filled.
- Client-side validation: date syntax; time syntax when non-blank; birthplace text non-blank
  without identifier → prompt and block (rule 3). Nothing else is checked in the browser.
- Results: "Birth details" block (replaces "Resolved place") with the effective values and
  sources; the assumed-values labelling of §3; the dominance notice and candidate list are
  gone (nothing is chosen automatically any more — the only automatic value is the configured
  default, which is labelled as such).
- Everything else — treegrid, birth chains, microseconds toggle, stale banner, supersede/cancel,
  scroll hints, SVG insertion — is unchanged.

## 9. Required existing-contract changes (additive; C1 and C2 approved in principle, revised as below)

### C1 — Layer 2, `vedic_chart.location.offline.resolver` (additive)

Two new read-only methods on `OfflineLocationResolver`; nothing existing changes.

```python
def suggest(self, text: str, *, limit: int) -> list[PlaceCandidate]:
    """Prefix listing for autocomplete (section 5.1): indexed range scan on
    place_names(norm_name) over the normalised text before the first comma;
    comma qualifiers filter through the existing qualifier matching; rows are
    deduplicated by geoname_id and ordered exact-name-first, then population
    descending, then name; at most `limit`. timezone_id is None (not resolved).
    Never raises for an unmatched or too-short prefix: returns []."""

def record(self, geoname_id: int) -> tuple[ResolvedLocation, PlaceCandidate]:
    """One place by primary key (section 5.3): the row joined to admin1 and
    country exactly as _CANDIDATE_SQL joins them, the timezone from the existing
    tz_lookup on the row's coordinates, the ResolvedLocation built by the same
    _canonical_name rule as resolve_with_details. Raises PlaceNotFoundError when
    the id is not in this database; TimezoneLookupError / InvalidTimezoneError /
    InvalidCoordinateError propagate exactly as they do from resolve today."""
```

`resolve`, `search`, `resolve_with_details`, `RankingConfig`, `ResolutionDecision`, the
dominance rules, the schema and the database build are untouched. `search.py` gains the
range-scan SQL constant and reuses its row→`PlaceCandidate` conversion. Why in Layer 2: the
viewer may not import `sqlite3` (Layer 14 §3.4), and the existing `search` is an exact
normalised-name match, not a prefix listing.

### C2 — Layer 11, `vedic_chart.app.pipeline` (additive; revised in v0.2)

`ChartAndDashaResult` and its **non-optional** `resolution: ResolutionDecision` are preserved
exactly; no existing caller ever sees `None`. The exact-location path gets its own result type
with explicit provenance:

```python
@dataclass(frozen=True)
class LocatedChartAndDashaResult:
    """Both outputs of one assembly from a caller-supplied location.

    No ResolutionDecision exists on this path and none is invented: the caller
    chose the location (a geodata record, a configured default, a test
    fixture), and `location` records exactly what was handed in. The pipeline
    asserts by identity that `chart.location is location` and that
    `d1.source is chart`, so the drawing, the table and the provenance cannot
    describe different places or different births.
    """
    request: BirthChartRequest
    location: ResolvedLocation        # the object the caller supplied; identical to chart.location
    chart: BirthChart
    d1: D1Chart
    svg: str
    timeline: VimshottariTimeline


def render_chart_and_dasha_at(
    request: BirthChartRequest,
    location: ResolvedLocation,
    config: ChartConfig,
    options: NorthIndianOptions,
    year: YearConvention,
) -> LocatedChartAndDashaResult:
    """One assembly from an already-resolved location; no name resolution.

    Validation order (each before any resource is opened): request kind,
    location must be a ResolvedLocation (ValueError otherwise), config,
    options, year. The geodata database is NOT opened on this path. The
    ephemeris session is opened around assembly exactly as in _assemble_once;
    assemble_chart receives _PreresolvedResolver(request.place_query, location),
    so Layer 3's zone/DST validation, Layer 2's coordinate validation (already
    performed when the ResolvedLocation was built) and the engine's ephemeris
    coverage checks run unchanged. Then build_d1_chart, render_north_indian_svg,
    vimshottari_from_chart — the same three steps as render_chart_and_dasha —
    on the one chart."""
```

`_assemble_once` is not modified; a sibling `_assemble_at(request, location, config)` performs
the ephemeris-session assembly and the identity assertion (the same lines minus the resolver
step). `vedic_chart.app.__all__` gains `LocatedChartAndDashaResult` and
`render_chart_and_dasha_at` (ten names). The CLI does not use them.

**Where the contract is recorded (v0.3).** The frozen Layer 11 specification
(`docs/LAYER11_PUBLIC_ENTRY_POINT_SPEC.md`, v1.0) is **not** edited. This section is the
record of the additive API: for the two new names, Layer 15 §9 supersedes Layer 11 §9's
enumeration of the package's public surface, and Layer 13 §2's public-name list is likewise
extended by this section rather than by editing that document.

### Precise test amendments required by C1/C2 (all additive except the listed assertions)

| File | Amendment |
|---|---|
| `tests/test_app_boundaries.py::test_the_public_names_are_exactly_the_eight_specified` | rename to `…_ten_specified`; the asserted `__all__` list gains `"LocatedChartAndDashaResult"` and `"render_chart_and_dasha_at"` in sorted position. `CLI_PROJECT_IMPORTS` and the pipeline import-list tests need no change (the pipeline already imports `ResolvedLocation`; the CLI imports nothing new). |
| `tests/test_app_pipeline.py` | new tests appended: `render_chart_and_dasha_at` with the Jalandhar record gives `svg` and `dasha_rows` byte/value-identical to `render_chart_and_dasha("Jalandhar")`; `result.location is result.chart.location`; `d1.source is chart`; `LocatedChartAndDashaResult` has **no** `resolution` field (`dataclasses.fields` asserted); a non-`ResolvedLocation` location → `ValueError` before any file is opened; the geodata path is never opened on this path (monkeypatched `OfflineLocationResolver` asserts it is not constructed); and the existing `ChartAndDashaResult` retains its non-optional `resolution: ResolutionDecision` — its field type annotation is asserted unchanged and the query path still returns a `ResolutionDecision`. |
| `tests/test_offline_resolver.py` | new tests appended for `suggest` and `record` (§13); no existing assertion changes. |
| `tests/test_viewer_boundaries.py` | `PROJECT_IMPORTS["server.py"]["vedic_chart.app"]` becomes `{"ChartConfig", "ConfigurationError", "render_chart_and_dasha_at"}`; `PROJECT_IMPORTS["transport.py"]["vedic_chart.app"]` gains `"LocatedChartAndDashaResult"` (and drops `ChartAndDashaResult` if no longer referenced); the engine-lock body assertion becomes `{"render_chart_and_dasha_at", "dasha_rows"}`; the `aria-controls` textual prohibition is narrowed to "absent from every treegrid row" with exactly one occurrence permitted on the combobox; route labels gain `api_places`. Public viewer names unchanged. |
| `tests/test_dasha_boundaries.py` | no change (the `dasha` package's `__all__` and consumers are unchanged; the viewer still imports only the package surface). |
| `tests/test_app_cli.py`, `tests/test_app_dasha.py`, Layer 12/13 tests, goldens | no change. |

Not changed: Layer 1 (`BirthChartRequest` still requires a non-blank `place_query`; the record
label is passed), Layer 3, Layers 5–10, Layer 12, Layer 13, the CLI, `pyproject.toml`.

## 10. Proposed file/API scope (final for this pass)

```
src/vedic_chart/location/offline/resolver.py   MOD  C1: suggest(), record(); _canonical_name reused for labels
src/vedic_chart/location/offline/search.py     MOD  C1: SUGGEST_SQL (indexed range scan) + shared row→PlaceCandidate helper
src/vedic_chart/app/pipeline.py                MOD  C2: LocatedChartAndDashaResult, render_chart_and_dasha_at, _assemble_at
src/vedic_chart/app/__init__.py                MOD  C2: two re-exports (ten public names)
src/vedic_chart/viewer/server.py               MOD  DEFAULT_PLACE_ID = 1269321; optional --default-place-id; default record
                                                    validated at create(); POST /api/places (label api_places); effective-input
                                                    construction; FIXED_365_256363 fixed; kinds place_selection_required,
                                                    stale_schema; engine lock body = render_chart_and_dasha_at + dasha_rows
src/vedic_chart/viewer/transport.py            MOD  schema /2: four-key parse_request with stale-schema check; effective and
                                                    assumptions blocks; suggestions document; year display string
src/vedic_chart/viewer/static/viewer.html      MOD  form (no year group; combobox + listbox; hidden place_id; inline note;
                                                    default-place meta)
src/vedic_chart/viewer/static/viewer.css       MOD  combobox/listbox/badge styles (v- prefix; nothing inside #chart)
src/vedic_chart/viewer/static/viewer.js        MOD  combobox controller (debounce, sequence, abort, keyboard); assumed-value
                                                    rendering; stale banner over the four fields; stale_schema handling
tests/test_offline_resolver.py                 MOD  C1 tests appended
tests/test_app_pipeline.py                     MOD  C2 tests appended
tests/test_app_boundaries.py                   MOD  the one public-name assertion (ten names)
tests/test_viewer_transport.py                 MOD  schema /2 cases; golden regenerated on the Mac for the new shape
tests/test_viewer_server.py                    MOD  /api/places; defaults; place_selection_required; stale_schema; unknown id;
                                                    invalid time never falls back; default-record start-up validation; override
tests/test_viewer_boundaries.py                MOD  the amendments listed in §9
tests/fixtures/viewer/jalandhar_365256363.json MOD  regenerated for schema /2 (Mac)
tests/fixtures/viewer/divergence_su_mo.json    MOD  regenerated for schema /2 (platform-independent)
tests/fixtures/viewer/divergence_ke.json       MOD  regenerated for schema /2 (platform-independent)
tools/viewer/acceptance.py                     MOD  new checks (§13); year-radio steps removed; default-record checks
docs/LAYER15_VIEWER_INPUT_FLOW_SPEC.md         NEW  this document
README.md                                      MOD  viewer subsection: default record 1269321 and --default-place-id, defaults,
                                                    autocomplete, implicit convention; geocoder subsection: suggest()/record()
```

No new dependency; no `pyproject.toml` change; the CLI is untouched; Layer 14's
`ChartAndDashaResult`, `render_chart_and_dasha`, `compute_dasha` and `render_birth_chart`
are untouched.

## 11. Evidence and validation statements

- **Owner-reported agreement (recorded as such).** The owner reports having manually compared
  the viewer's Lahiri output with deva.guru and observed agreement. This is recorded here as an
  **owner-reported manual comparison** with these stated evidence limits: it was not produced
  by any automated run, its inputs, compared fields and precision are not on file, it is not
  reproducible from the repository, and it does **not** change the status of the pending
  independent automated validation nor support any exact-compatibility claim. No further
  detail is requested as a prerequisite for this work; the record stays owner-reported.
- Layer 14's accepted evidence (SVG byte equality with the CLI, table equality with Layer 13,
  the aarch64/x86_64 environment-dependent numerical difference with cause not established)
  carries forward unchanged; §13 adds what this layer must show on top.

## 12. Layer 14 sections superseded on implementation

§5 (birth input), §6 (calculation settings — year selector), §9.2–§9.3 (request/response
shapes, replaced by schema `/2`), §9.4 (`ambiguous_place` removed, `place_selection_required`
added), §10.1 (validation and error focus rules extended to the combobox), §11.3 item 2 (the
route table gains `POST /api/places`; the `aria-controls` prohibition of §8.2/§13.3 is narrowed
to the treegrid), §13.1–§13.4 and §14 (tests and acceptance, extended); §4.2 step 6's banner line
`year conventions: 365.25, 365.256363 (explicit per request)` becomes `dasha year convention:
365.256363 days (Mean Sidereal year, fixed by the viewer)` (v0.3). §1's "no
reduced-depth page mode", §7, §8, §11.1–§11.2, §11.4–§11.5, §12's HTTP-level rows and §16's
records remain exactly as written.

## 13. Tests and acceptance (additions)

**Repository tests.** Layer 2: `suggest` returns ≤ limit deduplicated candidates for `jal`
including Jalandhar; `jāl` equals `jal`; one-character prefix → empty; qualifier filtering
(`hyderabad, india` → only the Indian record) per E4; ordering exact-name-first then
population (v0.3 ordering: population first, exact match as tie-breaker, then name, then
`geoname_id` — asserted on a constructed tie); `suggest`/`record` reject a non-`str` text, a
`bool` or non-`int` limit/id, `limit` 0 and 51, and id 0; the range upper bound for a prefix
ending in U+10FFFF and one ending in U+D7FF (no exception, correct results); `matched_name` is
the exact-match name when present and otherwise the smallest matching alias; `record(1268782)`
equals the location `resolve_with_details("Jalandhar")` returns for the same coordinates and
zone; `record(999999999)` raises `PlaceNotFoundError`. Layer 11: as listed in §9. Transport:
the four-key request; `time: ""` → `12:00:00` and `assumptions.time`; `time: "25:00"` → 400
and **no** fallback; `time: " "` blank; the four `place_text`/`place_id` combinations of
§5.3 including the inconsistent blank-text-with-id and the label-mismatch cases; `place_id`
`"abc"`/`"-1"`/`"１２"` → 400; unknown id → 404; both blank → default record with both flags
and the labels; a `/1` body (`place_query`, `year_convention`) → 400 `stale_schema`, while
invalid UTF-8 and duplicate keys → 400 `input` even when they also carry `/1` keys; golden for
schema `/2`. Server (fixture database, which lacks Jammu, so every normal server test starts
the server with the explicit override `--default-place-id 1268782` = Jalandhar; the banner
shows `(override)`): `/api/places` obeys every Layer 14 §11.3 check (Host, Origin, token,
Content-Length, Content-Type, Transfer-Encoding), refuses bodies over 256 bytes, returns ≤ 10
suggestions with the echoed `q`, answers `[]` for a one-character prefix, and the engine lock
is **not** held around it (the lock body is unchanged); an explicitly supplied invalid time
(`"25:00"`, `"24:00"`, `"07:60"`) sent by a **direct API request** is 400 with no result —
the browser-side sanitising of native time inputs is a separate matter proven in acceptance;
and, separately, `ViewerServer.create` with the built-in default against the fixture database
(no override) raises `ConfigurationError` naming record 1269321, and `serve` exits 4 before
binding, as does `--default-place-id 1`. Boundary: new allowed names; `aria-controls` permitted
only on the combobox element; no clock, no arithmetic, no browser storage, as before.

**Acceptance script (`tools/viewer/acceptance.py`, extended).** `defaults_date_only`
(Jalandhar date only → 12:00:00 at the default record Jammu, badge and labels present, chart
still byte-equal to the CLI run with `--time 12:00 --place "Jammu, India"` — the query the
resolver resolves to record 1269321, verified as part of the check by comparing coordinates),
`defaults_time_only` (time supplied, place blank → default zone applies),
`defaults_place_only` (place selected, time blank → noon in that place's zone),
`combobox_keyboard` (type `Jam`, ArrowDown, Enter selects `Jammu, Jammu and Kashmir, India`,
Escape closes, Tab does not select; `aria-activedescendant` and `aria-expanded` states in the
accessibility snapshot), `combobox_stale` (**note, v0.3:** with immediate invalidation two suggestion
requests can never be in flight at once from this page — the edit aborts the older request
before the debounce sends the newer one — so the check proves that invariant with measured
page-clock timings and then exercises the late-response path: it holds the older response — the script delays the first response with a Playwright route so
the second answers first — and the list shows only the second; then type `Jal`, `Jam` within
the debounce window with the same outcome; then select an option and release a delayed older
response afterwards: the list stays closed), `combobox_pointer` (click selection writes the
label and id), `selection_invalidated_on_edit` (select, type a character, the id is cleared
and Generate is blocked with the prompt; the same body sent directly returns 400
`place_selection_required`), `invalid_time_no_fallback` (the native time input's own
behaviour is recorded — Chromium empties `25:00` — and the proof is a **direct API request**
with `"time": "25:00"` answered 400 `input`, never a noon result), `year_implicit` (no radio
group; caption shows *Mean Sidereal year — 365.256363 days*; rows equal the CLI with
`--dasha-year 365.256363`), plus every existing Layer 14 check re-run. Reference flows: the
two births as before (Jammu now selected through the combobox), the default-record flow with a
date only, and a run with `--default-place-id 1268782` (Jalandhar) to prove the override,
including start-up exit 4 for `--default-place-id 1`.

## 14. Decisions (final)

| # | Decision | Status |
|---|---|---|
| E1 | Default birthplace | **Decided: Jammu, Jammu and Kashmir, India — record 1269321**, verified by primary key (§4.1). |
| E2 | Configuration mechanism | **Decided: built-in `DEFAULT_PLACE_ID = 1269321` with an optional `--default-place-id` override**; the effective record is validated at start-up and a missing record fails clearly with exit 4 (§4.2). Users need only `--geodata` and `--ephemeris` to launch. |
| E3 | Suggestion limit 10, minimum prefix 2, ordering | Limit and minimum **approved**. Ordering: **approved revision (owner, 2026-09-15)** — population descending first, exact normalised-name match as the tie-breaker, then name, then `geoname_id` (§5.1); the earlier exact-name-first order was withdrawn on the measured evidence that it surfaced population-0 hamlets above Jalandhar and London. No further ordering changes are authorised. |
| E4 | Comma qualifiers filter suggestions | **Approved**, full-name qualifier matching as in resolution (§5.1). |
| E5 | Assumption labels on the page only; SVG unchanged | **Approved.** |
| E6 | Assumed time `12:00:00` | **Approved.** |
| E7 | C1 — Layer 2 `suggest`/`record`, additive | **Approved in principle**; final form in §9. |
| E8 | C2 — Layer 11 exact-location entry point | **Approved with revision**: separate `LocatedChartAndDashaResult` with explicit `location` provenance; `ChartAndDashaResult.resolution` stays non-optional; no existing caller changes (§9). |
| E9 | (withdrawn) further deva.guru comparison details | **Not requested**; §11 retains the owner-reported agreement with its stated limits. |
| E10 | Schema `/2` replaces `/1` outright; stale `/1` requests rejected with `stale_schema` | **Approved** (§7.2). |

No decision remains open for this pass. Implementation awaits the owner's explicit
instruction against this revision.

## 15. Validation record (v1.0, 2026-09-15)

**Snapshot.** The 21 Layer 15 paths of §10 as written to the repository folder and hash-verified
against the cloud source (the 21-line list `l15_cloud_sha256.txt`, all matching), with the
Jalandhar viewer golden then regenerated on the session VM (`tests/fixtures/viewer/
jalandhar_365256363.json` = `7b8998f2…`); the two divergence fixtures regenerated byte-identical
(`75d40d04…`, `ebf1bb58…`); Layer 12/13 goldens untouched (`b4614676…`, `10923c52…`). Final
per-file hashes: `~/l14accept/l15_final_mac_sha256.txt` on the session VM.

**Working tree vs `2c90e0d`** (Layers 14 and 15 together): 9 modified tracked paths —
`README.md`, `src/vedic_chart/app/__init__.py`, `src/vedic_chart/app/pipeline.py`,
`src/vedic_chart/location/offline/resolver.py`, `src/vedic_chart/location/offline/search.py`,
`tests/test_app_boundaries.py`, `tests/test_app_pipeline.py`, `tests/test_dasha_boundaries.py`,
`tests/test_offline_resolver.py` — and 16 untracked paths — `docs/LAYER14_INTERACTIVE_VIEWER_SPEC.md`,
`docs/LAYER15_VIEWER_INPUT_FLOW_SPEC.md`, `src/vedic_chart/viewer/{__init__,__main__,server,transport}.py`,
`src/vedic_chart/viewer/static/viewer.{css,html,js}`, `tests/fixtures/viewer/{divergence_ke,
divergence_su_mo,jalandhar_365256363}.json`, `tests/test_viewer_{boundaries,server,transport}.py`,
`tools/viewer/acceptance.py` — 25 in all; nothing staged. Every other tracked path (102 files)
is byte-identical to `2c90e0d`. The only edits to pre-existing files are the approved additive
APIs (C1 in `resolver.py`/`search.py`, C2 in `pipeline.py`/`__init__.py`; the sole removed lines
are one import statement, the `_canonical_name` signature that now delegates to
`candidate_label`, and the candidate-construction block that became `candidate_from_row`, all
behaviour-preserving), the D17/Layer 14–15 README subsections, and the boundary-test amendments
(D18 in `test_dasha_boundaries.py`; the ten-name assertion in `test_app_boundaries.py`; appended
tests in `test_app_pipeline.py` and `test_offline_resolver.py`).

**Tests.** Session VM (aarch64 Linux, the project's `.venv`, Python 3.10.12 — not native
macOS): full suite **2626 passed, 0 failed**. Cloud acceptance environment (x86_64, Python
3.11.15), same source: 2616 passed, 10 failed — the ten environment-dependent exact-value tests
of Layers 12–13 documented in Layer 14 §16.3 (with the Mac golden installed there, the two
viewer golden tests join them); no assertion and no frozen golden was relaxed.

**Browser acceptance (cloud, real server).** Production database, built-in Jammu default:
**31 passed, 0 failed, 0 skipped**. Fixture database with the explicit `--default-place-id
1268782` override: **30 passed, 1 skipped** (`Jammu` absent from the fixture). Both runs were
executed against source byte-identical to the committed snapshot except the Jalandhar viewer
golden, which the script does not read.

**Native macOS (owner's Terminal, `mac_verify_layer15.sh`).** Python **3.11.16, Darwin arm64**:
imports (ten `vedic_chart.app` names, `suggest`/`record`, the viewer's three names), `--help`,
a real launch with the banner's default-place line, `POST /api/places` for *Jam* including record
1269321, `POST /api/chart` date-only with `12:00:00` and the Jammu record assumed, and rejection
of `"time": "25:00"` with 400 all **passed**, and the server stopped with exit 130. **No full
native macOS test-suite run was performed and none is claimed.**

**Owner-reported hands-on acceptance.** The owner completed the native browser checks of the
new input flow — the birthplace dropdown and all four supplied/blank time/place combinations —
and reported no issues. Recorded as owner-reported hands-on acceptance.

**Standing statements.** The environment-dependent numerical differences of Layer 14 §16.3
remain documented and unexplained as to cause. Independent automated Lahiri absolute-date
validation remains pending; the owner's manual deva.guru comparison stays owner-reported with
the limits of §11. No exact-compatibility claim is made.

## 16. Change log

- **v1.0** (2026-09-15). Promoted by the owner after native hands-on acceptance; §15 validation
  record added; status line updated; no other text changed.
- **v0.3a** (2026-09-15). E3 ordering revision recorded as approved by the owner (§5.1, §14).
- **v0.3** (implementation approved). (1) `LocatedChartAndDashaResult` has no `resolution`
  field; the existing `ChartAndDashaResult` contract is asserted unchanged (§9, §13). (2)
  Start-up validates existence and a valid location/zone against the configured database as
  authoritative; production values kept as reference evidence; examples corrected to Jammu;
  fixture-database server tests use the explicit Jalandhar override and the unavailable
  default is tested separately (§4, §7.3, §13). (3) Parse order: UTF-8, JSON with duplicate
  rejection, then `stale_schema`; the four `place_text`/`place_id` combinations defined and
  tested; label agreement required; `suggest`/`record` argument validation incl. `bool` (§5,
  §7). (4) Safe Unicode upper bound; parameterised SQL; qualifier filtering and deduplication
  before the limit; `geoname_id` tie-breaker; `matched_name` rule; production-database
  measurements; SQL-side ranking; ordering revised with evidence (§5.1, E3). (5) Immediate
  invalidation of pending suggestion responses; out-of-order, selection-then-edit and
  pointer/keyboard tests; direct-API proof for invalid time (§5.2, §13). (6) Layer 11
  specification left unchanged with the contract recorded here; manifest by individual path
  (§9, §10).
- **v0.2.** Default birthplace verified and fixed to record 1269321 with an optional override
  and start-up validation (§4); E3–E6, E10 approved and folded into §2, §3, §5, §7; C2 revised
  to an additive `LocatedChartAndDashaResult` + `render_chart_and_dasha_at` preserving
  `ChartAndDashaResult.resolution` (§9); provenance path without an invented resolution
  decision (§5.4); stale `/1` requests rejected with `stale_schema` (§7.2); precise boundary-test
  amendments listed (§9); file scope finalised (§10); E9 withdrawn (§11).
- **v0.1.** Initial proposal.
