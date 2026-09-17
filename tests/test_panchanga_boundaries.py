"""Layer 16's import boundary and packaging invariants (specification 3, 5, 6).

Enforced by parsing the source, not by trusting the prose, in the style
``tests/test_dasha_boundaries.py`` established and the viewer's boundary tests
continued. Specification section 3 gives a table of exactly what each of the
four modules may import; this file is that table, executable.

Three rules are about the package as a whole rather than about any one module,
and they are the reason the file matters:

**The astronomy boundary is still one module wide.** ``swisseph`` is imported
by ``src/vedic_chart/ephemeris/swiss_ephemeris.py`` and by nothing else
anywhere under ``src/``. Layer 16 reaches the sky through one added accessor,
``calc_sunrise_hindu``, and the sunrise module is the only thing in the package
that names it.

**Nothing rounds and nothing reads a clock.** A panchanga is a function of an
instant, two longitudes and a place; a ``round()`` would lose precision the
frozen layers were careful to keep, and a ``now()`` would make a result depend
on when it was computed rather than on what it was computed for.

**Nothing below imports this layer.** Layers 1 to 15 are untouched. The dasha
layer has two sanctioned consumers, ``app`` and ``viewer``; this layer has
none at all, which is the strongest form of "the engine did not change".
"""

import ast
import sys
from pathlib import Path

import pytest

from render_helpers import REPO_ROOT

PANCHANGA_PACKAGE = REPO_ROOT / "src" / "vedic_chart" / "panchanga"
SOURCE_ROOT = REPO_ROOT / "src" / "vedic_chart"
EPHEMERIS_MODULE = SOURCE_ROOT / "ephemeris" / "swiss_ephemeris.py"

PACKAGE_FILES = ("__init__.py", "elements.py", "sunrise.py", "compute.py")

#: Specification section 3's table, standard library column. ``compute.py``'s
#: cell is empty in the document; it is read as an omission rather than as a
#: prohibition -- section 5 asks for frozen dataclasses and enums, which cannot
#: be written without them -- and the three modules it actually uses are pinned
#: separately below, including the absence of ``zoneinfo``.
ALLOWED_STDLIB_BY_FILE = {
    "__init__.py": set(),
    "elements.py": {"dataclasses", "enum", "math", "typing"},
    "sunrise.py": {
        "dataclasses", "datetime", "enum", "math", "typing", "zoneinfo",
    },
    "compute.py": {"dataclasses", "datetime", "enum", "typing"},
}

#: What each module actually imports from the project, which may be a proper
#: subset of what section 3's table allows. Importing *less* than the table
#: permits is always inside the boundary; the subset test above is the
#: contract, this one records where the code is tighter and why.
ACTUAL_PROJECT_IMPORTS = {
    "__init__.py": {},
    "elements.py": {
        "vedic_chart.vedic.divisions": {
            "NAKSHATRA_SPAN",
            "DivisionalPlacement",
            "classify",
            "normalize_longitude",
        },
        "vedic_chart.vedic.grahas": {"Graha"},
    },
    "sunrise.py": {
        "vedic_chart.time.julian_day": {
            "SECONDS_PER_DAY",
            "UNIX_EPOCH_JD",
            "julian_day_ut",
        },
        "vedic_chart.time.local_time": {"InvalidTimezoneError"},
        "vedic_chart.ephemeris.swiss_ephemeris": {"calc_sunrise_hindu"},
    },
    # ``julian_day_ut`` is allowed here by the table but not taken: the UTC
    # normalisation of section 2.4 and the Julian Day that goes with it are one
    # rule, and it lives once, in ``sunrise.utc_instant``, which this module
    # already reaches for ``resolve_zone`` and ``validate_coordinates``.
    "compute.py": {
        "vedic_chart.chart.model": {"BirthChart"},
        "vedic_chart.vedic.grahas": {"Graha"},
        "vedic_chart.sidereal.positions": {"calculate_sidereal_positions"},
        "vedic_chart.astronomy.positions": {"Body"},
    },
}

#: What each module actually imports, which is a subset of what it may.
EXPECTED_STDLIB_BY_FILE = {
    "__init__.py": set(),
    "elements.py": {"dataclasses", "enum", "typing"},
    "sunrise.py": {"dataclasses", "datetime", "math", "typing", "zoneinfo"},
    # ``timezone`` is imported for the ``instant_utc.tzinfo`` guard of section
    # 5; the normalisation itself still happens once, in ``sunrise``.
    "compute.py": {"dataclasses", "datetime", "enum"},
}

