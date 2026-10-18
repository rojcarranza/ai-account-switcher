import contextlib
import json
import os
import re
import shlex
import shutil
import stat
import sys
import tempfile
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from ais import guards, procs, runner
from ais.accounts import EXIT_USAGE, NAME_RE, Account, Config, _check_cred_dir, load_config
from ais.errors import AisError
from ais.providers import DEFAULT_PROVIDER, REGISTRY
from ais.providers.base import Provider, Session
from ais.store import EXIT_CANNOT_WRITE, EXIT_CONFIG, Store, _size

CREDENTIAL_TTL = 600
EXIT_DECLINED = 65
EXIT_NO_INPUT = 66
EXIT_OPEN = 75
PICK_COUNT = 5
PROCESS_TIMEOUT = 3


def _read_cache(store: Store) -> dict:
    """cache.json is disposable: a corrupt one counts as empty and is removed so the next write replaces it."""
    try:
        return store.read_json("cache.json")
    except AisError as e:
        if e.code != EXIT_CONFIG:
            raise
        try:
            (store.dir / "cache.json").unlink()
        except OSError:
            pass
        return {}


def credential_state(store: Store, provider: Any, account: Account, cache_only: bool,
                     base_env: Mapping[str, str],
                     now: Callable[[], float] = time.time,
                     warnings: Optional[List[str]] = None) -> Tuple[str, str, str]:
    """(state, source, error); `auth status` results are cached 10 minutes, Keychain ones are not.

    With `warnings`, a failed cache write is appended there instead of raised.
    """
    try:
        cached = _read_cache(store)
    except AisError as e:
        if warnings is None:
            raise
        warnings.append(e.message)
        cached = {}
    entries = cached.get("credentials", {})
    e = entries.get(account.name) if isinstance(entries, dict) else None
    if isinstance(e, dict) and e.get("cred_dir") == account.cred_dir \
            and isinstance(e.get("at"), (int, float)) and 0 <= now() - e["at"] < CREDENTIAL_TTL \
            and all(isinstance(e.get(k), str) for k in ("state", "source", "error")):
        return e["state"], e["source"], e["error"]
    if cache_only:
        return provider.keychain_credential(account)
    result = provider.has_credential(account, base_env)
    if result[1] == "auth status":
        def fn(d: dict) -> dict:
            creds = d.get("credentials")
            d["credentials"] = creds = creds if isinstance(creds, dict) else {}
            creds[account.name] = {"cred_dir": account.cred_dir, "state": result[0],
                                   "source": result[1], "error": result[2], "at": now()}
            return d
        try:
            store.update_json("cache.json", fn)
        except (AisError, OSError) as e:
            if warnings is None:
                raise
            warnings.append("cannot write cache.json: %s" % getattr(e, "message", e))
    return result


class Cache:
    """Per-file (folder, title) cache in cache.json, keyed by path and valid for the same mtime and size."""

    def __init__(self, store: Store, on_error: Optional[Callable[[str], None]] = None, read_only: bool = False):
        """With on_error, a failed read or save is reported there and the cache starts empty."""
        self.store = store
        self._read_only = read_only  # FR-5.4: a dry run never writes cache.json
        self._on_error = on_error
        try:
            old = _read_cache(store).get("transcripts", {})
        except AisError as e:
            if on_error is None:
                raise
            on_error(e.message)
            old = {}
        self._old = old if isinstance(old, dict) else {}
        self._seen = {}  # type: Dict[str, dict]
        self._dirty = False

    def lookup(self, path: str, mtime: float, size: int) -> Optional[Tuple[str, str]]:
        e = self._seen.get(path) or self._old.get(path)
        if isinstance(e, dict) and e.get("mtime") == mtime and e.get("size") == size \
                and isinstance(e.get("folder"), str) and isinstance(e.get("title"), str):
            self._seen[path] = e
            return e["folder"], e["title"]
        return None

    def put(self, path: str, mtime: float, size: int, folder: str, title: str) -> None:
        self._dirty = True
        self._seen[path] = {"mtime": mtime, "size": size, "folder": folder, "title": title}

    def save(self) -> None:
        if self._read_only or (not self._dirty and self._seen.keys() == self._old.keys()):
            return  # warm scan: skip the lock, rewrite and fsync
        def fn(d: dict) -> dict:
            d["transcripts"] = self._seen  # paths not seen in this scan are dropped
            return d
        try:
            self.store.update_json("cache.json", fn)
        except (AisError, OSError) as e:
            if self._on_error is None:
                raise
            self._on_error("cannot write cache.json: %s" % getattr(e, "message", e))


@dataclass
class Context:
    store: Store
    config: Config
    provider_for: Callable[[Account], Provider]
    env: Dict[str, str]
    cwd: Path
    settings_roots: Optional[Mapping[str, Path]] = None  # None = the provider's default
    started: float = field(default_factory=time.monotonic)  # ais start, for the FR-3.14 tool time
    app_roots: Optional[List[Path]] = None  # None = /Applications and ~/Applications


def cmd_login(ctx: Context, account: str, dry_run: bool, allow_api_key: bool = False) -> int:
    acc = ctx.config.get(account)
    provider = ctx.provider_for(acc)
    env, warnings = provider.env_for(acc, ctx.env)
    guards.print_warnings(warnings)
    risks = provider.billing_risks(env, ctx.cwd, [], ctx.settings_roots or provider.default_settings_roots())
    guards.refuse_on_risks(risks, allow_api_key)
    cmd = provider.login_command()
    if dry_run:
        print(provider.describe_env(env) + " ".join(shlex.quote(a) for a in cmd))
        return 0
    rc = _spawn(ctx, provider, cmd, env, acc.label)
    try:
        ctx.store.log("login", acc.name, "", "exit %d" % rc)
    except AisError as e:  # claude already ran: its exit code wins over a failed log write
        guards.print_warnings([e.message])
    return rc


