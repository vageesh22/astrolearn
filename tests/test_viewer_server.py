"""Layer 14's live server: routes, HTTP contract, timeouts, lifecycle (13.2).

A real :class:`~vedic_chart.viewer.ViewerServer` on ``127.0.0.1:0``, over the
committed fixture geodata database and the committed ``ephe/`` directory. Never
any other interface, never the production database, no network, no clock.

The fixture database holds the exact records this module names -- Jalandhar
(1268782), London (2643743), Hyderabad India (1269843) and five Springfields --
and does **not** hold Jammu, the built-in default record 1269321, which belongs
to the production acceptance run of Layer 15 section 13. **Every normal server
here is therefore started with the explicit override ``--default-place-id
1268782``** (Jalandhar), and the unavailable built-in default is tested
separately, exactly as Layer 15 section 13 requires. Every assertion names the
exact record it applies to and carries no count from one to another.

Most requests are built and read as **raw bytes** rather than through
``http.client``, because a good part of the contract is about requests
``http.client`` would refuse to send: a duplicate ``Content-Length``, a value
with a trailing space, a malformed request line, an impossible HTTP version, a
70 000-byte request line, 150 header lines. The same helper then serves the
well-formed cases, so every test reads the same way.

Nothing here asserts an order of completion. The engine lock guarantees mutual
exclusion only (specification 2.1); the concurrency test therefore asserts that
two calculations never overlap and that all three requests succeed, and says
nothing about which finished first.
"""

import json
import re
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

from render_helpers import EPHE_DIR, FIXTURE_DB, REPO_ROOT
from vedic_chart.app import ConfigurationError
from vedic_chart.dasha import DashaRangeError
from vedic_chart.viewer import ViewerConfig, ViewerServer, serve
from vedic_chart.viewer import server as server_module

STATIC_DIR = REPO_ROOT / "src" / "vedic_chart" / "viewer" / "static"

#: Every header of specification 11.3 item 4, on every response.
REQUIRED_HEADERS = {
    "content-type",
    "content-length",
    "cache-control",
    "x-content-type-options",
    "referrer-policy",
    "x-frame-options",
    "content-security-policy",
}

EXPECTED_HEADER_VALUES = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "content-security-policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; form-action 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    ),
}

#: The reference birth, with the two optional fields left to each test.
BIRTH = {"date": "1995-03-21", "time": "06:45"}

#: The fixture's own records. The label is the one the server builds for the
#: record (Layer 15 section 5.2), which is what the page sends back.
JALANDHAR_ID = 1268782
JALANDHAR_LABEL = "Jalandhar, Punjab, India"
LONDON_ID = 2643743
LONDON_LABEL = "London, England, United Kingdom"
HYDERABAD_ID = 1269843
HYDERABAD_LABEL = "Hyderabad, Telangana, India"

#: The built-in default (Layer 15 section 4.1). Not in the fixture database.
BUILT_IN_DEFAULT_ID = 1269321

JSON_TYPE = "application/json"

_TOKEN_META = re.compile(r'<meta name="viewer-token" content="([^"]*)">')


# --- the running server -----------------------------------------------------


class Running:
    """A bound, serving :class:`ViewerServer` plus what tests need from it."""

    def __init__(self, server: ViewerServer) -> None:
        self.server = server
        self.port = server.port
        self.token = server.token
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=10)
        self.server.server_close()


def make_config(**changes) -> ViewerConfig:
    """A launch over the fixture database, with the documented override.

    The fixture holds no Jammu, so the built-in default record 1269321 is not
    available in it and ``create`` would refuse to start (Layer 15 section
    4.2). Every normal server in this module therefore names Jalandhar
    explicitly, which is what the acceptance run does with
    ``--default-place-id 1268782``. Pass ``default_place_id=None`` to get the
    built-in default back.
    """
    values = {
        "geodata_path": str(FIXTURE_DB),
        "ephemeris_path": EPHE_DIR,
        "port": 0,
        "default_place_id": JALANDHAR_ID,
    }
    values.update(changes)
    return ViewerConfig(**values)


def start(**changes) -> Running:
    return Running(ViewerServer.create(make_config(**changes)))


@pytest.fixture(scope="module")
def live():
    running = start()
    try:
        # One calculation before any timing assertion, so that sqlite's page
        # cache and the ephemeris files are warm for every later test.
        post(running)
        yield running
    finally:
        running.stop()


# --- raw request and response helpers --------------------------------------


def build(
    method,
    path,
    *,
    port,
    host=None,
    version="HTTP/1.1",
    headers=(),
    body=None,
    request_line=None,
) -> bytes:
    if request_line is None:
        request_line = f"{method} {path} {version}"
    lines = [request_line]
    if host is not False:
        lines.append(f"Host: {host if host else f'127.0.0.1:{port}'}")
    for name, value in headers:
        lines.append(f"{name}: {value}")
    head = "\r\n".join(lines).encode("latin-1")
    payload = b"" if body is None else body
    return b"".join((head, b"\r\n\r\n", payload))


def exchange(running, raw: bytes, *, timeout=20) -> bytes:
    sock = socket.create_connection(("127.0.0.1", running.port), timeout=timeout)
    try:
        sock.sendall(raw)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        sock.close()


class Answer:
    def __init__(self, raw: bytes) -> None:
        head, _, body = raw.partition(b"\r\n\r\n")
        self.raw = raw
        self.body = body
        self.headers: dict = {}
        self.status = None
        if not head:
            return
        lines = head.decode("latin-1").split("\r\n")
        parts = lines[0].split(" ")
        self.status = int(parts[1]) if len(parts) > 1 else None
        for line in lines[1:]:
            name, _, value = line.partition(":")
            self.headers.setdefault(name.strip().lower(), []).append(value.strip())

    def header(self, name):
        values = self.headers.get(name.lower())
        return values[0] if values else None

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    def text(self):
        return self.body.decode("utf-8")


def get(running, path="/", **kwargs) -> Answer:
    return Answer(exchange(running, build("GET", path, port=running.port, **kwargs)))


