"""Layer 14, part 2: the loopback HTTP server, its contract and its command.

Everything that is not a pure function lives here: argument parsing, the
configuration built once at start-up, the three static files loaded once into
memory, the per-launch token, the bind, the request handler, the engine lock,
the error mapping and the exit codes.

Implements ``docs/LAYER14_INTERACTIVE_VIEWER_SPEC.md`` (DRAFT v0.3) sections 4,
11 and 12, as amended by ``docs/LAYER15_VIEWER_INPUT_FLOW_SPEC.md`` (DRAFT
v0.3): the default birthplace record validated at start-up (section 4.2), the
offline suggestions endpoint (section 5.2), and the effective-input step that
decides -- once, in one function -- what a submission is actually calculated
from (sections 5.3, 7.2).

Five disciplines are worth naming, because each of them is a decision that is
easy to lose.

**Threaded connections, one sequential engine (D15).** ``ephemeris_session``
acts on process-global state inside the Swiss Ephemeris C library, so the
pipeline must be used sequentially. One module-level :data:`ENGINE_LOCK` is
held around the single ``render_chart_and_dasha_at`` call and the row
extraction, and around nothing else: parsing and the effective-input step
happen before it is acquired and serialisation after it is released, so a slow
client can never hold the engine. ``POST /api/places`` never acquires it at
all -- a suggestion touches the geodata database only, and a keystroke must
not queue behind a calculation. The lock guarantees **mutual exclusion only**. Which of several waiting
requests acquires it next is not defined by ``threading.Lock``, no FIFO
scheduler is added, and nothing here claims an order; the browser's sequence
check (section 10.2) is what makes the page show the latest submission.

**Every response goes through one function.** :meth:`_ViewerHandler._respond`
calls ``send_response_only`` -- which writes the status line and nothing else
-- and then exactly the header set of section 11.3. ``send_response`` is never
called, because it appends ``Server`` and ``Date``, and a
``version_string()`` returning ``""`` does not suppress them. The base class
answers some conditions before routing (a method with no ``do_`` handler, a
malformed request line, an unsupported version, an over-long line, too many
header lines) by calling ``send_error``; that method is therefore **overridden**
so those paths produce the same JSON document, the same headers and the same
log line as every other response.

**Logs carry no birth data.** ``log_message``, ``log_request`` and
``log_error`` are all overridden. In normal operation the only line is
``<label> <status>`` with the label drawn from a fixed set of six words --
never a path, a query string, a header or a body. ``--verbose`` is opt-in
diagnostics and may contain request data, because an exception message can
embed a place query or a date; the banner says so when it is on.

**Nothing is written anywhere.** No cache, no log file, no PID file, no export.
Python may still write ``__pycache__`` bytecode for these modules on first
import, which is a property of the interpreter and not of the application
(section 4.3).

**Stopping is three things, not one.** ``server_close()`` closes the listening
socket; ``shutdown()`` stops the accept loop and must be called from another
thread; neither joins a worker. With ``daemon_threads = True`` an in-flight
calculation is abandoned when the process exits, and that call's
``ephemeris_session`` cleanup does not run. The ephemeris files are opened
read-only and the viewer writes nothing, so an abandoned calculation leaves
nothing inconsistent behind. This is stated, not solved (section 4.2a).
"""

import argparse
import http.server
import importlib.resources
import re
import secrets
import sys
import threading
import traceback
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from vedic_chart.app import (
    ChartConfig,
    ConfigurationError,
    render_chart_and_dasha_at,
)
from vedic_chart.dasha import DashaRangeError, dasha_rows
from vedic_chart.inputs.model import (
    BirthChartRequest,
    InvalidBirthDateError,
    InvalidBirthTimeError,
    InvalidPlaceQueryError,
)
from vedic_chart.location.model import (
    InvalidCoordinateError,
    PlaceNotFoundError,
)
from vedic_chart.location.offline.db import GeodataError
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.time.local_time import (
    AmbiguousLocalTimeError,
    InvalidTimezoneError,
    NonexistentLocalTimeError,
)
from vedic_chart.viewer import transport
from vedic_chart.viewer.transport import (
    PlaceSelectionRequiredError,
    StaleSchemaError,
    TransportError,
)

__all__ = ["ViewerConfig", "ViewerServer", "main", "serve"]

PROGRAM = "python -m vedic_chart.viewer"

#: Loopback only. There is no ``--host`` option and IPv6 loopback is not bound
#: (section 11.1): a viewer that could be reached from another machine would be
#: a different product with a different threat model.
BIND_HOST = "127.0.0.1"

#: Section 11.1: applied by ``StreamRequestHandler.setup`` to the connection
#: socket. It bounds each individual blocking socket operation, **not** the
#: whole request.
HANDLER_TIMEOUT = 10

