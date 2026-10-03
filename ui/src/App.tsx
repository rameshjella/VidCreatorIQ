import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api";
import MusicStudio from "./MusicStudio";
import { useTheme, type Theme } from "./theme";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  Field,
  Progress,
  Segmented,
  Skeleton,
  Stat,
  ToastProvider,
  formatDuration,
  useToast,
} from "./components/ui";
import type {
  DependenciesResponse,
  DependencyInfo,
  JobArtifacts,
  JobEventOut,
  JobOut,
  ProjectOut,
  TTSProvidersResponse,
  TTSVoice,
} from "./types";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || "http://127.0.0.1:8000";

type View = "studio" | "storyboard" | "voice" | "render" | "preview" | "music" | "system";

const NAV: Array<{ id: View; label: string; icon: string; group: string }> = [
  { id: "studio", label: "Script Studio", icon: "\u270E", group: "Create" },
  { id: "storyboard", label: "Storyboard", icon: "\u25A6", group: "Create" },
  { id: "voice", label: "Voice Studio", icon: "\u25C9", group: "Create" },
  { id: "music", label: "Music Studio", icon: "\u266A", group: "Create" },
  { id: "render", label: "Render Console", icon: "\u25B6", group: "Produce" },
  { id: "preview", label: "Preview & Export", icon: "\u25C8", group: "Produce" },
  { id: "system", label: "System Health", icon: "\u2699", group: "Settings" },
];

const RENDER_STAGES = [
  { id: "director", label: "Analysing script" },
  { id: "narrator", label: "Voicing narration" },
  { id: "storyboard", label: "Generating visuals" },
  { id: "videographer", label: "Rendering clips" },
  { id: "editor", label: "Assembling & mastering" },
  { id: "done", label: "Movie ready" },
];

const SAMPLE_SCRIPT = `The lighthouse had stood for a hundred years, and it had never once gone dark.

Tonight the storm came in fast, swallowing the horizon whole. Rain moved sideways across the cliffs.

Far below, a single fishing boat fought the swell, its engine straining against water that wanted it gone.

Then the beam swung around, steady and patient and certain, and cut a road of light straight through the dark.

The boat turned toward it. And the lighthouse, as always, kept burning.`;

/* ========================================================================== */
/* Shell                                                                      */
/* ========================================================================== */