EXIT_DESKTOP = 69
OPEN_TIMEOUT = 10


def cmd_desktop(ctx: Context, account: str, dry_run: bool) -> int:
    """FR-6.1 to FR-6.4: open a new Desktop instance for the account. Writes no ais state and no log line."""
    acc = ctx.config.get(account)
    provider = ctx.provider_for(acc)
    home = ctx.store.home
    data_dir = provider.desktop_data_dir(acc, home)
    pid = provider.desktop_running_pid(data_dir)  # read-only, so --dry-run runs it too
    if pid is not None:
        print("%s Desktop is already open (PID %d)" % (acc.label, pid))
        return 0
    roots = ctx.app_roots if ctx.app_roots is not None else [Path("/Applications"), home / "Applications"]
    cmd = provider.desktop_launch_command(data_dir, roots)
    if dry_run:
        print("Would run: " + " ".join(shlex.quote(a) for a in cmd))
        return 0
    rc, _, warn, err = procs.run(cmd, OPEN_TIMEOUT, stderr=True)
    if rc != 0:
        raise AisError(EXIT_DESKTOP, warn or err.strip() or "%s exited %s" % (cmd[0], rc))
    return 0


def _record_last_used(store: Store, session: Session, account: Optional[str], restore: Any = None) -> Any:
    """Set the session's last-used entry (or, with account None, put `restore` back; None removes it).

    Returns the entry that was there before, or None.
    """
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    previous = []  # type: List[Any]

    def fn(d: dict) -> dict:
        sessions = d.setdefault("sessions", {})
        if not isinstance(sessions, dict):
            raise AisError(EXIT_CONFIG, "%s: sessions is not an object" % (store.dir / "state.json"))
        key = str(session.transcript)
        for stale in [k for k in sessions if k != key and not os.path.exists(k)]:  # FR-5.6
            del sessions[stale]
        previous.append(sessions.get(key))
        if account is not None:
            sessions[key] = {"account": account, "at": at}
        elif restore is not None:
            sessions[key] = restore
        else:
            sessions.pop(key, None)
        return d
    store.update_json("state.json", fn)
    return previous[0]


_SWITCH_HINT = "use `ais switch` to resume a session"


def _check_run_args(provider: Provider, args: List[str], allow_api_key: bool) -> None:
    # a short flag may carry its value attached (-r5, -r=abc) or sit in a cluster (-pr5)
    short = re.compile(r"^-[A-Za-z]*[%s]" % re.escape(provider.short_resume_letters))
    for a in args:
        flag = a.split("=", 1)[0]
        if flag in provider.resume_flags or (not a.startswith("--") and short.match(a)):
            raise AisError(EXIT_USAGE, "ais run does not take %s; %s" % (a, _SWITCH_HINT))
        if flag == "--settings" and not allow_api_key:
            raise AisError(EXIT_USAGE, "ais run does not take --settings (it can set an API key); %s" % _SWITCH_HINT)


def _spawn(ctx: Context, provider: Provider, cmd: List[str], env: Dict[str, str], label: str,
           cwd: Optional[Path] = None, on_started: Callable[[], None] = lambda: None) -> int:
    try:
        return runner.run_claude(cmd, env, cwd or ctx.cwd, label, on_started=on_started)
    except AisError as e:
        if e.code == 69:
            raise AisError(69, "%s; %s" % (e.message, provider.install_hint))
        raise


def cmd_run(ctx: Context, account: Optional[str], args: List[str], allow_api_key: bool, dry_run: bool) -> int:
    acc = ctx.config.get(account or ctx.config.default)
    provider = ctx.provider_for(acc)
    _check_run_args(provider, args, allow_api_key)
    env, warnings = provider.env_for(acc, ctx.env)
    guards.print_warnings(warnings)
    risks = provider.billing_risks(env, ctx.cwd, args, ctx.settings_roots or provider.default_settings_roots())
    guards.refuse_on_risks(risks, allow_api_key)
    cmd = provider.start_command(args)
    if dry_run:
        print(provider.describe_env(env) + " ".join(shlex.quote(a) for a in cmd))
        return 0
    launched = time.time()
    rc = _spawn(ctx, provider, cmd, env, acc.label)
    session_id = ""
    try:  # claude already ran: its exit code wins over a failed record or log write
        s = provider.newest_session(ctx.cwd, Cache(ctx.store))
        # accepted residual risk: a concurrent new session in this folder could be attributed to this run
        if s is not None:
            st = os.stat(str(s.transcript))
            if getattr(st, "st_birthtime", st.st_mtime) >= launched - 2:
                _record_last_used(ctx.store, s, acc.name)
                session_id = s.id
    except (AisError, OSError) as e:
        guards.print_warnings([getattr(e, "message", str(e))])
    try:  # NFR-OPS: the log line is written even when recording failed
        ctx.store.log("run", acc.name, session_id, "exit %d" % rc)
    except (AisError, OSError) as e:
        guards.print_warnings([getattr(e, "message", str(e))])
    return rc


