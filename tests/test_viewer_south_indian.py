"""Layer 19, viewer half: the additive ``south_indian_svg`` response field.

Specification ``docs/LAYER19_SOUTH_INDIAN_VIEWER_SPEC.md`` sections 5 and 9.2,
in the style of ``tests/test_viewer_planetary_positions.py``: the existing
transport fixture and its golden stay untouched, and these tests check the new
field independently, through the live server harness of
``tests/test_viewer_server.py``.

* The document carries ``south_indian_svg`` equal to a fresh
  ``render_south_indian_svg(result.d1, SOUTH_INDIAN_RENDERER_OPTIONS)`` of the
  one result the pipeline produced; ``svg`` is still the North Indian document;
  every other field is what ``serialize`` gives without the keyword.
* One pipeline call per request; the South Indian render sits after the
  engine lock and inside the ``try`` whose generic arm is the 500.
* A failing South Indian renderer is the existing ``500 unexpected`` document,
  never a partial success.
* Both SVGs pass the page's ``insertSvg`` acceptance, re-implemented below, and
  their ids are unique on one page.
"""

import ast
import json
import xml.etree.ElementTree as ET

import pytest

from render_helpers import REPO_ROOT
from test_viewer_server import (
    JALANDHAR_ID,
    JALANDHAR_LABEL,
    assert_contract_headers,
    assert_error_document,
    get,
    post,
    selected,
    start,
)
from vedic_chart.dasha import dasha_rows
from vedic_chart.render import (
    overlay_block,
    render_north_indian_svg,
    render_south_indian_svg,
)
from vedic_chart.viewer import server as server_module
from vedic_chart.viewer import transport

SERVER_SOURCE = REPO_ROOT / "src" / "vedic_chart" / "viewer" / "server.py"
PIPELINE_SOURCE = REPO_ROOT / "src" / "vedic_chart" / "app" / "pipeline.py"
GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "viewer" / "jalandhar_365256363.json"

SVG_NAMESPACE = "http://www.w3.org/2000/svg"

#: Specification 5.5: unchanged, spelled out rather than read from the module.
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; form-action 'none'; "
    "base-uri 'none'; frame-ancestors 'none'"
)

#: Section 2: the pre-Layer-19 response keys, in order, then the Layer 19 one
#: and the Layer 20 ``overlay`` block (Layer 20 section 6.2), last.
EXTENDED_KEYS = [
    "schema",
    "request",
    "engine",
    "location",
    "effective",
    "assumptions",
    "birth",
    "svg",
    "timeline",
    "birth_chain",
    "rows",
    "planetary_positions",
    "south_indian_svg",
    "overlay",
    "panchanga",
]

REQUEST_CASES = {
    "selected": ("06:45", JALANDHAR_LABEL, str(JALANDHAR_ID)),
    "time_assumed": ("", JALANDHAR_LABEL, str(JALANDHAR_ID)),
    "place_assumed": ("06:45", "", ""),
    "both_assumed": ("", "", ""),
}


# --- the page's insertSvg acceptance, re-implemented ------------------------


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def _namespace(name: str):
    return name[1:].split("}", 1)[0] if name.startswith("{") else None


def page_accepts_svg(text) -> bool:
    """``viewer.js`` ``insertSvg``'s acceptance rule, in Python.

    A non-empty string that parses as XML (DOMParser with image/svg+xml); the
    document element is ``svg`` in the SVG namespace; no ``script`` and no
    ``foreignObject`` anywhere; no ``on*`` attribute on any element, the root
    included. Nothing else is checked by the page, so nothing else is here.
    """
    if not isinstance(text, str) or text == "":
        return False
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return False
    if _namespace(root.tag) != SVG_NAMESPACE or _local(root.tag) != "svg":
        return False
    for element in root.iter():
        if _local(element.tag) in ("script", "foreignObject"):
            return False
        for attribute in element.attrib:
            if _local(attribute).lower().startswith("on"):
                return False
    return True


