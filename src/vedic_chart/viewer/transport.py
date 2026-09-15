"""Layer 14, part 1: the lossless transport between Python and the browser.

Pure functions only. Nothing here opens a file, a socket or a database, starts
a thread, reads a clock or calls the engine: :func:`parse_request` turns bytes
into the four validated fields of one submission, and :func:`serialize` turns a
finished :class:`~vedic_chart.app.LocatedChartAndDashaResult` into a JSON-ready
``dict`` of strings. The HTTP contract, the engine lock, the effective-input
construction and the error mapping belong to ``vedic_chart.viewer.server``.

Implements ``docs/LAYER14_INTERACTIVE_VIEWER_SPEC.md`` (DRAFT v0.3) sections
9.2 to 9.5 as amended by
``docs/LAYER15_VIEWER_INPUT_FLOW_SPEC.md`` (DRAFT v0.3) sections 5 to 7:
schema ``vedic_chart.viewer/2``, a four-key request whose time and birthplace
may be blank, the ``effective`` and ``assumptions`` blocks that say what was
assumed, the suggestions document of ``POST /api/places``, and no
``resolution`` block at all -- no name is resolved on this path, so there is no
decision to report and none is fabricated (section 5.4).

Four disciplines carry the whole module.

**Nothing is recalculated.** Every boundary, fraction, longitude, membership
flag and zone offset is read off the objects Layers 11--13 produced and turned
into a string. The module derives no quantity of its own. The one exception is
the presentation rule of section 9.5 number 3 --
:func:`decimal_truncated` -- which is the only function in the whole package
allowed to apply an arithmetic operator, and applies it to a ``Fraction``'s
``numerator`` and ``denominator`` as integers, never to a boundary.

**Lossless strings, never JSON numbers.** A float travels as ``repr`` (the
shortest string that round-trips), a ``Fraction`` as two decimal integer
strings, a ``datetime`` as ``isoformat(timespec="microseconds")`` with its
offset. JSON numbers appear only for small structural integers -- ``level``,
``posinset``, counts, ``geoname_id``, ``population`` -- so nothing a boundary
depends on is ever handed to a JavaScript ``Number``.

**Layer 13's private formatting is restated, not imported.** Layer 13 keeps
``_format_instant``, ``_balance_text``, ``_chain_text`` and ``_lord_name``
private, so section 9.5 enumerates the seven rules this module repeats and
``tests/test_viewer_transport.py`` checks each one against
``render_dasha_text`` output for the same birth. The lord abbreviations are
restated here for the same reason, as :data:`ABBREVIATIONS`: Layer 13 keeps
them inside ``vedic_chart.dasha.table``, which is past the daśā package's
published surface, and the package boundary is not something a consumer gets to
step over for nine two-letter strings. The copy is not left to drift --
``tests/test_viewer_transport.py`` asserts it equals Layer 13's own mapping,
exactly as Layer 13 itself does for the renderer's abbreviations it repeats.

**No comparison of a ``datetime`` or a ``Fraction``.** Membership comes from
``DashaRow``'s two flags, which Layer 13 computed from the timeline's own
queries; the ``identical`` flag of section 9.4 is a tuple equality of
``(level, lords)`` keys. Nothing here decides whether one instant precedes
another.
"""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from fractions import Fraction
from typing import Any, Iterable, Mapping, Optional

from vedic_chart.app import LocatedChartAndDashaResult
from vedic_chart.dasha import (
    DashaRangeError,
    DashaRow,
    VimshottariTimeline,
    YearConvention,
    dasha_rows,
    resolve_zone,
)
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.model import PlaceCandidate
from vedic_chart.render import NorthIndianOptions
from vedic_chart.vedic.grahas import Graha

__all__ = [
    "ABBREVIATIONS",
    "ASSUMED_TIME",
    "ASSUMED_TIME_TEXT",
    "ENGINE_BLOCK_KEYS",
    "PARSED_KEYS",
    "RENDERER_OPTIONS",
    "SCHEMA",
    "SOURCE_DEFAULT",
    "SOURCE_SELECTED",
    "STALE_KEYS",
    "VALIDATION_NOTE",
    "YEAR",
    "YEAR_DISPLAY",
    "YEAR_LABEL",
    "EffectiveInput",
    "ParsedRequest",
    "PlaceSelectionRequiredError",
    "StaleSchemaError",
    "TransportError",
    "decimal_truncated",
    "encode",
    "error_document",
    "parse_places_request",
    "parse_request",
    "serialize",
    "serialize_timeline_document",
    "suggestions_document",
]

#: The one schema string every document of this contract carries. Layer 15
#: decision E10: ``/2`` replaces ``/1`` outright -- the page is the only
#: client, there is no dual-schema support, and a request in the old shape is
#: refused with :class:`StaleSchemaError` rather than translated.
SCHEMA = "vedic_chart.viewer/2"

