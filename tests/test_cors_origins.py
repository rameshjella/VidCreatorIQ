"""CORS regression tests.

The launcher serves the UI on port 8501, but ``UI_ALLOWED_ORIGINS`` in .env
listed only 5173. Because the configured value *replaced* the defaults, every
preflight from 8501 returned 400 and the UI could not create projects.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app, resolve_allowed_origins

UI_ORIGINS = [
    "http://127.0.0.1:8501",
    "http://localhost:8501",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://localhost:4173",
    "http://127.0.0.1:3000",
]

WRITE_ENDPOINTS = [
    ("POST", "/projects"),
    ("POST", "/tts/preview"),
    ("PATCH", "/projects/1/scenes"),
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize(
    "configured",
    [
        # The exact value that was breaking the launcher UI.
        "http://127.0.0.1:5173,http://localhost:5173",
        None,
        "",
        "http://127.0.0.1:8501,http://localhost:8501",
    ],
)
def test_launcher_origin_survives_any_configuration(configured: str | None) -> None:
    """Port 8501 must be allowed no matter what .env says."""
    origins = resolve_allowed_origins(configured)
    assert "http://127.0.0.1:8501" in origins
    assert "http://localhost:8501" in origins


def test_configured_origins_are_added_not_substituted() -> None:
    origins = resolve_allowed_origins("https://studio.example.com")
    assert "https://studio.example.com" in origins
    assert "http://127.0.0.1:8501" in origins, "defaults must survive"


def test_origins_are_deduplicated_and_normalised() -> None:
    origins = resolve_allowed_origins("http://127.0.0.1:8501/,http://127.0.0.1:8501")
    assert origins.count("http://127.0.0.1:8501") == 1


@pytest.mark.parametrize("origin", UI_ORIGINS)
@pytest.mark.parametrize("method,path", WRITE_ENDPOINTS)
def test_preflight_succeeds(client: TestClient, origin: str, method: str, path: str) -> None:
    response = client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200, f"{method} {path} from {origin}"
    assert response.headers.get("access-control-allow-origin")


def test_preflight_from_arbitrary_localhost_port(client: TestClient) -> None:
    """Any localhost port should work, so a custom --port never breaks the UI."""
    response = client.options(
        "/projects",
        headers={
            "Origin": "http://localhost:61234",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200

