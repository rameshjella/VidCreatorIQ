from __future__ import annotations

from app import crud
from app.database import SessionLocal
from app.services.pipeline import MoviePipeline


def run_pipeline_job(
    project_id: int,
    job_id: int,
    resume_from_scene_index: int | None = None,
    visual_mode: str = "basic",
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
        )
    except Exception as exc:
        job = crud.get_job(db, job_id)
        if job:
            pipeline.mark_failure(job, exc)
    finally:
        db.close()

