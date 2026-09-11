"""Tests for Layer 11's command line front end (specification section 10.B).

``cli.run`` is called in process for almost everything, so the exit code, the
exact stdout bytes and the stderr wording can all be asserted directly; three
real subprocesses cover what only the executable boundary can show -- ``--help``,
a plain successful run through ``__main__``, and a reader that closes the pipe.

Every filesystem failure is *injected* on the exact call (``os.open``,
``os.write``, ``os.fsync``, ``os.replace``, ``os.unlink``, ``os.path.samefile``)
rather than produced with ``chmod``, so no case depends on the test user's
privileges. The destination protections are the reason for that care: the
claims are that the CLI never writes over an input resource, never through a
symlink or onto a non-regular file, never replaces a file it was not explicitly
told to replace, and removes on failure only a file it can still prove is its
own.
"""

import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest

from render_helpers import EPHE_DIR, FIXTURE_DB, GOLDEN_DIR, REPO_ROOT
from vedic_chart.app import cli
from vedic_chart.app.pipeline import EPHEMERIS_FILE_SIZES, ChartConfig
from vedic_chart.location.offline import db as db_module
from vedic_chart.location.offline.resolver import OfflineLocationResolver

EPHE_PATH = Path(EPHE_DIR)
GOLDEN = (GOLDEN_DIR / "jalandhar_nocaption_degrees.svg").read_bytes()

OK = 0
UNEXPECTED = 1
INPUT = 2
PLACE = 3
CONFIG = 4
OUTPUT = 5


def argv_for(
    out,
    *,
    place="Jalandhar",
    date="1995-03-21",
    time="06:45",
    geodata=FIXTURE_DB,
    ephemeris=EPHE_PATH,
    extra=(),
):
    return [
        "--date", date,
        "--time", time,
        "--place", place,
        "--geodata", str(geodata),
        "--ephemeris", str(ephemeris),
        "--out", str(out),
        *extra,
    ]


def invoke(capfdbinary, argv):
    """Run the CLI in process and return (code, stdout_broken, stdout, stderr)."""
    code, broken = cli.run(argv)
    captured = capfdbinary.readouterr()
    return code, broken, captured.out, captured.err.decode("utf-8")


def linked_ephemeris(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, _size in EPHEMERIS_FILE_SIZES:
        os.symlink(EPHE_PATH / name, directory / name)
    return directory


def forbid_the_resolver(monkeypatch) -> None:
    """Prove a refusal happened before any database was opened."""

    def forbidden(self, *args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("the geodata database was opened")

    monkeypatch.setattr(OfflineLocationResolver, "__init__", forbidden)


def temporaries_in(directory: Path) -> list[Path]:
    return [path for path in directory.iterdir() if path.name.endswith(".tmp")]


# --- success ---------------------------------------------------------------


def test_a_file_destination_receives_the_golden_bytes(capfdbinary, tmp_path):
    destination = tmp_path / "jalandhar.svg"

    code, broken, out, err = invoke(capfdbinary, argv_for(destination))

    assert (code, broken) == (OK, False)
    assert destination.read_bytes() == GOLDEN
    assert out == b""
    assert err == ""


def test_stdout_receives_the_golden_bytes_and_nothing_else(
    capfdbinary, tmp_path
):
    code, broken, out, err = invoke(capfdbinary, argv_for("-"))

    assert (code, broken) == (OK, False)
    assert out == GOLDEN
    assert err == ""


def test_main_returns_only_the_exit_code(capfdbinary, tmp_path):
    result = cli.main(argv_for(tmp_path / "chart.svg"))
    capfdbinary.readouterr()

    assert result == OK


def test_the_options_reach_the_renderer(capfdbinary, tmp_path):
    destination = tmp_path / "chart.svg"

    code, _broken, _out, _err = invoke(
        capfdbinary,
        argv_for(
            destination,
            extra=("--caption", "--width", "800", "--id-prefix", "chart-7"),
        ),
    )
    document = destination.read_text(encoding="utf-8")

    assert code == OK
    assert 'width="800"' in document
    assert "chart-7-title" in document


def test_no_degrees_matches_its_golden(capfdbinary, tmp_path):
    destination = tmp_path / "chart.svg"

    invoke(capfdbinary, argv_for(destination, extra=("--no-degrees",)))

    assert destination.read_bytes() == (
        GOLDEN_DIR / "jalandhar_nocaption_nodegrees.svg"
    ).read_bytes()


def test_help_goes_to_stdout_and_exits_zero(capfdbinary, tmp_path):
    code, broken, out, err = invoke(capfdbinary, ["--help"])

    assert (code, broken) == (OK, False)
    assert b"usage:" in out
    assert err == ""


# --- exit codes by type ----------------------------------------------------


def test_an_impossible_date_is_an_input_error(capfdbinary, tmp_path):
    code, _broken, out, err = invoke(
        capfdbinary, argv_for(tmp_path / "c.svg", date="2023-02-30")
    )

    assert code == INPUT
    assert out == b""
    assert "Invalid birth date" in err


def test_an_impossible_time_is_an_input_error(capfdbinary, tmp_path):
    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(tmp_path / "c.svg", time="25:00")
    )

    assert code == INPUT
    assert "Invalid birth time" in err


def test_fractional_seconds_are_rejected_by_the_parser(capfdbinary, tmp_path):
    code, _broken, out, err = invoke(
        capfdbinary, argv_for(tmp_path / "c.svg", time="06:45:30.5")
    )

    assert code == INPUT
    assert out == b""
    assert "fractional seconds" in err


def test_a_malformed_date_is_rejected_by_the_parser(capfdbinary, tmp_path):
    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(tmp_path / "c.svg", date="21/03/1995")
    )

    assert code == INPUT
    assert "YYYY-MM-DD" in err


