from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    title: str = "Untitled Project"
    script_text: str = Field(min_length=20)
    language: str = "en"


class SceneOut(BaseModel):
    id: int
    scene_index: int
    title: str
    script_chunk: str
    description: str
    image_prompt: str
    image_path: str
    video_path: str
    narration_path: str
    subtitle_path: str
    duration_seconds: float

    model_config = {"from_attributes": True}


class ProjectOut(BaseModel):
    id: int
    title: str
    script_text: str
    language: str
    status: str
    created_at: datetime
    updated_at: datetime
    scenes: list[SceneOut] = []

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: int
    project_id: int
    status: str
    stage: str
    message: str
    progress: float
    attempts: int
    processed_scenes: int
    total_scenes: int
    queue_job_id: str
    last_error: str
    output_video_path: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RegenerateSceneRequest(BaseModel):
    scene_id: int


class ResumeJobRequest(BaseModel):
    failed_scene_index: int = Field(ge=1)


class SceneTimelineEdit(BaseModel):
    scene_id: int
    scene_index: int = Field(ge=1)
    duration_seconds: float = Field(gt=0)


class SceneTimelineUpdateRequest(BaseModel):
    scenes: list[SceneTimelineEdit]


class MovieRunResponse(BaseModel):
    job_id: int
    project_id: int
    status: str


class RunProjectRequest(BaseModel):
    visual_mode: str = "basic"


class JobEventOut(BaseModel):
    id: int
    job_id: int
    stage: str
    level: str
    message: str
    progress: float
    created_at: datetime

    model_config = {"from_attributes": True}


class MusicGenerateRequest(BaseModel):
    prompt: str = Field(min_length=3)
    title: str = "Untitled Track"
    mood: str = "Emotional"
    style: str = "Cinematic"
    energy: str = "Medium"
    instrumentation: str = "Piano and strings"
    duration_seconds: int = Field(default=8, ge=1, le=60)
    seed: int | None = None


class MusicVariationRequest(BaseModel):
    title: str | None = None
    mood: str | None = None
    style: str | None = None
    energy: str | None = None
    instrumentation: str | None = None
    duration_seconds: int | None = Field(default=None, ge=1, le=60)
    seed: int | None = None


class MusicGenerationOut(BaseModel):
    id: int
    title: str
    status: str
    user_prompt: str
    composed_prompt: str
    model: str
    mood: str
    style: str
    energy: str
    instrumentation: str
    duration_seconds: int
    generation_time_ms: int
    sample_rate: int
    created_at: datetime
    parent_generation_id: int | None
    error_message: str
    audio_url: str | None = None
    generation_label: str | None = None

    model_config = {"from_attributes": True}


