#!/usr/bin/env python3
"""Layers 14, 15, 19 and 20 browser acceptance: drive the viewer in a real browser, record the evidence.

Validation tooling only (Layer 14 sections 13.4 and 14, Layer 15 section 13).
This script is NOT a project dependency, is never imported by the package and is
not collected by pytest; like ``tools/render/rasterise_inspection.py`` it needs
Playwright for Python with its Chromium in the environment that runs *the
script*:

    PYTHONPATH=src python tools/viewer/acceptance.py --geodata PATH --ephemeris PATH
            --out DIR [--python PATH-TO-INTERPRETER] [--default-place-id ID]
            [--keep-server] [--chromium PATH]

``--chromium`` names a Chromium executable for Playwright to launch instead of
its own bundled browser (``executable_path``); without it Playwright's own is
used, as before.

``--default-place-id`` is passed through to the viewer subprocess. It is needed
for the fixture database, which does not contain the built-in default record
1269321 (Jammu) and would make the viewer exit 4 at start-up; 1268782
(Jalandhar) is the override the fixture runs use.

``--python`` names the interpreter that runs the viewer subprocess and the CLI
comparisons; it defaults to the interpreter running this script. The two may be
different: the environment with Playwright and Chromium need not be the
environment with ``pyswisseph`` and ``timezonefinder``. So, for example:

    python3 tools/viewer/acceptance.py --python .venv/bin/python \\
            --geodata data/geodata.sqlite --ephemeris ephe --out ~/l14accept

What it does, in order:

* starts ``<python> -m vedic_chart.viewer --geodata … --ephemeris … --port 0``
  with ``PYTHONPATH=src``, ``PYTHONDONTWRITEBYTECODE=1`` and
  ``PYTHONUNBUFFERED=1`` (the third only so that the banner can be read line by
  line from a pipe; it changes nothing the viewer does), and reads the
  ``viewer: http://127.0.0.1:<port>/`` banner line for the URL;
* launches headless Chromium and runs every named check of section 13.4;
* writes ``DIR/report.json`` (one entry per check with pass/fail/skipped and the
  measured values), the screenshots, the captured JSON responses, the SVG bytes
  and the CLI outputs it compared against;
* stops the server with SIGINT and exits **non-zero if any check failed**.

``DIR`` must be outside the repository checkout: the script refuses a path
inside its own source tree, so that an acceptance run can never write into the
working tree it is testing. Everything the run produces is written under
``DIR`` and nowhere else.

The checks are the named list of Layer 14 section 13.4 as Layer 15 section 13
extends it. The two year-convention variants of the reference flows are gone
with the year radio group itself: the page can no longer produce a 365.25
result, because the viewer now fixes the convention (Layer 15 section 6).

    startup_banner, reference_jalandhar_365256363, reference_jammu_365256363
    (skipped, with an explicit entry, when the Jammu record is not in the
    configured database), svg_bytes_equal_cli, svg_dom_semantics,
    svg_pixels_equal_standalone, table_text_equal_cli, expand_levels,
    expand_birth_chain_focus_pd, birth_markers, keyboard_model,
    accessibility_tree, divergence_chains, superseded_response, errors,
    microseconds_toggle, stale_inputs_banner, mobile_scrolling,
    defaults_date_only, defaults_time_only, defaults_place_only,
    combobox_keyboard, combobox_pointer, combobox_stale,
    selection_invalidated_on_edit, invalid_time_no_fallback, year_implicit,
    default_override, default_unavailable, network_routes, csp_clean

Layer 19 section 9.3 adds the chart-style checks, each on a page of its own
(see the comment above ``StylePage``), and full-page previews of every
reference birth in every style at 1280 x 800 and 375 x 812
(``screenshots/preview_<birth>_<style>_<width>.png``, recorded by
``style_previews``):

    style_default_north, style_switch_no_requests,
    style_one_calculation_per_generate, style_both_side_by_side_1280,
    style_both_stacked_375, style_both_threshold, style_single_layout_unchanged,
    style_fallback_missing, style_fallback_malformed, style_fallback_valid,
    style_during_loading, style_after_failure, style_after_cancel,
    style_stale_preserved, style_keyboard,
    style_assumptions_and_dasha_preserved, style_unique_ids,
    south_svg_bytes_equal_renderer, south_svg_pixels_equal_standalone,
    south_text_bounds_600, style_previews

The births a Layer 19 check runs for are Jalandhar and, when the record is in
the configured database, Jammu; otherwise the check's report entry carries an
explicit ``jammu: skipped`` note with the reason.

Layer 20 section 10 adds the natal-transit overlay checks (transit instant
2026-10-08 14:30:00 at the natal record), each on pages of its own opened with
``#acceptance`` (see the comment above ``TransitPage``), with full-page
previews ``screenshots/transit_<birth>_<style>_<width>.png`` and a grayscale
``transit_<birth>_grayscale_1280.png``:

    transit_control_default, transit_metadata_fallback,
    transit_sign_placement, transit_text_bounds_600,
    transit_synthetic_crowded_600, transit_replacement,
    transit_request_counts, transit_races, transit_errors,
    transit_preserved_state, transit_previews

``transit_synthetic_crowded_600`` drives the page's own composition with
labelled **synthetic** natal and transit charts (``tests/render_helpers.py``,
rendered through the project interpreter with the server's fixed options): the
natal document goes in through ``window.__loadFixture`` and the transit
document is the viewer's real answer to the page's transit request with the
four synthetic keys swapped in by route interception
(``screenshots/transit_synthetic_<case>_600.png``).

``year_implicit`` counts the transit fieldset and its one checkbox, and
``south_svg_bytes_equal_renderer`` expects the key-order tail
``south_indian_svg, overlay`` (Layer 20 section 9).

Two facts about the comparisons are recorded rather than asserted, because the
specification says they are not the viewer's to guarantee:

* the order in which the server completes a burst of superseded submissions
  (section 2.1: the engine lock guarantees exclusion, not order);
* the header line of the committed golden dasha table
  ``tests/fixtures/dasha/jalandhar_md_ad_365256363_second_kolkata.txt`` versus
  the header line produced locally. The goldens were made on another machine
  and the Moon longitude can differ in the last float digits between
  platforms. Only the table rows are compared; both header lines are recorded.

Two comparisons are narrowed, each for a stated reason and with the reason in
the report entry:

* ``svg_pixels_equal_standalone`` compares every fully covered pixel row. The
  chart's height at 600 px is fractional, a screenshot clip rounds up, and that
  last partial row shows whatever lies *behind* the element -- the page in one
  case and a blank document in the other, which is not the chart.
* ``csp_clean`` classifies the console errors Chromium logs for the 400, 404 and
  409 answers the ``errors`` check deliberately provokes. Those are the server's
  contract working; every other console error, and every
  ``securitypolicyviolation`` event, fails the check.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import struct
import subprocess
import sys
import threading
import time
import traceback
import zlib
from pathlib import Path

# --- constants from the specification ---------------------------------------

#: Section 8.3 / viewer.js: the note shown when the two birth chains differ.
DIVERGENCE_NOTE = (
    "The nominal and quantized birth chains differ. N marks the chain "
    "defined by the Moon's exact nakṣatra fraction; Q marks the chain whose "
    "quantized microsecond intervals contain the birth timestamp. They "
    "differ only when a post-birth remainder is shorter than one microsecond "
    "(Layer 12 §7)."
)

#: Section 14: the two reference births. ``place_query`` is what is *typed*
#: into the combobox; ``place_label`` is the server-built label the page writes
#: into the field on selection and the string the CLI is given, so that both
#: sides of every comparison name the same geodata record (Layer 15 section 5).
JALANDHAR = {
    "date": "1995-03-21",
    "time": "06:45",
    "place_query": "Jal",
    "place_label": "Jalandhar, Punjab, India",
}
JAMMU = {
    "date": "2001-02-04",
    "time": "10:45",
    "place_query": "Jam",
    "place_label": "Jammu, Jammu and Kashmir, India",
}

YEAR_365256363 = "365.256363"

#: Layer 15 section 6: the one sentence the page shows, produced in Python and
#: carried in ``timeline.year_convention.display``.
YEAR_DISPLAY = "Mean Sidereal year — 365.256363 days"

#: Layer 15 sections 2 and 3, verbatim.
ASSUMED_BADGE = "Uses assumed birth details"
SELECTION_PROMPT = (
    "Select a suggestion from the list, or clear the field to use the "
    "default birthplace."
)
STALE_SCHEMA_SENTENCE = "This page is out of date: reload it to continue."

#: Section 11.3 as Layer 15 section 5.2 extends it: the only five routes the
#: page may ask for.
ALLOWED_PATHS = ("/", "/viewer.css", "/viewer.js", "/api/chart", "/api/places")

#: Section 14.2: what the resolver must say about these two records. There is no
#: resolution block any more (Layer 15 section 5.4), so what is asserted is the
#: record the page selected and the location the chart was built from.
EXPECTED_PLACES = {
    "Jalandhar, Punjab, India": {
        "canonical_name": "Jalandhar, Punjab, India",
        "latitude": "31.32556",
        "longitude": "75.57917",
        "timezone_id": "Asia/Kolkata",
        "offset": "+05:30",
        "geoname_id": 1268782,
        "birth_chain": ["Ju", "Ju-Su", "Ju-Su-Me"],
    },
    "Jammu, Jammu and Kashmir, India": {
        "canonical_name": "Jammu, Jammu and Kashmir, India",
        "latitude": "32.73528",
        "longitude": "74.86167",
        "timezone_id": "Asia/Kolkata",
        "offset": "+05:30",
        "geoname_id": 1269321,
        "birth_chain": ["Ma", "Ma-Ra", "Ma-Ra-Sa"],
    },
}

PIXEL_WIDTHS = (600, 1080)

#: Layer 15 section 4.2: the banner line that names the effective default
#: birthplace record, which several checks read rather than assume.
DEFAULT_PLACE_LINE = re.compile(
    r"default place: (?P<id>[0-9]+) = (?P<label>.+?) \((?P<zone>[^()]+)\)"
    r"(?P<override> \(override\))?\Z"
)

#: Layer 15 section 6: the banner no longer offers a choice, it states one.
YEAR_BANNER_LINE = (
    "dasha year convention: 365.256363 days (Mean Sidereal year, fixed by "
    "the viewer)"
)

#: A resolver query, run through the project interpreter, that says which record
#: a CLI ``--place`` string resolves to. The acceptance script compares that
#: record and its coordinates with the ones the response carries, so that "the
#: CLI produced the same bytes" is never an accident of two different places.
RESOLVE_SNIPPET = """
import json, sys
from vedic_chart.location.offline.resolver import OfflineLocationResolver

with OfflineLocationResolver(sys.argv[1]) as resolver:
    location, decision = resolver.resolve_with_details(sys.argv[2])
    print(json.dumps({
        "geoname_id": decision.chosen.geoname_id,
        "canonical_name": location.canonical_name,
        "latitude": repr(location.latitude),
        "longitude": repr(location.longitude),
        "timezone_id": location.timezone_id,
    }))
"""


# --- the report --------------------------------------------------------------


def brief(value, limit=400):
    """A short repr, so that one mismatched 819-row list cannot flood the report."""
    text = repr(value)
    if len(text) <= limit:
        return text
    return text[:limit] + f"… ({len(text)} chars)"


class Check:
    """One named entry of the report."""

    def __init__(self, name):
        self.name = name
        self.status = "pass"
        self.detail = {}
        self.failures = []

    def note(self, key, value):
        self.detail[key] = value

    def require(self, ok, message):
        if not ok:
            self.status = "fail"
            self.failures.append(message)
        return bool(ok)

    def equals(self, label, actual, expected):
        return self.require(
            actual == expected,
            f"{label}: expected {brief(expected)}, got {brief(actual)}",
        )

    def fail(self, message):
        self.status = "fail"
        self.failures.append(message)

    def skip(self, reason):
        self.status = "skipped"
        self.detail["skipped_because"] = reason

    def as_dict(self):
        return {
            "name": self.name,
            "status": self.status,
            "failures": self.failures,
            "measured": self.detail,
        }


class Report:
    def __init__(self):
        self.checks = []
        self.environment = {}
        self.banner = {}
        self.measurements = {}

    def run(self, name, function, *args):
        check = Check(name)
        self.checks.append(check)
        started = time.monotonic()
        try:
            function(check, *args)
        except Exception as error:  # noqa: BLE001 -- a crashed check is a failed check
            check.fail(f"exception: {type(error).__name__}: {error}")
            check.note("traceback", traceback.format_exc())
        check.note("seconds", round(time.monotonic() - started, 3))
        print(f"  {check.status.upper():<7} {name}", flush=True)
        for failure in check.failures:
            print(f"          {failure}", flush=True)
        return check

    def failed(self):
        return [check for check in self.checks if check.status == "fail"]

    def as_dict(self):
        counts = {"pass": 0, "fail": 0, "skipped": 0}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        return {
            "tool": "tools/viewer/acceptance.py",
            "specification": (
                "docs/LAYER14_INTERACTIVE_VIEWER_SPEC.md sections 13.4 and 14; "
                "docs/LAYER15_VIEWER_INPUT_FLOW_SPEC.md section 13; "
                "docs/LAYER19_SOUTH_INDIAN_VIEWER_SPEC.md section 9.3; "
                "docs/LAYER20_TRANSIT_OVERLAY_SPEC.md section 10"
            ),
            "environment": self.environment,
            "banner": self.banner,
            "measurements": self.measurements,
            "counts": counts,
            "checks": [check.as_dict() for check in self.checks],
        }


# --- the viewer subprocess ---------------------------------------------------


class ViewerProcess:
    """``python -m vedic_chart.viewer`` on an OS-assigned loopback port."""

    def __init__(self, python, repo_root, geodata, ephemeris, default_place_id=None):
        self.command = [
            str(python),
            "-m",
            "vedic_chart.viewer",
            "--geodata",
            str(geodata),
            "--ephemeris",
            str(ephemeris),
            "--port",
            "0",
        ]
        if default_place_id is not None:
            self.command += ["--default-place-id", str(default_place_id)]
        environment = dict(os.environ)
        environment["PYTHONPATH"] = "src"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONUNBUFFERED"] = "1"
        self.environment = environment
        self.lock = threading.Lock()
        self.stdout_lines = []
        self.stderr_lines = []  # (monotonic seconds, text)
        self.process = subprocess.Popen(  # noqa: S603 -- fixed argument vector
            self.command,
            cwd=str(repo_root),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.url = None
        self._start_reader(self.process.stdout, self.stdout_lines, False)
        self._start_reader(self.process.stderr, self.stderr_lines, True)

    def _start_reader(self, stream, sink, timestamped):
        def read():
            for line in stream:
                text = line.rstrip("\n")
                with self.lock:
                    sink.append((round(time.monotonic(), 4), text) if timestamped else text)

        thread = threading.Thread(target=read, daemon=True)
        thread.start()

    def wait_for_banner(self, timeout=120.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                lines = list(self.stdout_lines)
            if any(line.startswith("press Ctrl-C to stop") for line in lines):
                for line in lines:
                    if line.startswith("viewer: "):
                        self.url = line[len("viewer: ") :].strip()
                if self.url:
                    return lines
                raise RuntimeError("the banner has no 'viewer: ' line: " + repr(lines))
            if self.process.poll() is not None:
                with self.lock:
                    errors = [text for _, text in self.stderr_lines]
                raise RuntimeError(
                    f"the viewer exited with {self.process.returncode} before serving; "
                    f"stdout={lines!r} stderr={errors!r}"
                )
            time.sleep(0.05)
        raise RuntimeError("timed out waiting for the viewer banner")

    def stderr_since(self, mark):
        with self.lock:
            return [
                {"at": round(when - mark, 4), "line": text}
                for when, text in self.stderr_lines
                if when >= mark
            ]

    def mark(self):
        return time.monotonic()

    def stop(self):
        """Ctrl-C, as documented: exit 130 with the listening socket closed."""
        if self.process.poll() is not None:
            return self.process.returncode
        self.process.send_signal(signal.SIGINT)
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        return self.process.returncode


# --- the project CLI, for the "unchanged outputs" comparisons ----------------


class ProjectCli:
    def __init__(self, python, repo_root, geodata, ephemeris):
        self.python = str(python)
        self.repo_root = repo_root
        self.geodata = str(geodata)
        self.ephemeris = str(ephemeris)
        self.environment = dict(os.environ)
        self.environment["PYTHONPATH"] = "src"
        self.environment["PYTHONDONTWRITEBYTECODE"] = "1"
        self.runs = []

    def run(self, arguments):
        command = [self.python, "-m", "vedic_chart.app", *arguments]
        completed = subprocess.run(  # noqa: S603 -- fixed argument vector
            command,
            cwd=str(self.repo_root),
            env=self.environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.runs.append({"command": command, "returncode": completed.returncode})
        if completed.returncode != 0:
            raise RuntimeError(
                f"{' '.join(command)} exited {completed.returncode}: {completed.stderr.strip()}"
            )
        return completed.stdout

    def svg(self, date, time_text, place, target):
        """One chart file for a date, a wall time and a place **query**.

        The page never sends a query -- it sends a record identifier -- so the
        query given here is the one the resolver maps to that same record, which
        ``resolve`` verifies by identifier and coordinates before the bytes are
        compared.

        An existing file at ``target`` is removed first: the CLI refuses to
        overwrite one (exit 5), and ``--out`` is this script's own scratch
        directory, so a second run into the same directory must not fail on the
        leftovers of the first.
        """
        target.unlink(missing_ok=True)
        self.run(
            [
                "--date",
                date,
                "--time",
                time_text,
                "--place",
                place,
                "--geodata",
                self.geodata,
                "--ephemeris",
                self.ephemeris,
                "--out",
                str(target),
            ]
        )
        return target.read_bytes()

    def dasha(self, date, time_text, place, zone, depth="md-ad-pd"):
        """The Layer 13 table for the same birth, with the fixed convention.

        ``--dasha-year 365.256363`` is explicit here because the CLI contract is
        unchanged (Layer 15 section 6): it is the *viewer* that supplies the
        convention implicitly, and this is the comparison that shows the two
        agree.
        """
        return self.run(
            [
                "--date",
                date,
                "--time",
                time_text,
                "--place",
                place,
                "--geodata",
                self.geodata,
                "--ephemeris",
                self.ephemeris,
                "--dasha",
                depth,
                "--dasha-year",
                YEAR_365256363,
                "--dasha-out",
                "-",
                "--dasha-zone",
                zone,
            ]
        )

    def resolve(self, query):
        """Which record a ``--place`` string resolves to, as a dict."""
        command = [self.python, "-c", RESOLVE_SNIPPET, self.geodata, query]
        completed = subprocess.run(  # noqa: S603 -- fixed argument vector
            command,
            cwd=str(self.repo_root),
            env=self.environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.runs.append({"command": command[:2] + ["<resolve>", self.geodata, query],
                          "returncode": completed.returncode})
        if completed.returncode != 0:
            raise RuntimeError(
                f"resolving {query!r} exited {completed.returncode}: "
                f"{completed.stderr.strip()}"
            )
        return json.loads(completed.stdout)


def parse_cli_table(text):
    """Split a Layer 13 table into its header lines and its six-column rows."""
    lines = text.splitlines()
    header_index = None
    for index, line in enumerate(lines):
        if line.startswith("Level") and "Chain" in line and line.rstrip().endswith("Q"):
            header_index = index
            break
    if header_index is None:
        raise RuntimeError("no column header line in the dasha table")
    header = lines[header_index]
    bounds = []
    cursor = 0
    for word in ("Level", "Chain", "Start", "End", "N", "Q"):
        position = header.index(word, cursor)
        bounds.append(position)
        cursor = position + len(word)
    rows = []
    for line in lines[header_index + 1 :]:
        if not line.strip():
            continue
        cells = []
        for column, start in enumerate(bounds):
            stop = bounds[column + 1] if column + 1 < len(bounds) else len(line)
            cells.append(line[start:stop].strip())
        rows.append(cells)
    return {"header_lines": lines[:header_index], "column_header": header, "rows": rows}


# --- PNG comparison ----------------------------------------------------------


def decode_png(data):
    """A pure-Python reader for the PNGs Chromium writes: 8-bit, non-interlaced.

    Used when Pillow is absent, and as the second opinion the specification asks
    for in that case. Returns (width, height, channels, pixel bytes).
    """
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    position = 8
    header = None
    compressed = b""
    palette = b""
    while position < len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        kind = data[position + 4 : position + 8]
        payload = data[position + 8 : position + 8 + length]
        position += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed += payload
        elif kind == b"PLTE":
            palette = payload
        elif kind == b"IEND":
            break
    if header is None:
        raise ValueError("no IHDR")
    width, height, depth, colour, compression, filtering, interlace = header
    if depth != 8 or compression != 0 or filtering != 0 or interlace != 0:
        raise ValueError(f"unsupported PNG: depth={depth} interlace={interlace}")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour]
    raw = zlib.decompress(compressed)
    stride = width * channels
    out = bytearray(height * stride)
    previous = bytearray(stride)
    offset = 0
    for row in range(height):
        filter_type = raw[offset]
        offset += 1
        line = bytearray(raw[offset : offset + stride])
        offset += stride
        if filter_type == 1:
            for index in range(channels, stride):
                line[index] = (line[index] + line[index - channels]) & 0xFF
        elif filter_type == 2:
            for index in range(stride):
                line[index] = (line[index] + previous[index]) & 0xFF
        elif filter_type == 3:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                line[index] = (line[index] + ((left + previous[index]) >> 1)) & 0xFF
        elif filter_type == 4:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                up = previous[index]
                upper_left = previous[index - channels] if index >= channels else 0
                estimate = left + up - upper_left
                distance_left = abs(estimate - left)
                distance_up = abs(estimate - up)
                distance_corner = abs(estimate - upper_left)
                if distance_left <= distance_up and distance_left <= distance_corner:
                    predictor = left
                elif distance_up <= distance_corner:
                    predictor = up
                else:
                    predictor = upper_left
                line[index] = (line[index] + predictor) & 0xFF
        elif filter_type != 0:
            raise ValueError(f"unknown PNG filter {filter_type}")
        out[row * stride : (row + 1) * stride] = line
        previous = line
    if colour == 3:
        expanded = bytearray(width * height * 3)
        for index, entry in enumerate(out):
            expanded[index * 3 : index * 3 + 3] = palette[entry * 3 : entry * 3 + 3]
        return width, height, 3, bytes(expanded)
    return width, height, channels, bytes(out)


def compare_pngs(left_path, right_path, rows=None):
    """Differing-pixel count between two PNGs, by whichever reader is present.

    ``rows`` limits the comparison to the first N pixel rows. It is used for the
    one row a screenshot can legitimately disagree on: when an element's height
    is fractional, the screenshot clip rounds **up**, so the last row is a
    sliver of whatever lies behind the element — the page in one case, a blank
    document in the other. Every fully covered row is compared.
    """
    left_bytes = left_path.read_bytes()
    right_bytes = right_path.read_bytes()
    result = {
        "bytes_equal": left_bytes == right_bytes,
        "compared_rows": rows,
        "sha256": {
            left_path.name: hashlib.sha256(left_bytes).hexdigest(),
            right_path.name: hashlib.sha256(right_bytes).hexdigest(),
        },
    }
    try:
        from PIL import Image  # noqa: PLC0415 -- optional, tooling only
    except ImportError:
        Image = None
    if Image is not None:
        with Image.open(left_path) as left_image, Image.open(right_path) as right_image:
            left_rgba = left_image.convert("RGBA")
            right_rgba = right_image.convert("RGBA")
            result["method"] = "pillow"
            result["size"] = [list(left_rgba.size), list(right_rgba.size)]
            if left_rgba.size != right_rgba.size:
                result["differing_pixels"] = None
                result["size_mismatch"] = True
                return result
            height = left_rgba.size[1] if rows is None else min(rows, left_rgba.size[1])
            width = left_rgba.size[0]
            left_data = left_rgba.crop((0, 0, width, height)).tobytes()
            right_data = right_rgba.crop((0, 0, width, height)).tobytes()
            differing = 0
            for index in range(0, len(left_data), 4):
                if left_data[index : index + 4] != right_data[index : index + 4]:
                    differing += 1
            result["differing_pixels"] = differing
            return result
    # No Pillow: the byte comparison above plus a pure-Python decode.
    left_width, left_height, left_channels, left_pixels = decode_png(left_bytes)
    right_width, right_height, right_channels, right_pixels = decode_png(right_bytes)
    result["method"] = "pure-python-png-reader"
    result["size"] = [[left_width, left_height], [right_width, right_height]]
    if (left_width, left_height, left_channels) != (right_width, right_height, right_channels):
        result["differing_pixels"] = None
        result["size_mismatch"] = True
        return result
    height = left_height if rows is None else min(rows, left_height)
    limit = height * left_width * left_channels
    differing = 0
    for index in range(0, limit, left_channels):
        if left_pixels[index : index + left_channels] != right_pixels[index : index + left_channels]:
            differing += 1
    result["differing_pixels"] = differing
    return result


# --- page helpers ------------------------------------------------------------

ROW_SNAPSHOT = """
() => Array.from(document.querySelectorAll('#dasha-body tr')).map(tr => ({
  id: tr.id,
  level: tr.getAttribute('aria-level'),
  posinset: tr.getAttribute('aria-posinset'),
  setsize: tr.getAttribute('aria-setsize'),
  expanded: tr.getAttribute('aria-expanded'),
  tabindex: tr.getAttribute('tabindex'),
  label: tr.getAttribute('aria-label'),
  classes: tr.className,
  cells: Array.from(tr.children).map(td => td.textContent)
}))
"""

CSP_LISTENER = """
window.__acceptanceViolations = [];
document.addEventListener('securitypolicyviolation', function (event) {
  window.__acceptanceViolations.push({
    directive: event.violatedDirective,
    blocked: event.blockedURI,
    source: event.sourceFile
  });
});
"""

#: The four submitted strings of schema /2, written straight into the controls.
#: The birthplace identifier is assigned **after** the text field's `input`
#: event, because that event is exactly what clears a selection (Layer 15
#: section 2 rule 4); a check that wants a selection made the way a person makes
#: it uses `Viewer.select_place` instead.
SET_FORM = """
(values) => {
  const set = (id, value) => {
    const field = document.getElementById(id);
    field.value = value;
    field.dispatchEvent(new Event('input', {bubbles: true}));
    field.dispatchEvent(new Event('change', {bubbles: true}));
    return field.value;
  };
  const result = {
    date: set('birth-date', values.date),
    time: set('birth-time', values.time),
    place_text: set('birth-place', values.place_text)
  };
  const identifier = document.getElementById('place-id');
  identifier.value = values.place_id || '';
  result.place_id = identifier.value;
  return result;
}
"""

#: A request made from the page's own origin with the page's own token, for the
#: cases the user interface deliberately cannot produce: a stale /1 body, an
#: identifier without a label, an impossible time that the native control
#: refuses to hold.
DIRECT_API = """
(argument) => {
  const token = document.querySelector('meta[name="viewer-token"]').content;
  return fetch(argument.path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json; charset=utf-8',
              'X-Viewer-Token': token},
    body: JSON.stringify(argument.body)
  }).then(response => response.text().then(text => ({
    status: response.status, text: text
  })));
}
"""

#: Everything the combobox shows at one moment (Layer 15 section 5.2).
COMBOBOX_STATE = """
() => {
  const field = document.getElementById('birth-place');
  const marker = document.getElementById('place-marker');
  return {
    value: field.value,
    place_id: document.getElementById('place-id').value,
    expanded: field.getAttribute('aria-expanded'),
    activedescendant: field.getAttribute('aria-activedescendant'),
    autocomplete: field.getAttribute('aria-autocomplete'),
    role: field.getAttribute('role'),
    marker_hidden: marker.hidden,
    marker_text: marker.textContent,
    message: document.getElementById('birth-place-message').textContent,
    options: Array.from(document.querySelectorAll('#place-listbox li')).map(
      item => ({id: item.id, role: item.getAttribute('role'),
                text: item.textContent,
                selected: item.getAttribute('aria-selected'),
                active: item.classList.contains('v-option-active')})
    )
  };
}
"""

#: Section 10.2: superseding is what happens when Generate is pressed *while* a
#: request is in flight. One calculation takes about a tenth of a second here,
#: so the submissions are made through the DOM, one evaluation apart: a
#: Playwright click round trip is slower than the server.
SET_FORM_AND_SUBMIT = SET_FORM.replace(
    "  return result;",
    "  document.getElementById('generate').click();\n  return result;",
)

MARK_OLD_RESULTS = """
() => {
  const body = document.getElementById('results-body');
  if (body) { body.setAttribute('data-acceptance-old', '1'); }
  return Boolean(body);
}
"""

RESULTS_REPLACED = "() => !document.querySelector('#results-body[data-acceptance-old]')"

SVG_SEMANTICS = """
(root) => {
  const counts = (node) => {
    let elements = 1;
    let texts = 0;
    const walk = (parent) => {
      parent.childNodes.forEach(child => {
        if (child.nodeType === 1) { elements += 1; walk(child); }
        else if (child.nodeType === 3) { texts += 1; }
      });
    };
    walk(node);
    return {elements: elements, text_nodes: texts};
  };
  const title = root.querySelector('title');
  const desc = root.querySelector('desc');
  const box = root.getBoundingClientRect ? root.getBoundingClientRect() : null;
  return {
    role: root.getAttribute('role'),
    labelledby: root.getAttribute('aria-labelledby'),
    describedby: root.getAttribute('aria-describedby'),
    view_box: root.getAttribute('viewBox'),
    preserve_aspect_ratio: root.getAttribute('preserveAspectRatio'),
    title_id: title ? title.id : null,
    title_text: title ? title.textContent : null,
    desc_id: desc ? desc.id : null,
    desc_text: desc ? desc.textContent : null,
    counts: counts(root),
    box: box ? {width: box.width, height: box.height} : null
  };
}
"""


class Viewer:
    """One browser page on the viewer, with the helpers every check shares."""

    def __init__(self, page, url, requests, console, page_errors):
        self.page = page
        self.url = url
        self.api_url = url.rstrip("/") + "/api/chart"
        self.requests = requests
        self.console = console
        self.page_errors = page_errors
        self.shown = None  # the key of the document the page is displaying

    # -- form and submission --------------------------------------------------

    def set_form(self, values):
        return self.page.evaluate(SET_FORM, values)

    def api(self, path, body):
        """One request from the page's origin, with the page's own token."""
        answer = self.page.evaluate(DIRECT_API, {"path": path, "body": body})
        try:
            answer["document"] = json.loads(answer["text"])
        except ValueError:
            answer["document"] = None
        return answer

    def combobox(self):
        return self.page.evaluate(COMBOBOX_STATE)

    def select_place(self, query, label, timeout=30000):
        """Choose a suggestion the way a person does, by pointer.

        The typed text is a prefix; what lands in the field is the server's own
        label, which is what the server compares the submission against
        (Layer 15 section 5.3). The option is found by its *display* text, which
        is the label, optionally with the alias tail the page adds when the name
        that matched is a different one.
        """
        self.page.fill("#birth-place", "")
        self.page.fill("#birth-place", query)
        self.page.wait_for_selector("#place-listbox li", timeout=timeout)
        position = self.page.evaluate(
            "(label) => { const items = Array.from("
            " document.querySelectorAll('#place-listbox li'));"
            " for (let index = 0; index < items.length; index++) {"
            "   const text = items[index].textContent;"
            "   if (text === label || text.startsWith(label + ' (matched:'))"
            "     return index; } return -1; }",
            label,
        )
        if position < 0:
            raise RuntimeError(
                f"no suggestion labelled {label!r} for the query {query!r}: "
                f"{brief(self.combobox()['options'])}"
            )
        self.page.click(f"#place-option-{position}")
        chosen = self.combobox()
        if chosen["value"] != label:
            raise RuntimeError(
                f"selecting {label!r} left {chosen['value']!r} in the field"
            )
        return chosen

    def type_form(self, values):
        """Fill the form the way a person does, through Playwright's own input.

        A blank ``place_label`` means the birthplace is left blank, which is the
        request for the configured default (Layer 15 section 2).
        """
        self.page.fill("#birth-date", values["date"])
        self.page.fill("#birth-time", values.get("time", ""))
        if values.get("place_label"):
            self.select_place(
                values.get("place_query") or values["place_label"],
                values["place_label"],
            )
        else:
            self.page.fill("#birth-place", "")

    def submit(self, values, typed=True, timeout=120000):
        """Submit and wait for the answer; returns (status, document, raw bytes)."""
        if typed:
            self.type_form(values)
        else:
            self.set_form(values)
        self.page.evaluate(MARK_OLD_RESULTS)
        with self.page.expect_response(
            lambda response: response.url == self.api_url, timeout=timeout
        ) as caught:
            self.page.click("#generate")
        response = caught.value
        body = response.body()
        document = json.loads(body.decode("utf-8"))
        if response.status == 200:
            self.page.wait_for_function(RESULTS_REPLACED, timeout=timeout)
        else:
            self.page.wait_for_selector("#alert:not([hidden])", timeout=timeout)
        return response.status, document, body

    def show(self, key, birth, store):
        """Make sure the page is displaying this birth."""
        if self.shown == key:
            return store[key]
        values = dict(birth)
        status, document, body = self.submit(values)
        if status != 200:
            raise RuntimeError(f"{key}: the server answered {status}: {brief(document)}")
        self.shown = key
        store[key] = {"document": document, "raw": body, "values": values}
        return store[key]

    # -- reading the page -----------------------------------------------------

    def rows(self):
        return self.page.evaluate(ROW_SNAPSHOT)

    def row_count(self):
        return self.page.evaluate("() => document.querySelectorAll('#dasha-body tr').length")

    def text(self, selector):
        return self.page.evaluate(
            "(selector) => { const node = document.querySelector(selector);"
            " return node ? node.textContent : null; }",
            selector,
        )

    def hidden(self, selector):
        return self.page.evaluate(
            "(selector) => { const node = document.querySelector(selector);"
            " return node ? node.hidden : null; }",
            selector,
        )

    def details(self, selector):
        return self.page.evaluate(
            "(selector) => { const list = document.querySelector(selector);"
            " if (!list) return null;"
            " const out = {}; const keys = list.querySelectorAll('.v-detail-key');"
            " const values = list.querySelectorAll('.v-detail-value');"
            " for (let index = 0; index < keys.length; index++) {"
            "   out[keys[index].textContent] = values[index] ? values[index].textContent : null; }"
            " return out; }",
            selector,
        )

    def active(self):
        return self.page.evaluate(
            "() => { const node = document.activeElement;"
            " if (!node) return null;"
            " return {id: node.id, tag: node.tagName, className: node.className}; }"
        )

    def active_id(self):
        return (self.active() or {}).get("id")

    def badges(self):
        """The three assumed-values badges, by the heading each sits on."""
        return self.page.evaluate(
            "() => { const read = (id) => { const node = document.getElementById(id);"
            "   return node ? {hidden: node.hidden, text: node.textContent,"
            "                  role: node.getAttribute('role'),"
            "                  classes: node.className} : null; };"
            " return {results: read('results-badge'), chart: read('chart-badge'),"
            "         dasha: read('dasha-badge')}; }"
        )

    def assumption_labels(self):
        return self.page.evaluate(
            "() => Array.from(document.querySelectorAll('#assumption-labels li'))"
            ".map(item => item.textContent)"
        )

    def marker_rows(self):
        return self.page.evaluate(
            "() => { const out = {nominal: [], quantized: []};"
            " document.querySelectorAll('#dasha-body tr').forEach(tr => {"
            "   const cells = tr.children;"
            "   if (cells[4].textContent === 'N') out.nominal.push(tr.id);"
            "   if (cells[5].textContent === 'Q') out.quantized.push(tr.id); });"
            " return out; }"
        )

    def violations(self):
        return self.page.evaluate("() => window.__acceptanceViolations || []")


def level_text(cell):
    """The Level cell carries the pointer-only toggle glyph in front of the label."""
    return cell.replace("▸", "").replace("▾", "").strip()


def page_table(viewer):
    """The rendered table as six-column rows, in the CLI's own column order."""
    return [
        [
            level_text(row["cells"][0]),
            row["cells"][1],
            row["cells"][2],
            row["cells"][3],
            row["cells"][4],
            row["cells"][5],
        ]
        for row in viewer.rows()
    ]


def chain_of(document, entry):
    """The abbreviated chain of a birth-chain entry, read off the transport."""
    for row in document["rows"]:
        if row["level"] == entry["level"] and row["lords"] == entry["lords"]:
            return row["chain"]
    raise RuntimeError(f"no row for {entry!r}")


def row_id(chain):
    return "row-" + chain.lower()


# --- the checks --------------------------------------------------------------


def check_startup_banner(check, context):
    lines = context.banner_lines
    check.note("lines", lines)
    check.require(
        bool(lines) and re.fullmatch(r"viewer: http://127\.0\.0\.1:\d+/", lines[0]),
        f"the first banner line is not the URL line: {brief(lines[:1])}",
    )
    geodata_lines = [line for line in lines if line.startswith("geodata: ")]
    check.equals("geodata lines", len(geodata_lines), 1)
    if geodata_lines:
        path = geodata_lines[0][len("geodata: ") :]
        check.note("geodata_path", path)
        check.require(Path(path).is_absolute(), f"the geodata path is not absolute: {path}")
    metadata = [line[len("geodata metadata: ") :] for line in lines if line.startswith("geodata metadata: ")]
    check.note("metadata_rows", metadata)
    check.require(len(metadata) >= 1, "the banner carries no geodata metadata row")
    ephemeris_lines = [line for line in lines if line.startswith("ephemeris: ")]
    check.equals("ephemeris lines", len(ephemeris_lines), 1)
    if ephemeris_lines:
        path = ephemeris_lines[0][len("ephemeris: ") :]
        check.note("ephemeris_path", path)
        check.require(Path(path).is_absolute(), f"the ephemeris path is not absolute: {path}")
    files = [line[len("ephemeris file: ") :] for line in lines if line.startswith("ephemeris file: ")]
    check.note("ephemeris_files", files)
    check.equals("ephemeris file lines", len(files), 3)
    for entry in files:
        check.require(
            re.search(r"\((\d+) bytes\)$", entry) is not None,
            f"the ephemeris file line carries no size: {entry}",
        )
    check.require(
        YEAR_BANNER_LINE in lines,
        "the banner does not state the fixed dasha year convention",
    )
    default_lines = [line for line in lines if line.startswith("default place: ")]
    check.equals("default place lines", len(default_lines), 1)
    check.note("default_place_line", default_lines[0] if default_lines else None)
    check.note("default_place", context.default_place)
    if default_lines:
        check.require(
            DEFAULT_PLACE_LINE.fullmatch(default_lines[0]) is not None,
            f"the default place line is not <id> = <label> (<zone>): {default_lines[0]}",
        )
        check.require(
            context.default_place.get("override")
            == (context.default_place_id is not None),
            "the banner's (override) marker does not agree with the flag: "
            f"{default_lines[0]!r} for --default-place-id "
            f"{context.default_place_id!r}",
        )
    check.require("press Ctrl-C to stop" in lines, "the banner does not say how to stop")
    check.require(
        not any("token" in line.lower() for line in lines),
        "the banner mentions a token",
    )


def check_reference(check, context, name, birth, key):
    """One reference birth, entered the way a person enters it.

    Both optional values are supplied here -- a wall time, and a birthplace
    chosen from the offline list -- so nothing is assumed and the three badges
    must be absent. What the response says about the record is asserted against
    the record itself (Layer 15 section 5.4): there is no resolution block to
    read, because no name was resolved.
    """
    viewer = context.viewer
    label = birth["place_label"]
    expected = EXPECTED_PLACES[label]
    if label == JAMMU["place_label"] and not context.jammu_available:
        check.skip(
            "the Jammu record is not in the configured database "
            f"({context.jammu_reason})"
        )
        return
    shown = viewer.show(key, birth, context.documents)
    document = shown["document"]
    (context.out / "responses" / f"{key}.json").write_bytes(shown["raw"])
    (context.out / "svg" / f"{key}_response.svg").write_text(document["svg"], encoding="utf-8")

    location = document["location"]
    effective = document["effective"]
    place = effective["place"]
    check.equals("schema", document["schema"], "vedic_chart.viewer/2")
    check.require(
        "resolution" not in document,
        "the /2 document still carries a resolution block",
    )
    check.equals("canonical_name", location["canonical_name"], expected["canonical_name"])
    check.equals("latitude", location["latitude"], expected["latitude"])
    check.equals("longitude", location["longitude"], expected["longitude"])
    check.equals("timezone_id", location["timezone_id"], expected["timezone_id"])
    check.equals("birth.offset", document["birth"]["offset"], expected["offset"])
    check.equals("effective geoname_id", place["geoname_id"], expected["geoname_id"])
    check.equals("effective label", place["label"], label)
    check.equals("effective source", effective["source"], "selected")
    check.equals("place_assumed", effective["place_assumed"], False)
    check.equals("time_assumed", effective["time_assumed"], False)
    check.equals("assumptions.any", document["assumptions"]["any"], False)
    check.equals("assumption labels", document["assumptions"]["labels"], [])
    check.equals("rows", len(document["rows"]), 819)
    check.equals(
        "request.submitted",
        document["request"]["submitted"],
        {
            "date": birth["date"],
            "time": birth["time"],
            "place_text": label,
            "place_id": str(expected["geoname_id"]),
        },
    )
    check.equals(
        "request.normalized.place_id",
        document["request"]["normalized"]["place_id"],
        str(expected["geoname_id"]),
    )
    check.equals(
        "timeline.year_convention.display",
        document["timeline"]["year_convention"]["display"],
        YEAR_DISPLAY,
    )
    check.equals(
        "timeline.year_convention.label",
        document["timeline"]["year_convention"]["label"],
        YEAR_365256363,
    )

    # Section 14.3: the header shows the five D1Meta descriptors.
    engine = document["engine"]
    engine_line = viewer.text("#engine-line")
    check.note("engine_line", engine_line)
    check.note("validation_note", viewer.text("#validation-note"))
    check.equals(
        "engine line",
        engine_line,
        f"Ayanāṃśa: {engine['ayanamsha']} · Whole Sign houses · "
        f"Mean Node · {engine['engine_spec']}",
    )
    check.equals("engine.zodiac", engine["zodiac"], "sidereal")
    check.equals("engine.house_system", engine["house_system"], "whole_sign")
    check.equals("engine.node", engine["node"], "mean")
    check.equals("validation note shown", viewer.text("#validation-note"), engine["validation_note"])
    submitted_line = viewer.text("#submitted-line")
    check.note("submitted_line", submitted_line)
    check.equals(
        "results header line",
        submitted_line,
        f"Computed from {birth['date']}, {effective['time']}, {label}",
    )

    details = viewer.details("#birth-details")
    check.note("birth_details", details)
    check.equals("Date row", details.get("Date"), f"{birth['date']} (supplied)")
    check.equals(
        "Time row", details.get("Time"), f"{effective['time']} (supplied)"
    )
    check.equals(
        "Birthplace row",
        details.get("Birthplace"),
        f"{label} (supplied — selected from the list)",
    )
    check.equals("GeoNames id row", details.get("GeoNames id"), str(expected["geoname_id"]))
    check.equals("Time zone row", details.get("Time zone"), expected["timezone_id"])

    badges = viewer.badges()
    check.note("badges", badges)
    for name_, badge in badges.items():
        check.require(
            badge["hidden"] is True,
            f"the {name_} badge is shown for a birth with nothing assumed: {badge}",
        )
    check.equals("assumption list items", viewer.assumption_labels(), [])
    check.equals("initial visible rows", viewer.row_count(), 9)

    row_bytes = len(
        json.dumps(document["rows"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    context.measurements.setdefault("json_row_block_bytes", {})[key] = row_bytes
    check.note("json_row_block_bytes", row_bytes)
    context.measurements.setdefault("response_bytes", {})[key] = len(shown["raw"])

    if key.startswith("jalandhar"):
        # One of the four combination screenshots: both optional values given.
        viewer.page.screenshot(
            path=str(context.out / "screenshots" / "combo_time_place.png"),
            full_page=True,
        )


def check_svg_bytes_equal_cli(check, context):
    viewer = context.viewer
    results = {}
    targets = [("jalandhar", JALANDHAR, f"jalandhar_{YEAR_365256363.replace('.', '')}")]
    if context.jammu_available:
        targets.append(("jammu", JAMMU, f"jammu_{YEAR_365256363.replace('.', '')}"))
    for label, birth, key in targets:
        document = viewer.show(key, birth, context.documents)["document"]
        target = context.out / "cli" / f"{label}.svg"
        query = birth["place_label"]
        resolved = context.resolved(query)
        file_bytes = context.cli.svg(birth["date"], birth["time"], query, target)
        response_bytes = document["svg"].encode("utf-8")
        entry = {
            "cli_file": str(target),
            "cli_place_query": query,
            "cli_resolved": resolved,
            "page_geoname_id": document["effective"]["place"]["geoname_id"],
            "cli_sha256": hashlib.sha256(file_bytes).hexdigest(),
            "response_sha256": hashlib.sha256(response_bytes).hexdigest(),
            "cli_bytes": len(file_bytes),
            "response_bytes": len(response_bytes),
        }
        results[label] = entry
        # The two sides must be the same record before their bytes mean anything.
        check.equals(
            f"{label} CLI query resolves to the selected record",
            resolved["geoname_id"],
            document["effective"]["place"]["geoname_id"],
        )
        check.equals(f"{label} CLI latitude", resolved["latitude"], document["location"]["latitude"])
        check.equals(f"{label} CLI longitude", resolved["longitude"], document["location"]["longitude"])
        check.equals(f"{label} svg sha256", entry["response_sha256"], entry["cli_sha256"])
    check.note("svg", results)
    context.measurements["svg_sha256"] = results


def check_svg_dom_semantics(check, context):
    viewer = context.viewer
    key = f"jalandhar_{YEAR_365256363.replace('.', '')}"
    document = viewer.show(key, JALANDHAR, context.documents)["document"]
    inserted = viewer.page.evaluate(
        "() => { const svg = document.querySelector('#chart svg'); return svg ? true : false; }"
    )
    if not check.require(inserted, "no SVG element inside #chart"):
        return
    live = viewer.page.eval_on_selector("#chart svg", SVG_SEMANTICS)
    file_text = (context.out / "cli" / "jalandhar.svg").read_text(encoding="utf-8")
    scratch = context.scratch_page()
    scratch.set_content("<!doctype html><html><body></body></html>")
    parsed = scratch.evaluate(
        "(text) => { const parsedDocument = new DOMParser().parseFromString(text, 'image/svg+xml');"
        " const root = parsedDocument.documentElement;"
        " return (" + SVG_SEMANTICS + ")(root); }",
        file_text,
    )
    scratch.close()
    check.note("inserted", live)
    check.note("file", parsed)
    check.equals("role", live["role"], "img")
    check.equals("aria-labelledby", live["labelledby"], "d1-title")
    check.equals("aria-describedby", live["describedby"], "d1-desc")
    check.equals("title id", live["title_id"], "d1-title")
    check.equals("desc id", live["desc_id"], "d1-desc")
    check.equals("title text", live["title_text"], parsed["title_text"])
    check.equals("desc text", live["desc_text"], parsed["desc_text"])
    check.equals("viewBox", live["view_box"], parsed["view_box"])
    check.equals("preserveAspectRatio", live["preserve_aspect_ratio"], parsed["preserve_aspect_ratio"])
    check.equals("element count", live["counts"]["elements"], parsed["counts"]["elements"])
    check.equals("text node count", live["counts"]["text_nodes"], parsed["counts"]["text_nodes"])
    check.require(
        document["svg"].startswith("<svg"), "the transported SVG does not start with <svg"
    )
    match = re.search(r'viewBox="0 0 (\d+) (\d+)"', file_text)
    view_width, view_height = int(match.group(1)), int(match.group(2))
    box = live["box"]
    expected_height = box["width"] * view_height / view_width
    check.note(
        "aspect",
        {
            "view_box": [view_width, view_height],
            "box": box,
            "expected_height": expected_height,
            "difference": abs(box["height"] - expected_height),
        },
    )
    check.require(
        abs(box["height"] - expected_height) <= 1.0,
        f"the rendered box {box} does not keep the {view_width}:{view_height} ratio "
        f"(expected height {expected_height}, difference "
        f"{abs(box['height'] - expected_height)})",
    )


#: The element is pinned at the viewport's top-left corner at an exact pixel
#: size on both sides of the comparison, so that neither rendering can differ by
#: a fractional offset or a rounded layout height. The properties are set
#: through the CSSOM, one at a time: assigning a `style` **attribute** would be
#: an inline style, which this page's own Content-Security-Policy forbids, and
#: the acceptance script must not provoke the violation it checks for.
PINNED_PROPERTIES = (
    "position",
    "left",
    "top",
    "margin",
    "padding",
    "border",
    "z-index",
    "width",
    "height",
    "min-width",
    "max-width",
)

PIN_ELEMENT = """
(argument) => {
  const element = document.querySelector(argument.selector);
  const style = element.style;
  const saved = {};
  argument.properties.forEach(name => { saved[name] = style.getPropertyValue(name); });
  style.setProperty('position', 'fixed');
  style.setProperty('left', '0px');
  style.setProperty('top', '0px');
  style.setProperty('margin', '0px');
  style.setProperty('padding', '0px');
  style.setProperty('border', '0px');
  style.setProperty('z-index', '2147483647');
  style.setProperty('width', argument.width + 'px');
  /* The height stays automatic, so the element's box is exactly the viewBox's
   * aspect ratio on both sides of the comparison and no partial pixel row is
   * left over at the bottom. */
  style.setProperty('height', 'auto');
  style.setProperty('min-width', '0px');
  style.setProperty('max-width', 'none');
  window.scrollTo(0, 0);
  const box = element.getBoundingClientRect();
  return {saved: saved, box: {width: box.width, height: box.height,
                              left: box.left, top: box.top}};
}
"""

UNPIN_ELEMENT = """
(argument) => {
  const element = document.querySelector(argument.selector);
  const style = element.style;
  Object.keys(argument.saved).forEach(name => {
    const value = argument.saved[name];
    if (value === '') { style.removeProperty(name); }
    else { style.setProperty(name, value); }
  });
}
"""

STANDALONE_PAGE = (
    "<!doctype html><html><head><meta charset=\"utf-8\"></head>"
    "<body style=\"margin:0;padding:0;background:#ffffff\"></body></html>"
)


def check_svg_pixels_equal_standalone(check, context):
    viewer = context.viewer
    key = f"jalandhar_{YEAR_365256363.replace('.', '')}"
    viewer.show(key, JALANDHAR, context.documents)
    file_text = (context.out / "cli" / "jalandhar.svg").read_text(encoding="utf-8")
    match = re.search(r'viewBox="0 0 (\d+) (\d+)"', file_text)
    view_width, view_height = int(match.group(1)), int(match.group(2))
    original_viewport = dict(context.viewport)
    results = {}
    try:
        for width in PIXEL_WIDTHS:
            height = round(width * view_height / view_width)
            viewport = {"width": width + 120, "height": height + 120}
            viewer.page.set_viewport_size(viewport)
            argument = {
                "selector": "#chart svg",
                "width": width,
                "properties": list(PINNED_PROPERTIES),
            }
            pinned = viewer.page.evaluate(PIN_ELEMENT, argument)
            viewer.page.wait_for_timeout(120)
            inserted_path = context.out / "screenshots" / f"inserted_{width}.png"
            viewer.page.locator("#chart svg").screenshot(path=str(inserted_path))
            viewer.page.evaluate(
                UNPIN_ELEMENT, {"selector": "#chart svg", "saved": pinned["saved"]}
            )

            scratch = context.scratch_page()
            scratch.set_viewport_size(viewport)
            scratch.set_content(STANDALONE_PAGE)
            scratch.evaluate(
                "(text) => { const parsedDocument = new DOMParser()"
                ".parseFromString(text, 'image/svg+xml');"
                " document.body.appendChild(document.adoptNode(parsedDocument.documentElement)); }",
                file_text,
            )
            standalone_pinned = scratch.evaluate(
                PIN_ELEMENT,
                {
                    "selector": "svg",
                    "width": width,
                    "properties": list(PINNED_PROPERTIES),
                },
            )
            scratch.wait_for_timeout(120)
            standalone_path = context.out / "screenshots" / f"standalone_{width}.png"
            scratch.locator("svg").screenshot(path=str(standalone_path))
            scratch.close()

            covered_rows = int(
                min(pinned["box"]["height"], standalone_pinned["box"]["height"])
            )
            comparison = compare_pngs(inserted_path, standalone_path, rows=covered_rows)
            comparison["width"] = width
            comparison["aspect_height"] = height
            comparison["note"] = (
                "every fully covered pixel row is compared; a fractional element "
                "height makes the screenshot clip round up, and that last partial "
                "row shows what lies behind the element rather than the chart"
            )
            comparison["boxes"] = {
                "inserted": pinned["box"],
                "standalone": standalone_pinned["box"],
            }
            check.equals(
                f"box at {width} px",
                pinned["box"],
                standalone_pinned["box"],
            )
            results[str(width)] = comparison
            check.require(
                comparison.get("differing_pixels") == 0,
                f"at {width} px the inserted chart and the standalone file differ in "
                f"{comparison.get('differing_pixels')} pixels "
                f"(sizes {comparison.get('size')})",
            )
    finally:
        viewer.page.set_viewport_size(original_viewport)
    check.note("comparisons", results)
    context.measurements["pixel_comparisons"] = results


def check_table_text_equal_cli(check, context):
    viewer = context.viewer
    cases = [("jalandhar", JALANDHAR)]
    if context.jammu_available:
        cases.append(("jammu", JAMMU))
    summary = {}
    for label, birth in cases:
        key = f"{label}_{YEAR_365256363.replace('.', '')}"
        document = viewer.show(key, birth, context.documents)["document"]
        zone = document["timeline"]["zone"]
        viewer.page.click("#expand-all")
        viewer.page.wait_for_function(
            "() => document.querySelectorAll('#dasha-body tr').length === 819", timeout=60000
        )
        rendered = page_table(viewer)
        text = context.cli.dasha(
            birth["date"], birth["time"], birth["place_label"], zone
        )
        (context.out / "cli" / f"{key}_md_ad_pd.txt").write_text(text, encoding="utf-8")
        table = parse_cli_table(text)
        context.cli_tables[key] = table
        entry = {
            "zone": zone,
            "cli_rows": len(table["rows"]),
            "page_rows": len(rendered),
            "cli_header_lines": table["header_lines"],
        }
        summary[key] = entry
        check.equals(f"{key} CLI row count", len(table["rows"]), 819)
        check.equals(f"{key} rendered row count", len(rendered), 819)
        if len(table["rows"]) == len(rendered):
            mismatches = [
                {"index": index, "cli": cli_row, "page": page_row}
                for index, (cli_row, page_row) in enumerate(zip(table["rows"], rendered))
                if cli_row != page_row
            ]
            entry["mismatched_rows"] = len(mismatches)
            entry["first_mismatches"] = mismatches[:3]
            check.equals(f"{key} mismatched rows", len(mismatches), 0)
        else:
            check.fail(f"{key}: row counts differ, rows not compared")
        # Leave the table as it was found.
        viewer.page.click("#collapse-all")
        viewer.page.wait_for_function(
            "() => document.querySelectorAll('#dasha-body tr').length === 9", timeout=60000
        )

    # Section 14.4: the MD/AD rows of Jalandhar against the committed golden.
    # Only the rows are compared; both header lines are recorded, because the
    # golden was produced on another machine and the Moon longitude can differ
    # there in the last float digits.
    golden_path = context.repo_root / "tests" / "fixtures" / "dasha" / (
        "jalandhar_md_ad_365256363_second_kolkata.txt"
    )
    golden = parse_cli_table(golden_path.read_text(encoding="utf-8"))
    key = f"jalandhar_{YEAR_365256363.replace('.', '')}"
    viewer.show(key, JALANDHAR, context.documents)
    viewer.page.click("#expand-all")
    viewer.page.wait_for_function(
        "() => document.querySelectorAll('#dasha-body tr').length === 819", timeout=60000
    )
    rendered_md_ad = [row for row in page_table(viewer) if row[0] in ("MD", "AD")]
    viewer.page.click("#collapse-all")
    local_md_ad_text = context.cli.dasha(
        JALANDHAR["date"],
        JALANDHAR["time"],
        JALANDHAR["place_label"],
        "Asia/Kolkata",
        depth="md-ad",
    )
    (context.out / "cli" / "jalandhar_365256363_md_ad.txt").write_text(
        local_md_ad_text, encoding="utf-8"
    )
    local_md_ad = parse_cli_table(local_md_ad_text)
    check.note(
        "golden",
        {
            "path": str(golden_path),
            "golden_header_line": golden["header_lines"][0] if golden["header_lines"] else None,
            "local_header_line": (
                local_md_ad["header_lines"][0] if local_md_ad["header_lines"] else None
            ),
            "golden_header_lines": golden["header_lines"],
            "local_header_lines": local_md_ad["header_lines"],
            "note": (
                "header lines are recorded, not asserted: the committed golden was "
                "produced on another machine and the Moon longitude can differ in the "
                "last float digits"
            ),
            "golden_rows": len(golden["rows"]),
            "page_md_ad_rows": len(rendered_md_ad),
        },
    )
    check.equals("golden row count", len(golden["rows"]), len(rendered_md_ad))
    if len(golden["rows"]) == len(rendered_md_ad):
        mismatches = [
            {"index": index, "golden": golden_row, "page": page_row}
            for index, (golden_row, page_row) in enumerate(zip(golden["rows"], rendered_md_ad))
            if golden_row != page_row
        ]
        check.note("golden_mismatched_rows", len(mismatches))
        check.note("golden_first_mismatches", mismatches[:3])
        check.equals("golden mismatched rows", len(mismatches), 0)
    check.note("cases", summary)


def check_expand_levels(check, context):
    viewer = context.viewer
    key = f"jalandhar_{YEAR_365256363.replace('.', '')}"
    viewer.show(key, JALANDHAR, context.documents)
    counts = {"initial": viewer.row_count()}
    check.equals("initial rows", counts["initial"], 9)
    viewer.page.click("#row-ju .v-cell-level")
    counts["after_ju"] = viewer.row_count()
    check.equals("after expanding Ju", counts["after_ju"], 18)
    viewer.page.click("#row-ju-su .v-cell-level")
    counts["after_ju_su"] = viewer.row_count()
    check.equals("after expanding Ju-Su", counts["after_ju_su"], 27)
    viewer.page.click("#expand-all")
    viewer.page.wait_for_function(
        "() => document.querySelectorAll('#dasha-body tr').length === 819", timeout=60000
    )
    counts["expand_all"] = viewer.row_count()
    check.equals("after Expand all", counts["expand_all"], 819)
    viewer.page.click("#collapse-all")
    counts["collapse_all"] = viewer.row_count()
    check.equals("after Collapse all", counts["collapse_all"], 9)
    levels = [row["level"] for row in viewer.rows()]
    check.equals("levels after Collapse all", set(levels), {"1"})
    check.note("counts", counts)


def check_expand_birth_chain_focus_pd(check, context):
    viewer = context.viewer
    results = {}
    targets = [("jalandhar", JALANDHAR)]
    if context.jammu_available:
        targets.append(("jammu", JAMMU))
    for label, birth in targets:
        key = f"{label}_{YEAR_365256363.replace('.', '')}"
        document = viewer.show(key, birth, context.documents)["document"]
        viewer.page.click("#collapse-all")
        viewer.page.click("#expand-birth")
        nominal = [chain_of(document, entry) for entry in document["birth_chain"]["nominal"]]
        expected_id = row_id(nominal[2])
        active = viewer.active()
        results[label] = {
            "nominal_chain": nominal,
            "expected_focus": expected_id,
            "active_element": active,
            "visible_rows": viewer.row_count(),
        }
        check.equals(f"{label} focused row id", active["id"], expected_id)
        check.equals(f"{label} focused row tabindex", viewer.page.evaluate(
            "(id) => document.getElementById(id).getAttribute('tabindex')", expected_id
        ), "0")
    check.note("targets", results)


def check_birth_markers(check, context):
    viewer = context.viewer
    results = {}
    targets = [("jalandhar", JALANDHAR)]
    if context.jammu_available:
        targets.append(("jammu", JAMMU))
    for label, birth in targets:
        key = f"{label}_{YEAR_365256363.replace('.', '')}"
        document = viewer.show(key, birth, context.documents)["document"]
        viewer.page.click("#collapse-all")
        viewer.page.click("#expand-birth")
        nominal = [chain_of(document, entry) for entry in document["birth_chain"]["nominal"]]
        quantized = [chain_of(document, entry) for entry in document["birth_chain"]["quantized"]]
        markers = viewer.marker_rows()
        chains = viewer.details("#birth-chain-details")
        expected = EXPECTED_PLACES[birth["place_label"]]["birth_chain"]
        entry = {
            "nominal": nominal,
            "quantized": quantized,
            "identical": document["birth_chain"]["identical"],
            "marker_rows": markers,
            "birth_chain_panel": chains,
            "divergence_note_hidden": viewer.hidden("#divergence-note"),
        }
        results[label] = entry
        check.equals(f"{label} nominal chain", nominal, expected)
        check.equals(f"{label} quantized chain", quantized, expected)
        check.equals(f"{label} identical", document["birth_chain"]["identical"], True)
        check.equals(f"{label} N rows", markers["nominal"], [row_id(chain) for chain in nominal])
        check.equals(f"{label} Q rows", markers["quantized"], [row_id(chain) for chain in quantized])
        check.equals(
            f"{label} birth chain panel",
            chains,
            {"Nominal": " › ".join(expected), "Quantized": " › ".join(expected)},
        )
        check.require(
            viewer.hidden("#divergence-note") is True,
            f"{label}: the divergence note is shown for identical chains",
        )
        shading = viewer.page.evaluate(
            "(ids) => ids.map(id => document.getElementById(id).className)",
            [row_id(chain) for chain in nominal],
        )
        entry["row_classes"] = shading
        for chain, classes in zip(nominal, shading):
            check.require(
                "v-birth-nominal" in classes and "v-birth-quantized" in classes,
                f"{label}: row {chain} lacks the birth shading classes: {classes!r}",
            )
    check.note("targets", results)


def check_keyboard_model(check, context):
    viewer = context.viewer
    page = viewer.page
    key = f"jalandhar_{YEAR_365256363.replace('.', '')}"
    viewer.show(key, JALANDHAR, context.documents)
    page.click("#collapse-all")
    steps = {}

    # Tab into the table lands on the roving row (the one with tabindex="0").
    roving = page.evaluate(
        "() => { const row = document.querySelector('#dasha-body tr[tabindex=\"0\"]');"
        " return row ? row.id : null; }"
    )
    page.focus("#microseconds")
    page.keyboard.press("Tab")
    steps["tab_into_table"] = {"roving": roving, "active": viewer.active_id()}
    check.equals("Tab lands on the roving row", viewer.active_id(), roving)
    check.equals("the roving row after Collapse all", roving, "row-ju")

    # ArrowRight expands, then moves to the first child.
    page.keyboard.press("ArrowRight")
    steps["arrow_right_expand"] = {
        "active": viewer.active_id(),
        "rows": viewer.row_count(),
        "expanded": page.evaluate("() => document.getElementById('row-ju').getAttribute('aria-expanded')"),
    }
    check.equals("ArrowRight keeps focus", viewer.active_id(), "row-ju")
    check.equals("ArrowRight expands", steps["arrow_right_expand"]["rows"], 18)
    check.equals("aria-expanded after ArrowRight", steps["arrow_right_expand"]["expanded"], "true")
    page.keyboard.press("ArrowRight")
    steps["arrow_right_child"] = viewer.active_id()
    check.equals("ArrowRight moves to the first child", viewer.active_id(), "row-ju-ju")

    # ArrowDown / ArrowUp across MD, AD and PD rows.
    page.keyboard.press("ArrowRight")  # expand row-ju-ju
    page.keyboard.press("ArrowRight")  # focus row-ju-ju-ju (a PD row)
    steps["arrow_right_pd"] = {"active": viewer.active_id(), "rows": viewer.row_count()}
    check.equals("ArrowRight reaches a PD row", viewer.active_id(), "row-ju-ju-ju")
    check.equals("rows with one AD expanded", viewer.row_count(), 27)
    page.keyboard.press("ArrowDown")
    steps["arrow_down_pd"] = viewer.active_id()
    check.equals("ArrowDown on a PD row", viewer.active_id(), "row-ju-ju-sa")
    page.keyboard.press("ArrowUp")
    check.equals("ArrowUp on a PD row", viewer.active_id(), "row-ju-ju-ju")
    page.keyboard.press("ArrowRight")
    check.equals("ArrowRight on a PD row does nothing", viewer.active_id(), "row-ju-ju-ju")

    # ArrowLeft: to the parent from a leaf, then collapse, then to its parent.
    page.keyboard.press("ArrowLeft")
    check.equals("ArrowLeft from a PD row", viewer.active_id(), "row-ju-ju")
    page.keyboard.press("ArrowLeft")
    steps["arrow_left_collapse"] = {"active": viewer.active_id(), "rows": viewer.row_count()}
    check.equals("ArrowLeft collapses in place", viewer.active_id(), "row-ju-ju")
    check.equals("rows after collapsing the AD", viewer.row_count(), 18)
    page.keyboard.press("ArrowLeft")
    check.equals("ArrowLeft from a collapsed row", viewer.active_id(), "row-ju")

    # Enter toggles.
    page.keyboard.press("Enter")
    steps["enter_collapse"] = viewer.row_count()
    check.equals("Enter collapses", viewer.row_count(), 9)
    page.keyboard.press("Enter")
    steps["enter_expand"] = viewer.row_count()
    check.equals("Enter expands", viewer.row_count(), 18)

    # Home and End.
    page.keyboard.press("End")
    steps["end"] = viewer.active_id()
    last = page.evaluate("() => document.querySelector('#dasha-body tr:last-child').id")
    check.equals("End", viewer.active_id(), last)
    page.keyboard.press("Home")
    steps["home"] = viewer.active_id()
    check.equals("Home", viewer.active_id(), "row-ju")

    # Focus restoration: collapse an ancestor of the focused row.
    page.keyboard.press("ArrowRight")  # row-ju is collapsed? it is expanded; focus child
    if page.evaluate("() => document.getElementById('row-ju').getAttribute('aria-expanded')") == "false":
        page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")  # expand row-ju-ju
    page.keyboard.press("ArrowRight")  # focus row-ju-ju-ju
    steps["before_ancestor_collapse"] = viewer.active_id()
    page.click("#row-ju .v-cell-level")
    steps["after_ancestor_collapse"] = {"active": viewer.active_id(), "rows": viewer.row_count()}
    check.equals("collapsing an ancestor restores focus to it", viewer.active_id(), "row-ju")
    check.equals("rows after collapsing the ancestor", viewer.row_count(), 9)

    # Focus restoration on Collapse all.
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    steps["before_collapse_all"] = viewer.active_id()
    check.equals("focus before Collapse all", viewer.active_id(), "row-ju-ju-ju")
    page.click("#collapse-all")
    steps["after_collapse_all"] = {"active": viewer.active_id(), "rows": viewer.row_count()}
    check.equals("Collapse all restores focus to the Mahadasha", viewer.active_id(), "row-ju")
    check.equals("rows after Collapse all", viewer.row_count(), 9)
    check.require(
        (viewer.active() or {}).get("tag") == "TR",
        f"focus is not on a row after Collapse all: {viewer.active()!r}",
    )
    check.note("steps", steps)


def find_nodes(node, role, found=None):
    if found is None:
        found = []
    if isinstance(node, dict):
        if node.get("role") == role:
            found.append(node)
        for child in node.get("children", []) or []:
            find_nodes(child, role, found)
    return found


def platform_expanded_rows(page):
    """The row `expanded` property as the platform tree carries it, true or false.

    Playwright's own snapshot omits a false `expanded`, so the collapsed state is
    read from Chromium's full accessibility tree through CDP, the way
    ``tools/render/rasterise_inspection.py`` reads image names.
    """
    counts = {"true": 0, "false": 0, "absent": 0}
    try:
        session = page.context.new_cdp_session(page)
        session.send("Accessibility.enable")
        nodes = session.send("Accessibility.getFullAXTree")["nodes"]
        session.detach()
    except Exception as error:  # noqa: BLE001 -- tooling, not a contract
        return {"unavailable": f"{type(error).__name__}: {error}"}
    for node in nodes:
        if node.get("role", {}).get("value") != "row":
            continue
        states = {
            entry.get("name"): entry.get("value", {}).get("value")
            for entry in node.get("properties", []) or []
        }
        if "expanded" not in states:
            counts["absent"] += 1
        elif states["expanded"] is True:
            counts["true"] += 1
        elif states["expanded"] is False:
            counts["false"] += 1
    return counts


def check_accessibility_tree(check, context):
    viewer = context.viewer
    page = viewer.page
    key = f"jalandhar_{YEAR_365256363.replace('.', '')}"
    viewer.show(key, JALANDHAR, context.documents)
    page.click("#collapse-all")
    page.click("#expand-birth")

    # Layer 15 section 12 narrows D16's prohibition: no treegrid row may carry
    # `aria-controls`, and the combobox -- whose listbox element is always in the
    # document -- carries exactly one.
    check.equals(
        "aria-controls attributes in the DOM",
        page.evaluate("() => document.querySelectorAll('[aria-controls]').length"),
        1,
    )
    check.equals(
        "aria-controls on the combobox",
        page.evaluate(
            "() => { const node = document.querySelector('[aria-controls]');"
            " return [node.id, node.getAttribute('role'),"
            " node.getAttribute('aria-controls')]; }"
        ),
        ["birth-place", "combobox", "place-listbox"],
    )
    check.equals(
        "aria-controls on a treegrid row",
        page.evaluate(
            "() => document.querySelectorAll('#dasha-body tr[aria-controls]').length"
        ),
        0,
    )

    snapshot = None
    source = None
    accessibility = getattr(page, "accessibility", None)
    if accessibility is not None and hasattr(accessibility, "snapshot"):
        try:
            snapshot = accessibility.snapshot(interesting_only=False)
            source = "page.accessibility.snapshot()"
        except Exception as error:  # noqa: BLE001 -- fall back as the specification allows
            check.note("accessibility_snapshot_error", f"{type(error).__name__}: {error}")
    check.note("snapshot_source", source or "page.locator('body').aria_snapshot()")
    if snapshot is not None:
        (context.out / "accessibility_snapshot.json").write_text(
            json.dumps(snapshot, indent=1, ensure_ascii=False), encoding="utf-8"
        )
        treegrids = find_nodes(snapshot, "treegrid")
        check.equals("treegrid nodes", len(treegrids), 1)
        if treegrids:
            check.equals("treegrid name", treegrids[0].get("name"), "Vimshottari dasha")
            rows = find_nodes(treegrids[0], "row")
            levels = sorted({row.get("level") for row in rows if row.get("level") is not None})
            expanded_names = sorted(
                row.get("name") for row in rows if row.get("expanded") is True
            )
            # Playwright's snapshot carries `expanded` only when it is true, so
            # the collapsed state is read from the platform tree itself below.
            dom_states = page.evaluate(
                "() => { const out = {expanded: [], collapsed: [], leaves: 0};"
                " document.querySelectorAll('#dasha-body tr').forEach(tr => {"
                "   const state = tr.getAttribute('aria-expanded');"
                "   if (state === 'true') out.expanded.push(tr.getAttribute('aria-label'));"
                "   else if (state === 'false') out.collapsed.push(tr.id);"
                "   else out.leaves += 1; });"
                " return out; }"
            )
            platform = platform_expanded_rows(page)
            check.note(
                "treegrid",
                {
                    "rows": len(rows),
                    "levels": levels,
                    "snapshot_expanded_rows": expanded_names,
                    "dom_expanded_rows": len(dom_states["expanded"]),
                    "dom_collapsed_rows": len(dom_states["collapsed"]),
                    "dom_leaf_rows": dom_states["leaves"],
                    "platform_expanded_counts": platform,
                    "first_rows": [
                        {
                            "name": row.get("name"),
                            "level": row.get("level"),
                            "expanded": row.get("expanded"),
                        }
                        for row in rows[:4]
                    ],
                },
            )
            check.require(len(rows) >= 27, f"the treegrid exposes only {len(rows)} rows")
            check.require(
                levels in ([1, 2, 3], [2, 3, 4]),
                f"the exposed row levels are {levels}, not the three treegrid levels",
            )
            check.equals(
                "rows exposed as expanded",
                expanded_names,
                sorted(dom_states["expanded"]),
            )
            check.require(
                dom_states["collapsed"] and platform.get("false", 0) >= len(dom_states["collapsed"]) - 1,
                "the platform tree does not expose the collapsed rows as collapsed: "
                f"{platform} for {len(dom_states['collapsed'])} collapsed rows",
            )
            check.require(
                platform.get("true", 0) >= 1,
                f"the platform tree exposes no expanded row: {platform}",
            )
        images = find_nodes(snapshot, "image") + find_nodes(snapshot, "img")
        chart = [
            image
            for image in images
            if image.get("name") == "D1 chart (North Indian)"
        ]
        check.note(
            "image",
            [{"name": image.get("name"), "description": (image.get("description") or "")[:80]}
             for image in images],
        )
        check.require(len(chart) == 1, f"the chart image is not in the accessibility tree: {brief(images)}")
        if chart:
            check.require(
                (chart[0].get("description") or "").startswith("Lagna in rashi"),
                f"the chart image has no description: {brief(chart[0].get('description'))}",
            )
        status = find_nodes(snapshot, "status")
        check.note("status_nodes", [node.get("name") for node in status])
        check.require(bool(status), "no status region in the accessibility tree")
    else:
        aria = page.locator("body").aria_snapshot()
        (context.out / "aria_snapshot.txt").write_text(aria, encoding="utf-8")
        check.require("treegrid" in aria, "no treegrid in the aria snapshot")
        check.require("[level=" in aria or "level=" in aria, "no row levels in the aria snapshot")
        check.require("[expanded]" in aria, "no expanded row in the aria snapshot")
        check.require("img" in aria, "no image in the aria snapshot")
        check.require("status" in aria, "no status region in the aria snapshot")

    # The alert region is only in the tree while it carries an error. The page
    # cannot type an unknown identifier -- a selection always comes from the
    # list -- so the four submitted strings are written straight into the
    # controls, which is exactly the body a stale tab could still send.
    viewer.set_form(
        {
            "date": JALANDHAR["date"],
            "time": JALANDHAR["time"],
            "place_text": "Nowhere, Nowhere",
            "place_id": "999999999",
        }
    )
    page.evaluate(MARK_OLD_RESULTS)
    with page.expect_response(
        lambda response: response.url == viewer.api_url, timeout=120000
    ) as caught:
        page.click("#generate")
    status_code = caught.value.status
    page.wait_for_selector("#alert:not([hidden])", timeout=30000)
    viewer.shown = None
    check.equals("not-found status", status_code, 404)
    alert_snapshot = None
    if accessibility is not None and hasattr(accessibility, "snapshot"):
        try:
            alert_snapshot = accessibility.snapshot(interesting_only=False)
        except Exception:  # noqa: BLE001
            alert_snapshot = None
    if alert_snapshot is not None:
        alerts = find_nodes(alert_snapshot, "alert")
        check.note("alert_nodes", [(node.get("name") or "")[:120] for node in alerts])
        check.require(bool(alerts), "no alert region in the accessibility tree while an error is shown")
    else:
        aria = page.locator("#alert").aria_snapshot()
        check.note("alert_aria_snapshot", aria[:400])
        check.require("alert" in aria, "no alert role in the aria snapshot")


def check_divergence_chains(check, context):
    fixtures = {
        "divergence_su_mo": {
            "nominal": ["Su", "Su-Ve", "Su-Ve-Ke"],
            "quantized": ["Mo", "Mo-Mo", "Mo-Mo-Mo"],
        },
        "divergence_ke": {
            "nominal": ["Ke", "Ke-Su", "Ke-Su-Ve"],
            "quantized": ["Ke", "Ke-Mo", "Ke-Mo-Mo"],
        },
    }
    results = {}
    page = context.new_viewer_page(hash_fragment="#acceptance")
    try:
        seam = page.evaluate("() => typeof window.__loadFixture")
        check.equals("the #acceptance seam", seam, "function")
        for name, expected in fixtures.items():
            path = context.repo_root / "tests" / "fixtures" / "viewer" / f"{name}.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            loaded = page.evaluate("(doc) => window.__loadFixture(doc)", document)
            page.wait_for_selector("#dasha-body tr", timeout=30000)
            nominal = [chain_of(document, entry) for entry in document["birth_chain"]["nominal"]]
            quantized = [chain_of(document, entry) for entry in document["birth_chain"]["quantized"]]
            chains = page.evaluate(
                "() => { const list = document.querySelector('#birth-chain-details');"
                " const keys = list.querySelectorAll('.v-detail-key');"
                " const values = list.querySelectorAll('.v-detail-value');"
                " const out = {};"
                " for (let index = 0; index < keys.length; index++) {"
                "   out[keys[index].textContent] = values[index].textContent; }"
                " return out; }"
            )
            note_hidden = page.evaluate(
                "() => document.querySelector('#divergence-note').hidden"
            )
            note_text = page.evaluate(
                "() => document.querySelector('#divergence-note').textContent"
            )
            page.click("#expand-birth")
            markers = page.evaluate(
                "() => { const out = {nominal: [], quantized: []};"
                " document.querySelectorAll('#dasha-body tr').forEach(tr => {"
                "   if (tr.children[4].textContent === 'N') out.nominal.push(tr.id);"
                "   if (tr.children[5].textContent === 'Q') out.quantized.push(tr.id); });"
                " return out; }"
            )
            active = page.evaluate(
                "() => document.activeElement ? document.activeElement.id : null"
            )
            entry = {
                "loaded": loaded,
                "identical": document["birth_chain"]["identical"],
                "nominal": nominal,
                "quantized": quantized,
                "panel": chains,
                "note_hidden": note_hidden,
                "note_text": note_text,
                "marker_rows": markers,
                "focus_after_expand_birth": active,
                "visible_rows": page.evaluate(
                    "() => document.querySelectorAll('#dasha-body tr').length"
                ),
            }
            results[name] = entry
            check.equals(f"{name} identical", document["birth_chain"]["identical"], False)
            check.equals(f"{name} nominal chain", nominal, expected["nominal"])
            check.equals(f"{name} quantized chain", quantized, expected["quantized"])
            check.equals(
                f"{name} birth chain panel",
                chains,
                {
                    "Nominal": " › ".join(expected["nominal"]),
                    "Quantized": " › ".join(expected["quantized"]),
                },
            )
            check.require(note_hidden is False, f"{name}: the divergence note is hidden")
            check.equals(f"{name} note text", note_text, DIVERGENCE_NOTE)
            check.equals(
                f"{name} N rows",
                markers["nominal"],
                [row_id(chain) for chain in nominal],
            )
            check.equals(
                f"{name} Q rows",
                markers["quantized"],
                [row_id(chain) for chain in quantized],
            )
            check.require(
                markers["nominal"] != markers["quantized"],
                f"{name}: N and Q mark the same rows",
            )
            check.require(
                markers["nominal"][2] != markers["quantized"][2],
                f"{name}: the two chains share their Pratyantardasha row",
            )
            check.equals(f"{name} focus after Expand birth chain", active, row_id(nominal[2]))
        context.violations.extend(page.evaluate("() => window.__acceptanceViolations || []"))
    finally:
        page.close()
    check.note("fixtures", results)


def check_superseded_response(check, context):
    """Layer 14 section 10.2 over the /2 request.

    The two submissions differ in their date rather than their place, so the
    check needs no second geodata record and runs the same way against the
    fixture database and the production one.
    """
    viewer = context.viewer
    page = viewer.page
    first = {"date": "1995-03-21", "time": "06:45", "place_text": "", "place_id": ""}
    second = {"date": "1995-03-22", "time": "06:45", "place_text": "", "place_id": ""}
    third = {"date": "1995-03-23", "time": "06:45", "place_text": "", "place_id": ""}

    mark = context.viewer_process.mark()
    responses = []
    handler = lambda response: (  # noqa: E731 -- a listener, deliberately tiny
        responses.append((round(time.monotonic(), 4), response))
        if response.url == viewer.api_url
        else None
    )
    page.on("response", handler)
    try:
        # Pair: the first date, then immediately the second.
        page.evaluate(MARK_OLD_RESULTS)
        page.evaluate(SET_FORM_AND_SUBMIT, first)
        in_flight = page.evaluate("() => !document.getElementById('cancel').hidden")
        page.evaluate(SET_FORM_AND_SUBMIT, second)
        status_text = viewer.text("#status")
        page.wait_for_function(
            "() => { const line = document.getElementById('submitted-line');"
            " return line && line.textContent.indexOf('1995-03-22') !== -1; }",
            timeout=120000,
        )
        page.wait_for_timeout(1500)
        pair = {
            "first_request_still_in_flight_at_the_second_submit": in_flight,
            "status_after_second_submit": status_text,
            "submitted_line": viewer.text("#submitted-line"),
            "date_row": viewer.details("#birth-details").get("Date"),
            "first_row": page_table(viewer)[0],
        }
        check.require(
            "1995-03-22" in (pair["date_row"] or ""),
            f"the birth details are not the second submission's: {pair['date_row']!r}",
        )
        check.require(
            "1995-03-22" in pair["submitted_line"],
            f"the results header is not the second submission's: {pair['submitted_line']!r}",
        )
        check.require(in_flight, "the first request was not in flight at the second submit")
        check.equals(
            "status while superseding",
            status_text,
            "Calculating… (previous request replaced)",
        )
        check.note("pair", pair)

        # Burst of three.
        burst_responses_before = len(responses)
        page.evaluate(MARK_OLD_RESULTS)
        page.evaluate(SET_FORM_AND_SUBMIT, first)
        page.evaluate(SET_FORM_AND_SUBMIT, second)
        page.evaluate(SET_FORM_AND_SUBMIT, third)
        page.wait_for_function(
            "() => { const line = document.getElementById('submitted-line');"
            " return line && line.textContent.indexOf('1995-03-23') !== -1; }",
            timeout=180000,
        )
        page.wait_for_timeout(2500)
        burst = {
            "submitted_line": viewer.text("#submitted-line"),
            "caption": viewer.text("#table-caption"),
            "date_row": viewer.details("#birth-details").get("Date"),
            "rows": viewer.row_count(),
        }
        check.require(
            "1995-03-23" in (burst["date_row"] or ""),
            f"the third submission's date is not shown: {burst['date_row']!r}",
        )
        check.require(
            YEAR_DISPLAY in (burst["caption"] or ""),
            f"the caption does not carry the year convention: {brief(burst['caption'])}",
        )
        check.equals("rows after the burst", burst["rows"], 9)
        check.note("burst", burst)
    finally:
        page.remove_listener("response", handler)
    viewer.shown = None

    # Information only (section 2.1): the order in which work completed.
    observed = []
    for when, response in responses:
        entry = {"at": round(when, 4), "status": response.status}
        try:
            posted = response.request.post_data
            entry["submitted"] = json.loads(posted) if posted else None
        except Exception as error:  # noqa: BLE001
            entry["submitted"] = f"unavailable: {type(error).__name__}"
        observed.append(entry)
    server_lines = context.viewer_process.stderr_since(mark)
    check.note(
        "completion_order",
        {
            "note": (
                "recorded, never asserted: the engine lock guarantees exclusion, "
                "not order (specification 2.1 and 10.2)"
            ),
            "browser_side_responses": observed,
            "server_stderr_lines": server_lines,
            "burst_responses_seen": len(responses) - burst_responses_before,
        },
    )
    context.measurements["completion_order"] = {
        "browser_side_responses": observed,
        "server_stderr_lines": server_lines,
    }


def check_errors(check, context):
    """The error paths of Layer 14 section 10.1 as Layer 15 section 8 amends them.

    Ambiguity is gone with name resolution itself (Layer 15 section 7.3): a
    request names a record, and a record is either in this database or not.
    """
    viewer = context.viewer
    page = viewer.page
    results = {}

    # A known-good result to keep underneath every error.
    key = f"jalandhar_{YEAR_365256363.replace('.', '')}"
    viewer.show(key, JALANDHAR, context.documents)
    kept = page_table(viewer)[0]

    # An identifier this database does not have. The interface cannot type one,
    # so the four strings are written straight into the controls.
    viewer.set_form(
        {
            "date": JALANDHAR["date"],
            "time": JALANDHAR["time"],
            "place_text": "Nowhere, Nowhere",
            "place_id": "999999999",
        }
    )
    page.evaluate(MARK_OLD_RESULTS)
    with page.expect_response(
        lambda response: response.url == viewer.api_url, timeout=120000
    ) as caught:
        page.click("#generate")
    answered = caught.value
    page.wait_for_selector("#alert:not([hidden])", timeout=30000)
    body = json.loads(answered.body().decode("utf-8"))
    alert = page.evaluate(
        "() => { const box = document.getElementById('alert');"
        " return {hidden: box.hidden, title: box.querySelector('.v-alert-title').textContent,"
        " message: box.querySelector('.v-alert-message').textContent,"
        " controls: box.querySelectorAll('button, input, select, a, [role=\"button\"]').length}; }"
    )
    results["unknown_identifier"] = {
        "status": answered.status,
        "kind": body["error"]["kind"],
        "message": body["error"]["message"][:200],
        "alert": alert,
        "focus": viewer.active_id(),
        "previous_result_kept": page_table(viewer)[0] == kept,
    }
    check.equals("unknown identifier status", answered.status, 404)
    check.equals("unknown identifier kind", body["error"]["kind"], "place_not_found")
    check.equals("focus after a not-found", viewer.active_id(), "birth-place")
    check.equals("no selection control in the alert", alert["controls"], 0)
    check.require(
        page_table(viewer)[0] == kept, "the previous result changed on a not-found error"
    )
    viewer.shown = None

    # A typed birthplace with no selection: blocked in the browser, and refused
    # independently by the server for the very same body (Layer 15 section 2
    # rule 3). The direct request is what proves the second half.
    viewer.set_form(
        {
            "date": JALANDHAR["date"],
            "time": JALANDHAR["time"],
            "place_text": "Jalandh",
            "place_id": "",
        }
    )
    sent = None
    try:
        with page.expect_response(
            lambda response: response.url == viewer.api_url, timeout=4000
        ) as caught:
            page.click("#generate")
        sent = caught.value
    except Exception:  # noqa: BLE001 -- no request at all is the blocked case
        sent = None
    direct = viewer.api(
        "/api/chart",
        {
            "date": JALANDHAR["date"],
            "time": JALANDHAR["time"],
            "place_text": "Jalandh",
            "place_id": "",
        },
    )
    results["place_selection_required"] = {
        "request_sent_by_the_page": sent is not None,
        "status_line": viewer.text("#status"),
        "field_message": viewer.text("#birth-place-message"),
        "focus": viewer.active_id(),
        "direct_status": direct["status"],
        "direct_kind": direct["document"]["error"]["kind"],
        "direct_message": direct["document"]["error"]["message"][:200],
    }
    check.require(sent is None, "the page sent a request for a birthplace with no selection")
    check.equals("blocked status line", viewer.text("#status"), "Nothing sent: the form is incomplete.")
    check.equals("prompt shown", viewer.text("#birth-place-message"), SELECTION_PROMPT)
    check.equals("focus after the prompt", viewer.active_id(), "birth-place")
    check.equals("direct status", direct["status"], 400)
    check.equals("direct kind", direct["document"]["error"]["kind"], "place_selection_required")

    # An impossible but well-formed date: the browser has no calendar knowledge,
    # so the request goes out and the server refuses it.
    accepted = viewer.set_form(
        {
            "date": "1995-02-30",
            "time": JALANDHAR["time"],
            "place_text": "",
            "place_id": "",
        }
    )
    entry = {"values_the_browser_kept": accepted}
    answered = None
    try:
        with page.expect_response(
            lambda response: response.url == viewer.api_url, timeout=20000
        ) as caught:
            page.click("#generate")
        answered = caught.value
    except Exception:  # noqa: BLE001
        answered = None
    if answered is not None:
        page.wait_for_selector("#alert:not([hidden])", timeout=30000)
        body = json.loads(answered.body().decode("utf-8"))
        entry.update(
            {
                "status": answered.status,
                "kind": body.get("error", {}).get("kind"),
                "message": body.get("error", {}).get("message", "")[:200],
                "focus": viewer.active(),
            }
        )
        check.equals("impossible date refused with 400", answered.status, 400)
        check.equals("impossible date kind", entry["kind"], "input")
        check.equals("impossible date focused field", (entry["focus"] or {}).get("id"), "birth-date")
    else:
        entry["focus"] = viewer.active()
        entry["status_line"] = viewer.text("#status")
        check.equals(
            "impossible date focused field", (entry["focus"] or {}).get("id"), "birth-date"
        )
        check.equals(
            "impossible date status line",
            entry["status_line"],
            "Nothing sent: the form is incomplete.",
        )
    results["date_1995_02_30"] = entry
    viewer.shown = None

    # A stale /1 body. The page cannot compose one -- that is the point of the
    # kind -- so the server is asked directly, and the very document it answers
    # with is then handed to the page through one intercepted response, which is
    # how the page's own rendering of `stale_schema` is exercised.
    stale = viewer.api(
        "/api/chart",
        {
            "date": JALANDHAR["date"],
            "time": JALANDHAR["time"],
            "place_query": JALANDHAR["place_label"],
            "year_convention": YEAR_365256363,
        },
    )
    check.equals("stale /1 body status", stale["status"], 400)
    check.equals("stale /1 body kind", stale["document"]["error"]["kind"], "stale_schema")

    viewer.show(key, JALANDHAR, context.documents)
    kept = page_table(viewer)[0]
    served = {"count": 0}

    def stale_route(route):
        served["count"] += 1
        route.fulfill(
            status=400,
            content_type="application/json; charset=utf-8",
            body=stale["text"],
        )

    page.route("**/api/chart", stale_route)
    try:
        viewer.set_form(
            {
                "date": JALANDHAR["date"],
                "time": JALANDHAR["time"],
                "place_text": "",
                "place_id": "",
            }
        )
        page.click("#generate")
        page.wait_for_selector("#alert:not([hidden])", timeout=30000)
        alert = page.evaluate(
            "() => { const box = document.getElementById('alert');"
            " return {title: box.querySelector('.v-alert-title').textContent,"
            " lines: Array.from(box.querySelectorAll('.v-alert-message'))"
            "   .map(node => node.textContent)}; }"
        )
    finally:
        page.unroute("**/api/chart", stale_route)
    results["stale_schema"] = {
        "direct_status": stale["status"],
        "direct_kind": stale["document"]["error"]["kind"],
        "direct_message": stale["document"]["error"]["message"][:200],
        "intercepted_responses": served["count"],
        "alert": alert,
        "focus": viewer.active_id(),
        "previous_result_kept": page_table(viewer)[0] == kept,
    }
    check.equals("stale_schema alert title", alert["title"], "This page is out of date")
    check.require(
        alert["lines"] and alert["lines"][0] == STALE_SCHEMA_SENTENCE,
        f"the alert does not carry the reload sentence: {brief(alert['lines'])}",
    )
    check.require(
        len(alert["lines"]) >= 2 and "eload" in alert["lines"][1],
        f"the alert carries no reload hint: {brief(alert['lines'])}",
    )
    check.require(
        page_table(viewer)[0] == kept, "the previous result changed on a stale-schema error"
    )
    viewer.shown = None
    check.note("cases", results)


def check_microseconds_toggle(check, context):
    viewer = context.viewer
    key = f"jalandhar_{YEAR_365256363.replace('.', '')}"
    document = viewer.show(key, JALANDHAR, context.documents)["document"]
    first = document["rows"][0]
    before = viewer.rows()[0]
    viewer.page.check("#microseconds")
    during = viewer.rows()[0]
    viewer.page.uncheck("#microseconds")
    after = viewer.rows()[0]
    check.note(
        "first_row",
        {
            "seconds": [before["cells"][2], before["cells"][3]],
            "microseconds": [during["cells"][2], during["cells"][3]],
            "restored": [after["cells"][2], after["cells"][3]],
            "transport_local_seconds": [first["start"]["local_seconds"], first["end"]["local_seconds"]],
            "transport_local": [first["start"]["local"], first["end"]["local"]],
            "label_with_microseconds": during["label"],
        },
    )
    check.equals("start, seconds", before["cells"][2], first["start"]["local_seconds"])
    check.equals("end, seconds", before["cells"][3], first["end"]["local_seconds"])
    check.equals("start, microseconds", during["cells"][2], first["start"]["local"])
    check.equals("end, microseconds", during["cells"][3], first["end"]["local"])
    check.equals("start, restored", after["cells"][2], first["start"]["local_seconds"])
    check.require(
        first["start"]["local"] in (during["label"] or ""),
        "the row's accessible name was not refreshed with the microsecond text",
    )


def check_stale_inputs_banner(check, context):
    """Layer 14 section 10.3 over Layer 15's four submitted strings.

    Clearing the birthplace is an edit like any other, because the submission it
    would make is a different one -- the configured default rather than this
    record (Layer 15 section 3).
    """
    viewer = context.viewer
    page = viewer.page
    key = f"jalandhar_{YEAR_365256363.replace('.', '')}"
    document = viewer.show(key, JALANDHAR, context.documents)["document"]
    submitted = document["request"]["submitted"]
    expected_text = (
        "Inputs changed — the results below are for "
        f"{submitted['date']}, {submitted['time']}, {submitted['place_text']}. "
        "Press Generate to recalculate."
    )
    before = page_table(viewer)[0]

    page.fill("#birth-date", "1995-03-22")
    stale = {
        "data_stale": page.get_attribute("#results", "data-stale"),
        "hidden": viewer.hidden("#stale-banner"),
        "text": viewer.text("#stale-banner"),
        "first_row_unchanged": page_table(viewer)[0] == before,
    }
    check.equals("data-stale", stale["data_stale"], "true")
    check.require(stale["hidden"] is False, "the stale banner is hidden after an edit")
    check.equals("banner text", stale["text"], expected_text)
    check.require(stale["first_row_unchanged"], "editing a field changed a row")

    page.fill("#birth-date", submitted["date"])
    restored = {
        "data_stale": page.get_attribute("#results", "data-stale"),
        "hidden": viewer.hidden("#stale-banner"),
    }
    check.equals("data-stale after restoring", restored["data_stale"], None)
    check.require(restored["hidden"] is True, "the stale banner stays after restoring the value")

    # Clearing the birthplace: the identifier goes with the text (section 2
    # rule 4), so two of the four strings change at once.
    page.fill("#birth-place", "")
    cleared = {
        "data_stale": page.get_attribute("#results", "data-stale"),
        "hidden": viewer.hidden("#stale-banner"),
        "text": viewer.text("#stale-banner"),
        "place_id": page.input_value("#place-id"),
        "first_row_unchanged": page_table(viewer)[0] == before,
    }
    check.equals("data-stale after clearing the birthplace", cleared["data_stale"], "true")
    check.equals("banner text after clearing", cleared["text"], expected_text)
    check.equals("the identifier was cleared with the text", cleared["place_id"], "")
    check.require(cleared["first_row_unchanged"], "clearing the birthplace changed a row")

    # Choosing the same suggestion again restores both strings exactly.
    viewer.select_place(JALANDHAR["place_query"], JALANDHAR["place_label"])
    reselected = {
        "data_stale": page.get_attribute("#results", "data-stale"),
        "hidden": viewer.hidden("#stale-banner"),
        "place_id": page.input_value("#place-id"),
        "place_text": page.input_value("#birth-place"),
    }
    check.equals("data-stale after re-selecting", reselected["data_stale"], None)
    check.require(
        reselected["hidden"] is True,
        "the stale banner stays after the same suggestion is chosen again",
    )
    check.equals("place_id after re-selecting", reselected["place_id"], submitted["place_id"])
    check.equals("place_text after re-selecting", reselected["place_text"], submitted["place_text"])
    check.note("stale", stale)
    check.note("restored", restored)
    check.note("cleared", cleared)
    check.note("reselected", reselected)


def check_mobile_scrolling(check, context):
    viewer = context.viewer
    page = viewer.page
    key = f"jalandhar_{YEAR_365256363.replace('.', '')}"
    viewer.show(key, JALANDHAR, context.documents)
    desktop_hints = _scroll_hints(page)
    page.set_viewport_size({"width": 375, "height": 812})
    page.wait_for_timeout(200)
    measured = page.evaluate(
        "() => { const wrapper = document.getElementById('chart-wrapper');"
        " const table = document.getElementById('table-wrapper');"
        " const svg = document.querySelector('#chart svg');"
        " const box = svg.getBoundingClientRect();"
        " return {chart_wrapper: {scrollWidth: wrapper.scrollWidth, clientWidth: wrapper.clientWidth},"
        " table_wrapper: {scrollWidth: table.scrollWidth, clientWidth: table.clientWidth},"
        " svg_width: box.width, svg_height: box.height,"
        " document: {scrollWidth: document.documentElement.scrollWidth,"
        "            clientWidth: document.documentElement.clientWidth}}; }"
    )
    mobile_hints = _scroll_hints(page)
    page.screenshot(path=str(context.out / "screenshots" / "mobile_375.png"), full_page=True)
    page.set_viewport_size(context.viewport)
    page.wait_for_timeout(200)
    check.note("measured", measured)
    check.note("hints_at_1280", desktop_hints)
    check.note("hints_at_375", mobile_hints)
    check.require(
        measured["chart_wrapper"]["scrollWidth"] > measured["chart_wrapper"]["clientWidth"],
        f"the chart wrapper does not scroll: {measured['chart_wrapper']}",
    )
    check.equals("chart width at 375 px", measured["svg_width"], 600)
    check.require(
        measured["document"]["scrollWidth"] <= measured["document"]["clientWidth"],
        f"the page scrolls horizontally: {measured['document']}",
    )

    # The hint is shown exactly while its wrapper overflows, so at 1280 px --
    # where the chart fits -- it must be hidden, and at 375 px it must not.
    check.require(
        desktop_hints["chart"]["hidden"] is True,
        f"the chart scroll hint is visible at {context.viewport['width']} px: "
        f"{desktop_hints['chart']}",
    )
    check.require(
        mobile_hints["chart"]["hidden"] is False,
        f"the chart scroll hint is hidden at 375 px although the wrapper "
        f"scrolls: {mobile_hints['chart']}",
    )
    check.equals(
        "chart hint text",
        mobile_hints["chart"]["text"],
        "Scroll horizontally to see the full chart.",
    )

    # The daśā table may or may not overflow a 375 px viewport, depending on
    # the boundary text width, so the report records which it was rather than
    # pinning one. The hint must agree with the wrapper either way.
    table_overflows = (
        measured["table_wrapper"]["scrollWidth"]
        > measured["table_wrapper"]["clientWidth"]
    )
    check.note("table_overflows_at_375", table_overflows)
    check.equals(
        "table hint shown at 375 px",
        mobile_hints["table"]["hidden"] is False,
        table_overflows,
    )
    if table_overflows:
        check.equals(
            "table hint text",
            mobile_hints["table"]["text"],
            "Scroll horizontally to see the full table.",
        )


def _scroll_hints(page):
    """The two overflow hints: whether each is shown, and its text."""
    return page.evaluate(
        "() => { const read = (id) => { const node = document.getElementById(id);"
        "   return node ? {hidden: node.hidden, text: node.textContent} : null; };"
        " return {chart: read('chart-scroll-hint'), table: read('table-scroll-hint')}; }"
    )


def check_network_routes(check, context):
    seen = {}
    foreign = []
    non_http = []
    for entry in context.requests:
        url = entry["url"]
        if not url.startswith("http://") and not url.startswith("https://"):
            non_http.append(entry)
            continue
        if not url.startswith(context.url.rstrip("/")):
            foreign.append(entry)
            continue
        path = url[len(context.url.rstrip("/")) :] or "/"
        path = path.split("?", 1)[0].split("#", 1)[0]
        seen[path] = seen.get(path, 0) + 1
    check.note("origin", context.url.rstrip("/"))
    check.note("paths", seen)
    check.note("foreign_origin_requests", foreign)
    check.note("non_http_requests", non_http)
    check.note("total_requests", len(context.requests))
    check.equals("requests to another origin", foreign, [])
    check.equals("requests with a non-http scheme", non_http, [])
    unexpected = sorted(path for path in seen if path not in ALLOWED_PATHS)
    check.equals("unexpected paths", unexpected, [])
    for path in ALLOWED_PATHS:
        check.require(seen.get(path, 0) >= 1, f"nothing ever requested {path}")
    context.measurements["requests_by_path"] = seen


#: Chromium logs one console error for every fetch that answers with a non-2xx
#: status. The `errors` check deliberately provokes 400, 404 and 409 answers, so
#: those lines are recorded and classified rather than counted as page defects;
#: anything else is a failure.
PROVOKED_RESPONSE_ERROR = re.compile(
    r"^Failed to load resource: the server responded with a status of (400|404) "
)


def check_csp_clean(check, context):
    violations = list(context.violations) + context.viewer.violations()
    errors = [entry for entry in context.console if entry["type"] == "error"]
    provoked = [entry for entry in errors if PROVOKED_RESPONSE_ERROR.match(entry["text"])]
    unexpected = [entry for entry in errors if entry not in provoked]
    check.note("violations", violations)
    check.note("console_errors_total", len(errors))
    check.note(
        "console_errors_from_provoked_error_responses",
        {
            "count": len(provoked),
            "note": (
                "the errors check submits inputs the server must refuse (400, 404); "
                "Chromium logs one console error per non-2xx fetch, which is the "
                "server's contract working, not a page defect"
            ),
            "texts": sorted({entry["text"] for entry in provoked}),
        },
    )
    check.note("unexpected_console_errors", unexpected)
    check.note("page_errors", context.page_errors)
    check.note("console_messages", len(context.console))
    check.equals("securitypolicyviolation events", violations, [])
    check.equals("unexpected console errors", unexpected, [])
    check.equals("uncaught page errors", context.page_errors, [])



# --- Layer 15: defaults, the combobox, the implicit convention ---------------


def defaults_case(check, context, key, time_text, place_label, screenshot):
    """One submission with some optional value left blank (Layer 15 section 2).

    The same body for all three checks: what differs is which of the two
    optional values was supplied, and every assertion about assumption is made
    against the response's own ``effective`` and ``assumptions`` blocks, never
    against a guess.
    """
    viewer = context.viewer
    birth = {
        "date": JALANDHAR["date"],
        "time": time_text,
        "place_query": JALANDHAR["place_query"] if place_label else "",
        "place_label": place_label or "",
    }
    status, document, raw = viewer.submit(birth)
    viewer.shown = None
    check.equals("status", status, 200)
    if status != 200:
        check.note("error", document)
        return None
    (context.out / "responses" / f"{key}.json").write_bytes(raw)

    effective = document["effective"]
    assumptions = document["assumptions"]
    time_assumed = time_text.strip() == ""
    place_assumed = not place_label
    label = effective["place"]["label"]

    check.equals("time_assumed", effective["time_assumed"], time_assumed)
    check.equals("place_assumed", effective["place_assumed"], place_assumed)
    check.equals("assumptions.time", assumptions["time"], time_assumed)
    check.equals("assumptions.place", assumptions["place"], place_assumed)
    check.equals("assumptions.any", assumptions["any"], time_assumed or place_assumed)
    check.equals(
        "source", effective["source"], "default" if place_assumed else "selected"
    )
    check.equals(
        "effective time",
        effective["time"],
        "12:00:00" if time_assumed else f"{time_text}:00",
    )
    check.equals(
        "submitted strings",
        document["request"]["submitted"],
        {
            "date": birth["date"],
            "time": time_text,
            "place_text": place_label or "",
            "place_id": "" if place_assumed else str(effective["place"]["geoname_id"]),
        },
    )
    check.equals(
        "normalized time", document["request"]["normalized"]["time"], effective["time"]
    )
    check.equals("birth zone", document["birth"]["zone"], document["location"]["timezone_id"])

    expected_labels = []
    if time_assumed:
        expected_labels.append("Time 12:00:00 assumed: no time was supplied")
    if place_assumed:
        expected_labels.append(f"Birthplace {label} assumed: the configured default")
    check.equals("assumption labels", assumptions["labels"], expected_labels)
    check.equals("assumption labels on the page", viewer.assumption_labels(), expected_labels)

    badges = viewer.badges()
    check.note("badges", badges)
    for name, badge in badges.items():
        check.equals(f"{name} badge shown", badge["hidden"] is False, assumptions["any"])
        check.equals(f"{name} badge role", badge["role"], "status")
        if assumptions["any"]:
            check.equals(f"{name} badge text", badge["text"], ASSUMED_BADGE)
            check.require(
                "v-badge" in (badge["classes"] or ""),
                f"the {name} badge is not a v-badge: {badge}",
            )

    details = viewer.details("#birth-details")
    check.note("birth_details", details)
    check.equals("Date row", details.get("Date"), f"{birth['date']} (supplied)")
    check.equals(
        "Time row",
        details.get("Time"),
        f"{effective['time']} (assumed — no time was supplied)"
        if time_assumed
        else f"{effective['time']} (supplied)",
    )
    check.equals(
        "Birthplace row",
        details.get("Birthplace"),
        f"{label} (assumed — the configured default; no birthplace was supplied)"
        if place_assumed
        else f"{label} (supplied — selected from the list)",
    )
    submitted_line = viewer.text("#submitted-line")
    check.note("submitted_line", submitted_line)
    check.equals(
        "results header line",
        submitted_line,
        f"Computed from {effective['date']}, "
        f"{'assumed ' if time_assumed else ''}{effective['time']}, "
        f"{'assumed ' if place_assumed else ''}{label}",
    )
    check.equals("rows", len(document["rows"]), 819)
    check.equals("visible rows", viewer.row_count(), 9)

    viewer.page.screenshot(
        path=str(context.out / "screenshots" / screenshot), full_page=True
    )
    check.note("screenshot", screenshot)
    return document


def compare_with_cli(check, context, document, time_text, label_for_cli=None):
    """The same birth through the CLI, by a query that names the same record."""
    effective = document["effective"]
    expected_id = effective["place"]["geoname_id"]
    query, resolved = context.query_for(expected_id, effective["place"]["label"])
    check.note("cli_place_query", query)
    check.note("cli_resolved", resolved)
    if query is None:
        check.fail(
            "no CLI --place query resolves to the record the page used "
            f"({expected_id}); tried {brief(context.tried_queries)}"
        )
        return
    check.equals("CLI record", resolved["geoname_id"], expected_id)
    check.equals("CLI latitude", resolved["latitude"], document["location"]["latitude"])
    check.equals("CLI longitude", resolved["longitude"], document["location"]["longitude"])
    check.equals(
        "CLI timezone", resolved["timezone_id"], document["location"]["timezone_id"]
    )
    target = context.out / "cli" / f"default_{time_text.replace(':', '')}.svg"
    file_bytes = context.cli.svg(
        document["effective"]["date"], time_text, query, target
    )
    response_bytes = document["svg"].encode("utf-8")
    check.note(
        "svg",
        {
            "cli_file": str(target),
            "cli_command_time": time_text,
            "cli_sha256": hashlib.sha256(file_bytes).hexdigest(),
            "response_sha256": hashlib.sha256(response_bytes).hexdigest(),
            "bytes": [len(file_bytes), len(response_bytes)],
        },
    )
    check.equals(
        "svg bytes equal the CLI's",
        hashlib.sha256(response_bytes).hexdigest(),
        hashlib.sha256(file_bytes).hexdigest(),
    )


def check_defaults_date_only(check, context):
    document = defaults_case(
        check, context, "defaults_date_only", "", None, "combo_neither.png"
    )
    if document is None:
        return
    effective = document["effective"]
    check.note("default_place", context.default_place)
    check.equals(
        "the record is the configured default",
        effective["place"]["geoname_id"],
        context.default_place["id"],
    )
    check.equals(
        "the label is the configured default",
        effective["place"]["label"],
        context.default_place["label"],
    )
    check.equals("matched_name is null for the default", effective["place"]["matched_name"], None)
    check.equals("assumed time", effective["time"], "12:00:00")
    compare_with_cli(check, context, document, "12:00")


def check_defaults_time_only(check, context):
    document = defaults_case(
        check, context, "defaults_time_only", "06:45", None, "combo_time_only.png"
    )
    if document is None:
        return
    effective = document["effective"]
    check.equals(
        "the record is the configured default",
        effective["place"]["geoname_id"],
        context.default_place["id"],
    )
    check.equals("the supplied time is kept", effective["time"], "06:45:00")
    check.equals(
        "the default record's zone applies",
        document["birth"]["zone"],
        context.default_place["zone"],
    )
    compare_with_cli(check, context, document, "06:45")


def check_defaults_place_only(check, context):
    document = defaults_case(
        check,
        context,
        "defaults_place_only",
        "",
        JALANDHAR["place_label"],
        "combo_place_only.png",
    )
    if document is None:
        return
    effective = document["effective"]
    expected = EXPECTED_PLACES[JALANDHAR["place_label"]]
    check.equals("the selected record", effective["place"]["geoname_id"], expected["geoname_id"])
    check.equals("assumed noon", effective["time"], "12:00:00")
    check.equals(
        "noon in the selected place's zone",
        document["birth"]["local_seconds"],
        f"{JALANDHAR['date']} 12:00:00{expected['offset']}",
    )
    check.equals("the selected place's zone", document["birth"]["zone"], expected["timezone_id"])


def check_combobox_keyboard(check, context):
    """Layer 15 section 5.2 and the WAI-ARIA combobox keys."""
    viewer = context.viewer
    page = viewer.page
    if context.jammu_available:
        query, label = JAMMU["place_query"], JAMMU["place_label"]
    else:
        query, label = JALANDHAR["place_query"], JALANDHAR["place_label"]
    expected_id = EXPECTED_PLACES[label]["geoname_id"]
    check.note("typed", query)
    check.note("target", label)

    page.fill("#birth-place", "")
    page.fill("#birth-place", query)
    page.wait_for_selector("#place-listbox li", timeout=30000)
    opened = viewer.combobox()
    check.note("opened", opened)
    check.equals("role", opened["role"], "combobox")
    check.equals("aria-autocomplete", opened["autocomplete"], "list")
    check.equals("aria-expanded when open", opened["expanded"], "true")
    check.equals("no active option before a key", opened["activedescendant"], None)
    check.equals(
        "option ids",
        [option["id"] for option in opened["options"]],
        [f"place-option-{index}" for index in range(len(opened["options"]))],
    )
    check.equals(
        "option roles",
        sorted({option["role"] for option in opened["options"]}),
        ["option"],
    )
    positions = [
        index
        for index, option in enumerate(opened["options"])
        if option["text"] == label or option["text"].startswith(label + " (matched:")
    ]
    if not check.require(positions, f"{label} is not among the suggestions for {query!r}"):
        return
    position = positions[0]
    check.note("target_position", position)

    page.keyboard.press("ArrowDown")
    check.equals("ArrowDown highlights the first option", viewer.combobox()["activedescendant"], "place-option-0")
    page.keyboard.press("ArrowUp")
    check.equals(
        "ArrowUp wraps to the last option",
        viewer.combobox()["activedescendant"],
        f"place-option-{len(opened['options']) - 1}",
    )
    page.keyboard.press("ArrowDown")
    check.equals("ArrowDown wraps back to the first", viewer.combobox()["activedescendant"], "place-option-0")
    for _ in range(position):
        page.keyboard.press("ArrowDown")
    highlighted = viewer.combobox()
    check.equals("aria-activedescendant", highlighted["activedescendant"], f"place-option-{position}")
    check.equals(
        "the highlighted option is the selected one",
        [option["selected"] for option in highlighted["options"]],
        ["true" if index == position else "false" for index in range(len(highlighted["options"]))],
    )

    before = context.count_requests("/api/chart")
    page.keyboard.press("Enter")
    chosen = viewer.combobox()
    check.note("after_enter", chosen)
    check.equals("Enter writes the server's label", chosen["value"], label)
    check.equals("Enter writes the identifier", chosen["place_id"], str(expected_id))
    check.equals("the marker is shown", chosen["marker_hidden"], False)
    check.equals("the marker is text", chosen["marker_text"], "✓ selected")
    check.equals("the list is closed", chosen["options"], [])
    check.equals("aria-expanded after Enter", chosen["expanded"], "false")
    check.equals("no active option after Enter", chosen["activedescendant"], None)
    check.equals(
        "Enter did not submit the form", context.count_requests("/api/chart"), before
    )

    # Escape closes without selecting.
    page.fill("#birth-place", query)
    page.wait_for_selector("#place-listbox li", timeout=30000)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Escape")
    escaped = viewer.combobox()
    check.note("after_escape", escaped)
    check.equals("Escape closes the list", escaped["options"], [])
    check.equals("Escape leaves the text", escaped["value"], query)
    check.equals("Escape selects nothing", escaped["place_id"], "")
    check.equals("aria-expanded after Escape", escaped["expanded"], "false")

    # Enter with nothing highlighted does nothing at all.
    page.fill("#birth-place", query)
    page.wait_for_selector("#place-listbox li", timeout=30000)
    before = context.count_requests("/api/chart")
    page.keyboard.press("Enter")
    idle = viewer.combobox()
    check.note("after_bare_enter", idle)
    check.equals("Enter with nothing highlighted selects nothing", idle["place_id"], "")
    check.equals(
        "Enter with nothing highlighted sends nothing",
        context.count_requests("/api/chart"),
        before,
    )
    check.require(
        len(idle["options"]) >= 1,
        "the list closed although nothing was chosen",
    )

    # Tab closes without selecting.
    page.keyboard.press("Tab")
    tabbed = viewer.combobox()
    check.note("after_tab", tabbed)
    check.equals("Tab closes the list", tabbed["options"], [])
    check.equals("Tab selects nothing", tabbed["place_id"], "")
    check.equals("the prompt is shown on blur", tabbed["message"], SELECTION_PROMPT)
    page.fill("#birth-place", "")


def check_combobox_pointer(check, context):
    viewer = context.viewer
    page = viewer.page
    query, label = JALANDHAR["place_query"], JALANDHAR["place_label"]
    expected_id = EXPECTED_PLACES[label]["geoname_id"]
    page.fill("#birth-place", "")
    page.fill("#birth-place", query)
    page.wait_for_selector("#place-listbox li", timeout=30000)
    opened = viewer.combobox()
    check.note("options", [option["text"] for option in opened["options"]])
    positions = [
        index
        for index, option in enumerate(opened["options"])
        if option["text"] == label or option["text"].startswith(label + " (matched:")
    ]
    if not check.require(positions, f"{label} is not among the suggestions for {query!r}"):
        return
    before = context.count_requests("/api/chart")
    page.click(f"#place-option-{positions[0]}")
    chosen = viewer.combobox()
    check.note("after_click", chosen)
    check.equals("the click writes the server's label", chosen["value"], label)
    check.equals("the click writes the identifier", chosen["place_id"], str(expected_id))
    check.equals("the marker is shown", chosen["marker_hidden"], False)
    check.equals("the list is closed", chosen["options"], [])
    check.equals("no request was sent by the click", context.count_requests("/api/chart"), before)

    # An alias is shown in the list but never written into the field.
    aliased = [
        option["text"]
        for option in opened["options"]
        if "(matched:" in option["text"]
    ]
    check.note("aliased_options", aliased)
    check.require(
        all("(matched:" not in chosen["value"] for _ in [0]),
        f"an alias tail reached the field: {chosen['value']!r}",
    )
    page.fill("#birth-place", "")


#: The two edits are scheduled **inside the page**, so that they happen while a
#: Playwright route handler is deliberately holding the first response. The
#: handler blocks the script's own dispatcher; the page's timers do not care.
SCHEDULE_EDITS = """
(argument) => {
  const field = document.getElementById('birth-place');
  const fire = (text) => {
    field.value = text;
    field.dispatchEvent(new Event('input', {bubbles: true}));
  };
  window.__editLog = [];
  fire(argument.first);
  window.__editLog.push(['first', Math.round(performance.now())]);
  setTimeout(() => {
    fire(argument.second);
    window.__editLog.push(['second', Math.round(performance.now())]);
  }, argument.gap);
  return true;
}
"""

#: Type one more character, then choose from the list that is still on screen
#: while that character's request is in flight.
SCHEDULE_EDIT_THEN_SELECT = """
(argument) => {
  const field = document.getElementById('birth-place');
  window.__editLog = [];
  field.value = argument.text;
  field.dispatchEvent(new Event('input', {bubbles: true}));
  window.__editLog.push(['edit', Math.round(performance.now())]);
  setTimeout(() => {
    const option = document.querySelector('#place-listbox li');
    if (option) { option.click(); }
    window.__editLog.push(['select', Math.round(performance.now()),
                           option ? option.textContent : null]);
  }, argument.gap);
  return true;
}
"""

RESOURCE_TIMINGS = """
() => performance.getEntriesByType('resource')
  .filter(entry => entry.name.indexOf('/api/places') !== -1)
  .map(entry => ({start: Math.round(entry.startTime),
                  end: Math.round(entry.responseEnd),
                  duration: Math.round(entry.duration)}))
"""


def check_combobox_stale(check, context):
    """Layer 15 section 5.2: a late or out-of-order answer never reopens a list.

    Three situations, in the order the specification names them.

    1. Two suggestion requests, the first of which the server has already
       answered when the second goes out: a Playwright route holds that first
       response until well after the second request has been issued, and the
       page shows the second's suggestions and never the first's.
    2. Two edits inside the debounce window: one request, for the second text.
    3. A selection made while an older request is in flight: the list stays
       closed when that request is finally released.

    What the run also shows, and the report records with the timings that prove
    it, is that the page never has to *discard* the held answer: the edit aborts
    that request at once (immediate invalidation, section 5.2), 150 ms before
    the debounce lets the next one go out. Two suggestion requests are therefore
    never in flight from this page at the same instant -- the report states that
    as a measurement rather than leaving it implied -- and the sequence-number
    and echo checks in ``viewer.js`` are the second line of that defence, not
    the first.
    """
    viewer = context.viewer
    page = viewer.page
    first_query = JALANDHAR["place_query"]
    second_query = JAMMU["place_query"]
    delay = 1.5

    origin_page = page.evaluate("() => performance.now()")
    started = time.monotonic()
    log = []

    def page_time(relative):
        """A route timestamp on the page's own clock, near enough to compare."""
        return round(origin_page + relative * 1000.0)

    def handler(route):
        entry = {"enter": round(time.monotonic() - started, 3)}
        posted = route.request.post_data or ""
        try:
            entry["q"] = json.loads(posted).get("q")
        except ValueError:
            entry["q"] = None
        log.append(entry)
        if entry["q"] == first_query:
            time.sleep(delay)
        entry["release"] = round(time.monotonic() - started, 3)
        try:
            route.continue_()
        except Exception as error:  # noqa: BLE001 -- an aborted request cannot be continued
            entry["continue_error"] = f"{type(error).__name__}: {error}"

    page.fill("#birth-place", "")
    page.wait_for_timeout(400)
    expected_second = viewer.api("/api/places", {"q": second_query})["document"]
    expected_first = viewer.api("/api/places", {"q": first_query})["document"]
    check.note(
        "suggestions",
        {
            first_query: [item["label"] for item in expected_first["suggestions"]],
            second_query: [item["label"] for item in expected_second["suggestions"]],
        },
    )

    page.route("**/api/places", handler)
    try:
        before = context.count_requests("/api/places")
        scheduled_at = page.evaluate("() => performance.now()")
        page.evaluate(
            SCHEDULE_EDITS,
            {"first": first_query, "second": second_query, "gap": 500},
        )
        # The dispatcher is blocked inside the handler while the page goes on
        # living; this call returns once both responses have been dealt with.
        page.wait_for_timeout(int(delay * 1000) + 2500)
        out_of_order = viewer.combobox()
        edits = page.evaluate("() => window.__editLog")
        timings = [
            entry
            for entry in page.evaluate(RESOURCE_TIMINGS)
            if entry["start"] >= scheduled_at - 5
        ]
    finally:
        page.unroute("**/api/places", handler)
    requests_made = context.count_requests("/api/places") - before
    check.note("route_log", log)
    check.note("in_page_edits", edits)
    check.note("resource_timings", timings)
    check.note("requests_made", requests_made)
    check.note("state_after_out_of_order", out_of_order)

    # What overlapped what, on one clock, rather than by assertion of intent.
    overlap = {
        "note": (
            "the page aborts the older suggestion request the moment the field "
            "changes (section 5.2), and the debounce holds the newer one back "
            "150 ms, so two requests from this page are never in flight at the "
            "same instant; what this check produces is an older answer that the "
            "server had already made and that was still held when the newer "
            "request went out, and it never reaches the list"
        ),
        "first_request": timings[0] if timings else None,
        "second_request": timings[1] if len(timings) > 1 else None,
        "first_answer_held_from": page_time(log[0]["enter"]) if log else None,
        "first_answer_released_at": page_time(log[0]["release"]) if log else None,
        "second_answer_released_at": page_time(log[1]["release"]) if len(log) > 1 else None,
        "edits": edits,
    }
    if len(timings) > 1 and log:
        overlap["older_answer_still_held_when_the_newer_request_went_out"] = (
            page_time(log[0]["release"]) > timings[1]["start"]
        )
        overlap["the_two_requests_overlapped"] = timings[1]["start"] < timings[0]["end"]
    check.note("overlap", overlap)

    check.equals("two suggestion requests were made", requests_made, 2)
    check.equals("both were routed", [entry["q"] for entry in log], [first_query, second_query])
    check.require(
        log and log[0]["release"] - log[0]["enter"] >= delay - 0.05,
        f"the first response was not held: {brief(log)}",
    )
    check.require(
        len(log) > 1 and log[1]["enter"] >= log[0]["release"] - 0.001,
        f"the second request was not answered after the first was held: {brief(log)}",
    )
    check.require(
        len(timings) > 1 and log and page_time(log[0]["release"]) > timings[1]["start"],
        "the older answer was already released before the newer request went "
        f"out, so nothing was held: {brief(overlap)}",
    )
    check.equals("the field holds the second text", out_of_order["value"], second_query)
    shown_labels = [option["text"] for option in out_of_order["options"]]
    expected_labels = [item["label"] for item in expected_second["suggestions"]]
    check.equals(
        "the list shows the second query's suggestions",
        [text.split(" (matched:")[0] for text in shown_labels],
        expected_labels,
    )
    first_labels = {item["label"] for item in expected_first["suggestions"]}
    check.require(
        not (set(text.split(" (matched:")[0] for text in shown_labels) & first_labels),
        f"the held answer reopened the list: {brief(shown_labels)}",
    )
    check.note(
        "first_request_outcome",
        {
            "route": log[0].get("continue_error", "released after the delay"),
            "page": (
                "the fetch was aborted at the edit, before the answer was "
                "released"
                if len(timings) > 1 and timings[0]["end"] <= timings[1]["start"]
                else "the fetch was still open when the answer was released"
            ),
        },
    )

    # 2. Two edits inside the debounce window: one request only.
    before = context.count_requests("/api/places")
    page.fill("#birth-place", first_query)
    page.fill("#birth-place", second_query)
    page.wait_for_selector("#place-listbox li", timeout=30000)
    page.wait_for_timeout(600)
    debounced = viewer.combobox()
    within = context.count_requests("/api/places") - before
    check.note("requests_within_the_debounce_window", within)
    check.note("state_after_debounce", debounced)
    check.equals("one request for two edits inside 150 ms", within, 1)
    check.equals(
        "the debounced list is the second query's",
        [option["text"].split(" (matched:")[0] for option in debounced["options"]],
        expected_labels,
    )

    # 3. A selection made while an older request is in flight.
    log2 = []

    def slow(route):
        entry = {"enter": round(time.monotonic() - started, 3)}
        posted = route.request.post_data or ""
        try:
            entry["q"] = json.loads(posted).get("q")
        except ValueError:
            entry["q"] = None
        log2.append(entry)
        time.sleep(delay)
        entry["release"] = round(time.monotonic() - started, 3)
        try:
            route.continue_()
        except Exception as error:  # noqa: BLE001
            entry["continue_error"] = f"{type(error).__name__}: {error}"

    page.route("**/api/places", slow)
    try:
        selection_origin = page.evaluate("() => performance.now()")
        selection_started = time.monotonic()
        page.evaluate(
            SCHEDULE_EDIT_THEN_SELECT,
            {"text": second_query + second_query[-1], "gap": 400},
        )
        page.wait_for_timeout(int(delay * 1000) + 2000)
        after_selection = viewer.combobox()
        selection_log = page.evaluate("() => window.__editLog")
    finally:
        page.unroute("**/api/places", slow)
    check.note("route_log_selection", log2)
    check.note("in_page_selection", selection_log)
    check.note("state_after_selection", after_selection)
    if log2 and selection_log:
        released_at = round(
            selection_origin
            + (log2[0]["release"] - (selection_started - started)) * 1000.0
        )
        selected_at = selection_log[-1][1]
        check.note(
            "selection_while_the_older_request_was_held",
            {
                "selected_at": selected_at,
                "older_answer_released_at": released_at,
                "held_past_the_selection": released_at > selected_at,
            },
        )
        check.require(
            released_at > selected_at,
            "the older answer was released before the selection was made, so "
            "nothing was held across it",
        )
    check.require(
        after_selection["place_id"] != "",
        f"the scheduled selection did not take: {brief(after_selection)}",
    )
    check.equals("the list stays closed after the selection", after_selection["options"], [])
    check.equals("aria-expanded stays false", after_selection["expanded"], "false")
    check.equals("the marker is shown", after_selection["marker_hidden"], False)
    check.require(
        after_selection["value"] not in (second_query, second_query + second_query[-1]),
        "the field still holds the typed text rather than the chosen label",
    )
    page.fill("#birth-place", "")


def check_selection_invalidated_on_edit(check, context):
    """Layer 15 section 2 rule 4, and the server's independent answer."""
    viewer = context.viewer
    page = viewer.page
    label = JALANDHAR["place_label"]
    chosen = viewer.select_place(JALANDHAR["place_query"], label)
    check.note("after_selection", chosen)
    check.equals("the identifier is set", chosen["place_id"], str(EXPECTED_PLACES[label]["geoname_id"]))

    page.focus("#birth-place")
    page.keyboard.press("End")
    page.keyboard.type("x")
    edited = viewer.combobox()
    check.note("after_edit", edited)
    check.equals("the identifier is cleared", edited["place_id"], "")
    check.equals("the marker is hidden", edited["marker_hidden"], True)
    check.equals("the text kept the edit", edited["value"], label + "x")

    before = context.count_requests("/api/chart")
    page.fill("#birth-date", JALANDHAR["date"])
    page.click("#generate")
    page.wait_for_timeout(800)
    blocked = {
        "requests": context.count_requests("/api/chart") - before,
        "message": viewer.text("#birth-place-message"),
        "status": viewer.text("#status"),
        "focus": viewer.active_id(),
    }
    check.note("blocked", blocked)
    check.equals("nothing was sent", blocked["requests"], 0)
    check.equals("the prompt is shown", blocked["message"], SELECTION_PROMPT)
    check.equals("the status line says nothing was sent", blocked["status"], "Nothing sent: the form is incomplete.")
    check.equals("focus returns to the birthplace", blocked["focus"], "birth-place")

    direct = viewer.api(
        "/api/chart",
        {
            "date": JALANDHAR["date"],
            "time": JALANDHAR["time"],
            "place_text": label + "x",
            "place_id": "",
        },
    )
    check.note(
        "direct_api",
        {
            "status": direct["status"],
            "kind": direct["document"]["error"]["kind"],
            "message": direct["document"]["error"]["message"],
        },
    )
    check.equals("the same body sent directly", direct["status"], 400)
    check.equals("its kind", direct["document"]["error"]["kind"], "place_selection_required")
    page.fill("#birth-place", "")


def check_invalid_time_no_fallback(check, context):
    """Layer 15 section 2 rule 5: an invalid time is an error, never noon.

    Two different things are recorded. What the *browser* does with ``25:00`` in
    a native time control is the browser's business and is noted, not asserted.
    What the *server* does with it is the contract, and is proven by a request
    that goes straight to the endpoint, past any control that might sanitise it.
    """
    viewer = context.viewer
    page = viewer.page
    native = {}
    try:
        page.fill("#birth-time", "25:00")
        native["fill_error"] = None
    except Exception as error:  # noqa: BLE001 -- some builds refuse the value outright
        native["fill_error"] = f"{type(error).__name__}: {error}"
    native["value_after_fill"] = page.input_value("#birth-time")
    kept = viewer.set_form(
        {
            "date": JALANDHAR["date"],
            "time": "25:00",
            "place_text": "",
            "place_id": "",
        }
    )
    native["value_after_assignment"] = kept["time"]
    native["validity"] = page.evaluate(
        "() => { const field = document.getElementById('birth-time');"
        " return {value: field.value, badInput: field.validity.badInput,"
        "         valid: field.validity.valid}; }"
    )
    check.note("native_time_input", native)

    direct = viewer.api(
        "/api/chart",
        {
            "date": JALANDHAR["date"],
            "time": "25:00",
            "place_text": "",
            "place_id": "",
        },
    )
    check.note(
        "direct_api",
        {
            "status": direct["status"],
            "kind": direct["document"]["error"]["kind"],
            "message": direct["document"]["error"]["message"],
            "keys": sorted(direct["document"]),
        },
    )
    check.equals("25:00 sent directly is refused", direct["status"], 400)
    check.equals("its kind", direct["document"]["error"]["kind"], "input")
    check.require(
        "effective" not in direct["document"] and "svg" not in direct["document"],
        f"the refusal carries a result: {brief(sorted(direct['document']))}",
    )
    check.require(
        "12:00" not in direct["document"]["error"]["message"],
        "the refusal mentions a noon fallback: "
        f"{direct['document']['error']['message']!r}",
    )
    for other in ("24:00", "07:60"):
        answer = viewer.api(
            "/api/chart",
            {"date": JALANDHAR["date"], "time": other, "place_text": "", "place_id": ""},
        )
        check.equals(f"{other} refused", answer["status"], 400)
        check.equals(f"{other} kind", answer["document"]["error"]["kind"], "input")
    page.fill("#birth-time", "")


def check_year_implicit(check, context):
    """Layer 15 section 6: no control, one stated convention, the CLI's rows."""
    viewer = context.viewer
    page = viewer.page
    key = f"jalandhar_{YEAR_365256363.replace('.', '')}"
    document = viewer.show(key, JALANDHAR, context.documents)["document"]

    # Layer 19 adds one fieldset of three radios named ``chart-style`` -- a
    # display preference, not a year control (Layer 19 section 6.1). Layer 20
    # (section 9) adds a second, ``#transit``, holding one checkbox, two
    # native fields and a button. The assertion therefore counts every radio
    # and fieldset that is *not* one of those controls: there must be none,
    # exactly as before Layer 19; and the one transit checkbox is named.
    controls = page.evaluate(
        "() => ({radios: document.querySelectorAll('input[type=\"radio\"]').length,"
        " other_radios: document.querySelectorAll("
        "'input[type=\"radio\"]:not([name=\"chart-style\"])').length,"
        " named: document.querySelectorAll('[name=\"year_convention\"]').length,"
        " fieldsets: document.querySelectorAll('fieldset').length,"
        " other_fieldsets: document.querySelectorAll("
        "'fieldset:not(#chart-style):not(#transit)').length,"
        " transit_fieldsets: document.querySelectorAll('fieldset#transit').length,"
        " transit_checkboxes: Array.from(document.querySelectorAll("
        "'#transit input[type=\"checkbox\"]')).map(input => input.id),"
        " transit_radios: document.querySelectorAll('#transit input[type=\"radio\"]').length,"
        " style_radios: document.querySelectorAll("
        "'#chart-style input[type=\"radio\"][name=\"chart-style\"]').length,"
        " legend: document.querySelectorAll('legend').length})"
    )
    check.note("controls", controls)
    check.equals("radio buttons outside the chart-style control", controls["other_radios"], 0)
    check.equals("year_convention controls", controls["named"], 0)
    check.equals("fieldsets other than the chart-style and transit controls",
                 controls["other_fieldsets"], 0)
    check.equals("chart-style radios (Layer 19 section 6.1)", controls["style_radios"], 3)
    check.equals("the transit fieldset (Layer 20 section 3.1)", controls["transit_fieldsets"], 1)
    check.equals("the transit control's one checkbox", controls["transit_checkboxes"],
                 ["transit-toggle"])
    check.equals("radios in the transit control", controls["transit_radios"], 0)

    check.equals(
        "the submitted body has no year key",
        sorted(document["request"]["submitted"]),
        ["date", "place_id", "place_text", "time"],
    )
    check.equals(
        "the transported display string",
        document["timeline"]["year_convention"]["display"],
        YEAR_DISPLAY,
    )
    caption = viewer.text("#table-caption")
    heading = viewer.text("#dasha-heading")
    check.note("caption", caption)
    check.note("dasha_heading", heading)
    check.require(YEAR_DISPLAY in caption, f"the caption does not state the convention: {brief(caption)}")
    check.require(YEAR_DISPLAY in heading, f"the daśā heading does not state the convention: {brief(heading)}")
    check.require(
        f"shown in {document['timeline']['zone']}" in caption,
        f"the caption does not state the display zone: {brief(caption)}",
    )

    table = context.cli_tables.get(key)
    if table is None:
        text = context.cli.dasha(
            JALANDHAR["date"],
            JALANDHAR["time"],
            JALANDHAR["place_label"],
            document["timeline"]["zone"],
        )
        table = parse_cli_table(text)
        context.cli_tables[key] = table
    page.click("#expand-all")
    page.wait_for_function(
        "() => document.querySelectorAll('#dasha-body tr').length === 819", timeout=60000
    )
    rendered = page_table(viewer)
    page.click("#collapse-all")
    check.note("cli_rows", len(table["rows"]))
    check.note("page_rows", len(rendered))
    check.equals("row counts", len(rendered), len(table["rows"]))
    mismatches = [
        {"index": index, "cli": cli_row, "page": page_row}
        for index, (cli_row, page_row) in enumerate(zip(table["rows"], rendered))
        if cli_row != page_row
    ]
    check.note("first_mismatches", mismatches[:3])
    check.equals("rows equal the CLI's with --dasha-year 365.256363", len(mismatches), 0)
    check.note(
        "cli_command",
        [
            "--dasha", "md-ad-pd", "--dasha-year", YEAR_365256363,
            "--place", JALANDHAR["place_label"],
        ],
    )


def check_default_override(check, context):
    """Layer 15 section 4.2: ``--default-place-id`` is what the page assumes."""
    process = ViewerProcess(
        context.python, context.repo_root, context.geodata, context.ephemeris,
        default_place_id=1268782,
    )
    page = None
    try:
        lines = process.wait_for_banner()
        check.note("banner", lines)
        default = parse_default_place(lines)
        check.note("default_place", default)
        check.equals("the banner's default record", default.get("id"), 1268782)
        check.equals("the banner's default label", default.get("label"), "Jalandhar, Punjab, India")
        check.equals("the banner marks the override", default.get("override"), True)

        page = context.browser_context.new_page()
        page.set_viewport_size(context.viewport)
        page.goto(process.url, wait_until="load")
        meta = page.evaluate(
            "() => document.querySelector('meta[name=\"viewer-default-place\"]').content"
        )
        note = page.text_content("#form-note")
        placeholder = page.get_attribute("#birth-place", "placeholder")
        check.note("meta", meta)
        check.note("note", note)
        check.note("placeholder", placeholder)
        check.equals("the meta tag", meta, "1268782|Jalandhar, Punjab, India")
        check.require(
            "Jalandhar, Punjab, India" in note,
            f"the inline note does not name the override: {note!r}",
        )
        check.require(
            placeholder == "Jalandhar, Punjab, India assumed if blank",
            f"the placeholder does not name the override: {placeholder!r}",
        )
        page.fill("#birth-date", JALANDHAR["date"])
        with page.expect_response(
            lambda response: response.url.endswith("/api/chart"), timeout=120000
        ) as caught:
            page.click("#generate")
        answer = caught.value
        document = json.loads(answer.body().decode("utf-8"))
        check.equals("status", answer.status, 200)
        effective = document["effective"]
        check.note(
            "effective",
            {
                "geoname_id": effective["place"]["geoname_id"],
                "label": effective["place"]["label"],
                "place_assumed": effective["place_assumed"],
                "source": effective["source"],
            },
        )
        check.equals("the assumed record", effective["place"]["geoname_id"], 1268782)
        check.equals("the assumed label", effective["place"]["label"], "Jalandhar, Punjab, India")
        check.equals("place_assumed", effective["place_assumed"], True)
        check.equals("source", effective["source"], "default")
        page.wait_for_selector("#birth-details", timeout=30000)
        check.equals(
            "the page's Birthplace row",
            page.evaluate(
                "() => { const keys = document.querySelectorAll('#birth-details .v-detail-key');"
                " const values = document.querySelectorAll('#birth-details .v-detail-value');"
                " for (let index = 0; index < keys.length; index++) {"
                "   if (keys[index].textContent === 'Birthplace') return values[index].textContent; }"
                " return null; }"
            ),
            "Jalandhar, Punjab, India (assumed — the configured default; no "
            "birthplace was supplied)",
        )
    finally:
        if page is not None:
            page.close()
        code = process.stop()
        check.note("exit_code", code)


def check_default_unavailable(check, context):
    """Layer 15 section 4.2: a default that is not in this database is exit 4."""
    command = [
        str(context.python),
        "-m",
        "vedic_chart.viewer",
        "--geodata",
        str(context.geodata),
        "--ephemeris",
        str(context.ephemeris),
        "--port",
        "0",
        "--default-place-id",
        "1",
    ]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "src"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(  # noqa: S603 -- fixed argument vector
        command,
        cwd=str(context.repo_root),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )
    check.note("command", command)
    check.note("returncode", completed.returncode)
    check.note("stdout", completed.stdout.strip().splitlines())
    check.note("stderr", completed.stderr.strip().splitlines())
    check.equals("exit code", completed.returncode, 4)
    check.require(
        "the default birthplace record 1 is not available" in completed.stderr,
        f"stderr does not name the record: {completed.stderr.strip()[:300]!r}",
    )
    check.require(
        "viewer: http" not in completed.stdout,
        "the viewer bound a port before failing on the default record",
    )
    check.require(
        not completed.stdout.strip(),
        f"the failing start-up printed a banner: {completed.stdout.strip()[:200]!r}",
    )


def parse_default_place(lines):
    """The banner's ``default place:`` line, as a dict."""
    for line in lines:
        match = DEFAULT_PLACE_LINE.fullmatch(line)
        if match:
            return {
                "id": int(match.group("id")),
                "label": match.group("label"),
                "zone": match.group("zone"),
                "override": match.group("override") is not None,
                "line": line,
            }
    return {}


# --- Layer 19: the chart style -------------------------------------------------
#
# docs/LAYER19_SOUTH_INDIAN_VIEWER_SPEC.md section 9.3. Every check below runs on
# a page of its own (StylePage): the shared page the Layer 14/15 checks use is
# never switched to another style, and the deliberate failures a few of these
# checks provoke (an injected 500, an aborted request) are classified on their
# own page instead of reaching csp_clean's console list. Their requests are
# still appended to the run's request log, so network_routes covers them, and
# their CSP violation events are added to the run's list for csp_clean.

STYLE_VALUES = ("north", "south", "both")
STYLE_LABELS = {"north": "North Indian", "south": "South Indian", "both": "Both"}
NORTH_HEADING = "D1 chart — North Indian"
SOUTH_HEADING = "D1 chart — South Indian"

#: Section 5.6, verbatim.
SOUTH_MISSING_NOTICE = (
    "The South Indian chart is not available from this server's response; "
    "the North Indian chart is shown instead."
)
SOUTH_REJECTED_NOTICE = (
    "The South Indian chart could not be shown: the server's document was "
    "not one this page accepts; the North Indian chart is shown instead."
)
MALFORMED_SOUTH = "<svg><script/></svg>"
SOUTH_TITLE = "D1 chart (South Indian)"

DESKTOP_VIEWPORT = {"width": 1280, "height": 800}
MOBILE_VIEWPORT = {"width": 375, "height": 812}

#: The single chart's rendered width before Layer 19, measured by this script on
#: the pre-Layer-19 page (``svg_dom_semantics`` box and ``mobile_scrolling``
#: ``svg_width``, same Chromium) and equal to what the pre-Layer-19 rule gives:
#: ``clamp(600, min(1120, viewport - 32 - scrollbar) - 10, 1080)``.
PRE_LAYER19_CHART_WIDTH = {1280: 1080, 375: 600}

#: Section 2 and 3.3: the Layer 10 style numbers the South Indian document
#: repeats, and the pixel figures section 3.3 states for a 600 px chart.
SOUTH_MARGIN = 40
SOUTH_CHART_GAP = 30
SOUTH_CANVAS = 1080
SOUTH_LADDER_UNITS = (32.0, 30.0, 28.0, 26.0, 24.0, 22.0, 21.0)
SOUTH_FLOOR_UNITS = 21.0
SOUTH_LABEL_UNITS = 20.0
SOUTH_CENTRE_UNITS = 32.0
SOUTH_LEGEND_UNITS = 22.0
SOUTH_SPEC_PIXELS_600 = {
    "entry_floor": 11.67,
    "label": 11.11,
    "centre": 17.8,
    "legend": 12.2,
}
FONT_TOLERANCE_PX = 0.1
BOUNDS_EPSILON_PX = 0.01
RASHI_NAMES = (
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena",
)
STRESS_CASES = ("one_sign_all_nine", "lagna_sign_all_nine")
#: Section 3.3: five rows shown, then ``+n`` for the occupants omitted -- nine
#: grahas alone leave four out; with ``As`` first in the cell, five.
STRESS_OVERFLOW = {"one_sign_all_nine": "+4", "lagna_sign_all_nine": "+5"}

#: The renderer, run through the project interpreter: the South Indian (and
#: North Indian) documents for one birth, from the same public pipeline entry
#: point and fixed options the server uses -- the CLI-less comparison.
SOUTH_RENDER_SNIPPET = """
import json, sys
from datetime import date, time
from vedic_chart.app import ChartConfig, render_chart_and_dasha_at
from vedic_chart.inputs.model import BirthChartRequest
from vedic_chart.location.offline.resolver import OfflineLocationResolver
from vedic_chart.render import render_north_indian_svg, render_south_indian_svg
from vedic_chart.viewer import transport

geodata, ephemeris, date_text, time_text, place_id = sys.argv[1:6]
config = ChartConfig(geodata_path=geodata, ephemeris_path=ephemeris)
with OfflineLocationResolver(config.geodata_path) as resolver:
    location, place = resolver.record(int(place_id))
    label = resolver.candidate_label(place)
year, month, day = (int(part) for part in date_text.split("-"))
hour, minute = (int(part) for part in time_text.split(":")[:2])
request = BirthChartRequest(
    birth_date=date(year, month, day), birth_time=time(hour, minute, 0),
    place_query=label,
)
result = render_chart_and_dasha_at(
    request, location, config, transport.RENDERER_OPTIONS, transport.YEAR
)
sys.stdout.write(json.dumps({
    "south": render_south_indian_svg(result.d1, transport.SOUTH_INDIAN_RENDERER_OPTIONS),
    "north": render_north_indian_svg(result.d1, transport.RENDERER_OPTIONS),
    "pipeline_svg": result.svg,
}))
"""

#: The synthetic stress charts of section 9.3, rendered by the test suite's own
#: builders with the server's fixed South Indian options.
STRESS_RENDER_SNIPPET = """
import json, sys
from render_helpers import south_case_chart
from vedic_chart.render import render_south_indian_svg
from vedic_chart.viewer import transport

sys.stdout.write(json.dumps({
    name: render_south_indian_svg(
        south_case_chart(name), transport.SOUTH_INDIAN_RENDERER_OPTIONS
    )
    for name in sys.argv[1:]
}))
"""

#: Everything the chart-style layout shows at one moment.
STYLE_STATE = """
() => {
  const q = (id) => document.getElementById(id);
  const visible = (node) => Boolean(node) && node.checkVisibility();
  const block = (id) => {
    const node = q(id);
    if (!node) return null;
    const box = node.getBoundingClientRect();
    return {hidden: node.hidden, visible: visible(node), offsetTop: node.offsetTop,
            offsetLeft: node.offsetLeft, top: box.top + window.scrollY,
            left: box.left, width: box.width, height: box.height};
  };
  const svgBox = (selector) => {
    const svg = document.querySelector(selector);
    if (!svg) return null;
    const box = svg.getBoundingClientRect();
    return {width: box.width, height: box.height, visible: visible(svg)};
  };
  const wrapper = (id) => {
    const node = q(id);
    return node ? {hidden: node.hidden, visible: visible(node),
                   scrollWidth: node.scrollWidth, clientWidth: node.clientWidth} : null;
  };
  const text = (id) => {
    const node = q(id);
    return node ? {hidden: node.hidden, visible: visible(node), text: node.textContent} : null;
  };
  const heading = (id) => {
    const node = q(id);
    return node && node.firstChild ? node.firstChild.textContent : null;
  };
  const main = document.querySelector('.v-main');
  const group = q('chart-style');
  return {
    checked: Array.from(document.querySelectorAll('input[name="chart-style"]'))
      .filter(input => input.checked).map(input => input.value),
    disabled: group ? group.disabled : null,
    main_wide: main.classList.contains('v-main-wide'),
    main_max_width: getComputedStyle(main).maxWidth,
    main_width: main.getBoundingClientRect().width,
    charts_width: q('charts') ? q('charts').clientWidth : null,
    results_hidden: q('results').hidden,
    north: block('chart-block-north'),
    south: block('chart-block-south'),
    north_heading: heading('chart-heading'),
    south_heading: heading('chart-south-heading'),
    north_svg: svgBox('#chart svg'),
    south_svg: svgBox('#chart-south svg'),
    north_svg_count: document.querySelectorAll('#chart svg').length,
    south_svg_count: document.querySelectorAll('#chart-south svg').length,
    south_children: q('chart-south') ? q('chart-south').childNodes.length : null,
    north_wrapper: wrapper('chart-wrapper'),
    south_wrapper: wrapper('chart-south-wrapper'),
    north_hint: text('chart-scroll-hint'),
    south_hint: text('chart-south-scroll-hint'),
    north_message: text('chart-message'),
    south_message: text('chart-south-message'),
    page: {scrollWidth: document.documentElement.scrollWidth,
           clientWidth: document.documentElement.clientWidth,
           innerWidth: window.innerWidth},
    data_stale: q('results').getAttribute('data-stale'),
    stale_banner: text('stale-banner'),
    busy: q('results').getAttribute('aria-busy'),
    alert: text('alert'),
    status: q('status').textContent,
    submitted_line: q('submitted-line') ? q('submitted-line').textContent : null,
    active: document.activeElement ? document.activeElement.id : null
  };
}
"""

#: Identity marks on the live nodes, so that "no re-parse, no rebuild" is a
#: statement about the same objects rather than about equal-looking ones.
MARK_STYLE_NODES = """
() => {
  window.__styleMarks = {
    body: document.getElementById('results-body'),
    north: document.querySelector('#chart svg'),
    south: document.querySelector('#chart-south svg')
  };
  return Boolean(window.__styleMarks.body);
}
"""

SAME_STYLE_NODES = """
() => {
  const marks = window.__styleMarks || {};
  return {
    body: marks.body === document.getElementById('results-body'),
    north: marks.north === document.querySelector('#chart svg'),
    south: marks.south === document.querySelector('#chart-south svg')
  };
}
"""

FORM_VALUES = """
() => ({date: document.getElementById('birth-date').value,
        time: document.getElementById('birth-time').value,
        place_text: document.getElementById('birth-place').value,
        place_id: document.getElementById('place-id').value})
"""

#: Only the fields whose value differs are written, each with the events a
#: person's edit produces; the identifier is written after the text, whose
#: `input` event clears it (Layer 15 section 2 rule 4).
SET_CHANGED_FIELDS = """
(values) => {
  const changed = [];
  const set = (id, value) => {
    const field = document.getElementById(id);
    if (field.value === value) return;
    field.value = value;
    changed.push(id);
    field.dispatchEvent(new Event('input', {bubbles: true}));
    field.dispatchEvent(new Event('change', {bubbles: true}));
  };
  set('birth-date', values.date);
  set('birth-time', values.time);
  set('birth-place', values.place_text);
  const identifier = document.getElementById('place-id');
  if (identifier.value !== values.place_id) {
    identifier.value = values.place_id;
    changed.push('place-id');
  }
  return changed;
}
"""

CLOSE_SUGGESTIONS = """
() => document.getElementById('birth-place').dispatchEvent(
  new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))
"""

#: A style change made without moving focus: the radio's checked state is set
#: and its `change` event dispatched, exactly what the browser does on a click
#: minus the focus change, so that "focus stays where the browser keeps it"
#: can be observed.
CHOOSE_WITHOUT_FOCUS = """
(value) => {
  const input = document.getElementById('chart-style-' + value);
  input.checked = true;
  input.dispatchEvent(new Event('change', {bubbles: true}));
  return input.checked;
}
"""

LAYOUT_METRICS = """
() => {
  const px = (value) => parseFloat(value) || 0;
  const wrapper = getComputedStyle(document.getElementById('chart-wrapper'));
  const southWrapper = getComputedStyle(document.getElementById('chart-south-wrapper'));
  const charts = getComputedStyle(document.getElementById('charts'));
  const body = getComputedStyle(document.body);
  const html = getComputedStyle(document.documentElement);
  const north = getComputedStyle(document.getElementById('chart'));
  const south = getComputedStyle(document.getElementById('chart-south'));
  const main = getComputedStyle(document.querySelector('.v-main'));
  return {
    north_min_width: px(north.minWidth),
    south_min_width: px(south.minWidth),
    north_padding: px(wrapper.paddingLeft) + px(wrapper.paddingRight),
    north_border: px(wrapper.borderLeftWidth) + px(wrapper.borderRightWidth),
    south_padding: px(southWrapper.paddingLeft) + px(southWrapper.paddingRight),
    south_border: px(southWrapper.borderLeftWidth) + px(southWrapper.borderRightWidth),
    gap: px(charts.columnGap),
    body_padding: px(body.paddingLeft) + px(body.paddingRight),
    body_margin: px(body.marginLeft) + px(body.marginRight),
    html_padding: px(html.paddingLeft) + px(html.paddingRight),
    main_max_width: px(main.maxWidth),
    scrollbar: window.innerWidth - document.documentElement.clientWidth,
    inner_width: window.innerWidth
  };
}
"""

#: Section 9.3 `south_text_bounds_600`: every text of the inserted South Indian
#: document, its region (its sign cell, the centre square, or the legend band),
#: all mapped to CSS pixels through the element's own getScreenCTM(), and the
#: effective font size: the font-size attribute (user units) times the screen
#: transform's scale.
TEXT_BOUNDS = """
(argument) => {
  const svg = document.querySelector(argument.selector);
  if (!svg) return null;
  const mapped = (element, box) => {
    const matrix = element.getScreenCTM();
    const corners = [[box.x, box.y], [box.x + box.width, box.y],
                     [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]
      .map(([x, y]) => new DOMPoint(x, y).matrixTransform(matrix));
    const xs = corners.map(point => point.x);
    const ys = corners.map(point => point.y);
    return {left: Math.min(...xs), top: Math.min(...ys),
            right: Math.max(...xs), bottom: Math.max(...ys)};
  };
  const cellOf = (rashi) => svg.querySelector('g.sign[data-rashi="' + rashi + '"] > rect.cell');
  const user = (node) => ({x: parseFloat(node.getAttribute('x')), y: parseFloat(node.getAttribute('y')),
                           width: parseFloat(node.getAttribute('width')),
                           height: parseFloat(node.getAttribute('height'))});
  const cells = Array.from(svg.querySelectorAll('g.sign > rect.cell')).map(user);
  const chartLeft = Math.min(...cells.map(cell => cell.x));
  const chartTop = Math.min(...cells.map(cell => cell.y));
  const chartRight = Math.max(...cells.map(cell => cell.x + cell.width));
  const chartBottom = Math.max(...cells.map(cell => cell.y + cell.height));
  const view = svg.viewBox.baseVal;
  const mesha = user(cellOf(1)), vrishabha = user(cellOf(2));
  const kumbha = user(cellOf(11)), makara = user(cellOf(10));
  const centreUser = {x: mesha.x, y: kumbha.y,
                      width: vrishabha.x + vrishabha.width - mesha.x,
                      height: makara.y + makara.height - kumbha.y};
  const bandUser = {x: chartLeft, y: chartBottom + argument.chartGap,
                    width: chartRight - chartLeft,
                    height: view.height - argument.margin - (chartBottom + argument.chartGap)};
  const centre = mapped(svg, centreUser);
  const band = mapped(svg, bandUser);
  const rootBox = svg.getBoundingClientRect();
  const texts = Array.from(svg.querySelectorAll('text')).map((text, index) => {
    const sign = text.closest('g.sign');
    const legend = text.closest('g.legend');
    const inCentre = text.closest('g.centre');
    let region = null;
    let regionName = 'none';
    if (sign) {
      region = mapped(sign.querySelector('rect.cell'), sign.querySelector('rect.cell').getBBox());
      regionName = 'cell ' + sign.getAttribute('data-rashi');
    } else if (inCentre) {
      region = centre; regionName = 'centre';
    } else if (legend) {
      region = band; regionName = 'legend band';
    }
    const group = text.closest('g.entry, g.legend-entry');
    const matrix = text.getScreenCTM();
    const units = parseFloat(text.getAttribute('font-size'));
    return {
      index: index,
      cls: text.getAttribute('class'),
      group: group ? group.getAttribute('class') : null,
      graha: group ? group.getAttribute('data-graha') : null,
      content: text.textContent,
      region_name: regionName,
      region: region,
      box: mapped(text, text.getBBox()),
      font_units: units,
      ctm_a: matrix.a,
      ctm_d: matrix.d,
      effective_px: units * matrix.a,
      computed_font_size: getComputedStyle(text).fontSize
    };
  });
  return {
    svg_width: rootBox.width,
    svg_height: rootBox.height,
    view_box: [view.x, view.y, view.width, view.height],
    root_ctm_a: svg.getScreenCTM().a,
    centre: centre,
    band: band,
    title: svg.querySelector('title') ? svg.querySelector('title').textContent : null,
    texts: texts
  };
}
"""

ALL_IDS = """
() => {
  const ids = Array.from(document.querySelectorAll('[id]')).map(node => node.id);
  const counts = {};
  ids.forEach(id => { counts[id] = (counts[id] || 0) + 1; });
  const root = (selector) => {
    const svg = document.querySelector(selector);
    if (!svg) return null;
    const title = svg.querySelector('title');
    const desc = svg.querySelector('desc');
    return {labelledby: svg.getAttribute('aria-labelledby'),
            describedby: svg.getAttribute('aria-describedby'),
            title_id: title ? title.id : null, desc_id: desc ? desc.id : null,
            title_owner: title && document.getElementById(title.id) === title,
            desc_owner: desc && document.getElementById(desc.id) === desc};
  };
  return {total: ids.length,
          duplicates: Object.keys(counts).filter(id => counts[id] > 1),
          north: root('#chart svg'), south: root('#chart-south svg')};
}
"""

LABEL_STYLES = """
() => Array.from(document.querySelectorAll('.v-style-label')).map(label => {
  const style = getComputedStyle(label);
  const input = document.getElementById(label.getAttribute('for'));
  return {for: label.getAttribute('for'), text: label.textContent,
          checked: input ? input.checked : null,
          border: style.borderTopColor + ' ' + style.borderTopStyle + ' ' + style.borderTopWidth,
          background: style.backgroundColor, weight: style.fontWeight};
})
"""

TREE_STATE = """
() => ({
  rows: Array.from(document.querySelectorAll('#dasha-body tr')).map(tr => tr.id),
  expanded: Array.from(document.querySelectorAll('#dasha-body tr[aria-expanded="true"]')).map(tr => tr.id),
  roving: Array.from(document.querySelectorAll('#dasha-body tr[tabindex="0"]')).map(tr => tr.id),
  active: document.activeElement ? document.activeElement.id : null
})
"""

BADGES_AND_ASSUMPTIONS = """
() => {
  const read = (id) => { const node = document.getElementById(id);
    return node ? {hidden: node.hidden, text: node.textContent} : null; };
  return {results: read('results-badge'), chart: read('chart-badge'),
          chart_south: read('chart-south-badge'), dasha: read('dasha-badge'),
          labels: Array.from(document.querySelectorAll('#assumption-labels li')).map(item => item.textContent)};
}
"""


def birth_values(birth):
    """The four submitted strings for a reference birth, selection included."""
    expected = EXPECTED_PLACES[birth["place_label"]]
    return {
        "date": birth["date"],
        "time": birth["time"],
        "place_text": birth["place_label"],
        "place_id": str(expected["geoname_id"]),
    }


def style_births(context):
    """The reference births of section 9.3: Jalandhar, and Jammu when present."""
    births = [("jalandhar", JALANDHAR)]
    if context.jammu_available:
        births.append(("jammu", JAMMU))
    return births


def note_jammu(check, context):
    if not context.jammu_available:
        check.note(
            "jammu",
            {
                "status": "skipped",
                "skipped_because": "the Jammu record is not in the configured "
                f"database ({context.jammu_reason})",
            },
        )


def expected_style(preference, south_state):
    """Section 5.6's table, as the four facts the page must show."""
    present = south_state == "present"
    notice = None
    if south_state == "missing":
        notice = SOUTH_MISSING_NOTICE
    elif south_state == "rejected":
        notice = SOUTH_REJECTED_NOTICE
    return {
        "north_visible": not (preference == "south" and present),
        "south_visible": preference in ("south", "both"),
        "south_chart": present,
        "notice": notice,
        "main_wide": preference == "both",
    }


def assert_style_table(check, state, preference, south_state, label):
    """The page against section 5.6 for one preference and one South state."""
    expected = expected_style(preference, south_state)
    check.equals(f"{label}: checked radio", state["checked"], [preference])
    check.equals(
        f"{label}: North block visible", state["north"]["visible"], expected["north_visible"]
    )
    check.equals(f"{label}: North block hidden attribute", state["north"]["hidden"],
                 not expected["north_visible"])
    check.equals(
        f"{label}: South block visible", state["south"]["visible"], expected["south_visible"]
    )
    check.equals(f"{label}: South block hidden attribute", state["south"]["hidden"],
                 not expected["south_visible"])
    check.equals(f"{label}: North heading", state["north_heading"], NORTH_HEADING)
    check.equals(f"{label}: South heading", state["south_heading"], SOUTH_HEADING)
    check.equals(f"{label}: one North SVG", state["north_svg_count"], 1)
    check.require(
        state["north_message"]["hidden"] is True,
        f"{label}: the North chart's own message is shown: {state['north_message']}",
    )
    check.equals(f"{label}: v-main-wide", state["main_wide"], expected["main_wide"])
    if expected["south_chart"]:
        check.equals(f"{label}: one South SVG", state["south_svg_count"], 1)
        check.require(
            state["south_message"]["hidden"] is True,
            f"{label}: a South notice is shown beside a valid chart: {state['south_message']}",
        )
    else:
        check.equals(f"{label}: no South SVG", state["south_svg_count"], 0)
        check.equals(f"{label}: #chart-south is empty", state["south_children"], 0)
        check.equals(f"{label}: South notice text", state["south_message"]["text"],
                     expected["notice"])
        check.equals(
            f"{label}: South notice visible",
            state["south_message"]["visible"],
            expected["south_visible"],
        )
        check.require(
            state["south_wrapper"]["visible"] is False,
            f"{label}: the empty South wrapper is shown: {state['south_wrapper']}",
        )
    if expected["north_visible"]:
        check.require(
            bool(state["north_svg"]) and state["north_svg"]["visible"],
            f"{label}: the North chart is not visible: {state['north_svg']}",
        )
    if expected["south_visible"] and expected["south_chart"]:
        check.require(
            bool(state["south_svg"]) and state["south_svg"]["visible"],
            f"{label}: the South chart is not visible: {state['south_svg']}",
        )


def assert_no_page_overflow(check, state, label):
    page = state["page"]
    check.require(
        page["scrollWidth"] <= page["innerWidth"],
        f"{label}: the page overflows horizontally: {page}",
    )


class StylePage:
    """A fresh viewer page for one Layer 19 check, with its own logs."""

    def __init__(self, context, viewport=None, hash_fragment="", init_script=None):
        self.context = context
        self.requests = []
        self.console = []
        self.page_errors = []
        page = context.browser_context.new_page()
        if init_script is not None:
            page.add_init_script(init_script)
        page.set_viewport_size(dict(viewport or DESKTOP_VIEWPORT))
        page.on("request", self._on_request)
        page.on(
            "console",
            lambda message: self.console.append({"type": message.type, "text": message.text}),
        )
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        page.goto(context.url + hash_fragment, wait_until="load")
        self.page = page
        self.viewer = Viewer(page, context.url, self.requests, self.console, self.page_errors)
        self.api_url = self.viewer.api_url

    def _on_request(self, request):
        entry = {"url": request.url, "method": request.method, "resource": request.resource_type}
        self.requests.append(entry)
        self.context.requests.append(entry)

    def mark(self):
        return len(self.requests)

    def since(self, mark):
        return list(self.requests[mark:])

    def chart_requests(self):
        return [entry for entry in self.requests if entry["url"] == self.api_url]

    def state(self):
        return self.page.evaluate(STYLE_STATE)

    def choose(self, value):
        """A person's click on the label of one radio."""
        self.page.click(f'label[for="chart-style-{value}"]')
        return self.state()

    def set_viewport(self, viewport):
        self.page.set_viewport_size(dict(viewport))
        self.page.wait_for_timeout(150)

    def fill(self, values):
        """Write the four strings, touching only the fields that change.

        A changed birthplace text starts the combobox's debounced suggestions
        request; it is waited for here and the list closed again, so that no
        suggestions request can fall inside a later "no request" window and no
        open list can cover the controls.
        """
        current = self.page.evaluate(FORM_VALUES)
        place_changes = values["place_text"] != current["place_text"]
        if place_changes and len(values["place_text"].split(",")[0]) >= 2:
            places_url = self.context.url.rstrip("/") + "/api/places"
            with self.page.expect_response(
                lambda response: response.url == places_url, timeout=30000
            ):
                changed = self.page.evaluate(SET_CHANGED_FIELDS, values)
            self.page.wait_for_timeout(100)
        else:
            changed = self.page.evaluate(SET_CHANGED_FIELDS, values)
        self.page.evaluate(CLOSE_SUGGESTIONS)
        return changed

    def generate(self, birth=JALANDHAR, values=None, timeout=120000):
        """One Generate, answered; returns (status, document, raw bytes)."""
        self.fill(values or birth_values(birth))
        self.page.evaluate(MARK_OLD_RESULTS)
        with self.page.expect_response(
            lambda response: response.url == self.api_url, timeout=timeout
        ) as caught:
            self.page.click("#generate")
        response = caught.value
        body = response.body()
        document = json.loads(body.decode("utf-8"))
        if response.status == 200:
            self.page.wait_for_function(RESULTS_REPLACED, timeout=timeout)
        else:
            self.page.wait_for_selector("#alert:not([hidden])", timeout=timeout)
        return response.status, document, body

    def click_generate_without_waiting(self, values):
        self.fill(values)
        self.page.evaluate(MARK_OLD_RESULTS)
        self.page.evaluate("() => document.getElementById('generate').click()")

    def screenshot(self, name):
        path = self.context.out / "screenshots" / name
        self.page.screenshot(path=str(path), full_page=True)
        return name

    def close(self, check, allowed_console=()):
        """Record the page's console and CSP evidence, then close it."""
        try:
            violations = self.page.evaluate("() => window.__acceptanceViolations || []")
        except Exception:  # noqa: BLE001 -- a closed page has nothing to add
            violations = []
        self.context.violations.extend(violations)
        errors = [entry for entry in self.console if entry["type"] == "error"]
        provoked = [
            entry
            for entry in errors
            if any(re.search(pattern, entry["text"]) for pattern in allowed_console)
        ]
        unexpected = [entry for entry in errors if entry not in provoked]
        check.note(
            "page_evidence",
            {
                "requests": len(self.requests),
                "chart_requests": len(self.chart_requests()),
                "console_errors_provoked": provoked,
                "console_errors_unexpected": unexpected,
                "page_errors": self.page_errors,
                "csp_violations": violations,
            },
        )
        check.equals("console errors not provoked by this check", unexpected, [])
        check.equals("page errors", self.page_errors, [])
        check.equals("CSP violations", violations, [])
        self.page.close()


def intercept_south(page, mutate, log):
    """Front ``/api/chart`` with the real server's answer, modified by ``mutate``.

    The request goes to the server unchanged; its response is read, its JSON
    document is handed to ``mutate`` and the result is fulfilled in place of the
    original, with the original status and headers.
    """

    def handler(route):
        response = route.fetch()
        body = response.body()
        entry = {"status": response.status}
        if response.status == 200:
            document = json.loads(body.decode("utf-8"))
            mutate(document)
            entry["south_indian_svg"] = (
                "absent"
                if "south_indian_svg" not in document
                else brief(document["south_indian_svg"], 60)
            )
            body = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        headers = {
            name: value
            for name, value in response.headers.items()
            if name.lower() != "content-length"
        }
        log.append(entry)
        route.fulfill(status=response.status, headers=headers, body=body)

    page.route("**/api/chart", handler)
    return handler


def run_project_python(context, snippet, arguments, extra_path=()):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(["src", *extra_path])
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(  # noqa: S603 -- fixed argument vector
        [str(context.python), "-c", snippet, *[str(argument) for argument in arguments]],
        cwd=str(context.repo_root),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"the project interpreter exited {completed.returncode}: "
            f"{completed.stderr.strip()[-800:]}"
        )
    return json.loads(completed.stdout)


def renderer_documents(context, name, birth):
    """The renderer's own documents for one reference birth, cached per run."""
    cache = context.__dict__.setdefault("south_renderer", {})
    if name not in cache:
        values = birth_values(birth)
        cache[name] = run_project_python(
            context,
            SOUTH_RENDER_SNIPPET,
            [context.geodata, context.ephemeris, values["date"], values["time"],
             values["place_id"]],
        )
        (context.out / "svg" / f"{name}_south_renderer.svg").write_text(
            cache[name]["south"], encoding="utf-8"
        )
    return cache[name]


def stress_documents(context):
    cache = context.__dict__.setdefault("south_stress", None)
    if cache is None:
        cache = run_project_python(
            context, STRESS_RENDER_SNIPPET, list(STRESS_CASES), extra_path=("tests",)
        )
        for name, svg in cache.items():
            (context.out / "svg" / f"stress_{name}_south.svg").write_text(svg, encoding="utf-8")
        context.south_stress = cache
    return cache


# -- the named checks ---------------------------------------------------------


def check_style_default_north(check, context):
    style = StylePage(context)
    try:
        before = style.page.evaluate(
            "() => { const group = document.getElementById('chart-style');"
            " const legend = group.querySelector('legend');"
            " return {exists: Boolean(group), tag: group.tagName, disabled: group.disabled,"
            " legend: legend ? legend.textContent : null,"
            " radios: Array.from(group.querySelectorAll('input[type=radio]')).map(input => ({"
            "   value: input.value, name: input.name, checked: input.checked,"
            "   label: input.labels.length ? input.labels[0].textContent : null})),"
            " main_wide: document.querySelector('.v-main').classList.contains('v-main-wide'),"
            " results_hidden: document.getElementById('results').hidden,"
            " outside_form: !document.getElementById('birth-form').contains(group)}; }"
        )
        check.note("before_first_document", before)
        check.equals("control element", before["tag"], "FIELDSET")
        check.equals("legend", before["legend"], "Chart style")
        check.equals("disabled before the first document", before["disabled"], True)
        check.equals(
            "radios",
            [(radio["value"], radio["name"], radio["label"]) for radio in before["radios"]],
            [(value, "chart-style", STYLE_LABELS[value]) for value in STYLE_VALUES],
        )
        check.equals(
            "checked before the first document",
            [radio["value"] for radio in before["radios"] if radio["checked"]],
            ["north"],
        )
        check.equals("v-main-wide before the first document", before["main_wide"], False)
        check.equals("outside the form", before["outside_form"], True)

        status, _document, _raw = style.generate()
        check.equals("status", status, 200)
        after = style.state()
        check.note("after_first_document", after)
        check.equals("disabled after the first document", after["disabled"], False)
        assert_style_table(check, after, "north", "present", "first document")
        check.require(
            after["north_svg"] and after["north_svg"]["width"] > 0,
            f"no North chart is drawn: {after['north_svg']}",
        )
        check.note("screenshot", style.screenshot("style_default_north_1280.png"))
    finally:
        style.close(check)


def check_style_switch_no_requests(check, context):
    style = StylePage(context)
    try:
        status, document, _raw = style.generate()
        check.equals("status", status, 200)
        style.page.evaluate(MARK_STYLE_NODES)
        form_before = style.page.evaluate(FORM_VALUES)
        rows_before = style.viewer.rows()
        submitted_before = style.viewer.text("#submitted-line")
        details_before = style.viewer.details("#birth-details")
        mark = style.mark()
        steps = []
        for value in ("south", "both", "north"):
            state = style.choose(value)
            steps.append({"to": value, "checked": state["checked"],
                          "north_visible": state["north"]["visible"],
                          "south_visible": state["south"]["visible"],
                          "data_stale": state["data_stale"],
                          "stale_banner_hidden": state["stale_banner"]["hidden"]})
            assert_style_table(check, state, value, "present", f"switch to {value}")
            check.equals(f"data-stale after switching to {value}", state["data_stale"], None)
            check.require(
                state["stale_banner"]["hidden"] is True,
                f"the stale banner appeared on switching to {value}",
            )
        style.page.wait_for_timeout(400)
        issued = style.since(mark)
        same = style.page.evaluate(SAME_STYLE_NODES)
        check.note("steps", steps)
        check.note("requests_during_switches", issued)
        check.note("same_nodes", same)
        check.equals("requests issued by three switches", issued, [])
        check.equals(
            "results subtree, North SVG and South SVG are the same nodes",
            same,
            {"body": True, "north": True, "south": True},
        )
        check.equals("form values", style.page.evaluate(FORM_VALUES), form_before)
        check.equals("form values are the submitted ones", form_before,
                     document["request"]["submitted"])
        check.equals("rows", style.viewer.rows(), rows_before)
        check.equals("results header line", style.viewer.text("#submitted-line"),
                     submitted_before)
        check.equals("birth details", style.viewer.details("#birth-details"), details_before)
    finally:
        style.close(check)


def check_style_one_calculation_per_generate(check, context):
    style = StylePage(context)
    mark = context.viewer_process.mark()
    try:
        first = birth_values(JALANDHAR)
        second = dict(first, time="07:45")
        status, _document, _raw = style.generate(values=first)
        check.equals("first status", status, 200)
        after_first = len(style.chart_requests())
        for value in ("south", "both"):
            style.choose(value)
        style.choose("south")
        status, document, _raw = style.generate(values=second)
        check.equals("second status", status, 200)
        after_second = len(style.chart_requests())
        state = style.state()
        assert_style_table(check, state, "south", "present", "after the second Generate")
        check.equals("second document shown", document["request"]["submitted"], second)
        for value in ("north", "both", "north"):
            style.choose(value)
        style.page.wait_for_timeout(400)
        total = len(style.chart_requests())
        server_lines = [
            entry["line"]
            for entry in context.viewer_process.stderr_since(mark)
            if entry["line"].startswith("api_chart ")
        ]
        counts = {
            "after_first_generate": after_first,
            "after_second_generate": after_second,
            "after_all_switches": total,
            "server_api_chart_lines": server_lines,
        }
        check.note("chart_requests", counts)
        check.equals("chart requests after the first Generate", after_first, 1)
        check.equals("chart requests after the second Generate", after_second, 2)
        check.equals("chart requests after every switch", total, 2)
        check.equals("server api_chart log lines", server_lines, ["api_chart 200", "api_chart 200"])
    finally:
        style.close(check)


def _both_layout(check, style, label):
    state = style.choose("both")
    north, south = state["north"], state["south"]
    measured = {
        "viewport": style.page.viewport_size,
        "north_block": north,
        "south_block": south,
        "north_svg": state["north_svg"],
        "south_svg": state["south_svg"],
        "charts_width": state["charts_width"],
        "main_width": state["main_width"],
        "main_max_width": state["main_max_width"],
        "main_wide": state["main_wide"],
        "north_wrapper": state["north_wrapper"],
        "south_wrapper": state["south_wrapper"],
        "north_hint": state["north_hint"],
        "south_hint": state["south_hint"],
        "page": state["page"],
    }
    check.note(label, measured)
    assert_style_table(check, state, "both", "present", label)
    assert_no_page_overflow(check, state, label)
    return state, measured


def check_style_both_side_by_side_1280(check, context):
    note_jammu(check, context)
    for name, birth in style_births(context):
        style = StylePage(context, DESKTOP_VIEWPORT)
        try:
            status, _document, _raw = style.generate(birth)
            check.equals(f"{name} status", status, 200)
            state, _measured = _both_layout(check, style, f"{name}_1280")
            check.equals(f"{name}: blocks share one top edge (offsetTop)",
                         state["north"]["offsetTop"], state["south"]["offsetTop"])
            check.require(
                abs(state["north"]["top"] - state["south"]["top"]) < 0.5,
                f"{name}: the blocks' top edges differ: {state['north']['top']} vs "
                f"{state['south']['top']}",
            )
            check.require(
                state["north"]["left"] + state["north"]["width"] <= state["south"]["left"],
                f"{name}: the South block is not to the right of the North block",
            )
            for side in ("north_svg", "south_svg"):
                check.require(
                    state[side] and state[side]["width"] >= 600,
                    f"{name}: {side} is narrower than 600 px: {state[side]}",
                )
            for side in ("north_wrapper", "south_wrapper"):
                wrapper = state[side]
                check.require(
                    wrapper["scrollWidth"] <= wrapper["clientWidth"],
                    f"{name}: {side} overflows at 1280 px: {wrapper}",
                )
            for side in ("north_hint", "south_hint"):
                check.require(state[side]["hidden"] is True,
                              f"{name}: {side} is shown at 1280 px")
            check.equals(f"{name}: v-main-wide", state["main_wide"], True)
            check.note(f"{name}_screenshot",
                       style.screenshot(f"style_both_side_by_side_{name}_1280.png"))
        finally:
            style.close(check)


def check_style_both_stacked_375(check, context):
    note_jammu(check, context)
    for name, birth in style_births(context):
        style = StylePage(context, MOBILE_VIEWPORT)
        try:
            status, _document, _raw = style.generate(birth)
            check.equals(f"{name} status", status, 200)
            state, _measured = _both_layout(check, style, f"{name}_375")
            check.require(
                state["south"]["offsetTop"] > state["north"]["offsetTop"],
                f"{name}: the blocks do not stack at 375 px: "
                f"{state['north']['offsetTop']} / {state['south']['offsetTop']}",
            )
            check.require(
                state["south"]["top"] >= state["north"]["top"] + state["north"]["height"],
                f"{name}: the South block does not start below the North block",
            )
            for side, hint in (("north_wrapper", "north_hint"), ("south_wrapper", "south_hint")):
                wrapper = state[side]
                check.require(
                    wrapper["scrollWidth"] > wrapper["clientWidth"],
                    f"{name}: {side} does not overflow at 375 px: {wrapper}",
                )
                check.require(state[hint]["hidden"] is False,
                              f"{name}: {hint} is hidden although its wrapper scrolls")
                check.equals(f"{name}: {hint} text", state[hint]["text"],
                             "Scroll horizontally to see the full chart.")
            for side in ("north_svg", "south_svg"):
                check.equals(f"{name}: {side} width at 375 px", state[side]["width"], 600)
            check.note(f"{name}_screenshot",
                       style.screenshot(f"style_both_stacked_{name}_375.png"))
        finally:
            style.close(check)


def check_style_both_threshold(check, context):
    style = StylePage(context, DESKTOP_VIEWPORT)
    try:
        status, _document, _raw = style.generate()
        check.equals("status", status, 200)
        style.choose("both")
        metrics = style.page.evaluate(LAYOUT_METRICS)
        north_block = metrics["north_min_width"] + metrics["north_padding"] + metrics["north_border"]
        south_block = metrics["south_min_width"] + metrics["south_padding"] + metrics["south_border"]
        charts = north_block + south_block + metrics["gap"]
        threshold = int(round(
            charts + metrics["body_padding"] + metrics["body_margin"]
            + metrics["html_padding"] + metrics["scrollbar"]
        ))
        computed = {
            "metrics_at_1280": metrics,
            "north_block_min": north_block,
            "south_block_min": south_block,
            "charts_min": charts,
            "formula": "2 x (600 + 2 x padding + 2 x border) + gap + body side "
                       "paddings + scrollbar width",
            "threshold": threshold,
        }
        check.note("computed", computed)
        check.equals("block minimum (section 6.3)", [north_block, south_block], [610.0, 610.0])
        check.equals(".v-charts minimum (section 6.3)", charts, 1228.0)
        check.require(metrics["main_max_width"] >= charts,
                      f"v-main-wide's max-width {metrics['main_max_width']} < {charts}")
        results = {}
        for width in (threshold, threshold - 1):
            style.set_viewport({"width": width, "height": DESKTOP_VIEWPORT["height"]})
            at = style.page.evaluate(LAYOUT_METRICS)
            state = style.state()
            side_by_side = state["north"]["offsetTop"] == state["south"]["offsetTop"]
            results[str(width)] = {
                "scrollbar": at["scrollbar"],
                "charts_width": state["charts_width"],
                "main_width": state["main_width"],
                "north_offsetTop": state["north"]["offsetTop"],
                "south_offsetTop": state["south"]["offsetTop"],
                "north_left": state["north"]["left"],
                "south_left": state["south"]["left"],
                "side_by_side": side_by_side,
                "page": state["page"],
            }
            assert_no_page_overflow(check, state, f"at {width} px")
            check.equals(f"scrollbar width at {width} px", at["scrollbar"], metrics["scrollbar"])
            style.screenshot(f"style_both_threshold_{width}.png")
        check.note("viewports", results)
        check.equals(f"side by side at the threshold {threshold} px",
                     results[str(threshold)]["side_by_side"], True)
        check.equals(f"stacked at {threshold - 1} px",
                     results[str(threshold - 1)]["side_by_side"], False)
        check.equals(".v-charts width at the threshold", results[str(threshold)]["charts_width"],
                     int(charts))
        context.measurements["style_both_threshold"] = {
            "threshold_px": threshold,
            "scrollbar_px": metrics["scrollbar"],
        }
    finally:
        style.close(check)


def check_style_single_layout_unchanged(check, context):
    style = StylePage(context, DESKTOP_VIEWPORT)
    try:
        status, _document, _raw = style.generate()
        check.equals("status", status, 200)
        measured = {}
        for viewport in (DESKTOP_VIEWPORT, MOBILE_VIEWPORT):
            style.set_viewport(viewport)
            for value in ("north", "south"):
                state = style.choose(value)
                metrics = style.page.evaluate(LAYOUT_METRICS)
                shown = state["north_svg"] if value == "north" else state["south_svg"]
                block = state["north"] if value == "north" else state["south"]
                content = min(1120.0, metrics["inner_width"] - metrics["body_padding"]
                              - metrics["scrollbar"])
                rule = max(600.0, min(1080.0, content - 10.0))
                key = f"{value}_{viewport['width']}"
                measured[key] = {
                    "main_max_width": state["main_max_width"],
                    "main_wide": state["main_wide"],
                    "main_width": state["main_width"],
                    "block_width": block["width"],
                    "chart_width": shown["width"] if shown else None,
                    "pre_layer19_rule": rule,
                    "pre_layer19_measured": PRE_LAYER19_CHART_WIDTH[viewport["width"]],
                    "page": state["page"],
                }
                assert_style_table(check, state, value, "present", key)
                check.equals(f"{key}: .v-main max-width", state["main_max_width"], "1120px")
                check.equals(f"{key}: no v-main-wide", state["main_wide"], False)
                check.equals(f"{key}: chart width (pre-Layer-19 rule)",
                             shown["width"] if shown else None, rule)
                check.equals(f"{key}: chart width (pre-Layer-19 measurement)",
                             shown["width"] if shown else None,
                             PRE_LAYER19_CHART_WIDTH[viewport["width"]])
                check.equals(f"{key}: the single block fills .v-main",
                             block["width"], state["main_width"])
                assert_no_page_overflow(check, state, key)
        check.note("measured", measured)
    finally:
        style.close(check)


def _fallback(check, context, mode):
    """Section 5.6 under one South state, for the three preferences."""
    mutations = {
        "missing": lambda document: document.pop("south_indian_svg", None),
        "malformed": lambda document: document.__setitem__("south_indian_svg", MALFORMED_SOUTH),
        "valid": lambda document: None,
    }
    south_state = {"missing": "missing", "malformed": "rejected", "valid": "present"}[mode]
    style = StylePage(context)
    log = []
    try:
        status, _document, _raw = style.generate()
        check.equals("first (unintercepted) status", status, 200)
        handler = intercept_south(style.page, mutations[mode], log)
        results = {}
        try:
            for preference in STYLE_VALUES:
                style.choose(preference)
                status, document, _raw = style.generate()
                check.equals(f"{preference}: status", status, 200)
                check.equals(
                    f"{preference}: the intercepted document's South key",
                    "south_indian_svg" in document,
                    mode != "missing",
                )
                state = style.state()
                assert_style_table(check, state, preference, south_state,
                                   f"{mode}/{preference} on arrival")
                results[preference] = {
                    "north_visible": state["north"]["visible"],
                    "south_visible": state["south"]["visible"],
                    "south_svg_count": state["south_svg_count"],
                    "south_message": state["south_message"],
                    "checked": state["checked"],
                    "main_wide": state["main_wide"],
                }
                style.screenshot(f"style_fallback_{mode}_{preference}.png")
                # And switching over the same document, without a request.
                mark = style.mark()
                for other in STYLE_VALUES:
                    switched = style.choose(other)
                    assert_style_table(check, switched, other, south_state,
                                       f"{mode}/{preference} switched to {other}")
                style.choose(preference)
                check.equals(f"{mode}/{preference}: requests by switching", style.since(mark), [])
        finally:
            style.page.unroute("**/api/chart", handler)
        check.note("table", results)
        check.note("intercepted", log)
        check.equals("intercepted responses", len(log), 3)
        # The preference survives; a valid document then shows South under it.
        style.choose("south")
        status, document, _raw = style.generate()
        check.equals("valid document status", status, 200)
        state = style.state()
        assert_style_table(check, state, "south", "present", f"{mode} then a valid document")
        check.note("then_valid", {"checked": state["checked"],
                                  "north_visible": state["north"]["visible"],
                                  "south_visible": state["south"]["visible"],
                                  "south_svg_count": state["south_svg_count"]})
    finally:
        style.close(check)


def check_style_fallback_missing(check, context):
    _fallback(check, context, "missing")


def check_style_fallback_malformed(check, context):
    _fallback(check, context, "malformed")


def check_style_fallback_valid(check, context):
    _fallback(check, context, "valid")


def _switch_over_previous(check, style, label, expect_busy=None):
    """Switch through the three styles over the shown document; no request."""
    mark = style.mark()
    steps = []
    for value in ("south", "both", "north"):
        state = style.choose(value)
        assert_style_table(check, state, value, "present", f"{label}: {value}")
        steps.append({"to": value, "busy": state["busy"], "disabled": state["disabled"],
                      "submitted_line": state["submitted_line"],
                      "alert_hidden": state["alert"]["hidden"]})
        if expect_busy is not None:
            check.equals(f"{label}: aria-busy while switching to {value}", state["busy"],
                         expect_busy)
        check.equals(f"{label}: control enabled while switching to {value}",
                     state["disabled"], False)
    style.page.wait_for_timeout(300)
    same = style.page.evaluate(SAME_STYLE_NODES)
    check.equals(f"{label}: the previous document's nodes", same,
                 {"body": True, "north": True, "south": True})
    check.equals(f"{label}: requests issued by the switches", style.since(mark), [])
    return steps


def check_style_during_loading(check, context):
    style = StylePage(context)
    held = []
    try:
        status, document, _raw = style.generate()
        check.equals("status", status, 200)
        previous_line = style.viewer.text("#submitted-line")
        style.page.evaluate(MARK_STYLE_NODES)
        handler = lambda route: held.append(route)  # noqa: E731 -- held, released below
        style.page.route("**/api/chart", handler)
        try:
            second = dict(birth_values(JALANDHAR), date="1995-03-22")
            style.click_generate_without_waiting(second)
            style.page.wait_for_function(
                "() => document.getElementById('results').getAttribute('aria-busy') === 'true'"
            )
            for _ in range(50):
                if held:
                    break
                style.page.wait_for_timeout(50)
            check.equals("requests held", len(held), 1)
            steps = _switch_over_previous(check, style, "while loading", expect_busy="true")
            check.note("switches_while_loading", steps)
            check.equals("previous document still shown",
                         style.viewer.text("#submitted-line"), previous_line)
            style.choose("south")
            held[0].continue_()
            style.page.wait_for_function(RESULTS_REPLACED, timeout=120000)
        finally:
            style.page.unroute("**/api/chart", handler)
        state = style.state()
        check.note("after_arrival", {"submitted_line": state["submitted_line"],
                                     "checked": state["checked"],
                                     "north_visible": state["north"]["visible"],
                                     "south_visible": state["south"]["visible"]})
        check.require("1995-03-22" in (state["submitted_line"] or ""),
                      f"the new document is not shown: {state['submitted_line']!r}")
        assert_style_table(check, state, "south", "present", "the new document, South kept")
        check.equals("chart requests", len(style.chart_requests()), 2)
    finally:
        style.close(check)


def check_style_after_failure(check, context):
    style = StylePage(context)
    cases = {}
    try:
        status, _document, _raw = style.generate()
        check.equals("status", status, 200)
        previous_line = style.viewer.text("#submitted-line")
        style.page.evaluate(MARK_STYLE_NODES)
        error_body = json.dumps(
            {"schema": "vedic_chart.viewer/2",
             "error": {"kind": "unexpected", "message": "injected by the acceptance script"}}
        )
        failures = {
            "injected_500": lambda route: route.fulfill(
                status=500, content_type="application/json; charset=utf-8", body=error_body
            ),
            "network_failure": lambda route: route.abort("failed"),
        }
        for name, handler in failures.items():
            style.page.route("**/api/chart", handler)
            try:
                style.click_generate_without_waiting(dict(birth_values(JALANDHAR),
                                                          date="1995-03-22"))
                style.page.wait_for_selector("#alert:not([hidden])", timeout=30000)
            finally:
                style.page.unroute("**/api/chart", handler)
            alert = style.viewer.text("#alert")
            steps = _switch_over_previous(check, style, name)
            state = style.state()
            cases[name] = {"alert": alert, "switches": steps,
                           "submitted_line": state["submitted_line"],
                           "alert_hidden_after_switches": state["alert"]["hidden"]}
            check.equals(f"{name}: previous document still shown", state["submitted_line"],
                         previous_line)
            check.equals(f"{name}: the alert stays", state["alert"]["hidden"], False)
            style.screenshot(f"style_after_failure_{name}.png")
        check.note("cases", cases)
        check.equals("chart requests (one success, two failures)",
                     len(style.chart_requests()), 3)
    finally:
        style.close(
            check,
            allowed_console=(
                r"status of 500",
                r"net::ERR_FAILED",
            ),
        )


def check_style_after_cancel(check, context):
    style = StylePage(context)
    held = []
    try:
        status, _document, _raw = style.generate()
        check.equals("status", status, 200)
        previous_line = style.viewer.text("#submitted-line")
        style.page.evaluate(MARK_STYLE_NODES)
        handler = lambda route: held.append(route)  # noqa: E731 -- held, released below
        style.page.route("**/api/chart", handler)
        outcome = {}
        try:
            # 1. #cancel.
            style.click_generate_without_waiting(dict(birth_values(JALANDHAR), date="1995-03-22"))
            for _ in range(60):
                if held:
                    break
                style.page.wait_for_timeout(50)
            style.page.click("#cancel")
            style.page.wait_for_function(
                "() => document.getElementById('status').textContent === 'Cancelled'"
            )
            outcome["cancel_status"] = style.viewer.text("#status")
            steps = _switch_over_previous(check, style, "after #cancel", expect_busy=None)
            outcome["switches_after_cancel"] = steps
            check.equals("after #cancel: previous document", style.viewer.text("#submitted-line"),
                         previous_line)
            # 2. Superseded by a newer submission: both held, the first aborted.
            style.click_generate_without_waiting(dict(birth_values(JALANDHAR), date="1995-03-23"))
            style.page.evaluate(
                "(values) => { const set = (id, value) => { const field = document.getElementById(id);"
                " field.value = value; field.dispatchEvent(new Event('input', {bubbles: true})); };"
                " set('birth-date', values.date); document.getElementById('generate').click(); }",
                {"date": "1995-03-24"},
            )
            for _ in range(60):
                if len(held) >= 3:
                    break
                style.page.wait_for_timeout(50)
            outcome["held_requests"] = len(held)
            outcome["status_while_superseding"] = style.viewer.text("#status")
            steps = _switch_over_previous(check, style, "superseded, pending", expect_busy="true")
            outcome["switches_while_superseded"] = steps
            style.choose("both")
        finally:
            style.page.unroute("**/api/chart", handler)
            released = []
            for route in held:
                try:
                    route.continue_()
                    released.append("continued")
                except Exception as error:  # noqa: BLE001 -- an aborted request cannot be continued
                    released.append(f"{type(error).__name__}")
            outcome["released"] = released
        style.page.wait_for_function(
            "() => { const line = document.getElementById('submitted-line');"
            " return line && line.textContent.indexOf('1995-03-24') !== -1; }",
            timeout=120000,
        )
        state = style.state()
        outcome["final"] = {"submitted_line": state["submitted_line"], "checked": state["checked"]}
        check.note("outcome", outcome)
        check.equals("held requests (cancelled, superseded, newest)", len(held), 3)
        assert_style_table(check, state, "both", "present", "the newest document, Both kept")
    finally:
        style.close(check)


def check_style_stale_preserved(check, context):
    style = StylePage(context)
    try:
        status, document, _raw = style.generate()
        check.equals("status", status, 200)
        style.page.fill("#birth-date", "1995-03-22")
        stale = style.state()
        banner = stale["stale_banner"]
        check.equals("data-stale after an edit", stale["data_stale"], "true")
        check.require(banner["hidden"] is False, "the stale banner is not shown after an edit")
        mark = style.mark()
        steps = []
        for value in ("south", "both", "north", "south"):
            state = style.choose(value)
            steps.append({"to": value, "data_stale": state["data_stale"],
                          "banner": state["stale_banner"]})
            check.equals(f"data-stale after switching to {value}", state["data_stale"], "true")
            check.equals(f"banner after switching to {value}", state["stale_banner"], banner)
            assert_style_table(check, state, value, "present", f"stale, {value}")
        style.page.wait_for_timeout(300)
        check.equals("requests issued by the switches", style.since(mark), [])
        check.equals("the edited field is untouched", style.page.input_value("#birth-date"),
                     "1995-03-22")
        style.page.fill("#birth-date", document["request"]["submitted"]["date"])
        restored = style.state()
        check.equals("data-stale after restoring", restored["data_stale"], None)
        check.note("stale_banner", banner)
        check.note("steps", steps)
        style.choose("north")
    finally:
        style.close(check)


def check_style_keyboard(check, context):
    style = StylePage(context)
    page = style.page
    try:
        status, _document, _raw = style.generate()
        check.equals("status", status, 200)
        page.focus("#generate")
        page.keyboard.press("Tab")
        entered = style.state()
        check.equals("Tab from Generate reaches the checked radio", entered["active"],
                     "chart-style-north")
        sequence = []
        for key, expected in (
            ("ArrowRight", "south"),
            ("ArrowRight", "both"),
            ("ArrowRight", "north"),
            ("ArrowLeft", "both"),
            ("ArrowUp", "south"),
            ("ArrowDown", "both"),
        ):
            page.keyboard.press(key)
            state = style.state()
            sequence.append({"key": key, "active": state["active"], "checked": state["checked"],
                             "north_visible": state["north"]["visible"],
                             "south_visible": state["south"]["visible"]})
            check.equals(f"{key} moves the focus", state["active"], f"chart-style-{expected}")
            assert_style_table(check, state, expected, "present", f"keyboard {key}")
        check.note("sequence", sequence)
        labels = page.evaluate(LABEL_STYLES)
        check.note("label_styles", labels)
        checked_labels = [label for label in labels if label["checked"]]
        unchecked = [label for label in labels if not label["checked"]]
        check.equals("one checked label", len(checked_labels), 1)
        for other in unchecked:
            check.require(
                (other["border"], other["background"])
                != (checked_labels[0]["border"], checked_labels[0]["background"]),
                f"the checked label looks like an unchecked one: {checked_labels[0]} / {other}",
            )
        page.keyboard.press("Tab")
        left = style.state()["active"]
        page.keyboard.press("Shift+Tab")
        back = style.state()["active"]
        check.note("tab_out_and_back", {"after_tab": left, "after_shift_tab": back})
        check.require(left not in ("chart-style-north", "chart-style-south", "chart-style-both"),
                      f"Tab did not leave the group: {left}")
        check.equals("Shift+Tab returns to the checked radio", back, "chart-style-both")

        group = page.get_by_role("group", name="Chart style")
        check.equals("groups named 'Chart style'", group.count(), 1)
        radios = []
        for value in STYLE_VALUES:
            radio = group.get_by_role("radio", name=STYLE_LABELS[value], exact=True)
            radios.append({"name": STYLE_LABELS[value], "count": radio.count(),
                           "checked": radio.is_checked() if radio.count() == 1 else None})
        check.note("accessible_radios", radios)
        check.equals("three labelled radios", [entry["count"] for entry in radios], [1, 1, 1])
        check.equals("accessible checked states", [entry["checked"] for entry in radios],
                     [False, False, True])
        aria = group.aria_snapshot()
        check.note("aria_snapshot", aria)
        check.require('group "Chart style"' in aria, f"no named group in {aria!r}")
        for value in STYLE_VALUES:
            check.require(f'radio "{STYLE_LABELS[value]}"' in aria,
                          f"no radio {STYLE_LABELS[value]!r} in {aria!r}")
        check.require('radio "Both" [checked]' in aria, f"Both is not checked in {aria!r}")

        # Section 6.5: focus inside a block that is hidden moves to the checked
        # radio. The North wrapper scrolls at 375 px, which makes it focusable.
        style.set_viewport(MOBILE_VIEWPORT)
        page.evaluate(CHOOSE_WITHOUT_FOCUS, "north")
        page.evaluate("() => document.getElementById('chart-wrapper').focus()")
        before = style.state()["active"]
        page.evaluate(CHOOSE_WITHOUT_FOCUS, "south")
        after = style.state()
        check.note("focus_in_hidden_block", {"before": before, "after": after["active"],
                                             "north_visible": after["north"]["visible"]})
        if before == "chart-wrapper":
            check.equals("focus moved to the checked radio", after["active"], "chart-style-south")
        else:
            check.note("focus_in_hidden_block_skipped",
                       f"the North wrapper did not take focus (active: {before!r})")
        check.note("screenshot", style.screenshot("style_keyboard_375.png"))
    finally:
        style.close(check)


def check_style_assumptions_and_dasha_preserved(check, context):
    style = StylePage(context)
    page = style.page
    try:
        values = {"date": JALANDHAR["date"], "time": "", "place_text": "", "place_id": ""}
        status, document, _raw = style.generate(values=values)
        check.equals("status", status, 200)
        check.equals("assumptions.any", document["assumptions"]["any"], True)
        labels = document["assumptions"]["labels"]
        check.equals("both values assumed", len(labels), 2)
        # Two levels: the first Mahadasha, then its first Antardasha.
        page.click("#dasha-body tr:nth-child(1) .v-cell-level")
        page.click("#dasha-body tr:nth-child(2) .v-cell-level")
        page.click("#dasha-body tr:nth-child(4) .v-cell-chain")
        before = page.evaluate(TREE_STATE)
        check.note("tree_before", before)
        check.require(len(before["expanded"]) == 2, f"two rows are not expanded: {before}")
        results = {}
        for value in ("south", "both", "north", "both"):
            page.evaluate(CHOOSE_WITHOUT_FOCUS, value)
            state = style.state()
            tree = page.evaluate(TREE_STATE)
            badges = page.evaluate(BADGES_AND_ASSUMPTIONS)
            results[value] = {"tree": tree, "badges": badges}
            assert_style_table(check, state, value, "present", f"assumed, {value}")
            check.equals(f"{value}: tree unchanged (rows, expanded, roving, focus)", tree, before)
            for name in ("results", "chart", "chart_south", "dasha"):
                check.equals(f"{value}: {name} badge", badges[name],
                             {"hidden": False, "text": ASSUMED_BADGE})
            check.equals(f"{value}: assumption list", badges["labels"], labels)
        # A pointer switch moves focus to the radio but leaves the tree's own
        # roving position and expansion alone.
        style.choose("south")
        tree = page.evaluate(TREE_STATE)
        check.equals("after a click: rows", tree["rows"], before["rows"])
        check.equals("after a click: expanded", tree["expanded"], before["expanded"])
        check.equals("after a click: roving row", tree["roving"], before["roving"])
        check.note("switches", results)
        check.note("screenshot", style.screenshot("style_assumed_south_1280.png"))
    finally:
        style.close(check)


def check_style_unique_ids(check, context):
    style = StylePage(context)
    try:
        status, _document, _raw = style.generate()
        check.equals("status", status, 200)
        style.choose("both")
        ids = style.page.evaluate(ALL_IDS)
        check.note("ids", ids)
        check.equals("duplicate ids", ids["duplicates"], [])
        check.equals(
            "North root",
            ids["north"],
            {"labelledby": "d1-title", "describedby": "d1-desc", "title_id": "d1-title",
             "desc_id": "d1-desc", "title_owner": True, "desc_owner": True},
        )
        check.equals(
            "South root",
            ids["south"],
            {"labelledby": "d1-south-title", "describedby": "d1-south-desc",
             "title_id": "d1-south-title", "desc_id": "d1-south-desc",
             "title_owner": True, "desc_owner": True},
        )
    finally:
        style.close(check)


def check_south_svg_bytes_equal_renderer(check, context):
    note_jammu(check, context)
    results = {}
    for name, birth in style_births(context):
        style = StylePage(context)
        try:
            status, document, raw = style.generate(birth)
            check.equals(f"{name} status", status, 200)
            (context.out / "responses" / f"style_{name}.json").write_bytes(raw)
            response_svg = document.get("south_indian_svg")
            (context.out / "svg" / f"{name}_south_response.svg").write_text(
                response_svg or "", encoding="utf-8"
            )
            rendered = renderer_documents(context, name, birth)
            entry = {
                "response_sha256": hashlib.sha256((response_svg or "").encode("utf-8")).hexdigest(),
                "renderer_sha256": hashlib.sha256(rendered["south"].encode("utf-8")).hexdigest(),
                "response_bytes": len((response_svg or "").encode("utf-8")),
                "north_response_equals_renderer": document["svg"] == rendered["north"],
                "key_order_tail": list(document)[-2:],
            }
            check.equals(f"{name}: south_indian_svg equals the renderer's bytes",
                         entry["response_sha256"], entry["renderer_sha256"])
            check.equals(f"{name}: svg is still the North Indian renderer's",
                         document["svg"], rendered["north"])
            # Layer 20 section 6.2 appends ``overlay`` after it, so the South
            # Indian key is now the last but one.
            check.equals(f"{name}: the key order tail", list(document)[-2:],
                         ["south_indian_svg", "overlay"])
            # The inserted node against the renderer's file, as svg_dom_semantics
            # does for the North chart.
            style.choose("south")
            live = style.page.eval_on_selector("#chart-south svg", SVG_SEMANTICS)
            scratch = context.scratch_page()
            scratch.set_content("<!doctype html><html><body></body></html>")
            parsed = scratch.evaluate(
                "(text) => { const parsedDocument = new DOMParser().parseFromString(text, 'image/svg+xml');"
                " return (" + SVG_SEMANTICS + ")(parsedDocument.documentElement); }",
                rendered["south"],
            )
            scratch.close()
            entry["inserted"] = {key: live[key] for key in
                                 ("role", "labelledby", "describedby", "title_text", "counts",
                                  "view_box")}
            check.equals(f"{name}: title", live["title_text"], SOUTH_TITLE)
            check.equals(f"{name}: role", live["role"], "img")
            for key in ("title_text", "desc_text", "view_box", "preserve_aspect_ratio", "counts"):
                check.equals(f"{name}: inserted {key}", live[key], parsed[key])
            results[name] = entry
        finally:
            style.close(check)
    check.note("documents", results)
    context.measurements["south_svg_sha256"] = results


def check_south_svg_pixels_equal_standalone(check, context):
    style = StylePage(context)
    results = {}
    try:
        status, _document, _raw = style.generate()
        check.equals("status", status, 200)
        style.choose("south")
        file_text = renderer_documents(context, "jalandhar", JALANDHAR)["south"]
        match = re.search(r'viewBox="0 0 (\d+) (\d+)"', file_text)
        view_width, view_height = int(match.group(1)), int(match.group(2))
        for width in PIXEL_WIDTHS:
            height = round(width * view_height / view_width)
            viewport = {"width": width + 120, "height": height + 120}
            style.page.set_viewport_size(viewport)
            argument = {
                "selector": "#chart-south svg",
                "width": width,
                "properties": list(PINNED_PROPERTIES),
            }
            pinned = style.page.evaluate(PIN_ELEMENT, argument)
            style.page.wait_for_timeout(120)
            inserted_path = context.out / "screenshots" / f"south_inserted_{width}.png"
            style.page.locator("#chart-south svg").screenshot(path=str(inserted_path))
            style.page.evaluate(
                UNPIN_ELEMENT, {"selector": "#chart-south svg", "saved": pinned["saved"]}
            )

            scratch = context.scratch_page()
            scratch.set_viewport_size(viewport)
            scratch.set_content(STANDALONE_PAGE)
            scratch.evaluate(
                "(text) => { const parsedDocument = new DOMParser()"
                ".parseFromString(text, 'image/svg+xml');"
                " document.body.appendChild(document.adoptNode(parsedDocument.documentElement)); }",
                file_text,
            )
            standalone_pinned = scratch.evaluate(
                PIN_ELEMENT,
                {"selector": "svg", "width": width, "properties": list(PINNED_PROPERTIES)},
            )
            scratch.wait_for_timeout(120)
            standalone_path = context.out / "screenshots" / f"south_standalone_{width}.png"
            scratch.locator("svg").screenshot(path=str(standalone_path))
            scratch.close()

            covered_rows = int(
                min(pinned["box"]["height"], standalone_pinned["box"]["height"])
            )
            comparison = compare_pngs(inserted_path, standalone_path, rows=covered_rows)
            comparison["width"] = width
            comparison["aspect_height"] = height
            comparison["boxes"] = {
                "inserted": pinned["box"],
                "standalone": standalone_pinned["box"],
            }
            comparison["note"] = (
                "every fully covered pixel row is compared, as "
                "svg_pixels_equal_standalone does for the North chart"
            )
            results[str(width)] = comparison
            check.equals(f"box at {width} px", pinned["box"], standalone_pinned["box"])
            check.require(
                comparison.get("differing_pixels") == 0,
                f"at {width} px the inserted South chart and the standalone file differ in "
                f"{comparison.get('differing_pixels')} pixels (sizes {comparison.get('size')})",
            )
    finally:
        check.note("comparisons", results)
        context.measurements["south_pixel_comparisons"] = results
        style.close(check)


def _overlaps(first, second, epsilon=BOUNDS_EPSILON_PX):
    width = min(first["right"], second["right"]) - max(first["left"], second["left"])
    height = min(first["bottom"], second["bottom"]) - max(first["top"], second["top"])
    return width > epsilon and height > epsilon


def _inside(inner, outer, epsilon=BOUNDS_EPSILON_PX):
    return (
        inner["left"] >= outer["left"] - epsilon
        and inner["top"] >= outer["top"] - epsilon
        and inner["right"] <= outer["right"] + epsilon
        and inner["bottom"] <= outer["bottom"] + epsilon
    )


def _expected_units(text):
    """The font size section 3.3 allows a text of this class, in user units."""
    cls = text["cls"]
    group = text["group"]
    if cls in ("sign-label", "house-label"):
        return ("label", (SOUTH_LABEL_UNITS,))
    if cls == "centre-label":
        return ("centre", (SOUTH_CENTRE_UNITS,))
    if cls in ("legend-marker", "legend-heading") or group == "legend-entry":
        return ("legend", (SOUTH_LEGEND_UNITS,))
    if group == "entry" or cls == "overflow":
        return ("entry", SOUTH_LADDER_UNITS)
    return ("unknown", ())


def judge_text_bounds(check, label, bounds):
    """Containment, overlap and effective sizes of one measured document."""
    scale = 600.0 / SOUTH_CANVAS
    texts = bounds["texts"]
    check.require(abs(bounds["svg_width"] - 600) < 0.01,
                  f"{label}: the chart is {bounds['svg_width']} px wide, not 600")
    check.require(abs(bounds["root_ctm_a"] - scale) < 1e-4,
                  f"{label}: the screen scale is {bounds['root_ctm_a']}, not 600/1080")
    outside = [
        {"cls": text["cls"], "content": text["content"], "region": text["region_name"],
         "box": text["box"], "region_box": text["region"]}
        for text in texts
        if text["region"] is None or not _inside(text["box"], text["region"])
    ]
    overlapping = []
    for index, first in enumerate(texts):
        for second in texts[index + 1:]:
            if _overlaps(first["box"], second["box"]):
                overlapping.append(
                    {"first": [first["cls"], first["content"], first["box"]],
                     "second": [second["cls"], second["content"], second["box"]]}
                )
    sizes = []
    wrong_sizes = []
    for text in texts:
        kind, allowed = _expected_units(text)
        effective = text["effective_px"]
        expected_px = text["font_units"] * scale
        entry = {"cls": text["cls"], "group": text["group"], "content": text["content"],
                 "font_units": text["font_units"], "ctm_a": text["ctm_a"],
                 "effective_px": round(effective, 4), "kind": kind,
                 "computed_font_size": text["computed_font_size"]}
        problems = []
        if text["font_units"] not in allowed:
            problems.append(f"font-size {text['font_units']} is not one of {allowed}")
        if abs(effective - expected_px) > FONT_TOLERANCE_PX:
            problems.append(f"effective {effective} != {expected_px}")
        figure = {
            "label": SOUTH_SPEC_PIXELS_600["label"],
            "centre": SOUTH_SPEC_PIXELS_600["centre"],
            "legend": SOUTH_SPEC_PIXELS_600["legend"],
        }.get(kind)
        if figure is not None and abs(effective - figure) > FONT_TOLERANCE_PX:
            problems.append(f"effective {effective} is not section 3.3's {figure} px")
        if kind == "entry" and effective < SOUTH_SPEC_PIXELS_600["entry_floor"] - FONT_TOLERANCE_PX:
            problems.append(f"entry text {effective} px is below the floor")
        if kind == "entry" and text["font_units"] == SOUTH_FLOOR_UNITS and abs(
            effective - SOUTH_SPEC_PIXELS_600["entry_floor"]
        ) > FONT_TOLERANCE_PX:
            problems.append(f"floor text {effective} px is not section 3.3's 11.67 px")
        if problems:
            wrong_sizes.append(dict(entry, problems=problems))
        sizes.append(entry)
    sign_labels = sorted(text["content"] for text in texts if text["cls"] == "sign-label")
    house_labels = {
        text["content"]: {"inside": _inside(text["box"], text["region"]) if text["region"] else False,
                          "region": text["region_name"],
                          "effective_px": round(text["effective_px"], 4)}
        for text in texts
        if text["cls"] == "house-label"
    }
    by_kind = {}
    for entry in sizes:
        by_kind.setdefault(entry["kind"], set()).add(entry["effective_px"])
    summary = {
        "texts": len(texts),
        "svg_width": bounds["svg_width"],
        "root_ctm_a": bounds["root_ctm_a"],
        "effective_px_by_kind": {kind: sorted(values) for kind, values in by_kind.items()},
        "overflow_texts": [text["content"] for text in texts if text["cls"] == "overflow"],
        "legend_headings": [text["content"] for text in texts if text["cls"] == "legend-heading"],
        "h10_h12": {name: house_labels.get(name) for name in ("H10", "H11", "H12")},
        "vrishchika": [
            {"box": text["box"], "region": text["region"]}
            for text in texts if text["content"] == "Vrishchika"
        ],
        "computed_font_size_example": sizes[0]["computed_font_size"] if sizes else None,
        "outside": outside,
        "overlapping": overlapping,
        "wrong_sizes": wrong_sizes,
    }
    check.equals(f"{label}: sign labels", sign_labels, sorted(RASHI_NAMES))
    check.equals(f"{label}: house labels", sorted(house_labels),
                 sorted(f"H{number}" for number in range(1, 13)))
    for name in ("H10", "H11", "H12"):
        check.require(house_labels.get(name, {}).get("inside") is True,
                      f"{label}: {name} is not inside its cell: {house_labels.get(name)}")
    check.equals(f"{label}: texts outside their cell or band", outside, [])
    check.equals(f"{label}: overlapping texts", overlapping, [])
    check.equals(f"{label}: texts at a size section 3.3 does not give", wrong_sizes, [])
    return summary


def check_south_text_bounds_600(check, context):
    note_jammu(check, context)
    style = StylePage(context, MOBILE_VIEWPORT)
    summaries = {}
    arguments = {"selector": "#chart-south svg", "margin": SOUTH_MARGIN,
                 "chartGap": SOUTH_CHART_GAP}
    try:
        for name, birth in style_births(context):
            status, _document, _raw = style.generate(birth)
            check.equals(f"{name} status", status, 200)
            style.choose("south")
            bounds = style.page.evaluate(TEXT_BOUNDS, arguments)
            (context.out / f"text_bounds_{name}.json").write_text(
                json.dumps(bounds, indent=1, ensure_ascii=False), encoding="utf-8"
            )
            summaries[name] = judge_text_bounds(check, name, bounds)
            style.screenshot(f"south_text_bounds_{name}_600.png")
        stress = stress_documents(context)
        for name in STRESS_CASES:
            log = []
            handler = intercept_south(
                style.page,
                lambda document, svg=stress[name]: document.__setitem__("south_indian_svg", svg),
                log,
            )
            try:
                status, document, _raw = style.generate()
            finally:
                style.page.unroute("**/api/chart", handler)
            check.equals(f"{name} status", status, 200)
            check.equals(f"{name}: served through the interception",
                         document["south_indian_svg"], stress[name])
            state = style.state()
            check.equals(f"{name}: South chart shown", state["south_svg_count"], 1)
            bounds = style.page.evaluate(TEXT_BOUNDS, arguments)
            (context.out / f"text_bounds_{name}.json").write_text(
                json.dumps(bounds, indent=1, ensure_ascii=False), encoding="utf-8"
            )
            summary = judge_text_bounds(check, name, bounds)
            check.equals(f"{name}: the overflow row", summary["overflow_texts"],
                         [STRESS_OVERFLOW[name]])
            check.require(len(summary["legend_headings"]) == 1,
                          f"{name}: not one complete-list legend: {summary['legend_headings']}")
            summaries[name] = summary
            style.screenshot(f"south_text_bounds_{name}_600.png")
    finally:
        check.note("documents", summaries)
        context.measurements["south_text_bounds_600"] = {
            name: {key: summary[key] for key in
                   ("texts", "effective_px_by_kind", "overflow_texts", "h10_h12")}
            for name, summary in summaries.items()
        }
        style.close(check)


def check_style_previews(check, context):
    """Full-page previews: each reference birth, each style, both viewports."""
    note_jammu(check, context)
    written = []
    for name, birth in style_births(context):
        for viewport in (DESKTOP_VIEWPORT, MOBILE_VIEWPORT):
            style = StylePage(context, viewport)
            try:
                status, _document, _raw = style.generate(birth)
                check.equals(f"{name} {viewport['width']} status", status, 200)
                for value in STYLE_VALUES:
                    state = style.choose(value)
                    assert_style_table(check, state, value, "present",
                                       f"{name} {value} {viewport['width']}")
                    assert_no_page_overflow(check, state, f"{name} {value} {viewport['width']}")
                    written.append(style.screenshot(
                        f"preview_{name}_{value}_{viewport['width']}.png"
                    ))
            finally:
                style.close(check)
    check.note("screenshots", written)


# --- Layer 20: the natal-transit overlay -----------------------------------------
#
# docs/LAYER20_TRANSIT_OVERLAY_SPEC.md section 10.4 and 10.6 to 10.12. Every
# check runs on pages of its own (TransitPage, a StylePage opened with
# #acceptance so that the composition fault seam of section 10.8 exists). The
# transit instant is 2026-10-08 14:30:00 at the natal record for both births.
#
# Two kinds of page are used for the races of section 10.10. On an ordinary
# page an invalidated request is aborted by the browser, so its body never
# reaches the page. On a "late body" page AbortController.prototype.abort is
# replaced by a counter before the page script runs, so every disowned
# request still delivers its body -- which is what proves that the page's own
# ownership guard, not the abort, keeps a late response out.

TRANSIT_A = ("2026-10-08", "14:30:00")
TRANSIT_B = ("2026-10-09", "10:00:00")
TRANSIT_C = ("2027-01-15", "08:00:00")
TRANSIT_D = ("2026-11-20", "18:45:00")
TRANSIT_YEARS = ("2026", "2027")
TRANSIT_FILL = "#c2410c"
TRANSIT_LADDER_UNITS = (32.0, 30.0, 28.0, 26.0, 24.0, 22.0, 21.0)
TRANSIT_ENTRY_FLOOR_UNITS = 21.0
TRANSIT_MARKER_UNITS = 20.0
TRANSIT_NORTH_CLEARANCE_UNITS = 15.0
TRANSIT_SOUTH_LABEL_GAP_UNITS = 9.0
TRANSIT_ENTRY_FLOOR_PX = 11.67
TRANSIT_MARKER_PX = 11.11
CALCULATING_TRANSITS = "Calculating transits…"
NEW_NATAL_TRANSIT = "Press Update to show transits for the new natal chart."
NATAL_STALE_TRANSIT = "Natal inputs changed — generate the natal chart first."
LONDON = {
    "date": "1995-03-21",
    "time": "06:45",
    "place_label": "London, England, United Kingdom",
    "geoname_id": 2643743,
}

LATE_BODY_SCRIPT = """
(() => {
  window.__abortCalls = 0;
  AbortController.prototype.abort = function () {
    window.__abortCalls = window.__abortCalls + 1;
  };
})();
"""

#: Everything the transit control and the overlay show at one moment.
TRANSIT_STATE = """
() => {
  const q = (id) => document.getElementById(id);
  const groups = Array.from(document.querySelectorAll('svg g.transit')).map(group => {
    const root = group.ownerSVGElement;
    return {
      root: root && root.closest('#chart-south') ? 'south' : 'north',
      display: group.getAttribute('display'),
      aria_hidden: group.getAttribute('aria-hidden'),
      painted_texts: Array.from(group.querySelectorAll('text'))
        .filter(text => text.getClientRects().length > 0).length,
      date: group.getAttribute('data-transit-date'),
      time: group.getAttribute('data-transit-time'),
      zone: group.getAttribute('data-transit-zone'),
      texts: group.querySelectorAll('text').length,
      cells: Array.from(group.querySelectorAll('g.transit-cell')).map(cell => cell.getAttribute('data-rashi')),
      parent_is_root: group.parentNode === root,
      last_child: root ? root.lastElementChild === group : false
    };
  });
  const describedby = (selector) => {
    const svg = document.querySelector(selector);
    return svg ? svg.getAttribute('aria-describedby') : null;
  };
  const resolvable = (value) => !value || value.split(/\\s+/).every(id => document.getElementById(id) !== null);
  const panel = q('transit-panel');
  return {
    toggle: q('transit-toggle').checked,
    disabled: q('transit').disabled,
    busy: q('transit').getAttribute('aria-busy'),
    status: q('transit-status').textContent,
    page_status: q('status').textContent,
    place: q('transit-place').textContent,
    date: q('transit-date').value,
    time: q('transit-time').value,
    stale: q('results').getAttribute('data-stale'),
    natal_busy: q('results').getAttribute('aria-busy'),
    groups: groups,
    north_groups: document.querySelectorAll('#chart svg g.transit').length,
    south_groups: document.querySelectorAll('#chart-south svg g.transit').length,
    north_desc_ids: document.querySelectorAll('[id="d1-transit-desc"]').length,
    south_desc_ids: document.querySelectorAll('[id="d1-south-transit-desc"]').length,
    north_describedby: describedby('#chart svg'),
    south_describedby: describedby('#chart-south svg'),
    heading_describedby: [q('chart-heading') ? q('chart-heading').getAttribute('aria-describedby') : null,
                          q('chart-south-heading') ? q('chart-south-heading').getAttribute('aria-describedby') : null],
    references_resolve: Array.from(document.querySelectorAll('[aria-describedby]'))
      .every(node => resolvable(node.getAttribute('aria-describedby'))),
    panel_hidden: panel ? panel.hidden : null,
    panel_rows: Array.from(document.querySelectorAll('#transit-panel-body tr'))
      .map(tr => Array.from(tr.children).map(td => td.textContent)),
    summary: q('transit-summary') ? q('transit-summary').textContent : null,
    assumed_hidden: q('transit-assumed') ? q('transit-assumed').hidden : null,
    submitted_line: q('submitted-line') ? q('submitted-line').textContent : null,
    active: document.activeElement ? document.activeElement.id : null,
    abort_calls: window.__abortCalls === undefined ? null : window.__abortCalls
  };
}
"""

#: The natal nodes of both roots, serialised without the transit group, and
#: the roots' own attributes, for "every natal node untouched".
NATAL_NODES = """
() => {
  const serialiser = new XMLSerializer();
  const read = (selector) => {
    const svg = document.querySelector(selector);
    if (!svg) return null;
    const children = Array.from(svg.children).filter(node => !node.matches('g.transit'));
    const attributes = {};
    Array.from(svg.attributes).forEach(attribute => {
      if (attribute.name !== 'aria-describedby') attributes[attribute.name] = attribute.value;
    });
    return {children: children.map(node => serialiser.serializeToString(node)), attributes: attributes};
  };
  return {north: read('#chart svg'), south: read('#chart-south svg')};
}
"""

MARK_TRANSIT_GROUPS = """
() => {
  window.__transitMarks = {
    north: document.querySelector('#chart svg g.transit'),
    south: document.querySelector('#chart-south svg g.transit')
  };
  return true;
}
"""

SAME_TRANSIT_GROUPS = """
() => {
  const marks = window.__transitMarks || {};
  return {
    north: marks.north !== null && marks.north === document.querySelector('#chart svg g.transit'),
    south: marks.south !== null && marks.south === document.querySelector('#chart-south svg g.transit')
  };
}
"""

#: Section 10.4 and 10.7: every transit text of one inserted document and the
#: natal geometry around it, mapped to CSS pixels through getScreenCTM().
TRANSIT_BOUNDS = """
(argument) => {
  const svg = document.querySelector(argument.selector);
  if (!svg) return null;
  const mapPoint = (element, x, y) => new DOMPoint(x, y).matrixTransform(element.getScreenCTM());
  const mapped = (element, box) => {
    const corners = [[box.x, box.y], [box.x + box.width, box.y],
                     [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]
      .map(([x, y]) => mapPoint(element, x, y));
    const xs = corners.map(point => point.x);
    const ys = corners.map(point => point.y);
    return {left: Math.min(...xs), top: Math.min(...ys),
            right: Math.max(...xs), bottom: Math.max(...ys)};
  };
  const north = argument.style === 'north';
  const cellSelector = north ? 'g.house' : 'g.sign';
  const cells = {};
  Array.from(svg.querySelectorAll(cellSelector)).forEach(group => {
    const rashi = group.getAttribute('data-rashi');
    let polygon;
    if (north) {
      const shape = group.querySelector('polygon.cell');
      polygon = shape.getAttribute('points').trim().split(/\\s+/).map(pair => {
        const [x, y] = pair.split(',').map(parseFloat);
        const point = mapPoint(shape, x, y);
        return [point.x, point.y];
      });
    } else {
      const rect = group.querySelector('rect.cell');
      const box = mapped(rect, rect.getBBox());
      polygon = [[box.left, box.top], [box.right, box.top], [box.right, box.bottom], [box.left, box.bottom]];
    }
    const numeral = group.querySelector('text.numeral');
    const signLabel = group.querySelector('text.sign-label');
    const houseLabel = group.querySelector('text.house-label');
    cells[rashi] = {
      house: group.getAttribute('data-house'),
      polygon: polygon,
      numeral: numeral ? mapped(numeral, numeral.getBBox()) : null,
      sign_label: signLabel ? mapped(signLabel, signLabel.getBBox()) : null,
      house_label: houseLabel ? mapped(houseLabel, houseLabel.getBBox()) : null
    };
  });
  const natalTexts = Array.from(svg.querySelectorAll('text')).filter(text => !text.closest('g.transit'))
    .map(text => {
      const cell = text.closest(cellSelector);
      return {cls: text.getAttribute('class'), content: text.textContent,
              rashi: cell ? cell.getAttribute('data-rashi') : null,
              box: mapped(text, text.getBBox())};
    });
  const natalLines = Array.from(svg.querySelectorAll('line.retro')).map(line => {
    const x1 = parseFloat(line.getAttribute('x1')), x2 = parseFloat(line.getAttribute('x2'));
    const y1 = parseFloat(line.getAttribute('y1')), half = parseFloat(line.getAttribute('stroke-width')) / 2;
    const cell = line.closest(cellSelector);
    return {cls: 'retro', content: line.getAttribute('data-graha'),
            rashi: cell ? cell.getAttribute('data-rashi') : null,
            box: mapped(line, {x: Math.min(x1, x2), y: y1 - half, width: Math.abs(x2 - x1), height: 2 * half})};
  });
  const transit = Array.from(svg.querySelectorAll('g.transit text')).map(text => {
    const matrix = text.getScreenCTM();
    const units = parseFloat(text.getAttribute('font-size'));
    const baseline = mapPoint(text, parseFloat(text.getAttribute('x')), parseFloat(text.getAttribute('y')));
    return {cls: text.getAttribute('class'), content: text.textContent,
            graha: text.getAttribute('data-graha'),
            rashi: text.closest('g.transit-cell').getAttribute('data-rashi'),
            underline: text.getAttribute('text-decoration'),
            fill: text.getAttribute('fill'),
            anchor: text.getAttribute('text-anchor'),
            font_units: units, effective_px: units * matrix.a,
            baseline_y: baseline.y, box: mapped(text, text.getBBox())};
  });
  const rootBox = svg.getBoundingClientRect();
  return {svg_width: rootBox.width, svg_height: rootBox.height,
          svg_left: rootBox.left, svg_top: rootBox.top,
          scale: svg.getScreenCTM().a, cells: cells, natal_texts: natalTexts,
          natal_lines: natalLines, transit: transit,
          group_display: svg.querySelector('g.transit') ? svg.querySelector('g.transit').getAttribute('display') : 'absent'};
}
"""


class ChartRouter:
    """``/api/chart`` interception for the transit checks.

    A request whose submitted date is in 2026 or 2027 is a transit request;
    anything else is natal. Each kind is passed through, held for a later
    release, or answered with an injected 500.
    """

    ERROR_BODY = json.dumps(
        {"schema": "vedic_chart.viewer/2",
         "error": {"kind": "unexpected", "message": "injected by the acceptance script"}}
    )

    def __init__(self, page):
        self.page = page
        self.transit_mode = "pass"
        self.natal_mode = "pass"
        self.held = []
        self.log = []
        page.route("**/api/chart", self.handle)

    def handle(self, route):
        try:
            body = json.loads(route.request.post_data or "{}")
        except ValueError:
            body = {}
        kind = "transit" if str(body.get("date", ""))[:4] in TRANSIT_YEARS else "natal"
        mode = self.transit_mode if kind == "transit" else self.natal_mode
        self.log.append({"kind": kind, "mode": mode, "date": body.get("date"),
                         "time": body.get("time")})
        if mode == "hold":
            self.held.append({"kind": kind, "route": route, "body": body})
        elif mode == "fail500":
            route.fulfill(status=500, content_type="application/json; charset=utf-8",
                          body=self.ERROR_BODY)
        else:
            route.continue_()

    def wait_held(self, count, timeout_ms=5000):
        waited = 0
        while len(self.held) < count and waited < timeout_ms:
            self.page.wait_for_timeout(50)
            waited += 50
        return len(self.held) >= count

    def release(self, entry, delivered):
        """Let one held request through; ``delivered`` waits for its answer."""
        outcome = "continued"
        try:
            if delivered:
                with self.page.expect_response(
                    lambda response: response.request == entry["route"].request, timeout=60000
                ):
                    entry["route"].continue_()
            else:
                entry["route"].continue_()
        except Exception as error:  # noqa: BLE001 -- an aborted request cannot be continued
            outcome = f"{type(error).__name__}"
        self.page.wait_for_timeout(400)
        return outcome

    def stop(self):
        try:
            self.page.unroute("**/api/chart", self.handle)
        except Exception:  # noqa: BLE001 -- a closed page has no routes
            pass


class TransitPage(StylePage):
    """A viewer page for one Layer 20 check, opened with #acceptance."""

    def __init__(self, context, viewport=None, late_bodies=False):
        super().__init__(context, viewport, hash_fragment="#acceptance",
                         init_script=LATE_BODY_SCRIPT if late_bodies else None)
        self.late_bodies = late_bodies

    def transit_state(self):
        return self.page.evaluate(TRANSIT_STATE)

    def chart_count(self):
        return len(self.chart_requests())

    def set_transit(self, instant):
        self.page.fill("#transit-date", instant[0])
        self.page.fill("#transit-time", instant[1])

    def answered(self, action, timeout=120000):
        """Run ``action`` and wait for the /api/chart answer it causes."""
        with self.page.expect_response(
            lambda response: response.url == self.api_url, timeout=timeout
        ) as caught:
            action()
        response = caught.value
        body = response.body()
        self.page.wait_for_timeout(150)
        try:
            return response.status, json.loads(body.decode("utf-8"))
        except ValueError:
            return response.status, None

    def toggle(self, on):
        if on:
            self.page.check("#transit-toggle")
        else:
            self.page.uncheck("#transit-toggle")

    def show_transits(self, instant=TRANSIT_A):
        """Fill the instant, turn the toggle on and wait for the overlay."""
        self.set_transit(instant)
        status, document = self.answered(lambda: self.toggle(True))
        self.page.wait_for_function(
            "() => { const g = document.querySelector('#chart svg g.transit');"
            " return g && g.getAttribute('display') === null; }",
            timeout=30000,
        )
        return status, document

    def update(self):
        self.page.click("#transit-update")


def dom_predicate(state):
    """``overlayVisible()`` evaluated by the test from the DOM alone.

    The page keeps at most one result and its groups are the only ``g.transit``
    elements, which carry the result's date and time; the natal object is the
    shown subtree they live in.
    """
    groups = state["groups"]
    return bool(
        state["toggle"]
        and not state["disabled"]
        and state["stale"] is None
        and state["natal_busy"] is None
        and groups
        and all(group["date"] == state["date"] and group["time"] == state["time"]
                for group in groups)
    )


def assert_transit_consistent(check, state, label, expect=None):
    """Section 6.4/6.5/5.6 invariants, after any step."""
    groups = state["groups"]
    shown = [group for group in groups if group["display"] is None]
    visible = bool(groups) and len(shown) == len(groups)
    check.require(len(shown) in (0, len(groups)),
                  f"{label}: some groups shown and some hidden: {groups}")
    check.require(state["north_groups"] <= 1 and state["south_groups"] <= 1,
                  f"{label}: more than one g.transit in a root: {state['north_groups']}/"
                  f"{state['south_groups']}")
    check.require(state["north_desc_ids"] <= 1 and state["south_desc_ids"] <= 1,
                  f"{label}: a transit desc id is repeated")
    check.require(all(group["parent_is_root"] and group["last_child"] for group in groups),
                  f"{label}: a transit group is not the last child of its root: {groups}")
    check.require(state["references_resolve"],
                  f"{label}: an aria-describedby reference does not resolve")
    check.equals(f"{label}: visibility equals overlayVisible() from the DOM",
                 visible, dom_predicate(state))
    # A hidden group is neither painted nor exposed; a shown one is both.
    check.equals(f"{label}: aria-hidden of the groups",
                 [group["aria_hidden"] for group in groups],
                 [None if group["display"] is None else "true" for group in groups])
    check.equals(f"{label}: no hidden group has a painted text",
                 [group["painted_texts"] for group in groups if group["display"] is not None],
                 [0 for group in groups if group["display"] is not None])
    check.equals(f"{label}: panel hidden", state["panel_hidden"], not visible)
    if state["north_describedby"] is not None:
        check.equals(f"{label}: North root description",
                     state["north_describedby"],
                     "d1-desc d1-transit-desc" if visible and state["north_groups"] else "d1-desc")
    if state["south_describedby"] is not None:
        check.equals(f"{label}: South root description",
                     state["south_describedby"],
                     "d1-south-desc d1-south-transit-desc"
                     if visible and state["south_groups"] else "d1-south-desc")
    check.equals(f"{label}: heading descriptions", state["heading_describedby"],
                 ["transit-summary", "transit-summary"] if visible else [None, None])
    if expect is not None:
        check.equals(f"{label}: overlay shown", visible, expect)
    return visible


def _point_in_polygon(point, polygon):
    x, y = point
    inside = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing:
                inside = not inside
    return inside


def _segment_distance(point, start, end):
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _box_points(box):
    left, top, right, bottom = box["left"], box["top"], box["right"], box["bottom"]
    points = []
    for fx in (0.0, 0.25, 0.5, 0.75, 1.0):
        points.append((left + (right - left) * fx, top))
        points.append((left + (right - left) * fx, bottom))
    for fy in (0.25, 0.5, 0.75):
        points.append((left, top + (bottom - top) * fy))
        points.append((right, top + (bottom - top) * fy))
    return points


def _box_inside_polygon(box, polygon, epsilon=BOUNDS_EPSILON_PX):
    shrunk = {"left": box["left"] + epsilon, "top": box["top"] + epsilon,
              "right": box["right"] - epsilon, "bottom": box["bottom"] - epsilon}
    corners = [(shrunk["left"], shrunk["top"]), (shrunk["right"], shrunk["top"]),
               (shrunk["left"], shrunk["bottom"]), (shrunk["right"], shrunk["bottom"])]
    return all(_point_in_polygon(corner, polygon) for corner in corners)


def _edge_distance(box, polygon):
    count = len(polygon)
    return min(
        _segment_distance(point, polygon[index], polygon[(index + 1) % count])
        for point in _box_points(box)
        for index in range(count)
    )


def _box_gap(first, second):
    dx = max(second["left"] - first["right"], first["left"] - second["right"], 0.0)
    dy = max(second["top"] - first["bottom"], first["top"] - second["bottom"], 0.0)
    return (dx * dx + dy * dy) ** 0.5


def judge_transit_placement(check, label, bounds, document):
    """Section 10.4: every transit text in the natal cell of its sign."""
    planets = {planet["key"]: planet for planet in document["planetary_positions"]["planets"]}
    misplaced = []
    in_own_house = []
    signs_seen = set()
    for text in bounds["transit"]:
        cell = bounds["cells"].get(text["rashi"])
        if cell is None or not _box_inside_polygon(text["box"], cell["polygon"]):
            misplaced.append({"content": text["content"], "rashi": text["rashi"],
                              "box": text["box"]})
            continue
        if text["graha"] is None:
            continue
        planet = planets[text["graha"]]
        signs_seen.add(text["rashi"])
        if str(planet["sign"]["number"]) != text["rashi"]:
            misplaced.append({"content": text["content"], "rashi": text["rashi"],
                              "planet_sign": planet["sign"]["number"]})
        own = [rashi for rashi, other in bounds["cells"].items()
               if other["house"] == str(planet["house"])]
        if own and own[0] != text["rashi"] and _box_inside_polygon(
            text["box"], bounds["cells"][own[0]]["polygon"]
        ):
            in_own_house.append({"content": text["content"], "transit_house": planet["house"]})
    check.equals(f"{label}: transit texts outside the natal cell of their sign", misplaced, [])
    check.equals(f"{label}: transit texts in the transit chart's own house cell", in_own_house, [])
    return {"texts": len(bounds["transit"]), "cells_with_entries": sorted(signs_seen, key=int)}


def underline_bands(png_bytes, bounds):
    """The rendered underline of every underlined transit abbreviation.

    The screenshot is of the <svg> element alone; a pixel row counts as part
    of the underline when at least 60 per cent of the text's own columns are
    orange-ish (red channel well above green and blue -- the natal ink is
    black and the paper white, so nothing else in the chart qualifies).
    """
    width, height, channels, pixels = decode_png(png_bytes)
    results = []
    for text in bounds["transit"]:
        if text["underline"] != "underline":
            continue
        left = int(text["box"]["left"] - bounds["svg_left"])
        right = int(text["box"]["right"] - bounds["svg_left"] + 0.999)
        top = int(text["box"]["top"] - bounds["svg_top"])
        bottom = int(text["box"]["bottom"] - bounds["svg_top"] + 0.999)
        columns = max(1, right - left)
        rows = []
        for y in range(max(0, top), min(height, bottom + columns)):
            orange = 0
            for x in range(max(0, left), min(width, right)):
                offset = (y * width + x) * channels
                r, g, b = pixels[offset], pixels[offset + 1], pixels[offset + 2]
                if r > g + 40 and r > b + 60:
                    orange += 1
            if orange >= 0.6 * columns:
                rows.append(y)
        baseline = text["baseline_y"] - bounds["svg_top"]
        entry = {"content": text["content"], "rashi": text["rashi"],
                 "baseline_px": round(baseline, 2),
                 "box_px": [round(text["box"]["top"] - bounds["svg_top"], 2),
                            round(text["box"]["bottom"] - bounds["svg_top"], 2)],
                 "underline_rows_px": [rows[0], rows[-1]] if rows else None}
        if rows:
            entry["below_baseline_px"] = round(rows[0] - baseline, 2)
            entry["clear_of_box_bottom_px"] = round(
                (text["box"]["bottom"] - bounds["svg_top"]) - (rows[-1] + 1), 2
            )
            # The next text below it in the same cell, natal or transit, that
            # shares any of its columns: the underline must end above it.
            below = [
                other["box"]["top"] - bounds["svg_top"]
                for other in bounds["natal_texts"] + bounds["transit"]
                if other["rashi"] == text["rashi"]
                and other["box"]["top"] > text["baseline_y"]
                and other["box"]["left"] < text["box"]["right"]
                and other["box"]["right"] > text["box"]["left"]
            ]
            entry["clear_of_next_text_px"] = (
                round(min(below) - (rows[-1] + 1), 2) if below else None
            )
            # The row's share of the 1.45 f pitch below its baseline is 0.70 f
            # (the renderers' rows: baseline = top + 0.75 f, pitch 1.45 f).
            row_bottom = baseline + 0.70 * text["effective_px"]
            entry["row_bottom_px"] = round(row_bottom, 2)
            entry["within_row_pitch_px"] = round(row_bottom - (rows[-1] + 1), 2)
            band = {"left": text["box"]["left"], "right": text["box"]["right"],
                    "top": rows[0] + bounds["svg_top"], "bottom": rows[-1] + 1 + bounds["svg_top"]}
            entry["overlaps_natal"] = [
                other["content"] for other in bounds["natal_texts"] + bounds["natal_lines"]
                if _overlaps(band, other["box"])
            ]
        results.append(entry)
    return results


def judge_transit_bounds(check, label, bounds, style):
    """Section 10.7 on the browser's own text bounds of one 600 px document."""
    scale = bounds["scale"]
    units = lambda px: px / scale  # noqa: E731 -- one conversion
    check.require(abs(bounds["svg_width"] - 600) < 0.01,
                  f"{label}: the chart is {bounds['svg_width']} px wide, not 600")
    natal = bounds["natal_texts"] + bounds["natal_lines"]
    overlaps_natal = []
    overlaps_transit = []
    outside = []
    fonts = []
    wrong_fonts = []
    markers = []
    texts = bounds["transit"]
    for index, text in enumerate(texts):
        cell = bounds["cells"][text["rashi"]]
        if not _box_inside_polygon(text["box"], cell["polygon"]):
            outside.append({"content": text["content"], "rashi": text["rashi"], "box": text["box"]})
        for other in natal:
            if _overlaps(text["box"], other["box"]):
                overlaps_natal.append({"transit": text["content"], "natal": other["content"],
                                       "rashi": text["rashi"]})
        for other in texts[index + 1:]:
            if _overlaps(text["box"], other["box"]):
                overlaps_transit.append([text["content"], other["content"]])
        entry = {"cls": text["cls"], "content": text["content"],
                 "font_units": text["font_units"], "effective_px": round(text["effective_px"], 4)}
        fonts.append(entry)
        if text["fill"] != TRANSIT_FILL:
            wrong_fonts.append(dict(entry, problem=f"fill {text['fill']}"))
        if text["cls"] == "transit-marker":
            if text["font_units"] != TRANSIT_MARKER_UNITS or abs(
                text["effective_px"] - TRANSIT_MARKER_PX
            ) > FONT_TOLERANCE_PX:
                wrong_fonts.append(dict(entry, problem="marker is not 20 units / 11.11 px"))
            measured = {"content": text["content"], "rashi": text["rashi"],
                        "anchor": text["anchor"]}
            if style == "north":
                measured["edge_units"] = round(units(_edge_distance(text["box"], cell["polygon"])), 2)
                measured["numeral_units"] = round(units(_box_gap(text["box"], cell["numeral"])), 2)
                gaps = [units(_box_gap(text["box"], other["box"]))
                        for other in bounds["natal_texts"]
                        if other["rashi"] == text["rashi"] and other["cls"] != "numeral"]
                gaps += [units(_box_gap(text["box"], other["box"]))
                         for other in bounds["natal_lines"] if other["rashi"] == text["rashi"]]
                measured["natal_units"] = round(min(gaps), 2) if gaps else None
                for key in ("edge_units", "numeral_units", "natal_units"):
                    value = measured[key]
                    check.require(
                        value is None or value >= TRANSIT_NORTH_CLEARANCE_UNITS - 0.01,
                        f"{label}: marker {text['content']} in sign {text['rashi']}: "
                        f"{key} {value} < 15",
                    )
            else:
                sign_gap = units(text["box"]["left"] - cell["sign_label"]["right"])
                house_gap = units(cell["house_label"]["left"] - text["box"]["right"])
                measured["sign_label_units"] = round(sign_gap, 2)
                measured["house_label_units"] = round(house_gap, 2)
                for key, value in (("sign_label_units", sign_gap), ("house_label_units", house_gap)):
                    check.require(
                        value >= TRANSIT_SOUTH_LABEL_GAP_UNITS - 0.01,
                        f"{label}: marker {text['content']} in sign {text['rashi']}: "
                        f"{key} {round(value, 2)} < 9",
                    )
            markers.append(measured)
        else:
            if text["font_units"] not in TRANSIT_LADDER_UNITS or (
                text["effective_px"] < TRANSIT_ENTRY_FLOOR_PX - FONT_TOLERANCE_PX
            ):
                wrong_fonts.append(dict(entry, problem="entry text below the 21-unit floor"))
    check.equals(f"{label}: transit texts outside their natal cell", outside, [])
    check.equals(f"{label}: transit texts overlapping natal text or lines", overlaps_natal, [])
    check.equals(f"{label}: transit texts overlapping each other", overlaps_transit, [])
    check.equals(f"{label}: transit texts at a size or colour section 10.7 does not allow",
                 wrong_fonts, [])
    entry_units = [entry["font_units"] for entry in fonts if entry["cls"] != "transit-marker"]
    gaps_natal = []
    for text in texts:
        same = [units(_box_gap(text["box"], other["box"])) for other in natal
                if other["rashi"] == text["rashi"] and other["cls"] not in ("numeral",)]
        if same:
            gaps_natal.append(min(same))
    return {
        "svg_width": bounds["svg_width"],
        "scale": scale,
        "transit_texts": len(texts),
        "min_entry_font_units": min(entry_units) if entry_units else None,
        "min_entry_effective_px": min(
            (entry["effective_px"] for entry in fonts if entry["cls"] != "transit-marker"),
            default=None,
        ),
        "marker_effective_px": sorted({entry["effective_px"] for entry in fonts
                                       if entry["cls"] == "transit-marker"}),
        "min_gap_to_natal_in_same_cell_units": round(min(gaps_natal), 2) if gaps_natal else None,
        "markers": markers,
    }


# -- the named checks -------------------------------------------------------------


def check_transit_control_default(check, context):
    """Section 3.1, 3.2 and 3.4: the control, its start state, the keyboard path."""
    page_ = TransitPage(context)
    page = page_.page
    try:
        before = page.evaluate(
            "() => { const group = document.getElementById('transit');"
            " return {tag: group.tagName, disabled: group.disabled,"
            " legend: group.querySelector('legend').textContent,"
            " toggle: document.getElementById('transit-toggle').checked,"
            " date: document.getElementById('transit-date').value,"
            " time: document.getElementById('transit-time').value,"
            " outside_form: !document.getElementById('birth-form').contains(group),"
            " after_style: Boolean(document.getElementById('chart-style').compareDocumentPosition(group)"
            "   & Node.DOCUMENT_POSITION_FOLLOWING),"
            " before_results: Boolean(group.compareDocumentPosition(document.getElementById('results'))"
            "   & Node.DOCUMENT_POSITION_FOLLOWING)}; }"
        )
        check.note("before_first_document", before)
        check.equals("before: control", before, {
            "tag": "FIELDSET", "disabled": True, "legend": "Transits", "toggle": False,
            "date": "", "time": "", "outside_form": True, "after_style": True,
            "before_results": True,
        })
        status, document, _raw = page_.generate()
        check.equals("natal status", status, 200)
        after = page_.transit_state()
        check.note("after_first_document", {key: after[key] for key in
                                            ("disabled", "toggle", "place", "status", "groups")})
        check.equals("enabled after the first document", after["disabled"], False)
        check.equals("toggle off", after["toggle"], False)
        check.equals("place line", after["place"],
                     "Local time at Jalandhar, Punjab, India — Asia/Kolkata (the natal birthplace)")
        assert_transit_consistent(check, after, "after the first document", expect=False)
        check.equals("no group before a request", after["groups"], [])

        # The accessibility tree (section 10.12): the checkbox, the fields, the button.
        names = {
            "checkbox": page.get_by_role("checkbox", name="Show transits").count(),
            "date": page.get_by_label("Transit date", exact=True).count(),
            "time": page.get_by_label("Transit time", exact=True).count(),
            "button": page.get_by_role("button", name="Update", exact=True).count(),
            "group": page.get_by_role("group", name="Transits").count(),
        }
        check.note("accessible_names", names)
        check.equals("accessible controls", names,
                     {"checkbox": 1, "date": 1, "time": 1, "button": 1, "group": 1})

        # Incomplete inputs: no request, the prompt, the toggle stays on.
        mark = page_.chart_count()
        page_.toggle(True)
        page.wait_for_timeout(300)
        state = page_.transit_state()
        check.equals("incomplete: no request", page_.chart_count() - mark, 0)
        check.equals("incomplete: status", state["status"], "Enter a transit date and time.")
        check.equals("incomplete: toggle stays on", state["toggle"], True)
        page_.toggle(False)

        # The keyboard path of section 3.2.
        page_.set_transit(TRANSIT_A)
        page.focus("#generate")
        visited = []
        for _ in range(14):
            page.keyboard.press("Tab")
            active = page_.transit_state()["active"]
            if not visited or visited[-1] != active:
                visited.append(active)
            if active not in ("chart-style-north", "transit-toggle", "transit-date",
                              "transit-time", "transit-update"):
                break
        check.note("tab_sequence", visited)
        check.equals("Tab order from Generate", visited[:5],
                     ["chart-style-north", "transit-toggle", "transit-date",
                      "transit-time", "transit-update"])
        page.focus("#transit-toggle")
        status, transit = page_.answered(lambda: page.keyboard.press("Space"))
        page.wait_for_function(
            "() => { const g = document.querySelector('#chart svg g.transit');"
            " return g && g.getAttribute('display') === null; }")
        state = page_.transit_state()
        check.equals("Space: transit status", status, 200)
        check.equals("Space: focus stays on the toggle", state["active"], "transit-toggle")
        assert_transit_consistent(check, state, "after Space", expect=True)
        check.equals("success status", state["status"],
                     "Transits for 2026-10-08 14:30:00 Asia/Kolkata (UTC+05:30) shown.")
        check.equals("mirrored to #status", state["page_status"], state["status"])
        # Enter in a transit field activates Update.
        page.fill("#transit-date", TRANSIT_B[0])
        page.fill("#transit-time", TRANSIT_B[1])
        page.focus("#transit-time")
        status, _transit = page_.answered(lambda: page.keyboard.press("Enter"))
        page.wait_for_timeout(200)
        state = page_.transit_state()
        check.equals("Enter in a field: status", status, 200)
        check.equals("Enter in a field: focus stays", state["active"], "transit-time")
        assert_transit_consistent(check, state, "after Enter in the time field", expect=True)
        check.equals("the natal form was not submitted by Enter",
                     state["submitted_line"], after["submitted_line"])
        # Enter on Update with nothing changed: no request, "already shown".
        mark = page_.chart_count()
        page.focus("#transit-update")
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
        state = page_.transit_state()
        check.equals("Update unchanged: no request", page_.chart_count() - mark, 0)
        check.equals("Update unchanged: status", state["status"],
                     "Transits for 2026-10-09 10:00:00 Asia/Kolkata (UTC+05:30) already shown.")
        check.equals("Update keeps focus", state["active"], "transit-update")
        check.note("screenshot", page_.screenshot("transit_control_1280.png"))
    finally:
        page_.close(check)


def check_transit_metadata_fallback(check, context):
    """Section 6.7: an unusable natal block disables the control, nothing else."""
    results = {}
    for mode, mutate in (
        ("missing", lambda document: document.pop("overlay", None)),
        ("malformed", lambda document: document["overlay"]["slots"]["north"].pop("12")),
    ):
        page_ = TransitPage(context)
        log = []
        try:
            status, _document, _raw = page_.generate()
            check.equals(f"{mode}: first status", status, 200)
            page_.show_transits()
            handler = intercept_south(page_.page, mutate, log)
            try:
                status, document, _raw = page_.generate(values=dict(birth_values(JALANDHAR),
                                                                    time="07:45"))
            finally:
                page_.page.unroute("**/api/chart", handler)
            state = page_.transit_state()
            style_state = page_.state()
            results[mode] = {"status": state["status"], "disabled": state["disabled"],
                             "toggle": state["toggle"], "groups": state["groups"]}
            check.equals(f"{mode}: natal status", status, 200)
            check.equals(f"{mode}: fieldset disabled", state["disabled"], True)
            check.equals(f"{mode}: toggle off", state["toggle"], False)
            check.require(
                state["status"].startswith(
                    "Transit overlay not available: the server did not provide usable "
                    "placement data ("
                ) and state["status"].endswith("). Reload the page or restart the viewer."),
                f"{mode}: status {state['status']!r}",
            )
            check.equals(f"{mode}: no transit group", state["groups"], [])
            assert_style_table(check, style_state, "north", "present", f"{mode}: natal shown")
            check.require("07:45" in (state["submitted_line"] or ""),
                          f"{mode}: the natal document was not applied")
            # A usable document enables the control again.
            status, _document, _raw = page_.generate()
            state = page_.transit_state()
            check.equals(f"{mode}: re-enabled by a usable document", state["disabled"], False)
        finally:
            page_.close(check)
    check.note("results", results)


def check_transit_sign_placement(check, context):
    """Section 10.4: by sign into the natal frame, never by the transit's houses."""
    note_jammu(check, context)
    summary = {}
    for name, birth in style_births(context):
        page_ = TransitPage(context, DESKTOP_VIEWPORT)
        try:
            status, natal, _raw = page_.generate(birth)
            check.equals(f"{name}: natal status", status, 200)
            status, transit = page_.show_transits()
            check.equals(f"{name}: transit status", status, 200)
            check.equals(f"{name}: time_assumed", transit["effective"]["time_assumed"], False)
            check.equals(f"{name}: source", transit["effective"]["source"], "selected")
            check.equals(f"{name}: the transit request names the natal record",
                         transit["effective"]["place"]["geoname_id"],
                         natal["effective"]["place"]["geoname_id"])
            page_.choose("both")
            entry = {
                "natal_lagna": natal["planetary_positions"]["ascendant"]["sign"]["name"]
                if isinstance(natal["planetary_positions"].get("ascendant"), dict) else None,
                "transit_lagna": transit["planetary_positions"]["ascendant"]["sign"]["name"]
                if isinstance(transit["planetary_positions"].get("ascendant"), dict) else None,
            }
            for style, selector in (("north", "#chart svg"), ("south", "#chart-south svg")):
                bounds = page_.page.evaluate(TRANSIT_BOUNDS, {"selector": selector, "style": style})
                entry[style] = judge_transit_placement(check, f"{name} {style}", bounds, transit)
                check.require(entry[style]["texts"] > 0, f"{name} {style}: no transit text drawn")
            summary[name] = entry
            check.note(f"{name}_screenshot",
                       page_.screenshot(f"transit_placement_{name}_both_1280.png"))
        finally:
            page_.close(check)
    check.note("placements", summary)


def check_transit_text_bounds_600(check, context):
    """Section 10.7: browser text bounds at a 600 px chart, both styles."""
    note_jammu(check, context)
    summaries = {}
    try:
        for name, birth in style_births(context):
            page_ = TransitPage(context, DESKTOP_VIEWPORT)
            try:
                status, _natal, _raw = page_.generate(birth)
                check.equals(f"{name}: natal status", status, 200)
                page_.show_transits()
                # At 1280 x 800 "Both" puts two 600 px charts side by side.
                page_.choose("both")
                page_.page.wait_for_timeout(200)
                for style, selector in (("north", "#chart svg"), ("south", "#chart-south svg")):
                    page_.page.locator(selector).scroll_into_view_if_needed()
                    bounds = page_.page.evaluate(
                        TRANSIT_BOUNDS, {"selector": selector, "style": style}
                    )
                    (context.out / f"transit_bounds_{name}_{style}.json").write_text(
                        json.dumps(bounds, indent=1, ensure_ascii=False), encoding="utf-8"
                    )
                    label = f"{name} {style}"
                    summary = judge_transit_bounds(check, label, bounds, style)
                    shot = context.out / "screenshots" / f"transit_bounds_{name}_{style}_600.png"
                    page_.page.locator(selector).screenshot(path=str(shot))
                    bands = underline_bands(shot.read_bytes(), bounds)
                    summary["underlines"] = bands
                    for band in bands:
                        check.require(band["underline_rows_px"] is not None,
                                      f"{label}: no rendered underline under {band['content']}")
                        if band["underline_rows_px"] is not None:
                            check.require(band["below_baseline_px"] >= -0.5,
                                          f"{label}: the underline of {band['content']} is above "
                                          f"its baseline: {band}")
                            check.require(band["within_row_pitch_px"] >= 0,
                                          f"{label}: the underline of {band['content']} leaves "
                                          f"its row pitch: {band}")
                            check.equals(f"{label}: natal boxes under the underline of "
                                         f"{band['content']}", band["overlaps_natal"], [])
                            check.require(band["clear_of_next_text_px"] is None
                                          or band["clear_of_next_text_px"] > 0,
                                          f"{label}: the underline of {band['content']} reaches "
                                          f"the next row: {band}")
                    summaries[f"{name}_{style}"] = summary
            finally:
                page_.close(check)
    finally:
        check.note("documents", summaries)
        context.measurements["transit_text_bounds_600"] = summaries


def check_transit_replacement(check, context):
    """Section 10.8: A -> B -> C replacement, then an injected composition fault."""
    page_ = TransitPage(context)
    page = page_.page
    steps = {}
    try:
        status, _natal, _raw = page_.generate()
        check.equals("natal status", status, 200)
        page_.choose("both")
        natal_nodes = page.evaluate(NATAL_NODES)
        page_.show_transits(TRANSIT_A)
        for name, instant in (("B", TRANSIT_B), ("C", TRANSIT_C)):
            page_.set_transit(instant)
            status, _document = page_.answered(page_.update)
            page.wait_for_timeout(200)
            state = page_.transit_state()
            steps[name] = {"groups": state["groups"], "status": state["status"]}
            check.equals(f"{name}: status", status, 200)
            assert_transit_consistent(check, state, f"after {name}", expect=True)
            check.equals(f"{name}: one group per root",
                         [state["north_groups"], state["south_groups"]], [1, 1])
            check.equals(f"{name}: one of each desc id",
                         [state["north_desc_ids"], state["south_desc_ids"]], [1, 1])
            check.equals(f"{name}: the groups are the new instant's",
                         sorted({(group["date"], group["time"]) for group in state["groups"]}),
                         [instant])
            check.equals(f"{name}: natal nodes untouched", page.evaluate(NATAL_NODES), natal_nodes)
        # Hidden: the root description is restored and the natal nodes equal.
        page_.toggle(False)
        state = page_.transit_state()
        assert_transit_consistent(check, state, "hidden after C", expect=False)
        check.equals("hidden: natal nodes untouched", page.evaluate(NATAL_NODES), natal_nodes)
        page_.toggle(True)
        page.wait_for_timeout(200)
        completed = page_.transit_state()
        assert_transit_consistent(check, completed, "C re-shown", expect=True)
        success_status = completed["status"]

        for fault, instant in (("south", TRANSIT_D), ("panel", TRANSIT_A)):
            page.evaluate(MARK_TRANSIT_GROUPS)
            rows_before = completed["panel_rows"]
            page.evaluate("(value) => { window.__transitComposeFault = value; }", fault)
            page_.set_transit(instant)
            mark = page_.chart_count()
            status, _document = page_.answered(page_.update)
            page.wait_for_timeout(250)
            failed = page_.transit_state()
            page.evaluate("() => { delete window.__transitComposeFault; }")
            steps[f"fault_{fault}"] = {"status": failed["status"], "groups": failed["groups"],
                                       "busy": failed["busy"]}
            check.equals(f"fault {fault}: one request", page_.chart_count() - mark, 1)
            check.equals(f"fault {fault}: response status", status, 200)
            check.require(
                failed["status"].startswith("Transit overlay could not be composed: injected"),
                f"fault {fault}: status {failed['status']!r}",
            )
            check.equals(f"fault {fault}: busy cleared", failed["busy"], None)
            check.equals(f"fault {fault}: the previous groups are the same nodes",
                         page.evaluate(SAME_TRANSIT_GROUPS), {"north": True, "south": True})
            check.equals(f"fault {fault}: no partial group",
                         [failed["north_groups"], failed["south_groups"]], [1, 1])
            check.equals(f"fault {fault}: the retained groups are C's",
                         sorted({(group["date"], group["time"]) for group in failed["groups"]}),
                         [TRANSIT_C])
            check.equals(f"fault {fault}: the panel is C's", failed["panel_rows"], rows_before)
            assert_transit_consistent(check, failed, f"fault {fault}", expect=False)
            # Restoring C's inputs shows C, with C's success status, no request.
            mark = page_.chart_count()
            page_.set_transit(TRANSIT_C)
            page.wait_for_timeout(250)
            restored = page_.transit_state()
            check.equals(f"fault {fault}: restoring C makes no request",
                         page_.chart_count() - mark, 0)
            assert_transit_consistent(check, restored, f"fault {fault}: C restored", expect=True)
            check.equals(f"fault {fault}: C's success status restored",
                         restored["status"], success_status)
            check.equals(f"fault {fault}: natal nodes untouched", page.evaluate(NATAL_NODES),
                         natal_nodes)
            completed = restored
        # Retry after the composition failure: the same inputs, a second request.
        page_.set_transit(TRANSIT_A)
        status, _document = page_.answered(page_.update)
        page.wait_for_timeout(200)
        state = page_.transit_state()
        assert_transit_consistent(check, state, "A after the faults", expect=True)
        check.equals("A after the faults: groups", sorted({(g["date"], g["time"])
                                                          for g in state["groups"]}), [TRANSIT_A])
        check.note("screenshot", page_.screenshot("transit_replacement_1280.png"))
    finally:
        check.note("steps", steps)
        page_.close(check)


def check_transit_request_counts(check, context):
    """Section 10.9: requests are made only by rules (a) and (b)."""
    page_ = TransitPage(context)
    page = page_.page
    counts = {}
    try:
        page_.generate()
        counts["natal_generate"] = page_.chart_count()
        page_.show_transits(TRANSIT_A)
        counts["toggle_on_with_inputs"] = page_.chart_count()
        for _ in range(5):
            page_.toggle(False)
            page_.toggle(True)
        page.wait_for_timeout(300)
        counts["off_on_x5"] = page_.chart_count()
        assert_transit_consistent(check, page_.transit_state(), "after off/on x5", expect=True)
        for value in ("south", "both", "north", "south", "both", "north"):
            page_.choose(value)
        page.wait_for_timeout(300)
        counts["styles_x6"] = page_.chart_count()
        assert_transit_consistent(check, page_.transit_state(), "after six switches", expect=True)
        page_.update()
        page.wait_for_timeout(300)
        counts["update_unchanged"] = page_.chart_count()
        page_.set_transit(TRANSIT_B)
        hidden = page_.transit_state()
        assert_transit_consistent(check, hidden, "edited, before Update", expect=False)
        check.equals("edited: status", hidden["status"],
                     "Transit inputs changed — press Update to show transits for "
                     "2026-10-09 10:00:00.")
        page_.answered(page_.update)
        counts["edit_then_update"] = page_.chart_count()
        assert_transit_consistent(check, page_.transit_state(), "B shown", expect=True)
        page_.set_transit(TRANSIT_C)
        page_.set_transit(TRANSIT_B)
        page.wait_for_timeout(300)
        counts["revert_to_shown_pair"] = page_.chart_count()
        assert_transit_consistent(check, page_.transit_state(), "reverted to B", expect=True)
        # Update while pending: held, then Update again.
        router = ChartRouter(page)
        try:
            router.transit_mode = "hold"
            page_.set_transit(TRANSIT_C)
            page_.update()
            router.wait_held(1)
            page_.update()
            page.evaluate("() => document.getElementById('transit-update').click()")
            page.wait_for_timeout(300)
            pending = page_.transit_state()
            counts["update_while_pending"] = page_.chart_count()
            check.equals("pending: status", pending["status"], CALCULATING_TRANSITS)
            check.equals("pending: aria-busy", pending["busy"], "true")
            router.transit_mode = "pass"
            router.release(router.held[0], delivered=True)
            page.wait_for_timeout(200)
            assert_transit_consistent(check, page_.transit_state(), "C after release", expect=True)
        finally:
            router.stop()
        # Rapid edits: twenty input events, no request.
        mark = page_.chart_count()
        page.evaluate(
            "() => { const field = document.getElementById('transit-time');"
            " for (let index = 0; index < 20; index++) {"
            "   field.value = '1' + String(index % 10) + ':0' + String(index % 6) + ':00';"
            "   field.dispatchEvent(new Event('input', {bubbles: true})); } }"
        )
        page.wait_for_timeout(500)
        counts["rapid_edits_requests"] = page_.chart_count() - mark
        # Duplicate: Update twice in one task, one request.
        mark = page_.chart_count()
        page.evaluate(
            "() => { const button = document.getElementById('transit-update');"
            " button.click(); button.click(); }"
        )
        page.wait_for_function(
            "() => document.getElementById('transit').getAttribute('aria-busy') === null",
            timeout=60000)
        page.wait_for_timeout(300)
        counts["duplicate_update_requests"] = page_.chart_count() - mark
        assert_transit_consistent(check, page_.transit_state(), "after the duplicate", expect=True)
    finally:
        check.note("counts", counts)
        page_.close(check)
    check.equals("natal Generate", counts.get("natal_generate"), 1)
    check.equals("toggle on with inputs", counts.get("toggle_on_with_inputs"), 2)
    check.equals("off/on x5", counts.get("off_on_x5"), 2)
    check.equals("North/South/Both x6", counts.get("styles_x6"), 2)
    check.equals("Update unchanged", counts.get("update_unchanged"), 2)
    check.equals("edit then Update", counts.get("edit_then_update"), 3)
    check.equals("revert to the shown pair", counts.get("revert_to_shown_pair"), 3)
    check.equals("Update while pending (one more request)", counts.get("update_while_pending"), 4)
    check.equals("rapid edits", counts.get("rapid_edits_requests"), 0)
    check.equals("duplicate Update", counts.get("duplicate_update_requests"), 1)


def _race_page(context, late_bodies):
    page_ = TransitPage(context, late_bodies=late_bodies)
    status, _document, _raw = page_.generate()
    if status != 200:
        raise RuntimeError(f"natal status {status}")
    return page_, ChartRouter(page_.page)


def _race_edit_during_loading(check, page_, router, label):
    router.transit_mode = "hold"
    page_.set_transit(TRANSIT_A)
    page_.toggle(True)
    router.wait_held(1)
    check.equals(f"{label}: busy while A is held", page_.transit_state()["busy"], "true")
    page_.page.fill("#transit-date", TRANSIT_B[0])
    edited = page_.transit_state()
    check.equals(f"{label}: the edit clears aria-busy", edited["busy"], None)
    check.require(edited["status"].startswith("Transit inputs changed"),
                  f"{label}: status after the edit {edited['status']!r}")
    outcome = router.release(router.held[0], delivered=page_.late_bodies)
    state = page_.transit_state()
    check.equals(f"{label}: A not applied", state["groups"], [])
    check.equals(f"{label}: status unchanged by A", state["status"], edited["status"])
    assert_transit_consistent(check, state, f"{label}: after A", expect=False)
    router.transit_mode = "pass"
    page_.answered(page_.update)
    state = page_.transit_state()
    assert_transit_consistent(check, state, f"{label}: B applied", expect=True)
    return {"release_A": outcome, "groups": [(g["date"], g["time"]) for g in state["groups"]]}


def _race_off_on(check, page_, router, label):
    router.transit_mode = "hold"
    page_.set_transit(TRANSIT_A)
    page_.toggle(True)
    router.wait_held(1)
    page_.toggle(False)
    page_.toggle(True)
    router.wait_held(2)
    check.equals(f"{label}: B started", len(router.held), 2)
    outcome = router.release(router.held[0], delivered=page_.late_bodies)
    state = page_.transit_state()
    check.equals(f"{label}: B still pending (busy)", state["busy"], "true")
    check.equals(f"{label}: B's status intact", state["status"], CALCULATING_TRANSITS)
    check.equals(f"{label}: nothing drawn by A", state["groups"], [])
    router.transit_mode = "pass"
    router.release(router.held[1], delivered=True)
    state = page_.transit_state()
    assert_transit_consistent(check, state, f"{label}: B applied", expect=True)
    return {"release_A": outcome}


def _race_edit_restore(check, page_, router, label):
    router.transit_mode = "hold"
    page_.set_transit(TRANSIT_A)
    page_.toggle(True)
    router.wait_held(1)
    page_.page.fill("#transit-date", TRANSIT_B[0])
    mark = page_.chart_count()
    page_.page.fill("#transit-date", TRANSIT_A[0])
    page_.page.wait_for_timeout(300)
    check.equals(f"{label}: restoring makes no request", page_.chart_count() - mark, 0)
    assert_transit_consistent(check, page_.transit_state(), f"{label}: restored", expect=False)
    outcome = router.release(router.held[0], delivered=page_.late_bodies)
    state = page_.transit_state()
    check.equals(f"{label}: A ignored", state["groups"], [])
    router.transit_mode = "pass"
    page_.answered(page_.update)
    assert_transit_consistent(check, page_.transit_state(), f"{label}: C applied", expect=True)
    return {"release_A": outcome}


def _race_off_during_loading(check, page_, router, label):
    router.transit_mode = "hold"
    page_.set_transit(TRANSIT_A)
    page_.toggle(True)
    router.wait_held(1)
    page_.toggle(False)
    outcome = router.release(router.held[0], delivered=page_.late_bodies)
    state = page_.transit_state()
    check.equals(f"{label}: nothing drawn", state["groups"], [])
    check.equals(f"{label}: toggle still off", state["toggle"], False)
    check.equals(f"{label}: status", state["status"], "Transits off.")
    assert_transit_consistent(check, state, label, expect=False)
    return {"release_A": outcome}


def _race_natal_edit(check, page_, router, label):
    router.transit_mode = "hold"
    page_.set_transit(TRANSIT_A)
    page_.toggle(True)
    router.wait_held(1)
    page_.page.fill("#birth-date", "1995-03-22")
    stale = page_.transit_state()
    check.equals(f"{label}: stale status", stale["status"], NATAL_STALE_TRANSIT)
    check.equals(f"{label}: busy cleared", stale["busy"], None)
    page_.page.fill("#birth-date", JALANDHAR["date"])
    reverted = page_.transit_state()
    assert_transit_consistent(check, reverted, f"{label}: natal reverted", expect=False)
    outcome = router.release(router.held[0], delivered=page_.late_bodies)
    check.equals(f"{label}: A discarded", page_.transit_state()["groups"], [])
    router.transit_mode = "pass"
    mark = page_.chart_count()
    page_.answered(page_.update)
    check.equals(f"{label}: Update makes one request", page_.chart_count() - mark, 1)
    assert_transit_consistent(check, page_.transit_state(), f"{label}: applied", expect=True)
    return {"release_A": outcome}


def _race_natal_generate(check, page_, router, label):
    outcome = {}
    router.transit_mode = "hold"
    page_.set_transit(TRANSIT_A)
    page_.toggle(True)
    router.wait_held(1)
    status, _document, _raw = page_.generate(values=dict(birth_values(JALANDHAR), time="07:45"))
    check.equals(f"{label}: natal status", status, 200)
    state = page_.transit_state()
    check.equals(f"{label}: fieldset enabled", state["disabled"], False)
    check.equals(f"{label}: status", state["status"], NEW_NATAL_TRANSIT)
    check.equals(f"{label}: no transit result", state["groups"], [])
    outcome["release_A"] = router.release(router.held[0], delivered=page_.late_bodies)
    state = page_.transit_state()
    check.equals(f"{label}: A ignored", state["groups"], [])
    assert_transit_consistent(check, state, f"{label}: new natal", expect=False)
    router.transit_mode = "pass"
    page_.answered(page_.update)
    shown_state = page_.transit_state()
    assert_transit_consistent(check, shown_state, f"{label}: shown on the new natal", expect=True)
    # An injected natal 500: shown unchanged; hidden while stale; back on revert.
    router.natal_mode = "fail500"
    page_.click_generate_without_waiting(dict(birth_values(JALANDHAR), time="08:45"))
    page_.page.wait_for_selector("#alert:not([hidden])", timeout=30000)
    router.natal_mode = "pass"
    failed = page_.transit_state()
    check.equals(f"{label}: 500 leaves the natal document",
                 failed["submitted_line"], shown_state["submitted_line"])
    assert_transit_consistent(check, failed, f"{label}: after the natal 500 (stale)", expect=False)
    page_.fill(dict(birth_values(JALANDHAR), time="07:45"))
    back = page_.transit_state()
    assert_transit_consistent(check, back, f"{label}: natal form reverted", expect=True)
    # The transit inputs changed in between: stays hidden after the revert.
    page_.page.fill("#birth-date", "1995-03-22")
    page_.set_transit(TRANSIT_B)
    page_.page.fill("#birth-date", JALANDHAR["date"])
    assert_transit_consistent(check, page_.transit_state(),
                              f"{label}: natal reverted, transit changed", expect=False)
    mark = page_.chart_count()
    page_.set_transit(TRANSIT_A)
    page_.page.wait_for_timeout(250)
    check.equals(f"{label}: transit reverted, no request", page_.chart_count() - mark, 0)
    assert_transit_consistent(check, page_.transit_state(),
                              f"{label}: both reverted", expect=True)
    return outcome


def _race_natal_cancel(check, page_, router, label):
    page_.show_transits(TRANSIT_A)
    shown_state = page_.transit_state()
    router.natal_mode = "hold"
    page_.click_generate_without_waiting(dict(birth_values(JALANDHAR), date="1995-03-22"))
    router.wait_held(1)
    loading = page_.transit_state()
    assert_transit_consistent(check, loading, f"{label}: natal loading", expect=False)
    page_.page.click("#cancel")
    page_.page.wait_for_function(
        "() => document.getElementById('status').textContent === 'Cancelled'")
    router.natal_mode = "pass"
    cancelled = page_.transit_state()
    check.equals(f"{label}: shown unchanged", cancelled["submitted_line"],
                 shown_state["submitted_line"])
    assert_transit_consistent(check, cancelled, f"{label}: cancelled, form stale", expect=False)
    page_.page.fill("#birth-date", JALANDHAR["date"])
    assert_transit_consistent(check, page_.transit_state(), f"{label}: form reverted", expect=True)
    try:
        router.held[0]["route"].continue_()
    except Exception:  # noqa: BLE001 -- the cancelled request is gone
        pass
    return {}


def _race_completed_visibility(check, page_, router, label):
    """The three required visibility cases of section 6.4."""
    page_.show_transits(TRANSIT_A)
    mark = page_.chart_count()
    # 1. completed A -> off -> edit and revert the transit inputs: hidden.
    page_.toggle(False)
    page_.set_transit(TRANSIT_B)
    assert_transit_consistent(check, page_.transit_state(), f"{label}: off, edited", expect=False)
    page_.set_transit(TRANSIT_A)
    assert_transit_consistent(check, page_.transit_state(), f"{label}: off, reverted", expect=False)
    page_.toggle(True)
    assert_transit_consistent(check, page_.transit_state(), f"{label}: on again", expect=True)
    # 2. completed A -> natal edit -> change transit -> revert natal: hidden;
    #    revert transit: A shown, no request.
    page_.page.fill("#birth-date", "1995-03-22")
    state = page_.transit_state()
    assert_transit_consistent(check, state, f"{label}: natal edited", expect=False)
    check.equals(f"{label}: natal edited status", state["status"], NATAL_STALE_TRANSIT)
    page_.set_transit(TRANSIT_B)
    page_.page.fill("#birth-date", JALANDHAR["date"])
    assert_transit_consistent(check, page_.transit_state(), f"{label}: natal reverted", expect=False)
    page_.set_transit(TRANSIT_A)
    state = page_.transit_state()
    assert_transit_consistent(check, state, f"{label}: transit reverted", expect=True)
    check.require(state["status"].startswith("Transits for 2026-10-08 14:30:00"),
                  f"{label}: re-shown status {state['status']!r}")
    # 3. completed A, on, edit then restore: re-shown with no request.
    page_.set_transit(TRANSIT_C)
    assert_transit_consistent(check, page_.transit_state(), f"{label}: edited on", expect=False)
    page_.set_transit(TRANSIT_A)
    assert_transit_consistent(check, page_.transit_state(), f"{label}: restored on", expect=True)
    page_.page.wait_for_timeout(250)
    check.equals(f"{label}: no request in all three cases", page_.chart_count() - mark, 0)
    return {}


def _race_retry(check, page_, router, label):
    router.transit_mode = "fail500"
    page_.set_transit(TRANSIT_A)
    mark = page_.chart_count()
    page_.answered(lambda: page_.toggle(True))
    failed = page_.transit_state()
    check.equals(f"{label}: failure status", failed["status"],
                 "Transits could not be calculated: injected by the acceptance script")
    check.equals(f"{label}: nothing drawn", failed["groups"], [])
    check.equals(f"{label}: toggle stays on", failed["toggle"], True)
    router.transit_mode = "pass"
    page_.answered(page_.update)
    check.equals(f"{label}: a second request", page_.chart_count() - mark, 2)
    assert_transit_consistent(check, page_.transit_state(), f"{label}: retried", expect=True)
    return {}


RACES = (
    ("edit_during_loading", _race_edit_during_loading, (True, False)),
    ("off_on", _race_off_on, (True, False)),
    ("edit_restore", _race_edit_restore, (True, False)),
    ("off_during_loading", _race_off_during_loading, (True, False)),
    ("natal_edit_during_loading", _race_natal_edit, (True, False)),
    ("natal_generate_during_loading", _race_natal_generate, (True, False)),
    ("natal_cancel", _race_natal_cancel, (False,)),
    ("completed_visibility", _race_completed_visibility, (False,)),
    ("retry", _race_retry, (False,)),
)


def check_transit_races(check, context):
    """Section 10.10, with held responses; late bodies delivered or aborted."""
    results = {}
    for name, scenario, modes in RACES:
        for late in modes:
            label = f"{name}{' (late body)' if late else ''}"
            page_, router = _race_page(context, late)
            try:
                results[label] = scenario(check, page_, router, label)
                state = page_.transit_state()
                results[label]["abort_calls"] = state["abort_calls"]
                results[label]["requests"] = [(entry["kind"], entry["mode"]) for entry in router.log]
            finally:
                router.stop()
                for entry in router.held:
                    try:
                        entry["route"].continue_()
                    except Exception:  # noqa: BLE001 -- already handled or aborted
                        pass
                page_.close(check, allowed_console=(r"status of 500",))
    check.note("scenarios", results)


def check_transit_errors(check, context):
    """Section 10.6: errors in #transit-status, nothing drawn, no fallback."""
    page_ = TransitPage(context)
    results = {}
    try:
        values = {"date": LONDON["date"], "time": LONDON["time"],
                  "place_text": LONDON["place_label"], "place_id": str(LONDON["geoname_id"])}
        status, natal, _raw = page_.generate(values=values)
        check.equals("London natal status", status, 200)
        check.equals("London zone", natal["location"]["timezone_id"], "Europe/London")
        first = True
        for name, instant in (("dst_gap", ("2026-03-29", "01:30:00")),
                              ("dst_ambiguous", ("2026-10-25", "01:30:00"))):
            page_.set_transit(instant)
            if first:
                status, document = page_.answered(lambda: page_.toggle(True))
                first = False
            else:
                status, document = page_.answered(page_.update)
            state = page_.transit_state()
            results[name] = {"status": status, "kind": (document or {}).get("error", {}).get("kind"),
                             "line": state["status"]}
            check.equals(f"{name}: 400", status, 400)
            check.equals(f"{name}: input", results[name]["kind"], "input")
            check.require(state["status"].startswith("Transit time not accepted: "),
                          f"{name}: status {state['status']!r}")
            check.equals(f"{name}: nothing drawn", state["groups"], [])
            check.equals(f"{name}: toggle stays on", state["toggle"], True)
            check.equals(f"{name}: the natal alert is untouched", page_.state()["alert"]["hidden"], True)
        # Summer and winter: the offset is the transit instant's own.
        for name, instant, offset in (("summer", ("2026-07-01", "12:00:00"), "+01:00"),
                                      ("winter", ("2026-12-01", "12:00:00"), "+00:00")):
            page_.set_transit(instant)
            status, document = page_.answered(page_.update)
            state = page_.transit_state()
            results[name] = {"line": state["status"], "time_assumed":
                             document["effective"]["time_assumed"]}
            check.equals(f"{name}: time_assumed", document["effective"]["time_assumed"], False)
            check.equals(f"{name}: status", state["status"],
                         f"Transits for {instant[0]} {instant[1]} Europe/London (UTC{offset}) shown.")
            assert_transit_consistent(check, state, name, expect=True)
        # A blank time is never sent.
        mark = page_.chart_count()
        page_.page.fill("#transit-time", "")
        page_.update()
        page_.page.wait_for_timeout(300)
        state = page_.transit_state()
        check.equals("blank time: no request", page_.chart_count() - mark, 0)
        check.equals("blank time: status", state["status"], "Enter a transit date and time.")
    finally:
        check.note("results", results)
        page_.close(check, allowed_console=(r"status of 400",))


def _ax_descriptions(page):
    session = page.context.new_cdp_session(page)
    try:
        session.send("Accessibility.enable")
        nodes = session.send("Accessibility.getFullAXTree")["nodes"]
    finally:
        session.detach()
    images = {}
    transit_named = 0
    for node in nodes:
        if node.get("ignored"):
            continue
        name = (node.get("name") or {}).get("value") or ""
        role = (node.get("role") or {}).get("value")
        if role in ("image", "img") and name.startswith("D1 chart"):
            images[name] = (node.get("description") or {}).get("value") or ""
        if name.startswith("T:") or "Transit placements for" in name:
            transit_named += 1
    return images, transit_named


def check_transit_preserved_state(check, context):
    """Section 10.11: natal state preserved; the accessibility tree."""
    page_ = TransitPage(context)
    page = page_.page
    try:
        values = {"date": JALANDHAR["date"], "time": "", "place_text": "", "place_id": ""}
        status, natal, _raw = page_.generate(values=values)
        check.equals("assumed natal status", status, 200)
        # The transit fields are filled first, so that focus is on the tree
        # (not in a field) when the natal state is recorded.
        page_.set_transit(TRANSIT_A)
        page.click("#dasha-body tr:nth-child(1) .v-cell-level")
        page.click("#dasha-body tr:nth-child(2) .v-cell-level")
        page.click("#dasha-body tr:nth-child(3) .v-cell-level")
        page.click("#expand-birth")
        page.click("#dasha-body tr:nth-child(4) .v-cell-chain")
        before = {"tree": page.evaluate(TREE_STATE), "badges": page.evaluate(BADGES_AND_ASSUMPTIONS),
                  "submitted": page_.viewer.text("#submitted-line"),
                  "stale": page_.state()["data_stale"]}
        check.require(len(before["tree"]["expanded"]) >= 3, f"three rows not expanded: {before}")
        status, transit = page_.answered(lambda: page.evaluate(
            "() => { const box = document.getElementById('transit-toggle');"
            " box.checked = true; box.dispatchEvent(new Event('change', {bubbles: true})); }"))
        page.wait_for_timeout(200)
        check.equals("transit status", status, 200)
        check.equals("transit source (the default record sent explicitly)",
                     transit["effective"]["source"], "selected")
        state = page_.transit_state()
        assert_transit_consistent(check, state, "shown", expect=True)
        check.equals("assumed-details line shown", state["assumed_hidden"], False)
        images, named = _ax_descriptions(page)
        check.note("ax_shown", {"images": {k: v[:160] for k, v in images.items()},
                                "transit_named_nodes": named})
        north_description = images.get("D1 chart (North Indian)", "")
        check.require("Transit placements for 2026-10-08 14:30:00" in north_description,
                      f"the North description lacks the transit desc: {north_description[:200]!r}")
        for value in ("south", "both", "north"):
            page.evaluate(CHOOSE_WITHOUT_FOCUS, value)
            page.evaluate(
                "() => { const box = document.getElementById('transit-toggle');"
                " box.checked = !box.checked; box.dispatchEvent(new Event('change', {bubbles: true})); }")
            page.evaluate(
                "() => { const box = document.getElementById('transit-toggle');"
                " box.checked = !box.checked; box.dispatchEvent(new Event('change', {bubbles: true})); }")
            after = {"tree": page.evaluate(TREE_STATE),
                     "badges": page.evaluate(BADGES_AND_ASSUMPTIONS),
                     "submitted": page_.viewer.text("#submitted-line"),
                     "stale": page_.state()["data_stale"]}
            check.equals(f"{value}: natal state preserved", after, before)
        page.evaluate(
            "() => { const box = document.getElementById('transit-toggle');"
            " box.checked = false; box.dispatchEvent(new Event('change', {bubbles: true})); }")
        page.wait_for_timeout(150)
        state = page_.transit_state()
        assert_transit_consistent(check, state, "hidden", expect=False)
        images, named = _ax_descriptions(page)
        check.note("ax_hidden", {"images": {k: v[:160] for k, v in images.items()},
                                 "transit_named_nodes": named})
        north_description = images.get("D1 chart (North Indian)", "")
        check.require(north_description.startswith("Lagna in rashi"),
                      f"the North description is gone: {north_description[:120]!r}")
        check.require("Transit placements" not in north_description,
                      f"the hidden overlay is still described: {north_description[:200]!r}")
        check.equals("hidden: no transit node in the tree", named, 0)
        # checkVisibility() answers true for an SVG group hidden by `display`
        # in this Chromium; the rendering is read from the client rects.
        check.equals("hidden: no painted transit text", page.evaluate(
            "() => Array.from(document.querySelectorAll('svg g.transit text'))"
            ".filter(text => text.getClientRects().length > 0).length"), 0)
        check.equals("natal state after hiding", {"tree": page.evaluate(TREE_STATE),
                                                  "badges": page.evaluate(BADGES_AND_ASSUMPTIONS),
                                                  "submitted": page_.viewer.text("#submitted-line"),
                                                  "stale": page_.state()["data_stale"]}, before)
    finally:
        page_.close(check)


GRAYSCALE_ON = "() => { document.documentElement.style.filter = 'grayscale(1)'; return true; }"


def check_transit_previews(check, context):
    """Section 10.12: each birth, each style, 1280 and 375, overlay on."""
    note_jammu(check, context)
    written = []
    identified = {}
    for name, birth in style_births(context):
        for viewport in (DESKTOP_VIEWPORT, MOBILE_VIEWPORT):
            page_ = TransitPage(context, viewport)
            try:
                status, _document, _raw = page_.generate(birth)
                check.equals(f"{name} {viewport['width']}: natal", status, 200)
                status, transit = page_.show_transits()
                check.equals(f"{name} {viewport['width']}: transit", status, 200)
                check.equals(f"{name}: time_assumed", transit["effective"]["time_assumed"], False)
                for value in STYLE_VALUES:
                    state = page_.choose(value)
                    label = f"{name} {value} {viewport['width']}"
                    assert_style_table(check, state, value, "present", label)
                    assert_no_page_overflow(check, state, label)
                    transit_state = page_.transit_state()
                    assert_transit_consistent(check, transit_state, label, expect=True)
                    visible = page_.page.evaluate(
                        "() => Array.from(document.querySelectorAll('svg g.transit'))"
                        ".filter(g => Array.from(g.querySelectorAll('text'))"
                        ".some(text => text.getClientRects().length > 0)).length")
                    check.equals(f"{label}: visible overlay groups", visible,
                                 2 if value == "both" else 1)
                    written.append(page_.screenshot(f"transit_{name}_{value}_{viewport['width']}.png"))
                if viewport is DESKTOP_VIEWPORT:
                    page_.choose("both")
                    page_.page.evaluate(GRAYSCALE_ON)
                    texts = page_.page.evaluate(
                        "() => Array.from(document.querySelectorAll('svg g.transit text'))"
                        ".map(t => [t.getAttribute('class'), t.textContent,"
                        " t.previousElementSibling ? t.previousElementSibling.getAttribute('data-graha') : null,"
                        " t.getAttribute('data-graha')])")
                    unprefixed = [text for text in texts
                                  if text[0] != "transit-deg" and not text[1].startswith("T:")]
                    orphans = [text for text in texts
                               if text[0] == "transit-deg" and text[2] != text[3]]
                    rows = page_.transit_state()["panel_rows"]
                    identified[name] = {"texts": len(texts), "unprefixed": unprefixed,
                                        "degrees_without_prefixed_abbr": orphans,
                                        "panel_rows": len(rows)}
                    check.equals(f"{name} grayscale: texts without the T: prefix", unprefixed, [])
                    check.equals(f"{name} grayscale: degrees not after their T: abbreviation",
                                 orphans, [])
                    check.require(all(row[2].startswith("T:") for row in rows) and rows,
                                  f"{name} grayscale: panel rows {rows}")
                    written.append(page_.screenshot(f"transit_{name}_grayscale_1280.png"))
            finally:
                page_.close(check)
    check.note("screenshots", written)
    check.note("grayscale", identified)


# -- section 10.7 on synthetic crowded charts --------------------------------------

#: The labelled synthetic natal charts of ``transit_synthetic_crowded_600``:
#: ``name -> (builder, arguments, crowded rashi index, what it exercises)``.
#: ``count_in_house`` is ``render_helpers.count_in_house_d1(house, count)``,
#: whose crowded sign is always Mesha (index 0); ``signs`` is
#: ``render_helpers.signs_d1(lagna, {rashi_index: count})``. The North house of
#: a sign is ``(rashi_index - lagna_index) mod 12 + 1``; house 1 also holds the
#: Lagna's own row.
SYNTHETIC_NATAL_CASES = {
    "kite1_n7": ("count_in_house", [1, 6], 0, "North kite 1 full: six grahas and As"),
    "kite1_n2": ("count_in_house", [1, 1], 0, "North kite 1 with two entries (Su and As)"),
    "triangle2_n2": ("count_in_house", [2, 2], 0, "North triangle 2 with two: no free row"),
    "triangle2_n1": ("count_in_house", [2, 1], 0, "North triangle 2 with one: one free row"),
    "side3_n1": ("count_in_house", [3, 1], 0, "North side house 3 with one: one floor row"),
    "side3_n2": ("count_in_house", [3, 2], 0, "North side house 3 with two: no row"),
    "side11_n4": ("count_in_house", [11, 4], 0, "North side house 11 with four (overflowing)"),
    "mesha_kite4_n4": ("signs", [9, {"0": 4}], 0, "South Mesha with four; North kite 4"),
    "vrishabha_triangle2_n4": ("signs", [0, {"1": 4}], 1,
                               "South Vrishabha with four (marker null); North triangle 2"),
    "vrishchika_side3_n4": ("signs", [5, {"7": 4}], 7,
                            "South Vrishchika with four (marker null); North side house 3"),
}

#: Section 10.7: the numbers of transit grahas placed in the crowded sign.
SYNTHETIC_TRANSIT_COUNTS = (1, 2, 4, 9)

#: The four keys of a document the synthetic charts replace; every other key
#: of the real document is kept.
SYNTHETIC_KEYS = ("svg", "south_indian_svg", "overlay", "planetary_positions")

PANEL_ONLY_TEXT = "panel only — no room for marker"
PANEL_ONLY_SENTENCE = "Some transit entries appear in the panel only."

#: The documents of the synthetic charts, through the project interpreter: the
#: renderers with the server's fixed options, the overlay helper with the
#: server's flags and the transport's own ``planetary_positions`` block built
#: from each chart's ``source`` BirthChart -- no new server path.
SYNTHETIC_RENDER_SNIPPET = """
import json, sys
from types import SimpleNamespace
import render_helpers
from vedic_chart.render import render_north_indian_svg, render_south_indian_svg
from vedic_chart.render.overlay import overlay_block
from vedic_chart.viewer import transport

plan = json.loads(sys.argv[1])

def build(builder, arguments):
    if builder == "count_in_house":
        return render_helpers.count_in_house_d1(*arguments)
    if builder == "signs":
        lagna, counts = arguments
        return render_helpers.signs_d1(lagna, {int(key): value for key, value in counts.items()})
    raise ValueError(builder)

def documents(d1):
    return {
        "svg": render_north_indian_svg(d1, transport.RENDERER_OPTIONS),
        "south_indian_svg": render_south_indian_svg(d1, transport.SOUTH_INDIAN_RENDERER_OPTIONS),
        "overlay": overlay_block(
            d1, show_degrees=transport.RENDERER_OPTIONS.show_degrees,
            mark_node_retrograde=transport.RENDERER_OPTIONS.mark_node_retrograde),
        "planetary_positions": transport._planetary_positions(SimpleNamespace(chart=d1.source)),
    }

out = {"natal": {}, "transit": {}}
for name, (builder, arguments) in plan["natal"].items():
    out["natal"][name] = documents(build(builder, arguments))
for name, (builder, arguments) in plan["transit"].items():
    out["transit"][name] = documents(build(builder, arguments))
sys.stdout.write(json.dumps(out, ensure_ascii=False))
"""

#: Every drawn transit element of one root, with its attributes as strings.
TRANSIT_DRAWN = """
(selector) => {
  const svg = document.querySelector(selector);
  const group = svg ? svg.querySelector('g.transit') : null;
  if (!group) return null;
  const attribute = (node, name) => node.getAttribute(name);
  return {
    children: Array.from(group.children).map(node => node.localName),
    desc_id: group.querySelector('desc') ? group.querySelector('desc').getAttribute('id') : null,
    cells: Array.from(group.querySelectorAll('g')).map(cell => ({
      rashi: attribute(cell, 'data-rashi'), house: attribute(cell, 'data-house'),
      cls: attribute(cell, 'class'),
      texts: Array.from(cell.children).map(text => ({
        tag: text.localName, cls: attribute(text, 'class'), x: attribute(text, 'x'),
        y: attribute(text, 'y'), font_size: attribute(text, 'font-size'),
        font_family: attribute(text, 'font-family'), anchor: attribute(text, 'text-anchor'),
        fill: attribute(text, 'fill'), decoration: attribute(text, 'text-decoration'),
        graha: attribute(text, 'data-graha'), content: text.textContent
      }))
    }))
  };
}
"""

#: Section 10.8 on a fixture: the root's children minus the transit group,
#: against the same document parsed on its own; the root's attributes other
#: than the two the page sets (the inline size style, the description list).
NATAL_VS_STANDALONE = """
(argument) => {
  const serialiser = new XMLSerializer();
  const svg = document.querySelector(argument.selector);
  if (!svg) return null;
  const parsed = new DOMParser().parseFromString(argument.text, 'image/svg+xml').documentElement;
  const live = Array.from(svg.children).filter(node => !node.matches('g.transit'))
    .map(node => serialiser.serializeToString(node));
  const standalone = Array.from(parsed.children).map(node => serialiser.serializeToString(node));
  const attributes = (root) => {
    const out = {};
    Array.from(root.attributes).forEach(item => {
      if (item.name !== 'style' && item.name !== 'aria-describedby') out[item.name] = item.value;
    });
    return out;
  };
  let first = -1;
  for (let index = 0; index < Math.max(live.length, standalone.length); index++) {
    if (live[index] !== standalone[index]) { first = index; break; }
  }
  const groups = Array.from(svg.children).filter(node => node.matches('g.transit'));
  return {
    equal: first === -1 && live.length === standalone.length,
    live_children: live.length, standalone_children: standalone.length,
    first_difference: first,
    attributes_equal: JSON.stringify(attributes(svg)) === JSON.stringify(attributes(parsed)),
    transit_groups: groups.length,
    group_is_last: groups.length === 1 && svg.lastElementChild === groups[0]
  };
}
"""

#: The y attributes of the South label row of one sign.
SOUTH_LABEL_ROW = """
(rashi) => {
  const cell = document.querySelector(`#chart-south svg g.sign[data-rashi="${rashi}"]`);
  if (!cell) return null;
  const read = (selector) => {
    const node = cell.querySelector(selector);
    return node ? {y: node.getAttribute('y'), content: node.textContent} : null;
  };
  return {sign_label: read('text.sign-label'), house_label: read('text.house-label')};
}
"""


def _synthetic_plan():
    """The natal and transit chart builders and the case list."""
    natal = {name: [builder, arguments]
             for name, (builder, arguments, _rashi, _what) in SYNTHETIC_NATAL_CASES.items()}
    transit = {}
    cases = []
    for name, (_builder, _arguments, rashi, what) in SYNTHETIC_NATAL_CASES.items():
        for count in SYNTHETIC_TRANSIT_COUNTS:
            # The transit Lagna is opposite the crowded sign, so that the
            # leftover grahas (one per sign) never land in the crowded sign.
            transit_name = f"transit_r{rashi}_k{count}"
            transit[transit_name] = ["signs", [(rashi + 6) % 12, {str(rashi): count}]]
            cases.append({"case": f"{name}_k{count}", "natal": name, "transit": transit_name,
                          "rashi_index": rashi, "sign": str(rashi + 1), "k": count,
                          "what": what, "label": "synthetic"})
    return {"natal": natal, "transit": transit}, cases


def synthetic_documents(context):
    cache = context.__dict__.get("synthetic_transit")
    if cache is None:
        plan, cases = _synthetic_plan()
        documents = run_project_python(
            context, SYNTHETIC_RENDER_SNIPPET, [json.dumps(plan)], extra_path=("tests",)
        )
        cache = {"plan": plan, "cases": cases, "documents": documents}
        context.synthetic_transit = cache
    return cache


def _expected_text(cls, x, y, size, family, anchor, content, graha=None, decoration=None):
    return {"tag": "text", "cls": cls, "x": x, "y": y, "font_size": size,
            "font_family": family, "anchor": anchor, "fill": TRANSIT_FILL,
            "decoration": decoration, "graha": graha, "content": content}


def predict_transit_cell(slot, entries, natal_block):
    """Section 5.3 for one cell, from the natal slot alone: the texts the page
    must draw there, in DOM order, and the outcome the panel must state."""
    prefix = natal_block["prefix"]
    family = natal_block["font_family"]
    stacked = slot["layout"] == "stacked"
    count = len(entries)

    def capacity(rung):
        return len(rung["entries"]) if stacked else len(rung["rows"])

    def entry_texts(rung, row, entry):
        if stacked:
            abbr_y = rung["entries"][row]["abbr_y"]
            deg_x, deg_y = rung["x"], rung["entries"][row]["deg_y"]
        else:
            abbr_y = rung["rows"][row]
            deg_x, deg_y = rung["deg_x"], abbr_y
        return [
            _expected_text("transit", rung["x"], abbr_y, rung["font_size"], family, "start",
                           prefix + entry["abbr"], graha=entry["key"],
                           decoration="underline" if entry["underline"] else None),
            _expected_text("transit-deg", deg_x, deg_y, rung["font_size"], family, "start",
                           entry["degree_text"], graha=entry["key"]),
        ]

    for index, rung in enumerate(slot["rungs"]):
        if capacity(rung) >= count:
            texts = [text for row, entry in enumerate(entries)
                     for text in entry_texts(rung, row, entry)]
            return texts, {"mode": "shown", "shown": count, "more": 0,
                           "font": rung["font_size"], "rung": index}
    floor = slot["rungs"][-1]
    rows = capacity(floor)
    if rows >= 1:
        drawn = rows - 1
        texts = [text for row in range(drawn) for text in entry_texts(floor, row, entries[row])]
        more = count - drawn
        texts.append(_expected_text(
            "transit-more", floor["x"], floor["overflow_y"] if stacked else floor["rows"][drawn],
            floor["font_size"], family, "start", f"{prefix}+{more}"))
        return texts, {"mode": "row", "shown": drawn, "more": more,
                       "font": floor["font_size"], "rung": len(slot["rungs"]) - 1}
    marker = slot["marker"]
    if marker is not None:
        return [_expected_text("transit-marker", marker["x"], marker["y"],
                               natal_block["marker_font_size"], family, marker["anchor"],
                               f"{prefix}+{count}")], {
            "mode": "marker", "shown": 0, "more": count,
            "font": natal_block["marker_font_size"], "rung": None}
    return [], {"mode": "panel", "shown": 0, "more": count, "font": None, "rung": None}


def outcome_text(outcome):
    """The panel's per-style column for one outcome (section 5.5)."""
    if outcome["mode"] == "shown":
        return "shown"
    more = f"T:+{outcome['more']}"
    if outcome["mode"] == "row":
        return f"{more} in row ({outcome['shown']} shown)"
    if outcome["mode"] == "marker":
        return f"{more} marker (0 shown)"
    return PANEL_ONLY_TEXT


def observed_outcome(cell):
    """What a drawn cell actually shows, read off its texts alone."""
    if cell is None:
        return {"mode": "panel", "shown": 0, "more": None}
    shown = sum(1 for text in cell["texts"] if text["cls"] == "transit")
    more = [text["content"] for text in cell["texts"] if text["cls"] == "transit-more"]
    marker = [text["content"] for text in cell["texts"] if text["cls"] == "transit-marker"]
    if marker:
        return {"mode": "marker", "shown": shown, "more": marker[0].split("+", 1)[1]}
    if more:
        return {"mode": "row", "shown": shown, "more": more[0].split("+", 1)[1]}
    return {"mode": "shown", "shown": shown, "more": 0}


def predict_transit_overlay(natal_block, transit_block, transit_positions):
    """The groups' cells and the panel rows the page must produce."""
    by_sign = {str(number): [] for number in range(1, 13)}
    sign_name = {}
    for index, entry in enumerate(transit_block["entries"]):
        sign = str(entry["rashi_number"])
        by_sign[sign].append(entry)
        sign_name[sign] = transit_positions["planets"][index]["sign"]["name"]
    prefix = natal_block["prefix"]
    styles = {}
    for style in ("north", "south"):
        cells = []
        outcomes = {}
        for sign in (str(number) for number in range(1, 13)):
            if not by_sign[sign]:
                continue
            slot = natal_block["slots"][style][sign]
            texts, outcome = predict_transit_cell(slot, by_sign[sign], natal_block)
            outcomes[sign] = outcome
            if texts:
                cells.append({"rashi": sign, "house": str(slot["house"]), "cls": "transit-cell",
                              "texts": texts})
        styles[style] = {"cells": cells, "outcomes": outcomes}
    rows = []
    for house in range(1, 13):
        for sign in (str(number) for number in range(1, 13)):
            if natal_block["slots"]["north"][sign]["house"] != house or not by_sign[sign]:
                continue
            rows.append([
                str(house), sign_name[sign],
                ", ".join(f"{prefix}{entry['abbr']} {entry['degree_text']}"
                          f"{' ℞' if entry['underline'] else ''}" for entry in by_sign[sign]),
                outcome_text(styles["north"]["outcomes"][sign]),
                outcome_text(styles["south"]["outcomes"][sign]),
            ])
    return by_sign, styles, rows


def _synthetic_route(page, holder, log):
    """``/api/chart`` for the synthetic check: a transit request is answered
    with the real transit document of the running viewer (fetched once, for
    the page's own first transit request) with the four keys of the current
    case's synthetic transit chart, ``request.submitted`` echoing exactly the
    four strings the page posted, ``time_assumed`` false and source
    ``selected``. Anything else goes to the server unchanged."""

    def handler(route):
        try:
            body = json.loads(route.request.post_data or "{}")
        except ValueError:
            body = {}
        if str(body.get("date", ""))[:4] not in TRANSIT_YEARS or holder.get("transit") is None:
            log.append({"kind": "passed", "date": body.get("date")})
            route.continue_()
            return
        fetched = False
        if "base" not in holder:
            response = route.fetch()
            holder["base_status"] = response.status
            holder["base"] = response.body().decode("utf-8")
            fetched = True
        document = json.loads(holder["base"])
        for key in SYNTHETIC_KEYS:
            document[key] = holder["transit"][key]
        document["request"]["submitted"] = dict(body)
        document["effective"]["time_assumed"] = False
        document["effective"]["source"] = "selected"
        log.append({"kind": "synthetic", "case": holder.get("case"), "fetched_base": fetched,
                    "submitted": dict(body)})
        route.fulfill(status=200, content_type="application/json; charset=utf-8",
                      body=json.dumps(document, ensure_ascii=False, separators=(",", ":")))

    page.route("**/api/chart", handler)
    return handler


def _units_gap(bounds, first, second):
    return _box_gap(first, second) / bounds["scale"]


def _judge_synthetic_style(check, label, style, bounds, drawn, predicted, case,
                           by_sign, panel_rows, natal_block, page_):
    """Section 10.7 for one style of one case, on the page's own drawing."""
    sign = case["sign"]
    expected_cells = predicted["cells"]
    observed_cells = drawn["cells"] if drawn else []
    # The page drew exactly what section 5.3 predicts from the natal slots.
    check.equals(f"{label}: drawn cells and texts equal the prediction from overlay.slots",
                 observed_cells, expected_cells)
    check.equals(f"{label}: the group starts with its desc",
                 (drawn or {}).get("children", [None])[:1], ["desc"])
    summary = judge_transit_bounds(check, label, bounds, style)
    by_rashi = {cell["rashi"]: cell for cell in observed_cells}
    # (b), sections 6.2 and 10.7: every transit row's browser text box lies
    # inside its natal cell (judged above, point in polygon) at least 15 units
    # (MIN_BOX_CLEARANCE) from the cell's edges, and overlaps no natal text or
    # underline box (judged above). The rows' spacing from the natal text is the
    # renderers' own row pitch, so the gap to the nearest natal element (every
    # natal text box, numerals and labels included, in any cell, and every
    # natal underline box) is recorded, not asserted. The markers keep their
    # own section 5.4 rules (judged above).
    row_edges = []
    for text in bounds["transit"]:
        if text["cls"] == "transit-marker":
            continue
        units = _edge_distance(text["box"], bounds["cells"][text["rashi"]]["polygon"]) / bounds["scale"]
        row_edges.append({"content": text["content"], "cls": text["cls"],
                          "rashi": text["rashi"], "edge_units": round(units, 2)})
    check.equals(f"{label}: transit rows closer than 15 units to their cell's edges",
                 [edge for edge in row_edges
                  if edge["edge_units"] < TRANSIT_NORTH_CLEARANCE_UNITS - 0.01], [])
    natal = bounds["natal_texts"] + bounds["natal_lines"]
    gaps = []
    for text in bounds["transit"]:
        nearest = min(
            ((round(_units_gap(bounds, text["box"], other["box"]), 2), other["cls"] or "",
              other["content"], other["rashi"] or "") for other in natal),
            default=None,
        )
        if nearest is not None:
            gaps.append({"content": text["content"], "cls": text["cls"], "rashi": text["rashi"],
                         "units": nearest[0], "natal": nearest[2], "natal_cls": nearest[1],
                         "natal_rashi": nearest[3]})
    # The crowded cell: what it shows and the panel row that describes it.
    outcome = predicted["outcomes"][sign]
    cell = by_rashi.get(sign)
    observed = observed_outcome(cell)
    crowded_texts = [text for text in bounds["transit"] if text["rashi"] == sign]
    entry_fonts = sorted({text["font_units"] for text in crowded_texts
                          if text["cls"] != "transit-marker"})
    measured = {
        "cell": {"sign": sign, "house": natal_block["slots"][style][sign]["house"],
                 "layout": natal_block["slots"][style][sign]["layout"]},
        "natal_rows": natal_block["slots"][style][sign]["natal_rows"],
        "k": case["k"],
        "predicted": {key: outcome[key] for key in ("mode", "shown", "more", "font")},
        "observed": observed,
        "rung_font_used_units": entry_fonts,
        "marker_kind": {"marker": "cell marker", "row": "T:+n in row", "shown": "none",
                        "panel": "none (panel only)"}[outcome["mode"]],
        "min_entry_font_units": summary["min_entry_font_units"],
        "min_gap_to_natal_units": min((gap["units"] for gap in gaps), default=None),
        "min_gap_to_natal_in_crowded_cell_units": min(
            (gap["units"] for gap in gaps if gap["rashi"] == sign), default=None),
        "nearest_natal": min(gaps, key=lambda gap: gap["units"], default=None),
        "markers": summary["markers"],
    }
    edges = [round(units, 2) for units in (
        _edge_distance(text["box"], bounds["cells"][text["rashi"]]["polygon"]) / bounds["scale"]
        for text in bounds["transit"])]
    measured["min_edge_units"] = min(edges, default=None)
    measured["min_row_edge_units"] = min((edge["edge_units"] for edge in row_edges),
                                         default=None)
    if outcome["mode"] == "marker":
        markers = [text for text in crowded_texts if text["cls"] == "transit-marker"]
        check.equals(f"{label}: one marker in the crowded cell with n = k",
                     [text["content"] for text in markers], [f"T:+{case['k']}"])
        if style == "south" and markers:
            rows = page_.page.evaluate(SOUTH_LABEL_ROW, sign)
            marker_attributes = [text for text in cell["texts"]
                                 if text["cls"] == "transit-marker"][0]
            cell_bounds = bounds["cells"][sign]
            box = markers[0]["box"]
            measured["label_row"] = {
                "marker_y": marker_attributes["y"],
                "sign_label_y": rows["sign_label"]["y"] if rows else None,
                "house_label_y": rows["house_label"]["y"] if rows else None,
                "marker_box_px": [round(box["top"], 2), round(box["bottom"], 2)],
                "sign_label_box_px": [round(cell_bounds["sign_label"]["top"], 2),
                                      round(cell_bounds["sign_label"]["bottom"], 2)],
            }
            check.require(rows is not None
                          and marker_attributes["y"] == rows["sign_label"]["y"]
                          == rows["house_label"]["y"],
                          f"{label}: the marker is not on the label row's baseline: "
                          f"{measured['label_row']}")
            for name in ("sign_label", "house_label"):
                other = cell_bounds[name]
                check.require(abs(box["top"] - other["top"]) <= 0.5
                              and abs(box["bottom"] - other["bottom"]) <= 0.5,
                              f"{label}: the marker box is not in the label row ({name}): "
                              f"{box} vs {other}")
            entries_top = [other["box"]["top"] for other in bounds["natal_texts"]
                           if other["rashi"] == sign
                           and other["cls"] not in ("sign-label", "house-label")]
            if entries_top:
                measured["label_row"]["clear_above_entries_px"] = round(
                    min(entries_top) - box["bottom"], 2)
                check.require(box["bottom"] <= min(entries_top) + BOUNDS_EPSILON_PX,
                              f"{label}: the marker enters the entry area")
    if outcome["mode"] == "row":
        more = [text["content"] for text in crowded_texts if text["cls"] == "transit-more"]
        check.equals(f"{label}: the in-row T:+n", more, [f"T:+{outcome['more']}"])
    if outcome["mode"] == "panel":
        check.equals(f"{label}: no transit text in the panel-only cell", crowded_texts, [])
        check.require(sign not in by_rashi, f"{label}: a panel-only cell group was drawn")
    # The panel: one row per occupied natal house, consistent with the cells.
    column = 3 if style == "north" else 4
    for row in panel_rows:
        rashi = [key for key, value in natal_block["slots"]["north"].items()
                 if str(value["house"]) == row[0]][0]
        seen = observed_outcome(by_rashi.get(rashi))
        if seen["mode"] == "shown":
            check.equals(f"{label}: sign {rashi}: drawn entries equal k",
                         seen["shown"], len(by_sign[rashi]))
        stated = outcome_text({"mode": seen["mode"], "shown": seen["shown"],
                               "more": seen["more"] if seen["more"] is not None
                               else len(by_sign[rashi])})
        check.equals(f"{label}: sign {rashi}: the panel's column states what the cell shows",
                     row[column], stated)
    return measured


def check_transit_synthetic_crowded_600(check, context):
    """Section 10.7 on labelled synthetic crowded cells, at a 600 px chart.

    The natal document is the real Jalandhar document of the running viewer
    with ``svg``, ``south_indian_svg``, ``overlay`` and ``planetary_positions``
    taken from a synthetic chart, loaded through the ``#acceptance`` seam; the
    transit document is the viewer's own answer to the page's transit request
    with the same four keys from a synthetic transit chart, so that the page's
    validation and ``composeTransit`` run unchanged. What the page must draw is
    predicted from ``overlay.slots`` (section 5.3) and compared with the drawing;
    the clearances are measured on the browser's own text bounds.
    """
    synthetic = synthetic_documents(context)
    documents = synthetic["documents"]
    cases = synthetic["cases"]
    page_ = TransitPage(context, DESKTOP_VIEWPORT)
    page = page_.page
    holder = {}
    log = []
    measured = {}
    handler = None
    try:
        status, base, _raw = page_.generate()
        check.equals("Jalandhar natal status", status, 200)
        check.equals("the #acceptance seam", page.evaluate("() => typeof window.__loadFixture"),
                     "function")
        page_.choose("both")
        page_.set_transit(TRANSIT_A)
        handler = _synthetic_route(page, holder, log)
        for case in cases:
            name = case["case"]
            natal_doc = dict(base)
            natal_doc.update(documents["natal"][case["natal"]])
            transit = documents["transit"][case["transit"]]
            natal_block = natal_doc["overlay"]
            by_sign, predicted, panel_expected = predict_transit_overlay(
                natal_block, transit["overlay"], transit["planetary_positions"])
            check.equals(f"{name}: the transit chart puts k grahas in the crowded sign",
                         len(by_sign[case["sign"]]), case["k"])
            holder.update({"transit": transit, "case": name})
            page_.toggle(False)
            check.equals(f"{name}: fixture loaded",
                         page.evaluate("(doc) => window.__loadFixture(doc)", natal_doc), True)
            state = page_.transit_state()
            check.equals(f"{name}: the natal block is usable", state["disabled"], False)
            check.equals(f"{name}: the natal form is not stale", state["stale"], None)
            mark = page_.chart_count()
            status, answer = page_.answered(lambda: page_.toggle(True))
            page.wait_for_function(
                "() => { const g = document.querySelector('#chart svg g.transit');"
                " return g && g.getAttribute('display') === null; }", timeout=30000)
            check.equals(f"{name}: one transit request", page_.chart_count() - mark, 1)
            check.equals(f"{name}: transit status", status, 200)
            check.equals(f"{name}: echoed submission", answer["request"]["submitted"],
                         {"date": TRANSIT_A[0], "time": TRANSIT_A[1],
                          "place_text": base["effective"]["place"]["label"],
                          "place_id": str(base["effective"]["place"]["geoname_id"])})
            state = page_.transit_state()
            assert_transit_consistent(check, state, name, expect=True)
            panel_only = any(PANEL_ONLY_TEXT in row[3:] for row in panel_expected)
            check.equals(f"{name}: status line", state["status"],
                         f"Transits for {TRANSIT_A[0]} {TRANSIT_A[1]} Asia/Kolkata (UTC+05:30) "
                         f"shown.{' ' + PANEL_ONLY_SENTENCE if panel_only else ''}")
            # (g) the panel: the prediction, and every transit graha exactly once.
            check.equals(f"{name}: panel rows", state["panel_rows"], panel_expected)
            listed = [item for row in state["panel_rows"] for item in row[2].split(", ")]
            everyone = [f"T:{entry['abbr']} {entry['degree_text']}"
                        f"{' ℞' if entry['underline'] else ''}"
                        for entry in transit["overlay"]["entries"]]
            check.equals(f"{name}: every transit graha listed once with its degree text",
                         sorted(listed), sorted(everyone))
            entry = {"label": case["label"], "what": case["what"], "k": case["k"]}
            shot_paths = {}
            for style, selector in (("north", "#chart svg"), ("south", "#chart-south svg")):
                label = f"{name} {style}"
                page.locator(selector).scroll_into_view_if_needed()
                bounds = page.evaluate(TRANSIT_BOUNDS, {"selector": selector, "style": style})
                drawn = page.evaluate(TRANSIT_DRAWN, selector)
                (context.out / f"transit_synthetic_bounds_{name}_{style}.json").write_text(
                    json.dumps({"bounds": bounds, "drawn": drawn}, indent=1,
                               ensure_ascii=False), encoding="utf-8")
                entry[style] = _judge_synthetic_style(
                    check, label, style, bounds, drawn, predicted[style], case, by_sign,
                    state["panel_rows"], natal_block, page_)
                shot = context.out / "screenshots" / f"transit_synthetic_{name}_{style}_600.png"
                page.locator(selector).screenshot(path=str(shot))
                shot_paths[style] = shot.name
                if any(text["underline"] == "underline" for text in bounds["transit"]):
                    bands = underline_bands(shot.read_bytes(), bounds)
                    for band in bands:
                        check.require(band["underline_rows_px"] is not None,
                                      f"{label}: no rendered underline under {band['content']}")
                        if band["underline_rows_px"] is None:
                            continue
                        check.require(band["below_baseline_px"] >= -0.5,
                                      f"{label}: the underline of {band['content']} is above "
                                      f"its baseline: {band}")
                        check.require(band["within_row_pitch_px"] >= 0,
                                      f"{label}: the underline of {band['content']} leaves its "
                                      f"row pitch: {band}")
                        check.equals(f"{label}: natal boxes under the underline of "
                                     f"{band['content']}", band["overlaps_natal"], [])
                        check.require(band["clear_of_next_text_px"] is None
                                      or band["clear_of_next_text_px"] > 0,
                                      f"{label}: the underline of {band['content']} reaches "
                                      f"the next row: {band}")
                    entry[style]["underlines"] = [
                        {key: band.get(key) for key in ("content", "rashi", "below_baseline_px",
                                                        "within_row_pitch_px",
                                                        "clear_of_next_text_px")}
                        for band in bands]
                # (h) natal content equals the standalone document.
                key = "svg" if style == "north" else "south_indian_svg"
                same = page.evaluate(NATAL_VS_STANDALONE,
                                     {"selector": selector, "text": natal_doc[key]})
                check.require(same is not None and same["equal"] and same["attributes_equal"]
                              and same["transit_groups"] == 1 and same["group_is_last"],
                              f"{label}: natal nodes differ from the standalone document: {same}")
            # One screenshot of both charts and the panel.
            box = page.evaluate(
                "() => { const a = document.getElementById('charts').getBoundingClientRect();"
                " const b = document.getElementById('transit-panel').getBoundingClientRect();"
                " return {x: Math.min(a.left, b.left) + window.scrollX,"
                " y: Math.min(a.top, b.top) + window.scrollY,"
                " right: Math.max(a.right, b.right) + window.scrollX,"
                " bottom: Math.max(a.bottom, b.bottom) + window.scrollY}; }")
            shot = f"transit_synthetic_{name}_600.png"
            page.screenshot(path=str(context.out / "screenshots" / shot), full_page=True,
                            clip={"x": box["x"], "y": box["y"], "width": box["right"] - box["x"],
                                  "height": box["bottom"] - box["y"]})
            entry["screenshots"] = [shot, *shot_paths.values()]
            # (i) off/on three times: no request, one group and one desc id per root.
            mark = page_.chart_count()
            for turn in range(3):
                page_.toggle(False)
                hidden = page_.transit_state()
                assert_transit_consistent(check, hidden, f"{name}: off {turn + 1}", expect=False)
                check.equals(f"{name}: off {turn + 1}: hidden groups",
                             [(group["display"], group["aria_hidden"]) for group in hidden["groups"]],
                             [("none", "true"), ("none", "true")])
                page_.toggle(True)
                page.wait_for_timeout(50)
                shown_state = page_.transit_state()
                assert_transit_consistent(check, shown_state, f"{name}: on {turn + 1}", expect=True)
                check.equals(f"{name}: on {turn + 1}: groups and desc ids",
                             [shown_state["north_groups"], shown_state["south_groups"],
                              shown_state["north_desc_ids"], shown_state["south_desc_ids"]],
                             [1, 1, 1, 1])
            check.equals(f"{name}: off/on makes no request", page_.chart_count() - mark, 0)
            for style, selector in (("north", "#chart svg"), ("south", "#chart-south svg")):
                key = "svg" if style == "north" else "south_indian_svg"
                same = page.evaluate(NATAL_VS_STANDALONE,
                                     {"selector": selector, "text": natal_doc[key]})
                check.require(same is not None and same["equal"] and same["transit_groups"] == 1,
                              f"{name} {style}: natal nodes differ after off/on: {same}")
            measured[name] = entry
        check.equals("the base transit document's status", holder.get("base_status"), 200)
        check.equals("every transit request was answered synthetically",
                     [item["kind"] for item in log], ["synthetic"] * len(cases))
    finally:
        if handler is not None:
            try:
                page.unroute("**/api/chart", handler)
            except Exception:  # noqa: BLE001 -- a closed page has no routes
                pass
        check.note("cases", measured)
        check.note("route_log_size", len(log))
        context.measurements["transit_synthetic_crowded_600"] = {
            name: {
                style: {key: entry[style][key] for key in
                        ("cell", "natal_rows", "k", "predicted", "observed",
                         "rung_font_used_units", "marker_kind", "min_gap_to_natal_units",
                         "min_gap_to_natal_in_crowded_cell_units", "min_edge_units",
                         "min_row_edge_units", "markers")}
                for style in ("north", "south") if style in entry
            }
            for name, entry in measured.items()
        }
        page_.close(check)


def run_transit_checks(report, context):
    report.run("transit_control_default", check_transit_control_default, context)
    report.run("transit_metadata_fallback", check_transit_metadata_fallback, context)
    report.run("transit_sign_placement", check_transit_sign_placement, context)
    report.run("transit_text_bounds_600", check_transit_text_bounds_600, context)
    report.run("transit_synthetic_crowded_600", check_transit_synthetic_crowded_600, context)
    report.run("transit_replacement", check_transit_replacement, context)
    report.run("transit_request_counts", check_transit_request_counts, context)
    report.run("transit_races", check_transit_races, context)
    report.run("transit_errors", check_transit_errors, context)
    report.run("transit_preserved_state", check_transit_preserved_state, context)
    report.run("transit_previews", check_transit_previews, context)


# --- wiring ------------------------------------------------------------------


class Context:
    """Everything the checks share: the browser, the paths, the recorded values."""

    def __init__(self, out, repo_root, url, cli, viewer_process, browser, browser_context):
        self.out = out
        self.repo_root = repo_root
        self.url = url
        self.cli = cli
        self.viewer_process = viewer_process
        self.browser = browser
        self.browser_context = browser_context
        self.viewport = {"width": 1280, "height": 900}
        self.requests = []
        self.console = []
        self.page_errors = []
        self.violations = []
        self.documents = {}
        self.measurements = {}
        self.banner_lines = []
        self.jammu_available = False
        self.jammu_reason = ""
        self.viewer = None
        # Layer 15: what the run was launched with, so that a check can start a
        # second viewer of its own (the override and the unavailable-default
        # cases) without reaching for the argument parser again.
        self.python = None
        self.geodata = None
        self.ephemeris = None
        self.default_place_id = None
        self.default_place = {}
        self.cli_tables = {}
        self.tried_queries = []
        self._resolved = {}
        self._queries = {}

    def count_requests(self, path):
        """How many requests the instrumented pages have made to one path."""
        target = self.url.rstrip("/") + path
        return len(
            [entry for entry in self.requests if entry["url"].split("?")[0] == target]
        )

    def resolved(self, query):
        """What the configured database resolves a CLI ``--place`` query to."""
        if query not in self._resolved:
            self._resolved[query] = self.cli.resolve(query)
        return self._resolved[query]

    def query_for(self, geoname_id, label):
        """A CLI ``--place`` query that resolves to exactly this record.

        The page never sends a query, so a CLI comparison needs one, and it must
        be a query this database maps to the very record the page used. The
        candidates are tried in the order a person would write them -- "Jammu,
        India", then the full label, then the bare name -- and the first that
        resolves to the right identifier is the one the comparison uses.
        """
        if geoname_id in self._queries:
            return self._queries[geoname_id]
        parts = [part.strip() for part in label.split(",")]
        candidates = []
        if len(parts) >= 2:
            candidates.append(f"{parts[0]}, {parts[-1]}")
        candidates.append(label)
        candidates.append(parts[0])
        self.tried_queries = []
        for candidate in candidates:
            if candidate in [entry[0] for entry in self.tried_queries]:
                continue
            try:
                resolved = self.resolved(candidate)
            except Exception as error:  # noqa: BLE001 -- an ambiguous query is a miss
                self.tried_queries.append((candidate, f"{type(error).__name__}"))
                continue
            self.tried_queries.append((candidate, resolved["geoname_id"]))
            if resolved["geoname_id"] == geoname_id:
                self._queries[geoname_id] = (candidate, resolved)
                return self._queries[geoname_id]
        self._queries[geoname_id] = (None, None)
        return self._queries[geoname_id]

    def instrument(self, page):
        page.on(
            "request",
            lambda request: self.requests.append(
                {"url": request.url, "method": request.method, "resource": request.resource_type}
            ),
        )
        page.on(
            "console",
            lambda message: self.console.append({"type": message.type, "text": message.text}),
        )
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        return page

    def new_viewer_page(self, hash_fragment=""):
        page = self.browser_context.new_page()
        page.set_viewport_size(self.viewport)
        self.instrument(page)
        page.goto(self.url + hash_fragment, wait_until="load")
        return page

    def scratch_page(self):
        """A page that never touches the server: no instrumentation, about:blank."""
        page = self.browser_context.new_page()
        page.set_viewport_size(self.viewport)
        return page


def probe_jammu(context):
    """Layer 15 section 13: the fixture database has no Jammu; say so explicitly.

    The probe is one suggestions request, which costs nothing and needs no
    calculation: if the record cannot be chosen from the list, the reference
    flow that chooses it cannot run.
    """
    viewer = context.viewer
    answer = viewer.api("/api/places", {"q": JAMMU["place_query"]})
    if answer["status"] != 200 or answer["document"] is None:
        context.jammu_available = False
        context.jammu_reason = f"the suggestions endpoint answered {answer['status']}"
        return
    labels = [item["label"] for item in answer["document"]["suggestions"]]
    context.jammu_available = JAMMU["place_label"] in labels
    if not context.jammu_available:
        context.jammu_reason = (
            f"no suggestion for {JAMMU['place_query']!r} is "
            f"{JAMMU['place_label']!r}; the list was {labels}"
        )


def run_checks(report, context):
    report.run("startup_banner", check_startup_banner, context)
    jalandhar = f"jalandhar_{YEAR_365256363.replace('.', '')}"
    jammu = f"jammu_{YEAR_365256363.replace('.', '')}"
    try:
        probe_jammu(context)
    except Exception as error:  # noqa: BLE001 -- a failed probe skips, it does not crash
        context.jammu_available = False
        context.jammu_reason = f"the probe failed: {type(error).__name__}: {error}"
    report.run(
        "reference_jalandhar_365256363",
        check_reference,
        context,
        "reference_jalandhar_365256363",
        JALANDHAR,
        jalandhar,
    )
    report.run(
        "reference_jammu_365256363",
        check_reference,
        context,
        "reference_jammu_365256363",
        JAMMU,
        jammu,
    )
    report.run("svg_bytes_equal_cli", check_svg_bytes_equal_cli, context)
    report.run("svg_dom_semantics", check_svg_dom_semantics, context)
    report.run("svg_pixels_equal_standalone", check_svg_pixels_equal_standalone, context)
    report.run("table_text_equal_cli", check_table_text_equal_cli, context)
    report.run("expand_levels", check_expand_levels, context)
    report.run("expand_birth_chain_focus_pd", check_expand_birth_chain_focus_pd, context)
    report.run("birth_markers", check_birth_markers, context)
    report.run("keyboard_model", check_keyboard_model, context)
    report.run("accessibility_tree", check_accessibility_tree, context)
    report.run("divergence_chains", check_divergence_chains, context)
    report.run("superseded_response", check_superseded_response, context)
    report.run("errors", check_errors, context)
    report.run("microseconds_toggle", check_microseconds_toggle, context)
    report.run("stale_inputs_banner", check_stale_inputs_banner, context)
    report.run("mobile_scrolling", check_mobile_scrolling, context)
    # Layer 15 section 13.
    report.run("defaults_date_only", check_defaults_date_only, context)
    report.run("defaults_time_only", check_defaults_time_only, context)
    report.run("defaults_place_only", check_defaults_place_only, context)
    report.run("combobox_keyboard", check_combobox_keyboard, context)
    report.run("combobox_pointer", check_combobox_pointer, context)
    report.run("combobox_stale", check_combobox_stale, context)
    report.run(
        "selection_invalidated_on_edit", check_selection_invalidated_on_edit, context
    )
    report.run("invalid_time_no_fallback", check_invalid_time_no_fallback, context)
    report.run("year_implicit", check_year_implicit, context)
    report.run("default_override", check_default_override, context)
    report.run("default_unavailable", check_default_unavailable, context)
    # Layer 19 section 9.3: the chart style, each check on a page of its own.
    report.run("style_default_north", check_style_default_north, context)
    report.run("style_switch_no_requests", check_style_switch_no_requests, context)
    report.run(
        "style_one_calculation_per_generate",
        check_style_one_calculation_per_generate,
        context,
    )
    report.run("style_both_side_by_side_1280", check_style_both_side_by_side_1280, context)
    report.run("style_both_stacked_375", check_style_both_stacked_375, context)
    report.run("style_both_threshold", check_style_both_threshold, context)
    report.run("style_single_layout_unchanged", check_style_single_layout_unchanged, context)
    report.run("style_fallback_missing", check_style_fallback_missing, context)
    report.run("style_fallback_malformed", check_style_fallback_malformed, context)
    report.run("style_fallback_valid", check_style_fallback_valid, context)
    report.run("style_during_loading", check_style_during_loading, context)
    report.run("style_after_failure", check_style_after_failure, context)
    report.run("style_after_cancel", check_style_after_cancel, context)
    report.run("style_stale_preserved", check_style_stale_preserved, context)
    report.run("style_keyboard", check_style_keyboard, context)
    report.run(
        "style_assumptions_and_dasha_preserved",
        check_style_assumptions_and_dasha_preserved,
        context,
    )
    report.run("style_unique_ids", check_style_unique_ids, context)
    report.run("south_svg_bytes_equal_renderer", check_south_svg_bytes_equal_renderer, context)
    report.run(
        "south_svg_pixels_equal_standalone", check_south_svg_pixels_equal_standalone, context
    )
    report.run("south_text_bounds_600", check_south_text_bounds_600, context)
    report.run("style_previews", check_style_previews, context)
    # Layer 20 section 10: the natal-transit overlay, each check on pages of its own.
    run_transit_checks(report, context)
    context.viewer.page.screenshot(
        path=str(context.out / "screenshots" / "desktop_1280.png"), full_page=True
    )
    report.run("network_routes", check_network_routes, context)
    report.run("csp_clean", check_csp_clean, context)


def playwright_version():
    try:
        from importlib.metadata import version  # noqa: PLC0415 -- tooling only

        return version("playwright")
    except Exception:  # noqa: BLE001 -- a missing version is not a failure
        return "unknown"


def python_version(interpreter):
    completed = subprocess.run(  # noqa: S603 -- fixed argument vector
        [str(interpreter), "-c", "import sys; print(sys.version.replace('\\n', ' '))"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return completed.stdout.strip() or completed.stderr.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--geodata", required=True, type=Path)
    parser.add_argument("--ephemeris", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="interpreter for the viewer subprocess and the CLI comparisons",
    )
    parser.add_argument(
        "--default-place-id",
        type=int,
        default=None,
        help=(
            "passed through to the viewer subprocess; needed for the fixture "
            "database, which does not hold the built-in default record 1269321"
        ),
    )
    parser.add_argument("--keep-server", action="store_true")
    parser.add_argument(
        "--chromium",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "a Chromium executable for Playwright to launch instead of its own "
            "bundled browser (default: Playwright's own)"
        ),
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    out = args.out.expanduser().resolve()
    try:
        out.relative_to(repo_root)
    except ValueError:
        pass
    else:
        parser.error(
            f"--out {out} is inside the repository checkout at {repo_root}; "
            "the acceptance run writes outside its own source tree"
        )
    if out == repo_root or repo_root in out.parents:
        parser.error(f"--out {out} is inside the repository checkout at {repo_root}")

    for name in ("screenshots", "responses", "svg", "cli"):
        (out / name).mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is required in the environment running this script: "
            "pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 2

    report = Report()
    viewer_process = ViewerProcess(
        args.python,
        repo_root,
        args.geodata,
        args.ephemeris,
        default_place_id=args.default_place_id,
    )
    exit_code = 1
    try:
        banner_lines = viewer_process.wait_for_banner()
        url = viewer_process.url
        print(f"viewer: {url}", flush=True)
        cli = ProjectCli(args.python, repo_root, args.geodata, args.ephemeris)
        with sync_playwright() as playwright:
            if args.chromium is not None:
                browser = playwright.chromium.launch(
                    executable_path=str(args.chromium)
                )
            else:
                browser = playwright.chromium.launch()
            browser_context = browser.new_context(
                viewport={"width": 1280, "height": 900}, device_scale_factor=1
            )
            browser_context.add_init_script(CSP_LISTENER)
            context = Context(out, repo_root, url, cli, viewer_process, browser, browser_context)
            context.banner_lines = banner_lines
            context.python = args.python
            context.geodata = args.geodata
            context.ephemeris = args.ephemeris
            context.default_place_id = args.default_place_id
            context.default_place = parse_default_place(banner_lines)
            page = context.new_viewer_page()
            context.viewer = Viewer(page, url, context.requests, context.console, context.page_errors)
            report.environment = {
                "chromium_version": browser.version,
                "playwright_version": playwright_version(),
                "script_python": sys.version.replace("\n", " "),
                "script_executable": sys.executable,
                "viewer_python": python_version(args.python),
                "viewer_executable": str(args.python),
                "default_place_id_flag": args.default_place_id,
                "chromium_flag": None if args.chromium is None else str(args.chromium),
                "default_place": context.default_place,
                "viewer_command": viewer_process.command,
                "viewer_environment": {
                    key: viewer_process.environment[key]
                    for key in ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED")
                },
                "repository": str(repo_root),
                "geodata": str(Path(args.geodata).resolve()),
                "geodata_sha256": sha256_of(Path(args.geodata)),
                "ephemeris": str(Path(args.ephemeris).resolve()),
                "ephemeris_files": {
                    path.name: {"bytes": path.stat().st_size, "sha256": sha256_of(path)}
                    for path in sorted(Path(args.ephemeris).glob("*.se1"))
                },
                "out": str(out),
                "url": url,
                "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            try:
                run_checks(report, context)
            finally:
                report.banner = {
                    "lines": banner_lines,
                    "metadata_rows": [
                        line[len("geodata metadata: ") :]
                        for line in banner_lines
                        if line.startswith("geodata metadata: ")
                    ],
                    "ephemeris_files": [
                        line[len("ephemeris file: ") :]
                        for line in banner_lines
                        if line.startswith("ephemeris file: ")
                    ],
                }
                report.measurements = context.measurements
                report.measurements["jammu"] = {
                    "available": context.jammu_available,
                    "reason": context.jammu_reason,
                }
                report.measurements["default_place"] = context.default_place
                report.measurements["cli_runs"] = cli.runs
                browser_context.close()
                browser.close()
        exit_code = 1 if report.failed() else 0
    finally:
        report.measurements.setdefault("server", {})
        if args.keep_server:
            report.measurements["server"]["stopped"] = False
            print(f"the viewer is still serving on {viewer_process.url}", flush=True)
        else:
            code = viewer_process.stop()
            report.measurements["server"]["stopped"] = True
            report.measurements["server"]["exit_code"] = code
        report.measurements["server"]["stderr"] = [
            {"at": round(when, 4), "line": text} for when, text in viewer_process.stderr_lines
        ]
        report.measurements["server"]["stdout"] = list(viewer_process.stdout_lines)
        (out / "report.json").write_text(
            json.dumps(report.as_dict(), indent=1, ensure_ascii=False), encoding="utf-8"
        )
        summary = report.as_dict()["counts"]
        print(
            f"report: {out / 'report.json'}  "
            f"pass={summary.get('pass', 0)} fail={summary.get('fail', 0)} "
            f"skipped={summary.get('skipped', 0)}",
            flush=True,
        )
    return exit_code


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
