"""Verify the GeoNames inputs before anything reads them.

This does NOT download. The dumps are placed in data/raw/ by hand; this module
proves they are the files they claim to be and are structurally what the
importer expects, so a truncated or substituted file fails loudly here rather
than producing a quietly wrong database.
"""

import csv
import hashlib
import io
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .config import EXPECTED_INPUTS, BuildConfig, ExpectedInput

csv.field_size_limit(10**7)

GEONAME_COLUMNS = 19
ALTERNATE_COLUMNS_MIN = 8
ALTERNATE_COLUMNS_MAX = 10
STRUCTURAL_SAMPLE_ROWS = 1000


class InputVerificationError(RuntimeError):
    """An input file is missing, corrupt, or not the expected format."""


@dataclass
class InputReport:
    filename: str
    size_bytes: int
    sha256: str
    sha256_matches: bool
    zip_ok: bool | None
    inner_name: str | None
    inner_size: int | None
    total_rows: int
    notes: list[str]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_text(path: Path, inner: str | None):
    """Yield decoded lines from a .txt or from a named member of a .zip."""
    if inner is None:
        with path.open(encoding="utf-8", errors="strict") as handle:
            yield from handle
        return
    with zipfile.ZipFile(path) as archive:
        with archive.open(inner) as raw:
            with io.TextIOWrapper(raw, encoding="utf-8", errors="strict") as text:
                yield from text


def _check_geoname_rows(path: Path, inner: str, notes: list[str]) -> int:
    """Validate the 19-column geoname format, and count rows."""
    total = 0
    for index, line in enumerate(open_text(path, inner)):
        parts = line.rstrip("\n").split("\t")
        total += 1
        if index < STRUCTURAL_SAMPLE_ROWS:
            if len(parts) != GEONAME_COLUMNS:
                raise InputVerificationError(
                    f"{path.name}:{inner} row {index + 1} has {len(parts)} "
                    f"columns, expected {GEONAME_COLUMNS}."
                )
            if not parts[0].isdigit():
                raise InputVerificationError(
                    f"{path.name}:{inner} row {index + 1} geonameid "
                    f"{parts[0]!r} is not numeric."
                )
            try:
                latitude = float(parts[4])
                longitude = float(parts[5])
            except ValueError as exc:
                raise InputVerificationError(
                    f"{path.name}:{inner} row {index + 1} has unparseable "
                    f"coordinates ({parts[4]!r}, {parts[5]!r})."
                ) from exc
            if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
                raise InputVerificationError(
                    f"{path.name}:{inner} row {index + 1} coordinates out of "
                    f"range: {latitude}, {longitude}."
                )
            if len(parts[6]) > 1 or (parts[6] and not parts[6].isalpha()):
                raise InputVerificationError(
                    f"{path.name}:{inner} row {index + 1} feature class "
                    f"{parts[6]!r} is not a single letter."
                )
    notes.append(f"{GEONAME_COLUMNS}-column geoname format verified on first "
                 f"{min(total, STRUCTURAL_SAMPLE_ROWS)} rows")
    return total


