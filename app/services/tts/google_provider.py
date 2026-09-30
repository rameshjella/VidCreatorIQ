"""Google Cloud Text-to-Speech (Neural2 / Studio voices)."""

from __future__ import annotations

import base64
import os

import httpx

from app.config import settings
from app.services.tts.base import TTSResult, TTSUnavailable, VoiceOption


class GoogleTTSProvider:
    name = "google"
    quality_rank = 85

    def is_configured(self) -> bool:
        creds = settings.google_application_credentials.strip()
        return bool(creds and os.path.exists(creds))

    def _access_token(self) -> str:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account
        except ImportError as exc:
            raise TTSUnavailable(
                "google-auth is not installed (pip install google-auth google-cloud-texttospeech)"
            ) from exc

        try:
            credentials = service_account.Credentials.from_service_account_file(
                settings.google_application_credentials,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            credentials.refresh(Request())
            return credentials.token
        except Exception as exc:
            raise TTSUnavailable(f"Could not obtain a Google access token: {exc}") from exc

    def synthesize(self, text: str, *, voice: str = "", rate: float = 1.0, pitch: float = 0.0) -> TTSResult:
        if not self.is_configured():
            raise TTSUnavailable("GOOGLE_APPLICATION_CREDENTIALS is not set or the file is missing")

        selected = voice or settings.google_tts_voice
        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": settings.google_tts_language_code,
                "name": selected,
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": max(0.25, min(4.0, float(rate or 1.0))),
                "pitch": max(-20.0, min(20.0, float(pitch or 0.0))),
                "sampleRateHertz": settings.tts_sample_rate,
            },
        }

        try:
            response = httpx.post(
                "https://texttospeech.googleapis.com/v1/text:synthesize",
                json=payload,
                headers={"Authorization": f"Bearer {self._access_token()}"},
                timeout=120,
            )
            response.raise_for_status()
            encoded = response.json().get("audioContent", "")
        except httpx.HTTPStatusError as exc:
            raise TTSUnavailable(f"Google TTS returned {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except httpx.HTTPError as exc:
            raise TTSUnavailable(f"Google TTS request failed: {exc}") from exc

        if not encoded:
            raise TTSUnavailable("Google TTS returned an empty audio payload")

        return TTSResult(
            audio=base64.b64decode(encoded),
            source_format="mp3",
            provider=self.name,
            voice=selected,
        )

    def list_voices(self) -> list[VoiceOption]:
        if not self.is_configured():
            return []
        try:
            response = httpx.get(
                "https://texttospeech.googleapis.com/v1/voices",
                headers={"Authorization": f"Bearer {self._access_token()}"},
                params={"languageCode": settings.google_tts_language_code},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            return []

        return [
            VoiceOption(
                id=item.get("name", ""),
                name=item.get("name", ""),
                locale=(item.get("languageCodes") or [""])[0],
                gender=item.get("ssmlGender", ""),
                provider=self.name,
            )
            for item in data.get("voices", [])
        ]

