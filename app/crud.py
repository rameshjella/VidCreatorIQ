from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models


def create_project(db: Session, title: str, script_text: str, language: str) -> models.Project:
    project = models.Project(title=title, script_text=script_text, language=language)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project(db: Session, project_id: int) -> models.Project | None:
    stmt = select(models.Project).where(models.Project.id == project_id).options(selectinload(models.Project.scenes))
    return db.scalar(stmt)


def list_projects(db: Session) -> list[models.Project]:
    stmt = select(models.Project).order_by(models.Project.created_at.desc()).options(selectinload(models.Project.scenes))
    return list(db.scalars(stmt).all())


def create_job(db: Session, project_id: int) -> models.Job:
    job = models.Job(project_id=project_id)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: int) -> models.Job | None:
    stmt = select(models.Job).where(models.Job.id == job_id)
    return db.scalar(stmt)


def update_job_queue_id(db: Session, job: models.Job, queue_job_id: str) -> models.Job:
    job.queue_job_id = queue_job_id
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def create_job_event(
    db: Session,
    job_id: int,
    stage: str,
    level: str,
    message: str,
    progress: float,
) -> models.JobEvent:
    event = models.JobEvent(
        job_id=job_id,
        stage=stage,
        level=level,
        message=message,
        progress=progress,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_job_events(db: Session, job_id: int) -> list[models.JobEvent]:
    stmt = select(models.JobEvent).where(models.JobEvent.job_id == job_id).order_by(models.JobEvent.created_at.asc())
    return list(db.scalars(stmt).all())


def update_scene_timeline(
    db: Session,
    project_id: int,
    scene_updates: list[tuple[int, int, float]],
) -> list[models.Scene]:
    scenes = list(db.scalars(select(models.Scene).where(models.Scene.project_id == project_id)).all())
    by_id = {scene.id: scene for scene in scenes}
    for scene_id, scene_index, duration_seconds in scene_updates:
        scene = by_id.get(scene_id)
        if not scene:
            continue
        scene.scene_index = scene_index
        scene.duration_seconds = duration_seconds
        db.add(scene)
    db.commit()

    stmt = (
        select(models.Scene)
        .where(models.Scene.project_id == project_id)
        .order_by(models.Scene.scene_index.asc(), models.Scene.id.asc())
    )
    return list(db.scalars(stmt).all())


