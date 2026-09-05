"""Candidate lookup, scoring, and the ambiguity/dominance policy.

Every tunable number in the geocoder lives in :class:`RankingConfig` and
nowhere else. Scoring and dominance read them from the config they are handed,
so behaviour can be changed -- or tested -- without touching this logic.
"""

import math
import sqlite3
from dataclasses import dataclass, field

from ..model import PlaceCandidate
from .normalize import normalize_name, split_query

# Feature codes, in the GeoNames "P" (populated place) class, that carry
# administrative rank. Documented at https://www.geonames.org/export/codes.html
DEFAULT_FEATURE_WEIGHTS: dict[str, float] = {
    "PPLC": 6.0,   # capital of a country
    "PPLA": 4.0,   # seat of a first-order administrative division
    "PPLA2": 3.0,  # seat of a second-order division
    "PPLA3": 2.0,
    "PPLA4": 1.5,
    "PPLA5": 1.0,
    "PPLG": 1.0,   # seat of government
    "PPL": 0.0,    # ordinary populated place
    "PPLX": -0.5,  # section of a populated place
    "PPLL": -1.0,  # populated locality
    "PPLR": -1.0,  # religious populated place
    "PPLS": -1.0,  # populated places (plural)
    "PPLW": -3.0,  # destroyed populated place
    "PPLQ": -3.0,  # abandoned populated place
    "PPLH": -3.0,  # historical populated place
}


@dataclass(frozen=True)
class RankingConfig:
    """Every weight and threshold the geocoder uses.

    Scoring is additive: a feature-code weight, plus a population term, plus
    bonuses for how well the stored name matched the query.
    """

    feature_weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_FEATURE_WEIGHTS)
    )
    default_feature_weight: float = -1.0

    # Population enters as log10 so that a city ten times larger scores one
    # step higher, rather than swamping every other signal.
    population_log_weight: float = 1.5

    official_name_bonus: float = 1.0   # matched the GeoNames official name
    ascii_name_bonus: float = 0.8      # matched the asciiname column
    alternate_name_bonus: float = 0.0  # matched an alternate name
    preferred_name_bonus: float = 0.6  # alternate flagged isPreferredName
    short_name_bonus: float = 0.2
    colloquial_penalty: float = -0.5
    historic_penalty: float = -2.0     # e.g. "Jullundur" for Jalandhar

    # Each qualifier ("Punjab", "India") that a candidate satisfies.
    qualifier_match_bonus: float = 5.0

    # --- ambiguity policy -------------------------------------------------
    # Two candidates are "materially different" when they are in different
    # countries, or in different first-order divisions of one country.
    # Springfield IL and Springfield MO are different answers; two records for
    # the same town are not.

    # A candidate may only be auto-picked over materially different rivals if
    # its feature code appears here. This is a necessary condition, not a
    # sufficient one. Its real job is to exclude the degenerate codes -- PPLW
    # (destroyed), PPLQ (abandoned) and PPLH (historical) -- which must never
    # win automatically over a place people still live in. Every live
    # settlement code is allowed, because administrative rank is a poor gate:
    # Jalandhar, a city of 868,929, is a plain PPL.
    auto_pick_required_feature_codes: frozenset[str] = frozenset(
        {
            "PPLC", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLA5",
            "PPLG", "PPL", "PPLS", "PPLL", "PPLX", "PPLR",
        }
    )

    # A national capital that is the only capital among the rivals dominates
    # them regardless of population ratio. This is what separates London (GB,
    # PPLC) from London (CA, PPL) without pretending 21x is a decisive margin.
    capital_feature_codes: frozenset[str] = frozenset({"PPLC"})

    # Failing the capital rule, the top candidate must out-populate the best
    # materially different rival by at least this factor. Deliberately steep:
    # Hyderabad India is 3.6x Hyderabad Pakistan and must stay ambiguous.
    dominance_population_ratio: float = 50.0

    # The ratio rule only applies when the top candidate's own population is at
    # least this large. GeoNames records an unknown population as 0, not as
    # "empty", so a ratio measured against 0 says only that the rival is
    # unranked. Requiring the winner to be substantial in its own right stops
    # two obscure hamlets being separated by a meaningless ratio, while still
    # letting a real city beat unranked namesakes.
    dominance_min_population: int = 1000


