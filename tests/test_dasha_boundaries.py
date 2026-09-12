"""The dasha package's import boundary and packaging invariants.

Layer 12 section 3, as widened by Layer 13 section 2. The boundary is enforced
by parsing the source, not by trusting the prose. A dasha is arithmetic on two
numbers, so the three **core** modules are allowed seven standard library
modules, the two frozen Layer 7 constants modules, and -- in the adapter alone
-- the chart model it takes those two numbers from. Everything else is
forbidden by name: the ephemeris and its session, the sidereal and lagna
layers, the representation, the renderer and the CLI.

Layer 13 adds a fourth module, ``table``, and exactly one privilege:
``zoneinfo``, which it needs because presenting an instant means choosing a
zone. That privilege is checked to be **its alone** -- a core module that
imported ``zoneinfo`` would mean the arithmetic had acquired opinions about
local time -- and the table is otherwise held to the same rules, including the
two that are claims about the whole package rather than about any one
function: nothing calls ``round()`` (rule 12 -- the single documented floor,
and the table's integer truncations, are the only places precision is lost),
and nothing reads a clock, so no result can depend on when it was computed.
"""

import ast
import sys
from pathlib import Path

import pytest

from render_helpers import REPO_ROOT

DASHA_PACKAGE = REPO_ROOT / "src" / "vedic_chart" / "dasha"
APP_PACKAGE = REPO_ROOT / "src" / "vedic_chart" / "app"
CORE_FILES = ("__init__.py", "vimshottari.py", "from_chart.py")
PACKAGE_FILES = CORE_FILES + ("table.py",)

#: The standard library modules Layer 12 section 3 allows the core modules.
ALLOWED_STDLIB = {
    "dataclasses",
    "datetime",
    "enum",
    "fractions",
    "math",
    "types",
    "typing",
}

#: Layer 13 section 2: the presentation module's own list. ``zoneinfo`` appears
#: here and in no other module of the package.
TABLE_STDLIB = {"dataclasses", "datetime", "fractions", "typing", "zoneinfo"}

ALLOWED_STDLIB_BY_FILE = {
    "__init__.py": ALLOWED_STDLIB,
    "vimshottari.py": ALLOWED_STDLIB,
    "from_chart.py": ALLOWED_STDLIB,
    "table.py": TABLE_STDLIB,
}

#: The four names Layer 13 adds to the package surface.
TABLE_NAMES = ("DashaRow", "dasha_rows", "render_dasha_text", "resolve_zone")

FORBIDDEN_IMPORTS = (
    "swisseph",
    "vedic_chart.ephemeris",
    "vedic_chart.astronomy",
    "vedic_chart.sidereal",
    "vedic_chart.lagna",
    "vedic_chart.time",
    "vedic_chart.location",
    "vedic_chart.inputs",
    "vedic_chart.representation",
    "vedic_chart.render",
    "vedic_chart.app",
    "sqlite3",
    "random",
    "time",
    "os",
    "http",
    "urllib",
    "requests",
    "socket",
)

#: Module -> the exact names each dasha module may import from it.
PROJECT_IMPORTS = {
    "__init__.py": {},
    "vimshottari.py": {
        "vedic_chart.vedic.divisions": {"NAKSHATRA_NAMES"},
        "vedic_chart.vedic.grahas": {"Graha"},
    },
    "from_chart.py": {
        "vedic_chart.vedic.grahas": {"Graha"},
        "vedic_chart.chart.model": {"BirthChart"},
    },
    "table.py": {
        "vedic_chart.dasha.vimshottari": {
            "DashaPeriod",
            "DashaRangeError",
            "VimshottariTimeline",
            "YearConvention",
        },
        "vedic_chart.vedic.grahas": {"Graha"},
    },
}

#: Names that would mean the layer read a clock.
CLOCK_ATTRIBUTES = ("now", "utcnow", "today", "fromtimestamp", "monotonic")


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


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_no_dasha_module_imports_anything_forbidden(filename):
    absolute, _relative = imported_names(DASHA_PACKAGE / filename)

    for name in absolute:
        lowered = name.lower()
        for forbidden in FORBIDDEN_IMPORTS:
            assert not (
                lowered == forbidden or lowered.startswith(forbidden + ".")
            ), f"{filename} imports {name}"


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_only_the_allowed_standard_library_modules_are_used(filename):
    absolute, _relative = imported_names(DASHA_PACKAGE / filename)
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


@pytest.mark.parametrize("filename", CORE_FILES)
def test_no_core_module_knows_about_time_zones(filename):
    """The privilege is the table's alone (Layer 13 section 2)."""
    absolute, relative = imported_names(DASHA_PACKAGE / filename)

    assert not any(
        name.split(".")[0] == "zoneinfo" for name in absolute + relative
    ), f"{filename} imports zoneinfo"


