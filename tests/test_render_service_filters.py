from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import json
import pytest

import app.services.render_service as render_module
from app.services.ffmpeg_runner import FFmpegError


def _capture_filter_complex(monkeypatch, tmp_path: Path) -> tuple[render_module.RenderService, dict]:
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(render_module.ff, "ffmpeg_bin", lambda: "ffmpeg")
    monkeypatch.setattr(render_module.ff, "run", lambda cmd: captured.setdefault("cmd", cmd))
    monkeypatch.setattr(
        render_module.ff,
        "validate_output",
        lambda *args, **kwargs: SimpleNamespace(duration=1.0, width=1920, height=1080),
    )

    return render_module.RenderService(tmp_path), captured


def test_mux_narration_only_filtergraph_has_no_empty_filter(monkeypatch, tmp_path: Path) -> None:
    service, captured = _capture_filter_complex(monkeypatch, tmp_path)

    service.mux(
        video_path=tmp_path / "movie_silent.mp4",
        audio_path=tmp_path / "movie.wav",
        subtitle_path=None,
    )

    cmd = captured["cmd"]
    filtergraph = cmd[cmd.index("-filter_complex") + 1]
    assert "[narr],loudnorm" not in filtergraph
    assert "[narr]loudnorm" in filtergraph


def test_mux_without_subtitles_narration_only_filtergraph_has_no_empty_filter(monkeypatch, tmp_path: Path) -> None:
    service, captured = _capture_filter_complex(monkeypatch, tmp_path)

    service.mux_without_subtitles(
        video_path=tmp_path / "movie_silent.mp4",
        audio_path=tmp_path / "movie.wav",
    )

    cmd = captured["cmd"]
    filtergraph = cmd[cmd.index("-filter_complex") + 1]
    assert "[narr],loudnorm" not in filtergraph
    assert "[narr]loudnorm" in filtergraph


def test_generate_clip_with_comfyui_rejects_non_temporal_workflow(monkeypatch, tmp_path: Path) -> None:
    workflow = {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "x", "clip": ["11", 1]}},
        "11": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "m.safetensors"}},
        "6": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["5", 0]}},
    }
    wf_path = tmp_path / "wf.json"
    wf_path.write_text(json.dumps(workflow), encoding="utf-8")

    monkeypatch.setattr(render_module.settings, "comfyui_animatediff_workflow", str(wf_path))

    service = render_module.RenderService(tmp_path)
    with pytest.raises(FFmpegError, match="no temporal motion nodes"):
        service.generate_clip_with_comfyui("prompt", scene_index=1, duration=3.0, loras=[])


