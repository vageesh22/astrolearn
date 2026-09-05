"""QA gate for a built geodata database.

Fails loudly rather than letting a subtly wrong database reach the resolver:
checks row counts against expected bands, resolves a set of known places and
compares coordinates and timezones, validates every timezone identifier the
database carries, and measures the spatial-vs-GeoNames disagreement rate.

  python -m tools.geodata.verify_db                 # production database
  python -m tools.geodata.verify_db --fixture       # committed test fixture
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import BuildConfig
from vedic_chart.location.model import ResolvedLocation  # noqa: E402
from vedic_chart.location.offline.resolver import (  # noqa: E402
    OfflineLocationResolver,
)

# Expected row-count bands. Wide enough to survive an ordinary dump refresh,
# narrow enough to catch a truncated or mis-filtered import.
PRODUCTION_BANDS: dict[str, tuple[int, int]] = {
    "places": (700_000, 900_000),
    "place_names": (800_000, 1_200_000),
    "countries": (200, 300),
    "country_aliases": (600, 900),
    "admin1": (3_000, 5_000),
    "admin2": (40_000, 60_000),
    "dataset_metadata": (7, 7),
}

FIXTURE_BANDS: dict[str, tuple[int, int]] = {
    "places": (10_000, 15_000),
    "place_names": (12_000, 20_000),
    "countries": (200, 300),
    "country_aliases": (600, 900),
    "admin1": (500, 1_500),
    "admin2": (20_000, 30_000),
    "dataset_metadata": (7, 7),
}

# (query, expected latitude, expected longitude, expected timezone)
KNOWN_PLACES: tuple[tuple[str, float, float, str], ...] = (
    ("Jalandhar", 31.32556, 75.57917, "Asia/Kolkata"),
    ("New Delhi, India", 28.63576, 77.22445, "Asia/Kolkata"),
    ("Mumbai", 19.07283, 72.88261, "Asia/Kolkata"),
    ("Hyderabad, India", 17.38405, 78.45636, "Asia/Kolkata"),
    ("London", 51.50853, -0.12574, "Europe/London"),
    ("Paris", 48.85341, 2.3488, "Europe/Paris"),
    ("Tokyo", 35.6895, 139.69171, "Asia/Tokyo"),
    ("New York City", 40.71427, -74.00597, "America/New_York"),
)

COORDINATE_TOLERANCE = 0.5  # degrees
MAX_TZ_MISMATCH_PERCENT = 2.0


class VerificationFailure(RuntimeError):
    pass


def check_counts(connection, bands, failures, notes):
    for table, (low, high) in bands.items():
        count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        ok = low <= count <= high
        notes.append(
            f"  {'ok ' if ok else 'FAIL'} {table:<18} {count:>9}  "
            f"expected {low}-{high}"
        )
        if not ok:
            failures.append(
                f"{table} has {count} rows, expected {low}-{high}"
            )


def check_timezone_identifiers(connection, failures, notes):
    """Every distinct GeoNames timezone in the database must be real."""
    rows = connection.execute(
        "SELECT DISTINCT geonames_tz FROM places WHERE geonames_tz != ''"
    ).fetchall()
    bad = []
    for (zone_id,) in rows:
        try:
            ZoneInfo(zone_id)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            bad.append(zone_id)
    notes.append(
        f"  {'ok ' if not bad else 'FAIL'} {len(rows)} distinct timezone ids, "
        f"{len(bad)} not resolvable by zoneinfo"
    )
    if bad:
        failures.append(f"unresolvable timezone identifiers: {sorted(bad)[:10]}")


def check_known_places(db_path, failures, notes):
    resolver = OfflineLocationResolver(db_path)
    try:
        for query, latitude, longitude, timezone_id in KNOWN_PLACES:
            try:
                location: ResolvedLocation = resolver.resolve(query)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                failures.append(f"{query!r} failed to resolve: {exc}")
                notes.append(f"  FAIL {query:<20} {type(exc).__name__}")
                continue

            problems = []
            if abs(location.latitude - latitude) > COORDINATE_TOLERANCE:
                problems.append(f"lat {location.latitude} != {latitude}")
            if abs(location.longitude - longitude) > COORDINATE_TOLERANCE:
                problems.append(f"lon {location.longitude} != {longitude}")
            if location.timezone_id != timezone_id:
                problems.append(f"tz {location.timezone_id} != {timezone_id}")

            if problems:
                failures.append(f"{query!r}: {'; '.join(problems)}")
                notes.append(f"  FAIL {query:<20} {'; '.join(problems)}")
            else:
                notes.append(
                    f"  ok  {query:<20} {location.canonical_name[:42]:<42} "
                    f"{location.timezone_id}"
                )
    finally:
        resolver.close()


def check_tz_mismatch(db_path, config, failures, notes, skip):
    if skip:
        notes.append("  --  timezone cross-check skipped")
        return
    from .tz_crosscheck import crosscheck

    stats = crosscheck(Path(db_path), config.tz_report_path)
    ok = stats["percent"] < MAX_TZ_MISMATCH_PERCENT
    notes.append(
        f"  {'ok ' if ok else 'FAIL'} tz mismatch {stats['mismatches']}/"
        f"{stats['total']} = {stats['percent']:.3f}% "
        f"(limit {MAX_TZ_MISMATCH_PERCENT}%), "
        f"{stats['lookup_errors']} coordinates with no zone"
    )
    if not ok:
        failures.append(
            f"timezone mismatch rate {stats['percent']:.3f}% exceeds "
            f"{MAX_TZ_MISMATCH_PERCENT}%"
        )


def verify(db_path: Path, fixture: bool, skip_tz: bool = False) -> int:
    config = BuildConfig()
    failures: list[str] = []
    notes: list[str] = []

    print(f"Verifying {db_path} ({db_path.stat().st_size} bytes)\n")
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)

    notes.append("row counts:")
    check_counts(
        connection, FIXTURE_BANDS if fixture else PRODUCTION_BANDS, failures, notes
    )
    notes.append("timezone identifiers:")
    check_timezone_identifiers(connection, failures, notes)
    connection.close()

    notes.append("known places:")
    check_known_places(db_path, failures, notes)

    notes.append("timezone cross-check:")
    check_tz_mismatch(db_path, config, failures, notes, skip_tz)

    print("\n".join(notes))
    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nAll checks passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--db", default=None)
    parser.add_argument("--skip-tz", action="store_true")
    args = parser.parse_args()

    config = BuildConfig()
    if args.db:
        db_path = Path(args.db)
    elif args.fixture:
        db_path = config.fixture_path
    else:
        db_path = config.out_dir / "geodata.sqlite"

    return verify(db_path, fixture=args.fixture, skip_tz=args.skip_tz)


if __name__ == "__main__":
    sys.exit(main())
