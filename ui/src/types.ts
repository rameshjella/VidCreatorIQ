export type HealthResponse = {
  status: string;
};

export type DependencyInfo = {
  ready: boolean;
  detail: string;
  /** Display name, e.g. "ComfyUI" rather than the map key "comfyui". */
  label?: string;
  /** Optional dependencies are informational; only FFmpeg blocks rendering. */
  optional?: boolean;
  /** Actionable next step shown when not ready. */
  hint?: string;
  /** Full exception text, surfaced behind a disclosure for debugging. */
  raw_error?: string;
  configured?: string;
  configured_url?: string;
  resolved_path?: string;
  checkpoint_count?: number;
  has_checkpoints?: boolean;
  checkpoint_detail?: string;
};

export type DependenciesResponse = {
  status: string;
  dependencies: {
    ffmpeg: DependencyInfo;
    comfyui: DependencyInfo;
    piper: DependencyInfo;
  };
  ready_for_generation: boolean;
  ready_for_cinematic: boolean;
};

export type ComfyCheckpointHealth = {
  configured: boolean;
  configured_url: string;
  endpoint: string;
  reachable: boolean;
  schema_recognized: boolean;
  checkpoint_count: number;
  sample_checkpoint_names: string[];
  has_checkpoints: boolean;
  detail: string;
};

export type DependencyDoctorResponse = {
  status: string;
  summary: {
    blocking_issues: boolean;
    issue_count: number;
  };
  findings: Array<{
    dependency: string;
    severity: string;
    issue: string;
    missing?: Record<string, unknown>;
    suggested_fixes?: string[];
  }>;
  comfyui_checkpoints: ComfyCheckpointHealth;
};

export type ProjectOut = {
  id: number;
  title: string;
  script_text: string;
  language: string;
  character_identity_prompt: string;
  character_lora_tags: string;
  characters: Array<{
    id: number;
    project_id: number;
    name: string;
    identity_prompt: string;
    lora_adapter: string;
    lora_strength: number;
    notes: string;
  }>;
  status: string;
  created_at: string;
  updated_at: string;
  scenes: SceneOut[];
};

export type SceneOut = {
  id: number;
  scene_index: number;
  title: string;
  script_chunk: string;
  description: string;
  image_prompt: string;
  image_path: string;
  video_path: string;
  narration_path: string;
  subtitle_path: string;
  duration_seconds: number;
};

export type MovieRunResponse = {
  job_id: number;
  project_id: number;
  status: string;
};

export type JobOut = {
  id: number;
  project_id: number;
  status: string;
  stage: string;
  message: string;
  progress: number;
  attempts: number;
  processed_scenes: number;
  total_scenes: number;
  queue_job_id: string;
  last_error: string;
  output_video_path: string;
  created_at: string;
  updated_at: string;
};

export type JobEventOut = {
  id: number;
  job_id: number;
  stage: string;
  level: string;
  message: string;
  progress: number;
  created_at: string;
};

export type MusicEngineHealth = {
  status: string;
  music_engine: {
    model: string;
    device: string;
    model_loaded: boolean;
    supported_durations: number[];
    default_duration: number;
    max_duration: number;
  };
};

export type MusicWaveformOut = {
  generation_id: number;
  points: number;
  peaks: number[];
};

export type MusicModelsResponse = {
  status: string;
  models: Array<{
    id: string;
    provider: string;
    device: string;
    supports_local_inference: boolean;
    supports_variation: boolean;
    supported_durations: number[];
  }>;
};

export type MusicGenerationOut = {
  id: number;
  title: string;
  status: "ready" | "generating" | "completed" | "failed" | string;
  user_prompt: string;
  composed_prompt: string;
  model: string;
  mood: string;
  style: string;
  energy: string;
  instrumentation: string;
  duration_seconds: number;
  generation_time_ms: number;
  sample_rate: number;
  created_at: string;
  parent_generation_id: number | null;
  error_message: string;
  audio_url: string | null;
  generation_label: string | null;
};

// --- Voice Studio -----------------------------------------------------------
export interface TTSProvider {
  id: string;
  name: string;
  configured: boolean;
  quality_rank: number;
  requires_key: boolean;
}

export interface TTSProvidersResponse {
  providers: TTSProvider[];
  active: string;
  fallback_chain: string[];
  defaults: {
    speaking_rate: number;
    pitch: number;
    mp3_bitrate: string;
    sample_rate: number;
  };
}

export interface TTSVoice {
  id: string;
  name: string;
  locale: string;
  gender: string;
  provider: string;
  preview_url: string;
}

export interface TTSVoicesResponse {
  provider: string;
  voices: TTSVoice[];
}

// --- Render artifacts -------------------------------------------------------
export interface SceneArtifact {
  id: number;
  scene_index: number;
  title: string;
  script_chunk?: string;
  duration_seconds: number;
  tts_provider: string;
  tts_voice: string;
  image_url: string;
  video_url: string;
  narration_url: string;
  subtitle_url: string;
}

export interface JobArtifacts {
  job_id: number;
  project_id: number;
  status: string;
  progress: number;
  video_url: string;
  audio_url: string;
  music_url: string;
  sfx_url: string;
  subtitle_url: string;
  captions_vtt_url: string;
  poster_url: string;
  stems_manifest_url: string;
  stems_zip_url: string;
  duration_seconds: number;
  scenes: SceneArtifact[];
}
