import os
import re
import unicodedata
from pathlib import Path
from dataclasses import dataclass
from typing import Collection, Dict, Optional

from ais.errors import AisError
from ais.store import EXIT_CONFIG, Store

EXIT_USAGE = 64
NAME_RE = re.compile(r"[a-z][a-z0-9-]{0,31}")


@dataclass
class Account:
    name: str
    label: str
    provider: str
    cred_dir: Optional[str]
    desktop_data_dir: Optional[str] = None

    @property
    def is_default(self) -> bool:
        return self.cred_dir is None


@dataclass
class Config:
    accounts: Dict[str, Account]
    default: str
    acks: Dict[str, str]
    menu_privacy: bool

    def get(self, name: str) -> Account:
        if not NAME_RE.fullmatch(name) or name not in self.accounts:
            raise AisError(EXIT_USAGE, "unknown account %r; defined accounts: %s"
                           % (name, ", ".join(sorted(self.accounts))))
        return self.accounts[name]


def _check_cred_dir(path: Path, name: str, cred_dir: object, home: str) -> str:
    def bad(rule: str) -> AisError:
        return AisError(EXIT_CONFIG, "%s: account %s: credDir %r %s" % (path, name, cred_dir, rule))

    if not isinstance(cred_dir, str) or not os.path.isabs(cred_dir):
        raise bad("must be an absolute path")
    if "~" in cred_dir:
        raise bad("must not contain ~")
    if cred_dir.endswith("/"):
        raise bad("must not end with /")
    if unicodedata.normalize("NFC", cred_dir) != cred_dir:
        raise bad("must be NFC-normalized")
    if os.path.normpath(cred_dir) != cred_dir or "//" in cred_dir:
        raise bad("must be a canonical path (no '.', '..' or '//')")
    real = os.path.realpath(cred_dir)
    if real != home and not real.startswith(home.rstrip("/") + "/"):
        raise bad("resolves outside the home folder")
    return cred_dir


def _check_desktop_dir(path: Path, name: str, value: object, home: str) -> str:
    def bad(rule: str) -> AisError:
        return AisError(EXIT_CONFIG, "%s: account %s: desktop_data_dir %r %s" % (path, name, value, rule))

    if not isinstance(value, str) or not os.path.isabs(value):
        raise bad("must be an absolute path")
    if "~" in value:
        raise bad("must not contain ~")
    if os.path.normpath(value) != value or "//" in value:
        raise bad("must be a canonical path (no '.', '..', '//' or trailing /)")
    support = os.path.realpath(os.path.join(home, "Library", "Application Support"))
    real = os.path.realpath(value)
    if os.path.dirname(real) != support:
        raise bad("must be a folder directly under %s" % support)
    if os.path.exists(real) and not os.path.isdir(real):
        raise bad("must be a folder")
    return value


def load_config(store: Store, providers: Collection[str]) -> Config:
    path = store.dir / "config.json"
    if not path.exists():
        raise AisError(EXIT_CONFIG, "%s: not found; run `ais setup`" % path)
    raw = store.read_json("config.json")

    def bad(msg: str) -> AisError:
        return AisError(EXIT_CONFIG, "%s: %s" % (path, msg))

    if type(raw.get("version")) is not int or raw["version"] != 1:
        raise bad("unknown or missing version %r; only 1 is supported" % (raw.get("version"),))
    raw_accounts = raw.get("accounts")
    if not isinstance(raw_accounts, dict):
        raise bad("accounts must be an object")
    default = raw.get("default")
    if not isinstance(default, str) or default not in raw_accounts:
        raise bad("default account %r is not defined in accounts" % (default,))
    acks = raw.get("cross_account_ack", {})
    if not isinstance(acks, dict):
        raise bad("cross_account_ack must be an object")
    if not all(isinstance(v, str) for v in acks.values()):
        raise bad("cross_account_ack values must be strings")
    privacy = raw.get("menu_privacy", False)
    if not isinstance(privacy, bool):
        raise bad("menu_privacy must be true or false")

    home = os.path.realpath(str(store.home))
    accounts = {}  # type: Dict[str, Account]
    desks = {}  # type: Dict[str, str]  # realpath -> account, one Desktop profile each
    slots = {}  # type: Dict[str, str]  # realpath -> account, one Keychain slot each
    for name in sorted(raw_accounts, key=lambda n: n != default):  # default first: its errors win
        a = raw_accounts[name]
        if not NAME_RE.fullmatch(name):
            raise bad("account %s: id must match ^[a-z][a-z0-9-]{0,31}$" % name)
        if not isinstance(a, dict):
            raise bad("account %s: must be an object" % name)
        label = a.get("label")
        if not isinstance(label, str) or not label:
            raise bad("account %s: label must be a non-empty string" % name)
        provider = a.get("provider")
        if not isinstance(provider, str) or provider not in providers:
            raise bad("account %s: unknown provider %r; registered providers: %s"
                      % (name, provider, ", ".join(sorted(providers))))
        cred_dir = a.get("credDir")
        if name == default:
            if cred_dir is not None:
                raise bad("account %s: the default account must have credDir null" % name)
        elif cred_dir is None:
            raise bad("account %s: credDir is required for a non-default account" % name)
        else:
            cred_dir = _check_cred_dir(path, name, cred_dir, home)
            real = os.path.realpath(cred_dir)
            if real in slots:
                raise bad("accounts %s and %s share credDir %r" % (slots[real], name, cred_dir))
            slots[real] = name
        desktop = a.get("desktop_data_dir")
        if desktop is not None:
            if name == default:
                raise bad("account %s: the default account must not set desktop_data_dir" % name)
            desktop = _check_desktop_dir(path, name, desktop, home)
            real = os.path.realpath(desktop)
            if real in desks:
                raise bad("accounts %s and %s share desktop_data_dir %r" % (desks[real], name, desktop))
            desks[real] = name
        accounts[name] = Account(name, label, provider, cred_dir, desktop)
    return Config(accounts, default, acks, privacy)
