export type HealthResponse = {
  status: string;
};

export type DependencyInfo = {
  ready: boolean;
  detail: string;
  configured?: string;
  configured_url?: string;
  resolved_path?: string;
  checkpoint_count?: number;
  has_checkpoints?: boolean;
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