def test_a_missing_out_is_a_usage_error(capfdbinary):
    code, _broken, _out, err = invoke(
        capfdbinary,
        [
            "--date", "1995-03-21", "--time", "06:45", "--place", "Jalandhar",
            "--geodata", str(FIXTURE_DB), "--ephemeris", str(EPHE_PATH),
        ],
    )

    assert code == INPUT
    assert "--out" in err


def test_a_daylight_saving_gap_is_an_input_error(capfdbinary, tmp_path):
    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            tmp_path / "c.svg", place="London", date="2023-03-26", time="01:30"
        ),
    )

    assert code == INPUT
    assert "error:" in err


def test_a_bad_id_prefix_is_refused_before_the_database_opens(
    monkeypatch, capfdbinary, tmp_path
):
    forbid_the_resolver(monkeypatch)

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(tmp_path / "c.svg", extra=("--id-prefix", "9bad prefix!")),
    )

    assert code == INPUT
    assert "id_prefix" in err


def test_a_bad_width_is_refused(capfdbinary, tmp_path):
    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(tmp_path / "c.svg", extra=("--width", "0"))
    )

    assert code == INPUT
    assert "width" in err


def test_an_ambiguous_place_lists_its_candidates(capfdbinary, tmp_path):
    code, _broken, out, err = invoke(
        capfdbinary, argv_for(tmp_path / "c.svg", place="Springfield")
    )

    assert code == PLACE
    assert out == b""
    assert "Springfield, Illinois, United States (pop " in err
    assert "Add a qualifier" in err
    assert len(re.findall(r"^  Springfield, ", err, re.MULTILINE)) <= 5
    assert not (tmp_path / "c.svg").exists()


def test_an_unknown_place_is_a_place_error(capfdbinary, tmp_path):
    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(tmp_path / "c.svg", place="Xyzzyville")
    )

    assert code == PLACE
    assert "Xyzzyville" in err


def test_a_missing_ephemeris_file_is_a_configuration_error(
    capfdbinary, tmp_path
):
    ephemeris = linked_ephemeris(tmp_path / "ephe")
    (ephemeris / "sepl_18.se1").unlink()

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(tmp_path / "c.svg", ephemeris=ephemeris)
    )

    assert code == CONFIG
    assert "sepl_18.se1" in err


def test_a_database_with_the_wrong_schema_is_a_configuration_error(
    capfdbinary, tmp_path
):
    broken_db = tmp_path / "broken.sqlite"
    connection = sqlite3.connect(broken_db)
    connection.execute("CREATE TABLE places (geoname_id INTEGER)")
    connection.commit()
    connection.close()

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(tmp_path / "c.svg", geodata=broken_db)
    )

    assert code == CONFIG
    assert "missing tables" in err


def test_a_birth_outside_coverage_is_the_generic_failure(
    capfdbinary, tmp_path
):
    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(tmp_path / "c.svg", date="1750-06-01")
    )

    assert code == UNEXPECTED
    assert "RuntimeError" in err
    assert "Traceback" not in err