#: The lord abbreviations of specification 9.5 rule 1, **restated**: Layer 13
#: holds the same mapping in ``vedic_chart.dasha.table.ABBREVIATIONS``, a
#: module-level presentation constant that the daśā package deliberately does
#: not re-export, and a consumer that reached into the submodule for it would
#: be stepping over that package's published surface (Layer 13 section 2).
#: Layer 13 repeats the renderer's abbreviations for exactly the same reason
#: and for exactly the same cost; as there, the copy is held to the original by
#: a test rather than by hope -- ``tests/test_viewer_transport.py`` asserts
#: that this mapping equals Layer 13's, key for key.
ABBREVIATIONS: dict = {
    Graha.SUN: "Su",
    Graha.MOON: "Mo",
    Graha.MERCURY: "Me",
    Graha.VENUS: "Ve",
    Graha.MARS: "Ma",
    Graha.JUPITER: "Ju",
    Graha.SATURN: "Sa",
    Graha.RAHU: "Ra",
    Graha.KETU: "Ke",
}

#: Section 6: the milestone makes no exact-compatibility claim, and the page
#: must not either. Carried in the ``engine`` block so the claim and the
#: descriptors it qualifies travel together.
VALIDATION_NOTE = (
    "Independent Lahiri absolute-date validation pending; no exact "
    "compatibility claim."
)

#: Section 7.1, decision D4. Fixed: nothing in a request can vary them.
RENDERER_OPTIONS = NorthIndianOptions(
    show_degrees=True,
    mark_node_retrograde=False,
    caption=False,
    width=None,
    id_prefix="d1",
)

#: The four keys a request document must carry -- exactly these, no more
#: (Layer 15 section 7.2).
PARSED_KEYS = ("date", "time", "place_text", "place_id")

#: The two keys a page still running the ``/1`` script would send. Their
#: presence is not an unknown key but a stale page, and says so (section 7.2).
STALE_KEYS = ("place_query", "year_convention")

#: Layer 15 section 6: the viewer supplies the convention itself. The Python
#: APIs keep their explicit ``year`` parameter and the CLI keeps
#: ``--dasha-year``; the implicit choice is this page's presentation decision
#: and lives here, once.
YEAR = YearConvention.FIXED_365_256363

#: The label of that convention, in the spelling Layer 13's table prints.
YEAR_LABEL = "365.256363"

#: Section 6: what the page shows beside the table and in the caption line.
YEAR_DISPLAY = "Mean Sidereal year — 365.256363 days"

#: Decision E6: a blank time means noon at the effective place. It is an
#: assumption, never a fallback for an invalid time (section 2, rule 5).
ASSUMED_TIME = time(12, 0, 0)
ASSUMED_TIME_TEXT = "12:00:00"

#: Section 5.4 item 1: which record was used, and why. A fact about the
#: request, decided by the server, not a resolver judgement.
SOURCE_SELECTED = "selected"
SOURCE_DEFAULT = "default"

#: The five ``D1Meta`` descriptor fields the page displays, read off the
#: result and never restated as literals here (section 6).
ENGINE_BLOCK_KEYS = (
    "zodiac",
    "ayanamsha",
    "house_system",
    "node",
    "engine_spec",
)

#: Section 8.1: the three levels the page lists.
DEPTH = 3

#: Explicit ASCII digit classes. Python's ``\d`` matches Unicode digits --
#: ``\d{4}`` accepts the fullwidth ``１９９５``, which ``int()`` then accepts
#: too -- so the regex, not ``int()``, is what excludes signs, whitespace,
#: underscores and non-ASCII digits (section 9.2 rule 4).
_DATE_PATTERN = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_TIME_PATTERN = re.compile(r"([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?")

#: The trailing UTC offset of an ISO-8601 string, as the zone reports it.
#: Historical offsets are not whole minutes -- Asia/Kolkata was ``+05:21:10``
#: before 1906 -- so the seconds group is optional and the text is taken from
#: Python's own serialisation rather than computed from a ``timedelta``.
_OFFSET_PATTERN = re.compile(r"([+-][0-9]{2}:[0-9]{2}(?::[0-9]{2})?)\Z")

#: The separator the page uses between the full lord names of a chain.
_NAME_SEPARATOR = " › "

#: Layer 15 section 5.3: the identifier a suggestion carries, as the page
#: sends it back. ASCII digits only, for the reason the date and time patterns
#: give: ``int()`` accepts a sign, an underscore and a fullwidth digit.
_PLACE_ID_PATTERN = re.compile(r"[0-9]{1,12}")

#: The place query Layer 1 is given while it validates the date and the time.
#: Layer 1 requires a non-blank string and never resolves it; the real request
#: is built in the effective-input step from the record's own label (7.2).
_LAYER_ONE_PLACEHOLDER = "(validating the date and time only)"

#: A date that exists, for the wall-time check below. It is discarded.
_ANY_VALID_DATE = (2000, 1, 1)

_BYTE_ORDER_MARK = "﻿"


