# Structured planetary positions HTTP extension

Implemented as an additive extension to `POST /api/chart`. The four-field
request and outer `vedic_chart.viewer/2` schema are unchanged. Successful chart
responses now always include `planetary_positions`, with its own version
`vedic_chart.planetary_positions/1`. Existing SVG, timeline, birth, assumptions,
place selection, authentication and error behavior are unchanged.

Clients must tolerate additional top-level fields. No new endpoint, core
calculation, astronomy dependency or external request was added. The internal
synthetic timeline-only serializer cannot supply planets and does not invent
this block; it is not the HTTP chart path.

## Request

```json
{"date":"1995-03-21","time":"06:45","place_text":"Jalandhar, Punjab, India","place_id":"1268782"}
```

Select a record with `POST /api/places` (`{"q":"Jalandhar, India"}`), then send
its exact `label` as `place_text` and its GeoNames identifier as a **string**.
All four keys remain required strings. Blank time means assumed noon; both
blank place fields mean the configured default (Jammu in production). Invalid
supplied values never default. Read `effective`, `birth` and `assumptions` to
know the actual local time, UTC instant and IANA zone used. Do not append a
hardcoded `+05:30` to an international birth time.

For local API access: GET `/`, read `<meta name="viewer-token" content="…">`,
then POST UTF-8 JSON with `X-Viewer-Token`, `Content-Type: application/json`,
`Sec-Fetch-Site: same-origin` and a normal Content-Length. Through the current
ngrok setup, every request additionally uses tester HTTP Basic Auth;
`ngrok-skip-browser-warning: 1` bypasses the interstitial for automation.
The existing tunnel policy rewrites Host and strips Origin only after rejecting
foreign origins. Use backend-to-backend calls; unrelated browser origins remain
blocked. No credentials or persistent API keys are embedded in source.

## Block contract

| Field | Type | Meaning |
|---|---|---|
| `schema` | string | `vedic_chart.planetary_positions/1` |
| `longitude_frame` | string | `sidereal` |
| `angular_unit` | string | `degree` |
| `speed_unit` | string | `degree/day` |
| `ayanamsa_degrees` | decimal string | Actual chart ayanamsha, full float precision |
| `node_convention` | string | `mean` |
| `retrograde_rule` | string | Describes the frozen speed-based flag |
| `planets` | array of 9 records | Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Rahu, Ketu |
| `ascendant` | record | Ascendant explicitly separate from the nine grahas |

The existing `engine` block identifies the Lahiri convention, zodiac, house
system, node convention and engine specification. Its validation note remains
unchanged; this extension makes no provider-compatibility claim.

Each position record:

| Field | Type | Meaning |
|---|---|---|
| `key` | string | Stable lowercase graha key, or `ascendant` |
| `name` | string | English display name |
| `kind` | string | `planet`, `lunar_node`, or `ascendant`; the traditional planet group includes Sun/Moon |
| `sidereal_longitude` | decimal string | Full longitude in degrees from sidereal Aries |
| `sign.index` | integer | Zero-based Aries=0 through Pisces=11 |
| `sign.number` | integer | One-based Aries=1 through Pisces=12 |
| `sign.name` | string | Frozen Sanskrit rashi name |
| `sign.english_name` | string | English zodiac label |
| `degrees_in_sign` | decimal string | Offset within the already classified sign, copied from the engine |
| `house` | integer | Whole Sign house, 1–12; Ascendant is house 1 |
| `is_retrograde` | boolean or null | Engine's flag; null for Ascendant (not measured) |
| `speed_longitude` | decimal string or null | Engine's longitude speed in degrees/day; null for Ascendant |
| `nakshatra` | object | Engine's zero-based index, one-based number, name and pada (1–4) |

All floating-point data uses the existing transport's `repr`-string convention:
no display rounding, SVG parsing, longitude subtraction, reclassification or
new ephemeris call. Sign degree is copied from `placement.degrees_in_rashi`.
Do not reclassify rounded coordinates. Numeric conversion for a double-based
adapter can use `Number(value)` with finite/range validation, while retaining
the original strings for exact response reproduction. Last-bit cross-platform
variation already exists in the underlying engine.

