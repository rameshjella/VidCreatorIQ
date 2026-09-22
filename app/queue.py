from __future__ import annotations

from redis import Redis
from rq import Queue, Retry

from app.config import settings


def get_queue() -> Queue | None:
    if not settings.redis_url.strip():
        return None
    conn = Redis.from_url(settings.redis_url)
    return Queue(settings.queue_name, connection=conn, default_timeout=60 * 60)


def _retry_policy() -> Retry:
    intervals = [int(v.strip()) for v in settings.rq_retry_intervals.split(",") if v.strip()]
    return Retry(max=max(1, settings.rq_retry_max), interval=intervals or [30, 90, 180])


def enqueue_pipeline(
    project_id: int,
    job_id: int,
    resume_from_scene_index: int | None = None,
    visual_mode: str = "basic",
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
            retry=_retry_policy(),
            result_ttl=24 * 60 * 60,
        )
        return task.id
    except Exception:
        return None

