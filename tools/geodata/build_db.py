"""Build the geodata SQLite database.

Writes to a temporary file and atomically renames it into place, so a failed or
interrupted build can never leave a half-written database where the runtime
would read it.

  python -m tools.geodata.build_db              # production database
  python -m tools.geodata.build_db --fixture    # small committed test fixture
"""

import argparse
import datetime as dt
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from .config import (
    EXPECTED_INPUTS,
    GEONAMES_ATTRIBUTION,
    GEONAMES_BASE_URL,
    GEONAMES_LICENSE,
    IMPORTER_VERSION,
    PROVENANCE,
    SOURCE_RELEASE,
    BuildConfig,
)
from .import_geonames import (
    ImportStats,
    create_indexes,
    create_schema,
    import_admin_codes,
    import_alternate_names,
    import_countries,
    import_official_names,
    import_places,
)
from .verify_inputs import open_text, sha256_of, verify

# Places the test suite depends on by identity, so the fixture cannot drift.
FIXTURE_PLACE_IDS: dict[int, str] = {
    1261481: "New Delhi, IN (PPLC)",
    1273294: "Delhi, IN (PPLA)",
    1275339: "Mumbai, IN (PPLA)",
    1269843: "Hyderabad, IN (PPLA)",
    1176734: "Hyderabad, PK (PPLA2)",
    1850147: "Tokyo, JP (PPLC)",
    5128581: "New York City, US",
    2643743: "London, GB (PPLC)",
    6058560: "London, CA (PPL)",
    2988507: "Paris, FR (PPLC)",
    4717560: "Paris, TX US (PPLA2)",
    4250542: "Springfield, IL US (PPLA)",
    4409896: "Springfield, MO US (PPLA2)",
    4525353: "Springfield, OH US (PPLA2)",
    4951788: "Springfield, MA US (PPL)",
    5754005: "Springfield, OR US (PPL)",
    # Timezone-boundary pair, ~20 km apart across the Wabash River in two
    # different zones. Vincennes is also a genuine GeoNames-vs-spatial
    # mismatch: GeoNames records America/Chicago, the polygon says
    # America/Indiana/Vincennes.
    # Two population-0 villages that collide with Jalandhar city, so the
    # fixture exercises the real India name-collision case.
    1269432: "Jalandhar village, Madhya Pradesh IN (pop 0)",
    10528566: "Jalandhar village, Uttar Pradesh IN (pop 0)",
    4266307: "Vincennes, IN US (America/Indiana/Vincennes)",
    4244967: "Mount Carmel, IL US (America/Chicago)",
}

FIXTURE_ADMIN1 = ("IN", "23")  # Punjab: full P-class coverage in the fixture
FIXTURE_TOP_WORLD_CITIES = 60


def select_fixture_ids(config: BuildConfig, extra: set[int]) -> set[int]:
    """Choose the reduced slice the fixture database is built from."""
    keep: set[int] = set(FIXTURE_PLACE_IDS) | set(extra)

    # Every populated place in Punjab, so village-level India lookup is tested.
    country, admin1 = FIXTURE_ADMIN1
    for line in open_text(config.raw_dir / f"{country}.zip", f"{country}.txt"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) == 19 and parts[6] == "P" and parts[10] == admin1:
            keep.add(int(parts[0]))

    # The largest cities worldwide, for international coverage.
    largest: list[tuple[int, int]] = []
    for line in open_text(config.raw_dir / "cities500.zip", "cities500.txt"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) == 19:
            largest.append((int(parts[14] or 0), int(parts[0])))
    largest.sort(reverse=True)
    keep.update(gid for _pop, gid in largest[:FIXTURE_TOP_WORLD_CITIES])

    return keep