class TransportError(ValueError):
    """A request body is not a document this contract accepts.

    A ``ValueError`` because it is a statement about the bytes that arrived,
    not an arithmetic surprise, and because the server maps it beside Layer 1's
    own input errors to one HTTP 400 ``input`` response (section 12). The
    message is short and names the rule that refused, never the whole body.
    """


class StaleSchemaError(TransportError):
    """The body is a ``/1`` request from a page that has not been reloaded.

    A subclass, so a server that does not care still maps it to 400, and a
    distinct type, so the one that does care can answer with the ``kind``
    ``stale_schema`` and its own sentence (Layer 15 section 7.2, decision
    E10). Nothing is translated: a stale page is told to reload.
    """


class PlaceSelectionRequiredError(TransportError):
    """A birthplace was typed but no suggestion was chosen.

    Layer 15 section 2 rule 3: such a request is neither resolved nor
    defaulted. The page blocks it client-side; this is the server's
    independent answer, which is a 400 of its own ``kind`` rather than a plain
    input error, because the page has a specific thing to say about it.
    """


@dataclass(frozen=True)
class ParsedRequest:
    """One accepted request: the raw strings and what they were turned into.

    The four ``submitted_*`` fields are the strings **exactly as received**.
    The browser compares them against the values it captured at submission
    time (section 10.2), so normalising them here -- trimming, zero-padding,
    re-spelling a time -- would break the one check that proves a response
    belongs to the submission that is on screen.

    ``birth_date`` and ``birth_time`` are Layer 1's own validated values;
    ``time_assumed`` records that the time is the assumed noon rather than a
    supplied one. ``place_id`` is the integer of the submitted identifier, or
    None when the birthplace field was left blank. No
    :class:`~vedic_chart.inputs.model.BirthChartRequest` is built here: its
    ``place_query`` is the *effective* record's label, which is decided by the
    server one step later (section 7.2).
    """

    submitted_date: str
    submitted_time: str
    submitted_place_text: str
    submitted_place_id: str
    birth_date: date
    birth_time: time
    time_assumed: bool
    place_id: Optional[int]

    def submitted(self) -> dict:
        """The four strings, byte for byte as they arrived."""
        return {
            "date": self.submitted_date,
            "time": self.submitted_time,
            "place_text": self.submitted_place_text,
            "place_id": self.submitted_place_id,
        }

    @property
    def place_text_blank(self) -> bool:
        """Section 2 rule 6: whitespace-only birthplace text counts as blank."""
        return not self.submitted_place_text.strip()


@dataclass(frozen=True)
class EffectiveInput:
    """What one request is actually calculated from (sections 5.3, 5.4, 7.2).

    Built by the server in one place, from the parsed request and the record
    it names -- or, for a blank birthplace, from the default record read once
    at start-up. It carries no decision of its own beyond ``source``, which is
    a fact about the request: whether the record came from the submitted
    ``place_id`` or from the configured default.

    ``location`` is annotated as a string on purpose: it is Layer 2's
    ``ResolvedLocation``, and this module does not import Layer 2's location
    type (specification 3.4). The object is passed through to the pipeline and
    never inspected here.
    """

    request: BirthChartRequest
    location: "ResolvedLocation"  # noqa: F821 -- see the docstring
    place: PlaceCandidate
    label: str
    place_assumed: bool
    time_assumed: bool
    source: str

    def __post_init__(self) -> None:
        if self.source not in (SOURCE_SELECTED, SOURCE_DEFAULT):
            raise ValueError(
                f"source must be {SOURCE_SELECTED!r} or {SOURCE_DEFAULT!r}; "
                f"got {self.source!r}."
            )
        if not isinstance(self.place, PlaceCandidate):
            raise TypeError(
                f"place must be a PlaceCandidate; got "
                f"{type(self.place).__name__}."
            )


# --- section 9.5, rule 3: the only arithmetic in the package ---------------


def decimal_truncated(fraction: Fraction, places: int) -> str:
    """A ``Fraction`` as a decimal string, truncated toward zero.

    The single carve-out of section 3.4. Integer ``//``, ``%`` and ``*`` on the
    numerator and the denominator are exact, so the result is a truncation of
    the true value and never a rounding of it -- which is what Layer 13's
    private ``_balance_text`` produces, by the same integer identity:
    ``divmod(n * 10**p // d, 10**p)`` and ``(n // d, (n % d) * 10**p // d)``
    agree for every non-negative ``n``.

    A negative value raises. The only quantity this is called with is
    ``timeline.balance_years``, the remaining part of a nakshatra times a lord's
    years, which cannot be negative; a negative one would mean the core had
    changed underneath us, and printing ``-0.5`` as ``-1.500000000`` -- what
    flooring division would give -- would hide that rather than report it.
    """
    if not isinstance(fraction, Fraction):
        raise TypeError(
            f"fraction must be a fractions.Fraction; got "
            f"{type(fraction).__name__}."
        )
    if type(places) is not int:
        raise TypeError(
            f"places must be an int; got {type(places).__name__} ({places!r})."
        )
    if places < 1:
        raise ValueError(f"places must be at least 1; got {places!r}.")

    numerator = fraction.numerator
    denominator = fraction.denominator
    if numerator < 0:
        raise ValueError(
            f"decimal_truncated refuses the negative value {fraction!r}; a "
            "balance of nominal years is never negative."
        )

    whole = numerator // denominator
    remainder = (numerator % denominator) * 10 ** places // denominator
    return f"{whole}.{remainder:0{places}d}"


