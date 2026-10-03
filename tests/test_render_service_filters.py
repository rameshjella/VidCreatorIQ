from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import app.services.render_service as render_module


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

