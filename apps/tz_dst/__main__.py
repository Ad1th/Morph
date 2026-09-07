"""Entry point: `python -m apps.tz_dst run|test [--fixed] [--tz ZONE]`.

Accepts the command (run|test) and the flags in any order, matching the
interface contract in docs/faultyapps.md section 2.
"""

import sys

try:
    from apps.tz_dst.app import main
except ModuleNotFoundError:
    try:
        from .app import main
    except ImportError:
        from app import main

USAGE = "usage: python -m apps.tz_dst run|test [--fixed] [--tz ZONE]"

if __name__ == "__main__":
    args = sys.argv[1:]
    fixed = "--fixed" in args
    args = [a for a in args if a != "--fixed"]
    kwargs = {}
    if "--tz" in args:
        i = args.index("--tz")
        if i + 1 >= len(args):
            print(USAGE, file=sys.stderr)
            sys.exit(2)
        kwargs["requested_tz"] = args[i + 1]
        del args[i:i + 2]
    command = args[0] if args else "run"
    if command not in ("run", "test"):
        print(USAGE, file=sys.stderr)
        sys.exit(2)

    sys.exit(main(machine_mode=(command == "test"), fixed=fixed, **kwargs))
