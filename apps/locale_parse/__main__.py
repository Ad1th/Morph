"""Entry point: `python -m apps.locale_parse run|test [--fixed] [--locale NAME]`.

--locale is how Morph drives this app on Windows, where setlocale(LC_ALL, "")
ignores the LANG/LC_ALL environment variables. On Linux/macOS, omit it and set
LANG/LC_ALL in the environment instead.
"""

import sys

try:
    from apps.locale_parse.app import main
except ModuleNotFoundError:
    try:
        from .app import main
    except ImportError:
        from app import main


USAGE = "usage: python -m apps.locale_parse run|test [--fixed] [--locale NAME]"

if __name__ == "__main__":
    args = sys.argv[1:]
    fixed = "--fixed" in args
    args = [a for a in args if a != "--fixed"]

    requested_locale = None
    if "--locale" in args:
        i = args.index("--locale")
        if i + 1 >= len(args):
            print(USAGE, file=sys.stderr)
            sys.exit(2)
        requested_locale = args[i + 1]
        del args[i:i + 2]

    command = args[0] if args else "run"
    if command not in ("run", "test"):
        print(USAGE, file=sys.stderr)
        sys.exit(2)

    sys.exit(main(machine_mode=(command == "test"), fixed=fixed,
                  requested_locale=requested_locale))