def test_the_generic_failure_shows_a_traceback_only_when_verbose(
    capfdbinary, tmp_path
):
    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(tmp_path / "c.svg", date="1750-06-01", extra=("--verbose",)),
    )

    assert code == UNEXPECTED
    assert "Traceback" in err


def test_an_interrupt_is_exit_130(monkeypatch, capfdbinary, tmp_path):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_execute", interrupted)

    code, broken, _out, err = invoke(capfdbinary, argv_for(tmp_path / "c.svg"))

    assert (code, broken) == (130, False)
    assert "interrupted" in err


# --- error scopes ----------------------------------------------------------


def test_an_os_error_from_inside_the_pipeline_is_not_an_output_error(
    monkeypatch, capfdbinary, tmp_path
):
    def refusing(db_path):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(db_module, "connect", refusing)

    code, _broken, _out, err = invoke(capfdbinary, argv_for(tmp_path / "c.svg"))

    assert code == UNEXPECTED
    assert "PermissionError" in err


def test_a_value_error_from_inside_the_pipeline_is_not_an_input_error(
    monkeypatch, capfdbinary, tmp_path
):
    def exploding(request, config, options):
        raise ValueError("injected pipeline failure")

    monkeypatch.setattr(cli, "render_birth_chart", exploding)

    code, _broken, _out, err = invoke(capfdbinary, argv_for(tmp_path / "c.svg"))

    assert code == UNEXPECTED
    assert "injected pipeline failure" in err


# --- destination protection ------------------------------------------------


def test_an_existing_file_is_not_overwritten_without_force(
    monkeypatch, capfdbinary, tmp_path
):
    destination = tmp_path / "chart.svg"
    destination.write_bytes(b"mine\n")
    forbid_the_resolver(monkeypatch)

    code, _broken, _out, err = invoke(capfdbinary, argv_for(destination))

    assert code == OUTPUT
    assert destination.read_bytes() == b"mine\n"
    assert "--force" in err


def test_a_file_that_appears_after_the_pre_check_is_not_overwritten(
    monkeypatch, capfdbinary, tmp_path
):
    destination = tmp_path / "chart.svg"
    original = cli.render_birth_chart

    def intruding(request, config, options):
        result = original(request, config, options)
        destination.write_bytes(b"someone else got here first\n")
        return result

    monkeypatch.setattr(cli, "render_birth_chart", intruding)

    code, _broken, _out, err = invoke(capfdbinary, argv_for(destination))

    assert code == OUTPUT
    assert destination.read_bytes() == b"someone else got here first\n"
    assert "appeared" in err


def test_force_replaces_and_leaves_no_temporary(capfdbinary, tmp_path):
    destination = tmp_path / "chart.svg"
    destination.write_bytes(b"old\n")

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(destination, extra=("--force",))
    )

    assert code == OK
    assert destination.read_bytes() == GOLDEN
    assert temporaries_in(tmp_path) == []
    assert err == ""


def test_a_missing_parent_directory_is_an_output_error(capfdbinary, tmp_path):
    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(tmp_path / "absent" / "chart.svg")
    )

    assert code == OUTPUT
    assert "never creates directories" in err


def test_a_directory_destination_is_refused(capfdbinary, tmp_path):
    directory = tmp_path / "charts"
    directory.mkdir()

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(directory, extra=("--force",))
    )

    assert code == OUTPUT
    assert "not a regular file" in err
    assert directory.is_dir()


def test_a_symlink_destination_is_refused_even_with_force(
    capfdbinary, tmp_path
):
    target = tmp_path / "target.svg"
    target.write_bytes(b"target bytes\n")
    link = tmp_path / "link.svg"
    link.symlink_to(target)

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(link, extra=("--force",))
    )

    assert code == OUTPUT
    assert "symbolic link" in err
    assert link.is_symlink()
    assert target.read_bytes() == b"target bytes\n"


def test_a_dangling_symlink_destination_is_refused(capfdbinary, tmp_path):
    link = tmp_path / "link.svg"
    link.symlink_to(tmp_path / "nowhere.svg")

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(link, extra=("--force",))
    )

    assert code == OUTPUT
    assert "symbolic link" in err
    assert link.is_symlink()
    assert not (tmp_path / "nowhere.svg").exists()


def test_a_fifo_destination_is_refused_even_with_force(capfdbinary, tmp_path):
    fifo = tmp_path / "chart.svg"
    os.mkfifo(fifo)

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(fifo, extra=("--force",))
    )

    assert code == OUTPUT
    assert "not a regular file" in err
    assert os.path.exists(fifo)
    import stat as stat_module

    assert stat_module.S_ISFIFO(os.lstat(fifo).st_mode)


