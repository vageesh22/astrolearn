"""Panchanga viewer integration: core parity, edge cases and live HTTP.

These tests use the fixture DB and explicit locations, never production data.
No golden is regenerated; boundary values are compared with the unchanged
core in the same native environment.
"""

import json
from datetime import date, time

import pytest

from render_helpers import EPHE_DIR, FIXTURE_DB, REPO_ROOT
from test_viewer_server import post, start
from vedic_chart.app import ChartConfig, render_chart_and_dasha_at
from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.dasha import resolve_zone
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.model import ResolvedLocation
from vedic_chart.panchanga import (
    DayPlacement,
    PlacedTransition,
    TransitionKind,
    find_transitions,
    panchanga_day_containing,
    panchanga_from_chart,
)
from vedic_chart.viewer import panchanga as presentation
from vedic_chart.viewer import server, transport

JALANDHAR = ResolvedLocation("Jalandhar", 31.32556, 75.57917, "Asia/Kolkata")
JAMMU = ResolvedLocation("Jammu", 32.73528, 74.86167, "Asia/Kolkata")
LONDON = ResolvedLocation("London", 51.50853, -0.12574, "Europe/London")
TROMSO = ResolvedLocation("Tromso", 69.65, 18.96, "Europe/Oslo")


def result(day="1995-03-21", wall="06:45", location=JALANDHAR):
    request = BirthChartRequest(date.fromisoformat(day), time.fromisoformat(wall), location.canonical_name)
    return render_chart_and_dasha_at(
        request, location, ChartConfig(FIXTURE_DB, EPHE_DIR),
        transport.RENDERER_OPTIONS, transport.YEAR,
    )


@pytest.fixture(scope="module", params=[
    ("1995-03-21", "06:45", JALANDHAR),
    ("2001-02-04", "10:45", JAMMU),
    ("1995-03-21", "04:00", JALANDHAR),
    ("1890-03-21", "12:00", JALANDHAR),
    ("2026-10-25", "03:00", LONDON),
])
def example(request):
    chart = result(*request.param).chart
    doc = presentation.panchanga_document(chart, EPHE_DIR)
    with ephemeris_session(str(EPHE_DIR)):
        current = panchanga_from_chart(chart)
        changes = find_transitions(chart.moment_utc)
        day = panchanga_day_containing(
            chart.moment_utc, chart.location.latitude, chart.location.longitude,
            chart.location.timezone_id,
        )
    return chart, doc, current, changes, day


def test_instant_elements_and_vara_are_the_core_values(example):
    chart, doc, core, _changes, _day = example
    assert doc["status"] == "available"
    assert doc["instant"]["utc"] == chart.moment_utc.isoformat(timespec="microseconds")
    assert doc["instant"]["local"] == core.local_datetime.isoformat(sep=" ", timespec="microseconds")
    assert doc["vara"]["name"] == core.vara.name
    for row in doc["elements"]:
        value = getattr(core, row["kind"])
        assert (row["value"]["name"], row["value"]["index"], row["value"]["number"]) == (
            value.name, value.index, value.number,
        )
    assert json.loads(transport.encode(doc)) == doc


def test_every_transition_preserves_both_core_endpoints_and_offsets(example):
    chart, doc, _core, changes, _day = example
    zone = resolve_zone(chart.location.timezone_id)
    for row in doc["elements"]:
        neighbours = changes.neighbours[TransitionKind(row["kind"])]
        for direction in ("previous", "next"):
            expected = getattr(neighbours, direction)
            observed = row[direction]
            for side in ("before", "after"):
                instant = getattr(expected, f"{side}_utc")
                assert observed[f"{side}_time"]["utc"] == instant.isoformat(timespec="microseconds")
                assert observed[f"{side}_time"]["local"] == instant.astimezone(zone).isoformat(sep=" ", timespec="microseconds")
                assert observed[f"{side}_time"]["display"] == instant.astimezone(zone).replace(microsecond=0).isoformat(sep=" ", timespec="seconds")
            assert observed["before"]["index"] == expected.before.index
            assert observed["after"]["index"] == expected.after.index
            assert observed["ut1_note"] == expected.uncertainty.ut1_note
            assert observed["model_note"] == expected.uncertainty.model_note


def test_daily_day_boundaries_order_and_placement_come_from_layer18(example):
    _chart, doc, _core, _changes, day = example
    view = doc["day"]
    assert view["civil_date"] == day.civil_date.isoformat()
    assert view["sunrise_ordinal"] == day.sunrise_ordinal
    assert view["opening"]["utc"] == day.opening.utc.isoformat(timespec="microseconds")
    assert view["closing"]["utc"] == day.closing.utc.isoformat(timespec="microseconds")
    assert view["closing"]["located_by"] == day.closing.located_by.value
    assert len(view["transitions"]) == len(day.placed)
    for output, expected in zip(view["transitions"], day.placed):
        assert output["after_time"]["utc"] == expected.transition.after_utc.isoformat(timespec="microseconds")
        assert output["placement"] == expected.placement.value
    assert view["unordered_pairs"] == [list(pair) for pair in day.listing.unordered_pairs]
    assert len(view["cells_at_closing"]) == len(day.cells_at_closing)