# --- section 9.2: the request ----------------------------------------------


def _reject_duplicates(pairs) -> dict:
    """``object_pairs_hook`` that refuses a repeated key at any depth.

    ``json.loads`` keeps the last value for a repeated key, so
    ``{"date": "a", "date": "b"}`` would silently become one of the two. A
    request whose author disagreed with itself is refused instead.
    """
    document: dict = {}
    for key, value in pairs:
        if key in document:
            raise TransportError(
                f"the request document repeats the key {key!r}."
            )
        document[key] = value
    return document


def _reject_constant(name: str):
    raise TransportError(
        f"the request document contains the JSON constant {name}, which this "
        "contract does not accept."
    )


def _decoded_object(body) -> dict:
    """Bytes to a JSON object, in the order Layer 15 section 7.2 fixes.

    Strict UTF-8 (a byte order mark is not JSON), then JSON with duplicate
    keys and the three JSON constants refused, then the object check. An
    undecodable or duplicate-keyed body is refused *before any key is
    inspected*, which is why a stale ``/1`` body that is also invalid UTF-8 is
    a plain input error rather than a stale-schema one.
    """
    if not isinstance(body, (bytes, bytearray)):
        raise TransportError(
            f"the request body must be bytes; got {type(body).__name__}."
        )

    try:
        text = bytes(body).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise TransportError(
            f"the request body is not valid UTF-8: {error.reason}."
        ) from error

    if text.startswith(_BYTE_ORDER_MARK):
        raise TransportError(
            "the request body starts with a byte order mark; JSON has none."
        )

    try:
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise TransportError(f"the request body is not JSON: {error.msg}.") from error

    if not isinstance(document, dict):
        raise TransportError(
            "the request document must be a JSON object; got "
            f"{type(document).__name__}."
        )
    return document


def _layer_one_date(match) -> date:
    """Layer 1's own calendar validation, on the matched digit groups.

    ``int()`` is applied to the groups only; the regex is what excluded the
    sign, the underscore and the fullwidth digit that ``int()`` accepts. The
    request built here exists to be validated and is discarded: its
    ``place_query`` is not known yet and would not be resolved anyway (7.2).
    """
    return BirthChartRequest.from_components(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        0,
        0,
        0,
        place_query=_LAYER_ONE_PLACEHOLDER,
    ).birth_date


def _layer_one_time(hour: int, minute: int, second: int) -> time:
    """Layer 1's own wall-clock validation, on a date that always exists.

    The date is separate here because section 7.2 fixes the order: the date
    is validated by Layer 1 *before* the time is looked at, so an impossible
    date and an impossible time in one body report the date.
    """
    return BirthChartRequest.from_components(
        *_ANY_VALID_DATE,
        hour,
        minute,
        second,
        place_query=_LAYER_ONE_PLACEHOLDER,
    ).birth_time


