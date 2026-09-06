"""Write the section 10.D rendered-inspection set for Layer 10.

Validation tooling, not part of the package and not imported by it. It renders
the eleven cases the specification asks a human to look at, every one of them
with degrees enabled, and writes them as SVG files into a directory given on the
command line. Rasterising and judging them is the inspector's job; this script
only produces the material and prints what it wrote.

    python tools/render/render_inspection_set.py docs/render_inspection/svg

The chart builders are the test suite's, imported from ``tests/`` rather than
copied, so an inspected drawing and an asserted drawing can never drift apart.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import render_helpers as helpers  # noqa: E402
from vedic_chart.render import (  # noqa: E402
    NorthIndianOptions,
    render_north_indian_svg,
)

DEGREES = NorthIndianOptions(show_degrees=True)
DEGREES_CAPTION = NorthIndianOptions(show_degrees=True, caption=True)
DEGREES_NODES = NorthIndianOptions(show_degrees=True, mark_node_retrograde=True)


def inspection_set() -> list[tuple[str, object, NorthIndianOptions]]:
    """The eleven cases of section 10.D, in the order they are listed."""
    return [
        ("jalandhar_nocaption", helpers.jalandhar_d1, DEGREES),
        ("jalandhar_caption", helpers.jalandhar_d1, DEGREES_CAPTION),
        ("bharatpur_caption", helpers.bharatpur_d1, DEGREES_CAPTION),
        ("nine_house1", lambda: helpers.nine_in_house_d1(1), DEGREES),
        ("nine_house2", lambda: helpers.nine_in_house_d1(2), DEGREES),
        ("nine_house3", lambda: helpers.nine_in_house_d1(3), DEGREES),
        ("all_retrograde", helpers.all_retrograde_d1, DEGREES),
        ("all_retrograde_nodes_marked", helpers.all_retrograde_d1, DEGREES_NODES),
        (
            "long_caption_spaces",
            lambda: helpers.long_name_d1(helpers.LONG_NAME_WITH_SPACES),
            DEGREES_CAPTION,
        ),
        (
            "long_caption_nospaces",
            lambda: helpers.long_name_d1(helpers.LONG_NAME_NO_SPACES),
            DEGREES_CAPTION,
        ),
        ("two_overflow_houses", helpers.split_overflow_d1, DEGREES),
    ]


def write_set(output_directory: Path) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, build, options in inspection_set():
        svg = render_north_indian_svg(build(), options)
        path = output_directory / f"{name}.svg"
        path.write_text(svg, encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "usage: render_inspection_set.py <output-directory>",
            file=sys.stderr,
        )
        return 2
    for path in write_set(Path(argv[1])):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