def post(
    running,
    *,
    place_text="",
    place_id="",
    payload=None,
    token=True,
    origin=True,
    sec_fetch_site=None,
    content_type=JSON_TYPE,
    content_length=True,
    extra=(),
    path="/api/chart",
    host=None,
) -> Answer:
    """One ``POST``. The birthplace defaults to blank -- the default record."""
    if payload is None:
        payload = dict(BIRTH, place_text=place_text, place_id=place_id)
    body = (
        payload
        if isinstance(payload, bytes)
        else json.dumps(payload).encode("utf-8")
    )

    headers = []
    if origin is True:
        headers.append(("Origin", f"http://127.0.0.1:{running.port}"))
    elif origin:
        headers.append(("Origin", origin))
    if sec_fetch_site is not None:
        headers.append(("Sec-Fetch-Site", sec_fetch_site))
    if token is True:
        headers.append(("X-Viewer-Token", running.token))
    elif token:
        headers.append(("X-Viewer-Token", token))
    if content_type is not None:
        headers.append(("Content-Type", content_type))
    if content_length is True:
        headers.append(("Content-Length", str(len(body))))
    elif content_length:
        headers.append(("Content-Length", content_length))
    headers.extend(extra)

    return Answer(
        exchange(
            running,
            build(
                "POST",
                path,
                port=running.port,
                host=host,
                headers=headers,
                body=body,
            ),
        )
    )


def assert_contract_headers(answer, *, allow=None):
    """Every header of 11.3 item 4, and neither ``Server`` nor ``Date``."""
    assert set(answer.headers) >= REQUIRED_HEADERS, sorted(answer.headers)
    for name, value in EXPECTED_HEADER_VALUES.items():
        assert answer.header(name) == value
    assert "server" not in answer.headers
    assert "date" not in answer.headers
    assert answer.header("content-length") == str(len(answer.body))
    if allow is not None:
        assert answer.header("allow") == allow


def places(running, query, **changes) -> Answer:
    """One ``POST /api/places`` with the one-key body of section 5.2."""
    return post(
        running, path="/api/places", payload={"q": query}, **changes
    )


def selected(running, geoname_id, label, **changes) -> Answer:
    """A submission with a suggestion selected: the id and its own label."""
    return post(
        running, place_text=label, place_id=str(geoname_id), **changes
    )


def assert_error_document(answer, kind):
    document = answer.json()
    assert document["schema"] == "vedic_chart.viewer/2"
    assert document["error"]["kind"] == kind
    assert isinstance(document["error"]["message"], str)
    assert answer.header("content-type") == "application/json; charset=utf-8"


# --- routes and static files -----------------------------------------------


def test_the_index_carries_the_token_and_the_full_header_set(live):
    answer = get(live)

    assert answer.status == 200
    assert_contract_headers(answer)
    assert answer.header("content-type") == "text/html; charset=utf-8"
    match = _TOKEN_META.search(answer.text())
    assert match is not None
    assert match.group(1) == live.token
    assert "__VIEWER_" not in answer.text()


@pytest.mark.parametrize(
    "path,content_type",
    (
        ("/viewer.css", "text/css; charset=utf-8"),
        ("/viewer.js", "text/javascript; charset=utf-8"),
    ),
)
def test_the_static_files_are_served_byte_for_byte(live, path, content_type):
    answer = get(live, path)

    assert answer.status == 200
    assert_contract_headers(answer)
    assert answer.header("content-type") == content_type
    assert answer.body == (STATIC_DIR / path.lstrip("/")).read_bytes()


def test_the_index_is_the_package_file_with_the_launch_values_substituted(
    live
):
    """The package file, with the three placeholders replaced and no more.

    The replacement is restated here as three plain substitutions rather than
    borrowed from the server, and it holds whether or not the committed page
    carries the default-place placeholders: a page without them is served byte
    for byte (Layer 15 section 4.2). The label needs no attribute escaping --
    ``Jalandhar, Punjab, India`` carries none of the four characters that
    would -- which is asserted separately.
    """
    answer = get(live)
    expected = (STATIC_DIR / "viewer.html").read_bytes()
    for placeholder, value in (
        (b"__VIEWER_TOKEN__", live.token.encode("ascii")),
        (b"__VIEWER_DEFAULT_PLACE_ID__", str(JALANDHAR_ID).encode("ascii")),
        (b"__VIEWER_DEFAULT_PLACE_LABEL__", JALANDHAR_LABEL.encode("utf-8")),
    ):
        expected = expected.replace(placeholder, value)

    assert answer.body == expected
    assert b"__VIEWER_" not in answer.body


@pytest.mark.parametrize(
    "path", ("/?x=1", "/viewer.css?v=2", "/../viewer.js", "/etc/passwd", "/nope")
)
def test_an_unknown_path_or_a_query_string_is_not_found(live, path):
    answer = get(live, path)

    assert answer.status == 404
    assert_contract_headers(answer)
    assert_error_document(answer, "not_found")


def test_the_other_implemented_method_is_refused_with_allow(live):
    on_api = get(live, "/api/chart")
    assert on_api.status == 405
    assert_contract_headers(on_api, allow="POST")
    assert_error_document(on_api, "method_not_allowed")

    on_places = get(live, "/api/places")
    assert on_places.status == 405
    assert_contract_headers(on_places, allow="POST")
    assert_error_document(on_places, "method_not_allowed")

    on_index = post(live, path="/", payload=b"{}")
    assert on_index.status == 405
    assert_contract_headers(on_index, allow="GET")
    assert_error_document(on_index, "method_not_allowed")


# --- the base handler's own refusals (11.3 item 2) -------------------------


BASE_HANDLER_CASES = {
    "options": (b"OPTIONS /api/chart HTTP/1.1\r\nHost: HOST\r\n\r\n", 501, "not_implemented"),
    "head": (b"HEAD / HTTP/1.1\r\nHost: HOST\r\n\r\n", 501, "not_implemented"),
    "put": (b"PUT /api/chart HTTP/1.1\r\nHost: HOST\r\n\r\n", 501, "not_implemented"),
    "garbage": (b"GARBAGE\r\n\r\n", 400, "bad_request"),
    "version": (b"GET / HTTP/9.9\r\nHost: HOST\r\n\r\n", 505, "http_505"),
}


@pytest.mark.parametrize("name", sorted(BASE_HANDLER_CASES))
def test_the_base_handler_paths_answer_like_every_other_response(
    live, capsys, name
):
    template, status, kind = BASE_HANDLER_CASES[name]
    raw = template.replace(b"HOST", f"127.0.0.1:{live.port}".encode("ascii"))

    answer = Answer(exchange(live, raw))

    assert answer.status == status
    assert_contract_headers(answer)
    assert_error_document(answer, kind)
    assert f"other {status}" in capsys.readouterr().err


def test_an_over_long_request_line_is_refused(live, capsys):
    raw = build(
        "GET",
        "/" + "a" * 70000,
        port=live.port,
    )
    answer = Answer(exchange(live, raw))

    assert answer.status == 414
    assert_contract_headers(answer)
    assert_error_document(answer, "uri_too_long")
    assert "other 414" in capsys.readouterr().err