def _clean(text: str) -> str:
    """Transcript text is untrusted: drop control and format characters before it reaches the terminal."""
    return "".join(c for c in text if not unicodedata.category(c).startswith("C"))


def _ask(prompt: str) -> str:
    sys.stdout.flush()  # a piped listing must come out before the prompt
    print(prompt, end="", file=sys.stderr, flush=True)
    return sys.stdin.readline().strip()


def _open_pids(provider: Provider, sink: Optional[List[str]] = None) -> Mapping[int, Tuple[str, Path]]:
    found, warnings = procs.process_cwds(provider.process_name, PROCESS_TIMEOUT)
    if sink is None:
        guards.print_warnings(warnings)  # FR-3.11 check failed: warn and go on
    else:
        sink.extend(warnings)
    return found


def _last_used(ctx: Context, session: Session, sessions: Any = None) -> Optional[str]:
    """`sessions` is state.json's "sessions" value when the caller already read it."""
    if sessions is None:
        sessions = ctx.store.read_json("state.json").get("sessions")
    rec = sessions.get(str(session.transcript)) if isinstance(sessions, dict) else None
    name = rec.get("account") if isinstance(rec, dict) else None
    return name if isinstance(name, str) and name in ctx.config.accounts else None


def _resolve_session(ctx: Context, provider: Provider, pick: bool,
                     session_id: Optional[str], dry_run: bool = False) -> Tuple[Session, Path]:
    """(session, folder to resume in)."""
    cache = Cache(ctx.store, read_only=dry_run)
    if session_id is not None:
        try:
            valid = str(uuid.UUID(session_id)) == session_id
        except ValueError:
            valid = False
        if not valid:
            raise AisError(EXIT_USAGE, "--session needs a session ID (a lowercase UUID), not %r" % session_id)
        s = provider.find_session(session_id, cache)
        if s is None:
            raise AisError(EXIT_NO_INPUT, "session %s not found" % session_id)
        real = Path(os.path.realpath(str(s.folder)))
        if not os.path.isabs(str(s.folder)) or not real.is_dir():  # relative: would resolve against our cwd
            raise AisError(EXIT_NO_INPUT, "the folder of session %s does not exist: %s"
                           % (s.id, _clean(str(s.folder))))
        try:
            return s, guards.safe_path(real, [ctx.store.home])
        except AisError as e:  # its message holds the raw transcript folder
            raise AisError(e.code, "%s is outside the allowed folders" % _clean(str(real)))
    if pick:
        found = provider.recent_sessions(PICK_COUNT, cache, ctx.cwd)
        if not found:
            raise AisError(EXIT_NO_INPUT, "nothing to resume in %s" % ctx.cwd)
        # all listed sessions share this folder, so one check answers "open" for each
        is_open = provider.open_session_pid(found[0], _open_pids(provider)) is not None
        for n, s in enumerate(found, 1):
            when = datetime.fromtimestamp(s.modified).strftime("%Y-%m-%d %H:%M")
            print("%d  %s  %s  %s  %s" % (n, when, _clean(s.title) or "(untitled)",
                                          _last_used(ctx, s) or "unknown", "open" if is_open else "-"),
                  file=sys.stderr)
        answer = _ask("Resume which session? [1-%d] " % len(found))
        if not (answer.isascii() and answer.isdigit() and 1 <= int(answer) <= len(found)):
            raise AisError(EXIT_USAGE, "not a listed number: %r" % answer)
        ctx.started = time.monotonic()  # FR-3.14 tool time excludes the human's answer
        return found[int(answer) - 1], ctx.cwd
    s = provider.newest_session(ctx.cwd, cache)
    if s is None:
        raise AisError(EXIT_NO_INPUT, "nothing to resume in %s" % ctx.cwd)
    return s, ctx.cwd


def _target(ctx: Context, account: Optional[str], last: str) -> Account:
    if account is not None:
        return ctx.config.get(account)
    names = ", ".join(sorted(ctx.config.accounts))
    if len(ctx.config.accounts) != 2:  # FR-3.9: "the other account" needs exactly two
        raise AisError(EXIT_USAGE, "%d accounts are configured; run `ais switch <account>` with one of: %s"
                       % (len(ctx.config.accounts), names))
    return next(a for n, a in ctx.config.accounts.items() if n != last)


def _acknowledge(ctx: Context, last: Optional[str], target: Account, session: Session) -> None:
    """FR-2.8, asked once per account pair with no lock held."""
    if last is None or last == target.name:
        return
    key = "%s->%s" % (last, target.name)
    if key in ctx.config.acks:
        return
    print("ais: the full transcript of session %s (used under %s) will be sent under %s.\n"
          "ais: this is asked once for %s." % (session.id, ctx.config.accounts[last].label, target.label, key),
          file=sys.stderr)
    if _ask("Continue? [y/N] ").lower() not in ("y", "yes"):
        raise AisError(EXIT_DECLINED, "not acknowledged; claude was not started")
    ctx.started = time.monotonic()  # FR-3.14 tool time excludes the human's answer

    def fn(d: dict) -> dict:
        acks = d.setdefault("cross_account_ack", {})
        if not isinstance(acks, dict):
            raise AisError(EXIT_CONFIG, "%s: cross_account_ack must be an object" % (ctx.store.dir / "config.json"))
        acks[key] = date.today().isoformat()
        return d
    ctx.store.update_json("config.json", fn)


