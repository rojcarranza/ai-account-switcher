from typing import Dict, List, Optional, Tuple


class FakeProvider:
    """Minimal provider for registry tests."""

    cred_dir_root = ".fake-accounts"
    shared_data_note = "fake shared data"

    def auth_status_command(self) -> List[str]:
        return ["fake", "status"]

    def env_for(self, account, base_env: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
        return dict(base_env), []

    def billing_risks(self, env, folder, args, settings_roots) -> List[str]:
        return []

    def resume_command(self, session_id: str) -> List[str]:
        return ["fake", "resume", session_id]

    def start_command(self, args) -> List[str]:
        return ["fake"] + list(args)

    def login_command(self) -> List[str]:
        return ["fake", "login"]

    def self_check(self) -> List[str]:
        return []

    def credential_removal_hint(self, account) -> Optional[str]:
        return None if account.is_default else "fake remove %s" % account.name