def ids_of(svg: str) -> list:
    return [
        element.get("id")
        for element in ET.fromstring(svg).iter()
        if element.get("id") is not None
    ]


# --- the live exchange, with the one pipeline result captured --------------


class Capture:
    """Counts pipeline calls and keeps the results, wrapping the real one."""

    def __init__(self, real):
        self.real = real
        self.results = []

    def __call__(self, *args, **kwargs):
        result = self.real(*args, **kwargs)
        self.results.append(result)
        return result


def exchange_with_capture(monkeypatch, payload):
    capture = Capture(server_module.render_chart_and_dasha_at)
    monkeypatch.setattr(server_module, "render_chart_and_dasha_at", capture)
    running = start()
    try:
        answer = post(running, payload=payload)
        return running, answer, capture
    finally:
        running.stop()


@pytest.fixture(scope="module")
def reference():
    """One live selected-place request and the one result behind it."""
    patch = pytest.MonkeyPatch()
    try:
        payload = {
            "date": "1995-03-21",
            "time": "06:45",
            "place_text": JALANDHAR_LABEL,
            "place_id": str(JALANDHAR_ID),
        }
        running, answer, capture = exchange_with_capture(patch, payload)
    finally:
        patch.undo()
    assert answer.status == 200
    assert len(capture.results) == 1
    return running, payload, answer, capture.results[0]


def plain_document(running, payload, result):
    """``serialize`` without the keyword, for the same result and request."""
    parsed = transport.parse_request(json.dumps(payload).encode("utf-8"))
    effective = server_module._effective_input(running.server, parsed)
    rows = dasha_rows(result.timeline, depth=transport.DEPTH)
    return parsed, effective, rows, transport.serialize(
        result, parsed, effective=effective, rows=rows
    )


# --- the field --------------------------------------------------------------


def test_the_document_carries_the_south_indian_render_of_the_one_result(reference):
    _running, _payload, answer, result = reference
    document = answer.json()

    assert list(document) == EXTENDED_KEYS
    assert document["south_indian_svg"] == render_south_indian_svg(
        result.d1, transport.SOUTH_INDIAN_RENDERER_OPTIONS
    )
    assert document["south_indian_svg"].startswith("<svg")


def test_svg_is_still_the_north_indian_document(reference):
    _running, _payload, answer, result = reference
    document = answer.json()

    assert document["svg"] == render_north_indian_svg(
        result.d1, transport.RENDERER_OPTIONS
    )
    assert document["svg"] == result.svg
    assert document["svg"] != document["south_indian_svg"]


def test_svg_equals_the_golden_svg_where_the_platform_reproduces_it(reference):
    """Section 9.2: the golden is platform-pinned; its ``svg`` is compared here.

    The North Indian document prints degrees truncated to whole minutes, so it
    is reproduced on far more platforms than the whole golden document is.
    It is compared whenever it can be; a mismatch fails only where the golden
    is otherwise reproduced, which is where a mismatch would mean something.
    """
    _running, _payload, answer, _result = reference
    document = answer.json()
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    if document["svg"] == golden["svg"]:
        return
    if document["timeline"] == golden["timeline"]:
        pytest.fail("the golden is reproduced here but its svg is not")
    pytest.skip("the platform-pinned golden is not reproduced on this platform")


def test_every_other_field_is_what_serialize_gives_without_the_keyword(reference):
    running, payload, answer, result = reference
    document = answer.json()
    parsed, effective, rows, plain = plain_document(running, payload, result)

    for key in ("planetary_positions", "timeline", "rows", "birth_chain"):
        assert document[key] == plain[key], key
    without = {
        key: value
        for key, value in document.items()
        if key not in ("south_indian_svg", "overlay", "panchanga")
    }
    assert without == json.loads(transport.encode(plain))
    # The whole body is the encoder's bytes of the extended document.
    extended = transport.serialize(
        result,
        parsed,
        effective=effective,
        rows=rows,
        south_indian_svg=document["south_indian_svg"],
        overlay=document["overlay"],
        panchanga=document["panchanga"],
    )
    assert answer.body == transport.encode(extended)


