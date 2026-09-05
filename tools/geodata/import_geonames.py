"""Stream the GeoNames dumps into the geodata SQLite schema.

Everything is parsed line by line: the India dump alone is 660k rows and 70 MB,
so no file is ever loaded whole. Names are normalized with the *runtime's*
normalizer, so the importer and the query path cannot disagree about what
matches what.
"""

import sqlite3
from pathlib import Path

# .config must come first: importing it puts src/ on sys.path.
from .config import (
    COUNTRY_ALIAS_MAP,
    EXCLUDED_ISOLANGUAGES,
    BuildConfig,
)
from vedic_chart.location.offline.normalize import normalize_name  # noqa: E402
from .verify_inputs import open_text

SCHEMA = """
CREATE TABLE places (
    geoname_id     INTEGER PRIMARY KEY,
    name           TEXT    NOT NULL,
    ascii_name     TEXT,
    latitude       REAL    NOT NULL,
    longitude      REAL    NOT NULL,
    feature_class  TEXT,
    feature_code   TEXT,
    country_code   TEXT,
    admin1_code    TEXT,
    admin2_code    TEXT,
    population     INTEGER NOT NULL DEFAULT 0,
    geonames_tz    TEXT,
    source         TEXT    NOT NULL
);

CREATE TABLE place_names (
    norm_name      TEXT    NOT NULL,
    geoname_id     INTEGER NOT NULL,
    kind           TEXT    NOT NULL,
    isolanguage    TEXT,
    is_preferred   INTEGER NOT NULL DEFAULT 0,
    is_short       INTEGER NOT NULL DEFAULT 0,
    is_colloquial  INTEGER NOT NULL DEFAULT 0,
    is_historic    INTEGER NOT NULL DEFAULT 0,
    original       TEXT
);

CREATE TABLE countries (
    country_code TEXT PRIMARY KEY,
    iso3         TEXT,
    name         TEXT,
    norm_name    TEXT,
    geoname_id   INTEGER
);

CREATE TABLE country_aliases (
    norm_alias   TEXT PRIMARY KEY,
    country_code TEXT NOT NULL,
    origin       TEXT NOT NULL
);

CREATE TABLE admin1 (
    key          TEXT PRIMARY KEY,
    country_code TEXT,
    admin1_code  TEXT,
    name         TEXT,
    ascii_name   TEXT,
    norm_name    TEXT,
    geoname_id   INTEGER
);

CREATE TABLE admin2 (
    key          TEXT PRIMARY KEY,
    country_code TEXT,
    admin1_code  TEXT,
    admin2_code  TEXT,
    name         TEXT,
    ascii_name   TEXT,
    norm_name    TEXT,
    geoname_id   INTEGER
);

CREATE TABLE dataset_metadata (
    dataset          TEXT,
    source_url       TEXT,
    source_release   TEXT,
    provenance       TEXT,
    download_date    TEXT,
    sha256           TEXT,
    license          TEXT,
    attribution      TEXT,
    transformations  TEXT,
    row_count        INTEGER,
    importer_version TEXT
);
"""

INDEXES = """
CREATE INDEX idx_place_names_norm ON place_names(norm_name);
CREATE INDEX idx_place_names_geoname ON place_names(geoname_id);
CREATE INDEX idx_places_country ON places(country_code);
CREATE INDEX idx_admin1_norm ON admin1(norm_name);
CREATE INDEX idx_admin2_norm ON admin2(norm_name);
"""


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def create_indexes(connection: sqlite3.Connection) -> None:
    connection.executescript(INDEXES)


class ImportStats(dict):
    """Counters the build reports on."""

    def bump(self, key: str, amount: int = 1) -> None:
        self[key] = self.get(key, 0) + amount