def test_a_socket_destination_is_refused_even_with_force(
    monkeypatch, capfdbinary, tmp_path
):
    # Bound by a relative name from inside tmp_path: an absolute temporary
    # path can exceed the AF_UNIX sun_path limit.
    monkeypatch.chdir(tmp_path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        try:
            server.bind("s.svg")
        except OSError as exc:  # pragma: no cover - platform dependent
            pytest.skip(f"cannot bind a unix socket here: {exc}")

        code, _broken, _out, err = invoke(
            capfdbinary, argv_for("s.svg", extra=("--force",))
        )

        import stat as stat_module

        assert code == OUTPUT
        assert "not a regular file" in err
        assert stat_module.S_ISSOCK(os.lstat(tmp_path / "s.svg").st_mode)
    finally:
        server.close()


@pytest.mark.parametrize("index", range(3))
def test_an_ephemeris_file_is_never_the_destination(
    capfdbinary, tmp_path, index
):
    name = EPHEMERIS_FILE_SIZES[index][0]
    target = EPHE_PATH / name
    before = target.stat()

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(target, extra=("--force",))
    )
    after = target.stat()

    assert code == OUTPUT
    assert "input resource" in err
    assert (after.st_size, after.st_mtime_ns) == (
        before.st_size,
        before.st_mtime_ns,
    )


def test_the_geodata_file_is_never_the_destination(capfdbinary, tmp_path):
    before = FIXTURE_DB.stat()

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(FIXTURE_DB, extra=("--force",))
    )
    after = FIXTURE_DB.stat()

    assert code == OUTPUT
    assert "input resource" in err
    assert (after.st_size, after.st_mtime_ns) == (
        before.st_size,
        before.st_mtime_ns,
    )


def test_a_relative_spelling_of_an_input_resource_is_refused(
    monkeypatch, capfdbinary
):
    monkeypatch.chdir(REPO_ROOT)
    before = FIXTURE_DB.stat()

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            "tests/fixtures/geodata_fixture.sqlite", extra=("--force",)
        ),
    )

    assert code == OUTPUT
    assert "input resource" in err
    assert FIXTURE_DB.stat().st_mtime_ns == before.st_mtime_ns


def test_a_dotted_spelling_resolves_to_the_same_destination(
    capfdbinary,
):
    """The normalised destination -- not the raw path -- is what is checked."""
    spelled = FIXTURE_DB.parent / ".." / "fixtures" / "geodata_fixture.sqlite"
    before = FIXTURE_DB.stat()

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(spelled, extra=("--force",))
    )

    assert code == OUTPUT
    assert "input resource" in err
    assert FIXTURE_DB.stat().st_mtime_ns == before.st_mtime_ns


def test_a_hard_link_to_an_input_resource_is_refused(capfdbinary, tmp_path):
    geodata = tmp_path / "geo.sqlite"
    geodata.write_bytes(b"a geodata file for the alias check\n")
    alias = tmp_path / "alias.sqlite"
    os.link(geodata, alias)
    ephemeris = linked_ephemeris(tmp_path / "ephe")

    code, _broken, _out, err = invoke(
        capfdbinary,
        argv_for(
            alias, geodata=geodata, ephemeris=ephemeris, extra=("--force",)
        ),
    )

    assert code == OUTPUT
    assert "same file as" in err
    assert geodata.read_bytes() == b"a geodata file for the alias check\n"
    assert alias.read_bytes() == b"a geodata file for the alias check\n"


def test_an_unverifiable_destination_is_refused(
    monkeypatch, capfdbinary, tmp_path
):
    destination = tmp_path / "chart.svg"
    destination.write_bytes(b"existing\n")

    def refusing(one, other):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os.path, "samefile", refusing)

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(destination, extra=("--force",))
    )

    assert code == OUTPUT
    assert "unverifiable destination" in err
    assert destination.read_bytes() == b"existing\n"


# --- failed and partial writes ---------------------------------------------


def test_a_failed_direct_write_removes_the_file_it_created(
    monkeypatch, capfdbinary, tmp_path
):
    destination = tmp_path / "chart.svg"

    def failing(fd, data):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "write", failing)

    code, _broken, _out, err = invoke(capfdbinary, argv_for(destination))

    assert code == OUTPUT
    assert not destination.exists()
    assert "No space left on device" in err
    assert f"removed partial output {destination}" in err
    assert err.index("No space left") < err.index("removed partial output")


