"""Layer 11: the ``python -m vedic_chart.app`` front end.

A thin argparse wrapper around :func:`vedic_chart.app.pipeline.render_birth_chart`,
plus the one thing the pipeline deliberately refuses to do: write a file.

Three properties are worth stating, because they are what the writing policy is
for.

**Types decide exit codes, never messages.** Section 8.4 of the specification
maps exception *classes* to exit codes; nothing here parses an error string. The
engine's bare ``RuntimeError`` -- an instant outside the ephemeris files'
coverage, a refusal to fall back to Moshier, an ayanamsha inconsistency -- is
therefore the generic exit 1 with the engine's own message, not a reclassified
error this layer invented.

**Every handler is scoped to its stage.** The renderer ``ValueError`` handler
wraps only ``NorthIndianOptions(...)``; the output ``OSError`` handler wraps
only the write. A ``PermissionError`` opening the database is an ``OSError``
too, but it happens inside the pipeline and must never be reported as an output
error.

**The CLI never removes a path it cannot prove is its own.** After a failed
write it compares ``os.fstat`` on the descriptor it still holds with
``os.stat`` on the path; only a matching device and inode earn an unlink. A
mismatch leaves the path alone and says so. Anything left behind is reported.

``run(argv) -> (exit_code, stdout_broken)`` is the primitive. It performs no
process-wide redirection, because ``main`` may be called in-process by a test
or a host program and must not touch that process's descriptors; the executable
boundary ``__main__.py`` is the only place that acts on the broken-stdout flag.
"""

import argparse
import os
import re
import stat
import sys
import tempfile
import traceback
from pathlib import Path

from vedic_chart.app.pipeline import (
    ChartConfig,
    ConfigurationError,
    render_birth_chart,
)
from vedic_chart.inputs.model import (
    BirthChartRequest,
    InvalidBirthDateError,
    InvalidBirthTimeError,
    InvalidPlaceQueryError,
)
from vedic_chart.location.model import (
    AmbiguousPlaceError,
    InvalidCoordinateError,
    PlaceNotFoundError,
)
from vedic_chart.location.offline.db import GeodataError
from vedic_chart.render import NorthIndianOptions
from vedic_chart.time.local_time import (
    AmbiguousLocalTimeError,
    InvalidTimezoneError,
    NonexistentLocalTimeError,
)

__all__ = ["main", "run"]

PROGRAM = "python -m vedic_chart.app"

#: Defaults exist in the CLI only, and are relative to the working directory at
#: the moment the command runs. ChartConfig has none and stores absolute paths.
DEFAULT_GEODATA = "data/geodata.sqlite"
DEFAULT_EPHEMERIS = "ephe"

_DATE_PATTERN = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
#: ``HH:MM`` or ``HH:MM:SS``. Fractional seconds are rejected here, by the
#: argument parser, and are a recorded deferral rather than an oversight: the
#: Python request API keeps Layer 1's microsecond precision untouched.
_TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?")

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_INPUT = 2
EXIT_PLACE = 3
EXIT_CONFIG = 4
EXIT_OUTPUT = 5
EXIT_INTERRUPTED = 130

STDOUT_TARGET = "-"


def _stderr(message: str) -> None:
    print(message, file=sys.stderr)


# --- argument parsing ------------------------------------------------------


def _date_components(text: str) -> tuple[int, int, int]:
    match = _DATE_PATTERN.fullmatch(text)
    if match is None:
        raise argparse.ArgumentTypeError(
            f"expected a date as YYYY-MM-DD; got {text!r}."
        )
    return tuple(int(part) for part in match.groups())


