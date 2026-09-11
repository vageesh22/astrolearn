# Layer 11 — Public end-to-end entry point — SPECIFICATION v1.0

**Status:** v1.0 — **APPROVED.** Implemented against DRAFT v0.3 (v0.2 plus the four owner
corrections: conservative failed-output cleanup, non-regular destinations and the normalised
destination path, broken-pipe handling confined to the executable boundary, and consistency
fixes) and promoted after the pre-commit review recorded in §13; the promotion changed no
behaviour — v1.0 differs from v0.3 only in §3 (the derived `ephemeris_files` field shown in the
API block), §9 (`__main__` imports `run`, as implemented) and the new §13. This layer
composes the frozen calculation contract (`docs/CALCULATION_SPEC.md`, FROZEN v1.0, commit
`2b3a5a9`), the Layer 9 representation (`docs/LAYER9_D1_REPRESENTATION_SPEC.md` v1.0, `5f076fd`)
and the Layer 10 renderer (`docs/LAYER10_D1_RENDERER_SPEC.md` v1.0, `e6c60b5`) into one call and
one command. It changes none of them, computes nothing, and adds no astrology, no web API and no
UI.

Owner decisions carried into v0.2: a Python function **and** a thin CLI, both in
`vedic_chart.app`; `render_birth_chart` returns a `ChartResult` with `request`, `chart`, `d1`,
`svg`, `resolution`; `ChartConfig` requires explicit geodata and ephemeris paths; CLI-only
defaults may be relative to the current working directory and are documented as such; the
resolver's ambiguity/dominance behaviour is preserved with no pick-first or choose-by-index
option; existing typed exceptions propagate unchanged; `id_prefix` is passed through and exposed
as `--id-prefix` with no counter, random id or helper; no `from_components` convenience wrapper
and no `--print-chart`. Decisions closed in v0.2: **no** local-year coverage guard and **no**
`EphemerisCoverageError` (a local calendar year is not an exact test of UTC ephemeris coverage;
the engine's existing boundary behaviour is preserved and its bare `RuntimeError` maps to exit
1, §7); the CLI accepts `HH:MM` and `HH:MM:SS` and defers fractional seconds while the Python
request API keeps its existing microsecond precision; `--out` is required, with `--out -` for
stdout; caller-managed ephemeris sessions are deferred; a short README update belongs to the
later implementation milestone.

```
BirthChartRequest ──► OfflineLocationResolver.resolve_with_details ──► (location, decision)
        │                                                                      │
        └──► assemble_chart(request, _PreresolvedResolver(location)) ──► BirthChart ◄──┘ (same object)
                     └──► build_d1_chart ──► D1Chart ──► render_north_indian_svg ──► svg
                                                     ChartResult(request, chart, d1, svg, decision)
```

## 1. Scope and non-goals

In scope: `vedic_chart.app.pipeline.render_birth_chart` (the entry point), `ChartConfig`,
`ChartResult`, `ConfigurationError`; `vedic_chart.app.cli` and `vedic_chart.app.__main__` so that
`python -m vedic_chart.app` works without any packaging change; tests. Out of scope: batch
rendering, a caller-managed ephemeris session, any other renderer or output format, JSON export
of the chart, interactive disambiguation, console-script entries in `pyproject.toml`, fractional
seconds on the command line, and anything the frozen layers do not already provide.

## 2. Package layout and public names

```
src/vedic_chart/app/__init__.py     docstring; re-exports render_birth_chart, ChartConfig,
                                    ChartResult, ConfigurationError
src/vedic_chart/app/pipeline.py     the function and its types (reads resources; writes nothing)
src/vedic_chart/app/cli.py          argparse front end: run(argv) -> (exit_code, stdout_broken);
                                    main(argv: list[str] | None = None) -> int
src/vedic_chart/app/__main__.py     calls run(); redirects stdout to os.devnull only when
                                    stdout_broken (§8.3); raise SystemExit(exit_code)
```

## 3. Minimal API

```python
@dataclass(frozen=True)
class ChartConfig:
    geodata_path: Path            # required; the SQLite database built by tools/geodata/build_db.py
    ephemeris_path: Path          # required; the directory holding the three frozen .se1 files
    ranking_config: RankingConfig | None = None   # forwarded to OfflineLocationResolver unchanged
    ephemeris_files: tuple[Path, ...] = field(init=False)   # derived in __post_init__ (§3.1); never passed

@dataclass(frozen=True)
class ChartResult:
    request: BirthChartRequest    # the request as given (identity)
    chart: BirthChart             # the frozen engine's chart (identity)
    d1: D1Chart                   # build_d1_chart(chart) (identity; d1.source is chart)
    svg: str                      # render_north_indian_svg(d1, options), verbatim
    resolution: ResolutionDecision  # the one resolution the chart was built from

class ConfigurationError(ValueError): ...   # a ChartConfig field is unusable (§3.1)

def render_birth_chart(
    request: BirthChartRequest,
    config: ChartConfig,
    options: NorthIndianOptions = NorthIndianOptions(),
) -> ChartResult
```

`render_birth_chart` **always renders**: every call resolves, assembles, builds the D1 view and
produces the SVG. The intermediate objects are returned by identity for auditability and reuse,
not as a way to skip rendering. A caller who needs only a `BirthChart` keeps using the existing
Layer 8 API (`assemble_chart` with a resolver inside an `ephemeris_session`), exactly as the
README shows; this layer does not replace it.

