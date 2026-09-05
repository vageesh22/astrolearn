"""Read-only access to the geodata database.

The connection is opened through a SQLite URI with ``mode=ro`` and
``immutable=1``: the runtime never writes to this file, and declaring it
immutable lets SQLite skip locking entirely. Building the database is the
importer's job (``tools/geodata``), which is not part of this package.
"""

import sqlite3
from pathlib import Path


class GeodataError(RuntimeError):
    """The geodata database is missing, unreadable, or the wrong shape."""


REQUIRED_TABLES = frozenset(
    {
        "places",
        "place_names",
        "countries",
        "country_aliases",
        "admin1",
        "admin2",
        "dataset_metadata",
    }
)


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open the geodata database read-only, verifying its shape."""
    path = Path(db_path)
    if not path.is_file():
        raise GeodataError(
            f"Geodata database not found at {path}. Build it with "
            "tools/geodata/build_db.py, or point the resolver at the test "
            "fixture."
        )

    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
    connection.row_factory = sqlite3.Row

    present = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    missing = REQUIRED_TABLES - present
    if missing:
        connection.close()
        raise GeodataError(
            f"Geodata database at {path} is missing tables: "
            f"{', '.join(sorted(missing))}."
        )

    return connection


def dataset_metadata(connection: sqlite3.Connection) -> list[dict]:
    """Return the provenance rows recorded when the database was built."""
    return [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM dataset_metadata ORDER BY dataset"
        )
    ]


def table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Row count per table, for QA and reporting."""
    counts = {}
    for table in sorted(REQUIRED_TABLES):
        counts[table] = connection.execute(
            f"SELECT COUNT(*) AS n FROM {table}"
        ).fetchone()["n"]
    return counts
