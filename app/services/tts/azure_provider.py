"""Azure Cognitive Services Speech via the REST endpoint (no SDK required)."""

from __future__ import annotations

import html

import httpx

from app.config import settings
from app.services.tts.base import TTSResult, TTSUnavailable, VoiceOption


class AzureTTSProvider:
    name = "azure"
    quality_rank = 88

    def is_configured(self) -> bool:
        return bool(settings.azure_speech_key.strip() and settings.azure_speech_region.strip())

    def _endpoint(self) -> str:
        region = settings.azure_speech_region.strip()
        return f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

    def synthesize(self, text: str, *, voice: str = "", rate: float = 1.0, pitch: float = 0.0) -> TTSResult:
        if not self.is_configured():
            raise TTSUnavailable("AZURE_SPEECH_KEY / AZURE_SPEECH_REGION are not set")

        selected = voice or settings.azure_speech_voice
        locale = "-".join(selected.split("-")[:2]) or "en-US"
        rate_pct = f"{int(round((float(rate or 1.0) - 1.0) * 100)):+d}%"
        pitch_pct = f"{int(round(float(pitch or 0.0))):+d}%"

        ssml = (
            f"<speak version='1.0' xml:lang='{locale}'>"
            f"<voice xml:lang='{locale}' name='{selected}'>"
            f"<prosody rate='{rate_pct}' pitch='{pitch_pct}'>{html.escape(text)}</prosody>"
            f"</voice></speak>"
        )

        try:
            response = httpx.post(
                self._endpoint(),
                content=ssml.encode("utf-8"),
                headers={
                    "Ocp-Apim-Subscription-Key": settings.azure_speech_key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "audio-48khz-192kbitrate-mono-mp3",
                    "User-Agent": "VidCreatorIQ",
                },
                timeout=120,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TTSUnavailable(f"Azure Speech returned {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except httpx.HTTPError as exc:
            raise TTSUnavailable(f"Azure Speech request failed: {exc}") from exc

        if not response.content:
            raise TTSUnavailable("Azure Speech returned an empty audio payload")

        return TTSResult(audio=response.content, source_format="mp3", provider=self.name, voice=selected)

    def list_voices(self) -> list[VoiceOption]:
        if not self.is_configured():
            return []
        region = settings.azure_speech_region.strip()
        try:
            response = httpx.get(
                f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list",
                headers={"Ocp-Apim-Subscription-Key": settings.azure_speech_key},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            return []

        return [
            VoiceOption(
                id=item.get("ShortName", ""),
                name=item.get("DisplayName", ""),
                locale=item.get("Locale", ""),
                gender=item.get("Gender", ""),
                provider=self.name,
            )
            for item in data
            if item.get("VoiceType") == "Neural"
        ]

