"""Provider registry and fallback-chain resolution."""

from __future__ import annotations

from app.config import settings
from app.services.tts.azure_provider import AzureTTSProvider
from app.services.tts.base import TTSProvider, TTSUnavailable, VoiceOption
from app.services.tts.edge_provider import EdgeTTSProvider
from app.services.tts.elevenlabs_provider import ElevenLabsProvider
from app.services.tts.google_provider import GoogleTTSProvider
from app.services.tts.local_providers import PiperProvider, Pyttsx3Provider
from app.services.tts.openai_provider import OpenAITTSProvider

_PROVIDERS: dict[str, TTSProvider] = {
    ElevenLabsProvider.name: ElevenLabsProvider(),
    OpenAITTSProvider.name: OpenAITTSProvider(),
    AzureTTSProvider.name: AzureTTSProvider(),
    GoogleTTSProvider.name: GoogleTTSProvider(),
    EdgeTTSProvider.name: EdgeTTSProvider(),
    PiperProvider.name: PiperProvider(),
    Pyttsx3Provider.name: Pyttsx3Provider(),
}

# Common aliases so .env values are forgiving.
_ALIASES = {
    "eleven": "elevenlabs",
    "eleven_labs": "elevenlabs",
    "11labs": "elevenlabs",
    "openai_tts": "openai",
    "edge_tts": "edge",
    "edgetts": "edge",
    "microsoft": "azure",
    "gcp": "google",
    "sapi": "pyttsx3",
    "system": "pyttsx3",
}


def _canonical(name: str) -> str:
    key = (name or "").strip().lower().replace("-", "_")
    return _ALIASES.get(key, key)


def get_provider(name: str) -> TTSProvider:
    key = _canonical(name)
    if key not in _PROVIDERS:
        raise TTSUnavailable(f"Unknown TTS provider '{name}'. Known: {', '.join(sorted(_PROVIDERS))}")
    return _PROVIDERS[key]


def resolve_provider_chain(preferred: str | None = None) -> list[TTSProvider]:
    """Build the ordered list of providers to attempt.

    The explicitly requested provider (or ``TTS_PROVIDER``) is tried first,
    then ``TTS_FALLBACK_CHAIN``. Unconfigured providers are filtered out so a
    missing API key costs nothing at render time.
    """
    ordered: list[str] = []

    for candidate in [preferred, settings.tts_provider]:
        key = _canonical(candidate or "")
        if key and key in _PROVIDERS and key not in ordered:
            ordered.append(key)

    for raw in (settings.tts_fallback_chain or "").split(","):
        key = _canonical(raw)
        if key and key in _PROVIDERS and key not in ordered:
            ordered.append(key)

    # pyttsx3 is always the final safety net so a render can never be blocked
    # purely by a missing voice service.
    if Pyttsx3Provider.name not in ordered:
        ordered.append(Pyttsx3Provider.name)

    chain = [_PROVIDERS[key] for key in ordered]
    configured = [p for p in chain if _safe_is_configured(p)]
    return configured or chain


def _safe_is_configured(provider: TTSProvider) -> bool:
    try:
        return bool(provider.is_configured())
    except Exception:
        return False


def available_providers() -> list[dict]:
    """Describe every provider for the settings UI."""
    result = []
    for key, provider in sorted(_PROVIDERS.items(), key=lambda kv: -kv[1].quality_rank):
        result.append(
            {
                "id": key,
                "name": key.replace("_", " ").title(),
                "configured": _safe_is_configured(provider),
                "quality_rank": provider.quality_rank,
                "requires_key": key in {"elevenlabs", "openai", "azure", "google"},
            }
        )
    return result


def list_voices(provider_name: str) -> list[VoiceOption]:
    try:
        return get_provider(provider_name).list_voices()
    except Exception:
        return []

