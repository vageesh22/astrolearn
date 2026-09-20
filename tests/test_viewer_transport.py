"""The transport contract: serialisation and Layer 13 parity (14.13.1, 15.13).

Schema ``vedic_chart.viewer/2``: the four-key request of Layer 15 section 7.2,
the ``effective`` and ``assumptions`` blocks of section 7.3, the fixed daśā
convention of section 6, and no ``resolution`` block -- no name is resolved on
this path, so there is no decision to report (section 5.4).

Over the committed fixture geodata database and the committed ``ephe/``
directory, exactly as ``tests/test_app_dasha.py`` does. No production database,
no network, no clock.

Three kinds of claim are made here.

**Nothing is lost.** Every ``Fraction`` in the document parses back to the
timeline's own exact value, every ``utc``/``local`` string parses back through
``datetime.fromisoformat`` to the core's own instant, the row block is
``dasha_rows(timeline, depth=3)`` in its own order, and the whole document
survives ``json.dumps(..., allow_nan=False)`` and back.

**Nothing is restated differently.** Specification 9.5 lists the seven
presentation rules ``transport.py`` repeats because Layer 13 keeps its
formatting helpers private. Each is checked here against the *text*
``render_dasha_text`` prints for the same birth, convention and zone -- not
against a literal in this file -- so the page and the committed daśā table
cannot drift apart.

**Nothing is platform-pinned except the one golden.** Swiss Ephemeris float
results differ between architectures in the last ulp, so every assertion below
compares the document with values computed in the same process. The single
exception is ``tests/fixtures/viewer/jalandhar_365256363.json``, which pins a
whole document and must be regenerated on a change of platform. The two
divergence fixtures are built from ``build_vimshottari`` with exact rational
arithmetic and a synthetic birth instant, so they are platform-independent and
are compared strictly.

Regenerating the fixtures (from the repository root, one command)::

    PYTHONPATH=src .venv/bin/python tests/test_viewer_transport.py --write-fixtures

It rewrites all three files under ``tests/fixtures/viewer/`` from the
resources this suite uses, and prints each path it wrote. Run it on the machine
whose Swiss Ephemeris results the golden is meant to pin.
"""

import json
import math
import re
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import pytest

from render_helpers import EPHE_DIR, FIXTURE_DB, REPO_ROOT
from vedic_chart.app import ChartConfig, render_chart_and_dasha_at
from vedic_chart.dasha import (
    YearConvention,
    build_vimshottari,
    dasha_rows,
    render_dasha_text,
)
from vedic_chart.dasha.table import ABBREVIATIONS
from vedic_chart.inputs.model import (
    BirthChartRequest,
    InvalidBirthDateError,
    InvalidBirthTimeError,
)
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.representation.d1 import (
    AYANAMSHA,
    ENGINE_SPEC,
    HOUSE_SYSTEM,
    NODE,
    ZODIAC,
)
from vedic_chart.vedic.grahas import Graha
from vedic_chart.viewer import transport
from vedic_chart.viewer.transport import TransportError

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "viewer"
GOLDEN_PATH = FIXTURE_DIR / "jalandhar_365256363.json"
DIVERGENCE_SU_MO_PATH = FIXTURE_DIR / "divergence_su_mo.json"
DIVERGENCE_KE_PATH = FIXTURE_DIR / "divergence_ke.json"

ZONE = "Asia/Kolkata"
DEPTH = 3
ROW_COUNT = 819

#: The exact record this module uses throughout, and the label this server
#: builds for it. The page sends both back on a selection, and the submitted
#: text must equal the label (Layer 15 section 5.3).
JALANDHAR_ID = 1268782
JALANDHAR_LABEL = "Jalandhar, Punjab, India"
BIRTH_DATE = "1995-03-21"
BIRTH_TIME = "06:45"

REGENERATE = (
    "Regenerate it on this machine with:\n"
    "    PYTHONPATH=src .venv/bin/python tests/test_viewer_transport.py "
    "--write-fixtures\n"
    "Swiss Ephemeris float results differ between architectures in the last "
    "ulp, so a whole-document golden is pinned to the platform that produced "
    "it."
)

#: Specification 8.3 and 13.1: the two Layer 12 inputs for which the nominal
#: and the quantized birth chains differ, with the chains the specification
#: documents for each.
DIVERGENCE_CASES = {
    "su_mo": {
        "path": DIVERGENCE_SU_MO_PATH,
        "longitude": math.nextafter(40.0, 0),
        "longitude_text": "math.nextafter(40.0, 0)",
        "nominal": [["sun"], ["sun", "venus"], ["sun", "venus", "ketu"]],
        "quantized": [["moon"], ["moon", "moon"], ["moon", "moon", "moon"]],
    },
    "ke": {
        "path": DIVERGENCE_KE_PATH,
        "longitude": 3.666666666666666,
        "longitude_text": "3.666666666666666",
        "nominal": [["ketu"], ["ketu", "sun"], ["ketu", "sun", "venus"]],
        "quantized": [["ketu"], ["ketu", "moon"], ["ketu", "moon", "moon"]],
    },
}

#: The synthetic birth the divergence fixtures are anchored to. It is not a
#: resolved place and no chart is assembled: these documents exist to exercise
#: the two chains and the two marker columns, nothing else.
SYNTHETIC_BIRTH = datetime(2000, 1, 1, 0, 0, tzinfo=timezone.utc)
SYNTHETIC_SUBMITTED = {
    "date": "2000-01-01",
    "time": "05:30",
    "place_text": "PLACEHOLDER (synthetic fixture, no place was resolved)",
    "place_id": "0",
}
SYNTHETIC_NORMALIZED = {
    "date": "2000-01-01",
    "time": "05:30:00",
    "place_id": "0",
    "place_label": SYNTHETIC_SUBMITTED["place_text"],
}

#: The renderer's accessibility shape, with nothing drawn inside it. The
#: divergence fixtures are transport documents, not drawings.
PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" role="img" '
    'aria-labelledby="d1-title" aria-describedby="d1-desc" '
    'viewBox="0 0 1080 1080">'
    '<title id="d1-title">Fixture</title>'
    '<desc id="d1-desc">Fixture</desc></svg>'
)

