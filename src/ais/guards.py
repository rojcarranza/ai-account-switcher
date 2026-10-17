import os
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

from ais.accounts import EXIT_USAGE
from ais.errors import AisError

EXIT_BILLING = 77


def refuse_on_risks(risks: List[str], allow_api_key: bool) -> None:
    if risks and not allow_api_key:
        raise AisError(EXIT_BILLING, "%s; refusing to start claude "
                       "(pass --allow-api-key to override)" % risks[0])


def safe_path(p: Path, roots: Sequence[Path]) -> Path:
    real = Path(os.path.realpath(str(p)))
    for root in roots:
        r = Path(os.path.realpath(str(root)))
        if real == r or r in real.parents:  # component compare, not string prefix
            return real
    raise AisError(EXIT_USAGE, "%s is outside the allowed folders" % p)


def print_warnings(warnings: Iterable[str]) -> None:
    for w in warnings:
        print("ais: warning: " + w, file=sys.stderr)
