from pathlib import Path

import run_ai_movie_maker as launcher


def test_fingerprint_ignores_workflow_and_node_mapping_changes(tmp_path: Path) -> None:
    command = ["python", "main.py", "--listen", "127.0.0.1", "--port", "8188"]
    base_env = {
        "COMFYUI_SD_PROMPT_NODE_ID": "6",
        "COMFYUI_SD_WORKFLOW": "./app/workflows/comfyui_sdxl_image.json",
    }

    original = launcher._compute_comfyui_fingerprint(base_env, command, tmp_path)

    modified_env = {
        **base_env,
        "COMFYUI_SD_PROMPT_NODE_ID": "123",
        "COMFYUI_SD_WORKFLOW": "./different_workflow.json",
    }
    modified = launcher._compute_comfyui_fingerprint(modified_env, command, tmp_path)

    assert original == modified


def test_fingerprint_changes_when_model_paths_change(tmp_path: Path) -> None:
    command = ["python", "main.py", "--listen", "127.0.0.1", "--port", "8188"]
    env_a = {"COMFYUI_MODEL_PATHS": "C:/models/a"}
    env_b = {"COMFYUI_MODEL_PATHS": "C:/models/b"}

    fp_a = launcher._compute_comfyui_fingerprint(env_a, command, tmp_path)
    fp_b = launcher._compute_comfyui_fingerprint(env_b, command, tmp_path)

    assert fp_a != fp_b

