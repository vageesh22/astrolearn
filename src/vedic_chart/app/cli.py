"""Layer 11, extended by Layer 13: the ``python -m vedic_chart.app`` front end.

A thin argparse wrapper around the pipeline's three entry points --
``render_birth_chart``, ``compute_dasha`` and ``render_chart_and_dasha`` -- plus
the one thing the pipeline deliberately refuses to do: write a file.

The command now has two possible outputs, the SVG and the daśā table, and each
has its own destination. What that costs is stated plainly here because it
cannot be designed away: **two writes are not one transaction.** File
destinations are written first (the SVG before the table), a stdout destination
last, and if the second write fails the first output is *kept* -- never deleted
as a rollback -- and a note on stderr says where it is. Both destinations go
through the same pre-checks, ``--force`` applies to both, and the two may not be
the same file.

Three further properties are worth stating, because they are what the writing
policy is for.

**Types decide exit codes, never messages.** Section 8.4 of the specification
maps exception *classes* to exit codes; nothing here parses an error string. The
engine's bare ``RuntimeError`` -- an instant outside the ephemeris files'
coverage, a refusal to fall back to Moshier, an ayanamsha inconsistency -- is
therefore the generic exit 1 with the engine's own message, not a reclassified
error this layer invented.

**Every handler is scoped to its stage.** The renderer ``ValueError`` handler
wraps only ``NorthIndianOptions(...)``; the zone ``ValueError`` handler wraps
only ``resolve_zone(...)``; the ``DashaRangeError`` handler wraps only the
calculation and the table rendering; the output ``OSError`` handler wraps only
the write. A ``PermissionError`` opening the database is an ``OSError`` too, but
it happens inside the pipeline and must never be reported as an output error,
and an unrelated ``ValueError`` from inside the pipeline is still the generic
exit 1 -- ``DashaRangeError`` is caught by *type*, not because it is a
``ValueError``.

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
    compute_dasha,
    render_birth_chart,
    render_chart_and_dasha,
)
from vedic_chart.dasha import (
    DashaRangeError,
    YearConvention,
    render_dasha_text,
    resolve_zone,
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

#: The depth words ``--dasha`` accepts, and the level each stands for.
DASHA_DEPTHS: dict[str, int] = {"md": 1, "md-ad": 2, "md-ad-pd": 3}

#: The year conventions ``--dasha-year`` accepts, by their day count. There is
#: no default: Layer 12 refuses to pick one, and so does this command.
DASHA_YEARS: dict[str, YearConvention] = {
    "365.25": YearConvention.FIXED_365_25,
    "365.256363": YearConvention.FIXED_365_256363,
}

DASHA_PRECISIONS: tuple[str, ...] = ("second", "day")

DEFAULT_DASHA_PRECISION = "second"
DEFAULT_ID_PREFIX = "d1"

#: The default of every option whose *explicit supply* has to be detectable.
#: An option left at ``_UNSET`` was not given; one holding its documented
#: effective default may well have been given, and the difference decides
#: whether a renderer flag is an orphan (section 6). The effective defaults are
#: applied after the mode checks, never by argparse.
_UNSET = object()


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
            "Render a North Indian D1 chart as SVG and/or a Vimshottari dasha "
            "table, end to end: resolve the birthplace offline, assemble the "
            "chart once, and write what was asked for."
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
        default=None,
        metavar="PATH",
        help=(
            f"output SVG path, or {STDOUT_TARGET!r} for stdout; at least one "
            "of --out or --dasha is required"
        ),
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
        "--dasha",
        nargs="?",
        const="md-ad",
        default=None,
        choices=tuple(DASHA_DEPTHS),
        metavar="md|md-ad|md-ad-pd",
        help=(
            "request the Vimshottari dasha table; bare --dasha means md-ad "
            "(Mahadasha and Antardasha)"
        ),
    )
    parser.add_argument(
        "--dasha-year",
        default=None,
        choices=tuple(DASHA_YEARS),
        metavar="{365.25,365.256363}",
        help=(
            "length of one nominal dasha-year in days; required with --dasha, "
            "with no default"
        ),
    )
    parser.add_argument(
        "--dasha-out",
        default=None,
        metavar="PATH",
        help=(
            f"output path for the dasha table, or {STDOUT_TARGET!r} for "
            "stdout; required with --dasha"
        ),
    )
    parser.add_argument(
        "--dasha-precision",
        default=_UNSET,
        choices=DASHA_PRECISIONS,
        help=(
            f"timestamp precision of the table (default: "
            f"{DEFAULT_DASHA_PRECISION}); day omits boundary times and is "
            "warned about in the header"
        ),
    )
    parser.add_argument(
        "--dasha-zone",
        default=_UNSET,
        metavar="IANA",
        help=(
            "IANA zone the table is shown in (default: the resolved "
            "birthplace's zone)"
        ),
    )
    parser.add_argument(
        "--caption",
        action="store_const",
        const=True,
        default=_UNSET,
        help="draw the caption band",
    )
    parser.add_argument(
        "--no-degrees",
        action="store_const",
        const=True,
        default=_UNSET,
        help="omit the degree text beside each graha",
    )
    parser.add_argument(
        "--mark-node-retrograde",
        action="store_const",
        const=True,
        default=_UNSET,
        help="mark Rahu and Ketu as retrograde",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=_UNSET,
        metavar="N",
        help="width in CSS pixels",
    )
    parser.add_argument(
        "--id-prefix",
        default=_UNSET,
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


#: The renderer flags whose explicit supply is an error in dasha-only mode.
_RENDERER_FLAGS = (
    "caption",
    "no_degrees",
    "mark_node_retrograde",
    "width",
    "id_prefix",
)


def _flag_spelling(attribute: str) -> str:
    return "--" + attribute.replace("_", "-")


def _explicit(args, attribute: str) -> bool:
    """Was this option actually given, as opposed to left at its default?

    The distinction only exists because every such option is declared with
    ``_UNSET``; argparse cannot otherwise tell ``--caption`` absent from
    ``--caption`` present, nor an explicit ``--dasha-precision second`` from
    the default of the same name.
    """
    return getattr(args, attribute) is not _UNSET


def _check_modes(parser: argparse.ArgumentParser, args) -> None:
    """Section 6's output modes, all reported through ``parser.error``.

    ``parser.error`` prints usage on stderr and exits 2 -- argparse's own
    convention for a usage error, kept, so that nothing reaches stdout and the
    code does not depend on which check failed.
    """
    svg_requested = args.out is not None
    dasha_requested = args.dasha is not None

    if not svg_requested and not dasha_requested:
        parser.error("at least one of --out or --dasha is required")

    if not dasha_requested:
        orphans = [
            spelling
            for spelling, given in (
                ("--dasha-year", args.dasha_year is not None),
                ("--dasha-out", args.dasha_out is not None),
                ("--dasha-precision", _explicit(args, "dasha_precision")),
                ("--dasha-zone", _explicit(args, "dasha_zone")),
            )
            if given
        ]
        if orphans:
            parser.error(
                f"{', '.join(orphans)} without --dasha; the dasha options "
                "require --dasha"
            )

    if dasha_requested:
        missing = [
            spelling
            for spelling, absent in (
                ("--dasha-year", args.dasha_year is None),
                ("--dasha-out", args.dasha_out is None),
            )
            if absent
        ]
        if missing:
            parser.error(f"--dasha requires {' and '.join(missing)}")

        if not svg_requested:
            supplied = [
                _flag_spelling(name)
                for name in _RENDERER_FLAGS
                if _explicit(args, name)
            ]
            if supplied:
                parser.error(
                    f"{', '.join(supplied)}: renderer options require --out"
                )

    if args.out == STDOUT_TARGET and args.dasha_out == STDOUT_TARGET:
        parser.error("at most one output may go to stdout")


def _same_destination(one: Path, other: Path) -> tuple[bool, str | None]:
    """Do the two destinations name one file? (Section 6, the collision rule.)

    Equal normalised paths settle it without touching the filesystem. Otherwise
    two different spellings can still be one file -- a hard link, a bind mount --
    which only ``os.path.samefile`` can tell, and only when both exist. An
    unanswerable comparison is a refusal, never an assumption.
    """
    if one == other:
        return True, None
    if not (os.path.exists(one) and os.path.exists(other)):
        return False, None
    try:
        return os.path.samefile(one, other), None
    except OSError as exc:
        return False, (
            f"the SVG destination {one} could not be compared with the dasha "
            f"destination {other}: {exc}. Refusing an unverifiable pair."
        )


def _execute(argv: list[str] | None) -> tuple[int, bool]:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        # (1) the output modes, before anything is built or opened.
        _check_modes(parser, args)
    except SystemExit as exit_request:
        # argparse prints its own usage/help and chooses its own code: 0 for
        # --help, 2 for a usage error. Both are its convention, kept.
        code = exit_request.code
        return (int(code) if code is not None else EXIT_OK), False

    svg_requested = args.out is not None
    dasha_requested = args.dasha is not None

    # Effective defaults, applied only now: before the mode checks they would
    # have erased the difference the checks depend on.
    precision = (
        args.dasha_precision
        if _explicit(args, "dasha_precision")
        else DEFAULT_DASHA_PRECISION
    )
    requested_zone = args.dasha_zone if _explicit(args, "dasha_zone") else None
    depth = DASHA_DEPTHS[args.dasha] if dasha_requested else None
    year = DASHA_YEARS[args.dasha_year] if dasha_requested else None

    # (2) renderer options -- the only place a renderer ValueError is caught,
    # and only when a drawing was actually asked for.
    options = None
    if svg_requested:
        try:
            options = NorthIndianOptions(
                show_degrees=not _explicit(args, "no_degrees"),
                mark_node_retrograde=_explicit(args, "mark_node_retrograde"),
                caption=_explicit(args, "caption"),
                width=args.width if _explicit(args, "width") else None,
                id_prefix=(
                    args.id_prefix
                    if _explicit(args, "id_prefix")
                    else DEFAULT_ID_PREFIX
                ),
            )
        except ValueError as exc:
            _stderr(f"error: {exc}")
            return EXIT_INPUT, False

    # (2b) the dasha presentation options. resolve_zone is the single zone
    # validator, and this is the only place its ValueError is caught.
    if requested_zone is not None:
        try:
            resolve_zone(requested_zone)
        except ValueError as exc:
            _stderr(f"error: {exc}")
            return EXIT_INPUT, False

    # (3) the request -- Layer 1 owns calendar and wall-time validation.
    year_number, month, day = args.date
    hour, minute, second = args.time
    try:
        request = BirthChartRequest.from_components(
            year_number, month, day, hour, minute, second, place_query=args.place
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

    # (5) every requested file destination, before any resolution or
    # calculation. --force applies to both, and neither may be the other.
    dest = None
    if svg_requested and args.out != STDOUT_TARGET:
        dest, refusal = _check_destination(args.out, config, args.force)
        if refusal is not None:
            _stderr(f"error: {refusal}")
            return EXIT_OUTPUT, False
        if args.verbose:
            _stderr(f"output: {dest}")

    dasha_dest = None
    if dasha_requested and args.dasha_out != STDOUT_TARGET:
        dasha_dest, refusal = _check_destination(
            args.dasha_out, config, args.force
        )
        if refusal is not None:
            _stderr(f"error: {refusal}")
            return EXIT_OUTPUT, False
        if args.verbose:
            _stderr(f"dasha output: {dasha_dest}")
    elif dasha_requested and args.verbose:
        _stderr(f"dasha output: {STDOUT_TARGET}")

    if dest is not None and dasha_dest is not None:
        collides, unverifiable = _same_destination(dest, dasha_dest)
        if unverifiable is not None:
            _stderr(f"error: {unverifiable}")
            return EXIT_OUTPUT, False
        if collides:
            _stderr(
                "error: the SVG and dasha destinations refer to the same "
                f"file: {dest}. Two outputs need two destinations."
            )
            return EXIT_OUTPUT, False

    # (6) one calculation, chosen by mode. Handlers are by exception type only,
    # never by message; DashaRangeError is caught by type, not as a ValueError.
    try:
        if svg_requested and dasha_requested:
            result = render_chart_and_dasha(request, config, options, year)
        elif dasha_requested:
            result = compute_dasha(request, config, year)
        else:
            result = render_birth_chart(request, config, options)
    except DashaRangeError as exc:
        _stderr(f"error: {exc}")
        return EXIT_INPUT, False
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

    # (7) all requested content, generated in memory before anything is
    # written: a failure here must not leave a half-written pair behind.
    # DashaRangeError keeps its input classification; anything else raised
    # while presenting or encoding is the documented generic case, exactly as
    # for the pipeline -- never reinterpreted as an input error, and never
    # allowed to escape ``run`` as an uncaught exception.
    zone = None
    if dasha_requested:
        # The birthplace zone is the default. It comes from Layer 2, which
        # stores an IANA key, so it is not re-validated here: resolve_zone
        # answers for the key the *caller* supplied, and for nothing else.
        zone = (
            requested_zone
            if requested_zone is not None
            else result.chart.location.timezone_id
        )
        if args.verbose:
            _stderr(f"dasha zone: {zone}")
            _stderr(f"dasha year: {args.dasha_year} days")
            _stderr(f"dasha depth: {args.dasha}")
            _stderr(f"dasha precision: {precision}")

    svg_data = None
    dasha_data = None
    try:
        if svg_requested:
            svg_data = result.svg.encode("utf-8")
        if dasha_requested:
            table = render_dasha_text(
                result.timeline, zone=zone, depth=depth, precision=precision
            )
            dasha_data = table.encode("utf-8")
    except DashaRangeError as exc:
        _stderr(f"error: {exc}")
        return EXIT_INPUT, False
    except Exception as exc:  # noqa: BLE001 -- the documented generic case
        _stderr(f"error: {type(exc).__name__}: {exc}")
        if args.verbose:
            traceback.print_exc()
        return EXIT_UNEXPECTED, False

    # (8) the writes, in the order of section 6: files first -- the SVG before
    # the table -- and a stdout destination, if any, last.
    plan = []
    if svg_requested and dest is not None:
        plan.append(("svg", dest, svg_data))
    if dasha_requested and dasha_dest is not None:
        plan.append(("dasha", dasha_dest, dasha_data))
    if svg_requested and dest is None:
        plan.append(("svg", None, svg_data))
    if dasha_requested and dasha_dest is None:
        plan.append(("dasha", None, dasha_data))

    kept: list[tuple[str, Path]] = []
    for label, destination, data in plan:
        if destination is None:
            code, broken = _write_stdout(data)
        elif args.force:
            code, broken = _write_replacing(destination, data), False
        else:
            code, broken = _write_direct(destination, data), False
        if code != EXIT_OK:
            # Two writes are not one transaction: what is already on disk stays
            # there, and is named so the caller knows what it has.
            for kept_label, kept_path in kept:
                _stderr(
                    f"note: {kept_label} output was written to {kept_path} "
                    "and is kept"
                )
            return code, broken
        if destination is not None:
            kept.append((label, destination))

    return EXIT_OK, False


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
