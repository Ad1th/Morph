"""Entry point: `python -m apps.timeout run|test [--fixed]`.

Accepts the command (run|test) and the --fixed flag in any order, matching the
interface contract in docs/faultyapps.md section 2.
"""

import sys

from apps.timeout.app import main

if __name__ == "__main__":
    args = sys.argv[1:]
    fixed = "--fixed" in args
    positional = [a for a in args if a != "--fixed"]
    command = positional[0] if positional else "run"

    if command not in ("run", "test"):
        print(f"usage: python -m apps.timeout run|test [--fixed]", file=sys.stderr)
        sys.exit(2)

    sys.exit(main(machine_mode=(command == "test"), fixed=fixed))
