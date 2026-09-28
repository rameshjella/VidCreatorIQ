from __future__ import annotations

import time
import wave
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services import music_generation_service


client = TestClient(app)


def _wait_for_generation_done(generation_id: int, timeout_seconds: float = 6.0) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = client.get(f"/music/generations/{generation_id}")
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError("generation did not complete in test timeout")


def _write_test_wave(path: Path, sample_rate: int = 32000, duration_seconds: float = 1.0) -> None:
    t = np.arange(int(sample_rate * duration_seconds), dtype=np.float32) / sample_rate
    wave_data = np.sin(2 * np.pi * 440 * t) * 0.15
    pcm = np.clip(wave_data, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def test_music_health_contract() -> None:
    response = client.get("/music/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "music_engine" in payload
    assert "supported_durations" in payload["music_engine"]


def test_music_warmup_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        music_generation_service.music_engine,
        "warmup",
        lambda: {"model": "facebook/musicgen-small", "device": "cpu", "load_time_ms": 12, "ready": True},
    )
    response = client.post("/music/warmup")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["ready"] is True


def test_music_generate_and_history(monkeypatch) -> None:
    output_path = Path("workspace/test_music_generation.wav").resolve()

    def fake_generate_audio(*, composed_prompt: str, duration_seconds: int, generation_id: int, seed: int | None = None):
        del composed_prompt, duration_seconds, generation_id, seed
        _write_test_wave(output_path)
        return music_generation_service.GenerationResult(
            audio_path=str(output_path),
            generation_time_ms=420,
            sample_rate=32000,
            duration_seconds=1.0,
        )

    monkeypatch.setattr(music_generation_service.music_engine, "generate_audio", fake_generate_audio)

    payload = {
        "prompt": "A calm cinematic night piano",
        "title": "Night Piano",
        "mood": "Calm",
        "style": "Cinematic",
        "energy": "Low",
        "instrumentation": "Piano and soft strings",
        "duration_seconds": 8,
    }
    created = client.post("/music/generate", json=payload)
    assert created.status_code == 200
    created_payload = created.json()
    assert created_payload["status"] == "generating"

    final_payload = _wait_for_generation_done(created_payload["id"])
    assert final_payload["status"] == "completed"
    assert final_payload["audio_url"]

    history = client.get("/music/generations")
    assert history.status_code == 200
    items = history.json()
    assert len(items) >= 1

    fetched = client.get(f"/music/generations/{created_payload['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created_payload["id"]

    audio_resp = client.get(f"/music/audio/{created_payload['id']}")
    assert audio_resp.status_code == 200
    assert audio_resp.headers["content-type"].startswith("audio/wav")

    waveform_resp = client.get(f"/music/generations/{created_payload['id']}/waveform?points=64")
    assert waveform_resp.status_code == 200
    waveform = waveform_resp.json()
    assert waveform["generation_id"] == created_payload["id"]
    assert waveform["points"] == 64
    assert len(waveform["peaks"]) == 64


def test_music_variation(monkeypatch) -> None:
    output_path = Path("workspace/test_music_variation.wav").resolve()

    def fake_generate_audio(*, composed_prompt: str, duration_seconds: int, generation_id: int, seed: int | None = None):
        del composed_prompt, duration_seconds, generation_id, seed
        _write_test_wave(output_path)
        return music_generation_service.GenerationResult(
            audio_path=str(output_path),
            generation_time_ms=520,
            sample_rate=32000,
            duration_seconds=1.0,
        )

    monkeypatch.setattr(music_generation_service.music_engine, "generate_audio", fake_generate_audio)

    base_payload = {
        "prompt": "Dreamy ambient texture for sunrise",
        "title": "Sunrise",
        "mood": "Dreamy",
        "style": "Ambient",
        "energy": "Low",
        "instrumentation": "Pads and soft plucks",
        "duration_seconds": 8,
    }
    base = client.post("/music/generate", json=base_payload)
    assert base.status_code == 200
    base_id = base.json()["id"]
    base_done = _wait_for_generation_done(base_id)
    assert base_done["status"] == "completed"

    variation = client.post(
        f"/music/generations/{base_id}/variation",
        json={"title": "Sunrise V2", "energy": "Medium", "duration_seconds": 8},
    )
    assert variation.status_code == 200
    variation_payload = variation.json()
    assert variation_payload["parent_generation_id"] == base_id
    assert variation_payload["status"] == "generating"

    variation_done = _wait_for_generation_done(variation_payload["id"])
    assert variation_done["status"] == "completed"

