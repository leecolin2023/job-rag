"""Optional job-level reranking of a bounded frozen candidate pool."""
from sqlalchemy import select
from ..providers.rerank import RerankInputError, rerank
from ..providers.rerank_inputs import representation
from ..storage import Job


def rerank_candidates(db, settings, query, records):
    metadata = {"requested": True, "applied": False, "pool_jobs": min(len(records), 60),
                "input_representation": "full_title_and_exact_jd", "scores_are_probabilities": False}
    if not settings.rerank_enabled:
        return records, {**metadata, "reason": "not_configured"}
    if not records:
        return records, {**metadata, "reason": "empty_candidates"}
    pool = records[:60]
    with db.session() as session:
        jobs = {job.key: job for job in session.scalars(select(Job).where(Job.key.in_([r["key"] for r in pool])))}
        if any(r["key"] not in jobs or jobs[r["key"]].version != r["version"] or
               jobs[r["key"]].job_status != r["job_status"] for r in pool):
            return [], {**metadata, "reason": "candidates_changed"}
        documents = [representation(jobs[r["key"]].raw) for r in pool]
    try:
        ranking, input_stats = rerank(settings, query, documents)
    except Exception as exc:
        # Do not leak HTTP bodies, workspace credentials or model prompts.
        return records, {**metadata, "reason": "input_preflight_failed" if isinstance(exc, RerankInputError) else "provider_unavailable"}
    ordered = [{**pool[item["index"]], "rerank_score": item["relevance_score"]} for item in ranking]
    # A slow model call must never make a changed or closed job eligible again.
    with db.session() as session:
        valid = []
        for record in ordered + records[60:]:
            current = session.get(Job, record["key"])
            if current and current.version == record["version"] and current.job_status == record["job_status"]:
                valid.append(record)
    return valid, {**metadata, "applied": True, "model": settings.rerank_model,
                   "input_preflight": input_stats, "changed_jobs_excluded": len(records) - len(valid)}