def import_places(
    connection: sqlite3.Connection,
    config: BuildConfig,
    stats: ImportStats,
    keep: set[int] | None = None,
) -> set[int]:
    """Import cities500 then each country pack, deduping by geoname_id.

    cities500 and the country packs overlap: every Indian town above 500 people
    appears in both. cities500 is loaded first and wins, because a place is the
    same place either way; the country pack then contributes only what cities500
    left out.
    """
    seen: set[int] = set()
    batch: list[tuple] = []

    def flush() -> None:
        if batch:
            connection.executemany(
                "INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", batch
            )
            batch.clear()

    def consume(path: Path, inner: str, source: str, p_class_only: bool) -> None:
        for line in open_text(path, inner):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 19:
                stats.bump(f"{source}_malformed_rows")
                continue
            if p_class_only and parts[6] != "P":
                stats.bump(f"{source}_dropped_non_p_class")
                continue

            geoname_id = int(parts[0])
            if geoname_id in seen:
                stats.bump(f"{source}_duplicate_of_cities500")
                continue
            if keep is not None and geoname_id not in keep:
                stats.bump(f"{source}_outside_fixture_slice")
                continue

            seen.add(geoname_id)
            batch.append(
                (
                    geoname_id,
                    parts[1],
                    parts[2],
                    float(parts[4]),
                    float(parts[5]),
                    parts[6],
                    parts[7],
                    parts[8],
                    parts[10],
                    parts[11],
                    int(parts[14] or 0),
                    parts[17],
                    source,
                )
            )
            stats.bump(f"{source}_imported")
            if len(batch) >= 20000:
                flush()

    consume(config.raw_dir / "cities500.zip", "cities500.txt", "cities500", False)
    flush()
    for country in config.country_packs:
        consume(config.raw_dir / f"{country}.zip", f"{country}.txt", country, True)
        flush()
    flush()
    connection.commit()
    return seen


def import_official_names(
    connection: sqlite3.Connection, stats: ImportStats
) -> None:
    """Index every place under its official name and its ascii name."""
    rows = connection.execute(
        "SELECT geoname_id, name, ascii_name FROM places"
    ).fetchall()

    batch = []
    for geoname_id, name, ascii_name in rows:
        norm = normalize_name(name)
        if norm:
            batch.append((norm, geoname_id, "official", "", 0, 0, 0, 0, name))
            stats.bump("names_official")
        norm_ascii = normalize_name(ascii_name or "")
        if norm_ascii and norm_ascii != norm:
            batch.append(
                (norm_ascii, geoname_id, "ascii", "", 0, 0, 0, 0, ascii_name)
            )
            stats.bump("names_ascii")
        if len(batch) >= 50000:
            connection.executemany(
                "INSERT INTO place_names VALUES (?,?,?,?,?,?,?,?,?)", batch
            )
            batch.clear()
    if batch:
        connection.executemany(
            "INSERT INTO place_names VALUES (?,?,?,?,?,?,?,?,?)", batch
        )
    connection.commit()