Argument validation, before resolution or calculation begins: `request` must be a
`BirthChartRequest`, `config` a `ChartConfig`, `options` a `NorthIndianOptions` — `ValueError`
otherwise, in the project's style. (Note that constructing a `ChartConfig` already opens the
configured files briefly for the readability probes of §3.1; "before resolution or calculation"
is the precise statement everywhere in this document.) The birth date is **not** range-checked here: the frozen engine decides
ephemeris coverage at calculation time in UT (§7).

### 3.1 `ChartConfig` validation (at construction, in `__post_init__`)

Every failure raises `ConfigurationError` naming the field and the offending value; the checks
run in the order listed and stop at the first failure.

- **Types.** `geodata_path` and `ephemeris_path` must be `str` or `os.PathLike` (not `bytes`,
  not `None`, not `bool`/`int`); anything else is rejected before any filesystem access. The
  dataclass declares `geodata_path: Path`, `ephemeris_path: Path`, `ranking_config:
  RankingConfig | None = None` and `ephemeris_files: tuple[Path, ...] = field(init=False)`.
- **Normalisation.** Each path is converted with `Path(value).expanduser().resolve(strict=True)`
  and the **absolute, symlink-resolved** result is stored back on the frozen instance (via
  `object.__setattr__`), so a later change of the working directory cannot change what the
  configuration means and so that the alias checks of §8.2 compare canonical paths. A path that
  does not exist fails here (`resolve(strict=True)` raises `FileNotFoundError`, reported as
  `ConfigurationError`).
- **Access errors.** Any `OSError` raised while resolving or `stat`-ing a path — including
  `PermissionError` on a directory that cannot be traversed — is reported as
  `ConfigurationError` carrying the OS message; it is not allowed to escape as a bare `OSError`.
- **Geodata.** `geodata_path` must be a regular file (`is_file()`; a directory, socket or broken
  symlink fails) and readable: the check opens it for reading and closes it immediately
  (`open(path, "rb").close()`), so an unreadable file fails at configuration time rather than
  deep in the resolver. Nothing more is checked here: the schema check belongs to the resolver's
  own `db.connect`, which opens the file read-only/immutable and raises `GeodataError` when any
  `REQUIRED_TABLES` entry is missing (§7); duplicating it would be a second source of truth.
- **Ephemeris.** `ephemeris_path` must be a directory, and each of the three files the frozen
  contract names must exist **as a regular file with the recorded size** — `sepl_18.se1`
  484,061 bytes, `semo_18.se1` 1,304,771 bytes, `seas_18.se1` 223,004 bytes (the table in
  `docs/CALCULATION_SPEC.md`) — and be readable (opened and closed as above). A missing file, a
  non-regular entry, a size mismatch or an unreadable file is a `ConfigurationError` that names
  the file and the expected size. Other files in the directory (the licence notice, additional
  `.se1` ranges) are ignored. **The size check is a compatibility check against the frozen
  contract, not proof of file integrity**: content is not hashed, and the engine's own
  Moshier-refusal guard remains the runtime backstop for corrupt or wrong-content files (§7).
  The three resolved file paths are kept on the instance as **`ephemeris_files: tuple[Path,
  ...]`, a derived field declared `field(init=False)`** and set in `__post_init__`, so it can
  neither be passed by a caller nor drift from `ephemeris_path`; §8.2 uses it for the alias
  checks.
- **Ranking.** `ranking_config` must be `None` or a `RankingConfig` instance; anything else is a
  `ConfigurationError`.

## 4. Resolve the birthplace exactly once

`assemble_chart(request, resolver)` calls `resolver.resolve(request.place_query)` itself and
records the returned `ResolvedLocation` on the chart. Resolving with details first and then
handing `assemble_chart` the offline resolver would resolve twice — two database searches, two
timezone lookups, and a `ResolutionDecision` that is not provably the one the chart used.

The pipeline resolves once and feeds the result back through the Layer 8 contract unchanged via
an explicit private adapter:

```python
class _PreresolvedResolver:
    """LocationResolver over one already-resolved location (protocol-conformant)."""
    def __init__(self, place_query: str, location: ResolvedLocation) -> None: ...
    def resolve(self, place_query: str) -> ResolvedLocation:
        if place_query != self._place_query:      # defensive; assemble_chart passes request.place_query
            raise RuntimeError("internal: assemble_chart asked for a different place query")
        return self._location
```

Sequence: `with OfflineLocationResolver(config.geodata_path, config.ranking_config) as
resolver:` → `location, decision = resolver.resolve_with_details(request.place_query)` → the
resolver is closed on leaving the block → `with ephemeris_session(str(config.ephemeris_path)):
chart = assemble_chart(request, _PreresolvedResolver(request.place_query, location))` → after
assembly the pipeline asserts `chart.location is location` (identity, the discipline Layer 9
uses) and raises `RuntimeError("internal: …")` otherwise → `d1 = build_d1_chart(chart)` →
`svg = render_north_indian_svg(d1, options)`. `ChartResult.resolution` is `decision`.
`assemble_chart`, `LocationResolver`, `OfflineLocationResolver` and `ResolutionDecision` are used
as they exist; no frozen file changes. (`tests/render_helpers.py` already uses the same pattern
as `FixedResolver`.)

## 5. Input validation

Nothing new: `BirthChartRequest` (Layer 1) rejects malformed kinds; `from_components` rejects
impossible calendar values with `InvalidBirthDateError` / `InvalidBirthTimeError` and blank
places with `InvalidPlaceQueryError`; the resolver rejects unknown and ambiguous places; Layer 3
rejects nonexistent and ambiguous wall times. Ephemeris coverage (1800–2399, in UT) is decided
by the engine at calculation time and is not pre-checked (§7).

