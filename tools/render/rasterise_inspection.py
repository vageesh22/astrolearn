"""Rasterise the Layer 10 inspection set and run the embedding check (section 10.D / 10.A4).

Validation tooling only. This script is NOT a project dependency and is never
imported by the package: it needs Playwright with its bundled Chromium
(``pip install playwright && playwright install chromium``) and, for the pixel
crops, Pillow. It records exactly how the images under
``docs/render_inspection/png/`` were produced so that the evidence is
reproducible; the SVG inputs come from ``render_inspection_set.py``.

    python tools/render/rasterise_inspection.py SVG_DIR PNG_DIR [--widths 600 1000]
        [--font-family Arial] [--suffix _arial] [--worst] [--a11y]

* Each ``*.svg`` in SVG_DIR is placed inline in an empty HTML page (white
  background, zero margin), given ``width``/``height`` for the requested total
  width (height from the viewBox aspect), and screenshotted at device scale
  factor 1 -- one CSS pixel is one image pixel, no supersampling. Output name:
  ``<case><suffix>_<width>.png``.
* ``--font-family FAMILY`` replaces the renderer's declared stack
  (``"DejaVu Sans", Arial, Helvetica, sans-serif``) by FAMILY in a temporary
  copy of every SVG before rasterising. This is how the second-font evidence
  was made; the font Chromium actually used is reported per run via the CDP
  ``CSS.getPlatformFontsForNode`` call (in the validation environment
  ``Arial`` and ``Helvetica`` both resolved to Liberation Sans).
* ``--worst`` additionally builds ``typography_side_widest.svg`` from
  ``nine_house3.svg`` by replacing every ``deg`` text with ``29°59′`` and every
  abbreviation with ``Mo``. **This is a typography-only image. It is not a
  chart and it is never a test fixture.** It exists solely to judge how far
  the widest stacked row a side triangle can hold reaches towards the
  triangle's slanted edges and its numeral; its planet identities are
  fictitious and no real chart is altered to produce it. Section 10.D
  therefore keeps it apart from the semantic cases: it is written to
  ``SVG_DIR/../typography/`` and rasterised to ``PNG_DIR/../typography/``
  using the same ``--widths``, ``--font-family`` and ``--suffix`` options.
* ``--a11y`` loads every ``*.html`` in SVG_DIR and prints, per embedded SVG,
  whether its accessible name equals its own ``<title>`` and its accessible
  description its own ``<desc>``, plus the document's id set and duplicates.

Zoom crops (``zoom_*.png``) were made with Pillow from the PNGs above:
``Image.open(png).crop(box).resize(size, Image.NEAREST)`` for pixel-level
legibility judgement (NEAREST so that no smoothing is introduced).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DECLARED_STACK = 'font-family="&quot;DejaVu Sans&quot;, Arial, Helvetica, sans-serif"'


#: Where the typography-only image lives, relative to the SVG and PNG
#: directories: beside them, never among the section 10.D chart renders.
TYPOGRAPHY_DIRECTORY = "typography"
TYPOGRAPHY_NAME = "typography_side_widest.svg"


def typography_dir(directory: Path) -> Path:
    return directory.parent / TYPOGRAPHY_DIRECTORY


def build_worst(svg_dir: Path) -> Path:
    """The widest-glyph image of section 10.D -- typography only, no chart."""
    source = (svg_dir / "nine_house3.svg").read_text(encoding="utf-8")
    text = re.sub(r'(<text class="deg"[^>]*>)[^<]*(</text>)', r"\g<1>29°59′\2", source)
    text = re.sub(
        r'(<text class="abbr"[^>]*>)(Su|Mo|Me|Ve|Ma|Ju|Sa|Ra|Ke)(</text>)', r"\1Mo\3", text
    )
    target = typography_dir(svg_dir) / TYPOGRAPHY_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("svg_dir", type=Path)
    parser.add_argument("png_dir", type=Path)
    parser.add_argument("--widths", type=int, nargs="+", default=[600, 1000])
    parser.add_argument("--font-family", default=None)
    parser.add_argument("--suffix", default="")
    parser.add_argument("--worst", action="store_true")
    parser.add_argument("--a11y", action="store_true")
    args = parser.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover - validation tooling
        print("Playwright is required: pip install playwright && playwright install chromium")
        return 2

    if args.worst:
        print("built", build_worst(args.svg_dir))
    args.png_dir.mkdir(parents=True, exist_ok=True)

    def rasterise(browser, sources, png_dir, report_font):
        """Screenshot every SVG in ``sources`` at each requested width."""
        if not sources:
            return
        png_dir.mkdir(parents=True, exist_ok=True)
        for svg in sources:
            text = svg.read_text(encoding="utf-8")
            if args.font_family:
                assert DECLARED_STACK in text, svg
                text = text.replace(DECLARED_STACK, f'font-family="{args.font_family}"')
            match = re.search(r'viewBox="0 0 (\d+) (\d+)"', text)
            view_w, view_h = int(match.group(1)), int(match.group(2))
            for width in args.widths:
                height = round(width * view_h / view_w)
                page = browser.new_page(
                    viewport={"width": width, "height": height}, device_scale_factor=1
                )
                body = text.replace("<svg ", f'<svg width="{width}" height="{height}" ', 1)
                page.set_content(
                    f'<!doctype html><html><body style="margin:0;background:#fff">{body}'
                    "</body></html>"
                )
                page.wait_for_timeout(50)
                if report_font and svg == sources[0] and width == args.widths[0]:
                    cdp = page.context.new_cdp_session(page)
                    cdp.send("DOM.enable")
                    cdp.send("CSS.enable")
                    root = cdp.send("DOM.getDocument")["root"]["nodeId"]
                    node = cdp.send(
                        "DOM.querySelector", {"nodeId": root, "selector": "text.abbr"}
                    )["nodeId"]
                    fonts = cdp.send("CSS.getPlatformFontsForNode", {"nodeId": node})["fonts"]
                    print("platform font used:", [f["familyName"] for f in fonts])
                target = png_dir / f"{svg.stem}{args.suffix}_{width}.png"
                page.screenshot(path=str(target), full_page=True)
                page.close()
                print("wrote", target)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        rasterise(
            browser, sorted(args.svg_dir.glob("*.svg")), args.png_dir, True
        )
        # The typography-only image is kept in its own directory on both
        # sides, so no inspector can mistake it for a chart render.
        rasterise(
            browser,
            sorted(typography_dir(args.svg_dir).glob("*.svg")),
            typography_dir(args.png_dir),
            False,
        )

        if args.a11y:
            for html in sorted(args.svg_dir.glob("*.html")):
                page = browser.new_page()
                page.set_content(html.read_text(encoding="utf-8"))
                ids = page.evaluate(
                    "Array.from(document.querySelectorAll('[id]')).map(e => e.id)"
                )
                own = page.evaluate(
                    "Array.from(document.querySelectorAll('svg')).map(s => ({"
                    "title: s.querySelector('title').textContent,"
                    "desc: s.querySelector('desc').textContent}))"
                )
                cdp = page.context.new_cdp_session(page)
                cdp.send("Accessibility.enable")
                nodes = cdp.send("Accessibility.getFullAXTree")["nodes"]
                images = [n for n in nodes if n.get("role", {}).get("value") == "image"]
                duplicates = sorted({i for i in ids if ids.count(i) > 1})
                print(f"{html.name}: ids={ids} duplicates={duplicates}")
                for index, (node, expected) in enumerate(zip(images, own), start=1):
                    name = node.get("name", {}).get("value", "")
                    desc = node.get("description", {}).get("value", "")
                    print(
                        f"  svg #{index}: name is own title: {name == expected['title']};"
                        f" description is own desc: {desc == expected['desc']}"
                    )
                page.close()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
