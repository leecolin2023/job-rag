"""Behavioral checks for section scope, evidence, conditions and full-corpus counts."""
import asyncio
import inspect
from collections import Counter

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from conftest import csv_bytes, row
from job_rag.interfaces.api import create_app
from job_rag.interfaces.mcp_server import create_mcp
from job_rag.preprocessing.importer import import_csv
from job_rag.querying.catalog import CatalogRequest, catalog_query
from job_rag.querying.get_jobs_batch import BatchRequest, batch_jobs
from job_rag.querying.sections import parse_query_sections
from job_rag.querying.summarize_job_technical_mentions import TechnicalSummaryRequest, summarize_job_technical_mentions
from job_rag.querying.catalog_snapshot import SnapshotChanged


def seed(db, settings):
    descriptions = {
        "main": "公司介绍：RAG产品。\n岗位职责：建设RAG检索。\n任职要求：必须掌握Python；熟悉Milvus；Python优先。\n加分项：Docker优先。",
        "alias": "岗位职责负责GraphRAG建设。\n任职要求：必须掌握Python或Java至少一门；无需Docker。",
        "preferred": "岗位职责：后端研发。\n加分项：有RAG经验优先。",
        "intro": "公司介绍：我们的产品解析岗位职责与任职要求，并支持RAG。\n任职要求：熟悉Java。",
        "unknown": "熟悉RAG和Python，能够独立开发。",
        "negative": "任职要求：不要求RAG，也无需Python。",
        "ragflow": "任职要求：熟悉RAGFlow和Docker。",
        "broken": "岗\n位\n职\n责：建设RAG问答。\n任\n职\n要\n求：必须掌握Python。",
    }
    import_csv(db, settings, csv_bytes(*(row(key, description=value) for key, value in descriptions.items())))
    return descriptions


def test_scope_aliases_unknown_and_original_offsets(db, settings):
    descriptions = seed(db, settings)
    request = CatalogRequest(terms=["RAG"], sections=["responsibilities", "requirements"], match_mode="ascii_token")
    result = catalog_query(db, request)
    assert {r["job_id"] for r in result["results"]} == {"main", "negative", "broken"}
    assert result["unresolved_jobs"] == 1 and not result["section_scope_complete"]
    assert result["preferred_only_match_jobs"] == 1
    assert result["unknown_match_sample"][0]["job_id"] == "unknown"
    for record in result["results"]:
        source = descriptions[record["job_id"]]
        for evidence in record["match_evidence"]:
            assert source[evidence["source_start"]:evidence["source_end"]] == evidence["text"]
            assert source[evidence["match_start"]:evidence["match_end"]] == evidence["matched_text"]
    expanded = catalog_query(db, request.model_copy(update={"aliases": {"RAG": ["GraphRAG", "RAGFlow"]}}))
    assert expanded["matched_jobs"] == 5
    assert catalog_query(db, request.model_copy(update={"include_preferred": True}))["matched_jobs"] == 4
    with pytest.raises(SnapshotChanged):
        catalog_query(db, request.model_copy(update={"aliases": {"RAG": ["GraphRAG"]}, "snapshot_id": result["snapshot_id"]}))


def test_summary_counts_are_job_deduplicated_and_conditions_not_facts(db, settings):
    descriptions = seed(db, settings)
    req = TechnicalSummaryRequest(aliases={"RAG": ["GraphRAG", "RAGFlow"]}, include_details=True, page_size=2)
    first = summarize_job_technical_mentions(db, req)
    assert first["denominator_jobs"] == 5
    assert first["processed_jobs"] == 8 and first["unprocessed_jobs"] == 0
    assert first["unresolved_jobs"] == 1
    categories = {r["technology"]: r for r in first["categories"]}
    assert categories["python"]["job_count"] == 4
    assert categories["deployment"]["job_count"] == 2  # Standalone bonus Docker excluded.
    assert categories["python"]["condition_job_counts"]["not_required"] == 1
    assert not first["condition_counts_are_verified_requirements"]
    details = []
    page = first
    while True:
        details += page["details"]
        if not page["has_more"]:
            break
        page = summarize_job_technical_mentions(db, req.model_copy(update={"offset": page["next_offset"], "snapshot_id": first["snapshot_id"]}))
    assert len(details) == len({r["key"] for r in details}) == 5
    for detail in details:
        for evidence in detail["technical_mentions"]:
            source = descriptions[detail["job_id"]]
            assert source[evidence["source_start"]:evidence["source_end"]] == evidence["text"]
    alternative = next(e for r in details if r["job_id"] == "alias" for e in r["technical_mentions"] if e["technology"] == "python")
    assert alternative["alternative"] and alternative["needs_review"] and not alternative["verified"]
    import_csv(db, settings, csv_bytes(row("new", description="任职要求：RAG、Python")))
    with pytest.raises(SnapshotChanged):
        summarize_job_technical_mentions(db, req.model_copy(update={"corpus_id": first["corpus_id"]}))


