from sqlalchemy import delete, select

from ..storage import Chunk, IndexTask, Job
from ..providers.client import embed
from ..chunking import build_documents
from .tasks import enqueue


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
            try:
                docs = build_documents(job.raw, settings.chunking_strategy, settings.chunk_size,
                                       settings.chunk_budget_unit, settings.tokenizer_path)
            except Exception as exc:
                task.state, task.error, task.attempts = "failed", type(exc).__name__, task.attempts + 1
                session.commit()
                stats["failed"] += 1
                continue
            texts = [doc.text for doc in docs]
            old_chunks = list(session.scalars(select(Chunk).where(Chunk.job_key == job.key).order_by(Chunk.ordinal)))
            # Metadata-only edits reuse vectors when rendered text is unchanged.
            reuse = (job.index_signature == settings.index_signature and
                     [chunk.text for chunk in old_chunks] == texts)
            vectors = [chunk.embedding for chunk in old_chunks] if reuse else None
        try:
            if vectors is None:
                vectors = embed(settings, texts)
            if len(vectors) != len(docs):
                raise ValueError("Document/vector count mismatch")
            with db.session.begin() as session:
                task = session.get(IndexTask, task_id)
                job = session.get(Job, task.job_key, with_for_update=True)
                if job.version != task.version:
                    task.state = "obsolete"
                    stats["obsolete"] += 1
                    continue
                session.execute(delete(Chunk).where(Chunk.job_key == job.key))
                for ordinal, (doc, vector) in enumerate(zip(docs, vectors)):
                    session.add(Chunk(job_key=job.key, version=job.version, ordinal=ordinal,
                                       text=doc.text, details=doc.details, embedding=vector))
                job.indexed_version, job.index_signature = job.version, settings.index_signature
                task.state, task.error, task.attempts = "done", None, task.attempts + 1
            stats["indexed"] += 1
        except Exception as exc:
            with db.session.begin() as session:
                task = session.get(IndexTask, task_id)
                task.state, task.attempts = "failed", task.attempts + 1
                task.error = type(exc).__name__
            stats["failed"] += 1
    return stats


def reindex(db, settings):
    with db.session.begin() as session:
        for job in session.scalars(select(Job)):
            enqueue(session, job, settings)
    return run_index_tasks(db, settings)
