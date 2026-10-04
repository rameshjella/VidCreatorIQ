from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
import json
import requests
from pathlib import Path
from shutil import which
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.database import get_db
from app.models import Job, MusicGeneration, Scene
from app.queue import enqueue_pipeline
from app.schemas import (
    CharacterCreate,
    CharacterOut,
    JobEventOut,
    JobOut,
    MovieRunResponse,
    ProjectCreate,
    ProjectOut,
    RegenerateSceneRequest,
    ResumeJobRequest,
    RunProjectRequest,
    SceneOut,
    SceneCharactersUpdateRequest,
    SceneCharacterAssignmentOut,
    SceneTimelineUpdateRequest,
)
from app.services.pipeline import MoviePipeline
from app.services.comfyui_workflow_client import ComfyUIWorkflowClient

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _resolve_binary(command: str) -> str | None:
    command = (command or "").strip()
    if not command:
        return None
    if Path(command).exists():
        return str(Path(command).resolve())
    return which(command)


def _describe_request_error(exc: Exception, url: str) -> str:
    """Turn a noisy requests/urllib3 exception into one readable line.

    ``str(exc)`` on a refused connection produces a ~300 character wall of
    nested HTTPConnectionPool/NewConnectionError text that breaks any card
    layout and tells a user nothing they can act on.
    """
    if isinstance(exc, requests.ConnectionError):
        return f"Not running at {url}"
    if isinstance(exc, requests.Timeout):
        return f"No response from {url}"
    message = str(exc).strip()
    return message.split("\n")[0][:120] or exc.__class__.__name__


@router.get("/health/dependencies")
def health_dependencies() -> dict:
    ffmpeg_resolved = _resolve_binary(settings.ffmpeg_bin)
    checkpoint_health = _comfyui_checkpoint_health()

    comfy_url = settings.comfyui_url.strip().rstrip("/")
    comfy_ready = False
    comfy_raw_error = ""
    if not comfy_url:
        comfy_detail = "Not configured"
        comfy_hint = "Set COMFYUI_URL in .env to enable Cinematic mode."
    else:
        try:
            response = requests.get(f"{comfy_url}/system_stats", timeout=3)
            comfy_ready = response.ok
            if response.ok:
                comfy_detail = f"Connected to {comfy_url}"
                comfy_hint = ""
            else:
                comfy_detail = f"Responded HTTP {response.status_code}"
                comfy_hint = "ComfyUI is running but returned an error."
        except requests.RequestException as exc:
            comfy_detail = _describe_request_error(exc, comfy_url)
            comfy_hint = "Start ComfyUI, or run: python run_ai_movie_maker.py --with-comfyui-auto"
            comfy_raw_error = str(exc)

    if comfy_ready and not checkpoint_health.get("has_checkpoints", False):
        comfy_hint = "Connected, but no checkpoints found. Cinematic mode needs a model installed."

    piper_bin_resolved = _resolve_binary(settings.piper_executable)
    piper_model_exists = bool(settings.piper_model_path.strip()) and Path(settings.piper_model_path).exists()
    piper_ready = bool(piper_bin_resolved and piper_model_exists)
    if not settings.piper_executable.strip() and not settings.piper_model_path.strip():
        piper_detail = "Not configured"
        piper_hint = "Optional. Edge neural TTS is used by default and needs no setup."
    elif piper_ready:
        piper_detail = "Ready"
        piper_hint = ""
    else:
        piper_detail = "Binary or model path is not valid"
        piper_hint = "Check PIPER_EXECUTABLE and PIPER_MODEL_PATH in .env."

    dependencies = {
        "ffmpeg": {
            "label": "FFmpeg",
            "ready": bool(ffmpeg_resolved),
            "optional": False,
            "configured": settings.ffmpeg_bin,
            "resolved_path": ffmpeg_resolved or "",
            "detail": "Ready" if ffmpeg_resolved else "Not found",
            "hint": ""
            if ffmpeg_resolved
            else "Install FFmpeg or set FFMPEG_BIN in .env. A bundled copy ships with imageio-ffmpeg.",
            "raw_error": "",
        },
        "comfyui": {
            "label": "ComfyUI",
            "ready": comfy_ready,
            # Rendering works without it; only Cinematic mode needs ComfyUI.
            "optional": True,
            "configured_url": settings.comfyui_url,
            "resolved_path": comfy_url,
            "detail": comfy_detail,
            "hint": comfy_hint,
            "raw_error": comfy_raw_error,
            "checkpoint_count": checkpoint_health.get("checkpoint_count", 0),
            "has_checkpoints": checkpoint_health.get("has_checkpoints", False),
            "checkpoint_detail": checkpoint_health.get("detail", ""),
        },
        "piper": {
            "label": "Piper TTS",
            "ready": piper_ready,
            "optional": True,
            "configured_executable": settings.piper_executable,
            "configured_model_path": settings.piper_model_path,
            "resolved_path": piper_bin_resolved or "",
            "resolved_executable": piper_bin_resolved or "",
            "model_exists": piper_model_exists,
            "detail": piper_detail,
            "hint": piper_hint,
            "raw_error": "",
        },
    }

    return {
        "status": "ok",
        "dependencies": dependencies,
        "ready_for_generation": dependencies["ffmpeg"]["ready"],
        "ready_for_cinematic": (
            dependencies["ffmpeg"]["ready"]
            and dependencies["comfyui"]["ready"]
            and dependencies["comfyui"]["has_checkpoints"]
        ),
    }


