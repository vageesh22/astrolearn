"""Layer 12's import boundary and packaging invariants (section 3).

The boundary is enforced by parsing the source, not by trusting the prose. A
dasha is arithmetic on two numbers, so the package is allowed seven standard
library modules, the two frozen Layer 7 constants modules, and -- in the
adapter alone -- the chart model it takes those two numbers from. Everything
else is forbidden by name: the ephemeris and its session, the sidereal and
lagna layers, the representation, the renderer, the CLI, and ``zoneinfo``,
whose presence would mean this layer had opinions about local time.

Two further properties are checked here because they are claims about the
whole package rather than about any one function: nothing calls ``round()``
(rule 12 -- the single documented floor is the only place precision is lost),
and nothing reads a clock, so no result can depend on when it was computed.
"""

import ast
import sys
from pathlib import Path

import pytest

from render_helpers import REPO_ROOT

DASHA_PACKAGE = REPO_ROOT / "src" / "vedic_chart" / "dasha"
PACKAGE_FILES = ("__init__.py", "vimshottari.py", "from_chart.py")

#: The standard library modules section 3 allows the package.
ALLOWED_STDLIB = {
    "dataclasses",
    "datetime",
    "enum",
    "fractions",
    "math",
    "types",
    "typing",
}

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
    "zoneinfo",
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
def test_only_the_seven_allowed_standard_library_modules_are_used(filename):
    absolute, _relative = imported_names(DASHA_PACKAGE / filename)

    for name in absolute:
        if not name or name.startswith("vedic_chart"):
            continue
        top = name.split(".")[0]
        assert top in sys.stdlib_module_names, (
            f"{filename} imports the third-party module {name}"
        )
        assert top in ALLOWED_STDLIB, (
            f"{filename} imports the unlisted standard library module {name}"
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
    for filename in ("__init__.py", "vimshottari.py"):
        found = project_imports(DASHA_PACKAGE / filename)
        assert "vedic_chart.chart.model" not in found
        assert not any(name.startswith("vedic_chart.chart") for name in found)

    assert "vedic_chart.chart.model" in project_imports(
        DASHA_PACKAGE / "from_chart.py"
    )


def test_the_package_modules_are_exactly_the_three_specified():
    modules = sorted(path.name for path in DASHA_PACKAGE.glob("*.py"))

    assert modules == sorted(PACKAGE_FILES)


def test_the_package_re_exports_through_relative_imports_only():
    absolute, relative = imported_names(DASHA_PACKAGE / "__init__.py")

    assert absolute == []
    assert "vimshottari" in relative
    assert "from_chart" in relative
    assert "build_vimshottari" in relative
    assert "vimshottari_from_chart" in relative


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
        "LORD_SEQUENCE",
        "LORD_YEARS",
        "MICROSECONDS_PER_DAY",
        "NAKSHATRA_COUNT",
        "VimshottariTimeline",
        "YearConvention",
        "build_vimshottari",
        "vimshottari_from_chart",
    ]
    for name in package.__all__:
        assert hasattr(package, name)


def test_this_layer_added_no_dependency():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dependencies = text.split("dependencies = [")[1].split("]")[0]

    assert sorted(
        line.strip().strip('",')
        for line in dependencies.splitlines()
        if line.strip()
    ) == ["pyswisseph==2.10.3.2", "timezonefinder==8.2.0"]
    assert "[project.scripts]" not in text


def test_the_layers_below_do_not_know_about_this_one():
    """Nothing outside the package imports it: Layers 1-11 are unchanged."""
    source_root = REPO_ROOT / "src" / "vedic_chart"

    for path in source_root.rglob("*.py"):
        if DASHA_PACKAGE in path.parents:
            continue
        absolute, _relative = imported_names(path)
        assert not any(
            name.startswith("vedic_chart.dasha") for name in absolute
        ), f"{path} imports the dasha layer"