PLACEHOLDER_LOCATION = {
    "canonical_name": "PLACEHOLDER, synthetic fixture, no place was resolved",
    "latitude": "0.0",
    "longitude": "0.0",
    "timezone_id": ZONE,
}

#: The two Layer 15 blocks, as placeholders: these documents were built from
#: ``build_vimshottari`` directly, so no record was looked up and nothing was
#: assumed. They are page-shaped, not descriptions of a real birth.
PLACEHOLDER_EFFECTIVE = {
    "date": SYNTHETIC_NORMALIZED["date"],
    "time": SYNTHETIC_NORMALIZED["time"],
    "time_assumed": False,
    "place": {
        "geoname_id": 0,
        "label": SYNTHETIC_SUBMITTED["place_text"],
        "name": "PLACEHOLDER",
        "admin1_name": None,
        "country_name": None,
        "feature_code": None,
        "population": 0,
        "latitude": "0.0",
        "longitude": "0.0",
        "timezone_id": ZONE,
        "matched_name": None,
    },
    "place_assumed": False,
    "source": "selected",
}

PLACEHOLDER_ASSUMPTIONS = {
    "any": False,
    "time": False,
    "place": False,
    "labels": [],
}


# --- building the documents ------------------------------------------------


def _config() -> ChartConfig:
    return ChartConfig(geodata_path=FIXTURE_DB, ephemeris_path=EPHE_DIR)


def _body(**changes) -> bytes:
    """The reference submission: date and time supplied, place selected."""
    document = {
        "date": BIRTH_DATE,
        "time": BIRTH_TIME,
        "place_text": JALANDHAR_LABEL,
        "place_id": str(JALANDHAR_ID),
    }
    document.update(changes)
    return json.dumps(document).encode("utf-8")


def _record(geoname_id: int):
    """One geodata record, exactly as the server looks it up (section 5.3)."""
    with OfflineLocationResolver(FIXTURE_DB) as offline:
        location, candidate = offline.record(geoname_id)
        return location, candidate, OfflineLocationResolver.candidate_label(
            candidate
        )


def effective_input(parsed, *, place_assumed: bool = False):
    """The effective-input step of section 7.2, as the server performs it.

    The server owns this construction; this module repeats the two lines it
    needs so that the transport can be exercised without an HTTP server, and
    ``tests/test_viewer_server.py`` is what proves the server's own version.
    """
    geoname_id = JALANDHAR_ID if parsed.place_id is None else parsed.place_id
    location, candidate, label = _record(geoname_id)
    return transport.EffectiveInput(
        request=BirthChartRequest(
            birth_date=parsed.birth_date,
            birth_time=parsed.birth_time,
            place_query=label,
        ),
        location=location,
        place=candidate,
        label=label,
        place_assumed=place_assumed,
        time_assumed=parsed.time_assumed,
        source=(
            transport.SOURCE_DEFAULT
            if place_assumed
            else transport.SOURCE_SELECTED
        ),
    )


def _built(body: bytes, *, place_assumed: bool = False):
    parsed = transport.parse_request(body)
    effective = effective_input(parsed, place_assumed=place_assumed)
    result = render_chart_and_dasha_at(
        effective.request,
        effective.location,
        _config(),
        transport.RENDERER_OPTIONS,
        transport.YEAR,
    )
    return (
        parsed,
        result,
        transport.serialize(result, parsed, effective=effective),
    )


_CACHE: dict = {}


def built(body: bytes = None, *, place_assumed: bool = False):
    """One pipeline run per distinct body, shared by every test here."""
    body = _body() if body is None else body
    key = (body, place_assumed)
    if key not in _CACHE:
        _CACHE[key] = _built(body, place_assumed=place_assumed)
    return _CACHE[key]


@pytest.fixture(scope="module")
def jalandhar():
    return built()


@pytest.fixture(scope="module")
def defaulted():
    """The same birth with both optional fields blank (sections 2, 7.3)."""
    return built(_body(time="", place_text="", place_id=""), place_assumed=True)


@pytest.fixture(scope="module")
def table_text():
    _parsed, result, _document = built()
    return render_dasha_text(
        result.timeline, zone=ZONE, depth=DEPTH, precision="second"
    )


def divergence_document(case: dict) -> dict:
    """One divergence case as a full page-shaped document (8.3, 13.1)."""
    timeline = build_vimshottari(
        case["longitude"], SYNTHETIC_BIRTH, YearConvention.FIXED_365_256363
    )
    return transport.serialize_timeline_document(
        timeline,
        submitted=SYNTHETIC_SUBMITTED,
        normalized=SYNTHETIC_NORMALIZED,
        zone_key=ZONE,
        birth_utc=timeline.birth_utc,
        svg=PLACEHOLDER_SVG,
        engine={
            "zodiac": ZODIAC,
            "ayanamsha": AYANAMSHA,
            "house_system": HOUSE_SYSTEM,
            "node": NODE,
            "engine_spec": ENGINE_SPEC,
            "validation_note": transport.VALIDATION_NOTE,
        },
        location=PLACEHOLDER_LOCATION,
        effective=PLACEHOLDER_EFFECTIVE,
        assumptions=PLACEHOLDER_ASSUMPTIONS,
    )


# --- reading the Layer 13 text --------------------------------------------


def header_lines(text: str):
    return text.split("\n\n", 1)[0].splitlines()


def table_rows(text: str):
    """The Layer 13 table as ``(level, chain, start, end, n, q)`` tuples.

    Columns are read at the header's own offsets rather than by splitting on
    whitespace: an absent marker is a blank column, and a timestamp carries one
    space of its own, so splitting would confuse ``N``-only with ``Q``-only
    rows.
    """
    body = text.split("\n\n", 1)[1].splitlines()
    header = body[0]
    at_chain = header.index("Chain")
    at_start = header.index("Start")
    at_end = header.index("End")
    at_n = header.index("N")
    at_q = header.index("Q")

    parsed = []
    for line in body[1:]:
        if not line.strip():
            continue
        padded = line.ljust(at_q + 1)
        parsed.append(
            (
                padded[0:at_chain].strip(),
                padded[at_chain:at_start].strip(),
                padded[at_start:at_end].strip(),
                padded[at_end:at_n].strip(),
                padded[at_n:at_q].strip(),
                padded[at_q:].strip(),
            )
        )
    return parsed