#: Specification section 3: forbidden everywhere in the package.
FORBIDDEN_IMPORTS = (
    "swisseph",
    "vedic_chart.lagna",
    "vedic_chart.location",
    "vedic_chart.inputs",
    "vedic_chart.representation",
    "vedic_chart.render",
    "vedic_chart.dasha",
    "vedic_chart.app",
    "vedic_chart.viewer",
    "sqlite3",
    "random",
    "time",
    "os",
    "http",
    "urllib",
    "requests",
    "socket",
)

#: Specification section 3's table, project column: module -> the exact names
#: each panchanga module may import from it.
PROJECT_IMPORTS = {
    "__init__.py": {},
    "elements.py": {
        "vedic_chart.vedic.divisions": {
            "NAKSHATRA_SPAN",
            "DivisionalPlacement",
            "classify",
            "normalize_longitude",
        },
        "vedic_chart.vedic.grahas": {"Graha"},
    },
    "sunrise.py": {
        "vedic_chart.time.julian_day": {
            "SECONDS_PER_DAY",
            "UNIX_EPOCH_JD",
            "julian_day_ut",
        },
        "vedic_chart.time.local_time": {"InvalidTimezoneError"},
        "vedic_chart.ephemeris.swiss_ephemeris": {"calc_sunrise_hindu"},
    },
    "compute.py": {
        "vedic_chart.chart.model": {"BirthChart"},
        "vedic_chart.vedic.grahas": {"Graha"},
        "vedic_chart.sidereal.positions": {"calculate_sidereal_positions"},
        "vedic_chart.astronomy.positions": {"Body"},
        "vedic_chart.time.julian_day": {"julian_day_ut"},
    },
}

#: Names that would mean the layer read a clock.
CLOCK_ATTRIBUTES = ("now", "utcnow", "today", "fromtimestamp", "monotonic")

#: Specification section 5's public surface, sorted.
PUBLIC_SURFACE = [
    "CALCULATION_CONVENTION",
    "InvalidTimezoneError",
    "KARANA_FIXED_NAMES",
    "KARANA_REPEATING_NAMES",
    "Karana",
    "KaranaKind",
    "LocationProvenance",
    "LongitudeSource",
    "Nakshatra",
    "NityaYoga",
    "Paksha",
    "Panchanga",
    "PanchangaLocation",
    "SUNRISE_CONVENTION",
    "SunriseUnavailable",
    "SunriseWindow",
    "TITHI_NAMES",
    "Tithi",
    "TithiHalf",
    "VARA_LORDS",
    "VARA_NAMES",
    "Vara",
    "YOGA_NAMES",
    "calculate_panchanga",
    "find_sunrise_window",
    "panchanga_from_chart",
]


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


def stdlib_tops(path: Path) -> set:
    absolute, _relative = imported_names(path)
    return {
        name.split(".")[0]
        for name in absolute
        if name and not name.startswith("vedic_chart")
    }


# --- the four modules ------------------------------------------------------


def test_the_package_modules_are_exactly_the_four_specified():
    modules = sorted(path.name for path in PANCHANGA_PACKAGE.glob("*.py"))

    assert modules == sorted(PACKAGE_FILES)
    assert len(PACKAGE_FILES) == 4


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_no_panchanga_module_imports_anything_forbidden(filename):
    absolute, _relative = imported_names(PANCHANGA_PACKAGE / filename)

    for name in absolute:
        lowered = name.lower()
        for forbidden in FORBIDDEN_IMPORTS:
            assert not (
                lowered == forbidden or lowered.startswith(forbidden + ".")
            ), f"{filename} imports {name}"


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_only_the_allowed_standard_library_modules_are_used(filename):
    absolute, _relative = imported_names(PANCHANGA_PACKAGE / filename)
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
def test_each_module_uses_exactly_the_standard_library_it_is_pinned_to(
    filename,
):
    assert stdlib_tops(PANCHANGA_PACKAGE / filename) == (
        EXPECTED_STDLIB_BY_FILE[filename]
    )


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_each_module_imports_only_the_project_names_it_may(filename):
    found = project_imports(PANCHANGA_PACKAGE / filename)
    allowed = PROJECT_IMPORTS[filename]

    for module, names in found.items():
        assert module in allowed, (
            f"{filename} imports the unlisted module {module}"
        )
        unexpected = names - allowed[module]
        assert not unexpected, f"{filename} imports {unexpected} from {module}"


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_each_module_imports_exactly_the_names_it_is_pinned_to(filename):
    """Not just a subset of the table: pinned, so a new import is visible."""
    found = project_imports(PANCHANGA_PACKAGE / filename)

    assert found == ACTUAL_PROJECT_IMPORTS[filename]

    # And what is pinned is within what section 3 allows.
    for module, names in found.items():
        assert names <= PROJECT_IMPORTS[filename][module], (filename, module)


