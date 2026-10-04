import json
from pathlib import Path

import pytest
import requests

from app.services.comfyui_workflow_client import ComfyUIWorkflowClient


def _sample_workflow() -> dict:
    return {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "2": {"class_type": "KSampler", "inputs": {"seed": 1}},
        "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},
        "4": {"class_type": "SaveImage", "inputs": {"filename_prefix": ""}},
    }


def test_run_workflow_rejects_missing_configured_node(tmp_path) -> None:
    workflow_path = tmp_path / "wf.json"
    workflow_path.write_text(json.dumps(_sample_workflow()), encoding="utf-8")

    client = ComfyUIWorkflowClient("http://127.0.0.1:8188")
    client._assert_checkpoint_available = lambda checkpoint: None  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="Configured prompt node"):
        client.run_workflow(
            workflow_path=workflow_path,
            prompt="hello",
            scene_index=1,
            checkpoint="sd_xl_base_1.0.safetensors",
            node_map={"prompt": "999"},
        )


def test_run_workflow_surfaces_comfyui_400_details(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "wf.json"
    workflow_path.write_text(json.dumps(_sample_workflow()), encoding="utf-8")

    def _fake_post(*args, **kwargs):
        response = requests.Response()
        response.status_code = 400
        response._content = b'{"error":"invalid prompt graph"}'
        response.url = "http://127.0.0.1:8188/prompt"
        return response

    monkeypatch.setattr(requests, "post", _fake_post)

    client = ComfyUIWorkflowClient("http://127.0.0.1:8188")
    client._assert_checkpoint_available = lambda checkpoint: None  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="/prompt failed with HTTP 400"):
        client.run_workflow(
            workflow_path=workflow_path,
            prompt="hello",
            scene_index=1,
            checkpoint="sd_xl_base_1.0.safetensors",
        )


