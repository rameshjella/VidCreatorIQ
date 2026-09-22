from __future__ import annotations

import json
import sys
from pathlib import Path


def _find_first(workflow: dict, class_type: str) -> str:
    for node_id, node in workflow.items():
        if node.get("class_type") == class_type:
            return node_id
    return ""


def _find_with_input(workflow: dict, input_key: str) -> str:
    for node_id, node in workflow.items():
        if input_key in node.get("inputs", {}):
            return node_id
    return ""


def _derive(path: Path) -> dict[str, str]:
    workflow = json.loads(path.read_text(encoding="utf-8"))
    return {
        "PROMPT_NODE_ID": _find_first(workflow, "CLIPTextEncode"),
        "SEED_NODE_ID": _find_with_input(workflow, "seed"),
        "CHECKPOINT_NODE_ID": _find_first(workflow, "CheckpointLoaderSimple"),
        "OUTPUT_NODE_ID": _find_with_input(workflow, "filename_prefix"),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python scripts/derive_comfy_ids.py <sd_workflow.json> <animatediff_workflow.json>")
        return 1

    sd_path = Path(sys.argv[1])
    ad_path = Path(sys.argv[2])
    sd = _derive(sd_path)
    ad = _derive(ad_path)

    print(f"COMFYUI_SD_PROMPT_NODE_ID={sd['PROMPT_NODE_ID']}")
    print(f"COMFYUI_SD_SEED_NODE_ID={sd['SEED_NODE_ID']}")
    print(f"COMFYUI_SD_CHECKPOINT_NODE_ID={sd['CHECKPOINT_NODE_ID']}")
    print(f"COMFYUI_SD_OUTPUT_NODE_ID={sd['OUTPUT_NODE_ID']}")
    print(f"COMFYUI_AD_PROMPT_NODE_ID={ad['PROMPT_NODE_ID']}")
    print(f"COMFYUI_AD_SEED_NODE_ID={ad['SEED_NODE_ID']}")
    print(f"COMFYUI_AD_CHECKPOINT_NODE_ID={ad['CHECKPOINT_NODE_ID']}")
    print(f"COMFYUI_AD_OUTPUT_NODE_ID={ad['OUTPUT_NODE_ID']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

