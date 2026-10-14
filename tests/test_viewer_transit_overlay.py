"""Layer 20, page side: the natal–transit overlay toggle.

Specification ``docs/LAYER20_TRANSIT_OVERLAY_SPEC.md`` sections 3, 5, 6.3–6.8,
9 and 10.1–10.3, 10.6. Three groups of tests, in the style of
``tests/test_viewer_south_indian.py``:

* **static rules** for ``viewer.html``, ``viewer.js`` and ``viewer.css`` --
  the control's ids, order and attributes, the exact start-up strings, the
  third ``/api/chart`` request with the natal request's own options, the
  composition fault seam behind ``#acceptance``, the CSS classes;
* the page's **section 6.7 validation, re-implemented in Python** (as
  ``page_accepts_svg`` re-implements ``insertSvg``) and applied to the real
  server's documents and to malformed variants, plus the page's section 5.3
  placement rule applied to the reference natal and transit documents, which
  must give the section 5.5 panel;
* **server-level** tests that a transit request is an ordinary request: the
  transit-shaped body built from a natal document's effective place is
  answered byte for byte as the same four strings sent as a natal request,
  with ``time_assumed`` false and source ``selected``; the natal instant as a
  transit instant gives equal placements; DST-gap and ambiguous local times
  and an impossible date are 400 ``input``.

The browser behaviour (requests, races, visibility, text bounds) is the
acceptance script's (``tools/viewer/acceptance.py``, the ``transit_*``
checks); nothing here claims it.
"""

import copy
import json
import re

import pytest

from render_helpers import REPO_ROOT
from test_viewer_server import (
    JALANDHAR_ID,
    JALANDHAR_LABEL,
    LONDON_ID,
    LONDON_LABEL,
    assert_error_document,
    post,
    start,
)

STATIC_DIR = REPO_ROOT / "src" / "vedic_chart" / "viewer" / "static"

TRANSIT_DATE = "2026-10-08"
TRANSIT_TIME = "14:30:00"
NATAL = {"date": "1995-03-21", "time": "06:45"}

OVERLAY_SCHEMA = "vedic_chart.overlay/1"
POSITIONS_SCHEMA = "vedic_chart.planetary_positions/1"
SIGN_KEYS = [str(number) for number in range(1, 13)]
COORDINATE = re.compile(r"^[0-9]+\.[0-9]{2}$")
DEGREE_TEXT = re.compile(r"^[0-9]{1,2}°[0-9]{2}′$")
COUNT = re.compile(r"^[0-9]+$")
FLOOR_FONT = "21.00"

#: Section 5.5, for the Jalandhar natal chart and the 2026-10-08 14:30:00
#: transit (the worked example of section 5.7).
EXPECTED_PANEL = [
    ["1", "Meena", "T:Sa 16°45′ ℞", "shown", "shown"],
    ["5", "Karka", "T:Ma 11°41′, T:Ju 26°38′", "T:+2 in row (0 shown)", "shown"],
    ["6", "Simha", "T:Mo 22°49′, T:Ke 3°05′", "shown", "shown"],
    ["7", "Kanya", "T:Su 20°52′", "shown", "shown"],
    ["8", "Tula", "T:Me 15°34′, T:Ve 13°45′ ℞", "T:+2 marker (0 shown)", "shown"],
    ["12", "Kumbha", "T:Ra 3°05′", "T:+1 marker (0 shown)", "shown"],
]


