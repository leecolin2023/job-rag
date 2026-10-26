"""Transactional incremental import; no chunking or model calls."""
from ..storage import Job, Revision, now
from ..indexing.tasks import enqueue
from .normalize import content_hash, digest, normalize
from .validation import parse_csv


def import_csv(db, settings, content, source="boss"):
    if not source or len(source) > 60 or ":" in source:
        raise ValueError("source must be 1-60 characters and must not contain ':'")
    rows = parse_csv(content)  # Validate the entire input before writing anything.
    stats = {"created": 0, "updated": 0, "unchanged": 0, "total": len(rows)}
    stamp = now()
    with db.session.begin() as session:
        for row in rows:
            key = f"{source}:{row['job_id']}"
            raw_hash, search_hash = digest(row), content_hash(row)
            job = session.get(Job, key)
            if job is None:
                job = Job(key=key, source=source, job_id=row["job_id"], raw=row,
                          normalized=normalize(row), raw_hash=raw_hash, content_hash=search_hash,
                          version=1, job_status="unknown", status_reason="尚未核验招聘状态",
                          first_seen_at=stamp, last_seen_at=stamp)
                session.add(job)
                session.flush()
                stats["created"] += 1
            elif job.raw_hash != raw_hash:
                job.version += 1
                job.raw, job.normalized = row, normalize(row)
                job.raw_hash, job.content_hash = raw_hash, search_hash
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1
                job.last_seen_at = stamp
                if job.indexed_version != job.version or job.index_signature != settings.index_signature:
                    enqueue(session, job, settings)
                continue
            job.last_seen_at = stamp
            session.add(Revision(job_key=key, version=job.version, raw=row,
                                 normalized=job.normalized, created_at=stamp))
            enqueue(session, job, settings)
    # Absence in a CSV never closes a job. Observation time is not verification time.
    return stats
