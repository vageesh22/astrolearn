"""Structured positions preserve assembled values, HTTP behavior and old output.

No golden regeneration: existing viewer fixtures continue to pin the complete
pre-extension response. These tests independently check the additive block
against the chart object, including synthetic unrounded boundary values.
"""
import json
import math
from dataclasses import replace

import pytest

from vedic_chart.vedic.grahas import Graha, GrahaPosition
from vedic_chart.vedic.divisions import classify
from vedic_chart.viewer import transport
from vedic_chart.viewer import server as server_module
from test_viewer_transport import built, effective_input, _body
from test_viewer_server import start, post, JALANDHAR_ID, JALANDHAR_LABEL


@pytest.fixture(scope='module')
def reference():
    return built()


def assert_position(sent, original):
    p = original.placement
    assert sent['sidereal_longitude'] == repr(original.sidereal_longitude)
    assert float(sent['sidereal_longitude']) == original.sidereal_longitude
    assert sent['degrees_in_sign'] == repr(p.degrees_in_rashi)
    assert sent['sign']['index'] == p.rashi_index
    assert sent['sign']['number'] == p.rashi_number
    assert sent['sign']['name'] == p.rashi_name
    assert sent['nakshatra'] == dict(index=p.nakshatra_index,
        number=p.nakshatra_number, name=p.nakshatra_name, pada=p.pada)


@pytest.mark.parametrize('graha', list(Graha))
def test_every_planet_preserves_assembled_values(reference, graha):
    _, result, document = reference
    sent = next(p for p in document['planetary_positions']['planets'] if p['key'] == graha.value)
    original = result.chart.grahas[graha]
    assert_position(sent, original)
    assert sent['name'] == graha.value.capitalize()
    assert sent['house'] == result.chart.houses[graha]
    assert sent['is_retrograde'] is original.is_retrograde
    assert sent['speed_longitude'] == repr(original.speed_longitude)
    assert sent['kind'] == ('lunar_node' if graha in (Graha.RAHU, Graha.KETU) else 'planet')


def test_ascendant_is_explicit_and_has_no_invented_motion(reference):
    _, result, document = reference
    sent = document['planetary_positions']['ascendant']
    assert_position(sent, result.chart.lagna)
    assert sent['key'] == sent['kind'] == 'ascendant'
    assert sent['house'] == 1
    assert sent['is_retrograde'] is None
    assert sent['speed_longitude'] is None


def test_block_schema_units_membership_and_roundtrip(reference):
    _, result, document = reference
    block = document['planetary_positions']
    assert block['schema'] == 'vedic_chart.planetary_positions/1'
    assert block['longitude_frame'] == 'sidereal'
    assert block['angular_unit'] == 'degree'
    assert block['speed_unit'] == 'degree/day'
    assert block['node_convention'] == 'mean'
    assert block['ayanamsa_degrees'] == repr(result.chart.ayanamsa)
    assert [p['key'] for p in block['planets']] == [g.value for g in Graha]
    assert len(block['planets']) == 9
    assert json.loads(transport.encode(document)) == document
    nodes = [p for p in block['planets'] if p['kind'] == 'lunar_node']
    assert all(p['is_retrograde'] for p in nodes)
    assert nodes[0]['speed_longitude'] == nodes[1]['speed_longitude']


@pytest.mark.parametrize('index', range(12))
@pytest.mark.parametrize('side', [-1, 0, 1])
def test_sign_boundaries_are_taken_from_core_classification(reference, index, side):
    # Synthetic placement fixture: changing chart data while preserving its SVG
    # proves transport uses the chart, not SVG labels or independent arithmetic.
    longitude = index * 30.0
    if side:
        longitude = math.nextafter(longitude, math.inf if side > 0 else -math.inf)
    if longitude < 0:  # Avoid the frozen core's documented negative-zero seam.
        longitude = math.nextafter(360.0, 0.0)
    parsed, result, old_document = reference
    position = GrahaPosition(longitude, -0.0123456789012345, True, classify(longitude))
    grahas = dict(result.chart.grahas)
    grahas[Graha.MERCURY] = position
    chart = replace(result.chart, grahas=grahas)
    modified = replace(result, chart=chart)
    document = transport.serialize(modified, parsed, effective=effective_input(parsed))
    sent = next(p for p in document['planetary_positions']['planets'] if p['key'] == 'mercury')
    assert_position(sent, position)
    assert sent['sign']['english_name'] == (
        'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
        'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces'
    )[position.placement.rashi_index]
    assert document['svg'] == old_document['svg']
    assert document['rows'] == old_document['rows']
    assert sent['speed_longitude'] == repr(position.speed_longitude)


@pytest.mark.parametrize('speed', [-1.23456789012345, 0.0, 1.23456789012345])
def test_motion_flags_are_copied_even_when_svg_hides_them(reference, speed):
    parsed, result, _ = reference
    old = result.chart.grahas[Graha.MARS]
    grahas = dict(result.chart.grahas)
    grahas[Graha.MARS] = replace(old, speed_longitude=speed, is_retrograde=speed < 0)
    modified = replace(result, chart=replace(result.chart, grahas=grahas))
    document = transport.serialize(modified, parsed, effective=effective_input(parsed))
    sent = next(p for p in document['planetary_positions']['planets'] if p['key'] == 'mars')
    assert sent['is_retrograde'] is (speed < 0)
    assert sent['speed_longitude'] == repr(speed)


@pytest.mark.parametrize('time,place_text,place_id', [
    ('06:45', JALANDHAR_LABEL, str(JALANDHAR_ID)),
    ('', JALANDHAR_LABEL, str(JALANDHAR_ID)),
    ('06:45', '', ''), ('', '', ''),
    ('06:45', 'London, England, United Kingdom', '2643743'),
])
def test_http_positions_come_from_exactly_one_pipeline_call(monkeypatch, time, place_text, place_id):
    real = server_module.render_chart_and_dasha_at
    captured = []
    def spy(*args, **kwargs):
        result = real(*args, **kwargs)
        captured.append(result)
        return result
    monkeypatch.setattr(server_module, 'render_chart_and_dasha_at', spy)
    live = start()
    try:
        response = post(live, payload=dict(date='1995-03-21', time=time,
                       place_text=place_text, place_id=place_id))
        assert response.status == 200
        document = response.json()
        assert len(captured) == 1
        result = captured[0]
        for sent in document['planetary_positions']['planets']:
            assert_position(sent, result.chart.grahas[Graha(sent['key'])])
        assert_position(document['planetary_positions']['ascendant'], result.chart.lagna)
        assert document['svg'] == result.svg
        assert len(document['rows']) == 819
        assert document['birth']['zone'] == result.chart.location.timezone_id
        assert document['assumptions']['time'] is (time == '')
        assert document['assumptions']['place'] is (place_id == '')
    finally:
        live.stop()