def test_batch_keeps_full_text_and_unknown_coverage(db, settings):
    descriptions = seed(db, settings)
    result = batch_jobs(db, BatchRequest(jobs=[{"job_id": "main"}, {"job_id": "unknown"}]))
    for job in result["results"]:
        assert job["raw"]["description"] == descriptions[job["job_id"]]
        assert not job["source_text_truncated"]
        for s in job["sections"]:
            assert job["raw"]["description"][s["source_start"]:s["source_end"]] == s["text"]
    assert result["results"][1]["section_coverage"]["has_unknown_text"]
    brief = batch_jobs(db, BatchRequest(jobs=[{"job_id": "main"}], sections=["requirements"], include_raw=False))
    assert "raw" not in brief["results"][0]
    assert {s["section_type"] for s in brief["results"][0]["sections"]} == {"requirements"}


def test_partial_and_query_in_unknown_text_is_not_silently_rejected(db, settings):
    import_csv(db, settings, csv_bytes(row(description="Python开发。\n岗位职责：建设RAG系统。")))
    result = catalog_query(db, CatalogRequest(terms=["RAG", "Python"], sections=["responsibilities"], match_mode="ascii_token"))
    assert result["matched_jobs"] == 0
    assert result["unresolved_jobs"] == 1 and not result["section_scope_complete"]


def test_expanding_casefold_retains_original_offsets(db, settings):
    source = "岗位职责：Straße RAG检索。"
    import_csv(db, settings, csv_bytes(row(description=source)))
    result = catalog_query(db, CatalogRequest(terms=["STRASSE"], sections=["responsibilities"]))
    evidence = result["results"][0]["match_evidence"][0]
    assert evidence["matched_text"] == "Straße"
    assert source[evidence["match_start"]:evidence["match_end"]] == "Straße"


def test_mixed_conditions_and_vocabulary_version_invalidate_summary(db, settings, monkeypatch):
    import_csv(db, settings, csv_bytes(row(description="任职要求：RAG；Python优先，Java必须。")))
    request = TechnicalSummaryRequest(include_details=True)
    result = summarize_job_technical_mentions(db, request)
    python = next(e for e in result["details"][0]["technical_mentions"] if e["technology"] == "python")
    assert python["requirement_level"] == "mixed" and python["needs_review"]
    import importlib
    module = importlib.import_module("job_rag.querying.summarize_job_technical_mentions")
    monkeypatch.setattr(module, "VOCABULARY_VERSION", "changed-version")
    with pytest.raises(SnapshotChanged):
        summarize_job_technical_mentions(db, request.model_copy(update={"snapshot_id": result["snapshot_id"]}))


@pytest.mark.parametrize("payload", [
    {"sections": []}, {"sections": ["made_up"]}, {"sections": ["requirements"], "fields": ["title"]},
    {"aliases": {"Python": ["py"]}}, {"terms": ["RAG"], "aliases": {"RAG": [""]}},
    {"include_preferred": True}, {"evidence_limit": 0},
])
def test_invalid_section_query_rejected(payload):
    with pytest.raises(ValidationError):
        CatalogRequest(**payload)


def test_each_mcp_tool_is_defined_in_its_own_file_and_works(settings, monkeypatch):
    original_client = httpx.Client
    with TestClient(create_app(settings)) as api:
        seed(api.app.state.db, settings)
        def handle(request):
            response = api.request(request.method, request.url.path, params=request.url.query.decode(),
                                   content=request.content, headers={"Content-Type": "application/json"})
            return httpx.Response(response.status_code, json=response.json())
        monkeypatch.setattr("job_rag.interfaces.mcp_transport.httpx.Client", lambda **kwargs:
                            original_client(**kwargs, transport=httpx.MockTransport(handle)))
        async def check():
            server = create_mcp()
            tools = await server.list_tools()
            assert len(tools) == 6
            filenames = []
            for tool in tools:
                definition = server._tool_manager.get_tool(tool.name)
                filenames.append(inspect.getfile(definition.fn))
            assert len(set(filenames)) == 6
            result = await server.call_tool("summarize_job_technical_mentions", {"aliases": {"RAG": ["GraphRAG"]}})
            assert "denominator_jobs" in str(result) and "mcp_to_api" in str(result)
            result = await server.call_tool("get_job", {"job_id": "main", "sections": ["requirements"], "include_raw": False})
            assert "source_start" in str(result)
        asyncio.run(check())