def test_the_document_carries_the_overlay_block_of_the_one_result(reference):
    """Layer 20 section 6.2: ``overlay`` is ``overlay_block`` of ``result.d1``
    with the North Indian document's own display flags."""
    _running, _payload, answer, result = reference
    document = answer.json()

    assert document["overlay"] == overlay_block(
        result.d1,
        show_degrees=transport.RENDERER_OPTIONS.show_degrees,
        mark_node_retrograde=transport.RENDERER_OPTIONS.mark_node_retrograde,
    )
    assert document["overlay"]["schema"] == "vedic_chart.overlay/1"
    assert [entry["key"] for entry in document["overlay"]["entries"]] == [
        planet["key"] for planet in document["planetary_positions"]["planets"]
    ]


@pytest.mark.parametrize("case", sorted(REQUEST_CASES))
def test_every_request_shape_carries_both_documents(monkeypatch, case):
    time_text, place_text, place_id = REQUEST_CASES[case]
    payload = {
        "date": "1995-03-21",
        "time": time_text,
        "place_text": place_text,
        "place_id": place_id,
    }
    _running, answer, capture = exchange_with_capture(monkeypatch, payload)

    assert answer.status == 200
    assert len(capture.results) == 1
    document = answer.json()
    result = capture.results[0]
    assert list(document) == EXTENDED_KEYS
    assert document["svg"] == result.svg
    assert document["south_indian_svg"] == render_south_indian_svg(
        result.d1, transport.SOUTH_INDIAN_RENDERER_OPTIONS
    )


def test_the_fixed_south_indian_options_are_the_specified_ones():
    options = transport.SOUTH_INDIAN_RENDERER_OPTIONS

    assert options.show_degrees is True
    assert options.mark_node_retrograde is False
    assert options.caption is False
    assert options.width is None
    assert options.id_prefix == "d1-south"
    assert transport.RENDERER_OPTIONS.id_prefix == "d1"


# --- safety and coexistence -------------------------------------------------


def test_both_svgs_pass_the_page_s_insert_svg_acceptance(reference):
    _running, _payload, answer, _result = reference
    document = answer.json()

    assert page_accepts_svg(document["svg"])
    assert page_accepts_svg(document["south_indian_svg"])


@pytest.mark.parametrize(
    "text",
    [
        "",
        None,
        "<svg><script/></svg>",
        '<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" onload="x"></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><g onclick="x"/></svg>',
        '<html xmlns="http://www.w3.org/2000/svg"/>',
        "<svg",
    ],
)
def test_the_re_implemented_acceptance_refuses_what_the_page_refuses(text):
    assert page_accepts_svg(text) is False


def test_the_ids_are_unique_across_the_two_documents(reference):
    _running, _payload, answer, _result = reference
    document = answer.json()

    north = ids_of(document["svg"])
    south = ids_of(document["south_indian_svg"])
    assert north == ["d1-title", "d1-desc"]
    assert south == ["d1-south-title", "d1-south-desc"]
    assert len(set(north + south)) == len(north + south) == 4
    south_root = ET.fromstring(document["south_indian_svg"])
    assert south_root.get("aria-labelledby") == "d1-south-title"
    assert south_root.get("aria-describedby") == "d1-south-desc"


def test_the_content_security_policy_is_unchanged(reference):
    _running, _payload, answer, _result = reference

    assert server_module.CONTENT_SECURITY_POLICY == CONTENT_SECURITY_POLICY
    assert answer.header("content-security-policy") == CONTENT_SECURITY_POLICY
    assert_contract_headers(answer)


def test_the_index_is_served_with_the_same_policy():
    running = start()
    try:
        index = get(running, "/")
    finally:
        running.stop()
    assert index.status == 200
    assert index.header("content-security-policy") == CONTENT_SECURITY_POLICY


# --- one calculation, and where the second document is rendered -----------