def parse_request(body: bytes) -> ParsedRequest:
    """Turn a request body into one accepted submission, or raise.

    The order is Layer 15 section 7.2's, exactly: strict UTF-8 with the byte
    order mark refused; JSON with duplicate keys and NaN/Infinity refused;
    **then** the stale-schema check on the parsed object's keys; then exactly
    the four keys and all strings; ``date`` by regex then Layer 1; ``time``
    blank after ``strip`` means the assumed noon, otherwise regex then Layer 1;
    ``place_id`` blank means None, otherwise the identifier regex;
    ``place_text`` is kept verbatim.

    Every failure is a :class:`TransportError` -- :class:`StaleSchemaError`
    for a ``/1`` body -- except the Layer 1 errors raised for an impossible
    calendar date or wall time, which keep their own types so the server maps
    them by type, exactly as the CLI does (section 12). An invalid time is
    **never** replaced by the assumed noon: only a blank one is.
    """
    document = _decoded_object(body)

    keys = set(document)
    stale = sorted(keys.intersection(STALE_KEYS))
    if stale:
        raise StaleSchemaError(
            f"the request document carries the retired key(s) {stale}: this "
            "page is out of date, reload it to continue."
        )

    expected = set(PARSED_KEYS)
    if keys != expected:
        missing = sorted(expected.difference(keys))
        unknown = sorted(keys.difference(expected))
        raise TransportError(
            "the request document must carry exactly the keys "
            f"{sorted(expected)}; missing {missing}, unknown {unknown}."
        )

    for key in PARSED_KEYS:
        if not isinstance(document[key], str):
            raise TransportError(
                f"{key} must be a string; got "
                f"{type(document[key]).__name__}."
            )

    date_text = document["date"]
    time_text = document["time"]
    place_text = document["place_text"]
    place_id_text = document["place_id"]

    date_match = _DATE_PATTERN.fullmatch(date_text)
    if date_match is None:
        raise TransportError(
            f"date must be exactly YYYY-MM-DD in ASCII digits; got "
            f"{date_text!r}."
        )

    birth_date = _layer_one_date(date_match)

    time_assumed = not time_text.strip()
    if time_assumed:
        birth_time = ASSUMED_TIME
    else:
        time_match = _TIME_PATTERN.fullmatch(time_text)
        if time_match is None:
            raise TransportError(
                f"time must be exactly HH:MM or HH:MM:SS in ASCII digits, or "
                f"blank for the assumed {ASSUMED_TIME_TEXT}; got "
                f"{time_text!r}."
            )
        seconds_group = time_match.group(3)
        birth_time = _layer_one_time(
            int(time_match.group(1)),
            int(time_match.group(2)),
            0 if seconds_group is None else int(seconds_group),
        )

    if place_id_text.strip():
        if _PLACE_ID_PATTERN.fullmatch(place_id_text) is None:
            raise TransportError(
                "place_id must be one to twelve ASCII digits, or blank; got "
                f"{place_id_text!r}."
            )
        place_id = int(place_id_text)
        if place_id < 1:
            # GeoNames identifiers start at 1; the regex admits "0" and this
            # is where that one value is refused, as an input error rather
            # than as a lookup that could never succeed.
            raise TransportError(
                f"place_id must be 1 or greater; got {place_id_text!r}."
            )
    else:
        place_id = None

    return ParsedRequest(
        submitted_date=date_text,
        submitted_time=time_text,
        submitted_place_text=place_text,
        submitted_place_id=place_id_text,
        birth_date=birth_date,
        birth_time=birth_time,
        time_assumed=time_assumed,
        place_id=place_id,
    )


def parse_places_request(body: bytes) -> str:
    """The one field of a suggestions request (Layer 15 section 5.2).

    ``{"q": "<text>"}`` and nothing else: exactly one key, a string value,
    through the same decoding discipline as :func:`parse_request`. The text is
    **not** normalised here -- server normalisation is the resolver's, and it
    is authoritative (section 5.1) -- and it is echoed back verbatim so the
    page can discard a response that no longer matches its field.
    """
    document = _decoded_object(body)

    if set(document) != {"q"}:
        raise TransportError(
            "the suggestions document must carry exactly the key ['q']; got "
            f"{sorted(document)}."
        )
    query = document["q"]
    if not isinstance(query, str):
        raise TransportError(
            f"q must be a string; got {type(query).__name__}."
        )
    return query


# --- section 9.3: the response ---------------------------------------------


def _fraction(value: Fraction) -> dict:
    """One exact rational as two decimal integer strings."""
    return {"num": str(value.numerator), "den": str(value.denominator)}


def _lord_key(lord: Graha) -> str:
    return lord.value


def _lord_display_name(lord: Graha) -> str:
    """Section 9.5 rule 4: ``Graha.JUPITER`` -> ``Jupiter``."""
    return lord.value.capitalize()


def _chain_text(lords: Iterable[Graha]) -> str:
    """Section 9.5 rule 1, with Layer 13's own abbreviations."""
    return "-".join(ABBREVIATIONS[lord] for lord in lords)


def _chain_names(lords: Iterable[Graha]) -> str:
    return _NAME_SEPARATOR.join(_lord_display_name(lord) for lord in lords)


def _local_seconds(moment: datetime, zone, key: str) -> str:
    """Section 9.5 rule 2: Layer 13's second-precision instant, restated.

    ``astimezone`` can raise ``OverflowError`` within a zone offset of
    ``datetime``'s limits; Layer 13 turns that into ``DashaRangeError`` and so
    does this, by repeating the rule rather than importing the helper
    (section 3.2): ``DashaRangeError`` itself is public and is imported.
    """
    try:
        local = moment.astimezone(zone)
    except OverflowError as error:
        raise DashaRangeError(
            f"the timestamp {moment!r} cannot be shown in the zone {key!r}: "
            "the converted local time would fall outside the datetime range."
        ) from error
    return local.replace(microsecond=0).isoformat(sep=" ", timespec="seconds")


def _local_full(moment: datetime, zone, key: str) -> str:
    """The same instant at full precision: the standard library's own form."""
    try:
        local = moment.astimezone(zone)
    except OverflowError as error:
        raise DashaRangeError(
            f"the timestamp {moment!r} cannot be shown in the zone {key!r}: "
            "the converted local time would fall outside the datetime range."
        ) from error
    return local.isoformat(timespec="microseconds")


