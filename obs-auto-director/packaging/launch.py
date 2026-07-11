"""AutoDirector.app entry point.

Launches the engine + Control Room UI with the default config location
(~/.autodirector/config.json — created on first run) and opens the
browser. Double-click experience: the app starts, the Control Room
appears, first-run users land in guided Setup.
"""

import sys

from autodirector.app import main

if __name__ == "__main__":
    sys.exit(main(["app"]))