function Shell() {
  const toast = useToast();
  const [theme, setTheme] = useTheme();

  const [view, setView] = useState<View>("studio");
  const [navOpen, setNavOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const [title, setTitle] = useState("The Lighthouse");
  const [script, setScript] = useState(SAMPLE_SCRIPT);
  const [language, setLanguage] = useState("en");
  const [visualMode, setVisualMode] = useState<"basic" | "cinematic">("basic");
  const [characterIdentityPrompt, setCharacterIdentityPrompt] = useState("");
  const [characterLoraTags, setCharacterLoraTags] = useState("");

  const [project, setProject] = useState<ProjectOut | null>(null);
  const [job, setJob] = useState<JobOut | null>(null);
  const [events, setEvents] = useState<JobEventOut[]>([]);
  const [artifacts, setArtifacts] = useState<JobArtifacts | null>(null);

  const [deps, setDeps] = useState<DependenciesResponse | null>(null);
  const [providers, setProviders] = useState<TTSProvidersResponse | null>(null);
  const [voices, setVoices] = useState<TTSVoice[]>([]);
  const [provider, setProvider] = useState("");
  const [voice, setVoice] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewBusy, setPreviewBusy] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const pollRef = useRef<number | null>(null);

  /* --- Bootstrap --------------------------------------------------------- */
  const refreshDeps = useCallback(() => {
    api
      .dependencies(BASE_URL)
      .then(setDeps)
      .catch(() => setDeps(null));
  }, []);

  const refreshProjects = useCallback(() => {
    api
      .listProjects(BASE_URL)
      .then((list) => setProjects(list.slice().reverse()))
      .catch(() => setProjects([]));
  }, []);

  /** Open a previously rendered project in the Storyboard / Preview views. */
  const openProject = useCallback(
    async (projectId: number) => {
      try {
        const full = await api.getProject(BASE_URL, projectId);
        setProject(full);
        setTitle(full.title);
        setScript(full.script_text);
        setCharacterIdentityPrompt(full.character_identity_prompt || "");
        setCharacterLoraTags(full.character_lora_tags || "");
        try {
          setArtifacts(await api.projectArtifacts(BASE_URL, projectId));
        } catch {
          // Project exists but was never rendered - show scenes without media.
          setArtifacts(null);
        }
      } catch (err) {
        toast("error", err instanceof Error ? err.message : "Could not open that project.");
      }
    },
    [toast],
  );

  useEffect(() => {
    refreshDeps();
    refreshProjects();
    api
      .ttsProviders(BASE_URL)
      .then((data) => {
        setProviders(data);
        const firstReady = data.providers.find((p) => p.configured);
        setProvider(data.active || firstReady?.id || "");
      })
      .catch(() => setProviders(null));
  }, [refreshDeps, refreshProjects]);

  useEffect(() => {
    if (!provider) return;
    let cancelled = false;
    api
      .ttsVoices(BASE_URL, provider)
      .then((data) => {
        if (cancelled) return;
        setVoices(data.voices);
        setVoice(data.voices[0]?.id ?? "");
      })
      .catch(() => {
        if (!cancelled) setVoices([]);
      });
    return () => {
      cancelled = true;
    };
  }, [provider]);

  /* --- Command palette (Cmd/Ctrl + K) ------------------------------------ */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
      if (e.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  /* --- Job polling ------------------------------------------------------- */
  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (jobId: number, projectId: number) => {
      stopPolling();
      pollRef.current = window.setInterval(async () => {
        try {
          const [next, log] = await Promise.all([
            api.getJob(BASE_URL, jobId),
            api.getJobEvents(BASE_URL, jobId),
          ]);
          setJob(next);
          setEvents(log);

          // Pull artifacts every tick so the storyboard fills in scene by scene
          // while the render is still running, instead of only at the end.
          api
            .jobArtifacts(BASE_URL, jobId)
            .then(setArtifacts)
            .catch(() => undefined);

          if (next.status === "completed" || next.status === "failed") {
            stopPolling();
            setBusy(false);

            if (next.status === "completed") {
              const [art, proj] = await Promise.all([
                api.jobArtifacts(BASE_URL, jobId),
                api.getProject(BASE_URL, projectId),
              ]);
              setArtifacts(art);
              setProject(proj);
              refreshProjects();
              setView("preview");
              toast("success", `Movie ready - ${formatDuration(art.duration_seconds)}`);
            } else {
              setError(next.last_error || next.message);
              toast("error", "Render failed. See the console for details.");
            }
          }
        } catch {
          /* transient network hiccup; the next tick retries */
        }
      }, 1500);
    },
    [stopPolling, toast, refreshProjects],
  );

  useEffect(() => stopPolling, [stopPolling]);

  /* --- Actions ----------------------------------------------------------- */
  const handleGenerate = useCallback(async () => {
    if (!script.trim()) {
      toast("error", "Write a script first.");
      setView("studio");
      return;
    }
    setBusy(true);
    setError("");
    setArtifacts(null);
    setEvents([]);
    setJob(null);
    setView("render");

    try {
      const created = await api.createProject(BASE_URL, {
        title: title.trim() || "Untitled Project",
        script_text: script,
        language,
        character_identity_prompt: characterIdentityPrompt,
        character_lora_tags: characterLoraTags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      });
      setProject(created);

      const run = await api.runProject(BASE_URL, created.id, visualMode);
      setJob(await api.getJob(BASE_URL, run.job_id));
      startPolling(run.job_id, created.id);
      toast("info", "Render started.");
    } catch (err) {
      setBusy(false);
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      toast("error", "Could not start the render.");
    }
  }, [
    script,
    title,
    language,
    characterIdentityPrompt,
    characterLoraTags,
    visualMode,
    startPolling,
    toast,
  ]);

  const handleSaveTimeline = useCallback(
    async (updatedScenes: Array<{ scene_id: number; scene_index: number; duration_seconds: number }>) => {
      if (!project) return;
      const updated = await api.updateTimeline(BASE_URL, project.id, updatedScenes);
      setProject((prev) => (prev ? { ...prev, scenes: updated } : prev));
      setArtifacts((prev) =>
        prev
          ? {
              ...prev,
              scenes: prev.scenes
                .map((scene) => {
                  const next = updated.find((u) => u.id === scene.id);
                  if (!next) return scene;
                  return {
                    ...scene,
                    scene_index: next.scene_index,
                    duration_seconds: next.duration_seconds,
                  };
                })
                .sort((a, b) => a.scene_index - b.scene_index),
            }
          : prev,
      );
      toast("success", "Timeline saved.");
    },
    [project, toast],
  );

  const handlePreviewVoice = useCallback(async () => {
    setPreviewBusy(true);
    try {
      const url = await api.ttsPreviewUrl(BASE_URL, {
        text: script.slice(0, 300),
        provider: provider || null,
        voice,
      });
      setPreviewUrl(url);
    } catch (err) {
      toast("error", err instanceof Error ? err.message : "Voice preview failed.");
    } finally {
      setPreviewBusy(false);
    }
  }, [script, provider, voice, toast]);

  const handleNewProject = useCallback(() => {
    stopPolling();
    setProject(null);
    setJob(null);
    setEvents([]);
    setArtifacts(null);
    setError("");
    setBusy(false);
    setTitle("Untitled Project");
    setScript("");
    setCharacterIdentityPrompt("");
    setCharacterLoraTags("");
    setView("studio");
  }, [stopPolling]);

  /* --- Derived ----------------------------------------------------------- */
  const scenes = project?.scenes ?? [];
  const wordCount = useMemo(() => script.trim().split(/\s+/).filter(Boolean).length, [script]);
  const estimatedRuntime = Math.round((wordCount / 150) * 60);
  const stageIndex = RENDER_STAGES.findIndex((s) => s.id === (job?.stage ?? ""));

  const navGroups = useMemo(() => {
    const groups = new Map<string, typeof NAV>();
    NAV.forEach((item) => groups.set(item.group, [...(groups.get(item.group) ?? []), item]));
    return [...groups.entries()];
  }, []);

  const isLocked = useCallback(
    (_id: View) =>
      // Nothing is gated any more. Every view renders a useful empty state (and
      // Storyboard/Preview can load any previous project), so disabling nav just
      // made the app feel broken before the first render finished.
      false,
    [],
  );

  const current = NAV.find((n) => n.id === view);

  return (
    <div className="app">
      <a href="#main" className="sr-only">
        Skip to content
      </a>

      <aside className="sidebar" data-open={navOpen} aria-label="Primary">
        <div className="brand">
          <div className="brand__mark" aria-hidden>
            V
          </div>
          <div>
            <div className="brand__name">VidCreatorIQ</div>
            <div className="brand__tag">AI Film Studio</div>
          </div>
        </div>

        <nav>
          {navGroups.map(([group, items]) => (
            <div key={group}>
              <div className="nav-section">{group}</div>
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="nav-item"
                  aria-current={view === item.id ? "page" : undefined}
                  disabled={isLocked(item.id)}
                  onClick={() => {
                    setView(item.id);
                    setNavOpen(false);
                  }}
                >
                  <span className="nav-item__icon" aria-hidden>
                    {item.icon}
                  </span>
                  {item.label}
                  {item.id === "storyboard" && scenes.length > 0 && (
                    <span className="nav-item__badge">{scenes.length}</span>
                  )}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar__footer">
          <div className="col" style={{ gap: 12, padding: "0 12px" }}>
            <Badge tone={deps?.ready_for_generation ? "success" : "warning"}>
              <span className="dot" aria-hidden />
              {deps?.ready_for_generation ? "Engine ready" : "Check dependencies"}
            </Badge>
            <button
              type="button"
              className="btn btn--sm btn--block"
              onClick={() => setPaletteOpen(true)}
            >
              Search <span className="kbd">{"\u2318"}K</span>
            </button>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setNavOpen((v) => !v)}
            aria-label="Toggle navigation"
            aria-expanded={navOpen}
          >
            {"\u2630"}
          </button>
          <span className="topbar__title">{current?.label}</span>
          <div className="topbar__spacer" />

          {job?.status === "processing" && (
            <Badge tone="info" pulse>
              Rendering {Math.round((job.progress ?? 0) * 100)}%
            </Badge>
          )}
          {project && <Badge tone="accent">{project.title}</Badge>}

          <ThemeToggle theme={theme} setTheme={setTheme} />

          <button type="button" className="btn btn--sm" onClick={handleNewProject}>
            New
          </button>
          <button
            type="button"
            className="btn btn--primary btn--sm"
            onClick={handleGenerate}
            disabled={busy}
          >
            {busy ? "Rendering..." : "Generate Movie"}
          </button>
        </header>

        <main className="content" id="main">
          <div className="content__inner" key={view}>
            {error && view !== "render" && (
              <Alert tone="danger" title="Something went wrong">
                <pre>{error}</pre>
              </Alert>
            )}

            {view === "studio" && (
              <StudioView
                title={title}
                setTitle={setTitle}
                script={script}
                setScript={setScript}
                language={language}
                setLanguage={setLanguage}
                visualMode={visualMode}
                setVisualMode={setVisualMode}
                characterIdentityPrompt={characterIdentityPrompt}
                setCharacterIdentityPrompt={setCharacterIdentityPrompt}
                characterLoraTags={characterLoraTags}
                setCharacterLoraTags={setCharacterLoraTags}
                wordCount={wordCount}
                estimatedRuntime={estimatedRuntime}
                busy={busy}
                onGenerate={handleGenerate}
                onLoadSample={() => {
                  setTitle("The Lighthouse");
                  setScript(SAMPLE_SCRIPT);
                }}
              />
            )}

            {view === "storyboard" && (
              <StoryboardView
                scenes={scenes}
                artifacts={artifacts}
                projects={projects}
                activeProjectId={project?.id ?? null}
                onOpenProject={openProject}
                onSaveTimeline={handleSaveTimeline}
                onGoToStudio={() => setView("studio")}
              />
            )}

            {view === "voice" && (
              <VoiceView
                providers={providers}
                provider={provider}
                setProvider={setProvider}
                voices={voices}
                voice={voice}
                setVoice={setVoice}
                previewUrl={previewUrl}
                previewBusy={previewBusy}
                onPreview={handlePreviewVoice}
              />
            )}

            {view === "render" && (
              <RenderView job={job} events={events} stageIndex={stageIndex} error={error} />
            )}

            {view === "preview" && (
              <PreviewView artifacts={artifacts} onGoToStoryboard={() => setView("storyboard")} />
            )}

            {view === "music" && <MusicStudio apiBase={BASE_URL} />}

            {view === "system" && (
              <SystemView deps={deps} providers={providers} onRefresh={refreshDeps} />
            )}
          </div>
        </main>
      </div>

      {paletteOpen && (
        <CommandPalette
          onClose={() => setPaletteOpen(false)}
          onSelect={(id) => {
            setView(id);
            setPaletteOpen(false);
          }}
          isLocked={isLocked}
        />
      )}
    </div>
  );
}

/* ========================================================================== */
/* Chrome                                                                     */
/* ========================================================================== */

function ThemeToggle({ theme, setTheme }: { theme: Theme; setTheme: (t: Theme) => void }) {
  return (
    <div className="theme-toggle" role="group" aria-label="Colour theme">
      <button
        type="button"
        className="theme-toggle__btn"
        aria-pressed={theme === "light"}
        aria-label="Light theme"
        title="Light theme"
        onClick={() => setTheme("light")}
      >
        {"\u2600"}
      </button>
      <button
        type="button"
        className="theme-toggle__btn"
        aria-pressed={theme === "dark"}
        aria-label="Dark theme"
        title="Dark theme"
        onClick={() => setTheme("dark")}
      >
        {"\u263E"}
      </button>
    </div>
  );
}

function CommandPalette({
  onClose,
  onSelect,
  isLocked,
}: {
  onClose: () => void;
  onSelect: (view: View) => void;
  isLocked: (view: View) => boolean;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const results = useMemo(
    () =>
      NAV.filter((item) => !isLocked(item.id)).filter((item) =>
        item.label.toLowerCase().includes(query.trim().toLowerCase()),
      ),
    [query, isLocked],
  );

  useEffect(() => setActive(0), [query]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % Math.max(1, results.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i - 1 + results.length) % Math.max(1, results.length));
    } else if (e.key === "Enter" && results[active]) {
      onSelect(results[active].id);
    }
  };

  return (
    <div
      className="palette-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <input
          ref={inputRef}
          className="palette__input"
          placeholder="Jump to..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          aria-label="Search commands"
        />
        <div className="palette__list">
          {results.map((item, i) => (
            <button
              key={item.id}
              type="button"
              className="palette__item"
              data-active={i === active}
              onMouseEnter={() => setActive(i)}
              onClick={() => onSelect(item.id)}
            >
              <span aria-hidden>{item.icon}</span>
              {item.label}
              <span className="palette__hint">{item.group}</span>
            </button>
          ))}
          {results.length === 0 && <div className="palette__item dim">No matches</div>}
        </div>
      </div>
    </div>
  );
}

/* ========================================================================== */
/* Views                                                                      */
/* ========================================================================== */

function StudioView(props: {
  title: string;
  setTitle: (v: string) => void;
  script: string;
  setScript: (v: string) => void;
  language: string;
  setLanguage: (v: string) => void;
  visualMode: "basic" | "cinematic";
  setVisualMode: (v: "basic" | "cinematic") => void;
  characterIdentityPrompt: string;
  setCharacterIdentityPrompt: (v: string) => void;
  characterLoraTags: string;
  setCharacterLoraTags: (v: string) => void;
  wordCount: number;
  estimatedRuntime: number;
  busy: boolean;
  onGenerate: () => void;
  onLoadSample: () => void;
}) {
  return (
    <>
      <section className="hero">
        <div className="hero__content">
          <span className="hero__eyebrow">
            <span className="dot" aria-hidden />
            Script to screen
          </span>
          <h1 className="hero__title">
            Turn any script into a <em>finished film</em>.
          </h1>
          <p className="hero__text">
            We break your writing into scenes, voice it with neural narration, illustrate every beat,
            and master a broadcast-ready 1080p MP4 with captions and mixed audio.
          </p>
          <div className="hero__actions">
            <button
              type="button"
              className="btn btn--primary btn--lg"
              onClick={props.onGenerate}
              disabled={props.busy}
            >
              {props.busy ? "Rendering..." : "Generate Movie"}
            </button>
            <button type="button" className="btn btn--lg" onClick={props.onLoadSample}>
              Load sample script
            </button>
          </div>
        </div>
      </section>

      <div className="grid grid--4">
        <Stat label="Words" value={props.wordCount} />
        <Stat label="Est. runtime" value={formatDuration(props.estimatedRuntime)} hint="at 150 wpm" />
        <Stat label="Output" value="1080p" hint="H.264 / AAC 192k" />
        <Stat label="Mode" value={props.visualMode === "basic" ? "Fast" : "Cinematic"} />
      </div>

      <div className="grid grid--2" style={{ alignItems: "start" }}>
        <Card title="Screenplay" description="Blank lines separate scenes.">
          <div className="col">
            <Field label="Project title" htmlFor="title">
              <input
                id="title"
                className="input"
                value={props.title}
                onChange={(e) => props.setTitle(e.target.value)}
                placeholder="Untitled Project"
              />
            </Field>
            <Field label="Script" htmlFor="script" hint={`${props.wordCount} words`}>
              <textarea
                id="script"
                className="textarea textarea--mono"
                value={props.script}
                onChange={(e) => props.setScript(e.target.value)}
                placeholder="Open on a quiet street at dawn..."
              />
            </Field>

              <Field
                label="Character identity prompt"
                htmlFor="character-identity"
                hint="Shared visual identity applied to every scene prompt."
              >
                <textarea
                  id="character-identity"
                  className="textarea"
                  value={props.characterIdentityPrompt}
                  onChange={(e) => props.setCharacterIdentityPrompt(e.target.value)}
                  placeholder="Lead: Maya Chen, 32, short silver bob, amber eyes, red raincoat, consistent facial structure."
                />
              </Field>

              <Field
                label="LoRA tags"
                htmlFor="character-lora-tags"
                hint="Comma-separated (optional), e.g. hero_face_v1:0.8, outfit_redcoat_v2:0.6"
              >
                <input
                  id="character-lora-tags"
                  className="input"
                  value={props.characterLoraTags}
                  onChange={(e) => props.setCharacterLoraTags(e.target.value)}
                  placeholder="hero_face_v1:0.8"
                />
              </Field>
          </div>
        </Card>

        <div className="col">
          <Card title="Render settings">
            <div className="col">
              <Field label="Visual mode">
                <Segmented
                  label="Visual mode"
                  value={props.visualMode}
                  onChange={props.setVisualMode}
                  options={[
                    { value: "basic", label: "Fast" },
                    { value: "cinematic", label: "Cinematic" },
                  ]}
                />
                <span className="hint">
                  {props.visualMode === "basic"
                    ? "Designed art cards with Ken Burns motion. Renders in seconds."
                    : "Diffusion-generated frames via ComfyUI. Much slower, needs models installed."}
                </span>
              </Field>

              <Field label="Language" htmlFor="lang">
                <select
                  id="lang"
                  className="select"
                  value={props.language}
                  onChange={(e) => props.setLanguage(e.target.value)}
                >
                  <option value="en">English</option>
                  <option value="es">Spanish</option>
                  <option value="fr">French</option>
                  <option value="de">German</option>
                  <option value="hi">Hindi</option>
                </select>
              </Field>

              <button
                type="button"
                className="btn btn--primary btn--lg btn--block"
                onClick={props.onGenerate}
                disabled={props.busy}
              >
                {props.busy ? "Rendering..." : "Generate Movie"}
              </button>
            </div>
          </Card>

          <Card title="What you get">
            <div>
              <div className="kv">
                <span className="kv__key">Video</span>
                <span className="kv__value">1920x1080 H.264</span>
              </div>
              <div className="kv">
                <span className="kv__key">Audio</span>
                <span className="kv__value">AAC 192k, -16 LUFS</span>
              </div>
              <div className="kv">
                <span className="kv__key">Narration</span>
                <span className="kv__value">MP3 192k, 44.1 kHz</span>
              </div>
              <div className="kv">
                <span className="kv__key">Captions</span>
                <span className="kv__value">Burned-in + SRT/VTT</span>
              </div>
              <div className="kv">
                <span className="kv__key">Per scene</span>
                <span className="kv__value">Image, clip, audio</span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

function StoryboardView({
  scenes,
  artifacts,
  projects,
  activeProjectId,
  onOpenProject,
  onSaveTimeline,
  onGoToStudio,
}: {
  scenes: ProjectOut["scenes"];
  artifacts: JobArtifacts | null;
  projects: ProjectOut[];
  activeProjectId: number | null;
  onOpenProject: (projectId: number) => void;
  onSaveTimeline: (updatedScenes: Array<{ scene_id: number; scene_index: number; duration_seconds: number }>) => Promise<void>;
  onGoToStudio: () => void;
}) {
  // While a render is in flight the project record may not have scenes yet, but
  // the artifacts endpoint already does - prefer whichever is richer.
  const baseRows = useMemo(
    () =>
      (artifacts?.scenes?.length
        ? artifacts.scenes.map((a) => ({
            id: a.id,
            scene_index: a.scene_index,
            title: a.title,
            text: a.script_chunk ?? "",
            duration: a.duration_seconds,
            image: a.image_url,
            audio: a.narration_url,
            provider: a.tts_provider,
          }))
        : scenes.map((s) => ({
            id: s.id,
            scene_index: s.scene_index,
            title: s.title,
            text: s.script_chunk,
            duration: s.duration_seconds,
            image: "",
            audio: "",
            provider: "",
          })))
        .slice()
        .sort((a, b) => a.scene_index - b.scene_index),
    [artifacts, scenes],
  );
  const [rows, setRows] = useState(baseRows);
  const [savingTimeline, setSavingTimeline] = useState(false);
  const [draggingSceneId, setDraggingSceneId] = useState<number | null>(null);

  useEffect(() => {
    setRows(baseRows);
  }, [baseRows]);

  const reindex = useCallback(
    (nextRows: typeof baseRows) => nextRows.map((row, i) => ({ ...row, scene_index: i + 1 })),
    [],
  );

  const moveScene = useCallback(
    (draggedId: number, targetId: number) => {
      if (draggedId === targetId) return;
      const current = rows.slice();
      const from = current.findIndex((r) => r.id === draggedId);
      const to = current.findIndex((r) => r.id === targetId);
      if (from < 0 || to < 0) return;
      const [item] = current.splice(from, 1);
      current.splice(to, 0, item);
      setRows(reindex(current));
    },
    [rows, reindex],
  );

  const saveTimeline = useCallback(async () => {
    setSavingTimeline(true);
    try {
      await onSaveTimeline(
        rows.map((row) => ({
          scene_id: row.id,
          scene_index: row.scene_index,
          duration_seconds: Math.max(0.5, Number(row.duration || 0)),
        })),
      );
    } finally {
      setSavingTimeline(false);
    }
  }, [onSaveTimeline, rows]);

  const totalDuration = rows.reduce((sum, r) => sum + (r.duration || 0), 0);

  const library = projects.length > 0 && (
    <Card
      title="Project library"
      description={`${projects.length} project${projects.length === 1 ? "" : "s"} - open one to view its storyboard.`}
    >
      <div className="track-list">
        {projects.slice(0, 12).map((p) => (
          <button
            key={p.id}
            type="button"
            className="project-row"
            aria-pressed={activeProjectId === p.id}
            onClick={() => onOpenProject(p.id)}
          >
            <span className="track__icon" aria-hidden>
              {"\u25A6"}
            </span>
            <span className="project-row__body">
              <span className="project-row__title truncate">{p.title}</span>
              <span className="project-row__meta">
                #{p.id} · {p.scenes.length} scenes · {new Date(p.created_at).toLocaleDateString()}
              </span>
            </span>
            <Badge tone={p.status === "completed" ? "success" : "neutral"}>{p.status}</Badge>
          </button>
        ))}
      </div>
    </Card>
  );

  if (rows.length === 0) {
    return (
      <>
        <div className="page-head">
          <div className="page-head__text">
            <h1 className="page-title">Storyboard</h1>
            <p className="page-subtitle">
              Every scene of your film, with its artwork, runtime and narration.
            </p>
          </div>
        </div>

        <EmptyState
          icon={"\u25A6"}
          title="No storyboard open"
          text={
            projects.length > 0
              ? "Open a project below, or write a new script to generate a fresh storyboard."
              : "Write a script in the Script Studio and every scene will appear here with its artwork, narration and clip."
          }
          action={
            <button type="button" className="btn btn--primary" onClick={onGoToStudio}>
              Go to Script Studio
            </button>
          }
        />

        {library}
      </>
    );
  }

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="page-title">Storyboard</h1>
          <p className="page-subtitle">
            {rows.length} scenes, {formatDuration(totalDuration)} total runtime.
          </p>
        </div>
      </div>

      {totalDuration > 0 && (
        <Card title="Timeline" description="Drag scene cards to reorder, then save.">
          <div className="timeline-toolbar">
            <span className="dim">{rows.length} scenes</span>
            <button type="button" className="btn btn--sm" onClick={saveTimeline} disabled={savingTimeline}>
              {savingTimeline ? "Saving..." : "Save timeline"}
            </button>
          </div>
          <div className="timeline">
            {rows.map((row) => (
              <div
                key={row.id}
                className="timeline__block"
                style={{ flexGrow: Math.max(0.01, row.duration || 0) }}
                title={`Scene ${row.scene_index} - ${formatDuration(row.duration)}`}
              >
                {row.scene_index}
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid grid--3">
        {rows.map((row) => (
          <article
            className="scene-card scene-card--draggable"
            key={row.id}
            draggable
            onDragStart={() => setDraggingSceneId(row.id)}
            onDragEnd={() => setDraggingSceneId(null)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => {
              if (draggingSceneId !== null) moveScene(draggingSceneId, row.id);
              setDraggingSceneId(null);
            }}
          >
            <div className="scene-card__media">
              {row.image ? (
                <img src={row.image} alt={`Scene ${row.scene_index}: ${row.title}`} loading="lazy" />
              ) : (
                <Skeleton height="100%" />
              )}
              <span className="scene-card__index">SCENE {row.scene_index}</span>
              <span className="scene-card__duration">{formatDuration(row.duration)}</span>
            </div>
            <div className="scene-card__body">
              <div className="scene-card__controls">
                <span className="drag-handle" title="Drag to reorder" aria-hidden>
                  :::
                </span>
                <label className="dim" htmlFor={`duration-${row.id}`}>
                  Duration (s)
                </label>
                <input
                  id={`duration-${row.id}`}
                  className="input"
                  type="number"
                  min={0.5}
                  step={0.1}
                  value={Number(row.duration).toFixed(1)}
                  onChange={(e) => {
                    const value = Number(e.target.value);
                    setRows((prev) =>
                      prev.map((it) => (it.id === row.id ? { ...it, duration: Number.isFinite(value) ? value : it.duration } : it)),
                    );
                  }}
                />
              </div>
              <h3 className="scene-card__title">{row.title}</h3>
              {row.text && <p className="scene-card__text">{row.text}</p>}
              {row.provider && <span className="dim">Voiced by {row.provider}</span>}
            </div>
            {row.audio && (
              <div className="scene-card__foot">
                <audio controls preload="none" src={row.audio} style={{ width: "100%", height: 32 }} />
              </div>
            )}
          </article>
        ))}
      </div>

      {library}
    </>
  );
}

function VoiceView(props: {
  providers: TTSProvidersResponse | null;
  provider: string;
  setProvider: (v: string) => void;
  voices: TTSVoice[];
  voice: string;
  setVoice: (v: string) => void;
  previewUrl: string;
  previewBusy: boolean;
  onPreview: () => void;
}) {
  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="page-title">Voice Studio</h1>
          <p className="page-subtitle">
            Choose the narration engine. Engines configured in <code className="mono">.env</code> are
            selectable; the rest need an API key. Unavailable engines fall back automatically.
          </p>
        </div>
      </div>

      <div className="grid grid--2" style={{ alignItems: "start" }}>
        <Card title="Engine" description="Ordered by voice quality.">
          <div className="col" style={{ gap: 8 }}>
            {(props.providers?.providers ?? []).map((p) => (
              <button
                key={p.id}
                type="button"
                className="provider-row"
                aria-pressed={props.provider === p.id}
                disabled={!p.configured}
                onClick={() => props.setProvider(p.id)}
              >
                <span className="provider-row__name">{p.name}</span>
                {p.configured ? (
                  <Badge tone="success">Ready</Badge>
                ) : (
                  <Badge tone="warning">{p.requires_key ? "Needs API key" : "Not installed"}</Badge>
                )}
              </button>
            ))}
            {!props.providers && <Skeleton height={160} />}
          </div>
        </Card>

        <Card
          title="Voice"
          description={props.voices.length ? `${props.voices.length} voices available.` : undefined}
          actions={
            <button
              type="button"
              className="btn btn--sm"
              onClick={props.onPreview}
              disabled={!props.provider || props.previewBusy}
            >
              {props.previewBusy ? "Synthesising..." : "Preview"}
            </button>
          }
        >
          {props.voices.length === 0 ? (
            <EmptyState
              icon={"\u25C9"}
              title="No voice list"
              text="This engine uses its configured default voice. Preview still works."
            />
          ) : (
            <div className="voice-grid">
              {props.voices.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  className="voice-chip"
                  aria-pressed={props.voice === v.id}
                  onClick={() => props.setVoice(v.id)}
                >
                  <span className="voice-chip__name">{v.name}</span>
                  <span className="voice-chip__meta">
                    {[v.locale, v.gender].filter(Boolean).join(" / ") || v.provider}
                  </span>
                </button>
              ))}
            </div>
          )}

          {props.previewUrl && (
            <div className="audio-row" style={{ marginTop: 16 }}>
              <span aria-hidden>{"\u266A"}</span>
              <audio controls autoPlay src={props.previewUrl} />
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

function RenderView({
  job,
  events,
  stageIndex,
  error,
}: {
  job: JobOut | null;
  events: JobEventOut[];
  stageIndex: number;
  error: string;
}) {
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Keep the newest line in view, the way a real build console behaves.
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [events.length]);

  if (!job) {
    return (
      <EmptyState
        icon={"\u25B6"}
        title="Nothing rendering"
        text="Start a render from the Script Studio and live progress will stream here."
      />
    );
  }

  const tone = job.status === "failed" ? "danger" : job.status === "completed" ? "success" : "info";

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="page-title">Render Console</h1>
          <p className="page-subtitle">{job.message}</p>
        </div>
        <Badge tone={tone} pulse={job.status === "processing"}>
          {job.status}
        </Badge>
      </div>

      <Card>
        <div className="col">
          <div className="row">
            <strong className="nums" style={{ fontSize: "var(--text-xl)" }}>
              {Math.round((job.progress ?? 0) * 100)}%
            </strong>
            <div className="spacer" />
            <span className="dim nums">
              Scene {job.processed_scenes} / {job.total_scenes || "-"}
            </span>
          </div>
          <Progress value={job.progress ?? 0} label="Render progress" />
        </div>
      </Card>

      <div className="grid grid--2" style={{ alignItems: "start" }}>
        <Card title="Pipeline">
          <div className="stepper">
            {RENDER_STAGES.map((stage, i) => (
              <div
                key={stage.id}
                className="step"
                data-state={
                  job.status === "completed" || i < stageIndex
                    ? "done"
                    : i === stageIndex
                      ? "active"
                      : "idle"
                }
              >
                <span className="step__marker">
                  {job.status === "completed" || i < stageIndex ? "\u2713" : i + 1}
                </span>
                <span className="step__label">{stage.label}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Activity log">
          <div className="console" ref={logRef} role="log" aria-live="polite">
            {events.map((event) => (
              <div className="console__line" key={event.id} data-level={event.level}>
                <span className="console__time">
                  {new Date(event.created_at).toLocaleTimeString()}
                </span>
                <span className="console__stage">{event.stage}</span>
                <span className="console__msg">{event.message}</span>
              </div>
            ))}
            {events.length === 0 && <span className="dim">Waiting for the first event...</span>}
          </div>
        </Card>
      </div>

      {error && (
        <Alert tone="danger" title="Render failed">
          <pre>{error}</pre>
        </Alert>
      )}
    </>
  );
}

function PreviewView({
  artifacts,
  onGoToStoryboard,
}: {
  artifacts: JobArtifacts | null;
  onGoToStoryboard: () => void;
}) {
  if (!artifacts?.video_url) {
    return (
      <EmptyState
        icon={"\u25C8"}
        title="No movie loaded"
        text="Finish a render, or open a previously rendered project from the Storyboard library."
        action={
          <button type="button" className="btn btn--primary" onClick={onGoToStoryboard}>
            Browse projects
          </button>
        }
      />
    );
  }

  const assets = [
    { label: "Final movie (MP4)", url: artifacts.video_url },
    { label: "Narration (MP3)", url: artifacts.audio_url },
    { label: "Music stem (WAV)", url: artifacts.music_url },
    { label: "SFX stem (MP3)", url: artifacts.sfx_url },
    { label: "Stems manifest (JSON)", url: artifacts.stems_manifest_url },
    { label: "Stems package (ZIP)", url: artifacts.stems_zip_url },
    { label: "Subtitles (SRT)", url: artifacts.subtitle_url },
    { label: "Captions (VTT)", url: artifacts.captions_vtt_url },
    { label: "Poster frame (JPG)", url: artifacts.poster_url },
  ].filter((a) => a.url);

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="page-title">Preview &amp; Export</h1>
          <p className="page-subtitle">
            {formatDuration(artifacts.duration_seconds)}, {artifacts.scenes.length} scenes, 1080p H.264
          </p>
        </div>
        <a className="btn btn--primary" href={artifacts.video_url} download>
          Download MP4
        </a>
      </div>

      <div className="player">
        <video
          controls
          playsInline
          poster={artifacts.poster_url || undefined}
          src={artifacts.video_url}
        >
          {artifacts.captions_vtt_url && (
            <track
              kind="captions"
              srcLang="en"
              label="English"
              src={artifacts.captions_vtt_url}
              default
            />
          )}
        </video>
      </div>

      <div className="grid grid--2">
        <Card title="Narration audio" description="Mastered MP3, 192 kbps, 44.1 kHz.">
          <div className="audio-row">
            <span aria-hidden>{"\u266A"}</span>
            <audio controls src={artifacts.audio_url} />
          </div>
          <a className="btn btn--sm" href={artifacts.audio_url} download style={{ marginTop: 12 }}>
            Download MP3
          </a>
        </Card>

        <Card title="Assets">
          <div>
            {assets.map((asset) => (
              <div className="kv" key={asset.label}>
                <span className="kv__key">{asset.label}</span>
                <a className="btn btn--sm" href={asset.url} download style={{ marginLeft: "auto" }}>
                  Download
                </a>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Scenes">
        <div className="grid grid--3">
          {artifacts.scenes.map((scene) => (
            <article className="scene-card" key={scene.id}>
              <div className="scene-card__media">
                {scene.image_url && <img src={scene.image_url} alt={scene.title} loading="lazy" />}
                <span className="scene-card__index">SCENE {scene.scene_index}</span>
                <span className="scene-card__duration">
                  {formatDuration(scene.duration_seconds)}
                </span>
              </div>
              <div className="scene-card__body">
                <h3 className="scene-card__title">{scene.title}</h3>
                {scene.tts_provider && <span className="dim">Voiced by {scene.tts_provider}</span>}
              </div>
              {scene.narration_url && (
                <div className="scene-card__foot">
                  <audio
                    controls
                    preload="none"
                    src={scene.narration_url}
                    style={{ width: "100%", height: 32 }}
                  />
                </div>
              )}
            </article>
          ))}
        </div>
      </Card>
    </>
  );
}

/** One dependency widget. Fixed structure so every card lines up. */
function DependencyCard({ name, info }: { name: string; info: DependencyInfo }) {
  const label = info.label ?? name;

  // Three states, not two. An unconfigured optional dependency is normal and
  // should not wear the same warning colour as a broken required one.
  const state = info.ready ? "ready" : info.optional ? "optional" : "error";
  const tone = state === "ready" ? "success" : state === "optional" ? "neutral" : "danger";
  const statusText = state === "ready" ? "Ready" : state === "optional" ? "Inactive" : "Action needed";

  return (
    <article className="dep-card" data-state={state}>
      <header className="dep-card__head">
        <span className="dep-card__name">{label}</span>
        {info.optional && !info.ready && <span className="dep-card__tag">Optional</span>}
        <Badge tone={tone}>{statusText}</Badge>
      </header>

      <p className="dep-card__detail">{info.detail}</p>

      {info.hint && <p className="dep-card__hint">{info.hint}</p>}

      {info.resolved_path && (
        <p className="dep-card__path mono" title={info.resolved_path}>
          {info.resolved_path}
        </p>
      )}

      {typeof info.checkpoint_count === "number" && info.ready && (
        <p className="dep-card__hint">
          {info.checkpoint_count} checkpoint{info.checkpoint_count === 1 ? "" : "s"} available
        </p>
      )}

      {info.raw_error && (
        <details className="details dep-card__raw">
          <summary className="details__summary">Technical detail</summary>
          <div className="details__body">
            <pre className="dep-card__trace">{info.raw_error}</pre>
          </div>
        </details>
      )}
    </article>
  );
}

function SystemView({
  deps,
  providers,
  onRefresh,
}: {
  deps: DependenciesResponse | null;
  providers: TTSProvidersResponse | null;
  onRefresh: () => void;
}) {
  const blocking = deps
    ? Object.values(deps.dependencies).filter((d) => !d.ready && !d.optional).length
    : 0;

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="page-title">System Health</h1>
          <p className="page-subtitle">
            Everything the render pipeline depends on. Configure these in{" "}
            <code className="mono">.env</code>.
          </p>
        </div>
        <button type="button" className="btn" onClick={onRefresh}>
          Re-check
        </button>
      </div>

      {deps && (
        <Alert tone={blocking > 0 ? "danger" : "success"}>
          {blocking > 0
            ? `${blocking} required dependency needs attention before you can render.`
            : deps.ready_for_cinematic
              ? "All systems ready, including Cinematic mode."
              : "Ready to render. Cinematic mode is unavailable until ComfyUI is running."}
        </Alert>
      )}

      <div className="grid grid--3">
        {deps
          ? Object.entries(deps.dependencies).map(([name, info]) => (
              <DependencyCard key={name} name={name} info={info} />
            ))
          : [0, 1, 2].map((i) => <Skeleton key={i} height={170} />)}
      </div>

      <Card title="Narration engines" description="Configured via .env - no code changes needed.">
        <div>
          {(providers?.providers ?? []).map((p) => (
            <div className="kv" key={p.id}>
              <span className="kv__key">{p.name}</span>
              <span style={{ marginLeft: "auto" }}>
                <Badge tone={p.configured ? "success" : "neutral"}>
                  {p.configured ? "Configured" : p.requires_key ? "Needs API key" : "Not installed"}
                </Badge>
              </span>
            </div>
          ))}
          {!providers && <Skeleton height={180} />}
        </div>
      </Card>

      <Card title="Output profile">
        <div>
          <div className="kv">
            <span className="kv__key">Resolution</span>
            <span className="kv__value">1920 x 1080 @ 30 fps</span>
          </div>
          <div className="kv">
            <span className="kv__key">Video codec</span>
            <span className="kv__value">H.264, CRF 20, faststart</span>
          </div>
          <div className="kv">
            <span className="kv__key">Audio codec</span>
            <span className="kv__value">AAC 192 kbps, 44.1 kHz</span>
          </div>
          <div className="kv">
            <span className="kv__key">Loudness</span>
            <span className="kv__value">-16 LUFS, -1.5 dBTP</span>
          </div>
        </div>
      </Card>
    </>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}