#: Section 11.3: the body is read only after the length checks, and only for
#: exactly this many bytes at most. A birth request is a few hundred.
MAX_BODY_BYTES = 4096

#: Layer 15 section 5.2: a suggestions body is one short string. The cap is
#: separate from, and much smaller than, the chart cap because the two
#: endpoints carry different things.
MAX_PLACES_BODY_BYTES = 256

#: Layer 15 decision E3: how many suggestions one request may list.
SUGGESTION_LIMIT = 10

#: Layer 15 section 4.1, decision E1. The default birthplace is a **record**,
#: not a name: Jammu, Jammu and Kashmir, India, GeoNames 1269321, verified by
#: primary key on the production database ``data/geodata.sqlite`` (SHA-256
#: ``8afad22b...b7a4``) on the Mac session VM and again on the hash-identical
#: cloud copy -- one row, name Jammu, admin1 IN.12 Jammu and Kashmir, country
#: IN India, latitude 32.73528, longitude 74.86167, feature code PPLA,
#: population 576198, and ``timezonefinder`` answering Asia/Kolkata at those
#: coordinates. Those values are **reference evidence only**: the coordinates
#: and the zone are never hard-coded here. They are read from the configured
#: database at start-up, which is authoritative -- a rebuilt database whose
#: row 1269321 carried different coordinates would be used as it is (section
#: 4.1, v0.3).
DEFAULT_PLACE_ID = 1269321

#: Section 4.2 step 8, mirroring the CLI's own codes.
EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_USAGE = 2
EXIT_CONFIG = 4
EXIT_BIND = 5
EXIT_INTERRUPTED = 130

MIN_PORT = 0
MAX_PORT = 65535

JSON_CONTENT_TYPE = "application/json; charset=utf-8"

#: Section 11.3 item 4. ``img-src 'self' data:`` is here because the inserted
#: SVG is part of the document, not a separate image request; nothing else is
#: allowed to load at all.
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; form-action 'none'; "
    "base-uri 'none'; frame-ancestors 'none'"
)

#: Path -> (route label, the one method that path implements). Paths are
#: matched exactly and never joined to the filesystem, so ``/../viewer.js`` and
#: ``/etc/passwd`` are simply unknown paths.
ROUTES = {
    "/": ("index", "GET", "viewer.html", "text/html; charset=utf-8"),
    "/viewer.css": ("css", "GET", "viewer.css", "text/css; charset=utf-8"),
    "/viewer.js": ("js", "GET", "viewer.js", "text/javascript; charset=utf-8"),
    "/api/chart": ("api_chart", "POST", None, None),
    "/api/places": ("api_places", "POST", None, None),
}

#: Section 11.3 item 5, as Layer 15 section 5.2 extends it: the six words a
#: normal log line may begin with.
ROUTE_LABELS = ("index", "css", "js", "api_chart", "api_places", "other")

STATIC_FILES = ("viewer.html", "viewer.css", "viewer.js")

#: The placeholder ``viewer.html`` carries in place of the per-launch token.
TOKEN_PLACEHOLDER = "__VIEWER_TOKEN__"

#: Layer 15 section 4.2: the page's inline note names the default birthplace,
#: so the document carries the effective record's id and label in a meta tag
#: and an override is reflected automatically. The substitution is tolerant of
#: an absent placeholder: a page that does not carry the tag is served
#: unchanged rather than refused.
DEFAULT_PLACE_ID_PLACEHOLDER = "__VIEWER_DEFAULT_PLACE_ID__"
DEFAULT_PLACE_LABEL_PLACEHOLDER = "__VIEWER_DEFAULT_PLACE_LABEL__"

TOKEN_HEADER = "X-Viewer-Token"

#: Section 12: the ``kind`` the base handler's own conditions map to.
BASE_HANDLER_KINDS = {
    400: "bad_request",
    414: "uri_too_long",
    431: "headers_too_large",
    501: "not_implemented",
    505: "http_505",
}

#: Decision D15, section 2.1. Held around the pipeline call and the row
#: extraction of ``POST /api/chart``, and around nothing else. Plain, not reentrant: nothing inside
#: the held block calls anything that would want it again.
ENGINE_LOCK = threading.Lock()

#: Section 11.3 item 3. Explicit ASCII digits, one to five of them: a signed,
#: spaced, padded or non-ASCII value is a malformed header, not a number to be
#: coaxed into shape by ``int()`` (which accepts all four).
_CONTENT_LENGTH_PATTERN = re.compile(r"[0-9]{1,5}")

#: The same discipline for ``--port``: ``str.isdigit`` is true for fullwidth
#: digits, which ``int()`` also accepts.
_PORT_PATTERN = re.compile(r"[0-9]{1,5}")

#: And for ``--default-place-id`` (Layer 15 section 4.2).
_PLACE_ID_PATTERN = re.compile(r"[0-9]{1,12}")