def test_too_many_header_lines_are_refused(live, capsys):
    headers = [(f"X-Filler-{index}", "1") for index in range(150)]
    answer = Answer(
        exchange(live, build("GET", "/", port=live.port, headers=headers))
    )

    assert answer.status == 431
    assert_contract_headers(answer)
    assert_error_document(answer, "headers_too_large")
    assert "other 431" in capsys.readouterr().err


# --- the Host, Origin and token rules ---------------------------------------


@pytest.mark.parametrize("path", ("/", "/viewer.css", "/viewer.js"))
def test_a_foreign_host_is_refused_on_every_get_route(live, path):
    answer = get(live, path, host="evil.test")

    assert answer.status == 400
    assert_error_document(answer, "bad_request")
    assert_contract_headers(answer)


def test_a_foreign_host_is_refused_on_the_api_route(live):
    answer = post(live, host="evil.test")

    assert answer.status == 400
    assert_error_document(answer, "bad_request")


def test_a_missing_host_is_refused(live):
    answer = Answer(
        exchange(live, build("GET", "/", port=live.port, host=False))
    )

    assert answer.status == 400
    assert_error_document(answer, "bad_request")


@pytest.mark.parametrize("spelling", ("127.0.0.1", "localhost", "LOCALHOST"))
def test_both_permitted_hosts_are_accepted(live, spelling):
    answer = get(live, "/", host=f"{spelling}:{live.port}")

    assert answer.status == 200


def test_a_foreign_origin_is_refused_whatever_sec_fetch_site_claims(live):
    answer = post(
        live, origin="http://evil.test", sec_fetch_site="same-origin"
    )

    assert answer.status == 403
    assert_error_document(answer, "forbidden")
    assert_contract_headers(answer)


@pytest.mark.parametrize("origin_host", ("127.0.0.1", "localhost"))
def test_both_permitted_origins_are_accepted(live, origin_host):
    answer = post(live, origin=f"http://{origin_host}:{live.port}")

    assert answer.status == 200


def test_a_missing_origin_needs_the_same_origin_fetch_metadata(live):
    accepted = post(live, origin=False, sec_fetch_site="same-origin")
    assert accepted.status == 200

    refused = post(live, origin=False)
    assert refused.status == 403
    assert_error_document(refused, "forbidden")

    cross_site = post(live, origin=False, sec_fetch_site="cross-site")
    assert cross_site.status == 403


@pytest.mark.parametrize("token", (False, "wrong", "", "x" * 43))
def test_the_token_must_match(live, token):
    answer = post(live, token=token)

    assert answer.status == 403
    assert_error_document(answer, "forbidden")


def test_the_token_is_not_in_any_other_response(live):
    assert live.token not in get(live, "/viewer.js").text()
    assert live.token not in post(live, token="wrong").text()


# --- the body contract ------------------------------------------------------


def test_transfer_encoding_is_refused(live):
    answer = post(live, extra=(("Transfer-Encoding", "chunked"),))

    assert answer.status == 400
    assert_error_document(answer, "bad_request")


def test_a_missing_content_length_requires_one(live):
    answer = post(live, content_length=False)

    assert answer.status == 411
    assert_error_document(answer, "length_required")


def test_a_duplicate_content_length_is_refused(live):
    body = json.dumps(dict(BIRTH, place_text="", place_id="")).encode("utf-8")
    answer = post(
        live,
        payload=body,
        content_length=str(len(body)),
        extra=(("Content-Length", str(len(body))),),
    )

    assert answer.status == 400
    assert_error_document(answer, "bad_request")


#: ``" 5"`` is deliberately absent: leading whitespace after the colon is not
#: part of a header value, so the standard parser hands us ``"5"`` and the
#: request is simply a five-byte body. The trailing space of ``"5 "`` *is* part
#: of the value and is refused.
@pytest.mark.parametrize("value", ("-5", "+5", "0", "5 ", "abc", "1e3", "123456"))
def test_a_malformed_content_length_is_refused(live, value):
    answer = post(live, content_length=value)

    assert answer.status == 400
    assert_error_document(answer, "bad_request")


def test_a_body_larger_than_the_cap_is_refused_before_it_is_read(live):
    # The announced length exceeds the cap and only three bytes are sent; a
    # 413 proves the body was never read, because reading would have blocked
    # until the handler timeout.
    started = time.monotonic()
    answer = post(live, payload=b"abc", content_length="4097")
    elapsed = time.monotonic() - started

    assert answer.status == 413
    assert_error_document(answer, "payload_too_large")
    assert elapsed < 2.0


@pytest.mark.parametrize(
    "content_type",
    (
        None,
        "text/plain",
        "application/json; charset=latin-1",
        "application/json; charset=utf-8; boundary=x",
        "application/xml",
        "application/json+ld",
    ),
)
def test_a_wrong_content_type_is_refused(live, content_type):
    answer = post(live, content_type=content_type)

    assert answer.status == 415
    assert_error_document(answer, "unsupported_media_type")


@pytest.mark.parametrize(
    "content_type",
    (
        "application/json",
        "application/json; charset=utf-8",
        "application/JSON; CHARSET=UTF-8",
        "application/json;charset=UTF-8",
    ),
)
def test_the_accepted_content_types(live, content_type):
    answer = post(live, content_type=content_type)

    assert answer.status == 200


# --- results ----------------------------------------------------------------


def test_the_selected_record_is_calculated_from(live):
    answer = selected(live, JALANDHAR_ID, JALANDHAR_LABEL)

    assert answer.status == 200
    assert_contract_headers(answer)
    document = answer.json()
    assert document["request"]["submitted"] == dict(
        BIRTH, place_text=JALANDHAR_LABEL, place_id=str(JALANDHAR_ID)
    )
    assert document["location"]["canonical_name"] == JALANDHAR_LABEL
    assert document["effective"]["source"] == "selected"
    assert document["effective"]["place"]["geoname_id"] == JALANDHAR_ID
    assert document["effective"]["place_assumed"] is False
    # A matching name belongs to a suggestion list, not to a calculation.
    assert document["effective"]["place"]["matched_name"] is None
    assert document["assumptions"]["any"] is False
    assert "resolution" not in document
    assert len(document["rows"]) == 819


def test_another_selected_record_is_calculated_from(live):
    document = selected(live, LONDON_ID, LONDON_LABEL).json()

    assert document["location"]["canonical_name"] == LONDON_LABEL
    assert document["location"]["timezone_id"] == "Europe/London"
    assert document["effective"]["place"]["geoname_id"] == LONDON_ID
    assert document["effective"]["source"] == "selected"


