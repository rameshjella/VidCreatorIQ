from fastapi.testclient import TestClient

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


