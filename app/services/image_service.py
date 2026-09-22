from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.services.comfyui_workflow_client import ComfyUIWorkflowClient


class ImageService:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, prompt: str, scene_index: int, visual_mode: str = "basic") -> Path:
        if visual_mode == "cinematic" and settings.comfyui_url:
            try:
                return self._generate_with_comfyui(prompt, scene_index)
            except Exception:
                pass
        return self._generate_placeholder(prompt, scene_index)

    def _generate_with_comfyui(self, prompt: str, scene_index: int) -> Path:
        path = self.out_dir / f"scene_{scene_index:03d}.png"
        client = ComfyUIWorkflowClient(settings.comfyui_url)
        history = client.run_workflow(
            workflow_path=Path(settings.comfyui_sd_workflow),
            prompt=prompt,
            scene_index=scene_index,
            checkpoint=settings.comfyui_sd_checkpoint_name,
            node_map={
                "prompt": settings.comfyui_sd_prompt_node_id,
                "seed": settings.comfyui_sd_seed_node_id,
                "checkpoint": settings.comfyui_sd_checkpoint_node_id,
                "output": settings.comfyui_sd_output_node_id,
            },
        )
        client.download_first_image(history, path)
        return path

    def _generate_placeholder(self, prompt: str, scene_index: int) -> Path:
        image = Image.new("RGB", (1024, 576), color=(20, 24, 34))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        text = f"Scene {scene_index}\n\n{prompt[:320]}"
        draw.multiline_text((40, 40), text, fill=(230, 230, 240), font=font, spacing=6)
        path = self.out_dir / f"scene_{scene_index:03d}.png"
        image.save(path)
        return path

