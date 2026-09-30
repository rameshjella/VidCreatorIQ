"""System Health dependency reporting.

A refused ComfyUI connection used to surface the raw urllib3 exception:

    HTTPConnectionPool(host='127.0.0.1', port=8188): Max retries exceeded with
    url: /system_stats (Caused by NewConnectionError(...[WinError 10061]...))

That is ~300 characters of nested exception text. It broke the card layout and
told the user nothing actionable.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

REQUIRED_FIELDS = {"ready", "detail", "label", "optional", "hint", "raw_error"}


@pytest.fixture
def comfyui_refused():
    """Simulate ComfyUI not running, exactly as Windows reports it."""
    boom = requests.ConnectionError(
        "HTTPConnectionPool(host='127.0.0.1', port=8188): Max retries exceeded "
        "with url: /system_stats (Caused by NewConnectionError(\"HTTPConnection"
        "(host='127.0.0.1', port=8188): Failed to establish a new connection: "
        "[WinError 10061] No connection could be made because the target "
        "machine actively refused it\"))"
    )
    with patch("app.api.routes.requests.get", side_effect=boom):
        yield


def test_every_dependency_has_the_widget_contract() -> None:
    payload = client.get("/health/dependencies").json()
    for name, info in payload["dependencies"].items():
        missing = REQUIRED_FIELDS - info.keys()
        assert not missing, f"{name} is missing {missing}"


def test_refused_comfyui_is_summarised(comfyui_refused) -> None:
    comfy = client.get("/health/dependencies").json()["dependencies"]["comfyui"]

    assert comfy["ready"] is False
    assert comfy["detail"] == "Not running at http://127.0.0.1:8188"
    # The detail line must stay short enough to render on one or two lines.
    assert len(comfy["detail"]) < 80
    assert "HTTPConnectionPool" not in comfy["detail"]
    assert "WinError" not in comfy["detail"]
    assert "Traceback" not in comfy["detail"]


def test_refused_comfyui_offers_a_next_step(comfyui_refused) -> None:
    comfy = client.get("/health/dependencies").json()["dependencies"]["comfyui"]
    assert "--with-comfyui-auto" in comfy["hint"]


def test_full_error_is_preserved_for_debugging(comfyui_refused) -> None:
    """Summarised for humans, but nothing is lost."""
    comfy = client.get("/health/dependencies").json()["dependencies"]["comfyui"]
    assert "WinError 10061" in comfy["raw_error"]


def test_comfyui_is_optional_and_ffmpeg_is_not(comfyui_refused) -> None:
    """A stopped ComfyUI must not read as a broken install."""
    deps = client.get("/health/dependencies").json()["dependencies"]
    assert deps["comfyui"]["optional"] is True
    assert deps["piper"]["optional"] is True
    assert deps["ffmpeg"]["optional"] is False


def test_rendering_still_ready_without_comfyui(comfyui_refused) -> None:
    payload = client.get("/health/dependencies").json()
    assert payload["ready_for_generation"] is payload["dependencies"]["ffmpeg"]["ready"]
    assert payload["ready_for_cinematic"] is False


def test_timeout_is_summarised_too() -> None:
    with patch("app.api.routes.requests.get", side_effect=requests.Timeout("timed out")):
        comfy = client.get("/health/dependencies").json()["dependencies"]["comfyui"]
    assert comfy["detail"].startswith("No response from")
    assert len(comfy["detail"]) < 80


def test_healthy_comfyui_reports_connected() -> None:
    class FakeResponse:
        """Stands in for both the /system_stats and checkpoint probes."""

        ok = True
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            # Shape the checkpoint probe expects.
            return {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [[]]}}}}

    with patch("app.api.routes.requests.get", return_value=FakeResponse()):
        comfy = client.get("/health/dependencies").json()["dependencies"]["comfyui"]

    assert comfy["ready"] is True
    assert comfy["detail"].startswith("Connected to")
    assert comfy["raw_error"] == ""