def cmd_switch(ctx: Context, account: Optional[str], pick: bool, session: Optional[str],
               allow_api_key: bool, dry_run: bool) -> int:
    s, folder = _resolve_session(ctx, ctx.provider_for(ctx.config.accounts[ctx.config.default]), pick, session,
                            dry_run)
    last = _last_used(ctx, s)
    acc = _target(ctx, account, last or ctx.config.default)
    if last is None:  # FR-3.1: no record means a plain `claude`, on the default account
        last = ctx.config.default  # so FR-2.8 still asks before the transcript moves to the other account
        if acc.name != last:  # the FR-2.8 prompt below names this assumed account
            print("ais: no record of this session; assuming it last ran on %s"
                  % ctx.config.accounts[last].label, file=sys.stderr)
    provider = ctx.provider_for(acc)
    env, warnings = provider.env_for(acc, ctx.env)
    guards.print_warnings(warnings)
    cmd = provider.resume_command(s.id)
    risks = provider.billing_risks(env, folder, cmd[1:], ctx.settings_roots or provider.default_settings_roots())
    guards.refuse_on_risks(risks, allow_api_key)
    if dry_run:  # before the FR-2.8 prompt: a dry run never prompts, locks or writes
        print("session %s\nfolder %s\naccount %s\n%s%s" % (
            s.id, _clean(str(folder)), acc.name, provider.describe_env(env), " ".join(shlex.quote(a) for a in cmd)))
        return 0
    _acknowledge(ctx, last, acc, s)
    spawned = []  # type: List[float]
    with contextlib.ExitStack() as held:
        held.enter_context(ctx.store.switch_mutex())
        pid = provider.open_session_pid(s, _open_pids(provider))
        if pid is not None:
            raise AisError(EXIT_OPEN, "Claude is still running in %s (PID %d). Type /exit there, then run "
                           "`ais switch` again." % (_clean(str(folder)), pid))
        ctx.store.snapshot(provider.snapshot_paths(s), s.id)  # warns and returns None when impossible
        previous = _record_last_used(ctx.store, s, acc.name)
        try:  # FR-3.14: lines past this offset are the ones the resumed claude appends
            offset = os.path.getsize(str(s.transcript))
        except OSError:
            offset = 0

        def on_started() -> None:
            spawned.append(time.monotonic())
            held.close()  # FR-3.6: mutex held from the open check until claude has started

        try:
            rc = _spawn(ctx, provider, cmd, env, acc.label, folder, on_started)
        except AisError as e:  # claude never ran: undo the record, log, keep the spawn error primary
            for undo in (lambda: _record_last_used(ctx.store, s, None, previous),
                         lambda: ctx.store.log("switch", acc.name, s.id, "error %d" % e.code)):
                try:
                    undo()
                except (AisError, OSError) as u:
                    guards.print_warnings([getattr(u, "message", str(u))])
            raise
    try:  # claude already ran: its exit code wins over a failed measurement or log write
        ctx.store.log("switch", acc.name, s.id, "exit %d" % rc, round(spawned[0] - ctx.started, 3),
                      provider.limit_time(s, offset))
    except (AisError, OSError) as e:
        guards.print_warnings([getattr(e, "message", str(e))])
    return rc


RECENT_COUNT = 5
MENU_RECENT = 30  # FR-4.15: the menu groups more sessions than `ais status` lists


def _iso_utc(ts: float) -> Optional[str]:
    try:
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def gather_status(ctx: Context, cache_only: bool, open_warnings: Optional[List[str]] = None,
                  recent_count: int = RECENT_COUNT, desktop: bool = False) -> dict:
    """FR-4.6 dict (plus credential source and error); unreadable or unwritable state becomes a self-check message.

    Process-check warnings go to `open_warnings` when given (the menu treats them as a failure), else to stderr.
    """
    provider = ctx.provider_for(ctx.config.accounts[ctx.config.default])
    extra = []  # type: List[str]
    accounts = []
    for acc in ctx.config.accounts.values():
        state, source, error = credential_state(ctx.store, ctx.provider_for(acc), acc, cache_only, ctx.env,
                                                warnings=extra)
        accounts.append({"name": acc.name, "label": acc.label, "credential_present": state,
                         "credential_source": source, "credential_error": error})

    cache = Cache(ctx.store, extra.append)
    everything = provider.recent_sessions(sys.maxsize, cache)  # one scan serves both lists
    newest = next((s for s in everything if provider.in_folder(s, ctx.cwd)), None)
    recent = everything[:recent_count]
    found = _open_pids(provider, open_warnings)  # one process scan serves every open check
    try:  # read once; a corrupt state.json leaves every last-used unknown
        sessions = ctx.store.read_json("state.json").get("sessions") or {}
    except AisError as e:
        sessions = {}
        extra.append(e.message)

    def is_open(s: Session) -> bool:
        return provider.open_session_pid(s, found) is not None

    # FR-4.19: session ID -> (account, title, lastActivityAt) of the newest Desktop record across accounts
    desk = {}  # type: Dict[str, Tuple[str, str, int]]
    if desktop:
        for acc, a in zip(ctx.config.accounts.values(), accounts):
            p = ctx.provider_for(acc)
            data_dir = p.desktop_data_dir(acc, ctx.store.home)
            a["usage"] = p.desktop_usage(data_dir, ctx.store.home)  # FR-4.20
            for sid, (title, at) in p.desktop_records(data_dir, ctx.store.home).items():
                if sid not in desk or at > desk[sid][2]:
                    desk[sid] = (acc.name, title, at)

    def owner(s: Session) -> Optional[str]:
        return _last_used(ctx, s, sessions) or (desk[s.id][0] if s.id in desk else None)

    def title_of(s: Session) -> str:
        t = desk[s.id][1] if s.id in desk else ""
        return t if t.strip() else s.title

    messages = list(dict.fromkeys(provider.self_check() + extra))  # unique, first-seen order
    return {
        "accounts": accounts,
        "session": None if newest is None else {"id": newest.id, "last_used": _last_used(ctx, newest, sessions),
                                                "open": is_open(newest)},
        "recent": [{"id": s.id, "folder": str(s.folder), "title": title_of(s),
                    "last_used": owner(s), "open": is_open(s),
                    "modified": _iso_utc(s.modified)} for s in recent],
        "self_check": {"ok": not messages, "messages": messages},
    }