def _instant(moment: datetime, zone, key: str) -> dict:
    """One boundary in the three spellings the page may need."""
    return {
        "utc": moment.isoformat(timespec="microseconds"),
        "local": _local_full(moment, zone, key),
        "local_seconds": _local_seconds(moment, zone, key),
    }


def _offset_text(local_iso: str) -> str:
    """The UTC offset of an ISO-8601 string, read off the string itself.

    Python already printed the offset the zone reports, seconds included where
    a zone has them; reading it back is not a calculation, whereas formatting
    ``utcoffset()`` would be arithmetic on a ``timedelta``.
    """
    match = _OFFSET_PATTERN.search(local_iso)
    if match is None:  # pragma: no cover - an aware datetime always has one
        raise ValueError(
            f"the local timestamp {local_iso!r} carries no UTC offset."
        )
    return match.group(1)


def _chain_keys(periods) -> list:
    """Three ``(level, lords)`` keys, as the transport spells them."""
    return [
        {
            "level": period.level,
            "lords": [_lord_key(lord) for lord in period.lords],
        }
        for period in periods
    ]


def _period_index(timeline: VimshottariTimeline) -> dict:
    """``(level, lords)`` -> ``(posinset, nominal_years)`` for every period.

    ``DashaRow`` carries no sibling position and no ``nominal_years``; both are
    on the ``DashaPeriod`` the row was made from. Walking the timeline's own
    nesting with ``enumerate(..., 1)`` reads the position off Python's counter
    rather than deriving it, which is what keeps this module free of
    arithmetic.
    """
    index: dict = {}
    for mahadasha_position, mahadasha in enumerate(timeline.mahadashas, 1):
        index[(mahadasha.level, mahadasha.lords)] = (
            mahadasha_position,
            mahadasha.nominal_years,
        )
        for antardasha_position, antardasha in enumerate(
            mahadasha.children, 1
        ):
            index[(antardasha.level, antardasha.lords)] = (
                antardasha_position,
                antardasha.nominal_years,
            )
            for pratyantar_position, pratyantar in enumerate(
                antardasha.children, 1
            ):
                index[(pratyantar.level, pratyantar.lords)] = (
                    pratyantar_position,
                    pratyantar.nominal_years,
                )
    return index


def _row_document(row: DashaRow, index: dict, zone, key: str) -> dict:
    posinset, nominal_years = index[(row.level, row.lords)]
    return {
        "level": row.level,
        "lords": [_lord_key(lord) for lord in row.lords],
        "chain": _chain_text(row.lords),
        "chain_names": _chain_names(row.lords),
        "start": _instant(row.start_utc, zone, key),
        "end": _instant(row.end_utc, zone, key),
        "nominal_start": _fraction(row.nominal_start),
        "nominal_end": _fraction(row.nominal_end),
        "nominal_years": _fraction(nominal_years),
        "in_nominal_birth_chain": row.in_nominal_birth_chain,
        "in_quantized_birth_chain": row.in_quantized_birth_chain,
        "posinset": posinset,
    }


def _year_days_block(timeline: VimshottariTimeline) -> dict:
    """Section 9.5 rule 5, with Layer 15 section 6's display sentence.

    The label is the convention's own spelling and the days are the core's own
    exact value; ``display`` is the one wording the page shows beside the
    table and in the caption line, produced here so that the page has nothing
    to compose.
    """
    return {
        "label": YEAR_LABEL,
        "days": _fraction(timeline.year.value),
        "display": YEAR_DISPLAY,
    }


