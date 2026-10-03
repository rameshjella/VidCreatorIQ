"""Translate on-disk render artifacts into browser-reachable URLs."""

from __future__ import annotations

from pathlib import Path

from app.config import settings


def to_public_url(path: str | Path | None) -> str:
    """Map a workspace path to a URL served by the ``/static`` mount.

    Returns an empty string for missing files so the UI can simply check for
    truthiness instead of handling nulls everywhere.
    """
    if not path:
        return ""

    candidate = Path(path)
    if not candidate.exists():
        return ""

    workspace = Path(settings.workspace_dir).resolve()
    try:
        relative = candidate.resolve().relative_to(workspace)
    except ValueError:
        # Artifact lives outside the workspace and cannot be served safely.
        return ""

    base = settings.public_asset_base_url.rstrip("/")
    return f"{base}/workspace/{relative.as_posix()}"


def scene_artifacts(scene) -> dict:
    return {
        "image_url": to_public_url(scene.image_path),
        "video_url": to_public_url(scene.video_path),
        "narration_url": to_public_url(scene.narration_path),
        "subtitle_url": to_public_url(scene.subtitle_path),
    }


def job_artifacts(job) -> dict:
    subtitle_path = Path(job.output_subtitle_path) if job.output_subtitle_path else None
    vtt_path = subtitle_path.with_suffix(".vtt") if subtitle_path else None

    return {
        "video_url": to_public_url(job.output_video_path),
        "audio_url": to_public_url(job.output_audio_path),
        "music_url": to_public_url(job.output_music_path),
        "sfx_url": to_public_url(job.output_sfx_path),
        "subtitle_url": to_public_url(job.output_subtitle_path),
        "captions_vtt_url": to_public_url(vtt_path),
        "poster_url": to_public_url(job.output_poster_path),
        "stems_manifest_url": to_public_url(job.output_stems_manifest_path),
        "stems_zip_url": to_public_url(job.output_stems_zip_path),
        "duration_seconds": float(job.output_duration_seconds or 0.0),
    }

