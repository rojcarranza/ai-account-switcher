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

    install_hint: str
    resume_flags: Tuple[str, ...]  # long flags that resume or fork a session
    short_resume_letters: str  # short flags (single letters) that resume a session
    process_name: str  # exact process name of a running session (pgrep -x)
    cred_dir_root: str  # folder under home that holds extra accounts' credDirs
    shared_data_note: str  # FR-2.7: what is shared between accounts

    def default_settings_roots(self) -> Dict[str, Path]: ...

    def describe_env(self, env: Mapping[str, str]) -> str:
        """Shell-quoted `NAME=value ` prefix for the per-account variables in env, or ""."""
        ...

    def env_for(self, account: Account, base_env: Mapping[str, str]) -> Tuple[Dict[str, str], List[str]]: ...

    def billing_risks(self, env: Mapping[str, str], folder: Path, args: Sequence[str],
                      settings_roots: Mapping[str, Path]) -> List[str]: ...

    def resume_command(self, session_id: str) -> List[str]: ...

    def start_command(self, args: Sequence[str]) -> List[str]: ...

    def auth_status_command(self) -> List[str]: ...

    def login_command(self) -> List[str]: ...

    def newest_session(self, folder: Path, cache: Any) -> Optional[Session]: ...

    def recent_sessions(self, limit: int, cache: Any, folder: Optional[Path] = None) -> List[Session]:
        """Newest first; only sessions of that folder when one is given."""
        ...

    def in_folder(self, session: Session, folder: Path) -> bool:
        """Whether the session belongs to that folder (the rule newest_session uses)."""
        ...

    def find_session(self, session_id: str, cache: Any) -> Optional[Session]: ...

    def open_session_pid(self, session: Session, procs: Any) -> Optional[int]: ...

    def has_credential(self, account: Account, base_env: Mapping[str, str]) -> Tuple[str, str, str]:
        """(state yes|no|unknown, source, error)."""
        ...

    def keychain_credential(self, account: Account) -> Tuple[str, str, str]: ...

    def snapshot_paths(self, session: Session) -> List[Path]: ...

    def self_check(self) -> List[str]: ...

    def credential_removal_hint(self, account: Optional[Account]) -> Optional[str]:
        """Manual step that removes an extra account's stored credential; None for the default account.
        With account None (no config), a generic step for any extra account."""
        ...

    def limit_time(self, session: Session, launch_offset: int) -> Optional[float]:
        """End-to-end seconds from the limit hit to the first transcript line appended past launch_offset."""
        ...

    def desktop_data_dir(self, account: Account, home: Path) -> Optional[Path]:
        """The Desktop data folder of an extra account; None for the default account."""
        ...

    def desktop_records(self, data_dir: Optional[Path], home: Path) -> Dict[str, Tuple[str, int]]:
        """Session ID -> (title, last activity ms) from that Desktop data folder (None = default); never raises."""
        ...

    def desktop_usage(self, data_dir: Optional[Path], home: Path) -> Optional[Dict[str, Any]]:
        """{"t": ms, "fh": 5-hour %, "sd": weekly %} of the newest usage sample in that Desktop folder; never raises."""
        ...

    def desktop_launch_command(self, data_dir: Optional[Path], app_roots: Sequence[Path]) -> List[str]:
        """Command that opens a new Desktop instance; AisError(69) when the app is in none of the roots."""
        ...

    def desktop_running_pid(self, data_dir: Optional[Path]) -> Optional[int]:
        """PID of the Desktop instance using that data folder (None = the default one); AisError(69) if ps fails."""
        ...

    def desktop_running(self, data_dirs: Sequence[Optional[Path]]) -> List[bool]:
        """Per data folder, whether its Desktop instance runs, from one process listing; all False if it fails."""
        ...
