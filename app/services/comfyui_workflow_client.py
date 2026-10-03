from __future__ import annotations

import json
import logging
import random
import socket
import time
from pathlib import Path
from urllib.parse import urlencode

import requests


logger = logging.getLogger(__name__)


class ComfyUIWorkflowClient:
    def __init__(self, base_url: str, timeout_seconds: int = 600):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.preflight_retries = 6
        self.preflight_retry_delay_seconds = 2

    def run_workflow(
        self,
        workflow_path: Path,
        prompt: str,
        scene_index: int,
        checkpoint: str,
        node_map: dict[str, str] | None = None,
        loras: list[dict] | None = None,
    ) -> dict:
        raw = workflow_path.read_text(encoding="utf-8")
        workflow = self._load_workflow(raw)
        self._validate_workflow_shape(workflow)
        self._assert_checkpoint_available(checkpoint)
        seed = random.randint(1, 2_000_000_000)
        node_map = node_map or {}
        self._inject_runtime_values(workflow, prompt, seed, checkpoint, scene_index, node_map, loras or [])

        queued = requests.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow},
            timeout=30,
        )
        try:
            queued.raise_for_status()
        except requests.HTTPError as exc:
            detail = self._format_prompt_error(queued, workflow_path, node_map)
            raise RuntimeError(detail) from exc

        payload = queued.json()
        prompt_id = payload.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI /prompt response did not include prompt_id: {payload}")
        return self._wait_for_history(prompt_id)

    def download_first_image(self, history: dict, out_path: Path) -> Path:
        output = self._extract_output(history, ("images",))
        query = urlencode({"filename": output["filename"], "subfolder": output.get("subfolder", ""), "type": output.get("type", "output")})
        resp = requests.get(f"{self.base_url}/view?{query}", timeout=60)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        return out_path

    def download_first_video(self, history: dict, out_path: Path) -> Path:
        output = self._extract_output(history, ("gifs", "videos", "images"))
        query = urlencode({"filename": output["filename"], "subfolder": output.get("subfolder", ""), "type": output.get("type", "output")})
        resp = requests.get(f"{self.base_url}/view?{query}", timeout=120)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        return out_path

    def _wait_for_history(self, prompt_id: str) -> dict:
        deadline = time.time() + self.timeout_seconds
        while time.time() < deadline:
            resp = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=20)
            resp.raise_for_status()
            payload = resp.json()
            if prompt_id in payload:
                history = payload[prompt_id]
                execution_error = self._extract_history_error(history)
                if execution_error:
                    raise RuntimeError(f"ComfyUI execution failed for prompt_id={prompt_id}: {execution_error}")
                return history
            time.sleep(2)
        raise TimeoutError(f"ComfyUI workflow timed out for prompt_id={prompt_id}")

    @staticmethod
    def _extract_history_error(history: dict) -> str | None:
        status = history.get("status", {}) if isinstance(history, dict) else {}
        if status.get("status_str") != "error":
            return None

        messages = status.get("messages", [])
        for message in reversed(messages):
            if not isinstance(message, list) or len(message) < 2:
                continue
            if message[0] != "execution_error":
                continue
            detail = message[1] if isinstance(message[1], dict) else {}
            node_id = detail.get("node_id", "?")
            node_type = detail.get("node_type", "unknown")
            exc_type = detail.get("exception_type", "error")
            exc_message = str(detail.get("exception_message", "")).strip().replace("\n", " ")
            return f"{exc_type} at node {node_id} ({node_type}): {exc_message}"

        return "ComfyUI marked execution as error but did not return execution_error details"

    def _load_workflow(self, raw: str) -> dict:
        # Accept either plain exported JSON or placeholder-based templates.
        rendered = (
            raw.replace("{{seed}}", str(random.randint(1, 2_000_000_000)))
            .replace("{{scene_index}}", "000")
            .replace("{{checkpoint}}", "sd_xl_base_1.0.safetensors")
            .replace("{{prompt}}", "placeholder prompt")
        )
        return json.loads(rendered)

    def _inject_runtime_values(
        self,
        workflow: dict,
        prompt: str,
        seed: int,
        checkpoint: str,
        scene_index: int,
        node_map: dict[str, str],
        loras: list[dict],
    ) -> None:
        prompt_node = node_map.get("prompt") or self._find_node_id(workflow, "CLIPTextEncode")
        seed_node = node_map.get("seed") or self._find_node_with_input(workflow, "seed")
        checkpoint_node = node_map.get("checkpoint") or self._find_node_id(workflow, "CheckpointLoaderSimple")
        output_node = node_map.get("output") or self._find_node_with_input(workflow, "filename_prefix")

        if node_map.get("prompt") and node_map["prompt"] not in workflow:
            raise ValueError(f"Configured prompt node '{node_map['prompt']}' was not found in workflow")
        if node_map.get("seed") and node_map["seed"] not in workflow:
            raise ValueError(f"Configured seed node '{node_map['seed']}' was not found in workflow")
        if node_map.get("checkpoint") and node_map["checkpoint"] not in workflow:
            raise ValueError(f"Configured checkpoint node '{node_map['checkpoint']}' was not found in workflow")
        if node_map.get("output") and node_map["output"] not in workflow:
            raise ValueError(f"Configured output node '{node_map['output']}' was not found in workflow")

        if prompt_node:
            workflow[prompt_node]["inputs"]["text"] = prompt
        if seed_node:
            workflow[seed_node]["inputs"]["seed"] = seed
        if checkpoint_node:
            workflow[checkpoint_node]["inputs"]["ckpt_name"] = checkpoint
            self._inject_lora_chain(workflow, checkpoint_node, node_map, loras)
        if output_node and "filename_prefix" in workflow[output_node].get("inputs", {}):
            workflow[output_node]["inputs"]["filename_prefix"] = f"ai_movie/scene_{scene_index:03d}"

    def _inject_lora_chain(
        self,
        workflow: dict,
        checkpoint_node: str,
        node_map: dict[str, str],
        loras: list[dict],
    ) -> None:
        adapters = [l for l in loras if (l.get("adapter") or "").strip()]
        if not adapters:
            return

        configured = [n.strip() for n in (node_map.get("lora") or "").split(",") if n.strip()]
        for node_id in configured:
            if node_id not in workflow:
                raise ValueError(f"Configured lora node '{node_id}' was not found in workflow")

        existing_loaders = configured or [
            node_id for node_id, node in workflow.items() if node.get("class_type") == "LoraLoader"
        ]

        model_src: list[object] = [checkpoint_node, 0]
        clip_src: list[object] = [checkpoint_node, 1]
        lora_node_ids: list[str] = []
        for index, adapter in enumerate(adapters):
            if index < len(existing_loaders):
                node_id = existing_loaders[index]
            else:
                node_id = self._next_node_id(workflow)
                workflow[node_id] = {"class_type": "LoraLoader", "inputs": {}}

            workflow[node_id].setdefault("inputs", {})
            workflow[node_id]["class_type"] = "LoraLoader"
            workflow[node_id]["inputs"].update(
                {
                    "model": list(model_src),
                    "clip": list(clip_src),
                    "lora_name": str(adapter.get("adapter", "")).strip(),
                    "strength_model": float(adapter.get("strength", 0.8)),
                    "strength_clip": float(adapter.get("strength", 0.8)),
                }
            )
            lora_node_ids.append(node_id)
            model_src = [node_id, 0]
            clip_src = [node_id, 1]

        last_lora_node = lora_node_ids[-1]
        self._rewire_checkpoint_consumers(
            workflow,
            checkpoint_node=checkpoint_node,
            replacement_node=last_lora_node,
            skip_nodes=set(lora_node_ids),
        )

    @staticmethod
    def _rewire_checkpoint_consumers(
        workflow: dict,
        checkpoint_node: str,
        replacement_node: str,
        skip_nodes: set[str],
    ) -> None:
        for node_id, node_data in workflow.items():
            if node_id in skip_nodes:
                continue
            inputs = node_data.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            for key, value in list(inputs.items()):
                if not (isinstance(value, list) and len(value) >= 2):
                    continue
                source_node, source_slot = str(value[0]), value[1]
                if source_node != checkpoint_node:
                    continue
                if source_slot == 0:
                    inputs[key] = [replacement_node, 0]
                elif source_slot == 1:
                    inputs[key] = [replacement_node, 1]

    @staticmethod
    def _next_node_id(workflow: dict) -> str:
        numeric = [int(k) for k in workflow.keys() if str(k).isdigit()]
        return str((max(numeric) + 1) if numeric else 1)

    @staticmethod
    def _validate_workflow_shape(workflow: dict) -> None:
        if not isinstance(workflow, dict) or not workflow:
            raise ValueError("ComfyUI workflow JSON must be a non-empty object keyed by node id")
        for node_id, node_data in workflow.items():
            if not isinstance(node_data, dict):
                raise ValueError(f"Workflow node '{node_id}' must be an object")
            if "inputs" in node_data and not isinstance(node_data.get("inputs"), dict):
                raise ValueError(f"Workflow node '{node_id}' has invalid 'inputs' format")

    def _assert_checkpoint_available(self, checkpoint: str) -> None:
        target = (checkpoint or "").strip()
        if not target:
            raise ValueError("Checkpoint name is empty")

        endpoint = f"{self.base_url}/object_info/CheckpointLoaderSimple"
        last_exc: Exception | None = None
        response: requests.Response | None = None
        for attempt in range(1, self.preflight_retries + 1):
            try:
                response = requests.get(endpoint, timeout=20)
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self.preflight_retries and self._is_connection_issue(exc):
                    time.sleep(self.preflight_retry_delay_seconds)
                    continue
                raise RuntimeError(
                    "ComfyUI checkpoint preflight failed at "
                    f"{endpoint}: {exc}. Ensure ComfyUI is running and reachable before cinematic generation."
                ) from exc

        if response is None:
            raise RuntimeError(f"ComfyUI checkpoint preflight failed at {endpoint}: {last_exc}")

        try:
            payload = response.json()
        except ValueError as exc:
            preview = (response.text or "").strip()[:300]
            raise RuntimeError(
                f"ComfyUI checkpoint preflight returned non-JSON at {endpoint}: {preview}"
            ) from exc

        available, schema_recognized = self._extract_checkpoint_names(payload)
        if schema_recognized and not available:
            raise RuntimeError(
                "ComfyUI reports zero checkpoints in CheckpointLoaderSimple. "
                "Add models to ComfyUI checkpoints, or configure extra model paths "
                "(e.g. COMFYUI_MODEL_PATHS / --extra-model-paths-config)."
            )
        if not schema_recognized:
            logger.warning(
                "ComfyUI checkpoint preflight could not interpret ckpt_name schema at %s; continuing and relying on /prompt validation",
                endpoint,
            )
            return
        if target not in available:
            sample = ", ".join(available[:8])
            raise RuntimeError(
                f"Configured checkpoint '{target}' is not available in ComfyUI. "
                f"Found {len(available)} checkpoints (sample: {sample})"
            )

    @staticmethod
    def _is_connection_issue(exc: requests.RequestException) -> bool:
        current: BaseException | None = exc
        while current is not None:
            if isinstance(current, (requests.ConnectionError, ConnectionRefusedError, socket.timeout, TimeoutError)):
                return True
            current = current.__cause__
        return False

    @staticmethod
    def _extract_checkpoint_names(payload: object) -> tuple[list[str], bool]:
        names: set[str] = set()
        schema_recognized = False

        def consume_ckpt_spec(value: object) -> None:
            nonlocal schema_recognized
            schema_recognized = True
            if isinstance(value, str):
                if value:
                    names.add(value)
                return
            if not isinstance(value, list):
                return
            # Common ComfyUI format: [ ["model1.safetensors", ...], {metadata...} ]
            for item in value:
                if isinstance(item, str) and item:
                    names.add(item)
                elif isinstance(item, list):
                    for nested in item:
                        if isinstance(nested, str) and nested:
                            names.add(nested)

        def walk(obj: object) -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == "ckpt_name":
                        consume_ckpt_spec(value)
                    walk(value)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(payload)
        return sorted(names), schema_recognized

    @staticmethod
    def _format_prompt_error(response: requests.Response, workflow_path: Path, node_map: dict[str, str]) -> str:
        body = ""
        try:
            parsed = response.json()
            body = json.dumps(parsed)
        except ValueError:
            body = (response.text or "").strip()
        body = body[:700]
        return (
            f"ComfyUI /prompt failed with HTTP {response.status_code}. "
            f"workflow='{workflow_path}', node_map={node_map or {}}, response={body}"
        )

    @staticmethod
    def _find_node_id(workflow: dict, class_type: str) -> str | None:
        for node_id, node_data in workflow.items():
            if node_data.get("class_type") == class_type:
                return node_id
        return None

    @staticmethod
    def _find_node_with_input(workflow: dict, input_key: str) -> str | None:
        for node_id, node_data in workflow.items():
            if input_key in node_data.get("inputs", {}):
                return node_id
        return None

    @staticmethod
    def _extract_output(history: dict, keys: tuple[str, ...]) -> dict:
        for node_data in history.get("outputs", {}).values():
            for key in keys:
                values = node_data.get(key)
                if values:
                    return values[0]
        raise ValueError("No matching output artifact found in ComfyUI history")