def test_a_failed_direct_write_leaves_a_replaced_destination_alone(
    monkeypatch, capfdbinary, tmp_path
):
    """The conservative cleanup: never unlink a path proven not to be ours."""
    destination = tmp_path / "chart.svg"
    intruder = tmp_path / "intruder"
    intruder.write_bytes(b"another process wrote this\n")
    real_replace = os.replace

    def failing(fd, data):
        real_replace(intruder, destination)
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(os, "write", failing)

    code, _broken, _out, err = invoke(capfdbinary, argv_for(destination))

    assert code == OUTPUT
    assert destination.read_bytes() == b"another process wrote this\n"
    assert f"partial output may remain at {destination}" in err
    assert "not removed because the path no longer refers" in err


def test_a_cleanup_failure_is_reported_after_the_original_error(
    monkeypatch, capfdbinary, tmp_path
):
    destination = tmp_path / "chart.svg"

    def failing_write(fd, data):
        raise OSError(28, "No space left on device")

    def failing_unlink(path, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os, "write", failing_write)
    monkeypatch.setattr(os, "unlink", failing_unlink)

    code, _broken, _out, err = invoke(capfdbinary, argv_for(destination))

    assert code == OUTPUT
    assert err.index("No space left on device") < err.index(
        "warning: could not remove partial output"
    )
    assert "Permission denied" in err


def test_a_refused_create_is_an_output_error(monkeypatch, capfdbinary, tmp_path):
    destination = tmp_path / "chart.svg"
    real_open = os.open

    def refusing(path, flags, mode=0o777, **kwargs):
        if str(path) == str(destination):
            raise PermissionError(13, "Permission denied")
        return real_open(path, flags, mode, **kwargs)

    monkeypatch.setattr(os, "open", refusing)

    code, _broken, _out, err = invoke(capfdbinary, argv_for(destination))

    assert code == OUTPUT
    assert "could not create" in err
    assert not destination.exists()


def test_a_failed_fsync_removes_the_temporary(
    monkeypatch, capfdbinary, tmp_path
):
    destination = tmp_path / "chart.svg"
    destination.write_bytes(b"old\n")

    def failing(fd):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(os, "fsync", failing)

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(destination, extra=("--force",))
    )

    assert code == OUTPUT
    assert destination.read_bytes() == b"old\n"
    assert temporaries_in(tmp_path) == []
    assert "removed partial output" in err


def test_a_failed_replace_removes_the_temporary_and_spares_the_original(
    monkeypatch, capfdbinary, tmp_path
):
    destination = tmp_path / "chart.svg"
    destination.write_bytes(b"old\n")

    def failing(source, target):
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(os, "replace", failing)

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(destination, extra=("--force",))
    )

    assert code == OUTPUT
    assert destination.read_bytes() == b"old\n"
    assert temporaries_in(tmp_path) == []
    assert "removed partial output" in err


def test_a_replaced_temporary_is_left_alone_after_a_failed_replace(
    monkeypatch, capfdbinary, tmp_path
):
    destination = tmp_path / "chart.svg"
    destination.write_bytes(b"old\n")
    intruder = tmp_path / "intruder"
    intruder.write_bytes(b"another process wrote this\n")
    real_replace = os.replace

    def failing(source, target):
        real_replace(intruder, source)
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(os, "replace", failing)

    code, _broken, _out, err = invoke(
        capfdbinary, argv_for(destination, extra=("--force",))
    )
    leftovers = temporaries_in(tmp_path)

    assert code == OUTPUT
    assert destination.read_bytes() == b"old\n"
    assert len(leftovers) == 1
    assert leftovers[0].read_bytes() == b"another process wrote this\n"
    assert "partial output may remain at" in err
    assert "not removed because the path no longer refers" in err


# --- stdout ----------------------------------------------------------------


class _BrokenBuffer:
    def __init__(self, error):
        self._error = error
        self.written = BytesIO()

    def write(self, data):
        raise self._error

    def flush(self):  # pragma: no cover - never reached in these tests
        raise AssertionError("flush must not follow a failed write")


class _UnflushableBuffer:
    def __init__(self):
        self.written = BytesIO()

    def write(self, data):
        return self.written.write(data)

    def flush(self):
        raise OSError(5, "Input/output error")


class _FakeStdout:
    def __init__(self, buffer):
        self.buffer = buffer


