import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, NoReturn, Optional

from ais import __version__, core, menu, providers
from ais.accounts import EXIT_USAGE, Config, apply_default_swap, load_config
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
    dflt = sub.add_parser("default", help="make the machine's default sign-in hold an account (ADR-0011)",
                          allow_abbrev=False)
    dflt.add_argument("account", nargs="?")  # missing -> print which account the default sign-in holds
    dflt.add_argument("--dry-run", action="store_true")
    use = sub.add_parser("use", help="pick the account for this terminal window and start claude",
                         allow_abbrev=False)
    use.add_argument("account", nargs="?")  # missing -> print this window's account
    how = use.add_mutually_exclusive_group()
    how.add_argument("--shell", action="store_true", help="print the shell commands (used by ais shell-init)")
    how.add_argument("--copy", action="store_true", help="copy `ais use <account>` to the clipboard")
    sub.add_parser("shell-init", help="print the shell functions for ~/.zshrc", allow_abbrev=False)
    sub.add_parser("record", help="record the starting session's account (run by the SessionStart hook)",
                   allow_abbrev=False)
    desktop = sub.add_parser("desktop", help="open Claude Desktop for an account", allow_abbrev=False)
    desktop.add_argument("account", nargs="?")  # missing -> Config.get lists the names
    desktop.add_argument("--dry-run", action="store_true")
    status = sub.add_parser("status", help="show credentials, the newest session and the self-check",
                            allow_abbrev=False)
    status.add_argument("--json", action="store_true")
    setup = sub.add_parser("setup", help="guided first-time setup", allow_abbrev=False)
    setup.add_argument("--dry-run", action="store_true")
    uninstall = sub.add_parser("uninstall", help="remove ais's own files", allow_abbrev=False)
    uninstall.add_argument("--dry-run", action="store_true")
    menu_p = sub.add_parser("menu", help="SwiftBar menu", allow_abbrev=False)
    menu_sub = menu_p.add_subparsers(dest="menu_command", parser_class=_Parser)
    menu_sub.add_parser("render", help="print the SwiftBar menu", allow_abbrev=False)
    for name, text in (("install", "write the SwiftBar plugin"), ("uninstall", "remove the SwiftBar plugin")):
        sp = menu_sub.add_parser(name, help=text, allow_abbrev=False)
        sp.add_argument("--dry-run", action="store_true", help="print what would happen, change nothing")
    hook_p = sub.add_parser("hook", help="Claude Code SessionStart hook that records each session's account",
                            allow_abbrev=False)
    hook_sub = hook_p.add_subparsers(dest="hook_command", parser_class=_Parser)
    for name, text in (("install", "add ais's hook to ~/.claude/settings.json"),
                       ("uninstall", "remove ais's hook from ~/.claude/settings.json")):
        sp = hook_sub.add_parser(name, help=text, allow_abbrev=False)
        sp.add_argument("--dry-run", action="store_true", help="print what would happen, change nothing")
    return p


def _context(started: float, config: Optional[Config] = None, cwd_optional: bool = False,
             swap: bool = True) -> core.Context:
    store = Store(Path.home())
    try:
        cwd = Path.cwd()
    except OSError:
        if not cwd_optional:
            raise AisError(66, "the current folder no longer exists")
        cwd = Path.home()  # uninstall never reads the cwd
    if config is None:
        config = load_config(store, providers.REGISTRY)
        if swap:  # ADR-0011: the default sign-in may hold another account's login
            try:
                holds = store.read_json("state.json").get("default_holds")
            except AisError:  # a damaged state.json is reported where it is used, not here
                holds = None
            config = apply_default_swap(config, holds)
    return core.Context(store, config,
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
        if ns.command == "use":
            if (ns.shell or ns.copy) and ns.account is None:
                raise AisError(EXIT_USAGE, "--shell and --copy need an account")
            return core.cmd_use(_context(started), ns.account, ns.shell, ns.copy)
        if ns.command == "default":  # works on the raw config: it manages the swap itself
            return core.cmd_default(_context(started, swap=False), ns.account, ns.dry_run)
        if ns.command == "record":  # ADR-0010: a broken ais never blocks or clutters a session
            try:
                return core.cmd_record(_context(started, cwd_optional=True), sys.stdin.read(core.HOOK_INPUT_MAX + 1))
            except Exception:  # noqa: BLE001 - the hook must always exit 0 silently
                return 0
        if ns.command == "shell-init":  # needs no config
            return core.cmd_shell_init(_context(started, Config({}, "", {}, False), cwd_optional=True))
        if ns.command == "setup":  # no config exists yet: a placeholder one
            return core.cmd_setup(_context(started, Config({}, "", {}, False)), ns.dry_run)
        if ns.command == "uninstall":  # works with a broken or missing config
            try:
                ctx = _context(started, cwd_optional=True, swap=False)
            except (AisError, OSError) as e:  # 3.9's Path.exists() raises on an unreadable folder
                if os.path.lexists(str(Store(Path.home()).dir / "config.json")):  # missing = no warning
                    print("ais: warning: %s; the manual steps below are generic"
                          % (e.message if isinstance(e, AisError) else e), file=sys.stderr)
                ctx = _context(started, Config({}, "", {}, False), cwd_optional=True)
            return core.cmd_uninstall(ctx, ns.dry_run)
        if ns.command == "desktop":
            return core.cmd_desktop(_context(started, cwd_optional=True), ns.account or "", ns.dry_run)
        if ns.command == "menu":
            if ns.menu_command is None:
                raise AisError(EXIT_USAGE, "a menu command is required: render, install, uninstall")
            if ns.menu_command in ("install", "uninstall"):
                fn = core.cmd_menu_install if ns.menu_command == "install" else core.cmd_menu_uninstall
                try:
                    ctx = _context(started, cwd_optional=True)
                except (AisError, OSError):
                    if ns.menu_command == "install":
                        raise
                    ctx = _context(started, Config({}, "", {}, False), cwd_optional=True)  # uninstall needs no account
                return fn(ctx, ns.dry_run)
            menu.cmd_menu_render(lambda: _context(started, cwd_optional=True), os.path.abspath(sys.argv[0]), started)
        if ns.command == "hook":
            if ns.hook_command is None:
                raise AisError(EXIT_USAGE, "a hook command is required: install, uninstall")
            fn = core.cmd_hook_install if ns.hook_command == "install" else core.cmd_hook_uninstall
            return fn(_context(started, Config({}, "", {}, False), cwd_optional=True), ns.dry_run)  # needs no account
        if ns.command == "status":
            return core.cmd_status(_context(started), ns.json)
        return core.cmd_login(_context(started), ns.account or "", ns.dry_run, ns.allow_api_key)
    except KeyboardInterrupt:
        return 130
    except AisError as e:
        print("ais: " + e.message, file=sys.stderr)
        return e.code
