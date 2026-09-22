from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import crud
from app.agents.graph import build_graph
from app.models import Job, Project, Scene
from app.services.image_service import ImageService
from app.services.subtitle_service import SubtitleService
from app.services.tts_service import TTSService
from app.services.video_service import VideoService


def _project_dir(project_id: int) -> Path:
    from app.config import settings

    d = settings.workspace_dir / f"project_{project_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


class MoviePipeline:
    def __init__(self, db: Session):
        self.db = db

    def run(
        self,
        project: Project,
        job: Job,
        resume: bool = True,
        resume_from_scene_index: int | None = None,
        visual_mode: str = "basic",
    ) -> Job:
        job.attempts = (job.attempts or 0) + 1
        self.db.add(job)
        self.db.commit()
        project.status = "processing"
        self._update_job(job, "processing", "director", "Analyzing script", 0.05)

        scenes = self.db.query(Scene).filter(Scene.project_id == project.id).order_by(Scene.scene_index).all()
        if not scenes or not resume:
            graph = build_graph()
            state = graph.invoke({"script_text": project.script_text, "language": project.language, "scenes": [], "style": ""})

            self.db.execute(delete(Scene).where(Scene.project_id == project.id))
            self.db.commit()

            for scene_data in state["scenes"]:
                self.db.add(
                    Scene(
                        project_id=project.id,
                        scene_index=scene_data["scene_index"],
                        title=scene_data["title"],
                        script_chunk=scene_data["script_chunk"],
                        description=scene_data["description"],
                        image_prompt=scene_data["image_prompt"],
                        duration_seconds=scene_data["duration_seconds"],
                    )
                )
            self.db.commit()
            scenes = self.db.query(Scene).filter(Scene.project_id == project.id).order_by(Scene.scene_index).all()

        job.total_scenes = len(scenes)
        job.processed_scenes = 0
        self.db.add(job)
        self.db.commit()
        root = _project_dir(project.id)
        image_service = ImageService(root / "images")
        tts_service = TTSService(root / "audio")
        subtitle_service = SubtitleService(root / "subs")
        video_service = VideoService(root / "video")
        self._update_job(job, "processing", "dependency_check", "Validating FFmpeg dependency", 0.08)
        video_service.ensure_ffmpeg_available()

        clips = []
        audios = []
        sub_texts = []
        durations = []

        forced_restart_index = resume_from_scene_index or 1

        for idx, scene in enumerate(scenes, start=1):
            must_regenerate = scene.scene_index >= forced_restart_index
            if resume and not must_regenerate and scene.video_path and scene.narration_path and scene.subtitle_path:
                clip = Path(scene.video_path)
                wav = Path(scene.narration_path)
                sub = Path(scene.subtitle_path)
                job.processed_scenes = idx
            elif resume and not must_regenerate:
                raise RuntimeError(
                    f"Resume requested before scene {forced_restart_index}, but scene {scene.scene_index} artifacts are missing"
                )
            else:
                self._update_job(job, "processing", "storyboard", f"Generating scene {scene.scene_index} image", 0.1)
                img = image_service.generate(scene.image_prompt, scene.scene_index, visual_mode=visual_mode)
                scene.image_path = str(img)

                self._update_job(job, "processing", "videographer", f"Generating scene {scene.scene_index} video clip", 0.2)
                if scene.video_path and Path(scene.video_path).exists():
                    clip = Path(scene.video_path)
                else:
                    if visual_mode == "cinematic" and scene.image_prompt and scene.image_prompt.strip():
                        # Cinematic mode expects real model output and should fail if generation fails.
                        clip = video_service.generate_clip_with_comfyui(scene.image_prompt, scene.scene_index)
                    else:
                        clip = video_service.image_to_clip(img, scene.duration_seconds, scene.scene_index)
                scene.video_path = str(clip)

                self._update_job(job, "processing", "narrator", f"Generating scene {scene.scene_index} narration", 0.35)
                wav = tts_service.synthesize(scene.script_chunk, scene.scene_index)
                scene.narration_path = str(wav)

                sub = subtitle_service.create_scene_subtitle(scene.script_chunk, scene.duration_seconds, scene.scene_index)
                scene.subtitle_path = str(sub)

                job.processed_scenes = idx
                self.db.add(job)
                self.db.commit()

            clips.append(clip)
            audios.append(wav)
            sub_texts.append(scene.script_chunk)
            durations.append(scene.duration_seconds)
            self.db.add(scene)
            self.db.commit()

            scene_progress = 0.45 + (0.45 * idx / max(1, len(scenes)))
            self._update_job(job, "processing", "scene_complete", f"Scene {scene.scene_index} complete", scene_progress)

        self._update_job(job, "processing", "editor", "Merging clips", 0.92)
        merged_video = video_service.concat_videos(clips)
        merged_audio = video_service.concat_audio(audios)
        merged_subs = subtitle_service.merge_scene_subtitles(sub_texts, durations)
        final_video = video_service.mux(merged_video, merged_audio, merged_subs)

        project.status = "completed"
        self._update_job(job, "completed", "done", "Movie generated", 1.0)
        job.output_video_path = str(final_video)
        job.last_error = ""
        self.db.add(project)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def regenerate_scene(self, project: Project, scene: Scene) -> Scene:
        root = _project_dir(project.id)
        image_service = ImageService(root / "images")
        tts_service = TTSService(root / "audio")
        subtitle_service = SubtitleService(root / "subs")
        video_service = VideoService(root / "video")

        img = image_service.generate(scene.image_prompt, scene.scene_index)
        clip = video_service.image_to_clip(img, scene.duration_seconds, scene.scene_index)
        wav = tts_service.synthesize(scene.script_chunk, scene.scene_index)
        sub = subtitle_service.create_scene_subtitle(scene.script_chunk, scene.duration_seconds, scene.scene_index)

        scene.image_path = str(img)
        scene.video_path = str(clip)
        scene.narration_path = str(wav)
        scene.subtitle_path = str(sub)

        self.db.add(scene)
        self.db.commit()
        self.db.refresh(scene)
        return scene

    def _update_job(self, job: Job, status: str, stage: str, message: str, progress: float) -> None:
        job.status = status
        job.stage = stage
        job.message = message
        job.progress = progress
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        crud.create_job_event(self.db, job.id, stage=stage, level="info", message=message, progress=progress)

    def mark_failure(self, job: Job, error: Exception) -> None:
        job.status = "failed"
        job.stage = "error"
        job.message = str(error)
        job.last_error = str(error)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        crud.create_job_event(self.db, job.id, stage="error", level="error", message=str(error), progress=job.progress)

