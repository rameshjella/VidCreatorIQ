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

type TabKey = "launch" | "project" | "jobs" | "timeline" | "system";

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function statusClass(ready: boolean): string {
  return ready ? "ok" : "bad";
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
  const [activeTab, setActiveTab] = useState<TabKey>("launch");

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
      const [deps, doctorPayload] = await Promise.all([api.dependencies(apiBase), api.dependencyDoctor(apiBase)]);
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
    const [jobPayload, eventsPayload] = await Promise.all([api.getJob(apiBase, jobId), api.getJobEvents(apiBase, jobId)]);
    setJob(jobPayload);
    setJobEvents(eventsPayload);
  }

  async function refreshAll() {
    await Promise.all([refreshHealth(), refreshDependencies(), refreshProject(), refreshJob()]);
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
      void refreshAll();
    }, refreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, refreshSeconds, apiBase, projectId, jobId]);

  const canRunMovie = useMemo(() => {
    if (!dependencies) {
      return false;
    }
    return mode === "basic" ? dependencies.ready_for_generation : dependencies.ready_for_cinematic;
  }, [dependencies, mode]);

  const progressPercent = job ? Math.max(0, Math.min(100, Math.round(job.progress * 100))) : 0;
  const blockingIssues = doctor?.findings.filter((item) => item.severity === "error").length ?? 0;

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
      setMessage(`Project #${payload.id} created successfully.`);
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

  return (
    <div className="app">
      <header className="hero card">
        <div>
          <div className="eyebrow">VidCreatorIQ</div>
          <h1>AI Movie Maker Studio</h1>
          <p className="subhead">A modern production console for script-to-cinematic video generation.</p>
        </div>
        <div className="heroActions">
          <button className="ghost" disabled={busy} onClick={() => setAutoRefresh((old) => !old)}>
            {autoRefresh ? "Pause Auto Refresh" : "Resume Auto Refresh"}
          </button>
          <button className="primary" disabled={busy} onClick={() => void refreshAll()}>
            Refresh Workspace
          </button>
        </div>
      </header>

      <nav className="tabBar card">
        <button className={activeTab === "launch" ? "tab selected" : "tab"} onClick={() => setActiveTab("launch")}>
          Launchpad
        </button>
        <button className={activeTab === "project" ? "tab selected" : "tab"} onClick={() => setActiveTab("project")}>
          Project
        </button>
        <button className={activeTab === "jobs" ? "tab selected" : "tab"} onClick={() => setActiveTab("jobs")}>
          Jobs
        </button>
        <button className={activeTab === "timeline" ? "tab selected" : "tab"} onClick={() => setActiveTab("timeline")}>
          Timeline
        </button>
        <button className={activeTab === "system" ? "tab selected" : "tab"} onClick={() => setActiveTab("system")}>
          System
        </button>
      </nav>

      <section className="kpis">
        <article className="kpi card">
          <div className="kpiLabel">API Status</div>
          <div className={`kpiValue ${apiOnline ? "success" : "error"}`}>{apiOnline ? "Online" : "Offline"}</div>
          <div className="help">Base: {apiBase}</div>
        </article>
        <article className="kpi card">
          <div className="kpiLabel">Cinematic Readiness</div>
          <div className={`kpiValue ${dependencies?.ready_for_cinematic ? "success" : "error"}`}>
            {dependencies?.ready_for_cinematic ? "Ready" : "Blocked"}
          </div>
          <div className="help">Checkpoints: {doctor?.comfyui_checkpoints.checkpoint_count ?? 0}</div>
        </article>
        <article className="kpi card">
          <div className="kpiLabel">Active Job</div>
          <div className="kpiValue">{jobId ?? "-"}</div>
          <div className="help">Project: {projectId ?? "-"}</div>
        </article>
      </section>

      {activeTab === "launch" && (
        <section className="grid two">
          <article className="card launchPanel">
            <h3>Launch Page</h3>
            <p className="subhead">Run a movie in minutes: configure system, create project, start generation, then monitor results.</p>
            <div className="checklist">
              <div className="checkItem">1. Verify API, FFmpeg, and ComfyUI readiness in System tab.</div>
              <div className="checkItem">2. Create or paste your script in Project tab.</div>
              <div className="checkItem">3. Start generation and monitor logs in Jobs tab.</div>
              <div className="checkItem">4. Fine-tune scene order and duration in Timeline tab.</div>
            </div>
            <div className="row">
              <button className="primary" onClick={() => setActiveTab("project")}>Open Project Workspace</button>
              <button className="ghost" onClick={() => setActiveTab("system")}>Open System Doctor</button>
            </div>
          </article>
          <article className="card launchPanel">
            <h3>Readiness Snapshot</h3>
            <div className="pillRow">
              <span className={`pill ${apiOnline ? "ok" : "bad"}`}>API {apiOnline ? "Online" : "Offline"}</span>
              <span className={`pill ${statusClass(Boolean(dependencies?.ready_for_generation))}`}>
                Generation {dependencies?.ready_for_generation ? "Ready" : "Blocked"}
              </span>
              <span className={`pill ${statusClass(Boolean(dependencies?.ready_for_cinematic))}`}>
                Cinematic {dependencies?.ready_for_cinematic ? "Ready" : "Blocked"}
              </span>
            </div>
            <div className="launchStats">
              <div><strong>Blocking issues:</strong> {blockingIssues}</div>
              <div><strong>Checkpoint count:</strong> {doctor?.comfyui_checkpoints.checkpoint_count ?? 0}</div>
              <div><strong>Current project:</strong> {projectId ?? "none"}</div>
              <div><strong>Current job:</strong> {jobId ?? "none"}</div>
            </div>
            <div className="row">
              <button className="primary" disabled={!canRunMovie || !projectId || busy} onClick={() => void runMovie()}>
                Quick Start Movie Run
              </button>
            </div>
          </article>
          <article className="card fullSpan">
            <h3>Recent Live Events</h3>
            <div className="logBox">
              {jobEvents.length === 0 && <div>No job events yet.</div>}
              {jobEvents.slice(-12).map((event) => (
                <div key={event.id}>
                  [{event.created_at}] [{event.stage}] {event.message}
                </div>
              ))}
            </div>
          </article>
        </section>
      )}

      {activeTab === "project" && (
        <section className="card">
          <h3>Project Workspace</h3>
          <label>Project title</label>
          <input value={title} onChange={(event) => setTitle(event.target.value)} />

          <label>Script</label>
          <textarea
            placeholder="Paste screenplay or narrative script here..."
            value={scriptText}
            onChange={(event) => setScriptText(event.target.value)}
          />

          <label>Visual mode</label>
          <div className="modeToggle">
            <button className={mode === "basic" ? "selected" : ""} type="button" onClick={() => setMode("basic")}>
              Basic
            </button>
            <button className={mode === "cinematic" ? "selected" : ""} type="button" onClick={() => setMode("cinematic")}>
              Cinematic
            </button>
          </div>

          <div className="row">
            <button className="primary" disabled={busy} onClick={() => void createProject()}>
              Create Project
            </button>
            <button className="primary" disabled={!canRunMovie || busy} onClick={() => void runMovie()}>
              Generate Movie
            </button>
          </div>
        </section>
      )}

      {activeTab === "jobs" && (
        <section className="card">
          <h3>Job Timeline</h3>
          {job ? (
            <>
              <div className="help">
                Status: <strong>{job.status}</strong> | Stage: <strong>{job.stage}</strong> | Scenes: {job.processed_scenes}/{job.total_scenes} | Attempts: {job.attempts}
              </div>
              <div className="progressWrap">
                <div className="progressBar" style={{ width: `${progressPercent}%` }} />
              </div>
              <div className="help">{progressPercent}% - {job.message}</div>
            </>
          ) : (
            <div className="help">No job selected yet.</div>
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
            <div className="alignBottom">
              <button className="ghost" disabled={!jobId || busy} onClick={() => void resumeJob()}>
                Resume Job
              </button>
            </div>
          </div>

          <div className="logBox">
            {jobEvents.length === 0 && <div>No events yet.</div>}
            {jobEvents.slice(-30).map((event) => (
              <div key={event.id}>
                [{event.created_at}] [{event.stage}] {event.message}
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "timeline" && (
        <section className="card">
          <h3>Scene Timeline Editor</h3>
          {!project && <div className="help">Create or load a project to edit scenes.</div>}
          {project && timelineDraft.length === 0 && <div className="help">Scenes will appear after first generation run.</div>}
          {project && timelineDraft.map((scene, index) => (
            <div className="sceneRow" key={scene.scene_id}>
              <div className="sceneTitle">{scene.title}</div>
              <div className="help">Scene ID: {scene.scene_id}</div>
              <div className="row">
                <div>
                  <label>Order</label>
                  <input
                    type="number"
                    min={1}
                    value={scene.scene_index}
                    onChange={(event) => {
                      const next = [...timelineDraft];
                      next[index] = {
                        ...next[index],
                        scene_index: Math.max(1, Number(event.target.value || 1)),
                      };
                      setTimelineDraft(next);
                    }}
                  />
                </div>
                <div>
                  <label>Duration (seconds)</label>
                  <input
                    type="number"
                    min={0.1}
                    step={0.1}
                    value={scene.duration_seconds}
                    onChange={(event) => {
                      const next = [...timelineDraft];
                      next[index] = {
                        ...next[index],
                        duration_seconds: Math.max(0.1, Number(event.target.value || 0.1)),
                      };
                      setTimelineDraft(next);
                    }}
                  />
                </div>
                <div className="alignBottom">
                  <button className="ghost" disabled={busy} onClick={() => void regenerateScene(scene.scene_id)}>
                    Regenerate Scene
                  </button>
                </div>
              </div>
            </div>
          ))}
          {project && timelineDraft.length > 0 && (
            <div className="actionsRight">
              <button className="primary" disabled={busy} onClick={() => void saveTimeline()}>
                Save Timeline
              </button>
              <a className="downloadLink" href={`${apiBase}/projects/${project.id}/download`} target="_blank" rel="noreferrer">
                Download Final MP4
              </a>
            </div>
          )}
        </section>
      )}

      {activeTab === "system" && (
        <>
          <section className="card">
            <h3>Connection and Runtime</h3>
            <div className="grid two">
              <div>
                <label>API Base URL</label>
                <input value={apiBase} onChange={(event) => setApiBase(event.target.value)} />
              </div>
              <div>
                <label>Refresh Interval (seconds)</label>
                <input
                  type="number"
                  min={2}
                  max={30}
                  value={refreshSeconds}
                  onChange={(event) => setRefreshSeconds(Math.max(2, Number(event.target.value || 4)))}
                />
              </div>
            </div>
          </section>

          <section className="card">
            <h3>Dependency Doctor</h3>
            {dependencyError && <p className="error">{dependencyError}</p>}
            {dependencies && (
              <div className="pillRow">
                <span className={`pill ${statusClass(dependencies.dependencies.ffmpeg.ready)}`}>
                  ffmpeg: {dependencies.dependencies.ffmpeg.detail}
                </span>
                <span className={`pill ${statusClass(dependencies.dependencies.comfyui.ready)}`}>
                  comfyui: {dependencies.dependencies.comfyui.detail}
                </span>
                <span className={`pill ${statusClass(dependencies.dependencies.piper.ready)}`}>
                  piper: {dependencies.dependencies.piper.detail}
                </span>
              </div>
            )}
            {doctor?.comfyui_checkpoints && (
              <div className="help">
                Checkpoint endpoint: {doctor.comfyui_checkpoints.endpoint || "not configured"}
                <br />
                Checkpoint count: {doctor.comfyui_checkpoints.checkpoint_count} | Samples: {doctor.comfyui_checkpoints.sample_checkpoint_names.join(", ") || "(none)"}
              </div>
            )}
          </section>
        </>
      )}

      {message && <div className="toast">{message}</div>}
    </div>
  );
}

