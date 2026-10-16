import json
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bash_hook():
    with open(os.path.join(ROOT, ".claude", "settings.json")) as f:
        hooks = json.load(f)["hooks"]["PreToolUse"]
    return next(h["hooks"][0]["command"] for h in hooks if h["matcher"] == "Bash")


def blocked(command):
    r = subprocess.run(["sh", "-c", bash_hook()], input=json.dumps({"tool_input": {"command": command}}),
                       capture_output=True, text=True, timeout=10)
    return r.returncode == 2


class BashHookTest(unittest.TestCase):
    def test_blocks_secret_printing_and_config_dir(self):
        for command in ('security find-generic-password -s "Claude Code-credentials" -w',
                        "security find-generic-password -ga x",
                        "security dump-keychain -d",
                        'security find-generic-password -s "Claude Code-credentials" "-w"',
                        "security find-generic-password -s x '-g'",
                        "CLAUDE_CONFIG_DIR=/tmp/x claude"):
            self.assertTrue(blocked(command), command)

    def test_allows_read_only_keychain_lookups(self):
        for command in ('security find-generic-password -s "Claude Code-credentials-f9fb4ac6"',
                        "security dump-keychain | grep -d skip",
                        "claude auth status"):
            self.assertFalse(blocked(command), command)


if __name__ == "__main__":
    unittest.main()
