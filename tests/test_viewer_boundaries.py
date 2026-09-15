"""Layer 14's import, arithmetic and page boundaries (specification 3.4, 13.3).

Enforced by parsing the source, not by trusting the prose, in the style Layers
11 to 13 already use. The viewer is a *consumer* of the layers below it, so the
rules here are mostly about what it may not reach for: no ephemeris, no
astronomy, no sidereal or vedic arithmetic, no renderer internals, no
``sqlite3``, no ``round()``, no ``float()``, no ``math``, no clock, and no
``logging``.

Two rules are stronger than anything in the earlier layers and are the reason
this file exists.

**One arithmetic function, and it is named.** Specification 3.4 permits
``transport.decimal_truncated`` -- and nothing else in the package -- to apply
``+ - * / // % **``. Everywhere else an arithmetic operator would mean the
viewer had started deriving a quantity instead of displaying one. The test
therefore walks every ``BinOp``, ``AugAssign`` and ``UnaryOp`` in both modules
and demands that its enclosing function be that one.

**Nothing compares a ``datetime`` or a ``Fraction``.** Membership comes from
``DashaRow``'s flags and from the core's own queries; the ``identical`` flag is
a tuple equality of ``(level, lords)`` keys. A comparison of two instants or
two exact offsets anywhere in this package would be a second, competing
definition of the same thing. The check is by *name*: every field of
``DashaPeriod``, ``DashaRow`` and ``VimshottariTimeline`` that holds a
``datetime`` or a ``Fraction`` is listed, and none of those names may appear as
an operand of a comparison or of an arithmetic operator.

The rest of the file checks the page: ``viewer.js`` is scanned textually for
the forbidden browser APIs of 13.3 (supplemental to the browser acceptance
script of 13.4, not a substitute for it), ``viewer.html`` for inline script,
inline style and ``on*`` attributes, and ``viewer.css`` for any selector that
could reach inside the chart container or match the renderer's own SVG
elements.
"""

import ast
import re
import sys
from pathlib import Path

import pytest

from render_helpers import REPO_ROOT

VIEWER_PACKAGE = REPO_ROOT / "src" / "vedic_chart" / "viewer"
STATIC_DIR = VIEWER_PACKAGE / "static"

PACKAGE_FILES = ("__init__.py", "__main__.py", "server.py", "transport.py")
STATIC_FILES = ("viewer.css", "viewer.html", "viewer.js")

#: Specification 3.4. ``dataclasses`` is on this list although 3.4's own
#: sentence for ``server.py`` omits it: 4.2 requires ``ViewerConfig`` to be a
#: frozen dataclass and that class lives in ``server.py``, so the omission is a
#: drafting gap rather than a prohibition.
SERVER_STDLIB = {
    "argparse",
    "dataclasses",
    "http",
    "importlib",
    "json",
    "re",
    "secrets",
    "socket",
    "socketserver",
    "sys",
    "threading",
    "traceback",
    "pathlib",
    "typing",
    "webbrowser",
}

TRANSPORT_STDLIB = {
    "dataclasses",
    "datetime",
    "fractions",
    "json",
    "re",
    "typing",
}

ALLOWED_STDLIB_BY_FILE = {
    "__init__.py": set(),
    "__main__.py": {"sys"},
    "server.py": SERVER_STDLIB,
    "transport.py": TRANSPORT_STDLIB,
}

#: Specification 3.4, "forbidden everywhere in the package".
FORBIDDEN_IMPORTS = (
    "swisseph",
    "timezonefinder",
    "sqlite3",
    "logging",
    "math",
    "time",
    "random",
    "os",
    "subprocess",
    "urllib",
    "requests",
    "ssl",
    "zoneinfo",
    "vedic_chart.astronomy",
    "vedic_chart.sidereal",
    "vedic_chart.ephemeris",
    "vedic_chart.vedic.divisions",
    "vedic_chart.chart",
    "vedic_chart.representation",
    "vedic_chart.render.north_indian",
    "vedic_chart.render.north_indian_geometry",
    "vedic_chart.location.offline.search",
    "vedic_chart.location.offline.db.connect",
    "vedic_chart.location.static_resolver",
    "vedic_chart.app.cli",
)