@dataclass(frozen=True)
class ResolutionDecision:
    """Why the resolver answered as it did."""

    query: str
    place_token: str
    qualifiers: tuple[str, ...]
    candidates: tuple[PlaceCandidate, ...]
    chosen: PlaceCandidate | None
    materially_different_count: int
    dominance_applied: bool
    dominance_reason: str
    population_ratio: float | None


_CANDIDATE_SQL = """
SELECT
    p.geoname_id, p.name, p.ascii_name, p.latitude, p.longitude,
    p.feature_code, p.country_code, p.admin1_code, p.admin2_code, p.population,
    pn.kind, pn.is_preferred, pn.is_short, pn.is_colloquial, pn.is_historic,
    pn.original AS matched_name,
    c.name AS country_name, c.norm_name AS country_norm, c.iso3 AS country_iso3,
    a1.name AS admin1_name, a1.norm_name AS admin1_norm,
    a2.name AS admin2_name, a2.norm_name AS admin2_norm
FROM place_names pn
JOIN places p ON p.geoname_id = pn.geoname_id
LEFT JOIN countries c ON c.country_code = p.country_code
LEFT JOIN admin1 a1 ON a1.key = p.country_code || '.' || p.admin1_code
LEFT JOIN admin2 a2 ON a2.key = p.country_code || '.' || p.admin1_code || '.' || p.admin2_code
WHERE pn.norm_name = ?
"""


def _name_bonus(row: sqlite3.Row, config: RankingConfig) -> float:
    kind = row["kind"]
    if kind == "official":
        bonus = config.official_name_bonus
    elif kind == "ascii":
        bonus = config.ascii_name_bonus
    else:
        bonus = config.alternate_name_bonus

    if row["is_preferred"]:
        bonus += config.preferred_name_bonus
    if row["is_short"]:
        bonus += config.short_name_bonus
    if row["is_colloquial"]:
        bonus += config.colloquial_penalty
    if row["is_historic"]:
        bonus += config.historic_penalty
    return bonus


def _qualifier_targets(row: sqlite3.Row, aliases: dict[str, str]) -> set[str]:
    """Everything a qualifier token is allowed to match for this candidate."""
    targets = {
        row["country_norm"],
        row["admin1_norm"],
        row["admin2_norm"],
        normalize_name(row["country_code"] or ""),
        normalize_name(row["country_iso3"] or ""),
    }
    # Country aliases ("uk", "usa", "england") that point at this country.
    country_code = row["country_code"]
    targets.update(
        alias for alias, code in aliases.items() if code == country_code
    )
    return {target for target in targets if target}


def load_country_aliases(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        row["norm_alias"]: row["country_code"]
        for row in connection.execute(
            "SELECT norm_alias, country_code FROM country_aliases"
        )
    }


