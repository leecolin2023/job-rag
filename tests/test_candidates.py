import asyncio

import pytest
from fastapi.testclient import TestClient

from job_rag.api import create_app
from job_rag.candidates import CandidateRequest, candidates
from job_rag.ingest import import_csv, run_index_tasks, set_status
from job_rag.mcp_server import create_mcp

from conftest import csv_bytes, row


def test_multiquery_deduplicates_and_preserves_constraints(db, settings):
    import_csv(db, settings, csv_bytes(row(), row("low", salary="10-25K"), row("remote", location="深圳")))
    run_index_tasks(db, settings)
    result = candidates(db, settings, CandidateRequest(query="广州 20K以上 RAG",
                        reformulations=["知识库 向量检索", "深圳 Python 5K以上"]))
    assert [item["job_id"] for item in result["results"]] == ["one"]
    assert result["semantic_assessment"] == "caller_llm_required"
    assert result["filters"]["min_salary"] == 20000
    assert result["filters"]["city"] == "广州"


def test_expansion_does_not_invent_filters(db, settings):
    import_csv(db, settings, csv_bytes(row(), row("remote", location="深圳")))
    run_index_tasks(db, settings)
    result = candidates(db, settings, CandidateRequest(query="RAG", reformulations=["深圳 Python 50K以上"]))
    assert result["filters"]["city"] is None
    assert result["filters"]["min_salary"] is None
    assert {r["job_id"] for r in result["results"]} == {"one", "remote"}


def test_closed_not_in_candidates(db, settings):
    import_csv(db, settings, csv_bytes(row()))
    run_index_tasks(db, settings)
    set_status(db, "boss:one", "closed", "已关闭")
    assert candidates(db, settings, CandidateRequest(query="RAG", reformulations=["Python"]))["results"] == []


def test_candidate_api(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        import_csv(app.state.db, settings, csv_bytes(row()))
        run_index_tasks(app.state.db, settings)
        result = client.post("/api/candidates", json={"query": "RAG", "reformulations": ["知识库"]})
        assert result.status_code == 200
        assert result.json()["results"][0]["job_id"] == "one"
        assert client.post("/api/candidates", json={"query": "RAG", "reformulations": ["x"] * 5}).status_code == 422


def test_mcp_only_readonly_tools():
    async def check():
        server = create_mcp()
        tools = await server.list_tools()
        assert {tool.name for tool in tools} == {"get_knowledge_base_stats", "search_job_candidates", "get_job",
                                               "query_job_catalog", "get_jobs_batch"}

    asyncio.run(check())
