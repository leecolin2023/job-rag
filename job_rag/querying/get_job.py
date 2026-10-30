"""Full job details, versions and status history."""
from sqlalchemy import select
from ..storage import Job, Revision, StatusEvent
from ..storage.serialization import serialize
from .get_jobs_batch import enrich_job_sections

def job_detail(db, job_id, source="boss", sections=None, include_raw=True):
    with db.session() as session:
        job = session.get(Job, f"{source}:{job_id}")
        if not job:
            raise KeyError(job_id)
        result = serialize(job, detail=True)
        result["versions"] = [{"version": r.version, "created_at": r.created_at} for r in
                              session.scalars(select(Revision).where(Revision.job_key == job.key).order_by(Revision.version))]
        result["status_history"] = [{"old_status": e.old_status, "new_status": e.new_status,
                                     "reason": e.reason, "created_at": e.created_at} for e in
                                    session.scalars(select(StatusEvent).where(StatusEvent.job_key == job.key).order_by(StatusEvent.id))]
        return enrich_job_sections(result, sections, include_raw)
