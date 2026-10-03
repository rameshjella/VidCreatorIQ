import type {
  DependenciesResponse,
  DependencyDoctorResponse,
  HealthResponse,
  JobArtifacts,
  JobEventOut,
  JobOut,
  MusicEngineHealth,
  MusicGenerationOut,
  MusicModelsResponse,
  MusicWaveformOut,
  MovieRunResponse,
  ProjectOut,
  SceneOut,
  TTSProvidersResponse,
  TTSVoicesResponse,
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
  createProject: (
    baseUrl: string,
    payload: {
      title: string;
      script_text: string;
      language: string;
      character_identity_prompt?: string;
      character_lora_tags?: string[];
    },
  ) =>
    requestJson<ProjectOut>(`${baseUrl}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listProjects: (baseUrl: string) => requestJson<ProjectOut[]>(`${baseUrl}/projects`),
  getProject: (baseUrl: string, projectId: number) => requestJson<ProjectOut>(`${baseUrl}/projects/${projectId}`),
  runProject: (
    baseUrl: string,
    projectId: number,
    visualMode: "basic" | "cinematic",
    options?: {
      cinematic_quality_profile?: "fast" | "balanced" | "true_motion";
      music_generation_id?: number | null;
      export_stems?: boolean;
    },
  ) =>
    requestJson<MovieRunResponse>(`${baseUrl}/projects/${projectId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        visual_mode: visualMode,
        cinematic_quality_profile: options?.cinematic_quality_profile ?? "balanced",
        music_generation_id: options?.music_generation_id ?? null,
        export_stems: options?.export_stems ?? true,
      }),
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
  listCharacters: (baseUrl: string, projectId: number) =>
    requestJson<
      Array<{
        id: number;
        project_id: number;
        name: string;
        identity_prompt: string;
        lora_adapter: string;
        lora_strength: number;
        notes: string;
      }>
    >(`${baseUrl}/projects/${projectId}/characters`),
  createCharacter: (
    baseUrl: string,
    projectId: number,
    payload: {
      name: string;
      identity_prompt?: string;
      lora_adapter?: string;
      lora_strength?: number;
      notes?: string;
    },
  ) =>
    requestJson(`${baseUrl}/projects/${projectId}/characters`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateSceneCharacters: (
    baseUrl: string,
    projectId: number,
    sceneId: number,
    assignments: Array<{ character_id: number; role?: string; weight?: number }>,
  ) =>
    requestJson(`${baseUrl}/projects/${projectId}/scenes/${sceneId}/characters`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assignments }),
    }),

  // --- Voice Studio -------------------------------------------------------
  ttsProviders: (baseUrl: string) => requestJson<TTSProvidersResponse>(`${baseUrl}/tts/providers`),
  ttsVoices: (baseUrl: string, provider: string) =>
    requestJson<TTSVoicesResponse>(`${baseUrl}/tts/voices?provider=${encodeURIComponent(provider)}`),
  ttsPreviewUrl: async (
    baseUrl: string,
    payload: { text: string; provider: string | null; voice: string },
  ): Promise<string> => {
    const response = await fetch(`${baseUrl}/tts/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error((await response.text()) || "Voice preview failed");
    // Blob URL lets the <audio> element play the MP3 without a second round-trip.
    return URL.createObjectURL(await response.blob());
  },

  // --- Render artifacts ---------------------------------------------------
  jobArtifacts: (baseUrl: string, jobId: number) =>
    requestJson<JobArtifacts>(`${baseUrl}/jobs/${jobId}/artifacts`),
  projectArtifacts: (baseUrl: string, projectId: number) =>
    requestJson<JobArtifacts>(`${baseUrl}/projects/${projectId}/artifacts`),
  stemsPackageUrl: (baseUrl: string, jobId: number) => `${baseUrl}/jobs/${jobId}/stems-package`,

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
  cancelMusicGeneration: (baseUrl: string, generationId: number) =>
    requestJson<MusicGenerationOut>(`${baseUrl}/music/generations/${generationId}/cancel`, {
      method: "POST",
    }),
  retryMusicGeneration: (baseUrl: string, generationId: number) =>
    requestJson<MusicGenerationOut>(`${baseUrl}/music/generations/${generationId}/retry`, {
      method: "POST",
    }),
  getMusicWaveform: (baseUrl: string, generationId: number, points = 140) =>
    requestJson<MusicWaveformOut>(`${baseUrl}/music/generations/${generationId}/waveform?points=${points}`),
};
