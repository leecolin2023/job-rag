"""Shared read-only corpus snapshots and structural scope."""
from sqlalchemy import select
from ..storage import Job
from ..preprocessing.normalize import digest
from ..storage.serialization import serialize
from .filters import matches

class SnapshotChanged(ValueError):
    pass


def load_catalog(db):
    with db.session() as session:
        records = list(session.scalars(select(Job).order_by(Job.key)))
        rows = [serialize(job, detail=True) for job in records]
        return records, digest(rows)


def eligible_jobs(jobs, filters):
    return [job for job in jobs if matches(job, filters) and (
        job.job_status == "active" if filters.active_only else
        filters.include_closed or job.job_status in {"active", "unknown"})]
