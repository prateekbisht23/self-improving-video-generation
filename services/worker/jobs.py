"""RQ job definitions + enqueue helpers.

The API enqueues `process_asset` by import path; a worker process imports this module and
runs it. Retries: RQ re-enqueues a failed job after the given intervals, and because the
pipeline is resumable each retry starts at the failed stage.
"""

import logging
import uuid
from functools import lru_cache

from redis import Redis
from rq import Queue, Retry, get_current_job

from config.settings import get_settings
from db.models import AssetStatus, MediaAsset
from db.session import session_scope
from services.worker.pipeline import run_pipeline

QUEUE = "media"
log = logging.getLogger("jobs")


@lru_cache
def redis_conn() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_queue() -> Queue:
    # is_async=False runs jobs inline (tests / debugging) through the same code path.
    return Queue(QUEUE, connection=redis_conn(), is_async=not get_settings().rq_sync)


def process_asset(asset_id: str, force_from: str | None = None) -> dict:
    try:
        return run_pipeline(asset_id, force_from=force_from)
    except Exception:
        job = get_current_job()
        if job is not None and job.retries_left:
            # RQ will run this job again: report "queued" so clients keep waiting instead of
            # treating a transient failure (e.g. a 429) as final. last_error keeps the reason.
            with session_scope() as s:
                a = s.get(MediaAsset, uuid.UUID(asset_id))
                a.status = AssetStatus.queued
                a.last_error = f"retrying ({job.retries_left} left) after: {a.last_error}"[:2000]
        raise


def enqueue_processing(asset_id: uuid.UUID, force_from: str | None = None) -> str:
    with session_scope() as s:
        a = s.get(MediaAsset, asset_id)
        a.status, a.last_error = AssetStatus.queued, None
    job = get_queue().enqueue(
        process_asset, str(asset_id), force_from,
        retry=Retry(max=2, interval=[15, 60]),  # transient failures: rate limits, timeouts
        job_timeout=30 * 60,
        result_ttl=24 * 3600, failure_ttl=7 * 24 * 3600,
        description=f"process asset {asset_id}" + (f" from {force_from}" if force_from else ""),
    ) if not get_settings().rq_sync else None
    if job is None:  # sync mode: run now, but let failures land in the DB rather than the request
        try:
            process_asset(str(asset_id), force_from)
        except Exception:
            log.exception("inline processing failed for %s", asset_id)
        return "inline"
    with session_scope() as s:
        s.get(MediaAsset, asset_id).rq_job_id = job.id
    return job.id


def _enqueue(fn, *args, description: str):
    """Run via RQ, or inline in sync mode (errors are recorded in the DB by the job itself)."""
    if get_settings().rq_sync:
        try:
            fn(*args)
        except Exception:
            log.exception("inline job failed: %s", description)
        return "inline"
    return get_queue().enqueue(fn, *args, job_timeout=30 * 60, result_ttl=24 * 3600,
                               failure_ttl=7 * 24 * 3600, description=description).id


def edit_job(session_id: str) -> dict:
    from services.worker.editing import run_editing_session

    return run_editing_session(session_id)


def render_job(version_id: str) -> dict:
    from services.worker.editing import render_version

    return render_version(uuid.UUID(version_id))


def enqueue_edit(session_id: uuid.UUID) -> str:
    # No automatic retry: a session is an expensive, single-shot agent run; retry is explicit.
    return _enqueue(edit_job, str(session_id), description=f"edit session {session_id}")


def enqueue_render(version_id: uuid.UUID) -> str:
    return _enqueue(render_job, str(version_id), description=f"render timeline version {version_id}")