def test_a_name_that_would_once_have_been_ambiguous_is_now_a_selection(live):
    """Nothing is chosen automatically any more: the page names the record."""
    document = selected(live, HYDERABAD_ID, HYDERABAD_LABEL).json()

    assert document["location"]["canonical_name"] == HYDERABAD_LABEL
    assert document["effective"]["place"]["country_name"] == "India"


# --- the four place_text/place_id combinations (5.3) ------------------------


def test_both_blank_uses_the_default_record_and_says_so(live):
    answer = post(live)

    assert answer.status == 200
    document = answer.json()
    assert document["effective"]["source"] == "default"
    assert document["effective"]["place_assumed"] is True
    assert document["effective"]["place"]["geoname_id"] == JALANDHAR_ID
    assert document["effective"]["place"]["matched_name"] is None
    assert document["request"]["normalized"]["place_id"] == str(JALANDHAR_ID)
    assert document["request"]["normalized"]["place_label"] == JALANDHAR_LABEL
    assert document["assumptions"]["place"] is True
    assert f"Birthplace {JALANDHAR_LABEL} assumed" in " ".join(
        document["assumptions"]["labels"]
    )


def test_text_without_an_identifier_requires_a_selection(live):
    answer = post(live, place_text="Jalandhar")

    assert answer.status == 400
    assert_contract_headers(answer)
    assert_error_document(answer, "place_selection_required")
    assert "select a suggestion" in answer.json()["error"]["message"].lower()


def test_an_identifier_without_its_label_is_inconsistent(live):
    answer = post(live, place_id=str(JALANDHAR_ID))

    assert answer.status == 400
    assert_error_document(answer, "input")
    assert "inconsistent" in answer.json()["error"]["message"]


def test_a_label_that_does_not_match_the_record_is_refused(live):
    """The viewer never substitutes another record for the one named."""
    answer = post(live, place_text="Jalandhar", place_id=str(JALANDHAR_ID))

    assert answer.status == 400
    assert_error_document(answer, "input")
    message = answer.json()["error"]["message"]
    assert "does not match" in message
    assert JALANDHAR_LABEL in message

    swapped = post(live, place_text=LONDON_LABEL, place_id=str(JALANDHAR_ID))
    assert swapped.status == 400
    assert_error_document(swapped, "input")


@pytest.mark.parametrize("text", ("", "   ", "\t"))
def test_whitespace_only_birthplace_text_counts_as_blank(live, text):
    answer = post(live, place_text=text)

    assert answer.status == 200
    assert answer.json()["effective"]["source"] == "default"


def test_an_unknown_identifier_is_not_found(live):
    answer = post(live, place_text="Nowhere", place_id="999999999")

    assert answer.status == 404
    assert_error_document(answer, "place_not_found")


@pytest.mark.parametrize(
    "place_id", ("abc", "-1", "１２", "0", "12.5", "1268782 ", "1" * 13)
)
def test_a_malformed_identifier_is_an_input_error(live, place_id):
    answer = post(live, place_text=JALANDHAR_LABEL, place_id=place_id)

    assert answer.status == 400
    assert_error_document(answer, "input")


# --- the assumed time, and the invalid one that is never assumed ------------


def test_a_blank_time_becomes_the_assumed_noon(live):
    answer = post(live, payload=dict(BIRTH, time="", place_text="", place_id=""))

    assert answer.status == 200
    document = answer.json()
    assert document["request"]["submitted"]["time"] == ""
    assert document["request"]["normalized"]["time"] == "12:00:00"
    assert document["effective"]["time_assumed"] is True
    assert document["assumptions"]["time"] is True
    assert document["birth"]["local_seconds"].startswith("1995-03-21 12:00:00")


@pytest.mark.parametrize("value", ("25:00", "24:00", "07:60"))
def test_an_invalid_time_from_a_direct_api_request_is_never_a_result(
    live, value
):
    """Section 13: a direct request, not the browser's own sanitising."""
    answer = post(
        live, payload=dict(BIRTH, time=value, place_text="", place_id="")
    )

    assert answer.status == 400
    assert_error_document(answer, "input")
    assert "rows" not in answer.json()
    assert "12:00" not in answer.json()["error"]["message"]


# --- stale /1 requests, and the malformed bodies that precede them ----------


@pytest.mark.parametrize(
    "payload",
    (
        {
            "date": "1995-03-21",
            "time": "06:45",
            "place_query": "Jalandhar",
            "year_convention": "365.256363",
        },
        {
            "date": "1995-03-21",
            "time": "06:45",
            "place_text": "",
            "place_id": "",
            "year_convention": "365.256363",
        },
    ),
)
def test_a_stale_schema_one_request_says_so(live, payload):
    answer = post(live, payload=payload)

    assert answer.status == 400
    assert_contract_headers(answer)
    assert_error_document(answer, "stale_schema")
    assert "out of date" in answer.json()["error"]["message"]


@pytest.mark.parametrize(
    "body",
    (
        b'{"place_query":"J\xff","year_convention":"365.25"}',
        b'{"place_query":"J","place_query":"J","year_convention":"365.25"}',
        b'\xef\xbb\xbf{"place_query":"J","year_convention":"365.25"}',
    ),
)
def test_an_undecodable_or_duplicate_keyed_body_is_input_not_stale(live, body):
    """Section 7.2: decoding happens before any key is inspected."""
    answer = post(live, payload=body)

    assert answer.status == 400
    assert_error_document(answer, "input")


@pytest.mark.parametrize(
    "payload",
    (
        dict(BIRTH, date="1995-02-30", place_text="", place_id=""),
        dict(BIRTH, date="1995-3-21", place_text="", place_id=""),
        dict(BIRTH, place_text="", place_id="", extra="x"),
        {"date": "1995-03-21", "time": "06:45", "place_text": ""},
        {"date": "1995-03-21", "time": "06:45", "place_text": "", "place_id": 5},
    ),
)
def test_a_bad_request_document_is_one_input_error(live, payload):
    answer = post(live, payload=payload)

    assert answer.status == 400
    assert_error_document(answer, "input")


def test_an_unparseable_body_is_an_input_error(live):
    answer = post(live, payload=b"\xff\xfe not json")

    assert answer.status == 400
    assert_error_document(answer, "input")


def test_a_dasha_range_failure_is_reported_as_such(live, monkeypatch):
    def refuse(*args, **kwargs):
        raise DashaRangeError("the cycle would leave the datetime range.")

    monkeypatch.setattr(server_module, "render_chart_and_dasha_at", refuse)
    answer = post(live)

    assert answer.status == 400
    assert_error_document(answer, "dasha_range")


