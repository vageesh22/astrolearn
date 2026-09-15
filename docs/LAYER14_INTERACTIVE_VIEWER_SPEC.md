# Layer 14 — Interactive D1 chart and Vimshottari daśā viewer

**Status: SPECIFICATION v1.0 (promoted 2026-09-15). This document is the historical record of
the Layer 14 implementation and its acceptance exactly as reviewed at the v0.5 closing revision;
§1–§16 are preserved unchanged. Layer 15 (`docs/LAYER15_VIEWER_INPUT_FLOW_SPEC.md`, v1.0)
supersedes the sections listed in §16.6; the Layer 14 files as committed carry the Layer 15
revisions, so the code on disk follows Layer 15 wherever the two differ.**

Builds on Layers 1–13 as committed at `2c90e0d` (v1.0 of `docs/LAYER11_PUBLIC_ENTRY_POINT_SPEC.md`,
`docs/LAYER12_VIMSHOTTARI_SPEC.md` and `docs/LAYER13_DASHA_OUTPUT_SPEC.md`). Those layers are
**not modified** by this milestone: the viewer is a consumer of their public surfaces and adds no
astronomy, no astrology and no recalculation of any chart or timeline value.

**Validation status carried forward.** The production-resource integration of Layers 11–13 is
accepted (Layer 13 §11). Independent absolute-date validation of the frozen Lahiri convention
against deva.guru **remains pending** because that site's Ayanāṃśa control is unavailable; the
partial validation on record is a same-input True Citrā comparison (Layer 12 §2, §13). **This
milestone makes no exact-compatibility claim** with deva.guru or any other calculator, and the
viewer's page must not either (§6, §9.3 `engine.validation_note`).

**Decisions.** D1–D11 and D13 of v0.1 are approved subject to the v0.2 corrections (§15). D12 is
revised: the textual scan is retained as a supplemental check and a reproducible browser
acceptance script is committed (§13.4, §14). D14–D17 are approved with v0.3 (§15).

## 1. Goal, scope and non-goals

**Goal.** A person enters a birth (date, local wall time, place query), chooses a daśā year
convention, and the browser shows the existing North Indian D1 SVG and the Vimshottari timeline;
the nine Mahādaśās are listed, each expands into its nine Antardaśās, and each of those into its
nine Pratyantardaśās. Everything shown is produced by one call to the Layer 13 combined API,
`vedic_chart.app.render_chart_and_dasha`, from one resolved `BirthChart`.

**In scope.** A local, single-user, browser-based viewer: a small standard-library HTTP server in
a new package `vedic_chart.viewer`, one static page, one JSON endpoint, a lossless transport
contract, a committed acceptance script, and the acceptance procedure of §14.

**Out of scope (unchanged from the standing rules).** Hosting, accounts, cloud deployment, TLS,
multi-user operation, any external service, analytics, persistent storage of births, automatic
file exports, a current-time ("now") lookup, daśā levels beyond Pratyantardaśā, a reduced-depth
page mode, any other daśā system or option, any change to the frozen Lahiri convention, any
change to the SVG renderer, and any new astrology feature. No new runtime dependency is
introduced (§3.3).

## 2. Architecture recommendation

### 2.1 Recommended: standard-library threaded HTTP server, one engine lock, one static page

```
browser (static HTML/CSS/JS, no framework)        Python process (vedic_chart.viewer)
────────────────────────────────────────          ─────────────────────────────────────────────
GET  /              ← viewer.html                 http.server.ThreadingHTTPServer on 127.0.0.1
GET  /viewer.css    ← static file                 one ChartConfig built at start-up (fail fast)
GET  /viewer.js     ← static file                 per-connection socket read timeout (§11.1)
POST /api/chart     → JSON request                parse + validate (any thread)
                    ← JSON response               with ENGINE_LOCK:                      ← strictly one at a time
                                                      render_chart_and_dasha(request, config, options, year)
                                                      dasha_rows(timeline, depth=3)
                                                  transport.serialize(result, parsed) → JSON (strings only)
```

- **Python supplies everything.** One `POST /api/chart` per "Generate". The server calls the
  combined API once and serialises the whole result: the resolution decision, the birth instant,
  the SVG string verbatim, the timeline summary, all 819 rows (pre-order, with Layer 13's
  `in_nominal_birth_chain` / `in_quantized_birth_chain` flags) and the two birth chains. The
  browser only **arranges and displays strings**: it nests rows by their `level` sequence,
  toggles visibility, and inserts the SVG. It never computes a boundary, a fraction, a membership
  or a zone offset (§9.1).
- **Whole tree in one response.** 819 rows serialise to well under 1 MB of JSON (measured at
  acceptance: row block 516 088 B for Jalandhar and 519 117 B for Jammu; whole Jalandhar
  response 529 930 B — larger than the ≈ 413 KB pre-implementation estimate because each row
  also carries `chain_names`, `nominal_years` and `posinset`).
  Expansion is therefore instantaneous, needs no second request, and cannot race with a newer
  submission.
- **Threaded connections, sequential engine (v0.2 correction; D15).** v0.1 proposed the
  single-threaded `HTTPServer`. That design blocks on a browser's speculative pre-opened idle
  connection or on an incomplete request until the read timeout expires, because one connection
  owns the only thread. v0.2 uses `http.server.ThreadingHTTPServer` (`daemon_threads = True`) so
  that header parsing, static files and idle sockets never delay a valid request, and protects
  the frozen engine — whose `ephemeris_session` acts on process-global state and must be used
  sequentially (Layer 11 spec) — with **one module-level `threading.Lock`** held around the
  single pipeline call and the row extraction. Nothing outside that block touches the engine, the
  geodata connection or any `vedic_chart` computation; parsing, serialisation and writing happen
  outside it. The lock is plain (non-reentrant). **It guarantees mutual exclusion only**: which
  of several waiting requests acquires it next is not defined by `threading.Lock`, so the order
  in which calculations complete may differ from the order in which they were submitted. No
  FIFO scheduler is added; the browser's sequence check (§10.2) is what ensures that only the
  latest submission can update the page, whatever the completion order. Each connection carries
  a bounded socket read timeout (§11.1). Verified on Python 3.10.12
  with a scratch probe (§14.7): a valid request is served promptly (within the probe's 0.3 s
  wait) while another client holds an idle connection; the idle connection and a
  partial-header connection are closed by the server when the timeout expires; a short body is
  answered 408; the next valid request succeeds; a client that disconnects during the response
  produces one `handle_error` line and the server continues.
- **Static assets are package files** under `src/vedic_chart/viewer/static/`, read once at
  start-up with `importlib.resources.files("vedic_chart.viewer")` and served from memory. No
  inline script or style, so the Content Security Policy is `script-src 'self'` without nonces.
- **Starts with one command** (§4). It prints the URL (`http://127.0.0.1:<port>/`), the
  resolved resource paths and the geodata provenance rows, then serves until Ctrl-C.

### 2.2 Alternatives considered and rejected

| Alternative | Why not |
|---|---|
| Flask / FastAPI / Starlette | New dependency (plus a server such as uvicorn) for one endpoint and three static files; violates "no new dependencies without approval" for no functional gain. |
| Static HTML + pre-generated JSON, no server | Cannot accept a birth input at all; the astrology must run in Python at request time. |
| Desktop wrapper (pywebview, tkinter, Qt) | New dependency or a second UI toolkit; a browser is already present and the user asked for a browser-based viewer. |
| Single-threaded `HTTPServer` (v0.1) | Blocks on idle pre-opened or incomplete connections for the whole read timeout; rejected in v0.2 as described above. |
| Re-implementing membership or boundaries in JavaScript | Explicitly forbidden by the milestone brief and by Layer 12 §7: the `Fraction`/`datetime` arithmetic exists once, in Python. |
| `python -m http.server` + CGI | Deprecated CGI module (removed in 3.13) and process-per-request would re-open the ephemeris every time. |

## 3. Files, modules, dependencies and import rules

### 3.1 New files (proposed manifest — nothing else in the repository changes)

```
src/vedic_chart/viewer/__init__.py        NEW  package docstring; re-exports ViewerConfig, ViewerServer, serve
src/vedic_chart/viewer/__main__.py        NEW  `python -m vedic_chart.viewer` → sys.exit(main())
src/vedic_chart/viewer/server.py          NEW  argument parsing, server subclass, request handler, HTTP
                                               contract (§11), error mapping (§12), engine lock
src/vedic_chart/viewer/transport.py       NEW  pure functions: request parsing (§9.2) and response
                                               serialisation (§9.3–9.5); no I/O, no HTTP, no threads
src/vedic_chart/viewer/static/viewer.html NEW  the page (no inline script/style)
src/vedic_chart/viewer/static/viewer.css  NEW
src/vedic_chart/viewer/static/viewer.js   NEW  plain ES2020, no bundler, no framework
tests/test_viewer_transport.py            NEW  serialisation and Layer 13 parity (§13.1)
tests/test_viewer_server.py               NEW  live loopback server over the fixture database (§13.2)
tests/test_viewer_boundaries.py           NEW  AST import/arithmetic rules (§3.4), module count, public
                                               names, viewer.js textual scan (§13.3)
tests/fixtures/viewer/jalandhar_365256363.json   NEW  golden transport document (§13.1)
tests/fixtures/viewer/divergence_su_mo.json      NEW  timeline-only transport documents for the two
tests/fixtures/viewer/divergence_ke.json         NEW  Layer 12 divergence cases (§8.3, §13.1, §13.4)
tools/viewer/acceptance.py                NEW  reproducible browser acceptance script (§13.4, §14);
                                               Playwright-dependent like tools/render/rasterise_inspection.py,
                                               not imported by the package, not collected by pytest
docs/LAYER14_INTERACTIVE_VIEWER_SPEC.md   NEW  this document
README.md                                 MOD  one "Interactive viewer (Layer 14)" subsection: the executable
                                               start-up command (§4), the URL, limits, how to run the acceptance script;
                                               the PYTHONPATH=src prefix on the four existing examples (D17)
tests/test_dasha_boundaries.py            MOD  D18 only: the Layer 13 consumer test now admits app AND viewer as
                                               surface-only consumers of vedic_chart.dasha (renamed
                                               test_only_the_app_and_viewer_packages_consume_this_layer_s_surface;
                                               submodule/private imports and imports from every other package stay
                                               forbidden). The sole authorised change to an existing test.
```

`pyproject.toml` is **not** modified (§4 explains how the command runs from the source checkout);
`tests/test_app_boundaries.py::test_packaging_is_unchanged` keeps passing unchanged. `tools/`
already holds Playwright-dependent scripts outside the package (`tools/render/`), so
`tools/viewer/acceptance.py` follows an existing convention rather than creating one.

### 3.2 Existing public surfaces consumed (read-only)

| Surface | Used for |
|---|---|
| `vedic_chart.app.ChartConfig`, `ConfigurationError` | one configuration at start-up; fail fast before binding |
| `vedic_chart.app.render_chart_and_dasha`, `ChartAndDashaResult` | the single calculation per request |
| `vedic_chart.inputs.model.BirthChartRequest.from_components` + its three errors | request construction and typed input errors |
| `vedic_chart.dasha.YearConvention`, `DashaRangeError`, `dasha_rows`, `DashaRow`, `resolve_zone` | convention selection; 819 rows with N/Q flags; the birth-zone `ZoneInfo` |
| *(not imported — see §9.5 rule 1)* `vedic_chart.dasha.table.ABBREVIATIONS` | the Layer 13 lord abbreviations are **restated** in `transport.py`, because importing the submodule would reach past the daśā package's published surface (Layer 13 §2 forbids that for the app package and `tests/test_dasha_boundaries.py` enforces it); the viewer imports `vedic_chart.dasha` only through its package surface, and a parity test asserts the restated mapping equals Layer 13's (v0.4 correction) |
| `vedic_chart.render.NorthIndianOptions` | the fixed renderer option set (§7.1) |
| `result.d1.meta` (`D1Meta`: `zodiac`, `ayanamsha`, `house_system`, `node`, `engine_spec`) | the displayed calculation convention (§6) — read, never restated |
| `vedic_chart.location.model.AmbiguousPlaceError`, `PlaceNotFoundError`, `InvalidCoordinateError`, `PlaceCandidate` | ambiguity and not-found responses |
| `vedic_chart.location.offline.resolver.OfflineLocationResolver` | start-up banner only: `dataset_metadata()` read once and closed (§4) |
| `vedic_chart.location.offline.db.GeodataError` | resource error mapping |
| `vedic_chart.time.local_time.InvalidTimezoneError`, `NonexistentLocalTimeError`, `AmbiguousLocalTimeError` | input error mapping |
| Result attributes: `result.svg`, `result.chart.location`, `result.chart.moment_utc`, `result.resolution`, `result.timeline` (`VimshottariTimeline` fields, `periods_at_birth()`, `active_periods_at(birth_utc)`) | serialisation |

