# AI Movie Maker (Local Open-Source MVP)

AI Movie Maker converts a script into a narrated MP4 with one click.

## What This MVP Delivers

- React + Vite web UX for script upload/paste, dependency checks, timeline updates, and job monitoring
- FastAPI backend with local SQLite project history
- LangGraph multi-agent pipeline:
  - Director Agent
  - Storyboard Agent
  - Videographer Agent
  - Narrator Agent
  - Editor Agent
- Ollama integration for script-to-scene reasoning (with deterministic fallback)
- ComfyUI integration point for image generation (with local placeholder fallback)
- Piper integration for local neural TTS (with `pyttsx3` fallback)
- FFmpeg-based clip creation, subtitle generation, and final MP4 muxing
- AI Music Studio tab with real local text-to-music generation, variation, and persisted history

## Architecture

See `docs/architecture.md` for:
- High-level architecture diagram
- Sequence diagram
- Folder structure
- API design
- Database schema

## Requirements

- Python 3.11+
- FFmpeg in PATH (`ffmpeg -version`)
- Optional but recommended:
  - Ollama running locally (`ollama serve`)
  - A pulled model (`ollama pull llama3.1` or `ollama pull qwen2.5`)
  - Piper binary + voice model
  - ComfyUI local endpoint

## Setup (Windows/Linux)

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# Linux/macOS
# source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Create `.env` from `.env.example` and adjust paths:

```bash
copy .env.example .env
```

## Run Backend

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Run Frontend

```bash
cd ui
npm install
npm run dev -- --host 127.0.0.1 --port 8501
```

## Single-Command Launcher (Windows/Linux/macOS)

Use one command to install (optional), start API + UI in the same terminal, and stream all logs:

```bash
python run_ai_movie_maker.py --install
```

Useful variants:

```bash
# start without install (React UI default)
python run_ai_movie_maker.py

# keep legacy Streamlit UI
python run_ai_movie_maker.py --ui streamlit

# dev mode with API auto-reload
python run_ai_movie_maker.py --api-reload

# include RQ worker (requires REDIS_URL env)
python run_ai_movie_maker.py --with-worker

# include ComfyUI auto-start (requires COMFYUI_START_COMMAND)
python run_ai_movie_maker.py --with-comfyui

# include ComfyUI auto-discovery + auto-start (no COMFYUI_WORKDIR required)
python run_ai_movie_maker.py --with-comfyui-auto

# smoke-test startup and auto-stop
python run_ai_movie_maker.py --smoke-test
```

Logs are written to `logs/`:
- `logs/launcher_YYYYMMDD_HHMMSS.log` (combined)
- `logs/api.log`
- `logs/ui.log`
- `logs/worker.log` (when `--with-worker` is used)

UI stack:
- Default: React + Vite (`ui/`)
- Legacy fallback: Streamlit (`streamlit_app.py`) via `--ui streamlit`

## True ComfyUI Integration

The app now supports workflow-based generation for:

- Stable Diffusion image generation via `app/workflows/comfyui_sdxl_image.json`
- AnimateDiff video clip generation via `app/workflows/comfyui_animatediff_video.json`

Set these in `.env` if you keep custom workflow paths:

```bash
COMFYUI_URL=http://127.0.0.1:8188
COMFYUI_SD_WORKFLOW=./app/workflows/comfyui_sdxl_image.json
COMFYUI_ANIMATEDIFF_WORKFLOW=./app/workflows/comfyui_animatediff_video.json
```

For single-command startup with launcher-managed ComfyUI, configure:

```bash
COMFYUI_URL=http://127.0.0.1:8188
COMFYUI_START_COMMAND=python main.py --listen 127.0.0.1 --port 8188
COMFYUI_WORKDIR=C:/Path/To/ComfyUI
COMFYUI_STARTUP_TIMEOUT=180
```

Then run:

```bash
python run_ai_movie_maker.py --with-comfyui
```

If `COMFYUI_WORKDIR` is not set, you can use auto-discovery mode. The launcher tries common local paths such as `./ComfyUI`, `../ComfyUI`, `~/ComfyUI`, and Windows drive roots:

```bash
python run_ai_movie_maker.py --with-comfyui-auto
```

Optional custom path list for auto mode:

```bash
COMFYUI_AUTO_WORKDIRS=C:/AI/ComfyUI;D:/ComfyUI
```

For guaranteed execution against your exact exported workflow, set node IDs from your ComfyUI JSON export:

```bash
COMFYUI_SD_PROMPT_NODE_ID=6
COMFYUI_SD_SEED_NODE_ID=3
COMFYUI_SD_CHECKPOINT_NODE_ID=10
COMFYUI_SD_OUTPUT_NODE_ID=9
COMFYUI_AD_PROMPT_NODE_ID=1
COMFYUI_AD_SEED_NODE_ID=4
COMFYUI_AD_CHECKPOINT_NODE_ID=11
COMFYUI_AD_OUTPUT_NODE_ID=6
```

If IDs are not set, the app attempts class-type auto-detection.

You can auto-derive IDs from your exported workflows:

```bash
python scripts/derive_comfy_ids.py /path/to/sd_workflow.json /path/to/animatediff_workflow.json
```

## Queue Retry + Resume

- RQ retries are enabled with backoff via `.env`:
  - `RQ_RETRY_MAX=3`
  - `RQ_RETRY_INTERVALS=20,60,180`
- Resume failed jobs from a specific scene index in the UI (`Resume from scene index`).
- Reorder scenes and edit clip durations in the Streamlit timeline editor, then click **Save Timeline**.

Open:
- UI: `http://localhost:8501`
- FastAPI docs: `http://localhost:8000/docs`

## One-Click Flow

1. Paste/upload script in Streamlit.
2. Click **Create Project**.
3. Click **Generate Full Movie**.
4. Refresh job status and preview storyboard.
5. Download final MP4.

## Docker

```bash
docker compose up --build
```

Services:
- API: `http://localhost:8000`
- UI: `http://localhost:8501`

## Tests

```bash
pytest -q
```

## AI Music Studio

The React app includes a **Music Studio** tab for local generative music:

- Prompt + mood/style/energy/instrumentation controls
- Real model inference through local `transformers` + `torch`
- Variation generation from previous tracks
- SQLite-backed generation history
- WAV playback + download

Primary backend endpoints:

- `GET /music/health`
- `GET /music/models`
- `POST /music/generate`
- `GET /music/generations`
- `GET /music/generations/{id}`
- `POST /music/generations/{id}/variation`
- `GET /music/audio/{id}`

## Sample Script

Use `samples/sample_script.txt` for a quick first run.

## Future Enhancements

1. True image/video generation via Stable Diffusion + AnimateDiff/SVD workflow nodes.
2. Character consistency with LoRA embeddings and identity prompts.
3. Distributed task queue with retries and resumable pipelines.
4. Scene-level timeline editor in UI.
5. Automatic soundtrack and sound effects layers.

