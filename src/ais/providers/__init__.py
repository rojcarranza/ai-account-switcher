from typing import Dict

from ais.errors import AisError
from ais.providers.base import Provider
from ais.providers.claude import ClaudeProvider
from ais.store import EXIT_CONFIG

REGISTRY = {"claude": ClaudeProvider}  # type: Dict[str, type]
DEFAULT_PROVIDER = "claude"  # what `ais setup` writes into new accounts


def get(name: str) -> Provider:
    if name not in REGISTRY:
        raise AisError(EXIT_CONFIG, "unknown provider %r; registered providers: %s"
                       % (name, ", ".join(sorted(REGISTRY))))
    return REGISTRY[name]()