#: The four characters that would end a quoted HTML attribute or start a tag.
#: A place label is data from the geodata database, and it is written into the
#: default-place meta tag, so it is escaped there rather than trusted.
_ATTRIBUTE_ESCAPES = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
)


def _stderr(message: str) -> None:
    print(message, file=sys.stderr)


# --- configuration and the server ------------------------------------------


@dataclass(frozen=True)
class ViewerConfig:
    """What one launch of the viewer was asked for.

    ``geodata_path`` and ``ephemeris_path`` are handed to ``ChartConfig``
    unchanged: that class is the single validator of both, stores their
    absolute resolved forms, and refuses a wrong kind of value before touching
    the filesystem. Repeating any of that here would be a second source of
    truth.

    ``default_place_id`` is None when ``--default-place-id`` was not given,
    and the built-in :data:`DEFAULT_PLACE_ID` applies. The distinction is kept
    rather than folded away because the banner states whether the default was
    overridden (Layer 15 section 4.2).
    """

    geodata_path: str
    ephemeris_path: str
    port: int = 0
    open_browser: bool = False
    verbose: bool = False
    default_place_id: "int | None" = None


class ViewerServer(http.server.ThreadingHTTPServer):
    """The bound loopback server, with everything one launch needs on it.

    ``create`` performs steps 2 to 5 of section 4.2 -- configuration, banner
    metadata, token, static files, bind -- and prints nothing. The exit-code
    mapping belongs to :func:`serve`, so an embedding caller (the repository
    tests, the acceptance script) sees the typed exceptions themselves.
    """

    daemon_threads = True

    #: Set by ``create``; declared here so the attributes are documented in one
    #: place rather than appearing out of a constructor.
    config: ViewerConfig
    chart_config: ChartConfig
    metadata_rows: list
    token: str
    url: str
    port: int
    allowed_hosts: frozenset
    allowed_origins: frozenset
    static: dict
    #: Layer 15 section 4.2: the effective default birthplace, read once from
    #: the configured database and reused for every defaulted request. There
    #: is no per-request database read for the default.
    default_place_id: int
    default_place_override: bool
    default_location: object
    default_place: object
    default_label: str

    @classmethod
    def create(cls, config: "ViewerConfig") -> "ViewerServer":
        """Steps 2 to 5 of section 4.2, in order, then return the bound server.

        The two resource failures are wrapped in ``ConfigurationError`` on
        purpose. Step 3's failure is documented as "caught as ``Exception``
        here, since the viewer imports no ``sqlite3`` name", and step 4's is a
        missing package file; both mean *a configured resource cannot be used*,
        which is exactly what ``ConfigurationError`` says and what
        :func:`serve` maps to exit 4. A bind failure keeps its own ``OSError``,
        which is how :func:`serve` tells the two apart without inspecting a
        message.
        """
        if not isinstance(config, ViewerConfig):
            raise TypeError(
                f"config must be a ViewerConfig; got {type(config).__name__}."
            )

        # Step 2. ChartConfig is the single validator of both resources.
        chart_config = ChartConfig(
            geodata_path=config.geodata_path,
            ephemeris_path=config.ephemeris_path,
        )

        # Step 3. The connection is closed by the context manager on every
        # path, including the failing one.
        try:
            with OfflineLocationResolver(chart_config.geodata_path) as resolver:
                metadata_rows = list(resolver.dataset_metadata())
        except Exception as error:  # noqa: BLE001 -- documented in step 3
            raise ConfigurationError(
                f"geodata metadata could not be read: {error}"
            ) from error

        # Step 3a (Layer 15 section 4.2). The effective default birthplace,
        # looked up by primary key in the configured database, which is
        # authoritative: what is validated is that the record exists there and
        # yields a valid location with a land time zone, not that its contents
        # equal the values recorded in section 4.1. There is no fallback to
        # another record, and this happens before the bind.
        default_place_id = (
            DEFAULT_PLACE_ID
            if config.default_place_id is None
            else config.default_place_id
        )
        try:
            with OfflineLocationResolver(chart_config.geodata_path) as resolver:
                default_location, default_place = resolver.record(
                    default_place_id
                )
                default_label = resolver.candidate_label(default_place)
        except Exception as error:  # noqa: BLE001 -- documented above
            raise ConfigurationError(
                f"the default birthplace record {default_place_id} is not "
                f"available in {chart_config.geodata_path}: {error}"
            ) from error

        # Step 4. The token first, then the files it is substituted into.
        token = secrets.token_urlsafe(32)
        try:
            static = _load_static_files()
        except Exception as error:  # noqa: BLE001 -- a packaging failure
            raise ConfigurationError(
                f"the viewer's static files could not be read: {error}"
            ) from error
        static["viewer.html"] = _substituted_index(
            static["viewer.html"], token, default_place_id, default_label
        )

        # Step 5. Binding is the last thing that happens, so a configuration
        # failure never leaves a socket behind.
        server = cls((BIND_HOST, config.port), _ViewerHandler)
        port = server.server_address[1]

        server.config = config
        server.chart_config = chart_config
        server.metadata_rows = metadata_rows
        server.token = token
        server.port = port
        server.url = f"http://{BIND_HOST}:{port}/"
        server.allowed_hosts = frozenset(
            {f"{BIND_HOST}:{port}", f"localhost:{port}"}
        )
        server.allowed_origins = frozenset(
            {f"http://{BIND_HOST}:{port}", f"http://localhost:{port}"}
        )
        server.static = static
        server.default_place_id = default_place_id
        server.default_place_override = config.default_place_id is not None
        server.default_location = default_location
        server.default_place = default_place
        server.default_label = default_label
        server._route_labels = threading.local()
        return server

    # --- diagnostics ------------------------------------------------------

    def note_label(self, label: str) -> None:
        """Record which route this connection's thread is serving.

        ``handle_error`` runs in the worker thread that raised, so a
        thread-local is enough to name the route in its one line without
        keeping any shared state.
        """
        self._route_labels.label = label

    def current_label(self) -> str:
        return getattr(self._route_labels, "label", "other")

    def handle_error(self, request, client_address) -> None:
        """One line for a client that went away; the traceback only if asked.

        The default implementation prints a full traceback for every dropped
        connection, which a browser produces routinely when it abandons a
        superseded fetch (section 10.2). One line says the same thing without
        burying the log.
        """
        _stderr(f"connection closed by client during {self.current_label()}")
        if self.config.verbose:
            traceback.print_exc()