def read_static(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


_START_TAG = re.compile(r"<[a-zA-Z][^>]*>", re.DOTALL)


def _tag(source: str, identifier: str) -> str:
    for tag in _START_TAG.findall(source):
        if re.search(rf'\sid="{re.escape(identifier)}"', tag):
            return tag
    raise AssertionError(f"no element with id {identifier!r}")


def _attribute(tag: str, name: str):
    match = re.search(rf'\s{name}="([^"]*)"', tag)
    return None if match is None else match.group(1)


def _has_flag(tag: str, name: str) -> bool:
    return re.search(rf"\s{name}(?=[\s>/=])", tag) is not None


def _transit_fieldset(source: str) -> str:
    start_at = source.index('<fieldset class="v-transit" id="transit"')
    return source[start_at : source.index("</fieldset>", start_at) + len("</fieldset>")]


def _template(source: str) -> str:
    start_at = source.index('<template id="results-template">')
    return source[start_at : source.index("</template>", start_at)]


# --- static rules: viewer.html ----------------------------------------------


def test_the_transit_control_is_a_disabled_native_fieldset_after_chart_style():
    source = read_static("viewer.html")
    fieldset = _tag(source, "transit")

    assert fieldset.startswith("<fieldset")
    assert _attribute(fieldset, "class") == "v-transit"
    assert _has_flag(fieldset, "disabled")
    assert '<legend class="v-transit-legend">Transits</legend>' in source
    order = [
        source.index('id="chart-style"'),
        source.index('id="transit"'),
        source.index('id="results"'),
    ]
    assert order == sorted(order)
    form = source[source.index("<form"): source.index("</form>")]
    assert 'id="transit' not in form
    assert 'id="transit"' not in _template(source)


def test_the_transit_controls_and_their_labels():
    source = read_static("viewer.html")
    fieldset = _transit_fieldset(source)

    toggle = _tag(fieldset, "transit-toggle")
    assert _attribute(toggle, "type") == "checkbox"
    date = _tag(fieldset, "transit-date")
    assert _attribute(date, "type") == "date"
    assert _attribute(date, "autocomplete") == "off"
    time = _tag(fieldset, "transit-time")
    assert _attribute(time, "type") == "time"
    assert _attribute(time, "step") == "1"
    assert _attribute(time, "autocomplete") == "off"
    update = _tag(fieldset, "transit-update")
    assert update.startswith("<button")
    assert _attribute(update, "type") == "button"
    assert not _has_flag(update, "hidden")
    assert not _has_flag(update, "disabled")
    assert re.search(r'id="transit-update">Update</button>', fieldset)
    status = _tag(fieldset, "transit-status")
    assert status.startswith("<p")
    assert _attribute(status, "role") == "status"
    assert _attribute(status, "tabindex") == "-1"
    assert _tag(fieldset, "transit-place").startswith("<p")

    for identifier, text in (
        ("transit-toggle", "Show transits"),
        ("transit-date", "Transit date"),
        ("transit-time", "Transit time"),
    ):
        assert re.search(
            rf'<label class="v-transit-label" for="{identifier}">{re.escape(text)}</label>',
            fieldset,
        ), identifier

    # No `name` attribute, no `checked` anywhere, no inline handler.
    assert " name=" not in fieldset
    assert "checked" not in source
    assert re.search(r"<[^>]*?\son[a-z]+\s*=", fieldset, re.IGNORECASE) is None
    assert source.count('autocomplete="off"') == 5


def test_the_transits_panel_is_in_the_template_after_the_charts():
    template = _template(read_static("viewer.html"))
    panel_tag = _tag(template, "transit-panel")

    assert panel_tag.startswith("<section")
    assert _has_flag(panel_tag, "hidden")
    assert template.index('id="charts"') < template.index('id="transit-panel"')
    panel = template[template.index('id="transit-panel"'):]
    panel = panel[: panel.index("</section>")]
    # The summary is the panel's first paragraph.
    first_p = re.search(r"<p[^>]*>", panel).group(0)
    assert _attribute(first_p, "id") == "transit-summary"
    assert _has_flag(_tag(panel, "transit-assumed"), "hidden")
    assert "Natal chart uses assumed birth details." in panel
    assert "<caption" in panel
    headers = re.findall(r'<th class="v-transit-panel-th" scope="col">([^<]*)</th>', panel)
    assert headers == [
        "House", "Sign (natal)", "Transit planets", "North Indian", "South Indian"
    ]
    assert _tag(panel, "transit-panel-body").startswith("<tbody")
    assert _tag(panel, "transit-panel-wrapper").startswith("<div")
    assert _has_flag(_tag(panel, "transit-panel-scroll-hint"), "hidden")


# --- static rules: viewer.js ------------------------------------------------


def _fetch_options(source: str, start_at: int) -> str:
    """The text of one ``fetch(...)`` call's option object, without the body."""
    opening = source.index("{", start_at)
    closing = source.index("body:", opening)
    return source[opening:closing]


def test_the_transit_request_is_a_third_call_with_the_natal_options():
    source = read_static("viewer.js")
    chart_calls = [match.start() for match in re.finditer(r'fetch\("/api/chart"', source)]

    assert source.count("fetch(") == 3
    assert len(chart_calls) == 2
    natal, transit = (_fetch_options(source, at) for at in chart_calls)
    assert natal == transit
    for option in (
        'method: "POST"', 'mode: "same-origin"', 'credentials: "omit"',
        'cache: "no-store"', 'redirect: "error"', 'referrerPolicy: "no-referrer"',
        '"X-Viewer-Token": token',
    ):
        assert option in transit
    # The body is the captured four-key record: the effective place record.
    assert "place_text: shown.document.effective.place.label," in source
    assert "place_id: String(shown.document.effective.place.geoname_id)" in source


def test_the_start_up_state_and_the_forbidden_names():
    source = read_static("viewer.js")

    for exact in (
        "var transitOn = false;",
        "transitToggle.checked = false;",
        "wireTransitControl();",
        "var transitSequence = 0;",
        "var transitPending = null;",
        "var transitResult = null;",
        "var transitFailure = null;",
        "var overlayMeta = META_NONE;",
        "var natalLoading = false;",
    ):
        assert exact in source, exact
    for function in (
        "sameKey", "currentKey", "natalUsable", "overlayVisible", "syncOverlay",
        "invalidatePending", "composeTransit", "commitTransit",
    ):
        assert f"function {function}(" in source, function
    for forbidden in (
        "setInterval", "new Date", "Date.", "Number(", "parseFloat", "innerHTML",
        "localStorage", "sessionStorage", "history.",
    ):
        assert forbidden not in source, forbidden


def test_the_single_visibility_predicate_is_the_specified_one():
    source = read_static("viewer.js")
    body = source[source.index("function overlayVisible("):]
    body = body[: body.index("\n  }\n")]

    for term in (
        "transitOn", "natalUsable()", "transitResult !== null",
        "sameKey(transitResult.key, currentKey())",
    ):
        assert term in body, term
    # Every show goes through it: showOverlay is called from syncOverlay only.
    assert source.count("showOverlay(") == 2  # the definition and syncOverlay


def test_the_composition_fault_seam_is_behind_the_acceptance_hash():
    source = read_static("viewer.js")
    hash_check = source.index('window.location.hash === "#acceptance"')

    assert "window.__transitComposeFault" in source
    assert source.index("window.__transitComposeFault") > hash_check
    assert "var composeFault = null;" in source
    # Consulted only inside composeTransit.
    compose = source[source.index("function composeTransit("):]
    compose = compose[: compose.index("\n  }\n")]
    assert source.count("composeFault()") == compose.count("composeFault()") == 2


def test_the_ownership_guard_precedes_every_response_handler_action():
    source = read_static("viewer.js")
    request = source[source.index("function requestTransit("):]
    request = request[: request.index("\n  }\n")]

    handlers = re.findall(r"\.(then|catch)\(function \((answer|error)\) \{\n\s*(.*)", request)
    assert [(kind, first) for kind, _name, first in handlers] == [
        ("then", "if (!owns(mine)) {"),
        ("catch", "if (!owns(mine)) {"),
    ]


# --- static rules: viewer.css -----------------------------------------------


def test_the_transit_css_classes_carry_the_prefix_and_stay_out_of_the_charts():
    body = re.sub(r"/\*.*?\*/", "", read_static("viewer.css"), flags=re.DOTALL)
    selectors = [
        selector.strip()
        for group in re.findall(r"([^{}]+)\{", body)
        for selector in group.split(",")
        if "transit" in selector
    ]
    assert selectors
    for selector in selectors:
        assert "#chart" not in selector, selector
        for name in re.findall(r"\.([A-Za-z][A-Za-z0-9_-]*)", selector):
            assert name.startswith("v-"), selector
    html_classes = set(
        name
        for value in re.findall(r'class="([^"]*)"', read_static("viewer.html"))
        for name in value.split()
        if "transit" in name
    )
    assert html_classes
    assert all(name.startswith("v-transit") for name in html_classes)


# --- the page's section 6.7 validation, re-implemented -----------------------


def _is_object(value) -> bool:
    return isinstance(value, dict)


def _is_coordinate(value) -> bool:
    return isinstance(value, str) and COORDINATE.fullmatch(value) is not None


def _is_count(value) -> bool:
    # The page tests String(value) against /^[0-9]+$/ on a JSON number.
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and COUNT.fullmatch(str(value)) is not None
    )