def _check_alternate_rows(
    path: Path, inner: str, notes: list[str], known_ids: set[int] | None
) -> int:
    """Validate the alternateNamesV2 format, and count rows."""
    total = 0
    referenced = 0
    sampled_ids: list[int] = []
    for index, line in enumerate(open_text(path, inner)):
        parts = line.rstrip("\n").split("\t")
        total += 1
        if index < STRUCTURAL_SAMPLE_ROWS:
            if not (ALTERNATE_COLUMNS_MIN <= len(parts) <= ALTERNATE_COLUMNS_MAX):
                raise InputVerificationError(
                    f"{path.name}:{inner} row {index + 1} has {len(parts)} "
                    f"columns, expected {ALTERNATE_COLUMNS_MIN}-"
                    f"{ALTERNATE_COLUMNS_MAX} (alternateNamesV2)."
                )
            if not parts[0].isdigit() or not parts[1].isdigit():
                raise InputVerificationError(
                    f"{path.name}:{inner} row {index + 1} has non-numeric "
                    f"alternateNameId/geonameid ({parts[0]!r}, {parts[1]!r})."
                )
            sampled_ids.append(int(parts[1]))
        if known_ids is not None and len(parts) > 1 and parts[1].isdigit():
            if int(parts[1]) in known_ids:
                referenced += 1

    notes.append(
        "alternateNamesV2 format verified on first "
        f"{min(total, STRUCTURAL_SAMPLE_ROWS)} rows"
    )
    if known_ids is not None:
        if referenced == 0:
            raise InputVerificationError(
                f"{path.name}:{inner} references no geonameid present in the "
                "country places file: this is not the matching per-country "
                "alternate-names file."
            )
        percent = 100.0 * referenced / total if total else 0.0
        notes.append(
            f"{referenced} of {total} rows ({percent:.1f}%) reference a "
            "geonameid in the country places file"
        )
    return total


def load_geoname_ids(path: Path, inner: str) -> set[int]:
    ids: set[int] = set()
    for line in open_text(path, inner):
        head, _, _ = line.partition("\t")
        if head.isdigit():
            ids.add(int(head))
    return ids


def verify(config: BuildConfig | None = None, verbose: bool = True) -> list[InputReport]:
    """Verify every expected input. Raises InputVerificationError on any problem."""
    config = config or BuildConfig()
    reports: list[InputReport] = []

    # The India places file is needed to prove the alternate file matches it.
    india_ids: set[int] | None = None
    india_zip = config.raw_dir / "IN.zip"
    if india_zip.is_file():
        india_ids = load_geoname_ids(india_zip, "IN.txt")

    for expected in EXPECTED_INPUTS:
        path = config.raw_dir / expected.filename
        notes: list[str] = []

        if not path.is_file():
            raise InputVerificationError(
                f"Required input {expected.filename} not found in "
                f"{config.raw_dir}."
            )

        digest = sha256_of(path)
        matches = digest == expected.sha256
        if not matches:
            raise InputVerificationError(
                f"{expected.filename} sha256 mismatch.\n  expected "
                f"{expected.sha256}\n  actual   {digest}"
            )

        zip_ok: bool | None = None
        inner_size: int | None = None
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                bad = archive.testzip()
                zip_ok = bad is None
                if not zip_ok:
                    raise InputVerificationError(
                        f"{expected.filename} failed integrity test at {bad}."
                    )
                info = archive.getinfo(expected.inner_txt)
                inner_size = info.file_size
                notes.append(
                    f"inner {expected.inner_txt} {inner_size} bytes, "
                    f"dated {info.date_time[0]:04d}-{info.date_time[1]:02d}-"
                    f"{info.date_time[2]:02d}"
                )

        if expected.kind == "places":
            total = _check_geoname_rows(path, expected.inner_txt, notes)
        elif expected.kind == "alternates":
            total = _check_alternate_rows(
                path, expected.inner_txt, notes, india_ids
            )
        else:
            total = sum(
                1
                for line in open_text(path, expected.inner_txt)
                if not line.startswith("#")
            )
            notes.append("plain tab-separated reference file")

        report = InputReport(
            filename=expected.filename,
            size_bytes=path.stat().st_size,
            sha256=digest,
            sha256_matches=matches,
            zip_ok=zip_ok,
            inner_name=expected.inner_txt,
            inner_size=inner_size,
            total_rows=total,
            notes=notes,
        )
        reports.append(report)

        if verbose:
            print(f"[ok] {report.filename}")
            print(f"     {report.size_bytes} bytes  sha256 {digest[:16]}... MATCH")
            print(f"     rows: {report.total_rows}")
            for note in notes:
                print(f"     - {note}")

    return reports


if __name__ == "__main__":
    try:
        verify()
    except InputVerificationError as error:
        print(f"INPUT VERIFICATION FAILED:\n{error}", file=sys.stderr)
        raise SystemExit(1)
    print("\nAll inputs verified.")