def test_the_utc_normalisation_rule_lives_in_exactly_one_place():
    """Section 2.4 is one rule, so ``astimezone`` appears once in the package.

    ``compute`` imports ``timezone`` to *check* the stored tzinfo, which is a
    different thing from performing the conversion.
    """
    users = []

    for filename in PACKAGE_FILES:
        source = (PANCHANGA_PACKAGE / filename).read_text(encoding="utf-8")
        if "astimezone(timezone.utc)" in source:
            users.append(filename)

    assert users == ["sunrise.py"]

    import vedic_chart.panchanga.compute as compute_module
    import vedic_chart.panchanga.sunrise as sunrise_module

    assert compute_module.utc_instant is sunrise_module.utc_instant


# --- the divisions of labour inside the package ----------------------------


def test_only_the_sunrise_module_knows_about_time_zones():
    for filename in ("__init__.py", "elements.py", "compute.py"):
        absolute, relative = imported_names(PANCHANGA_PACKAGE / filename)
        assert not any(
            name.split(".")[0] == "zoneinfo" for name in absolute + relative
        ), f"{filename} imports zoneinfo"

    absolute, _relative = imported_names(PANCHANGA_PACKAGE / "sunrise.py")
    assert "zoneinfo" in absolute


def test_only_the_sunrise_module_reaches_the_astronomy_boundary():
    for filename in ("__init__.py", "elements.py", "compute.py"):
        found = project_imports(PANCHANGA_PACKAGE / filename)
        assert "vedic_chart.ephemeris.swiss_ephemeris" not in found
        assert not any(
            name.startswith("vedic_chart.ephemeris") for name in found
        )

    assert project_imports(PANCHANGA_PACKAGE / "sunrise.py")[
        "vedic_chart.ephemeris.swiss_ephemeris"
    ] == {"calc_sunrise_hindu"}


def test_only_the_composition_module_knows_about_the_chart_model():
    for filename in ("__init__.py", "elements.py", "sunrise.py"):
        found = project_imports(PANCHANGA_PACKAGE / filename)
        assert not any(name.startswith("vedic_chart.chart") for name in found)

    assert "vedic_chart.chart.model" in project_imports(
        PANCHANGA_PACKAGE / "compute.py"
    )


def test_only_the_elements_module_knows_about_the_frozen_divisions():
    """``classify`` is reached through ``elements`` or not at all."""
    for filename in ("__init__.py", "sunrise.py", "compute.py"):
        found = project_imports(PANCHANGA_PACKAGE / filename)
        assert not any(name.startswith("vedic_chart.vedic.divisions") for name in found)

    assert "classify" in project_imports(PANCHANGA_PACKAGE / "elements.py")[
        "vedic_chart.vedic.divisions"
    ]


def test_the_elements_module_is_pure_arithmetic():
    """No instant, no zone, no place: two longitudes in, four elements out."""
    absolute, _relative = imported_names(PANCHANGA_PACKAGE / "elements.py")

    for name in absolute:
        top = name.split(".")[0]
        assert top not in ("datetime", "zoneinfo"), (
            f"elements.py imports {name}"
        )


def test_the_package_re_exports_through_relative_imports_only():
    absolute, relative = imported_names(PANCHANGA_PACKAGE / "__init__.py")

    assert absolute == []
    for module in ("elements", "sunrise", "compute"):
        assert module in relative
    for name in PUBLIC_SURFACE:
        assert name in relative


# --- no rounding, no clock -------------------------------------------------


@pytest.mark.parametrize("filename", PACKAGE_FILES)
def test_no_panchanga_module_rounds_anything(filename):
    tree = ast.parse((PANCHANGA_PACKAGE / filename).read_text(encoding="utf-8"))

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
def test_no_panchanga_module_reads_a_clock(filename):
    source = (PANCHANGA_PACKAGE / filename).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in CLOCK_ATTRIBUTES, (
                f"{filename} calls {node.func.attr}()"
            )
        if isinstance(node, ast.Attribute):
            assert node.attr not in CLOCK_ATTRIBUTES, (
                f"{filename} names {node.attr}"
            )


