"""Centralised FFmpeg / FFprobe execution and media inspection.

Every render operation in the project funnels through here so that binary
resolution, error reporting and output validation behave consistently.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from shutil import which

from app.config import settings


class FFmpegError(RuntimeError):
    """Raised when an ffmpeg/ffprobe invocation fails or yields invalid media."""


def _resolve_binary(configured: str, fallback_names: list[str]) -> str:
    candidate = (configured or "").strip()
    if candidate:
        if Path(candidate).exists():
            return candidate
        resolved = which(candidate)
        if resolved:
            return resolved

    for name in fallback_names:
        resolved = which(name)
        if resolved:
            return resolved

    # Last resort: imageio-ffmpeg ships a static build.
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # pragma: no cover - optional dependency
        pass

    raise FFmpegError(
        f"Could not locate '{configured or fallback_names[0]}'. Install FFmpeg and add it to PATH, "
        "or set FFMPEG_BIN / FFPROBE_BIN to the full executable path in .env."
    )


def ffmpeg_bin() -> str:
    return _resolve_binary(settings.ffmpeg_bin, ["ffmpeg"])


def ffprobe_bin() -> str:
    configured = (settings.ffprobe_bin or "").strip()
    if not configured or configured == "ffprobe":
        # Derive ffprobe from a fully-qualified ffmpeg path when possible.
        ff = Path(ffmpeg_bin())
        sibling = ff.with_name("ffprobe" + ff.suffix)
        if sibling.exists():
            return str(sibling)
    return _resolve_binary(configured, ["ffprobe"])


@dataclass
class MediaInfo:
    path: Path
    duration: float
    has_video: bool
    has_audio: bool
    width: int = 0
    height: int = 0

    @property
    def is_playable(self) -> bool:
        return self.duration > 0.05 and (self.has_video or self.has_audio)


def run(cmd: list[str], *, timeout: int = 3600) -> str:
    """Run an ffmpeg command, raising a readable error on failure."""
    try:
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise FFmpegError(f"FFmpeg binary not found while running: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"FFmpeg timed out after {timeout}s: {' '.join(cmd[:6])} ...") from exc
    except subprocess.CalledProcessError as exc:
        stderr_tail = (exc.stderr or "").strip()[-1200:]
        raise FFmpegError(f"FFmpeg failed (exit {exc.returncode}).\nCommand: {' '.join(cmd)}\n{stderr_tail}") from exc
    return completed.stderr or ""


def probe(path: Path) -> MediaInfo:
    """Inspect a media file and report duration plus stream presence."""
    path = Path(path)
    if not path.exists():
        raise FFmpegError(f"Media file does not exist: {path}")
    if path.stat().st_size == 0:
        raise FFmpegError(f"Media file is empty (0 bytes): {path}")

    cmd = [
        ffprobe_bin(),
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        completed = subprocess.run(
            cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
        )
        data = json.loads(completed.stdout or "{}")
    except subprocess.CalledProcessError as exc:
        raise FFmpegError(f"ffprobe could not read '{path.name}': {(exc.stderr or '').strip()[-500:]}") from exc
    except json.JSONDecodeError as exc:
        raise FFmpegError(f"ffprobe returned malformed JSON for '{path.name}'") from exc

    streams = data.get("streams") or []
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    duration = 0.0
    try:
        duration = float((data.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        for stream in streams:
            try:
                duration = max(duration, float(stream.get("duration") or 0.0))
            except (TypeError, ValueError):
                continue

    first_video = video_streams[0] if video_streams else {}
    return MediaInfo(
        path=path,
        duration=duration,
        has_video=bool(video_streams),
        has_audio=bool(audio_streams),
        width=int(first_video.get("width") or 0),
        height=int(first_video.get("height") or 0),
    )


def probe_duration(path: Path) -> float:
    """Return the duration of a media file in seconds."""
    return probe(path).duration


def validate_output(path: Path, *, expect_video: bool = True, expect_audio: bool = False) -> MediaInfo:
    """Assert that a freshly rendered file is actually playable."""
    info = probe(path)
    problems: list[str] = []
    if info.duration <= 0.05:
        problems.append("duration is zero")
    if expect_video and not info.has_video:
        problems.append("no video stream")
    if expect_audio and not info.has_audio:
        problems.append("no audio stream")
    if problems:
        raise FFmpegError(f"Rendered file '{path.name}' is invalid: {', '.join(problems)}")
    return info

