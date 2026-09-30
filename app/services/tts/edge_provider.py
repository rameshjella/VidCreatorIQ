"""Microsoft Edge neural voices via the free `edge-tts` endpoint.

This is the default provider because it needs no API key yet still produces
genuinely neural (not robotic) speech — a large upgrade over pyttsx3/SAPI.
"""

from __future__ import annotations

import asyncio

from app.config import settings
from app.services.tts.base import TTSResult, TTSUnavailable, VoiceOption

CURATED_VOICES = [
    ("en-US-AriaNeural", "Aria", "en-US", "female"),
    ("en-US-JennyNeural", "Jenny", "en-US", "female"),
    ("en-US-GuyNeural", "Guy", "en-US", "male"),
    ("en-US-ChristopherNeural", "Christopher", "en-US", "male"),
    ("en-US-EricNeural", "Eric", "en-US", "male"),
    ("en-US-MichelleNeural", "Michelle", "en-US", "female"),
    ("en-GB-RyanNeural", "Ryan", "en-GB", "male"),
    ("en-GB-SoniaNeural", "Sonia", "en-GB", "female"),
    ("en-AU-NatashaNeural", "Natasha", "en-AU", "female"),
    ("en-IN-NeerjaNeural", "Neerja", "en-IN", "female"),
    ("en-IN-PrabhatNeural", "Prabhat", "en-IN", "male"),
]


def _percent(value: float, *, baseline: float = 1.0) -> str:
    delta = int(round((value - baseline) * 100))
    return f"{delta:+d}%"


class EdgeTTSProvider:
    name = "edge"
    quality_rank = 80

    def is_configured(self) -> bool:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False
        return True

    def synthesize(self, text: str, *, voice: str = "", rate: float = 1.0, pitch: float = 0.0) -> TTSResult:
        try:
            import edge_tts
        except ImportError as exc:
            raise TTSUnavailable("edge-tts is not installed (pip install edge-tts)") from exc

        selected = voice or settings.edge_tts_voice
        rate_str = _percent(rate or 1.0)
        pitch_str = f"{int(round(pitch or 0))}Hz"
        if not pitch_str.startswith("-"):
            pitch_str = f"+{pitch_str}"

        async def _run() -> bytes:
            communicate = edge_tts.Communicate(text, selected, rate=rate_str, pitch=pitch_str)
            buffer = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    buffer.extend(chunk.get("data") or b"")
            return bytes(buffer)

        try:
            audio = _run_async(_run())
        except Exception as exc:
            raise TTSUnavailable(f"edge-tts synthesis failed: {exc}") from exc

        if not audio:
            raise TTSUnavailable("edge-tts returned an empty audio payload")

        return TTSResult(audio=audio, source_format="mp3", provider=self.name, voice=selected)

    def list_voices(self) -> list[VoiceOption]:
        return [
            VoiceOption(id=vid, name=label, locale=locale, gender=gender, provider=self.name)
            for vid, label, locale, gender in CURATED_VOICES
        ]


def _run_async(coro):
    """Run a coroutine even when an event loop is already active in this thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()

