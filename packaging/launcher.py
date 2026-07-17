"""Frozen-app entry point.

PyInstaller executes its entry script as __main__, so pointing it straight at
src/filery/app.py breaks that module's relative imports ("attempted relative
import with no known parent package"). Importing the package by name instead keeps
app.py a normal package module.

`--cli` runs the command-line interface from inside the bundle, which is how the
packaged build gets exercised in CI without a display.
"""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()  # no-op unless a dep spawns workers

    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        from filery.cli import main
        raise SystemExit(main(sys.argv[2:]))

    from filery.app import main
    raise SystemExit(main())