def _load_static_files() -> dict:
    """The three package files, read once into memory (section 2.1)."""
    root = importlib.resources.files("vedic_chart.viewer").joinpath("static")
    return {
        name: root.joinpath(name).read_bytes() for name in STATIC_FILES
    }


def _attribute_text(value: str) -> str:
    """One string, safe to write inside a double-quoted HTML attribute."""
    for character, replacement in _ATTRIBUTE_ESCAPES:
        value = value.replace(character, replacement)
    return value


def _substituted_index(
    document: bytes, token: str, place_id: int, label: str
) -> bytes:
    """The index page with the per-launch values written into it.

    Three placeholders, each replaced only where it is present: a page that
    carries none of them is returned byte for byte, which is what lets the
    document and this module be revised one at a time (Layer 15 section 4.2).
    """
    for placeholder, value in (
        (TOKEN_PLACEHOLDER, token),
        (DEFAULT_PLACE_ID_PLACEHOLDER, str(place_id)),
        (DEFAULT_PLACE_LABEL_PLACEHOLDER, _attribute_text(label)),
    ):
        document = document.replace(
            placeholder.encode("ascii"), value.encode("utf-8")
        )
    return document


# --- the request handler ---------------------------------------------------


class _ViewerHandler(http.server.BaseHTTPRequestHandler):
    """One connection. Private: the public surface is the three exported names.

    ``protocol_version`` keeps its ``HTTP/1.0`` default, so ``Connection:
    close`` is implied and one connection carries one request. That is what
    makes the response-writing path simple enough to have a single
    implementation.
    """

    timeout = HANDLER_TIMEOUT

    # --- responses --------------------------------------------------------

    def _respond(
        self,
        status: int,
        content_type: str,
        body: bytes,
        *,
        label: str,
        allow=None,
    ) -> None:
        """The one place a response is written (section 11.3 item 4).

        ``send_response_only`` writes the status line and nothing else; every
        header below is therefore deliberate and the set is identical on a
        200, a 403 and a 501.

        A request line the base class could not parse leaves
        ``request_version`` at ``HTTP/0.9``, for which ``send_response_only``
        and ``end_headers`` write *nothing at all*. Section 13.2 requires the
        malformed-request-line and bad-version paths to answer with the full
        JSON document and header set, so the version is normalised to the one
        this server speaks before anything is written. Nothing else reads
        ``request_version`` after this point.
        """
        if self.request_version == "HTTP/0.9":
            self.request_version = self.protocol_version

        phrase = _status_phrase(status)
        self.send_response_only(status, phrase)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        if allow is not None:
            self.send_header("Allow", allow)
        self.end_headers()
        self.wfile.write(body)
        self._log(label, status)

    def _fail(
        self,
        status: int,
        kind: str,
        message: str,
        label: str,
        *,
        allow=None,
    ) -> None:
        body = transport.encode(transport.error_document(kind, message))
        self._respond(
            status, JSON_CONTENT_TYPE, body, label=label, allow=allow
        )

    def send_error(self, code, message=None, explain=None) -> None:
        """The base handler's own refusals, answered like every other response.

        ``BaseHTTPRequestHandler`` calls this before routing for a method with
        no ``do_`` handler (501), a malformed request line (400), an
        unsupported HTTP version (505), an over-long request line (414) and
        more than a hundred header lines (431). Avoiding explicit ``send_error``
        calls in our own code would therefore not be enough: this override is
        what makes those paths carry the JSON document, the full header set and
        the ``other <status>`` log line (section 11.3 item 2).

        ``self.headers`` may not exist yet on some of these paths, so nothing
        here reads a header.
        """
        kind = BASE_HANDLER_KINDS.get(code, f"http_{code}")
        text = message if message else _status_phrase(code)
        self.close_connection = True
        self._fail(code, kind, str(text), "other")

    # --- logging ----------------------------------------------------------

    def _log(self, label: str, status) -> None:
        _stderr(f"{label} {status}")

    def log_message(self, format, *args) -> None:
        """Silence. Every line this server prints goes through ``_log``."""

    def log_request(self, code="-", size="-") -> None:
        """Silence: ``send_response`` is never called, and this with it."""

    def log_error(self, format, *args) -> None:
        """The base class's one remaining diagnostic: the read timeout.

        ``handle_one_request`` answers a connection that stops sending with
        ``log_error("Request timed out: %r", e)``. It becomes ``other
        timeout``, which is the same ``<label> <status>`` shape as every other
        line and carries nothing about the request. Any other message the base
        class might invent is dropped rather than printed unexamined.
        """
        if "timed out" in str(format):
            self._log("other", "timeout")

    # --- routing ----------------------------------------------------------

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        route = ROUTES.get(self.path)
        matched = route is not None and route[1] == method
        label = route[0] if matched else "other"
        self.server.note_label(label)

        # 1. Host, before anything is served, on every route: a request that
        #    reached us under another name is a DNS-rebinding attempt.
        hosts = self.headers.get_all("Host") or []
        if len(hosts) != 1 or hosts[0].lower() not in self.server.allowed_hosts:
            self._fail(
                400,
                "bad_request",
                "the Host header must be exactly 127.0.0.1:<port> or "
                "localhost:<port> for this server's port.",
                label,
            )
            return

        # 2. Exact path match. A query string makes the path unknown, which is
        #    what section 11.3 asks for: the page never sends one.
        if route is None:
            self._fail(
                404, "not_found", "no such resource on this server.", label
            )
            return
        if not matched:
            self._fail(
                405,
                "method_not_allowed",
                f"{method} is not allowed on this path.",
                label,
                allow=route[1],
            )
            return

        if label == "api_chart":
            self._api_chart(label)
        elif label == "api_places":
            self._api_places(label)
        else:
            self._static(route, label)

    def _static(self, route, label: str) -> None:
        body = self.server.static[route[2]]
        self._respond(200, route[3], body, label=label)

    # --- POST /api/chart --------------------------------------------------

    def _api_chart(self, label: str) -> None:
        body = self._read_api_body(label, MAX_BODY_BYTES)
        if body is None:
            return

        try:
            parsed = transport.parse_request(body)
        except StaleSchemaError as error:
            self._fail(400, "stale_schema", str(error), label)
            return
        except (
            TransportError,
            InvalidBirthDateError,
            InvalidBirthTimeError,
            InvalidPlaceQueryError,
        ) as error:
            self._fail(400, "input", str(error), label)
            return

        # Types decide, never messages (Layer 11 section 8.4). The engine's
        # bare RuntimeError for an instant outside the ephemeris files' UT
        # coverage is deliberately not reclassified by reading its text.
        try:
            effective = _effective_input(self.server, parsed)
            with ENGINE_LOCK:
                result = render_chart_and_dasha_at(
                    effective.request,
                    effective.location,
                    self.server.chart_config,
                    transport.RENDERER_OPTIONS,
                    transport.YEAR,
                )
                rows = dasha_rows(result.timeline, depth=transport.DEPTH)
            document = transport.serialize(
                result, parsed, effective=effective, rows=rows
            )
        except PlaceSelectionRequiredError as error:
            self._fail(400, "place_selection_required", str(error), label)
            return
        except DashaRangeError as error:
            self._fail(400, "dasha_range", str(error), label)
            return
        except (
            TransportError,
            InvalidBirthDateError,
            InvalidBirthTimeError,
            InvalidPlaceQueryError,
            InvalidTimezoneError,
            NonexistentLocalTimeError,
            AmbiguousLocalTimeError,
        ) as error:
            self._fail(400, "input", str(error), label)
            return
        except PlaceNotFoundError as error:
            self._fail(404, "place_not_found", str(error), label)
            return
        except (
            ConfigurationError,
            GeodataError,
            InvalidCoordinateError,
        ) as error:
            self._fail(500, "resource", str(error), label)
            return
        except Exception as error:  # noqa: BLE001 -- the documented generic case
            if self.server.config.verbose:
                traceback.print_exc()
            self._fail(
                500,
                "unexpected",
                f"{type(error).__name__}: {error}",
                label,
            )
            return

        self._respond(
            200, JSON_CONTENT_TYPE, transport.encode(document), label=label
        )

    # --- POST /api/places -------------------------------------------------

    def _api_places(self, label: str) -> None:
        """Layer 15 section 5.2: the offline suggestions endpoint.

        Every check of section 11.3 applies unchanged -- they are the same
        code -- with a 256-byte body cap of its own. The engine lock is **not**
        held: nothing here touches the Swiss Ephemeris, and a suggestion
        keystroke must never queue behind a calculation. The resolver is
        opened read-only for the one query and closed again.
        """
        body = self._read_api_body(label, MAX_PLACES_BODY_BYTES)
        if body is None:
            return

        try:
            query = transport.parse_places_request(body)
        except TransportError as error:
            self._fail(400, "input", str(error), label)
            return

        try:
            with OfflineLocationResolver(
                self.server.chart_config.geodata_path
            ) as resolver:
                document = transport.suggestions_document(
                    query,
                    [
                        (
                            candidate,
                            resolver.candidate_label(candidate),
                            resolver.suggestion_label(candidate),
                        )
                        for candidate in resolver.suggest(
                            query, limit=SUGGESTION_LIMIT
                        )
                    ],
                )
        except (
            ConfigurationError,
            GeodataError,
            InvalidCoordinateError,
        ) as error:
            self._fail(500, "resource", str(error), label)
            return
        except Exception as error:  # noqa: BLE001 -- the documented generic case
            if self.server.config.verbose:
                traceback.print_exc()
            self._fail(
                500,
                "unexpected",
                f"{type(error).__name__}: {error}",
                label,
            )
            return

        self._respond(
            200, JSON_CONTENT_TYPE, transport.encode(document), label=label
        )

    def _read_api_body(self, label: str, maximum: int):
        """Section 11.3 item 3, in order. ``None`` means already answered."""
        # Origin, then the fallback for browsers that omit it on same-origin
        # POSTs. A foreign Origin is 403 whatever Sec-Fetch-Site claims.
        origin = self.headers.get("Origin")
        if origin is not None:
            if origin not in self.server.allowed_origins:
                self._fail(
                    403,
                    "forbidden",
                    "the Origin header is not this server's own origin.",
                    label,
                )
                return None
        elif self.headers.get("Sec-Fetch-Site") != "same-origin":
            self._fail(
                403,
                "forbidden",
                "a request without an Origin header must carry "
                "Sec-Fetch-Site: same-origin.",
                label,
            )
            return None

        supplied = self.headers.get(TOKEN_HEADER)
        if supplied is None or not supplied.isascii():
            self._fail(
                403,
                "forbidden",
                f"the {TOKEN_HEADER} header is missing or malformed.",
                label,
            )
            return None
        if not secrets.compare_digest(supplied, self.server.token):
            self._fail(
                403, "forbidden", f"the {TOKEN_HEADER} header is wrong.", label
            )
            return None

        # The page never chunks, and accepting a chunked body would mean a
        # second body-reading path with a second set of bounds.
        if self.headers.get_all("Transfer-Encoding"):
            self._fail(
                400,
                "bad_request",
                "Transfer-Encoding is not accepted on this endpoint.",
                label,
            )
            return None

        lengths = self.headers.get_all("Content-Length") or []
        if not lengths:
            self._fail(
                411,
                "length_required",
                "Content-Length is required on this endpoint.",
                label,
            )
            return None
        if len(lengths) != 1:
            self._fail(
                400,
                "bad_request",
                "Content-Length must appear exactly once.",
                label,
            )
            return None
        if _CONTENT_LENGTH_PATTERN.fullmatch(lengths[0]) is None:
            self._fail(
                400,
                "bad_request",
                "Content-Length must be one to five ASCII digits.",
                label,
            )
            return None
        length = int(lengths[0])
        if length == 0:
            self._fail(
                400, "bad_request", "Content-Length must be greater than 0.", label
            )
            return None
        if length > maximum:
            # Answered before a single body byte is read.
            self._fail(
                413,
                "payload_too_large",
                f"the request body may not exceed {maximum} bytes.",
                label,
            )
            return None

        content_type = self.headers.get("Content-Type")
        if not _acceptable_content_type(content_type):
            self._fail(
                415,
                "unsupported_media_type",
                "Content-Type must be application/json, optionally with "
                "charset=utf-8.",
                label,
            )
            return None

        try:
            body = self.rfile.read(length)
        except TimeoutError:
            self.close_connection = True
            self._fail(
                408,
                "request_timeout",
                "the request body did not arrive within the read timeout.",
                label,
            )
            return None
        if len(body) != length:
            self.close_connection = True
            self._fail(
                400,
                "bad_request",
                "the request body was shorter than Content-Length.",
                label,
            )
            return None
        return body