def score_candidates(
    connection: sqlite3.Connection,
    query: str,
    config: RankingConfig,
) -> tuple[str, list[str], list[PlaceCandidate]]:
    """Find and rank every place matching a query. Best first."""
    place_token, qualifiers = split_query(query)
    if not place_token:
        return place_token, qualifiers, []

    aliases = load_country_aliases(connection)
    best: dict[int, tuple[float, PlaceCandidate]] = {}

    for row in connection.execute(_CANDIDATE_SQL, (place_token,)):
        if qualifiers:
            targets = _qualifier_targets(row, aliases)
            matched = sum(1 for q in qualifiers if q in targets)
            if matched < len(qualifiers):
                continue
        else:
            matched = 0

        feature_weight = config.feature_weights.get(
            row["feature_code"], config.default_feature_weight
        )
        population = row["population"] or 0
        score = (
            feature_weight
            + config.population_log_weight * math.log10(population + 1)
            + _name_bonus(row, config)
            + config.qualifier_match_bonus * matched
        )

        candidate = PlaceCandidate(
            geoname_id=row["geoname_id"],
            name=row["name"],
            admin1_name=row["admin1_name"],
            country_name=row["country_name"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            timezone_id=None,  # resolved spatially only for a returned place
            population=population,
            feature_code=row["feature_code"],
            score=round(score, 6),
            matched_name=row["matched_name"],
        )

        # One row per place: a place may match on several of its names, and
        # the best-scoring match is the one that represents it.
        previous = best.get(candidate.geoname_id)
        if previous is None or score > previous[0]:
            best[candidate.geoname_id] = (score, candidate)

    ranked = [candidate for _, candidate in best.values()]
    ranked.sort(key=lambda c: (-c.score, -c.population, c.geoname_id))
    return place_token, qualifiers, ranked


def evaluate(
    query: str,
    place_token: str,
    qualifiers: list[str],
    ranked: list[PlaceCandidate],
    config: RankingConfig,
) -> ResolutionDecision:
    """Decide whether the top candidate may be auto-picked.

    Returns a decision whose ``chosen`` is None when the query is ambiguous
    under the configured policy; the caller turns that into an error.
    """
    base = ResolutionDecision(
        query=query,
        place_token=place_token,
        qualifiers=tuple(qualifiers),
        candidates=tuple(ranked),
        chosen=None,
        materially_different_count=0,
        dominance_applied=False,
        dominance_reason="no candidates",
        population_ratio=None,
    )
    if not ranked:
        return base

    top = ranked[0]
    rivals = [
        candidate
        for candidate in ranked[1:]
        if (candidate.country_name, candidate.admin1_name)
        != (top.country_name, top.admin1_name)
    ]

    if not rivals:
        return ReplaceDecision(
            base,
            chosen=top,
            materially_different_count=0,
            dominance_applied=False,
            dominance_reason=(
                "single place: no materially different candidates"
            ),
        )

    best_rival = rivals[0]
    ratio = (top.population + 1) / (best_rival.population + 1)

    if top.feature_code not in config.auto_pick_required_feature_codes:
        return ReplaceDecision(
            base,
            materially_different_count=len(rivals),
            dominance_reason=(
                f"top candidate feature code {top.feature_code!r} is not in "
                "auto_pick_required_feature_codes"
            ),
            population_ratio=ratio,
        )

    top_is_capital = top.feature_code in config.capital_feature_codes
    rival_capitals = [
        rival for rival in rivals if rival.feature_code in config.capital_feature_codes
    ]

    if top_is_capital and not rival_capitals:
        return ReplaceDecision(
            base,
            chosen=top,
            materially_different_count=len(rivals),
            dominance_applied=True,
            dominance_reason=(
                f"{top.name} is the only candidate with a capital feature code "
                f"({top.feature_code}); best rival {best_rival.name} "
                f"({best_rival.country_name}) is {best_rival.feature_code}"
            ),
            population_ratio=ratio,
        )

    if top.population < config.dominance_min_population:
        return ReplaceDecision(
            base,
            materially_different_count=len(rivals),
            dominance_reason=(
                f"top candidate population {top.population} is below "
                f"dominance_min_population {config.dominance_min_population}, "
                "so the population ratio is not a meaningful signal"
            ),
            population_ratio=ratio,
        )

    if ratio >= config.dominance_population_ratio:
        return ReplaceDecision(
            base,
            chosen=top,
            materially_different_count=len(rivals),
            dominance_applied=True,
            dominance_reason=(
                f"population {top.population} gives a {ratio:.1f}x ratio over "
                f"{best_rival.name} ({best_rival.admin1_name}, "
                f"{best_rival.country_name}, pop {best_rival.population}), "
                f"meeting the required {config.dominance_population_ratio:.1f}x"
            ),
            population_ratio=ratio,
        )

    return ReplaceDecision(
        base,
        materially_different_count=len(rivals),
        dominance_reason=(
            f"population ratio {ratio:.1f}x over {best_rival.name} "
            f"({best_rival.country_name}) is below the required "
            f"{config.dominance_population_ratio:.1f}x and no capital rule applies"
        ),
        population_ratio=ratio,
    )


def ReplaceDecision(base: ResolutionDecision, **changes) -> ResolutionDecision:
    """Small helper: frozen dataclasses need explicit replacement."""
    import dataclasses

    return dataclasses.replace(base, **changes)
