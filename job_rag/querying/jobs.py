"""Read-only job details/history and corpus/index statistics."""
from sqlalchemy import func, select

from ..storage import IndexTask, Job, Revision, StatusEvent
from ..storage.serialization import serialize


def knowledge_base_stats(db, settings):
    with db.session() as session:
        jobs = list(session.scalars(select(Job)))
        statuses = dict(session.execute(select(Job.job_status, func.count()).group_by(Job.job_status)).all())
        tasks = dict(session.execute(select(IndexTask.state, func.count()).group_by(IndexTask.state)).all())
        return {"total": len(jobs), "statuses": statuses, "index_tasks": tasks,
                "indexed": sum(j.indexed_version == j.version and j.index_signature == settings.index_signature for j in jobs),
                "cities": sorted({j.normalized["city"] for j in jobs}),
                "retrieval": "hybrid" if settings.semantic_enabled else "keyword",
                "generation_enabled": bool(settings.chat_api_key and settings.chat_model)}


def job_detail(db, job_id, source="boss"):
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
        return result
