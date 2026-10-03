from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models


def create_project(
    db: Session,
    title: str,
    script_text: str,
    language: str,
    character_identity_prompt: str = "",
    character_lora_tags: str = "",
) -> models.Project:
    project = models.Project(
        title=title,
        script_text=script_text,
        language=language,
        character_identity_prompt=character_identity_prompt,
        character_lora_tags=character_lora_tags,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project(db: Session, project_id: int) -> models.Project | None:
    stmt = (
        select(models.Project)
        .where(models.Project.id == project_id)
        .options(
            selectinload(models.Project.scenes).selectinload(models.Scene.character_assignments),
            selectinload(models.Project.characters),
        )
    )
    return db.scalar(stmt)


def list_projects(db: Session) -> list[models.Project]:
    stmt = (
        select(models.Project)
        .order_by(models.Project.created_at.desc())
        .options(
            selectinload(models.Project.scenes).selectinload(models.Scene.character_assignments),
            selectinload(models.Project.characters),
        )
    )
    return list(db.scalars(stmt).all())


def list_project_characters(db: Session, project_id: int) -> list[models.CharacterProfile]:
    stmt = (
        select(models.CharacterProfile)
        .where(models.CharacterProfile.project_id == project_id)
        .order_by(models.CharacterProfile.id.asc())
    )
    return list(db.scalars(stmt).all())


def create_project_character(
    db: Session,
    project_id: int,
    *,
    name: str,
    identity_prompt: str = "",
    lora_adapter: str = "",
    lora_strength: float = 0.8,
    notes: str = "",
) -> models.CharacterProfile:
    character = models.CharacterProfile(
        project_id=project_id,
        name=name,
        identity_prompt=identity_prompt,
        lora_adapter=lora_adapter,
        lora_strength=lora_strength,
        notes=notes,
    )
    db.add(character)
    db.commit()
    db.refresh(character)
    return character


def set_scene_character_assignments(
    db: Session,
    scene: models.Scene,
    assignments: list[tuple[int, str, float]],
) -> list[models.SceneCharacter]:
    db.query(models.SceneCharacter).filter(models.SceneCharacter.scene_id == scene.id).delete()
    for character_id, role, weight in assignments:
        db.add(
            models.SceneCharacter(
                scene_id=scene.id,
                character_id=character_id,
                role=(role or "support")[:64],
                weight=max(0.0, min(2.0, float(weight))),
            )
        )
    db.commit()
    stmt = (
        select(models.SceneCharacter)
        .where(models.SceneCharacter.scene_id == scene.id)
        .order_by(models.SceneCharacter.id.asc())
    )
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


def create_music_generation(
    db: Session,
    *,
    title: str,
    user_prompt: str,
    composed_prompt: str,
    model: str,
    mood: str,
    style: str,
    energy: str,
    instrumentation: str,
    duration_seconds: int,
    parent_generation_id: int | None = None,
    retry_of_generation_id: int | None = None,
) -> models.MusicGeneration:
    record = models.MusicGeneration(
        title=title,
        user_prompt=user_prompt,
        composed_prompt=composed_prompt,
        model=model,
        mood=mood,
        style=style,
        energy=energy,
        instrumentation=instrumentation,
        duration_seconds=duration_seconds,
        status="generating",
        parent_generation_id=parent_generation_id,
        retry_of_generation_id=retry_of_generation_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_music_generation(db: Session, generation_id: int) -> models.MusicGeneration | None:
    stmt = select(models.MusicGeneration).where(models.MusicGeneration.id == generation_id)
    return db.scalar(stmt)


def list_music_generations(db: Session, limit: int = 50) -> list[models.MusicGeneration]:
    stmt = select(models.MusicGeneration).order_by(models.MusicGeneration.created_at.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def mark_music_generation_completed(
    db: Session,
    record: models.MusicGeneration,
    *,
    audio_path: str,
    generation_time_ms: int,
    sample_rate: int,
) -> models.MusicGeneration:
    record.status = "completed"
    record.audio_path = audio_path
    record.generation_time_ms = generation_time_ms
    record.sample_rate = sample_rate
    record.error_message = ""
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def mark_music_generation_failed(db: Session, record: models.MusicGeneration, error_message: str) -> models.MusicGeneration:
    record.status = "failed"
    record.error_message = error_message[:1000]
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_music_generation_queue_id(db: Session, record: models.MusicGeneration, queue_job_id: str) -> models.MusicGeneration:
    record.queue_job_id = queue_job_id
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def request_music_generation_cancel(db: Session, record: models.MusicGeneration) -> models.MusicGeneration:
    record.cancel_requested = 1
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def mark_music_generation_canceled(db: Session, record: models.MusicGeneration, reason: str = "Canceled by user") -> models.MusicGeneration:
    record.status = "canceled"
    record.error_message = reason[:1000]
    record.cancel_requested = 1
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