def cmd_status(ctx: Context, as_json: bool) -> int:
    d = gather_status(ctx, False)
    if as_json:
        print(json.dumps(d, indent=2))
        return 0
    for a in d["accounts"]:
        line = "  %s (%s): credential present: %s" % (a["name"], _clean(a["label"]), a["credential_present"])
        if a["credential_source"] == "keychain" and a["credential_present"] == "yes":
            line += " (Keychain item exists; not a validity check)"
        if a["credential_present"] == "unknown" and a["credential_error"]:
            line += " — " + _clean(a["credential_error"])
        print(line)
    s = d["session"]
    print("no session in this folder" if s is None else "session %s: last used %s, %s" % (
        s["id"], s["last_used"] or "unknown", "open" if s["open"] else "not open"))
    for m in d["self_check"]["messages"]:
        print("warning: " + _clean(m))
    if d["self_check"]["ok"]:
        print("self-check: ok")
    print("ais cannot see which account each slot is signed in to; sign in to the matching account in each")
    return 0


SETUP_FILES = ("config.json", ".lock", "cache.json", "ais.log")


def _missing_dirs(path: Path) -> List[Path]:
    """The folders mkdir -p would create for path, outermost first."""
    out = []  # type: List[Path]
    while not path.exists():
        out.append(path)
        path = path.parent
    return out[::-1]


