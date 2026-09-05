"""Independent verification cases for the Core Engine Audit (2026-09-05).

Defines ~10 deliberately diverse birth cases, computes them through the frozen
engine, and (when run as a script) writes docs/verification_cases.md with the
complete calculated output of every case. tests/test_verification_cases.py
imports the same definitions and asserts internal-consistency invariants.

Read-only with respect to the engine: nothing here changes a convention.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from vedic_chart.astronomy.positions import Body, calculate_positions, ephemeris_session  # noqa: E402
from vedic_chart.chart.assemble import assemble_chart  # noqa: E402
from vedic_chart.chart.model import BirthChart  # noqa: E402
from vedic_chart.inputs.model import BirthChartRequest  # noqa: E402
from vedic_chart.location.model import ResolvedLocation  # noqa: E402
from vedic_chart.location.offline.resolver import OfflineLocationResolver  # noqa: E402
from vedic_chart.sidereal.positions import calculate_sidereal_positions  # noqa: E402
from vedic_chart.time.julian_day import julian_day_ut  # noqa: E402
from vedic_chart.time.local_time import NonexistentLocalTimeError, normalize_birth_time  # noqa: E402
from vedic_chart.vedic.grahas import Graha  # noqa: E402

EPHE_DIR = str(ROOT / "ephe")
FIXTURE_DB = ROOT / "tests" / "fixtures" / "geodata_fixture.sqlite"


class FixedResolver:
    """Protocol-conformant resolver over explicit coordinates (test aid)."""

    def __init__(self, places: dict[str, ResolvedLocation]) -> None:
        self._places = places

    def resolve(self, place_query: str) -> ResolvedLocation:
        return self._places[place_query]


PLACES = {
    "Sydney": ResolvedLocation("Sydney, New South Wales, Australia", -33.8688, 151.2093, "Australia/Sydney"),
    "New York": ResolvedLocation("New York City, New York, United States", 40.7128, -74.0060, "America/New_York"),
    "London": ResolvedLocation("London, England, United Kingdom", 51.5074, -0.1278, "Europe/London"),
    "Kolkata": ResolvedLocation("Kolkata, West Bengal, India", 22.5726, 88.3639, "Asia/Kolkata"),
    "Kiritimati": ResolvedLocation("Kiritimati, Line Islands, Kiribati", 1.8721, -157.4278, "Pacific/Kiritimati"),
    "Midway": ResolvedLocation("Midway Atoll, United States Minor Outlying Islands", 28.2072, -177.3735, "Pacific/Midway"),
    "Tromso": ResolvedLocation("Tromsø, Troms, Norway", 69.6492, 18.9553, "Europe/Oslo"),
    "New Delhi": ResolvedLocation("New Delhi, Delhi, India", 28.6139, 77.2090, "Asia/Kolkata"),
}
FIXED = FixedResolver(PLACES)


@dataclass(frozen=True)
class Case:
    key: str
    title: str
    purpose: str
    request: BirthChartRequest
    resolver_name: str  # "fixture" or "fixed"
    expect_error: type | None = None
    notes: str = ""


def _req(y, m, d, hh, mm, ss=0, us=0, *, place):
    return BirthChartRequest.from_components(y, m, d, hh, mm, ss, us, place_query=place)


def _sun_sidereal(moment: datetime) -> float:
    return calculate_sidereal_positions(moment).bodies[Body.SUN].sidereal_longitude


def find_mesha_sankranti_2024() -> datetime:
    """Bisect the instant the Sun's Lahiri sidereal longitude crosses 0 deg (2024)."""
    lo = datetime(2024, 4, 12, tzinfo=timezone.utc)
    hi = datetime(2024, 4, 15, tzinfo=timezone.utc)
    f = lambda t: ((_sun_sidereal(t) + 180.0) % 360.0) - 180.0  # signed distance from 0
    assert f(lo) < 0 < f(hi), (f(lo), f(hi))
    for _ in range(60):
        mid = lo + (hi - lo) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return hi


def find_mercury_station_2024() -> datetime:
    from vedic_chart.ephemeris.swiss_ephemeris import MERCURY, calc_planet_position
    lo = datetime(2024, 3, 25, tzinfo=timezone.utc)
    hi = datetime(2024, 4, 10, tzinfo=timezone.utc)
    sp = lambda t: calc_planet_position(julian_day_ut(t), MERCURY).speed_longitude
    assert sp(lo) > 0 > sp(hi)
    for _ in range(60):
        mid = lo + (hi - lo) / 2
        if sp(mid) > 0:
            lo = mid
        else:
            hi = mid
    return lo