# --- the golden document ---------------------------------------------------


def _legacy_document(document):
    """Keep the complete pre-extension golden without platform regeneration."""
    return {key: value for key, value in document.items() if key != "planetary_positions"}


def test_the_golden_transport_document_is_reproduced(jalandhar):
    _parsed, _result, document = jalandhar
    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    legacy = _legacy_document(document)
    assert legacy == expected, (
        f"the transport document no longer equals {GOLDEN_PATH}.\n{REGENERATE}"
    )


def test_the_golden_is_the_encoder_s_own_bytes(jalandhar):
    """The legacy projection retains the committed encoder bytes."""
    _parsed, _result, document = jalandhar
    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    legacy = _legacy_document(document)
    assert transport.encode(legacy) == transport.encode(expected), REGENERATE


# --- shape ------------------------------------------------------------------


def test_the_document_carries_the_whole_depth_three_tree():
    _parsed, result, document = built()
    rows = dasha_rows(result.timeline, depth=DEPTH)

    assert len(document["rows"]) == ROW_COUNT
    assert len(rows) == ROW_COUNT
    for sent, row in zip(document["rows"], rows):
        assert sent["level"] == row.level
        assert sent["lords"] == [lord.value for lord in row.lords]


def test_the_row_order_is_the_core_s_own_pre_order():
    _parsed, result, document = built()
    rows = dasha_rows(result.timeline, depth=DEPTH)

    assert [(row.level, row.lords) for row in rows] == [
        (sent["level"], tuple(_grahas(sent["lords"]))) for sent in document["rows"]
    ]


def _grahas(keys):
    return [Graha(key) for key in keys]


def test_the_sibling_positions_are_one_to_nine(jalandhar):
    _parsed, _result, document = jalandhar

    for level in (1, 2, 3):
        positions = [
            row["posinset"] for row in document["rows"] if row["level"] == level
        ]
        assert set(positions) == set(range(1, 10))
    assert [row["posinset"] for row in document["rows"][:1]] == [1]


def test_the_schema_and_the_top_level_keys_are_the_contract_s(jalandhar):
    _parsed, _result, document = jalandhar

    assert document["schema"] == "vedic_chart.viewer/2"
    assert set(document) == {
        "schema",
        "request",
        "engine",
        "location",
        "effective",
        "assumptions",
        "birth",
        "svg",
        "timeline",
        "birth_chain",
        "rows",
        "planetary_positions",
    }
    # Section 5.4: the Layer 14 resolution block is absent, not emptied.
    assert "resolution" not in document


def test_the_svg_travels_verbatim(jalandhar):
    _parsed, result, document = jalandhar

    assert document["svg"] == result.svg
    assert document["svg"].startswith("<svg")


def test_the_document_survives_the_encoder_and_comes_back_equal(jalandhar):
    _parsed, _result, document = jalandhar

    encoded = transport.encode(document)
    assert json.loads(encoded.decode("utf-8")) == document
    # The encoder's own refusal, stated as a test rather than as a comment.
    with pytest.raises(ValueError):
        json.dumps({"x": float("nan")}, allow_nan=False)


def test_no_json_number_carries_a_boundary(jalandhar):
    """9.1 rule 2: only small structural integers are JSON numbers."""
    _parsed, _result, document = jalandhar
    row = document["rows"][0]

    for key in ("chain", "chain_names"):
        assert isinstance(row[key], str)
    for key in ("start", "end"):
        for spelling in ("utc", "local", "local_seconds"):
            assert isinstance(row[key][spelling], str)
    for key in ("nominal_start", "nominal_end", "nominal_years"):
        assert isinstance(row[key]["num"], str)
        assert isinstance(row[key]["den"], str)
    assert isinstance(document["timeline"]["moon_sidereal_longitude"], str)
    assert isinstance(document["location"]["latitude"], str)
    assert isinstance(document["effective"]["place"]["latitude"], str)


# --- losslessness -----------------------------------------------------------


def test_every_fraction_round_trips_to_the_core_s_own_value():
    _parsed, result, document = built()
    timeline = result.timeline
    rows = dasha_rows(timeline, depth=DEPTH)

    block = document["timeline"]
    for key, value in (
        ("elapsed_fraction", timeline.elapsed_fraction),
        ("remaining_fraction", timeline.remaining_fraction),
        ("elapsed_years", timeline.elapsed_years),
        ("balance_years", timeline.balance_years),
    ):
        sent = block[key]
        assert Fraction(int(sent["num"]), int(sent["den"])) == value

    sent_days = block["year_convention"]["days"]
    assert Fraction(int(sent_days["num"]), int(sent_days["den"])) == (
        timeline.year.value
    )

    for sent, row in zip(document["rows"], rows):
        for key, value in (
            ("nominal_start", row.nominal_start),
            ("nominal_end", row.nominal_end),
        ):
            assert Fraction(int(sent[key]["num"]), int(sent[key]["den"])) == value


def test_every_instant_round_trips_through_from_isoformat(jalandhar):
    _parsed, result, document = jalandhar
    rows = dasha_rows(result.timeline, depth=DEPTH)

    for sent, row in zip(document["rows"], rows):
        for key, moment in (("start", row.start_utc), ("end", row.end_utc)):
            assert datetime.fromisoformat(sent[key]["utc"]) == moment
            assert datetime.fromisoformat(sent[key]["local"]) == moment

    assert datetime.fromisoformat(document["birth"]["utc"]) == (
        result.chart.moment_utc
    )
    assert datetime.fromisoformat(document["birth"]["local"]) == (
        result.chart.moment_utc
    )
    for key, moment in (
        ("cycle_start", result.timeline.cycle_start_utc),
        ("cycle_end", result.timeline.cycle_end_utc),
    ):
        block = document["timeline"][key]
        assert datetime.fromisoformat(block["utc"]) == moment
        assert datetime.fromisoformat(block["local"]) == moment