def test_an_unexpected_failure_is_reported_with_its_type(live, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("jd 9999999 outside the ephemeris coverage")

    monkeypatch.setattr(server_module, "render_chart_and_dasha_at", explode)
    answer = post(live)

    assert answer.status == 500
    assert_contract_headers(answer)
    document = answer.json()
    assert document["error"]["kind"] == "unexpected"
    assert document["error"]["message"].startswith("RuntimeError: ")
    assert "outside the ephemeris coverage" in document["error"]["message"]


def test_a_resource_failure_is_reported_as_a_resource_error(live, monkeypatch):
    def refuse(*args, **kwargs):
        raise ConfigurationError("the geodata database vanished.")

    monkeypatch.setattr(server_module, "render_chart_and_dasha_at", refuse)
    answer = post(live)

    assert answer.status == 500
    assert_error_document(answer, "resource")


# --- responsiveness (11.1) --------------------------------------------------


@pytest.fixture
def impatient(monkeypatch):
    """A server whose per-operation read timeout is one second."""
    monkeypatch.setattr(server_module._ViewerHandler, "timeout", 1)
    running = start()
    try:
        post(running)
        yield running
    finally:
        running.stop()


def test_an_idle_connection_delays_nothing_and_is_closed(impatient):
    idle = socket.create_connection(("127.0.0.1", impatient.port), timeout=10)
    try:
        started = time.monotonic()
        answer = post(impatient)
        elapsed = time.monotonic() - started

        assert answer.status == 200
        assert elapsed < 0.5

        # The server closes the idle connection when its timeout expires.
        idle.settimeout(5)
        assert idle.recv(4096) == b""
    finally:
        idle.close()

    assert post(impatient).status == 200


def test_a_connection_with_partial_headers_is_closed(impatient):
    partial = socket.create_connection(
        ("127.0.0.1", impatient.port), timeout=10
    )
    try:
        partial.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n" % impatient.port)
        partial.settimeout(5)
        assert partial.recv(4096) == b""
    finally:
        partial.close()

    assert post(impatient).status == 200


def test_a_body_that_never_arrives_is_answered_with_a_timeout(impatient):
    sock = socket.create_connection(("127.0.0.1", impatient.port), timeout=10)
    try:
        headers = [
            ("Origin", f"http://127.0.0.1:{impatient.port}"),
            ("X-Viewer-Token", impatient.token),
            ("Content-Type", JSON_TYPE),
            ("Content-Length", "100"),
        ]
        sock.sendall(
            build(
                "POST",
                "/api/chart",
                port=impatient.port,
                headers=headers,
                body=b"abc",
            )
        )
        sock.settimeout(10)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        answer = Answer(b"".join(chunks))
    finally:
        sock.close()

    assert answer.status == 408
    assert_error_document(answer, "request_timeout")
    assert_contract_headers(answer)
    assert post(impatient).status == 200


def test_a_body_that_arrives_in_two_parts_within_the_timeout_succeeds(impatient):
    payload = json.dumps(dict(BIRTH, place_text="", place_id="")).encode("utf-8")
    head, tail = payload[:20], payload[20:]
    sock = socket.create_connection(("127.0.0.1", impatient.port), timeout=20)
    try:
        headers = [
            ("Origin", f"http://127.0.0.1:{impatient.port}"),
            ("X-Viewer-Token", impatient.token),
            ("Content-Type", JSON_TYPE),
            ("Content-Length", str(len(payload))),
        ]
        sock.sendall(
            build(
                "POST",
                "/api/chart",
                port=impatient.port,
                headers=headers,
                body=head,
            )
        )
        time.sleep(0.5)
        sock.sendall(tail)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        answer = Answer(b"".join(chunks))
    finally:
        sock.close()

    assert answer.status == 200
    assert len(answer.json()["rows"]) == 819


def test_a_client_that_vanishes_costs_one_line_and_no_traceback(live, capsys):
    capsys.readouterr()
    payload = json.dumps(dict(BIRTH, place_text="", place_id="")).encode("utf-8")
    sock = socket.create_connection(("127.0.0.1", live.port), timeout=10)
    headers = [
        ("Origin", f"http://127.0.0.1:{live.port}"),
        ("X-Viewer-Token", live.token),
        ("Content-Type", JSON_TYPE),
        ("Content-Length", str(len(payload))),
    ]
    sock.sendall(
        build("POST", "/api/chart", port=live.port, headers=headers, body=payload)
    )
    sock.close()
    time.sleep(1.0)

    captured = capsys.readouterr().err
    assert "Traceback" not in captured
    assert captured.count("connection closed by client") <= 1
    assert post(live).status == 200


def test_three_concurrent_calculations_never_overlap(live, monkeypatch):
    """2.1: mutual exclusion only. Nothing here asserts a completion order."""
    original = server_module.render_chart_and_dasha_at
    spans = []
    guard = threading.Lock()

    def recorded(*args, **kwargs):
        entered = time.monotonic()
        try:
            return original(*args, **kwargs)
        finally:
            left = time.monotonic()
            with guard:
                spans.append((entered, left))

    monkeypatch.setattr(server_module, "render_chart_and_dasha_at", recorded)

    answers = {}

    def run(index, record):
        answers[index] = (
            post(live) if record is None else selected(live, *record)
        )

    threads = [
        threading.Thread(target=run, args=(index, record))
        for index, record in enumerate(
            (
                None,
                (LONDON_ID, LONDON_LABEL),
                (HYDERABAD_ID, HYDERABAD_LABEL),
            )
        )
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(answers) == [0, 1, 2]
    for answer in answers.values():
        assert answer.status == 200
    assert len(spans) == 3

    ordered = sorted(spans)
    for earlier, later in zip(ordered, ordered[1:]):
        assert earlier[1] <= later[0], f"overlapping calculations: {ordered}"


# --- lifecycle ---------------------------------------------------------------


# --- POST /api/places (Layer 15 section 5.2) --------------------------------


def test_the_suggestions_endpoint_lists_the_prefix(live):
    answer = places(live, "jal")

    assert answer.status == 200
    assert_contract_headers(answer)
    document = answer.json()
    assert document["schema"] == "vedic_chart.viewer/2"
    assert document["q"] == "jal"
    assert 0 < len(document["suggestions"]) <= 10
    first = document["suggestions"][0]
    assert first == {
        "geoname_id": JALANDHAR_ID,
        "label": JALANDHAR_LABEL,
        # A primary-name match: what the option reads as and what a selection
        # sends back are the same string (Layer 15 section 5.1).
        "display_label": JALANDHAR_LABEL,
        "name": "Jalandhar",
        "admin1_name": "Punjab",
        "country_name": "India",
        "population": 868929,
        "matched_name": "Jalandhar",
    }


def test_every_suggestion_carries_both_labels(live):
    """The page shows ``display_label`` and sends ``label`` back, always."""
    for query in ("jal", "lond", "spring", "hyderabad"):
        for suggestion in places(live, query).json()["suggestions"]:
            assert isinstance(suggestion["display_label"], str)
            assert suggestion["display_label"].startswith(suggestion["label"])
            if suggestion["matched_name"] == suggestion["name"]:
                assert suggestion["display_label"] == suggestion["label"]


def test_an_alias_match_is_displayed_with_the_name_that_matched(live):
    """Layer 2 owns the comparison; the page never collates the two names."""
    suggestion = next(
        one
        for one in places(live, "london").json()["suggestions"]
        if one["geoname_id"] == 10304286
    )

    assert suggestion["name"] == "Ban Sarkāri"
    assert suggestion["matched_name"] == "London"
    assert suggestion["label"] == "Ban Sarkāri, Punjab, India"
    assert suggestion["display_label"] == (
        "Ban Sarkāri, Punjab, India (matched: London)"
    )

    # And it is the plain label, not the displayed one, that is accepted.
    assert post(
        live,
        place_text=suggestion["label"],
        place_id=str(suggestion["geoname_id"]),
    ).status == 200
    assert post(
        live,
        place_text=suggestion["display_label"],
        place_id=str(suggestion["geoname_id"]),
    ).status == 400


def test_the_suggestions_endpoint_lists_at_most_ten(live):
    document = places(live, "ja").json()

    assert len(document["suggestions"]) == 10
    ids = [one["geoname_id"] for one in document["suggestions"]]
    assert len(set(ids)) == 10


def test_the_suggestions_endpoint_echoes_the_query_verbatim(live):
    document = places(live, "  JĀL  ").json()

    assert document["q"] == "  JĀL  "
    assert document["suggestions"][0]["geoname_id"] == JALANDHAR_ID


@pytest.mark.parametrize("query", ("j", "", " ", "xyzzyville"))
def test_a_short_or_unmatched_prefix_lists_nothing(live, query):
    answer = places(live, query)

    assert answer.status == 200
    assert answer.json()["suggestions"] == []


def test_a_comma_qualifier_reaches_the_endpoint(live):
    document = places(live, "hyderabad, india").json()

    assert [one["country_name"] for one in document["suggestions"]] == ["India"]


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"q": "jal", "limit": 5},
        {"q": 5},
        {"query": "jal"},
    ),
)
def test_a_malformed_suggestions_body_is_an_input_error(live, payload):
    answer = post(live, path="/api/places", payload=payload)

    assert answer.status == 400
    assert_error_document(answer, "input")


