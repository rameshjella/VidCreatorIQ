"""ElevenLabs — best-in-class expressive neural voices."""

from __future__ import annotations

import httpx

from app.config import settings
from app.services.tts.base import TTSResult, TTSUnavailable, VoiceOption

API_ROOT = "https://api.elevenlabs.io/v1"


class ElevenLabsProvider:
    name = "elevenlabs"
    quality_rank = 100

    def is_configured(self) -> bool:
        return bool(settings.elevenlabs_api_key.strip())

    def synthesize(self, text: str, *, voice: str = "", rate: float = 1.0, pitch: float = 0.0) -> TTSResult:
        if not self.is_configured():
            raise TTSUnavailable("ELEVENLABS_API_KEY is not set")

        voice_id = voice or settings.elevenlabs_voice_id
        url = f"{API_ROOT}/text-to-speech/{voice_id}"
        payload = {
            "text": text,
            "model_id": settings.elevenlabs_model_id,
            "voice_settings": {
                "stability": settings.elevenlabs_stability,
                "similarity_boost": settings.elevenlabs_similarity_boost,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }
        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        try:
            response = httpx.post(
                url,
                json=payload,
                headers=headers,
                params={"output_format": "mp3_44100_192"},
                timeout=120,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise TTSUnavailable(f"ElevenLabs returned {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise TTSUnavailable(f"ElevenLabs request failed: {exc}") from exc

        if not response.content:
            raise TTSUnavailable("ElevenLabs returned an empty audio payload")

        return TTSResult(audio=response.content, source_format="mp3", provider=self.name, voice=voice_id)

    def list_voices(self) -> list[VoiceOption]:
        if not self.is_configured():
            return []
        try:
            response = httpx.get(
                f"{API_ROOT}/voices",
                headers={"xi-api-key": settings.elevenlabs_api_key},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            return []

        return [
            VoiceOption(
                id=item.get("voice_id", ""),
                name=item.get("name", ""),
                locale=(item.get("labels") or {}).get("accent", ""),
                gender=(item.get("labels") or {}).get("gender", ""),
                provider=self.name,
                preview_url=item.get("preview_url", "") or "",
            )
            for item in data.get("voices", [])
        ]