def test_the_microsecond_spelling_is_used_everywhere(jalandhar):
    _parsed, _result, document = jalandhar
    microseconds = re.compile(r"\.[0-9]{6}[+-][0-9]{2}:[0-9]{2}")

    for row in document["rows"][:40]:
        assert microseconds.search(row["start"]["utc"])
        assert microseconds.search(row["start"]["local"])
    assert microseconds.search(document["birth"]["local"])


# --- the request echo -------------------------------------------------------


def test_the_submitted_strings_are_echoed_byte_for_byte(jalandhar):
    _parsed, _result, document = jalandhar

    assert document["request"]["submitted"] == {
        "date": BIRTH_DATE,
        "time": BIRTH_TIME,
        "place_text": JALANDHAR_LABEL,
        "place_id": str(JALANDHAR_ID),
    }
    assert document["request"]["submitted"]["time"] == "06:45"


def test_the_normalized_block_carries_the_effective_values(jalandhar):
    parsed, _result, document = jalandhar

    assert document["request"]["normalized"] == {
        "date": parsed.birth_date.isoformat(),
        "time": "06:45:00",
        "place_id": str(JALANDHAR_ID),
        "place_label": JALANDHAR_LABEL,
    }


def test_a_blank_submission_echoes_the_blanks_and_normalizes_the_defaults(
    defaulted
):
    """Section 7.3: the submitted strings are what arrived, blanks included."""
    _parsed, _result, document = defaulted

    assert document["request"]["submitted"] == {
        "date": BIRTH_DATE,
        "time": "",
        "place_text": "",
        "place_id": "",
    }
    assert document["request"]["normalized"] == {
        "date": BIRTH_DATE,
        "time": "12:00:00",
        "place_id": str(JALANDHAR_ID),
        "place_label": JALANDHAR_LABEL,
    }


def test_the_engine_block_is_the_five_descriptors_and_the_note(jalandhar):
    _parsed, result, document = jalandhar
    meta = result.d1.meta

    assert document["engine"] == {
        "zodiac": meta.zodiac,
        "ayanamsha": meta.ayanamsha,
        "house_system": meta.house_system,
        "node": meta.node,
        "engine_spec": meta.engine_spec,
        "validation_note": transport.VALIDATION_NOTE,
    }
    assert "no exact compatibility claim" in document["engine"]["validation_note"]
    # Specification 6: no Swiss Ephemeris version string is transported.
    assert "swisseph" not in json.dumps(document["engine"]).lower()


def test_the_effective_block_describes_the_selected_record(jalandhar):
    """Section 7.3: which record, which time, and where each came from."""
    _parsed, _result, document = jalandhar
    _location, candidate, label = _record(JALANDHAR_ID)
    block = document["effective"]

    assert block == {
        "date": BIRTH_DATE,
        "time": "06:45:00",
        "time_assumed": False,
        "place": {
            "geoname_id": JALANDHAR_ID,
            "label": label,
            "name": candidate.name,
            "admin1_name": candidate.admin1_name,
            "country_name": candidate.country_name,
            "feature_code": candidate.feature_code,
            "population": candidate.population,
            "latitude": repr(candidate.latitude),
            "longitude": repr(candidate.longitude),
            "timezone_id": candidate.timezone_id,
            # Always null here, selected or default: a matching name is a
            # suggestion-list fact, and this path observed none.
            "matched_name": None,
        },
        "place_assumed": False,
        "source": "selected",
    }
    assert candidate.matched_name == "Jalandhar"


def test_the_effective_block_describes_the_default_record(defaulted):
    """The default's ``matched_name`` is null: nothing matched a name."""
    _parsed, _result, document = defaulted
    block = document["effective"]

    assert block["source"] == "default"
    assert block["place_assumed"] is True
    assert block["time_assumed"] is True
    assert block["time"] == "12:00:00"
    assert block["place"]["geoname_id"] == JALANDHAR_ID
    assert block["place"]["label"] == JALANDHAR_LABEL
    assert block["place"]["matched_name"] is None
    assert block["place"]["timezone_id"] == ZONE


def test_the_effective_place_never_reports_a_matched_name(jalandhar, defaulted):
    """Section 7.3 as amended: null on both paths, never the record's name."""
    for _parsed, _result, document in (jalandhar, defaulted):
        assert document["effective"]["place"]["matched_name"] is None


def test_nothing_is_assumed_when_both_optional_fields_are_supplied(jalandhar):
    _parsed, _result, document = jalandhar

    assert document["assumptions"] == {
        "any": False,
        "time": False,
        "place": False,
        "labels": [],
    }


def test_the_assumptions_block_states_both_assumptions_in_english(defaulted):
    """Section 7.3: the sentences are produced here, once, not in the page."""
    _parsed, _result, document = defaulted

    assert document["assumptions"] == {
        "any": True,
        "time": True,
        "place": True,
        "labels": [
            "Time 12:00:00 assumed: no time was supplied",
            f"Birthplace {JALANDHAR_LABEL} assumed: the configured default",
        ],
    }


def test_one_assumption_alone_is_labelled_alone():
    """A supplied time with a blank birthplace, and the other way round."""
    _parsed, _result, place_only = built(
        _body(place_text="", place_id=""), place_assumed=True
    )
    _parsed, _result, time_only = built(_body(time=""))

    assert place_only["assumptions"]["any"] is True
    assert place_only["assumptions"]["time"] is False
    assert place_only["assumptions"]["labels"] == [
        f"Birthplace {JALANDHAR_LABEL} assumed: the configured default"
    ]
    assert place_only["effective"]["time"] == "06:45:00"

    assert time_only["assumptions"]["place"] is False
    assert time_only["assumptions"]["labels"] == [
        "Time 12:00:00 assumed: no time was supplied"
    ]
    assert time_only["effective"]["source"] == "selected"


