import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..config import Settings
from ..retrieval.candidates import CandidateRequest, candidates
from ..querying.catalog import BatchRequest, CatalogRequest, SnapshotChanged, batch_jobs, catalog_query
from ..querying.jobs import job_detail, knowledge_base_stats
from ..querying.summarize_job_technical_mentions import TechnicalSummaryRequest, summarize_job_technical_mentions
from ..storage import Database
from ..preprocessing.importer import import_csv
from ..storage.status import set_status
from ..retrieval.search import SearchRequest
from ..retrieval.answer import answer


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
        return knowledge_base_stats(db, settings)

    @app.post("/api/search")
    def search(request: SearchRequest):
        return answer(db, settings, request)

    @app.post("/api/candidates")
    def recall(request: CandidateRequest):
        try:
            return candidates(db, settings, request)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/catalog")
    def catalog(request: CatalogRequest):
        try:
            return catalog_query(db, request)
        except SnapshotChanged as exc:
            raise HTTPException(409, str(exc))

    @app.post("/api/jobs/batch")
    def batch(request: BatchRequest):
        try:
            return batch_jobs(db, request)
        except SnapshotChanged as exc:
            raise HTTPException(409, str(exc))

    @app.post("/api/technical-mentions")
    def technical_mentions(request: TechnicalSummaryRequest):
        try:
            return summarize_job_technical_mentions(db, request)
        except SnapshotChanged as exc:
            raise HTTPException(409, str(exc))

    @app.get("/api/jobs/{job_id}")
    def detail(job_id: str, source: str = "boss", sections: list[str] | None = Query(default=None), include_raw: bool = True):
        try:
            return job_detail(db, job_id, source, sections, include_raw)
        except KeyError:
            raise HTTPException(404, "岗位不存在")
        except ValueError as exc:
            raise HTTPException(400, str(exc))

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
