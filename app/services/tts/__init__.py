"""Multi-provider text-to-speech.

Providers are tried in the order given by ``TTS_PROVIDER`` followed by
``TTS_FALLBACK_CHAIN``. Every provider returns raw bytes in some source
format; :mod:`app.services.tts.postprocess` then normalises loudness and
encodes a consistent 44.1 kHz / 192 kbps MP3 so the downstream render stage
never has to deal with mismatched sample rates.
"""

from app.services.tts.base import TTSProvider, TTSResult, TTSUnavailable, VoiceOption
from app.services.tts.registry import (
    available_providers,
    get_provider,
    resolve_provider_chain,
)

__all__ = [
    "TTSProvider",
    "TTSResult",
    "TTSUnavailable",
    "VoiceOption",
    "available_providers",
    "get_provider",
    "resolve_provider_chain",
]

