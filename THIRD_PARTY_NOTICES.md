# Third-Party Notices

This project (the AstroLearn Vedic Chart Engine) is licensed under the GNU Affero General
Public License v3.0 — see `LICENSE`. It depends on, or redistributes, the following
third-party components. Nothing in this file grants any right beyond those licenses.

## Swiss Ephemeris (Astrodienst AG) — redistributed data files

`ephe/sepl_18.se1`, `ephe/semo_18.se1`, `ephe/seas_18.se1` are unmodified Swiss Ephemeris
data files, Copyright (C) 1997–2021 Astrodienst AG, Switzerland. Swiss Ephemeris is offered
under a dual licensing system: (a) the GNU Affero General Public License, or (b) the Swiss
Ephemeris Professional License. **This project has chosen option (a), AGPL**, and is
accordingly licensed as a whole under the AGPL-3.0. The original license notice is preserved
verbatim in `ephe/SWISSEPH_LICENSE.txt`, as that notice requires. Per the same notice, the
names of the Swiss Ephemeris authors and of Astrodienst are not used to promote this software;
they appear only in these license notices. Should this engine ever be offered as a
closed-source network service, option (b) would have to be purchased from Astrodienst instead.

## pyswisseph (Stanislas Marquis) — dependency, not redistributed

Python binding to Swiss Ephemeris, licensed under the GNU Affero General Public License v3
(`pyswisseph==2.10.3.2`, https://astrorigin.com/pyswisseph). Installed from PyPI at build
time; not included in this repository.

## timezonefinder (Jannik Michelfeit) — dependency, not redistributed

MIT License (`timezonefinder==8.2.0`). Its bundled timezone-boundary data is derived from
timezone-boundary-builder / OpenStreetMap under the Open Database License (ODbL) 1.0. This
repository stores no boundary polygons and no spatial results, so ODbL share-alike does not
attach to any file here; see `data/DATA_SOURCES.md`.

## GeoNames — redistributed in derived form (test fixture)

`tests/fixtures/geodata_fixture.sqlite` is a database derived from the GeoNames gazetteer
(https://www.geonames.org/), licensed under the Creative Commons Attribution 4.0 International
License (https://creativecommons.org/licenses/by/4.0/). Attribution: "This product includes
data from GeoNames (geonames.org), licensed CC BY 4.0." The data has been modified: filtered,
normalized and reorganized into SQLite as described in `data/DATA_SOURCES.md`, which also
records the source release (2026-09-04 dump) and SHA-256 checksums. The production database
built by `tools/geodata/` is not part of this repository and carries the same attribution.

## IANA Time Zone Database

Consumed through the operating system's `tzdata` package via Python's `zoneinfo`; public
domain. Not redistributed.
