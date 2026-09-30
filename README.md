# VidCreatorIQ

Turn a script into a finished, narrated 1080p film — locally.

Paste a script, pick a voice, press generate. VidCreatorIQ splits it into
scenes, narrates each one with neural TTS, illustrates every beat, and masters
a broadcast-ready MP4 with burned-in captions and mixed audio.

---

## Quick start

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows
# source .venv/bin/activate       # Linux/macOS

pip install -r requirements.txt
copy .env.example .env            # cp on Linux/macOS

python run_ai_movie_maker.py --install
```

Then open **<http://127.0.0.1:8501>**. API docs are at <http://127.0.0.1:8000/docs>.

The only hard requirement is **Python 3.11+**. FFmpeg is bundled via
`imageio-ffmpeg` if it is not on your PATH, and the default voice
(Microsoft Edge neural TTS) needs no API key.

### Verify it works

```bash
python scripts/smoketest_render.py   # services only, no server needed
python scripts/smoketest_api.py      # full stack; API must be running
pytest -q                            # 62 tests
```

`smoketest_api.py` asserts a real, playable MP4 with both streams:

```
[100.0%] done  Movie ready - 13.3s, 1920x1080
OK  final MP4      3552 KB  video/mp4
OK  narration MP3   312 KB  audio/mpeg
OK  poster JPG      144 KB  image/jpeg
PASS - full stack produced a real, downloadable movie.
```

---

## What you get

Every render produces:

| Artifact | Format |
|---|---|
| Final movie | 1920x1080 H.264, 30 fps, CRF 20, `+faststart` |
| Audio track | AAC 192 kbps, 44.1 kHz, mastered to -16 LUFS |
| Narration | MP3 192 kbps, 44.1 kHz |
| Captions | Burned in, plus `.srt` and `.vtt` sidecars |
| Poster | JPG frame |
| Per scene | Image, clip, narration, subtitle |

---

## The web UI

Seven views, light theme by default (dark is one click away and persists):

| View | Purpose |
|---|---|
| **Script Studio** | Write or paste a script, choose render settings |
| **Storyboard** | Scene cards, proportional timeline, project library |
| **Voice Studio** | Pick a narration engine and voice, preview instantly |
| **Music Studio** | Generate an original score, with variations and history |
| **Render Console** | Live progress, stage stepper, streaming activity log |
| **Preview & Export** | Play the film with captions, download every asset |
| **System Health** | Dependency status and output profile |

Press <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>K</kbd> for the command palette.
No view is gated — each one is always reachable and explains what to do next.

---

## Narration engines

Seven providers, tried in order and skipped silently when unconfigured. The
default needs no account.

| Provider | Quality | Requires |
|---|---|---|
| ElevenLabs | Highest | `ELEVENLABS_API_KEY` |
| OpenAI | Very high | `OPENAI_API_KEY` |
| Azure Speech | Very high | `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` |
| Google Cloud | High | `GOOGLE_APPLICATION_CREDENTIALS` |
| **Edge** *(default)* | High | nothing — free and neural |
| Piper | Medium | local binary + voice model |
| pyttsx3 | Low | always available (last-resort fallback) |

Set the order in `.env`:

```bash
TTS_PROVIDER=edge
TTS_FALLBACK_CHAIN=edge,openai,elevenlabs,azure,google,piper,pyttsx3
```

Regardless of engine, output is normalised to -16 LUFS, trimmed of leading and
trailing silence, and encoded to MP3 192 kbps. Results are cached by
`sha256(text + voice + provider + params)`, so re-rendering never re-bills an API.

---

## Configuration

Everything lives in `.env` — see `.env.example` for the annotated full set.

```bash
# Render profile
RENDER_WIDTH=1920
RENDER_HEIGHT=1080
RENDER_FPS=30
RENDER_CRF=20
RENDER_LOUDNESS_LUFS=-16
RENDER_TRANSITION=fade
RENDER_TRANSITION_SECONDS=0.5
RENDER_KEN_BURNS=true
RENDER_BURN_SUBTITLES=true

# Binaries (auto-detected if omitted)
FFMPEG_BIN=
FFPROBE_BIN=

# Web
UI_ALLOWED_ORIGINS=http://127.0.0.1:8501,http://localhost:8501
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### Visual modes

- **Fast** (default) — designed gradient art cards with Ken Burns motion.
  Renders in seconds, no models required.
- **Cinematic** — diffusion frames via ComfyUI. Much slower and needs
  checkpoints installed; falls back to art cards with a logged warning.