No private name (`_classify_moon`, `_format_instant`, `_balance_text`, `_chain_text`,
`_lord_name`, `_year_days_text`, `_report_decision`, …) is imported. The presentation rules the
transport restates because Layer 13 keeps them private are listed exhaustively in §9.5, each with
its parity test (D5).

### 3.3 Dependencies

- **Runtime: none new.** Python ≥ 3.10 standard library only: `http.server`, `socketserver`,
  `threading`, `json`, `re`, `secrets`, `argparse`, `importlib.resources`, `zoneinfo` (through
  `resolve_zone`), `webbrowser` (only behind `--open`, D3). The existing `pyswisseph==2.10.3.2`
  and `timezonefinder==8.2.0` are reached only through Layers 1–13.
- **Browser: none.** No framework, no npm, no bundler, no CDN. The page loads nothing from the
  network except its own three files from the local server.
- **Repository tests: none new.** `pytest` as already used.
- **Acceptance script (tools, not the package):** Playwright for Python with its Chromium, in the
  environment where the script runs (D14). It is not a project dependency and is not installed by
  this milestone.

### 3.4 Import and arithmetic rules for `vedic_chart.viewer` (AST-enforced, mirroring Layer 11 §9 / Layer 13 §2)

- `server.py` may import: stdlib `argparse`, `dataclasses` (for `ViewerConfig`, v0.4), `http`,
  `http.server`, `importlib.resources`, `json`, `re`, `secrets`, `socket`, `socketserver`,
  `sys`, `threading`, `traceback`, `pathlib`, `typing`, `webbrowser`; project
  `vedic_chart.app`, `vedic_chart.viewer.transport`,
  `vedic_chart.location.offline.resolver` (`OfflineLocationResolver`, start-up banner only), and
  exception classes from `vedic_chart.inputs.model`, `vedic_chart.location.model`,
  `vedic_chart.location.offline.db`, `vedic_chart.time.local_time`, `vedic_chart.dasha`.
- `transport.py` may import: stdlib `dataclasses`, `datetime`, `fractions`, `json`, `re`,
  `typing`; project `vedic_chart.app` (result types), `vedic_chart.dasha` (`dasha_rows`,
  `DashaRow`, `YearConvention`, `VimshottariTimeline`, `resolve_zone`, `DashaRangeError` for
  §9.5 rule 2), `vedic_chart.inputs.model`, `vedic_chart.location.model` (`PlaceCandidate`),
  `vedic_chart.render` (`NorthIndianOptions`), `vedic_chart.vedic.grahas` (`Graha`). **No
  viewer module imports a `vedic_chart.dasha` submodule** (surface only; AST-enforced, v0.4).
- Forbidden everywhere in the package: `vedic_chart.astronomy`, `.sidereal`, `.ephemeris`,
  `.vedic.divisions`, `.chart.assemble`, `.representation` (the `D1Meta` values are read off the
  result object, not imported), `.render.north_indian` internals, `swisseph`, `timezonefinder`,
  `sqlite3`; `round()`, `math`, `float()`; `time`, `datetime.now`, `datetime.utcnow`,
  `date.today` (no clock anywhere — the viewer has no notion of "now"); `open()` for writing;
  `logging`.
- **Arithmetic (v0.2 clarification).** The prohibition is on *recalculation*: no module of the
  package may compute, compare or derive a period boundary, a duration, an offset, a membership,
  a coordinate, a longitude or a zone offset. Reading existing core values — `nominal_years`,
  `nominal_start`, `nominal_end`, `elapsed_years`, `balance_years`, `start_utc`, `end_utc` — and
  passing them through as strings is reading, not arithmetic. **Narrowly scoped presentation
  formatting is permitted in exactly one function**, `transport.decimal_truncated(fraction:
  Fraction, places: int) -> str`, which uses integer `//`, `%` and `*` on `Fraction.numerator`
  and `Fraction.denominator` to print a truncated decimal (§9.5 rule 3). The AST test allows the
  arithmetic operators and `**` inside that function only, and asserts that no other function in
  the package applies `+ - * / // % **` to anything, that `decimal_truncated` is called only with
  `timeline.balance_years` and the literal `9`, and that no comparison operator is applied to a
  `datetime` or `Fraction` value anywhere in the package (membership comes from `DashaRow` flags
  and from Python's own `periods_at_birth()` / `active_periods_at()`; the `identical` flag is a
  tuple equality of `(level, lords)` keys, §9.4).
- `viewer.js` rules are stated in §9.1 and checked textually in §13.3: no `Date`, no `parseFloat`
  / `Number(` on transported values, no arithmetic operators on transported strings, no `eval`,
  no `innerHTML`, no browser storage APIs, no non-relative `fetch`.

## 4. Start-up, configuration and shutdown

### 4.1 The executable command (source checkout)

The project is **not installed** into its virtual environment: `.venv` holds `pyswisseph`,
`timezonefinder` and `pytest` only, there is no editable install and no `.pth` entry for `src`,
and `pyproject.toml`'s `pythonpath = ["src"]` applies to **pytest only**. A plain
`python -m vedic_chart.viewer` from the repository root therefore fails with
`ModuleNotFoundError` unless `src` is on `sys.path`. The documented command sets it explicitly
(zsh and bash, from the repository root):

```
PYTHONPATH=src .venv/bin/python -m vedic_chart.viewer --geodata data/geodata.sqlite --ephemeris ephe
```

(The README's existing Layer 11 examples of `python -m vedic_chart.app` share this assumption
without stating it; the Layer 14 README subsection states it for the viewer and notes that the
same prefix applies to the CLI. Whether to also amend the Layer 11 examples is D17.)

Options: `--geodata PATH` and `--ephemeris PATH` (required, D1); `--port N` (default `0`, D2);
`--open` (D3); `--verbose`.

### 4.2 Start-up sequence and failure handling

1. Parse arguments. Missing required flags, or a `--port` that is not an integer in `0..65535`,
   are argparse errors: usage on stderr, **exit 2**; nothing else has happened.
2. Build `ChartConfig(geodata_path, ephemeris_path)`. `ConfigurationError` → `error: …`,
   **exit 4** (the CLI's `EXIT_CONFIG`). Nothing is bound.
3. Read the banner metadata: `with OfflineLocationResolver(config.geodata_path) as r:
   rows = r.dataset_metadata()`. `GeodataError` or `sqlite3.Error` (caught as `Exception` here,
   since the viewer imports no `sqlite3` name) → `error: geodata metadata could not be read:
   …`, **exit 4**. The connection is closed by the context manager on every path.
4. Generate the per-launch token (§11.2). Load the three static files into memory
   (`importlib.resources`); a missing or unreadable file → **exit 4**.
5. Bind `127.0.0.1:<port>`. `OSError` (port in use, permission) → `error: cannot bind
   127.0.0.1:<port>: …`, **exit 5**. `ThreadingHTTPServer` sets `allow_reuse_address`, so a
   fixed port can be reused immediately after a clean stop.
6. Print the banner (stdout, one line each): `viewer: http://127.0.0.1:<port>/`; `geodata:
   <absolute path>`; one `geodata metadata: <key> = <value>` line per `dataset_metadata` row;
   `ephemeris: <absolute dir>`; one line per `config.ephemeris_files` entry with its size;
   `year conventions: 365.25, 365.256363 (explicit per request)`; `press Ctrl-C to stop`. The
   token is **not** printed.
7. If `--open`: `webbrowser.open(url)`. A `False` return or any exception → one stderr line
   `warning: could not open a browser: …`; the server keeps serving. The URL is already on
   stdout.
8. `serve_forever()` inside `try/finally: server.server_close()`. `KeyboardInterrupt` → the
   `finally` closes the **listening** socket and the process exits **130** (the CLI's
   `EXIT_INTERRUPTED`). Any other exception escaping `serve_forever` → traceback to stderr,
   listening socket closed by the same `finally`, **exit 1**. Exit 0 is not reachable from the
   command line while serving.

### 4.2a Stopping, precisely (v0.3)

Three things are distinct and the specification does not conflate them:

- **Closing the listening socket** (`server_close()`): no new connections are accepted. With
  `daemon_threads = True`, `ThreadingMixIn.server_close()` does **not** join worker threads.
- **Stopping the accept loop** (`shutdown()`): makes `serve_forever()` return; it must be
  called from a thread other than the one running `serve_forever()`, and it does not close
  the socket or touch workers.
- **Active worker threads**: a worker in the middle of a request (reading, calculating under
  the engine lock, or writing) keeps running after both of the above. From the command line
  the process exits when the main thread returns, and the daemon workers are terminated with
  it: an in-flight calculation is abandoned, its response is never written, and the
  `ephemeris_session` context manager's exit (which closes the Swiss Ephemeris files) does
  **not** run for that abandoned call. This is stated, not solved: the ephemeris files are
  opened read-only and the viewer writes nothing, so an abandoned calculation leaves nothing
  inconsistent behind. Neither `server_close()` nor `shutdown()` is claimed to terminate
  workers or to complete ephemeris cleanup.

**Public API lifecycle.** `vedic_chart.viewer` exports three names:

- `ViewerConfig(geodata_path, ephemeris_path, port=0, open_browser=False, verbose=False)` —
  a frozen dataclass; `geodata_path`/`ephemeris_path` are handed to `ChartConfig` unchanged.
- `ViewerServer` — the `ThreadingHTTPServer` subclass. `ViewerServer.create(config)` performs
  steps 2–5 (configuration, metadata, token, static files, bind) and returns a bound server
  with `.url`, `.config`, `.metadata_rows`; the caller then calls `serve_forever()` and, from
  another thread, `shutdown()` followed by `server_close()`. The repository tests and the
  acceptance script use this path. Creating the server does not print anything.
- `serve(config) -> int` — the command-line lifecycle: `ViewerServer.create`, print the banner
  (step 6), optional browser (step 7), `serve_forever()` (step 8), and the exit code mapping of
  steps 1–8. It returns 130 on `KeyboardInterrupt` and never returns 0 while serving.
  `main(argv) -> int` in `server.py` parses arguments into a `ViewerConfig` and calls `serve`;
  `__main__` calls `sys.exit(main())`. Exceptions during `create` are mapped to exit codes by
  `serve`, not by `create`, so embedding callers see the typed exceptions themselves.

### 4.3 Persistence statement (v0.2 qualification)

The viewer performs **no application persistence**: it writes no cache, temporary file, log
file, PID file or export, and the birth exists in process memory only for the duration of one
request. Two things outside the application's control are stated rather than claimed away:
Python may write `__pycache__/*.pyc` bytecode for the package modules on first import (as for
every run of the project; `PYTHONDONTWRITEBYTECODE=1` or `python -B` suppresses it), and the
browser is a separate program with its own cache, history, session-restore and form-data
behaviour (§11.4). The repository test of §13.2 checks the working tree for new files
**excluding `__pycache__` directories**.

## 5. Birth input

**Form fields** (all required; the browser blocks submission until each is syntactically valid
and the server re-validates everything):

| Field | Control | Client-side syntax check (no `Date` object) | Authority |
|---|---|---|---|
| Date | `<input type="date">` with a text fallback; value `YYYY-MM-DD` | regex `^[0-9]{4}-[0-9]{2}-[0-9]{2}$` only; **no** range or calendar check in the browser | server regex (§9.2), then `BirthChartRequest.from_components` → `InvalidBirthDateError` (impossible dates); ephemeris coverage (1800–2399 UT) is decided by the engine at calculation time and surfaces as its own `RuntimeError` message (§12) |
| Local time | `<input type="time" step="1">`; value `HH:MM` or `HH:MM:SS` | regex `^[0-9]{2}:[0-9]{2}(:[0-9]{2})?$`; seconds default to 0 | server regex, then `InvalidBirthTimeError`; Layer 3's `NonexistentLocalTimeError` / `AmbiguousLocalTimeError` for DST gaps and folds |
| Place query | `<input type="text" autocomplete="off">`, sent verbatim | non-blank | Layer 2 resolver: `PlaceNotFoundError`, `AmbiguousPlaceError` |
| Year convention | two radio buttons, **neither pre-selected** | one must be chosen | server accepts only the literal strings `"365.25"` / `"365.256363"` (§6) |

**Resolved place display** (after success), from `resolution` and `location` in the response:
canonical name; latitude and longitude as Python `repr` strings, unrounded, with hemisphere
words added by the browser only as text (`N/S`, `E/W` chosen from the sign character of the
string, no numeric conversion); IANA timezone id; the UTC offset in force at the birth instant
(Python computes it — `moment_utc.astimezone(zone)` — and sends `+05:30`-style text; pre-1906
Kolkata prints seconds, `+05:21:10`, exactly as Layer 13 does); the chosen GeoNames id, feature
code and population; and, whenever `dominance_applied` is true, a visible notice: *"Chosen
automatically over N materially different place(s): <dominance_reason>. Add a qualifier such as
"<name>, <country>" if this is not the place you meant."* An automatic choice is therefore never
invisible, in line with Layer 2's `resolve_with_details` contract.

**Bare and qualified queries are different queries.** On the production database the exact
query `Jalandhar` resolves with 3 candidates, 2 materially different, dominance applied; the
exact query `Jammu` with 8 candidates, 7 materially different, dominance applied; the exact query
`Hyderabad` is ambiguous with 2 candidates (Telangana, India; Sindh, Pakistan); the exact query
`Hyderabad, India` resolves with 1 candidate and no dominance. Every assertion in §13 and §14
names the exact query string it applies to and never carries a count from one query to another.

**Ambiguity.** On `AmbiguousPlaceError` the server returns HTTP 409 with **every** candidate the
error carries (`error.candidates`, ranked best first), each as name, admin1, country, population,
coordinates and GeoNames id, plus the resolver's own message. The page lists them under the
heading *"Several places match — add a qualifier and generate again"* and leaves the query field
focused with its text intact. There is **no** click-to-select control (D6): the viewer never
substitutes a candidate for the person's query; a qualified query goes back through the resolver
like any other.

**Not found.** HTTP 404 with the resolver's message (which already states the coverage: cities
of 500+ population worldwide plus all populated places in India).

