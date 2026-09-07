"""Entry point: `python -m apps.fd_limit run|test [--fixed]`.

Accepts the command (run|test) and the flags in any order, matching the
interface contract in docs/faultyapps.md section 2.
"""

import sys

try:
    from apps.fd_limit.app import main
except ModuleNotFoundError:
    try:
        from .app import main
    except ImportError:
        from app import main

USAGE = "usage: python -m apps.fd_limit run|test [--fixed]"

if __name__ == "__main__":
    args = sys.argv[1:]
    fixed = "--fixed" in args
    args = [a for a in args if a != "--fixed"]
    kwargs = {}
    command = args[0] if args else "run"
    if command not in ("run", "test"):
        print(USAGE, file=sys.stderr)
        sys.exit(2)

    sys.exit(main(machine_mode=(command == "test"), fixed=fixed, **kwargs))