# --- the astronomy boundary is still one module wide -----------------------


def test_swisseph_is_imported_by_exactly_one_module_in_the_whole_source():
    importers = []

    for path in SOURCE_ROOT.rglob("*.py"):
        absolute, relative = imported_names(path)
        if any(
            name == "swisseph" or name.startswith("swisseph.")
            for name in absolute + relative
        ):
            importers.append(path)

    assert importers == [EPHEMERIS_MODULE], [str(p) for p in importers]


def test_the_layer_five_accessor_is_imported_by_the_sunrise_module_alone():
    importers = []

    for path in SOURCE_ROOT.rglob("*.py"):
        if path == EPHEMERIS_MODULE:
            continue
        found = project_imports(path)
        for module, names in found.items():
            if "calc_sunrise_hindu" in names:
                importers.append(path)

    assert importers == [PANCHANGA_PACKAGE / "sunrise.py"], [
        str(p) for p in importers
    ]


def test_the_probing_constants_are_the_specified_ones():
    """Section 3.2's constants, and MAX_PROBES derived rather than chosen."""
    from vedic_chart.panchanga import sunrise as module

    assert module.SEARCH_SPAN_DAYS == 2.0
    assert module.SEARCH_STEP_DAYS == 0.5
    assert module.MAX_CONSECUTIVE_GAP_DAYS == 2.0
    assert module.MAX_PROBES == int(
        (module.SEARCH_SPAN_DAYS + module.MAX_CONSECUTIVE_GAP_DAYS)
        / module.SEARCH_STEP_DAYS
    ) + 1
    assert module.MAX_PROBES == 9


def test_the_progress_and_bound_checks_survive_optimised_python():
    """They must be ``if``/``raise``: ``python -O`` strips every ``assert``.

    An assert here would mean that under ``-O`` a misbehaving library hangs the
    process instead of raising. The check is by parsing: the walk's three
    guards -- the probe bound, the progress requirement and the backtrack
    limit -- must all be ``Raise`` nodes, and the function must contain no
    ``Assert`` at all.
    """
    tree = ast.parse(
        (PANCHANGA_PACKAGE / "sunrise.py").read_text(encoding="utf-8")
    )

    probe_function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_probe_forward"
    )

    raised = [
        node
        for node in ast.walk(probe_function)
        if isinstance(node, ast.Raise)
    ]
    asserted = [
        node
        for node in ast.walk(probe_function)
        if isinstance(node, ast.Assert)
    ]

    assert len(raised) == 3, (
        "the bound, progress and backtrack checks must all three raise"
    )
    assert asserted == [], "an assert here would vanish under python -O"
    assert all(
        isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
        and node.exc.func.id == "RuntimeError"
        for node in raised
    )


def test_the_layer_five_accessor_uses_the_specified_flags():
    """897, disc centre, no refraction, geocentric, 0 m, 0.0 pressure and temp.

    The flag value is checked against the library's own constants rather than
    against the literal, and the deliberately unused bits of specification 2.3
    are checked to be absent from the module's source.
    """
    import swisseph as swe

    from vedic_chart.ephemeris.swiss_ephemeris import RISE_HINDU_FLAGS

    assert RISE_HINDU_FLAGS == swe.CALC_RISE | swe.BIT_HINDU_RISING
    assert RISE_HINDU_FLAGS == 897
    assert swe.BIT_HINDU_RISING == 896

    source = EPHEMERIS_MODULE.read_text(encoding="utf-8")
    assert "BIT_FORCE_SLOW_METHOD" not in source
    assert "BIT_DISC_BOTTOM" not in source
    assert "BIT_FIXED_DISC_SIZE" not in source


def test_the_accessor_passes_the_place_in_the_librarys_own_order():
    """``(longitude, latitude, 0.0)``: the library's order is the reverse."""
    import inspect

    from vedic_chart.ephemeris.swiss_ephemeris import calc_sunrise_hindu

    source = inspect.getsource(calc_sunrise_hindu)

    assert "(longitude, latitude, 0.0)" in source
    assert "calc_planet_position(julian_day_ut, SUN)" in source


# --- nothing below this layer knows it exists ------------------------------


def test_no_module_outside_the_package_imports_it():
    """Layers 1 to 15 are unchanged; this layer has no consumers at all."""
    for path in SOURCE_ROOT.rglob("*.py"):
        if PANCHANGA_PACKAGE in path.parents:
            continue
        absolute, _relative = imported_names(path)
        assert not [
            name for name in absolute if name.startswith("vedic_chart.panchanga")
        ], f"{path} imports the panchanga layer"


