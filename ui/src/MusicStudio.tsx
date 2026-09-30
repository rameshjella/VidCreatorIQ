import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "./api";
import { Alert, Badge, Card, EmptyState, Field, Skeleton, formatDuration } from "./components/ui";
import type { MusicEngineHealth, MusicGenerationOut } from "./types";

type Props = {
  apiBase: string;
};

const MOODS = ["Emotional", "Calm", "Energetic", "Dark", "Hopeful", "Dreamy", "Epic", "Nostalgic"];
const STYLES = [
  "Cinematic",
  "Ambient",
  "Electronic",
  "Acoustic",
  "Classical",
  "Lo-fi",
  "Rock",
  "Indian-inspired",
  "Experimental",
];
const ENERGIES = ["Low", "Medium", "High"];

const PRESETS = [
  {
    label: "Rainy piano",
    prompt: "A peaceful cinematic piano piece inspired by rain at night.",
    title: "Rainy Night Study",
    mood: "Nostalgic",
    style: "Cinematic",
    energy: "Low",
    instrumentation: "Intimate piano and expressive strings",
  },
  {
    label: "Lo-fi focus",
    prompt: "Warm lo-fi beat with soft vinyl crackle and mellow electric piano for late-night focus.",
    title: "Late Night Focus",
    mood: "Calm",
    style: "Lo-fi",
    energy: "Low",
    instrumentation: "Electric piano, brushed drums, vinyl crackle",
  },
  {
    label: "Epic reveal",
    prompt: "Epic orchestral build with taiko drums and rising strings for a heroic reveal.",
    title: "Heroic Reveal",
    mood: "Epic",
    style: "Cinematic",
    energy: "High",
    instrumentation: "Taiko drums, brass, soaring strings",
  },
  {
    label: "Dreamy ambient",
    prompt: "Dreamy ambient texture with airy pads and subtle pulses, like sunrise above clouds.",
    title: "Above The Clouds",
    mood: "Dreamy",
    style: "Ambient",
    energy: "Low",
    instrumentation: "Airy pads, soft synth pulses, distant choir",
  },
];

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export default function MusicStudio({ apiBase }: Props) {
  const [engineHealth, setEngineHealth] = useState<MusicEngineHealth | null>(null);
  const [history, setHistory] = useState<MusicGenerationOut[]>([]);
  const [selected, setSelected] = useState<MusicGenerationOut | null>(null);

  const [prompt, setPrompt] = useState(PRESETS[0].prompt);
  const [title, setTitle] = useState(PRESETS[0].title);
  const [mood, setMood] = useState(PRESETS[0].mood);
  const [style, setStyle] = useState(PRESETS[0].style);
  const [energy, setEnergy] = useState(PRESETS[0].energy);
  const [instrumentation, setInstrumentation] = useState(PRESETS[0].instrumentation);
  const [durationSeconds, setDurationSeconds] = useState(8);

  const [state, setState] = useState<"READY" | "GENERATING" | "COMPLETED" | "FAILED">("READY");
  const [error, setError] = useState("");
  const [waveformPeaks, setWaveformPeaks] = useState<number[]>([]);

  const supportedDurations = useMemo(
    () => engineHealth?.music_engine.supported_durations ?? [4, 8, 12, 16],
    [engineHealth],
  );
  const engineReady = Boolean(engineHealth?.music_engine.model_loaded);
  const busy = state === "GENERATING";

  const refreshMusicData = useCallback(async () => {
    const [health, generations] = await Promise.all([
      api.musicHealth(apiBase),
      api.listMusicGenerations(apiBase),
    ]);
    setEngineHealth(health);
    setHistory(generations);
    setSelected((current) => current ?? generations[0] ?? null);
  }, [apiBase]);

  useEffect(() => {
    void refreshMusicData().catch(() => undefined);
  }, [refreshMusicData]);

  useEffect(() => {
    if (!supportedDurations.includes(durationSeconds)) {
      setDurationSeconds(supportedDurations[0]);
    }
  }, [supportedDurations, durationSeconds]);

  useEffect(() => {
    async function loadWaveform() {
      if (!selected || selected.status !== "completed") {
        setWaveformPeaks([]);
        return;
      }
      try {
        const waveform = await api.getMusicWaveform(apiBase, selected.id, 160);
        setWaveformPeaks(waveform.peaks);
      } catch {
        setWaveformPeaks([]);
      }
    }
    void loadWaveform();
  }, [apiBase, selected?.id, selected?.status]);

  async function pollUntilDone(generationId: number): Promise<MusicGenerationOut> {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const current = await api.getMusicGeneration(apiBase, generationId);
      setSelected(current);
      if (current.status === "completed") return current;
      if (current.status === "failed" || current.status === "canceled") {
        throw new Error(current.error_message || "Generation failed");
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    throw new Error("Generation is taking longer than expected. Please check status again.");
  }

  async function generateMusic() {
    if (!prompt.trim()) {
      setError("Describe your music before generating.");
      setState("FAILED");
      return;
    }

    setState("GENERATING");
    setError("");
    try {
      const created = await api.musicGenerate(apiBase, {
        prompt,
        title,
        mood,
        style,
        energy,
        instrumentation,
        duration_seconds: durationSeconds,
      });
      setSelected(created);
      setSelected(await pollUntilDone(created.id));
      setState("COMPLETED");
      await refreshMusicData();
    } catch (err) {
      setState("FAILED");
      setError(toErrorMessage(err));
    }
  }

  async function createVariation() {
    if (!selected) {
      setError("Select a generated track first.");
      setState("FAILED");
      return;
    }

    setState("GENERATING");
    setError("");
    try {
      const variation = await api.createMusicVariation(apiBase, selected.id, {
        title: `${selected.title} - Variation`,
        mood,
        style,
        energy,
        instrumentation,
        duration_seconds: durationSeconds,
      });
      setSelected(variation);
      setSelected(await pollUntilDone(variation.id));
      setState("COMPLETED");
      await refreshMusicData();
    } catch (err) {
      setState("FAILED");
      setError(toErrorMessage(err));
    }
  }

  function applyPreset(preset: (typeof PRESETS)[number]) {
    setPrompt(preset.prompt);
    setTitle(preset.title);
    setMood(preset.mood);
    setStyle(preset.style);
    setEnergy(preset.energy);
    setInstrumentation(preset.instrumentation);
  }

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="page-title">Music Studio</h1>
          <p className="page-subtitle">
            Generate an original score locally with an open pretrained model, then drop it under your
            film as a ducked music bed.
          </p>
        </div>
        <button
          type="button"
          className="btn"
          onClick={() => void refreshMusicData().catch(() => undefined)}
        >
          Refresh
        </button>
      </div>

      <div className="grid grid--4">
        <div className="stat">
          <div className="stat__label">Engine</div>
          <div className="stat__value" style={{ fontSize: "var(--text-md)" }}>
            {engineHealth ? (
              <Badge tone={engineReady ? "success" : "warning"} pulse={!engineReady}>
                {engineReady ? "Ready" : "Preparing"}
              </Badge>
            ) : (
              <Skeleton height={22} width={90} />
            )}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Model</div>
          <div className="stat__value truncate" style={{ fontSize: "var(--text-base)" }}>
            {engineHealth?.music_engine.model ?? "loading..."}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Device</div>
          <div className="stat__value" style={{ fontSize: "var(--text-md)", textTransform: "uppercase" }}>
            {engineHealth?.music_engine.device ?? "unknown"}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Lengths</div>
          <div className="stat__value" style={{ fontSize: "var(--text-md)" }}>
            {supportedDurations.join(" / ")}s
          </div>
        </div>
      </div>

      <div className="grid grid--2" style={{ alignItems: "start" }}>
        <Card title="Compose" description="Describe the music you want, or start from a preset.">
          <div className="col">
            <Field label="Prompt" htmlFor="music-prompt" hint={`${prompt.trim().length} characters`}>
              <textarea
                id="music-prompt"
                className="textarea"
                style={{ minHeight: 120 }}
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="A peaceful cinematic piano piece inspired by rain at night."
              />
            </Field>

            <div className="chip-row">
              {PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className="chip"
                  aria-pressed={prompt === preset.prompt}
                  onClick={() => applyPreset(preset)}
                >
                  {preset.label}
                </button>
              ))}
            </div>

            <div className="grid grid--2" style={{ gap: "var(--space-4)" }}>
              <Field label="Title" htmlFor="music-title">
                <input
                  id="music-title"
                  className="input"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </Field>
              <Field label="Duration" htmlFor="music-duration">
                <select
                  id="music-duration"
                  className="select"
                  value={durationSeconds}
                  onChange={(event) => setDurationSeconds(Number(event.target.value))}
                >
                  {supportedDurations.map((value) => (
                    <option key={value} value={value}>
                      {value} seconds
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Mood" htmlFor="music-mood">
                <select
                  id="music-mood"
                  className="select"
                  value={mood}
                  onChange={(event) => setMood(event.target.value)}
                >
                  {MOODS.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Style" htmlFor="music-style">
                <select
                  id="music-style"
                  className="select"
                  value={style}
                  onChange={(event) => setStyle(event.target.value)}
                >
                  {STYLES.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Energy" htmlFor="music-energy">
                <select
                  id="music-energy"
                  className="select"
                  value={energy}
                  onChange={(event) => setEnergy(event.target.value)}
                >
                  {ENERGIES.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Instrumentation" htmlFor="music-instr">
                <input
                  id="music-instr"
                  className="input"
                  value={instrumentation}
                  onChange={(event) => setInstrumentation(event.target.value)}
                />
              </Field>
            </div>

            <button
              type="button"
              className="btn btn--primary btn--lg btn--block"
              disabled={busy}
              onClick={() => void generateMusic()}
            >
              {busy ? "Creating your track..." : "Generate Music"}
            </button>

            {busy && (
              <div className="progress">
                <div className="progress__bar progress__bar--indeterminate" />
              </div>
            )}
            {busy && <span className="hint">This can take a while on CPU.</span>}

            {state === "FAILED" && (
              <Alert tone="danger" title="Generation failed">
                {error}
              </Alert>
            )}
            {state === "COMPLETED" && <Alert tone="success">Your track is ready.</Alert>}
          </div>
        </Card>

        <Card title="Latest creation">
          {!selected ? (
            <EmptyState
              icon={"\u266A"}
              title="No track yet"
              text="Generate your first track to preview, download and remix it here."
            />
          ) : (
            <div className="col">
              <div>
                <h3 style={{ fontSize: "var(--text-lg)", fontWeight: 600, letterSpacing: "-0.02em" }}>
                  {selected.title}
                </h3>
                <div className="row row--wrap" style={{ marginTop: 8, gap: 8 }}>
                  <Badge tone="accent">{selected.generation_label || "Original"}</Badge>
                  <Badge>{selected.style}</Badge>
                  <Badge>{selected.mood}</Badge>
                  <Badge>{selected.energy}</Badge>
                </div>
              </div>

              {waveformPeaks.length > 0 && (
                <div className="waveform" aria-label="Audio waveform" role="img">
                  <svg viewBox={`0 0 ${waveformPeaks.length} 40`} preserveAspectRatio="none">
                    {waveformPeaks.map((peak, idx) => {
                      const h = Math.max(2, Math.min(38, Math.round(peak * 38)));
                      return (
                        <rect
                          key={idx}
                          x={idx}
                          y={Math.round((40 - h) / 2)}
                          width="0.8"
                          height={h}
                          rx="0.4"
                        />
                      );
                    })}
                  </svg>
                </div>
              )}

              {selected.audio_url ? (
                <div className="audio-row">
                  <span aria-hidden>{"\u266A"}</span>
                  <audio controls preload="metadata" src={`${apiBase}${selected.audio_url}`} />
                </div>
              ) : (
                <span className="hint">
                  {selected.status === "generating"
                    ? "Creating your track..."
                    : "Audio is not available for this generation."}
                </span>
              )}

              <div>
                <div className="kv">
                  <span className="kv__key">Duration</span>
                  <span className="kv__value">{formatDuration(selected.duration_seconds)}</span>
                </div>
                <div className="kv">
                  <span className="kv__key">Generated in</span>
                  <span className="kv__value">
                    {(selected.generation_time_ms / 1000).toFixed(1)}s
                  </span>
                </div>
                <div className="kv">
                  <span className="kv__key">Sample rate</span>
                  <span className="kv__value">{selected.sample_rate} Hz</span>
                </div>
                <div className="kv">
                  <span className="kv__key">Status</span>
                  <span className="kv__value">{selected.status}</span>
                </div>
              </div>

              <div className="row row--wrap">
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={busy}
                  onClick={() => void createVariation()}
                >
                  Create variation
                </button>
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={busy}
                  onClick={() => void generateMusic()}
                >
                  Regenerate
                </button>
                {selected.audio_url && (
                  <a className="btn btn--sm" href={`${apiBase}${selected.audio_url}`} download>
                    Download WAV
                  </a>
                )}
              </div>

              <details className="details">
                <summary className="details__summary">Generation details</summary>
                <div className="details__body">
                  <div className="kv">
                    <span className="kv__key">Model</span>
                    <span className="kv__value mono">{selected.model}</span>
                  </div>
                  <p className="dim" style={{ marginTop: 12 }}>
                    {selected.composed_prompt}
                  </p>
                </div>
              </details>
            </div>
          )}
        </Card>
      </div>

      <Card
        title="Generation history"
        description={history.length ? `${history.length} tracks` : undefined}
      >
        {history.length === 0 ? (
          <EmptyState icon={"\u2637"} title="No generations yet" text="Your tracks will be listed here." />
        ) : (
          <div className="track-list">
            {history.map((item) => (
              <button
                key={item.id}
                type="button"
                className="track"
                aria-pressed={selected?.id === item.id}
                onClick={() => setSelected(item)}
              >
                <span className="track__icon" aria-hidden>
                  {"\u266A"}
                </span>
                <span className="track__body">
                  <span className="track__title">{item.title}</span>
                  <span className="track__meta">
                    #{item.id} · {item.generation_label || "Original"} · {item.style} ·{" "}
                    {item.duration_seconds}s
                  </span>
                </span>
                <Badge
                  tone={
                    item.status === "completed"
                      ? "success"
                      : item.status === "failed"
                        ? "danger"
                        : "info"
                  }
                >
                  {item.status}
                </Badge>
                <span className="track__date dim">
                  {new Date(item.created_at).toLocaleDateString()}
                </span>
              </button>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}

