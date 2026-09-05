"""The offline LocationResolver implementation.

Composes the geodata database (place lookup and ranking) with timezonefinder
(spatial timezone). No network access: see the module docstring of the package.
"""

import sqlite3
from pathlib import Path

from ..model import (
    AmbiguousPlaceError,
    LocationResolver,
    PlaceCandidate,
    PlaceNotFoundError,
    ResolvedLocation,
)
from . import db as db_module
from .search import RankingConfig, ResolutionDecision, evaluate, score_candidates
from .tz_lookup import lookup as timezone_lookup


class OfflineLocationResolver:
    """Resolve birth places against a locally built GeoNames database.

    Implements the Layer 2 ``LocationResolver`` protocol -- ``resolve`` is the
    only method the protocol requires. ``search`` and ``resolve_with_details``
    are a richer API this resolver offers in addition; callers that want to
    stay portable across resolvers should depend only on ``resolve``.
    """

    def __init__(
        self,
        db_path: str | Path,
        ranking_config: RankingConfig | None = None,
    ) -> None:
        self._connection: sqlite3.Connection = db_module.connect(db_path)
        self.db_path = Path(db_path)
        self.ranking_config = ranking_config or RankingConfig()

    # --- the protocol ----------------------------------------------------

    def resolve(self, place_query: str) -> ResolvedLocation:
        """Resolve a place query to a single validated location."""
        location, _decision = self.resolve_with_details(place_query)
        return location

    # --- the richer API --------------------------------------------------

    def search(self, place_query: str) -> list[PlaceCandidate]:
        """Return every matching place, ranked best first, without deciding."""
        if not isinstance(place_query, str):
            raise PlaceNotFoundError(
                f"place_query must be a string; got {type(place_query).__name__}."
            )
        _token, _qualifiers, ranked = score_candidates(
            self._connection, place_query, self.ranking_config
        )
        return ranked

    def resolve_with_details(
        self, place_query: str
    ) -> tuple[ResolvedLocation, ResolutionDecision]:
        """Resolve, and report why this answer was chosen.

        The decision records whether the answer was auto-picked over materially
        different rivals and on what grounds, so an automatic choice is never
        invisible to the caller.
        """
        if not isinstance(place_query, str):
            raise PlaceNotFoundError(
                f"place_query must be a string; got {type(place_query).__name__}."
            )

        token, qualifiers, ranked = score_candidates(
            self._connection, place_query, self.ranking_config
        )
        decision = evaluate(
            place_query, token, qualifiers, ranked, self.ranking_config
        )

        if not ranked:
            raise PlaceNotFoundError(
                f"No place matching {place_query!r} in the offline geodata "
                f"database at {self.db_path.name}. Coverage is cities of 500+ "
                "population worldwide plus all populated places in India."
            )

        if decision.chosen is None:
            listed = ", ".join(
                f"{c.name} ({c.admin1_name or '?'}, {c.country_name or '?'}, "
                f"pop {c.population})"
                for c in ranked[:5]
            )
            raise AmbiguousPlaceError(
                f"{place_query!r} matches several materially different places: "
                f"{listed}. {decision.dominance_reason}. Add a qualifier, for "
                'example "Hyderabad, India".',
                candidates=list(ranked),
            )

        chosen = decision.chosen
        timezone_id = timezone_lookup(chosen.latitude, chosen.longitude)

        location = ResolvedLocation(
            canonical_name=self._canonical_name(chosen),
            latitude=chosen.latitude,
            longitude=chosen.longitude,
            timezone_id=timezone_id,
        )
        return location, decision

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _canonical_name(candidate: PlaceCandidate) -> str:
        parts = [candidate.name]
        if candidate.admin1_name:
            parts.append(candidate.admin1_name)
        if candidate.country_name:
            parts.append(candidate.country_name)
        return ", ".join(parts)

    def dataset_metadata(self) -> list[dict]:
        """Provenance rows recorded when the database was built."""
        return db_module.dataset_metadata(self._connection)

    def table_counts(self) -> dict[str, int]:
        return db_module.table_counts(self._connection)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "OfflineLocationResolver":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


# Structural check: the class must satisfy the protocol it is written against.
def _protocol_check(resolver: LocationResolver) -> None:  # pragma: no cover
    return None