def _is_comfyui_ready() -> bool:
    comfy_url = settings.comfyui_url.strip()
    if not comfy_url:
        return False
    try:
        response = requests.get(f"{comfy_url.rstrip('/')}/system_stats", timeout=3)
        return response.ok
    except requests.RequestException:
        return False


def _has_comfyui_checkpoints() -> bool:
    return bool(_comfyui_checkpoint_health().get("has_checkpoints", False))


def _has_temporal_video_workflow_nodes() -> bool:
    try:
        payload = json.loads(Path(settings.comfyui_animatediff_workflow).read_text(encoding="utf-8"))
    except Exception:
        return False

    markers = ("animatediff", "ade_", "motionmodel", "svd", "videolinear")
    for node in payload.values() if isinstance(payload, dict) else []:
        class_type = str((node or {}).get("class_type", "")).lower() if isinstance(node, dict) else ""
        if any(marker in class_type for marker in markers):
            return True
    return False


def _estimate_script_runtime_seconds(script_text: str) -> int:
    words = len([w for w in (script_text or "").split() if w.strip()])
    # 150 wpm baseline, rounded to nearest second.
    return max(1, int(round(words * 60 / 150)))


def _resolve_cinematic_quality_profile(requested: str, script_text: str) -> str:
    requested = (requested or "balanced").strip().lower()
    if requested not in {"fast", "balanced", "true_motion"}:
        requested = "balanced"

    if requested == "fast":
        return "fast"

    comfy_ready = _is_comfyui_ready()
    has_checkpoints = _has_comfyui_checkpoints()
    has_temporal_graph = _has_temporal_video_workflow_nodes()

    if requested == "true_motion":
        if not comfy_ready:
            raise HTTPException(
                status_code=400,
                detail="True Motion requires ComfyUI readiness. Configure COMFYUI_URL and ensure the server is running.",
            )
        if not has_checkpoints:
            raise HTTPException(
                status_code=400,
                detail=(
                    "True Motion requires at least one ComfyUI checkpoint model. "
                    "Add a .safetensors/.ckpt file and verify /health/comfyui-checkpoints."
                ),
            )
        if not has_temporal_graph:
            raise HTTPException(
                status_code=400,
                detail=(
                    "True Motion requires a temporal ComfyUI video workflow (AnimateDiff/SVD). "
                    "Update COMFYUI_ANIMATEDIFF_WORKFLOW to a motion-capable graph."
                ),
            )
        return "true_motion"

    # Balanced: prefer speed unless motion path is healthy and script is short.
    if not (comfy_ready and has_checkpoints and has_temporal_graph):
        return "fast"

    est_runtime = _estimate_script_runtime_seconds(script_text)
    if est_runtime > int(settings.render_cinematic_balanced_max_runtime_seconds):
        return "fast"
    return "true_motion"