def test_one_pipeline_call_per_request(monkeypatch):
    capture = Capture(server_module.render_chart_and_dasha_at)
    monkeypatch.setattr(server_module, "render_chart_and_dasha_at", capture)
    renders = []
    real_south = server_module.render_south_indian_svg

    def counting_south(*args, **kwargs):
        renders.append(args)
        return real_south(*args, **kwargs)

    monkeypatch.setattr(server_module, "render_south_indian_svg", counting_south)
    blocks = []
    real_overlay = server_module.overlay_block

    def counting_overlay(*args, **kwargs):
        blocks.append((args, kwargs))
        return real_overlay(*args, **kwargs)

    monkeypatch.setattr(server_module, "overlay_block", counting_overlay)
    running = start()
    try:
        first = selected(running, JALANDHAR_ID, JALANDHAR_LABEL)
        assert first.status == 200
        assert len(capture.results) == 1
        assert len(renders) == 1
        assert len(blocks) == 1
        second = post(running)
        assert second.status == 200
        assert len(capture.results) == 2
        assert len(renders) == 2
        assert len(blocks) == 2
    finally:
        running.stop()
    # The South Indian document and the overlay block are made from the very
    # result the pipeline returned for that request, never from a second
    # calculation.
    for args, result in zip(renders, capture.results):
        assert args[0] is result.d1
        assert args[1] is transport.SOUTH_INDIAN_RENDERER_OPTIONS
    for (args, kwargs), result in zip(blocks, capture.results):
        assert args == (result.d1,)
        assert kwargs == {
            "show_degrees": transport.RENDERER_OPTIONS.show_degrees,
            "mark_node_retrograde": transport.RENDERER_OPTIONS.mark_node_retrograde,
        }


def _api_chart_tree():
    tree = ast.parse(SERVER_SOURCE.read_text(encoding="utf-8"))
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_api_chart"
    )


def _is_lock(node) -> bool:
    return isinstance(node, ast.With) and any(
        isinstance(item.context_expr, ast.Name)
        and item.context_expr.id == "ENGINE_LOCK"
        for item in node.items
    )


def _calls(node, name):
    return [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == name
    ]


