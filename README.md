# vedic-chart-backend

## What this is

The foundation of a Vedic astrology chart backend. It turns a stated birth —
a date, a wall time and a place — into an exact UTC instant, then into raw
astronomical positions for the classical bodies, rotates those into the Lahiri
sidereal frame, classifies them into the rashis, nakshatras and padas of the
nine grahas, computes the sidereal Lagna and Whole Sign houses, and assembles
one immutable `BirthChart` (Layer 8). Layer 9 turns that chart into a canonical,
format-neutral D1 representation for renderers to draw. Aspects, dashas, yogas,
divisional charts beyond D1, interpretation and the renderers themselves are not
built.

## Target architecture

The finished system is planned as nine strictly separated layers:

1. Input (birth date, time, place as given by the user) — **built**
2. Geocoding (place name to latitude/longitude) — **built** (offline GeoNames geocoder)
3. Timezone (local civil time to UTC, including historical rules) — **built**
4. Julian Day (UTC to Julian Day in Universal Time) — **built**
5. Swiss Ephemeris (Julian Day to raw tropical geocentric positions) — **built**
6. Sidereal (tropical to sidereal via an ayanamsha) — **built**
7. Vedic (signs, nakshatras, padas, grahas) — **built**, with the Lagna and Whole Sign houses
8. Chart assembly (one immutable BirthChart) — **built**
9. Canonical D1 representation (`vedic_chart.representation`) — **built**

**All nine layers are now built**, plus a thin position API
(`vedic_chart.astronomy`) composing 4 and 5, and a Lagna layer
(`vedic_chart.lagna`) giving the sidereal ascendant and Whole Sign houses.
**Renderers are not built** — no North/South/East Indian diagram, no table,
no JSON shape, no HTML. Layer 9 is the boundary they will consume.

Still out of scope, with no code and no stubs: aspects, dashas, yogas,
divisional charts beyond D1, any interpretation, HTTP endpoints, persistence,
and every visual/geometric format concern.
A caller states a birth as a date, a wall time and a place query (Layer 1), and
Layer 8 returns a finished `BirthChart`.

## The public API

```python
from vedic_chart.astronomy.positions import Body, ephemeris_session
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.static_resolver import StaticLocationResolver
from vedic_chart.sidereal.positions import calculate_sidereal_positions
from vedic_chart.time.local_time import normalize_birth_time

# Layer 1: what the caller asked for, validated.
request = BirthChartRequest.from_components(
    2000, 1, 1, 17, 30, place_query="Jalandhar"
)

# Layer 2: a place -> coordinates and an IANA timezone identifier.
place = StaticLocationResolver().resolve(request.place_query)

# Layer 3: the local wall time plus that zone -> an exact UTC instant.
moment = normalize_birth_time(
    request.birth_date, request.birth_time, place.timezone_id
)

with ephemeris_session("ephe"):
    result = calculate_sidereal_positions(moment)

print(result.ayanamsa)                                  # 23.853222
sun = result.bodies[Body.SUN]
print(sun.tropical.longitude, sun.sidereal_longitude)   # 280.368919 256.515696
print(sun.tropical.speed_longitude)                     # 1.019434
```

`vedic_chart.astronomy.positions.calculate_positions` remains available on its
own when the raw tropical frame is what you want.

This is a Python module API. There is no HTTP layer and none is planned for this
stage.

### `vedic_chart.inputs` (Layer 1)

`BirthChartRequest` is what a caller asked for, validated but not interpreted:
a `birth_date`, a naive `birth_time` and a `place_query` string. It is frozen,
and it validates on construction:

- `birth_date` must be a `datetime.date` and explicitly **not** a `datetime`.
  Since `datetime` subclasses `date`, an unchecked field would happily accept
  one — and an aware `datetime` would carry a timezone straight past Layer 3,
  the only layer entitled to resolve one.
- `birth_time` must be a naive `datetime.time`. An aware time would be a second,
  competing source of zone truth alongside the resolved place.
- `place_query` must be a non-blank string, and is stored **verbatim**.
  Surrounding whitespace is preserved rather than trimmed, because normalizing
  queries belongs to the resolver.

