"""Everything Claude Code specific (FR-5.1). Constants come from docs/spike-results.md."""
import getpass
import hashlib
import json
import plistlib
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ais.accounts import Account

SLOT_ENV = "CLAUDE_SECURESTORAGE_CONFIG_DIR"
CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
TESTED_VERSIONS = ("2.1.301", "2.1.301")  # min, max inclusive (spike (f))
VERSION_TIMEOUT = 10
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
    if cred_dir is None:
        return "Claude Code-credentials"
    digest = hashlib.sha256(unicodedata.normalize("NFC", cred_dir).encode("utf-8")).hexdigest()
    return "Claude Code-credentials-" + digest[:8]


def _set(env: Mapping[str, Any], name: str) -> bool:
    # A variable counts when present with a non-empty value; claude ignores empty ones.
    return env.get(name) not in (None, "")


def _settings_risks(path: Path, data: Any) -> List[str]:
    if not isinstance(data, dict):
        return ["cannot read %s: top level is not an object" % path]
    risks = ["%s in %s" % (k, path) for k in SETTINGS_KEYS if k in data]
    block = data.get("env")
    if isinstance(block, dict):
        risks += ["%s in %s env" % (n, path) for n in BILLING_ENV if _set(block, n)]
    return risks


def _read(path: Path, loader) -> List[str]:
    try:
        with open(str(path), "rb") as f:
            data = loader(f)
    except FileNotFoundError:
        return []
    except Exception as e:  # unreadable or invalid: fail safe, report it
        return ["cannot read %s: %s" % (path, e)]
    return _settings_risks(path, data)


class ClaudeProvider:
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

    def billing_risks(self, env: Mapping[str, str], folder: Path, args: Sequence[str],
                      settings_roots: Mapping[str, Path]) -> List[str]:
        risks = ["%s in the environment" % n for n in BILLING_ENV if _set(env, n)]
        for root, rel in SETTINGS_FILES:
            base = folder if root == "folder" else settings_roots[root]
            risks += _read(Path(base) / rel, json.load)
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

    def self_check(self) -> List[str]:
        try:
            out = subprocess.run(["claude", "--version"], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 universal_newlines=True, timeout=VERSION_TIMEOUT).stdout
        except (OSError, subprocess.TimeoutExpired) as e:
            return ["cannot check the Claude Code version: %s" % e]
        m = re.match(r"\s*(\d+)\.(\d+)\.(\d+)", out)
        if not m:
            return ["cannot parse the Claude Code version from %r" % out.strip()[:80]]
        version = tuple(int(x) for x in m.groups())
        lo, hi = (tuple(int(x) for x in v.split(".")) for v in TESTED_VERSIONS)
        if not lo <= version <= hi:
            return ["Claude Code %s is outside the tested range %s-%s"
                    % (".".join(m.groups()), TESTED_VERSIONS[0], TESTED_VERSIONS[1])]
        return []