## 6. Resource lifecycle and concurrency

- **Geodata**: `OfflineLocationResolver` opens the SQLite file read-only and immutable
  (`mode=ro&immutable=1`) and is a context manager; the pipeline opens it with `with`, resolves,
  and closes it before the ephemeris is opened. It is never kept open across calls.
- **Ephemeris**: `ephemeris_session(path)` calls `swe.set_ephe_path` on entry and `swe.close()`
  on exit; both act on **process-global state inside the Swiss Ephemeris C library**. The
  pipeline opens one session per call, around `assemble_chart` only; the context manager closes
  it in `finally`, including on every failure path. Consequences, stated as limitations of the
  existing engine and not redesigned here: calls to `render_birth_chart` must be **sequential
  within a process**; the function must not be called while any other `ephemeris_session` is
  open (nesting would close the outer session's files on exit); thread safety of the underlying
  library is **not verified** and must not be assumed; parallel rendering, if ever wanted, is a
  separate-processes matter. Re-opening the ephemeris per call is accepted for this milestone; a
  caller-managed session is deferred.
- The function **reads** the geodata file and the ephemeris files and **writes nothing**: no
  output files, no caches, no temporary files, no logging handlers. Writing is the CLI's job.

## 7. Errors

Existing typed exceptions propagate unchanged from `render_birth_chart`; the pipeline adds only
`ConfigurationError` (a `ValueError` subclass in `vedic_chart.app.pipeline`) and the two internal
`RuntimeError`s of §4. Where the exceptions live:

| Exception | Module | Raised when |
|---|---|---|
| `InvalidBirthDateError`, `InvalidBirthTimeError`, `InvalidPlaceQueryError` | `vedic_chart.inputs.model` | Layer 1 request validation |
| `PlaceNotFoundError`, `AmbiguousPlaceError` (with `.candidates`), `InvalidCoordinateError` | `vedic_chart.location.model` | resolver |
| `GeodataError` (subclass of `RuntimeError`) | `vedic_chart.location.offline.db` | database missing at open, or required tables missing |
| `InvalidTimezoneError`, `NonexistentLocalTimeError`, `AmbiguousLocalTimeError` | `vedic_chart.time.local_time` | Layer 3 |
| `ValueError` (renderer options, e.g. bad `id_prefix`/`width`) | `vedic_chart.render.north_indian` | `NorthIndianOptions` construction |
| `ConfigurationError` | `vedic_chart.app.pipeline` | §3.1 |

**Engine boundary behaviour, preserved.** Layer 5 raises a **bare `RuntimeError`** ("Swiss
Ephemeris did not use the .se1 data files … refusing the Moshier fallback") both for an instant
outside the files' 1800–2399 UT coverage and for missing or unusable files (verified: the two
paths produce the same exception). Layer 8's ayanamsha-consistency check also raises a bare
`RuntimeError`. This layer neither pre-empts nor reclassifies them: the CLI classifies by
exception **type only**, never by message, so these map to the generic exit code 1 (§8.4). The
§3.1 file checks catch the common *configuration* cause (wrong directory, wrong files) with a
typed error before the engine runs; an out-of-coverage birth remains an exit-1 case with the
engine's own message, which is the documented limitation of the frozen contract.

## 8. CLI

Invocation is `python -m vedic_chart.app` (via `app/__main__.py`); no console script is added to
`pyproject.toml`, so packaging is unchanged. Run from any directory with `src` importable (an
editable install or `PYTHONPATH=src`, as for the tests).

```
python -m vedic_chart.app --date YYYY-MM-DD --time HH:MM[:SS] --place "QUERY"
                          (--out PATH | --out -) [--force]
                          [--geodata PATH] [--ephemeris PATH]
                          [--caption] [--no-degrees] [--mark-node-retrograde]
                          [--width N] [--id-prefix PREFIX] [--verbose]
```

- `--date`, `--time`, `--place` and `--out` are required. `--time` accepts `HH:MM` or `HH:MM:SS`
  (24-hour); fractional seconds are rejected by the argument parser (exit 2) and deferred. The
  CLI parses the components into integers and calls `BirthChartRequest.from_components(year,
  month, day, hour, minute, second, place_query=...)` — it never constructs a `datetime`, so no
  zone can be smuggled past Layer 3. The Python API keeps Layer 1's full precision
  (`datetime.time` with microseconds) untouched.
- `--geodata` defaults to `data/geodata.sqlite` and `--ephemeris` to `ephe`, **both relative to
  the current working directory at the moment the command runs** (the project root when run
  from it). These defaults exist in the CLI only; `ChartConfig` has none and stores the absolute,
  resolved paths (§3.1). `--verbose` echoes the absolute paths used.
- `--out PATH` writes the SVG file; `--out -` writes it to stdout. Omitting `--out` is a usage
  error (exit 2); the CLI never invents a filename.
- `--caption`, `--no-degrees`, `--mark-node-retrograde`, `--width`, `--id-prefix` map 1:1 to
  `NorthIndianOptions(caption=…, show_degrees=…, mark_node_retrograde=…, width=…,
  id_prefix=…)`. `--id-prefix` is the caller's responsibility when embedding several charts in
  one HTML document (Layer 10 §2 U-7); the CLI produces one document per run and adds no
  uniqueness logic.
- `--verbose` prints, to stderr, the resolved configuration paths, the canonical place, the
  resolution decision (chosen candidate, whether dominance was applied and why) and, on an
  unexpected error, the traceback.

Order of operations in `cli.run` (shared by `cli.main`), so that a doomed run costs as little as possible (the only
filesystem work before step 5 is `ChartConfig`'s readability probes): (1) argument parsing;
(2) `NorthIndianOptions(...)` construction — the only place a renderer `ValueError` is caught
(exit 2); (3) `BirthChartRequest.from_components(...)` (Layer 1 errors → exit 2); (4) `ChartConfig`
(→ exit 4); (5) output destination pre-check, §8.2 (→ exit 5) — before any resolution or
calculation; (6) `render_birth_chart`; (7) the write, §8.3 (→ exit 5).

Examples:

```bash
python -m vedic_chart.app --date 1995-03-21 --time 06:45 --place "Jalandhar" --out jalandhar.svg
python -m vedic_chart.app --date 2003-12-09 --time 04:00 --place "Bharatpur, Rajasthan" \
        --caption --out - > bharatpur.svg
python -m vedic_chart.app --date 1995-03-21 --time 06:45:30 --place "Jalandhar" \
        --id-prefix chart-1 --width 800 --out charts/j1.svg --force
python -m vedic_chart.app --date 1995-03-21 --time 06:45 --place "Springfield" --out s.svg
# -> stderr: 'Springfield' matches several materially different places: ... ; exit 3
```

### 8.1 stdout / stderr

stdout carries **only the SVG bytes, and only when `--out -`** is selected; in every other case
the CLI writes nothing to stdout. The one intentional exception is `--help` (and `argparse`'s
`--version`-style output if ever added): `argparse` prints usage/help to stdout and exits 0, as
is conventional. All diagnostics — errors, candidate lists, `--verbose` output — go to stderr.

The SVG is written as `svg.encode("utf-8")` exactly as the renderer returned it: no BOM, nothing
added, nothing removed (the renderer's contract already ends its document with a single newline;
the CLI neither relies on nor alters that). With `--out -` the bytes go to `sys.stdout.buffer`,
which is flushed. Note that `> file` in an example is **the shell's** redirection: the shell
creates or truncates that file before the CLI runs, so none of the CLI's overwrite protection of
§8.2 applies to it — the CLI only guarantees that what it writes to stdout is exactly the SVG.

### 8.2 Output destination policy (pre-check, before resolution or calculation)

With `--out -` there is nothing to check. With `--out PATH`, the CLI first forms the
**normalised destination** `dest = PATH.parent.resolve(strict=True) / PATH.name` (the parent
canonicalised, the final component kept literal so that a symlink *as the final component* is
still detectable) and uses `dest` for every check below **and** for every write in §8.3 — never
the raw `PATH`.

1. **Parent.** `PATH.parent` must exist and be a directory; any `OSError` from resolving it, or a
   missing/non-directory parent → exit 5. The CLI never creates directories.
2. **Symlink.** If `dest` is a symlink (`os.path.islink`), refuse (exit 5, "output path is a
   symbolic link; give the real path") regardless of `--force`: the CLI never writes through a
   link it did not create, and `os.replace` onto a symlink would replace the link, not its
   target. Symlinks in the parent directories are followed normally (they are part of the
   directory tree, not of the file being created).
3. **Non-regular.** If `dest` exists and is not a regular file — a directory, FIFO, socket,
   device or anything else `stat.S_ISREG` rejects — refuse (exit 5) regardless of `--force`.
   Writing into a FIFO or device is never what "write the SVG file" means, and `os.replace` onto
   a directory fails anyway.
4. **Protected aliases.** Refuse, **even with `--force`** (exit 5, "refusing to write over an
   input resource"), when `dest` equals `config.geodata_path` or any of
   `config.ephemeris_files` (all canonical absolute paths, §3.1), or — when `dest` exists — when
   `os.path.samefile(dest, resource)` is true for any of them (this catches hard links and any
   other alias by device and inode). If `samefile` raises `OSError` the destination is treated
   as not verifiable and refused (exit 5).
5. **Existence.** If `dest` exists (necessarily a regular file after step 3) and `--force` is
   absent → exit 5, "refusing to overwrite; pass --force". This pre-check gives a fast, clear
   refusal; the race protection is in §8.3.

### 8.3 Safe writes, cleanup policy and their guarantees

All writes target `dest` from §8.2.

- **Without `--force` (direct write).** After rendering, the file is created with
  `fd = os.open(dest, O_WRONLY | O_CREAT | O_EXCL, 0o644)` and the bytes are written through
  that descriptor, then it is closed. `O_EXCL` makes creation atomic with respect to other
  processes: a file that appeared between the pre-check and the write causes `FileExistsError`
  → exit 5, and that file is never touched. **This path is a direct write, not an atomic
  replacement**: a reader that opens `dest` while the CLI is still writing can observe partial
  content; the guarantee is only that the CLI never overwrites a pre-existing file here.
- **With `--force` (atomic replacement).** The bytes are written to a temporary file created by
  `tempfile.NamedTemporaryFile(dir=dest.parent, prefix=f".{dest.name}.", suffix=".tmp",
  delete=False)`, `flush()`ed and `os.fsync()`ed, closed, and moved into place with
  `os.replace(tmp, dest)`. Replacing an existing file is the explicitly authorised effect of
  `--force`; it is the only way the CLI ever replaces a file it did not create in this run.
- **What "atomic" means here, and what it does not.** `os.replace` is an atomic *rename* on the
  same filesystem: any reader opening `dest` sees either the complete old file or the complete
  new file, never a partial one, and a failure of the CLI *before* the rename leaves the old
  file intact. This guarantee is scoped to `--force`. It is **not** a durability guarantee:
  after `os.replace` returns, the new directory entry may not yet be on stable storage — the
  CLI fsyncs the file's contents but does not fsync the parent directory, so a power loss
  immediately after a successful run can, on some filesystems, lose the rename. The CLI makes no
  claim beyond "a process that observes `dest` observes a complete file, and a failure reported
  by the CLI did not replace the destination".
- **Conservative cleanup after a failed write.** Having created a file earlier does not prove
  the path still refers to it — another process may have replaced or removed it meanwhile. So
  the CLI never unlinks a destination or temporary path unconditionally. While it still holds
  the descriptor of the file it created (`fd` on the direct path, the temporary file's
  descriptor on the `--force` path), it compares `os.fstat(fd)` with `os.stat(path)`: if
  `st_dev` and `st_ino` match, the path still refers to our file and it is unlinked, and stderr
  says "removed partial output PATH"; if they differ, or `os.stat` fails, the path is **left
  alone** and stderr says "partial output may remain at PATH; not removed because the path no
  longer refers to the file this run created". The comparison itself has a small window before
  the unlink, and the CLI does not claim immunity to arbitrary concurrent changes to the
  directory — only that it never removes a path it has positive evidence is not its own file,
  and that any leftover is reported. On the `--force` path the destination itself is never a
  cleanup target: only the temporary file is.
- **Cleanup failures are reported, never hidden.** If unlinking our file fails with `OSError`,
  stderr gets a second line, "warning: could not remove partial output PATH: <OS message>",
  after the original error; the original error and its exit code are unchanged.
- **Errors.** Any `OSError` raised by the output operations only — creating, writing, syncing,
  closing, replacing, or writing/flushing stdout — is an output error (exit 5) with the OS
  message. `OSError`s from anywhere else (resource access inside the pipeline, §7) are not
  caught by this handler and fall through to their own classification.
- **stdout and broken pipes.** With `--out -`, if writing or flushing `sys.stdout.buffer` raises
  `BrokenPipeError` (the reader closed early, e.g. `| head`), `cli.run` reports "stdout closed by
  reader" on stderr and returns exit 5 together with a flag saying stdout is broken; it performs
  **no** process-wide redirection, because `cli.main(argv)` may be called in-process (tests, a
  host program) and must not alter the host's file descriptors. The executable boundary
  `app/__main__.py` is the only place that, when the flag is set, redirects the process's stdout
  to `os.devnull` — `fd = os.open(os.devnull, os.O_WRONLY); os.dup2(fd, sys.stdout.fileno());
  os.close(fd)` — so that the interpreter's final flush at shutdown cannot raise again and print
  a second traceback; it then exits with the code. Concretely: `cli.run(argv) -> tuple[int,
  bool]` is the primitive, `cli.main(argv) -> int` returns its first element, and `__main__`
  calls `run`. Other `OSError`s on stdout are exit 5 without the redirection.

### 8.4 Exit codes (by exception type only)

| Exit | Meaning | Exception types / conditions |
|---|---|---|
| 0 | SVG written | — |
| 2 | invalid input or arguments | `argparse` usage errors (its own exit 2, including a missing `--out` and a fractional `--time`); `InvalidBirthDateError`, `InvalidBirthTimeError`, `InvalidPlaceQueryError`; `InvalidTimezoneError`, `NonexistentLocalTimeError`, `AmbiguousLocalTimeError` (message states the gap/overlap); `ValueError` raised by `NorthIndianOptions(...)` (`--id-prefix`, `--width`), caught around that construction only |
| 3 | place not resolved | `PlaceNotFoundError`; `AmbiguousPlaceError` — stderr lists up to five candidates as `name, admin1, country (pop N)` plus the resolver's own hint to add a qualifier; no automatic choice is ever made |
| 4 | configuration / resources | `ConfigurationError`; `GeodataError`; `InvalidCoordinateError` (geodata produced an invalid coordinate) |
| 5 | output | §8.2 pre-check refusals (parent, symlink, non-regular destination, protected alias, exists without `--force`); `FileExistsError` from `O_EXCL`; any `OSError` raised by the output operations of §8.3, including `BrokenPipeError` on stdout |
| 1 | unexpected | anything else, including the engine's bare `RuntimeError`s of §7 (out-of-coverage instant, Moshier refusal, ayanamsha inconsistency); one-line message, traceback only with `--verbose` |
| 130 | interrupted | `KeyboardInterrupt` |

The catch order in `cli.run` is specific-to-general by type, and each handler is scoped to the
stage it belongs to (§8, order of operations): the renderer `ValueError` handler wraps only
`NorthIndianOptions(...)`; the output `OSError` handler wraps only the write of §8.3; resource
errors raised inside `render_birth_chart` (a `PermissionError` opening the database, say) are
`OSError`s too but are never reached by the output handler — they propagate to the generic
handler (exit 1) unless they are one of the typed classes above. This is deliberate: the pipeline
turns the configuration-time access errors it can foresee into `ConfigurationError` (§3.1), and
anything the engine raises untyped stays untyped.

## 9. Import rules (AST-enforced by tests)

Both modules import the standard library freely (`argparse`, `dataclasses`, `os`, `sys`,
`tempfile`, `pathlib`, `datetime`, `contextlib`, `typing`). Internal imports within the package
are allowed and expected: `cli` imports from `pipeline`; `__init__` re-exports from `pipeline`;
`__main__` imports `run` from `cli` (not `main`: it needs the `stdout_broken` flag of §8.3, which
`main` discards).

`vedic_chart.app.pipeline` may import: `vedic_chart.inputs.model` (`BirthChartRequest`);
`vedic_chart.location.model` (`LocationResolver`, `ResolvedLocation`);
`vedic_chart.location.offline.resolver` (`OfflineLocationResolver`);
`vedic_chart.location.offline.search` (`RankingConfig`, `ResolutionDecision`);
`vedic_chart.chart.assemble` (`assemble_chart`); `vedic_chart.chart.model` (`BirthChart`, for
typing); `vedic_chart.astronomy.positions` (**`ephemeris_session` only** — the sanctioned
session boundary; nothing else from that module); `vedic_chart.representation.d1` (`D1Chart`,
`build_d1_chart`); `vedic_chart.render` (`NorthIndianOptions`, `render_north_indian_svg`).

`vedic_chart.app.cli` may import: `vedic_chart.app.pipeline` (any public name);
`vedic_chart.render` (`NorthIndianOptions`); `vedic_chart.inputs.model` (`BirthChartRequest` —
needed for `from_components` — and its three `Invalid*Error` classes); and **exception classes
only** from `vedic_chart.location.model` (`PlaceNotFoundError`, `AmbiguousPlaceError`,
`InvalidCoordinateError`), `vedic_chart.location.offline.db` (`GeodataError`) and
`vedic_chart.time.local_time` (`InvalidTimezoneError`, `NonexistentLocalTimeError`,
`AmbiguousLocalTimeError`). The AST test checks the imported *names*, so importing a function from
`time.local_time` or `location.offline.db` fails the test even though the module is on the list.

Forbidden for both: `swisseph`, `vedic_chart.ephemeris`, `.sidereal`, `.vedic`, `.lagna`,
`.time.julian_day`, `.location.static_resolver`, `tools.*`, any name from
`vedic_chart.astronomy.positions` other than `ephemeris_session`, and any network access.
Neither module calls `round()` or performs arithmetic on chart values.

## 10. Tests (self-contained: committed fixture DB `tests/fixtures/geodata_fixture.sqlite` + `ephe/`)

All tests run without the production database; none is skipped for its absence, and none
depends on the test user's privileges — where a real permission change would be unreliable
(root, CI sandboxes, Windows), the failure is **injected** with `monkeypatch` on the exact call
(`os.open`, `os.replace`, `builtins.open`, `os.fsync`, `Path.resolve`, `os.path.samefile`,
`sys.stdout.buffer.write`) rather than produced with `chmod`. The fixture already contains the
needed places (verified): Jalandhar, London (`Europe/London`, DST), "New York City"
(`America/New_York`), "Springfield" (five US states → ambiguous), "Hyderabad" (India vs Pakistan
→ ambiguous; "Hyderabad, India" resolves). The fixture's "Bharatpur" is a different settlement
from the audit birthplace and is **not** used; the fixture is not modified.

**A. Pipeline.**
- Jalandhar reference round trip: `ChartResult.chart` equals the chart the existing Layer 8/9
  tests build; `ChartResult.svg` is **byte-identical** to
  `tests/fixtures/render/jalandhar_nocaption_degrees.svg` with default options and to the
  caption / no-degrees goldens with the matching options; `result.d1.source is result.chart`;
  `result.request is request`; `result.resolution.chosen.name == "Jalandhar"`.
- Single resolution: with `OfflineLocationResolver.resolve_with_details` wrapped by a counting
  spy and `.resolve` by a failing spy, one call → `resolve_with_details` called exactly once,
  `resolve` never, and `result.chart.location is` the object the spy returned.
- Ambiguity: "Springfield" and "Hyderabad" raise `AmbiguousPlaceError` with ≥ 2 candidates and
  the ephemeris is never opened (spy on `ephemeris_session`); "Hyderabad, India" succeeds.
  Not found: "Xyzzyville" → `PlaceNotFoundError`.
- DST: London 2023-03-26 01:30 → `NonexistentLocalTimeError`; London 2023-10-29 01:30 →
  `AmbiguousLocalTimeError`; London 2023-07-01 12:00 succeeds with `chart.moment_utc` at 11:00
  UTC.
- Boundary dates, compatibility with the existing engine (no guard in this layer): a birth on
  1800-01-01 12:00 in Jalandhar and on 2399-12-31 12:00 in Jalandhar render successfully (both
  instants lie inside the files' UT coverage); a birth in 1750 and one in 2450 raise the
  engine's bare `RuntimeError` **from inside `render_birth_chart`**, after the resolver has been
  closed and with the ephemeris session exited (spies) — the test asserts the type is exactly
  `RuntimeError` and that this layer added no subclass or wrapper. The exact edges are the
  engine's business and are not asserted by this layer (observed, for the record: 1799-12-31
  12:00 UT is refused, while 2400-01-01 00:00 UT is still served and 2400-01-15 is refused — a
  small overhang of the data files that no calendar-year rule would reproduce).
- `ChartConfig`: non-path types (`None`, `123`, `b"x"`, `True`) → `ConfigurationError` before
  any filesystem call (spy on `Path.resolve`); relative paths are stored absolute and unchanged
  by a later `monkeypatch.chdir`; `~` expansion; missing geodata file; geodata path that is a
  directory; a temporary SQLite file lacking a required table → `GeodataError` from the
  resolver; missing ephemeris directory; a temporary ephemeris directory with one file absent,
  one file of the wrong size, one entry that is a directory named `sepl_18.se1`, and extra files
  present (accepted); an injected `PermissionError` from `open` on the geodata file and on one
  ephemeris file → `ConfigurationError` carrying the OS message; an injected `PermissionError`
  from `Path.resolve` → `ConfigurationError`; `ranking_config="strict"` → `ConfigurationError`;
  a `RankingConfig` instance is forwarded to the resolver (spy on the constructor).
- Argument kinds: non-`BirthChartRequest`, non-`ChartConfig`, non-`NorthIndianOptions` →
  `ValueError`. Options pass-through: `id_prefix="chart-7"` appears as `chart-7-title` in the
  SVG.
- Lifecycle and failure-path cleanup: after a successful call the resolver's connection is
  closed and `ephemeris_session` was entered and exited exactly once; after each failure path
  (`AmbiguousPlaceError`, `NonexistentLocalTimeError`, the engine's `RuntimeError`, an injected
  exception from `render_north_indian_svg`) the resolver is closed and the ephemeris session, if
  entered, was exited (spies on `OfflineLocationResolver.close` and on the session's exit).

**B. CLI** (call `cli.main(argv)` in-process with `capfdbinary`; plus one `subprocess` run of
`python -m vedic_chart.app` to prove the `__main__` path and one of `--help`).
- Success: `--out FILE` in `tmp_path` → exit 0, file bytes equal the golden, stdout empty;
  `--out -` → exit 0, stdout bytes equal the golden exactly, stderr empty; `--help` → exit 0,
  usage on stdout, nothing on stderr.
- Every exit code of §8.4 by type: bad date (2), bad time (2), fractional `--time` (2), missing
  `--out` (2), DST gap (2), bad `--id-prefix` (2, and the resolver was never opened — spy),
  ambiguous place (3, candidates on stderr), not found (3), missing ephemeris file (4), bad
  geodata schema (4), engine out-of-coverage birth (1, message on stderr, no traceback without
  `--verbose`, traceback with it).
- Output protection: existing file without `--force` → 5 and the bytes are unchanged, and the
  resolver was never opened (pre-check first — spy); a destination that **appears after the
  pre-check** (a spy on `render_birth_chart` creates the file, then the `O_EXCL` open raises
  `FileExistsError`) → 5 and the intruding file's bytes are unchanged; existing file with
  `--force` → 0, replaced, no `.tmp` left in the directory; parent directory missing → 5; output
  path is a directory → 5; output path is a symlink (to a regular file, and dangling) → 5 even
  with `--force`, link and target untouched; `--out` equal to the geodata path, to each
  ephemeris file, to a relative spelling of them, and to a hard link of the geodata file → 5 even
  with `--force`, resource bytes unchanged; injected `OSError` from `os.path.samefile` → 5.
- Non-regular destinations: `--out` naming an existing FIFO (`os.mkfifo` in `tmp_path`) and,
  where the platform allows, a Unix socket → 5 even with `--force`, the object untouched; the
  normalised destination is what the checks and writes use (a `--out` spelled with `./` and
  `..` segments resolves to the same `dest`, asserted through the alias refusal).
- Failed and partial writes: injected `OSError` on the `O_EXCL` descriptor's `write` → 5, the
  file this invocation created is gone, stderr reports "removed partial output"; injected
  `OSError` on `os.replace` → 5, the temporary file is gone, the original destination bytes are
  intact; the same with a replacement file written by "another process" between rendering and
  the failed `os.replace` (spy) → that file is left in place; injected `OSError` on `os.fsync` →
  5, temporary removed; injected `PermissionError` on `os.open` of the destination → 5.
- **Replacement during a failed write (regression):** on the direct path, a spy makes the
  descriptor `write` fail *after* another "process" has renamed a different file onto `dest`
  (so `os.stat(dest)` no longer matches `os.fstat(fd)`) → 5, the intruding file's bytes are
  unchanged, and stderr reports "partial output may remain … not removed"; the mirror case on
  the `--force` path with the temporary file replaced → the temporary path is left alone and
  reported. Cleanup failure: an injected `OSError` on `os.unlink` during cleanup → exit code
  still 5 with the original message first and the "could not remove partial output" warning
  second.
- stdout failure: in-process, injected `BrokenPipeError` on `sys.stdout.buffer.write` →
  `cli.run` returns `(5, True)`, message on stderr, and **no** `os.dup2` was called (spy) — the
  host process's descriptors are untouched; injected `OSError` on `flush` → `(5, False)`. In a
  real subprocess, `python -m vedic_chart.app … --out -` started with `stdout=PIPE` whose read
  end the test closes immediately → return code 5, stderr contains "stdout closed by reader"
  exactly once and contains no "Traceback" (the shutdown flush is silenced by `__main__`'s
  redirection, and the extra `os.devnull` descriptor is closed — asserted by a spy-free check
  that the child exits cleanly).
- Defaults: with no `--geodata`/`--ephemeris`, the paths used are `Path.cwd()/"data/geodata.sqlite"`
  and `Path.cwd()/"ephe"` resolved at call time (asserted via `--verbose` under
  `monkeypatch.chdir`).
- Error scopes: an injected `OSError` raised inside `render_birth_chart` (from the resolver's
  connect) is reported as exit 1, not 5; an injected `ValueError` raised inside
  `render_birth_chart` is exit 1, not 2.

**C. Boundaries.** AST test over `app/*.py` against §9; `pyproject.toml` unchanged; no new
dependency.

## 11. Acceptance criteria

1. `render_birth_chart` reproduces the Jalandhar golden byte-for-byte and resolves the place once.
2. Every error in §7 reaches the caller with its existing type; the CLI maps types to §8.4 exactly,
   with handlers scoped as described.
3. The function opens the geodata file read-only and the ephemeris once per call, closes both on
   every path, and writes nothing; the CLI writes only the normalised destination, never over an
   input resource, never through a symlink or onto a non-regular file, never replaces an existing
   file except when explicitly authorised by `--force`, removes on failure only a file it has
   positive evidence is its own and reports any leftover, and writes only the SVG to stdout.
4. Frozen calculation, Layer 9 and Layer 10 files unchanged; full suite green; import rules pass.
5. The implementation milestone includes a short README "End-to-end" section pointing at
   `python -m vedic_chart.app` and `render_birth_chart` (owner-reviewed text).

## 12. Deferred (recorded, not open)

Fractional seconds on the CLI; a caller-managed ephemeris session for repeated calls; any
pre-check of ephemeris coverage in this layer; console-script packaging. Each is revisited only
if the owner reopens it.

## 13. Validation record and known limitations (v1.0)

**Test suite.** Full suite on the owner's machine (project `.venv`, pyswisseph 2.10.3.2, the
committed fixture database and `ephe/`): **1543 passed, 0 failed, 0 skipped** — the 1412 tests
of Layer 10 v1.0 (`e6c60b5`) plus 131 Layer 11 tests (`tests/test_app_pipeline.py` 60,
`tests/test_app_cli.py` 54, `tests/test_app_boundaries.py` 17). This is the run made after the
implementation was completed and is recorded as a **previous run**; the promotion to v1.0 and
the owner's follow-up corrections changed only documentation (§3, §9, this section, and the
README's Layer 11 and Lagna sections), so that result is reused rather than re-run. Files of the frozen
calculation contract, Layer 9, Layer 10, `pyproject.toml`, the fixtures and the goldens are
unchanged against `e6c60b5` (`git status`, `git diff --stat HEAD` — only `README.md` modified,
the new `app/` package, the specification and the three test files untracked).

**Demonstrations** (generated outside the repository, not committed): the Jalandhar reference
(`--date 1995-03-21 --time 06:45 --place Jalandhar`, fixture database) written to a file and to
stdout is byte-identical to `tests/fixtures/render/jalandhar_nocaption_degrees.svg`;
`--place Springfield` exits 3 listing the candidates; an existing destination without `--force`
exits 5 with the bytes unchanged; `--out ephe/sepl_18.se1 --force` exits 5 and the file is still
484,061 bytes; an injected write failure exits 5 with "removed partial output" and no file left;
`python -m vedic_chart.app … --out -` piped into a reader that closes immediately exits 5 with
"stdout closed by reader" once and no traceback.

**Pre-commit review (read-only, against §§3, 7, 8, 9, 10).** Confirmed by reading the code and
tests: the place is resolved exactly once (`resolve_with_details`, the answer fed back through
`_PreresolvedResolver`, identity assertion after assembly); the resolver is closed before the
ephemeris session opens and both are released on every failure path; the direct write loops on
`os.write` over a `memoryview` until every byte is written; the `--force` path writes through
the buffered temporary file, flushes and fsyncs before duplicating the guard descriptor, and
closes the guard on every path (success, failed close, failed replace); cleanup is by
`fstat`/`stat` device-and-inode match only, with the three stderr wordings of §8.3; handlers are
scoped as §8.4 requires (`OSError`/`ValueError` from inside the pipeline → exit 1); `cli.run`
never redirects — only `__main__` does. An ad-hoc check outside the suite additionally drove the
direct write with an `os.write` that accepts at most 7 bytes per call (1,429 calls; output
byte-identical) and compared the process's open descriptors before and after the direct,
`--force` and failed-`--force` paths (unchanged). README examples were checked against the
implemented signatures and flags.

**Known limitations (recorded, not defects).**
- `ephemeris_session` acts on process-global state in the Swiss Ephemeris library: calls to
  `render_birth_chart` must be sequential within a process and must not be nested in another
  session; thread safety is not established (§7).
- `--force` fsyncs the temporary file's contents but not the parent directory; the rename may be
  lost on power failure immediately after a successful run on some filesystems (§8.3).
- Failed-write cleanup compares device and inode and then unlinks; the two steps are not atomic,
  and the CLI claims only that it never removes a path it has positive evidence is not its own
  file, and that any leftover is reported (§8.3).
- On the direct (non-`--force`) path, a failure of the final `os.close` is reported as exit 5
  with the OS message; the file, which by then has received every byte, is not removed and no
  "partial output" line is printed, because the write itself did not fail. Whether such a file is
  complete depends on the filesystem's meaning of a close error.
- The §8.2 pre-checks and the write are separated by a window: the direct path is protected by
  `O_EXCL` (a file or symlink that appears meanwhile is refused), and the `--force` path never
  writes through a link (`os.replace` swaps the directory entry), but a non-regular file created
  at the destination between the pre-check and `os.replace` is not re-checked.
- No coverage guard: a birth outside the files' UT coverage reaches the engine and is its bare
  `RuntimeError`, exit 1 (§7).
- The suite injects no short `os.write`; that behaviour is covered by the ad-hoc check above and
  by the loop's construction, not by a committed test.
