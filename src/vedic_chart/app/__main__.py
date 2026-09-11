"""The executable boundary for ``python -m vedic_chart.app``.

This is the only place that touches the process's file descriptors. When the
reader of a ``--out -`` pipe closes early, the interpreter's final flush at
shutdown would raise ``BrokenPipeError`` again and print a second traceback
after the CLI has already reported the failure cleanly; redirecting stdout to
``os.devnull`` here gives that flush somewhere harmless to go. ``cli.run`` never
does this itself, because it may be called inside a host process whose
descriptors are not ours to change.
"""

import os
import sys

from .cli import run

if __name__ == "__main__":
    exit_code, stdout_broken = run()
    if stdout_broken:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_fd, sys.stdout.fileno())
        os.close(devnull_fd)
    raise SystemExit(exit_code)