def _is_sign(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 12


def _rung_problem(rung, layout):
    if not _is_object(rung):
        return "rung"
    if not _is_coordinate(rung.get("font_size")) or not _is_coordinate(rung.get("x")):
        return "font_size/x"
    if layout == "inline":
        if not _is_coordinate(rung.get("deg_x")):
            return "deg_x"
        rows = rung.get("rows")
        if not isinstance(rows, list) or not all(_is_coordinate(row) for row in rows):
            return "rows"
        return None
    entries = rung.get("entries")
    if not isinstance(entries, list):
        return "entries"
    for entry in entries:
        if not (_is_object(entry) and _is_coordinate(entry.get("abbr_y"))
                and _is_coordinate(entry.get("deg_y"))):
            return "entry"
    if not entries:
        return None if rung.get("overflow_y", "absent") is None else "overflow_y"
    return None if _is_coordinate(rung.get("overflow_y")) else "overflow_y"


def _slot_problem(slot):
    if not _is_object(slot):
        return "slot"
    if not _is_sign(slot.get("house")):
        return "house"
    if slot.get("layout") not in ("inline", "stacked"):
        return "layout"
    if not _is_count(slot.get("natal_rows")):
        return "natal_rows"
    rungs = slot.get("rungs")
    if not isinstance(rungs, list) or not rungs:
        return "rungs"
    if not _is_object(rungs[-1]) or rungs[-1].get("font_size") != FLOOR_FONT:
        return "floor"
    for rung in rungs:
        problem = _rung_problem(rung, slot["layout"])
        if problem:
            return problem
    marker = slot.get("marker", "absent")
    if marker is not None:
        if not (_is_object(marker) and _is_coordinate(marker.get("x"))
                and _is_coordinate(marker.get("y"))
                and marker.get("anchor") in ("start", "middle", "end")):
            return "marker"
    return None


def natal_overlay_problem(document):
    """``viewer.js`` ``natalOverlayProblem``, in Python. None when usable."""
    if "overlay" not in document:
        return "no overlay block"
    block = document["overlay"]
    if not _is_object(block):
        return "not an object"
    if block.get("schema") != OVERLAY_SCHEMA:
        return "schema"
    if not isinstance(block.get("prefix"), str) or block["prefix"] == "":
        return "prefix"
    if not isinstance(block.get("font_family"), str) or block["font_family"] == "":
        return "font_family"
    if not _is_coordinate(block.get("marker_font_size")):
        return "marker_font_size"
    slots = block.get("slots")
    if not _is_object(slots):
        return "slots"
    for style in ("north", "south"):
        table = slots.get(style)
        if not _is_object(table) or sorted(table) != sorted(SIGN_KEYS):
            return f"slots.{style} keys"
        for sign in SIGN_KEYS:
            problem = _slot_problem(table[sign])
            if problem:
                return f"slots.{style}.{sign}: {problem}"
    seen = set()
    for sign in SIGN_KEYS:
        house = slots["north"][sign]["house"]
        if house != slots["south"][sign]["house"]:
            return "houses differ"
        if house in seen:
            return "not a permutation"
        seen.add(house)
    return None


def transit_overlay_problem(document, natal_block):
    """``viewer.js`` ``transitOverlayProblem``, in Python. None when usable."""
    block = document.get("overlay")
    positions = document.get("planetary_positions")
    if not _is_object(block) or block.get("schema") != OVERLAY_SCHEMA:
        return "overlay schema"
    if block.get("prefix") != natal_block["prefix"]:
        return "prefix"
    if not _is_object(positions) or positions.get("schema") != POSITIONS_SCHEMA:
        return "positions schema"
    entries = block.get("entries")
    planets = positions.get("planets")
    if not isinstance(entries, list) or len(entries) != 9:
        return "entries"
    if not isinstance(planets, list) or len(planets) != 9:
        return "planets"
    keys = set()
    for entry, planet in zip(entries, planets):
        if not (_is_object(entry) and _is_object(planet) and _is_object(planet.get("sign"))):
            return "entry"
        if not isinstance(entry.get("key"), str) or entry["key"] != planet.get("key"):
            return "key order"
        if entry["key"] in keys:
            return "duplicate key"
        keys.add(entry["key"])
        if not isinstance(entry.get("abbr"), str) or len(entry["abbr"]) != 2:
            return "abbr"
        if not isinstance(entry.get("degree_text"), str) or not DEGREE_TEXT.fullmatch(
            entry["degree_text"]
        ):
            return "degree_text"
        if not isinstance(entry.get("underline"), bool):
            return "underline"
        if not _is_sign(planet["sign"].get("number")) or not isinstance(
            planet["sign"].get("name"), str
        ):
            return "sign"
        if not isinstance(planet.get("kind"), str):
            return "kind"
        if entry.get("rashi_number") != planet["sign"]["number"]:
            return "rashi_number"
    return None


# --- the page's section 5.3 rule, re-implemented ------------------------------


def _capacity(rung, layout):
    return len(rung["entries"]) if layout == "stacked" else len(rung["rows"])


def cell_outcome(slot, count):
    """``viewer.js`` ``placeCell``'s decision, as the panel words it."""
    for rung in slot["rungs"]:
        if _capacity(rung, slot["layout"]) >= count:
            return "shown"
    rows = _capacity(slot["rungs"][-1], slot["layout"])
    if rows >= 1:
        return f"T:+{count - (rows - 1)} in row ({rows - 1} shown)"
    if slot["marker"] is not None:
        return f"T:+{count} marker (0 shown)"
    return "panel only — no room for marker"


def panel_rows(natal, transit):
    block = natal["overlay"]
    prefix = block["prefix"]
    by_sign = {}
    names = {}
    for entry, planet in zip(transit["overlay"]["entries"], transit["planetary_positions"]["planets"]):
        sign = str(entry["rashi_number"])
        by_sign.setdefault(sign, []).append(entry)
        names[sign] = planet["sign"]["name"]
    rows = []
    for house in range(1, 13):
        for sign in SIGN_KEYS:
            if block["slots"]["north"][sign]["house"] != house or sign not in by_sign:
                continue
            entries = by_sign[sign]
            rows.append([
                str(house),
                names[sign],
                ", ".join(
                    f"{prefix}{entry['abbr']} {entry['degree_text']}"
                    + (" ℞" if entry["underline"] else "")
                    for entry in entries
                ),
                cell_outcome(block["slots"]["north"][sign], len(entries)),
                cell_outcome(block["slots"]["south"][sign], len(entries)),
            ])
    return rows


# --- the live documents -----------------------------------------------------


def _body(date, time, place_text, place_id):
    return {"date": date, "time": time, "place_text": place_text, "place_id": place_id}


@pytest.fixture(scope="module")
def exchanges():
    """The natal document (default place), the transit-shaped request built
    from it as the page builds it, and the same strings sent again."""
    running = start()
    try:
        natal = post(running, payload=_body(NATAL["date"], NATAL["time"], "", ""))
        assert natal.status == 200
        natal_document = natal.json()
        place = natal_document["effective"]["place"]
        transit_body = _body(
            TRANSIT_DATE, TRANSIT_TIME, place["label"], str(place["geoname_id"])
        )
        transit = post(running, payload=transit_body)
        again = post(running, payload=dict(transit_body))
        selected_natal = post(
            running,
            payload=_body(NATAL["date"], NATAL["time"], JALANDHAR_LABEL, str(JALANDHAR_ID)),
        )
        natal_as_transit = post(
            running,
            payload=_body(NATAL["date"], "06:45:00", JALANDHAR_LABEL, str(JALANDHAR_ID)),
        )
        return {
            "natal": natal,
            "transit_body": transit_body,
            "transit": transit,
            "again": again,
            "selected_natal": selected_natal,
            "natal_as_transit": natal_as_transit,
        }
    finally:
        running.stop()


def test_the_natal_document_s_overlay_is_usable(exchanges):
    document = exchanges["natal"].json()

    assert document["effective"]["source"] == "default"
    assert document["effective"]["place"]["geoname_id"] == JALANDHAR_ID
    assert natal_overlay_problem(document) is None


def test_the_transit_body_is_the_ordinary_four_key_request(exchanges):
    body = exchanges["transit_body"]

    assert list(body) == ["date", "time", "place_text", "place_id"]
    assert body == {
        "date": TRANSIT_DATE,
        "time": TRANSIT_TIME,
        "place_text": JALANDHAR_LABEL,
        "place_id": str(JALANDHAR_ID),
    }


def test_a_transit_request_is_answered_as_the_same_natal_request(exchanges):
    """Section 10.2: byte-equal to the same four strings sent as a natal request."""
    transit = exchanges["transit"]
    again = exchanges["again"]

    assert transit.status == again.status == 200
    assert transit.body == again.body
    document = transit.json()
    assert document["request"]["submitted"] == exchanges["transit_body"]
    assert document["effective"]["time_assumed"] is False
    assert document["effective"]["source"] == "selected"
    assert document["effective"]["date"] == TRANSIT_DATE
    assert document["effective"]["time"] == TRANSIT_TIME
    assert document["birth"]["offset"] == "+05:30"
    assert document["birth"]["zone"] == "Asia/Kolkata"


def test_the_transit_document_passes_the_page_s_validation(exchanges):
    natal = exchanges["natal"].json()
    transit = exchanges["transit"].json()

    assert natal_overlay_problem(transit) is None
    assert transit_overlay_problem(transit, natal["overlay"]) is None


def test_the_natal_instant_as_a_transit_gives_the_same_placements(exchanges):
    """Section 10.3."""
    natal = exchanges["selected_natal"].json()
    as_transit = exchanges["natal_as_transit"].json()

    assert natal["planetary_positions"]["planets"] == as_transit["planetary_positions"]["planets"]
    assert natal["overlay"]["entries"] == as_transit["overlay"]["entries"]
    assert as_transit["effective"]["time_assumed"] is False
    assert as_transit["effective"]["source"] == "selected"


def test_the_page_rule_gives_the_specified_panel(exchanges):
    """Sections 5.3, 5.5 and 5.7: the worked example, from the real documents."""
    natal = exchanges["natal"].json()
    transit = exchanges["transit"].json()

    assert panel_rows(natal, transit) == EXPECTED_PANEL


# --- malformed variants -------------------------------------------------------


def _set(path, value):
    def mutate(document):
        target = document
        for part in path[:-1]:
            target = target[part]
        if value is _DELETE:
            del target[path[-1]]
        else:
            target[path[-1]] = value
    return mutate


_DELETE = object()

NATAL_MALFORMED = {
    "missing_block": _set(["overlay"], _DELETE),
    "block_not_object": _set(["overlay"], []),
    "schema": _set(["overlay", "schema"], "vedic_chart.overlay/2"),
    "empty_prefix": _set(["overlay", "prefix"], ""),
    "font_family": _set(["overlay", "font_family"], 3),
    "marker_font_size": _set(["overlay", "marker_font_size"], 20),
    "eleven_signs": _set(["overlay", "slots", "north", "12"], _DELETE),
    "extra_sign": _set(["overlay", "slots", "south", "13"], {}),
    "house_zero": _set(["overlay", "slots", "north", "1", "house"], 0),
    "house_text": _set(["overlay", "slots", "north", "1", "house"], "2"),
    "houses_differ": _set(["overlay", "slots", "south", "1", "house"], 3),
    "layout": _set(["overlay", "slots", "north", "1", "layout"], "grid"),
    "natal_rows_negative": _set(["overlay", "slots", "north", "1", "natal_rows"], -1),
    "natal_rows_fraction": _set(["overlay", "slots", "north", "1", "natal_rows"], 1.5),
    "no_rungs": _set(["overlay", "slots", "north", "1", "rungs"], []),
    "floor_not_last": _set(["overlay", "slots", "north", "1", "rungs", -1, "font_size"], "22.00"),
    "coordinate_number": _set(["overlay", "slots", "north", "1", "rungs", 0, "x"], 195),
    "coordinate_three_decimals": _set(
        ["overlay", "slots", "north", "1", "rungs", 0, "x"], "195.000"
    ),
    "inline_no_deg_x": _set(["overlay", "slots", "north", "1", "rungs", 0, "deg_x"], _DELETE),
    "inline_row": _set(["overlay", "slots", "north", "1", "rungs", 0, "rows"], ["1.5"]),
    "stacked_entry": _set(
        ["overlay", "slots", "north", "2", "rungs", 0, "entries"], [{"abbr_y": "1.00"}]
    ),
    "stacked_overflow_null_with_entries": _set(
        ["overlay", "slots", "north", "2", "rungs", 0, "overflow_y"], None
    ),
    "stacked_overflow_without_entries": _set(
        ["overlay", "slots", "north", "4", "rungs", 0], {
            "font_size": "21.00", "x": "65.00", "entries": [], "overflow_y": "1.00"
        }
    ),
    "marker_anchor": _set(["overlay", "slots", "north", "1", "marker", "anchor"], "left"),
    "marker_coordinate": _set(["overlay", "slots", "north", "1", "marker", "x"], "x"),
}


def _permuted(document):
    north = document["overlay"]["slots"]["north"]
    south = document["overlay"]["slots"]["south"]
    for table in (north, south):
        table["2"]["house"] = table["1"]["house"]


NATAL_MALFORMED["not_a_permutation"] = _permuted


@pytest.mark.parametrize("case", sorted(NATAL_MALFORMED))
def test_a_malformed_natal_block_disables_the_control(exchanges, case):
    document = copy.deepcopy(exchanges["natal"].json())
    NATAL_MALFORMED[case](document)

    assert natal_overlay_problem(document) is not None


def test_a_valid_crowded_block_is_usable(exchanges):
    """Section 6.7: empty rungs and null markers are not malformed."""
    document = copy.deepcopy(exchanges["natal"].json())
    for table in document["overlay"]["slots"].values():
        for slot in table.values():
            slot["marker"] = None
            floor = slot["rungs"][-1]
            if slot["layout"] == "inline":
                slot["rungs"] = [dict(floor, rows=[])]
            else:
                slot["rungs"] = [dict(floor, entries=[], overflow_y=None)]

    assert natal_overlay_problem(document) is None
    transit = exchanges["transit"].json()
    rows = panel_rows(document, transit)
    assert {row[3] for row in rows} == {"panel only — no room for marker"}
    assert {row[4] for row in rows} == {"panel only — no room for marker"}


TRANSIT_MALFORMED = {
    "schema": _set(["overlay", "schema"], "x"),
    "prefix": _set(["overlay", "prefix"], "TR:"),
    "positions_schema": _set(["planetary_positions", "schema"], "x"),
    "eight_entries": _set(["overlay", "entries", 8], _DELETE),
    "key_order": _set(["overlay", "entries", 0, "key"], "moon"),
    "abbr": _set(["overlay", "entries", 0, "abbr"], "Sun"),
    "degree_text": _set(["overlay", "entries", 0, "degree_text"], "20.87"),
    "degree_text_seconds": _set(["overlay", "entries", 0, "degree_text"], "20°52′11″"),
    "underline": _set(["overlay", "entries", 0, "underline"], "false"),
    "rashi_number": _set(["overlay", "entries", 0, "rashi_number"], 1),
    "sign_number": _set(["planetary_positions", "planets", 0, "sign", "number"], 13),
    "kind": _set(["planetary_positions", "planets", 0, "kind"], None),
}


def _duplicate_key(document):
    entries = document["overlay"]["entries"]
    planets = document["planetary_positions"]["planets"]
    entries[1]["key"] = entries[0]["key"]
    planets[1]["key"] = planets[0]["key"]


TRANSIT_MALFORMED["duplicate_key"] = _duplicate_key


@pytest.mark.parametrize("case", sorted(TRANSIT_MALFORMED))
def test_a_malformed_transit_document_is_rejected(exchanges, case):
    natal = exchanges["natal"].json()
    document = copy.deepcopy(exchanges["transit"].json())
    TRANSIT_MALFORMED[case](document)

    assert transit_overlay_problem(document, natal["overlay"]) is not None


# --- errors: no fallback ------------------------------------------------------


@pytest.fixture(scope="module")
def error_server():
    running = start()
    try:
        yield running
    finally:
        running.stop()


@pytest.mark.parametrize(
    "case, date, time",
    [
        # Europe/London (the fixture's London record): the spring-forward gap
        # and the autumn overlap of 2026.
        ("dst_gap", "2026-03-29", "01:30:00"),
        ("dst_ambiguous", "2026-10-25", "01:30:00"),
        ("impossible_date", "2026-02-30", "12:00:00"),
    ],
)
def test_a_transit_time_the_zone_refuses_is_an_input_error(error_server, case, date, time):
    """Section 10.6: 400 ``input``, never a result and never an assumption."""
    answer = post(
        error_server, payload=_body(date, time, LONDON_LABEL, str(LONDON_ID))
    )

    assert answer.status == 400, case
    assert_error_document(answer, "input")
    assert set(answer.json()) == {"schema", "error"}


def test_the_dst_aware_offset_comes_from_the_transit_instant(error_server):
    """Section 6.7: the offset shown is the transit instant's own."""
    summer = post(
        error_server, payload=_body("2026-07-01", "12:00:00", LONDON_LABEL, str(LONDON_ID))
    ).json()
    winter = post(
        error_server, payload=_body("2026-12-01", "12:00:00", LONDON_LABEL, str(LONDON_ID))
    ).json()

    assert summer["birth"]["zone"] == winter["birth"]["zone"] == "Europe/London"
    assert summer["birth"]["offset"] == "+01:00"
    assert winter["birth"]["offset"] == "+00:00"
    assert json.dumps(summer["effective"]["source"]) == '"selected"'
