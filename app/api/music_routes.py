from __future__ import annotations

from pathlib import Path
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.database import get_db
from app.schemas import (
    MusicGenerateRequest,
    MusicGenerationOut,
    MusicVariationRequest,
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
            "supported_durations": supported,
            "default_duration": settings.music_default_duration_seconds,
            "max_duration": max(supported) if supported else settings.music_max_duration_seconds,
        },
    }


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

    try:
        result = music_engine.generate_audio(
            composed_prompt=composed_prompt,
            duration_seconds=payload.duration_seconds,
            generation_id=record.id,
            seed=payload.seed,
        )
        valid, _, detail = music_engine.validate_audio_file(result.audio_path)
        if not valid:
            raise RuntimeError(detail)
        record = crud.mark_music_generation_completed(
            db,
            record,
            audio_path=result.audio_path,
            generation_time_ms=result.generation_time_ms,
            sample_rate=result.sample_rate,
        )
        return _to_generation_out(record)
    except Exception as exc:
        crud.mark_music_generation_failed(db, record, str(exc))
        raise HTTPException(status_code=500, detail=f"We couldn't generate this track. {exc}") from None


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
def create_variation(generation_id: int, payload: MusicVariationRequest, db: Session = Depends(get_db)):
    base = crud.get_music_generation(db, generation_id)
    if not base:
        raise HTTPException(status_code=404, detail="Base generation not found")

    base_id = int(base.id)
    base_prompt: str = str(base.user_prompt)
    duration = payload.duration_seconds if payload.duration_seconds is not None else int(base.duration_seconds)
    supported = music_engine.supported_durations()
    if duration not in supported:
        raise HTTPException(status_code=400, detail=f"duration_seconds must be one of {supported}")

    base_mood: str = str(base.mood)
    base_style: str = str(base.style)
    base_energy: str = str(base.energy)
    base_instrumentation: str = str(base.instrumentation)

    mood: str = cast(str, payload.mood) if payload.mood is not None else base_mood
    style: str = cast(str, payload.style) if payload.style is not None else base_style
    energy: str = cast(str, payload.energy) if payload.energy is not None else base_energy
    instrumentation: str = cast(str, payload.instrumentation) if payload.instrumentation is not None else base_instrumentation
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

    try:
        result = music_engine.generate_audio(
            composed_prompt=composed_prompt,
            duration_seconds=duration,
            generation_id=record.id,
            seed=payload.seed,
        )
        valid, _, detail = music_engine.validate_audio_file(result.audio_path)
        if not valid:
            raise RuntimeError(detail)
        record = crud.mark_music_generation_completed(
            db,
            record,
            audio_path=result.audio_path,
            generation_time_ms=result.generation_time_ms,
            sample_rate=result.sample_rate,
        )
        return _to_generation_out(record)
    except Exception as exc:
        crud.mark_music_generation_failed(db, record, str(exc))
        raise HTTPException(status_code=500, detail=f"Variation generation failed. {exc}") from None


@router.get("/audio/{generation_id}")
def get_music_audio(generation_id: int, db: Session = Depends(get_db)):
    record = crud.get_music_generation(db, generation_id)
    if not record or not record.audio_path:
        raise HTTPException(status_code=404, detail="Audio not found")
    path = Path(str(record.audio_path))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing on disk")
    return FileResponse(str(path), media_type="audio/wav", filename=f"music_{generation_id}.wav")

