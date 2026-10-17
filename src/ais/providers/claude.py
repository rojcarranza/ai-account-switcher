"""Everything Claude Code specific (FR-5.1). Constants come from docs/spike-results.md."""
import getpass
import hashlib
import json
import os
import plistlib
import re
import shlex
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ais import procs
from ais.accounts import Account
from ais.providers.base import Session

PROCESS_NAME = "claude"  # what pgrep -x matches (spike (g))
SLOT_ENV = "CLAUDE_SECURESTORAGE_CONFIG_DIR"
CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
TESTED_VERSIONS = ("2.1.301", "2.1.301")  # min, max inclusive (spike (f))
VERSION_TIMEOUT = 10
AUTH_TIMEOUT = 10
KEYCHAIN_TIMEOUT = 5
KEYCHAIN_NOT_FOUND = 44  # errSecItemNotFound
MANAGED_PROFILE = "com.anthropic.claudecode"
LIMIT_MARKER = {"isApiErrorMessage": True, "error": "rate_limit"}  # spike (j); used by task 14

BILLING_ENV = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY", "CLAUDE_CODE_USE_MANTLE", "CLAUDE_CODE_USE_ANTHROPIC_AWS",
    "CLAUDE_CODE_USE_GATEWAY", "CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD",
    "CLAUDE_CODE_OAUTH_REFRESH_TOKEN", "CLAUDE_CODE_OAUTH_SCOPES", "ANTHROPIC_FOUNDRY_API_KEY",
    "ANTHROPIC_FOUNDRY_AUTH_TOKEN", "ANTHROPIC_AWS_API_KEY", "AWS_BEARER_TOKEN_BEDROCK",
    "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_PROFILE", "ANTHROPIC_FEDERATION_RULE_ID",
    "ANTHROPIC_ORGANIZATION_ID", "ANTHROPIC_WORKSPACE_ID",
    "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR", "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
    "ANTHROPIC_IDENTITY_TOKEN", "ANTHROPIC_IDENTITY_TOKEN_FILE", "CLAUDE_CODE_ACCOUNT_UUID",
    "CLAUDE_CODE_ORGANIZATION_UUID",
    "ANTHROPIC_BEDROCK_BASE_URL", "ANTHROPIC_VERTEX_BASE_URL", "ANTHROPIC_FOUNDRY_BASE_URL",
    "ANTHROPIC_FOUNDRY_RESOURCE", "ANTHROPIC_AWS_BASE_URL", "ANTHROPIC_BEDROCK_MANTLE_BASE_URL",
    "ANTHROPIC_CONFIG_DIR", "CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST",
)
SETTINGS_KEYS = ("apiKeyHelper", "forceLoginMethod", "forceLoginOrgUUID", "awsAuthRefresh",
                 "awsCredentialExport", "gcpAuthRefresh")
# (root, relative path); root "folder" is the session folder, the others come from settings_roots.
SETTINGS_FILES = (
    ("home", ".claude/settings.json"),
    ("home", ".claude/settings.local.json"),
    ("folder", ".claude/settings.json"),
    ("folder", ".claude/settings.local.json"),
    ("managed", "managed-settings.json"),
)
RISKY_FLAGS = ("--settings", "--bare")


def default_settings_roots() -> Dict[str, Path]:
    return {"home": Path.home(),
            "managed": Path("/Library/Application Support/ClaudeCode"),
            "managed_prefs": Path("/Library/Managed Preferences")}


def keychain_service(cred_dir: Optional[str]) -> str:
    # Callers pass None for the default slot; "" would hash, unlike claude (FR-1.7 rejects it).
    if cred_dir is None:
        return "Claude Code-credentials"
    digest = hashlib.sha256(unicodedata.normalize("NFC", cred_dir).encode("utf-8")).hexdigest()
    return "Claude Code-credentials-" + digest[:8]


def _set(env: Mapping[str, Any], name: str) -> bool:
    # A variable counts when present, even empty: set-and-empty can differ from unset (fail safe).
    return name in env