#: Module -> the exact project names each viewer module may import from it.
#: ``DashaRangeError`` is on the transport's list because 9.5 rule 2 requires
#: the restated instant formatter to raise exactly it.
PROJECT_IMPORTS = {
    "__init__.py": {},
    "__main__.py": {},
    "server.py": {
        # Layer 15 section 9 (C2): the server calls the exact-location entry
        # point and never the name-resolving one.
        "vedic_chart.app": {
            "ChartConfig",
            "ConfigurationError",
            "render_chart_and_dasha_at",
        },
        "vedic_chart.dasha": {"DashaRangeError", "dasha_rows"},
        # ``BirthChartRequest`` is built by the effective-input step from
        # Layer 1's own validated values and the record's label (15, 7.2).
        "vedic_chart.inputs.model": {
            "BirthChartRequest",
            "InvalidBirthDateError",
            "InvalidBirthTimeError",
            "InvalidPlaceQueryError",
        },
        # ``AmbiguousPlaceError`` is gone with the kind it mapped to: no name
        # is resolved on this path, so no request can be ambiguous (15, 7.3).
        "vedic_chart.location.model": {
            "InvalidCoordinateError",
            "PlaceNotFoundError",
        },
        "vedic_chart.location.offline.db": {"GeodataError"},
        "vedic_chart.location.offline.resolver": {"OfflineLocationResolver"},
        "vedic_chart.time.local_time": {
            "AmbiguousLocalTimeError",
            "InvalidTimezoneError",
            "NonexistentLocalTimeError",
        },
        "vedic_chart.viewer": {"transport"},
        "vedic_chart.viewer.transport": {
            "PlaceSelectionRequiredError",
            "StaleSchemaError",
            "TransportError",
        },
    },
    "transport.py": {
        "vedic_chart.app": {"LocatedChartAndDashaResult"},
        "vedic_chart.dasha": {
            "DashaRangeError",
            "DashaRow",
            "VimshottariTimeline",
            "YearConvention",
            "dasha_rows",
            "resolve_zone",
        },
        "vedic_chart.inputs.model": {"BirthChartRequest"},
        "vedic_chart.location.model": {"PlaceCandidate"},
        "vedic_chart.render": {"NorthIndianOptions"},
        "vedic_chart.vedic.grahas": {"Graha"},
    },
}

#: The one function permitted to apply an arithmetic operator (3.4).
ARITHMETIC_FUNCTION = "decimal_truncated"

#: Names that would mean a clock had been read. The viewer has no notion of
#: "now" and shows no "current period" marker (1, 8.3).
CLOCK_ATTRIBUTES = ("now", "utcnow", "today", "fromtimestamp", "monotonic")

#: Builtins the package may not call at all. ``re.compile`` is of course fine;
#: the list is of bare names, plus the two that would also be a breach as a
#: method (``value.round()``, ``value.float()``).
FORBIDDEN_CALLS = ("round", "float", "eval", "exec")
FORBIDDEN_METHOD_CALLS = ("round", "float")

#: Every ``datetime``- or ``Fraction``-valued field of the three core types.
#: None of these names may be an operand of a comparison or of an arithmetic
#: operator anywhere in the package.
EXACT_VALUE_ATTRIBUTES = frozenset(
    {
        "start_utc",
        "end_utc",
        "birth_utc",
        "moment_utc",
        "cycle_start_utc",
        "cycle_end_utc",
        "nominal_start",
        "nominal_end",
        "nominal_years",
        "elapsed_years",
        "balance_years",
        "elapsed_fraction",
        "remaining_fraction",
    }
)

#: Specification 13.3, verbatim.
FORBIDDEN_JS_TEXT = (
    "new Date",
    "Date.",
    "parseFloat",
    "Number(",
    "eval(",
    "innerHTML",
    "outerHTML =",
    "insertAdjacentHTML",
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "document.cookie",
)

_FETCH_CALL = re.compile(r"fetch\(\s*([^\s,)]+)")
#: Every start tag of a document, for the ``aria-controls`` scan below.
_START_TAG = re.compile(r"<[a-zA-Z][^>]*>", re.DOTALL)
_ON_ATTRIBUTE = re.compile(r"<[^>]*?\son[a-z]+\s*=", re.IGNORECASE)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_AT_RULE = re.compile(r"^@")
_CHART_DESCENDANT = re.compile(r"#chart\s*[>+~\s]\s*[^,{]")