def _effective_input(
    server: "ViewerServer", parsed
) -> "transport.EffectiveInput":
    """The one place the four birthplace combinations are decided (5.3, 7.2).

    ``place_text``/``place_id``, after ``strip``:

    * blank, blank -- the configured default record, ``place_assumed``;
    * non-blank, blank -- 400 ``place_selection_required``: a typed birthplace
      without a chosen suggestion is neither resolved nor defaulted;
    * blank, non-blank -- an identifier without its label is inconsistent;
    * non-blank, non-blank -- the identifier is used, and the submitted text
      must equal the label this server builds for that record. The viewer
      never substitutes another record for the one the page named.

    The request handed to the engine carries the record's label as its
    ``place_query``: Layer 1 requires a non-blank string, and on this path it
    is informational only and is never resolved.
    """
    if parsed.place_id is None:
        if not parsed.place_text_blank:
            raise PlaceSelectionRequiredError(
                "select a suggestion from the list, or clear the birthplace "
                "field to use the default birthplace."
            )
        location = server.default_location
        place = server.default_place
        label = server.default_label
        place_assumed = True
        source = transport.SOURCE_DEFAULT
    else:
        if parsed.place_text_blank:
            raise TransportError(
                "inconsistent: an identifier without its label. Clear the "
                "birthplace field, or choose a suggestion again."
            )
        # Opened read-only for the one lookup and closed again; the default
        # record is never re-read, it was resolved once at start-up.
        with OfflineLocationResolver(server.chart_config.geodata_path) as resolver:
            location, place = resolver.record(parsed.place_id)
            label = resolver.candidate_label(place)
        if parsed.submitted_place_text != label:
            raise TransportError(
                "the selected label does not match the record: the page sent "
                f"{parsed.submitted_place_text!r} for record "
                f"{parsed.place_id}, which this database calls {label!r}."
            )
        place_assumed = False
        source = transport.SOURCE_SELECTED

    request = BirthChartRequest(
        birth_date=parsed.birth_date,
        birth_time=parsed.birth_time,
        place_query=label,
    )
    return transport.EffectiveInput(
        request=request,
        location=location,
        place=place,
        label=label,
        place_assumed=place_assumed,
        time_assumed=parsed.time_assumed,
        source=source,
    )