def _comfyui_checkpoint_health(sample_limit: int = 8) -> dict:
    comfy_url = settings.comfyui_url.strip()
    endpoint = f"{comfy_url.rstrip('/')}/object_info/CheckpointLoaderSimple" if comfy_url else ""
    payload = {
        "configured": bool(comfy_url),
        "configured_url": comfy_url,
        "endpoint": endpoint,
        "reachable": False,
        "schema_recognized": False,
        "checkpoint_count": 0,
        "sample_checkpoint_names": [],
        "has_checkpoints": False,
        "detail": "COMFYUI_URL is not configured",
    }
    if not comfy_url:
        return payload

    try:
        response = requests.get(endpoint, timeout=6)
        response.raise_for_status()
        payload["reachable"] = True
    except requests.RequestException as exc:
        payload["detail"] = f"Checkpoint endpoint not reachable: {exc}"
        return payload

    try:
        data = response.json()
    except ValueError:
        preview = (response.text or "").strip()[:220]
        payload["detail"] = f"Checkpoint endpoint returned non-JSON: {preview}"
        return payload

    names, schema_recognized = ComfyUIWorkflowClient._extract_checkpoint_names(data)
    payload["schema_recognized"] = schema_recognized
    payload["checkpoint_count"] = len(names)
    payload["sample_checkpoint_names"] = names[:sample_limit]
    payload["has_checkpoints"] = len(names) > 0
    if not schema_recognized:
        payload["detail"] = "Unable to parse ckpt_name schema from CheckpointLoaderSimple"
    elif names:
        payload["detail"] = f"Found {len(names)} checkpoints"
    else:
        payload["detail"] = "ComfyUI reports zero checkpoints"
    return payload


@router.get("/health/comfyui-checkpoints")
def health_comfyui_checkpoints() -> dict:
    return {
        "status": "ok",
        "comfyui_checkpoints": _comfyui_checkpoint_health(),
    }


