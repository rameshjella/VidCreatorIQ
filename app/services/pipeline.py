from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import crud
from app.agents.graph import build_graph
from app.config import settings
from app.models import Job, Project, Scene
from app.services import ffmpeg_runner as ff
from app.services.image_service import ImageService
from app.services.narration_service import TTSService
from app.services.render_service import RenderService
from app.services.subtitle_service import SubtitleService

logger = logging.getLogger(__name__)

# Weighted stage model so progress reflects real work instead of magic numbers.
STAGE_WEIGHTS = {
    "plan": 0.05,
    "scenes": 0.70,
    "assemble": 0.25,
}


def _project_dir(project_id: int) -> Path:
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
        tts_provider: str | None = None,
        tts_voice: str = "",
        music_path: str | None = None,
    ) -> Job:
        job.attempts = (job.attempts or 0) + 1
        self.db.add(job)
        self.db.commit()
        project.status = "processing"
        self._update_job(job, "processing", "director", "Analyzing script", 0.02)

        scenes = self.db.query(Scene).filter(Scene.project_id == project.id).order_by(Scene.scene_index).all()
        if not scenes or not resume:
            graph = build_graph()
            state = graph.invoke(
                {"script_text": project.script_text, "language": project.language, "scenes": [], "style": ""}
            )

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

        if not scenes:
            raise RuntimeError("The script could not be split into any scenes. Check the script content.")

        job.total_scenes = len(scenes)
        job.processed_scenes = 0
        self.db.add(job)
        self.db.commit()

        root = _project_dir(project.id)
        image_service = ImageService(root / "images")
        tts_service = TTSService(root / "audio", provider=tts_provider, voice=tts_voice)
        subtitle_service = SubtitleService(root / "subs")
        render_service = RenderService(root / "video")

        self._update_job(job, "processing", "dependency_check", "Validating FFmpeg dependency", 0.04)
        render_service.ensure_ffmpeg_available()

        clips: list[Path] = []
        audios: list[Path] = []
        sub_texts: list[str] = []
        durations: list[float] = []

        forced_restart_index = resume_from_scene_index or 1
        total = len(scenes)

        for idx, scene in enumerate(scenes, start=1):
            must_regenerate = scene.scene_index >= forced_restart_index
            reusable = (
                resume
                and not must_regenerate
                and scene.video_path
                and scene.narration_path
                and Path(scene.video_path).exists()
                and Path(scene.narration_path).exists()
            )

            if reusable:
                clip = Path(scene.video_path)
                narration = Path(scene.narration_path)
                scene_duration = scene.audio_duration_seconds or ff.probe_duration(narration)
            elif resume and not must_regenerate:
                raise RuntimeError(
                    f"Resume requested before scene {forced_restart_index}, but scene "
                    f"{scene.scene_index} artifacts are missing"
                )
            else:
                base = STAGE_WEIGHTS["plan"]
                span = STAGE_WEIGHTS["scenes"] / total

                # 1. Narration FIRST. Its measured length is the source of truth
                #    for scene duration; previously the LLM's guess was used and
                #    audio/video drifted apart permanently.
                self._update_job(
                    job, "processing", "narrator",
                    f"Voicing scene {scene.scene_index} of {total}",
                    base + span * (idx - 1) + span * 0.1,
                )
                result = tts_service.synthesize_detailed(scene.script_chunk, scene.scene_index)
                narration = result.path
                scene.narration_path = str(narration)
                scene.tts_provider = result.provider
                scene.tts_voice = result.voice or ""
                scene_duration = max(float(settings.render_min_scene_seconds), result.duration)
                scene.audio_duration_seconds = scene_duration
                scene.duration_seconds = scene_duration

                # 2. Visuals.
                self._update_job(
                    job, "processing", "storyboard",
                    f"Illustrating scene {scene.scene_index} of {total}",
                    base + span * (idx - 1) + span * 0.45,
                )
                img = image_service.generate(scene.image_prompt, scene.scene_index, visual_mode=visual_mode)
                scene.image_path = str(img)

                # 3. Motion, matched to the narration length.
                self._update_job(
                    job, "processing", "videographer",
                    f"Rendering scene {scene.scene_index} of {total}",
                    base + span * (idx - 1) + span * 0.7,
                )
                if visual_mode == "cinematic" and (scene.image_prompt or "").strip():
                    clip = render_service.generate_clip_with_comfyui(
                        scene.image_prompt, scene.scene_index, self._clip_length(scene_duration, idx, total)
                    )
                else:
                    clip = render_service.image_to_clip(
                        img, self._clip_length(scene_duration, idx, total), scene.scene_index
                    )
                scene.video_path = str(clip)

                scene.subtitle_path = str(
                    subtitle_service.create_scene_subtitle(scene.script_chunk, scene_duration, scene.scene_index)
                )

            job.processed_scenes = idx
            clips.append(Path(clip))
            audios.append(Path(narration))
            sub_texts.append(scene.script_chunk)
            durations.append(float(scene_duration))

            self.db.add(scene)
            self.db.add(job)
            self.db.commit()

            self._update_job(
                job, "processing", "scene_complete",
                f"Scene {scene.scene_index} complete ({scene_duration:.1f}s)",
                STAGE_WEIGHTS["plan"] + STAGE_WEIGHTS["scenes"] * idx / total,
            )

        assemble_base = STAGE_WEIGHTS["plan"] + STAGE_WEIGHTS["scenes"]

        self._update_job(job, "processing", "editor", "Assembling picture", assemble_base + 0.05)
        merged_video = render_service.concat_videos(clips)

        self._update_job(job, "processing", "editor", "Mixing narration", assemble_base + 0.11)
        merged_audio = render_service.concat_audio(audios)
        narration_mp3 = render_service.to_mp3(merged_audio)

        self._update_job(job, "processing", "editor", "Timing captions", assemble_base + 0.15)
        merged_subs = subtitle_service.merge_scene_subtitles(sub_texts, durations)

        self._update_job(job, "processing", "editor", "Mastering final movie", assemble_base + 0.18)
        final_video = render_service.mux(
            merged_video,
            merged_audio,
            merged_subs,
            music_path=Path(music_path) if music_path else None,
        )

        # Confirm we really produced a playable movie before declaring success.
        info = ff.validate_output(final_video, expect_video=True, expect_audio=True)

        poster = ""
        try:
            poster = str(render_service.extract_poster(final_video))
        except Exception as exc:  # noqa: BLE001 - a missing thumbnail must not fail the render
            logger.warning("Could not extract poster frame: %s", exc)

        job.output_video_path = str(final_video)
        job.output_audio_path = str(narration_mp3)
        job.output_subtitle_path = str(merged_subs)
        job.output_poster_path = poster
        job.output_duration_seconds = info.duration
        job.last_error = ""

        project.status = "completed"
        self._update_job(
            job, "completed", "done",
            f"Movie ready — {info.duration:.1f}s, {info.width}x{info.height}",
            1.0,
        )
        self.db.add(project)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def _clip_length(self, narration_duration: float, index: int, total: int) -> float:
        """Length to render a clip at so the assembled picture matches the audio.

        Crossfades overlap neighbouring clips, so every clip except the last
        must be extended by the transition duration; otherwise the finished
        picture ends up ``fade * (n - 1)`` seconds shorter than the narration.
        """
        transition = (settings.render_transition or "none").strip().lower()
        fade = float(settings.render_transition_seconds)
        if total > 1 and transition not in ("", "none") and fade > 0 and index < total:
            return narration_duration + fade
        return narration_duration

    def regenerate_scene(self, project: Project, scene: Scene) -> Scene:
        root = _project_dir(project.id)
        image_service = ImageService(root / "images")
        tts_service = TTSService(root / "audio")
        subtitle_service = SubtitleService(root / "subs")
        render_service = RenderService(root / "video")

        result = tts_service.synthesize_detailed(scene.script_chunk, scene.scene_index)
        duration = max(float(settings.render_min_scene_seconds), result.duration)

        img = image_service.generate(scene.image_prompt, scene.scene_index)
        clip = render_service.image_to_clip(img, duration, scene.scene_index)
        sub = subtitle_service.create_scene_subtitle(scene.script_chunk, duration, scene.scene_index)

        scene.image_path = str(img)
        scene.video_path = str(clip)
        scene.narration_path = str(result.path)
        scene.subtitle_path = str(sub)
        scene.duration_seconds = duration
        scene.audio_duration_seconds = duration
        scene.tts_provider = result.provider
        scene.tts_voice = result.voice or ""

        self.db.add(scene)
        self.db.commit()
        self.db.refresh(scene)
        return scene

    def _update_job(self, job: Job, status: str, stage: str, message: str, progress: float) -> None:
        job.status = status
        job.stage = stage
        job.message = message
        job.progress = max(0.0, min(1.0, float(progress)))
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        crud.create_job_event(self.db, job.id, stage=stage, level="info", message=message, progress=job.progress)

    def mark_failure(self, job: Job, error: Exception) -> None:
        job.status = "failed"
        job.stage = "error"
        job.message = str(error)
        job.last_error = str(error)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        crud.create_job_event(self.db, job.id, stage="error", level="error", message=str(error), progress=job.progress)

