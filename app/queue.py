from __future__ import annotations

from redis import Redis
from rq.command import send_stop_job_command
from rq.job import Job
from rq import Queue, Retry

from app.config import settings


def get_queue() -> Queue | None:
    if not settings.redis_url.strip():
        return None
    conn = Redis.from_url(settings.redis_url)
    return Queue(settings.queue_name, connection=conn, default_timeout=60 * 60)


def get_redis_connection() -> Redis | None:
    if not settings.redis_url.strip():
        return None
    return Redis.from_url(settings.redis_url)


def _retry_policy() -> Retry:
    intervals = [int(v.strip()) for v in settings.rq_retry_intervals.split(",") if v.strip()]
    return Retry(max=max(1, settings.rq_retry_max), interval=intervals or [30, 90, 180])


def enqueue_pipeline(
    project_id: int,
    job_id: int,
    resume_from_scene_index: int | None = None,
    visual_mode: str = "basic",
    cinematic_quality_profile: str = "balanced",
    output_resolution: str = "1080p",
    output_fps: int = 30,
    burn_subtitles: bool | None = None,
    music_path: str | None = None,
    export_stems: bool = True,
) -> str | None:
    try:
        queue = get_queue()
    except Exception:
        return None
    if not queue:
        return None
    try:
        task = queue.enqueue(
            "app.worker.run_pipeline_job",
            project_id,
            job_id,
            resume_from_scene_index,
            visual_mode,
            cinematic_quality_profile,
            output_resolution,
            output_fps,
            burn_subtitles,
            music_path,
            export_stems,
            retry=_retry_policy(),
            result_ttl=24 * 60 * 60,
        )
        return task.id
    except Exception:
        return None


def enqueue_music_generation(generation_id: int, seed: int | None = None) -> str | None:
    try:
        queue = get_queue()
    except Exception:
        return None
    if not queue:
        return None
    try:
        task = queue.enqueue(
            "app.worker.run_music_generation_job",
            generation_id,
            seed,
            retry=_retry_policy(),
            result_ttl=24 * 60 * 60,
        )
        return task.id
    except Exception:
        return None


def cancel_queued_job(queue_job_id: str | None) -> bool:
    queue_job_id = "" if queue_job_id is None else queue_job_id.strip()
    try:
        conn = Redis.from_url(settings.redis_url)
    except Exception:
        return False
    try:
        job = Job.fetch(queue_job_id, connection=conn)
    except Exception:
        return False
    try:
        if job.get_status(refresh=True) == "started":
            send_stop_job_command(conn, queue_job_id)
        else:
            job.cancel()
        return True
    except Exception:
        return False