def test_the_location_block_carries_unrounded_repr_coordinates(jalandhar):
    _parsed, result, document = jalandhar
    location = result.location

    # Section 5.4 item 3: the block is built from the object the engine used.
    assert result.location is result.chart.location

    assert document["location"] == {
        "canonical_name": location.canonical_name,
        "latitude": repr(location.latitude),
        "longitude": repr(location.longitude),
        "timezone_id": location.timezone_id,
    }


# --- the birth chains -------------------------------------------------------


def test_the_birth_chains_are_the_core_s_own_two_queries():
    _parsed, result, document = built()
    timeline = result.timeline

    nominal = [
        {"level": period.level, "lords": [lord.value for lord in period.lords]}
        for period in timeline.periods_at_birth()
    ]
    quantized = [
        {"level": period.level, "lords": [lord.value for lord in period.lords]}
        for period in timeline.active_periods_at(timeline.birth_utc)
    ]

    assert document["birth_chain"]["nominal"] == nominal
    assert document["birth_chain"]["quantized"] == quantized
    assert document["birth_chain"]["identical"] == (nominal == quantized)


def test_the_reference_birth_chains_agree(jalandhar):
    _parsed, _result, document = jalandhar

    assert document["birth_chain"]["identical"] is True
    assert [
        entry["lords"] for entry in document["birth_chain"]["nominal"]
    ] == [["jupiter"], ["jupiter", "sun"], ["jupiter", "sun", "mercury"]]


def test_the_marker_flags_agree_with_the_chains(jalandhar):
    _parsed, _result, document = jalandhar

    nominal = {
        (entry["level"], tuple(entry["lords"]))
        for entry in document["birth_chain"]["nominal"]
    }
    quantized = {
        (entry["level"], tuple(entry["lords"]))
        for entry in document["birth_chain"]["quantized"]
    }
    for row in document["rows"]:
        key = (row["level"], tuple(row["lords"]))
        assert row["in_nominal_birth_chain"] == (key in nominal)
        assert row["in_quantized_birth_chain"] == (key in quantized)


# --- the two Layer 12 divergence cases -------------------------------------


@pytest.mark.parametrize("name", sorted(DIVERGENCE_CASES))
def test_the_divergence_cases_show_two_different_chains(name):
    case = DIVERGENCE_CASES[name]
    document = divergence_document(case)

    assert document["birth_chain"]["identical"] is False
    assert [
        entry["lords"] for entry in document["birth_chain"]["nominal"]
    ] == case["nominal"]
    assert [
        entry["lords"] for entry in document["birth_chain"]["quantized"]
    ] == case["quantized"]


@pytest.mark.parametrize("name", sorted(DIVERGENCE_CASES))
def test_the_divergence_fixtures_are_reproduced(name):
    case = DIVERGENCE_CASES[name]
    expected = json.loads(case["path"].read_text(encoding="utf-8"))

    assert divergence_document(case) == expected, (
        f"{case['path']} no longer matches. {REGENERATE}"
    )


@pytest.mark.parametrize("name", sorted(DIVERGENCE_CASES))
def test_the_divergence_fixtures_are_page_shaped(name):
    """13.4 loads them through the page's one test seam, so they must be whole."""
    document = json.loads(DIVERGENCE_CASES[name]["path"].read_text("utf-8"))

    assert set(document) == {
        "schema",
        "request",
        "engine",
        "location",
        "effective",
        "assumptions",
        "birth",
        "svg",
        "timeline",
        "birth_chain",
        "rows",
    }
    assert len(document["rows"]) == ROW_COUNT
    assert document["svg"] == PLACEHOLDER_SVG
    assert "PLACEHOLDER" in document["location"]["canonical_name"]
    assert document["assumptions"]["any"] is False
    assert sum(row["in_nominal_birth_chain"] for row in document["rows"]) == 3
    assert sum(row["in_quantized_birth_chain"] for row in document["rows"]) == 3


# --- specification 9.5: the seven restated presentation rules ---------------


def test_rule_one_every_chain_equals_the_layer_thirteen_column(
    jalandhar, table_text
):
    _parsed, _result, document = jalandhar
    printed = table_rows(table_text)

    assert len(printed) == ROW_COUNT
    for sent, row in zip(document["rows"], printed):
        assert sent["chain"] == row[1]


def test_rule_one_uses_layer_thirteen_s_own_abbreviations(jalandhar):
    _parsed, result, document = jalandhar
    rows = dasha_rows(result.timeline, depth=DEPTH)

    for sent, row in zip(document["rows"], rows):
        assert sent["chain"] == "-".join(
            ABBREVIATIONS[lord] for lord in row.lords
        )


def test_the_restated_abbreviations_equal_layer_thirteen_s():
    """The transport restates the mapping; this is what keeps the copy honest.

    ``vedic_chart.dasha.table`` is past the daśā package's published surface,
    so no module of ``vedic_chart.viewer`` may import it (Layer 13 section 2)
    and ``transport.ABBREVIATIONS`` is a restatement. A test is not the
    package, so this one reaches for the original and demands equality -- key
    for key, value for value, and no extra or missing lord -- exactly as Layer
    13 itself is held to the renderer's abbreviations it repeats.
    """
    restated = transport.ABBREVIATIONS

    assert restated == ABBREVIATIONS
    assert restated is not ABBREVIATIONS
    assert set(restated) == set(Graha)
    assert sorted(restated.values()) == sorted(
        ["Su", "Mo", "Me", "Ve", "Ma", "Ju", "Sa", "Ra", "Ke"]
    )
    for lord, abbreviation in restated.items():
        assert isinstance(lord, Graha)
        assert abbreviation == ABBREVIATIONS[lord]


def test_rule_two_every_boundary_equals_the_layer_thirteen_column(
    jalandhar, table_text
):
    _parsed, _result, document = jalandhar
    printed = table_rows(table_text)

    for sent, row in zip(document["rows"], printed):
        assert sent["start"]["local_seconds"] == row[2]
        assert sent["end"]["local_seconds"] == row[3]


