"""Storyboard data path: project list and project-level artifact resolution.

The Storyboard was previously unreachable because navigation was gated on the
in-memory project. It now loads any past project through
``GET /projects/{id}/artifacts``, which resolves that project's most recent
render so the UI never has to track job IDs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def rendered_project(client: TestClient) -> dict:
    """Newest project that actually produced a video, or skip."""
    response = client.get("/projects")
    assert response.status_code == 200
    for project in reversed(response.json()):
        if not project["scenes"]:
            continue
        artifacts = client.get(f"/projects/{project['id']}/artifacts")
        if artifacts.status_code == 200 and artifacts.json().get("video_url"):
            return artifacts.json()
    pytest.skip("No completed render in the database; run scripts/smoketest_api.py first")


def test_project_list_is_available(client: TestClient) -> None:
    response = client.get("/projects")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_unknown_project_artifacts_returns_404(client: TestClient) -> None:
    assert client.get("/projects/99999999/artifacts").status_code == 404


def test_artifacts_expose_final_movie(rendered_project: dict) -> None:
    assert rendered_project["video_url"].endswith(".mp4")
    assert rendered_project["scenes"], "a rendered project must report its scenes"


def test_every_scene_has_storyboard_fields(rendered_project: dict) -> None:
    """The storyboard card needs text, art and a runtime for each scene."""
    for scene in rendered_project["scenes"]:
        index = scene["scene_index"]
        assert scene.get("script_chunk"), f"scene {index} has no text"
        assert scene.get("image_url"), f"scene {index} has no artwork"
        assert scene["duration_seconds"] > 0, f"scene {index} has no duration"


def test_scene_media_urls_resolve(client: TestClient, rendered_project: dict) -> None:
    """A URL in the payload that 404s would render as a broken storyboard tile."""
    for scene in rendered_project["scenes"]:
        for key in ("image_url", "narration_url"):
            url = scene.get(key)
            if not url:
                continue
            path = url.split("/static", 1)[-1]
            response = client.head(f"/static{path}")
            assert response.status_code == 200, f"scene {scene['scene_index']} {key} is dead"