---

## Optional integrations

### Ollama — smarter scene planning

```bash
ollama serve
ollama pull llama3.1
```

Without it, a deterministic splitter is used instead.

### ComfyUI — diffusion imagery

```bash
COMFYUI_URL=http://127.0.0.1:8188
COMFYUI_SD_WORKFLOW=./app/workflows/comfyui_sdxl_image.json
COMFYUI_ANIMATEDIFF_WORKFLOW=./app/workflows/comfyui_animatediff_video.json
```

Launch it alongside the app:

```bash
python run_ai_movie_maker.py --with-comfyui       # uses COMFYUI_WORKDIR
python run_ai_movie_maker.py --with-comfyui-auto  # auto-discovers the install
```

Node IDs are auto-detected by class type. To pin them explicitly, derive them
from your own export:

```bash
python scripts/derive_comfy_ids.py sd_workflow.json animatediff_workflow.json
```

### Redis — queued jobs with retry

```bash
REDIS_URL=redis://localhost:6379
python run_ai_movie_maker.py --with-worker
```

Enables retry with backoff (`RQ_RETRY_MAX`, `RQ_RETRY_INTERVALS`), cancel, and
resume-from-scene.

---

## Launcher reference

```bash
python run_ai_movie_maker.py [options]
```

| Option | Effect |
|---|---|
| `--install` | Install Python and npm dependencies first |
| `--api-reload` | Auto-reload the API on code changes |
| `--with-worker` | Start an RQ worker (needs `REDIS_URL`) |
| `--with-comfyui` | Start ComfyUI from `COMFYUI_WORKDIR` |
| `--with-comfyui-auto` | Find and start ComfyUI automatically |
| `--music-warmup` | Preload the music model so the first track is fast |
| `--smoke-test` | Start everything, verify, then exit |

Logs stream to the terminal and to `logs/` (`api.log`, `ui.log`, `worker.log`,
and a combined `launcher_*.log`).

---

## Docker

```bash
docker compose up --build
```

API on `:8000`, UI on `:8501`.

---

## Troubleshooting

**Buttons do nothing; console shows a CORS error**
`UI_ALLOWED_ORIGINS` is *added to* the built-in defaults, and any localhost
port is accepted, so this should not occur. If it does, confirm
`VITE_API_BASE_URL` points at the right API.

**Storyboard is empty**
Open a past project from the library at the bottom of the Storyboard view, or
generate a new one. Projects persist in `ai_movie_maker.db`.

**System Health shows ComfyUI as "Not running"**
Expected unless you started it. ComfyUI is **optional** — it only powers
Cinematic mode, and `ready_for_generation` stays true without it. `WinError
10061` / connection refused simply means nothing is listening on port 8188.
Start it with `python run_ai_movie_maker.py --with-comfyui-auto`, or leave it
off and use Fast mode.

**Music Studio says "Preparing"**
The model loads lazily on first use and is slow on CPU. Preload it with
`python run_ai_movie_maker.py --music-warmup`.

**Render fails at the assembly stage**
Check the Render Console log. Every output is verified with `ffprobe`, so a
failure here means a genuinely bad file rather than a silent corruption.

**Video and audio drift apart**
Should be impossible — narration is synthesised first and its measured
duration drives scene length. If you see it, file the `ffprobe` output.

**UI still looks unstyled after an update**
Restart the dev server so Vite picks up the new stylesheet
(`python run_ai_movie_maker.py`), or rebuild with `cd ui && npm run build`.

---

## Project layout

```text
app/
  api/          FastAPI routes
  agents/       LangGraph pipeline
  services/
    tts/        Multi-provider narration
    render_service.py   Normalise, concat, master, verify
    ffmpeg_runner.py    Binary resolution + ffprobe validation
  workflows/    ComfyUI graph templates
ui/src/
  styles/tokens.css   All design tokens
  styles.css          Component layer
  App.tsx             Views and shell
scripts/        Smoke tests and utilities
tests/          pytest suite
docs/architecture.md
```

Deeper design notes — diagrams, schema, the render pipeline's failure modes,
and the design-token system — are in
**[docs/architecture.md](docs/architecture.md)**.

---

## Roadmap

1. Character consistency via LoRA embeddings and identity prompts
2. Scene-level timeline editing with drag-to-reorder
3. Automatic sound-effects layer
4. Music bed auto-ducking under narration
5. Multi-track export (stems) for external NLE finishing