## 6. Calculation settings

- **Displayed convention comes from the chart's own descriptors** (v0.2 correction). The
  response's `engine` block carries the five `D1Meta` strings of `result.d1.meta` verbatim —
  `zodiac` (`"sidereal"`), `ayanamsha` (`"Lahiri (Chitrapaksha), true equinox"`),
  `house_system` (`"whole_sign"`), `node` (`"mean"`), `engine_spec` (`"AstroLearn Calculation
  Specification FROZEN v1.0"`) — and the page shows them as *"Ayanāṃśa: Lahiri (Chitrapaksha),
  true equinox · Whole Sign houses · Mean Node · AstroLearn Calculation Specification FROZEN
  v1.0"*, using the `house_system`/`node` labels the renderer already uses for its accessible
  description (`Whole Sign`, `Mean Node`) by exact string match in `viewer.js`, and the
  descriptor text itself for anything unmatched. **No Swiss Ephemeris version string is
  displayed or transported**: the viewer does not import the ephemeris layer, and a version is
  not something the `.se1` file names establish. The frozen version is recorded where it belongs,
  in `docs/CALCULATION_SPEC.md`. The ephemeris file names are listed in the start-up banner only,
  as configuration, not as provenance.
- **Ayanāṃśa is not selectable**; nothing in the request can vary it.
- **Year convention:** explicit per request, `365.25` or `365.256363` days, mapped to
  `YearConvention.FIXED_365_25` / `FIXED_365_256363` by exact string match in `transport.py`.
  There is no default and no memory of the previous choice beyond the current page state
  (nothing is stored, §11.4). The results header repeats *"Year: 365.256363 days"* beside the
  table, taken from the response's `request.submitted.year_convention`, so the label and the rows
  come from the same document (§10.2).
- Changing a form field after a result is shown does **not** change the result; §10.3 defines
  how the page shows that the inputs and the displayed result no longer agree.

## 7. Chart display

### 7.1 Renderer options (fixed; the SVG is the renderer's own output, unchanged)

```python
NorthIndianOptions(
    show_degrees=True,          # degrees on (brief)
    mark_node_retrograde=False, # renderer default: the seven bodies keep their existing retrograde
                                # underlines; the nodes' perpetual motion is not marked (D4)
    caption=False,              # the page shows the birth details itself (D4)
    width=None,                 # viewBox-only document; CSS sizes it (§7.2)
    id_prefix="d1",             # exactly one chart is in the document at a time (§7.3)
)
```

The server passes `result.svg` through **verbatim** as a JSON string. §14.4 requires the
response's `svg` string to be **byte-identical** to the file written by `python -m
vedic_chart.app --out` for the same birth with the equivalent flags (degrees on by default, no
`--caption`, no `--mark-node-retrograde`, no `--width`, default `--id-prefix d1`).

### 7.2 Sizing, aspect ratio and scrolling

- The SVG carries `viewBox="0 0 1080 H"` and `preserveAspectRatio="xMidYMin meet"` (Layer 10
  §7), so aspect ratio is preserved at any CSS size. The page styles the element `width: 100%;
  height: auto; max-width: 1080px; min-width: 600px` inside a wrapper with `overflow-x: auto`.
- **600 px is the renderer's supported minimum** (Layer 10 §3(b), U-3). The viewer never renders
  the chart narrower than 600 CSS px: on a viewport narrower than that the wrapper scrolls
  horizontally and the chart keeps 600 px. The daśā table sits in its own horizontally
  scrolling wrapper. The page body itself must not scroll horizontally (§14.6 checks
  `document.documentElement.scrollWidth <= clientWidth`). Beside each wrapper a static hint —
  *"Scroll horizontally to see the full chart."* / *"…the full table."* — is shown only while
  that wrapper actually overflows (`scrollWidth > clientWidth`, re-evaluated after every
  render, expand/collapse, microseconds toggle and window resize) and hidden otherwise (v0.5).
  The page's lede reads: *"Runs locally. Everything shown is computed in Python from one call
  per submission. The viewer sends no birth data to external services and does not save birth
  records."* — a statement about the application's behaviour, not about the browser or the
  operating system (§4.3, §11.4).
- **No viewer CSS rule selects inside the chart container** (`#chart *` is never a target, and
  no global element or class rule matches SVG content: the viewer's classes are prefixed `v-`,
  the renderer's are `paper`, `retro` and its text classes). The inserted document therefore
  renders exactly as the standalone file does, which §14.4 checks pixel by pixel.
- No zoom, pan or download control in this milestone.

### 7.3 Inserting the SVG and its accessibility

The renderer emits `role="img"`, `aria-labelledby="d1-title"`, `aria-describedby="d1-desc"`,
`<title id="d1-title">` and `<desc id="d1-desc">`. Inserting the SVG **inline** (not as `<img>`)
keeps those readable by assistive technology. The string is parsed with `DOMParser` as
`image/svg+xml`; the result is accepted only if the document element is `svg` in the SVG
namespace and contains no `script`, `foreignObject` or `on*` attribute (a defensive check on our
own renderer's output, which never has any); the element is then adopted into the emptied chart
container. The `d1-*` ids are unique because the container is emptied first and only one chart
exists in the document at a time. **Byte equality is not required after DOM insertion**
(v0.2 correction): browsers may legitimately re-serialise attributes and whitespace. The DOM is
checked semantically instead (§14.4).

## 8. Daśā interaction

### 8.1 Table

One table, `<table role="treegrid" aria-label="Vimshottari dasha">`, with column headers
`Level`, `Chain`, `Start`, `End`, `N`, `Q` — the Layer 13 columns, in the Layer 13 order — and
initially the **nine Mahādaśā rows** in cycle order (the birth Mahādaśā first, from its true
pre-birth start; Layer 12 §5).

| Column | Content (all strings from the transport) |
|---|---|
| Level | `MD`, `AD`, `PD`, preceded on MD and AD rows by the toggle glyph (§8.2) |
| Chain | full lord chain, abbreviated exactly as Layer 13 (`Ju-Sa-Me`); the cell's `title` and the row's accessible name carry the full names (`Jupiter › Saturn › Mercury`) |
| Start / End | `local_seconds` text in the birth place's zone with its UTC offset, e.g. `1986-04-22 03:10:52+05:30`, identical to Layer 13 second precision; with the "show microseconds" toggle (D7) the `local` field, `1986-04-22T03:10:52.123456+05:30`, is shown instead |
| N | `N` when `in_nominal_birth_chain`, else empty; header title "contains the birth instant by exact nominal offset" |
| Q | `Q` when `in_quantized_birth_chain`, else empty; header title "contains the birth timestamp after microsecond quantization" |

A caption above the table restates the Layer 13 header facts, all from the transport: Moon
sidereal longitude (repr string), nakṣatra name and number, lord, the nominal balance of the
first Mahādaśā at birth as the exact fraction and its 9-place truncated decimal (§9.5), the year
convention, the display zone, and the two sentences *"Intervals are half-open [start, end)"* and
*"The first Mahadasha begins at or before birth (before birth unless the core's elapsed
nakshatra fraction is zero); its pre-birth part is listed."*

### 8.2 Focus model: every visible row is a focus target (v0.2 rewrite; D16)

The v0.1 description — buttons as the only focus targets, skipping PD rows — was not a coherent
treegrid pattern. v0.2 adopts the WAI-ARIA treegrid **row-focus** model:

- **Rows are the focus targets.** Every visible `<tr role="row">` — MD, AD and PD alike — has
  `tabindex="-1"` except the current row, which has `tabindex="0"` (roving tabindex). The table
  is one Tab stop. Each row has `aria-level` (1, 2, 3), `aria-posinset` (1–9), `aria-setsize="9"`
  and a stable `id` derived from its chain (`row-ju`, `row-ju-sa`, `row-ju-sa-me`). MD and AD rows
  carry `aria-expanded="true|false"`; PD rows carry **no** `aria-expanded` (they are leaves).
- **No `aria-controls`.** Child rows are created on expand and removed on collapse, so a
  reference to them would dangle while collapsed. The treegrid pattern does not need it: the
  parent–child relation is expressed by DOM order plus `aria-level`. The v0.1 `aria-controls`
  is removed; the repository test asserts that no `aria-controls` attribute appears in the page.
- **Toggle glyph.** MD and AD rows show a `<span class="v-toggle" aria-hidden="true">` (▸/▾)
  in the Level cell for pointer users; clicking anywhere on the Level cell toggles the row. It
  is not a button and not focusable: the row already carries the state and the keyboard
  behaviour, so a second focusable control would double the Tab stops without adding meaning.
  The row's accessible name is *"Mahadasha Jupiter, 1984-03-03 22:03:19+05:30 to 2000-03-04
  00:29:56+05:30, N, Q"*-style text built from the cells; the expanded state comes from
  `aria-expanded`.
- **Keys** (on the focused row):

  | Key | Behaviour |
  |---|---|
  | `ArrowDown` / `ArrowUp` | focus the next / previous **visible** row, any level (PD rows included); no wrap |
  | `ArrowRight` | collapsed expandable row: expand (focus stays); expanded row: focus its first child; PD row: nothing |
  | `ArrowLeft` | expanded row: collapse (focus stays); collapsed or PD row: focus its parent row (nothing on an MD row) |
  | `Enter` / `Space` | toggle an expandable row; nothing on a PD row |
  | `Home` / `End` | first / last visible row |
  | `Tab` / `Shift+Tab` | leave the table (to the next / previous page control) |

- **Collapse removes descendants and restores focus.** Collapsing a row removes all its
  descendant rows and forgets their expanded state (D8). If the focused row was among the
  removed descendants, focus moves to the collapsed ancestor. "Collapse all" moves focus to
  the nearest still-visible ancestor of the focused row (its MD row). "Expand all" (bounded:
  at most 819 rows) keeps focus where it is. Focus is never lost to `body`.
