import subprocess
from shutil import which
from pathlib import Path

from app.config import settings
from app.services.comfyui_workflow_client import ComfyUIWorkflowClient


class VideoService:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_cmd = self._resolve_ffmpeg_cmd()

    def ensure_ffmpeg_available(self) -> None:
        # Constructor already validates, this method keeps call sites explicit.
        return None

    def _resolve_ffmpeg_cmd(self) -> str:
        configured = settings.ffmpeg_bin.strip()
        if not configured:
            raise RuntimeError("FFMPEG_BIN is empty. Set FFMPEG_BIN in .env or add ffmpeg to PATH.")

        if Path(configured).exists():
            return configured

        resolved = which(configured)
        if resolved:
            return resolved

        raise RuntimeError(
            f"FFmpeg binary not found: '{configured}'. Install FFmpeg and add it to PATH, "
            "or set FFMPEG_BIN to the full executable path in .env."
        )

    def _run_ffmpeg(self, cmd: list[str]) -> None:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Failed to execute FFmpeg command. Binary not found: '{self.ffmpeg_cmd}'. "
                "Verify FFMPEG_BIN and PATH settings."
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr_tail = (exc.stderr or "").strip()[-400:]
            raise RuntimeError(f"FFmpeg command failed (exit {exc.returncode}): {stderr_tail}") from exc

    @staticmethod
    def _concat_line(path: Path) -> str:
        absolute = path.resolve().as_posix()
        escaped = absolute.replace("'", "'\\''")
        return f"file '{escaped}'"

    def _write_concat_list(self, entries: list[Path], list_file: Path) -> None:
        lines = [self._concat_line(entry) for entry in entries]
        list_file.write_text("\n".join(lines), encoding="utf-8")

    def image_to_clip(self, image_path: Path, duration: float, scene_index: int) -> Path:
        clip_path = self.out_dir / f"scene_{scene_index:03d}.mp4"
        cmd = [
            self.ffmpeg_cmd,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            str(duration),
            "-vf",
            "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(clip_path),
        ]
        self._run_ffmpeg(cmd)
        return clip_path

    def generate_clip_with_comfyui(self, prompt: str, scene_index: int) -> Path:
        clip_path = self.out_dir / f"scene_{scene_index:03d}.mp4"
        client = ComfyUIWorkflowClient(settings.comfyui_url)
        history = client.run_workflow(
            workflow_path=Path(settings.comfyui_animatediff_workflow),
            prompt=prompt,
            scene_index=scene_index,
            checkpoint=settings.comfyui_ad_checkpoint_name,
            node_map={
                "prompt": settings.comfyui_ad_prompt_node_id,
                "seed": settings.comfyui_ad_seed_node_id,
                "checkpoint": settings.comfyui_ad_checkpoint_node_id,
                "output": settings.comfyui_ad_output_node_id,
            },
        )
        client.download_first_video(history, clip_path)
        return clip_path

    def concat_videos(self, clips: list[Path], output_name: str = "movie_silent.mp4") -> Path:
        list_file = self.out_dir / "concat.txt"
        self._write_concat_list(clips, list_file)
        out_path = self.out_dir / output_name
        cmd = [
            self.ffmpeg_cmd,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(out_path),
        ]
        self._run_ffmpeg(cmd)
        return out_path

    def concat_audio(self, audios: list[Path], output_name: str = "movie.wav") -> Path:
        list_file = self.out_dir / "audio_concat.txt"
        self._write_concat_list(audios, list_file)
        out_path = self.out_dir / output_name
        cmd = [
            self.ffmpeg_cmd,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(out_path),
        ]
        self._run_ffmpeg(cmd)
        return out_path

    def mux(self, video_path: Path, audio_path: Path, subtitle_path: Path, output_name: str = "final_movie.mp4") -> Path:
        out_path = self.out_dir / output_name
        cmd = [
            self.ffmpeg_cmd,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-i",
            str(subtitle_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-c:s",
            "mov_text",
            "-shortest",
            str(out_path),
        ]
        self._run_ffmpeg(cmd)
        return out_path

