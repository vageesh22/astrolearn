# Data sources, licensing and provenance

This project builds a local geocoding database from GeoNames dumps and resolves
timezones with `timezonefinder`. Nothing is fetched at runtime. This file
records where the data came from, what was done to it, and what the licences
require.

## Provenance of this build

The six GeoNames files were **supplied out-of-band by the project owner from
the official `download.geonames.org` URLs**, because this build environment's
network policy does not permit reaching `geonames.org`. They were not fetched by
the tooling, and `tools/geodata/verify_inputs.py` therefore recomputes and
checks every SHA-256 before the importer reads a byte. The same provenance
string is stored in the database's `dataset_metadata` table.

**Upstream release:** the 2026-09-04 daily dump. The inner `.txt` members of all
three archives carry a 2026-09-04 timestamp, consistent with that.

## Datasets

| File | SHA-256 | Bytes | Rows | Source URL |
|---|---|---:|---:|---|
| `cities500.zip` | `a7c0b85b…a5a84a` | 13,598,403 | 235,669 | `https://download.geonames.org/export/dump/cities500.zip` |
| `IN.zip` | `af2c41e2…a967bc` | 15,747,411 | 660,026 | `https://download.geonames.org/export/dump/IN.zip` |
| `IN-alternatenames.zip` | `7fbb361c…2439fe` | 1,365,984 | 121,543 | `https://download.geonames.org/export/dump/alternatenames/IN.zip` |
| `admin1CodesASCII.txt` | `59065149…a5448c` | 151,536 | 3,865 | `https://download.geonames.org/export/dump/admin1CodesASCII.txt` |
| `admin2Codes.txt` | `fe8196f9…b48aba` | 2,373,027 | 47,593 | `https://download.geonames.org/export/dump/admin2Codes.txt` |
| `countryInfo.txt` | `93bafc52…d5512` | 31,678 | 252 | `https://download.geonames.org/export/dump/countryInfo.txt` |

Full checksums are stored in `dataset_metadata` inside the built database.

**Coverage.** `cities500` gives every populated place of 500+ inhabitants
worldwide. `IN.zip` adds *every* populated place in India, down to village
level, which is the point of the India pack. More countries can be added by
appending to `COUNTRY_PACKS` in `tools/geodata/config.py` and dropping the
matching `<CC>.zip` and `<CC>-alternatenames.zip` into `data/raw/`.

### Timezone boundaries

Timezones are resolved spatially by **`timezonefinder` 8.2.0** (MIT), installed
from PyPI. Its boundary polygons ship inside the package, so the lookup is
offline. The underlying dataset is the **timezone-boundary-builder** release
**as bundled with timezonefinder 8.2.0** — the package exposes no release tag
or `__version__` programmatically, so no specific tag is claimed here. The one
determinable fingerprint is that it carries **444 timezone names**, recorded in
`dataset_metadata`.

The boundary data is **not imported** into our database. It is queried live from
a place's coordinates at resolve time.

## Transformations we applied

These are our changes, not GeoNames data:

1. **Filtering.** Country packs are reduced to `feature_class = 'P'` (populated
   places); 102,031 non-P rows were dropped from `IN.txt`.
2. **Deduplication.** `cities500` is loaded first and wins; the India pack then
   contributes only what it lacks. 7,112 India rows were dropped as duplicates.
3. **Name normalization.** Every stored and queried name is casefolded,
   NFKD-decomposed with combining marks stripped, whitespace-collapsed and
   edge-punctuation-trimmed, so "Jālandhar" and "jalandhar" match. The importer
   and the query path share one implementation
   (`vedic_chart.location.offline.normalize`).
4. **Alternate-name filtering.** Rows in the pseudo-languages `link`, `wkdt`,
   `post`, `iata`, `icao`, `faac`, `unlc`, `abbr` and `fr_1793` are dropped —
   they are identifiers and URLs, not names. 13,373 rows dropped this way;
   46,604 more referenced geonameids we did not import.
5. **Country alias map — entirely ours.** GeoNames does not supply these:
   `uk → GB`, `usa → US`, `united states → US`, `u.s.a. → US`, `england → GB`.
   They exist because people type them. They are recorded with
   `origin = 'project alias map'` in the `country_aliases` table, distinct from
   the ISO codes and country names sourced from `countryInfo.txt`.
6. **The GeoNames `timezone` column is stored but never used at runtime.** It is
   kept solely so `tools/geodata/tz_crosscheck.py` can measure disagreement
   against the spatial lookup.

## Licensing — three distinct things

**1. The source data.** GeoNames dumps are licensed **CC BY 4.0**. Attribution
is required wherever the data or anything derived from it is distributed:

> This product includes GeoNames data (https://www.geonames.org/), licensed
> under Creative Commons Attribution 4.0.

**2. The derived database.** `data/geodata-*.sqlite` and the committed
`tests/fixtures/geodata_fixture.sqlite` are derived works of the GeoNames dumps,
so the CC BY 4.0 attribution obligation travels with them.

The timezone boundary data is **ODbL**, which is share-alike. That obligation
attaches only if a *derived database* containing that data is distributed — and
we do not: we neither import nor redistribute the boundary polygons. They stay
inside the `timezonefinder` package, which carries its own licence. If a future
build ever bakes spatial timezone results into our database, the resulting
database would become ODbL-encumbered and share-alike would apply. It does not
today.

**3. Our code.** The importer and resolver are our own work. Note that this is
*not* the project's binding licence constraint: **the Swiss Ephemeris and
pyswisseph are AGPL-3.0**, which already governs the project as a whole and is
the strictest term in play. Running this code as a closed-source network service
requires a commercial Swiss Ephemeris licence from Astrodienst regardless of
anything on this page.

**tzdata**, used by Layer 3 via `zoneinfo` for the actual offset *rules*, is
public domain.

## Rebuilding

```
python -m tools.geodata.verify_inputs     # checksums + structural validation
python -m tools.geodata.build_db          # production database
python -m tools.geodata.verify_db         # QA gate
python -m tools.geodata.build_db --fixture   # the committed test fixture
```
