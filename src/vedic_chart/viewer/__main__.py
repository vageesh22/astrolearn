"""The executable boundary for ``python -m vedic_chart.viewer``.

Nothing but the exit code crosses this line. Unlike ``vedic_chart.app``'s
boundary there is no broken-stdout case to handle: the viewer writes the banner
to stdout and then nothing more, and every response goes to a socket, so the
interpreter's final flush has nothing left to fail on.
"""

import sys

from .server import main

if __name__ == "__main__":
    sys.exit(main())