def test_rule_two_the_birth_line_equals_the_header_field(jalandhar, table_text):
    _parsed, _result, document = jalandhar
    line = header_lines(table_text)[1]
    printed = line.split("Birth ", 1)[1].split(f" ({ZONE})", 1)[0]

    assert document["birth"]["local_seconds"] == printed


def test_rule_two_the_markers_equal_the_layer_thirteen_columns(
    jalandhar, table_text
):
    _parsed, _result, document = jalandhar
    printed = table_rows(table_text)

    for sent, row in zip(document["rows"], printed):
        assert sent["in_nominal_birth_chain"] == (row[4] == "N")
        assert sent["in_quantized_birth_chain"] == (row[5] == "Q")


def test_rule_three_the_balance_decimal_equals_the_header_figure(
    jalandhar, table_text
):
    _parsed, _result, document = jalandhar
    line = header_lines(table_text)[2]
    printed = line.split(" = ", 1)[1].split(" years", 1)[0]
    balance = document["timeline"]["balance_years"]

    assert balance["decimal_9"] == printed
    assert f"{balance['num']}/{balance['den']} = {balance['decimal_9']}" in line


@pytest.mark.parametrize(
    "value,expected",
    (
        # The reference birth's own balance, as the Layer 13 golden prints it.
        (Fraction(174328378011627, 35184372088832), "4.954710505"),
        # The Jammu balance recorded for the production acceptance run (14.2).
        (Fraction(6181544622, 10 ** 9), "6.181544622"),
        # An integer balance still carries its nine places.
        (Fraction(7), "7.000000000"),
        # Trailing zeros are kept, never trimmed.
        (Fraction(1, 2), "0.500000000"),
        (Fraction(1, 5), "0.200000000"),
        # The tenth digit is 9 and is discarded, not rounded up.
        (Fraction(19999999999, 10 ** 10), "1.999999999"),
        (Fraction(2, 3), "0.666666666"),
        # Zero.
        (Fraction(0), "0.000000000"),
    ),
)
def test_rule_three_truncates_and_never_rounds(value, expected):
    assert transport.decimal_truncated(value, 9) == expected


def test_rule_three_refuses_a_negative_balance():
    with pytest.raises(ValueError):
        transport.decimal_truncated(Fraction(-1, 2), 9)


def test_rule_three_refuses_a_non_fraction_and_a_bad_place_count():
    with pytest.raises(TypeError):
        transport.decimal_truncated(0.5, 9)
    with pytest.raises(TypeError):
        transport.decimal_truncated(Fraction(1, 2), True)
    with pytest.raises(ValueError):
        transport.decimal_truncated(Fraction(1, 2), 0)


def test_rule_four_the_lord_name_equals_the_header(jalandhar, table_text):
    _parsed, _result, document = jalandhar
    line = header_lines(table_text)[0]
    printed = line.split("lord ", 1)[1].strip()

    assert document["timeline"]["lord"]["name"] == printed
    assert document["timeline"]["lord"]["key"] == printed.lower()


def test_rule_five_the_year_label_is_the_convention_s_own_spelling(
    jalandhar, table_text
):
    """Section 6: the page has no year control, so the label is not submitted.

    It is still the spelling Layer 13's own header prints, which is what the
    rule has always required.
    """
    _parsed, _result, document = jalandhar
    line = header_lines(table_text)[1]
    printed = line.split("year ", 1)[1].split(" days", 1)[0]
    block = document["timeline"]["year_convention"]

    assert block["label"] == "365.256363" == printed
    assert transport.YEAR is YearConvention.FIXED_365_256363


def test_the_year_convention_block_carries_the_display_sentence(jalandhar):
    """Section 6: one wording, produced in Python, shown everywhere."""
    _parsed, result, document = jalandhar
    block = document["timeline"]["year_convention"]

    assert block["display"] == "Mean Sidereal year — 365.256363 days"
    assert set(block) == {"label", "days", "display"}
    assert Fraction(
        int(block["days"]["num"]), int(block["days"]["den"])
    ) == result.timeline.year.value


def test_rule_six_the_moon_longitude_equals_the_header(jalandhar, table_text):
    _parsed, result, document = jalandhar
    line = header_lines(table_text)[0]
    printed = line.split("Moon ", 1)[1].split(" (", 1)[0]

    assert document["timeline"]["moon_sidereal_longitude"] == printed
    assert document["timeline"]["moon_sidereal_longitude"] == repr(
        result.timeline.moon_sidereal_longitude
    )


def test_rule_seven_the_nakshatra_equals_the_header(jalandhar, table_text):
    _parsed, _result, document = jalandhar
    line = header_lines(table_text)[0]
    printed = line.split("(", 1)[1].split(")", 1)[0]
    block = document["timeline"]

    assert printed == f"{block['nakshatra_name']} #{block['nakshatra_number']}"


def test_the_offset_text_is_the_zone_s_own(jalandhar):
    _parsed, _result, document = jalandhar

    assert document["birth"]["offset"] == "+05:30"
    assert document["birth"]["local"].endswith(document["birth"]["offset"])
    assert document["birth"]["zone"] == ZONE


def test_a_pre_1906_kolkata_birth_prints_seconds_in_its_offset():
    """The offset is never forced into whole minutes (Layer 13's rule)."""
    _parsed, _result, document = built(_body(date="1900-06-15", time="07:30"))

    assert document["birth"]["offset"] == "+05:21:10"
    assert document["birth"]["local_seconds"].endswith("+05:21:10")


# --- specification 9.2: parsing ---------------------------------------------


def _payload(**changes) -> bytes:
    return _body(**changes)


def test_the_reference_request_parses():
    parsed = transport.parse_request(_payload())

    assert parsed.submitted_time == "06:45"
    assert parsed.birth_time.isoformat() == "06:45:00"
    assert parsed.birth_date.isoformat() == BIRTH_DATE
    assert parsed.time_assumed is False
    assert parsed.place_id == JALANDHAR_ID
    assert parsed.submitted() == {
        "date": BIRTH_DATE,
        "time": BIRTH_TIME,
        "place_text": JALANDHAR_LABEL,
        "place_id": str(JALANDHAR_ID),
    }


