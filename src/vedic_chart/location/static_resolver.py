"""Layer 2, part 2: a fixed, in-memory resolver.

**For tests and development only.** This is not a geocoding service. It knows a
handful of hardcoded places and nothing else: it makes no network calls, does no
fuzzy or partial matching, and infers nothing from a query it does not
recognize. An unknown place raises PlaceNotFoundError rather than guessing.

Its purpose is to let the rest of the system be built and tested against the
:class:`~vedic_chart.location.model.LocationResolver` protocol before a real
geocoding provider is chosen and plugged in.
"""

from .model import LocationResolver, PlaceNotFoundError, ResolvedLocation

_NEW_DELHI = ResolvedLocation(
    canonical_name="New Delhi, India",
    latitude=28.6139,
    longitude=77.2090,
    timezone_id="Asia/Kolkata",
)

_JALANDHAR = ResolvedLocation(
    canonical_name="Jalandhar, India",
    latitude=31.3260,
    longitude=75.5762,
    timezone_id="Asia/Kolkata",
)

_NEW_YORK = ResolvedLocation(
    canonical_name="New York, USA",
    latitude=40.7128,
    longitude=-74.0060,
    timezone_id="America/New_York",
)

_LONDON = ResolvedLocation(
    canonical_name="London, UK",
    latitude=51.5074,
    longitude=-0.1278,
    timezone_id="Europe/London",
)

_TOKYO = ResolvedLocation(
    canonical_name="Tokyo, Japan",
    latitude=35.6764,
    longitude=139.6500,
    timezone_id="Asia/Tokyo",
)

# Several keys may point at one place; each place is a single shared instance.
_PLACES_BY_KEY: dict[str, ResolvedLocation] = {
    "new delhi": _NEW_DELHI,
    "new delhi, india": _NEW_DELHI,
    "delhi": _NEW_DELHI,
    "jalandhar": _JALANDHAR,
    "jalandhar, india": _JALANDHAR,
    "new york": _NEW_YORK,
    "new york, usa": _NEW_YORK,
    "new york city": _NEW_YORK,
    "nyc": _NEW_YORK,
    "london": _LONDON,
    "london, uk": _LONDON,
    "tokyo": _TOKYO,
    "tokyo, japan": _TOKYO,
}

_CANONICAL_NAMES: tuple[str, ...] = (
    _NEW_DELHI.canonical_name,
    _JALANDHAR.canonical_name,
    _NEW_YORK.canonical_name,
    _LONDON.canonical_name,
    _TOKYO.canonical_name,
)


def _normalize_query(place_query: str) -> str:
    """Casefold, trim, and collapse internal whitespace runs to single spaces.

    This is the only leniency offered. It makes lookup insensitive to case and
    to stray spacing; it is not fuzzy matching.
    """
    return " ".join(place_query.casefold().split())


class StaticLocationResolver:
    """A deterministic resolver over a fixed table of places.

    Implements the LocationResolver protocol. For tests and development only --
    see the module docstring.
    """

    def resolve(self, place_query: str) -> ResolvedLocation:
        """Return the place matching the query, or raise PlaceNotFoundError."""
        if not isinstance(place_query, str):
            raise PlaceNotFoundError(
                "place_query must be a string; got "
                f"{type(place_query).__name__}."
            )

        try:
            return _PLACES_BY_KEY[_normalize_query(place_query)]
        except KeyError:
            raise PlaceNotFoundError(
                f"No place matching {place_query!r}. This is the static test "
                "resolver, which knows only a fixed list of places "
                f"({', '.join(_CANONICAL_NAMES)}) and does not perform "
                "geocoding or fuzzy matching."
            ) from None

    def known_places(self) -> tuple[str, ...]:
        """Return the canonical names this resolver can resolve."""
        return _CANONICAL_NAMES


# A structural check: the class must satisfy the protocol it is written against.
_: LocationResolver = StaticLocationResolver()
