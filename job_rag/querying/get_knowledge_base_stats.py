"""Read-only job details/history and corpus/index statistics."""
from sqlalchemy import func, select

from ..storage import IndexTask, Job, Revision, StatusEvent
from ..storage.serialization import serialize
from .sections import parse_query_sections, section_coverage, SECTION_RULE_VERSION


def knowledge_base_stats(db, settings):
    with db.session() as session:
        jobs = list(session.scalars(select(Job)))
        statuses = dict(session.execute(select(Job.job_status, func.count()).group_by(Job.job_status)).all())
        tasks = dict(session.execute(select(IndexTask.state, func.count()).group_by(IndexTask.state)).all())
        coverage = [section_coverage(parse_query_sections(j.raw.get("description", ""))) for j in jobs]
        return {"total": len(jobs), "statuses": statuses, "index_tasks": tasks,
                "indexed": sum(j.indexed_version == j.version and j.index_signature == settings.index_signature for j in jobs),
                "cities": sorted({j.normalized["city"] for j in jobs}),
                "retrieval": "hybrid" if settings.semantic_enabled else "keyword",
                "generation_enabled": bool(settings.chat_api_key and settings.chat_model),
                "rerank_configured": settings.rerank_enabled,
                "descriptions": {"present": sum(bool(j.raw.get("description", "").strip()) for j in jobs),
                                 "missing": sum(not j.raw.get("description", "").strip() for j in jobs)},
                "section_coverage": {"rule_version": SECTION_RULE_VERSION,
                    "jobs_with_recognized_sections": sum(c["has_recognized_sections"] for c in coverage),
                    "jobs_with_unknown_text": sum(c["has_unknown_text"] for c in coverage),
                    "classification": "rule_derived"},
                "freshness": {"latest_collected_at": max((j.raw.get("collected_at", "") for j in jobs), default=None),
                              "latest_seen_at": max((j.last_seen_at for j in jobs if j.last_seen_at), default=None),
                               "latest_verified_at": max((j.last_verified_at for j in jobs if j.last_verified_at), default=None)}}
