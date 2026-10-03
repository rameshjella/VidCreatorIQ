from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="Untitled Project")
    script_text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16), default="en")
    # Global prompt fragment appended to every scene image prompt.
    character_identity_prompt: Mapped[str] = mapped_column(Text, default="")
    # Comma-separated LoRA adapter tags, e.g. "hero_face_v1:0.8,wardrobe_v2:0.6".
    character_lora_tags: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    scenes: Mapped[list["Scene"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    characters: Mapped[list["CharacterProfile"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    scene_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255), default="Scene")
    script_chunk: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    image_prompt: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str] = mapped_column(String(512), default="")
    video_path: Mapped[str] = mapped_column(String(512), default="")
    narration_path: Mapped[str] = mapped_column(String(512), default="")
    subtitle_path: Mapped[str] = mapped_column(String(512), default="")
    duration_seconds: Mapped[float] = mapped_column(Float, default=6.0)
    # Measured from the rendered narration, not estimated by the LLM. This is
    # the value the video stage uses so audio and picture stay in sync.
    audio_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    tts_provider: Mapped[str] = mapped_column(String(64), default="")
    tts_voice: Mapped[str] = mapped_column(String(128), default="")

    project: Mapped["Project"] = relationship(back_populates="scenes")
    character_assignments: Mapped[list["SceneCharacter"]] = relationship(
        back_populates="scene", cascade="all, delete-orphan"
    )


class CharacterProfile(Base):
    __tablename__ = "character_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="Character")
    identity_prompt: Mapped[str] = mapped_column(Text, default="")
    lora_adapter: Mapped[str] = mapped_column(String(255), default="")
    lora_strength: Mapped[float] = mapped_column(Float, default=0.8)
    notes: Mapped[str] = mapped_column(Text, default="")

    project: Mapped["Project"] = relationship(back_populates="characters")
    scene_assignments: Mapped[list["SceneCharacter"]] = relationship(
        back_populates="character", cascade="all, delete-orphan"
    )


class SceneCharacter(Base):
    __tablename__ = "scene_characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), index=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("character_profiles.id"), index=True)
    role: Mapped[str] = mapped_column(String(64), default="support")
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    scene: Mapped["Scene"] = relationship(back_populates="character_assignments")
    character: Mapped["CharacterProfile"] = relationship(back_populates="scene_assignments")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    message: Mapped[str] = mapped_column(Text, default="")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    processed_scenes: Mapped[int] = mapped_column(Integer, default=0)
    total_scenes: Mapped[int] = mapped_column(Integer, default=0)
    queue_job_id: Mapped[str] = mapped_column(String(128), default="")
    last_error: Mapped[str] = mapped_column(Text, default="")
    output_video_path: Mapped[str] = mapped_column(String(512), default="")
    output_audio_path: Mapped[str] = mapped_column(String(512), default="")
    output_music_path: Mapped[str] = mapped_column(String(512), default="")
    output_sfx_path: Mapped[str] = mapped_column(String(512), default="")
    output_subtitle_path: Mapped[str] = mapped_column(String(512), default="")
    output_stems_manifest_path: Mapped[str] = mapped_column(String(512), default="")
    output_stems_zip_path: Mapped[str] = mapped_column(String(512), default="")
    output_poster_path: Mapped[str] = mapped_column(String(512), default="")
    output_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped[Project] = relationship(back_populates="jobs")


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    stage: Mapped[str] = mapped_column(String(64), default="info")
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text, default="")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MusicGeneration(Base):
    __tablename__ = "music_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="Untitled Track")
    user_prompt: Mapped[str] = mapped_column(Text)
    composed_prompt: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(255), default="")
    mood: Mapped[str] = mapped_column(String(64), default="")
    style: Mapped[str] = mapped_column(String(64), default="")
    energy: Mapped[str] = mapped_column(String(32), default="")
    instrumentation: Mapped[str] = mapped_column(String(255), default="")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=8)
    status: Mapped[str] = mapped_column(String(32), default="ready")
    audio_path: Mapped[str] = mapped_column(String(512), default="")
    generation_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    sample_rate: Mapped[int] = mapped_column(Integer, default=32000)
    parent_generation_id: Mapped[int | None] = mapped_column(ForeignKey("music_generations.id"), nullable=True)
    retry_of_generation_id: Mapped[int | None] = mapped_column(ForeignKey("music_generations.id"), nullable=True)
    queue_job_id: Mapped[str] = mapped_column(String(128), default="")
    cancel_requested: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