- **"Expand birth chain"** (a page button above the table) expands the MD and AD rows of the
  nominal chain and, when the chains differ, also those of the quantized chain, then **moves
  focus to the nominal chain's PD row** (`row-<md>-<ad>-<pd>`), which is scrolled into view. It
  expands; it never collapses other rows. There is no depth setting on the page (§1), so this
  target always exists.

### 8.3 Birth chains

The transport carries both chains explicitly (§9.4): `birth_chain.nominal` from
`timeline.periods_at_birth()` and `birth_chain.quantized` from
`timeline.active_periods_at(timeline.birth_utc)`, each as three `(level, lords)` keys, plus
`birth_chain.identical`, computed in Python as tuple equality of the two key lists.

- A "Birth chain" panel above the table shows *Nominal:* `Ju › Ju-Su › Ju-Su-Me` and
  *Quantized:* `Ju › Ju-Su › Ju-Su-Me`. When `identical` is false the panel adds, in a
  `role="note"` box: *"The nominal and quantized birth chains differ. N marks the chain defined
  by the Moon's exact nakṣatra fraction; Q marks the chain whose quantized microsecond intervals
  contain the birth timestamp. They differ only when a post-birth remainder is shorter than one
  microsecond (Layer 12 §7)."* Both Layer 12 divergence cases — `nextafter(40.0, 0)` (Su /
  Su-Ve / Su-Ve-Ke nominal vs Mo / Mo-Mo / Mo-Mo-Mo quantized) and `3.666666666666666` (Ke-Su /
  Ke-Su-Ve vs Ke-Mo / Ke-Mo-Mo) — must render with both chains and both marker columns intact;
  §13.1 and §14.5 exercise them through the transport with `build_vimshottari` directly.
- Rows in a birth chain carry `class="v-birth-nominal"` / `class="v-birth-quantized"` for a
  subtle background in addition to the N/Q text — colour is never the only cue.
- There is **no** "current period" or "today" marker; the page never reads a clock (§1).

## 9. Shared calculation and data transport

### 9.1 Principles

1. **One calculation, one result.** The server calls `render_chart_and_dasha` exactly once per
   request, under the engine lock; the SVG and the timeline come from the same `BirthChart` by
   construction (Layer 13 §4).
2. **Lossless strings.** Every timestamp is transported as an ISO-8601 string **with
   microseconds** (`timespec="microseconds"`) and an explicit offset; every `Fraction` as an
   object of two decimal integer strings; every float as its Python `repr` (shortest round-trip).
   JSON numbers appear only for small structural integers (`level`, `posinset`, counts,
   `geoname_id`, `population`) — never for anything a boundary depends on.
3. **The browser recomputes nothing.** `viewer.js` uses no `Date`, no `parseFloat`/`Number` on
   transported values, no arithmetic on them, and no timezone logic. Membership is the `N`/`Q`
   flags; ordering is the array order; nesting is by `level`.
4. **Python formats presentation once**, by the rules of §9.5, so the page shows exactly what
   `render_dasha_text` prints for the same birth, convention and zone.

### 9.2 Request (`POST /api/chart`)

```json
{"date": "1995-03-21", "time": "06:45", "place_query": "Jalandhar", "year_convention": "365.256363"}
```

`transport.parse_request(body: bytes) -> ParsedRequest` (pure; every failure is a
`TransportError(ValueError)` with a short reason, mapped to 400 `input` by the server):

1. `body.decode("utf-8", errors="strict")`; a leading BOM is rejected (JSON has none).
2. `json.loads(text, object_pairs_hook=_reject_duplicates)`, where the hook raises on a
   repeated key at any depth; `parse_constant` raises on `NaN`/`Infinity`.
3. The document must be an object with **exactly** the four keys `date`, `time`,
   `place_query`, `year_convention` — missing or unknown keys are rejected — and every value
   must be a `str`.
4. `date` must `re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")` and `time` must
   `re.fullmatch(r"[0-9]{2}:[0-9]{2}(?::[0-9]{2})?")` **before** any component parsing —
   explicit ASCII classes, because Python's `\d` matches Unicode digits (verified: `\d{4}`
   accepts fullwidth `１９９５`, which `int()` then also accepts). `int()` is applied to the
   matched digit groups only; the regex is what excludes signs, whitespace, underscores and
   non-ASCII digits that `int()` would otherwise accept (verified: `int(" 12 ")`, `int("1_2")`,
   `int("+12")` and `int("１２")` all return 12). The §13.1 rejection list includes a fullwidth
   digit case.
5. `year_convention` must be exactly `"365.25"` or `"365.256363"`.
6. `place_query` is passed verbatim; `BirthChartRequest` applies the blank check.
7. The components go to `BirthChartRequest.from_components(year, month, day, hour, minute,
   second, place_query=…)`; its typed errors are the server's to map (§12).

`ParsedRequest` holds the four **submitted strings exactly as received** plus the constructed
`BirthChartRequest` and the `YearConvention`.

### 9.3 Response (HTTP 200, `Content-Type: application/json; charset=utf-8`)

```jsonc
{
  "schema": "vedic_chart.viewer/1",
  "request": {
    "submitted":  {"date": "1995-03-21", "time": "06:45", "place_query": "Jalandhar",
                   "year_convention": "365.256363"},                       // the four strings, byte for byte
    "normalized": {"date": "1995-03-21", "time": "06:45:00", "place_query": "Jalandhar",
                   "year_convention": "365.256363"}                        // date.isoformat(), time.isoformat()
  },
  "engine": {"zodiac": "sidereal", "ayanamsha": "Lahiri (Chitrapaksha), true equinox",
             "house_system": "whole_sign", "node": "mean",
             "engine_spec": "AstroLearn Calculation Specification FROZEN v1.0",
             "validation_note": "Independent Lahiri absolute-date validation pending; no exact compatibility claim."},
  "location": {"canonical_name": "Jalandhar, Punjab, India", "latitude": "31.32556",
               "longitude": "75.57917", "timezone_id": "Asia/Kolkata"},
  "resolution": {"query": "Jalandhar", "place_token": "…", "qualifiers": [],
                 "chosen": {"geoname_id": 1268782, "name": "Jalandhar", "admin1_name": "Punjab",
                            "country_name": "India", "feature_code": "PPL", "population": 868929,
                            "latitude": "31.32556", "longitude": "75.57917", "score": "9.908477"},
                 "materially_different_count": 2, "dominance_applied": true,
                 "dominance_reason": "…", "population_ratio": "…",
                 "candidate_count": 3},
  "birth": {"local": "1995-03-21T06:45:00.000000+05:30", "utc": "1995-03-21T01:15:00.000000+00:00",
            "local_seconds": "1995-03-21 06:45:00+05:30", "offset": "+05:30", "zone": "Asia/Kolkata"},
  "svg": "<svg xmlns=…>…</svg>",
  "timeline": {
    "moon_sidereal_longitude": "209.20440791222882", "normalized_longitude": "209.20440791222882",
    "nakshatra_index": 15, "nakshatra_number": 16, "nakshatra_name": "Vishakha",
    "lord": {"key": "jupiter", "name": "Jupiter", "abbr": "Ju"},
    "elapsed_fraction": {"num": "…", "den": "…"}, "remaining_fraction": {"num": "…", "den": "…"},
    "elapsed_years": {"num": "…", "den": "…"},
    "balance_years": {"num": "87164189005907", "den": "17592186044416", "decimal_9": "4.954710505"},
    "cycle_start": {"utc": "…", "local": "…", "local_seconds": "…"},
    "cycle_end":   {"utc": "…", "local": "…", "local_seconds": "…"},
    "year_convention": {"label": "365.256363", "days": {"num": "365256363", "den": "1000000"}},
    "zone": "Asia/Kolkata"
  },
  "birth_chain": {
    "nominal":   [{"level": 1, "lords": ["jupiter"]}, {"level": 2, "lords": ["jupiter","sun"]},
                  {"level": 3, "lords": ["jupiter","sun","mercury"]}],
    "quantized": [ …same shape… ],
    "identical": true
  },
  "rows": [
    {"level": 1, "lords": ["jupiter"], "chain": "Ju", "chain_names": "Jupiter",
     "start": {"utc": "1984-03-03T16:33:19.…+00:00", "local": "1984-03-03T22:03:19.…+05:30",
               "local_seconds": "1984-03-03 22:03:19+05:30"},
     "end":   {"utc": "…", "local": "…", "local_seconds": "2000-03-04 00:29:56+05:30"},
     "nominal_start": {"num": "…", "den": "…"}, "nominal_end": {"num": "…", "den": "…"},
     "nominal_years": {"num": "16", "den": "1"},
     "in_nominal_birth_chain": true, "in_quantized_birth_chain": true, "posinset": 1},
    … 818 more, pre-order (MD, its 9 AD, each AD's 9 PD, next MD, …) exactly as dasha_rows(depth=3)
  ]
}
```

Rules:
- `request.submitted` echoes the four strings **exactly as received** (v0.2 correction; the
  browser compares these, §10.2). `request.normalized` carries the Layer 1 values
  (`birth_date.isoformat()`, `birth_time.isoformat()`) for display.
- `rows` is `dasha_rows(timeline, depth=3)` in its own order; `posinset` is the row's 1-based
  position among its siblings (Python counts; JavaScript reads). The browser nests a level-*k*
  row under the most recent level-*(k−1)* row — a structural rule, not a comparison of values.
- `nominal_years`, `nominal_start`, `nominal_end` are the core's own `Fraction` values
  (`DashaRow` / `DashaPeriod` fields), read and stringified, never derived.
- Coordinates and scores are `repr` strings. `population_ratio` is a `repr` string or `null`.
- All text is UTF-8; `json.dumps(obj, ensure_ascii=False, allow_nan=False,
  separators=(",", ":"))`.
- `transport.serialize(result: ChartAndDashaResult, parsed: ParsedRequest, *, rows=None) ->
  dict` is pure and deterministic; §13.1 keeps a golden document. The keyword-only `rows`
  (v0.4) lets the server hand over the `dasha_rows(depth=3)` tuple it extracted under the
  engine lock (§2.1); when omitted, `serialize` extracts the rows itself and the document is
  identical.

### 9.4 Error responses

```json
{"schema": "vedic_chart.viewer/1", "error": {"kind": "ambiguous_place", "message": "…",
 "candidates": [ {"geoname_id": …, "name": "Hyderabad", "admin1_name": "Telangana",
                  "country_name": "India", "population": …, "latitude": "…", "longitude": "…"}, … ]}}
```

`kind` ∈ `input`, `place_not_found`, `ambiguous_place`, `dasha_range`, `resource`,
`unexpected`, `forbidden`, `bad_request`, `length_required`, `payload_too_large`,
`unsupported_media_type`, `request_timeout`, `not_found`, `method_not_allowed` (§12). Every
error response, including the HTTP-level ones, is a JSON document of this shape with the
headers of §11.3; the server never calls `send_error` (§11.3).

### 9.5 Restated presentation rules and their Layer 13 parity tests (D5)

Layer 13 keeps its formatting helpers private, so `transport.py` restates the following rules
— and nothing else — each verified against `render_dasha_text` output by `tests/test_viewer_transport.py`:

| # | Rule | Restated as | Parity test |
|---|---|---|---|
| 1 | Lord chain text | `"-".join(ABBREVIATIONS[lord] for lord in lords)` with the nine abbreviations (`Su Mo Me Ve Ma Ju Sa Ra Ke`) **restated** as a module-level mapping in `transport.py` (v0.4: not imported, to keep daśā imports surface-only) | the restated mapping equals `vedic_chart.dasha.table.ABBREVIATIONS` (the test may import the submodule), and every row's `chain` equals the `Chain` column of the depth-3 table |
| 2 | Second-precision instant | `moment.astimezone(zone).replace(microsecond=0).isoformat(sep=" ", timespec="seconds")`; `OverflowError` → `DashaRangeError` as in Layer 13 | every row's `start.local_seconds` / `end.local_seconds` equals the `Start` / `End` column; `birth.local_seconds` equals the `Birth` header field |
| 3 | Balance decimal | `decimal_truncated(balance_years, 9)`: `whole = num // den`; `frac = (num % den) * 10**9 // den`; `f"{whole}.{frac:09d}"` (truncation, never rounding); negative values are impossible for a balance and raise | `balance_years.decimal_9` equals the header's `= 4.954710505 years` figure; also `6.181544622` (Jammu, production acceptance), an integer balance, and a value needing trailing zeros |
| 4 | Lord display name | `lord.value.capitalize()` | `timeline.lord.name` equals the header's `lord Jupiter` |
| 5 | Year label | taken from the submitted string (`"365.25"` / `"365.256363"`), not derived | equals the header's `year 365.256363 days` |
| 6 | Moon longitude text | `repr(timeline.moon_sidereal_longitude)` | equals the header's `Moon 209.20440791222882` |
| 7 | Nakṣatra text | `timeline.nakshatra_name`, `timeline.nakshatra_number` read as-is | equals the header's `(Vishakha #16)` |

