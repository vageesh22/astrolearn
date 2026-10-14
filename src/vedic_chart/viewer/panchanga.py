"""Viewer composition of the unchanged Panchanga Layers 16–18.

The server calls ``panchanga_document`` while holding ENGINE_LOCK. The chart
pipeline's ephemeris session has already closed; this adapter owns a second,
sequential session for sunrise and transition searches. It never assembles a
second chart. Instant elements come from ``panchanga_from_chart``; searches,
day membership and uncertainty are owned entirely by the existing core.
"""

from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.dasha import resolve_zone
from vedic_chart.panchanga import (
    PanchangaDayUnavailable,
    SunriseUnavailable,
    TransitionKind,
    UnsupportedInstantError,
    find_transitions,
    panchanga_day_containing,
    panchanga_from_chart,
)

SCHEMA = "vedic_chart.panchanga/1"
ELEMENTS = (
    (TransitionKind.TITHI, "Tithi"),
    (TransitionKind.NAKSHATRA, "Nakshatra"),
    (TransitionKind.YOGA, "Nitya yoga"),
    (TransitionKind.KARANA, "Karana"),
)
PLACEMENT_LABELS = {
    "within": "Within the day",
    "straddles_opening_reflected": "Opening window; already reflected at sunrise",
    "straddles_opening_after": "Opening window; change after sunrise",
    "at_or_before_closing": "Closing window; change at or before closing",
}
TIMING_NOTE = (
    "Times shown in tables are approximate, truncated to the second. A change "
    "lies in (before, after]; the after endpoint is not an exact event time. "
    "Exact calculation windows are available below."
)
SUNRISE_NOTE = (
    "Geometric Hindu sunrise: centre of the Sun, no atmospheric refraction. "
    "This differs from an upper-limb refracted sunrise. Vara follows sunrise, "
    "not civil midnight. High-latitude sunrise searches can be unavailable."
)


def _instant(moment, zone):
    local = moment.astimezone(zone)
    return {
        "utc": moment.isoformat(timespec="microseconds"),
        "local": local.isoformat(sep=" ", timespec="microseconds"),
        "display": local.replace(microsecond=0).isoformat(sep=" ", timespec="seconds"),
    }


def _element(value):
    detail = ""
    if hasattr(value, "paksha"):
        detail = f"{value.paksha.value.capitalize()} paksha; day {value.number_in_paksha}"
    elif hasattr(value, "pada"):
        detail = f"Pada {value.pada}"
    elif hasattr(value, "half"):
        detail = f"{value.half.value.capitalize()} half of the tithi"
    return {
        "name": value.name,
        "index": value.index,
        "number": value.number,
        "detail": detail,
    }


def _transition(value, zone):
    before = _instant(value.before_utc, zone)
    after = _instant(value.after_utc, zone)
    return {
        "kind": value.kind.value,
        "before": _element(value.before),
        "after": _element(value.after),
        "before_time": before,
        "after_time": after,
        "window": f"({before['local']}, {after['local']}]",
        "tolerance": str(value.tolerance),
        "ut1_note": value.uncertainty.ut1_note,
        "model_note": value.uncertainty.model_note,
    }


def _sunrise(value, zone):
    if isinstance(value, SunriseUnavailable):
        return {"status": "unavailable", "reason": value.reason}
    return {
        "status": "available",
        "previous": _instant(value.previous_utc, zone),
        "next": _instant(value.next_utc, zone),
    }


def _day_sunrise(value, zone):
    if value is None:
        return None
    document = _instant(value.utc, zone)
    document["located_by"] = value.located_by.value
    return document


def _placed(value, zone):
    document = _transition(value.transition, zone)
    document["placement"] = value.placement.value
    document["placement_label"] = PLACEMENT_LABELS[value.placement.value]
    return document


def _day(value, zone):
    if isinstance(value, PanchangaDayUnavailable):
        return {
            "status": "unavailable",
            "reason": value.reason.value,
            "reasons": list(value.layer16_reasons),
            "preceding_sunrise": _day_sunrise(value.preceding_sunrise, zone),
            "following_sunrise": _day_sunrise(value.following_sunrise, zone),
            "note": "No sunrise-to-sunrise day was found containing this instant. "
                    "Missing neighbours mean not found within the bounded search.",
        }
    return {
        "status": "available",
        "civil_date": value.civil_date.isoformat(),
        "sunrise_ordinal": value.sunrise_ordinal,
        "vara": value.vara.name,
        "opening": _day_sunrise(value.opening, zone),
        "closing": _day_sunrise(value.closing, zone),
        "at_opening": [
            {"kind": kind.value, "label": label,
             "value": _element(getattr(value.at_opening, kind.value))}
            for kind, label in ELEMENTS
        ],
        "transitions": [_placed(entry, zone) for entry in value.placed],
        "cells_at_closing": [_placed(entry, zone) for entry in value.cells_at_closing.values()],
        "unordered_pairs": [list(pair) for pair in value.listing.unordered_pairs],
        "note": "The day contains the selected instant by the core's Julian Day "
                "membership rule. Changes are listed by their after endpoint in "
                "[opening, closing); boundary-window notes are retained separately. "
                "The day can carry the previous civil date before sunrise.",
    }


def panchanga_document(chart, ephemeris_path):
    """Return a display document; caller must hold the viewer's engine lock.

    Unsupported search ranges produce a typed unavailable section, leaving
    the successful chart usable. Internal search failures remain exceptions:
    no civil-weekday fallback or fabricated boundary is substituted.
    """
    zone = resolve_zone(chart.location.timezone_id)
    document = {
        "schema": SCHEMA,
        "status": "available",
        "instant": _instant(chart.moment_utc, zone),
        "timezone_id": chart.location.timezone_id,
        "timing_note": TIMING_NOTE,
        "sunrise_note": SUNRISE_NOTE,
    }
    with ephemeris_session(str(ephemeris_path)):
        # Layer 17 validates its safe search range before the first planetary
        # call. Within that range Layer 16's bounded sunrise probes also fit.
        try:
            changes = find_transitions(chart.moment_utc)
        except UnsupportedInstantError as error:
            document.update(status="unavailable", reason=str(error))
            return document
        current = panchanga_from_chart(chart)
        try:
            day = panchanga_day_containing(
                chart.moment_utc,
                chart.location.latitude,
                chart.location.longitude,
                chart.location.timezone_id,
            )
        except UnsupportedInstantError as error:
            day_document = {"status": "unavailable", "reason": str(error)}
        else:
            day_document = _day(day, zone)

    rows = []
    for kind, label in ELEMENTS:
        element = getattr(current, kind.value)
        neighbour = changes.neighbours[kind]
        if element.index != neighbour.current.index:
            raise RuntimeError("Panchanga transition and chart classifications disagree.")
        rows.append({
            "kind": kind.value,
            "label": label,
            "value": _element(element),
            "previous": _transition(neighbour.previous, zone),
            "next": _transition(neighbour.next, zone),
        })
    document.update(
        elements=rows,
        vara=None if current.vara is None else {
            "name": current.vara.name,
            "weekday": current.vara.english_weekday,
        },
        sunrise=_sunrise(current.sunrise, zone),
        day=day_document,
        calculation_convention=current.calculation_convention,
        sunrise_convention=current.sunrise_convention,
    )
    return document