def test_a_suggestions_body_over_the_cap_is_refused_before_it_is_read(live):
    started = time.monotonic()
    answer = post(
        live, path="/api/places", payload=b"abc", content_length="257"
    )
    elapsed = time.monotonic() - started

    assert answer.status == 413
    assert_error_document(answer, "payload_too_large")
    assert "256" in answer.json()["error"]["message"]
    assert elapsed < 2.0


def test_a_suggestions_body_at_the_cap_is_accepted(live):
    """256 bytes exactly: the cap is a maximum, not a strict bound."""
    filler = "j" * (256 - len(json.dumps({"q": ""}).encode("utf-8")))
    body = json.dumps({"q": filler}).encode("utf-8")
    assert len(body) == 256

    answer = post(live, path="/api/places", payload=body)

    assert answer.status == 200
    assert answer.json()["suggestions"] == []


def test_the_suggestions_endpoint_obeys_every_http_check(live):
    """11.3, item for item, on the second endpoint (section 5.2)."""
    assert places(live, "jal", host="evil.test").status == 400
    assert places(live, "jal", origin="http://evil.test").status == 403
    assert places(live, "jal", origin=False).status == 403
    assert places(
        live, "jal", origin=False, sec_fetch_site="same-origin"
    ).status == 200
    assert places(live, "jal", token=False).status == 403
    assert places(live, "jal", token="wrong").status == 403
    assert places(live, "jal", content_length=False).status == 411
    assert places(live, "jal", content_length="0").status == 400
    assert places(live, "jal", content_type="text/plain").status == 415
    assert places(
        live, "jal", extra=(("Transfer-Encoding", "chunked"),)
    ).status == 400
    assert post(live, path="/api/places?q=jal", payload={"q": "jal"}).status == (
        404
    )


def test_a_duplicate_content_length_is_refused_on_the_places_route(live):
    body = json.dumps({"q": "jal"}).encode("utf-8")
    answer = post(
        live,
        path="/api/places",
        payload=body,
        content_length=str(len(body)),
        extra=(("Content-Length", str(len(body))),),
    )

    assert answer.status == 400
    assert_error_document(answer, "bad_request")


def test_the_engine_lock_is_not_held_around_a_suggestion(live):
    """Section 5.2: a keystroke never queues behind a calculation."""
    server_module.ENGINE_LOCK.acquire()
    try:
        started = time.monotonic()
        answer = places(live, "jal")
        elapsed = time.monotonic() - started
    finally:
        server_module.ENGINE_LOCK.release()

    assert answer.status == 200
    assert answer.json()["suggestions"]
    assert elapsed < 2.0


def test_a_suggestion_label_is_what_a_selection_must_send_back(live):
    """The two endpoints agree on one label, which is the whole contract."""
    suggestion = places(live, "lond").json()["suggestions"][0]

    accepted = post(
        live,
        place_text=suggestion["label"],
        place_id=str(suggestion["geoname_id"]),
    )

    assert accepted.status == 200
    assert accepted.json()["effective"]["place"]["label"] == (
        suggestion["label"]
    )


# --- the default birthplace record (Layer 15 section 4.2) -------------------


def test_the_effective_default_is_read_once_at_start_up():
    server = ViewerServer.create(make_config())
    try:
        assert server.default_place_id == JALANDHAR_ID
        assert server.default_label == JALANDHAR_LABEL
        assert server.default_place.geoname_id == JALANDHAR_ID
        assert server.default_location.timezone_id == "Asia/Kolkata"
        assert server.default_place_override is True
    finally:
        server.server_close()


