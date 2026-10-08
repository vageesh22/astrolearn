"""Golden documents for Layer 19's South Indian renderer (spec section 9.1).

The exact bytes for the two anchored charts in all four option combinations are
pinned in ``tests/fixtures/render_south/``. Regenerating them is deliberately
awkward: set ``RENDER_GOLDEN_UPDATE=1`` and run this module once. Without it a
difference is a failure, and a missing golden file is a failure too. The North
Indian goldens live in their own directory and are never written from here.
"""

import os
import xml.etree.ElementTree as ET

import pytest

from render_helpers import SOUTH_GOLDEN_DIR, case_chart
from vedic_chart.render import SouthIndianOptions, render_south_indian_svg

UPDATE_ENVIRONMENT_VARIABLE = "RENDER_GOLDEN_UPDATE"

OPTION_COMBINATIONS = {
    "caption_degrees": SouthIndianOptions(caption=True, show_degrees=True),
    "caption_nodegrees": SouthIndianOptions(caption=True, show_degrees=False),
    "nocaption_degrees": SouthIndianOptions(caption=False, show_degrees=True),
    "nocaption_nodegrees": SouthIndianOptions(caption=False, show_degrees=False),
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
    return SOUTH_GOLDEN_DIR / f"{name}.svg"


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


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_golden_files_match_exactly(name):
    chart_name, _, combination = name.partition("_")
    svg = render_south_indian_svg(
        case_chart(chart_name), OPTION_COMBINATIONS[combination]
    )

    compare_with_golden(name, svg)


def test_the_golden_set_is_exactly_the_eight_documented_files():
    if updating():
        pytest.skip("the set is being regenerated")
    stored = sorted(path.name for path in SOUTH_GOLDEN_DIR.glob("*.svg"))

    assert stored == sorted(f"{name}.svg" for name in GOLDEN_NAMES)


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_every_golden_file_is_well_formed_and_utf8(name):
    if updating():
        pytest.skip("the set is being regenerated")
    text = golden_path(name).read_text(encoding="utf-8")

    ET.fromstring(text)
    assert text.endswith("\n")
    assert "°" in text or "nodegrees" in name
