"""Layer 10: renderers that turn a Layer 9 ``D1Chart`` into a drawing.

The package draws and nothing else. It reads a ``D1Chart``, never a
``BirthChart`` and never the ephemeris; it recalculates no longitude, house,
rashi, nakshatra, pada, speed or retrograde flag; and it formats degrees only
through Layer 9's truncating ``dms()``. Semantic data (the ``D1Chart``),
geometry (``north_indian_geometry``) and style (the private ``RenderStyle``)
stay separate objects, composed by :func:`render_north_indian_svg`; Layer 19's
South Indian renderer keeps the same separation in its own two modules.

Five names are public: the North Indian renderer and its option set, the South
Indian renderer and its option set (Layer 19), and ``overlay_block`` (Layer
20), the presentation helper that formats one chart's placement facts and slot
coordinates for the viewer's transit overlay.
"""

from .north_indian import NorthIndianOptions, render_north_indian_svg
from .overlay import overlay_block
from .south_indian import SouthIndianOptions, render_south_indian_svg

__all__ = [
    "NorthIndianOptions",
    "SouthIndianOptions",
    "overlay_block",
    "render_north_indian_svg",
    "render_south_indian_svg",
]