def test_the_south_indian_render_is_after_the_lock_and_inside_the_try():
    """Section 5.2, by the syntax tree of ``_api_chart``; Layer 20 section 6.2
    adds the ``overlay_block`` call immediately after the South render."""
    function = _api_chart_tree()

    calls = _calls(function, "render_south_indian_svg")
    assert len(calls) == 1
    call = calls[0]

    locks = [node for node in ast.walk(function) if _is_lock(node)]
    assert len(locks) == 1
    lock = locks[0]
    assert call not in list(ast.walk(lock))

    tries = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Try) and any(_is_lock(item) for item in node.body)
    ]
    assert len(tries) == 1
    attempt = tries[0]
    body = list(attempt.body)
    lock_position = body.index(lock)
    owners = [
        position
        for position, statement in enumerate(body)
        if call in list(ast.walk(statement))
    ]
    # A statement of the try body itself, immediately after the lock block.
    assert owners == [lock_position + 1]
    assert isinstance(body[lock_position + 1], ast.Assign)

    # Its arguments: the result's D1 chart and the fixed options.
    assert ast.unparse(call.args[0]) == "result.d1"
    assert ast.unparse(call.args[1]) == "transport.SOUTH_INDIAN_RENDERER_OPTIONS"

    # Layer 20: the overlay block, the next statement of the same try body,
    # from the same chart with the North Indian document's display flags.
    overlay_calls = _calls(function, "overlay_block")
    assert len(overlay_calls) == 1
    overlay_call = overlay_calls[0]
    assert overlay_call not in list(ast.walk(lock))
    overlay_owners = [
        position
        for position, statement in enumerate(body)
        if overlay_call in list(ast.walk(statement))
    ]
    assert overlay_owners == [lock_position + 2]
    assert isinstance(body[lock_position + 2], ast.Assign)
    assert [ast.unparse(argument) for argument in overlay_call.args] == ["result.d1"]
    assert {
        keyword.arg: ast.unparse(keyword.value) for keyword in overlay_call.keywords
    } == {
        "show_degrees": "transport.RENDERER_OPTIONS.show_degrees",
        "mark_node_retrograde": "transport.RENDERER_OPTIONS.mark_node_retrograde",
    }

    # The serialisation receives it, outside the lock as before.
    serialize = [
        node
        for node in ast.walk(attempt)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "serialize"
    ]
    assert len(serialize) == 1
    keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in serialize[0].keywords}
    assert keywords["south_indian_svg"] == "south"
    assert keywords["overlay"] == "overlay"
    assert serialize[0] not in list(ast.walk(lock))

    # The generic arm that turns any failure into the 500 is this try's.
    generic = [
        handler
        for handler in attempt.handlers
        if isinstance(handler.type, ast.Name) and handler.type.id == "Exception"
    ]
    assert len(generic) == 1
    failures = [
        node
        for node in ast.walk(generic[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_fail"
    ]
    assert len(failures) == 1
    assert [
        argument.value
        for argument in failures[0].args[:2]
        if isinstance(argument, ast.Constant)
    ] == [500, "unexpected"]

    # And the lock still holds exactly the two calls it held before.
    held = {
        node.func.id
        for node in ast.walk(ast.Module(body=lock.body, type_ignores=[]))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert held == {"render_chart_and_dasha_at", "dasha_rows", "panchanga_document"}


# --- failure ----------------------------------------------------------------


@pytest.mark.parametrize("error", [ValueError, RuntimeError])
def test_a_failing_south_indian_renderer_is_the_unexpected_500(monkeypatch, error):
    def failing(*_args, **_kwargs):
        raise error("injected South Indian renderer failure")

    monkeypatch.setattr(server_module, "render_south_indian_svg", failing)
    running = start()
    try:
        answer = selected(running, JALANDHAR_ID, JALANDHAR_LABEL)
    finally:
        running.stop()

    assert answer.status == 500
    assert answer.status != 200
    assert_error_document(answer, "unexpected")
    assert_contract_headers(answer)
    document = answer.json()
    assert set(document) == {"schema", "error"}
    assert "svg" not in document
    assert "south_indian_svg" not in document
    assert "overlay" not in document
    assert error.__name__ in document["error"]["message"]


@pytest.mark.parametrize("error", [ValueError, RuntimeError])
def test_a_failing_overlay_block_is_the_unexpected_500(monkeypatch, error):
    """Layer 20 section 6.2: as a South render failure is."""

    def failing(*_args, **_kwargs):
        raise error("injected overlay block failure")

    monkeypatch.setattr(server_module, "overlay_block", failing)
    running = start()
    try:
        answer = selected(running, JALANDHAR_ID, JALANDHAR_LABEL)
    finally:
        running.stop()

    assert answer.status == 500
    assert_error_document(answer, "unexpected")
    assert_contract_headers(answer)
    document = answer.json()
    assert set(document) == {"schema", "error"}
    assert "south_indian_svg" not in document
    assert "overlay" not in document
    assert error.__name__ in document["error"]["message"]


# --- the pipeline is not touched --------------------------------------------


def test_the_pipeline_s_project_imports_are_unchanged():
    """Section 8.3: ``pipeline.py`` does not know the South Indian renderer."""
    tree = ast.parse(PIPELINE_SOURCE.read_text(encoding="utf-8"))
    render_names = set()
    every_name = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            every_name.add(module)
            every_name.update(alias.name for alias in node.names)
            if module == "vedic_chart.render":
                render_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            every_name.update(alias.name for alias in node.names)

    assert render_names == {"NorthIndianOptions", "render_north_indian_svg"}
    assert not [name for name in every_name if "south" in name.lower()]
    assert "south" not in PIPELINE_SOURCE.read_text(encoding="utf-8").lower()