def build_cases() -> list[Case]:
    ist = timezone(timedelta(hours=5, minutes=30))
    sankranti = find_mesha_sankranti_2024()
    before = (sankranti - timedelta(seconds=30)).astimezone(ist)
    after = (sankranti + timedelta(seconds=30)).astimezone(ist)
    station = find_mercury_station_2024()
    st_before = (station - timedelta(minutes=1)).astimezone(ist)
    st_after = (station + timedelta(minutes=1)).astimezone(ist)

    return [
        Case("V01", "Jalandhar 1995-03-21 06:45 IST (anchored reference)",
             "Baseline chart used since the Lagna milestone; resolved through the offline fixture geocoder.",
             _req(1995, 3, 21, 6, 45, place="Jalandhar"), "fixture"),
        Case("V02", "Sydney 1988-01-26 14:00 AEDT (southern hemisphere, DST)",
             "Southern latitude ascendant geometry; Australia/Sydney daylight time (+11).",
             _req(1988, 1, 26, 14, 0, place="Sydney"), "fixed"),
        Case("V03", "New York 2023-03-12 02:30 (nonexistent local time)",
             "Birth time inside the DST spring-forward gap must be REJECTED, not guessed.",
             _req(2023, 3, 12, 2, 30, place="New York"), "fixed", expect_error=NonexistentLocalTimeError),
        Case("V04", "London 1943-07-15 12:00 (British Double Summer Time)",
             "Historical tzdata rule: wartime BDST, expected offset +02:00.",
             _req(1943, 7, 15, 12, 0, place="London"), "fixed"),
        Case("V05", "Kolkata 1943-01-01 12:00 (India war time +06:30)",
             "Historical Indian offset from tzdata; pre-independence chart.",
             _req(1943, 1, 1, 12, 0, place="Kolkata"), "fixed"),
        Case("V06a", "Kiritimati 2024-01-02 03:00 (+14) — date-line pair A",
             "Same UTC instant as V06b via a +14 zone; wall date one day LATER than Midway's.",
             _req(2024, 1, 2, 3, 0, place="Kiritimati"), "fixed"),
        Case("V06b", "Midway 2024-01-01 02:00 (−11) — date-line pair B",
             "Same UTC instant as V06a (2024-01-01T13:00Z). Positions must be identical; Lagna differs (different longitude).",
             _req(2024, 1, 1, 2, 0, place="Midway"), "fixed"),
        Case("V07", "Tromsø 1990-06-21 12:00 CEST (69.65°N, midsummer)",
             "High-latitude ascendant; polar caveat applies (non-uniform rising).",
             _req(1990, 6, 21, 12, 0, place="Tromso"), "fixed"),
        Case("V08a", "New Delhi, 30 s BEFORE Mesha Sankranti 2024 (boundary-hugging)",
             f"Sun < 0.0004° below the Meena/Mesha boundary at {sankranti.isoformat(timespec='seconds')}; must classify Meena.",
             _req(before.year, before.month, before.day, before.hour, before.minute, before.second, before.microsecond, place="New Delhi"), "fixed",
             notes="Sun expected in Meena (rashi index 11)."),
        Case("V08b", "New Delhi, 30 s AFTER Mesha Sankranti 2024 (boundary-hugging)",
             "Sun < 0.0004° above the boundary; must classify Mesha. Unrounded classification is what separates a and b.",
             _req(after.year, after.month, after.day, after.hour, after.minute, after.second, after.microsecond, place="New Delhi"), "fixed",
             notes="Sun expected in Mesha (rashi index 0)."),
        Case("V09a", "New Delhi, 1 min BEFORE Mercury station 2024-04-01",
             f"Station located at {station.isoformat(timespec='seconds')} UTC; Mercury speed ≈ +8e-5°/day → direct.",
             _req(st_before.year, st_before.month, st_before.day, st_before.hour, st_before.minute, st_before.second, st_before.microsecond, place="New Delhi"), "fixed"),
        Case("V09b", "New Delhi, 1 min AFTER Mercury station 2024-04-01",
             "Mercury speed ≈ −8e-5°/day → retrograde. Sign of a near-zero speed decides.",
             _req(st_after.year, st_after.month, st_after.day, st_after.hour, st_after.minute, st_after.second, st_after.microsecond, place="New Delhi"), "fixed"),
        Case("V10", "London 1840-05-10 08:00 (LMT era, pre-GMT)",
             "tzdata gives Europe/London LMT −00:01:15 before 1847-12-01; 19th-century ephemeris coverage.",
             _req(1840, 5, 10, 8, 0, place="London"), "fixed"),
    ]