def _time_components(text: str) -> tuple[int, int, int]:
    match = _TIME_PATTERN.fullmatch(text)
    if match is None:
        raise argparse.ArgumentTypeError(
            f"expected a 24-hour wall time as HH:MM or HH:MM:SS, without "
            f"fractional seconds; got {text!r}."
        )
    hour, minute, second = match.groups()
    return int(hour), int(minute), int(second or 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "Render a North Indian D1 chart as SVG, end to end: resolve the "
            "birthplace offline, assemble the chart, and write the drawing."
        ),
    )
    parser.add_argument(
        "--date",
        required=True,
        type=_date_components,
        metavar="YYYY-MM-DD",
        help="birth date, proleptic Gregorian",
    )
    parser.add_argument(
        "--time",
        required=True,
        type=_time_components,
        metavar="HH:MM[:SS]",
        help="birth wall time at the birthplace, 24-hour, no fractional seconds",
    )
    parser.add_argument(
        "--place",
        required=True,
        metavar="QUERY",
        help='birthplace query, e.g. "Jalandhar" or "Hyderabad, India"',
    )
    parser.add_argument(
        "--out",
        required=True,
        metavar="PATH",
        help=f"output SVG path, or {STDOUT_TARGET!r} for stdout",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing output file (atomically); never an input resource",
    )
    parser.add_argument(
        "--geodata",
        default=DEFAULT_GEODATA,
        metavar="PATH",
        help=(
            f"geodata SQLite database (default: {DEFAULT_GEODATA}, relative to "
            "the current directory)"
        ),
    )
    parser.add_argument(
        "--ephemeris",
        default=DEFAULT_EPHEMERIS,
        metavar="PATH",
        help=(
            f"directory holding the Swiss Ephemeris .se1 files (default: "
            f"{DEFAULT_EPHEMERIS}, relative to the current directory)"
        ),
    )
    parser.add_argument(
        "--caption", action="store_true", help="draw the caption band"
    )
    parser.add_argument(
        "--no-degrees",
        action="store_true",
        help="omit the degree text beside each graha",
    )
    parser.add_argument(
        "--mark-node-retrograde",
        action="store_true",
        help="mark Rahu and Ketu as retrograde",
    )
    parser.add_argument(
        "--width", type=int, default=None, metavar="N", help="width in CSS pixels"
    )
    parser.add_argument(
        "--id-prefix",
        default="d1",
        metavar="PREFIX",
        help="prefix for every id in the document, for embedding several charts",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="report the paths, place and resolution decision on stderr",
    )
    return parser


# --- output destination ----------------------------------------------------


def _normalized_destination(raw: str) -> Path:
    """``PATH.parent`` canonicalised, the final component kept literal.

    Keeping the last component literal is what makes a symlink *as the
    destination itself* detectable; symlinks among the parent directories are
    part of the tree and are followed normally.
    """
    path = Path(raw)
    parent = path.parent.resolve(strict=True)
    return parent / path.name


def _check_destination(
    raw: str, config: ChartConfig, force: bool
) -> tuple[Path | None, str | None]:
    """Section 8.2, run before any resolution or calculation."""
    try:
        dest = _normalized_destination(raw)
    except OSError as exc:
        return None, (
            f"output directory for {raw} is unusable: {exc}. The CLI never "
            "creates directories."
        )
    if not dest.parent.is_dir():
        return None, f"output directory {dest.parent} is not a directory."

    if os.path.islink(dest):
        return None, (
            f"output path {dest} is a symbolic link; give the real path. "
            "Refused even with --force."
        )

    try:
        status = os.lstat(dest)
    except FileNotFoundError:
        status = None
    except OSError as exc:
        return None, f"output path {dest} could not be inspected: {exc}"

    if status is not None and not stat.S_ISREG(status.st_mode):
        return None, (
            f"output path {dest} exists and is not a regular file. Refused "
            "even with --force."
        )

    resources = (config.geodata_path,) + config.ephemeris_files
    for resource in resources:
        if dest == resource:
            return None, (
                f"refusing to write over an input resource: {dest}. Refused "
                "even with --force."
            )
        if status is None:
            continue
        try:
            same = os.path.samefile(dest, resource)
        except OSError as exc:
            return None, (
                f"output path {dest} could not be compared with the input "
                f"resource {resource}: {exc}. Refusing an unverifiable "
                "destination."
            )
        if same:
            return None, (
                f"refusing to write over an input resource: {dest} is the "
                f"same file as {resource}. Refused even with --force."
            )

    if status is not None and not force:
        return None, (
            f"refusing to overwrite {dest}; pass --force to replace it."
        )

    return dest, None


# --- writing ---------------------------------------------------------------


