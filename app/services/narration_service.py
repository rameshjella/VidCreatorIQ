"""High-level narration synthesis.

Responsibilities beyond raw synthesis:

* walk the provider fallback chain with retries,
* split long scene text into sentence-sized chunks the APIs accept,
* normalise loudness and encode a consistent 192 kbps / 44.1 kHz MP3,
* cache results so re-rendering a project does not re-bill API calls,
* report the *measured* duration so the video stage can match scene length.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.services import ffmpeg_runner as ff
from app.services.tts import postprocess
from app.services.tts.base import TTSUnavailable
from app.services.tts.registry import resolve_provider_chain

logger = logging.getLogger(__name__)


@dataclass
class Narration:
    path: Path
    duration: float
    provider: str
    voice: str


class TTSService:
    def __init__(self, out_dir: Path, *, provider: str | None = None, voice: str = ""):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.provider_name = provider
        self.voice = voice
        self.cache_dir = Path(settings.workspace_dir) / ".tts_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def synthesize(self, text: str, scene_index: int) -> Path:
        """Synthesize one scene's narration, returning the MP3 path.

        Kept returning a ``Path`` for backwards compatibility with existing
        call sites; use :meth:`synthesize_detailed` when you need the duration.
        """
        return self.synthesize_detailed(text, scene_index).path

    def synthesize_detailed(self, text: str, scene_index: int) -> Narration:
        output_path = self.out_dir / f"scene_{scene_index:03d}.mp3"
        clean = " ".join((text or "").split())

        if not clean:
            # An empty scene still needs a real audio file so concat stays aligned.
            self._render_silence(output_path, seconds=settings.render_min_scene_seconds)
            return Narration(output_path, ff.probe_duration(output_path), "silence", "")

        cache_key = self._cache_key(clean)
        cached = self.cache_dir / f"{cache_key}.mp3"
        if cached.exists() and cached.stat().st_size > 0:
            output_path.write_bytes(cached.read_bytes())
            return Narration(output_path, ff.probe_duration(output_path), "cache", self.voice)

        errors: list[str] = []
        for provider in resolve_provider_chain(self.provider_name):
            try:
                self._synthesize_with(provider, clean, output_path)
            except Exception as exc:  # noqa: BLE001 - capture the reason, then try the next one
                errors.append(f"{provider.name}: {exc}")
                logger.warning("TTS provider %s failed for scene %s: %s", provider.name, scene_index, exc)
                continue

            duration = ff.probe_duration(output_path)
            cached.write_bytes(output_path.read_bytes())
            return Narration(output_path, duration, provider.name, self.voice or "")

        raise TTSUnavailable(
            "All TTS providers failed for scene "
            f"{scene_index}. Configure a provider in .env (TTS_PROVIDER / API keys).\n"
            + "\n".join(errors)
        )

    def preview(self, text: str, provider: str | None = None, voice: str = "") -> Path:
        """Render a short sample for the Voice Studio UI."""
        sample = " ".join((text or "").split())[:400] or "This is a preview of the selected narration voice."
        key = self._cache_key(f"preview::{provider}::{voice}::{sample}")
        out_path = self.out_dir / f"preview_{key[:12]}.mp3"

        errors: list[str] = []
        for candidate in resolve_provider_chain(provider):
            try:
                result = candidate.synthesize(
                    sample,
                    voice=voice or self.voice,
                    rate=settings.tts_speaking_rate,
                    pitch=settings.tts_pitch,
                )
                return postprocess.encode_to_mp3(result.audio, result.source_format, out_path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{candidate.name}: {exc}")
        raise TTSUnavailable("Preview failed. " + "; ".join(errors))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _synthesize_with(self, provider, text: str, output_path: Path) -> Path:
        chunks = postprocess.split_sentences(text)
        attempts = max(1, settings.tts_max_retries)

        segments: list[Path] = []
        temp_dir = self.out_dir / ".segments"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            for i, chunk in enumerate(chunks):
                last_error: Exception | None = None
                for attempt in range(attempts):
                    try:
                        result = provider.synthesize(
                            chunk,
                            voice=self.voice,
                            rate=settings.tts_speaking_rate,
                            pitch=settings.tts_pitch,
                        )
                        seg_path = temp_dir / f"{output_path.stem}_{i:03d}.mp3"
                        postprocess.encode_to_mp3(result.audio, result.source_format, seg_path)
                        segments.append(seg_path)
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
                        if attempt < attempts - 1:
                            # Exponential backoff smooths over provider rate limits.
                            time.sleep(1.5 * (2**attempt))
                else:
                    raise last_error or TTSUnavailable("Unknown synthesis failure")

            postprocess.concat_segments(segments, output_path)
            return output_path
        finally:
            for seg in segments:
                seg.unlink(missing_ok=True)

    def _render_silence(self, output_path: Path, seconds: float) -> Path:
        cmd = [
            ff.ffmpeg_bin(), "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=channel_layout=mono:sample_rate={settings.tts_sample_rate}",
            "-t", f"{max(0.5, seconds):.3f}",
            "-c:a", "libmp3lame",
            "-b:a", settings.tts_mp3_bitrate,
            str(output_path),
        ]
        ff.run(cmd)
        return output_path

    def _cache_key(self, text: str) -> str:
        payload = "::".join(
            [
                text,
                str(self.provider_name or settings.tts_provider),
                str(self.voice),
                str(settings.tts_speaking_rate),
                str(settings.tts_pitch),
                str(settings.tts_mp3_bitrate),
                str(settings.tts_sample_rate),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