`BirthChartRequest.from_components(year, month, day, hour, minute, second=0,
microsecond=0, *, place_query=...)` is the typed rejection surface for raw
numbers. An already-constructed `date` or `time` cannot be invalid — the
standard library refuses to build one — so `__post_init__` can only check kinds
of value, never ranges. Callers holding raw components (a form submission, a
parsed record) come through the factory and get `InvalidBirthDateError` or
`InvalidBirthTimeError` for February 30th or hour 24, rather than a bare
`ValueError` from inside `datetime`. `InvalidPlaceQueryError` covers the third
field, and all three subclass `ValueError` per project convention.

**What the model deliberately excludes:** latitude, longitude, UTC offsets,
timezone identifiers, and aware datetimes. A request describes a birth *as
stated*. Accepting any of those here would let a caller bypass Layer 2's
coordinate validation or Layer 3's gap-and-overlap checks and inject an
unvalidated instant into the pipeline. The layer is pure stdlib and imports
nothing from the project at all — not even `zoneinfo`, since timezone concepts
should not exist at this level. The test suite enforces that by parsing the
module's import statements.

### `vedic_chart.location` (Layer 2)

Layer 2 is the birth-place boundary. It is built as a boundary first and
deliberately has no geocoding provider behind it yet.

`ResolvedLocation` is the whole contract the calculation engine sees: a
`canonical_name`, a `latitude` (north-positive) and `longitude`
(east-positive) in degrees, and a `timezone_id`. It is frozen, and it validates
on construction — latitude within ±90 and longitude within ±180 inclusive, both
finite, or `InvalidCoordinateError`; a non-blank name; and an IANA identifier
the system tzdata accepts, or `InvalidTimezoneError`. That is the *same*
exception Layer 3 raises, imported rather than redefined, so one condition has
one type across the codebase.

**An identifier is stored, never a UTC offset.** A place's offset is not a
property of the place — it changes with the date, because zones revise their
rules over time. India ran +06:30 during the second world war and +05:30 since.
An offset frozen into this model would be silently wrong for some birth dates.
Turning an identifier into an offset *for a particular instant* is Layer 3's
job, and only Layer 3 has the instant required to do it correctly.

**`LocationResolver` is where a provider will plug in.** It is a
`runtime_checkable` `Protocol` with a single method,
`resolve(place_query) -> ResolvedLocation`, raising `PlaceNotFoundError` when a
query cannot be resolved. An external geocoding provider will implement this
protocol later; that choice is deliberately deferred, and nothing in the
calculation engine should ever depend on a concrete provider — only on the
protocol and on `ResolvedLocation`. Swapping a real provider in should require
no change to any calculation layer.

**`StaticLocationResolver` is for tests and development only.** It is not a
geocoding service. It knows five hardcoded places — New Delhi, Jalandhar, New
York, London and Tokyo — makes no network calls, and does no fuzzy or partial
matching. It remains useful as a trivial stand-in; the real implementation is
the offline geocoder below.

The layer imports nothing from the ephemeris, astronomy, sidereal or vedic
modules, and the test suite enforces that by parsing the import statements
rather than trusting a convention.

### `vedic_chart.time.local_time` (Layer 3)

`normalize_birth_time(birth_date, birth_time, timezone_id) -> datetime` turns a
wall-clock date, a naive wall-clock time and an IANA timezone identifier into an
exact timezone-aware UTC datetime, ready for Layer 4.

The `time` package holds two distinct layers in separate modules: `local_time`
is Layer 3, `julian_day` is Layer 4. Both are pure stdlib — `datetime` and
`zoneinfo` — and neither knows anything about the ephemeris.

**Offsets come from the OS.** Zones are resolved with the standard library's
`zoneinfo`, which reads the operating system's tzdata database. Historical
offsets therefore reflect the installed tzdata version and can change when it is
updated. This machine resolves zones from `/usr/share/zoneinfo` (Debian/Ubuntu
tzdata 2026c); the `tzdata` pip package is not installed and is not a
dependency. India's wartime `+06:30` (1942–45), for instance, is asserted in the
tests as what the installed database reports, not as an independent authority.

**No timezone inference, ever.** The zone comes only from `timezone_id`, and
only identifiers the IANA database accepts are accepted. Nothing is guessed from
a country, a city, a place name or a bare offset, and this layer defines no
aliases of its own. Mapping a birth *place* to a timezone is Layer 2's job and
Layer 2 is not built. An unrecognized identifier raises `InvalidTimezoneError`.

