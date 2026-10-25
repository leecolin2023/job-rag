import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .config import Settings
from .candidates import CandidateRequest, candidates
from .db import Database, IndexTask, Job, Revision, StatusEvent
from .ingest import import_csv, set_status
from .search import SearchRequest, answer, serialize


class StatusRequest(BaseModel):
    source: str = "boss"
    status: str = Field(pattern="^(unknown|active|suspected_expired|closed)$")
    reason: str = Field(min_length=1, max_length=2000)


def create_app(settings=None):
    settings = settings or Settings()
    db = Database(settings)

    @asynccontextmanager
    async def lifespan(app):
        db.initialize()
        yield
        db.engine.dispose()

    app = FastAPI(title="Job-RAG", version="0.1.0", lifespan=lifespan)
    app.state.db, app.state.settings = db, settings

    def admin(authorization: str | None = Header(default=None)):
        if not settings.admin_token:
            raise HTTPException(403, "管理 API 未启用；请使用 CLI 或配置 ADMIN_TOKEN")
        if not secrets.compare_digest(authorization or "", f"Bearer {settings.admin_token}"):
            raise HTTPException(401, "无效的管理凭据")

    @app.get("/")
    def index():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/health")
    def health():
        with db.session() as session:
            session.execute(select(1))
        return {"status": "ok", "retrieval": "hybrid" if settings.semantic_enabled else "keyword"}

    @app.get("/api/stats")
    def stats():
        with db.session() as session:
            jobs = list(session.scalars(select(Job)))
            statuses = dict(session.execute(select(Job.job_status, func.count()).group_by(Job.job_status)).all())
            tasks = dict(session.execute(select(IndexTask.state, func.count()).group_by(IndexTask.state)).all())
            return {"total": len(jobs), "statuses": statuses, "index_tasks": tasks,
                    "indexed": sum(j.indexed_version == j.version and j.index_signature == settings.index_signature for j in jobs),
                    "cities": sorted({j.normalized["city"] for j in jobs}),
                    "retrieval": "hybrid" if settings.semantic_enabled else "keyword",
                    "generation_enabled": bool(settings.chat_api_key and settings.chat_model)}

    @app.post("/api/search")
    def search(request: SearchRequest):
        return answer(db, settings, request)

    @app.post("/api/candidates")
    def recall(request: CandidateRequest):
        try:
            return candidates(db, settings, request)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/jobs/{job_id}")
    def job_detail(job_id: str, source: str = "boss"):
        with db.session() as session:
            job = session.get(Job, f"{source}:{job_id}")
            if not job:
                raise HTTPException(404, "岗位不存在")
            result = serialize(job, detail=True)
            result["versions"] = [{"version": r.version, "created_at": r.created_at} for r in
                                  session.scalars(select(Revision).where(Revision.job_key == job.key).order_by(Revision.version))]
            result["status_history"] = [{"old_status": e.old_status, "new_status": e.new_status,
                                         "reason": e.reason, "created_at": e.created_at} for e in
                                        session.scalars(select(StatusEvent).where(StatusEvent.job_key == job.key).order_by(StatusEvent.id))]
            return result

    @app.post("/api/jobs/{job_id}/status", dependencies=[Depends(admin)])
    def update_status(job_id: str, payload: StatusRequest):
        try:
            set_status(db, f"{payload.source}:{job_id}", payload.status, payload.reason)
        except KeyError:
            raise HTTPException(404, "岗位不存在")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {"ok": True}

    @app.post("/api/import", dependencies=[Depends(admin)])
    async def ingest(request: Request, source: str = "boss"):
        # Stream with a bounded size; never accept an arbitrary server-side file path.
        content = bytearray()
        async for block in request.stream():
            content.extend(block)
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(413, "CSV 最大 20 MiB")
        try:
            from starlette.concurrency import run_in_threadpool
            result = await run_in_threadpool(import_csv, db, settings, bytes(content), source)
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(400, str(exc))
        return {**result, "message": "数据已入库，请运行 job-rag worker 构建索引"}

    return app


app = create_app()
