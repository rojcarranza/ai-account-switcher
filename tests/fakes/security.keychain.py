"""Stateful fake `security` for tests of `ais default`: items are files in $FAKE_KEYCHAIN_DIR/<service>
(line 1 the account attribute, then the secret). Supports find-generic-password [-w], and
`security -i` reading add-generic-password -U -s S -a A -X HEX from stdin. $FAKE_KEYCHAIN_FAIL_ADD=<service>
makes the add for that service fail. Every argv and stdin command is logged to $FAKE_KEYCHAIN_LOG."""
import os
import shlex
import sys

root = os.environ["FAKE_KEYCHAIN_DIR"]
log = os.environ.get("FAKE_KEYCHAIN_LOG")


def note(text):
    if log:
        with open(log, "a") as f:
            f.write(text + "\n")


def opt(argv, flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


def run(argv):
    cmd = argv[0]
    path = os.path.join(root, opt(argv, "-s") or "")
    if cmd == "find-generic-password":
        if not os.path.exists(path):
            print("security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.", file=sys.stderr)
            return 44
        acct, _, secret = open(path).read().partition("\n")
        if "-w" in argv:
            print(secret)
        else:
            print('keychain: "/fake/login.keychain-db"\n    "acct"<blob>="%s"\n    "svce"<blob>="%s"' % (acct, opt(argv, "-s")))
        return 0
    if cmd == "add-generic-password":
        if os.environ.get("FAKE_KEYCHAIN_FAIL_ADD") == opt(argv, "-s"):
            print("security: write failed", file=sys.stderr)
            return 1
        with open(path, "w") as f:
            f.write(opt(argv, "-a") + "\n" + bytes.fromhex(opt(argv, "-X")).decode())
        return 0
    return 2


args = sys.argv[1:]
note("argv " + " ".join(args))
if args[:1] == ["-i"]:
    rc = 0
    for line in sys.stdin.read().splitlines():
        note("stdin " + line.split(" -X ")[0])  # the hex secret is not logged
        rc = rc or run(shlex.split(line))
    sys.exit(rc)
sys.exit(run(args))
