# Independent Verification Cases (Core Engine Audit, 2026-09-05)

Complete calculated output of every case, produced by `tools/audit/verification_cases.py` against the frozen engine (252-test state). Values are printed at full precision (`repr`) where they feed later layers. Nothing in these cases changes a convention; they record what the engine does today.

**Frame note:** the Lahiri ayanamsha is referred to the true equinox of date (`swe.get_ayanamsa_ex_ut(jd, 0)`), the same frame as the apparent tropical positions, so every sidereal longitude below equals Swiss Ephemeris' native `SEFLG_SIDEREAL` Lahiri value (Core Engine Audit OPEN-1, resolved 2026-09-05 with owner approval).

## V01 — Jalandhar 1995-03-21 06:45 IST (anchored reference)

*Purpose:* Baseline chart used since the Lagna milestone; resolved through the offline fixture geocoder.

*Input:* 1995-03-21 06:45:00 local, place query `Jalandhar` (resolver: fixture)

*Resolved:* Jalandhar, Punjab, India — lat 31.32556, lon 75.57917, tz `Asia/Kolkata`
*UTC:* 1995-03-21T01:15:00+00:00  *JD(UT):* 2449797.5520833335  *Ayanamsha:* 23.793221685520077
*Lagna:* tropical 3.589132428435006 → sidereal 339.79591074291494 → Meena 9.795911°, Uttara Bhadrapada pada 2

| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |
|---|---:|---|---:|---|---:|---:|---:|---|
| SUN | 336.165799 | Meena | 6.165799 | Uttara Bhadrapada | 1 | 1 | +0.993178 | D |
| MOON | 209.204408 | Tula | 29.204408 | Vishakha | 3 | 8 | +14.370728 | D |
| MERCURY | 315.396890 | Kumbha | 15.396890 | Shatabhisha | 3 | 12 | +1.562144 | D |
| VENUS | 297.652559 | Makara | 27.652559 | Dhanishta | 2 | 11 | +1.191480 | D |
| MARS | 109.455103 | Karka | 19.455103 | Ashlesha | 1 | 5 | -0.045591 | R |
| JUPITER | 231.384758 | Vrishchika | 21.384758 | Jyeshtha | 2 | 9 | +0.035696 | D |
| SATURN | 323.048592 | Kumbha | 23.048592 | Purva Bhadrapada | 1 | 12 | +0.120768 | D |
| RAHU | 193.788209 | Tula | 13.788209 | Swati | 3 | 8 | -0.052955 | R |
| KETU | 13.788209 | Mesha | 13.788209 | Bharani | 1 | 2 | -0.052955 | R |