def test_checkpoint_preflight_blocks_unknown_checkpoint(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "wf.json"
    workflow_path.write_text(json.dumps(_sample_workflow()), encoding="utf-8")
    post_called = {"value": False}

    def _fake_get(*args, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response._content = (
            b'{"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["anime_v1.safetensors"]]}}}}'
        )
        return response

    def _fake_post(*args, **kwargs):
        post_called["value"] = True
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"prompt_id":"abc"}'
        return response

    monkeypatch.setattr(requests, "get", _fake_get)
    monkeypatch.setattr(requests, "post", _fake_post)

    client = ComfyUIWorkflowClient("http://127.0.0.1:8188")
    with pytest.raises(RuntimeError, match="is not available"):
        client.run_workflow(
            workflow_path=workflow_path,
            prompt="hello",
            scene_index=1,
            checkpoint="sd_xl_base_1.0.safetensors",
        )
    assert post_called["value"] is False


def test_checkpoint_preflight_reports_endpoint_failure(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "wf.json"
    workflow_path.write_text(json.dumps(_sample_workflow()), encoding="utf-8")

    def _fake_get(*args, **kwargs):
        raise requests.RequestException("connection refused")

    monkeypatch.setattr(requests, "get", _fake_get)

    client = ComfyUIWorkflowClient("http://127.0.0.1:8188")
    with pytest.raises(RuntimeError, match="checkpoint preflight failed"):
        client.run_workflow(
            workflow_path=workflow_path,
            prompt="hello",
            scene_index=1,
            checkpoint="sd_xl_base_1.0.safetensors",
        )


def test_checkpoint_preflight_retries_transient_connection_errors(monkeypatch) -> None:
    calls = {"count": 0}

    def _fake_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise requests.ConnectionError("connection refused")
        response = requests.Response()
        response.status_code = 200
        response._content = (
            b'{"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["sd_xl_base_1.0.safetensors"]]}}}}'
        )
        return response

    monkeypatch.setattr(requests, "get", _fake_get)

    client = ComfyUIWorkflowClient("http://127.0.0.1:8188")
    client.preflight_retry_delay_seconds = 0
    client._assert_checkpoint_available("sd_xl_base_1.0.safetensors")

    assert calls["count"] == 3


def test_checkpoint_preflight_reports_empty_checkpoint_list(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "wf.json"
    workflow_path.write_text(json.dumps(_sample_workflow()), encoding="utf-8")

    def _fake_get(*args, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response._content = (
            b'{"CheckpointLoaderSimple":{"input":{"required":{"ckpt_name":[[],{"tooltip":"x"}]}}}}'
        )
        return response

    monkeypatch.setattr(requests, "get", _fake_get)

    client = ComfyUIWorkflowClient("http://127.0.0.1:8188")
    with pytest.raises(RuntimeError, match="zero checkpoints"):
        client.run_workflow(
            workflow_path=workflow_path,
            prompt="hello",
            scene_index=1,
            checkpoint="sd_xl_base_1.0.safetensors",
        )


def test_checkpoint_preflight_unknown_schema_falls_back_to_prompt_validation(tmp_path, monkeypatch) -> None:
    workflow_path = tmp_path / "wf.json"
    workflow_path.write_text(json.dumps(_sample_workflow()), encoding="utf-8")
    calls = {"post": 0}

    def _fake_get(*args, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"CheckpointLoaderSimple":{"input":{"required":{"different_key":123}}}}'
        return response

    def _fake_post(*args, **kwargs):
        calls["post"] += 1
        response = requests.Response()
        response.status_code = 400
        response._content = b'{"error":"invalid prompt graph"}'
        response.url = "http://127.0.0.1:8188/prompt"
        return response

    monkeypatch.setattr(requests, "get", _fake_get)
    monkeypatch.setattr(requests, "post", _fake_post)

    client = ComfyUIWorkflowClient("http://127.0.0.1:8188")
    with pytest.raises(RuntimeError, match="/prompt failed with HTTP 400"):
        client.run_workflow(
            workflow_path=workflow_path,
            prompt="hello",
            scene_index=1,
            checkpoint="sd_xl_base_1.0.safetensors",
        )
    assert calls["post"] == 1


def test_extract_history_error_parses_execution_error_details() -> None:
    history = {
        "status": {
            "status_str": "error",
            "messages": [
                [
                    "execution_error",
                    {
                        "node_id": "4",
                        "node_type": "KSampler",
                        "exception_type": "OSError",
                        "exception_message": "[Errno 22] Invalid argument\n",
                    },
                ]
            ],
        }
    }

    detail = ComfyUIWorkflowClient._extract_history_error(history)

    assert detail == "OSError at node 4 (KSampler): [Errno 22] Invalid argument"


def test_extract_history_error_returns_none_for_non_error_status() -> None:
    history = {"status": {"status_str": "success", "messages": []}}

    detail = ComfyUIWorkflowClient._extract_history_error(history)

    assert detail is None


def test_inject_runtime_values_builds_lora_chain_and_rewires_consumers() -> None:
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},
        "2": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ["1", 0]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
    }
    client = ComfyUIWorkflowClient("http://127.0.0.1:8188")

    client._inject_runtime_values(
        workflow,
        prompt="hello",
        seed=123,
        checkpoint="sd_xl_base_1.0.safetensors",
        scene_index=1,
        node_map={"checkpoint": "1", "seed": "2", "prompt": "3"},
        loras=[{"adapter": "hero_face_v1.safetensors", "strength": 0.9}],
    )

    lora_nodes = [n for n, data in workflow.items() if data.get("class_type") == "LoraLoader"]
    assert lora_nodes, "Expected a LoraLoader node to be injected"
    lora_id = lora_nodes[0]
    assert workflow[lora_id]["inputs"]["lora_name"] == "hero_face_v1.safetensors"
    assert workflow["2"]["inputs"]["model"] == [lora_id, 0]
    assert workflow["3"]["inputs"]["clip"] == [lora_id, 1]


def test_sdxl_template_cliptext_nodes_reference_clip_output_slot() -> None:
    workflow_path = Path("app/workflows/comfyui_sdxl_image.json")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))

    clip_source = workflow["6"]["inputs"]["clip"]
    negative_clip_source = workflow["7"]["inputs"]["clip"]

    assert clip_source[1] == 1
    assert negative_clip_source[1] == 1


