"""Voice Studio endpoints: provider discovery, voice lists and previews."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Job, Scene
from app.services.artifact_service import job_artifacts, scene_artifacts
from app.services.narration_service import TTSService
from app.services.tts.registry import available_providers, list_voices

router = APIRouter()


class TTSPreviewRequest(BaseModel):
    text: str = Field(default="", max_length=600)
    provider: str | None = None
    voice: str = ""


@router.get("/tts/providers")
def get_providers() -> dict:
    """List every provider plus whether it is usable with the current .env."""
    providers = available_providers()
    return {
        "providers": providers,
        "active": settings.tts_provider,
        "fallback_chain": [p.strip() for p in settings.tts_fallback_chain.split(",") if p.strip()],
        "defaults": {
            "speaking_rate": settings.tts_speaking_rate,
            "pitch": settings.tts_pitch,
            "mp3_bitrate": settings.tts_mp3_bitrate,
            "sample_rate": settings.tts_sample_rate,
        },
    }


@router.get("/tts/voices")
def get_voices(provider: str = "") -> dict:
    name = provider or settings.tts_provider
    voices = list_voices(name)
    return {
        "provider": name,
        "voices": [
            {
                "id": v.id,
                "name": v.name,
                "locale": v.locale,
                "gender": v.gender,
                "provider": v.provider,
                "preview_url": v.preview_url,
            }
            for v in voices
        ],
    }


@router.post("/tts/preview")
def preview_voice(payload: TTSPreviewRequest) -> FileResponse:
    preview_dir = Path(settings.workspace_dir) / "previews"
    service = TTSService(preview_dir, provider=payload.provider, voice=payload.voice)
    try:
        path = service.preview(payload.text, provider=payload.provider, voice=payload.voice)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return FileResponse(path, media_type="audio/mpeg", filename="voice-preview.mp3")


@router.get("/jobs/{job_id}/artifacts")
def get_job_artifacts(job_id: int, db: Session = Depends(get_db)) -> dict:
    """Everything the player page needs: video, audio, captions, poster, scenes."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _artifacts_payload(job, db)


@router.get("/projects/{project_id}/artifacts")
def get_project_artifacts(project_id: int, db: Session = Depends(get_db)) -> dict:
    """Artifacts for a project's most recent render.

    Lets the UI reopen an older project's storyboard and finished movie without
    the caller having to know which job produced it.
    """
    job = (
        db.query(Job)
        .filter(Job.project_id == project_id, Job.output_video_path != "")
        .order_by(Job.updated_at.desc())
        .first()
    )
    if not job:
        # Fall back to the newest job of any status so a part-rendered project
        # still shows whatever scenes it managed to produce.
        job = (
            db.query(Job)
            .filter(Job.project_id == project_id)
            .order_by(Job.updated_at.desc())
            .first()
        )
    if not job:
        raise HTTPException(status_code=404, detail="No renders found for this project")
    return _artifacts_payload(job, db)


@router.get("/jobs/{job_id}/stems-package")
def download_stems_package(job_id: int, db: Session = Depends(get_db)) -> FileResponse:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    zip_path = Path(job.output_stems_zip_path or "") if job.output_stems_zip_path else None
    if zip_path and zip_path.exists():
        return FileResponse(str(zip_path), media_type="application/zip", filename=f"project_{job.project_id}_stems.zip")

    manifest = Path(job.output_stems_manifest_path or "") if job.output_stems_manifest_path else None
    if not manifest or not manifest.exists():
        raise HTTPException(status_code=404, detail="No stems package available for this job")

    stems_dir = manifest.parent
    zip_path = stems_dir / "stems_package.zip"
    with ZipFile(zip_path, mode="w", compression=ZIP_DEFLATED) as bundle:
        for file in stems_dir.iterdir():
            if file.is_file() and file.suffix.lower() in {".wav", ".json"}:
                bundle.write(file, arcname=f"stems/{file.name}")
    return FileResponse(str(zip_path), media_type="application/zip", filename=f"project_{job.project_id}_stems.zip")


def _artifacts_payload(job: Job, db: Session) -> dict:
    scenes = (
        db.query(Scene)
        .filter(Scene.project_id == job.project_id)
        .order_by(Scene.scene_index)
        .all()
    )

    return {
        "job_id": job.id,
        "project_id": job.project_id,
        "status": job.status,
        "progress": job.progress,
        **job_artifacts(job),
        "scenes": [
            {
                "id": s.id,
                "scene_index": s.scene_index,
                "title": s.title,
                "script_chunk": s.script_chunk,
                "duration_seconds": s.audio_duration_seconds or s.duration_seconds,
                "tts_provider": s.tts_provider,
                "tts_voice": s.tts_voice,
                **scene_artifacts(s),
            }
            for s in scenes
        ],
    }

