from __future__ import annotations

from app import crud
from app.database import SessionLocal
from app.services.music_generation_service import music_engine
from app.services.pipeline import MoviePipeline


def run_pipeline_job(
    project_id: int,
    job_id: int,
    resume_from_scene_index: int | None = None,
    visual_mode: str = "basic",
    music_path: str | None = None,
    export_stems: bool = True,
) -> None:
    db = SessionLocal()
    pipeline = MoviePipeline(db)
    try:
        project = crud.get_project(db, project_id)
        job = crud.get_job(db, job_id)
        if not project or not job:
            return
        pipeline.run(
            project,
            job,
            resume=True,
            resume_from_scene_index=resume_from_scene_index,
            visual_mode=visual_mode,
            music_path=music_path,
            export_stems=export_stems,
        )
    except Exception as exc:
        job = crud.get_job(db, job_id)
        if job:
            pipeline.mark_failure(job, exc)
    finally:
        db.close()


def run_music_generation_job(generation_id: int, seed: int | None = None) -> None:
    db = SessionLocal()
    try:
        record = crud.get_music_generation(db, generation_id)
        if not record:
            return
        if int(getattr(record, "cancel_requested", 0)) == 1:
            crud.mark_music_generation_canceled(db, record, "Canceled before generation started")
            return

        try:
            result = music_engine.generate_audio(
                composed_prompt=str(getattr(record, "composed_prompt")),
                duration_seconds=int(getattr(record, "duration_seconds")),
                generation_id=int(getattr(record, "id")),
                seed=seed,
            )

            refreshed = crud.get_music_generation(db, generation_id)
            if refreshed and int(getattr(refreshed, "cancel_requested", 0)) == 1:
                crud.mark_music_generation_canceled(db, refreshed, "Canceled during generation")
                return

            valid, _, detail = music_engine.validate_audio_file(result.audio_path)
            if not valid:
                raise RuntimeError(detail)

            target = refreshed or record
            crud.mark_music_generation_completed(
                db,
                target,
                audio_path=result.audio_path,
                generation_time_ms=result.generation_time_ms,
                sample_rate=result.sample_rate,
            )
        except Exception as exc:
            latest = crud.get_music_generation(db, generation_id) or record
            if int(getattr(latest, "cancel_requested", 0)) == 1:
                crud.mark_music_generation_canceled(db, latest, "Canceled")
            else:
                crud.mark_music_generation_failed(db, latest, str(exc))
    finally:
        db.close()