**Ambiguous and nonexistent times are rejected, never resolved.** A wall time in
a spring-forward gap raises `NonexistentLocalTimeError`; one in a fall-back
overlap raises `AmbiguousLocalTimeError`. Both messages name the wall time, the
zone and the two candidate offsets, and both tell the caller to disambiguate —
typically by supplying an exact UTC instant. Silently picking one would bury an
hour-sized error inside a finished chart. Detection uses the standard `fold`
technique: the wall time is interpreted with `fold=0` and `fold=1`, and if the
offsets differ, a round trip through UTC separates the time that never happened
from the one that happened twice.

All three errors subclass `ValueError`, so a caller can catch them individually
or as a group. A timezone-aware `birth_time` is also rejected with `ValueError`:
the zone must have exactly one source.

**Nothing is rounded.** Seconds and microseconds pass through untouched. The
result feeds a Julian Day, where any adjustment here would move every computed
position.

### `vedic_chart.time.julian_day.julian_day_ut(moment) -> float`

Layer 4. Converts a timezone-aware datetime to a Julian Day in UT. Any aware
datetime is accepted and converted to UTC internally; a naive datetime raises
`ValueError` rather than having a timezone guessed for it. Pure stdlib — this
module imports neither `swisseph` nor anything from Layer 5.

Two documented approximations apply. **UTC is used as UT1**: leap seconds keep
the two within 0.9 s, which bounds the positional error at roughly 0.00015° even
for the Moon — far below any precision a chart depends on. And the calendar is
**proleptic Gregorian**, since Python's `datetime` extends the Gregorian rules
back past their 1582 adoption; pre-1582 dates will not match Julian-calendar
civil records.

### `vedic_chart.astronomy.positions`

- `Body` — an `Enum` of the nine computed bodies: `SUN`, `MOON`, `MERCURY`,
  `VENUS`, `MARS`, `JUPITER`, `SATURN`, `MEAN_NODE`, `TRUE_NODE`. Astronomical
  names only.
- `calculate_positions(moment_utc)` — converts the moment via `julian_day_ut`
  and returns a `dict[Body, PlanetPosition]` in `Body` definition order. The
  values are Layer 5's output passed through unchanged: raw tropical geocentric
  longitude, latitude, distance and the three corresponding speeds. Nothing is
  derived, flagged or interpreted.
- `ephemeris_session(ephe_path)` — a context manager that opens the ephemeris on
  entry and closes it on exit. A convenience over the Layer 5
  `init_ephemeris`/`close_ephemeris` pair; lifecycle is otherwise the caller's.

This module never imports `swisseph`. It reaches the library only through the
Layer 5 boundary.

### Both lunar nodes

Both the mean and the true node are computed, and both are returned. Which node
is treated as Rahu — and how Ketu is derived from it — is an astrological
decision that belongs to the Vedic layer, which does not exist yet. Nothing in
the current code makes that choice. The outer planets are not computed.

### `vedic_chart.sidereal.positions` (Layer 6)

The sidereal layer is one rotation and nothing else:

    sidereal_longitude = (tropical_longitude - ayanamsha) mod 360

- `sidereal_longitude(tropical_longitude, ayanamsa)` — the pure helper doing
  exactly that subtraction and wrap.
- `SiderealBodyPosition` — a body's `sidereal_longitude` beside the untouched
  `tropical` `PlanetPosition`.
- `SiderealPositions` — `julian_day_ut`, the `ayanamsa` used, and `bodies`, a
  dict keyed by `Body`.
- `calculate_sidereal_positions(moment_utc)` — takes the Julian Day, the
  tropical positions and the ayanamsha once each at the same instant, so every
  body is rotated by the same value.