def serialize_timeline_document(
    timeline: VimshottariTimeline,
    *,
    submitted: Mapping[str, str],
    normalized: Mapping[str, str],
    zone_key: str,
    birth_utc: datetime,
    svg: str,
    engine: Mapping[str, str],
    location: Mapping[str, Any],
    effective: Mapping[str, Any],
    assumptions: Mapping[str, Any],
    rows: Optional[tuple] = None,
) -> dict:
    """The whole page document, built from one finished timeline.

    The timeline-only path of section 13.1. ``serialize`` is the request path
    and calls this with the blocks it read off the result; the two Layer 12
    divergence cases of section 8.3 call it with a timeline from
    ``build_vimshottari`` and explicit placeholder blocks, which is how a page
    whose two birth chains differ can be exercised without a chart.

    ``rows`` exists so the server can extract them under the engine lock and
    hand them over afterwards; left ``None`` they are extracted here. The
    result is the same document either way.
    """
    if not isinstance(timeline, VimshottariTimeline):
        raise TypeError(
            "timeline must be a VimshottariTimeline; got "
            f"{type(timeline).__name__}."
        )
    if not isinstance(svg, str):
        raise TypeError(f"svg must be a str; got {type(svg).__name__}.")

    zone = resolve_zone(zone_key)
    table_rows = dasha_rows(timeline, depth=DEPTH) if rows is None else rows
    index = _period_index(timeline)

    nominal = _chain_keys(timeline.periods_at_birth())
    quantized = _chain_keys(timeline.active_periods_at(timeline.birth_utc))

    birth_local = _local_full(birth_utc, zone, zone_key)

    return {
        "schema": SCHEMA,
        "request": {
            "submitted": dict(submitted),
            "normalized": dict(normalized),
        },
        "engine": dict(engine),
        "location": dict(location),
        # Layer 15 section 5.4: the Layer 14 ``resolution`` block is absent,
        # not emptied. No name was resolved, so there is no dominance, no
        # rival count and no candidate list to report.
        "effective": dict(effective),
        "assumptions": dict(assumptions),
        "birth": {
            "local": birth_local,
            "utc": birth_utc.isoformat(timespec="microseconds"),
            "local_seconds": _local_seconds(birth_utc, zone, zone_key),
            "offset": _offset_text(birth_local),
            "zone": zone_key,
        },
        "svg": svg,
        "timeline": {
            "moon_sidereal_longitude": repr(
                timeline.moon_sidereal_longitude
            ),
            "normalized_longitude": repr(timeline.normalized_longitude),
            "nakshatra_index": timeline.nakshatra_index,
            "nakshatra_number": timeline.nakshatra_number,
            "nakshatra_name": timeline.nakshatra_name,
            "lord": {
                "key": _lord_key(timeline.lord),
                "name": _lord_display_name(timeline.lord),
                "abbr": ABBREVIATIONS[timeline.lord],
            },
            "elapsed_fraction": _fraction(timeline.elapsed_fraction),
            "remaining_fraction": _fraction(timeline.remaining_fraction),
            "elapsed_years": _fraction(timeline.elapsed_years),
            "balance_years": {
                "num": str(timeline.balance_years.numerator),
                "den": str(timeline.balance_years.denominator),
                "decimal_9": decimal_truncated(timeline.balance_years, 9),
            },
            "cycle_start": _instant(
                timeline.cycle_start_utc, zone, zone_key
            ),
            "cycle_end": _instant(timeline.cycle_end_utc, zone, zone_key),
            "year_convention": _year_days_block(timeline),
            "zone": zone_key,
        },
        "birth_chain": {
            "nominal": nominal,
            "quantized": quantized,
            # Section 9.4: tuple equality of the two key lists. No datetime and
            # no Fraction is compared anywhere in this package.
            "identical": nominal == quantized,
        },
        "rows": [
            _row_document(row, index, zone, zone_key) for row in table_rows
        ],
    }


def _engine_block(result: LocatedChartAndDashaResult) -> dict:
    """The five ``D1Meta`` descriptors, read off the result (section 6)."""
    meta = result.d1.meta
    block = {name: getattr(meta, name) for name in ENGINE_BLOCK_KEYS}
    block["validation_note"] = VALIDATION_NOTE
    return block


def _location_block(result: LocatedChartAndDashaResult) -> dict:
    """What the chart was built from (Layer 15 section 5.4 item 3).

    Read off ``result.location``, which the pipeline asserted **is**
    ``result.chart.location``: the coordinates and the zone shown are the ones
    the engine used, not a second description of the same place.
    """
    location = result.location
    return {
        "canonical_name": location.canonical_name,
        "latitude": repr(location.latitude),
        "longitude": repr(location.longitude),
        "timezone_id": location.timezone_id,
    }


def _place_block(candidate: PlaceCandidate, label: str) -> dict:
    """One geodata record as the page shows it (Layer 15 section 7.3).

    ``matched_name`` is **always** null here, for the selected record as much
    as for the configured default. A matching name is a fact about a
    suggestion list -- which of a place's names the typed prefix hit -- and
    neither path that reaches this block has one: the default was named by its
    identifier at start-up, and a selection arrives as an identifier and a
    label, with whatever the user typed already gone. Reporting the record's
    own name here would be inventing a match that nothing observed.
    """
    return {
        "geoname_id": candidate.geoname_id,
        "label": label,
        "name": candidate.name,
        "admin1_name": candidate.admin1_name,
        "country_name": candidate.country_name,
        "feature_code": candidate.feature_code,
        "population": candidate.population,
        "latitude": repr(candidate.latitude),
        "longitude": repr(candidate.longitude),
        "timezone_id": candidate.timezone_id,
        "matched_name": None,
    }


def _effective_block(
    effective: EffectiveInput, normalized: Mapping[str, str]
) -> dict:
    """Which record, which time, and where each of them came from."""
    return {
        "date": normalized["date"],
        "time": normalized["time"],
        "time_assumed": effective.time_assumed,
        "place": _place_block(effective.place, effective.label),
        "place_assumed": effective.place_assumed,
        "source": effective.source,
    }