def import_alternate_names(
    connection: sqlite3.Connection,
    config: BuildConfig,
    stats: ImportStats,
    kept_ids: set[int],
) -> None:
    """Import alternate names for the country packs only.

    Only rows whose geonameid survived the place import are kept, and
    identifier pseudo-languages (links, Wikidata ids, postal and airport codes)
    are dropped -- they are not names anyone would type.
    """
    batch = []
    for country in config.country_packs:
        path = config.raw_dir / f"{country}-alternatenames.zip"
        if not path.is_file():
            stats.bump(f"{country}_alternates_file_missing")
            continue
        for line in open_text(path, f"{country}.txt"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 8:
                stats.bump("alternates_malformed")
                continue
            geoname_id = int(parts[1]) if parts[1].isdigit() else None
            if geoname_id is None or geoname_id not in kept_ids:
                stats.bump("alternates_dropped_unknown_geoname_id")
                continue
            isolanguage = parts[2]
            if isolanguage in EXCLUDED_ISOLANGUAGES:
                stats.bump("alternates_dropped_by_language_filter")
                continue
            norm = normalize_name(parts[3])
            if not norm:
                stats.bump("alternates_dropped_empty_after_normalize")
                continue
            batch.append(
                (
                    norm,
                    geoname_id,
                    "alternate",
                    isolanguage,
                    1 if parts[4] == "1" else 0,
                    1 if parts[5] == "1" else 0,
                    1 if parts[6] == "1" else 0,
                    1 if parts[7] == "1" else 0,
                    parts[3],
                )
            )
            stats.bump("names_alternate")
            if len(batch) >= 20000:
                connection.executemany(
                    "INSERT INTO place_names VALUES (?,?,?,?,?,?,?,?,?)", batch
                )
                batch.clear()
    if batch:
        connection.executemany(
            "INSERT INTO place_names VALUES (?,?,?,?,?,?,?,?,?)", batch
        )
    connection.commit()


def import_countries(
    connection: sqlite3.Connection, config: BuildConfig, stats: ImportStats
) -> None:
    rows = []
    aliases: list[tuple[str, str, str]] = []
    for line in open_text(config.raw_dir / "countryInfo.txt", None):
        if line.startswith("#"):
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 17:
            continue
        code, iso3, name = parts[0], parts[1], parts[4]
        geoname_id = int(parts[16]) if parts[16].isdigit() else None
        norm = normalize_name(name)
        rows.append((code, iso3, name, norm, geoname_id))
        if norm:
            aliases.append((norm, code, "geonames countryInfo"))
        aliases.append((normalize_name(code), code, "geonames ISO 3166-1 alpha-2"))
        if iso3:
            aliases.append(
                (normalize_name(iso3), code, "geonames ISO 3166-1 alpha-3")
            )
        stats.bump("countries")

    connection.executemany(
        "INSERT OR REPLACE INTO countries VALUES (?,?,?,?,?)", rows
    )
    # Our own alias map is applied last so it wins any collision.
    for alias, code in COUNTRY_ALIAS_MAP.items():
        aliases.append((normalize_name(alias), code, "project alias map"))
        stats.bump("country_aliases_project")
    connection.executemany(
        "INSERT OR REPLACE INTO country_aliases VALUES (?,?,?)", aliases
    )
    connection.commit()


def import_admin_codes(
    connection: sqlite3.Connection,
    config: BuildConfig,
    stats: ImportStats,
    restrict_countries: set[str] | None = None,
) -> None:
    """Import admin1/admin2 reference names.

    ``restrict_countries`` trims the tables to the countries actually present
    in ``places``. The production build keeps everything; the fixture uses it to
    stay small, since an admin division no place refers to is dead weight.
    """
    admin1_rows = []
    for line in open_text(config.raw_dir / "admin1CodesASCII.txt", None):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 4:
            continue
        key = parts[0]
        pieces = key.split(".")
        if len(pieces) != 2:
            continue
        if restrict_countries is not None and pieces[0] not in restrict_countries:
            stats.bump("admin1_outside_fixture_countries")
            continue
        admin1_rows.append(
            (
                key,
                pieces[0],
                pieces[1],
                parts[1],
                parts[2],
                normalize_name(parts[1]),
                int(parts[3]) if parts[3].isdigit() else None,
            )
        )
        stats.bump("admin1")
    connection.executemany(
        "INSERT OR REPLACE INTO admin1 VALUES (?,?,?,?,?,?,?)", admin1_rows
    )

    admin2_rows = []
    for line in open_text(config.raw_dir / "admin2Codes.txt", None):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 4:
            continue
        key = parts[0]
        pieces = key.split(".")
        if len(pieces) != 3:
            continue
        if restrict_countries is not None and pieces[0] not in restrict_countries:
            stats.bump("admin2_outside_fixture_countries")
            continue
        admin2_rows.append(
            (
                key,
                pieces[0],
                pieces[1],
                pieces[2],
                parts[1],
                parts[2],
                normalize_name(parts[1]),
                int(parts[3]) if parts[3].isdigit() else None,
            )
        )
        stats.bump("admin2")
    connection.executemany(
        "INSERT OR REPLACE INTO admin2 VALUES (?,?,?,?,?,?,?,?)", admin2_rows
    )
    connection.commit()