def test_the_frozen_modules_this_layer_reads_were_not_changed_to_suit_it():
    """The accessor is the only addition; nothing else gained a name for us.

    A weak check by construction -- it cannot see an edit it does not look
    for -- but it pins the two things this layer could have been tempted to
    change: the divisional classifier and the ayanamsha accessor.
    """
    divisions = (SOURCE_ROOT / "vedic" / "divisions.py").read_text(
        encoding="utf-8"
    )

    assert "tithi" not in divisions.lower()
    assert "karana" not in divisions.lower()
    assert "yoga" not in divisions.lower()
    assert "vara" not in divisions.lower()
    assert "panchanga" not in divisions.lower()

    # Layer 5 gained one function and one constant and lost nothing.
    tree = ast.parse(EPHEMERIS_MODULE.read_text(encoding="utf-8"))
    functions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]

    assert functions == [
        "init_ephemeris",
        "close_ephemeris",
        "get_version",
        "calc_planet_position",
        "get_ayanamsa_lahiri",
        "calc_ascendant_tropical",
        "calc_sunrise_hindu",
    ]

    ephemeris = EPHEMERIS_MODULE.read_text(encoding="utf-8")
    assert "SIDM_LAHIRI" in ephemeris
    assert "get_ayanamsa_ex_ut(julian_day_ut, 0)" in ephemeris


# --- the public surface ----------------------------------------------------


def test_the_public_names_are_exactly_the_specified_surface():
    import vedic_chart.panchanga as package

    assert package.__all__ == PUBLIC_SURFACE
    assert package.__all__ == sorted(package.__all__)
    for name in package.__all__:
        assert hasattr(package, name), name


def test_every_public_type_is_a_frozen_dataclass_or_an_enum():
    import dataclasses
    from enum import Enum

    import vedic_chart.panchanga as package

    dataclass_names = (
        "Tithi", "Nakshatra", "NityaYoga", "Karana", "Vara", "SunriseWindow",
        "SunriseUnavailable", "PanchangaLocation", "Panchanga",
    )
    enum_names = ("Paksha", "KaranaKind", "TithiHalf", "LocationProvenance",
                  "LongitudeSource")

    for name in dataclass_names:
        value = getattr(package, name)
        assert dataclasses.is_dataclass(value), name
        assert value.__dataclass_params__.frozen, name

    for name in enum_names:
        assert issubclass(getattr(package, name), Enum), name

    assert set(dataclass_names) | set(enum_names) <= set(package.__all__)


def test_the_error_is_layer_threes_and_not_a_new_one():
    import vedic_chart.panchanga as package
    from vedic_chart.time.local_time import InvalidTimezoneError

    assert package.InvalidTimezoneError is InvalidTimezoneError
    assert issubclass(InvalidTimezoneError, ValueError)


def test_the_two_convention_strings_name_what_they_should():
    import vedic_chart.panchanga as package

    calculation = package.CALCULATION_CONVENTION
    sunrise = package.SUNRISE_CONVENTION

    assert isinstance(calculation, str) and isinstance(sunrise, str)
    for fragment in ("Lahiri", "sidereal", "tithi", "karana", "yoga",
                     "nakshatra", "half-open", "rounding", "epsilon"):
        assert fragment in calculation, fragment
    for fragment in ("CALC_RISE", "BIT_HINDU_RISING", "897", "refraction",
                     "0 m", "SWIEPH"):
        assert fragment in sunrise, fragment


def test_the_name_tables_are_the_specified_lengths():
    import vedic_chart.panchanga as package

    assert len(package.TITHI_NAMES) == 30
    assert len(package.YOGA_NAMES) == 27
    assert len(package.KARANA_REPEATING_NAMES) == 7
    assert len(package.KARANA_FIXED_NAMES) == 4
    assert len(package.VARA_NAMES) == 7
    assert len(package.VARA_LORDS) == 7


# --- packaging -------------------------------------------------------------


def test_this_layer_added_no_dependency():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dependencies = text.split("dependencies = [")[1].split("]")[0]

    assert sorted(
        line.strip().strip('",')
        for line in dependencies.splitlines()
        if line.strip()
    ) == ["pyswisseph==2.10.3.2", "timezonefinder==8.2.0"]
    assert "[project.scripts]" not in text