def _close_fd(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def _cleanup(fd: int, path: Path) -> None:
    """Remove the file this run created -- and only if it still is that file.

    Having created a file earlier does not prove the path still refers to it:
    another process may have replaced or removed it meanwhile. So the path is
    unlinked only when the descriptor we still hold and the path agree on
    device and inode. Anything left behind is reported rather than hidden.
    """
    left_alone = (
        f"partial output may remain at {path}; not removed because the path "
        "no longer refers to the file this run created"
    )
    try:
        ours = os.fstat(fd)
        current = os.stat(path)
    except OSError:
        _stderr(left_alone)
        return
    if (ours.st_dev, ours.st_ino) != (current.st_dev, current.st_ino):
        _stderr(left_alone)
        return
    try:
        os.unlink(path)
    except OSError as exc:
        _stderr(f"warning: could not remove partial output {path}: {exc}")
        return
    _stderr(f"removed partial output {path}")


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def _write_direct(dest: Path, data: bytes) -> int:
    """Create the destination with ``O_EXCL`` and write through it.

    ``O_EXCL`` makes creation atomic with respect to other processes: a file
    that appeared since the pre-check causes ``FileExistsError`` and is never
    touched. This is a direct write, **not** an atomic replacement -- a reader
    opening the destination mid-write can see partial content. The guarantee is
    only that a pre-existing file is never overwritten here.
    """
    try:
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        _stderr(
            f"error: {dest} appeared before it could be created; refusing to "
            "overwrite it. Pass --force to replace an existing file."
        )
        return EXIT_OUTPUT
    except OSError as exc:
        _stderr(f"error: could not create {dest}: {exc}")
        return EXIT_OUTPUT

    try:
        _write_all(fd, data)
    except OSError as exc:
        _stderr(f"error: could not write {dest}: {exc}")
        _cleanup(fd, dest)
        _close_fd(fd)
        return EXIT_OUTPUT

    try:
        os.close(fd)
    except OSError as exc:
        _stderr(f"error: could not close {dest}: {exc}")
        return EXIT_OUTPUT
    return EXIT_OK


def _write_replacing(dest: Path, data: bytes) -> int:
    """Write a temporary file beside the destination and rename it into place.

    ``os.replace`` is an atomic rename on one filesystem: a reader sees either
    the complete old file or the complete new one, and a failure before the
    rename leaves the old file intact. It is **not** a durability guarantee --
    the file's contents are fsynced but the parent directory is not, so a power
    loss immediately after a successful run can, on some filesystems, lose the
    rename. On this path the destination is never a cleanup target; only the
    temporary file is.
    """
    try:
        handle = tempfile.NamedTemporaryFile(
            dir=dest.parent,
            prefix=f".{dest.name}.",
            suffix=".tmp",
            delete=False,
        )
    except OSError as exc:
        _stderr(f"error: could not create a temporary file beside {dest}: {exc}")
        return EXIT_OUTPUT

    tmp_path = Path(handle.name)
    # A second descriptor on our own temporary file, kept open past the close
    # below: without it a cleanup after a failed rename could not prove the
    # temporary path still refers to the file this run created.
    guard_fd = -1
    try:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        guard_fd = os.dup(handle.fileno())
    except OSError as exc:
        _stderr(f"error: could not write {tmp_path}: {exc}")
        _cleanup(handle.fileno(), tmp_path)
        try:
            handle.close()
        except OSError:
            pass
        if guard_fd >= 0:
            _close_fd(guard_fd)
        return EXIT_OUTPUT

    try:
        handle.close()
    except OSError as exc:
        _stderr(f"error: could not close {tmp_path}: {exc}")
        _cleanup(guard_fd, tmp_path)
        _close_fd(guard_fd)
        return EXIT_OUTPUT

    try:
        os.replace(tmp_path, dest)
    except OSError as exc:
        _stderr(f"error: could not move {tmp_path} into place at {dest}: {exc}")
        _cleanup(guard_fd, tmp_path)
        _close_fd(guard_fd)
        return EXIT_OUTPUT

    _close_fd(guard_fd)
    return EXIT_OK


def _write_stdout(data: bytes) -> tuple[int, bool]:
    """Write the SVG to stdout and flush it.

    A ``BrokenPipeError`` -- the reader closed early, as ``| head`` does -- is
    reported once and returned with a flag. No redirection happens here: this
    function may be running inside a host process whose descriptors are none of
    our business.
    """
    try:
        sys.stdout.buffer.write(data)
    except BrokenPipeError:
        _stderr("stdout closed by reader")
        return EXIT_OUTPUT, True
    except OSError as exc:
        _stderr(f"error: could not write to stdout: {exc}")
        return EXIT_OUTPUT, False

    try:
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        _stderr("stdout closed by reader")
        return EXIT_OUTPUT, True
    except OSError as exc:
        _stderr(f"error: could not flush stdout: {exc}")
        return EXIT_OUTPUT, False

    return EXIT_OK, False


# --- reporting -------------------------------------------------------------


def _report_ambiguity(error: AmbiguousPlaceError) -> None:
    """List the choices; never make one."""
    for candidate in list(error.candidates)[:5]:
        _stderr(
            f"  {candidate.name}, {candidate.admin1_name or '?'}, "
            f"{candidate.country_name or '?'} (pop {candidate.population})"
        )
    _stderr(f"error: {error}")


def _report_decision(result) -> None:
    decision = result.resolution
    chosen = decision.chosen
    _stderr(f"place: {result.chart.location.canonical_name}")
    if chosen is not None:
        _stderr(
            f"chosen: {chosen.name} (geoname {chosen.geoname_id}, "
            f"{chosen.feature_code}, pop {chosen.population}, "
            f"score {chosen.score})"
        )
    _stderr(
        f"materially different rivals: {decision.materially_different_count}; "
        f"dominance applied: {decision.dominance_applied}"
    )
    _stderr(f"reason: {decision.dominance_reason}")
    if decision.population_ratio is not None:
        _stderr(f"population ratio: {decision.population_ratio}")
    _stderr(f"timezone: {result.chart.location.timezone_id}")
    _stderr(f"instant (UTC): {result.chart.moment_utc}")


# --- the run ---------------------------------------------------------------


def _execute(argv: list[str] | None) -> tuple[int, bool]:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        # argparse prints its own usage/help and chooses its own code: 0 for
        # --help, 2 for a usage error. Both are its convention, kept.
        code = exit_request.code
        return (int(code) if code is not None else EXIT_OK), False

    # (2) renderer options -- the only place a renderer ValueError is caught.
    try:
        options = NorthIndianOptions(
            show_degrees=not args.no_degrees,
            mark_node_retrograde=args.mark_node_retrograde,
            caption=args.caption,
            width=args.width,
            id_prefix=args.id_prefix,
        )
    except ValueError as exc:
        _stderr(f"error: {exc}")
        return EXIT_INPUT, False

    # (3) the request -- Layer 1 owns calendar and wall-time validation.
    year, month, day = args.date
    hour, minute, second = args.time
    try:
        request = BirthChartRequest.from_components(
            year, month, day, hour, minute, second, place_query=args.place
        )
    except (
        InvalidBirthDateError,
        InvalidBirthTimeError,
        InvalidPlaceQueryError,
    ) as exc:
        _stderr(f"error: {exc}")
        return EXIT_INPUT, False

    # (4) the configuration.
    try:
        config = ChartConfig(
            geodata_path=args.geodata, ephemeris_path=args.ephemeris
        )
    except ConfigurationError as exc:
        _stderr(f"error: {exc}")
        return EXIT_CONFIG, False

    if args.verbose:
        _stderr(f"geodata: {config.geodata_path}")
        _stderr(f"ephemeris: {config.ephemeris_path}")
        for path in config.ephemeris_files:
            _stderr(f"ephemeris file: {path}")

    # (5) the output destination, before any resolution or calculation.
    dest = None
    if args.out != STDOUT_TARGET:
        dest, refusal = _check_destination(args.out, config, args.force)
        if refusal is not None:
            _stderr(f"error: {refusal}")
            return EXIT_OUTPUT, False
        if args.verbose:
            _stderr(f"output: {dest}")

    # (6) the pipeline. Handlers are by exception type only, never by message.
    try:
        result = render_birth_chart(request, config, options)
    except (
        InvalidBirthDateError,
        InvalidBirthTimeError,
        InvalidPlaceQueryError,
        InvalidTimezoneError,
        NonexistentLocalTimeError,
        AmbiguousLocalTimeError,
    ) as exc:
        _stderr(f"error: {exc}")
        return EXIT_INPUT, False
    except AmbiguousPlaceError as exc:
        _report_ambiguity(exc)
        return EXIT_PLACE, False
    except PlaceNotFoundError as exc:
        _stderr(f"error: {exc}")
        return EXIT_PLACE, False
    except (ConfigurationError, GeodataError, InvalidCoordinateError) as exc:
        _stderr(f"error: {exc}")
        return EXIT_CONFIG, False
    except Exception as exc:  # noqa: BLE001 -- the documented generic case
        _stderr(f"error: {type(exc).__name__}: {exc}")
        if args.verbose:
            traceback.print_exc()
        return EXIT_UNEXPECTED, False

    if args.verbose:
        _report_decision(result)

    # (7) the write.
    data = result.svg.encode("utf-8")
    if dest is None:
        return _write_stdout(data)
    if args.force:
        return _write_replacing(dest, data), False
    return _write_direct(dest, data), False


def run(argv: list[str] | None = None) -> tuple[int, bool]:
    """Do everything and report ``(exit_code, stdout_broken)``.

    ``stdout_broken`` says the reader closed the pipe; acting on it is the
    executable boundary's job, never this function's.
    """
    try:
        return _execute(argv)
    except KeyboardInterrupt:
        _stderr("interrupted")
        return EXIT_INTERRUPTED, False


def main(argv: list[str] | None = None) -> int:
    """The in-process entry point: the exit code, and no side effects on fds."""
    return run(argv)[0]
