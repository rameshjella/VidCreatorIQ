import type {
  DependenciesResponse,
  DependencyDoctorResponse,
  HealthResponse,
  JobEventOut,
  JobOut,
  MusicEngineHealth,
  MusicGenerationOut,
  MusicModelsResponse,
  MusicWaveformOut,
  MovieRunResponse,
  ProjectOut,
  SceneOut,
} from "./types";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  health: (baseUrl: string) => requestJson<HealthResponse>(`${baseUrl}/health`),
  dependencies: (baseUrl: string) => requestJson<DependenciesResponse>(`${baseUrl}/health/dependencies`),
  dependencyDoctor: (baseUrl: string) =>
    requestJson<DependencyDoctorResponse>(`${baseUrl}/health/dependency-doctor`),
  createProject: (baseUrl: string, payload: { title: string; script_text: string; language: string }) =>
    requestJson<ProjectOut>(`${baseUrl}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getProject: (baseUrl: string, projectId: number) => requestJson<ProjectOut>(`${baseUrl}/projects/${projectId}`),
  runProject: (baseUrl: string, projectId: number, visualMode: "basic" | "cinematic") =>
    requestJson<MovieRunResponse>(`${baseUrl}/projects/${projectId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ visual_mode: visualMode }),
    }),
  getJob: (baseUrl: string, jobId: number) => requestJson<JobOut>(`${baseUrl}/jobs/${jobId}`),
  getJobEvents: (baseUrl: string, jobId: number) => requestJson<JobEventOut[]>(`${baseUrl}/jobs/${jobId}/events`),
  resumeJob: (baseUrl: string, jobId: number, failedSceneIndex: number) =>
    requestJson<MovieRunResponse>(`${baseUrl}/jobs/${jobId}/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ failed_scene_index: failedSceneIndex }),
    }),
  updateTimeline: (
    baseUrl: string,
    projectId: number,
    scenes: Array<{ scene_id: number; scene_index: number; duration_seconds: number }>,
  ) =>
    requestJson<SceneOut[]>(`${baseUrl}/projects/${projectId}/scenes`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenes }),
    }),
  regenerateScene: (baseUrl: string, projectId: number, sceneId: number) =>
    requestJson<SceneOut>(`${baseUrl}/projects/${projectId}/scenes/regenerate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scene_id: sceneId }),
    }),
  musicHealth: (baseUrl: string) => requestJson<MusicEngineHealth>(`${baseUrl}/music/health`),
  musicWarmup: (baseUrl: string) => requestJson(`${baseUrl}/music/warmup`, { method: "POST" }),
  musicModels: (baseUrl: string) => requestJson<MusicModelsResponse>(`${baseUrl}/music/models`),
  musicGenerate: (
    baseUrl: string,
    payload: {
      prompt: string;
      title: string;
      mood: string;
      style: string;
      energy: string;
      instrumentation: string;
      duration_seconds: number;
      seed?: number;
    },
  ) =>
    requestJson<MusicGenerationOut>(`${baseUrl}/music/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listMusicGenerations: (baseUrl: string) => requestJson<MusicGenerationOut[]>(`${baseUrl}/music/generations`),
  getMusicGeneration: (baseUrl: string, generationId: number) =>
    requestJson<MusicGenerationOut>(`${baseUrl}/music/generations/${generationId}`),
  createMusicVariation: (
    baseUrl: string,
    generationId: number,
    payload: {
      title?: string;
      mood?: string;
      style?: string;
      energy?: string;
      instrumentation?: string;
      duration_seconds?: number;
      seed?: number;
    },
  ) =>
    requestJson<MusicGenerationOut>(`${baseUrl}/music/generations/${generationId}/variation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getMusicWaveform: (baseUrl: string, generationId: number, points = 140) =>
    requestJson<MusicWaveformOut>(`${baseUrl}/music/generations/${generationId}/waveform?points=${points}`),
};

