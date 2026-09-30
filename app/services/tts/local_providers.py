"""Fully offline fallbacks: Piper (neural, good) and pyttsx3 (SAPI, last resort)."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.config import settings
from app.services.tts.base import TTSResult, TTSUnavailable, VoiceOption


class PiperProvider:
    name = "piper"
    quality_rank = 60

    def is_configured(self) -> bool:
        return bool(
            settings.piper_executable
            and settings.piper_model_path
            and Path(settings.piper_executable).exists()
            and Path(settings.piper_model_path).exists()
        )

    def synthesize(self, text: str, *, voice: str = "", rate: float = 1.0, pitch: float = 0.0) -> TTSResult:
        if not self.is_configured():
            raise TTSUnavailable("PIPER_EXECUTABLE / PIPER_MODEL_PATH are not set or do not exist")

        model = voice or settings.piper_model_path
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "piper.wav"
            # Piper's length_scale is inverse to speaking rate.
            length_scale = settings.piper_length_scale / max(0.25, float(rate or 1.0))
            cmd = [
                settings.piper_executable,
                "--model", str(model),
                "--output_file", str(out_path),
                "--length_scale", f"{length_scale:.3f}",
                "--noise_scale", f"{settings.piper_noise_scale:.3f}",
                "--sentence_silence", f"{settings.tts_sentence_pause_ms / 1000.0:.3f}",
            ]
            try:
                subprocess.run(
                    cmd,
                    input=text.encode("utf-8"),
                    check=True,
                    capture_output=True,
                    timeout=300,
                )
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b"").decode("utf-8", "replace")[-300:]
                raise TTSUnavailable(f"Piper failed (exit {exc.returncode}): {stderr}") from exc
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise TTSUnavailable(f"Piper could not be executed: {exc}") from exc

            if not out_path.exists() or out_path.stat().st_size == 0:
                raise TTSUnavailable("Piper produced no audio")

            return TTSResult(
                audio=out_path.read_bytes(),
                source_format="wav",
                provider=self.name,
                voice=str(model),
            )

    def list_voices(self) -> list[VoiceOption]:
        if not self.is_configured():
            return []
        model = Path(settings.piper_model_path)
        return [VoiceOption(id=str(model), name=model.stem, provider=self.name)]


class Pyttsx3Provider:
    """Offline OS speech synthesis. Robotic, but guarantees the render never dies."""

    name = "pyttsx3"
    quality_rank = 10

    def is_configured(self) -> bool:
        try:
            import pyttsx3  # noqa: F401
        except ImportError:
            return False
        return True

    def synthesize(self, text: str, *, voice: str = "", rate: float = 1.0, pitch: float = 0.0) -> TTSResult:
        try:
            import pyttsx3
        except ImportError as exc:
            raise TTSUnavailable("pyttsx3 is not installed") from exc

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "speech.wav"
            try:
                engine = pyttsx3.init()
                base_rate = engine.getProperty("rate") or 200
                engine.setProperty("rate", int(base_rate * float(rate or 1.0)))
                if voice:
                    engine.setProperty("voice", voice)
                engine.save_to_file(text, str(out_path))
                engine.runAndWait()
                engine.stop()
            except Exception as exc:
                raise TTSUnavailable(f"pyttsx3 synthesis failed: {exc}") from exc

            if not out_path.exists() or out_path.stat().st_size == 0:
                raise TTSUnavailable("pyttsx3 produced no audio")

            return TTSResult(audio=out_path.read_bytes(), source_format="wav", provider=self.name, voice=voice)

    def list_voices(self) -> list[VoiceOption]:
        try:
            import pyttsx3

            engine = pyttsx3.init()
            voices = engine.getProperty("voices") or []
            engine.stop()
        except Exception:
            return []

        return [
            VoiceOption(id=v.id, name=getattr(v, "name", v.id), provider=self.name)
            for v in voices
        ]

