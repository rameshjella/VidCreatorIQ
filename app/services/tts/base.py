from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class TTSUnavailable(RuntimeError):
    """Raised when a provider is not configured or cannot fulfil a request.

    Raising this (rather than returning ``None``) lets the registry move on to
    the next provider in the fallback chain while still surfacing the reason.
    """


class TTSPermanentFailure(TTSUnavailable):
    """Raised for non-retryable provider failures (for example billing/quotas)."""


@dataclass
class VoiceOption:
    id: str
    name: str
    locale: str = ""
    gender: str = ""
    provider: str = ""
    preview_url: str = ""


@dataclass
class TTSResult:
    """Raw synthesis output, before normalisation/encoding."""

    audio: bytes
    source_format: str  # "mp3" | "wav" | "ogg"
    provider: str
    voice: str = ""
    meta: dict = field(default_factory=dict)


@runtime_checkable
class TTSProvider(Protocol):
    name: str
    #: Higher quality providers are preferred when auto-selecting.
    quality_rank: int

    def is_configured(self) -> bool:
        """Return True when credentials / binaries for this provider exist."""
        ...

    def synthesize(self, text: str, *, voice: str = "", rate: float = 1.0, pitch: float = 0.0) -> TTSResult:
        """Synthesize ``text``, raising :class:`TTSUnavailable` on failure."""
        ...

    def list_voices(self) -> list[VoiceOption]:
        """Return the voices this provider exposes (may be empty)."""
        ...