Rule 3 is the only arithmetic in the package (§3.4). The full-precision `local` and `utc`
strings (`isoformat(timespec="microseconds")`) are not restatements: Layer 13 prints no
microseconds, and these are the standard library's own serialisation of the core's `datetime`s.

## 10. Interaction states, superseding and staleness

### 10.1 States

| State | Behaviour |
|---|---|
| Idle | Form enabled; results region empty or showing the last result; `role="status"` region empty. |
| Validating | Native `required`/`pattern` validation plus the §5 regexes; the first invalid field is focused and described by an inline `aria-describedby` message. No request is sent. |
| Loading | **"Generate" stays enabled** (v0.2 correction; it is how a request is superseded); a "Cancel" button appears; the results region gets `aria-busy="true"` and is dimmed and `inert`; the status region announces *"Calculating…"*; the previous result remains visible underneath. |
| Success | Results region replaced atomically (one DOM subtree swap); `aria-busy` cleared; Cancel hidden; status announces *"Chart and daśā for <canonical_name>, <year> days"*; focus moves to the results heading. |
| Error | Results region unchanged and restored (undimmed, not `inert`); `aria-busy` cleared; Cancel hidden; a `role="alert"` box shows `kind`-specific text plus the server message, and for `ambiguous_place` the candidate list; focus returns to the relevant field (place for place errors, date/time for input errors, convention for a missing selection, the alert itself for server/network errors). |
| Cancelled | As Error, with the status *"Cancelled"* and no alert; focus returns to Generate. |

### 10.2 Superseding a request and discarding stale responses

- Each submission increments a sequence number `n` and creates its own `AbortController`.
  Pressing Generate while a request is in flight **supersedes** it: the older controller is
  aborted, the new request is sent, and the status says *"Calculating… (previous request
  replaced)"*. Cancel aborts the current controller without submitting.