def test_the_default_record_is_not_read_again_per_request(live, monkeypatch):
    """Section 4.2: no per-request database read for the default."""
    opened = []
    original = server_module.OfflineLocationResolver.__init__

    def recorder(self, db_path, ranking_config=None):
        opened.append(str(db_path))
        original(self, db_path, ranking_config)

    monkeypatch.setattr(
        server_module.OfflineLocationResolver, "__init__", recorder
    )

    assert post(live).status == 200

    assert opened == []


def test_the_built_in_default_is_refused_against_a_database_without_it():
    """The fixture has no Jammu, and there is no fallback to another record."""
    with pytest.raises(ConfigurationError) as caught:
        ViewerServer.create(make_config(default_place_id=None))

    message = str(caught.value)
    assert str(BUILT_IN_DEFAULT_ID) in message
    assert "default birthplace record" in message
    assert str(FIXTURE_DB.name) in message
    assert server_module.DEFAULT_PLACE_ID == BUILT_IN_DEFAULT_ID


def test_serve_exits_four_before_binding_when_the_default_is_unavailable(
    monkeypatch, capsys
):
    bound = []
    original = ViewerServer.__init__

    def recorder(self, *args, **kwargs):  # pragma: no cover - must not run
        bound.append(args)
        original(self, *args, **kwargs)

    monkeypatch.setattr(ViewerServer, "__init__", recorder)

    code = serve(make_config(default_place_id=None))

    assert code == 4
    assert bound == []
    captured = capsys.readouterr().err
    assert "error: the default birthplace record 1269321" in captured
    assert "cannot bind" not in captured


def test_serve_exits_four_for_an_override_that_is_not_in_the_database(capsys):
    code = serve(make_config(default_place_id=1))

    assert code == 4
    assert "the default birthplace record 1 is not available" in (
        capsys.readouterr().err
    )


def test_the_command_line_override_reaches_the_same_exit_code(capsys):
    code = server_module.main(
        [
            "--geodata",
            str(FIXTURE_DB),
            "--ephemeris",
            EPHE_DIR,
            "--default-place-id",
            "1",
        ]
    )

    assert code == 4
    assert "the default birthplace record 1 is not available" in (
        capsys.readouterr().err
    )


def test_the_banner_states_the_default_record_and_the_override(
    capsys, monkeypatch
):
    monkeypatch.setattr(ViewerServer, "serve_forever", lambda self: None)

    serve(make_config())
    banner = capsys.readouterr().out

    assert (
        f"default place: {JALANDHAR_ID} = {JALANDHAR_LABEL} "
        "(Asia/Kolkata) (override)" in banner
    )


def test_the_banner_omits_the_override_note_without_the_flag(
    capsys, monkeypatch, tmp_path
):
    """Proven on a server whose built-in default *is* available."""
    monkeypatch.setattr(ViewerServer, "serve_forever", lambda self: None)
    monkeypatch.setattr(server_module, "DEFAULT_PLACE_ID", JALANDHAR_ID)

    serve(make_config(default_place_id=None))
    banner = capsys.readouterr().out

    assert f"default place: {JALANDHAR_ID} = {JALANDHAR_LABEL} (Asia/Kolkata)" in (
        banner
    )
    assert "(override)" not in banner


@pytest.mark.parametrize("value", ("abc", "-1", "1.5", "", "１２", "1" * 13))
def test_a_malformed_default_place_id_is_an_argparse_error(capsys, value):
    assert (
        server_module.main(
            [
                "--geodata",
                str(FIXTURE_DB),
                "--ephemeris",
                EPHE_DIR,
                "--default-place-id",
                value,
            ]
        )
        == 2
    )
    capsys.readouterr()


def test_the_index_carries_the_default_place_when_the_page_asks_for_it():
    """Section 4.2, both ways round: the substitution is tolerant.

    The committed page does not yet carry the meta tag, so the served
    document must be the package file with only the token substituted; a page
    that does carry the two placeholders must get the effective record.
    """
    server = ViewerServer.create(make_config())
    try:
        page = (
            b'<meta name="viewer-token" content="__VIEWER_TOKEN__">'
            b'<meta name="viewer-default-place" content="'
            b'__VIEWER_DEFAULT_PLACE_ID__|__VIEWER_DEFAULT_PLACE_LABEL__">'
        )
        substituted = server_module._substituted_index(
            page, server.token, server.default_place_id, server.default_label
        ).decode("utf-8")

        assert f'content="{JALANDHAR_ID}|{JALANDHAR_LABEL}"' in substituted
        assert f'content="{server.token}"' in substituted
        assert "__VIEWER_" not in substituted
    finally:
        server.server_close()


def test_a_default_place_label_is_escaped_for_the_meta_attribute():
    """A label is database content; it is escaped, not trusted."""
    page = b'<meta name="x" content="__VIEWER_DEFAULT_PLACE_LABEL__">'

    substituted = server_module._substituted_index(
        page, "token", 7, 'A "quoted" & <angled> place'
    ).decode("utf-8")

    assert substituted == (
        '<meta name="x" content="A &quot;quoted&quot; &amp; '
        '&lt;angled&gt; place">'
    )


def test_create_then_shutdown_then_close_releases_the_port():
    server = ViewerServer.create(make_config())
    port = server.port
    assert server.url == f"http://127.0.0.1:{port}/"
    assert server.metadata_rows
    assert server.config.geodata_path == str(FIXTURE_DB)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.shutdown()
    thread.join(timeout=10)
    assert not thread.is_alive()
    server.server_close()

    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=2).close()


def test_create_prints_nothing(capsys):
    server = ViewerServer.create(make_config())
    try:
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
    finally:
        server.server_close()


def test_create_on_an_occupied_port_raises_oserror():
    first = ViewerServer.create(make_config())
    try:
        with pytest.raises(OSError):
            ViewerServer.create(make_config(port=first.port))
    finally:
        first.server_close()


def test_create_refuses_a_non_config():
    with pytest.raises(TypeError):
        ViewerServer.create("not a config")


def test_serve_maps_a_configuration_failure_to_four(tmp_path, capsys):
    missing = tmp_path / "nowhere.sqlite"

    code = serve(make_config(geodata_path=str(missing)))

    assert code == 4
    assert "error: " in capsys.readouterr().err


def test_serve_maps_a_metadata_failure_to_four(monkeypatch, capsys):
    class Broken:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("database disk image is malformed")

    monkeypatch.setattr(server_module, "OfflineLocationResolver", Broken)

    code = serve(make_config())

    assert code == 4
    assert "geodata metadata could not be read" in capsys.readouterr().err


def test_serve_maps_a_bind_failure_to_five(capsys):
    occupied = ViewerServer.create(make_config())
    try:
        code = serve(make_config(port=occupied.port))
    finally:
        occupied.server_close()

    assert code == 5
    assert "cannot bind 127.0.0.1:" in capsys.readouterr().err


