import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, NoReturn, Optional

from ais import __version__, core, providers
from ais.accounts import EXIT_USAGE, Config, load_config
from ais.errors import AisError
from ais.store import Store


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise AisError(EXIT_USAGE, "%s\n%s" % (message, self.format_usage().rstrip()))


def _parser() -> argparse.ArgumentParser:
    p = _Parser(prog="ais", allow_abbrev=False)
    p.add_argument("--version", action="store_true")
    sub = p.add_subparsers(dest="command", parser_class=_Parser)
    login = sub.add_parser("login", help="sign an account in", allow_abbrev=False)
    login.add_argument("account", nargs="?")  # missing -> Config.get lists the names
    login.add_argument("--dry-run", action="store_true")
    login.add_argument("--allow-api-key", action="store_true")
    run = sub.add_parser("run", help="start claude on an account", allow_abbrev=False)
    run.add_argument("account", nargs="?")  # default = config.default
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--allow-api-key", action="store_true")
    switch = sub.add_parser("switch", help="resume a session on another account", allow_abbrev=False)
    switch.add_argument("account", nargs="?")  # missing -> the session's other account
    switch.add_argument("--pick", action="store_true")
    switch.add_argument("--session")
    switch.add_argument("--dry-run", action="store_true")
    switch.add_argument("--allow-api-key", action="store_true")
    status = sub.add_parser("status", help="show credentials, the newest session and the self-check",
                            allow_abbrev=False)
    status.add_argument("--json", action="store_true")
    setup = sub.add_parser("setup", help="guided first-time setup", allow_abbrev=False)
    setup.add_argument("--dry-run", action="store_true")
    uninstall = sub.add_parser("uninstall", help="remove ais's own files", allow_abbrev=False)
    uninstall.add_argument("--dry-run", action="store_true")
    return p


def _context(started: float, config: Optional[Config] = None) -> core.Context:
    store = Store(Path.home())
    try:
        cwd = Path.cwd()
    except OSError:
        raise AisError(66, "the current folder no longer exists")
    return core.Context(store, config or load_config(store, providers.REGISTRY),
                        lambda a: providers.get(a.provider), dict(os.environ), cwd, started=started)


def main(argv: Optional[List[str]] = None) -> int:
    started = time.monotonic()  # FR-3.14 tool time starts here
    args = sys.argv[1:] if argv is None else argv
    passthrough = []  # type: List[str]
    if args[:1] == ["run"] and "--" in args:  # everything after the first "--" goes to claude untouched
        i = args.index("--")
        args, passthrough = args[:i], args[i + 1:]
    try:
        ns = _parser().parse_args(args)
        if ns.version:
            print("ais " + __version__)
            return 0
        if ns.command is None:
            raise AisError(EXIT_USAGE, "a command is required\n" + _parser().format_usage().rstrip())
        if ns.command == "run":
            return core.cmd_run(_context(started), ns.account, passthrough, ns.allow_api_key, ns.dry_run)
        if ns.command == "switch":
            if ns.pick and ns.session is not None:
                raise AisError(EXIT_USAGE, "--pick and --session cannot be combined")
            return core.cmd_switch(_context(started), ns.account, ns.pick, ns.session,
                                   ns.allow_api_key, ns.dry_run)
        if ns.command == "setup":  # no config exists yet: a placeholder one
            return core.cmd_setup(_context(started, Config({}, "", {}, False)), ns.dry_run)
        if ns.command == "uninstall":  # works with a broken or missing config
            try:
                ctx = _context(started)
            except AisError:
                ctx = _context(started, Config({}, "", {}, False))
            return core.cmd_uninstall(ctx, ns.dry_run)
        if ns.command == "status":
            return core.cmd_status(_context(started), ns.json)
        return core.cmd_login(_context(started), ns.account or "", ns.dry_run, ns.allow_api_key)
    except KeyboardInterrupt:
        return 130
    except AisError as e:
        print("ais: " + e.message, file=sys.stderr)
        return e.code