- A response is applied only if its captured `n` equals the current sequence number **and** its
  `request.submitted` block equals, string for string, the four values captured from the form
  at that submission (not the form's current values). Any other response is discarded; a
  mismatch of the echo against the captured values is reported as `unexpected` (it cannot
  happen with this server, and the check guards against a wrong server on the port).
- **Aborting a fetch does not cancel the Python calculation** (v0.2 clarification). The
  server cannot observe the abort until it writes; the superseded calculation still runs to
  completion under the engine lock, and its response write then fails with a broken pipe or is
  ignored by the browser. Rapid resubmission therefore costs one sub-second calculation per
  submission server-side, and **the order in which those calculations complete is not
  specified** (§2.1). Correctness does not depend on it: a response is applied only if it
  belongs to the current sequence number, so the page can only ever show the latest
  submission's result, and a later-completing superseded calculation is discarded. The page
  does not rate-limit beyond this; §14.6 records the completion order for a burst of three
  without asserting it.

### 10.3 Old results versus edited inputs

The results header always states the `request.submitted` values it was computed from. Whenever
any form field's current value differs (string comparison) from the displayed result's
submitted values, the results region is marked `data-stale="true"` — a visible banner *"Inputs
changed — the results below are for 1995-03-21 06:45, Jalandhar, 365.256363 days. Press Generate
to recalculate."* — and the banner disappears when the values agree again. The old result is
never removed by editing, only by a newer successful result.

### 10.4 Keyboard and screen readers

Every page control is a native `<button>`, `<input>` or `<label>`ed field; the table follows
§8.2; the SVG keeps its title/desc (§7.3); live regions are `role="status"` (polite) for progress
and `role="alert"` for errors; focus is managed as in §10.1; colour contrast ≥ 4.5:1; the N/Q
markers and birth-row shading are text plus colour. `prefers-reduced-motion` disables the
loading dim transition.

### 10.5 Escaping and DOM insertion

All dynamic text is inserted with `textContent` (never `innerHTML`, never template strings into
HTML). The SVG is the one exception, handled as §7.3 describes.

## 11. Local operation, HTTP contract, privacy and security

### 11.1 Binding, timeouts and connection handling

- The server binds **`127.0.0.1` only**. There is no `--host` option. IPv6 loopback is not
  bound.
- `ThreadingHTTPServer` with `daemon_threads = True`; the handler sets `timeout = 10`
  (seconds), which `StreamRequestHandler.setup` applies to the connection socket. **What this
  guarantees (v0.3 precision):** each individual blocking socket operation waits at most 10 s
  for the peer; it is **not** a total request deadline. A connection that sends nothing for
  10 s — an idle pre-opened connection, or a request line or headers left incomplete — is
  closed by `handle_one_request`'s own timeout path; a body that stops arriving for 10 s is
  answered **408** `request_timeout` and closed by the handler's `except TimeoutError`. A
  client that keeps sending bytes slower than one per 10 s can hold **its own connection
  thread** longer, bounded in bytes rather than time: `http.server` refuses a request line over
  65 536 bytes (414) and more than 100 header lines (431), and the body is capped at 4 096 bytes
  by `Content-Length` (§11.3), so the worst case is a finite number of 10 s waits. Such a client
  never holds the engine: the lock is acquired only after the whole body has been read and
  parsed. Other connections are unaffected because each runs in its own thread, and the next
  valid request on a fresh connection succeeds (§13.2).
- **Client disconnect during the response**: `BrokenPipeError` / `ConnectionResetError` while
  writing propagate to the server's `handle_error`, which is overridden to print one line
  (`connection closed by client during <route>`) and return; the default implementation's
  traceback is not printed and the server continues. `--verbose` adds the traceback.
- The engine lock (§2.1) is acquired only after the request has been fully read and parsed, so
  a slow or malicious client cannot hold the engine while dribbling a body.

### 11.2 Per-launch token (cross-site request protection)

At start-up `secrets.token_urlsafe(32)` is generated. `viewer.html` is served with the token
in `<meta name="viewer-token" content="…">`, and `viewer.js` sends it in the `X-Viewer-Token`
header of every `POST`. The server compares with `secrets.compare_digest` and answers 403
`forbidden` without it or with a wrong value. A page on any other origin cannot read the
token; the server answers no `OPTIONS` and sends no `Access-Control-*` header, so a
cross-origin request with the custom header also fails its preflight.

### 11.3 HTTP contract (v0.2)

**Origins.** The two permitted origins are `http://127.0.0.1:<port>` and
`http://localhost:<port>` (D9), computed once at bind time. Rules, evaluated in this order for
every request:

1. `Host` must be exactly `127.0.0.1:<port>` or `localhost:<port>` (case-insensitive host
   part) → otherwise **400** `bad_request`, on every route, before anything is served
   (DNS-rebinding protection).
2. Route by exact path match: `GET /` → `index`; `GET /viewer.css` → `css`; `GET /viewer.js` →
   `js`; `POST /api/chart` → `api_chart`. A query string on any route → **404** `not_found`
   (the page never sends one). Any other path → **404**; a known path with the other of the
   two implemented methods → **405** `method_not_allowed` with `Allow`. Paths are matched,
   never joined to the filesystem.
   **Base-handler paths (v0.3).** `BaseHTTPRequestHandler` itself answers some conditions
   before routing, by calling `send_error`: a method with no `do_<METHOD>` handler (`OPTIONS`,
   `HEAD`, `PUT`, `BREW`, …) → 501; a malformed request line or unsupported HTTP version → 400
   or 505; a request line over 65 536 bytes → 414; more than 100 header lines → 431. Avoiding
   explicit `send_error` calls in our own code is therefore insufficient: the handler
   **overrides `send_error`** so that these paths produce the same JSON error document, the same
   header set and the same route-label logging as every other response (`kind` =
   `not_implemented`, `bad_request`, `uri_too_long`, `headers_too_large`, or `http_<code>` for
   any other code the base class may choose), written through `_respond` (item 4). §13.2 tests
   a malformed request line, an unsupported HTTP version, an over-long request line, too many
   headers, and `OPTIONS`/`HEAD`/`PUT`, and asserts the headers and log line on each.
3. For `api_chart` only:
   - If an `Origin` header is present it must be one of the two permitted origins, exactly;
     **a foreign `Origin` is 403 regardless of any `Sec-Fetch-*` header** (v0.2 correction). If
     `Origin` is absent, `Sec-Fetch-Site` must be present and equal `same-origin`; otherwise
     403. (Fetch from the page always sends `Origin`; the fallback covers browsers that omit it
     on same-origin POSTs while still sending `Sec-Fetch-Site`.)
   - `X-Viewer-Token` must match (§11.2) → otherwise **403** `forbidden`.
   - `Transfer-Encoding` present (any value) → **400** `bad_request` (the page never chunks;
     accepting it would require a second body-reading path).
   - `Content-Length`: exactly one header, `re.fullmatch(r"[0-9]{1,5}")`, value `> 0`;
     missing → **411** `length_required`; duplicate (`headers.get_all` returns more than one),
     non-digit, signed, or zero → **400**; greater than **4096** → **413** `payload_too_large`.
     The body is read only after these checks and only for exactly `Content-Length` bytes.
   - `Content-Type` must be `application/json`, optionally with the single parameter
     `charset=utf-8` (case-insensitive type and parameter; any other parameter or type) →
     **415** `unsupported_media_type`.
   - Body decoding and JSON rules are §9.2 (→ **400** `input`).
4. Responses. The handler never calls `send_response`, and `send_error` is overridden as in
   item 2 (both would append `Server` and `Date` headers through `send_response`;
   `version_string()` returning `""` does **not** suppress them — v0.2 correction). Every
   response, success or error, base-handler path included, is written by one function
   `_respond(status, content_type, body_bytes)` that calls **`send_response_only`**
   (which writes the status line and nothing else), then exactly these headers, then
   `end_headers()` and the body: `Content-Type`, `Content-Length`, `Cache-Control: no-store`,
   `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`,
   `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src
   'self' data:; connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors
   'none'`, and `Allow` on 405. `Connection: close` is implied by HTTP/1.0 (the handler keeps
   the default `protocol_version`). Verified on Python 3.10.12 that `send_response_only` emits
   no `Server` or `Date` header (§14.7). One base-class detail found at implementation (v0.4):
   after a malformed request line or an unsupported version the base handler leaves
   `request_version` at `HTTP/0.9`, for which `send_response_only` and `end_headers` write
   nothing at all; `_respond` therefore normalises it to the server's own version before
   writing, so those paths carry the full document and header set as required. The route
   label of a method mismatch on a known path is `other` (for example `GET /api/chart` logs
   `other 405`).
5. **Logging.** `log_message`, `log_request` and `log_error` are overridden. In normal
   operation the only log line format is `<route-label> <status>` where the label is one of
   `index`, `css`, `js`, `api_chart`, `other` (for any unmatched path or method, including the
   base-handler paths of item 2) — **never the request path, query string, headers or body**,
   so normal logs contain no birth data. The base class's own `Request timed out` message is
   routed through the same override and becomes `other timeout`. **`--verbose` is opt-in
   diagnostics and may contain request data (v0.3 correction):** it adds exception tracebacks for
   `unexpected` errors and for `handle_error`, and exception messages can embed user input (for
   example a place query inside a resolver error, or a date inside a Layer 1 error). The
   start-up banner states this when `--verbose` is on. No guarantee is made about the content
   of verbose output beyond the fact that it goes to stderr and is never written to a file by
   the viewer.

### 11.4 Privacy

No external request of any kind (the page loads only its three local files; CSP enforces it).
No analytics. No cookie, `localStorage`, `sessionStorage` or IndexedDB in `viewer.js` (§13.3).
No application persistence (§4.3). No file export. The birth fields carry
`autocomplete="off"`, which is a **request** to the browser: browsers may still offer their own
form-restore or autofill behaviour, keep the page in the back-forward cache, or record the URL
(which never contains birth data) in history. The viewer cannot make guarantees about the
browser; it makes them about itself.

### 11.5 What this does not protect against

A process on the same machine running as the same user can connect to the loopback port; that
is the accepted trust boundary of a local single-user tool and is the same boundary the CLI has.
There is no TLS because there is no network path.

## 12. Error mapping (server-side; types decide, never messages — Layer 11 §8.4 discipline)

| Condition (caught by type or decided by the contract) | HTTP | `kind` | Notes |
|---|---|---|---|
| `TransportError` (§9.2), `InvalidBirthDateError`, `InvalidBirthTimeError`, `InvalidPlaceQueryError`, `InvalidTimezoneError`, `NonexistentLocalTimeError`, `AmbiguousLocalTimeError` | 400 | `input` | CLI exit 2 equivalents |
| `DashaRangeError` | 400 | `dasha_range` | CLI exit 2 |
| `PlaceNotFoundError` | 404 | `place_not_found` | CLI exit 3 |
| `AmbiguousPlaceError` | 409 | `ambiguous_place` | CLI exit 3; carries all candidates |
| `GeodataError`, `InvalidCoordinateError`, `ConfigurationError` (post-start-up) | 500 | `resource` | CLI exit 4 |
| any other `Exception` (including the engine's bare `RuntimeError` for out-of-coverage dates and Moshier refusal) | 500 | `unexpected` | message is `type: text`; traceback to stderr only under `--verbose`; CLI exit 1 |
| bad `Host`, `Transfer-Encoding`, malformed/duplicate/zero `Content-Length` | 400 | `bad_request` | |
| token/origin failure | 403 | `forbidden` | |
| body shorter than `Content-Length` within the timeout | 408 | `request_timeout` | connection closed |
| missing `Content-Length` | 411 | `length_required` | |
| `Content-Length` > 4096 | 413 | `payload_too_large` | body not read |
| wrong `Content-Type` | 415 | `unsupported_media_type` | |
| unknown path / query string | 404 | `not_found` | |
| known path, the other implemented method | 405 | `method_not_allowed` | `Allow` header |
| method with no handler (base handler, via overridden `send_error`) | 501 | `not_implemented` | |
| malformed request line / unsupported HTTP version / over-long line / too many headers (base handler, via overridden `send_error`) | 400 / 505 / 414 / 431 | `bad_request` / `http_505` / `uri_too_long` / `headers_too_large` | same headers and logging as every response |

The engine's coverage `RuntimeError` is deliberately **not** reclassified by inspecting its
message (Layer 11 §8.4); the page shows the engine's own text under a generic heading.

## 13. Tests

### 13.1 `tests/test_viewer_transport.py` (repository)

Over the fixture database and the real `ephe` directory (as `tests/test_app_dasha.py` does),
exact query `Jalandhar`, both conventions: golden JSON fixture equality for 365.256363; the seven
parity rules of §9.5 against `render_dasha_text(timeline, zone="Asia/Kolkata", depth=3,
precision="second")`; row count 819 and pre-order equal to `dasha_rows(depth=3)`; every
fraction string round-trips to the timeline's `Fraction`; every `utc`/`local` string round-trips
through `datetime.fromisoformat` to the core's instants; `birth_chain` equals
`periods_at_birth()` / `active_periods_at(birth_utc)`; `request.submitted` is the raw input
(`"06:45"` stays `"06:45"`) while `request.normalized.time` is `"06:45:00"`; `engine` equals
the five `D1Meta` fields; both Layer 12 divergence longitudes (via `build_vimshottari` with a
synthetic birth instant, through a timeline-only serialiser path) give `identical: false` and
the documented chains; `decimal_truncated` cases (`4.954710505`, an integer, trailing zeros, a
value whose 10th digit would round up but is truncated); `parse_request` rejects a BOM, invalid
UTF-8, duplicate keys, `NaN`, unknown/missing keys, non-string values, `"1995-3-21"`,
`" 1995-03-21"`, `"１９９５-03-21"` (fullwidth digits), `"1995-03-21T00:00"`, `"6:45"`,
`"06:45:00.5"`, `"365.2500"`, `"365,25"`;
`json.dumps(..., allow_nan=False)` round trip.

### 13.2 `tests/test_viewer_server.py` (repository)

A real server on `127.0.0.1:0` in a thread, over the fixture database
(`tests/fixtures/geodata_fixture.sqlite` — holds the exact queries `Jalandhar` (3 candidates,
2 materially different, dominance), `London` (3, 2, dominance), `Hyderabad` (ambiguous, 2
candidates), `Hyderabad, India` (1 candidate, no dominance), `Springfield` (ambiguous, 5
candidates) and not `Jammu`, which belongs to §14):

- Routes and headers: `GET /` 200 with the token meta and every §11.3 header; `GET /viewer.css`,
  `GET /viewer.js`; `Server` and `Date` headers absent on 200, 400, 403, 404, 405, 501 and 500
  responses; `GET /?x=1` 404; `GET /../viewer.js`, `GET /etc/passwd` 404; `GET /api/chart` 405
  with `Allow: POST`; `POST /` 405 with `Allow: GET`.
- Base-handler paths (§11.3 item 2), each asserting the JSON body shape, the full header set,
  the absence of `Server`/`Date`, and the `other <status>` log line: `OPTIONS /api/chart`,
  `HEAD /`, `PUT /api/chart` → 501 `not_implemented`; a malformed request line (`GARBAGE\r\n`)
  → 400; `GET / HTTP/9.9` → 505; a 70 000-byte request line → 414; 150 header lines → 431.
- Contract: foreign `Host` 400 on every route; `Origin: http://evil.test` 403 even with
  `Sec-Fetch-Site: same-origin`; `Origin: http://localhost:<port>` and
  `http://127.0.0.1:<port>` both 200; no `Origin` + `Sec-Fetch-Site: same-origin` 200; no
  `Origin` + no `Sec-Fetch-Site` 403; missing/wrong token 403; `Transfer-Encoding: chunked` 400;
  missing `Content-Length` 411; two `Content-Length` headers 400; `Content-Length: -5`, `+5`,
  `0`, `5 ` 400; `4097` 413 with the body unread; `text/plain` and `application/json;
  charset=latin-1` 415; `application/JSON; CHARSET=UTF-8` 200.
- Results: 200 for `Jalandhar` (echo exact; `dominance_applied: true`,
  `materially_different_count: 2`, `candidate_count: 3`) and `London`; 409 for `Hyderabad` with
  2 candidates and for `Springfield` with 5; 200 for `Hyderabad, India` with no dominance; 404
  for `Xyzzyville`; 400 for `1995-02-30`, `25:00`, blank place, `"365.2500"`; `dasha_range` and
  `unexpected` paths via a monkeypatched pipeline function.
- Responsiveness (§11.1), with the handler timeout monkeypatched to 1 s: a raw socket opened
  and left idle does not delay a concurrent valid request (served in < 0.5 s); the idle socket
  is closed by the server after the timeout; a request with partial headers is closed after
  the timeout; a `POST` announcing `Content-Length: 100` and sending 3 bytes receives 408 and
  is closed; a body that arrives in two parts with a 0.5 s gap (shorter than the timeout)
  succeeds; after each of these the next valid request succeeds; three concurrent valid
  `POST`s all succeed and their calculations never overlap (a monkeypatched wrapper around the
  pipeline call records enter/exit timestamps and asserts no interleaving; **no assertion is
  made about their completion order**); a client that closes its socket immediately after
  sending a valid request produces at most one stderr line, no traceback, and the server
  answers the next request.
- Lifecycle: `ViewerServer.create` → `serve_forever` in a thread → `shutdown()` returns →
  `server_close()` → the port refuses new connections; `create` on an occupied port raises
  `OSError`; `serve` maps `ConfigurationError` to 4, a metadata failure to 4, bind failure to 5,
  and `KeyboardInterrupt` (injected by monkeypatching `serve_forever`) to 130 with the listening
  socket closed afterwards.
- Hygiene: stderr contains only `<label> <status>` lines and no query string, place, date or
  time; the working tree (excluding `__pycache__`) has no new files after the session; the
  static responses are byte-identical to the package files.

### 13.3 `tests/test_viewer_boundaries.py` (repository)

AST rules of §3.4 for the two Python modules, including the single-function arithmetic carve-out
and the no-comparison rule; the package has exactly four Python modules (`__init__`,
`__main__`, `server`, `transport`) and three static files; public names are exactly
`ViewerConfig`, `ViewerServer` and `serve`; the existing AST tests for `app` and `dasha` keep
passing unchanged except the one Layer 13 consumer test amended under D18 (Layers 1–13
production code untouched); a textual scan of `viewer.js` for `new Date`, `Date.`, `parseFloat`,
`Number(`, `eval(`, `innerHTML`, `outerHTML =`, `insertAdjacentHTML`, `localStorage`,
`sessionStorage`, `indexedDB`, `document.cookie`, `aria-controls`, and `fetch(` with anything
other than the literal `"/api/chart"` — all absent; `viewer.html` contains no `<script>` or
`<style>` element body and no `on*` attribute; `viewer.css` contains no selector beginning with
`#chart` followed by a descendant or child combinator and no bare element selector.
The textual scan is **supplemental** to the browser acceptance script (D12 as revised).

### 13.4 `tools/viewer/acceptance.py` (repository; reproducible browser acceptance)

A Playwright-for-Python script, in the style of `tools/render/rasterise_inspection.py`,
that is **not** imported by the package and not collected by pytest. Its docstring carries the
run instructions; the README subsection repeats the command.

```
PYTHONPATH=src python tools/viewer/acceptance.py --geodata PATH --ephemeris PATH --out DIR
        [--python PATH-TO-INTERPRETER] [--keep-server]
```

- Starts the viewer as a subprocess (`<python> -m vedic_chart.viewer --geodata … --ephemeris …
  --port 0`, with `PYTHONPATH=src` and `PYTHONDONTWRITEBYTECODE=1`), reads the `viewer:` banner
  line for the URL, launches headless Chromium, runs every check below, writes
  `DIR/report.json` (one entry per check: name, pass/fail, measured values), screenshots,
  captured responses and the SVG bytes, stops the server, and exits **non-zero on any failed
  check**. `DIR` must be outside the repository (the script refuses a path inside its own
  checkout).
- Checks (each is one named entry; §14 maps them to the acceptance items):
  `startup_banner`, `reference_jalandhar_365256363`, `reference_jalandhar_36525`,
  `reference_jammu_365256363`, `reference_jammu_36525` (skipped with an explicit `skipped`
  entry when the exact query `Jammu` is not in the configured database), `svg_bytes_equal_cli`
  (runs `python -m vedic_chart.app --out` in a temp dir under `DIR` and compares bytes with the
  response's `svg`), `svg_dom_semantics`, `svg_pixels_equal_standalone` (screenshots the
  inserted element and a standalone rendering of the CLI file at the same pixel width in the
  same Chromium and requires zero differing pixels over every **fully covered** pixel row; when
  the element's CSS height is fractional the screenshot clip rounds up and the last, partially
  covered row shows what lies behind the element, so it is excluded and the PNG bytes may
  differ even though every compared pixel is identical — the report records both the PNG
  hashes and the compared-row count), `table_text_equal_cli` (`--dasha md-ad-pd
  --dasha-zone <birth zone>` compared row by row with the rendered cells), `expand_levels`
  (9 → 18 → 27 visible rows through `Ju` and `Ju-Su`; 819 after Expand all),
  `birth_markers`, `expand_birth_chain_focus_pd` (the focused element after the action is the
  nominal PD row; `document.activeElement.id` is checked), `keyboard_model` (Tab into the
  table, ArrowDown across MD/AD/PD rows, ArrowRight/ArrowLeft, Home/End, Enter, focus
  restoration on collapse and Collapse all), `accessibility_tree` (Playwright's accessibility
  snapshot: `treegrid`, row levels, `expanded` states, the SVG `img` with its name and
  description, the status and alert regions, no `aria-controls`), `divergence_chains` (loads
  `tests/fixtures/viewer/divergence_*.json` through a page hook `window.__loadFixture` that is
  present only when the page is opened with `#acceptance` in the URL; the hook renders a
  transport document without a request and is the only test seam in `viewer.js`),
  `superseded_response` (submit `Jalandhar` then immediately `London`; the final header and
  rows are London's whatever the server's completion order; a burst of three submissions
  records the server's completion order without asserting it and asserts that the page shows
  the third), `errors` (ambiguous
  `Hyderabad` shows exactly 2 candidates and no selection control; `Hyderabad, India` then
  resolves with no dominance notice; `Xyzzyville` 404; `1995-02-30`, `25:00`, blank place and no
  convention are blocked or refused with the focused field), `microseconds_toggle`,
  `stale_inputs_banner`, `mobile_scrolling` (375 px viewport: chart wrapper `scrollWidth >
  clientWidth`, chart element width 600 px, `documentElement.scrollWidth <= clientWidth`),
  `network_routes` (every request URL is one of the four routes on the server's origin; **no
  request to any other origin**; repeated submissions legitimately add `api_chart` requests, so
  the check is on the set of routes and origins, not on a count), `csp_clean` (no
  `securitypolicyviolation` events, no console errors).
- The script is deterministic given the same resources and Chromium build; the report records
  the Chromium version, the Python version, the `dataset_metadata` rows and the `.se1` sizes.

## 14. Acceptance (scratch output, outside the repository; production resources)

Reference flows: exact queries **`Jalandhar`** with 1995-03-21 06:45 and **`Jammu`** with
2001-02-04 10:45, both conventions, over `data/geodata.sqlite` (SHA-256 `8afad22b…`) and
`ephe/`. The committed script of §13.4 produces the evidence; the items below say what the
report must show.

1. **Start-up.** Omitting either resource flag exits 2; a wrong path exits 4 before binding;
   `--port 70000` exits 2; a port already in use exits 5; the banner shows the absolute paths,
   the seven `dataset_metadata` rows and the three `.se1` sizes; `--open` failure (run with
   `BROWSER=/nonexistent`) prints the warning and keeps serving. No file other than
   `__pycache__` appears under the working directory after a session.
2. **Birth input.** `Jalandhar`: `Jalandhar, Punjab, India`, `31.32556`, `75.57917`,
   `Asia/Kolkata`, `+05:30`, GeoNames `1268782`, dominance notice naming 2 materially different
   rivals. `Jammu`: `Jammu, Jammu and Kashmir, India`, `32.73528`, `74.86167`, GeoNames
   `1269321`, notice naming 7. `Hyderabad`: ambiguous, exactly 2 candidates listed, no choice
   made, query text retained. `Hyderabad, India`: resolves, no notice. Invalid `1995-02-30`,
   `25:00`, blank place and no convention: blocked or refused with the described focused field.
   A pre-1906 Kolkata birth shows `+05:21:10`.
3. **Settings.** Header shows the five `D1Meta` descriptors and the submitted year; editing a
   field after a result shows the stale-inputs banner and changes no row.
4. **Unchanged outputs.** `svg_bytes_equal_cli` passes for both births (response string vs CLI
   file, SHA-256 recorded); `svg_dom_semantics` shows `role="img"`, the `d1-title`/`d1-desc`
   ids and texts, the `viewBox`, the same element and text-node counts as the file, and a
   bounding box with the file's 1080:H aspect ratio within one CSS pixel;
   `svg_pixels_equal_standalone` passes at 600 px and 1080 px widths (§16 states the exact
   form of each result);
   `table_text_equal_cli` passes at depth 3 for both conventions and both births, and the MD/AD
   rows for Jalandhar 365.256363 also equal the committed golden
   `tests/fixtures/dasha/jalandhar_md_ad_365256363_second_kolkata.txt`.
5. **Daśā interaction.** Nine rows initially; `expand_levels`, `birth_markers` (N and Q on
   `Ju › Ju-Su › Ju-Su-Me` for Jalandhar and `Ma › Ma-Ra › Ma-Ra-Sa` for Jammu, `identical:
   true`), `expand_birth_chain_focus_pd` (focus on `row-ju-su-me` / `row-ma-ra-sa`),
   `keyboard_model`, `divergence_chains` (both chains, N and Q on different rows, the note),
   `microseconds_toggle`.
6. **Browser checks.** `accessibility_tree`, `superseded_response` (final result is the last
   submission regardless of server completion order; the burst report lists the observed
   completion order as information only),
   `stale_inputs_banner`, `mobile_scrolling`, `network_routes` (routes and origins only, no
   count), `csp_clean`; screenshots at 1280 px and 375 px.
7. **Server contract, without a browser** (`curl` or `http.client` from the report): foreign
   `Host`, foreign `Origin` with `Sec-Fetch-Site: same-origin`, missing token, 5 KB body,
   `Transfer-Encoding: chunked`, missing/duplicate/negative `Content-Length`, `text/plain`,
   `/../`, an idle connection during a valid request, a 3-byte body for `Content-Length: 100`
   (408, then a valid request succeeds), and `http://[::1]:<port>/` (connection refused). The
   Python 3.10.12 probe of these mechanics (`send_response_only` headers, timeout closure,
   408, `handle_error`) is in `~/l14research/probe.py` on the session VM and is repeated
   against the real server here.
8. **Record and provenance.** Evidence in the acceptance environment of D14, report and hashes
   summarised in §16 when this document is promoted to v1.0. The record states the source
   provenance: a SHA-256 list of every copied source, fixture and resource file computed on the
   Mac and again in the acceptance environment, with zero differences, so that the tested source
   is provably the reviewed Mac source; the Python, `pyswisseph`, `timezonefinder`, Playwright
   and Chromium versions; and the production database and `.se1` hashes. The Lahiri validation
   statement of the preamble is repeated in the record.

## 15. Decisions

| # | Decision | Status / recommendation |
|---|---|---|
| D1 | `--geodata` and `--ephemeris` required, no defaults | **Approved.** |
| D2 | Default port OS-assigned, printed; `--port N` optional | **Approved.** |
| D3 | `--open` via stdlib `webbrowser`, failure is a warning | **Approved** (failure handling added, §4.2). |
| D4 | Renderer options `show_degrees=True, mark_node_retrograde=False, caption=False, width=None, id_prefix="d1"` | **Approved.** |
| D5 | Restate Layer 13 presentation rules in `transport.py`, each with a parity test | **Approved**; the rules are now enumerated in §9.5. |
| D6 | Ambiguity list text only, no click-to-select | **Approved.** |
| D7 | "Show microseconds" toggle, default off | **Approved.** |
| D8 | Collapsing an MD forgets its ADs; "Expand birth chain" also opens the quantized chain when it differs | **Approved**; focus restoration added (§8.2). |
| D9 | Accept `localhost:<port>` as well as `127.0.0.1:<port>` | **Approved**; consistent Host/Origin handling in §11.3. |
| D10 | `autocomplete="off"` on birth fields | **Approved**, qualified as a request to the browser (§11.4). |
| D11 | Package `vedic_chart.viewer` with modules `server`, `transport` | **Approved.** |
| D12 | Textual `viewer.js` scan | **Revised as instructed**: retained as supplemental (§13.3); reproducible browser acceptance script committed (§13.4). |
| D13 | Display zone fixed to the birth place's zone | **Approved.** |
| D14 | **Acceptance environment.** No single available environment has both Playwright/Chromium and the project's runtime: the cloud sandbox has Playwright 1.56 with Chromium but not `pyswisseph`/`timezonefinder`; the Mac session VM has the project's `.venv` but no Playwright and no Chromium. | **Approved: option (a)** — an isolated temporary cloud environment. Authorisation is limited to: installing the two exact project runtime pins (`pyswisseph==2.10.3.2`, `timezonefinder==8.2.0`) and their required dependencies there; copying the reviewed source snapshot (tracked files at `2c90e0d` plus the uncommitted Layer 14 files), the required test fixtures, the three ephemeris files and the production geodata database; verifying transferred resource hashes and recording Python, package and browser versions. Not copied: `.git`, credentials, `.venv`, unrelated files, personal saved charts. Nothing is installed into the Mac environment and no project dependency declaration changes. The tested source must hash-match the reviewed Mac source (§14.8). |
| D15 | `ThreadingHTTPServer` + one engine lock replaces the single-threaded server | **Approved** (§2.1, §11.1; exclusion only, no ordering claim — v0.3). |
| D16 | Row-focus treegrid model, no `aria-controls`, non-focusable toggle glyph | **Approved** (§8.2). |
| D17 | Amend the README's Layer 11 `python -m vedic_chart.app` examples to show the `PYTHONPATH=src` prefix, in the same README edit | **Approved** — documentation only; applied to all four examples. |
| D18 | **Layer 13 boundary test conflict (found at implementation).** `tests/test_dasha_boundaries.py::test_only_the_app_package_knows_about_this_layer` asserts that *no* module under `src/vedic_chart` other than the `app` package imports `vedic_chart.dasha`. Layer 14 cannot satisfy it: the viewer needs `dasha_rows`, `DashaRow`, `VimshottariTimeline`, `YearConvention`, `resolve_zone` and `DashaRangeError`, and re-exporting them from `vedic_chart.app` would itself change Layer 11/13 code. The test was written for a codebase without Layer 14; §13.3's claim that the existing AST tests keep passing unchanged was wrong for this one test. Options: (a) amend that one test to exempt `vedic_chart.viewer` under the same surface-only rule it applies to `vedic_chart.app` (the viewer already imports no daśā submodule — the exemption is a one-line addition next to `APP_PACKAGE`); (b) leave the test and accept one permanent failure; (c) re-export the six names from `vedic_chart.app` (changes Layer 11/13 public names and their own boundary tests). | **Approved (a) and applied (v0.5).** `tests/test_dasha_boundaries.py` gains `VIEWER_PACKAGE` and `CONSUMER_PACKAGES = (APP_PACKAGE, VIEWER_PACKAGE)`; the test is renamed `test_only_the_app_and_viewer_packages_consume_this_layer_s_surface` with a docstring stating the rule; both consumers may import the package surface only (the submodule check is unchanged and now applies to both), and every other package is still forbidden to import the layer at all. The file is in the manifest (§3.1). No production code of Layers 1–13 was touched. |

## 16. Validation record (closing revision, 2026-09-13; document still DRAFT)

### 16.1 Changed-file manifest and protected-file verification

Seventeen paths differ from `2c90e0d` on the Mac; nothing else does. Fifteen new files:
`src/vedic_chart/viewer/{__init__,__main__,server,transport}.py`,
`src/vedic_chart/viewer/static/viewer.{html,css,js}`,
`tests/test_viewer_{transport,server,boundaries}.py`,
`tests/fixtures/viewer/{jalandhar_365256363,divergence_su_mo,divergence_ke}.json`,
`tools/viewer/acceptance.py`, `docs/LAYER14_INTERACTIVE_VIEWER_SPEC.md`. Two modified files:
`README.md` (Layer 14 subsection; D17 prefix on four examples) and
`tests/test_dasha_boundaries.py` (D18 only — the sole authorised change to an existing test).
`git diff --quiet 2c90e0d --` over every Layers 1–13 source package, every other existing
test, `tests/fixtures/{dasha,render,geodata_fixture.sqlite}`, `pyproject.toml`, `ephe/`,
`tools/{audit,geodata,render}` and the Layer 9–13 specifications reports **no difference**:
Layers 1–13 production code and the existing fixtures and goldens are unchanged.

### 16.2 Repository tests

Mac (aarch64 session VM, Python 3.10.12, the project's `.venv`): full suite **2447 passed,
0 failed** (the three viewer modules contribute 258; the amended D18 test passes).

Cloud acceptance environment (x86_64, Python 3.11.15, the D14 venv), same source: **2435
passed, 12 failed**. The twelve failures are, exactly: ten **legacy value-pinning tests** of
Layers 12–13 that pin Mac-computed values —
`tests/test_dasha_from_chart.py::test_the_reference_charts_carry_the_recorded_moon[jalandhar|jammu]`,
`::test_the_adapter_equals_the_core_on_the_extracted_values[{jalandhar,jammu}-{FIXED_365_25,FIXED_365_256363}]`,
`::test_the_adapter_reproduces_the_reference_balances[jalandhar|jammu]`,
`tests/test_dasha_table.py::test_the_golden_is_reproduced_byte_for_byte[jalandhar_md_ad_365256363_second_kolkata.txt|jammu_md_36525_day_kolkata.txt]`
— and two **newly introduced Layer 14 golden tests** that pin the Mac-generated transport
document: `tests/test_viewer_transport.py::test_the_golden_transport_document_is_reproduced`
and `::test_the_golden_is_the_encoder_s_own_bytes`. None of these was relaxed, no golden was
regenerated to fit the cloud, and no calculation was tuned. The two divergence fixtures, which
are pure `Fraction` arithmetic over a synthetic instant, are byte-identical on both machines.

### 16.3 Observed environment-dependent numerical differences

For the two tested reference births the engine's Moon sidereal longitude differs between the
two environments at the last few significant digits: Jalandhar `209.20440791222882` (Mac) vs
`209.20440791223328` (cloud); Jammu `54.892295957053236` vs `54.89229595705784`. The exact
Layer 12 balance fractions differ accordingly (Jalandhar `87164189005907/17592186044416` vs
`174328378011627/35184372088832`, both truncating to `4.954710505`). **The cause is not
established.** The two environments differ in CPU architecture (aarch64 vs x86_64), Python
version (3.10.12 vs 3.11.15) and the dependency build environment (the `pyswisseph` wheel and
its compiled Swiss Ephemeris library, `numpy`, `h3`, `cffi`, and `tzdata` from PyPI in the
cloud vs the OS database on the Mac); architecture alone is not shown to be the cause. What
*was* observed to be equal across the two environments, **for the tested reference cases
only** (Jalandhar 1995-03-21 06:45 and Jammu 2001-02-04 10:45, both conventions): every SVG
byte (`a385f87b…2bdca8` Jalandhar, `d4f22f52…c09e34` Jammu) and every second-precision daśā
boundary in the depth-3 tables and in the two committed Layer 13 goldens. No wider
reproducibility claim is made; in particular the ten legacy tests above do not pass in the
cloud, and the viewer golden is a Mac artefact.

### 16.4 Browser acceptance (cloud, D14 environment) — current runs on the final source

`tools/viewer/acceptance.py` was run on the final source (hashes of §16.5) after the v0.5 UI
edits; the earlier runs made before those edits are superseded and not relied on.
Production `data/geodata.sqlite` (SHA-256 `8afad22b…b7a4`): **22 checks pass, 0 fail,
0 skipped**. Fixture database: 20 pass, 0 fail, 2 skipped (the exact query `Jammu` is not in
the fixture). Measured on the production run: `Jalandhar` 3 candidates / 2 materially
different / dominance; `Jammu` 8 / 7 / dominance; `Hyderabad` ambiguous with exactly 2
candidates; `Hyderabad, India` 1 / no dominance; `svg_bytes_equal_cli` for both births;
`svg_dom_semantics`; **`svg_pixels_equal_standalone`: at 1080 px the inserted-element and
standalone screenshots are byte-identical PNGs (1202 rows compared, 0 differing pixels); at
600 px the element is 667.765625 CSS px tall, the 667 fully covered rows compare with 0
differing pixels, the last partially covered row is excluded, and the two PNG files differ in
bytes** (`1919b4f9…` vs `75c095c6…`); `table_text_equal_cli` 819/819 rows for both births ×
both conventions and 90/90 MD–AD rows against the committed Jalandhar golden (header lines
recorded, not asserted — §16.3); `expand_levels` 9 → 18 → 27 → 819 → 9;
`expand_birth_chain_focus_pd` `row-ju-su-me` / `row-ma-ra-sa`; `keyboard_model`;
`accessibility_tree` (treegrid, levels, expanded states, `img` name and description, zero
`aria-controls`); `divergence_chains` (both fixtures, N and Q on different rows, the note);
`superseded_response` (last submission wins; completion order recorded only); `errors`;
`microseconds_toggle`; `stale_inputs_banner`; `mobile_scrolling` (svg 600 px inside a
scrolling wrapper at a 375 px viewport, no page-level horizontal scroll; both scroll hints
hidden at 1280 px and shown at 375 px with their exact texts); `network_routes`; `csp_clean`.
Server exit 130 on every run. Row-block sizes 516 088 B (Jalandhar) and 519 117 B (Jammu).

### 16.5 Provenance and inventory of the acceptance environment

Inventory, so the counts are explicit: **111** = the files `git ls-files` reports at `2c90e0d`
(README, LICENSE, THIRD_PARTY_NOTICES, `.gitignore`, `pyproject.toml`, `data/DATA_SOURCES.md`,
nine `docs/` files, four `ephe/` files, 44 `src/` files, 38 `tests/` files including the
fixture database, goldens and render fixtures, 10 `tools/` files: 5 + 1 + 9 + 4 + 44 + 38 + 10).
**113** = those 111 plus two
untracked paths hashed with them: `docs/LAYER14_INTERACTIVE_VIEWER_SPEC.md` (this document,
new) and `data/geodata.sqlite` (the production resource, git-ignored, 150 712 320 B). All 113
SHA-256 values computed on the Mac matched after transfer to the cloud. The **17** Layer 14
paths of §16.1 were then hashed on both machines and are identical, with one deliberate
exception in the opposite direction: `tests/fixtures/viewer/jalandhar_365256363.json` was
generated on the Mac (`4b3fd00a…`) and copied to the cloud, where it fails as recorded in
§16.2. Resources: `sepl_18.se1` `ca1393ce…`, `semo_18.se1` `1ca07bd6…`, `seas_18.se1`
`a2cd8fc3…`. Versions: Python 3.11.15; `pyswisseph 2.10.3.2` (`swe.version` 2.10.03);
`timezonefinder 8.2.0` with its dependencies `numpy 2.4.6`, `h3 4.5.0`, `cffi 2.1.1`; `pytest
9.1.1`; `tzdata 2026.4` (installed because the container's system tz database lacks
backward-compatibility links such as `America/Argentina/ComodRivadavia` that existing Layer 2
tests use; the Mac provides them from the OS); Playwright 1.56.0; Chromium 141.0.7390.37. Not
copied: `.git`, `.venv`, credentials, anything outside the tracked set. Nothing was installed
on the Mac; `pyproject.toml` is unchanged.

**Independent Lahiri absolute-date validation remains pending; no exact compatibility claim is
made** (preamble). The viewer's page and transport state this.

**Open items.** None; promoted to v1.0 (§16.6).

### 16.6 Promotion and supersession by Layer 15 (v1.0, 2026-09-15)

The owner reviewed the Layer 14 previews and promoted this document together with Layer 15.
Because Layer 15 modified the still-uncommitted Layer 14 implementation, there is no separate
Layer 14 commit: the reviewed final snapshot of both layers is committed together, and the
acceptance figures of §16.2–§16.5 describe the Layer 14 closing snapshot (hashes in §16.5), not
the committed files. The Layer 15 record (`LAYER15_VIEWER_INPUT_FLOW_SPEC.md` §15) is the
validation record of the committed state.

**Sections superseded by Layer 15 v1.0** (identical to Layer 15 §12): §5 (birth input — date
mandatory, time and birthplace optional with labelled defaults, offline autocomplete); §6 (the
year selector — the page fixes `FIXED_365_256363` and states it); §9.2–§9.3 (request/response
shapes — schema `vedic_chart.viewer/2`); §9.4 (`ambiguous_place` removed from the viewer's
vocabulary; `place_selection_required` and `stale_schema` added); §10.1 (validation and focus
rules extended to the combobox); §11.3 item 2 (the route table gains `POST /api/places`) and
the `aria-controls` prohibition of §8.2/§13.3 (narrowed to the treegrid; permitted on the
combobox); §4.2 step 6's banner line `year conventions: …` (now `dasha year convention:
365.256363 days (Mean Sidereal year, fixed by the viewer)`); §13.1–§13.4 and §14 (tests and
acceptance, extended). Everything else — §1's non-goals, §2 architecture, §3 files and import
rules (as extended by Layer 15 §9), §4.2a lifecycle, §7 chart display, §8 treegrid, §11.1–§11.2
and §11.4–§11.5 security and privacy, §12's HTTP-level rows, §16.1–§16.5 — remains in force
and unrevised.

## 17. Change log

- **v1.0** (2026-09-15). Promoted by the owner with Layer 15; status line and §16.6 added; no
  other text changed.
- **v0.5** (closing revision). D18 approved as option (a) and applied; the amended test added
  to the manifest (§3.1, §13.3, §15). Reproducibility claims corrected: the Mac/cloud
  numerical differences are recorded as observed environment-dependent differences with the
  cause not established, the cloud failures are listed exactly and split into legacy
  value-pinning and new viewer-golden tests, and the SVG/second-precision equality statements
  are scoped to the tested reference cases (§16.2, §16.3). Acceptance reporting made precise
  (1080 px byte-identical PNGs; 600 px zero differing pixels over 667 fully covered rows with
  the partial row excluded and differing PNG bytes) and the 111/113/17 file counts
  inventoried (§13.4, §16.4, §16.5). UI wording: application-scoped lede and horizontal-scroll
  hints shown only while a wrapper overflows (§7.2); acceptance re-run on the final source.
- **v0.4** (implementation review). Abbreviations restated rather than imported so the viewer
  uses only the daśā package surface (§3.2, §3.4, §9.5); `serialize(..., rows=None)` (§9.3);
  `request_version` normalisation and the `other` label for method mismatches (§11.3); measured
  response sizes (§2.1); D18 added for the Layer 13 boundary-test conflict (§15); the
  implementation review record and the acceptance provenance (§16; the v0.4 description of the
  numerical difference as an architecture finding is superseded by v0.5 §16.3).
- **v0.3** (implementation approved against this revision). Lock: mutual exclusion only, no
  submission-order or completion-order claim, no FIFO scheduler; tests assert non-overlap and
  latest-wins without asserting order (§2.1, §10.2, §13.2, §13.4, §14.6). Timeouts: per
  blocking-operation bound, not a total deadline; byte bounds stated (§11.1). Base-handler
  paths: `send_error` overridden so 501/400/505/414/431 use the same response, headers and
  logging; tested (§11.3, §12, §13.2). Logging: normal logs omit birth data; `--verbose` is
  opt-in and may contain request data (§11.3). Shutdown: listening socket vs accept loop vs
  daemon workers distinguished; abandoned in-flight calculation and ephemeris cleanup stated;
  `ViewerServer.create`/`serve`/`main` lifecycle defined; public names `ViewerConfig`,
  `ViewerServer`, `serve` (§4.2, §4.2a, §3.1, §13.3). D14–D17 recorded as approved with the
  D14 authorisation limits (§15).
- **v0.2.** Threaded server with engine lock and bounded read timeouts,
  disconnect handling (§2.1, §11.1); exact echo of submitted strings plus normalized values,
  supersede/cancel model, stale-inputs banner, abort-vs-calculation distinction (§9.3, §10);
  row-focus treegrid model with PD rows focusable, focus restoration, no `aria-controls`,
  "Expand birth chain" focuses the nominal PD row, depth-1 reference removed (§8.2); SVG byte
  equality required on the response string only, DOM checked semantically and by pixels
  (§7.3, §14.4); full HTTP contract — Content-Type/Length/Transfer-Encoding, strict date/time
  syntax with ASCII digit classes (Python's `\d` admits Unicode digits), duplicate JSON keys,
  Host/Origin rules, route-label logging, `send_response_only` as the header mechanism (§9.2,
  §11.3, §12); convention labels from `D1Meta`, no ephemeris
  version string (§6); arithmetic carve-out for one presentation function and enumerated
  restated rules with parity tests (§3.4, §9.5); executable start-up command with
  `PYTHONPATH=src`, failure handling for metadata, ports and `--open`, socket cleanup, qualified
  persistence and autocomplete statements (§4, §11.4); committed acceptance script with named
  checks, route-set network assertion, exact place-query strings throughout (§13.4, §14);
  manifest and import rules updated (§3); decisions D14–D17 added.
- **v0.1.** Initial proposal.