*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py (Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); (B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; (C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).


## V02 — Sydney 1988-01-26 14:00 AEDT (southern hemisphere, DST)

*Purpose:* Southern latitude ascendant geometry; Australia/Sydney daylight time (+11).

*Input:* 1988-01-26 14:00:00 local, place query `Sydney` (resolver: fixed)

*Resolved:* Sydney, New South Wales, Australia — lat -33.8688, lon 151.2093, tz `Australia/Sydney`
*UTC:* 1988-01-26T03:00:00+00:00  *JD(UT):* 2447186.625  *Ayanamsha:* 23.691071750550133
*Lagna:* tropical 42.501230658270785 → sidereal 18.810158907720652 → Mesha 18.810159°, Bharani pada 2

| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |
|---|---:|---|---:|---|---:|---:|---:|---|
| SUN | 281.675980 | Makara | 11.675980 | Shravana | 1 | 10 | +1.016739 | D |
| MOON | 14.269124 | Mesha | 14.269124 | Bharani | 1 | 1 | +13.163273 | D |
| MERCURY | 300.157375 | Kumbha | 0.157375 | Dhanishta | 3 | 11 | +1.081035 | D |
| VENUS | 319.018861 | Kumbha | 19.018861 | Shatabhisha | 4 | 11 | +1.209621 | D |
| MARS | 227.973603 | Vrishchika | 17.973603 | Jyeshtha | 1 | 8 | +0.668877 | D |
| JUPITER | 358.920630 | Meena | 28.920630 | Revati | 4 | 12 | +0.129817 | D |
| SATURN | 244.540142 | Dhanu | 4.540142 | Mula | 2 | 9 | +0.102202 | D |
| RAHU | 332.146510 | Meena | 2.146510 | Purva Bhadrapada | 4 | 12 | -0.052952 | R |
| KETU | 152.146510 | Kanya | 2.146510 | Uttara Phalguni | 2 | 6 | -0.052952 | R |

*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py (Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); (B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; (C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).


## V03 — New York 2023-03-12 02:30 (nonexistent local time)

*Purpose:* Birth time inside the DST spring-forward gap must be REJECTED, not guessed.

*Input:* 2023-03-12 02:30:00 local, place query `New York` (resolver: fixed)

**Result: `NonexistentLocalTimeError`** — Local time 2023-03-12T02:30:00 does not exist in America/New_York: the clock jumps from offset -05:00 to -04:00 across it. The caller must supply a wall time that occurred, or pass an exact UTC instant instead; this layer will not choose one.

*Verification class:* (A) internal — typed rejection is the specified behaviour; (C) conforms to the no-silent-disambiguation rule. No external comparison applicable.

## V04 — London 1943-07-15 12:00 (British Double Summer Time)

*Purpose:* Historical tzdata rule: wartime BDST, expected offset +02:00.

*Input:* 1943-07-15 12:00:00 local, place query `London` (resolver: fixed)

*Resolved:* London, England, United Kingdom — lat 51.5074, lon -0.1278, tz `Europe/London`
*UTC:* 1943-07-15T10:00:00+00:00  *JD(UT):* 2430920.9166666665  *Ayanamsha:* 23.06533353936836
*Lagna:* tropical 174.5392609046897 → sidereal 151.47392736532134 → Kanya 1.473927°, Uttara Phalguni pada 2

| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |
|---|---:|---|---:|---|---:|---:|---:|---|
| SUN | 88.980942 | Mithuna | 28.980942 | Punarvasu | 3 | 10 | +0.953577 | D |
| MOON | 239.446242 | Vrishchika | 29.446242 | Jyeshtha | 4 | 3 | +14.758905 | D |
| MERCURY | 85.729271 | Mithuna | 25.729271 | Punarvasu | 2 | 10 | +2.149574 | D |
| VENUS | 133.079039 | Simha | 13.079039 | Magha | 4 | 12 | +0.782163 | D |
| MARS | 12.052915 | Mesha | 12.052915 | Ashwini | 4 | 8 | +0.679511 | D |
| JUPITER | 100.080837 | Karka | 10.080837 | Pushya | 3 | 11 | +0.219423 | D |
| SATURN | 57.689054 | Vrishabha | 27.689054 | Mrigashira | 2 | 9 | +0.117617 | D |
| RAHU | 114.099661 | Karka | 24.099661 | Ashlesha | 3 | 11 | -0.052917 | R |
| KETU | 294.099661 | Makara | 24.099661 | Dhanishta | 1 | 5 | -0.052917 | R |

*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py (Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); (B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; (C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).


## V05 — Kolkata 1943-01-01 12:00 (India war time +06:30)

*Purpose:* Historical Indian offset from tzdata; pre-independence chart.

*Input:* 1943-01-01 12:00:00 local, place query `Kolkata` (resolver: fixed)

*Resolved:* Kolkata, West Bengal, India — lat 22.5726, lon 88.3639, tz `Asia/Kolkata`
*UTC:* 1943-01-01T05:30:00+00:00  *JD(UT):* 2430725.7291666665  *Ayanamsha:* 23.05841239985251
*Lagna:* tropical 1.1473282456016152 → sidereal 338.0889158457491 → Meena 8.088916°, Uttara Bhadrapada pada 2

| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |
|---|---:|---|---:|---|---:|---:|---:|---|
| SUN | 256.868375 | Dhanu | 16.868375 | Purva Ashadha | 2 | 10 | +1.019414 | D |
| MOON | 184.586652 | Tula | 4.586652 | Chitra | 4 | 8 | +13.544262 | D |
| MERCURY | 273.897292 | Makara | 3.897292 | Uttara Ashadha | 3 | 11 | +1.467576 | D |
| VENUS | 267.914510 | Dhanu | 27.914510 | Uttara Ashadha | 1 | 10 | +1.255887 | D |
| MARS | 228.586723 | Vrishchika | 18.586723 | Jyeshtha | 1 | 9 | +0.710047 | D |
| JUPITER | 88.479584 | Mithuna | 28.479584 | Punarvasu | 3 | 4 | -0.129992 | R |
| SATURN | 43.697419 | Vrishabha | 13.697419 | Rohini | 2 | 3 | -0.061303 | R |
| RAHU | 124.443050 | Simha | 4.443050 | Magha | 2 | 6 | -0.052961 | R |
| KETU | 304.443050 | Kumbha | 4.443050 | Dhanishta | 4 | 12 | -0.052961 | R |

*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py (Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); (B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; (C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).


## V06a — Kiritimati 2024-01-02 03:00 (+14) — date-line pair A

*Purpose:* Same UTC instant as V06b via a +14 zone; wall date one day LATER than Midway's.

*Input:* 2024-01-02 03:00:00 local, place query `Kiritimati` (resolver: fixed)

*Resolved:* Kiritimati, Line Islands, Kiribati — lat 1.8721, lon -157.4278, tz `Pacific/Kiritimati`
*UTC:* 2024-01-01T13:00:00+00:00  *JD(UT):* 2460311.0416666665  *Ayanamsha:* 24.190871809093274
*Lagna:* tropical 230.1009006012759 → sidereal 205.91002879218263 → Tula 25.910029°, Vishakha pada 2

| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |
|---|---:|---|---:|---|---:|---:|---:|---|
| SUN | 256.400082 | Dhanu | 16.400082 | Purva Ashadha | 1 | 3 | +1.019027 | D |
| MOON | 138.208364 | Simha | 18.208364 | Purva Phalguni | 2 | 11 | +11.811829 | D |
| MERCURY | 238.017173 | Vrishchika | 28.017173 | Jyeshtha | 4 | 2 | -0.092215 | R |
| VENUS | 219.080249 | Vrishchika | 9.080249 | Anuradha | 2 | 2 | +1.216535 | D |
| MARS | 243.519195 | Dhanu | 3.519195 | Mula | 2 | 3 | +0.741828 | D |
| JUPITER | 11.393693 | Mesha | 11.393693 | Ashwini | 4 | 7 | +0.004945 | D |
| SATURN | 309.100769 | Kumbha | 9.100769 | Shatabhisha | 1 | 5 | +0.089078 | D |
| RAHU | 356.657345 | Meena | 26.657345 | Revati | 3 | 6 | -0.052964 | R |
| KETU | 176.657345 | Kanya | 26.657345 | Chitra | 1 | 12 | -0.052964 | R |

*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py (Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); (B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; (C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).


## V06b — Midway 2024-01-01 02:00 (−11) — date-line pair B

*Purpose:* Same UTC instant as V06a (2024-01-01T13:00Z). Positions must be identical; Lagna differs (different longitude).

*Input:* 2024-01-01 02:00:00 local, place query `Midway` (resolver: fixed)

*Resolved:* Midway Atoll, United States Minor Outlying Islands — lat 28.2072, lon -177.3735, tz `Pacific/Midway`
*UTC:* 2024-01-01T13:00:00+00:00  *JD(UT):* 2460311.0416666665  *Ayanamsha:* 24.190871809093274
*Lagna:* tropical 204.91368496148706 → sidereal 180.7228131523938 → Tula 0.722813°, Chitra pada 3

| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |
|---|---:|---|---:|---|---:|---:|---:|---|
| SUN | 256.400082 | Dhanu | 16.400082 | Purva Ashadha | 1 | 3 | +1.019027 | D |
| MOON | 138.208364 | Simha | 18.208364 | Purva Phalguni | 2 | 11 | +11.811829 | D |
| MERCURY | 238.017173 | Vrishchika | 28.017173 | Jyeshtha | 4 | 2 | -0.092215 | R |
| VENUS | 219.080249 | Vrishchika | 9.080249 | Anuradha | 2 | 2 | +1.216535 | D |
| MARS | 243.519195 | Dhanu | 3.519195 | Mula | 2 | 3 | +0.741828 | D |
| JUPITER | 11.393693 | Mesha | 11.393693 | Ashwini | 4 | 7 | +0.004945 | D |
| SATURN | 309.100769 | Kumbha | 9.100769 | Shatabhisha | 1 | 5 | +0.089078 | D |
| RAHU | 356.657345 | Meena | 26.657345 | Revati | 3 | 6 | -0.052964 | R |
| KETU | 176.657345 | Kanya | 26.657345 | Chitra | 1 | 12 | -0.052964 | R |

*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py (Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); (B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; (C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).


## V07 — Tromsø 1990-06-21 12:00 CEST (69.65°N, midsummer)

*Purpose:* High-latitude ascendant; polar caveat applies (non-uniform rising).

*Input:* 1990-06-21 12:00:00 local, place query `Tromso` (resolver: fixed)

*Resolved:* Tromsø, Troms, Norway — lat 69.6492, lon 18.9553, tz `Europe/Oslo`
*UTC:* 1990-06-21T10:00:00+00:00  *JD(UT):* 2448063.9166666665  *Ayanamsha:* 23.727563234045558
*Lagna:* tropical 174.12484882853732 → sidereal 150.39728559449176 → Kanya 0.397286°, Uttara Phalguni pada 2

| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |
|---|---:|---|---:|---|---:|---:|---:|---|
| SUN | 66.051801 | Mithuna | 6.051801 | Mrigashira | 4 | 10 | +0.954717 | D |
| MOON | 46.782968 | Vrishabha | 16.782968 | Rohini | 3 | 9 | +15.062307 | D |
| MERCURY | 52.890106 | Vrishabha | 22.890106 | Rohini | 4 | 9 | +1.970796 | D |
| VENUS | 32.023532 | Vrishabha | 2.023532 | Krittika | 2 | 9 | +1.181150 | D |
| MARS | 351.546473 | Meena | 21.546473 | Revati | 2 | 7 | +0.711593 | D |
| JUPITER | 83.453033 | Mithuna | 23.453033 | Punarvasu | 2 | 10 | +0.219697 | D |
| SATURN | 269.940783 | Dhanu | 29.940783 | Uttara Ashadha | 1 | 4 | -0.064067 | R |
| RAHU | 285.657050 | Makara | 15.657050 | Shravana | 2 | 5 | -0.052900 | R |
| KETU | 105.657050 | Karka | 15.657050 | Pushya | 4 | 11 | -0.052900 | R |

*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py (Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); (B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; (C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).


## V08a — New Delhi, 30 s BEFORE Mesha Sankranti 2024 (boundary-hugging)

*Purpose:* Sun < 0.0004° below the Meena/Mesha boundary at 2024-04-13T15:34:23+00:00; must classify Meena.

*Input:* 2024-04-13 21:03:53.829020 local, place query `New Delhi` (resolver: fixed)

*Resolved:* New Delhi, Delhi, India — lat 28.6139, lon 77.209, tz `Asia/Kolkata`
*UTC:* 2024-04-13T15:33:53.829020+00:00  *JD(UT):* 2460414.1485396875  *Ayanamsha:* 24.194860560888195
*Lagna:* tropical 234.58251552887955 → sidereal 210.38765496799135 → Vrishchika 0.387655°, Vishakha pada 4

| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |
|---|---:|---|---:|---|---:|---:|---:|---|
| SUN | 359.999660 | Meena | 29.999660 | Revati | 4 | 5 | +0.980106 | D |
| MOON | 64.606162 | Mithuna | 4.606162 | Mrigashira | 4 | 8 | +13.199488 | D |
| MERCURY | 357.071219 | Meena | 27.071219 | Revati | 4 | 5 | -0.750626 | R |
| VENUS | 346.281759 | Meena | 16.281759 | Uttara Bhadrapada | 4 | 5 | +1.234529 | D |
| MARS | 322.651360 | Kumbha | 22.651360 | Purva Bhadrapada | 1 | 4 | +0.776406 | D |
| JUPITER | 25.941242 | Mesha | 25.941242 | Bharani | 4 | 6 | +0.225021 | D |
| SATURN | 320.777067 | Kumbha | 20.777067 | Purva Bhadrapada | 1 | 4 | +0.103887 | D |
| RAHU | 351.193507 | Meena | 21.193507 | Revati | 2 | 5 | -0.052924 | R |
| KETU | 171.193507 | Kanya | 21.193507 | Hasta | 4 | 11 | -0.052924 | R |

*Notes:* Sun expected in Meena (rashi index 11).

*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py (Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); (B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; (C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).


## V08b — New Delhi, 30 s AFTER Mesha Sankranti 2024 (boundary-hugging)

*Purpose:* Sun < 0.0004° above the boundary; must classify Mesha. Unrounded classification is what separates a and b.

*Input:* 2024-04-13 21:04:53.829020 local, place query `New Delhi` (resolver: fixed)

*Resolved:* New Delhi, Delhi, India — lat 28.6139, lon 77.209, tz `Asia/Kolkata`
*UTC:* 2024-04-13T15:34:53.829020+00:00  *JD(UT):* 2460414.1492341324  *Ayanamsha:* 24.194860608227724
*Lagna:* tropical 234.79560590362416 → sidereal 210.60074529539645 → Vrishchika 0.600745°, Vishakha pada 4

| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |
|---|---:|---|---:|---|---:|---:|---:|---|
| SUN | 0.000340 | Mesha | 0.000340 | Ashwini | 1 | 6 | +0.980105 | D |
| MOON | 64.615329 | Mithuna | 4.615329 | Mrigashira | 4 | 8 | +13.199192 | D |
| MERCURY | 357.070697 | Meena | 27.070697 | Revati | 4 | 5 | -0.750618 | R |
| VENUS | 346.282616 | Meena | 16.282616 | Uttara Bhadrapada | 4 | 5 | +1.234529 | D |
| MARS | 322.651899 | Kumbha | 22.651899 | Purva Bhadrapada | 1 | 4 | +0.776405 | D |
| JUPITER | 25.941399 | Mesha | 25.941399 | Bharani | 4 | 6 | +0.225022 | D |
| SATURN | 320.777139 | Kumbha | 20.777139 | Purva Bhadrapada | 1 | 4 | +0.103886 | D |
| RAHU | 351.193470 | Meena | 21.193470 | Revati | 2 | 5 | -0.052924 | R |
| KETU | 171.193470 | Kanya | 21.193470 | Hasta | 4 | 11 | -0.052924 | R |

*Notes:* Sun expected in Mesha (rashi index 0).

*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py (Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); (B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; (C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).


## V09a — New Delhi, 1 min BEFORE Mercury station 2024-04-01

*Purpose:* Station located at 2024-04-01T22:14:30+00:00 UTC; Mercury speed ≈ +8e-5°/day → direct.

*Input:* 2024-04-02 03:43:30.000236 local, place query `New Delhi` (resolver: fixed)

*Resolved:* New Delhi, Delhi, India — lat 28.6139, lon 77.209, tz `Asia/Kolkata`
*UTC:* 2024-04-01T22:13:30.000236+00:00  *JD(UT):* 2460402.426041669  *Ayanamsha:* 24.194460672886837
*Lagna:* tropical 320.8035145448986 → sidereal 296.6090538720117 → Makara 26.609054°, Dhanishta pada 1

| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |
|---|---:|---|---:|---|---:|---:|---:|---|
| SUN | 348.471665 | Meena | 18.471665 | Revati | 1 | 3 | +0.986494 | D |
| MOON | 255.858580 | Dhanu | 15.858580 | Purva Ashadha | 1 | 12 | +13.439074 | D |
| MERCURY | 3.024158 | Mesha | 3.024158 | Ashwini | 1 | 4 | +0.000082 | D |
| VENUS | 331.800212 | Meena | 1.800212 | Purva Bhadrapada | 4 | 3 | +1.236071 | D |
| MARS | 313.537036 | Kumbha | 13.537036 | Shatabhisha | 3 | 2 | +0.778268 | D |
| JUPITER | 23.357755 | Mesha | 23.357755 | Bharani | 4 | 4 | +0.215286 | D |
| SATURN | 319.508814 | Kumbha | 19.508814 | Shatabhisha | 4 | 2 | +0.112187 | D |
| RAHU | 351.814705 | Meena | 21.814705 | Revati | 2 | 3 | -0.052926 | R |
| KETU | 171.814705 | Kanya | 21.814705 | Hasta | 4 | 9 | -0.052926 | R |

*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py (Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); (B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; (C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).


## V09b — New Delhi, 1 min AFTER Mercury station 2024-04-01

*Purpose:* Mercury speed ≈ −8e-5°/day → retrograde. Sign of a near-zero speed decides.

*Input:* 2024-04-02 03:45:30.000236 local, place query `New Delhi` (resolver: fixed)

*Resolved:* New Delhi, Delhi, India — lat 28.6139, lon 77.209, tz `Asia/Kolkata`
*UTC:* 2024-04-01T22:15:30.000236+00:00  *JD(UT):* 2460402.4274305585  *Ayanamsha:* 24.194460764015346
*Lagna:* tropical 321.43770252577536 → sidereal 297.24324176176003 → Makara 27.243242°, Dhanishta pada 2

| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |
|---|---:|---|---:|---|---:|---:|---:|---|
| SUN | 348.473035 | Meena | 18.473035 | Revati | 1 | 3 | +0.986493 | D |
| MOON | 255.877246 | Dhanu | 15.877246 | Purva Ashadha | 1 | 12 | +13.439587 | D |
| MERCURY | 3.024158 | Mesha | 3.024158 | Ashwini | 1 | 4 | -0.000082 | R |
| VENUS | 331.801928 | Meena | 1.801928 | Purva Bhadrapada | 4 | 3 | +1.236070 | D |
| MARS | 313.538117 | Kumbha | 13.538117 | Shatabhisha | 3 | 2 | +0.778267 | D |
| JUPITER | 23.358054 | Mesha | 23.358054 | Bharani | 4 | 4 | +0.215288 | D |
| SATURN | 319.508969 | Kumbha | 19.508969 | Shatabhisha | 4 | 2 | +0.112186 | D |
| RAHU | 351.814632 | Meena | 21.814632 | Revati | 2 | 3 | -0.052926 | R |
| KETU | 171.814632 | Kanya | 21.814632 | Hasta | 4 | 9 | -0.052926 | R |

*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py (Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); (B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; (C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).


## V10 — London 1840-05-10 08:00 (LMT era, pre-GMT)

*Purpose:* tzdata gives Europe/London LMT −00:01:15 before 1847-12-01; 19th-century ephemeris coverage.

*Input:* 1840-05-10 08:00:00 local, place query `London` (resolver: fixed)

*Resolved:* London, England, United Kingdom — lat 51.5074, lon -0.1278, tz `Europe/London`
*UTC:* 1840-05-10T08:01:15+00:00  *JD(UT):* 2393235.834201389  *Ayanamsha:* 21.629743936909072
*Lagna:* tropical 107.86939814488977 → sidereal 86.23965420798069 → Mithuna 26.239654°, Punarvasu pada 2

| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |
|---|---:|---|---:|---|---:|---:|---:|---|
| SUN | 28.056140 | Mesha | 28.056140 | Krittika | 1 | 11 | +0.964972 | D |
| MOON | 138.821973 | Simha | 18.821973 | Purva Phalguni | 2 | 3 | +12.789324 | D |
| MERCURY | 2.258687 | Mesha | 2.258687 | Ashwini | 1 | 11 | +1.181271 | D |
| VENUS | 7.667489 | Mesha | 7.667489 | Ashwini | 3 | 11 | +1.220255 | D |
| MARS | 26.674654 | Mesha | 26.674654 | Krittika | 1 | 11 | +0.723235 | D |
| JUPITER | 201.532047 | Tula | 21.532047 | Vishakha | 1 | 5 | -0.126076 | R |
| SATURN | 238.869063 | Vrishchika | 28.869063 | Jyeshtha | 4 | 6 | -0.057603 | R |
| RAHU | 311.111905 | Kumbha | 11.111905 | Shatabhisha | 2 | 9 | -0.052976 | R |
| KETU | 131.111905 | Simha | 11.111905 | Magha | 4 | 3 | -0.052976 | R |

*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py (Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); (B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; (C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).