def test_seconds_are_accepted_and_kept():
    parsed = transport.parse_request(_payload(time="06:45:07"))

    assert parsed.submitted_time == "06:45:07"
    assert parsed.birth_time.isoformat() == "06:45:07"


@pytest.mark.parametrize("blank", ("", " ", "   ", "\t", "\n"))
def test_a_blank_time_becomes_the_assumed_noon(blank):
    """Decision E6, and section 2 rule 6: whitespace-only counts as blank."""
    parsed = transport.parse_request(_payload(time=blank))

    assert parsed.time_assumed is True
    assert parsed.birth_time.isoformat() == "12:00:00"
    assert parsed.submitted_time == blank


@pytest.mark.parametrize("value", ("25:00", "24:00", "07:60", "6:45", "0645"))
def test_an_invalid_time_is_refused_and_never_becomes_noon(value):
    """Section 2 rule 5: an error, **never** a fallback to the assumed noon."""
    with pytest.raises((TransportError, InvalidBirthTimeError)):
        transport.parse_request(_payload(time=value))


@pytest.mark.parametrize("blank", ("", " ", "  "))
def test_a_blank_place_id_means_no_selection(blank):
    parsed = transport.parse_request(
        _payload(place_text="", place_id=blank)
    )

    assert parsed.place_id is None
    assert parsed.place_text_blank is True


@pytest.mark.parametrize(
    "value", ("abc", "-1", "+1", "１２", "12.0", "0", "1268782 ", "1" * 13)
)
def test_a_malformed_place_id_is_refused(value):
    with pytest.raises(TransportError):
        transport.parse_request(_payload(place_id=value))


def test_the_place_text_travels_verbatim_and_decides_nothing_here():
    """All four combinations parse; the server decides what they mean (5.3)."""
    for place_text, place_id in (
        ("", ""),
        ("Jalandhar", ""),
        ("", "1268782"),
        (JALANDHAR_LABEL, "1268782"),
    ):
        parsed = transport.parse_request(
            _payload(place_text=place_text, place_id=place_id)
        )
        assert parsed.submitted_place_text == place_text
        assert parsed.submitted_place_id == place_id


@pytest.mark.parametrize(
    "body",
    (
        b'{"date":"1995-03-21","time":"06:45","place_query":"Jalandhar",'
        b'"year_convention":"365.256363"}',
        b'{"date":"1995-03-21","time":"06:45","place_text":"","place_id":"",'
        b'"year_convention":"365.256363"}',
        b'{"date":"1995-03-21","time":"06:45","place_text":"","place_id":"",'
        b'"place_query":"Jalandhar"}',
    ),
)
def test_a_stale_schema_one_body_is_refused_as_such(body):
    """Decision E10: a tab still running the old script is told to reload."""
    with pytest.raises(transport.StaleSchemaError) as caught:
        transport.parse_request(body)

    assert "out of date" in str(caught.value)
    # It is still a TransportError, so a server that does not distinguish the
    # two still answers 400.
    assert isinstance(caught.value, TransportError)


@pytest.mark.parametrize(
    "body",
    (
        # Invalid UTF-8, carrying a /1 key.
        b'{"place_query":"J\xff","year_convention":"365.25"}',
        # A duplicate key, carrying a /1 key.
        b'{"place_query":"J","place_query":"J","year_convention":"365.25"}',
        # A byte order mark, carrying a /1 key.
        b'\xef\xbb\xbf{"place_query":"J","year_convention":"365.25"}',
    ),
)
def test_an_undecodable_or_duplicate_keyed_body_is_refused_before_the_keys(
    body
):
    """Section 7.2: the stale-schema check happens *after* decoding."""
    with pytest.raises(TransportError) as caught:
        transport.parse_request(body)

    assert not isinstance(caught.value, transport.StaleSchemaError)


@pytest.mark.parametrize(
    "body",
    (
        b"\xef\xbb\xbf{}",
        b"\xff\xfe{}",
        b"not json at all",
        b"[]",
        b'"a string"',
        b'{"date":"1995-03-21","date":"1995-03-22","time":"06:45",'
        b'"place_text":"","place_id":""}',
        b'{"date":NaN,"time":"06:45","place_text":"","place_id":""}',
        b'{"date":"1995-03-21","time":"06:45","place_text":"",'
        b'"place_id":"","extra":"x"}',
        b'{"date":"1995-03-21","time":"06:45","place_text":""}',
        b'{"date":19950321,"time":"06:45","place_text":"","place_id":""}',
        b'{"date":"1995-03-21","time":"06:45","place_text":null,'
        b'"place_id":""}',
    ),
)
def test_parse_request_refuses_a_malformed_document(body):
    with pytest.raises(TransportError):
        transport.parse_request(body)


@pytest.mark.parametrize(
    "value",
    (
        "1995-3-21",
        " 1995-03-21",
        "1995-03-21 ",
        "１９９５-03-21",
        "1995-03-21T00:00",
        "1995/03/21",
        "+1995-03-21",
        "",
    ),
)
def test_parse_request_refuses_a_malformed_date(value):
    with pytest.raises(TransportError):
        transport.parse_request(_payload(date=value))


@pytest.mark.parametrize(
    "value",
    ("6:45", "06:45:00.5", "06:45:", "0645", "06:45 ", "０６:45"),
)
def test_parse_request_refuses_a_malformed_time(value):
    with pytest.raises(TransportError):
        transport.parse_request(_payload(time=value))


def test_the_fullwidth_digit_case_is_the_reason_for_the_ascii_classes():
    """Python's ``\\d`` and ``int()`` both accept ``１９９５``; the regex does not."""
    assert re.fullmatch(r"\d{4}", "１９９５")
    assert int("１９９５") == 1995
    assert re.fullmatch(r"[0-9]{4}", "１９９５") is None


