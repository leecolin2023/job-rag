from sqlalchemy import select

from ..storage import IndexTask, now


def enqueue(session, job, settings):
    existing = session.scalar(select(IndexTask).where(
        IndexTask.job_key == job.key, IndexTask.version == job.version,
        IndexTask.signature == settings.index_signature))
    if existing:
        existing.state, existing.error = "pending", None
    else:
        session.add(IndexTask(job_key=job.key, version=job.version,
                              signature=settings.index_signature, state="pending", attempts=0, created_at=now()))
