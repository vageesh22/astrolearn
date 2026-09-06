"""Write the section 10.D rendered-inspection set for Layer 10.

Validation tooling, not part of the package and not imported by it. It renders
the cases the specification asks a human to look at -- with degrees enabled
except for the one case that exists to show a side triangle *without* them --
and writes them as SVG files into a directory given on the command line. It also writes the two HTML documents of section 10.A4, in which
two charts are embedded inline in one page with distinct ``id_prefix`` values,
for the Chromium half of the embedding check. Rasterising and judging them is
the inspector's job; this script only produces the material and prints what it
wrote.

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
NO_DEGREES = NorthIndianOptions(show_degrees=False)
DEGREES_CAPTION = NorthIndianOptions(show_degrees=True, caption=True)
DEGREES_NODES = NorthIndianOptions(show_degrees=True, mark_node_retrograde=True)


def inspection_set() -> list[tuple[str, object, NorthIndianOptions]]:
    """The cases of section 10.D, in the order they are listed."""
    return [
        ("jalandhar_nocaption", helpers.jalandhar_d1, DEGREES),
        ("jalandhar_caption", helpers.jalandhar_d1, DEGREES_CAPTION),
        ("bharatpur_caption", helpers.bharatpur_d1, DEGREES_CAPTION),
        ("nine_house1", lambda: helpers.nine_in_house_d1(1), DEGREES),
        ("nine_house2", lambda: helpers.nine_in_house_d1(2), DEGREES),
        ("nine_house3", lambda: helpers.nine_in_house_d1(3), DEGREES),
        # U-8: the third of the one-/two-/three-occupant side triangles of
        # section 10.D item 5, stacked at 0.022 -- the Jalandhar and Bharatpur
        # charts already cover one occupant (0.032) and two (0.028).
        ("side_three", lambda: helpers.count_in_house_d1(3, 3), DEGREES),
        # The same crowded side triangle with degrees off: nine single
        # abbreviation rows at 0.024 and no overflow.
        ("side_nodegrees", lambda: helpers.nine_in_house_d1(3), NO_DEGREES),
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
        (
            # Both crowding pressures at once: a side triangle overflowed to
            # its floor with a legend block, under a wrapped long caption.
            "long_caption_overflow",
            lambda: helpers.nine_in_house_long_caption_d1(
                3, helpers.LONG_NAME_WITH_SPACES
            ),
            DEGREES_CAPTION,
        ),
    ]


#: The section 10.A4 pairs: two different charts, and the same chart twice.
EMBEDDING_DOCUMENTS = {
    "embed_two_different": (
        ("jalandhar_caption", helpers.jalandhar_d1, DEGREES_CAPTION),
        ("nine_house1", lambda: helpers.nine_in_house_d1(1), DEGREES),
    ),
    "embed_two_identical": (
        ("jalandhar_caption", helpers.jalandhar_d1, DEGREES_CAPTION),
        ("jalandhar_caption", helpers.jalandhar_d1, DEGREES_CAPTION),
    ),
}

PREFIXES = ("chart-1", "chart-2")


def with_prefix(options: NorthIndianOptions, prefix: str) -> NorthIndianOptions:
    return NorthIndianOptions(
        show_degrees=options.show_degrees,
        mark_node_retrograde=options.mark_node_retrograde,
        caption=options.caption,
        width=options.width,
        id_prefix=prefix,
    )


def embedding_document(name: str) -> str:
    """Two charts inline in one HTML body, each with its own id prefix."""
    parts = [
        "<!doctype html>",
        '<html lang="en">',
        '<head><meta charset="utf-8">',
        f"<title>{name}</title></head>",
        "<body>",
    ]
    for index, (case, build, options) in enumerate(EMBEDDING_DOCUMENTS[name]):
        if index:
            parts.append("<hr>")
        parts.append(f"<!-- {case} as {PREFIXES[index]} -->")
        parts.append(
            render_north_indian_svg(
                build(), with_prefix(options, PREFIXES[index])
            ).rstrip("\n")
        )
    parts.extend(["</body>", "</html>", ""])
    return "\n".join(parts)


def write_set(output_directory: Path) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, build, options in inspection_set():
        svg = render_north_indian_svg(build(), options)
        path = output_directory / f"{name}.svg"
        path.write_text(svg, encoding="utf-8")
        written.append(path)
    for name in EMBEDDING_DOCUMENTS:
        path = output_directory / f"{name}.html"
        path.write_text(embedding_document(name), encoding="utf-8")
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
