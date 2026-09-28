import { useEffect, useMemo, useState } from "react";

import { api } from "./api";
import type { DependenciesResponse, DependencyDoctorResponse, JobEventOut, JobOut, ProjectOut } from "./types";

const defaultBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

type SceneDraft = {
  scene_id: number;
  scene_index: number;
  duration_seconds: number;
  title: string;
};

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

export default function App() {
  const [apiBase, setApiBase] = useState(defaultBaseUrl);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);

  const [dependencies, setDependencies] = useState<DependenciesResponse | null>(null);
  const [doctor, setDoctor] = useState<DependencyDoctorResponse | null>(null);
  const [dependencyError, setDependencyError] = useState("");

  const [title, setTitle] = useState("My AI Movie");
  const [scriptText, setScriptText] = useState("");
  const [mode, setMode] = useState<"basic" | "cinematic">("basic");

  const [projectId, setProjectId] = useState<number | null>(null);
  const [project, setProject] = useState<ProjectOut | null>(null);
  const [timelineDraft, setTimelineDraft] = useState<SceneDraft[]>([]);

  const [jobId, setJobId] = useState<number | null>(null);
  const [job, setJob] = useState<JobOut | null>(null);
  const [jobEvents, setJobEvents] = useState<JobEventOut[]>([]);

  const [resumeSceneIndex, setResumeSceneIndex] = useState(1);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshSeconds, setRefreshSeconds] = useState(4);

  async function refreshHealth() {
    try {
      await api.health(apiBase);
      setApiOnline(true);
    } catch {
      setApiOnline(false);
    }
  }

  async function refreshDependencies() {
    try {
      const [deps, doctorPayload] = await Promise.all([
        api.dependencies(apiBase),
        api.dependencyDoctor(apiBase),
      ]);
      setDependencies(deps);
      setDoctor(doctorPayload);
      setDependencyError("");
    } catch (error) {
      setDependencyError(toErrorMessage(error));
    }
  }

  async function refreshProject() {
    if (!projectId) {
      return;
    }
    const payload = await api.getProject(apiBase, projectId);
    setProject(payload);
    setTimelineDraft(
      payload.scenes.map((scene) => ({
        scene_id: scene.id,
        scene_index: scene.scene_index,
        duration_seconds: scene.duration_seconds,
        title: scene.title,
      })),
    );
  }

  async function refreshJob() {
    if (!jobId) {
      return;
    }
    const [jobPayload, eventsPayload] = await Promise.all([
      api.getJob(apiBase, jobId),
      api.getJobEvents(apiBase, jobId),
    ]);
    setJob(jobPayload);
    setJobEvents(eventsPayload);
  }

  useEffect(() => {
    void refreshHealth();
    void refreshDependencies();
  }, [apiBase]);

  useEffect(() => {
    if (!autoRefresh) {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshHealth();
      void refreshDependencies();
      void refreshProject();
      void refreshJob();
    }, refreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, refreshSeconds, apiBase, projectId, jobId]);

  const canRunMovie = useMemo(() => {
    if (!dependencies) {
      return false;
    }
    if (mode === "basic") {
      return dependencies.ready_for_generation;
    }
    return dependencies.ready_for_cinematic;
  }, [dependencies, mode]);

  async function createProject() {
    const text = scriptText.trim();
    if (text.length < 20) {
      setMessage("Script must be at least 20 characters.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const payload = await api.createProject(apiBase, {
        title: title.trim() || "My AI Movie",
        script_text: text,
        language: "en",
      });
      setProjectId(payload.id);
      setProject(payload);
      setMessage(`Project #${payload.id} created.`);
    } catch (error) {
      setMessage(toErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function runMovie() {
    if (!projectId) {
      setMessage("Create a project first.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const payload = await api.runProject(apiBase, projectId, mode);
      setJobId(payload.job_id);
      setMessage(`Job #${payload.job_id} queued.`);
      await refreshJob();
    } catch (error) {
      setMessage(toErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function resumeJob() {
    if (!jobId) {
      setMessage("No job selected.");
      return;
    }
    setBusy(true);
    try {
      await api.resumeJob(apiBase, jobId, resumeSceneIndex);
      setMessage("Resume requested.");
      await refreshJob();
    } catch (error) {
      setMessage(toErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function saveTimeline() {
    if (!projectId) {
      return;
    }
    setBusy(true);
    try {
      await api.updateTimeline(
        apiBase,
        projectId,
        timelineDraft.map((scene) => ({
          scene_id: scene.scene_id,
          scene_index: scene.scene_index,
          duration_seconds: scene.duration_seconds,
        })),
      );
      setMessage("Timeline updated.");
      await refreshProject();
    } catch (error) {
      setMessage(toErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function regenerateScene(sceneId: number) {
    if (!projectId) {
      return;
    }
    setBusy(true);
    try {
      await api.regenerateScene(apiBase, projectId, sceneId);
      setMessage(`Scene ${sceneId} regenerated.`);
      await refreshProject();
    } catch (error) {
      setMessage(toErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  const progressPercent = job ? Math.max(0, Math.min(100, Math.round(job.progress * 100))) : 0;

  return (
    <div className="app">
      <h1>AI Movie Maker</h1>
      <p className="help">React + FastAPI UI replacing Streamlit.</p>

      <div className="card">
        <h3>Connection</h3>
        <div className="row">
          <div>
            <label>API Base URL</label>
            <input value={apiBase} onChange={(event) => setApiBase(event.target.value)} />
          </div>
          <div>
            <label>Auto Refresh (sec)</label>
            <input
              type="number"
              value={refreshSeconds}
              min={2}
              max={20}
              onChange={(event) => setRefreshSeconds(Math.max(2, Number(event.target.value || 4)))}
            />
          </div>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <button onClick={() => setAutoRefresh((old) => !old)}>{autoRefresh ? "Pause Refresh" : "Resume Refresh"}</button>
          <button onClick={() => { void refreshHealth(); void refreshDependencies(); void refreshProject(); void refreshJob(); }}>
            Refresh Now
          </button>
        </div>
        <p className={apiOnline ? "success" : "error"}>API: {apiOnline ? "reachable" : "unreachable"}</p>
      </div>

      <div className="card">
        <h3>Dependency Doctor</h3>
        {dependencyError && <p className="error">{dependencyError}</p>}
        {dependencies && (
          <>
            <span className={`pill ${dependencies.dependencies.ffmpeg.ready ? "ok" : "bad"}`}>
              ffmpeg: {dependencies.dependencies.ffmpeg.detail}
            </span>
            <span className={`pill ${dependencies.dependencies.comfyui.ready ? "ok" : "bad"}`}>
              comfyui: {dependencies.dependencies.comfyui.detail}
            </span>
            <span className={`pill ${dependencies.dependencies.piper.ready ? "ok" : "bad"}`}>
              piper: {dependencies.dependencies.piper.detail}
            </span>
            <p className="help">
              Cinematic readiness: {String(dependencies.ready_for_cinematic)} | Generation readiness: {String(dependencies.ready_for_generation)}
            </p>
          </>
        )}
        {doctor?.comfyui_checkpoints && (
          <p className="help">
            Checkpoints: {doctor.comfyui_checkpoints.checkpoint_count} | Sample: {doctor.comfyui_checkpoints.sample_checkpoint_names.join(", ") || "(none)"}
          </p>
        )}
      </div>

      <div className="grid two">
        <div className="card">
          <h3>1) Script and Project</h3>
          <label>Project title</label>
          <input value={title} onChange={(event) => setTitle(event.target.value)} />

          <label style={{ marginTop: 8 }}>Script text</label>
          <textarea value={scriptText} onChange={(event) => setScriptText(event.target.value)} />

          <label style={{ marginTop: 8 }}>Visual mode</label>
          <select value={mode} onChange={(event) => setMode(event.target.value as "basic" | "cinematic") }>
            <option value="basic">Basic</option>
            <option value="cinematic">Cinematic</option>
          </select>

          <div className="row" style={{ marginTop: 10 }}>
            <button onClick={() => void createProject()} disabled={busy}>Create Project</button>
            <button onClick={() => void runMovie()} disabled={!canRunMovie || busy}>Generate Movie</button>
          </div>
        </div>

        <div className="card">
          <h3>2) Job Timeline</h3>
          <p className="help">Project: {projectId ?? "-"} | Job: {jobId ?? "-"}</p>
          {job ? (
            <>
              <p>
                Status: {job.status} | Stage: {job.stage} | Scenes: {job.processed_scenes}/{job.total_scenes} | Attempts: {job.attempts}
              </p>
              <progress value={progressPercent} max={100} style={{ width: "100%" }} />
              <p>{progressPercent}% - {job.message}</p>
            </>
          ) : (
            <p className="help">No job selected.</p>
          )}

          <div className="row">
            <div>
              <label>Resume from scene index</label>
              <input
                type="number"
                min={1}
                value={resumeSceneIndex}
                onChange={(event) => setResumeSceneIndex(Math.max(1, Number(event.target.value || 1)))}
              />
            </div>
            <div style={{ display: "flex", alignItems: "end" }}>
              <button onClick={() => void resumeJob()} disabled={!jobId || busy}>Resume Job</button>
            </div>
          </div>

          <div className="logBox">
            {jobEvents.slice(-30).map((event) => (
              <div key={event.id}>
                [{event.created_at}] [{event.stage}] {event.message}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h3>3) Scene Timeline Editor</h3>
        {!project && <p className="help">Create or load a project to edit scenes.</p>}
        {project && timelineDraft.map((scene, idx) => (
          <div className="sceneRow" key={scene.scene_id}>
            <p>
              <strong>{scene.title}</strong> (Scene #{scene.scene_id})
            </p>
            <div className="row">
              <div>
                <label>Order</label>
                <input
                  type="number"
                  min={1}
                  value={scene.scene_index}
                  onChange={(event) => {
                    const next = [...timelineDraft];
                    next[idx] = {
                      ...next[idx],
                      scene_index: Math.max(1, Number(event.target.value || 1)),
                    };
                    setTimelineDraft(next);
                  }}
                />
              </div>
              <div>
                <label>Duration (s)</label>
                <input
                  type="number"
                  min={0.1}
                  step={0.1}
                  value={scene.duration_seconds}
                  onChange={(event) => {
                    const next = [...timelineDraft];
                    next[idx] = {
                      ...next[idx],
                      duration_seconds: Math.max(0.1, Number(event.target.value || 0.1)),
                    };
                    setTimelineDraft(next);
                  }}
                />
              </div>
              <div style={{ display: "flex", alignItems: "end" }}>
                <button onClick={() => void regenerateScene(scene.scene_id)} disabled={busy}>Regenerate Scene</button>
              </div>
            </div>
          </div>
        ))}
        {project && (
          <div style={{ marginTop: 12 }}>
            <button onClick={() => void saveTimeline()} disabled={busy}>Save Timeline</button>
            <p className="help">Download: {apiBase}/projects/{project.id}/download</p>
          </div>
        )}
      </div>

      {message && <p>{message}</p>}
    </div>
  );
}

