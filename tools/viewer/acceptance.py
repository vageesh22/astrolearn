#!/usr/bin/env python3
"""Layers 14 and 15 browser acceptance: drive the viewer in a real browser, record the evidence.

Validation tooling only (Layer 14 sections 13.4 and 14, Layer 15 section 13).
This script is NOT a project dependency, is never imported by the package and is
not collected by pytest; like ``tools/render/rasterise_inspection.py`` it needs
Playwright for Python with its Chromium in the environment that runs *the
script*:

    PYTHONPATH=src python tools/viewer/acceptance.py --geodata PATH --ephemeris PATH
            --out DIR [--python PATH-TO-INTERPRETER] [--default-place-id ID]
            [--keep-server]

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
                "docs/LAYER15_VIEWER_INPUT_FLOW_SPEC.md section 13"
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

    controls = page.evaluate(
        "() => ({radios: document.querySelectorAll('input[type=\"radio\"]').length,"
        " named: document.querySelectorAll('[name=\"year_convention\"]').length,"
        " fieldsets: document.querySelectorAll('fieldset').length,"
        " legend: document.querySelectorAll('legend').length})"
    )
    check.note("controls", controls)
    check.equals("radio buttons on the page", controls["radios"], 0)
    check.equals("year_convention controls", controls["named"], 0)
    check.equals("fieldsets", controls["fieldsets"], 0)

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
