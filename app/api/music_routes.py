from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.database import get_db
from app.queue import cancel_queued_job, enqueue_music_generation
from app.schemas import (
    MusicGenerateRequest,
    MusicGenerationOut,
    MusicWarmupOut,
    MusicVariationRequest,
    MusicWaveformOut,
)
from app.services.music_generation_service import music_engine
from app.services.music_prompt_service import compose_music_prompt

router = APIRouter(prefix="/music", tags=["music"])


def _to_generation_out(record) -> MusicGenerationOut:
    audio_url = f"/music/audio/{record.id}" if record.audio_path else None
    generation_label = "Original" if not record.parent_generation_id else f"Variation of #{record.parent_generation_id}"
    payload = MusicGenerationOut.model_validate(record)
    payload.audio_url = audio_url
    payload.generation_label = generation_label
    return payload


@router.get("/health")
def music_health() -> dict:
    supported = music_engine.supported_durations()
    return {
        "status": "ok",
        "music_engine": {
            "model": music_engine.model_id,
            "device": music_engine.device,
            "model_loaded": music_engine.loaded,
            "supported_durations": supported,
            "default_duration": settings.music_default_duration_seconds,
            "max_duration": max(supported) if supported else settings.music_max_duration_seconds,
        },
    }


@router.post("/warmup", response_model=MusicWarmupOut)
def music_warmup() -> MusicWarmupOut:
    payload = music_engine.warmup()
    return MusicWarmupOut(status="ok", **payload)


@router.get("/models")
def music_models() -> dict:
    return {
        "status": "ok",
        "models": [
            {
                "id": music_engine.model_id,
                "provider": "Hugging Face Transformers",
                "device": music_engine.device,
                "supports_local_inference": True,
                "supports_variation": True,
                "supported_durations": music_engine.supported_durations(),
            }
        ],
    }


@router.post("/generate", response_model=MusicGenerationOut)
def generate_music(payload: MusicGenerateRequest, db: Session = Depends(get_db)):
    supported = music_engine.supported_durations()
    if payload.duration_seconds not in supported:
        raise HTTPException(status_code=400, detail=f"duration_seconds must be one of {supported}")

    composed_prompt = compose_music_prompt(
        payload.prompt,
        mood=payload.mood,
        style=payload.style,
        energy=payload.energy,
        instrumentation=payload.instrumentation,
    )

    record = crud.create_music_generation(
        db,
        title=payload.title.strip() or "Untitled Track",
        user_prompt=payload.prompt,
        composed_prompt=composed_prompt,
        model=music_engine.model_id,
        mood=payload.mood,
        style=payload.style,
        energy=payload.energy,
        instrumentation=payload.instrumentation,
        duration_seconds=payload.duration_seconds,
        parent_generation_id=None,
    )

    record_id: int = int(getattr(record, "id"))
    queue_job_id = enqueue_music_generation(record_id, payload.seed)
    if not queue_job_id:
        crud.mark_music_generation_failed(
            db,
            record,
            "Queue unavailable. Configure REDIS_URL and run worker to enable music generation.",
        )
        raise HTTPException(
            status_code=503,
            detail="Music queue unavailable. Configure REDIS_URL and run `python run_ai_movie_maker.py --with-worker`.",
        )
    record = crud.update_music_generation_queue_id(db, record, queue_job_id)
    return _to_generation_out(record)


@router.get("/generations", response_model=list[MusicGenerationOut])
def list_music_generations(db: Session = Depends(get_db)):
    items = crud.list_music_generations(db)
    return [_to_generation_out(item) for item in items]


