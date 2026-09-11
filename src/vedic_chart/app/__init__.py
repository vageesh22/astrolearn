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

The same pipeline is available as a command, ``python -m vedic_chart.app``; see
``vedic_chart.app.cli``. The function reads and returns; only the command
writes.
"""

from .pipeline import (
    ChartConfig,
    ChartResult,
    ConfigurationError,
    render_birth_chart,
)

__all__ = [
    "ChartConfig",
    "ChartResult",
    "ConfigurationError",
    "render_birth_chart",
]
