import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from conftest import csv_bytes, row
from job_rag.api import create_app
from job_rag.catalog import BatchRequest, CatalogRequest, JobRef, SnapshotChanged, batch_jobs, catalog_query
from job_rag.ingest import import_csv, set_status
from job_rag.mcp_server import create_mcp


def test_exhaustive_without_index_and_pagination(db, settings):
    import_csv(db, settings, csv_bytes(*(row(str(i), description="vLLM 优先") for i in range(75))))
    first = catalog_query(db, CatalogRequest(terms=["vllm"], page_size=30))
    assert first["matched_jobs"] == 75
    assert first["count_complete"] and first["next_offset"] == 30
    ids = [r["key"] for r in first["results"]]
    for offset in (30, 60):
        page = catalog_query(db, CatalogRequest(terms=["vllm"], page_size=30,
                                             offset=offset, snapshot_id=first["snapshot_id"]))
        ids.extend(r["key"] for r in page["results"])
    assert len(ids) == len(set(ids)) == 75
    assert not page["has_more"] and page["next_offset"] is None
    count = catalog_query(db, CatalogRequest(terms=["vllm"], count_only=True))
    assert count["results"] == [] and count["matched_jobs"] == 75
    assert count["snapshot_id"] == first["snapshot_id"]


def test_matching_modes_and_scope(db, settings):
    import_csv(db, settings, csv_bytes(row("a", title="vLLM", description="Python"),
                                     row("b", title="xvLLMy", description="SGLang"),
                                     row("c", title="无", description="")))
    def query(**kwargs):
        return catalog_query(db, CatalogRequest(**kwargs))
    assert query(terms=["vllm"])["matched_jobs"] == 2
    assert query(terms=["vllm"], match_mode="token")["matched_jobs"] == 1
    assert query(terms=["vllm"], case_sensitive=True)["matched_jobs"] == 0
    assert query(terms=["vLLM"], fields=["description"])["matched_jobs"] == 0
    assert query(terms=["vLLM", "Python"])["matched_jobs"] == 1
    assert query(terms=["Python", "SGLang"], operator="or")["matched_jobs"] == 2
    assert query()["missing_description_jobs"] == 1
    assert query(filters={"city": "深圳"})["matched_jobs"] == 0
    set_status(db, "boss:a", "closed", "确认关闭")
    set_status(db, "boss:b", "suspected_expired", "无法核验")
    assert query()["matched_jobs"] == 1
    assert query(filters={"include_closed": True})["matched_jobs"] == 3
    assert query(filters={"active_only": True})["matched_jobs"] == 0


@pytest.mark.parametrize("change", ["status", "content", "new"])
def test_snapshot_invalidates_changes(db, settings, change):
    import_csv(db, settings, csv_bytes(row()))
    initial = catalog_query(db, CatalogRequest())
    if change == "status":
        set_status(db, "boss:one", "active", "核验")
    else:
        import_csv(db, settings, csv_bytes(row("new" if change == "new" else "one", description="changed")))
    with pytest.raises(SnapshotChanged):
        catalog_query(db, CatalogRequest(offset=1, snapshot_id=initial["snapshot_id"]))
    with pytest.raises(SnapshotChanged):
        batch_jobs(db, BatchRequest(jobs=[JobRef(job_id="one")], corpus_id=initial["corpus_id"]))


def test_snapshot_binds_conditions_and_batch_errors(db, settings):
    import_csv(db, settings, csv_bytes(row()))
    first = catalog_query(db, CatalogRequest())
    with pytest.raises(SnapshotChanged):
        catalog_query(db, CatalogRequest(terms=["RAG"], snapshot_id=first["snapshot_id"]))
    batch = batch_jobs(db, BatchRequest(jobs=[JobRef(job_id="one", version=1),
                                            JobRef(job_id="missing"), JobRef(job_id="one", version=2)],
                                       corpus_id=first["corpus_id"]))
    assert batch["results"][0]["raw"]["description"]
    assert [e["reason"] for e in batch["errors"]] == ["not_found", "version_changed"]


@pytest.mark.parametrize("payload", [{"offset": 1}, {"terms": [" "]}, {"terms": ["a" * 201]},
                                    {"fields": []}, {"fields": ["company"]}, {"operator": "xor"},
                                    {"page_size": 101}, {"filters": {"ctiy": "广州"}},
                                    {"filters": {"active_only": True, "include_closed": True}}])
def test_invalid_catalog_requests(payload):
    with pytest.raises(ValidationError):
        CatalogRequest(**payload)


def test_api_and_mcp_schema(settings):
    with TestClient(create_app(settings)) as client:
        import_csv(client.app.state.db, settings, csv_bytes(row()))
        page = client.post("/api/catalog", json={}).json()
        assert page["matched_jobs"] == 1
        assert client.post("/api/catalog", json={"offset": 1}).status_code == 422
        assert client.post("/api/catalog", json={"snapshot_id": "stale"}).status_code == 409
        assert client.post("/api/jobs/batch", json={"jobs": [{"job_id": "one"}]}).json()["results"][0]["job_id"] == "one"
        assert client.post("/api/jobs/batch", json={"jobs": [{"job_id": "one"}], "corpus_id": "stale"}).status_code == 409
        assert client.post("/api/jobs/batch", json={"jobs": []}).status_code == 422
    tools = {tool.name: tool for tool in asyncio.run(create_mcp().list_tools())}
    assert {"get_job", "get_jobs_batch", "query_job_catalog", "search_job_candidates"} <= tools.keys()
    assert "snapshot_id" in tools["query_job_catalog"].inputSchema["properties"]


def test_mcp_forwards_validated_requests_and_conflicts(settings, monkeypatch):
    from mcp.server.fastmcp.exceptions import ToolError

    original_client = httpx.Client
    with TestClient(create_app(settings)) as api:
        import_csv(api.app.state.db, settings, csv_bytes(row()))

        def handle(request):
            response = api.request(request.method, request.url.path, content=request.content,
                                   headers={"Content-Type": "application/json"})
            return httpx.Response(response.status_code, json=response.json())

        monkeypatch.setattr("job_rag.mcp_server.httpx.Client", lambda **kwargs:
                            original_client(**kwargs, transport=httpx.MockTransport(handle)))
        server = create_mcp()
        result = asyncio.run(server.call_tool("query_job_catalog", {"terms": ["RAG"], "count_only": True}))
        assert "matched_jobs" in str(result) and "exact_literal_not_semantic" in str(result)
        result = asyncio.run(server.call_tool("get_jobs_batch", {"jobs": [{"job_id": "one", "version": 2}]}))
        assert "version_changed" in str(result)
        with pytest.raises(ToolError, match="第一页"):
            asyncio.run(server.call_tool("query_job_catalog", {"snapshot_id": "stale"}))
