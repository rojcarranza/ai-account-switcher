from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from ais.accounts import Account


@dataclass
class Session:
    id: str
    folder: Path
    transcript: Path
    title: str
    modified: float


class Provider(Protocol):
    """Everything provider-specific goes through this interface (FR-5.1)."""

    def env_for(self, account: Account, base_env: Mapping[str, str]) -> Tuple[Dict[str, str], List[str]]: ...

    def billing_risks(self, env: Mapping[str, str], folder: Path, args: Sequence[str],
                      settings_roots: Mapping[str, Path]) -> List[str]: ...

    def resume_command(self, session_id: str) -> List[str]: ...

    def start_command(self, args: Sequence[str]) -> List[str]: ...

    def login_command(self) -> List[str]: ...

    def newest_session(self, folder: Path, cache: Any) -> Optional[Session]: ...

    def recent_sessions(self, limit: int, cache: Any) -> List[Session]: ...

    def find_session(self, session_id: str, cache: Any) -> Optional[Session]: ...

    def open_session_pid(self, session: Session, procs: Any) -> Optional[int]: ...

    def has_credential(self, account: Account, base_env: Mapping[str, str]) -> Tuple[str, str, str]:
        """(state yes|no|unknown, source, error)."""
        ...

    def keychain_credential(self, account: Account) -> Tuple[str, str, str]: ...

    def snapshot_paths(self, session: Session) -> List[Path]: ...

    def self_check(self) -> List[str]: ...

    def limit_time(self, session: Session, launched_at: float) -> Optional[float]: ...
