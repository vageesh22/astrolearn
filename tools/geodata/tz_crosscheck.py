"""Compare each place's GeoNames timezone against a spatial lookup.

The database stores the GeoNames ``timezone`` column purely for this QA check.
The runtime never reads it: it looks the timezone up spatially from the place's
coordinates at resolve time. This tool quantifies how far the two disagree, so
the decision to trust the spatial lookup is an evidenced one rather than an
assumption.

A disagreement is not automatically a defect. GeoNames assigns a zone by
administrative association; timezonefinder assigns it by which boundary polygon
contains the point. Near a boundary, or for a place whose coordinates sit just
across a line from its administrative centre, the two legitimately differ.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# .config must come first: importing it puts src/ on sys.path so the runtime
# normalizer and timezone lookup can be shared with the importer.
from .config import BuildConfig
from vedic_chart.location.offline.tz_lookup import TimezoneLookupError  # noqa: E402
from vedic_chart.location.offline.tz_lookup import lookup as spatial_lookup  # noqa: E402


def crosscheck(db_path: Path, report_path: Path, limit: int | None = None) -> dict:
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row

    sql = (
        "SELECT geoname_id, name, country_code, latitude, longitude, "
        "geonames_tz FROM places"
    )
    if limit:
        sql += f" LIMIT {limit}"

    total = 0
    mismatches = 0
    errors = 0
    blank = 0
    examples: list[tuple] = []

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as report:
        report.write(
            "geoname_id\tname\tcountry\tlatitude\tlongitude\t"
            "geonames_tz\tspatial_tz\n"
        )
        for row in connection.execute(sql):
            total += 1
            geonames_tz = row["geonames_tz"] or ""
            if not geonames_tz:
                blank += 1
            try:
                spatial_tz = spatial_lookup(row["latitude"], row["longitude"])
            except TimezoneLookupError:
                errors += 1
                spatial_tz = "<no zone>"
            if spatial_tz != geonames_tz:
                mismatches += 1
                line = (
                    f"{row['geoname_id']}\t{row['name']}\t{row['country_code']}\t"
                    f"{row['latitude']}\t{row['longitude']}\t{geonames_tz}\t"
                    f"{spatial_tz}\n"
                )
                report.write(line)
                if len(examples) < 25:
                    examples.append(
                        (
                            row["geoname_id"],
                            row["name"],
                            row["country_code"],
                            geonames_tz,
                            spatial_tz,
                        )
                    )
    connection.close()

    percent = 100.0 * mismatches / total if total else 0.0
    return {
        "total": total,
        "mismatches": mismatches,
        "percent": percent,
        "lookup_errors": errors,
        "blank_geonames_tz": blank,
        "examples": examples,
        "report_path": report_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    config = BuildConfig()
    db_path = Path(args.db) if args.db else config.out_dir / "geodata.sqlite"
    stats = crosscheck(db_path, config.tz_report_path, args.limit)

    print(f"places checked      : {stats['total']}")
    print(f"mismatches          : {stats['mismatches']} ({stats['percent']:.3f}%)")
    print(f"spatial lookup errors: {stats['lookup_errors']}")
    print(f"blank geonames_tz   : {stats['blank_geonames_tz']}")
    print(f"report              : {stats['report_path']}")
    print("\nexamples:")
    for example in stats["examples"][:5]:
        print(f"  {example[0]:>9}  {example[1][:26]:<26} {example[2]}  "
              f"{example[3]} -> {example[4]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
