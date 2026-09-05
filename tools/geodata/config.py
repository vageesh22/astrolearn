"""Build configuration for the geodata database.

Ranking weights and dominance thresholds are deliberately NOT here: they belong
to the runtime (``vedic_chart.location.offline.search.RankingConfig``), because
they govern query behaviour rather than how the database is built.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# The tools import the runtime's normalizer so importer and query path share
# exactly one definition of "the same name".
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

IMPORTER_VERSION = "1.0.0"

GEONAMES_BASE_URL = "https://download.geonames.org/export/dump/"

# The dump these inputs came from. Recorded in dataset_metadata.
SOURCE_RELEASE = "2026-09-04 daily dump"
PROVENANCE = (
    "supplied out-of-band by project owner from official "
    "download.geonames.org URLs"
)

GEONAMES_LICENSE = "CC BY 4.0"
GEONAMES_ATTRIBUTION = (
    "This product includes GeoNames data (https://www.geonames.org/), "
    "licensed under Creative Commons Attribution 4.0."
)

# Countries given full GeoNames coverage (all populated places), on top of the
# worldwide cities500 baseline. Add an entry here and drop its <CC>.zip and
# <CC>-alternatenames.zip into data/raw/ to extend coverage.
COUNTRY_PACKS: tuple[str, ...] = ("IN",)

# Alternate-name rows in these pseudo-languages are identifiers and URLs, not
# names a person would ever type.
EXCLUDED_ISOLANGUAGES = frozenset(
    {"link", "wkdt", "post", "iata", "icao", "faac", "unlc", "abbr", "fr_1793"}
)

# Our own transformation, not GeoNames data: colloquial country names people
# type that the official country list does not contain.
COUNTRY_ALIAS_MAP: dict[str, str] = {
    "uk": "GB",
    "usa": "US",
    "united states": "US",
    "u.s.a.": "US",
    "england": "GB",
}


@dataclass(frozen=True)
class ExpectedInput:
    """One required input file and the checksum it must have."""

    filename: str
    sha256: str
    source_path: str
    inner_txt: str | None = None
    kind: str = "places"


EXPECTED_INPUTS: tuple[ExpectedInput, ...] = (
    ExpectedInput(
        "cities500.zip",
        "a7c0b85bb699e55a1c258fe91cb5fd5a60871fc6467c6f8fc0955b6eeda5a84a",
        "cities500.zip",
        "cities500.txt",
        "places",
    ),
    ExpectedInput(
        "IN.zip",
        "af2c41e229ccff147382f42abc9e956e37d67d3b3a3cfe3c9beccf6db3a967bc",
        "IN.zip",
        "IN.txt",
        "places",
    ),
    ExpectedInput(
        "IN-alternatenames.zip",
        "7fbb361c02c997c43a2c04cd76b12619bc0403280a9a0494f93dde83542439fe",
        "alternatenames/IN.zip",
        "IN.txt",
        "alternates",
    ),
    ExpectedInput(
        "admin1CodesASCII.txt",
        "590651498043f674accda2b7f46d21286cda0e290b02f8561c5005eee9a5448c",
        "admin1CodesASCII.txt",
        None,
        "admin1",
    ),
    ExpectedInput(
        "admin2Codes.txt",
        "fe8196f90676f40a8845f24cc0687dadc668fe8c0f9de6458da65fda50b48aba",
        "admin2Codes.txt",
        None,
        "admin2",
    ),
    ExpectedInput(
        "countryInfo.txt",
        "93bafc525813f22e4711ff9ed6d626343094ce48c26388dc7c49189b3d7d5512",
        "countryInfo.txt",
        None,
        "countries",
    ),
)


@dataclass(frozen=True)
class BuildConfig:
    """Where the build reads from and writes to."""

    project_root: Path = PROJECT_ROOT
    raw_dir: Path = field(default=PROJECT_ROOT / "data" / "raw")
    work_dir: Path = field(default=PROJECT_ROOT / "data" / "work")
    out_dir: Path = field(default=PROJECT_ROOT / "data")
    fixture_path: Path = field(
        default=PROJECT_ROOT / "tests" / "fixtures" / "geodata_fixture.sqlite"
    )
    tz_report_path: Path = field(
        default=PROJECT_ROOT / "data" / "tz_mismatch_report.txt"
    )
    country_packs: tuple[str, ...] = COUNTRY_PACKS
