import { useEffect, useMemo, useState } from "react";

import { api } from "./api";
import type { MusicEngineHealth, MusicGenerationOut } from "./types";

type Props = {
  apiBase: string;
};

const moodOptions = ["Emotional", "Calm", "Energetic", "Dark", "Hopeful", "Dreamy", "Epic", "Nostalgic"];
const styleOptions = ["Cinematic", "Ambient", "Electronic", "Acoustic", "Classical", "Lo-fi", "Rock", "Indian-inspired", "Experimental"];
const energyOptions = ["Low", "Medium", "High"];
const examples = [
  "A peaceful cinematic piano piece inspired by rain at night.",
  "Warm lo-fi beat with soft vinyl crackle and mellow electric piano for late-night focus.",
  "Epic orchestral build with taiko drums and rising strings for a heroic reveal.",
  "Dreamy ambient texture with airy pads and subtle pulses, like sunrise above clouds.",
];

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function formatMs(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function MusicStudio({ apiBase }: Props) {
  const [engineHealth, setEngineHealth] = useState<MusicEngineHealth | null>(null);
  const [history, setHistory] = useState<MusicGenerationOut[]>([]);
  const [selected, setSelected] = useState<MusicGenerationOut | null>(null);

  const [prompt, setPrompt] = useState(examples[0]);
  const [title, setTitle] = useState("Rainy Night Study");
  const [mood, setMood] = useState("Nostalgic");
  const [style, setStyle] = useState("Cinematic");
  const [energy, setEnergy] = useState("Low");
  const [instrumentation, setInstrumentation] = useState("Intimate piano and expressive strings");
  const [durationSeconds, setDurationSeconds] = useState(8);

  const [state, setState] = useState<"READY" | "GENERATING" | "COMPLETED" | "FAILED">("READY");
  const [error, setError] = useState("");
  const [waveformPeaks, setWaveformPeaks] = useState<number[]>([]);

  const supportedDurations = useMemo(() => engineHealth?.music_engine.supported_durations ?? [4, 8, 12, 16], [engineHealth]);

  async function refreshMusicData() {
    const [health, generations] = await Promise.all([api.musicHealth(apiBase), api.listMusicGenerations(apiBase)]);
    setEngineHealth(health);
    setHistory(generations);
    if (generations.length > 0 && !selected) {
      setSelected(generations[0]);
    }
  }

  useEffect(() => {
    void refreshMusicData();
  }, [apiBase]);

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
    const maxChecks = 120;
    for (let attempt = 0; attempt < maxChecks; attempt += 1) {
      const current = await api.getMusicGeneration(apiBase, generationId);
      setSelected(current);
      if (current.status === "completed") {
        return current;
      }
      if (current.status === "failed") {
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
      const finalItem = await pollUntilDone(created.id);
      setSelected(finalItem);
      setState("COMPLETED");
      await refreshMusicData();
    } catch (err) {
      setState("FAILED");
      setError(toErrorMessage(err));
    }
  }

  async function regenerateMusic() {
    await generateMusic();
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
      const finalItem = await pollUntilDone(variation.id);
      setSelected(finalItem);
      setState("COMPLETED");
      await refreshMusicData();
    } catch (err) {
      setState("FAILED");
      setError(toErrorMessage(err));
    }
  }

  return (
    <section className="musicStudioWrap">
      <div className="musicIntro card">
        <h3>AI Music Studio</h3>
        <p className="subhead">Experimental local music generation powered by an open pretrained model.</p>
        <div className="pillRow">
          <span className="pill ok">Model: {engineHealth?.music_engine.model ?? "loading..."}</span>
          <span className="pill">Device: {engineHealth?.music_engine.device ?? "unknown"}</span>
          <span className={`pill ${engineHealth?.music_engine.model_loaded ? "ok" : ""}`}>
            Engine: {engineHealth?.music_engine.model_loaded ? "Ready" : "Preparing"}
          </span>
          <span className="pill">Durations: {supportedDurations.join(" / ")}s</span>
        </div>
      </div>

      <div className="grid two">
        <article className="card musicComposer">
          <h3>Create Something New</h3>
          <label>Describe your music</label>
          <textarea className="musicPrompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} />

          <div className="exampleRow">
            {examples.map((example) => (
              <button key={example} className="exampleChip" type="button" onClick={() => setPrompt(example)}>
                {example.slice(0, 48)}...
              </button>
            ))}
          </div>

          <div className="grid two">
            <div>
              <label>Title</label>
              <input value={title} onChange={(event) => setTitle(event.target.value)} />
            </div>
            <div>
              <label>Duration</label>
              <select value={durationSeconds} onChange={(event) => setDurationSeconds(Number(event.target.value))}>
                {supportedDurations.map((value) => (
                  <option key={value} value={value}>{value} seconds</option>
                ))}
              </select>
            </div>
            <div>
              <label>Mood</label>
              <select value={mood} onChange={(event) => setMood(event.target.value)}>
                {moodOptions.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </div>
            <div>
              <label>Style</label>
              <select value={style} onChange={(event) => setStyle(event.target.value)}>
                {styleOptions.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </div>
            <div>
              <label>Energy</label>
              <select value={energy} onChange={(event) => setEnergy(event.target.value)}>
                {energyOptions.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </div>
            <div>
              <label>Instrumentation</label>
              <input value={instrumentation} onChange={(event) => setInstrumentation(event.target.value)} />
            </div>
          </div>

          <button className="primary" disabled={state === "GENERATING"} onClick={() => void generateMusic()}>
            {state === "GENERATING" ? "Creating your track..." : "Generate Music"}
          </button>

          {state === "GENERATING" && <p className="help">Creating your track... this can take longer on CPU.</p>}

          {state === "FAILED" && <p className="error">We couldn't generate this track. {error}</p>}
          {state === "COMPLETED" && <p className="success">Your track is ready.</p>}
        </article>

        <article className="card musicResult">
          <h3>Latest Creation</h3>
          {!selected && <p className="help">Generate your first track to preview and download it here.</p>}
          {selected && (
            <>
              <div className="resultTitle">{selected.title}</div>
              <div className="help">
                {selected.generation_label || "Original"} · {selected.style} · {selected.mood} · {selected.instrumentation}
              </div>
              {selected.audio_url ? (
                <audio className="audioPlayer" controls src={`${apiBase}${selected.audio_url}`} preload="metadata" />
              ) : (
                <div className="help">
                  {selected.status === "generating"
                    ? "Creating your track..."
                    : "Audio is not available for this generation."}
                </div>
              )}
              {waveformPeaks.length > 0 && (
                <div className="waveform" aria-label="Audio waveform">
                  <svg viewBox={`0 0 ${waveformPeaks.length} 40`} preserveAspectRatio="none" role="img">
                    {waveformPeaks.map((peak, idx) => {
                      const h = Math.max(2, Math.min(38, Math.round(peak * 38)));
                      const y = Math.round((40 - h) / 2);
                      return <rect key={`${idx}`} x={idx} y={y} width="0.8" height={h} rx="0.4" />;
                    })}
                  </svg>
                </div>
              )}
              <div className="help">Generated in {formatMs(selected.generation_time_ms)} · Duration {selected.duration_seconds}s</div>
              <div className="row">
                <button className="ghost" onClick={() => void createVariation()} disabled={state === "GENERATING"}>Create Variation</button>
                <button className="ghost" onClick={() => void regenerateMusic()} disabled={state === "GENERATING"}>Regenerate</button>
              </div>
              {selected.audio_url && (
                <a className="downloadLink" href={`${apiBase}${selected.audio_url}`} download>
                  Download WAV
                </a>
              )}
              <details className="generationDetails">
                <summary>Generation details</summary>
                <div className="help">Composed prompt: {selected.composed_prompt}</div>
                <div className="help">Model: {selected.model}</div>
                <div className="help">Status: {selected.status}</div>
              </details>
            </>
          )}
        </article>
      </div>

      <article className="card musicHistory">
        <h3>Generation History</h3>
        {history.length === 0 && <p className="help">No generations yet.</p>}
        <div className="historyList">
          {history.map((item) => (
            <button
              key={item.id}
              className={`historyItem ${selected?.id === item.id ? "active" : ""}`}
              type="button"
              onClick={() => setSelected(item)}
            >
              <div>
                <strong>{item.title}</strong>
                <div className="help">#{item.id} · {item.generation_label || "Original"} · {item.status}</div>
              </div>
              <div className="help">{new Date(item.created_at).toLocaleString()}</div>
            </button>
          ))}
        </div>
      </article>
    </section>
  );
}

