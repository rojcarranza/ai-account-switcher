import sys
from typing import List, Optional

from ais import __version__

EXIT_USAGE = 64


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--version"]:
        print("ais " + __version__)
        return 0
    if not args:
        print("usage: ais --version", file=sys.stderr)
        return EXIT_USAGE
    print("ais: unknown command: " + " ".join(args), file=sys.stderr)
    return EXIT_USAGE