def cmd_setup(ctx: Context, dry_run: bool, answers: Optional[Iterable[str]] = None) -> int:
    """FR-2.3 to FR-2.7: ask, list what will be created, ask for a yes, then write and sign in."""
    it = iter(answers) if answers is not None else None

    def ask(prompt: str, default: str = "") -> str:
        a = (next(it, "") if it is not None else _ask(prompt + (" [%s]" % default if default else "") + ": ")).strip()
        return a or default

    home = ctx.store.home
    existing = ctx.store.read_json("config.json")  # 78 when it is not valid JSON: never drop acks
    acks, privacy = existing.get("cross_account_ack", {}), existing.get("menu_privacy", False)
    for key, ok in (("cross_account_ack", isinstance(acks, dict) and all(isinstance(v, str) for v in acks.values())),
                    ("menu_privacy", isinstance(privacy, bool))):
        if not ok:  # load_config would reject it after the write
            raise AisError(EXIT_CONFIG, "%s: %s is malformed; fix or remove it first"
                           % (ctx.store.dir / "config.json", key))
    provider = ctx.provider_for(Account("", "", DEFAULT_PROVIDER, None))
    names = []  # type: List[str]
    picked = []  # type: List[Account]
    for extra in (False, True):
        name = ask("%s account name" % ("Extra" if extra else "Default"), "work" if extra else "personal")
        if not NAME_RE.fullmatch(name):
            raise AisError(EXIT_USAGE, "account name %r must match ^[a-z][a-z0-9-]{0,31}$" % name)
        if name in names:
            raise AisError(EXIT_USAGE, "account name %r is used twice" % name)
        names.append(name)
        label = ask("Label for %s" % name, name[0].upper() + name[1:])
        cred = None  # type: Optional[str]
        if extra:
            root = home / provider.cred_dir_root
            found = []  # type: List[Path]
            for p in sorted(root.glob("*")) if root.is_dir() else []:
                if p.name.startswith(".") or not p.is_dir():
                    continue
                if unicodedata.normalize("NFC", str(p)) != str(p):  # a different spelling is another Keychain slot
                    print("skipping %s: its name is not NFC-normalized" % p, file=sys.stderr)
                    continue
                found.append(p)
            for n, p in enumerate(found, 1):
                print("  %d) %s" % (n, p), file=sys.stderr)
            a = ask("Folder for %s (number or path)" % name, str(root / name))
            if a.isascii() and a.isdigit() and 1 <= int(a) <= len(found):
                cred = str(found[int(a) - 1])
            else:
                cred = unicodedata.normalize("NFC", str(home / a[2:]) if a.startswith("~/") else a)
                cred = cred.rstrip("/") or cred
            try:
                _check_cred_dir(ctx.store.dir / "config.json", name, cred, os.path.realpath(str(home)))
            except AisError as e:
                # drop _check_cred_dir's config.json prefix: no config exists yet
                raise AisError(EXIT_USAGE, "account %s: %s" % (name, e.message.partition(": account %s: " % name)[2]))
        old = existing.get("accounts")
        old = old.get(name) if isinstance(old, dict) else None
        desk = old.get("desktop_data_dir") if extra and isinstance(old, dict) else None  # kept for the same extra
        picked.append(Account(name, label, DEFAULT_PROVIDER, cred, desk if isinstance(desk, str) else None))

    new_dirs = [] if ctx.store.dir.exists() else _missing_dirs(ctx.store.dir)
    creates = ["%s/" % d for d in new_dirs]
    cfg = ctx.store.dir / "config.json"
    creates += [str(ctx.store.dir / f) + (" (replace)" if f == "config.json" and cfg.exists() else "")
                for f in SETUP_FILES if f == "config.json" or not (ctx.store.dir / f).exists()]
    cred_dirs = [d for a in picked if a.cred_dir for d in _missing_dirs(Path(a.cred_dir))]
    creates += ["%s/ (empty, mode 0700)" % d for d in cred_dirs]
    print("Setup would create:" if dry_run else "Setup will create:")
    for c in creates:
        print("  " + c)
    config = {"version": 1, "default": picked[0].name,
              "accounts": {a.name: dict({"label": a.label, "provider": a.provider, "credDir": a.cred_dir},
                                        **({"desktop_data_dir": a.desktop_data_dir} if a.desktop_data_dir else {}))
                           for a in picked},
              "cross_account_ack": existing.get("cross_account_ack", {}),
              "menu_privacy": existing.get("menu_privacy", False)}
    if dry_run:
        print("config.json would contain:\n" + json.dumps(config, indent=2))
        seen = set()  # type: set
        for a in picked:
            env, warnings = provider.env_for(a, ctx.env)
            guards.print_warnings([w for w in warnings if w not in seen])
            seen.update(warnings)
            prefix = provider.describe_env(env)
            print("%s: check with: %s%s" % (a.name, prefix, shlex.join(provider.auth_status_command())))
            print("%s: sign in only if logged out: %s%s" % (a.name, prefix, shlex.join(provider.login_command())))
    elif ask("Create these? [y/N]").lower() not in ("y", "yes"):
        print("Nothing written.", file=sys.stderr)
        return EXIT_DECLINED
    else:
        made = []  # type: List[Path]
        try:
            try:
                for d in cred_dirs:
                    try:
                        d.mkdir(mode=0o700)
                    except FileExistsError:  # it appeared since the listing: leave it as it is
                        if d.is_dir():
                            continue
                        raise
                    made.append(d)
                    d.chmod(0o700)  # the umask must not decide the mode
            except OSError as e:
                raise AisError(EXIT_CANNOT_WRITE, "%s: %s" % (d, e))
            keep = {k: config[k] for k in ("cross_account_ack", "menu_privacy")}

            def fn(cur: dict) -> dict:
                out = dict(config)
                out.update({k: cur.get(k, v) for k, v in keep.items()})
                return out
            ctx.store.update_json("config.json", fn)
        except (AisError, OSError):
            for d in reversed(made):  # undo only what this run created, never recursively
                with contextlib.suppress(OSError):
                    d.rmdir()
            raise
        ctx2 = Context(ctx.store, load_config(ctx.store, REGISTRY), ctx.provider_for, ctx.env, ctx.cwd,
                       ctx.settings_roots, ctx.started)
        for a in picked:
            state, _, err = credential_state(ctx2.store, provider, a, False, ctx.env)
            if state == "unknown":
                print("%s: could not tell whether it is signed in (%s); run `ais login %s`"
                      % (a.name, err, a.name))
            elif state == "no":
                try:
                    rc = cmd_login(ctx2, a.name, False)
                except AisError:
                    print("sign-in of %s failed; run `ais login %s` to retry" % (a.name, a.name), file=sys.stderr)
                    raise
                if rc != 0:
                    print("sign-in of %s exited %d; run `ais login %s` to retry" % (a.name, rc, a.name),
                          file=sys.stderr)
                    return rc
    bin_dir = str(home / ".local" / "bin")
    on_path = any((str(home / e[2:]) if e.startswith("~/") else e).rstrip("/") == bin_dir
                  for e in ctx.env.get("PATH", "").split(":"))
    if not on_path:
        print("\nAdd this line to ~/.zshrc so your shell finds ais:\n  " + 'export PATH="$HOME/.local/bin:$PATH"'
              + "\nIt puts ~/.local/bin, where ais is installed, on your PATH.")
    print("\n" + provider.shared_data_note)
    return 0


def _unlink(path: Path) -> None:
    """Unlink a file or symlink, never a folder; a missing path is skipped."""
    try:
        os.unlink(str(path))
    except FileNotFoundError:
        pass
    except OSError as e:
        raise AisError(EXIT_CANNOT_WRITE, "%s: %s" % (path, e))


def _remove(path: Path) -> None:
    """Remove a file, symlink or folder tree without following symlinks; a missing path is skipped."""
    try:
        if path.is_symlink() or not path.is_dir():  # inside try: 3.9 raises PermissionError here
            _unlink(path)
            return
        for child in sorted(path.iterdir()):
            _remove(child)
        os.rmdir(str(path))
    except FileNotFoundError:
        pass
    except OSError as e:
        raise AisError(EXIT_CANNOT_WRITE, "%s: %s" % (path, e))


def _yes(answers: Optional[Iterable[str]]) -> Callable[[str], bool]:
    """A yes/no asker: the scripted answers when given (tests), else stdin."""
    it = iter(answers) if answers is not None else None

    def yes(prompt: str) -> bool:
        a = next(it, "") if it is not None else _ask(prompt)
        return a.strip().lower() in ("y", "yes")
    return yes


