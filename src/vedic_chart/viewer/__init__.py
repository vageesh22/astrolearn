"""Layer 14: a local, browser-based viewer for the D1 chart and the daśā.

A person enters a birth -- date, local wall time, place query -- and a daśā year
convention; the browser shows the existing North Indian D1 SVG and the
Vimshottari timeline, nine Mahādaśās expanding into nine Antardaśās each and
those into nine Pratyantardaśās. Everything on the page comes from one call to
the Layer 13 combined API, ``vedic_chart.app.render_chart_and_dasha``, over one
resolved ``BirthChart``.

This package is a **consumer** of Layers 1--13 and changes none of them. It
adds no astronomy, no astrology and no recalculation: it resolves nothing, it
computes no boundary, no fraction, no membership and no zone offset, and the
browser arranges strings. The one presentation formatting it performs is the
truncated balance decimal of specification section 9.5, in
``transport.decimal_truncated`` and nowhere else.

    from vedic_chart.viewer import ViewerConfig, serve

    raise SystemExit(serve(ViewerConfig("data/geodata.sqlite", "ephe")))

From the source checkout the command is::

    PYTHONPATH=src python -m vedic_chart.viewer \\
        --geodata data/geodata.sqlite --ephemeris ephe

``pyproject.toml``'s ``pythonpath = ["src"]`` applies to pytest only and the
project is not installed into its virtual environment, so the prefix is
required -- for this command and for ``python -m vedic_chart.app`` alike.

The server binds ``127.0.0.1`` and nothing else, writes no file, keeps no
birth beyond one request, and reads no clock: the viewer has no notion of
"now" and shows no "current period" marker.

Three names are public. ``ViewerConfig`` is what one launch was asked for;
``ViewerServer.create(config)`` returns a bound server without printing
anything, for a test or a host program that wants to drive the lifecycle
itself; ``serve(config)`` is the command-line lifecycle and returns an exit
code. ``vedic_chart.viewer.transport`` is importable but not re-exported: it is
the wire format, not the product.
"""

from .server import ViewerConfig, ViewerServer, serve

__all__ = ["ViewerConfig", "ViewerServer", "serve"]
