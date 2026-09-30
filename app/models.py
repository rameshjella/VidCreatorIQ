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
    status: Mapped[str] = mapped_column(String(32), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    scenes: Mapped[list["Scene"]] = relationship(back_populates="project", cascade="all, delete-orphan")
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

    project: Mapped["Project"] = relationship(back_populates="scenes")


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


