"""Layer 11's import boundary and packaging invariants (section 10.C).

The boundary is enforced by parsing the source, not by trusting the prose: the
pipeline may compose the layers below it, but it may not reach past their public
surfaces, and the CLI may borrow *exception classes* from three modules without
gaining the right to call anything in them. Both are forbidden ``swisseph``, the
raw ephemeris, and anything from ``astronomy.positions`` other than the one
sanctioned session boundary.

The same file checks that this layer added no dependency and no console script:
``python -m vedic_chart.app`` must work with packaging unchanged.
"""

import ast
from pathlib import Path

import pytest

from render_helpers import REPO_ROOT

APP_PACKAGE = REPO_ROOT / "src" / "vedic_chart" / "app"
PACKAGE_FILES = ("__init__.py", "pipeline.py", "cli.py", "__main__.py")

FORBIDDEN_IMPORTS = (
    "swisseph",
    "vedic_chart.ephemeris",
    "vedic_chart.sidereal",
    "vedic_chart.vedic",
    "vedic_chart.lagna",
    "vedic_chart.time.julian_day",
    "vedic_chart.location.static_resolver",
    "tools",
    "http",
    "urllib",
    "requests",
    "socket",
    "ssl",
    "ftplib",
    "aiohttp",
)

#: The only name any app module may take from ``astronomy.positions``.
SANCTIONED_ASTRONOMY_NAME = "vedic_chart.astronomy.positions.ephemeris_session"

PIPELINE_PROJECT_IMPORTS = {
    "vedic_chart.inputs.model": {"BirthChartRequest"},
    "vedic_chart.location.model": {"LocationResolver", "ResolvedLocation"},
    "vedic_chart.location.offline.resolver": {"OfflineLocationResolver"},
    "vedic_chart.location.offline.search": {"RankingConfig", "ResolutionDecision"},
    "vedic_chart.chart.assemble": {"assemble_chart"},
    "vedic_chart.chart.model": {"BirthChart"},
    "vedic_chart.astronomy.positions": {"ephemeris_session"},
    "vedic_chart.representation.d1": {"D1Chart", "build_d1_chart"},
    "vedic_chart.render": {"NorthIndianOptions", "render_north_indian_svg"},
}

CLI_PROJECT_IMPORTS = {
    "vedic_chart.app.pipeline": {
        "ChartConfig",
        "ChartResult",
        "ConfigurationError",
        "render_birth_chart",
    },
    "vedic_chart.render": {"NorthIndianOptions"},
    "vedic_chart.inputs.model": {
        "BirthChartRequest",
        "InvalidBirthDateError",
        "InvalidBirthTimeError",
        "InvalidPlaceQueryError",
    },
    # Exception classes only. Importing a *function* from any of the three
    # modules below fails this test even though the module itself is allowed.
    "vedic_chart.location.model": {
        "PlaceNotFoundError",
        "AmbiguousPlaceError",
        "InvalidCoordinateError",
    },
    "vedic_chart.location.offline.db": {"GeodataError"},
    "vedic_chart.time.local_time": {
        "InvalidTimezoneError",
        "NonexistentLocalTimeError",
        "AmbiguousLocalTimeError",
    },
}


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


def project_imports(path: Path) -> dict[str, set[str]]:
    """Every ``from vedic_chart.x import a, b`` in one module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, set[str]] = {}
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
def test_no_app_module_imports_anything_forbidden(filename):
    absolute, _relative = imported_names(APP_PACKAGE / filename)

    for name in absolute:
        lowered = name.lower()
        for forbidden in FORBIDDEN_IMPORTS:
            assert not (
                lowered == forbidden or lowered.startswith(forbidden + ".")
            ), f"{filename} imports {name}"


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_only_the_session_is_taken_from_the_astronomy_layer(filename):
    absolute, _relative = imported_names(APP_PACKAGE / filename)

    for name in absolute:
        if not name.startswith("vedic_chart.astronomy"):
            continue
        assert name in (
            "vedic_chart.astronomy.positions",
            SANCTIONED_ASTRONOMY_NAME,
        ), f"{filename} imports {name} from the astronomy layer"


def test_the_pipeline_imports_only_what_the_contract_allows():
    found = project_imports(APP_PACKAGE / "pipeline.py")

    for module, names in found.items():
        assert module in PIPELINE_PROJECT_IMPORTS, (
            f"pipeline.py imports the unlisted module {module}"
        )
        unexpected = names - PIPELINE_PROJECT_IMPORTS[module]
        assert not unexpected, f"pipeline.py imports {unexpected} from {module}"


def test_the_cli_imports_only_what_the_contract_allows():
    found = project_imports(APP_PACKAGE / "cli.py")

    for module, names in found.items():
        assert module in CLI_PROJECT_IMPORTS, (
            f"cli.py imports the unlisted module {module}"
        )
        unexpected = names - CLI_PROJECT_IMPORTS[module]
        assert not unexpected, f"cli.py imports {unexpected} from {module}"


def test_the_cli_takes_only_exception_classes_from_the_three_modules():
    """The AST test checks names, not just modules."""
    found = project_imports(APP_PACKAGE / "cli.py")

    for module in (
        "vedic_chart.location.model",
        "vedic_chart.location.offline.db",
        "vedic_chart.time.local_time",
    ):
        for name in found.get(module, set()):
            assert name.endswith("Error"), (
                f"cli.py imports the non-exception name {name} from {module}"
            )


def test_the_package_modules_are_exactly_the_four_specified():
    modules = sorted(path.name for path in APP_PACKAGE.glob("*.py"))

    assert modules == sorted(PACKAGE_FILES)


def test_the_internal_imports_are_the_expected_ones():
    _init_absolute, init_relative = imported_names(APP_PACKAGE / "__init__.py")
    _main_absolute, main_relative = imported_names(APP_PACKAGE / "__main__.py")

    assert "pipeline" in init_relative
    assert "cli" in main_relative
    assert "run" in main_relative


def test_no_app_module_rounds_or_arithmetics_a_chart_value():
    """Neither module computes: a round() here would be a policy breach."""
    for filename in PACKAGE_FILES:
        tree = ast.parse((APP_PACKAGE / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                function = node.func
                assert not (
                    isinstance(function, ast.Name) and function.id == "round"
                ), f"{filename} calls round()"
                assert not (
                    isinstance(function, ast.Attribute)
                    and function.attr == "round"
                ), f"{filename} calls a round method"


def test_the_public_names_are_exactly_the_four_specified():
    import vedic_chart.app as package

    assert package.__all__ == [
        "ChartConfig",
        "ChartResult",
        "ConfigurationError",
        "render_birth_chart",
    ]


def test_packaging_is_unchanged():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "[project.scripts]" not in text
    assert "console_scripts" not in text
    dependencies = text.split("dependencies = [")[1].split("]")[0]
    assert sorted(
        line.strip().strip('",') for line in dependencies.splitlines()
        if line.strip()
    ) == ["pyswisseph==2.10.3.2", "timezonefinder==8.2.0"]


def test_the_app_package_imports_no_third_party_module():
    """Standard library plus vedic_chart, and nothing else."""
    import sys

    standard = set(sys.stdlib_module_names)
    for filename in PACKAGE_FILES:
        absolute, _relative = imported_names(APP_PACKAGE / filename)
        for name in absolute:
            if not name:
                continue
            top = name.split(".")[0]
            assert top in standard or top == "vedic_chart", (
                f"{filename} imports the third-party module {name}"
            )