def test_serve_maps_a_keyboard_interrupt_to_one_hundred_and_thirty(
    monkeypatch, capsys
):
    captured_servers = []

    def interrupt(self):
        captured_servers.append(self)
        raise KeyboardInterrupt

    monkeypatch.setattr(ViewerServer, "serve_forever", interrupt)

    code = serve(make_config())

    assert code == 130
    assert len(captured_servers) == 1
    port = captured_servers[0].port
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=2).close()

    banner = capsys.readouterr().out
    assert banner.startswith("viewer: http://127.0.0.1:")
    assert "press Ctrl-C to stop" in banner


def test_the_banner_states_the_resources_and_never_the_token(capsys, monkeypatch):
    monkeypatch.setattr(ViewerServer, "serve_forever", lambda self: None)

    code = serve(make_config())
    banner = capsys.readouterr().out

    assert code == 0
    assert "geodata: " in banner
    assert banner.count("geodata metadata: ") == 7
    assert "ephemeris: " in banner
    assert banner.count("ephemeris file: ") == 3
    assert (
        "dasha year convention: 365.256363 days (Mean Sidereal year, fixed "
        "by the viewer)" in banner
    )
    for line in banner.splitlines():
        assert len(line) < 400


def test_the_verbose_banner_warns_that_diagnostics_carry_request_data(
    capsys, monkeypatch
):
    monkeypatch.setattr(ViewerServer, "serve_forever", lambda self: None)

    serve(make_config(verbose=True))

    assert "may contain request data" in capsys.readouterr().out


def test_main_reports_argparse_usage_errors_as_two(capsys):
    assert server_module.main([]) == 2
    assert server_module.main(["--geodata", "x"]) == 2
    assert (
        server_module.main(
            [
                "--geodata",
                str(FIXTURE_DB),
                "--ephemeris",
                EPHE_DIR,
                "--port",
                "70000",
            ]
        )
        == 2
    )
    assert (
        server_module.main(
            [
                "--geodata",
                str(FIXTURE_DB),
                "--ephemeris",
                EPHE_DIR,
                "--port",
                "eight",
            ]
        )
        == 2
    )
    capsys.readouterr()


def test_main_builds_the_config_and_hands_it_to_serve(monkeypatch):
    seen = []

    monkeypatch.setattr(
        server_module, "serve", lambda config: seen.append(config) or 7
    )

    code = server_module.main(
        [
            "--geodata",
            str(FIXTURE_DB),
            "--ephemeris",
            EPHE_DIR,
            "--port",
            "0",
            "--verbose",
        ]
    )

    assert code == 7
    assert seen == [
        ViewerConfig(
            geodata_path=str(FIXTURE_DB),
            ephemeris_path=EPHE_DIR,
            port=0,
            open_browser=False,
            verbose=True,
            default_place_id=None,
        )
    ]

    seen.clear()
    server_module.main(
        [
            "--geodata",
            str(FIXTURE_DB),
            "--ephemeris",
            EPHE_DIR,
            "--default-place-id",
            str(JALANDHAR_ID),
        ]
    )

    assert seen == [
        ViewerConfig(
            geodata_path=str(FIXTURE_DB),
            ephemeris_path=EPHE_DIR,
            port=0,
            open_browser=False,
            verbose=False,
            default_place_id=JALANDHAR_ID,
        )
    ]


def test_a_failing_browser_open_is_only_a_warning(monkeypatch, capsys):
    monkeypatch.setattr(ViewerServer, "serve_forever", lambda self: None)
    monkeypatch.setattr(
        server_module.webbrowser, "open", lambda url: (_ for _ in ()).throw(
            OSError("no browser")
        )
    )

    code = serve(make_config(open_browser=True))
    captured = capsys.readouterr()

    assert code == 0
    assert "warning: could not open a browser" in captured.err
    assert "viewer: http://127.0.0.1:" in captured.out


def test_a_browser_open_that_returns_false_is_only_a_warning(
    monkeypatch, capsys
):
    monkeypatch.setattr(ViewerServer, "serve_forever", lambda self: None)
    monkeypatch.setattr(server_module.webbrowser, "open", lambda url: False)

    assert serve(make_config(open_browser=True)) == 0
    assert "warning: could not open a browser" in capsys.readouterr().err


# --- hygiene -----------------------------------------------------------------


def test_normal_logs_are_label_and_status_only(capsys):
    running = start()
    try:
        capsys.readouterr()
        get(running, "/")
        get(running, "/viewer.css")
        get(running, "/viewer.js")
        get(running, "/secret/path?place=Jalandhar&date=1995-03-21")
        post(running)
        post(running, place_text="Hyderabad")
        post(running, token="wrong")
        places(running, "jal")
        time.sleep(0.2)
        captured = capsys.readouterr()
    finally:
        running.stop()

    assert captured.out == ""
    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert lines
    for line in lines:
        assert re.fullmatch(
            r"(index|css|js|api_chart|api_places|other) [0-9]{3}", line
        ), line
    for secret in ("Jalandhar", "Hyderabad", "1995-03-21", "06:45", "?", "/secret"):
        assert secret not in captured.err
    assert sorted(set(lines)) == sorted(
        {
            "index 200",
            "css 200",
            "js 200",
            "other 404",
            "api_chart 200",
            "api_chart 400",
            "api_chart 403",
            "api_places 200",
        }
    )
    assert set(server_module.ROUTE_LABELS) == {
        "index",
        "css",
        "js",
        "api_chart",
        "api_places",
        "other",
    }


def test_a_session_writes_no_file_into_the_working_tree():
    before = _tree_snapshot()
    running = start()
    try:
        get(running, "/")
        post(running)
        post(running, place_text="Nowhere", place_id="999999999")
        places(running, "jal")
    finally:
        running.stop()

    assert _tree_snapshot() == before


def _tree_snapshot():
    return {
        path
        for path in REPO_ROOT.rglob("*")
        if "__pycache__" not in path.parts and path.is_file()
    }


def test_no_response_carries_a_server_or_date_header(live):
    answers = [
        get(live, "/"),
        get(live, "/nope"),
        get(live, "/", host="evil.test"),
        get(live, "/api/chart"),
        post(live, token="wrong"),
        post(live),
        Answer(
            exchange(
                live,
                build("OPTIONS", "/api/chart", port=live.port),
            )
        ),
    ]

    for answer in answers:
        assert "server" not in answer.headers, answer.status
        assert "date" not in answer.headers, answer.status
        assert answer.raw.startswith(b"HTTP/1.0 ")
