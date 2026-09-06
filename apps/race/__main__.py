"""Entry point: `python -m apps.race run|test [--fixed]`."""

import sys

from apps.race.app import main

if __name__ == "__main__":
    args = sys.argv[1:]
    fixed = "--fixed" in args
    positional = [a for a in args if a != "--fixed"]
    command = positional[0] if positional else "run"

    if command not in ("run", "test"):
        print("usage: python -m apps.race run|test [--fixed]", file=sys.stderr)
        sys.exit(2)

    sys.exit(main(machine_mode=(command == "test"), fixed=fixed))
