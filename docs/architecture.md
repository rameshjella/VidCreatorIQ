# AI Movie Maker Architecture

## High-Level Architecture Diagram

```mermaid
graph TD
    U[Streamlit UI] -->|REST| A[FastAPI Backend]
    A --> D[(SQLite)]
    A --> G[LangGraph Agents]
    G --> O[Ollama LLM]
    A --> I[Image Service\nComfyUI or Placeholder]
    A --> T[TTS Service\nPiper or pyttsx3]
    A --> F[FFmpeg Video Service]
    F --> W[(Workspace Assets)]
    A --> W
```

## Sequence Diagram

```mermaid
sequenceDiagram
    participant User
    participant UI as Streamlit
    participant API as FastAPI
    participant DB as SQLite
    participant AG as LangGraph Agents
    participant GEN as Asset Services
    participant FF as FFmpeg

    User->>UI: Paste/upload script + click Generate
    UI->>API: POST /projects
    API->>DB: Save project
    UI->>API: POST /projects/{id}/run
    API->>DB: Create job
    API->>AG: Director -> Storyboard -> Videographer -> Narrator -> Editor
    AG-->>API: Scene plan + prompts
    API->>GEN: Generate images + audio + per-scene subtitles
    API->>FF: image->clips, concat clips/audio, mux subtitles
    FF-->>API: final_movie.mp4
    API->>DB: Update job output path
    UI->>API: GET /jobs/{id}
    UI->>API: GET /projects/{id}/download
    API-->>UI: MP4 stream
```

## Folder Structure

```text
app/
  api/routes.py
  agents/graph.py
  services/
  config.py
  database.py
  models.py
  schemas.py
  crud.py
streamlit_app.py
docs/architecture.md
samples/sample_script.txt
tests/
```

## Database Schema

- `projects`: id, title, script_text, language, status, timestamps
- `scenes`: id, project_id, scene_index, script_chunk, description, image/video/audio/subtitle paths, duration
- `jobs`: id, project_id, status, stage, message, output_video_path, timestamps

## API Design

- `GET /health`
- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`
- `POST /projects/{project_id}/run`
- `GET /jobs/{job_id}`
- `POST /projects/{project_id}/scenes/regenerate`
- `GET /projects/{project_id}/download`

## Agent Responsibilities

- **Director Agent**: split script, infer style/mood, structure scenes
- **Storyboard Agent**: refine scene prompts for image generation
- **Videographer Agent**: coordinate scene clip generation
- **Narrator Agent**: prepare narration text and speech synthesis
- **Editor Agent**: merge clips, voice, and subtitles into final movie

