"""Layer 10: renderers that turn a Layer 9 ``D1Chart`` into a drawing.

The package draws and nothing else. It reads a ``D1Chart``, never a
``BirthChart`` and never the ephemeris; it recalculates no longitude, house,
rashi, nakshatra, pada, speed or retrograde flag; and it formats degrees only
through Layer 9's truncating ``dms()``. Semantic data (the ``D1Chart``),
geometry (``north_indian_geometry``) and style (the private ``RenderStyle``)
stay separate objects, composed by :func:`render_north_indian_svg`; Layer 19's
South Indian renderer keeps the same separation in its own two modules.

Only four names are public: the North Indian renderer and its option set, and
the South Indian renderer and its option set (Layer 19).
"""

from .north_indian import NorthIndianOptions, render_north_indian_svg
from .south_indian import SouthIndianOptions, render_south_indian_svg

__all__ = [
    "NorthIndianOptions",
    "SouthIndianOptions",
    "render_north_indian_svg",
    "render_south_indian_svg",
]
