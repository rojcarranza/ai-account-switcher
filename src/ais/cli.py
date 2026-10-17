import argparse
import os
import sys
from pathlib import Path
from typing import List, NoReturn, Optional

from ais import __version__, core, providers
from ais.accounts import EXIT_USAGE, load_config
from ais.errors import AisError
from ais.store import Store


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise AisError(EXIT_USAGE, "%s\n%s" % (self.format_usage().rstrip(), message))


def _parser() -> argparse.ArgumentParser:
    p = _Parser(prog="ais")
    p.add_argument("--version", action="store_true")
    sub = p.add_subparsers(dest="command", parser_class=_Parser)
    login = sub.add_parser("login", help="sign an account in")
    login.add_argument("account")
    login.add_argument("--dry-run", action="store_true")
    login.add_argument("--allow-api-key", action="store_true")
    return p


def _context() -> core.Context:
    store = Store(Path.home())
    return core.Context(store, load_config(store, providers.REGISTRY),
                        lambda a: providers.get(a.provider), dict(os.environ), Path.cwd())


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        ns = _parser().parse_args(args)
        if ns.version:
            print("ais " + __version__)
            return 0
        if ns.command is None:
            raise AisError(EXIT_USAGE, _parser().format_usage().rstrip())
        return core.cmd_login(_context(), ns.account, ns.dry_run, ns.allow_api_key)
    except AisError as e:
        print("ais: " + e.message, file=sys.stderr)
        return e.code