def test_before_sunrise_belongs_to_previous_civil_day():
    doc = presentation.panchanga_document(result(wall="04:00").chart, EPHE_DIR)
    assert doc["day"]["civil_date"] == "1995-03-20"
    assert doc["vara"]["name"] == "Somavara"


def test_historical_second_offset_is_not_lost():
    doc = presentation.panchanga_document(result("1890-03-21", "12:00").chart, EPHE_DIR)
    assert doc["instant"]["display"].endswith("+05:21:10")
    assert all(row["next"]["after_time"]["display"].endswith("+05:21:10") for row in doc["elements"])


def test_polar_unavailability_keeps_four_elements_and_has_no_vara_fallback():
    doc = presentation.panchanga_document(result("2024-06-21", "12:00", TROMSO).chart, EPHE_DIR)
    assert doc["status"] == "available"
    assert len(doc["elements"]) == 4
    assert doc["vara"] is None
    assert doc["sunrise"]["status"] == "unavailable"
    assert doc["day"]["status"] == "unavailable"
    assert doc["day"]["reason"] == "sunrise_unavailable"


def test_transition_range_edge_leaves_a_typed_unavailable_section():
    doc = presentation.panchanga_document(result("1800-01-03", "12:00").chart, EPHE_DIR)
    assert doc["status"] == "unavailable"
    assert "supported range" in doc["reason"]


def test_daily_range_edge_preserves_instant_elements_and_transitions():
    doc = presentation.panchanga_document(result("1800-01-08", "12:00").chart, EPHE_DIR)
    assert doc["status"] == "available"
    assert len(doc["elements"]) == 4
    assert doc["day"]["status"] == "unavailable"
    assert "supported range" in doc["day"]["reason"]


@pytest.mark.parametrize("placement", list(DayPlacement))
def test_all_boundary_placements_are_preserved_without_membership_recomputation(placement):
    chart = result().chart
    with ephemeris_session(str(EPHE_DIR)):
        transition = find_transitions(chart.moment_utc).neighbours[TransitionKind.TITHI].next
    doc = presentation._placed(PlacedTransition(transition, placement), resolve_zone("Asia/Kolkata"))
    assert doc["placement"] == placement.value
    assert doc["placement_label"]
    assert doc["after_time"]["utc"] == transition.after_utc.isoformat(timespec="microseconds")


def test_http_reuses_the_one_chart_and_keeps_panchanga_inside_the_lock(monkeypatch):
    charts = []
    seen = []
    pipeline = server.render_chart_and_dasha_at
    compose = server.panchanga_document

    def capture(*args, **kwargs):
        built = pipeline(*args, **kwargs)
        charts.append(built.chart)
        return built

    def locked(chart, path):
        assert server.ENGINE_LOCK.locked()
        assert chart is charts[0]
        seen.append(chart)
        return compose(chart, path)

    monkeypatch.setattr(server, "render_chart_and_dasha_at", capture)
    monkeypatch.setattr(server, "panchanga_document", locked)
    running = start()
    try:
        answer = post(running)
        assert answer.status == 200
        assert len(charts) == len(seen) == 1
        assert list(answer.json())[-3:] == ["south_indian_svg", "overlay", "panchanga"]
        assert answer.json()["panchanga"]["instant"]["utc"] == charts[0].moment_utc.isoformat(timespec="microseconds")
    finally:
        running.stop()


@pytest.mark.parametrize("wall,place_text,place_id", [
    ("", "", ""), ("06:45", "", ""),
    ("", "Jalandhar, Punjab, India", "1268782"),
    ("06:45", "Jalandhar, Punjab, India", "1268782"),
])
def test_http_panchanga_uses_the_effective_defaults(wall, place_text, place_id):
    running = start()
    try:
        answer = post(running, payload={"date": "1995-03-21", "time": wall,
                                       "place_text": place_text, "place_id": place_id})
        assert answer.status == 200
        doc = answer.json()
        assert doc["panchanga"]["timezone_id"] == doc["effective"]["place"]["timezone_id"]
        assert doc["panchanga"]["instant"]["display"].startswith(f"1995-03-21 {'06:45:00' if wall else '12:00:00'}")
        assert doc["assumptions"]["any"] is (not wall or not place_id)
    finally:
        running.stop()


def test_internal_panchanga_failure_returns_no_partial_document_and_releases_lock(monkeypatch):
    def fail(*args):
        raise RuntimeError("injected search failure")
    monkeypatch.setattr(server, "panchanga_document", fail)
    running = start()
    try:
        answer = post(running)
        assert answer.status == 500
        assert answer.json()["error"]["kind"] == "unexpected"
        assert "svg" not in answer.json()
        assert not server.ENGINE_LOCK.locked()
    finally:
        running.stop()


def test_the_page_reads_the_document_and_has_no_new_request():
    source = (REPO_ROOT / "src/vedic_chart/viewer/static/viewer.js").read_text()
    section = source[source.index("function panchangaTable"):source.index("function fillSummary")]
    assert "fetch(" not in section
    assert "data.elements" in section and "data.day" in section
    assert "day.cells_at_closing" in section
    assert "day.unordered_pairs" in section
    assert "Uses assumed birth details" in section
    assert "fillPanchanga(fragment, document_);" in source