def _settings_risks(path: Path, data: Any) -> List[str]:
    if not isinstance(data, dict):
        return ["cannot read %s: top level is not an object" % path]
    risks = ["%s in %s" % (k, path) for k in SETTINGS_KEYS if k in data]
    block = data.get("env", {})
    if not isinstance(block, dict):
        risks.append("cannot read %s: env is not an object" % path)
    else:
        risks += ["%s in %s env" % (n, path) for n in BILLING_ENV if _set(block, n)]
    return risks


def _global_risks(path: Path, data: Any) -> List[str]:
    # ~/.claude.json is not a settings file: only its /login managed key matters; never print the value.
    if isinstance(data, dict) and data.get("primaryApiKey") is not None:
        return ["primaryApiKey in %s" % path]
    return []


def _read(path: Path, loader, check=_settings_risks) -> List[str]:
    try:
        with open(str(path), "rb") as f:
            data = loader(f)
    except FileNotFoundError:
        return []
    except Exception as e:  # unreadable or invalid: fail safe, report it
        return ["cannot read %s: %s" % (path, e)]
    return check(path, data)


def _main_checkout(dot_git: Path) -> Optional[Path]:
    """For a worktree's `.git` file ("gitdir: <X>/.git/worktrees/<name>"), return <X>."""
    try:
        line = dot_git.read_text(errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return None
    if not line.startswith("gitdir:"):
        return None
    gitdir = Path(os.path.normpath(str(dot_git.parent / line[len("gitdir:"):].strip())))
    if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
        return gitdir.parent.parent.parent
    return None


def _repo_roots(folder: Path) -> List[Path]:
    """Repo root and, for a worktree, the main checkout; claude reads their local settings too.

    Walks both the folder as given and its realpath (claude compares realpaths); roots are
    de-duplicated by realpath, keeping the first (lexical) spelling, and the folder itself is skipped.
    """
    real = os.path.realpath(str(folder))
    seen = {real}
    roots = []  # type: List[Path]
    for start in (folder, Path(real)):
        for d in [start] + list(start.parents):
            dot_git = d / ".git"
            if not os.path.lexists(str(dot_git)):
                continue
            found = [d]
            if dot_git.is_file():
                main = _main_checkout(dot_git)
                if main is not None:
                    found.append(main)
            for r in found:
                if os.path.realpath(str(r)) not in seen:
                    seen.add(os.path.realpath(str(r)))
                    roots.append(r)
            break
    return roots


_FRACTION = re.compile(r"\.(\d+)")


def _parse_time(stamp: str) -> datetime:
    # 3.9 fromisoformat takes no "Z" and only 3 or 6 fraction digits: pad or cut to 6
    stamp = _FRACTION.sub(lambda m: "." + (m.group(1) + "00000")[:6], stamp.replace("Z", "+00:00"), count=1)
    return datetime.fromisoformat(stamp)


TITLE_MAX = 60


def _prompt_title(d: Any) -> Optional[str]:
    """Title from a transcript line if it is a real user prompt, else None."""
    if not isinstance(d, dict) or d.get("type") != "user" or d.get("isMeta") is True:
        return None
    msg = d.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, list):
        content = next((b.get("text") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"), None)
    if not isinstance(content, str) or content.lstrip().startswith("<"):
        return None
    for line in content.splitlines():
        if line.strip():
            return line.strip()[:TITLE_MAX]
    return ""


def _read_transcript(path: Path) -> Tuple[Optional[str], str]:
    """(session folder, title); stops once both are known. Folder is None without any cwd line."""
    folder, title = None, None  # type: Optional[str], Optional[str]
    with open(str(path), encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if folder is None and isinstance(d, dict) and isinstance(d.get("cwd"), str) and d["cwd"]:
                folder = d["cwd"]
            if title is None:
                title = _prompt_title(d)
            if folder is not None and title is not None:
                break
    return folder, title or ""


def _nfc_real(p: str) -> str:
    # NFC on both sides: Finder hands out NFD names
    return unicodedata.normalize("NFC", os.path.realpath(p))


def _same_folder(cwd: str, target_real: str) -> bool:
    # target_real is already resolved, so an equal spelling needs no realpath of cwd
    return unicodedata.normalize("NFC", cwd) == target_real or _nfc_real(cwd) == target_real


class ClaudeProvider:
    install_hint = "install Claude Code: https://code.claude.com/docs/en/setup"
    resume_flags = ("--resume", "--continue", "--from-pr", "--fork-session")
    short_resume_letters = "rc"
    process_name = PROCESS_NAME

    def default_settings_roots(self) -> Dict[str, Path]:
        return default_settings_roots()

    def describe_env(self, env: Mapping[str, str]) -> str:
        return "%s=%s " % (SLOT_ENV, shlex.quote(env[SLOT_ENV])) if SLOT_ENV in env else ""

    def _scan(self, cache: Any) -> List[Session]:
        """Sessions from projects/*/*.jsonl (top level only: subagent transcripts live deeper), newest first."""
        found = []
        for path in (Path.home() / ".claude" / "projects").glob("*/*.jsonl"):
            try:
                if str(uuid.UUID(path.stem)) != path.stem:
                    continue
                st = path.stat()
                key = str(path)
                hit = cache.lookup(key, st.st_mtime, st.st_size)
                if hit is None:
                    folder, title = _read_transcript(path)
                    cache.put(key, st.st_mtime, st.st_size, folder or "", title)  # "" = no cwd line
                else:
                    folder, title = hit
                if not folder:
                    continue
            except (ValueError, OSError):  # not a UUID name, or the file vanished or is unreadable
                continue
            found.append(Session(path.stem, Path(folder), path, title, st.st_mtime))
        cache.save()
        return sorted(found, key=lambda s: s.modified, reverse=True)

    def newest_session(self, folder: Path, cache: Any) -> Optional[Session]:
        target = _nfc_real(str(folder))
        return next((s for s in self._scan(cache) if _same_folder(str(s.folder), target)), None)

    def recent_sessions(self, limit: int, cache: Any, folder: Optional[Path] = None) -> List[Session]:
        found = self._scan(cache)
        if folder is not None:
            target = _nfc_real(str(folder))
            found = [s for s in found if _same_folder(str(s.folder), target)]
        return found[:limit]

    def find_session(self, session_id: str, cache: Any) -> Optional[Session]:
        return next((s for s in self._scan(cache) if s.id == session_id), None)

    def limit_time(self, session: Session, launched_at: float) -> Optional[float]:
        """Seconds from a LIMIT_MARKER line that is the last timestamped line before launched_at
        to the first line at or after it; None when the session did not stop at the limit."""
        last = None  # type: Optional[float]
        try:
            with open(str(session.transcript), encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        t = _parse_time(d["timestamp"])
                        if t.tzinfo is None:  # a naive time has no defined zone: skip it
                            continue
                    except (ValueError, TypeError, KeyError, AttributeError):
                        continue
                    if t.timestamp() >= launched_at:
                        return None if last is None else t.timestamp() - last
                    # only a session that stopped at the limit counts: a later normal line resets it
                    last = t.timestamp() if all(d.get(k) == v for k, v in LIMIT_MARKER.items()) else None
        except OSError:
            pass
        return None

    def open_session_pid(self, session: Session, procs: Mapping[int, Tuple[str, Path]]) -> Optional[int]:
        """Lowest PID of a claude with cwd in the session folder; the daemon and bg-* helpers are not sessions."""
        target = _nfc_real(str(session.folder))
        for pid in sorted(procs):
            args, cwd = procs[pid]
            # the executable path may hold spaces (Application Support): find the token that ends it
            words = args.split()
            i = next((n for n, w in enumerate(words) if w == PROCESS_NAME or w.endswith("/" + PROCESS_NAME)), None)
            if i is not None and i + 1 < len(words) and (words[i + 1] == "daemon" or words[i + 1].startswith("bg-")):
                continue
            if _same_folder(str(cwd), target):
                return pid
        return None

    def env_for(self, account: Account, base_env: Mapping[str, str]) -> Tuple[Dict[str, str], List[str]]:
        env = dict(base_env)
        warnings = []
        if env.pop(CONFIG_DIR_ENV, None) is not None:
            warnings.append("removed inherited %s; ais never splits ~/.claude" % CONFIG_DIR_ENV)
        if account.cred_dir is None:
            if env.pop(SLOT_ENV, None) is not None:
                warnings.append("removed inherited %s for the default account %s"
                                % (SLOT_ENV, account.name))
        else:
            env[SLOT_ENV] = account.cred_dir  # exactly as stored: the string is the Keychain hash input
        return env, warnings

    def keychain_credential(self, account: Account) -> Tuple[str, str, str]:
        """Existence check by exit code only: no -w/-g, stdout discarded, so no secret is read."""
        argv = ["security", "find-generic-password", "-s", keychain_service(account.cred_dir)]
        rc, _, warn, err = procs.run(argv, KEYCHAIN_TIMEOUT, stderr=True)
        if warn:
            return "unknown", "keychain", warn.splitlines()[0]
        if rc == 0:
            return "yes", "keychain", ""
        if rc == KEYCHAIN_NOT_FOUND:
            return "no", "keychain", ""
        lines = err.splitlines()
        return "unknown", "keychain", "security exited %d%s" % (rc, ": " + lines[0] if lines else "")

    def has_credential(self, account: Account, base_env: Mapping[str, str]) -> Tuple[str, str, str]:
        env, _ = self.env_for(account, base_env)
        rc, out, warn, _ = procs.run(["claude", "auth", "status", "--json"], AUTH_TIMEOUT, env)
        if not warn and rc == 0:
            try:
                data = json.loads(out)
            except ValueError:
                data = None
            # only loggedIn: email/org are not per slot (spike (h))
            if isinstance(data, dict) and isinstance(data.get("loggedIn"), bool):
                return ("yes" if data["loggedIn"] else "no"), "auth status", ""
        return self.keychain_credential(account)

    def billing_risks(self, env: Mapping[str, str], folder: Path, args: Sequence[str],
                      settings_roots: Mapping[str, Path]) -> List[str]:
        risks = ["%s in the environment" % n for n in BILLING_ENV if _set(env, n)]
        for root, rel in SETTINGS_FILES:
            base = folder if root == "folder" else settings_roots[root]
            risks += _read(Path(base) / rel, json.load)
        for root in _repo_roots(Path(folder)):
            risks += _read(root / ".claude" / "settings.local.json", json.load)
        for drop_in in sorted((Path(settings_roots["managed"]) / "managed-settings.d").glob("*.json")):
            risks += _read(drop_in, json.load)
        risks += _read(Path(settings_roots["home"]) / ".claude.json", json.load, _global_risks)
        prefs = Path(settings_roots["managed_prefs"])
        for plist in (prefs / (MANAGED_PROFILE + ".plist"),
                      prefs / getpass.getuser() / (MANAGED_PROFILE + ".plist")):
            risks += _read(plist, plistlib.load)
        for flag in RISKY_FLAGS:
            if any(a == flag or a.startswith(flag + "=") for a in args):
                risks.append("%s in arguments" % flag)
        return risks

    def resume_command(self, session_id: str) -> List[str]:
        return ["claude", "--resume", session_id]

    def start_command(self, args: Sequence[str]) -> List[str]:
        return ["claude"] + list(args)

    def login_command(self) -> List[str]:
        return ["claude", "auth", "login"]

    def snapshot_paths(self, session: Session) -> List[Path]:
        sub = session.transcript.with_suffix("")  # <id>/ holds subagent files
        return [session.transcript] + ([sub] if sub.is_dir() else [])

    def self_check(self) -> List[str]:
        _, out, warn, _ = procs.run(["claude", "--version"], VERSION_TIMEOUT)
        if warn:
            return ["cannot check the Claude Code version: %s" % warn]
        m = re.match(r"\s*(\d+)\.(\d+)\.(\d+)", out)
        if not m:
            return ["cannot parse the Claude Code version from %r" % out.strip()[:80]]
        version = tuple(int(x) for x in m.groups())
        lo, hi = (tuple(int(x) for x in v.split(".")) for v in TESTED_VERSIONS)
        if not lo <= version <= hi:
            return ["Claude Code %s is outside the tested range %s-%s"
                    % (".".join(m.groups()), TESTED_VERSIONS[0], TESTED_VERSIONS[1])]
        return []