def _plugin_record(store: Store) -> Tuple[Optional[Path], Optional[str], bool]:
    """(plugin, gone, warned): the recorded plugin if it is an absolute existing file or symlink; `gone` is a
    recorded absolute path that no longer exists; `warned` says a bad record already printed a warning."""
    plugin, gone, warned = None, None, False  # type: Optional[Path], Optional[str], bool
    try:
        recorded = store.read_json("state.json").get("menu_plugin")
        if recorded is not None and not isinstance(recorded, str):
            raise AisError(EXIT_CONFIG, "menu_plugin is not a path")
        if recorded and os.path.lexists(recorded):
            rp = Path(recorded)
            if rp.is_absolute() and (rp.is_symlink() or rp.is_file()):
                plugin = rp
            else:  # untrusted data: never delete a folder or a relative path
                warned = True
                print("ais: warning: state.json menu_plugin %r is not an absolute file path; "
                      "remove the plugin by hand" % recorded, file=sys.stderr)
        elif recorded and os.path.isabs(recorded):
            gone = recorded
    except AisError:
        warned = True
        print("ais: warning: state.json is unreadable; a SwiftBar plugin, if you installed one, "
              "must be removed by hand", file=sys.stderr)
    return plugin, gone, warned


def _recorded_plugin(store: Store) -> Optional[Path]:
    return _plugin_record(store)[0]


def cmd_uninstall(ctx: Context, dry_run: bool, answers: Optional[Iterable[str]] = None) -> int:
    """FR-5.3, FR-5.5: list, ask, remove ~/.config/ais and the recorded plugin, print the manual steps. No lock."""
    yes = _yes(answers)
    store, home = ctx.store, ctx.store.home
    provider = ctx.provider_for(Account("", "", DEFAULT_PROVIDER, None))
    plugin = _recorded_plugin(store)
    entries = []  # type: List[Path]
    here = True
    try:  # os.lstat, not pathlib: 3.14 pathlib reports EACCES as "missing", 3.9 raises
        mode = os.lstat(str(store.dir)).st_mode
        if not stat.S_ISDIR(mode):
            entries = [store.dir]  # a symlink or plain file: unlinked, never followed
        else:
            entries = sorted(store.dir.iterdir())
    except FileNotFoundError:
        here = False
    except OSError as e:
        raise AisError(EXIT_CANNOT_WRITE, "%s: %s" % (store.dir, e))
    snaps = store.dir / "snapshots"
    snaps_here = snaps in entries
    steps = ["~/.local/bin/ais and ~/.local/bin/ais.prev: delete both files"]
    extras = [a for a in ctx.config.accounts.values() if not a.is_default]
    for a in extras:
        steps.append("%s: your %s sign-in folder (kept; delete it if you no longer need it)" % (a.cred_dir, a.label))
        hint = ctx.provider_for(a).credential_removal_hint(a)
        if hint:
            steps.append("Keychain item of %s: %s" % (a.label, hint))
        steps.append("%s: your %s Desktop data folder (kept; it holds the Desktop sign-in)"
                     % (a.desktop_data_dir or ctx.provider_for(a).desktop_data_dir(a, home), a.label))
    if not ctx.config.accounts:  # the no-config placeholder: generic wording
        steps.append(str(home / provider.cred_dir_root / "<account>") + ": each extra account's folder (kept)")
        hint = provider.credential_removal_hint(None)
        if hint:
            steps.append("Keychain: " + hint)
        placeholder = Account("<account>", "<account>", DEFAULT_PROVIDER, "<credDir>")  # non-default
        steps.append("%s: each extra account's Desktop data folder (kept; it holds the Desktop sign-in)"
                     % provider.desktop_data_dir(placeholder, home))
    steps.append('~/.zshrc: remove the line  export PATH="$HOME/.local/bin:$PATH"  only if you added it for ais '
                 "and nothing else in ~/.local/bin needs it (claude itself lives there)")

    def manual() -> None:
        print("\nManual steps (ais never touches these):")
        for s in steps:
            print("  " + s)

    if not here and plugin is None:
        print("Nothing to remove.")
        manual()
        return 0
    print("Uninstall would remove:" if dry_run else "Uninstall will remove:")
    if plugin is not None:
        print("  %s (SwiftBar plugin recorded in state.json)" % plugin)
    for e in entries:
        print("  %s%s" % (e, "/ (asks first)" if e == snaps else ""))
    if not entries:
        print("  %s/ (empty)" % store.dir)
    if dry_run:
        manual()
        return 0
    if not yes("Remove these? [y/N] "):
        print("Nothing removed.", file=sys.stderr)
        return EXIT_DECLINED
    keep = snaps_here and not yes("Also delete the saved snapshots in %s? [y/N] " % snaps)
    if plugin is not None:
        _unlink(plugin)  # untrusted path: never a folder, even if swapped in after the check
    if keep:
        for e in entries:
            if e != snaps:
                _remove(e)
        if snaps.is_symlink():
            print("Kept %s (a symlink to %s)" % (snaps, os.readlink(str(snaps))))
        else:
            print("Kept %s (%d bytes)" % (snaps, _size(snaps)))
    else:
        _remove(store.dir)
    manual()
    return 0


EXIT_SWIFTBAR = 71
EXIT_MISSING_TOOL = 69
PLUGIN_NAME = "ais.1m.sh"
SWIFTBAR_DOMAIN = "com.ameba.SwiftBar"
_PATH_UNSAFE = re.compile(r'["$`\\:\x00-\x1f\x7f]')  # would break the quoting or the PATH list in the plugin