@router.get("/health/dependency-doctor")
def health_dependency_doctor() -> dict:
    findings: list[dict] = []
    checkpoint_health = _comfyui_checkpoint_health()

    ffmpeg_configured = settings.ffmpeg_bin.strip()
    ffmpeg_resolved = _resolve_binary(ffmpeg_configured)
    if not ffmpeg_resolved:
        findings.append(
            {
                "dependency": "ffmpeg",
                "severity": "error",
                "issue": "FFmpeg binary is not resolvable",
                "missing": {
                    "configured_ffmpeg_bin": ffmpeg_configured,
                    "resolved_path": "",
                },
                "suggested_fixes": [
                    "Install FFmpeg and ensure it is available in PATH.",
                    "Set FFMPEG_BIN in .env to the full path of ffmpeg executable.",
                    "Example (Windows): FFMPEG_BIN=C:\\ffmpeg\\bin\\ffmpeg.exe",
                ],
            }
        )

    comfy_url = settings.comfyui_url.strip()
    if not comfy_url:
        findings.append(
            {
                "dependency": "comfyui",
                "severity": "warning",
                "issue": "COMFYUI_URL is not configured",
                "missing": {
                    "comfyui_url": "",
                },
                "suggested_fixes": [
                    "Start ComfyUI locally and set COMFYUI_URL in .env.",
                    "Example: COMFYUI_URL=http://127.0.0.1:8188",
                ],
            }
        )
    else:
        try:
            stats_resp = requests.get(f"{comfy_url.rstrip('/')}/system_stats", timeout=3)
            if not stats_resp.ok:
                findings.append(
                    {
                        "dependency": "comfyui",
                        "severity": "warning",
                        "issue": "ComfyUI endpoint is configured but not healthy",
                        "missing": {
                            "comfyui_url": comfy_url,
                            "http_status": stats_resp.status_code,
                        },
                        "suggested_fixes": [
                            "Ensure ComfyUI server is running and reachable.",
                            "Verify COMFYUI_URL points to the correct host and port.",
                        ],
                    }
                )
        except requests.RequestException as exc:
            findings.append(
                {
                    "dependency": "comfyui",
                    "severity": "warning",
                    "issue": "ComfyUI connection failed",
                    "missing": {
                        "comfyui_url": comfy_url,
                        "error": str(exc),
                    },
                    "suggested_fixes": [
                        "Start ComfyUI and verify the URL manually in a browser.",
                        "Check firewall/network settings if ComfyUI is remote.",
                    ],
                }
            )

    if checkpoint_health.get("configured") and checkpoint_health.get("reachable"):
        if not checkpoint_health.get("schema_recognized"):
            findings.append(
                {
                    "dependency": "comfyui",
                    "severity": "warning",
                    "issue": "ComfyUI checkpoint schema is not recognized",
                    "missing": {
                        "endpoint": checkpoint_health.get("endpoint", ""),
                        "detail": checkpoint_health.get("detail", ""),
                    },
                    "suggested_fixes": [
                        "Update ComfyUI to a version with standard CheckpointLoaderSimple schema.",
                        "Verify /object_info/CheckpointLoaderSimple returns ckpt_name options.",
                    ],
                }
            )
        elif not checkpoint_health.get("has_checkpoints"):
            findings.append(
                {
                    "dependency": "comfyui",
                    "severity": "error",
                    "issue": "ComfyUI reports zero checkpoints in CheckpointLoaderSimple",
                    "missing": {
                        "endpoint": checkpoint_health.get("endpoint", ""),
                        "checkpoint_count": checkpoint_health.get("checkpoint_count", 0),
                    },
                    "suggested_fixes": [
                        "Add model files to ComfyUI checkpoints directories.",
                        "Configure model search paths via COMFYUI_MODEL_PATHS and/or --extra-model-paths-config.",
                    ],
                }
            )

    workflow_checks = [
        ("comfyui_sd_workflow", settings.comfyui_sd_workflow),
        ("comfyui_animatediff_workflow", settings.comfyui_animatediff_workflow),
    ]
    for key, workflow_path in workflow_checks:
        if not Path(workflow_path).exists():
            findings.append(
                {
                    "dependency": "comfyui",
                    "severity": "warning",
                    "issue": f"Workflow file is missing: {key}",
                    "missing": {
                        "setting": key,
                        "path": workflow_path,
                    },
                    "suggested_fixes": [
                        f"Set {key.upper()} to an existing workflow JSON path.",
                        "Keep default app/workflows JSON files or export workflows from ComfyUI.",
                    ],
                }
            )

    piper_exe = settings.piper_executable.strip()
    piper_model = settings.piper_model_path.strip()
    piper_exe_resolved = _resolve_binary(piper_exe) if piper_exe else None
    piper_model_exists = Path(piper_model).exists() if piper_model else False
    if not piper_exe or not piper_model:
        findings.append(
            {
                "dependency": "piper",
                "severity": "info",
                "issue": "Piper is not configured (fallback TTS will be used)",
                "missing": {
                    "piper_executable": piper_exe,
                    "piper_model_path": piper_model,
                },
                "suggested_fixes": [
                    "Set PIPER_EXECUTABLE and PIPER_MODEL_PATH in .env for neural voice generation.",
                    "If fallback is acceptable, this can be ignored.",
                ],
            }
        )
    elif not piper_exe_resolved or not piper_model_exists:
        findings.append(
            {
                "dependency": "piper",
                "severity": "warning",
                "issue": "Piper path configuration is invalid",
                "missing": {
                    "piper_executable": piper_exe,
                    "resolved_executable": piper_exe_resolved or "",
                    "piper_model_path": piper_model,
                    "model_exists": piper_model_exists,
                },
                "suggested_fixes": [
                    "Set PIPER_EXECUTABLE to a valid piper binary path.",
                    "Set PIPER_MODEL_PATH to an existing .onnx voice model.",
                ],
            }
        )

    has_blockers = any(item["severity"] == "error" for item in findings)
    return {
        "status": "ok",
        "summary": {
            "blocking_issues": has_blockers,
            "issue_count": len(findings),
        },
        "findings": findings,
        "comfyui_checkpoints": checkpoint_health,
    }