@router.get("/generations/{generation_id}", response_model=MusicGenerationOut)
def get_music_generation(generation_id: int, db: Session = Depends(get_db)):
    record = crud.get_music_generation(db, generation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Generation not found")
    return _to_generation_out(record)


@router.post("/generations/{generation_id}/variation", response_model=MusicGenerationOut)
def create_variation(
    generation_id: int,
    payload: MusicVariationRequest,
    db: Session = Depends(get_db),
):
    base = crud.get_music_generation(db, generation_id)
    if not base:
        raise HTTPException(status_code=404, detail="Base generation not found")

    base_id: int = int(getattr(base, "id"))
    base_prompt: str = str(base.user_prompt)
    base_duration: int = int(getattr(base, "duration_seconds"))
    duration = payload.duration_seconds if payload.duration_seconds is not None else base_duration
    supported = music_engine.supported_durations()
    if duration not in supported:
        raise HTTPException(status_code=400, detail=f"duration_seconds must be one of {supported}")

    base_mood: str = str(base.mood)
    base_style: str = str(base.style)
    base_energy: str = str(base.energy)
    base_instrumentation: str = str(base.instrumentation)

    mood: str = payload.mood if payload.mood is not None else base_mood
    style: str = payload.style if payload.style is not None else base_style
    energy: str = payload.energy if payload.energy is not None else base_energy
    instrumentation: str = payload.instrumentation if payload.instrumentation is not None else base_instrumentation
    prompt: str = base_prompt

    composed_prompt = compose_music_prompt(
        prompt,
        mood=mood,
        style=style,
        energy=energy,
        instrumentation=instrumentation,
    )

    base_title = str(base.title)

    record = crud.create_music_generation(
        db,
        title=payload.title or f"Variation of {base_title}",
        user_prompt=prompt,
        composed_prompt=composed_prompt,
        model=music_engine.model_id,
        mood=mood,
        style=style,
        energy=energy,
        instrumentation=instrumentation,
        duration_seconds=duration,
        parent_generation_id=base_id,
    )

    record_id: int = int(getattr(record, "id"))
    queue_job_id = enqueue_music_generation(record_id, payload.seed)
    if not queue_job_id:
        crud.mark_music_generation_failed(
            db,
            record,
            "Queue unavailable. Configure REDIS_URL and run worker to enable variation generation.",
        )
        raise HTTPException(
            status_code=503,
            detail="Music queue unavailable. Configure REDIS_URL and run `python run_ai_movie_maker.py --with-worker`.",
        )
    record = crud.update_music_generation_queue_id(db, record, queue_job_id)
    return _to_generation_out(record)


@router.post("/generations/{generation_id}/cancel", response_model=MusicGenerationOut)
def cancel_music_generation(generation_id: int, db: Session = Depends(get_db)):
    record = crud.get_music_generation(db, generation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Generation not found")

    status = str(getattr(record, "status", ""))
    if status in {"completed", "failed", "canceled"}:
        return _to_generation_out(record)

    record = crud.request_music_generation_cancel(db, record)
    queue_job_id = str(getattr(record, "queue_job_id", ""))
    canceled = cancel_queued_job(queue_job_id)
    if canceled:
        record = crud.mark_music_generation_canceled(db, record, "Canceled by user")
    return _to_generation_out(record)


@router.post("/generations/{generation_id}/retry", response_model=MusicGenerationOut)
def retry_music_generation(generation_id: int, db: Session = Depends(get_db)):
    source = crud.get_music_generation(db, generation_id)
    if not source:
        raise HTTPException(status_code=404, detail="Generation not found")

    source_status = str(getattr(source, "status", ""))
    if source_status not in {"failed", "canceled"}:
        raise HTTPException(status_code=409, detail="Retry is available only for failed or canceled generations")

    retry_record = crud.create_music_generation(
        db,
        title=f"Retry of {str(getattr(source, 'title', 'track'))}",
        user_prompt=str(getattr(source, "user_prompt")),
        composed_prompt=str(getattr(source, "composed_prompt")),
        model=str(getattr(source, "model")),
        mood=str(getattr(source, "mood")),
        style=str(getattr(source, "style")),
        energy=str(getattr(source, "energy")),
        instrumentation=str(getattr(source, "instrumentation")),
        duration_seconds=int(getattr(source, "duration_seconds")),
        parent_generation_id=int(getattr(source, "parent_generation_id")) if getattr(source, "parent_generation_id") else None,
        retry_of_generation_id=int(getattr(source, "id")),
    )

    retry_id = int(getattr(retry_record, "id"))
    queue_job_id = enqueue_music_generation(retry_id, seed=None)
    if not queue_job_id:
        crud.mark_music_generation_failed(
            db,
            retry_record,
            "Queue unavailable. Configure REDIS_URL and run worker to enable retry.",
        )
        raise HTTPException(
            status_code=503,
            detail="Music queue unavailable. Configure REDIS_URL and run `python run_ai_movie_maker.py --with-worker`.",
        )

    retry_record = crud.update_music_generation_queue_id(db, retry_record, queue_job_id)
    return _to_generation_out(retry_record)


@router.get("/generations/{generation_id}/waveform", response_model=MusicWaveformOut)
def get_music_waveform(generation_id: int, points: int = 120, db: Session = Depends(get_db)):
    record = crud.get_music_generation(db, generation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Generation not found")
    if str(record.status) != "completed" or not record.audio_path:
        raise HTTPException(status_code=409, detail="Waveform is available only after generation completes")

    try:
        peaks, _ = music_engine.extract_waveform_peaks(str(record.audio_path), points=points)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Audio file missing on disk") from None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to derive waveform: {exc}") from None

    record_id: int = int(getattr(record, "id"))
    return MusicWaveformOut(generation_id=record_id, points=len(peaks), peaks=peaks)


@router.get("/audio/{generation_id}")
def get_music_audio(generation_id: int, db: Session = Depends(get_db)):
    record = crud.get_music_generation(db, generation_id)
    if not record or not record.audio_path:
        raise HTTPException(status_code=404, detail="Audio not found")
    path = Path(str(record.audio_path))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing on disk")
    return FileResponse(str(path), media_type="audio/wav", filename=f"music_{generation_id}.wav")