def _swiftbar_folder(ctx: Context) -> str:
    """FR-4.10: SwiftBar's configured plugin folder, or exit 71."""
    home = ctx.store.home
    roots = ctx.app_roots if ctx.app_roots is not None else [Path("/Applications"), home / "Applications"]
    folder = ""
    if any((r / "SwiftBar.app").is_dir() for r in roots):
        rc, out, _, _ = procs.run(["defaults", "read", SWIFTBAR_DOMAIN, "PluginDirectory"], PROCESS_TIMEOUT)
        folder = out.strip() if rc == 0 else ""
        if folder.startswith("~/"):
            folder = str(home / folder[2:])
    if not folder or not os.path.isabs(folder) or not os.path.isdir(folder):
        raise AisError(EXIT_SWIFTBAR, "SwiftBar is not installed or has no plugin folder; ais never installs it.\n"
                       "Install it with: brew install --cask swiftbar\n"
                       "then open SwiftBar and choose a plugin folder, and run this again.")
    return folder


def cmd_menu_install(ctx: Context, dry_run: bool, answers: Optional[Iterable[str]] = None) -> int:
    """FR-4.7, FR-4.10: show the plugin, ask, write it atomically into SwiftBar's plugin folder, record it."""
    store, home = ctx.store, ctx.store.home
    folder = os.path.realpath(_swiftbar_folder(ctx))
    provider = ctx.provider_for(Account("", "", DEFAULT_PROVIDER, None))
    found = shutil.which(provider.start_command([])[0], path=ctx.env.get("PATH", ""))
    if not found:
        raise AisError(EXIT_MISSING_TOOL, provider.install_hint)
    claude_dir = os.path.dirname(os.path.abspath(found))  # which() keeps a relative PATH entry relative
    for part in (str(home), claude_dir):
        if _PATH_UNSAFE.search(part):
            raise AisError(EXIT_CONFIG, "cannot build the plugin PATH: %r has a quote, $, backtick, backslash, "
                           "colon or control character" % part)
    store.read_json("state.json")  # a corrupt state.json fails 78 now, not after the plugin is written
    target = os.path.join(folder, PLUGIN_NAME)
    exists = os.path.lexists(target)
    if exists and not stat.S_ISREG(os.lstat(target).st_mode):  # never follow a symlink or replace a folder
        raise AisError(EXIT_CANNOT_WRITE, "%s is not a regular file; remove it by hand" % target)
    local_bin = "%s/.local/bin" % home
    dirs = [local_bin] + ([claude_dir] if claude_dir != local_bin else [])
    # /usr/sbin: lsof lives there on macOS, and render needs it (#42)
    body = ('#!/bin/sh\nexport PATH="%s:/usr/bin:/bin:/usr/sbin:/sbin"\nexec ais menu render\n' % ":".join(dirs))
    print("%s %s%s:\n%s" % ("Would write" if dry_run else "Will write", target, " (replace)" if exists else "", body))
    if not (home / ".local" / "bin" / "ais").is_file():
        print("ais: warning: %s is missing; the menu finds no ais until `make install`"
              % (home / ".local" / "bin" / "ais"), file=sys.stderr)
    prev = _recorded_plugin(store)
    if prev is not None and str(prev) != target:
        print("ais: warning: state.json also records %s; remove it by hand" % prev, file=sys.stderr)
    if dry_run:
        return 0
    if not _yes(answers)("Write this file? [y/N] "):
        print("Nothing written.", file=sys.stderr)
        return EXIT_DECLINED
    # record first: a failing state.json write then leaves no unrecorded plugin (a stale record is cleared by uninstall)
    store.update_json("state.json", lambda d: dict(d, menu_plugin=target))
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + PLUGIN_NAME + ".")
        with os.fdopen(fd, "w") as f:
            f.write(body)
        os.chmod(tmp, 0o700)  # SwiftBar must execute it
        os.replace(tmp, target)
        tmp = None
    except OSError as e:
        raise AisError(EXIT_CANNOT_WRITE, "%s: %s" % (target, e))
    finally:
        if tmp is not None:
            _unlink(Path(tmp))
    print("Wrote " + target)
    return 0


def cmd_menu_uninstall(ctx: Context, dry_run: bool, answers: Optional[Iterable[str]] = None) -> int:
    """FR-4.7: remove only the recorded ais.1m.sh after a yes, and forget it in state.json."""
    plugin, gone, warned = _plugin_record(ctx.store)
    if plugin is None:
        if gone is not None:
            print("The recorded SwiftBar plugin %s is already gone." % gone)
            if not dry_run:
                ctx.store.update_json("state.json", lambda d: {k: v for k, v in d.items() if k != "menu_plugin"})
        elif not warned:
            print("No SwiftBar plugin recorded.")
        return 0
    if plugin.name != PLUGIN_NAME:  # untrusted state: never remove another file
        print("ais: warning: state.json records %s, which is not named %s; remove it by hand" % (plugin, PLUGIN_NAME),
              file=sys.stderr)
        return 0
    print("%s %s" % ("Would remove" if dry_run else "Will remove", plugin))
    if dry_run:
        return 0
    if not _yes(answers)("Remove it? [y/N] "):
        print("Nothing removed.", file=sys.stderr)
        return EXIT_DECLINED
    _unlink(plugin)
    ctx.store.update_json("state.json", lambda d: {k: v for k, v in d.items() if k != "menu_plugin"})
    print("Removed " + str(plugin))
    return 0