def test_the_table_is_the_only_module_that_imports_zoneinfo():
    absolute, _relative = imported_names(DASHA_PACKAGE / "table.py")

    assert "zoneinfo" in absolute
    assert {"zoneinfo.ZoneInfo", "zoneinfo.ZoneInfoNotFoundError"} <= set(
        absolute
    )


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_each_module_imports_only_the_project_names_it_may(filename):
    found = project_imports(DASHA_PACKAGE / filename)
    allowed = PROJECT_IMPORTS[filename]

    for module, names in found.items():
        assert module in allowed, (
            f"{filename} imports the unlisted module {module}"
        )
        unexpected = names - allowed[module]
        assert not unexpected, f"{filename} imports {unexpected} from {module}"


def test_the_core_takes_only_the_names_it_is_allowed_from_layer_seven():
    """``classify`` is the tests' oracle, never the core's implementation."""
    found = project_imports(DASHA_PACKAGE / "vimshottari.py")

    assert found == {
        "vedic_chart.vedic.divisions": {"NAKSHATRA_NAMES"},
        "vedic_chart.vedic.grahas": {"Graha"},
    }
    assert "classify" not in found["vedic_chart.vedic.divisions"]


def test_only_the_adapter_knows_about_the_chart_model():
    for filename in ("__init__.py", "vimshottari.py", "table.py"):
        found = project_imports(DASHA_PACKAGE / filename)
        assert "vedic_chart.chart.model" not in found
        assert not any(name.startswith("vedic_chart.chart") for name in found)

    assert "vedic_chart.chart.model" in project_imports(
        DASHA_PACKAGE / "from_chart.py"
    )


def test_the_package_modules_are_exactly_the_four_specified():
    """Three of arithmetic and one of presentation; Layer 13 adds no other."""
    modules = sorted(path.name for path in DASHA_PACKAGE.glob("*.py"))

    assert modules == sorted(PACKAGE_FILES)
    assert len(PACKAGE_FILES) == 4


def test_the_package_re_exports_through_relative_imports_only():
    absolute, relative = imported_names(DASHA_PACKAGE / "__init__.py")

    assert absolute == []
    assert "vimshottari" in relative
    assert "from_chart" in relative
    assert "table" in relative
    assert "build_vimshottari" in relative
    assert "vimshottari_from_chart" in relative
    for name in TABLE_NAMES:
        assert name in relative


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_no_dasha_module_rounds_anything(filename):
    """Rule 12: the single documented floor is the only quantization."""
    tree = ast.parse((DASHA_PACKAGE / filename).read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            assert not (
                isinstance(function, ast.Name) and function.id == "round"
            ), f"{filename} calls round()"
            assert not (
                isinstance(function, ast.Attribute) and function.attr == "round"
            ), f"{filename} calls a round method"


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_no_dasha_module_reads_a_clock(filename):
    """No implicit "now": every instant is derived from the birth anchor."""
    source = (DASHA_PACKAGE / filename).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in CLOCK_ATTRIBUTES, (
                f"{filename} calls {node.func.attr}()"
            )


def test_the_public_names_are_exactly_the_specified_surface():
    import vedic_chart.dasha as package

    assert package.__all__ == [
        "CYCLE_YEARS",
        "DashaPeriod",
        "DashaRangeError",
        "DashaRow",
        "LORD_SEQUENCE",
        "LORD_YEARS",
        "MICROSECONDS_PER_DAY",
        "NAKSHATRA_COUNT",
        "VimshottariTimeline",
        "YearConvention",
        "build_vimshottari",
        "dasha_rows",
        "render_dasha_text",
        "resolve_zone",
        "vimshottari_from_chart",
    ]
    for name in package.__all__:
        assert hasattr(package, name)
    for name in TABLE_NAMES:
        assert name in package.__all__


def test_this_layer_added_no_dependency():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dependencies = text.split("dependencies = [")[1].split("]")[0]

    assert sorted(
        line.strip().strip('",')
        for line in dependencies.splitlines()
        if line.strip()
    ) == ["pyswisseph==2.10.3.2", "timezonefinder==8.2.0"]
    assert "[project.scripts]" not in text


def test_only_the_app_package_knows_about_this_layer():
    """Layers 1-10 are unchanged; the app package is the single consumer.

    Layer 13 section 2 makes ``vedic_chart.app`` the one place outside this
    package that may import it, and only through the package surface -- never a
    submodule, which would be reaching past what the package chose to publish.
    """
    source_root = REPO_ROOT / "src" / "vedic_chart"

    for path in source_root.rglob("*.py"):
        if DASHA_PACKAGE in path.parents:
            continue
        absolute, _relative = imported_names(path)
        importers = [
            name for name in absolute if name.startswith("vedic_chart.dasha")
        ]
        if APP_PACKAGE in path.parents:
            # ``imported_names`` spells an imported *name* the same way as a
            # submodule, so the check is against the module names themselves.
            submodules = {name.removesuffix(".py") for name in PACKAGE_FILES}
            for name in importers:
                head = name[len("vedic_chart.dasha."):].split(".")[0]
                assert head not in submodules, (
                    f"{path} reaches past the dasha package surface: {name}"
                )
            continue
        assert not importers, f"{path} imports the dasha layer"