def _assumptions_block(effective: EffectiveInput) -> dict:
    """The sentences the page shows wherever an assumed value appears.

    Produced in Python (section 7.3) so that the badge, the birth-details
    block and the results header line all say the same thing, and so that a
    change of wording is one change here rather than three in the page.
    """
    labels = []
    if effective.time_assumed:
        labels.append(
            f"Time {ASSUMED_TIME_TEXT} assumed: no time was supplied"
        )
    if effective.place_assumed:
        labels.append(
            f"Birthplace {effective.label} assumed: the configured default"
        )
    return {
        "any": effective.time_assumed or effective.place_assumed,
        "time": effective.time_assumed,
        "place": effective.place_assumed,
        "labels": labels,
    }


def _suggestion_block(
    candidate: PlaceCandidate, label: str, display_label: str
) -> dict:
    """One entry of the suggestions list (Layer 15 section 5.2).

    Two labels, and they are not interchangeable. ``label`` is what a
    selection writes into the field and what the server compares the
    submission against (section 5.3); ``display_label`` is what the option
    reads as, and carries ``(matched: …)`` when the name that matched is a
    different name. Both are built by Layer 2, which owns the normalisation
    that decides "different"; the page shows one and sends back the other.
    """
    return {
        "geoname_id": candidate.geoname_id,
        "label": label,
        "display_label": display_label,
        "name": candidate.name,
        "admin1_name": candidate.admin1_name,
        "country_name": candidate.country_name,
        "population": candidate.population,
        "matched_name": candidate.matched_name,
    }


def suggestions_document(query: str, suggestions: Iterable[tuple]) -> dict:
    """The whole answer to ``POST /api/places`` (Layer 15 section 5.2).

    ``suggestions`` is an iterable of ``(PlaceCandidate, label,
    display_label)`` triples, in the order the resolver returned them; both
    labels are built by Layer 2's own rules, so the page composes neither and
    compares neither. ``q`` is echoed exactly as it arrived: the page applies
    a response only when the echo still equals its field.
    """
    if not isinstance(query, str):
        raise TypeError(f"query must be a str; got {type(query).__name__}.")
    return {
        "schema": SCHEMA,
        "q": query,
        "suggestions": [
            _suggestion_block(candidate, label, display_label)
            for candidate, label, display_label in suggestions
        ],
    }


def serialize(
    result: LocatedChartAndDashaResult,
    parsed: ParsedRequest,
    *,
    effective: EffectiveInput,
    rows: Optional[tuple] = None,
) -> dict:
    """One finished calculation as the JSON document of section 7.3.

    Pure and deterministic: the same result, parsed request and effective
    input always give the same ``dict``.
    ``tests/test_viewer_transport.py`` keeps a golden copy of one such
    document.

    ``rows`` is the depth-3 row extraction. The server performs it inside the
    engine lock, together with the single pipeline call, and passes it here so
    that serialisation -- which touches nothing global -- happens outside the
    lock; a caller that does not care passes nothing and the rows are extracted
    here instead.
    """
    if not isinstance(result, LocatedChartAndDashaResult):
        raise TypeError(
            "result must be a LocatedChartAndDashaResult; got "
            f"{type(result).__name__}."
        )
    if not isinstance(parsed, ParsedRequest):
        raise TypeError(
            f"parsed must be a ParsedRequest; got {type(parsed).__name__}."
        )
    if not isinstance(effective, EffectiveInput):
        raise TypeError(
            f"effective must be an EffectiveInput; got "
            f"{type(effective).__name__}."
        )

    # Decision D13: the display zone is the birth place's own zone. The key
    # comes from Layer 2, which stores an IANA identifier; ``resolve_zone`` is
    # the system's single zone validator and is applied to that key alone.
    zone_key = result.location.timezone_id

    normalized = {
        "date": result.request.birth_date.isoformat(),
        "time": result.request.birth_time.isoformat(),
        "place_id": str(effective.place.geoname_id),
        "place_label": effective.label,
    }

    return serialize_timeline_document(
        result.timeline,
        submitted=parsed.submitted(),
        normalized=normalized,
        zone_key=zone_key,
        birth_utc=result.chart.moment_utc,
        svg=result.svg,
        engine=_engine_block(result),
        location=_location_block(result),
        effective=_effective_block(effective, normalized),
        assumptions=_assumptions_block(effective),
        rows=rows,
    )


# --- section 9.4: errors, and the single encoder ---------------------------


def error_document(kind: str, message: str) -> dict:
    """The one shape every error response has, HTTP-level ones included.

    Layer 15 section 7.3: the ``candidates`` list of Layer 14's
    ``ambiguous_place`` is gone with the kind itself. No name is resolved on
    this path, so no request can be ambiguous and no candidate list can exist
    to attach.
    """
    return {"schema": SCHEMA, "error": {"kind": kind, "message": message}}


def encode(document: dict) -> bytes:
    """The single JSON encoding of this contract (section 9.3).

    ``allow_nan=False`` is the encoder's half of the ``parse_constant``
    refusal: neither direction of this transport may carry ``NaN`` or
    ``Infinity``, which are not JSON and which no consumer agrees on.
    """
    text = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return text.encode("utf-8")
