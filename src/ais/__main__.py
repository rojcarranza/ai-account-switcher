import sys

from ais import cli


def run() -> None:
    # zipapp ignores main()'s return value, so exit explicitly.
    sys.exit(cli.main())


if __name__ == "__main__":
    run()
