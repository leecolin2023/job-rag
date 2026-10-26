"""Shared job output shape; no queries, ranking, or model calls."""


def serialize(job, detail=False):
    result = {key: job.raw.get(key, "") for key in (
        "title", "company", "location", "salary", "experience", "education", "url", "collected_at")}
    result.update(key=job.key, source=job.source, job_id=job.job_id,
                  job_status=job.job_status, status_reason=job.status_reason,
                  last_verified_at=job.last_verified_at, last_seen_at=job.last_seen_at,
                  first_seen_at=job.first_seen_at, version=job.version,
                  indexed_version=job.indexed_version, normalized=job.normalized,
                  collection_status=job.raw.get("status", ""))
    if detail:
        result["raw"] = job.raw
    return result
