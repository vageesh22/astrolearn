"""Layer 11: the public end-to-end entry point.

One call turns a validated request plus a configuration into a finished SVG:

    request -> resolve the place -> assemble the chart -> D1 view -> SVG

This layer composes and nothing else. It computes no astronomy, applies no
astrological rule, changes none of the frozen layers below it, and -- unlike
the CLI that sits on top of it -- **writes nothing**: no output file, no cache,
no temporary file, no logging handler. It reads the geodata database and the
ephemeris files, and returns objects.

Two disciplines are worth naming because they are easy to lose:

**The place is resolved exactly once.** ``assemble_chart`` resolves the place
itself, so handing it the offline resolver after asking that resolver for the
decision would search the database twice and produce a ``ResolutionDecision``
that is not provably the one the chart was built from. Instead the pipeline
resolves once, with details, and feeds the answer back through the Layer 8
contract via :class:`_PreresolvedResolver`. After assembly it asserts by
*identity* that the chart carries the very object the decision describes.

**The ephemeris session is opened around assembly only.** ``ephemeris_session``
acts on process-global state inside the Swiss Ephemeris C library, so calls to
:func:`render_birth_chart` must be sequential within a process and must not be
nested inside another session. That is a limitation of the existing engine,
recorded here rather than redesigned.

Errors from the layers below propagate with their own types, unchanged. The
only exception this module adds is :class:`ConfigurationError` for a
``ChartConfig`` field that cannot be used, plus two internal ``RuntimeError``s
that can only fire if the Layer 8 contract itself changed underneath us.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.chart.assemble import assemble_chart
from vedic_chart.chart.model import BirthChart
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.model import ResolvedLocation
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.location.offline.search import RankingConfig, ResolutionDecision
from vedic_chart.render import NorthIndianOptions, render_north_indian_svg
from vedic_chart.representation.d1 import D1Chart, build_d1_chart

__all__ = [
    "ChartConfig",
    "ChartResult",
    "ConfigurationError",
    "render_birth_chart",
]

#: The three Swiss Ephemeris data files the frozen calculation contract names,
#: with the exact sizes recorded in ``docs/CALCULATION_SPEC.md``. The size is a
#: compatibility check against that contract, **not** proof of file integrity:
#: nothing is hashed here, and the engine's own refusal of the Moshier fallback
#: remains the runtime backstop for a corrupt or wrong-content file.
EPHEMERIS_FILE_SIZES: tuple[tuple[str, int], ...] = (
    ("sepl_18.se1", 484_061),
    ("semo_18.se1", 1_304_771),
    ("seas_18.se1", 223_004),
)


class ConfigurationError(ValueError):
    """A ``ChartConfig`` field is unusable: missing, wrong kind, or unreadable."""


def _probe_readable(path: Path, description: str) -> None:
    """Open the file for reading and close it immediately.

    An unreadable resource should fail at configuration time with a typed
    error, not deep inside the resolver or the C library.
    """
    try:
        open(path, "rb").close()
    except OSError as exc:
        raise ConfigurationError(
            f"{description} at {path} could not be opened for reading: {exc}"
        ) from exc


def _check_path_kind(value: object, field_name: str) -> None:
    """Reject a value that is not a path *before* any filesystem access.

    ``bytes`` is not a ``str`` and not ``os.PathLike``, so it falls out here
    with everything else; ``bool`` is excluded explicitly because it is an
    ``int`` and an ``int`` is not a path either.
    """
    if isinstance(value, bool) or not isinstance(value, (str, os.PathLike)):
        raise ConfigurationError(
            f"{field_name} must be a str or os.PathLike path; got "
            f"{type(value).__name__} ({value!r})."
        )


def _normalized_path(value: object, field_name: str) -> Path:
    """Absolute, symlink-resolved form of a configured path.

    Resolving here -- and storing the result -- means a later change of the
    working directory cannot change what the configuration means, and gives the
    CLI canonical paths to compare its output destination against.
    """
    try:
        return Path(value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise ConfigurationError(
            f"{field_name} {value!r} could not be resolved: {exc}"
        ) from exc


@dataclass(frozen=True)
class ChartConfig:
    """Where the two data resources live, validated at construction.

    There are no defaults. A default geodata or ephemeris path would be a real
    decision buried in a signature; the CLI has documented defaults of its own
    (relative to the working directory) and passes explicit values here.

    ``ephemeris_files`` is derived, never given: it is ``field(init=False)`` so
    that a caller can neither pass it nor let it drift from ``ephemeris_path``.
    """

    geodata_path: Path
    ephemeris_path: Path
    ranking_config: RankingConfig | None = None
    ephemeris_files: tuple[Path, ...] = field(init=False)

    def __post_init__(self) -> None:
        # Kinds first, for *both* fields, so that a wrong type never reaches
        # the filesystem at all -- not even through the other field.
        _check_path_kind(self.geodata_path, "geodata_path")
        _check_path_kind(self.ephemeris_path, "ephemeris_path")

        geodata_path = _normalized_path(self.geodata_path, "geodata_path")
        ephemeris_path = _normalized_path(self.ephemeris_path, "ephemeris_path")
        object.__setattr__(self, "geodata_path", geodata_path)
        object.__setattr__(self, "ephemeris_path", ephemeris_path)

        try:
            is_file = geodata_path.is_file()
        except OSError as exc:
            raise ConfigurationError(
                f"geodata_path at {geodata_path} could not be inspected: {exc}"
            ) from exc
        if not is_file:
            raise ConfigurationError(
                f"geodata_path must be a regular file; {geodata_path} is not. "
                "Build the database with tools/geodata/build_db.py, or point "
                "at the test fixture."
            )
        _probe_readable(geodata_path, "the geodata database")
        # The schema is not checked here: db.connect owns that check and
        # raises GeodataError; a second copy would be a second source of truth.

        try:
            is_dir = ephemeris_path.is_dir()
        except OSError as exc:
            raise ConfigurationError(
                f"ephemeris_path at {ephemeris_path} could not be inspected: "
                f"{exc}"
            ) from exc
        if not is_dir:
            raise ConfigurationError(
                f"ephemeris_path must be a directory holding the Swiss "
                f"Ephemeris .se1 files; {ephemeris_path} is not."
            )

        files = []
        for name, expected_size in EPHEMERIS_FILE_SIZES:
            candidate = ephemeris_path / name
            try:
                status = candidate.stat()
            except OSError as exc:
                raise ConfigurationError(
                    f"ephemeris_path {ephemeris_path} is missing the required "
                    f"file {name} ({expected_size} bytes): {exc}"
                ) from exc
            if not candidate.is_file():
                raise ConfigurationError(
                    f"the ephemeris entry {candidate} is not a regular file; "
                    f"{name} must be a regular file of {expected_size} bytes."
                )
            if status.st_size != expected_size:
                raise ConfigurationError(
                    f"the ephemeris file {candidate} is {status.st_size} bytes "
                    f"but the frozen calculation contract records {name} as "
                    f"{expected_size} bytes."
                )
            _probe_readable(candidate, f"the ephemeris file {name}")
            files.append(candidate)
        # Other files in the directory -- the licence notice, additional .se1
        # ranges -- are ignored on purpose.
        object.__setattr__(self, "ephemeris_files", tuple(files))

        if self.ranking_config is not None and not isinstance(
            self.ranking_config, RankingConfig
        ):
            raise ConfigurationError(
                "ranking_config must be None or a RankingConfig instance; got "
                f"{type(self.ranking_config).__name__} "
                f"({self.ranking_config!r})."
            )


@dataclass(frozen=True)
class ChartResult:
    """Everything one end-to-end call produced, by identity.

    The intermediate objects are here for auditability and reuse -- not as a
    way to skip rendering. Every call renders.
    """

    request: BirthChartRequest
    chart: BirthChart
    d1: D1Chart
    svg: str
    resolution: ResolutionDecision


class _PreresolvedResolver:
    """A ``LocationResolver`` over one already-resolved location.

    Protocol-conformant, and deliberately private: it exists so the pipeline
    can resolve *with details* once and still hand ``assemble_chart`` the
    resolver it expects, rather than resolving a second time.
    """

    def __init__(self, place_query: str, location: ResolvedLocation) -> None:
        self._place_query = place_query
        self._location = location

    def resolve(self, place_query: str) -> ResolvedLocation:
        if place_query != self._place_query:
            # Defensive: assemble_chart passes request.place_query, which is
            # what this adapter was built from. Reaching this means the Layer 8
            # contract changed underneath us.
            raise RuntimeError(
                "internal: assemble_chart asked for a different place query "
                f"({place_query!r}, expected {self._place_query!r})."
            )
        return self._location


_DEFAULT_OPTIONS = NorthIndianOptions()


def render_birth_chart(
    request: BirthChartRequest,
    config: ChartConfig,
    options: NorthIndianOptions = _DEFAULT_OPTIONS,
) -> ChartResult:
    """Resolve, assemble, represent and render one birth chart.

    The birth date is deliberately **not** range-checked here: the frozen
    engine decides ephemeris coverage at calculation time, in UT, and a local
    calendar year is not an exact test of it. An instant outside the data
    files' coverage reaches the caller as the engine's own bare ``RuntimeError``.
    """
    if not isinstance(request, BirthChartRequest):
        raise ValueError(
            "request must be a BirthChartRequest; got "
            f"{type(request).__name__}."
        )
    if not isinstance(config, ChartConfig):
        raise ValueError(
            f"config must be a ChartConfig; got {type(config).__name__}."
        )
    if not isinstance(options, NorthIndianOptions):
        raise ValueError(
            "options must be a NorthIndianOptions; got "
            f"{type(options).__name__}."
        )

    # The geodata connection is opened read-only and immutable, and closed
    # before the ephemeris is opened: two resources, never held together.
    with OfflineLocationResolver(
        config.geodata_path, config.ranking_config
    ) as resolver:
        location, decision = resolver.resolve_with_details(request.place_query)

    with ephemeris_session(str(config.ephemeris_path)):
        chart = assemble_chart(
            request, _PreresolvedResolver(request.place_query, location)
        )

    if chart.location is not location:
        raise RuntimeError(
            "internal: the assembled chart does not carry the location this "
            "resolution decided on; the single-resolution guarantee is broken."
        )

    d1 = build_d1_chart(chart)
    svg = render_north_indian_svg(d1, options)

    return ChartResult(
        request=request,
        chart=chart,
        d1=d1,
        svg=svg,
        resolution=decision,
    )