def test_a_broken_pipe_sets_the_flag_and_touches_no_descriptor(
    monkeypatch, capfdbinary
):
    redirections = []
    real_dup2 = os.dup2

    def recording_dup2(*args, **kwargs):
        redirections.append(args)
        return real_dup2(*args, **kwargs)

    monkeypatch.setattr(
        sys,
        "stdout",
        _FakeStdout(_BrokenBuffer(BrokenPipeError(32, "Broken pipe"))),
    )
    monkeypatch.setattr(os, "dup2", recording_dup2)
    try:
        code, broken = cli.run(argv_for("-"))
    finally:
        # Restore before pytest's own capture machinery runs again: it uses
        # both sys.stdout and os.dup2.
        monkeypatch.undo()
    err = capfdbinary.readouterr().err.decode("utf-8")

    assert (code, broken) == (OUTPUT, True)
    assert err.count("stdout closed by reader") == 1
    assert redirections == []


def test_a_failed_flush_is_an_output_error_without_the_flag(
    monkeypatch, capfdbinary
):
    monkeypatch.setattr(sys, "stdout", _FakeStdout(_UnflushableBuffer()))
    try:
        code, broken = cli.run(argv_for("-"))
    finally:
        monkeypatch.undo()
    err = capfdbinary.readouterr().err.decode("utf-8")

    assert (code, broken) == (OUTPUT, False)
    assert "could not flush stdout" in err


def test_a_plain_os_error_on_stdout_does_not_set_the_flag(
    monkeypatch, capfdbinary
):
    monkeypatch.setattr(
        sys,
        "stdout",
        _FakeStdout(_BrokenBuffer(OSError(5, "Input/output error"))),
    )
    try:
        code, broken = cli.run(argv_for("-"))
    finally:
        monkeypatch.undo()
    capfdbinary.readouterr()

    assert (code, broken) == (OUTPUT, False)


# --- defaults --------------------------------------------------------------


def test_the_defaults_are_resolved_against_the_working_directory(
    monkeypatch, capfdbinary, tmp_path
):
    workspace = tmp_path / "workspace"
    (workspace / "data").mkdir(parents=True)
    (workspace / "ephe").mkdir()
    shutil.copy(FIXTURE_DB, workspace / "data" / "geodata.sqlite")
    for name, _size in EPHEMERIS_FILE_SIZES:
        shutil.copy(EPHE_PATH / name, workspace / "ephe" / name)
    monkeypatch.chdir(workspace)

    code, _broken, _out, err = invoke(
        capfdbinary,
        [
            "--date", "1995-03-21", "--time", "06:45", "--place", "Jalandhar",
            "--out", "chart.svg", "--verbose",
        ],
    )
    resolved = workspace.resolve()

    assert code == OK
    assert f"geodata: {resolved / 'data' / 'geodata.sqlite'}" in err
    assert f"ephemeris: {resolved / 'ephe'}" in err
    assert "place: Jalandhar, Punjab, India" in err
    assert "chosen: Jalandhar" in err
    assert (workspace / "chart.svg").read_bytes() == GOLDEN


# --- the executable boundary -----------------------------------------------


def child_environment():
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    return environment


def test_the_module_runs_as_a_command(tmp_path):
    destination = tmp_path / "chart.svg"
    completed = subprocess.run(
        [sys.executable, "-m", "vedic_chart.app", *argv_for(destination)],
        cwd=REPO_ROOT,
        env=child_environment(),
        capture_output=True,
    )

    assert completed.returncode == OK
    assert completed.stdout == b""
    assert destination.read_bytes() == GOLDEN


def test_the_command_prints_usage_for_help():
    completed = subprocess.run(
        [sys.executable, "-m", "vedic_chart.app", "--help"],
        cwd=REPO_ROOT,
        env=child_environment(),
        capture_output=True,
    )

    assert completed.returncode == OK
    assert b"usage:" in completed.stdout
    assert completed.stderr == b""


def test_a_reader_that_closes_the_pipe_gets_one_clean_message():
    """The shutdown flush must not raise a second time and print a traceback."""
    process = subprocess.Popen(
        [sys.executable, "-m", "vedic_chart.app", *argv_for("-")],
        cwd=REPO_ROOT,
        env=child_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Close the read end before the child can render anything, so its first
    # write to stdout is guaranteed to find no reader.
    process.stdout.close()
    _out, err = process.communicate()
    stderr = err.decode("utf-8")

    assert process.returncode == OUTPUT
    assert stderr.count("stdout closed by reader") == 1
    assert "Traceback" not in stderr
