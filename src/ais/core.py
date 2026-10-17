import contextlib
import os
import re
import shlex
import sys
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from ais import guards, procs, runner
from ais.accounts import EXIT_USAGE, Account, Config
from ais.errors import AisError
from ais.providers.base import Provider, Session
from ais.store import EXIT_CONFIG, Store

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
                     now: Callable[[], float] = time.time) -> Tuple[str, str, str]:
    """(state, source, error); `auth status` results are cached 10 minutes, Keychain ones are not."""
    entries = _read_cache(store).get("credentials", {})
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
        store.update_json("cache.json", fn)
    return result


class Cache:
    """Per-file (folder, title) cache in cache.json, keyed by path and valid for the same mtime and size."""

    def __init__(self, store: Store):
        self.store = store
        old = _read_cache(store).get("transcripts", {})
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
        if not self._dirty and self._seen.keys() == self._old.keys():
            return  # warm scan: skip the lock, rewrite and fsync
        def fn(d: dict) -> dict:
            d["transcripts"] = self._seen  # paths not seen in this scan are dropped
            return d
        self.store.update_json("cache.json", fn)


@dataclass
class Context:
    store: Store
    config: Config
    provider_for: Callable[[Account], Provider]
    env: Dict[str, str]
    cwd: Path
    settings_roots: Optional[Mapping[str, Path]] = None  # None = the provider's default
    started: float = field(default_factory=time.monotonic)  # ais start, for the FR-3.14 tool time


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
    print(prompt, end="", file=sys.stderr, flush=True)
    return sys.stdin.readline().strip()


def _open_pids(provider: Provider) -> Mapping[int, Tuple[str, Path]]:
    found, warnings = procs.process_cwds(provider.process_name, PROCESS_TIMEOUT)
    guards.print_warnings(warnings)  # FR-3.11 check failed: warn and go on
    return found


def _last_used(ctx: Context, session: Session) -> Optional[str]:
    sessions = ctx.store.read_json("state.json").get("sessions")
    rec = sessions.get(str(session.transcript)) if isinstance(sessions, dict) else None
    name = rec.get("account") if isinstance(rec, dict) else None
    return name if isinstance(name, str) and name in ctx.config.accounts else None


def _resolve_session(ctx: Context, provider: Provider, pick: bool,
                     session_id: Optional[str]) -> Tuple[Session, Path]:
    """(session, folder to resume in)."""
    cache = Cache(ctx.store)
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


def _target(ctx: Context, account: Optional[str], last: Optional[str]) -> Account:
    if account is not None:
        return ctx.config.get(account)
    names = ", ".join(sorted(ctx.config.accounts))
    if len(ctx.config.accounts) != 2:  # FR-3.9: "the other account" needs exactly two
        raise AisError(EXIT_USAGE, "%d accounts are configured; run `ais switch <account>` with one of: %s"
                       % (len(ctx.config.accounts), names))
    if last is None:
        raise AisError(EXIT_USAGE, "the last-used account of this session is unknown; "
                       "run `ais switch <account>` with one of: %s" % names)
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
    s, folder = _resolve_session(ctx, ctx.provider_for(ctx.config.accounts[ctx.config.default]), pick, session)
    last = _last_used(ctx, s)
    acc = _target(ctx, account, last)
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