def _acceptable_content_type(raw) -> bool:
    """``application/json``, optionally with the single ``charset=utf-8``.

    Type and parameter name are matched case-insensitively, as HTTP requires;
    the parameter *value* is matched case-insensitively too, since ``UTF-8``
    and ``utf-8`` name one encoding. Any second parameter, any other parameter
    name and any other charset are refused rather than ignored: ignoring a
    parameter is deciding it did not matter.
    """
    if raw is None:
        return False
    parts = raw.split(";")
    if parts[0].strip().lower() != "application/json":
        return False
    parameters = [part.strip() for part in parts[1:] if part.strip()]
    if not parameters:
        return True
    if len(parameters) != 1:
        return False
    name, separator, value = parameters[0].partition("=")
    if not separator:
        return False
    return (
        name.strip().lower() == "charset"
        and value.strip().lower() == "utf-8"
    )


def _status_phrase(status) -> str:
    """The reason phrase for a status line, or a neutral word.

    ``send_response_only`` formats the phrase into the status line with ``%s``,
    so a ``None`` would literally print ``None``. The base class hands us codes
    it chose itself, including ones with no message, so every phrase is looked
    up here.
    """
    try:
        return http.server.BaseHTTPRequestHandler.responses[status][0]
    except Exception:  # noqa: BLE001 -- an unknown code is not a failure
        return "Error"


