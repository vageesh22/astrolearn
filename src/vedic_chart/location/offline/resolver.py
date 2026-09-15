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
from .normalize import normalize_name, split_query
from .search import (
    RankingConfig,
    ResolutionDecision,
    SUGGESTION_SCORE,
    candidate_from_row,
    evaluate,
    record_row,
    score_candidates,
    suggest_candidates,
)
from .tz_lookup import lookup as timezone_lookup

#: Layer 15 section 5.1: a prefix shorter than this after normalisation lists
#: nothing. Two code points is the point at which a prefix scan of a national
#: dataset stops being a scan of the whole table.
MIN_SUGGEST_PREFIX = 2

#: Layer 15 section 5.1: the largest listing any caller may ask for. The page
#: asks for ten; the cap exists so that a caller cannot turn an autocomplete
#: into a table dump.
MAX_SUGGEST_LIMIT = 50


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

    # --- Layer 15 C1: read-only additions --------------------------------

    def suggest(self, text: str, *, limit: int) -> "list[PlaceCandidate]":
        """Prefix listing for autocomplete (Layer 15 section 5.1).

        An indexed range scan on ``place_names(norm_name)`` over the
        normalised text before the first comma; comma qualifiers filter
        through the same full-name matching resolution applies; rows are
        deduplicated by ``geoname_id`` and ordered by population descending,
        then exact-name match, then name, then ``geoname_id``; at most
        ``limit``. ``timezone_id`` is None -- a suggestion is not a resolved
        place and its zone is looked up only for the record actually used
        (:meth:`record`).

        Never raises for an unmatched or too-short prefix: it returns ``[]``.
        It does raise for an argument that is not what the signature says,
        because that is a programming error rather than an empty answer.
        """
        if not isinstance(text, str):
            raise TypeError(
                f"text must be a string; got {type(text).__name__}."
            )
        # A bool is an int in Python, and ``limit=True`` would silently mean
        # one suggestion. It is rejected explicitly (section 5.1, v0.3).
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                f"limit must be an int; got {type(limit).__name__} "
                f"({limit!r})."
            )
        if not 1 <= limit <= MAX_SUGGEST_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {MAX_SUGGEST_LIMIT} inclusive; "
                f"got {limit!r}."
            )

        place_prefix, qualifiers = split_query(text)
        if len(place_prefix) < MIN_SUGGEST_PREFIX:
            return []
        return suggest_candidates(
            self._connection, place_prefix, qualifiers, limit
        )

    def record(
        self, geoname_id: int
    ) -> "tuple[ResolvedLocation, PlaceCandidate]":
        """One place by primary key (Layer 15 section 5.3).

        The row joined to admin1 and country exactly as the candidate query
        joins them, the timezone from the existing spatial lookup on the row's
        own coordinates, and the ``ResolvedLocation`` built by the same
        canonical-name rule as :meth:`resolve_with_details`. No name is
        resolved and no ranking or dominance rule runs: the caller has already
        said which record it means.

        Raises :class:`PlaceNotFoundError` when the id is not in this
        database. ``TimezoneLookupError``, ``InvalidTimezoneError`` and
        ``InvalidCoordinateError`` propagate exactly as they do from
        ``resolve`` today.
        """
        if isinstance(geoname_id, bool) or not isinstance(geoname_id, int):
            raise TypeError(
                f"geoname_id must be an int; got {type(geoname_id).__name__} "
                f"({geoname_id!r})."
            )
        if geoname_id < 1:
            raise ValueError(
                f"geoname_id must be 1 or greater; got {geoname_id!r}."
            )

        row = record_row(self._connection, geoname_id)
        if row is None:
            raise PlaceNotFoundError(
                f"No place with GeoNames id {geoname_id} in the offline "
                f"geodata database at {self.db_path.name}."
            )

        timezone_id = timezone_lookup(row["latitude"], row["longitude"])
        candidate = candidate_from_row(
            row, score=SUGGESTION_SCORE, timezone_id=timezone_id
        )
        location = ResolvedLocation(
            canonical_name=self.candidate_label(candidate),
            latitude=candidate.latitude,
            longitude=candidate.longitude,
            timezone_id=timezone_id,
        )
        return location, candidate

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def candidate_label(candidate: PlaceCandidate) -> str:
        """``name, admin1, country``, omitting the parts a place lacks.

        Public because the viewer shows this label beside a suggestion and
        compares the submitted text against it (Layer 15 sections 5.2, 5.3),
        and a consumer must be able to build it by the one rule that produced
        ``ResolvedLocation.canonical_name`` without reaching for a private
        name.
        """
        parts = [candidate.name]
        if candidate.admin1_name:
            parts.append(candidate.admin1_name)
        if candidate.country_name:
            parts.append(candidate.country_name)
        return ", ".join(parts)

    @staticmethod
    def suggestion_label(candidate: PlaceCandidate) -> str:
        """The label a suggestion is *shown* as (Layer 15 section 5.1).

        ``name, admin1, country``, with ``(matched: <matched_name>)`` appended
        only when the name that matched is a different name -- an alias, a
        historic spelling, another script -- and not merely another spelling
        of the place's own name.

        "Different" is decided by :func:`normalize_name`, because this layer
        owns what "the same name" means: it is the one definition the importer
        wrote the database with and the resolver queries it with. A consumer
        that compared the two strings with its own collation -- a browser's
        ``localeCompare``, a casefold of its own -- would be a second, quietly
        disagreeing definition, so the comparison is made here and the answer
        travels as a string.

        The label the server compares a submission against stays
        :meth:`candidate_label`: this one is for display only.
        """
        label = OfflineLocationResolver.candidate_label(candidate)
        if normalize_name(candidate.matched_name) == normalize_name(
            candidate.name
        ):
            return label
        return f"{label} (matched: {candidate.matched_name})"

    @staticmethod
    def _canonical_name(candidate: PlaceCandidate) -> str:
        return OfflineLocationResolver.candidate_label(candidate)

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
