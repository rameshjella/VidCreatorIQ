"""OpenAI text-to-speech (gpt-4o-mini-tts / tts-1-hd)."""

from __future__ import annotations

import httpx

from app.config import settings
from app.services.tts.base import TTSResult, TTSUnavailable, VoiceOption

VOICES = [
    ("alloy", "Alloy", "neutral"),
    ("echo", "Echo", "male"),
    ("fable", "Fable", "male"),
    ("onyx", "Onyx", "male"),
    ("nova", "Nova", "female"),
    ("shimmer", "Shimmer", "female"),
    ("ash", "Ash", "male"),
    ("sage", "Sage", "female"),
    ("coral", "Coral", "female"),
]


class OpenAITTSProvider:
    name = "openai"
    quality_rank = 90

    def is_configured(self) -> bool:
        return bool(settings.openai_api_key.strip())

    def synthesize(self, text: str, *, voice: str = "", rate: float = 1.0, pitch: float = 0.0) -> TTSResult:
        if not self.is_configured():
            raise TTSUnavailable("OPENAI_API_KEY is not set")

        selected = voice or settings.openai_tts_voice
        payload = {
            "model": settings.openai_tts_model,
            "input": text,
            "voice": selected,
            "response_format": "mp3",
            # The API clamps speed to [0.25, 4.0].
            "speed": max(0.25, min(4.0, float(rate or 1.0))),
        }
        try:
            response = httpx.post(
                f"{settings.openai_base_url.rstrip('/')}/audio/speech",
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=180,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TTSUnavailable(f"OpenAI TTS returned {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except httpx.HTTPError as exc:
            raise TTSUnavailable(f"OpenAI TTS request failed: {exc}") from exc

        if not response.content:
            raise TTSUnavailable("OpenAI TTS returned an empty audio payload")

        return TTSResult(audio=response.content, source_format="mp3", provider=self.name, voice=selected)

    def list_voices(self) -> list[VoiceOption]:
        return [
            VoiceOption(id=vid, name=label, locale="en-US", gender=gender, provider=self.name)
            for vid, label, gender in VOICES
        ]