# --- the command-line lifecycle --------------------------------------------


def _print_banner(server: "ViewerServer") -> None:
    """Section 4.2 step 6. The token is never printed."""
    config = server.chart_config
    print(f"viewer: {server.url}")
    print(f"geodata: {config.geodata_path}")
    for row in server.metadata_rows:
        dataset = row.get("dataset", "?")
        release = row.get("source_release", "?")
        digest = row.get("sha256", "?")
        rows_count = row.get("row_count", "?")
        print(
            f"geodata metadata: {dataset} = {release}, sha256 {digest}, "
            f"{rows_count} rows"
        )
    override = " (override)" if server.default_place_override else ""
    print(
        f"default place: {server.default_place_id} = {server.default_label} "
        f"({server.default_location.timezone_id}){override}"
    )
    print(f"ephemeris: {config.ephemeris_path}")
    for path in config.ephemeris_files:
        print(f"ephemeris file: {path} ({_file_size(path)} bytes)")
    print(
        "dasha year convention: 365.256363 days (Mean Sidereal year, fixed by "
        "the viewer)"
    )
    if server.config.verbose:
        print(
            "verbose: diagnostics on stderr may contain request data, "
            "including a place query or a date inside an exception message"
        )
    print("press Ctrl-C to stop")


def _file_size(path: Path):
    try:
        return path.stat().st_size
    except OSError as error:  # pragma: no cover - ChartConfig already read it
        return f"unreadable: {error}"


