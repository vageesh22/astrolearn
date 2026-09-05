"""Spatial timezone lookup from coordinates, fully offline.

``timezonefinder`` carries its timezone boundary polygons inside the installed
package, so this makes no network call. It answers only "which zone is this
point in"; the *rules* of that zone -- offsets, daylight saving, historical
changes -- remain Layer 3's business via ``zoneinfo``. This module returns an
identifier and nothing more.
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from timezonefinder import TimezoneFinder


class TimezoneLookupError(LookupError):
    """No usable IANA timezone could be determined for a coordinate."""


_FINDER: TimezoneFinder | None = None


def get_finder() -> TimezoneFinder:
    """Return the process-wide TimezoneFinder.

    Constructing one loads the bundled polygon data, which is slow enough that
    it must not happen per query.
    """
    global _FINDER
    if _FINDER is None:
        _FINDER = TimezoneFinder()
    return _FINDER


def lookup(latitude: float, longitude: float) -> str:
    """Return the IANA timezone identifier containing a coordinate.

    Raises TimezoneLookupError when the point yields no zone, or yields an
    ``Etc/GMT*`` fixed-offset zone. Both mean the point missed every real
    timezone polygon -- typically open ocean -- and neither is a legitimate
    answer for a birth place on land. A fixed-offset zone in particular would
    silently discard daylight-saving history and produce a wrong chart rather
    than an error.
    """
    zone_id = get_finder().timezone_at(lng=longitude, lat=latitude)

    if zone_id is None:
        raise TimezoneLookupError(
            f"No timezone found for latitude {latitude}, longitude "
            f"{longitude}. The coordinate does not fall inside any timezone "
            "boundary, which for a birth place means the coordinate is wrong."
        )

    if zone_id.startswith("Etc/"):
        raise TimezoneLookupError(
            f"Coordinate latitude {latitude}, longitude {longitude} resolved "
            f"to the fixed-offset zone {zone_id!r}, which carries no "
            "daylight-saving or historical rules. This indicates a coordinate "
            "outside any real timezone region rather than a usable place."
        )

    try:
        ZoneInfo(zone_id)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise TimezoneLookupError(
            f"Timezone {zone_id!r} is not present in the system tzdata "
            "database, so Layer 3 could not resolve offsets for it."
        ) from exc

    return zone_id