def test_layer_one_errors_keep_their_own_types():
    """9.2 step 7: these are the server's to map, not the transport's."""
    with pytest.raises(InvalidBirthDateError):
        transport.parse_request(_payload(date="1995-02-30"))
    with pytest.raises(InvalidBirthTimeError):
        transport.parse_request(_payload(time="25:00"))


def test_parse_request_refuses_a_non_bytes_body():
    with pytest.raises(TransportError):
        transport.parse_request("{}")


# --- section 5.2: the suggestions request ----------------------------------


def test_a_suggestions_request_carries_exactly_one_key():
    assert transport.parse_places_request(b'{"q":"jal"}') == "jal"
    assert transport.parse_places_request(b'{"q":""}') == ""
    assert transport.parse_places_request(
        b'{"q":"  Hyderabad, India "}'
    ) == "  Hyderabad, India "


@pytest.mark.parametrize(
    "body",
    (
        b'{}',
        b'{"q":"jal","limit":5}',
        b'{"query":"jal"}',
        b'{"q":5}',
        b'{"q":null}',
        b'{"q":"a","q":"b"}',
        b'["jal"]',
        b'\xff\xfe',
        b'\xef\xbb\xbf{"q":"jal"}',
        b'not json',
    ),
)
def test_a_malformed_suggestions_request_is_refused(body):
    with pytest.raises(TransportError):
        transport.parse_places_request(body)


def suggestion_triples(query: str, limit: int = 10):
    """What the server hands the transport: both of Layer 2's labels."""
    with OfflineLocationResolver(FIXTURE_DB) as offline:
        return [
            (
                candidate,
                OfflineLocationResolver.candidate_label(candidate),
                OfflineLocationResolver.suggestion_label(candidate),
            )
            for candidate in offline.suggest(query, limit=limit)
        ]


def test_the_suggestions_document_echoes_the_query_and_lists_the_labels():
    triples = suggestion_triples("jal")

    document = transport.suggestions_document("  JAL ", triples)

    assert document["schema"] == "vedic_chart.viewer/2"
    assert document["q"] == "  JAL "
    assert len(document["suggestions"]) == len(triples)
    first = document["suggestions"][0]
    assert set(first) == {
        "geoname_id",
        "label",
        "display_label",
        "name",
        "admin1_name",
        "country_name",
        "population",
        "matched_name",
    }
    assert first["geoname_id"] == JALANDHAR_ID
    assert first["label"] == JALANDHAR_LABEL
    assert first["display_label"] == JALANDHAR_LABEL
    assert transport.encode(document)


def test_a_primary_name_match_displays_the_plain_label():
    """The page shows ``display_label`` and sends back ``label``."""
    document = transport.suggestions_document("jal", suggestion_triples("jal"))

    for sent, (_candidate, label, display) in zip(
        document["suggestions"], suggestion_triples("jal")
    ):
        assert sent["label"] == label
        assert sent["display_label"] == display
        if sent["matched_name"] == sent["name"]:
            assert sent["display_label"] == sent["label"]


def test_an_alias_match_displays_the_name_that_matched():
    """Layer 2 decided that the two names differ; the transport only carries it."""
    document = transport.suggestions_document(
        "london", suggestion_triples("london", limit=50)
    )
    hamlet = next(
        one
        for one in document["suggestions"]
        if one["geoname_id"] == 10304286
    )

    assert hamlet["label"] == "Ban Sarkāri, Punjab, India"
    assert hamlet["display_label"] == (
        "Ban Sarkāri, Punjab, India (matched: London)"
    )
    assert hamlet["matched_name"] == "London"


def test_the_transport_decides_nothing_about_the_two_labels():
    """Both strings are Layer 2's; the transport does not compare names."""
    with OfflineLocationResolver(FIXTURE_DB) as offline:
        candidate = offline.suggest("jal", limit=1)[0]

    document = transport.suggestions_document(
        "jal", [(candidate, "A LABEL", "A DISPLAY LABEL")]
    )

    assert document["suggestions"][0]["label"] == "A LABEL"
    assert document["suggestions"][0]["display_label"] == "A DISPLAY LABEL"


def test_an_empty_suggestions_document_is_still_a_document():
    document = transport.suggestions_document("j", [])

    assert document == {
        "schema": "vedic_chart.viewer/2",
        "q": "j",
        "suggestions": [],
    }


# --- the error document -----------------------------------------------------


def test_the_error_document_has_the_one_shape():
    document = transport.error_document("input", "no good")

    assert document == {
        "schema": "vedic_chart.viewer/2",
        "error": {"kind": "input", "message": "no good"},
    }
    for kind in ("place_selection_required", "stale_schema"):
        assert transport.error_document(kind, "x")["error"]["kind"] == kind


def test_serialize_refuses_the_wrong_kinds(jalandhar):
    parsed, result, _document = jalandhar
    effective = effective_input(parsed)

    with pytest.raises(TypeError):
        transport.serialize(object(), parsed, effective=effective)
    with pytest.raises(TypeError):
        transport.serialize(result, object(), effective=effective)
    with pytest.raises(TypeError):
        transport.serialize(result, parsed, effective=object())


def test_an_effective_input_states_one_of_the_two_sources(jalandhar):
    parsed, _result, _document = jalandhar
    effective = effective_input(parsed)

    with pytest.raises(ValueError):
        dataclasses_replace(effective, source="invented")


def dataclasses_replace(value, **changes):
    import dataclasses

    return dataclasses.replace(value, **changes)


# --- regeneration -----------------------------------------------------------


def write_fixtures() -> None:
    """Rewrite all three committed fixtures from the resources above."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    _parsed, _result, document = _built(_body())
    written = [(GOLDEN_PATH, _legacy_document(document))]
    for name in sorted(DIVERGENCE_CASES):
        case = DIVERGENCE_CASES[name]
        written.append((case["path"], divergence_document(case)))

    for path, content in written:
        path.write_text(
            json.dumps(content, ensure_ascii=False, indent=1, sort_keys=False)
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {path}")


if __name__ == "__main__":
    if "--write-fixtures" not in sys.argv[1:]:
        print(__doc__)
        raise SystemExit(2)
    write_fixtures()
