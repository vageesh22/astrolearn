"""Layer 7, part 1: the zodiacal divisions of a sidereal longitude.

Pure module. It imports nothing from the other layers and nothing outside the
standard library, so every rule below can be tested on plain numbers.

Implements the locked AstroLearn Vedic D1 calculation specification:

* rule 5  -- the rashis are 12 equal 30 deg divisions of the sidereal zodiac,
  counted from 0 deg Mesha.
* rule 6  -- the index is 0-based internally; the 1-based number and the
  Sanskrit name are carried in the output for callers.
* rule 7  -- 27 equal nakshatras, counted from Ashwini at 0 deg sidereal Aries.
* rule 8  -- ``nakshatra_index = floor(longitude * 27 / 360)``.
* rule 9  -- ``pada = floor(longitude * 108 / 360) % 4 + 1``.
* rule 10 -- every interval is half-open, ``[start, end)``: a longitude exactly
  on a boundary belongs to the division that starts there.
* rule 11 -- classification happens on the unrounded longitude. Nothing is
  rounded before a division is decided.
* rule 12 -- no epsilon nudging. No value is shifted toward or away from a
  boundary to make a comparison come out a particular way.
* rule 13 -- the longitude is normalized into [0, 360) first.
* rule 15 -- 27 nakshatras only. The 28-nakshatra Abhijit scheme is not used.

Degrees are kept at full precision (rule 14); formatting them as degrees,
minutes and seconds is a display concern and no display layer exists yet.
"""

from dataclasses import dataclass

RASHI_NAMES: tuple[str, ...] = (
    "Mesha",
    "Vrishabha",
    "Mithuna",
    "Karka",
    "Simha",
    "Kanya",
    "Tula",
    "Vrishchika",
    "Dhanu",
    "Makara",
    "Kumbha",
    "Meena",
)

NAKSHATRA_NAMES: tuple[str, ...] = (
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashira",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "Purva Phalguni",
    "Uttara Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Mula",
    "Purva Ashadha",
    "Uttara Ashadha",
    "Shravana",
    "Dhanishta",
    "Shatabhisha",
    "Purva Bhadrapada",
    "Uttara Bhadrapada",
    "Revati",
)

RASHI_SPAN = 30.0
NAKSHATRA_SPAN = 360.0 / 27.0
PADA_SPAN = 360.0 / 108.0


def normalize_longitude(longitude: float) -> float:
    """Wrap a longitude into [0, 360) (rule 13).

    Python's ``%`` already yields a result in [0, 360) for any finite float,
    negatives included: it takes the sign of the divisor. No branching or
    epsilon adjustment is needed or wanted (rule 12).
    """
    return longitude % 360.0


@dataclass(frozen=True)
class DivisionalPlacement:
    """Where one sidereal longitude falls in the rashi and nakshatra schemes.

    The index fields are 0-based for internal use, the number fields 1-based
    for output (rule 6). Every ``degrees_in_*`` field is the full-precision
    offset from the start of that division (rules 11 and 14).
    """

    rashi_index: int
    rashi_number: int
    rashi_name: str
    degrees_in_rashi: float
    nakshatra_index: int
    nakshatra_number: int
    nakshatra_name: str
    degrees_in_nakshatra: float
    pada: int
    degrees_in_pada: float


def classify(sidereal_longitude: float) -> DivisionalPlacement:
    """Classify a sidereal longitude into rashi, nakshatra and pada.

    Follows the specification exactly: normalize (rule 13), then take plain
    floors of the unrounded value (rules 8, 9, 11). Boundaries are half-open
    (rule 10) and nothing is nudged (rule 12).

    The index assertions below are guards, not clamps. A clamp would silently
    move a value across a boundary, which rule 12 forbids; these instead let an
    impossible index surface as an error.
    """
    longitude = normalize_longitude(sidereal_longitude)

    rashi_index = int(longitude // RASHI_SPAN)
    nakshatra_index = int(longitude * 27.0 / 360.0)
    pada_of_zodiac = int(longitude * 108.0 / 360.0)

    assert 0 <= rashi_index <= 11, (longitude, rashi_index)
    assert 0 <= nakshatra_index <= 26, (longitude, nakshatra_index)
    assert 0 <= pada_of_zodiac <= 107, (longitude, pada_of_zodiac)

    return DivisionalPlacement(
        rashi_index=rashi_index,
        rashi_number=rashi_index + 1,
        rashi_name=RASHI_NAMES[rashi_index],
        degrees_in_rashi=longitude - rashi_index * RASHI_SPAN,
        nakshatra_index=nakshatra_index,
        nakshatra_number=nakshatra_index + 1,
        nakshatra_name=NAKSHATRA_NAMES[nakshatra_index],
        degrees_in_nakshatra=longitude - nakshatra_index * NAKSHATRA_SPAN,
        pada=pada_of_zodiac % 4 + 1,
        degrees_in_pada=longitude - pada_of_zodiac * PADA_SPAN,
    )
