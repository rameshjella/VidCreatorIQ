from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    title: str = "Untitled Project"
    script_text: str = Field(min_length=20)
    language: str = "en"
    character_identity_prompt: str = ""
    character_lora_tags: list[str] = Field(default_factory=list)


class CharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    identity_prompt: str = ""
    lora_adapter: str = ""
    lora_strength: float = Field(default=0.8, ge=0.0, le=2.0)
    notes: str = ""


class CharacterOut(BaseModel):
    id: int
    project_id: int
    name: str
    identity_prompt: str
    lora_adapter: str
    lora_strength: float
    notes: str

    model_config = {"from_attributes": True}


class SceneCharacterAssignmentIn(BaseModel):
    character_id: int
    role: str = "support"
    weight: float = Field(default=1.0, ge=0.0, le=2.0)


class SceneCharacterAssignmentOut(BaseModel):
    id: int
    scene_id: int
    character_id: int
    role: str
    weight: float

    model_config = {"from_attributes": True}


class SceneCharactersUpdateRequest(BaseModel):
    assignments: list[SceneCharacterAssignmentIn]


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
    character_assignments: list[SceneCharacterAssignmentOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ProjectOut(BaseModel):
    id: int
    title: str
    script_text: str
    language: str
    character_identity_prompt: str
    character_lora_tags: str
    status: str
    created_at: datetime
    updated_at: datetime
    scenes: list[SceneOut] = Field(default_factory=list)
    characters: list[CharacterOut] = Field(default_factory=list)

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
    output_music_path: str
    output_sfx_path: str
    output_stems_manifest_path: str
    output_stems_zip_path: str
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
    cinematic_quality_profile: Literal["fast", "balanced", "true_motion"] = "balanced"
    output_resolution: Literal["720p", "1080p", "1440p", "4k", "vertical_1080p"] = "1080p"
    output_fps: Literal[24, 30, 60] = 30
    burn_subtitles: bool | None = None
    music_generation_id: int | None = None
    export_stems: bool = True


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


class MusicWarmupOut(BaseModel):
    status: str
    model: str
    device: str
    load_time_ms: int
    ready: bool


class MusicWaveformOut(BaseModel):
    generation_id: int
    points: int
    peaks: list[float]