@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = crud.create_project(
        db,
        payload.title,
        payload.script_text,
        payload.language,
        payload.character_identity_prompt,
        ",".join(tag.strip() for tag in payload.character_lora_tags if tag.strip()),
    )

    if payload.character_identity_prompt or payload.character_lora_tags:
        adapters = [tag.strip() for tag in payload.character_lora_tags if tag.strip()]
        if not adapters:
            adapters = [""]
        for idx, adapter in enumerate(adapters, start=1):
            crud.create_project_character(
                db,
                project.id,
                name="Lead" if idx == 1 else f"Lead Variant {idx}",
                identity_prompt=payload.character_identity_prompt,
                lora_adapter=adapter,
                lora_strength=0.8,
                notes="Seeded from project create payload",
            )
        project = crud.get_project(db, project.id) or project
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return crud.list_projects(db)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/projects/{project_id}/characters", response_model=list[CharacterOut])
def list_project_characters(project_id: int, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return crud.list_project_characters(db, project_id)


@router.post("/projects/{project_id}/characters", response_model=CharacterOut)
def create_project_character(project_id: int, payload: CharacterCreate, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return crud.create_project_character(
        db,
        project_id,
        name=payload.name,
        identity_prompt=payload.identity_prompt,
        lora_adapter=payload.lora_adapter,
        lora_strength=payload.lora_strength,
        notes=payload.notes,
    )


@router.put("/projects/{project_id}/scenes/{scene_id}/characters", response_model=list[SceneCharacterAssignmentOut])
def update_scene_characters(
    project_id: int,
    scene_id: int,
    payload: SceneCharactersUpdateRequest,
    db: Session = Depends(get_db),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    scene = db.query(Scene).filter(Scene.id == scene_id, Scene.project_id == project_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    valid_character_ids = {c.id for c in crud.list_project_characters(db, project_id)}
    assignments: list[tuple[int, str, float]] = []
    for item in payload.assignments:
        if item.character_id not in valid_character_ids:
            raise HTTPException(status_code=400, detail=f"character_id {item.character_id} does not belong to project")
        assignments.append((item.character_id, item.role, item.weight))

    return crud.set_scene_character_assignments(db, scene, assignments)


def _run_pipeline(
    project_id: int,
    job_id: int,
    resume_from_scene_index: int | None = None,
    visual_mode: str = "basic",
    cinematic_quality_profile: str = "balanced",
    output_resolution: str = "1080p",
    output_fps: int = 30,
    burn_subtitles: bool | None = None,
    music_path: str | None = None,
    export_stems: bool = True,
):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        project = crud.get_project(db, project_id)
        job = crud.get_job(db, job_id)
        if not project or not job:
            return
        pipeline = MoviePipeline(db)
        pipeline.run(
            project,
            job,
            resume=True,
            resume_from_scene_index=resume_from_scene_index,
            visual_mode=visual_mode,
            cinematic_quality_profile=cinematic_quality_profile,
            output_resolution=output_resolution,
            output_fps=output_fps,
            burn_subtitles=burn_subtitles,
            music_path=music_path,
            export_stems=export_stems,
        )
    except Exception as exc:
        job = crud.get_job(db, job_id)
        if job:
            MoviePipeline(db).mark_failure(job, exc)
    finally:
        db.close()


@router.post("/projects/{project_id}/run", response_model=MovieRunResponse)
def run_project(
    project_id: int,
    payload: RunProjectRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    visual_mode = (payload.visual_mode or "basic").strip().lower()
    if visual_mode not in {"basic", "cinematic"}:
        raise HTTPException(status_code=400, detail="visual_mode must be 'basic' or 'cinematic'")

    effective_profile = "balanced"
    if visual_mode == "cinematic":
        effective_profile = _resolve_cinematic_quality_profile(
            payload.cinematic_quality_profile,
            project.script_text,
        )

    music_path: str | None = None
    if payload.music_generation_id is not None:
        music_record = (
            db.query(MusicGeneration)
            .filter(MusicGeneration.id == payload.music_generation_id)
            .first()
        )
        if not music_record or music_record.status != "completed" or not music_record.audio_path:
            raise HTTPException(status_code=400, detail="music_generation_id must reference a completed track")
        music_path = music_record.audio_path

    job = crud.create_job(db, project_id)
    queue_job_id = enqueue_pipeline(
        project_id,
        job.id,
        resume_from_scene_index=None,
        visual_mode=visual_mode,
        cinematic_quality_profile=effective_profile,
        output_resolution=payload.output_resolution,
        output_fps=payload.output_fps,
        burn_subtitles=payload.burn_subtitles,
        music_path=music_path,
        export_stems=payload.export_stems,
    )
    if queue_job_id:
        crud.update_job_queue_id(db, job, queue_job_id)
    else:
        background_tasks.add_task(
            _run_pipeline,
            project_id,
            job.id,
            None,
            visual_mode,
            effective_profile,
            payload.output_resolution,
            payload.output_fps,
            payload.burn_subtitles,
            music_path,
            payload.export_stems,
        )
    return {"job_id": job.id, "project_id": project_id, "status": "queued"}


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/events", response_model=list[JobEventOut])
def get_job_events(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return crud.list_job_events(db, job_id)


@router.post("/jobs/{job_id}/resume", response_model=MovieRunResponse)
def resume_job(
    job_id: int,
    payload: ResumeJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    project = crud.get_project(db, job.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    queue_job_id = enqueue_pipeline(
        project.id,
        job.id,
        resume_from_scene_index=payload.failed_scene_index,
        visual_mode="basic",
        cinematic_quality_profile="fast",
        output_resolution="1080p",
        output_fps=30,
        burn_subtitles=None,
    )
    if queue_job_id:
        crud.update_job_queue_id(db, job, queue_job_id)
    else:
        background_tasks.add_task(_run_pipeline, project.id, job.id, payload.failed_scene_index)
    return {"job_id": job.id, "project_id": project.id, "status": "queued"}


@router.patch("/projects/{project_id}/scenes", response_model=list[SceneOut])
def update_scene_timeline(project_id: int, payload: SceneTimelineUpdateRequest, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    updates = [(item.scene_id, item.scene_index, item.duration_seconds) for item in payload.scenes]
    return crud.update_scene_timeline(db, project_id, updates)


@router.post("/projects/{project_id}/scenes/regenerate", response_model=SceneOut)
def regenerate_scene(project_id: int, payload: RegenerateSceneRequest, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    scene = db.query(Scene).filter(Scene.id == payload.scene_id, Scene.project_id == project_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    updated = MoviePipeline(db).regenerate_scene(project, scene)
    return updated


@router.get("/projects/{project_id}/download")
def download_movie(project_id: int, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    latest_job = (
        db.query(Job)
        .filter(Job.project_id == project_id, Job.status == "completed")
        .order_by(Job.updated_at.desc())
        .first()
    )
    if not latest_job or not latest_job.output_video_path:
        raise HTTPException(status_code=404, detail="Final video not found")

    return FileResponse(latest_job.output_video_path, media_type="video/mp4", filename="ai_movie.mp4")


