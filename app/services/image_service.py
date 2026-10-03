import logging
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.config import settings
from app.services.comfyui_workflow_client import ComfyUIWorkflowClient

logger = logging.getLogger(__name__)

# Cinematic duotone palettes used by the fallback renderer.
PALETTES = [
    ((12, 18, 42), (94, 63, 168), (0, 212, 255)),
    ((30, 10, 28), (140, 45, 90), (255, 138, 92)),
    ((6, 26, 28), (18, 92, 96), (122, 222, 199)),
    ((26, 16, 8), (128, 78, 30), (255, 196, 110)),
    ((10, 12, 26), (54, 60, 140), (150, 170, 255)),
]


class ImageService:
    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        prompt: str,
        scene_index: int,
        visual_mode: str = "basic",
        loras: list[dict] | None = None,
    ) -> Path:
        if visual_mode == "cinematic" and settings.comfyui_url:
            try:
                return self._generate_with_comfyui(prompt, scene_index, loras or [])
            except Exception as exc:  # noqa: BLE001
                # Previously this was swallowed silently, so "cinematic" renders
                # quietly became grey text cards. Log loudly, then degrade.
                logger.warning(
                    "ComfyUI image generation failed for scene %s (%s). "
                    "Falling back to the generated art card.",
                    scene_index,
                    exc,
                )
        return self._generate_placeholder(prompt, scene_index)

    def _generate_with_comfyui(self, prompt: str, scene_index: int, loras: list[dict]) -> Path:
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
                "lora": settings.comfyui_sd_lora_node_ids,
                "output": settings.comfyui_sd_output_node_id,
            },
            loras=loras,
        )
        client.download_first_image(history, path)
        return path

    # ------------------------------------------------------------------
    # Fallback art card
    # ------------------------------------------------------------------
    def _load_font(self, size: int) -> ImageFont.FreeTypeFont:
        for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Helvetica.ttc"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    def _generate_placeholder(self, prompt: str, scene_index: int) -> Path:
        """Render a designed title card rather than a flat grey rectangle."""
        width, height = int(settings.render_width), int(settings.render_height)
        # Deterministic per scene so re-renders look identical.
        rng = random.Random(f"{scene_index}:{prompt}")
        dark, mid, accent = rng.choice(PALETTES)

        image = Image.new("RGB", (width, height), dark)
        draw = ImageDraw.Draw(image)

        # Vertical gradient wash.
        for y in range(height):
            t = y / max(1, height - 1)
            draw.line(
                [(0, y), (width, y)],
                fill=(
                    int(dark[0] + (mid[0] - dark[0]) * t),
                    int(dark[1] + (mid[1] - dark[1]) * t),
                    int(dark[2] + (mid[2] - dark[2]) * t),
                ),
            )

        # Soft accent glow.
        glow = Image.new("RGB", (width, height), dark)
        gdraw = ImageDraw.Draw(glow)
        cx, cy = rng.randint(int(width * 0.2), int(width * 0.8)), rng.randint(int(height * 0.2), int(height * 0.8))
        radius = int(min(width, height) * 0.45)
        gdraw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=accent)
        glow = glow.filter(ImageFilter.GaussianBlur(radius // 2))
        image = Image.blend(image, glow, 0.28)
        draw = ImageDraw.Draw(image)

        # Film-grain-ish vignette bars for a cinematic frame.
        bar = int(height * 0.06)
        draw.rectangle([0, 0, width, bar], fill=(0, 0, 0))
        draw.rectangle([0, height - bar, width, height], fill=(0, 0, 0))

        margin = int(width * 0.08)
        label_font = self._load_font(max(18, height // 34))
        title_font = self._load_font(max(28, height // 16))

        draw.text((margin, int(height * 0.24)), f"SCENE {scene_index:02d}", font=label_font, fill=accent)
        draw.line(
            [(margin, int(height * 0.30)), (margin + int(width * 0.08), int(height * 0.30))],
            fill=accent,
            width=4,
        )

        text = " ".join((prompt or "Untitled scene").split())
        wrapped = self._wrap(text[:260], title_font, width - margin * 2, draw)
        draw.multiline_text(
            (margin, int(height * 0.36)),
            wrapped,
            font=title_font,
            fill=(245, 246, 252),
            spacing=int(height * 0.018),
        )

        path = self.out_dir / f"scene_{scene_index:03d}.png"
        image.save(path, quality=95)
        return path

    @staticmethod
    def _wrap(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> str:
        words, lines, current = text.split(), [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return "\n".join(lines[:6])