Rahu is the Mean Node. Ketu's position and speed come from the assembled engine
result; its speed inherits Rahu's speed. Both retrograde flags are exported
even though the SVG deliberately hides node underlines. Ascendant motion is
**null**, not falsely reported as direct. Any downstream Boolean-only contract
must make its Ascendant convention explicit.

## Example (response excerpt)

The following contains one of nine grahas plus the complete Ascendant record;
the actual `planets` array contains all nine. Values were captured from the
native Darwin server with production resources; they are evidence, not new
portable golden constants.

```json
{
  "planetary_positions": {
    "schema": "vedic_chart.planetary_positions/1",
    "longitude_frame": "sidereal",
    "angular_unit": "degree",
    "speed_unit": "degree/day",
    "ayanamsa_degrees": "23.793221685520077",
    "node_convention": "mean",
    "retrograde_rule": "speed_longitude < 0; Ketu inherits Rahu's speed",
    "planets": [
      {
        "key": "mercury",
        "name": "Mercury",
        "kind": "planet",
        "sidereal_longitude": "315.39689013842946",
        "sign": {
          "index": 10,
          "number": 11,
          "name": "Kumbha",
          "english_name": "Aquarius"
        },
        "degrees_in_sign": "15.396890138429455",
        "house": 12,
        "is_retrograde": false,
        "speed_longitude": "1.5621436857187385",
        "nakshatra": {
          "index": 23,
          "number": 24,
          "name": "Shatabhisha",
          "pada": 3
        }
      }
    ],
    "ascendant": {
      "key": "ascendant",
      "name": "Ascendant",
      "kind": "ascendant",
      "sidereal_longitude": "339.79591074291494",
      "sign": {
        "index": 11,
        "number": 12,
        "name": "Meena",
        "english_name": "Pisces"
      },
      "degrees_in_sign": "9.795910742914941",
      "house": 1,
      "is_retrograde": null,
      "speed_longitude": null,
      "nakshatra": {
        "index": 25,
        "number": 26,
        "name": "Uttara Bhadrapada",
        "pada": 2
      }
    }
  }
}
```

## Integration mapping

| Required downstream concept | Source |
|---|---|
| Planet identity | `planetary_positions.planets[].key` / `.name` |
| Sign | `.sign.english_name` or explicitly chosen `.index` / `.number` |
| Degree within sign | `.degrees_in_sign` |
| Absolute zodiac longitude | `.sidereal_longitude` |
| Retrograde | `.is_retrograde` |
| Ascendant | `planetary_positions.ascendant` |
| Birth timezone and instant | `birth.zone`, `birth.utc`, `birth.local` |
| Assumed birth inputs | `assumptions` and `effective` |

The cited consuming repository's `types/astrology.ts` and `lib/backend/prokerala.ts`
at `2e3b03a67ed219114c91d847781c498ae0bd3e19` returned HTTP 404 during implementation.
No undocumented `PlanetsData` shape or Prokerala numeric identifier mapping is
invented. This supplies the missing source data; deployment and changing that
application's provider require access to that application's actual contract.

## Validation and protected scope

`tests/test_viewer_planetary_positions.py` checks every graha against the actual
assembled chart, Ascendant/null motion, all 12 sign boundaries on both sides,
retrograde/direct/zero motion, exact JSON round-tripping, all four optional-input
combinations and London over real HTTP. Pipeline spies verify one calculation
per request. Existing AST rules still prohibit transport arithmetic and imports
of calculation internals.

The prior complete viewer golden remains unchanged. Its tests compare every
pre-extension field and its encoder bytes; the added block is independently
checked against the chart, rather than regenerating platform-sensitive fixtures.
The fixture-generation command preserves this legacy projection too.

Production-resource before/after checks cover Jalandhar, Jammu, date-only Jammu
and London: all pre-existing response values, SVG strings and 819 daśā rows
are identical. Only the new block is added. Native regression results and
pre-existing environment failures are recorded in the implementation handoff.

Only viewer transport, its tests and documentation change. Layers 1–13, viewer
server/security/HTML/CSS/JS, project dependencies, ephemeris files and existing
goldens are untouched. A running server must be restarted to load the extension.