**Where Lahiri comes from.** The ayanamsha value is not computed by this
project. It is asked of Swiss Ephemeris through the Layer 5 accessor
`get_ayanamsa_lahiri`, which calls `set_sid_mode(SIDM_LAHIRI, 0, 0)` and then
`get_ayanamsa_ut`. `SIDM_LAHIRI` is the library's built-in Lahiri/Chitrapaksha
ayanamsha — the one used by the Indian national ephemeris. No formula is
implemented or hardcoded anywhere in this codebase. `set_sid_mode` is global
library state, so the mode is set on every call rather than once at startup;
the `t0`/`ayan_t0` arguments are 0 because SIDM_LAHIRI is a predefined mode
that carries its own reference epoch. For reference, the library returns
22.465373° at 1900-01-01, 23.853222° at J2000 and 24.190855° at 2024-01-01 (true-equinox values, matching Jagannatha Hora's published Lahiri tables to the arcsecond).

**Tropical data is preserved.** Positions are still computed tropically —
`SEFLG_SIDEREAL` is not used anywhere, and Layer 5's raw output is unchanged.
Every sidereal result carries the original `PlanetPosition` alongside it, so
nothing downstream has to trust this layer to have kept the raw numbers intact.

**Speeds are not rotated.** Latitude, distance and all three speeds live in
`tropical` and are unaffected by the frame rotation. The ayanamsha drifts by
roughly 0.000038°/day, which is negligible against any speed of interest, so it
is deliberately not applied to the speeds.

Naming the result — signs, nakshatras, houses — is Layer 7's job and is not
built.

### `vedic_chart.vedic` (Layer 7)

Layer 7 implements the locked **AstroLearn Vedic D1 calculation specification**.
Its fifteen rules, in brief:

1. Rahu is the Mean Lunar Node.
2. Ketu is Rahu + 180°, normalized into [0, 360).
3. Ketu inherits Rahu's longitude speed.
4. The True Node stays available from Layer 6 but is not in the standard chart.
5. The rashis are 12 equal 30° divisions of the sidereal zodiac from 0° Mesha.
6. The rashi index is 0-based internally; output carries the 1-based number and
   the Sanskrit name.
7. 27 equal nakshatras, counted from Ashwini at 0° sidereal Aries.
8. `nakshatra_index = floor(longitude × 27 / 360)`.
9. `pada = floor(longitude × 108 / 360) % 4 + 1`.
10. All intervals are half-open, `[start, end)`.
11. Classification never rounds first.
12. No epsilon nudging.
13. Longitudes are normalized into [0, 360).
14. Full precision internally; degrees/minutes/seconds is a display concern and
    no display layer exists.
15. 27 nakshatras only — the Abhijit 28-nakshatra scheme is not used.

**Retrograde** is derived uniformly: `is_retrograde = speed_longitude < 0` for
every graha, with the raw speed kept alongside. Because Rahu is the Mean Node
(rule 1), whose motion is uniformly negative, the classical always-retrograde
convention for Rahu and Ketu falls out as a consequence rather than a hardcoded
special case. The True Node, by contrast, is genuinely direct at some epochs.

**Module layout.** `vedic/divisions.py` is pure: stdlib only, no imports from
any other layer, so the whole rashi/nakshatra/pada scheme is testable on plain
numbers. It exposes `RASHI_NAMES`, `NAKSHATRA_NAMES`, `normalize_longitude`,
`DivisionalPlacement` and `classify`. `vedic/grahas.py` composes it with Layer 6:
it exposes the `Graha` enum, `GrahaPosition` and `derive_grahas`, and never
imports `swisseph` or the ephemeris module.

**A note on boundaries.** A rashi boundary (30k) is always exactly representable
as a float, but a nakshatra boundary (40k/3) and a pada boundary (10k/3) are
only exact when k is a multiple of 3; the other 18 nakshatra boundaries are
irrational in binary and no float equals them. Rule 12 forbids nudging a value
across, so a longitude that rounds just below such a boundary is classified into
the lower division — which is correct for that value. The ambiguity is confined
to roughly one ULP, about 6×10⁻¹⁴ degrees, some ten orders of magnitude finer
than the ephemeris itself, so it cannot affect a real chart.

**Not built:** aspects, yogas, dashas, chart assembly, chart rendering, and any
degrees/minutes/seconds formatting. The lagna and houses are built — see below.

## Chart assembly (Layer 8)

`assemble_chart` composes the layers into one immutable `BirthChart`. It is the
entry point for anything built on top of this engine.

```python
from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.chart.assemble import assemble_chart
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.offline.resolver import OfflineLocationResolver

request = BirthChartRequest.from_components(
    1995, 3, 21, 6, 45, place_query="Jalandhar"
)

with OfflineLocationResolver("data/geodata.sqlite") as resolver:
    with ephemeris_session("ephe"):
        chart = assemble_chart(request, resolver)

print(chart.location.canonical_name)   # Jalandhar, Punjab, India
print(chart.moment_utc)                # 1995-03-21 01:15:00+00:00
print(chart.lagna.placement.rashi_name)  # Meena

for graha, house in chart.houses.items():
    placement = chart.grahas[graha].placement
    print(f"{graha.name:<8} {placement.rashi_name:<11} house {house}")
```

### It calculates nothing

Every value in a chart is produced by the layer that owns it; assembly is only
the wiring. The tests prove this rather than assert it in prose: `chart.grahas`,
`chart.lagna` and `chart.houses` are compared for equality against direct calls
to the underlying layers, and an AST test forbids the package from importing
`swisseph`, the ephemeris or astronomy layers, `vedic_chart.time.julian_day`,
`vedic_chart.vedic.divisions` or `zoneinfo`.

The Julian Day and ayanamsha are taken from the `SiderealPositions` already
computed, never recomputed — a second path to the same numbers is a second
chance for them to disagree. An internal guard raises `RuntimeError` if the
Lagna's ayanamsha ever differs from the planets'.

### The resolver is injected

`assemble_chart(request, resolver)` takes any `LocationResolver`, with no
default — the static resolver, the offline geocoder, or a future provider all
work unchanged. Choosing one inside this module would bury a real decision.

### The access contract

`chart.lagna`, `chart.grahas` and `chart.houses` are the stable surface for
future layers. A caller needs to know nothing about which ephemeris was
consulted, which ayanamsha was applied, or how the place was resolved.

Immutability is real, not nominal. `frozen=True` stops attributes being
rebound, but a plain dict field would still allow `chart.grahas[SUN] = ...`, so
both mappings are wrapped in a `MappingProxyType` **over a private copy** — the
copy matters as much as the proxy, or the dict the caller passed in would remain
a live handle into the chart. Assembly also validates that both mappings carry
exactly the nine grahas and every house is in 1..12.

### What it refuses to do

Errors from the layers below propagate untouched: an ambiguous or unknown place,
a nonexistent or ambiguous local time, a coordinate off the globe. Assembly has
no better answer than the layer that raised them, and swallowing one would hide
a real problem behind a half-built chart.

Ephemeris lifecycle stays the caller's job, so assembling many charts does not
reopen the ephemeris each time.

## Layer 9 — canonical D1 representation

`vedic_chart.representation` turns a finished `BirthChart` into a `D1Chart`: the
astrological *structure* of a D1 (Rashi) chart — which rashi sits in which
house, which grahas occupy it, where the Lagna is — in a form no visual layout
can bias. It is specified in `docs/LAYER9_D1_REPRESENTATION_SPEC.md`
(SPECIFICATION v1.0, approved 2026-09-06).

```
BirthChart (frozen, Layer 8)  ->  D1Chart (derived, immutable)  ->  Renderer(s)
```

```python
from vedic_chart.representation.d1 import build_d1_chart
from vedic_chart.vedic.grahas import Graha

d1 = build_d1_chart(chart)   # the BirthChart assembled above

print(d1.lagna.rashi_name, d1.lagna.dms())     # Meena 9°47'45"

for house in d1.houses:
    occupants = ", ".join(g.name for g in house.occupants) or "-"
    print(f"{house.number:>2}  {house.rashi_name:<11} {occupants}")

sun = d1.grahas[Graha.SUN]
print(sun.house, sun.rashi_name, sun.dms(2), sun.nakshatra_name, sun.pada)
print(d1.house_of(Graha.SUN).number, d1.house(8).occupants)
```

### Derived, never copied

`BirthChart` stays the single authority. `D1Chart` holds it as `source` and
exposes every value **by reference**: `d1.grahas[g].position is
chart.grahas[g]`, `d1.lagna.position is chart.lagna`, and each longitude *is*
the frozen float rather than a copy of it (the tests assert object identity, not
equality). Nothing is rounded and nothing is recomputed, so a representation
cannot drift from its chart; rebuilding it from the same chart yields an equal
object.

The only genuinely new data is structural: house *n* holds rashi
`(lagna_rashi_index + n − 1) mod 12`, and a house's `occupants` are the grahas
whose `BirthChart.houses[g]` is that number, in `Graha` enum order — so the
order never depends on how a mapping was built. An empty house is present with
`occupants == ()`, never omitted and never `None`. The Lagna is exposed once, as
`d1.lagna`, and is **never** an occupant. `D1Meta` adds the constant convention
labels (`sidereal`, `Lahiri (Chitrapaksha), true equinox`, `whole_sign`, `mean`,
the frozen engine spec) so a renderer can caption a chart without knowing the
layers beneath it.

Immutability is real: frozen dataclasses throughout, `houses` a tuple of frozen
houses with tuple `occupants`, and `grahas` a `MappingProxyType` over a private
copy — the same copy-then-proxy discipline `BirthChart` uses.

### The renderer boundary

A renderer consumes a `D1Chart` and nothing else. All layout knowledge — the
North Indian fixed-house diamond, the South Indian fixed-rashi grid, the East
Indian grid, tabular columns, JSON field names, web components — lives inside
the renderer, and **no renderer is built**. Layer 9 computes no astronomy and
applies no astrological rule: no drishti, dashas, yogas, dignity, combustion,
planetary war, strength, divisional charts, chalit, lordship or interpretation,
and no placeholders for them. Rashi lords are deliberately absent — lordship is
an astrological rule, not D1 geometry. An AST test enforces the import boundary
(no `swisseph`, `ephemeris`, `astronomy`, `sidereal`, `time` or
`lagna.whole_sign`) exactly as for every other layer.

### DMS is display only, and truncates

`representation/dms.py` is the first and only display derivation in the
codebase: `to_dms(value_degrees, seconds_decimals=0) -> DMS(degrees, minutes,
seconds)`, computed on call and **never stored, compared or fed back**. The
policy is **truncation toward zero at every stage, never rounding** — so a
displayed value can never appear to cross a rashi, nakshatra or pada boundary
that the authoritative value did not: 29.999999° displays as `29°59'59"`, never
`30°0'0"`. `round()` appears nowhere in the package and a test parses the AST to
prove it. Negative, non-finite and non-numeric inputs are rejected with
`ValueError`, since degrees within a division are non-negative by definition.

## The Lagna and Whole Sign houses

`vedic_chart.lagna` computes the rising sign and assigns houses. It is kept
separate from chart assembly (Layer 8), which is not built.

```python
from vedic_chart.lagna.ascendant import calculate_lagna
from vedic_chart.lagna.whole_sign import assign_houses

lagna = calculate_lagna(moment_utc, place.latitude, place.longitude)
houses = assign_houses(
    lagna.placement.rashi_index,
    {graha: p.placement.rashi_index for graha, p in grahas.items()},
)
```

### Method

The tropical ascendant comes from Swiss Ephemeris (`swe.houses_ex`), which
computes the *apparent* ascendant using true obliquity. The sidereal Lagna is
then `(tropical − ayanamsha) mod 360`, using the **same** Lahiri accessor and
the **same** rotation helper as every planetary position, at the same Julian
Day — nothing is recomputed or duplicated. The result is classified by the
same `classify()` the grahas use, so the Lagna gets a rashi, a nakshatra and a
pada on identical terms.

**The library's house cusps are deliberately discarded.** `houses_ex` returns
twelve cusps alongside the ascendant, and they are tropical. Whole Sign houses
are derived instead from the *sidereal* Lagna's sign, so those cusps would be
wrong to use. The ascendant point itself is house-system-independent — it is
where the ecliptic meets the eastern horizon — so the house-system argument
does not affect the value taken.

Whole Sign assignment is one line of arithmetic in a module that knows nothing
about astronomy: `house = (rashi_index − lagna_rashi_index) mod 12 + 1`. A sign
*is* a house; the Lagna's sign is house 1 in its entirety, and the exact degree
within it plays no part.

### Verification

The ascendant is cross-checked in the test suite against a **textbook formula
written from scratch and sharing no code with the implementation** — GMST from
the IAU 1982 polynomial, mean obliquity, and the standard ascendant equation —
across five places spanning both hemispheres and the equator. The worst
disagreement is **0.004°**, consistent with the test formula omitting nutation
where Swiss Ephemeris includes it.

It is also checked against physics: the ascendant meets the Sun's longitude at
sunrise (located by bisection, agreeing to under 0.01°), passes through all
twelve signs in a day, advances monotonically, and returns to its starting point
after one sidereal day to within 0.0003°.

### Polar caveat

Above roughly 66.5° of latitude the ascendant stays mathematically defined but
behaves badly: it moves extremely non-uniformly, racing through some signs in
minutes, and near the poles whole stretches of the ecliptic never rise at all,
so some Lagnas are unreachable on a given date. No special handling is applied —
the value is returned exactly as computed, and interpreting it there is the
caller's problem. Latitudes beyond ±90° or longitudes beyond ±180° are rejected
with `ValueError`. The layer takes plain coordinates and does not import the
location layer, so the calculation engine stays independent of how a place was
resolved.

## The offline geocoder

`OfflineLocationResolver` is the real Layer 2 implementation. It answers place
queries from a locally built GeoNames database and resolves timezones from
coordinates, **with no network access at any point** — not at build time for
timezones, and never at runtime.

```python
from vedic_chart.location.offline.resolver import OfflineLocationResolver

with OfflineLocationResolver("data/geodata.sqlite") as resolver:
    place = resolver.resolve("Jalandhar")
    # ResolvedLocation('Jalandhar, Punjab, India', 31.32556, 75.57917, 'Asia/Kolkata')
```

### Architecture

- `offline/normalize.py` — the single definition of "the same name", shared by
  the importer and the query path so they cannot disagree.
- `offline/db.py` — read-only SQLite (`mode=ro&immutable=1`), schema checks.
- `offline/search.py` — candidate lookup, scoring, and **`RankingConfig`**,
  which holds every weight and threshold in the geocoder. Nothing is tuned
  anywhere else.
- `offline/tz_lookup.py` — `timezonefinder` singleton; rejects `None` and
  `Etc/*` results, which mean the coordinate missed every real timezone polygon.
- `offline/resolver.py` — `resolve()` (the protocol method), plus `search()` and
  `resolve_with_details()` as a richer API this resolver offers in addition.

`resolve()` is the only method the `LocationResolver` protocol requires; code
that wants to stay portable across resolvers should depend on it alone.

### Coverage

Every populated place of 500+ people worldwide (`cities500`), plus **every**
populated place in India down to village level. Adding a country is a one-line
change to `COUNTRY_PACKS` plus its dumps in `data/raw/`.

### Ambiguity: dominance, not guessing

Candidates are "materially different" when they sit in different countries or
different first-order divisions. Faced with those, the resolver auto-picks only
when the top candidate **dominates**, and otherwise raises
`AmbiguousPlaceError` carrying the ranked candidates. Dominance requires a live
settlement feature code (never a destroyed, abandoned or historical place) and
then either:

- **the unique-capital rule** — the top is the only `PPLC` among the rivals.
  This is what separates London, England from London, Ontario, whose
  populations differ by only 21×; or
- **the population-ratio rule** — the top has at least
  `dominance_min_population` (1,000) inhabitants *and* out-populates the best
  rival by `dominance_population_ratio` (50×).

The minimum-population condition exists because **GeoNames records an unknown
population as 0, not as empty**. A ratio measured against 0 says only that the
rival is unranked, so the winner must be substantial in its own right. This is
what lets Jalandhar (868,929) beat two same-named population-0 villages in
Madhya Pradesh and Uttar Pradesh, while two obscure hamlets stay ambiguous.

Hyderabad stays ambiguous on purpose: India's is 3.6× Pakistan's, nowhere near
50×, and neither is a national capital. `"Hyderabad, India"` resolves.

Every automatic choice is recorded. `resolve_with_details()` returns a
`ResolutionDecision` with `dominance_applied` and the reason in words, so a
silent auto-pick is impossible.

### Timezones

Resolved spatially from the place's coordinates, not read from the GeoNames
`timezone` column — that column is stored only so the build can measure the
disagreement. Across all 786,552 places the two differ for 866 (**0.110%**),
almost all at genuine boundaries. Vincennes, Indiana is a good example: GeoNames
says `America/Chicago`, the polygon says `America/Indiana/Vincennes`, and the
polygon is right.

The resolver returns only an identifier. Turning it into an offset for a given
instant stays Layer 3's job via `zoneinfo`.

### Building the database

The GeoNames dumps go in `data/raw/` (gitignored — see `data/DATA_SOURCES.md`
for provenance, checksums and licensing):

```
python -m tools.geodata.verify_inputs        # checksums + structural validation
python -m tools.geodata.build_db             # production DB (~144 MB)
python -m tools.geodata.verify_db            # QA gate
python -m tools.geodata.build_db --fixture   # the committed test fixture
```

The build writes to a temporary file and atomically renames it, so an
interrupted build cannot leave a half-written database where the runtime reads
it. Output is dated (`geodata-YYYYMMDD.sqlite`) with a stable `geodata.sqlite`
copy alongside.

**Production vs fixture.** The production database (786,552 places, ~144 MB) is
built locally and gitignored. `tests/fixtures/geodata_fixture.sqlite` (11,567
places, ~5 MB) **is committed**, is built by the same importer over a reduced
slice, and is the only database the tests touch — so the suite runs anywhere
without a build step and cannot drift.

### The no-network guarantee

Enforced two ways in the test suite: an AST test asserting no module in
`offline/` imports anything network-capable (`http`, `urllib`, `requests`,
`socket`, `ssl`, `ftplib`, `aiohttp`), and a runtime test that monkeypatches
`socket.socket`, `socket.create_connection` and `socket.getaddrinfo` to raise,
then performs real resolutions.

## What is installed and why

- **pyswisseph 2.10.3.2** — the official Python binding to the Swiss Ephemeris C
  library (library version 2.10.03). It is the reference implementation for
  high-precision planetary positions and is what Layer 5 wraps.
- **pytest 9.1.1** — test runner, used to prove the ephemeris boundary actually
  invokes the C library correctly and reads real data files.
- **timezonefinder 8.2.0** — offline spatial timezone lookup for the geocoder.
  Its boundary polygons ship inside the package, so no network call is needed.
  Pulls `numpy`, `h3`, `cffi`, `pycparser` and `flatbuffers` transitively.

No other dependencies are installed. Place and timezone data sources, with
checksums and licensing, are documented in `data/DATA_SOURCES.md`.

### Ephemeris data files

The three official Swiss Ephemeris data files in `ephe/` cover 1800–2400 AD:

- `sepl_18.se1` (484 KB) — planets
- `semo_18.se1` (1.3 MB) — Moon
- `seas_18.se1` (223 KB) — asteroids, which also underpins node calculation

They were downloaded from
`https://raw.githubusercontent.com/aloistr/swisseph/master/ephe/<file>`
(the upstream mirror of the official distribution; `https://www.astro.com/ftp/swisseph/ephe/`
returned HTTP 403 at build time).

These files are used deliberately instead of the library's built-in Moshier
approximation. Moshier needs no data files but is markedly less accurate; for
chart work we want the full Swiss Ephemeris precision, so the code refuses to
run without the files rather than degrading silently.

## The calculation boundary

`src/vedic_chart/ephemeris/swiss_ephemeris.py` is the only module in this
codebase that may import `swisseph`. Callers use the constants and functions it
re-exports; they never touch the C library directly.

Everything the module returns is **raw tropical geocentric ecliptic data** —
longitude, latitude, distance in AU, and the corresponding daily speeds. No
ayanamsha, no sidereal mode, no signs, no houses, no interpretation of any kind.
Sidereal conversion is Layer 6's job, and it consumes this output rather than
asking the library for sidereal coordinates.

`calc_planet_position` inspects the flags the library returns and raises
`RuntimeError` if `SEFLG_SWIEPH` is absent. That is the Moshier-fallback guard:
when the `.se1` files cannot be found, Swiss Ephemeris quietly switches to
Moshier and reports it only in the returned flags. The guard turns that silent
downgrade into a loud failure.

## Licensing

The Swiss Ephemeris and pyswisseph are distributed under the **AGPL-3.0**. This
project is therefore AGPL-3.0 as well. The practical consequence: running this
code inside a closed-source network service is not permitted under the AGPL —
network users are entitled to the corresponding source. A commercial Swiss
Ephemeris licence from Astrodienst is required for that case.

## Running the tests

```
cd "path/to/APC Tool"
.venv/bin/python -m pytest -v
```

## Approved methodology

The astrological methodology agreed for this project is **sidereal zodiac,
Lahiri ayanamsha, D1 (Rashi) chart, Whole Sign houses**, with the D1 details
fixed by the locked AstroLearn specification described above. The sidereal
zodiac, the Lahiri ayanamsha and the D1 graha classification are implemented
(Layers 6 and 7). Whole Sign houses and the lagna are not, and no other
methodology is assumed anywhere in the code.

## Audit and specification

See `docs/CORE_ENGINE_AUDIT.md` (2026-09-05 findings; OPEN-1 closed) and `docs/CALCULATION_SPEC.md` (FROZEN v1.0, 2026-09-05). Verification cases: `docs/verification_cases.md`, regenerated by `python tools/audit/verification_cases.py`.

## License

AGPL-3.0 — see `LICENSE`. Third-party components and the Swiss Ephemeris dual-licensing choice are documented in `THIRD_PARTY_NOTICES.md`; the Astrodienst notice for the bundled `.se1` files is preserved in `ephe/SWISSEPH_LICENSE.txt`.