# --- shared AST helpers (the style of tests/test_app_boundaries.py) --------


def imported_names(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    absolute = []
    relative = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                if module:
                    relative.append(module)
                relative.extend(alias.name for alias in node.names)
            else:
                absolute.append(module)
                absolute.extend(f"{module}.{alias.name}" for alias in node.names)
    return absolute, relative


def project_imports(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and not node.level:
            module = node.module or ""
            if module.startswith("vedic_chart"):
                found.setdefault(module, set()).update(
                    alias.name for alias in node.names
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("vedic_chart"):
                    found.setdefault(alias.name, set())
    return found


def module_tree(filename: str) -> ast.Module:
    return ast.parse((VIEWER_PACKAGE / filename).read_text(encoding="utf-8"))


def enclosing_functions(tree: ast.Module) -> dict:
    """Every node in the tree mapped to the name of the function holding it."""
    owner: dict = {}

    def walk(node, current):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            current = node.name
        for child in ast.iter_child_nodes(node):
            owner[child] = current
            walk(child, current)

    owner[tree] = None
    walk(tree, None)
    return owner


def operand_names(node: ast.AST):
    """Every attribute and bare name used anywhere under ``node``."""
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute):
            names.add(child.attr)
        elif isinstance(child, ast.Name):
            names.add(child.id)
    return names


# --- imports ---------------------------------------------------------------


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_no_viewer_module_imports_anything_forbidden(filename):
    absolute, _relative = imported_names(VIEWER_PACKAGE / filename)

    for name in absolute:
        lowered = name.lower()
        for forbidden in FORBIDDEN_IMPORTS:
            assert not (
                lowered == forbidden or lowered.startswith(forbidden + ".")
            ), f"{filename} imports {name}"


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_only_the_allowed_standard_library_modules_are_used(filename):
    absolute, _relative = imported_names(VIEWER_PACKAGE / filename)
    allowed = ALLOWED_STDLIB_BY_FILE[filename]

    for name in absolute:
        if not name or name.startswith("vedic_chart"):
            continue
        top = name.split(".")[0]
        assert top in sys.stdlib_module_names, (
            f"{filename} imports the third-party module {name}"
        )
        assert top in allowed, (
            f"{filename} imports the unlisted standard library module {name}"
        )


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_each_module_imports_only_the_project_names_it_may(filename):
    found = project_imports(VIEWER_PACKAGE / filename)
    allowed = PROJECT_IMPORTS[filename]

    for module, names in found.items():
        assert module in allowed, (
            f"{filename} imports the unlisted module {module}"
        )
        unexpected = names - allowed[module]
        assert not unexpected, f"{filename} imports {unexpected} from {module}"


def test_the_package_re_exports_through_relative_imports_only():
    absolute, relative = imported_names(VIEWER_PACKAGE / "__init__.py")

    assert absolute == []
    assert "server" in relative
    for name in ("ViewerConfig", "ViewerServer", "serve"):
        assert name in relative


def test_the_executable_boundary_is_the_documented_two_lines():
    _absolute, relative = imported_names(VIEWER_PACKAGE / "__main__.py")

    assert "server" in relative
    assert "main" in relative
    source = (VIEWER_PACKAGE / "__main__.py").read_text(encoding="utf-8")
    assert "sys.exit(main())" in source


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_no_viewer_module_reaches_past_the_dasha_package_surface(filename):
    """Layer 13 section 2: the daśā layer is consumed through what it publishes.

    ``vedic_chart.dasha.table.ABBREVIATIONS`` is the one thing the viewer would
    have liked from a submodule. It is restated in ``transport.py`` instead,
    with a parity test against the original, so that no module of this package
    names a daśā submodule at all.
    """
    absolute, _relative = imported_names(VIEWER_PACKAGE / filename)

    # ``imported_names`` spells an imported *name* the same way as a submodule
    # (``vedic_chart.dasha.DashaRow``), so the check is against the daśā
    # package's real module names, read off the filesystem rather than listed
    # here -- the same discipline tests/test_dasha_boundaries.py applies to the
    # app package.
    submodules = {
        path.stem
        for path in (REPO_ROOT / "src" / "vedic_chart" / "dasha").glob("*.py")
    }
    assert "table" in submodules

    for name in absolute:
        if not name.startswith("vedic_chart.dasha."):
            continue
        head = name[len("vedic_chart.dasha."):].split(".")[0]
        assert head not in submodules, (
            f"{filename} reaches past the dasha package surface: {name}"
        )

    for module in project_imports(VIEWER_PACKAGE / filename):
        assert not module.startswith("vedic_chart.dasha."), (
            f"{filename} imports the dasha submodule {module}"
        )


def test_the_abbreviations_are_defined_in_the_transport_not_imported():
    """The restatement is a module-level assignment, held to Layer 13 by a test.

    The parity assertion itself lives in ``tests/test_viewer_transport.py``,
    which may reach for the submodule because a test is not the package.
    """
    tree = module_tree("transport.py")

    assigned = {
        target.id
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (
            node.targets if isinstance(node, ast.Assign) else [node.target]
        )
        if isinstance(target, ast.Name)
    }
    assert "ABBREVIATIONS" in assigned

    for module, names in project_imports(VIEWER_PACKAGE / "transport.py").items():
        assert "ABBREVIATIONS" not in names, (
            f"transport.py imports ABBREVIATIONS from {module}"
        )


def test_no_private_layer_thirteen_name_is_imported():
    """Specification 3.2: the private helpers are restated, never imported."""
    for filename in PACKAGE_FILES:
        absolute, relative = imported_names(VIEWER_PACKAGE / filename)
        for name in absolute + relative:
            leaf = name.split(".")[-1]
            assert not leaf.startswith("_"), (
                f"{filename} imports the private name {name}"
            )


# --- the package shape -----------------------------------------------------


def test_the_package_modules_are_exactly_the_four_specified():
    modules = sorted(path.name for path in VIEWER_PACKAGE.glob("*.py"))

    assert modules == sorted(PACKAGE_FILES)
    assert len(PACKAGE_FILES) == 4


def test_the_static_files_are_exactly_the_three_specified():
    files = sorted(path.name for path in STATIC_DIR.iterdir() if path.is_file())

    assert files == sorted(STATIC_FILES)


def test_the_public_names_are_exactly_the_three_specified():
    import vedic_chart.viewer as package

    assert package.__all__ == ["ViewerConfig", "ViewerServer", "serve"]
    for name in package.__all__:
        assert hasattr(package, name)


def test_this_layer_added_no_dependency_and_no_console_script():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dependencies = text.split("dependencies = [")[1].split("]")[0]

    assert sorted(
        line.strip().strip('",')
        for line in dependencies.splitlines()
        if line.strip()
    ) == ["pyswisseph==2.10.3.2", "timezonefinder==8.2.0"]
    assert "[project.scripts]" not in text
    assert "console_scripts" not in text


def test_only_the_viewer_package_knows_about_the_viewer():
    """Layers 1 to 13 are unchanged: nothing below imports this layer."""
    source_root = REPO_ROOT / "src" / "vedic_chart"

    for path in source_root.rglob("*.py"):
        if VIEWER_PACKAGE in path.parents or path.parent == VIEWER_PACKAGE:
            continue
        absolute, _relative = imported_names(path)
        assert not [
            name for name in absolute if name.startswith("vedic_chart.viewer")
        ], f"{path} imports the viewer layer"


# --- arithmetic, comparisons and calls -------------------------------------


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_arithmetic_appears_only_inside_decimal_truncated(filename):
    tree = module_tree(filename)
    owner = enclosing_functions(tree)

    for node in ast.walk(tree):
        if isinstance(node, (ast.BinOp, ast.AugAssign, ast.UnaryOp)):
            if isinstance(node, ast.UnaryOp) and isinstance(
                node.op, (ast.Not, ast.Invert)
            ):
                continue
            assert owner.get(node) == ARITHMETIC_FUNCTION, (
                f"{filename} applies an arithmetic operator outside "
                f"{ARITHMETIC_FUNCTION} (line {node.lineno})"
            )


def test_decimal_truncated_uses_only_integer_operators():
    tree = module_tree("transport.py")
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == ARITHMETIC_FUNCTION
    )

    allowed = (ast.FloorDiv, ast.Mod, ast.Mult, ast.Pow)
    for node in ast.walk(function):
        if isinstance(node, ast.BinOp):
            assert isinstance(node.op, allowed), (
                f"{ARITHMETIC_FUNCTION} uses {type(node.op).__name__}"
            )
        assert not isinstance(node, ast.AugAssign)
        if isinstance(node, ast.UnaryOp):
            assert isinstance(node.op, (ast.Not, ast.Invert)), (
                f"{ARITHMETIC_FUNCTION} uses a unary sign"
            )


def test_decimal_truncated_is_called_only_with_the_balance_and_nine():
    """3.4: the one call site, with the one quantity and the literal 9."""
    calls = []
    for filename in PACKAGE_FILES:
        for node in ast.walk(module_tree(filename)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == ARITHMETIC_FUNCTION
            ):
                calls.append(node)

    assert len(calls) == 1
    call = calls[0]
    assert len(call.args) == 2
    assert isinstance(call.args[0], ast.Attribute)
    assert call.args[0].attr == "balance_years"
    assert isinstance(call.args[1], ast.Constant)
    assert call.args[1].value == 9


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_no_datetime_or_fraction_is_compared_or_computed_with(filename):
    tree = module_tree(filename)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Compare, ast.BinOp, ast.AugAssign)):
            continue
        used = operand_names(node) & EXACT_VALUE_ATTRIBUTES
        assert not used, (
            f"{filename} line {node.lineno} applies an operator to the exact "
            f"value(s) {sorted(used)}"
        )


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_no_viewer_module_rounds_or_converts_to_float(filename):
    tree = module_tree(filename)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in FORBIDDEN_CALLS, (
                    f"{filename} calls {function.id}()"
                )
            if isinstance(function, ast.Attribute):
                assert function.attr not in FORBIDDEN_METHOD_CALLS, (
                    f"{filename} calls a {function.attr} method"
                )


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_no_viewer_module_reads_a_clock(filename):
    tree = module_tree(filename)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in CLOCK_ATTRIBUTES, (
                f"{filename} calls {node.func.attr}()"
            )


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_no_viewer_module_opens_a_file_for_writing(filename):
    source = (VIEWER_PACKAGE / filename).read_text(encoding="utf-8")

    assert "open(" not in source.replace("webbrowser.open(", "")
    assert "ZoneInfo(" not in source, f"{filename} constructs a ZoneInfo"


