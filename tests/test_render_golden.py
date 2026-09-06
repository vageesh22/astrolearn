"""Tests for Layer 10's deterministic serialization (section 10.C).

Two claims. First, the renderer is a pure function of chart and options: the
same inputs produce byte-identical output, with no timestamp, generated
identifier, dictionary-order artefact or environment value anywhere in the
document. Second, the exact bytes for the two anchored charts in all four
option combinations are pinned in ``tests/fixtures/render/`` so that any change
of coordinate, attribute order or rounding shows up as a diff rather than as a
silent redesign.

Regenerating the golden files is deliberately awkward: set
``RENDER_GOLDEN_UPDATE=1`` and run the suite once. Without it a difference is a
failure, and a missing golden file is a failure too -- never a quiet pass.
"""

import os
import xml.etree.ElementTree as ET

import pytest

from render_helpers import (
    CASE_NAMES,
    GOLDEN_DIR,
    case_chart,
    case_options,
)
from vedic_chart.render import NorthIndianOptions, render_north_indian_svg

UPDATE_ENVIRONMENT_VARIABLE = "RENDER_GOLDEN_UPDATE"

OPTION_COMBINATIONS = {
    "caption_degrees": NorthIndianOptions(caption=True, show_degrees=True),
    "caption_nodegrees": NorthIndianOptions(caption=True, show_degrees=False),
    "nocaption_degrees": NorthIndianOptions(caption=False, show_degrees=True),
    "nocaption_nodegrees": NorthIndianOptions(caption=False, show_degrees=False),
}
GOLDEN_CHARTS = ("jalandhar", "bharatpur")
GOLDEN_NAMES = tuple(
    f"{chart}_{combination}"
    for chart in GOLDEN_CHARTS
    for combination in OPTION_COMBINATIONS
)


def updating() -> bool:
    return os.environ.get(UPDATE_ENVIRONMENT_VARIABLE) == "1"


def golden_path(name: str):
    return GOLDEN_DIR / f"{name}.svg"


def compare_with_golden(name: str, svg: str) -> None:
    """Compare against the stored bytes, or rewrite them when asked to."""
    path = golden_path(name)
    if updating():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg, encoding="utf-8")
    assert path.exists(), (
        f"golden file {path} is missing; regenerate the set with "
        f"{UPDATE_ENVIRONMENT_VARIABLE}=1"
    )
    assert path.read_text(encoding="utf-8") == svg, (
        f"rendered output differs from {path}; if the change is intended, "
        f"regenerate with {UPDATE_ENVIRONMENT_VARIABLE}=1 and review the diff"
    )


@pytest.mark.parametrize("name", CASE_NAMES)
def test_two_renders_of_one_chart_are_byte_identical(name):
    chart = case_chart(name)
    options = case_options(name)

    assert render_north_indian_svg(chart, options) == render_north_indian_svg(
        chart, options
    )


def test_rebuilding_the_chart_does_not_change_the_bytes():
    """Determinism survives a fresh build of an equal representation."""
    from render_helpers import synthetic_d1

    first = render_north_indian_svg(synthetic_d1(5))
    second = render_north_indian_svg(synthetic_d1(5))

    assert first == second


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_document_carries_no_environment_dependent_content(name):
    svg = render_north_indian_svg(case_chart(name), case_options(name))
    root = ET.fromstring(svg)

    identifiers = [
        element.get("id") for element in root.iter() if element.get("id")
    ]
    assert identifiers == ["title", "desc"]
    assert "<!--" not in svg
    for forbidden in ("/home/", "/Users/", "C:\\", "file://", ".venv"):
        assert forbidden not in svg


@pytest.mark.parametrize("name", CASE_NAMES)
def test_every_coordinate_is_written_with_two_decimals(name):
    root = ET.fromstring(
        render_north_indian_svg(case_chart(name), case_options(name))
    )

    numeric_attributes = (
        "x", "y", "x1", "y1", "x2", "y2", "width", "height", "font-size",
        "stroke-width",
    )
    for element in root.iter():
        if element.tag.endswith("}svg"):
            continue
        for attribute in numeric_attributes:
            value = element.get(attribute)
            if value is None:
                continue
            assert "." in value and len(value.split(".")[1]) == 2, (
                element.tag, attribute, value
            )


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_golden_files_match_exactly(name):
    chart_name, _, combination = name.partition("_")
    svg = render_north_indian_svg(
        case_chart(chart_name), OPTION_COMBINATIONS[combination]
    )

    compare_with_golden(name, svg)


def test_the_golden_set_is_exactly_the_eight_documented_files():
    if updating():
        pytest.skip("the set is being regenerated")
    stored = sorted(path.name for path in GOLDEN_DIR.glob("*.svg"))

    assert stored == sorted(f"{name}.svg" for name in GOLDEN_NAMES)


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_every_golden_file_is_well_formed_and_utf8(name):
    if updating():
        pytest.skip("the set is being regenerated")
    text = golden_path(name).read_text(encoding="utf-8")

    ET.fromstring(text)
    assert text.endswith("\n")
    assert "°" in text or "nodegrees" in name
