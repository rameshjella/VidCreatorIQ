from fastapi.testclient import TestClient

from app.api import routes as api_routes
from app.database import SessionLocal
from app.models import Scene
from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_dependencies_contract() -> None:
    response = client.get("/health/dependencies")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "dependencies" in payload
    assert "ffmpeg" in payload["dependencies"]
    assert "comfyui" in payload["dependencies"]
    assert "piper" in payload["dependencies"]
    assert "ready" in payload["dependencies"]["ffmpeg"]
    assert isinstance(payload["ready_for_generation"], bool)


def test_health_dependency_doctor_contract() -> None:
    response = client.get("/health/dependency-doctor")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "summary" in payload
    assert "blocking_issues" in payload["summary"]
    assert "issue_count" in payload["summary"]
    assert "findings" in payload
    assert isinstance(payload["findings"], list)
    assert "comfyui_checkpoints" in payload


def test_health_comfyui_checkpoints_contract() -> None:
    response = client.get("/health/comfyui-checkpoints")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "comfyui_checkpoints" in payload
    checkpoints = payload["comfyui_checkpoints"]
    assert "configured" in checkpoints
    assert "checkpoint_count" in checkpoints
    assert "sample_checkpoint_names" in checkpoints
    assert isinstance(checkpoints["sample_checkpoint_names"], list)


def test_create_project_and_fetch() -> None:
    payload = {
        "title": "Test Project",
        "script_text": "This is a valid test script with enough characters to pass validation.",
        "language": "en",
    }
    created = client.post("/projects", json=payload)
    assert created.status_code == 200
    assert created.json()["character_identity_prompt"] == ""
    assert created.json()["character_lora_tags"] == ""
    project_id = created.json()["id"]

    fetched = client.get(f"/projects/{project_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Test Project"


def test_update_scene_timeline_empty_payload() -> None:
    payload = {
        "title": "Timeline Project",
        "script_text": "This is another valid test script with enough characters for creation.",
        "language": "en",
    }
    created = client.post("/projects", json=payload)
    project_id = created.json()["id"]

    response = client.patch(f"/projects/{project_id}/scenes", json={"scenes": []})
    assert response.status_code == 200
    assert response.json() == []


def test_resume_job_requires_payload() -> None:
    response = client.post("/jobs/999999/resume", json={"failed_scene_index": 1})
    assert response.status_code == 404


def test_run_project_rejects_unknown_music_generation() -> None:
    created = client.post(
        "/projects",
        json={
            "title": "Music Validation",
            "script_text": "This is a valid test script with enough characters to pass validation.",
            "language": "en",
        },
    )
    assert created.status_code == 200
    project_id = created.json()["id"]

    response = client.post(
        f"/projects/{project_id}/run",
        json={"visual_mode": "basic", "music_generation_id": 99999999, "export_stems": True},
    )
    assert response.status_code == 400
    assert "music_generation_id" in response.text


def test_character_registry_and_scene_assignment() -> None:
    created = client.post(
        "/projects",
        json={
            "title": "Character Registry",
            "script_text": "This is a valid test script with enough characters to pass validation.",
            "language": "en",
        },
    )
    assert created.status_code == 200
    project_id = created.json()["id"]

    # Seed one scene so per-scene character assignment can be tested without running the full render pipeline.
    db = SessionLocal()
    try:
        db.add(
            Scene(
                project_id=project_id,
                scene_index=1,
                title="Scene 1",
                script_chunk="Maya enters the station.",
                description="",
                image_prompt="cinematic still",
                duration_seconds=4.0,
            )
        )
        db.commit()
        scene_id = int(db.query(Scene.id).filter(Scene.project_id == project_id).first()[0])
    finally:
        db.close()

    character = client.post(
        f"/projects/{project_id}/characters",
        json={
            "name": "Maya",
            "identity_prompt": "short silver bob, red raincoat",
            "lora_adapter": "maya_face_v2.safetensors",
            "lora_strength": 0.85,
            "notes": "Main protagonist",
        },
    )
    assert character.status_code == 200
    character_id = character.json()["id"]

    listing = client.get(f"/projects/{project_id}/characters")
    assert listing.status_code == 200
    assert any(c["id"] == character_id for c in listing.json())

    assigned = client.put(
        f"/projects/{project_id}/scenes/{scene_id}/characters",
        json={"assignments": [{"character_id": character_id, "role": "lead", "weight": 1.0}]},
    )
    assert assigned.status_code == 200
    assert assigned.json()[0]["character_id"] == character_id


def test_stems_package_endpoint_missing_job() -> None:
    response = client.get("/jobs/99999999/stems-package")
    assert response.status_code == 404


def test_run_project_rejects_invalid_cinematic_quality_profile() -> None:
    created = client.post(
        "/projects",
        json={
            "title": "Profile Validation",
            "script_text": "This is a valid test script with enough characters to pass validation.",
            "language": "en",
        },
    )
    assert created.status_code == 200
    project_id = created.json()["id"]

    response = client.post(
        f"/projects/{project_id}/run",
        json={"visual_mode": "cinematic", "cinematic_quality_profile": "ultra"},
    )
    assert response.status_code == 422


def test_true_motion_requires_comfyui_readiness(monkeypatch) -> None:
    created = client.post(
        "/projects",
        json={
            "title": "True Motion Readiness",
            "script_text": "This is a valid test script with enough characters to pass validation.",
            "language": "en",
        },
    )
    assert created.status_code == 200
    project_id = created.json()["id"]

    monkeypatch.setattr(api_routes, "_is_comfyui_ready", lambda: False)
    monkeypatch.setattr(api_routes.time, "sleep", lambda _: None)
    response = client.post(
        f"/projects/{project_id}/run",
        json={"visual_mode": "cinematic", "cinematic_quality_profile": "true_motion"},
    )
    assert response.status_code == 400
    assert "True Motion requires ComfyUI readiness" in response.text


def test_true_motion_recovers_from_transient_comfyui_readiness_failure(monkeypatch) -> None:
    created = client.post(
        "/projects",
        json={
            "title": "True Motion Retry",
            "script_text": "This is a valid test script with enough characters to pass validation.",
            "language": "en",
        },
    )
    assert created.status_code == 200
    project_id = created.json()["id"]

    readiness_results = iter([False, True])
    monkeypatch.setattr(api_routes, "_is_comfyui_ready", lambda: next(readiness_results))
    monkeypatch.setattr(api_routes, "_has_comfyui_checkpoints", lambda: True)
    monkeypatch.setattr(api_routes, "_has_temporal_video_workflow_nodes", lambda: True)
    monkeypatch.setattr(api_routes.time, "sleep", lambda _: None)

    response = client.post(
        f"/projects/{project_id}/run",
        json={"visual_mode": "cinematic", "cinematic_quality_profile": "true_motion"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_run_project_accepts_output_controls() -> None:
    created = client.post(
        "/projects",
        json={
            "title": "Output Controls",
            "script_text": "This is a valid test script with enough characters to pass validation.",
            "language": "ta",
        },
    )
    assert created.status_code == 200
    project_id = created.json()["id"]

    response = client.post(
        f"/projects/{project_id}/run",
        json={
            "visual_mode": "basic",
            "cinematic_quality_profile": "balanced",
            "output_resolution": "720p",
            "output_fps": 24,
            "burn_subtitles": False,
            "export_stems": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"