def test_the_server_holds_the_engine_lock_around_the_pipeline_call_only():
    """2.1: the lock covers the calculation and the row extraction, no more.

    Layer 15 adds ``POST /api/places``, which is **not** under the lock: it
    touches the geodata database only, and there is still exactly one ``with
    ENGINE_LOCK`` in the module.
    """
    tree = module_tree("server.py")

    held = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.With)
        and any(
            isinstance(item.context_expr, ast.Name)
            and item.context_expr.id == "ENGINE_LOCK"
            for item in node.items
        )
    ]
    assert len(held) == 1

    inside = held[0].body
    called = {
        node.func.id
        for node in ast.walk(ast.Module(body=inside, type_ignores=[]))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert called == {"render_chart_and_dasha_at", "dasha_rows"}


def test_the_server_never_calls_send_response():
    """11.3 item 4: ``send_response`` would append Server and Date."""
    source = (VIEWER_PACKAGE / "server.py").read_text(encoding="utf-8")

    assert "send_response(" not in source
    assert "send_response_only(" in source
    assert "def send_error(" in source


# --- the page: viewer.js ---------------------------------------------------


def read_static(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("forbidden", FORBIDDEN_JS_TEXT)
def test_viewer_js_does_not_mention_the_forbidden_browser_apis(forbidden):
    """13.3, supplemental to the browser acceptance script of 13.4."""
    assert forbidden not in read_static("viewer.js")


def test_viewer_js_fetches_only_the_two_relative_endpoints():
    """11.4: relative paths only, and only the routes this server serves.

    Layer 15 section 5.2 adds ``/api/places`` to the page's vocabulary. The
    chart endpoint is required; the suggestions endpoint is permitted.
    """
    source = read_static("viewer.js")
    targets = _FETCH_CALL.findall(source)

    assert set(targets) <= {'"/api/chart"', '"/api/places"'}
    assert '"/api/chart"' in targets


def test_viewer_js_carries_the_acceptance_seam_behind_the_hash():
    """13.4: the hook exists only when the page was opened with #acceptance."""
    source = read_static("viewer.js")

    assert "__loadFixture" in source
    assert 'window.location.hash === "#acceptance"' in source
    assert source.index('window.location.hash === "#acceptance"') < source.index(
        "window.__loadFixture"
    )


def test_viewer_js_inserts_text_with_text_content():
    source = read_static("viewer.js")

    assert "textContent" in source
    assert "DOMParser" in source
    assert "image/svg+xml" in source


# --- the page: viewer.html -------------------------------------------------


def test_viewer_html_has_no_inline_script_or_style_and_no_event_attribute():
    source = read_static("viewer.html")

    for opening, closing in (("<script", "</script>"), ("<style", "</style>")):
        for match in re.finditer(re.escape(opening), source):
            end = source.index(">", match.start())
            body_end = source.find(closing, end)
            body = source[end + 1 : body_end] if body_end != -1 else ""
            assert body.strip() == "", f"{opening} carries an inline body"

    assert "<style" not in source
    assert _ON_ATTRIBUTE.search(source) is None


def test_viewer_html_carries_the_token_placeholder_and_the_three_assets():
    source = read_static("viewer.html")

    assert '<meta name="viewer-token" content="__VIEWER_TOKEN__">' in source
    assert 'href="viewer.css"' in source
    assert 'src="viewer.js"' in source


def test_aria_controls_appears_only_on_a_combobox():
    """Layer 14 8.2/13.3 as Layer 15 section 12 narrows the prohibition.

    D16's rule was that ``aria-controls`` must not appear on a treegrid row:
    the rows it would have pointed at are not always in the document. The
    combobox is the opposite case -- its listbox element is always present,
    empty when closed -- so exactly one occurrence is permitted there and
    nowhere else. The scan is structural: every occurrence must be inside a
    start tag that also carries ``role="combobox"``.
    """
    source = read_static("viewer.html")
    tags = [tag for tag in _START_TAG.findall(source) if "aria-controls" in tag]

    # No occurrence outside a start tag -- in text, in a comment, in an
    # attribute value -- which is what makes counting tags sufficient.
    assert sum(tag.count("aria-controls") for tag in tags) == source.count(
        "aria-controls"
    )
    assert len(tags) <= 1
    for tag in tags:
        assert 'role="combobox"' in tag, tag
    assert "aria-controls" not in read_static("viewer.js")


def test_viewer_html_declares_the_treegrid_and_the_live_regions():
    source = read_static("viewer.html")

    assert 'role="treegrid"' in source
    assert 'role="status"' in source
    assert 'role="alert"' in source
    assert 'id="chart"' in source
    assert source.count('autocomplete="off"') == 3
    assert "checked" not in source


# --- the page: viewer.css --------------------------------------------------


def css_selectors(source: str):
    without_comments = _CSS_COMMENT.sub("", source)
    selectors = []
    depth = 0
    buffer = []
    for character in without_comments:
        if character == "{":
            if depth == 0:
                selectors.append("".join(buffer).strip())
                buffer = []
            depth += 1
            continue
        if character == "}":
            depth -= 1
            buffer = []
            continue
        if depth == 0:
            buffer.append(character)
    return [
        one.strip()
        for group in selectors
        if group and not _CSS_AT_RULE.match(group)
        for one in group.split(",")
        if one.strip()
    ]


def test_no_viewer_css_rule_reaches_inside_the_chart_container():
    """7.2: the inserted SVG must render exactly as the standalone file."""
    source = read_static("viewer.css")

    assert _CHART_DESCENDANT.search(source) is None


def test_no_viewer_css_selector_is_a_bare_element_selector():
    """No rule of this file can match the renderer's own SVG content."""
    bare = []
    for selector in css_selectors(read_static("viewer.css")):
        for compound in re.split(r"[\s>+~]+", selector):
            if not compound:
                continue
            if compound.startswith((".", "#", ":", "[", "*")):
                continue
            if re.match(r"^[A-Za-z][A-Za-z0-9-]*$", compound):
                bare.append(selector)
                break
    assert bare == []


def test_every_viewer_css_class_carries_the_prefix():
    body = _CSS_COMMENT.sub("", read_static("viewer.css"))
    classes = set(re.findall(r"\.([A-Za-z][A-Za-z0-9_-]*)", body))

    assert classes
    assert all(name.startswith("v-") for name in sorted(classes)), sorted(
        name for name in classes if not name.startswith("v-")
    )
