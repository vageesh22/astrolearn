"""Layer 11: one call and one command, from a birth to a finished SVG.

``vedic_chart.app`` composes the frozen calculation engine (Layer 8), the
canonical D1 representation (Layer 9) and the North Indian renderer (Layer 10)
into a single entry point. It changes none of them, computes nothing itself,
and adds no astrology, no web API and no user interface.

    from vedic_chart.app import ChartConfig, render_birth_chart
    from vedic_chart.inputs.model import BirthChartRequest

    request = BirthChartRequest.from_components(
        1995, 3, 21, 6, 45, place_query="Jalandhar"
    )
    config = ChartConfig(
        geodata_path="data/geodata.sqlite", ephemeris_path="ephe"
    )
    result = render_birth_chart(request, config)

Layer 13 exposes the Vimshottari daśā through the same composition, over one
shared assembly step: ``compute_dasha`` returns the timeline alone, and
``render_chart_and_dasha`` returns the drawing and the timeline of one chart.

    from vedic_chart.app import compute_dasha
    from vedic_chart.dasha import YearConvention, render_dasha_text

    dasha = compute_dasha(request, config, YearConvention.FIXED_365_256363)
    print(render_dasha_text(dasha.timeline, zone="Asia/Kolkata"))

The same pipeline is available as a command, ``python -m vedic_chart.app``; see
``vedic_chart.app.cli``. The functions read and return; only the command
writes.
"""

from .pipeline import (
    ChartAndDashaResult,
    ChartConfig,
    ChartResult,
    ConfigurationError,
    DashaResult,
    compute_dasha,
    render_birth_chart,
    render_chart_and_dasha,
)

__all__ = [
    "ChartAndDashaResult",
    "ChartConfig",
    "ChartResult",
    "ConfigurationError",
    "DashaResult",
    "compute_dasha",
    "render_birth_chart",
    "render_chart_and_dasha",
]