def run_case(case: Case, fixture_resolver) -> BirthChart | Exception:
    resolver = fixture_resolver if case.resolver_name == "fixture" else FIXED
    try:
        return assemble_chart(case.request, resolver)
    except Exception as exc:  # recorded, not swallowed: the doc shows it
        return exc


def render(case: Case, result) -> str:
    out = [f"## {case.key} — {case.title}", "", f"*Purpose:* {case.purpose}", ""]
    r = case.request
    out.append(f"*Input:* {r.birth_date.isoformat()} {r.birth_time.isoformat()} local, place query `{r.place_query}` "
               f"(resolver: {case.resolver_name})")
    if isinstance(result, Exception):
        out += ["", f"**Result: `{type(result).__name__}`** — {result}", ""]
        out.append("*Verification class:* (A) internal — typed rejection is the specified behaviour; (C) conforms to the "
                   "no-silent-disambiguation rule. No external comparison applicable.")
        return "\n".join(out) + "\n"
    c: BirthChart = result
    utc_off = c.moment_utc.astimezone(timezone.utc)
    out += ["",
            f"*Resolved:* {c.location.canonical_name} — lat {c.location.latitude}, lon {c.location.longitude}, tz `{c.location.timezone_id}`",
            f"*UTC:* {utc_off.isoformat()}  *JD(UT):* {c.julian_day_ut!r}  *Ayanamsha:* {c.ayanamsa!r}",
            f"*Lagna:* tropical {c.lagna.tropical_longitude!r} → sidereal {c.lagna.sidereal_longitude!r} → "
            f"{c.lagna.placement.rashi_name} {c.lagna.placement.degrees_in_rashi:.6f}°, "
            f"{c.lagna.placement.nakshatra_name} pada {c.lagna.placement.pada}",
            "",
            "| Graha | Sidereal lon | Rashi | ° in rashi | Nakshatra | Pada | House | Speed °/day | Retro |",
            "|---|---:|---|---:|---|---:|---:|---:|---|"]
    for g in Graha:
        p = c.grahas[g]; pl = p.placement
        out.append(f"| {g.name} | {p.sidereal_longitude:.6f} | {pl.rashi_name} | {pl.degrees_in_rashi:.6f} | {pl.nakshatra_name} | {pl.pada} | {c.houses[g]} | {p.speed_longitude:+.6f} | {'R' if p.is_retrograde else 'D'} |")
    if case.notes:
        out += ["", f"*Notes:* {case.notes}"]
    out += ["",
            "*Verification class:* (A) internal invariants asserted by tests/test_verification_cases.py "
            "(Ketu opposition, house formula, sidereal = tropical − ayanamsha, placement = classify, tz validity); "
            "(B) astronomy rests on Swiss Ephemeris + the Lagna formula cross-check; "
            "(C) convention conformity per the AstroLearn spec. **External comparison needed:** full-chart agreement "
            "with an independent Lahiri/Whole-Sign implementation (e.g. Jagannatha Hora, Drik Panchang).", ""]
    return "\n".join(out) + "\n"


def main() -> None:
    with ephemeris_session(EPHE_DIR), OfflineLocationResolver(FIXTURE_DB) as fixture:
        cases = build_cases()
        parts = ["# Independent Verification Cases (Core Engine Audit, 2026-09-05)", "",
                 "Complete calculated output of every case, produced by `tools/audit/verification_cases.py` against the "
                 "frozen engine (252-test state). Values are printed at full precision (`repr`) where they feed later layers. "
                 "Nothing in these cases changes a convention; they record what the engine does today.", "",
                 "**Frame note:** the Lahiri ayanamsha is referred to the true equinox of date (`swe.get_ayanamsa_ex_ut(jd, 0)`), the same frame as the apparent tropical positions, so every sidereal longitude below equals Swiss Ephemeris' native `SEFLG_SIDEREAL` Lahiri value (Core Engine Audit OPEN-1, resolved 2026-09-05 with owner approval).", ""]
        for case in cases:
            parts.append(render(case, run_case(case, fixture)))
        (ROOT / "docs" / "verification_cases.md").write_text("\n".join(parts), encoding="utf-8")
        print(f"wrote docs/verification_cases.md with {len(cases)} cases")


if __name__ == "__main__":
    main()
