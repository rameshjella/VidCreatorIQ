from __future__ import annotations

import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from transformers import AutoProcessor, MusicgenForConditionalGeneration

from app.config import settings


@dataclass
class GenerationResult:
    audio_path: str
    generation_time_ms: int
    sample_rate: int
    duration_seconds: float


class MusicGenerationEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model = None
        self._processor = None
        self._model_id = settings.music_model_id.strip() or "facebook/musicgen-small"
        self._device = self._resolve_device()
        self._output_dir = Path(settings.music_output_dir).resolve()
        self._output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _resolve_device() -> str:
        if torch.cuda.is_available() and torch.version.cuda:
            return "cuda"
        return "cpu"

    @property
    def device(self) -> str:
        return self._device

    @property
    def model_id(self) -> str:
        return self._model_id

    def supported_durations(self) -> list[int]:
        values: list[int] = []
        for raw in settings.music_allowed_durations.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                values.append(int(raw))
            except ValueError:
                continue
        values = sorted({v for v in values if v > 0})
        return values or [4, 8, 12, 16]

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._processor is not None:
            return
        with self._lock:
            if self._model is not None and self._processor is not None:
                return
            self._processor = AutoProcessor.from_pretrained(self._model_id)
            self._model = MusicgenForConditionalGeneration.from_pretrained(self._model_id)
            if self._device == "cuda":
                self._model = self._model.to("cuda")

    def _save_wave(self, values: np.ndarray, sample_rate: int, output_path: Path) -> None:
        values = np.clip(values, -1.0, 1.0)
        pcm = (values * 32767).astype(np.int16)
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())

    def generate_audio(
        self,
        *,
        composed_prompt: str,
        duration_seconds: int,
        generation_id: int,
        seed: int | None = None,
    ) -> GenerationResult:
        self._ensure_loaded()
        assert self._model is not None
        assert self._processor is not None

        allowed_durations = self.supported_durations()
        if duration_seconds not in allowed_durations:
            raise ValueError(f"Duration {duration_seconds}s is not supported. Choose one of: {allowed_durations}")

        max_duration = max(allowed_durations)
        duration_seconds = min(duration_seconds, max_duration, max(1, settings.music_max_duration_seconds))

        frame_rate = int(self._model.config.audio_encoder.frame_rate)
        sample_rate = int(self._model.config.audio_encoder.sampling_rate)
        max_new_tokens = max(1, int(duration_seconds * frame_rate))

        if seed is not None:
            torch.manual_seed(seed)

        inputs = self._processor(text=[composed_prompt], padding=True, return_tensors="pt")
        if self._device == "cuda":
            inputs = {k: v.to("cuda") if hasattr(v, "to") else v for k, v in inputs.items()}

        infer_start = time.perf_counter()
        with torch.inference_mode():
            audio_values = self._model.generate(
                **inputs,
                do_sample=True,
                guidance_scale=3.0,
                max_new_tokens=max_new_tokens,
            )
        generation_time_ms = int((time.perf_counter() - infer_start) * 1000)

        values = audio_values[0, 0].detach().cpu().numpy()
        output_path = self._output_dir / f"music_generation_{generation_id}.wav"
        self._save_wave(values, sample_rate, output_path)

        return GenerationResult(
            audio_path=str(output_path),
            generation_time_ms=generation_time_ms,
            sample_rate=sample_rate,
            duration_seconds=round(len(values) / float(sample_rate), 2),
        )

    def validate_audio_file(self, path: str) -> tuple[bool, float, str]:
        p = Path(path)
        if not p.exists():
            return False, 0.0, "Generated file not found"
        try:
            with wave.open(str(p), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                duration = frames / float(rate) if rate > 0 else 0.0
                if duration <= 0:
                    return False, 0.0, "Generated audio has zero duration"
                _ = wf.readframes(min(frames, 4096))
                return True, duration, "ok"
        except wave.Error as exc:
            return False, 0.0, f"Audio decode failed: {exc}"


music_engine = MusicGenerationEngine()

