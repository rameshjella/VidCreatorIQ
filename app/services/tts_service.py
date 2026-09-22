import subprocess
from pathlib import Path

import pyttsx3

from app.config import settings


class TTSService:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def synthesize(self, text: str, scene_index: int) -> Path:
        if settings.piper_executable and settings.piper_model_path:
            try:
                return self._synthesize_with_piper(text, scene_index)
            except Exception:
                pass
        return self._synthesize_with_pyttsx3(text, scene_index)

    def _synthesize_with_piper(self, text: str, scene_index: int) -> Path:
        output_path = self.out_dir / f"scene_{scene_index:03d}.wav"
        cmd = [
            settings.piper_executable,
            "--model",
            settings.piper_model_path,
            "--output_file",
            str(output_path),
        ]
        subprocess.run(cmd, input=text.encode("utf-8"), check=True)
        return output_path

    def _synthesize_with_pyttsx3(self, text: str, scene_index: int) -> Path:
        output_path = self.out_dir / f"scene_{scene_index:03d}.wav"
        engine = pyttsx3.init()
        engine.save_to_file(text, str(output_path))
        engine.runAndWait()
        return output_path