def record_metadata(
    connection: sqlite3.Connection, config: BuildConfig, stats: ImportStats
) -> None:
    """Write one provenance row per input dataset, plus the timezone source."""
    download_date = dt.date.today().isoformat()
    rows = []
    for expected in EXPECTED_INPUTS:
        path = config.raw_dir / expected.filename
        transformations = {
            "places": (
                "streamed 19-column dump; cities500 imported whole; country "
                "packs filtered to feature_class='P' and deduped against "
                "cities500 by geoname_id; names normalized (NFKD, combining "
                "marks stripped, casefolded, whitespace collapsed)"
            ),
            "alternates": (
                "filtered to imported geoname_ids; isolanguage in "
                "(link, wkdt, post, iata, icao, faac, unlc, abbr, fr_1793) "
                "dropped; names normalized as above"
            ),
            "countries": (
                "imported whole; ISO alpha-2/alpha-3 and normalized country "
                "names registered as query aliases; PROJECT-SPECIFIC alias map "
                "(uk->GB, usa/united states/u.s.a.->US, england->GB) added by "
                "this project, NOT GeoNames data"
            ),
            "admin1": "imported whole; names normalized as above",
            "admin2": "imported whole; names normalized as above",
        }[expected.kind]

        rows.append(
            (
                expected.filename,
                GEONAMES_BASE_URL + expected.source_path,
                SOURCE_RELEASE,
                PROVENANCE,
                download_date,
                sha256_of(path),
                GEONAMES_LICENSE,
                GEONAMES_ATTRIBUTION,
                transformations,
                stats.get(f"rows_{expected.filename}", 0),
                IMPORTER_VERSION,
            )
        )

    import timezonefinder
    from timezonefinder import TimezoneFinder

    try:
        from importlib.metadata import version as _pkg_version

        tzf_version = _pkg_version("timezonefinder")
    except Exception:  # pragma: no cover
        tzf_version = "unknown"

    rows.append(
        (
            "timezone boundaries (timezonefinder)",
            "https://pypi.org/project/timezonefinder/",
            f"as bundled with timezonefinder {tzf_version} "
            f"({len(TimezoneFinder().timezone_names)} timezone names)",
            "installed from PyPI; boundary data ships inside the package",
            download_date,
            "n/a (package data, not a downloaded file)",
            "timezonefinder MIT; bundled boundary data ODbL "
            "(timezone-boundary-builder)",
            "Timezone boundaries from the timezone-boundary-builder project, "
            "as distributed with timezonefinder.",
            "not imported into this database; queried live at resolve time "
            "from place coordinates",
            len(TimezoneFinder().timezone_names),
            IMPORTER_VERSION,
        )
    )

    connection.executemany(
        "INSERT INTO dataset_metadata VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
    )
    connection.commit()


def build(fixture: bool = False, extra_fixture_ids: set[int] | None = None) -> Path:
    config = BuildConfig()
    print("Verifying inputs...")
    reports = verify(config, verbose=False)
    print("  all inputs verified\n")

    stats = ImportStats()
    for report in reports:
        stats[f"rows_{report.filename}"] = report.total_rows
    keep = None
    if fixture:
        keep = select_fixture_ids(config, extra_fixture_ids or set())
        print(f"Fixture slice: {len(keep)} candidate geoname_ids\n")

    config.out_dir.mkdir(parents=True, exist_ok=True)
    config.fixture_path.parent.mkdir(parents=True, exist_ok=True)

    if fixture:
        final_path = config.fixture_path
    else:
        stamp = dt.date.today().strftime("%Y%m%d")
        final_path = config.out_dir / f"geodata-{stamp}.sqlite"
    tmp_path = final_path.with_suffix(".sqlite.tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    connection = sqlite3.connect(tmp_path)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")

    try:
        create_schema(connection)
        print("Importing places...")
        kept_ids = import_places(connection, config, stats, keep)
        print(f"  {len(kept_ids)} places")

        print("Indexing official and ascii names...")
        import_official_names(connection, stats)

        print("Importing alternate names...")
        import_alternate_names(connection, config, stats, kept_ids)

        print("Importing countries and admin codes...")
        import_countries(connection, config, stats)
        restrict = None
        if fixture:
            restrict = {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT country_code FROM places"
                )
                if row[0]
            }
        import_admin_codes(connection, config, stats, restrict)

        print("Creating indexes...")
        create_indexes(connection)

        record_metadata(connection, config, stats)

        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"integrity_check failed: {integrity}")
        connection.execute("VACUUM")
        connection.commit()
    finally:
        connection.close()

    os.replace(tmp_path, final_path)
    print(f"\nWrote {final_path} ({final_path.stat().st_size} bytes)")

    if not fixture:
        stable = config.out_dir / "geodata.sqlite"
        shutil.copy2(final_path, stable)
        print(f"Copied to {stable}")

    print("\n--- import statistics ---")
    for key in sorted(stats):
        print(f"  {key}: {stats[key]}")
    return final_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument(
        "--extra-id", type=int, action="append", default=[],
        help="extra geoname_id to include in the fixture slice",
    )
    args = parser.parse_args()
    build(fixture=args.fixture, extra_fixture_ids=set(args.extra_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