def _open_browser(url: str) -> None:
    """Decision D3: a failure to open a browser is a warning, never fatal."""
    try:
        opened = webbrowser.open(url)
    except Exception as error:  # noqa: BLE001 -- every backend is possible
        _stderr(f"warning: could not open a browser: {error}")
        return
    if not opened:
        _stderr(
            "warning: could not open a browser: no usable browser was found. "
            f"Open {url} yourself."
        )


def serve(config: ViewerConfig) -> int:
    """The command-line lifecycle of section 4.2, as an exit code.

    Returns 130 on ``KeyboardInterrupt`` and never returns 0 while serving; a
    0 can only come from another thread calling ``shutdown()``, which the
    command line never does.
    """
    try:
        server = ViewerServer.create(config)
    except ConfigurationError as error:
        _stderr(f"error: {error}")
        return EXIT_CONFIG
    except OSError as error:
        _stderr(f"error: cannot bind {BIND_HOST}:{config.port}: {error}")
        return EXIT_BIND

    try:
        _print_banner(server)
        if config.open_browser:
            _open_browser(server.url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return EXIT_INTERRUPTED
        except Exception:  # noqa: BLE001 -- the documented generic case
            traceback.print_exc()
            return EXIT_UNEXPECTED
        return EXIT_OK
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    finally:
        # The listening socket, and only it: with daemon_threads a worker in
        # the middle of a request is not joined and not interrupted here.
        server.server_close()


# --- arguments -------------------------------------------------------------


def _port_number(text: str) -> int:
    if _PORT_PATTERN.fullmatch(text) is None:
        raise argparse.ArgumentTypeError(
            f"expected a port number between {MIN_PORT} and {MAX_PORT}; got "
            f"{text!r}."
        )
    value = int(text)
    if not MIN_PORT <= value <= MAX_PORT:
        raise argparse.ArgumentTypeError(
            f"expected a port number between {MIN_PORT} and {MAX_PORT}; got "
            f"{text!r}."
        )
    return value


def _place_id_number(text: str) -> int:
    """``--default-place-id``: ASCII digits, exactly as ``--port`` is read."""
    if _PLACE_ID_PATTERN.fullmatch(text) is None:
        raise argparse.ArgumentTypeError(
            "expected a GeoNames identifier of one to twelve ASCII digits; "
            f"got {text!r}."
        )
    return int(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "Serve the interactive D1 chart and Vimshottari dasha viewer on "
            "127.0.0.1 until Ctrl-C. Local, single-user, no network access "
            "beyond the loopback interface."
        ),
    )
    parser.add_argument(
        "--geodata",
        required=True,
        metavar="PATH",
        help="geodata SQLite database (required; there is no default)",
    )
    parser.add_argument(
        "--ephemeris",
        required=True,
        metavar="PATH",
        help=(
            "directory holding the Swiss Ephemeris .se1 files (required; "
            "there is no default)"
        ),
    )
    parser.add_argument(
        "--port",
        type=_port_number,
        default=0,
        metavar="N",
        help="TCP port on 127.0.0.1 (default: 0, meaning OS-assigned)",
    )
    parser.add_argument(
        "--default-place-id",
        type=_place_id_number,
        default=None,
        metavar="ID",
        help=(
            "GeoNames identifier of the birthplace assumed when the "
            f"birthplace field is left blank (default: {DEFAULT_PLACE_ID}, "
            "Jammu, Jammu and Kashmir, India). The record must exist in the "
            "configured geodata database or the viewer exits 4"
        ),
    )
    parser.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        help="try to open the URL in a browser; a failure is only a warning",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "add exception tracebacks on stderr; opt-in diagnostics that may "
            "contain request data"
        ),
    )
    return parser


def main(argv=None) -> int:
    """Parse arguments into a :class:`ViewerConfig` and serve.

    argparse owns its own conventions: usage on stderr and exit 2 for a bad
    flag, 0 for ``--help``. Nothing else has happened by then.
    """
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        code = exit_request.code
        return int(code) if code is not None else EXIT_OK

    return serve(
        ViewerConfig(
            geodata_path=args.geodata,
            ephemeris_path=args.ephemeris,
            port=args.port,
            open_browser=args.open_browser,
            verbose=args.verbose,
            default_place_id=args.default_place_id,
        )
    )
