"""Local provider contracts and URL validation; no credentials or cloud routes."""

from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Provider:
    id: str
    task: str
    files: tuple[str, ...]
    status: Callable
    prepare: Callable
    run: Callable
    needs_secret: bool = False


class Registry:
    def __init__(self):
        self._providers = {}

    def register(self, provider: Provider) -> None:
        if provider.needs_secret:
            raise ValueError("Only local providers are supported.")
        if provider.id in self._providers:
            raise ValueError("Provider already registered.")
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> Provider:
        return self._providers[provider_id]


def local_base_url(value: str) -> str:
    """Accept loopback hosts only, without embedded credentials or query data."""
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError("Use a server on this Mac: localhost, 127.0.0.1 or ::1.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("The local server port is invalid.") from exc
    return value.rstrip("/")
