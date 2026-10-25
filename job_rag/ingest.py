import csv
import io

from sqlalchemy import delete, select

from .db import Chunk, IndexTask, Job, Revision, StatusEvent, now
from .models import embed
from .normalize import REQUIRED_COLUMNS, content_hash, digest, documents, normalize

STATUSES = {"unknown", "active", "suspected_expired", "closed"}


def parse_csv(content):
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff"), newline=""))
    if not REQUIRED_COLUMNS.issubset(reader.fieldnames or []):
        raise ValueError("CSV missing columns: " + ", ".join(sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))))
    rows, seen = [], set()
    for line, row in enumerate(reader, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"CSV record {line}: column count mismatch")
        row = {k: v.strip() if k != "description" else v for k, v in row.items()}
        job_id = row["job_id"]
        if not job_id or job_id in seen:
            raise ValueError(f"CSV record {line}: empty or duplicate job_id")
        seen.add(job_id)
        rows.append(row)
    if not rows:
        raise ValueError("CSV has no records")
    return rows


def enqueue(session, job, settings):
    existing = session.scalar(select(IndexTask).where(
        IndexTask.job_key == job.key, IndexTask.version == job.version,
        IndexTask.signature == settings.index_signature))
    if existing:
        existing.state, existing.error = "pending", None
    else:
        session.add(IndexTask(job_key=job.key, version=job.version,
                              signature=settings.index_signature, state="pending", attempts=0, created_at=now()))


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


def run_index_tasks(db, settings):
    """Single-writer worker; atomic replace, safe retry after interruption."""
    stats = {"indexed": 0, "failed": 0, "obsolete": 0}
    with db.session() as session:
        ids = list(session.scalars(select(IndexTask.id).where(IndexTask.state.in_(["pending", "failed"])).order_by(IndexTask.id)))
    for task_id in ids:
        with db.session() as session:
            task = session.get(IndexTask, task_id)
            job = session.get(Job, task.job_key)
            if task.version != job.version or task.signature != settings.index_signature:
                task.state = "obsolete"
                session.commit()
                stats["obsolete"] += 1
                continue
            texts = documents(job.raw)
            old_chunks = list(session.scalars(select(Chunk).where(Chunk.job_key == job.key).order_by(Chunk.ordinal)))
            # Timestamp/collection metadata edits reuse vectors if searchable text is identical.
            reuse = (job.index_signature == settings.index_signature and
                     [chunk.text for chunk in old_chunks] == texts)
            vectors = [chunk.embedding for chunk in old_chunks] if reuse else None
        try:
            if vectors is None:
                vectors = embed(settings, texts)
            with db.session.begin() as session:
                task = session.get(IndexTask, task_id)
                job = session.get(Job, task.job_key, with_for_update=True)
                if job.version != task.version:
                    task.state = "obsolete"
                    stats["obsolete"] += 1
                    continue
                session.execute(delete(Chunk).where(Chunk.job_key == job.key))
                for ordinal, (text, vector) in enumerate(zip(texts, vectors)):
                    session.add(Chunk(job_key=job.key, version=job.version, ordinal=ordinal,
                                      text=text, embedding=vector))
                job.indexed_version, job.index_signature = job.version, settings.index_signature
                task.state, task.error, task.attempts = "done", None, task.attempts + 1
            stats["indexed"] += 1
        except Exception as exc:
            with db.session.begin() as session:
                task = session.get(IndexTask, task_id)
                task.state, task.attempts = "failed", task.attempts + 1
                # Do not persist provider URLs, response bodies or secrets.
                task.error = type(exc).__name__
            stats["failed"] += 1
    return stats


def reindex(db, settings):
    with db.session.begin() as session:
        for job in session.scalars(select(Job)):
            enqueue(session, job, settings)
    return run_index_tasks(db, settings)


def set_status(db, key, status, reason):
    if status not in STATUSES or not reason.strip():
        raise ValueError("Valid status and nonempty evidence/reason required")
    with db.session.begin() as session:
        job = session.get(Job, key, with_for_update=True)
        if job is None:
            raise KeyError(key)
        stamp = now()
        session.add(StatusEvent(job_key=key, old_status=job.job_status,
                                new_status=status, reason=reason, created_at=stamp))
        job.job_status, job.status_reason = status, reason
        # A failure or unknown state does not constitute a successful verification.
        if status in {"active", "closed"}:
            job.last_verified_at = stamp
